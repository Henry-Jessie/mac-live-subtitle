import threading

from PyQt6.QtCore import QObject, pyqtSignal

from core.audio_capture import AudioCapture
from core.config import config
from core.translator import Translator


class WorkerSignals(QObject):
    update_text = pyqtSignal(int, str, str)  # (chunk_id, original, translated)
    update_live_text = pyqtSignal(int, str, str)  # (chunk_id, confirmed, interim)
    error = pyqtSignal(str)  # (message,)
    status = pyqtSignal(str, int)  # (message, timeout_ms)
    stopped = pyqtSignal()  # processing loop ended


class Pipeline(QObject):
    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        self.running = True
        self._pause_evt = threading.Event()
        self.supports_soft_pause = config.asr_backend == "funasr_realtime"

        config.print_config()

        self.audio = AudioCapture(
            device_index=config.device_index,
            sample_rate=config.sample_rate,
            step_size=config.streaming_step_size,
        )

        self.translation_enabled = config.translation_enabled

        # LLM client needed only when translation is on
        if config.translation_enabled:
            self.translator = Translator(
                target_lang=config.target_lang,
                base_url=config.api_base_url,
                api_key=config.api_key,
                model=config.model,
                extra_body=config.translation_extra_body,
                temperature=config.translation_temperature,
                debug=self._translation_debug_enabled(),
                thinking=config.translation_thinking,
            )
        else:
            self.translator = None

        self.thread = None

    def start(self):
        """Start the processing pipeline in a dedicated thread."""
        self.thread = threading.Thread(target=self.processing_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        try:
            self._pause_evt.clear()
        except Exception:
            pass
        try:
            self.audio.stop()
        except Exception:
            pass
        try:
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=2)
        except Exception:
            pass

    def pause(self):
        """Soft pause (keep backend alive) when supported."""
        if not self.supports_soft_pause:
            return
        self._pause_evt.set()

    def resume(self):
        """Resume from soft pause when supported."""
        if not self.supports_soft_pause:
            return
        self._pause_evt.clear()

    def _translation_debug_enabled(self) -> bool:
        try:
            val = (config._get("translation", "debug", "") or "").strip().lower()
            if val in ("true", "1", "yes", "on"):
                return True
            if val in ("false", "0", "no", "off"):
                return False
        except Exception:
            pass
        return False

    def _run_translation(self, text: str, chunk_id: int, trailing_context: str | None = None, interim: bool = False):
        # interim translations only refresh the translation slot of the live
        # line (empty original keeps the growing source text untouched) and
        # are fully overwritten by the next interim or the final translation.
        original = "" if interim else text
        try:
            translated = self.translator.translate(
                text,
                debug=self._translation_debug_enabled(),
                trailing_context=trailing_context,
                interim=interim,
            )
            self.signals.update_text.emit(chunk_id, original, translated)
        except Exception as e:
            self.signals.update_text.emit(chunk_id, original, "[Translation Failed]")
            try:
                self.signals.error.emit(f"Translation failed: {type(e).__name__}: {e}")
            except Exception:
                pass

    def _signal_error(self, message: str) -> None:
        msg = (message or "").strip()
        if not msg:
            return
        try:
            self.signals.error.emit(msg)
        except Exception:
            pass

    def _signal_status(self, message: str, timeout_ms: int = 0) -> None:
        msg = (message or "").strip()
        if not msg:
            return
        try:
            self.signals.status.emit(msg, int(timeout_ms))
        except Exception:
            pass

    def processing_loop(self):
        try:
            backend = (config.asr_backend or "").strip().lower()

            if backend == "funasr_realtime":
                from asr.funasr_realtime import run_funasr_realtime

                run_funasr_realtime(self)
                return

            self._signal_error(f"Unsupported backend: {backend!r}")

        except Exception as e:
            self._signal_error(f"Pipeline error: {type(e).__name__}: {e}")
        finally:
            try:
                self.signals.stopped.emit()
            except Exception:
                pass
