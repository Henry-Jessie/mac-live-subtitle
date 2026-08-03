import unittest
from dataclasses import FrozenInstanceError

from core.settings import PipelineSettings


class PipelineSettingsTests(unittest.TestCase):
    def test_snapshot_is_frozen_and_hides_secrets(self):
        snapshot = PipelineSettings(
            asr_backend="funasr_realtime",
            audio_capture_backend="native",
            sample_rate=16000,
            streaming_step_size=0.2,
            translation_enabled=True,
            target_lang="Chinese",
            api_base_url="https://api.example.test/v1",
            api_key="translation-secret",
            model="test-model",
            translation_extra_body={"thinking": {"type": "disabled"}},
            translation_temperature=1.0,
            translation_debug=True,
            translation_thinking=False,
            funasr_realtime_model="fun-asr-realtime",
            funasr_realtime_ws_url="wss://example.test/asr",
            funasr_realtime_api_key="asr-secret",
            funasr_realtime_event_log="",
            funasr_realtime_semantic_punctuation=True,
            funasr_realtime_max_sentence_silence=0,
            funasr_realtime_multi_threshold=False,
            source_language=None,
        )

        self.assertEqual(snapshot.model, "test-model")
        self.assertEqual(
            snapshot.translation_extra_body,
            {"thinking": {"type": "disabled"}},
        )
        self.assertNotIn("translation-secret", repr(snapshot))
        self.assertNotIn("asr-secret", repr(snapshot))
        with self.assertRaises(FrozenInstanceError):
            snapshot.model = "other"


if __name__ == "__main__":
    unittest.main()
