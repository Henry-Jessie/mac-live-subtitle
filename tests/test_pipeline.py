import unittest
from unittest.mock import patch

from core.pipeline import Pipeline
from core.settings import PipelineSettings


def make_settings(**overrides) -> PipelineSettings:
    values = {
        "asr_backend": "unsupported",
        "audio_capture_backend": "native",
        "sample_rate": 16000,
        "streaming_step_size": 0.2,
        "translation_enabled": False,
        "target_lang": "Chinese",
        "api_base_url": "https://api.example.test/v1",
        "api_key": None,
        "model": "test-model",
        "translation_extra_body": None,
        "translation_temperature": 1.0,
        "translation_debug": False,
        "translation_thinking": None,
        "funasr_realtime_model": "fun-asr-realtime",
        "funasr_realtime_ws_url": "wss://example.test/asr",
        "funasr_realtime_api_key": None,
        "funasr_realtime_event_log": "",
        "funasr_realtime_semantic_punctuation": True,
        "funasr_realtime_max_sentence_silence": 0,
        "funasr_realtime_multi_threshold": False,
        "source_language": None,
    }
    values.update(overrides)
    return PipelineSettings(**values)


class RecordingEvents:
    def __init__(self):
        self.text = []
        self.live_text = []
        self.errors = []
        self.statuses = []
        self.stop_count = 0

    def on_text(self, chunk_id, original, translated):
        self.text.append((chunk_id, original, translated))

    def on_live_text(self, chunk_id, confirmed, interim):
        self.live_text.append((chunk_id, confirmed, interim))

    def on_error(self, message):
        self.errors.append(message)

    def on_status(self, message, timeout_ms):
        self.statuses.append((message, timeout_ms))

    def on_stopped(self):
        self.stop_count += 1


class FakeAudioCapture:
    def __init__(self, sample_rate, step_size):
        self.sample_rate = sample_rate
        self.step_size = step_size
        self.stopped = 0

    def stop(self):
        self.stopped += 1


def create_fake_audio_capture(
    backend,
    *,
    sample_rate,
    step_size,
):
    capture = FakeAudioCapture(sample_rate, step_size)
    capture.backend = backend
    return capture


class FakeTranslator:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.commits = []

    def translate(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return f"translated:{text}"

    def commit_translation(self, source, translated):
        self.commits.append((source, translated))


class PipelineTests(unittest.TestCase):
    def test_processing_loop_reports_through_plain_event_sink(self):
        events = RecordingEvents()
        settings = make_settings()

        with patch(
            "core.pipeline.create_audio_capture",
            side_effect=create_fake_audio_capture,
        ):
            pipeline = Pipeline(settings=settings, events=events)

        pipeline.processing_loop()

        self.assertEqual(
            events.errors,
            ["Unsupported backend: 'unsupported'"],
        )
        self.assertEqual(events.stop_count, 1)

    def test_translation_helpers_delegate_to_translator(self):
        events = RecordingEvents()
        settings = make_settings(
            translation_enabled=True,
            api_key="translation-secret",
        )

        with (
            patch(
                "core.pipeline.create_audio_capture",
                side_effect=create_fake_audio_capture,
            ),
            patch("core.pipeline.Translator", FakeTranslator),
        ):
            pipeline = Pipeline(settings=settings, events=events)

        translated = pipeline._translate_text(
            "growing",
            trailing_context="earlier draft",
            interim=True,
            record_context=False,
        )
        pipeline._commit_translation("growing", translated)

        self.assertEqual(translated, "translated:growing")
        self.assertEqual(
            pipeline.translator.calls,
            [
                (
                    "growing",
                    {
                        "debug": False,
                        "trailing_context": "earlier draft",
                        "interim": True,
                        "record_context": False,
                    },
                )
            ],
        )
        self.assertEqual(
            pipeline.translator.commits,
            [("growing", "translated:growing")],
        )

    def test_pause_resume_and_stop_do_not_use_qt(self):
        events = RecordingEvents()
        settings = make_settings(asr_backend="funasr_realtime")

        with patch(
            "core.pipeline.create_audio_capture",
            side_effect=create_fake_audio_capture,
        ):
            pipeline = Pipeline(settings=settings, events=events)

        pipeline.pause()
        self.assertTrue(pipeline._pause_evt.is_set())
        pipeline.resume()
        self.assertFalse(pipeline._pause_evt.is_set())
        pipeline.stop()
        self.assertFalse(pipeline.running)
        self.assertEqual(pipeline.audio.stopped, 1)

    def test_audio_backend_is_passed_to_capture_factory(self):
        events = RecordingEvents()
        settings = make_settings(audio_capture_backend="blackhole")

        with patch(
            "core.pipeline.create_audio_capture",
            side_effect=create_fake_audio_capture,
        ) as create_capture:
            pipeline = Pipeline(settings=settings, events=events)

        create_capture.assert_called_once_with(
            "blackhole",
            sample_rate=16000,
            step_size=0.2,
        )
        self.assertEqual(pipeline.audio.backend, "blackhole")


if __name__ == "__main__":
    unittest.main()
