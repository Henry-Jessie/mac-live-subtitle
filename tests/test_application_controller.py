import unittest

from core.application_controller import ApplicationController, ApplicationState


class FakePipeline:
    def __init__(self, *, supports_soft_pause: bool = True):
        self.supports_soft_pause = supports_soft_pause
        self.started = 0
        self.stopped = 0
        self.paused = 0
        self.resumed = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def pause(self) -> None:
        self.paused += 1

    def resume(self) -> None:
        self.resumed += 1


class ApplicationControllerTests(unittest.TestCase):
    def test_soft_pause_lifecycle(self):
        controller = ApplicationController()
        pipeline = FakePipeline()

        controller.begin_start()
        self.assertIs(controller.state, ApplicationState.STARTING)

        controller.pipeline_ready(pipeline)
        self.assertIs(controller.state, ApplicationState.RUNNING)
        self.assertEqual(pipeline.started, 1)

        controller.pause()
        self.assertIs(controller.state, ApplicationState.PAUSED)
        self.assertEqual(pipeline.paused, 1)

        self.assertTrue(controller.resume())
        self.assertIs(controller.state, ApplicationState.RUNNING)
        self.assertEqual(pipeline.resumed, 1)

        controller.stop()
        self.assertIs(controller.state, ApplicationState.IDLE)
        self.assertIsNone(controller.pipeline)
        self.assertEqual(pipeline.stopped, 1)

    def test_hard_pause_requires_a_new_pipeline(self):
        controller = ApplicationController()
        pipeline = FakePipeline(supports_soft_pause=False)

        controller.begin_start()
        controller.pipeline_ready(pipeline)
        controller.pause()

        self.assertIs(controller.state, ApplicationState.PAUSED)
        self.assertIsNone(controller.pipeline)
        self.assertEqual(pipeline.stopped, 1)
        self.assertFalse(controller.resume())

        controller.begin_start()
        self.assertIs(controller.state, ApplicationState.STARTING)

    def test_stale_pipeline_events_are_rejected(self):
        controller = ApplicationController()
        current = FakePipeline()
        retired = FakePipeline()

        controller.begin_start()
        controller.pipeline_ready(current)

        self.assertFalse(controller.record_error(retired, "late error"))
        self.assertFalse(controller.pipeline_stopped(retired))
        self.assertIs(controller.state, ApplicationState.RUNNING)
        self.assertIs(controller.pipeline, current)

        self.assertTrue(controller.record_error(current, "network failed"))
        self.assertTrue(controller.pipeline_stopped(current))
        self.assertIs(controller.state, ApplicationState.FAILED)
        self.assertEqual(controller.last_error, "network failed")

    def test_startup_failure_can_restart(self):
        controller = ApplicationController()

        controller.begin_start()
        controller.startup_failed("missing key")
        self.assertIs(controller.state, ApplicationState.FAILED)
        self.assertEqual(controller.last_error, "missing key")

        controller.begin_start()
        self.assertIs(controller.state, ApplicationState.STARTING)
        self.assertEqual(controller.last_error, "")

    def test_stop_can_complete_asynchronously(self):
        controller = ApplicationController()
        pipeline = FakePipeline()
        controller.begin_start()
        controller.pipeline_ready(pipeline)

        stopping = controller.begin_stop()
        self.assertIs(stopping, pipeline)
        self.assertIs(controller.state, ApplicationState.STOPPING)
        self.assertIs(controller.pipeline, pipeline)

        pipeline.stop()
        self.assertTrue(controller.complete_stop(pipeline))
        self.assertIs(controller.state, ApplicationState.IDLE)
        self.assertIsNone(controller.pipeline)
        self.assertEqual(pipeline.stopped, 1)


if __name__ == "__main__":
    unittest.main()
