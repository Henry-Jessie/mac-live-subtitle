import threading
from typing import Protocol

from core.audio_capture import AudioCapture
from core.settings import PipelineSettings
from core.translator import Translator


class PipelineEvents(Protocol):
    def on_text(
        self,
        chunk_id: int,
        original: str,
        translated: str,
    ) -> None: ...

    def on_live_text(
        self,
        chunk_id: int,
        confirmed: str,
        interim: str,
    ) -> None: ...

    def on_error(self, message: str) -> None: ...

    def on_status(self, message: str, timeout_ms: int) -> None: ...

    def on_stopped(self) -> None: ...


class Pipeline:
    def __init__(
        self,
        settings: PipelineSettings,
        events: PipelineEvents,
    ):
        self.settings = settings
        self.events = events
        self.running = True
        self._pause_evt = threading.Event()
        self.supports_soft_pause = settings.asr_backend == "funasr_realtime"

        settings.print_summary()

        self.audio = AudioCapture(
            sample_rate=settings.sample_rate,
            step_size=settings.streaming_step_size,
        )

        self.translation_enabled = settings.translation_enabled

        # LLM client needed only when translation is on
        if settings.translation_enabled:
            self.translator = Translator(
                target_lang=settings.target_lang,
                base_url=settings.api_base_url,
                api_key=settings.api_key,
                model=settings.model,
                extra_body=settings.translation_extra_body,
                temperature=settings.translation_temperature,
                debug=self._translation_debug_enabled(),
                thinking=settings.translation_thinking,
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
        return self.settings.translation_debug

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
            self.events.on_text(chunk_id, original, translated)
        except Exception as e:
            self.events.on_text(chunk_id, original, "[Translation Failed]")
            self.events.on_error(
                f"Translation failed: {type(e).__name__}: {e}"
            )

    def _signal_error(self, message: str) -> None:
        msg = (message or "").strip()
        if not msg:
            return
        self.events.on_error(msg)

    def _signal_status(self, message: str, timeout_ms: int = 0) -> None:
        msg = (message or "").strip()
        if not msg:
            return
        self.events.on_status(msg, int(timeout_ms))

    def processing_loop(self):
        try:
            backend = (self.settings.asr_backend or "").strip().lower()

            if backend == "funasr_realtime":
                from asr.funasr_realtime import run_funasr_realtime

                run_funasr_realtime(self)
                return

            self._signal_error(f"Unsupported backend: {backend!r}")

        except Exception as e:
            self._signal_error(f"Pipeline error: {type(e).__name__}: {e}")
        finally:
            self.events.on_stopped()
