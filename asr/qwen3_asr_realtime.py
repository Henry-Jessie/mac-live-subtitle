import base64
import json
import random
import threading
import time

from core.config import config

from .segmenter import StreamingSegmenter


def run_qwen3_asr_realtime(pipeline) -> None:
    """Qwen3 ASR Realtime streaming ASR via WebSocket with interim updates + segmentation/translation."""
    import numpy as np
    import os
    import websocket

    sr = int(config.sample_rate)
    if sr <= 0:
        raise ValueError(f"Invalid sample_rate={sr}")
    if sr != 16000:
        print(f"[Pipeline] Warning: Qwen3 ASR Realtime expects 16kHz PCM16. Current sample_rate={sr}.")

    model = (config.qwen3_asr_realtime_model or "qwen3-asr-flash-realtime").strip()
    base_url = (config.qwen3_asr_realtime_ws_url or "").strip() or "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime"
    url = base_url
    if "model=" not in url:
        joiner = "&" if "?" in url else "?"
        url = f"{url}{joiner}model={model}"

    api_key = (config.qwen3_asr_realtime_api_key or "").strip()
    if not api_key:
        env_name = (config.qwen3_asr_realtime_api_key_env or "DASHSCOPE_API_KEY").strip()
        api_key = (os.getenv(env_name) or "").strip()
    if not api_key:
        raise RuntimeError(
            "Qwen3 ASR Realtime API key not found. Set env var "
            f"${config.qwen3_asr_realtime_api_key_env or 'DASHSCOPE_API_KEY'} "
            "or configure [transcription] qwen3_asr_realtime_api_key."
        )

    headers = [
        f"Authorization: Bearer {api_key}",
        "OpenAI-Beta: realtime=v1",
    ]

    segmenter = StreamingSegmenter(
        pipeline,
        label="Qwen3 ASR",
        join_with_space=False,
        strip_parts=False,
    )

    current_item_id: str | None = None
    utt_last_text = ""

    def _trim_for_log(text: str, max_len: int = 180) -> str:
        s = (text or "").replace("\n", "\\n")
        if len(s) <= max_len:
            return s
        return s[:max_len] + f"…(+{len(s) - max_len} chars)"

    def _status_emit(message: str, timeout_ms: int = 0) -> None:
        msg = (message or "").strip()
        if msg:
            print(f"[Qwen3 ASR] {msg}")
        try:
            pipeline.signals.status.emit(message, int(timeout_ms))
        except Exception:
            pass

    def _error_emit(message: str) -> None:
        msg = (message or "").strip()
        if msg:
            print(f"[Qwen3 ASR] ERROR: {msg}")
        try:
            pipeline.signals.error.emit(message)
        except Exception:
            pass

    def _new_event_id() -> str:
        return f"event_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"

    def _build_session_update() -> dict:
        session: dict = {
            "modalities": ["text"],
            "input_audio_format": "pcm",
            "sample_rate": sr,
            "input_audio_transcription": {},
        }
        lang = (config.source_language or "").strip()
        if lang:
            session["input_audio_transcription"]["language"] = lang
        else:
            session["input_audio_transcription"].pop("language", None)

        if config.qwen3_asr_realtime_server_vad:
            session["turn_detection"] = {
                "type": "server_vad",
                "threshold": float(config.qwen3_asr_realtime_vad_threshold),
                "silence_duration_ms": int(config.qwen3_asr_realtime_silence_duration_ms),
            }
        else:
            session["turn_detection"] = None

        return {
            "event_id": _new_event_id(),
            "type": "session.update",
            "session": session,
        }

    try:
        max_retries = 6
        retry = 0
        base_backoff_s = 0.5
        max_backoff_s = 8.0

        while getattr(pipeline, "running", False):
            stop_evt = threading.Event()
            session_ready_evt = threading.Event()
            err = {"msg": ""}
            listener_thread = None
            session_started_at = None
            ws_app = None

            if retry <= 0:
                print(f"[Qwen3 ASR] Connecting URL: {url}")
                _status_emit("Connecting to Qwen3 ASR…", 0)
            else:
                attempt = retry + 1
                print(f"[Qwen3 ASR] Reconnecting URL: {url} ({attempt}/{max_retries})")
                _status_emit(f"Connection lost, reconnecting ({attempt}/{max_retries})…", 0)

            def _get_item_id(payload: dict) -> str | None:
                val = payload.get("item_id")
                if isinstance(val, str) and val.strip():
                    return val.strip()
                item = payload.get("item")
                if isinstance(item, dict):
                    v2 = item.get("id")
                    if isinstance(v2, str) and v2.strip():
                        return v2.strip()
                return None

            def _on_open(ws, *, stop_evt=stop_evt) -> None:
                if stop_evt.is_set() or (not getattr(pipeline, "running", False)):
                    return
                print(f"[Qwen3 ASR] WebSocket opened: {url}")
                _status_emit("Connected", 1500)

                update_evt = _build_session_update()
                try:
                    sess = update_evt.get("session") or {}
                    turn = sess.get("turn_detection")
                    vad_desc = "server_vad" if isinstance(turn, dict) else "manual"
                    lang = (sess.get("input_audio_transcription") or {}).get("language") or "auto"
                    print(f"[Qwen3 ASR] Sending session.update (vad={vad_desc}, lang={lang}, sr={sr})")
                except Exception:
                    print("[Qwen3 ASR] Sending session.update")

                try:
                    ws.send(json.dumps(update_evt, ensure_ascii=False))
                except Exception as e:
                    err["msg"] = f"{type(e).__name__}: {e}"
                    _error_emit(f"Qwen3 ASR: session.update failed: {err['msg']}")
                    stop_evt.set()
                    try:
                        ws.close()
                    except Exception:
                        pass

            def _on_message(ws, message, *, stop_evt=stop_evt) -> None:
                nonlocal current_item_id, utt_last_text
                if stop_evt.is_set() or (not getattr(pipeline, "running", False)):
                    return
                try:
                    data = json.loads(message)
                except Exception:
                    return

                etype = data.get("type")
                if etype == "session.created":
                    sid = ""
                    sess = data.get("session")
                    if isinstance(sess, dict):
                        sid = (sess.get("id") or "").strip()
                    print(f"[Qwen3 ASR] session.created id={sid or '(unknown)'}")
                    return

                if etype == "session.updated":
                    sid = ""
                    sess = data.get("session")
                    if isinstance(sess, dict):
                        sid = (sess.get("id") or "").strip()
                    print(f"[Qwen3 ASR] session.updated id={sid or '(unknown)'}")
                    session_ready_evt.set()
                    return

                if etype == "error":
                    try:
                        print(f"[Qwen3 ASR] error event: {json.dumps(data, ensure_ascii=False)}")
                    except Exception:
                        print("[Qwen3 ASR] error event (failed to serialize)")

                    emsg = ""
                    err_obj = data.get("error")
                    if isinstance(err_obj, dict):
                        emsg = (err_obj.get("message") or err_obj.get("msg") or "").strip()
                    if not emsg:
                        emsg = (data.get("message") or "").strip()
                    err["msg"] = emsg or json.dumps(data, ensure_ascii=False)[:400]
                    _error_emit(f"Qwen3 ASR: {err['msg']}")
                    stop_evt.set()
                    try:
                        ws.close()
                    except Exception:
                        pass
                    return

                if etype == "input_audio_buffer.speech_started":
                    item_id = _get_item_id(data)
                    ms = data.get("audio_start_ms")
                    print(f"[Qwen3 ASR] VAD speech_started item_id={item_id or '(unknown)'} audio_start_ms={ms}")
                    if item_id and item_id != current_item_id:
                        current_item_id = item_id
                        utt_last_text = ""
                        segmenter.update(interim="", interim_strip=False, emit=False)
                    return

                if etype == "input_audio_buffer.speech_stopped":
                    item_id = _get_item_id(data)
                    ms = data.get("audio_end_ms")
                    print(f"[Qwen3 ASR] VAD speech_stopped item_id={item_id or '(unknown)'} audio_end_ms={ms}")
                    return

                if etype == "conversation.item.input_audio_transcription.failed":
                    item_id = _get_item_id(data)
                    emsg = ""
                    err_obj = data.get("error")
                    if isinstance(err_obj, dict):
                        emsg = (err_obj.get("message") or err_obj.get("msg") or "").strip()
                    if not emsg:
                        emsg = json.dumps(data, ensure_ascii=False)[:400]
                    try:
                        print(
                            f"[Qwen3 ASR] transcription.failed item_id={item_id or '(unknown)'}: "
                            f"{json.dumps(data, ensure_ascii=False)[:800]}"
                        )
                    except Exception:
                        print(
                            f"[Qwen3 ASR] transcription.failed item_id={item_id or '(unknown)'} "
                            "(failed to serialize)"
                        )
                    _error_emit(f"Qwen3 ASR utterance failed: {emsg}")
                    if item_id and item_id == current_item_id:
                        utt_last_text = ""
                        segmenter.update(interim="", interim_strip=False, emit=False)
                    return

                if etype == "conversation.item.input_audio_transcription.text":
                    item_id = _get_item_id(data)
                    text = data.get("text")
                    stash = data.get("stash")
                    text = text if isinstance(text, str) else ""
                    stash = stash if isinstance(stash, str) else ""

                    if item_id and item_id != current_item_id:
                        current_item_id = item_id
                        utt_last_text = ""
                        segmenter.update(interim="", interim_strip=False, emit=False)

                    delta = ""
                    if text.startswith(utt_last_text):
                        delta = text[len(utt_last_text) :]
                        utt_last_text = text
                    elif utt_last_text and utt_last_text.startswith(text):
                        delta = ""
                    else:
                        utt_last_text = text
                        delta = ""

                    appended, _lid, snap, _it = segmenter.update(
                        append_confirmed=delta if delta else None,
                        append_separator="",
                        append_strip=False,
                        interim=stash or "",
                        interim_strip=False,
                    )

                    if appended:
                        if segmenter.use_llm_segmenter:
                            segmenter.dispatch_llm_if_needed(snap)
                        else:
                            segmenter.try_split(force_flush=False)
                    return

                if etype == "conversation.item.input_audio_transcription.completed":
                    item_id = _get_item_id(data)
                    transcript = data.get("transcript")
                    transcript = transcript if isinstance(transcript, str) else ""
                    transcript = transcript.strip()

                    if transcript:
                        print(
                            f"[Qwen3 ASR] completed item_id={item_id or '(unknown)'} "
                            f"transcript={_trim_for_log(transcript, 400)}"
                        )
                    else:
                        print(f"[Qwen3 ASR] completed item_id={item_id or '(unknown)'} (empty transcript)")

                    if item_id and item_id != current_item_id:
                        current_item_id = item_id
                        utt_last_text = ""

                    tail = ""
                    if transcript:
                        base = utt_last_text
                        if base:
                            common_len = 0
                            max_common = min(len(base), len(transcript))
                            while common_len < max_common and base[common_len] == transcript[common_len]:
                                common_len += 1
                            tail = transcript[common_len:]
                        else:
                            tail = transcript

                    utt_last_text = ""
                    appended, _lid, snap, _it = segmenter.update(
                        append_confirmed=tail if tail else None,
                        append_separator="",
                        append_strip=False,
                        clear_interim=True,
                    )

                    if appended:
                        if segmenter.use_llm_segmenter:
                            segmenter.dispatch_llm_if_needed(snap, force_flush=True)
                        else:
                            segmenter.try_split(force_flush=True)
                    else:
                        # No new text appended but utterance ended —
                        # flush whatever remains in the buffer.
                        if segmenter.use_llm_segmenter:
                            with segmenter.state_lock:
                                remaining = segmenter.pending_confirmed
                            if remaining.strip():
                                segmenter.dispatch_llm_if_needed(remaining, force_flush=True)
                    return

                if etype == "session.finished":
                    print("[Qwen3 ASR] session.finished received; closing WebSocket")
                    stop_evt.set()
                    try:
                        ws.close()
                    except Exception:
                        pass
                    return

            def _on_error(_ws, error, *, stop_evt=stop_evt) -> None:
                err["msg"] = f"{type(error).__name__}: {error}"
                _error_emit(f"Qwen3 ASR websocket error: {err['msg']}")
                stop_evt.set()

            def _on_close(_ws, close_status_code, close_msg, *, stop_evt=stop_evt) -> None:
                msg = close_msg if isinstance(close_msg, str) else str(close_msg or "")
                print(
                    f"[Qwen3 ASR] WebSocket closed: {url} "
                    f"(code={close_status_code}, msg={_trim_for_log(msg, 200)})"
                )
                stop_evt.set()

            try:
                ws_app = websocket.WebSocketApp(
                    url,
                    header=headers,
                    on_open=_on_open,
                    on_message=_on_message,
                    on_error=_on_error,
                    on_close=_on_close,
                )
                session_started_at = time.time()

                def _run_ws() -> None:
                    try:
                        ws_app.run_forever(ping_interval=10, ping_timeout=5)
                    except TypeError:
                        ws_app.run_forever()

                listener_thread = threading.Thread(target=_run_ws, daemon=True)
                listener_thread.start()

                session_ready_evt.wait(timeout=3.0)

                audio_gen = pipeline.audio.generator()
                try:
                    for frame in audio_gen:
                        if not getattr(pipeline, "running", False) or stop_evt.is_set():
                            break
                        if frame is None or len(frame) == 0:
                            continue

                        if getattr(pipeline, "_pause_evt", None) is not None and pipeline._pause_evt.is_set():
                            continue

                        audio_f32 = np.asarray(frame, dtype=np.float32).flatten()
                        pcm16 = (np.clip(audio_f32, -1.0, 1.0) * 32767.0).astype("<i2", copy=False)
                        audio_b64 = base64.b64encode(pcm16.tobytes()).decode("ascii")
                        evt = {
                            "event_id": _new_event_id(),
                            "type": "input_audio_buffer.append",
                            "audio": audio_b64,
                        }
                        try:
                            if not ws_app.sock or not ws_app.sock.connected:
                                err["msg"] = "WebSocket not connected"
                                stop_evt.set()
                                break
                            ws_app.send(json.dumps(evt, ensure_ascii=False))
                        except Exception as e:
                            err["msg"] = f"{type(e).__name__}: {e}"
                            _error_emit(f"Qwen3 ASR send failed: {err['msg']}")
                            stop_evt.set()
                            break
                finally:
                    try:
                        audio_gen.close()
                    except Exception:
                        pass

                if ws_app and ws_app.sock and ws_app.sock.connected:
                    try:
                        print("[Qwen3 ASR] Sending session.finish")
                        ws_app.send(json.dumps({"event_id": _new_event_id(), "type": "session.finish"}))
                    except Exception as e:
                        print(f"[Qwen3 ASR] session.finish send failed: {type(e).__name__}: {e}")

                stop_evt.wait(timeout=3.0)
                try:
                    if ws_app:
                        ws_app.close()
                except Exception:
                    pass

            except Exception as e:
                err["msg"] = f"{type(e).__name__}: {e}"
                _error_emit(f"Qwen3 ASR: {err['msg']}")

            try:
                pipeline.audio.stop()
            except Exception:
                pass

            if listener_thread:
                listener_thread.join(timeout=5.0)
                if listener_thread.is_alive():
                    _error_emit("Qwen3 ASR: listener thread did not stop in time")
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
            print(f"[Qwen3 ASR] Reconnecting in {backoff:.2f}s (retry {retry}/{max_retries}): {last_err}")
            time.sleep(backoff)

    finally:
        try:
            pipeline.audio.stop()
        except Exception:
            pass
        segmenter.shutdown()

