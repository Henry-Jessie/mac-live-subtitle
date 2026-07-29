# Mac Live Subtitle

<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="Mac Live Subtitle icon">
</p>

Real-time speech-to-text and translation with a floating subtitle window for macOS. Captures system audio directly through ScreenCaptureKit and streams it to a cloud ASR service, then displays translated subtitles on screen — useful for meetings, lectures, videos, and gaming.

<video src="demo/demo.mp4" width="100%" autoplay muted loop></video>

https://github.com/user-attachments/assets/2faca983-a76b-4591-95a8-5a11c1233a83


## Quick Start

```bash
# Install
git clone https://github.com/Henry-Jessie/mac-live-subtitle.git
cd mac-live-subtitle
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.ini.example config.ini

# Run
python app.py
```

Open Settings and enter the ASR and translation API keys. They are stored in macOS Keychain.

On first use, allow Screen Recording (shown as Screen & System Audio Recording on newer macOS versions), then restart the app. BlackHole and a Multi-Output Device are no longer required.

| API Key | Get it from | |
|:---|:---|:---|
| FunASR Realtime ASR | [DashScope China](https://bailian.console.aliyun.com/) / [DashScope Intl](https://bailian.console.alibabacloud.com/) | Region-specific endpoints & keys — see [Configuration](#configuration) |
| Translation LLM | [DeepSeek](https://platform.deepseek.com/) | Default provider |
| *Translation alternatives* | [Google AI Studio](https://aistudio.google.com/) · [OpenAI](https://platform.openai.com/) | Any OpenAI-compatible endpoint |

## Features

### Cloud-based Streaming ASR (FunASR Realtime)

No local model, no GPU required. The app streams audio to Alibaba Cloud's FunASR Realtime service over WebSocket:

- Server-side semantic sentence segmentation — each final result arrives as a complete, punctuated sentence; no client-side splitting heuristics needed
- Mandarin + Cantonese/Sichuan dialects, auto language detection, non-speech filtering, emotion recognition
- Hotword customization and context enhancement, word-level timestamps
- Optional VAD segmentation mode with tunable silence threshold for lower-latency scenarios

### Interim & Final Translation

Subtitles and translation are decoupled. While a sentence is still growing, temporary translations fire at configurable length thresholds (`funasr_interim_translate_chars`) — each translates the full current text, overwriting the previous one. A final, context-aware translation runs when the sentence ends. Interim translations never enter the translation context window.

Translation can be toggled off — then only the segmented source text is displayed (ASR-only mode).

### Context-aware Translation

A sliding context window (capped by token count) feeds recent source/translation pairs into every request, keeping terminology consistent across sentences. Powered by any OpenAI-compatible Chat Completions API (default: DeepSeek `deepseek-v4-flash`). Supports configurable temperature, a dedicated `thinking` toggle for DeepSeek V4 reasoning, extra body parameters, and reasoning-model `<think>` tag stripping.

### Single-window macOS-native UI

- Unified PyQt6 window with play/pause/stop controls
- Tabbed settings popover (Transcription / Translation / Display) with provider presets, configurable font sizes, and live preview
- Pushpin button for always-on-top, visible across all macOS Spaces via PyObjC
- Soft pause/resume (keeps WebSocket alive) and automatic reconnection with exponential backoff

<details>
<summary><h2>System Audio Permission</h2></summary>

System audio capture uses ScreenCaptureKit and requires macOS 13 or later.

1. Start the app and press **Play**.
2. Approve the macOS system-audio capture prompt.
3. If the prompt was previously dismissed, open **System Settings → Privacy & Security → Screen & System Audio Recording** and enable the terminal or packaged application used to launch Mac Live Subtitle.
4. Quit and restart the application after changing the permission.

</details>

## Usage

Run `python app.py`. Use **Play** / **Pause** / **Stop** to control the pipeline, **Gear** for settings, **Pin** for always-on-top. API keys entered in Settings are stored in macOS Keychain; clear a key field and save to remove it. Each API key has a **Test** button that checks the current field without saving it; the FunASR test performs only an authenticated WebSocket handshake and sends no audio. Most settings can be changed in the settings popover; advanced settings (`extra_body`, VAD parameters) require editing `config.ini`. ASR/translation setting changes take effect after restarting the pipeline; display settings (font size) apply immediately.

## Configuration

All settings are stored in `config.ini` and can be edited either in the settings popover or by hand. Copy `config.ini.example` as a starting point:

```bash
cp config.ini.example config.ini
```

### `[transcription]` — ASR backend

| Key | Description | Default |
|:---|:---|:---|
| `backend` | `funasr_realtime` (currently the only supported backend) | `funasr_realtime` |
| `source_language` | Language hint (`auto` = auto-detect; maps to `language_hints`, e.g. `zh`, `en`, `ja`) | `auto` |
| `funasr_realtime_model` | FunASR model name | `fun-asr-realtime` |
| `funasr_realtime_ws_url` | WebSocket endpoint — standard: `wss://dashscope.aliyuncs.com/api-ws/v1/inference`, workspace-specific: `wss://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference` (Beijing and Singapore API keys are region-specific and not interchangeable) | Beijing endpoint |
| `funasr_realtime_semantic_punctuation` | Server-side semantic sentence segmentation (accurate boundaries, longer segments). `false` = VAD segmentation (lower latency) | `true` |
| `funasr_realtime_max_sentence_silence` | VAD silence threshold in ms (200–6000, server default 1300; `0` = omit). VAD mode only | `0` |
| `funasr_realtime_multi_threshold` | Prevent VAD from producing over-long sentences. VAD mode only | `false` |
| `funasr_interim_translate_chars` | Interim translations: fire a temporary translation each time a growing sentence's display length crosses another multiple of this value (CJK chars count 2; `0` = disable) | `40` |
| `funasr_realtime_event_log` | Optional JSONL file logging raw sentence events (interim/end with timestamps) | *(empty)* |

### `[translation]` — LLM translation

| Key | Description | Default |
|:---|:---|:---|
| `provider` | Stable provider ID for provider-specific Keychain entries (`deepseek`, `google`, or `custom`) | `deepseek` |
| `base_url` | OpenAI-compatible API endpoint | `https://api.deepseek.com/v1` |
| `model` | Model identifier | `deepseek-v4-flash` |
| `target_lang` | Target language for translation | `Simplified Chinese` |
| `enabled` | Enable translation (`true`/`false`). When `false`, only segmented source text is shown | `true` |
| `thinking` | DeepSeek V4 thinking mode: `false` = disabled, `true` = enabled, `auto` = omit the parameter (use for non-DeepSeek providers) | `false` |
| `temperature` | Sampling temperature | `1.0` |
| `extra_body` | Extra JSON merged into API calls (e.g. `{"thinking": {"type": "disabled"}}`) | *(empty)* |

> **API key storage**: provider-specific credentials are read only from macOS Keychain. A legacy literal key in `config.ini` remains readable for migration and is removed after the next successful Settings save.

### `[audio]` / `[display]`

| Key | Section | Description | Default |
|:---|:---|:---|:---|
| `sample_rate` | audio | ScreenCaptureKit output sample rate in Hz | `16000` |
| `streaming_step_size` | audio | Audio frame duration in seconds | `0.2` |
| `always_on_top` | display | Start with window pinned on top | `true` |
| `original_font_size` | display | Font size (px) for source text | `13` |
| `translated_font_size` | display | Font size (px) for translated text | `17` |

## Build the macOS application

The current PyQt transition build uses `py2app`. Releases are distributed only as a standalone `.app`; `uv` remains a development and build tool. The transition build remains a regular Dock application, while the later AppKit menu-bar build will set `LSUIElement`.

```bash
uv sync --group build

# Development bundle that references the source tree
uv run python setup.py py2app --alias

# Standalone arm64 bundle
uv run python setup.py py2app
```

Delete the generated `build/` and `dist/` directories before switching between alias and standalone modes. The result is `dist/Mac Live Subtitle.app`. Packaged settings are written to `~/Library/Application Support/Mac Live Subtitle/config.ini`; API keys remain in Keychain. The build does not include the ignored development `config.ini`.

py2app applies an ad-hoc signature, which is suitable for running this local transition build. Public distribution still requires a Developer ID Application signature and Apple notarization.

## Troubleshooting

<details>
<summary><b>No audio captured</b></summary>

- Confirm Mac Live Subtitle is enabled under **System Settings → Privacy & Security → Screen & System Audio Recording**
- Quit and restart the application after granting permission
- Play audible media from another application; audio produced by Mac Live Subtitle itself is excluded from capture
</details>

<details>
<summary><b>ASR not connecting</b></summary>

- Confirm the DashScope API key is present under **Settings → Transcription**
- FunASR authentication and server errors appear in the application error banner
- The app retries up to 6 times with exponential backoff
</details>

<details>
<summary><b>Translation not appearing</b></summary>

- Confirm the provider API key is present under **Settings → Translation**
- Confirm `[translation] base_url` and `model` are set correctly
- Translation request errors appear in the application error banner
</details>

<details>
<summary><b>High latency</b></summary>

- Try a faster translation model (e.g. DeepSeek V4 Flash non-thinking or Gemini Flash)
- Reduce `streaming_step_size` for more frequent audio frames
- For lower-latency sentence boundaries, switch to VAD mode (`funasr_realtime_semantic_punctuation = false`) and lower `funasr_realtime_max_sentence_silence`
</details>

## How It Works

The pipeline has three concurrent stages:

1. **Audio capture** — ScreenCaptureKit captures macOS system audio directly as 16 kHz mono float32 samples. The capture layer groups variable callback sizes into fixed frames controlled by `streaming_step_size`, then the existing pipeline converts them to PCM16 for ASR.

2. **Streaming ASR** — the FunASR backend opens a duplex WebSocket to DashScope (`run-task` → binary PCM16 frames → `result-generated` events). Each event carries the full text of the current sentence: interim results replace the live subtitle line, and `sentence_end` commits the sentence verbatim. No client-side segmentation.

3. **Translation & display** — committed sentences are translated by the LLM endpoint (sliding context window) on a single serial executor, so interim and final translations can never arrive out of order. Growing sentences fire temporary translations at length thresholds; the final translation overwrites them. Results reach the UI via pipeline-identity-guarded Qt signals and appear as timestamped original/translation pairs with follow-tail auto-scroll.

---

## Privacy & Data Flow

> **All data is cloud-processed.** Audio is streamed to a cloud ASR service; transcribed text is sent to an external LLM for translation. No data stays local. Be mindful of this in sensitive contexts — speech content passes through third-party servers subject to their privacy policies. An active internet connection is required.

## Roadmap

- **Native macOS rewrite** — AppKit menu-bar controls and floating subtitle panel, followed by Developer ID signing and notarization

## Acknowledgments

Inspired by and forked from [Real-Time Translator](https://github.com/Vanyoo/realtime-subtitle) by Van (local ASR + dashboard/overlay architecture). This project replaces local ASR with cloud streaming, and consolidates the UI into a single macOS-native window.

## License

MIT
