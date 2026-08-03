import json
import random
import threading
import time
import uuid

from core.translation_scheduler import TranslationScheduler


def run_funasr_realtime(pipeline) -> None:
    """Fun-ASR Realtime streaming ASR via the DashScope Recognition WebSocket API.

    Protocol (duplex):
      client -> {"header": {"action": "run-task", ...}, "payload": {...}}
      server -> {"header": {"event": "task-started", ...}}
      client -> binary PCM16 frames (16kHz mono)
      server -> {"header": {"event": "result-generated"},
                 "payload": {"output": {"sentence": {"text", "begin_time",
                             "end_time", "sentence_end"}}}}
      client -> {"header": {"action": "finish-task", ...}, "payload": {"input": {}}}
      server -> {"header": {"event": "task-finished"|"task-failed", ...}}

    Every result-generated carries the FULL text of the current sentence:
    interim events replace the live subtitle line wholesale, sentence_end
    commits the sentence verbatim. No client-side delta computation or
    segmentation anywhere.
    """
    import numpy as np
    import websocket

    settings = pipeline.settings
    sr = int(settings.sample_rate)
    if sr <= 0:
        raise ValueError(f"Invalid sample_rate={sr}")
    if sr not in (8000, 16000):
        print(f"[FunASR] Warning: fun-asr-realtime expects 8/16kHz PCM16. Current sample_rate={sr}.")

    model = (settings.funasr_realtime_model or "fun-asr-realtime").strip()
    url = (
        (settings.funasr_realtime_ws_url or "").strip()
        or "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
    )

    api_key = (settings.funasr_realtime_api_key or "").strip()
    if not api_key:
        raise RuntimeError(
            "FunASR API key is not configured. "
            "Open Settings → Transcription and enter an API key."
        )

    headers = [f"Authorization: Bearer {api_key}"]

    sentence_id = 1
    last_committed = ""
    last_interim = ""

    translation_scheduler = None
    if (
        getattr(pipeline, "translation_enabled", False)
        and getattr(pipeline, "translator", None) is not None
    ):
        translation_scheduler = TranslationScheduler(
            translate=lambda text, interim: pipeline._translate_text(
                text,
                interim=interim,
                record_context=False,
            ),
            commit_final=pipeline._commit_translation,
            on_interim=lambda sid, translated: pipeline.events.on_text(
                sid,
                "",
                translated,
            ),
            on_final=lambda sid, source, translated: pipeline.events.on_text(
                sid,
                source,
                translated,
            ),
            on_final_failure=lambda sid, source: pipeline.events.on_text(
                sid,
                source,
                "[Translation Failed]",
            ),
        )

    event_log = None
    event_log_path = (settings.funasr_realtime_event_log or "").strip()
    if event_log_path:
        try:
            event_log = open(event_log_path, "a", encoding="utf-8")
            print(f"[FunASR] Logging sentence events to: {event_log_path}")
        except Exception as e:
            print(f"[FunASR] Cannot open event log {event_log_path}: {type(e).__name__}: {e}")

    def _trim_for_log(text: str, max_len: int = 180) -> str:
        s = (text or "").replace("\n", "\\n")
        if len(s) <= max_len:
            return s
        return s[:max_len] + f"…(+{len(s) - max_len} chars)"

    def _status_emit(message: str, timeout_ms: int = 0) -> None:
        msg = (message or "").strip()
        if msg:
            print(f"[FunASR] {msg}")
        pipeline.events.on_status(message, int(timeout_ms))

    def _error_emit(message: str) -> None:
        msg = (message or "").strip()
        if msg:
            print(f"[FunASR] ERROR: {msg}")
        pipeline.events.on_error(message)

    def _log_event(kind: str, sentence: dict) -> None:
        if event_log is None:
            return
        try:
            event_log.write(
                json.dumps(
                    {
                        "ts": round(time.time(), 3),
                        "kind": kind,
                        "begin_time": sentence.get("begin_time"),
                        "end_time": sentence.get("end_time"),
                        "text": sentence.get("text") or "",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            event_log.flush()
        except Exception:
            pass

    def _show_interim(text: str) -> None:
        t = (text or "").strip()
        if not t:
            return
        pipeline.events.on_live_text(sentence_id, "", t)
        if translation_scheduler is not None:
            translation_scheduler.submit_interim(sentence_id, t)

    def _commit_sentence(text: str) -> None:
        nonlocal sentence_id, last_committed
        seg = (text or "").strip()
        if not seg or seg == last_committed:
            return
        last_committed = seg
        cid = sentence_id
        if translation_scheduler is not None:
            # Empty translation preserves an already displayed interim result;
            # a row without one renders its standard ellipsis placeholder.
            pipeline.events.on_text(cid, seg, "")
            translation_scheduler.submit_final(cid, seg)
        else:
            pipeline.events.on_text(cid, seg, "")
        sentence_id = cid + 1

    def _build_run_task(task_id: str) -> dict:
        params = {
            "format": "pcm",
            "sample_rate": sr,
            "semantic_punctuation_enabled": bool(
                settings.funasr_realtime_semantic_punctuation
            ),
        }
        # VAD-mode knobs (only effective when semantic punctuation is off)
        max_silence = int(
            settings.funasr_realtime_max_sentence_silence or 0
        )
        if max_silence > 0:
            params["max_sentence_silence"] = max_silence
        if settings.funasr_realtime_multi_threshold:
            params["multi_threshold_mode_enabled"] = True
        lang = (settings.source_language or "").strip()
        if lang:
            params["language_hints"] = [lang]
        return {
            "header": {
                "action": "run-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "asr",
                "function": "recognition",
                "model": model,
                "parameters": params,
                "input": {},
            },
        }

    try:
        max_retries = 6
        retry = 0
        base_backoff_s = 0.5
        max_backoff_s = 8.0

        while getattr(pipeline, "running", False):
            stop_evt = threading.Event()
            task_started_evt = threading.Event()
            err = {"msg": ""}
            listener_thread = None
            session_started_at = None
            ws_app = None
            task_id = uuid.uuid4().hex

            if retry <= 0:
                print(f"[FunASR] Connecting URL: {url}")
                _status_emit("Connecting to FunASR…", 0)
            else:
                attempt = retry + 1
                print(f"[FunASR] Reconnecting URL: {url} ({attempt}/{max_retries})")
                _status_emit(f"Connection lost, reconnecting ({attempt}/{max_retries})…", 0)

            def _on_open(ws, *, stop_evt=stop_evt, task_id=task_id) -> None:
                if stop_evt.is_set() or (not getattr(pipeline, "running", False)):
                    return
                print(f"[FunASR] WebSocket opened: {url}")
                run_task = _build_run_task(task_id)
                try:
                    params = run_task["payload"]["parameters"]
                    print(
                        f"[FunASR] Sending run-task (model={model}, sr={params.get('sample_rate')}, "
                        f"semantic_punct={params.get('semantic_punctuation_enabled')}, "
                        f"hints={params.get('language_hints') or 'auto'})"
                    )
                    ws.send(json.dumps(run_task, ensure_ascii=False))
                except Exception as e:
                    err["msg"] = f"{type(e).__name__}: {e}"
                    _error_emit(f"FunASR: run-task failed: {err['msg']}")
                    stop_evt.set()
                    try:
                        ws.close()
                    except Exception:
                        pass

            def _on_message(ws, message, *, stop_evt=stop_evt, task_started_evt=task_started_evt) -> None:
                nonlocal last_interim
                if stop_evt.is_set() or (not getattr(pipeline, "running", False)):
                    return
                try:
                    data = json.loads(message)
                except Exception:
                    return

                header = data.get("header") or {}
                event = header.get("event")

                if event == "task-started":
                    print(f"[FunASR] task-started task_id={header.get('task_id') or '(unknown)'}")
                    task_started_evt.set()
                    _status_emit("Connected", 1500)
                    return

                if event == "result-generated":
                    payload = data.get("payload") or {}
                    output = payload.get("output") or {}
                    sentence = output.get("sentence")
                    if not isinstance(sentence, dict):
                        return
                    if sentence.get("heartbeat"):
                        return  # keep-alive packet, sentence_id=0 — skip
                    text = (sentence.get("text") or "").strip()
                    if sentence.get("sentence_end"):
                        _log_event("end", sentence)
                        print(f"[FunASR] sentence_end: {_trim_for_log(text, 200)}")
                        _commit_sentence(text)
                        last_interim = ""
                    else:
                        if text != last_interim:
                            _log_event("interim", sentence)
                            last_interim = text
                        _show_interim(text)
                    return

                if event == "task-finished":
                    print("[FunASR] task-finished received")
                    stop_evt.set()
                    try:
                        ws.close()
                    except Exception:
                        pass
                    return

                if event == "task-failed":
                    emsg = (header.get("error_message") or "").strip()
                    ecode = (header.get("error_code") or "").strip()
                    if not emsg:
                        emsg = json.dumps(data, ensure_ascii=False)[:400]
                    err["msg"] = emsg
                    _error_emit(f"FunASR task-failed ({ecode or 'unknown'}): {emsg}")
                    stop_evt.set()
                    try:
                        ws.close()
                    except Exception:
                        pass
                    return

            def _on_error(_ws, error, *, stop_evt=stop_evt) -> None:
                err["msg"] = f"{type(error).__name__}: {error}"
                _error_emit(f"FunASR websocket error: {err['msg']}")
                stop_evt.set()

            def _on_close(_ws, close_status_code, close_msg, *, stop_evt=stop_evt) -> None:
                msg = close_msg if isinstance(close_msg, str) else str(close_msg or "")
                print(
                    f"[FunASR] WebSocket closed: {url} "
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

                # Audio must not start before the task is accepted by the server.
                if not task_started_evt.wait(timeout=5.0):
                    err["msg"] = "Timed out waiting for task-started"
                    _error_emit(f"FunASR: {err['msg']}")
                    stop_evt.set()
                    try:
                        ws_app.close()
                    except Exception:
                        pass
                else:
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
                            try:
                                if not ws_app.sock or not ws_app.sock.connected:
                                    err["msg"] = "WebSocket not connected"
                                    stop_evt.set()
                                    break
                                ws_app.send(pcm16.tobytes(), opcode=websocket.ABNF.OPCODE_BINARY)
                            except Exception as e:
                                err["msg"] = f"{type(e).__name__}: {e}"
                                _error_emit(f"FunASR send failed: {err['msg']}")
                                stop_evt.set()
                                break
                    finally:
                        try:
                            audio_gen.close()
                        except Exception:
                            pass

                    # Surface capture failures as pipeline errors
                    # (otherwise a stopped ScreenCaptureKit stream looks clean).
                    audio_err = getattr(pipeline.audio, "last_error", None)
                    if audio_err:
                        err["msg"] = f"Audio capture failed: {audio_err}"
                        _error_emit(err["msg"])
                        pipeline.running = False
                        stop_evt.set()

                    if ws_app and ws_app.sock and ws_app.sock.connected:
                        try:
                            print("[FunASR] Sending finish-task")
                            ws_app.send(
                                json.dumps(
                                    {
                                        "header": {
                                            "action": "finish-task",
                                            "task_id": task_id,
                                            "streaming": "duplex",
                                        },
                                        "payload": {"input": {}},
                                    },
                                    ensure_ascii=False,
                                )
                            )
                        except Exception as e:
                            print(f"[FunASR] finish-task send failed: {type(e).__name__}: {e}")

                    stop_evt.wait(timeout=3.0)
                    try:
                        if ws_app:
                            ws_app.close()
                    except Exception:
                        pass

            except Exception as e:
                err["msg"] = f"{type(e).__name__}: {e}"
                _error_emit(f"FunASR: {err['msg']}")

            try:
                pipeline.audio.stop()
            except Exception:
                pass

            if listener_thread:
                listener_thread.join(timeout=5.0)
                if listener_thread.is_alive():
                    _error_emit("FunASR: listener thread did not stop in time")
                    pipeline.running = False
                    break

            if not getattr(pipeline, "running", False):
                break

            # An interrupted sentence is dropped on reconnect; the server
            # re-starts recognition state with the next run-task anyway.
            last_interim = ""

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
            print(f"[FunASR] Reconnecting in {backoff:.2f}s (retry {retry}/{max_retries}): {last_err}")
            time.sleep(backoff)

    finally:
        try:
            pipeline.audio.stop()
        except Exception:
            pass
        if translation_scheduler is not None:
            translation_scheduler.shutdown()
        try:
            if event_log is not None:
                event_log.close()
        except Exception:
            pass
