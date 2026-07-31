# Mac Live Subtitle

<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="Mac Live Subtitle icon">
</p>

Real-time speech-to-text and translation with a floating subtitle window for macOS. Captures system audio directly through ScreenCaptureKit and streams it to a cloud ASR service, then displays translated subtitles on screen — useful for meetings, lectures, videos, and gaming.

<video src="demo/demo.mp4" width="100%" autoplay muted loop></video>

https://github.com/user-attachments/assets/2faca983-a76b-4591-95a8-5a11c1233a83


## Quick Start

```bash
git clone https://github.com/Henry-Jessie/mac-live-subtitle.git
cd mac-live-subtitle
uv sync
cp config.ini.example config.ini

uv run python app.py
```

The app appears in the menu bar rather than the Dock. Open **Settings…** from
the menu-bar menu and enter the ASR and translation API keys. They are stored
in an application-specific local credentials file.

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

### Native menu-bar UI

- AppKit menu-bar item with a native three-action menu for Settings, the subtitle window, and Quit
- Floating black subtitle panel with play/pause, stop, pin, and settings controls; it can remain visible across Spaces and full-screen applications
- Native preference-style Transcription, Translation, and Display settings with toolbar navigation, grouped forms, provider presets, locally stored password fields, connection tests, and live font and background-opacity preview
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

Run `uv run python app.py`, then use the subtitle-panel toolbar to start,
pause, resume, or stop the pipeline. The toolbar also controls pinning and
opens Settings. The native menu-bar menu opens Settings or the subtitle
window and quits the application. The subtitle panel starts visible; closing
it hides it until **Subtitle Window** is selected from the menu.

API keys entered in Settings are stored in
`~/Library/Application Support/Mac Live Subtitle/credentials.json`. The file is
restricted to the current macOS user (`0600`) and does not use Keychain, so it
does not trigger password authorization prompts. A stored key appears as a
fixed-length mask; use the eye button to reveal it on demand. Entering a value
replaces the stored key. Reveal and clear the field, then save, to remove it.
Existing Keychain items are not imported, so enter each required key once after
upgrading from a Keychain-based build.
Each key has a **Test** button that checks the current field without saving it;
the FunASR test performs an authenticated WebSocket handshake and sends no
audio. ASR and translation changes take effect on the next start. Display
settings apply immediately.

## Configuration

Ordinary settings are stored in macOS `NSUserDefaults` under
`com.henryjessie.MacLiveSubtitle`; API keys are stored separately in the local
credentials file. On the first native launch, an existing `config.ini` is
imported once and is left unchanged. Copy `config.ini.example` before that
first launch when migrating an existing source checkout:

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
| `provider` | Stable provider ID for provider-specific credential entries (`deepseek`, `google`, or `custom`) | `deepseek` |
| `base_url` | OpenAI-compatible API endpoint | `https://api.deepseek.com/v1` |
| `model` | Model identifier | `deepseek-v4-flash` |
| `target_lang` | Target language for translation | `Simplified Chinese` |
| `enabled` | Enable translation (`true`/`false`). When `false`, only segmented source text is shown | `true` |
| `thinking` | DeepSeek V4 thinking mode: `false` = disabled, `true` = enabled, `auto` = omit the parameter (use for non-DeepSeek providers) | `false` |
| `temperature` | Sampling temperature | `1.0` |
| `extra_body` | Extra JSON merged into API calls (e.g. `{"thinking": {"type": "disabled"}}`) | *(empty)* |

> **API key storage**: provider-specific credentials are read only from the
> application credentials file. Literal API keys are never stored in
> `NSUserDefaults` or `config.ini`. The file is plaintext and readable by
> processes running as the same macOS user.

### `[audio]` / `[display]`

| Key | Section | Description | Default |
|:---|:---|:---|:---|
| `sample_rate` | audio | ScreenCaptureKit output sample rate in Hz | `16000` |
| `streaming_step_size` | audio | Audio frame duration in seconds | `0.2` |
| `always_on_top` | display | Start with window pinned on top | `true` |
| `background_opacity` | display | Black subtitle background opacity (`0.4`–`1.0`) | `0.82` |
| `original_font_size` | display | Font size (px) for source text | `13` |
| `translated_font_size` | display | Font size (px) for translated text | `17` |

## Build the macOS application

The AppKit menu-bar application is packaged with `py2app`. Releases are
standalone `.app` bundles; `uv` is used only for development and builds.

```bash
uv sync --group build

# Development bundle that references the source tree
uv run python setup.py py2app --alias

# Standalone arm64 bundle
uv run python setup.py py2app
```

The result is `dist/Mac Live Subtitle.app`. It runs as an `LSUIElement`
application, so it has a menu-bar item and no Dock icon. Packaged and source
runs use the same `NSUserDefaults` suite and local credentials file. The
ignored development `config.ini` is not included in the bundle.

py2app applies an ad-hoc signature suitable for local testing. This project
uses one stable self-signed identity for open-source builds so ScreenCaptureKit
authorization survives updates. These builds cannot be notarized and require
the standard **Open Anyway** flow on first installation.

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

3. **Translation & display** — committed sentences are translated by the LLM endpoint (sliding context window) on a single serial executor, so interim and final translations cannot arrive out of order. Growing sentences fire temporary translations at length thresholds; the final translation overwrites them. A UI-neutral event sink dispatches results onto AppKit's main thread and rejects late events from a retired pipeline.

---

## Privacy & Data Flow

> **Speech data is cloud-processed.** Audio is streamed to the configured ASR
> service. When translation is enabled, transcribed text is sent to the
> configured translation provider. Transcripts are not persisted by default;
> the optional FunASR event log writes source text locally when configured.

## Roadmap

- Developer ID signing and notarization
- Additional streaming ASR providers

## Acknowledgments

Inspired by and forked from [Real-Time Translator](https://github.com/Vanyoo/realtime-subtitle) by Van (local ASR + dashboard/overlay architecture). This project replaces local ASR with cloud streaming and uses an AppKit menu-bar interface with a separate floating subtitle panel.

## License

MIT
