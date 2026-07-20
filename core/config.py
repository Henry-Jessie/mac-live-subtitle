import configparser
import ipaddress
import os
from urllib.parse import urlparse


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
        if config_path is None:
            # Look for config.ini in the project root (parent of core/)
            config_path = os.path.join(os.path.dirname(__file__), "..", "config.ini")
        
        self.config = configparser.ConfigParser()
        
        if os.path.exists(config_path):
            self.config.read(config_path)
            print(f"[Config] Loaded from: {config_path}")
        else:
            print(f"[Config] Warning: {config_path} not found, using defaults/env vars")
        
        # Translation LLM settings (explicit config.ini values take precedence over env vars)
        self.api_base_url = self._get("translation", "base_url") or os.getenv("OPENAI_BASE_URL") or None
        api_key_env = (self._get("translation", "api_key_env", "OPENAI_API_KEY") or "").strip()
        self.api_key = self._get("translation", "api_key") or os.getenv(api_key_env) or "dummy-key-for-local"
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
        self.funasr_realtime_api_key_env = (
            self._get("transcription", "funasr_realtime_api_key_env", "DASHSCOPE_API_KEY") or ""
        ).strip()
        self.funasr_realtime_api_key = (self._get("transcription", "funasr_realtime_api_key", "") or "").strip()
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
        
        # Device index: 'auto' or empty = auto-detect BlackHole, or set a specific index
        device_idx_str = self._get("audio", "device_index", "auto")
        if device_idx_str.isdigit():
            self.device_index = int(device_idx_str)
        elif device_idx_str.lower() in ("auto", ""):
            self.device_index = self._find_blackhole_device()
        else:
            self.device_index = None

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
    
    def _find_blackhole_device(self):
        """Auto-detect a usable virtual capture device (e.g. BlackHole).

        Prefers the exact 'BlackHole 2ch' name and verifies the device can
        actually be opened (multi-channel variants like 16ch may reject mono).
        """
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            candidates = [
                (i, d)
                for i, d in enumerate(devices)
                if d['max_input_channels'] > 0 and 'blackhole' in d['name'].lower()
            ]
            if not candidates:
                print("[Config] BlackHole not found, using default input device")
                return None
            candidates.sort(key=lambda t: 0 if t[1]['name'].strip().lower() == 'blackhole 2ch' else 1)
            for i, d in candidates:
                for ch in (1, 2):
                    try:
                        sd.check_input_settings(device=i, channels=ch, samplerate=self.sample_rate)
                        print(f"[Config] Auto-detected BlackHole device: [{i}] {d['name']} (channels={ch})")
                        return i
                    except Exception:
                        continue
            i, d = candidates[0]
            print(f"[Config] Auto-detected BlackHole device: [{i}] {d['name']} (unverified)")
            return i
        except Exception as e:
            print(f"[Config] Error detecting audio devices: {e}")
            return None
    
    def print_config(self):
        """Print current configuration for debugging"""
        print("[Config] Current settings:")
        print(f"  API Base URL: {self.api_base_url or '(default OpenAI)'}")
        print(f"  API Key: {self.api_key[:8]}...{self.api_key[-4:] if len(self.api_key) > 12 else '***'}")
        print(f"  Model: {self.model}")
        _thinking_disp = {True: "enabled", False: "disabled", None: "auto (omit)"}[self.translation_thinking]
        print(f"  Thinking: {_thinking_disp}")
        print(f"  Target Language: {self.target_lang}")
        print(f"  Translation Enabled: {self.translation_enabled}")
        print(f"  ASR Backend: {self.asr_backend}")
        print(f"  FunASR Realtime Model: {self.funasr_realtime_model}")
        print(f"  FunASR Realtime WS URL: {self.funasr_realtime_ws_url}")
        print(f"  FunASR Realtime API Key Env: {self.funasr_realtime_api_key_env or '(none)'}")
        print(f"  FunASR Realtime Semantic Punctuation: {self.funasr_realtime_semantic_punctuation}")
        print(f"  FunASR Realtime Event Log: {self.funasr_realtime_event_log or '(off)'}")
        print(f"  FunASR Realtime VAD Knobs: max_sentence_silence={self.funasr_realtime_max_sentence_silence or '(default)'}, multi_threshold={self.funasr_realtime_multi_threshold}")
        print(f"  FunASR Interim Translate Chars: {self.funasr_interim_translate_chars}")
        print(f"  Sample Rate: {self.sample_rate}")
        print(f"  Audio Device Index: {self.device_index}")
        print(f"  Streaming Step Size: {self.streaming_step_size}")

    def reload(self):
        """Re-read config.ini and re-initialize all fields."""
        self.__init__()

# Global config instance
config = Config()
