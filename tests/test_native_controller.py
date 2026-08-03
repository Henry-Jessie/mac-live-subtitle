import unittest
from unittest.mock import patch

from core.application_controller import ApplicationState
from ui_macos.controller import (
    STOP_TIMEOUT_SECONDS,
    NativeApplicationController,
)


class FakePanel:
    def __init__(self):
        self.events = []
        self.translation_enabled = None

    def clear(self):
        self.events.append(("clear",))

    def show_status(self, message, timeout_ms):
        self.events.append(("status", message, timeout_ms))

    def show_error(self, message, timeout_ms):
        self.events.append(("error", message, timeout_ms))

    def set_translation_enabled(self, enabled):
        self.translation_enabled = enabled

    def update_text(self, *args):
        self.events.append(("text", *args))

    def update_live_text(self, *args):
        self.events.append(("live", *args))


class FakeSettingsStore:
    def pipeline_settings(self):
        return object()


class FakePipeline:
    def __init__(self):
        self.translation_enabled = True
        self.supports_soft_pause = True
        self.started = 0
        self.stopped = 0
        self.paused = 0
        self.resumed = 0

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1

    def pause(self):
        self.paused += 1

    def resume(self):
        self.resumed += 1


class NativeApplicationControllerTests(unittest.TestCase):
    def setUp(self):
        self.panel = FakePanel()
        self.controller = NativeApplicationController(
            FakeSettingsStore(),
            self.panel,
        )
        self.states = []
        self.controller.state_changed = self.states.append
        self.call_later_patcher = patch(
            "ui_macos.controller.AppHelper.callLater"
        )
        self.call_later = self.call_later_patcher.start()
        self.addCleanup(self.call_later_patcher.stop)

    def test_pipeline_callbacks_reject_retired_pipeline(self):
        current = FakePipeline()
        retired = FakePipeline()
        self.controller.lifecycle.begin_start()
        self.controller._pipeline_ready(
            self.controller.start_generation,
            current,
        )

        self.controller.pipeline_text(retired, 1, "late", "")
        self.controller.pipeline_text(current, 1, "current", "")

        self.assertNotIn(("text", 1, "late", ""), self.panel.events)
        self.assertIn(("text", 1, "current", ""), self.panel.events)

    def test_pause_and_resume_update_one_state(self):
        pipeline = FakePipeline()
        self.controller.lifecycle.begin_start()
        self.controller._pipeline_ready(
            self.controller.start_generation,
            pipeline,
        )

        self.controller.toggle_running()
        self.assertIs(self.controller.state, ApplicationState.PAUSED)
        self.assertEqual(pipeline.paused, 1)

        self.controller.toggle_running()
        self.assertIs(self.controller.state, ApplicationState.RUNNING)
        self.assertEqual(pipeline.resumed, 1)

    def test_stop_runs_pipeline_work_outside_main_callback(self):
        pipeline = FakePipeline()
        self.controller.lifecycle.begin_start()
        self.controller._pipeline_ready(
            self.controller.start_generation,
            pipeline,
        )
        callbacks = []

        with patch(
            "ui_macos.controller.AppHelper.callAfter",
            side_effect=lambda callback, *args: callback(*args),
        ):
            self.controller.stop(lambda: callbacks.append("done"))
            self.controller.stop_thread.join(timeout=1)

        self.assertIs(self.controller.state, ApplicationState.STOPPING)
        self.assertEqual(pipeline.stopped, 1)
        self.assertEqual(callbacks, [])

        self.controller.pipeline_stopped(pipeline)

        self.assertIs(self.controller.state, ApplicationState.IDLE)
        self.assertEqual(callbacks, ["done"])

        _, watchdog, scheduled_pipeline = self.call_later.call_args.args
        watchdog(scheduled_pipeline)
        self.assertIs(self.controller.state, ApplicationState.IDLE)
        self.assertEqual(callbacks, ["done"])

    def test_stop_timeout_detaches_pipeline_and_completes(self):
        pipeline = FakePipeline()
        self.controller.lifecycle.begin_start()
        self.controller._pipeline_ready(
            self.controller.start_generation,
            pipeline,
        )
        callbacks = []

        self.controller.stop(lambda: callbacks.append("done"))
        self.controller.stop_thread.join(timeout=1)
        delay, watchdog, scheduled_pipeline = self.call_later.call_args.args

        self.assertEqual(delay, STOP_TIMEOUT_SECONDS)
        self.assertIs(scheduled_pipeline, pipeline)
        watchdog(scheduled_pipeline)

        self.assertIs(self.controller.state, ApplicationState.FAILED)
        self.assertIsNone(self.controller.lifecycle.pipeline)
        self.assertEqual(callbacks, ["done"])
        self.assertIn(
            (
                "error",
                f"Stopped: Stop timed out after {STOP_TIMEOUT_SECONDS} seconds",
                0,
            ),
            self.panel.events,
        )

        self.controller.pipeline_stopped(pipeline)
        self.assertEqual(callbacks, ["done"])

    def test_stop_preserves_errors_until_pipeline_stopped(self):
        pipeline = FakePipeline()
        self.controller.lifecycle.begin_start()
        self.controller._pipeline_ready(
            self.controller.start_generation,
            pipeline,
        )

        self.controller.stop()
        self.controller.stop_thread.join(timeout=1)
        self.controller.pipeline_error(pipeline, "teardown failed")
        self.controller.pipeline_stopped(pipeline)

        self.assertIs(self.controller.state, ApplicationState.FAILED)
        self.assertIn(
            ("error", "Stopped: teardown failed", 0),
            self.panel.events,
        )

    def test_cancelled_start_does_not_attach_late_pipeline(self):
        self.controller.lifecycle.begin_start()
        generation = self.controller.start_generation
        self.controller.stop()
        late_pipeline = FakePipeline()

        self.controller._pipeline_ready(generation, late_pipeline)

        self.assertIs(self.controller.state, ApplicationState.IDLE)
        self.assertIsNone(self.controller.lifecycle.pipeline)
        self.assertEqual(late_pipeline.started, 0)
        self.assertEqual(late_pipeline.stopped, 1)


if __name__ == "__main__":
    unittest.main()
