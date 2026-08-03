from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PipelineSettings:
    asr_backend: str
    audio_capture_backend: str
    sample_rate: int
    streaming_step_size: float
    translation_enabled: bool
    target_lang: str
    api_base_url: str | None
    api_key: str | None = field(repr=False)
    model: str
    translation_extra_body: dict[str, Any] | None
    translation_temperature: float
    translation_debug: bool
    translation_thinking: bool | None
    funasr_realtime_model: str
    funasr_realtime_ws_url: str
    funasr_realtime_api_key: str | None = field(repr=False)
    funasr_realtime_event_log: str
    funasr_realtime_semantic_punctuation: bool
    funasr_realtime_max_sentence_silence: int
    funasr_realtime_multi_threshold: bool
    source_language: str | None

    def print_summary(self) -> None:
        print("[Config] Current settings:")
        print(f"  API Base URL: {self.api_base_url or '(default OpenAI)'}")
        print(f"  API Key Configured: {'yes' if self.api_key else 'no'}")
        print(f"  Model: {self.model}")
        thinking = {
            True: "enabled",
            False: "disabled",
            None: "default",
        }[self.translation_thinking]
        print(f"  Thinking: {thinking}")
        print(f"  Target Language: {self.target_lang}")
        print(f"  Translation Enabled: {self.translation_enabled}")
        print(f"  ASR Backend: {self.asr_backend}")
        print(f"  FunASR Realtime Model: {self.funasr_realtime_model}")
        print(f"  FunASR Realtime WS URL: {self.funasr_realtime_ws_url}")
        print(
            "  FunASR Realtime API Key Configured: "
            f"{'yes' if self.funasr_realtime_api_key else 'no'}"
        )
        print(
            "  FunASR Realtime Semantic Punctuation: "
            f"{self.funasr_realtime_semantic_punctuation}"
        )
        print(
            "  FunASR Realtime Event Log: "
            f"{self.funasr_realtime_event_log or '(off)'}"
        )
        print(
            "  FunASR Realtime VAD Knobs: "
            f"max_sentence_silence="
            f"{self.funasr_realtime_max_sentence_silence or '(default)'}, "
            f"multi_threshold={self.funasr_realtime_multi_threshold}"
        )
        audio_capture = {
            "native": "Native system audio (ScreenCaptureKit)",
            "blackhole": "BlackHole compatibility mode",
        }[self.audio_capture_backend]
        print(f"  Audio Capture: {audio_capture}")
        print(f"  Sample Rate: {self.sample_rate}")
        print(f"  Streaming Step Size: {self.streaming_step_size}")
