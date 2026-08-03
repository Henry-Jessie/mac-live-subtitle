import json
from dataclasses import dataclass

from Foundation import NSBundle, NSUserDefaults

from core.credentials import (
    ASR_DASHSCOPE_ACCOUNT,
    credential_store,
    translation_account,
)
from core.settings import PipelineSettings


BUNDLE_ID = "com.henryjessie.MacLiveSubtitle"
INTERFACE_LANGUAGE_KEY = "interface.language"


def _default_user_defaults():
    if NSBundle.mainBundle().bundleIdentifier() == BUNDLE_ID:
        return NSUserDefaults.standardUserDefaults()
    return NSUserDefaults.alloc().initWithSuiteName_(BUNDLE_ID)


@dataclass(frozen=True, slots=True)
class Preferences:
    asr_backend: str
    audio_capture_backend: str
    source_language: str
    funasr_realtime_model: str
    funasr_realtime_ws_url: str
    funasr_realtime_semantic_punctuation: bool
    funasr_realtime_max_sentence_silence: int
    funasr_realtime_multi_threshold: bool
    funasr_realtime_event_log: str
    sample_rate: int
    streaming_step_size: float
    translation_enabled: bool
    translation_provider: str
    api_base_url: str
    model: str
    translation_thinking: str
    target_lang: str
    translation_temperature: float
    translation_extra_body_json: str
    translation_debug: bool
    always_on_top: bool
    background_opacity: float
    original_font_size: int
    translated_font_size: int


DEFAULTS = {
    "transcription.backend": "funasr_realtime",
    "audio.capture_backend": "native",
    "transcription.source_language": "auto",
    "transcription.funasr_realtime_model": "fun-asr-realtime",
    "transcription.funasr_realtime_ws_url": (
        "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
    ),
    "transcription.funasr_realtime_semantic_punctuation": True,
    "transcription.funasr_realtime_max_sentence_silence": 0,
    "transcription.funasr_realtime_multi_threshold": False,
    "transcription.funasr_realtime_event_log": "",
    "audio.sample_rate": 16000,
    "audio.streaming_step_size": 0.2,
    "translation.enabled": True,
    "translation.provider": "deepseek",
    "translation.base_url": "https://api.deepseek.com/v1",
    "translation.model": "deepseek-v4-flash",
    "translation.thinking": "false",
    "translation.target_lang": "Simplified Chinese",
    "translation.temperature": 1.0,
    "translation.extra_body_json": "",
    "translation.debug": False,
    "display.always_on_top": True,
    "display.background_opacity": 0.82,
    "display.original_font_size": 13,
    "display.translated_font_size": 17,
    INTERFACE_LANGUAGE_KEY: "en",
}


class SettingsStore:
    def __init__(
        self,
        *,
        defaults=None,
        credentials=credential_store,
    ):
        self.defaults = (
            defaults
            if defaults is not None
            else _default_user_defaults()
        )
        self.credentials = credentials
        self.defaults.registerDefaults_(DEFAULTS)

    def load(self) -> Preferences:
        return Preferences(
            asr_backend=self._string("transcription.backend"),
            audio_capture_backend=self._string("audio.capture_backend"),
            source_language=self._string("transcription.source_language"),
            funasr_realtime_model=self._string(
                "transcription.funasr_realtime_model"
            ),
            funasr_realtime_ws_url=self._string(
                "transcription.funasr_realtime_ws_url"
            ),
            funasr_realtime_semantic_punctuation=self.defaults.boolForKey_(
                "transcription.funasr_realtime_semantic_punctuation"
            ),
            funasr_realtime_max_sentence_silence=self.defaults.integerForKey_(
                "transcription.funasr_realtime_max_sentence_silence"
            ),
            funasr_realtime_multi_threshold=self.defaults.boolForKey_(
                "transcription.funasr_realtime_multi_threshold"
            ),
            funasr_realtime_event_log=self._string(
                "transcription.funasr_realtime_event_log"
            ),
            sample_rate=self.defaults.integerForKey_("audio.sample_rate"),
            streaming_step_size=self.defaults.doubleForKey_(
                "audio.streaming_step_size"
            ),
            translation_enabled=self.defaults.boolForKey_(
                "translation.enabled"
            ),
            translation_provider=self._string("translation.provider"),
            api_base_url=self._string("translation.base_url"),
            model=self._string("translation.model"),
            translation_thinking=self._string("translation.thinking"),
            target_lang=self._string("translation.target_lang"),
            translation_temperature=self.defaults.doubleForKey_(
                "translation.temperature"
            ),
            translation_extra_body_json=self._string(
                "translation.extra_body_json"
            ),
            translation_debug=self.defaults.boolForKey_("translation.debug"),
            always_on_top=self.defaults.boolForKey_(
                "display.always_on_top"
            ),
            background_opacity=self.defaults.doubleForKey_(
                "display.background_opacity"
            ),
            original_font_size=self.defaults.integerForKey_(
                "display.original_font_size"
            ),
            translated_font_size=self.defaults.integerForKey_(
                "display.translated_font_size"
            ),
        )

    def save(self, preferences: Preferences) -> None:
        values = {
            "transcription.backend": preferences.asr_backend,
            "audio.capture_backend": preferences.audio_capture_backend,
            "transcription.source_language": preferences.source_language,
            "transcription.funasr_realtime_model": (
                preferences.funasr_realtime_model
            ),
            "transcription.funasr_realtime_ws_url": (
                preferences.funasr_realtime_ws_url
            ),
            "transcription.funasr_realtime_semantic_punctuation": (
                preferences.funasr_realtime_semantic_punctuation
            ),
            "transcription.funasr_realtime_max_sentence_silence": (
                preferences.funasr_realtime_max_sentence_silence
            ),
            "transcription.funasr_realtime_multi_threshold": (
                preferences.funasr_realtime_multi_threshold
            ),
            "transcription.funasr_realtime_event_log": (
                preferences.funasr_realtime_event_log
            ),
            "audio.sample_rate": preferences.sample_rate,
            "audio.streaming_step_size": preferences.streaming_step_size,
            "translation.enabled": preferences.translation_enabled,
            "translation.provider": preferences.translation_provider,
            "translation.base_url": preferences.api_base_url,
            "translation.model": preferences.model,
            "translation.thinking": preferences.translation_thinking,
            "translation.target_lang": preferences.target_lang,
            "translation.temperature": preferences.translation_temperature,
            "translation.extra_body_json": (
                preferences.translation_extra_body_json
            ),
            "translation.debug": preferences.translation_debug,
            "display.always_on_top": preferences.always_on_top,
            "display.background_opacity": preferences.background_opacity,
            "display.original_font_size": preferences.original_font_size,
            "display.translated_font_size": preferences.translated_font_size,
        }
        for key, value in values.items():
            self.defaults.setObject_forKey_(value, key)

    def interface_language(self) -> str:
        return self._string(INTERFACE_LANGUAGE_KEY)

    def save_interface_language(self, language: str) -> None:
        self.defaults.setObject_forKey_(language, INTERFACE_LANGUAGE_KEY)

    def pipeline_settings(self) -> PipelineSettings:
        preferences = self.load()
        extra_body = None
        if preferences.translation_extra_body_json:
            parsed = json.loads(preferences.translation_extra_body_json)
            if not isinstance(parsed, dict):
                raise ValueError("Translation extra body must be a JSON object")
            extra_body = parsed
        thinking = {
            "true": True,
            "false": False,
            "auto": None,
        }[preferences.translation_thinking]
        source_language = (
            None
            if preferences.source_language == "auto"
            else preferences.source_language
        )
        return PipelineSettings(
            asr_backend=preferences.asr_backend,
            audio_capture_backend=preferences.audio_capture_backend,
            sample_rate=preferences.sample_rate,
            streaming_step_size=preferences.streaming_step_size,
            translation_enabled=preferences.translation_enabled,
            target_lang=preferences.target_lang,
            api_base_url=preferences.api_base_url or None,
            api_key=self.translation_key(preferences.translation_provider),
            model=preferences.model,
            translation_extra_body=extra_body,
            translation_temperature=preferences.translation_temperature,
            translation_debug=preferences.translation_debug,
            translation_thinking=thinking,
            funasr_realtime_model=preferences.funasr_realtime_model,
            funasr_realtime_ws_url=preferences.funasr_realtime_ws_url,
            funasr_realtime_api_key=self.asr_key(),
            funasr_realtime_event_log=preferences.funasr_realtime_event_log,
            funasr_realtime_semantic_punctuation=(
                preferences.funasr_realtime_semantic_punctuation
            ),
            funasr_realtime_max_sentence_silence=(
                preferences.funasr_realtime_max_sentence_silence
            ),
            funasr_realtime_multi_threshold=(
                preferences.funasr_realtime_multi_threshold
            ),
            source_language=source_language,
        )

    def asr_key(self) -> str | None:
        return self.credentials.get(ASR_DASHSCOPE_ACCOUNT)

    def has_asr_key(self) -> bool:
        return self.credentials.exists(ASR_DASHSCOPE_ACCOUNT)

    def save_asr_key(self, value: str) -> None:
        self._save_secret(ASR_DASHSCOPE_ACCOUNT, value)

    def translation_key(self, provider: str) -> str | None:
        return self.credentials.get(translation_account(provider))

    def has_translation_key(self, provider: str) -> bool:
        return self.credentials.exists(translation_account(provider))

    def save_translation_key(self, provider: str, value: str) -> None:
        self._save_secret(translation_account(provider), value)

    def _save_secret(self, account: str, value: str) -> None:
        normalized = value.strip()
        if normalized:
            self.credentials.save(account, normalized)
        else:
            self.credentials.delete(account)

    def _string(self, key: str) -> str:
        return str(self.defaults.stringForKey_(key) or "")
