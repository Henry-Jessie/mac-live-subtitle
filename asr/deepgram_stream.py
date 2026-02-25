import random
import threading
import time

from core.config import config

from .segmenter import StreamingSegmenter


def run_deepgram_stream(pipeline) -> None:
    """Deepgram streaming ASR via WebSocket with interim updates + segmentation/translation."""
    import numpy as np
    import websockets
    from deepgram import DeepgramClient
    from deepgram.core.api_error import ApiError
    from deepgram.extensions.types.sockets.listen_v1_control_message import ListenV1ControlMessage
    from deepgram.listen.v1.socket_client import EventType

    client = DeepgramClient()

    sr = int(config.sample_rate)
    if sr <= 0:
        raise ValueError(f"Invalid sample_rate={sr}")

    model = config.deepgram_model or "nova-3"

    connect_kwargs = {
        "model": model,
        "encoding": "linear16",
        "sample_rate": str(sr),
        "channels": "1",
        "interim_results": "true",
        "smart_format": "true",
        "punctuate": "true",
        "endpointing": "400",
        "vad_events": "true",
        "utterance_end_ms": "1000",
    }
    if config.source_language:
        connect_kwargs["language"] = config.source_language
    else:
        connect_kwargs["language"] = "multi"
        connect_kwargs["endpointing"] = "100"

    segmenter = StreamingSegmenter(
        pipeline,
        label="Deepgram",
        join_with_space=True,
        strip_parts=True,
    )

    def _format_ws_exc(exc: Exception) -> str:
        if isinstance(exc, websockets.exceptions.ConnectionClosed):
            code = getattr(exc, "code", None)
            reason = (getattr(exc, "reason", None) or "").strip()
            if reason:
                return f"WebSocket closed (code={code}, reason={reason})"
            return f"WebSocket closed (code={code})"
        return f"{type(exc).__name__}: {exc}"

    def _status_emit(message: str, timeout_ms: int = 0) -> None:
        msg = (message or "").strip()
        if msg:
            print(f"[Deepgram] {msg}")
        try:
            pipeline.signals.status.emit(message, int(timeout_ms))
        except Exception:
            pass

    def _error_emit(message: str) -> None:
        msg = (message or "").strip()
        if msg:
            print(f"[Deepgram] ERROR: {msg}")
        try:
            pipeline.signals.error.emit(message)
        except Exception:
            pass

    try:
        max_retries = 6
        retry = 0
        base_backoff_s = 0.5
        max_backoff_s = 8.0

        while getattr(pipeline, "running", False):
            stop_evt = threading.Event()
            err = {"msg": ""}
            listener_thread = None
            session_started_at = None

            if retry <= 0:
                _status_emit("Connecting to Deepgram…", 0)
            else:
                attempt = retry + 1
                _status_emit(f"Connection lost, reconnecting ({attempt}/{max_retries})…", 0)

            try:
                with client.listen.v1.connect(**connect_kwargs) as conn:

                    def _on_message(event, *, stop_evt=stop_evt) -> None:
                        if stop_evt.is_set() or (not getattr(pipeline, "running", False)):
                            return
                        etype = getattr(event, "type", None)
                        if etype == "Results":
                            try:
                                alt = event.channel.alternatives[0]
                                transcript = (alt.transcript or "").strip()
                            except Exception:
                                transcript = ""
                            if not transcript:
                                return

                            is_final = bool(getattr(event, "is_final", False))
                            speech_final = bool(getattr(event, "speech_final", False))

                            if segmenter.use_llm_segmenter:
                                if is_final:
                                    appended, _lid, snap, _it = segmenter.update(
                                        append_confirmed=transcript,
                                        append_separator=" ",
                                        append_strip=True,
                                        clear_interim=True,
                                    )
                                    if appended:
                                        segmenter.dispatch_llm_if_needed(snap, force_flush=speech_final)
                                else:
                                    segmenter.update(interim=transcript, interim_strip=True)
                            else:
                                if is_final:
                                    segmenter.update(
                                        append_confirmed=transcript,
                                        append_separator=" ",
                                        append_strip=True,
                                        clear_interim=True,
                                    )
                                    segmenter.try_split(force_flush=speech_final)
                                else:
                                    segmenter.update(interim=transcript, interim_strip=True)

                        elif etype == "UtteranceEnd":
                            if segmenter.use_llm_segmenter:
                                with segmenter.state_lock:
                                    snap = segmenter.pending_confirmed
                                if snap.strip():
                                    segmenter.dispatch_llm_if_needed(snap, force_flush=True)
                            else:
                                segmenter.try_split(force_flush=True)

                    def _on_error(exc, *, stop_evt=stop_evt, err=err) -> None:
                        err["msg"] = _format_ws_exc(exc)
                        _error_emit(f"Deepgram stream: {err['msg']}")
                        stop_evt.set()

                    def _on_close(_data, *, stop_evt=stop_evt) -> None:
                        stop_evt.set()

                    session_started_at = time.time()
                    conn.on(EventType.MESSAGE, _on_message)
                    conn.on(EventType.ERROR, _on_error)
                    conn.on(EventType.CLOSE, _on_close)

                    listener_thread = threading.Thread(target=conn.start_listening, daemon=True)
                    listener_thread.start()

                    last_keepalive_at = 0.0
                    keepalive_interval_s = 5.0
                    audio_gen = pipeline.audio.generator()
                    try:
                        for frame in audio_gen:
                            if not getattr(pipeline, "running", False) or stop_evt.is_set():
                                break
                            if frame is None or len(frame) == 0:
                                continue

                            if getattr(pipeline, "_pause_evt", None) is not None and pipeline._pause_evt.is_set():
                                now = time.time()
                                if now - last_keepalive_at >= keepalive_interval_s:
                                    try:
                                        conn.send_control(ListenV1ControlMessage(type="KeepAlive"))
                                        last_keepalive_at = now
                                    except Exception as e:
                                        err["msg"] = _format_ws_exc(e)
                                        _error_emit(f"Deepgram stream keepalive failed: {err['msg']}")
                                        stop_evt.set()
                                        break
                                continue

                            audio_f32 = np.asarray(frame, dtype=np.float32).flatten()
                            pcm16 = (np.clip(audio_f32, -1.0, 1.0) * 32767.0).astype("<i2", copy=False)
                            try:
                                conn.send_media(pcm16.tobytes())
                            except Exception as e:
                                err["msg"] = _format_ws_exc(e)
                                _error_emit(f"Deepgram stream send failed: {err['msg']}")
                                stop_evt.set()
                                break
                    finally:
                        try:
                            audio_gen.close()
                        except Exception:
                            pass

                    try:
                        conn.send_control(ListenV1ControlMessage(type="Finalize"))
                    except Exception:
                        pass
                    try:
                        conn.send_control(ListenV1ControlMessage(type="CloseStream"))
                    except Exception:
                        pass

            except ApiError as e:
                err["msg"] = f"Connect failed (status={e.status_code}): {e.body}"
                _error_emit(f"Deepgram stream: {err['msg']}")
                if e.status_code in (401, 403):
                    pipeline.running = False
                    break
            except Exception as e:
                err["msg"] = _format_ws_exc(e)
                _error_emit(f"Deepgram stream: {err['msg']}")

            try:
                pipeline.audio.stop()
            except Exception:
                pass

            if listener_thread:
                listener_thread.join(timeout=5.0)
                if listener_thread.is_alive():
                    _error_emit("Deepgram stream: listener thread did not stop in time")
                    pipeline.running = False
                    break

            if not getattr(pipeline, "running", False):
                break

            if segmenter.use_llm_segmenter:
                segmenter.flush_pending_local()

            last_err = (err.get("msg") or "").strip()
            if not last_err:
                break

            session_age_s = 0.0
            if session_started_at is not None:
                session_age_s = max(0.0, time.time() - session_started_at)
            if session_age_s >= 20.0:
                retry = 0

            retry += 1
            if retry > max_retries:
                pipeline.running = False
                break

            backoff = min(max_backoff_s, base_backoff_s * (2 ** (retry - 1)))
            backoff *= 1.0 + random.random() * 0.2
            print(f"[Deepgram] Reconnecting in {backoff:.2f}s (retry {retry}/{max_retries}): {last_err}")
            time.sleep(backoff)

    finally:
        try:
            pipeline.audio.stop()
        except Exception:
            pass
        segmenter.shutdown()

