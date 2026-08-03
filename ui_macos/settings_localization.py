INTERFACE_LANGUAGES = ("en", "zh")
INTERFACE_LANGUAGE_TITLES = ("English", "中文")


SETTINGS_STRINGS = {
    "en": {
        "pane.transcription.title": "Transcription",
        "pane.transcription.description": "FunASR Realtime",
        "pane.translation.title": "Translation",
        "pane.translation.description": (
            "Choose a translation service and output language."
        ),
        "pane.display.title": "Display",
        "pane.display.description": (
            "Adjust the subtitle window, background, and typography."
        ),
        "common.save": "Save",
        "common.advanced": "Advanced",
        "common.advanced_description": "Advanced settings",
        "common.show_advanced": "Show advanced settings",
        "common.hide_advanced": "Hide advanced settings",
        "common.api_access": "API Access",
        "common.api_key": "API Key",
        "common.test_connection": "Test Connection",
        "common.testing": "Testing…",
        "common.show_api_key": "Show API key",
        "common.hide_api_key": "Hide API key",
        "common.remove_key_on_save": (
            "Key will be removed when you save"
        ),
        "common.replace_saved_key": (
            "New key will replace the saved key"
        ),
        "common.save_new_key": "New key will be saved locally",
        "common.enter_api_key": "Enter an API key first.",
        "common.saved_message": (
            "Saved. ASR and translation changes apply on the next start."
        ),
        "transcription.title": "FunASR Realtime",
        "transcription.china_guide": "China Guide",
        "transcription.international_guide": "International Guide",
        "transcription.china_guide_help": (
            "Open the Alibaba Cloud Model Studio API key guide for China."
        ),
        "transcription.international_guide_help": (
            "Open the international Alibaba Cloud Model Studio API key guide."
        ),
        "transcription.introduction": (
            "An Alibaba Cloud Model Studio API key is required. Choose the "
            "guide for your account region; API keys cannot be shared across "
            "regions."
        ),
        "transcription.api_key_help": (
            "Stored only on this Mac. Use an API key from the selected "
            "service region."
        ),
        "transcription.region": "Service region",
        "transcription.region_help": (
            "Choose the region where your API key was created."
        ),
        "transcription.region_china": "China (Beijing)",
        "transcription.region_international": (
            "International (Singapore)"
        ),
        "transcription.language_section": "Language & Sentences",
        "transcription.source_language": "Source language",
        "transcription.source_language_help": (
            "Use auto to detect the language, or enter a hint such as zh, "
            "en, or ja."
        ),
        "transcription.semantic_punctuation": (
            "Use semantic punctuation for sentence endings"
        ),
        "transcription.semantic_punctuation_help": (
            "Let FunASR use punctuation to decide when a sentence ends."
        ),
        "transcription.audio_capture": "Audio capture",
        "transcription.audio_capture_help": (
            "Native needs no setup. Use BlackHole Compatibility after "
            "configuring a Multi-Output Device for protected players such "
            "as Apple TV."
        ),
        "audio.native": "Native System Audio",
        "audio.blackhole": "BlackHole Compatibility",
        "transcription.model": "Model",
        "transcription.model_help": "FunASR model identifier.",
        "transcription.maximum_silence": "Maximum silence (ms)",
        "transcription.maximum_silence_help": (
            "Use 0 for the provider default, or 200–6000 ms in VAD mode."
        ),
        "transcription.multi_threshold": "Multi-threshold VAD",
        "transcription.multi_threshold_help": (
            "Helps VAD mode avoid overly long sentences."
        ),
        "translation.title": "Translation",
        "translation.introduction": (
            "Choose a service for translated subtitles."
        ),
        "translation.enable": "Enable translation",
        "translation.enable_help": "Enable translated subtitle output.",
        "translation.service": "Service",
        "translation.provider": "Provider",
        "translation.target_language": "Target language",
        "translation.target_language_help": (
            "Language used for translated subtitle output."
        ),
        "translation.api_key_help": "Stored only on this Mac.",
        "translation.base_url": "Base URL",
        "translation.base_url_help": "OpenAI-compatible API base URL.",
        "translation.model": "Model",
        "translation.model_help": (
            "Model identifier used by the selected provider."
        ),
        "translation.thinking": "Thinking",
        "translation.thinking_help": (
            "Choose Enabled, Disabled, or Default. Default omits the "
            "thinking parameter."
        ),
        "translation.temperature": "Temperature",
        "translation.temperature_help": (
            "Sampling temperature from 0 to 2."
        ),
        "display.window": "Window",
        "display.always_on_top": "Always on top",
        "display.background_opacity": "Background opacity",
        "display.typography": "Typography",
        "display.original_font": "Original font",
        "display.translated_font": "Translated font",
        "display.interface": "Interface",
        "display.settings_language": "Settings language",
        "display.settings_language_help": (
            "Changes immediately and is saved automatically."
        ),
        "provider.deepseek": "DeepSeek",
        "provider.gemini": "Gemini",
        "provider.custom": "Custom",
        "thinking.false": "Disabled",
        "thinking.true": "Enabled",
        "thinking.auto": "Default",
        "validation.funasr_model": "FunASR model is required",
        "validation.maximum_silence": (
            "Max silence must be 0 or between 200 and 6000 ms"
        ),
        "validation.translation_model": "Translation model is required",
        "validation.target_language": "Target language is required",
        "validation.temperature": "Temperature must be between 0 and 2",
        "validation.extra_body": (
            "Translation extra body must be a JSON object"
        ),
    },
    "zh": {
        "pane.transcription.title": "识别",
        "pane.transcription.description": "FunASR 实时识别",
        "pane.translation.title": "翻译",
        "pane.translation.description": "选择翻译服务和输出语言。",
        "pane.display.title": "显示",
        "pane.display.description": "调整字幕窗口、背景和字体。",
        "common.save": "保存",
        "common.advanced": "高级设置",
        "common.advanced_description": "高级设置",
        "common.show_advanced": "显示高级设置",
        "common.hide_advanced": "隐藏高级设置",
        "common.api_access": "API 访问",
        "common.api_key": "API Key",
        "common.test_connection": "测试连接",
        "common.testing": "正在测试…",
        "common.show_api_key": "显示 API Key",
        "common.hide_api_key": "隐藏 API Key",
        "common.remove_key_on_save": "保存后将删除此密钥",
        "common.replace_saved_key": "新密钥将替换已保存的密钥",
        "common.save_new_key": "新密钥将保存在本机",
        "common.enter_api_key": "请先输入 API Key。",
        "common.saved_message": "已保存。识别和翻译设置将在下次启动时生效。",
        "transcription.title": "FunASR 实时识别",
        "transcription.china_guide": "国内申请教程",
        "transcription.international_guide": "国际申请教程",
        "transcription.china_guide_help": (
            "打开阿里云百炼国内站 API Key 申请文档。"
        ),
        "transcription.international_guide_help": (
            "打开 Alibaba Cloud 国际站 API Key 申请文档。"
        ),
        "transcription.introduction": (
            "使用本服务需要阿里云百炼 API Key。请选择账号所在地域的"
            "申请教程，不同地域的 API Key 不能混用。"
        ),
        "transcription.api_key_help": "仅保存在本机。请使用所选服务区域的 API Key。",
        "transcription.region": "服务区域",
        "transcription.region_help": "请选择 API Key 所属的服务区域。",
        "transcription.region_china": "中国（北京）",
        "transcription.region_international": "国际（新加坡）",
        "transcription.language_section": "语言与分句",
        "transcription.source_language": "源语言",
        "transcription.source_language_help": (
            "使用 auto 自动检测，或填写 zh、en、ja 等语言提示。"
        ),
        "transcription.semantic_punctuation": "使用语义标点判断句子结束",
        "transcription.semantic_punctuation_help": (
            "让 FunASR 根据标点判断句子结束位置。"
        ),
        "transcription.audio_capture": "音频捕获",
        "transcription.audio_capture_help": (
            "原生模式无需设置。Apple TV 等受保护播放器可在配置多输出设备后"
            "使用 BlackHole 兼容模式。"
        ),
        "audio.native": "原生系统音频",
        "audio.blackhole": "BlackHole 兼容模式",
        "transcription.model": "模型",
        "transcription.model_help": "FunASR 模型标识。",
        "transcription.maximum_silence": "最长静音（毫秒）",
        "transcription.maximum_silence_help": (
            "填写 0 使用服务默认值；VAD 模式可填写 200–6000。"
        ),
        "transcription.multi_threshold": "多阈值 VAD",
        "transcription.multi_threshold_help": (
            "帮助 VAD 模式避免生成过长的句子。"
        ),
        "translation.title": "翻译",
        "translation.introduction": "选择字幕翻译服务。",
        "translation.enable": "启用翻译",
        "translation.enable_help": "显示翻译后的字幕。",
        "translation.service": "服务",
        "translation.provider": "服务商",
        "translation.target_language": "目标语言",
        "translation.target_language_help": "翻译字幕使用的输出语言。",
        "translation.api_key_help": "仅保存在本机。",
        "translation.base_url": "基础地址",
        "translation.base_url_help": "兼容 OpenAI 接口的 API 基础地址。",
        "translation.model": "模型",
        "translation.model_help": "当前服务商使用的模型标识。",
        "translation.thinking": "思考模式",
        "translation.thinking_help": (
            "可选择开启、关闭或默认；“默认”不会发送 thinking 参数。"
        ),
        "translation.temperature": "温度",
        "translation.temperature_help": "采样温度，取值范围为 0 到 2。",
        "display.window": "窗口",
        "display.always_on_top": "始终置顶",
        "display.background_opacity": "背景不透明度",
        "display.typography": "字体",
        "display.original_font": "原文大小",
        "display.translated_font": "译文大小",
        "display.interface": "界面",
        "display.settings_language": "设置界面语言",
        "display.settings_language_help": "切换后立即生效并自动保存。",
        "provider.deepseek": "DeepSeek",
        "provider.gemini": "Gemini",
        "provider.custom": "自定义",
        "thinking.false": "关闭",
        "thinking.true": "开启",
        "thinking.auto": "默认",
        "validation.funasr_model": "请填写 FunASR 模型",
        "validation.maximum_silence": (
            "最长静音必须为 0，或介于 200 到 6000 毫秒"
        ),
        "validation.translation_model": "请填写翻译模型",
        "validation.target_language": "请填写目标语言",
        "validation.temperature": "温度必须介于 0 到 2",
        "validation.extra_body": "翻译附加参数必须是 JSON 对象",
    },
}


def settings_text(language: str, key: str) -> str:
    return SETTINGS_STRINGS[language][key]
