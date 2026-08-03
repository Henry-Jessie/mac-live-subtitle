from enum import Enum
from typing import Protocol


class ApplicationState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    FAILED = "failed"


class ManagedPipeline(Protocol):
    supports_soft_pause: bool

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...


class ApplicationController:
    def __init__(self) -> None:
        self.state = ApplicationState.IDLE
        self.pipeline: ManagedPipeline | None = None
        self.last_error = ""

    def begin_start(self) -> None:
        if self.state not in {
            ApplicationState.IDLE,
            ApplicationState.PAUSED,
            ApplicationState.FAILED,
        }:
            raise RuntimeError(f"Cannot start from state {self.state.value}")
        if self.pipeline is not None:
            raise RuntimeError("Cannot create a second pipeline")
        self.last_error = ""
        self.state = ApplicationState.STARTING

    def pipeline_ready(self, pipeline: ManagedPipeline) -> None:
        if self.state is not ApplicationState.STARTING:
            raise RuntimeError(f"Pipeline became ready in state {self.state.value}")
        self.pipeline = pipeline
        pipeline.start()
        self.state = ApplicationState.RUNNING

    def startup_failed(self, message: str) -> None:
        if self.state is not ApplicationState.STARTING:
            raise RuntimeError(f"Pipeline startup failed in state {self.state.value}")
        self.last_error = message.strip()
        self.state = ApplicationState.FAILED

    def pause(self) -> None:
        if self.state is not ApplicationState.RUNNING or self.pipeline is None:
            raise RuntimeError(f"Cannot pause from state {self.state.value}")
        if self.pipeline.supports_soft_pause:
            self.pipeline.pause()
        else:
            self.pipeline.stop()
            self.pipeline = None
        self.state = ApplicationState.PAUSED

    def resume(self) -> bool:
        if self.state is not ApplicationState.PAUSED:
            raise RuntimeError(f"Cannot resume from state {self.state.value}")
        if self.pipeline is None:
            return False
        self.pipeline.resume()
        self.state = ApplicationState.RUNNING
        return True

    def begin_stop(self) -> ManagedPipeline | None:
        pipeline = self.pipeline
        self.last_error = ""
        self.state = ApplicationState.STOPPING
        return pipeline

    def complete_stop(self, pipeline: ManagedPipeline | None) -> bool:
        if pipeline is not None and not self.accepts(pipeline):
            return False
        self.pipeline = None
        self.state = ApplicationState.IDLE
        return True

    def accepts(self, pipeline: ManagedPipeline) -> bool:
        return pipeline is self.pipeline

    def record_error(self, pipeline: ManagedPipeline, message: str) -> bool:
        if not self.accepts(pipeline):
            return False
        normalized = message.strip()
        if not normalized:
            return False
        self.last_error = normalized
        return True

    def pipeline_stopped(self, pipeline: ManagedPipeline) -> bool:
        if not self.accepts(pipeline):
            return False
        self.pipeline = None
        self.state = (
            ApplicationState.FAILED
            if self.last_error
            else ApplicationState.IDLE
        )
        return True
