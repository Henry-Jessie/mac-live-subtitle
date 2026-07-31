from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PipelineSettings:
    asr_backend: str
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
    funasr_interim_translate_chars: int
    funasr_realtime_semantic_punctuation: bool
    funasr_realtime_max_sentence_silence: int
    funasr_realtime_multi_threshold: bool
    source_language: str | None

    @classmethod
    def from_config(cls, config) -> "PipelineSettings":
        return cls(
            asr_backend=config.asr_backend,
            sample_rate=config.sample_rate,
            streaming_step_size=config.streaming_step_size,
            translation_enabled=config.translation_enabled,
            target_lang=config.target_lang,
            api_base_url=config.api_base_url,
            api_key=config.api_key,
            model=config.model,
            translation_extra_body=deepcopy(config.translation_extra_body),
            translation_temperature=config.translation_temperature,
            translation_debug=config.translation_debug,
            translation_thinking=config.translation_thinking,
            funasr_realtime_model=config.funasr_realtime_model,
            funasr_realtime_ws_url=config.funasr_realtime_ws_url,
            funasr_realtime_api_key=config.funasr_realtime_api_key,
            funasr_realtime_event_log=config.funasr_realtime_event_log,
            funasr_interim_translate_chars=config.funasr_interim_translate_chars,
            funasr_realtime_semantic_punctuation=config.funasr_realtime_semantic_punctuation,
            funasr_realtime_max_sentence_silence=config.funasr_realtime_max_sentence_silence,
            funasr_realtime_multi_threshold=config.funasr_realtime_multi_threshold,
            source_language=config.source_language,
        )

    def print_summary(self) -> None:
        print("[Config] Current settings:")
        print(f"  API Base URL: {self.api_base_url or '(default OpenAI)'}")
        print(f"  API Key Configured: {'yes' if self.api_key else 'no'}")
        print(f"  Model: {self.model}")
        thinking = {
            True: "enabled",
            False: "disabled",
            None: "auto (omit)",
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
        print(
            "  FunASR Interim Translate Chars: "
            f"{self.funasr_interim_translate_chars}"
        )
        print("  Audio Capture: ScreenCaptureKit system audio")
        print(f"  Sample Rate: {self.sample_rate}")
        print(f"  Streaming Step Size: {self.streaming_step_size}")
