import threading

from PyObjCTools import AppHelper

from core.application_controller import ApplicationController, ApplicationState
from core.pipeline import Pipeline
from ui_macos.events import AppKitPipelineEvents


STOP_TIMEOUT_SECONDS = 15


class NativeApplicationController:
    def __init__(self, settings_store, subtitle_panel):
        self.lifecycle = ApplicationController()
        self.settings_store = settings_store
        self.subtitle_panel = subtitle_panel
        self.state_changed = None
        self.stop_completion = None
        self.start_generation = 0
        self.start_thread = None
        self.stop_thread = None

    @property
    def state(self) -> ApplicationState:
        return self.lifecycle.state

    def toggle_running(self) -> None:
        if self.state is ApplicationState.RUNNING:
            self.lifecycle.pause()
            self._notify_state()
            return

        if self.state is ApplicationState.PAUSED:
            if self.lifecycle.resume():
                self._notify_state()
                return
            self._start_pipeline(preserve_display=True)
            return

        if self.state in {ApplicationState.IDLE, ApplicationState.FAILED}:
            self._start_pipeline(preserve_display=False)

    def stop(self, completion=None) -> None:
        if self.state is ApplicationState.STOPPING:
            if completion is not None:
                self.stop_completion = completion
            return
        self.start_generation += 1
        pipeline = self.lifecycle.begin_stop()
        self.stop_completion = completion
        self._notify_state()
        if pipeline is None:
            self.lifecycle.complete_stop(None)
            self._notify_state()
            self._finish_stop_completion()
            return

        def stop_pipeline():
            pipeline.stop()

        self.stop_thread = threading.Thread(
            target=stop_pipeline,
            daemon=True,
        )
        self.stop_thread.start()
        AppHelper.callLater(
            STOP_TIMEOUT_SECONDS,
            self._stop_timed_out,
            pipeline,
        )

    def _start_pipeline(self, *, preserve_display: bool) -> None:
        self.start_generation += 1
        generation = self.start_generation
        self.lifecycle.begin_start()
        if not preserve_display:
            self.subtitle_panel.clear()
        self.subtitle_panel.show_status("Starting…", timeout_ms=0)
        self._notify_state()

        events = AppKitPipelineEvents(self)

        def create_pipeline():
            try:
                settings = self.settings_store.pipeline_settings()
                pipeline = Pipeline(settings=settings, events=events)
                events.bind_pipeline(pipeline)
                AppHelper.callAfter(
                    self._pipeline_ready,
                    generation,
                    pipeline,
                )
            except Exception as exc:
                AppHelper.callAfter(
                    self._startup_failed,
                    generation,
                    exc,
                )

        self.start_thread = threading.Thread(
            target=create_pipeline,
            daemon=True,
        )
        self.start_thread.start()

    def _pipeline_ready(self, generation: int, pipeline) -> None:
        if (
            generation != self.start_generation
            or self.state is not ApplicationState.STARTING
        ):
            pipeline.stop()
            return
        self.lifecycle.pipeline_ready(pipeline)
        self.subtitle_panel.set_translation_enabled(
            pipeline.translation_enabled
        )
        self.subtitle_panel.show_status("Connected", timeout_ms=1200)
        self._notify_state()

    def _startup_failed(
        self,
        generation: int,
        error: BaseException,
    ) -> None:
        if (
            generation != self.start_generation
            or self.state is not ApplicationState.STARTING
        ):
            return
        message = f"{type(error).__name__}: {error}"
        self.lifecycle.startup_failed(message)
        self.subtitle_panel.show_error(
            f"Initialization failed: {message}",
            timeout_ms=0,
        )
        self._notify_state()

    def _finish_stop_completion(self) -> None:
        completion = self.stop_completion
        self.stop_completion = None
        if completion is not None:
            completion()

    def _stop_timed_out(self, pipeline) -> None:
        if (
            self.state is not ApplicationState.STOPPING
            or not self.lifecycle.accepts(pipeline)
        ):
            return
        self.lifecycle.record_error(
            pipeline,
            f"Stop timed out after {STOP_TIMEOUT_SECONDS} seconds",
        )
        self.pipeline_stopped(pipeline)

    def pipeline_text(
        self,
        pipeline,
        chunk_id: int,
        original: str,
        translated: str,
    ) -> None:
        if self.lifecycle.accepts(pipeline):
            self.subtitle_panel.update_text(
                chunk_id,
                original,
                translated,
            )

    def pipeline_live_text(
        self,
        pipeline,
        chunk_id: int,
        confirmed: str,
        interim: str,
    ) -> None:
        if self.lifecycle.accepts(pipeline):
            self.subtitle_panel.update_live_text(
                chunk_id,
                confirmed,
                interim,
            )

    def pipeline_error(self, pipeline, message: str) -> None:
        if self.lifecycle.record_error(pipeline, message):
            self.subtitle_panel.show_error(
                f"Pipeline error: {self.lifecycle.last_error}",
                timeout_ms=8000,
            )

    def pipeline_status(
        self,
        pipeline,
        message: str,
        timeout_ms: int,
    ) -> None:
        if self.lifecycle.accepts(pipeline):
            self.subtitle_panel.show_status(message, timeout_ms=timeout_ms)

    def pipeline_stopped(self, pipeline) -> None:
        if not self.lifecycle.pipeline_stopped(pipeline):
            return
        if self.lifecycle.last_error:
            self.subtitle_panel.show_error(
                f"Stopped: {self.lifecycle.last_error}",
                timeout_ms=0,
            )
        self._notify_state()
        self._finish_stop_completion()

    def _notify_state(self) -> None:
        if self.state_changed is not None:
            self.state_changed(self.state)
