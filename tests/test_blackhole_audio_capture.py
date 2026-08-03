import unittest
from unittest.mock import patch

from core.blackhole_audio_capture import (
    BlackHoleAudioCapture,
    select_blackhole_device,
)


class BlackHoleDeviceSelectionTests(unittest.TestCase):
    def test_exact_blackhole_2ch_is_preferred(self):
        devices = [
            {"name": "BlackHole 16ch", "max_input_channels": 16},
            {"name": "BlackHole 2ch", "max_input_channels": 2},
            {"name": "blackhole custom", "max_input_channels": 2},
        ]

        self.assertEqual(select_blackhole_device(devices), 1)

    def test_prefix_match_is_case_insensitive_and_requires_input(self):
        devices = [
            {"name": "BlackHole Output", "max_input_channels": 0},
            {"name": "BLACKHOLE Virtual", "max_input_channels": 8},
            {"name": "MacBook Pro Microphone", "max_input_channels": 1},
        ]

        self.assertEqual(select_blackhole_device(devices), 1)

    def test_smallest_channel_candidate_is_used_without_2ch(self):
        devices = [
            {"name": "BlackHole 64ch", "max_input_channels": 64},
            {"name": "BlackHole 16ch", "max_input_channels": 16},
        ]

        self.assertEqual(select_blackhole_device(devices), 1)

    def test_missing_blackhole_never_selects_default_input(self):
        devices = [
            {"name": "MacBook Pro Microphone", "max_input_channels": 1},
            {"name": "NoMachine Audio Adapter", "max_input_channels": 2},
        ]

        with self.assertRaisesRegex(
            RuntimeError,
            "BlackHole input device not found.*MacBook Pro Microphone",
        ):
            select_blackhole_device(devices)

    def test_channel_negotiation_falls_back_to_stereo(self):
        capture = BlackHoleAudioCapture(sample_rate=16000, step_size=0.2)

        with patch(
            "core.blackhole_audio_capture.sd.check_input_settings",
            side_effect=[ValueError("mono unavailable"), None],
        ) as check:
            channels = capture._negotiate_channels(4)

        self.assertEqual(channels, 2)
        self.assertEqual(check.call_count, 2)


if __name__ == "__main__":
    unittest.main()
