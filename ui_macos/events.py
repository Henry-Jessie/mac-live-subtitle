from PyObjCTools import AppHelper


class AppKitPipelineEvents:
    def __init__(self, owner):
        self.owner = owner
        self.pipeline = None

    def bind_pipeline(self, pipeline) -> None:
        self.pipeline = pipeline

    def on_text(self, chunk_id: int, original: str, translated: str) -> None:
        AppHelper.callAfter(
            self.owner.pipeline_text,
            self.pipeline,
            chunk_id,
            original,
            translated,
        )

    def on_live_text(
        self,
        chunk_id: int,
        confirmed: str,
        interim: str,
    ) -> None:
        AppHelper.callAfter(
            self.owner.pipeline_live_text,
            self.pipeline,
            chunk_id,
            confirmed,
            interim,
        )

    def on_error(self, message: str) -> None:
        AppHelper.callAfter(
            self.owner.pipeline_error,
            self.pipeline,
            message,
        )

    def on_status(self, message: str, timeout_ms: int) -> None:
        AppHelper.callAfter(
            self.owner.pipeline_status,
            self.pipeline,
            message,
            timeout_ms,
        )

    def on_stopped(self) -> None:
        AppHelper.callAfter(
            self.owner.pipeline_stopped,
            self.pipeline,
        )
