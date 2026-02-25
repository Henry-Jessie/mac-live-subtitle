import configparser
import os

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
        self.model = self._get("translation", "model", "gpt-3.5-turbo")
        self.target_lang = self._get("translation", "target_lang", "Chinese")
        self.use_llm_segmenter = self._get("translation", "use_llm_segmenter", "true").lower() == "true"
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
        self.asr_backend = (self._get("transcription", "backend", "deepgram_stream") or "").strip().lower()
        self.deepgram_model = self._get("transcription", "deepgram_model", "nova-3")
        self.qwen3_asr_realtime_model = self._get("transcription", "qwen3_asr_realtime_model", "qwen3-asr-flash-realtime")
        self.qwen3_asr_realtime_ws_url = self._get(
            "transcription",
            "qwen3_asr_realtime_ws_url",
            "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        )
        self.qwen3_asr_realtime_api_key_env = (
            self._get("transcription", "qwen3_asr_realtime_api_key_env", "DASHSCOPE_API_KEY") or ""
        ).strip()
        self.qwen3_asr_realtime_api_key = (self._get("transcription", "qwen3_asr_realtime_api_key", "") or "").strip()
        self.qwen3_asr_realtime_server_vad = (
            self._get("transcription", "qwen3_asr_realtime_server_vad", "true").lower() == "true"
        )
        self.qwen3_asr_realtime_vad_threshold = self._getfloat("transcription", "qwen3_asr_realtime_vad_threshold", 0.0)
        self.qwen3_asr_realtime_silence_duration_ms = self._getint(
            "transcription", "qwen3_asr_realtime_silence_duration_ms", 400
        )
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
        """Auto-detect BlackHole audio device index"""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for i, d in enumerate(devices):
                if d['max_input_channels'] > 0 and 'blackhole' in d['name'].lower():
                    print(f"[Config] Auto-detected BlackHole device: [{i}] {d['name']}")
                    return i
            print("[Config] BlackHole not found, using default input device")
            return None
        except Exception as e:
            print(f"[Config] Error detecting audio devices: {e}")
            return None
    
    def print_config(self):
        """Print current configuration for debugging"""
        print("[Config] Current settings:")
        print(f"  API Base URL: {self.api_base_url or '(default OpenAI)'}")
        print(f"  API Key: {self.api_key[:8]}...{self.api_key[-4:] if len(self.api_key) > 12 else '***'}")
        print(f"  Model: {self.model}")
        print(f"  Target Language: {self.target_lang}")
        print(f"  Use LLM Segmenter: {self.use_llm_segmenter}")
        print(f"  ASR Backend: {self.asr_backend}")
        print(f"  Deepgram Model: {self.deepgram_model}")
        print(f"  Qwen3 ASR Realtime Model: {self.qwen3_asr_realtime_model}")
        print(f"  Qwen3 ASR Realtime WS URL: {self.qwen3_asr_realtime_ws_url}")
        print(f"  Qwen3 ASR Realtime API Key Env: {self.qwen3_asr_realtime_api_key_env or '(none)'}")
        print(
            "  Qwen3 ASR Realtime Server VAD: "
            f"{self.qwen3_asr_realtime_server_vad} "
            f"(threshold={self.qwen3_asr_realtime_vad_threshold}, "
            f"silence_ms={self.qwen3_asr_realtime_silence_duration_ms})"
        )
        print(f"  Sample Rate: {self.sample_rate}")
        print(f"  Audio Device Index: {self.device_index}")
        print(f"  Streaming Step Size: {self.streaming_step_size}")

    def reload(self):
        """Re-read config.ini and re-initialize all fields."""
        self.__init__()

# Global config instance
config = Config()
