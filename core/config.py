import configparser
import ipaddress
from pathlib import Path
from urllib.parse import urlparse

from keyring.errors import KeyringError

from core.credentials import (
    ASR_DASHSCOPE_ACCOUNT,
    TRANSLATION_ACCOUNTS,
    credential_store,
    infer_translation_provider,
    translation_account,
)
from core.paths import default_config_path


def is_local_url(base_url: str | None) -> bool:
    """Return True if *base_url* points to a loopback or unspecified address.

    Covers localhost, the full 127.0.0.0/8 range, IPv6 loopback (::1),
    unspecified addresses (0.0.0.0, ::), and IPv6-mapped loopback
    (e.g. ::ffff:127.0.0.1).
    """
    if not base_url:
        return False
    try:
        host = urlparse(base_url).hostname or ""
    except Exception:
        return False
    if host == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_loopback or addr.is_unspecified
    except ValueError:
        return False


class Config:
    """Centralized configuration loaded from config.ini"""
    
    def __init__(self, config_path=None):
        self.config_path = Path(config_path) if config_path is not None else default_config_path()
        
        self.config = configparser.ConfigParser()
        
        if self.config_path.exists():
            self.config.read(self.config_path)
            print(f"[Config] Loaded from: {self.config_path}")
        else:
            print(f"[Config] Warning: {self.config_path} not found, using defaults")
        
        # Translation LLM settings
        self.api_base_url = self._get(
            "translation",
            "base_url",
            "https://api.deepseek.com/v1",
        )
        configured_provider = (self._get("translation", "provider") or "").strip().lower()
        self.translation_provider = (
            configured_provider
            if configured_provider in TRANSLATION_ACCOUNTS
            else infer_translation_provider(self.api_base_url)
        )
        self.legacy_translation_api_key = (
            self._get("translation", "api_key") or ""
        ).strip()
        self.credential_error = ""
        try:
            self.translation_keychain_api_key = credential_store.get(
                translation_account(self.translation_provider)
            )
        except KeyringError as exc:
            self.translation_keychain_api_key = None
            self.credential_error = str(exc)
            print(f"[Config] Keychain unavailable: {exc}")
        self.api_key = (
            self.translation_keychain_api_key
            or self.legacy_translation_api_key
            or None
        )
        self.translation_api_key_configured = bool(
            self.translation_keychain_api_key
            or self.legacy_translation_api_key
        )
        self.model = self._get("translation", "model", "deepseek-v4-flash")
        self.target_lang = self._get("translation", "target_lang", "Chinese")
        # DeepSeek V4 thinking mode: True = enabled, False = disabled (default),
        # None = omit the parameter entirely ("auto", for non-DeepSeek providers).
        _thinking_raw = (self._get("translation", "thinking", "false") or "").strip().lower()
        if _thinking_raw in ("true", "1", "yes", "on", "enabled"):
            self.translation_thinking = True
        elif _thinking_raw in ("auto", "none", ""):
            self.translation_thinking = None
        else:
            self.translation_thinking = False
        self.translation_enabled = self._get("translation", "enabled", "true").strip().lower() in ("true", "1", "yes")
        self.translation_temperature = self._getfloat("translation", "temperature", 1.0)
        # Extra body for LLM API calls (JSON string, e.g. {"thinking": {"type": "disabled"}})
        _extra_body_raw = self._get("translation", "extra_body", "").strip()
        self.translation_extra_body = None
        if _extra_body_raw:
            try:
                import json
                self.translation_extra_body = json.loads(_extra_body_raw)
            except Exception:
                print(f"[Config] Warning: invalid JSON in [translation] extra_body: {_extra_body_raw}")

        # Transcription settings
        self.asr_backend = (self._get("transcription", "backend", "funasr_realtime") or "").strip().lower()
        # --- FunASR Realtime (DashScope Recognition API) ---
        self.funasr_realtime_model = self._get("transcription", "funasr_realtime_model", "fun-asr-realtime")
        self.funasr_realtime_ws_url = self._get(
            "transcription",
            "funasr_realtime_ws_url",
            "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
        )
        self.legacy_funasr_realtime_api_key = (
            self._get("transcription", "funasr_realtime_api_key", "") or ""
        ).strip()
        try:
            self.funasr_keychain_api_key = credential_store.get(ASR_DASHSCOPE_ACCOUNT)
        except KeyringError as exc:
            self.funasr_keychain_api_key = None
            if not self.credential_error:
                self.credential_error = str(exc)
            print(f"[Config] Keychain unavailable: {exc}")
        self.funasr_realtime_api_key = (
            self.funasr_keychain_api_key or self.legacy_funasr_realtime_api_key
            or None
        )
        self.funasr_realtime_semantic_punctuation = (
            self._get("transcription", "funasr_realtime_semantic_punctuation", "true").lower() == "true"
        )
        # Optional JSONL file for raw sentence events (golden-test material)
        self.funasr_realtime_event_log = (self._get("transcription", "funasr_realtime_event_log", "") or "").strip()
        # VAD-mode knobs (only effective when funasr_realtime_semantic_punctuation = false)
        self.funasr_realtime_max_sentence_silence = self._getint("transcription", "funasr_realtime_max_sentence_silence", 0)
        self.funasr_realtime_multi_threshold = (
            self._get("transcription", "funasr_realtime_multi_threshold", "false").lower() == "true"
        )
        # Interim translations: fire a temporary translation each time a growing
        # sentence crosses 1x/2x/3x of this display-length threshold
        # (CJK chars count 2; 0 = disable). Results are overwritten freely and
        # never enter the translation context window.
        self.funasr_interim_translate_chars = self._getint("transcription", "funasr_interim_translate_chars", 40)
        self.source_language = self._get("transcription", "source_language", "auto")
        if self.source_language == "auto":
            self.source_language = None  # None means auto-detect
        
        # Audio settings
        self.sample_rate = self._getint("audio", "sample_rate", 16000)

        self.streaming_step_size = self._getfloat("audio", "streaming_step_size", 0.2)
        
        # Display settings
        self.always_on_top = self._get("display", "always_on_top", "true").lower() == "true"
        self.original_font_size = self._getint("display", "original_font_size", 13)
        self.translated_font_size = self._getint("display", "translated_font_size", 17)
    
    def _get(self, section, key, fallback=""):
        try:
            value = self.config.get(section, key)
            return value if value else fallback
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback
    
    def _getint(self, section, key, fallback=0):
        try:
            return self.config.getint(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback
    
    def _getfloat(self, section, key, fallback=0.0):
        try:
            return self.config.getfloat(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return fallback
    
    def print_config(self):
        """Print current configuration for debugging"""
        print("[Config] Current settings:")
        print(f"  API Base URL: {self.api_base_url or '(default OpenAI)'}")
        print(f"  API Key Configured: {'yes' if self.translation_api_key_configured else 'no'}")
        print(f"  Model: {self.model}")
        _thinking_disp = {True: "enabled", False: "disabled", None: "auto (omit)"}[self.translation_thinking]
        print(f"  Thinking: {_thinking_disp}")
        print(f"  Target Language: {self.target_lang}")
        print(f"  Translation Enabled: {self.translation_enabled}")
        print(f"  ASR Backend: {self.asr_backend}")
        print(f"  FunASR Realtime Model: {self.funasr_realtime_model}")
        print(f"  FunASR Realtime WS URL: {self.funasr_realtime_ws_url}")
        print(
            "  FunASR Realtime API Key Configured: "
            f"{'yes' if self.funasr_realtime_api_key else 'no'}"
        )
        print(f"  FunASR Realtime Semantic Punctuation: {self.funasr_realtime_semantic_punctuation}")
        print(f"  FunASR Realtime Event Log: {self.funasr_realtime_event_log or '(off)'}")
        print(f"  FunASR Realtime VAD Knobs: max_sentence_silence={self.funasr_realtime_max_sentence_silence or '(default)'}, multi_threshold={self.funasr_realtime_multi_threshold}")
        print(f"  FunASR Interim Translate Chars: {self.funasr_interim_translate_chars}")
        print("  Audio Capture: ScreenCaptureKit system audio")
        print(f"  Sample Rate: {self.sample_rate}")
        print(f"  Streaming Step Size: {self.streaming_step_size}")

    def reload(self):
        """Re-read config.ini and re-initialize all fields."""
        self.__init__(self.config_path)

# Global config instance
config = Config()
