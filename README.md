# Mac Live Subtitle

<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="Mac Live Subtitle icon">
</p>

Real-time speech-to-text and translation with a floating subtitle window for macOS. Captures audio (system output via BlackHole, or any microphone) and streams it to a cloud ASR service, then displays translated subtitles on screen — perfect for meetings, lectures, videos, and gaming.

<video src="demo/demo.mp4" width="100%" autoplay muted loop></video>

https://github.com/user-attachments/assets/2faca983-a76b-4591-95a8-5a11c1233a83


## Quick Start

```bash
# Install
brew install blackhole-2ch
git clone https://github.com/Henry-Jessie/mac-live-subtitle.git
cd mac-live-subtitle
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.ini.example config.ini

# Set API keys (get from links below)
export DASHSCOPE_API_KEY="your-key"    # Qwen3 ASR
export DEEPSEEK_API_KEY="your-key"     # translation LLM

# Run
python app.py
```

Before running, [configure audio routing](#audio-routing-setup) for system audio capture.

| API Key | Get it from | |
|:---|:---|:---|
| Qwen3 ASR | [DashScope China](https://bailian.console.aliyun.com/) / [DashScope Intl](https://bailian.console.alibabacloud.com/) | Region-specific endpoints & keys — see [Configuration](#configuration) |
| Translation LLM | [DeepSeek](https://platform.deepseek.com/) | Default provider |
| *Alternatives* | [Deepgram](https://console.deepgram.com/) · [Google AI Studio](https://aistudio.google.com/) · [OpenAI](https://platform.openai.com/) | Deepgram offers $200 free credit |

## Features

### Cloud-based Streaming ASR

No local model, no GPU required. Two backends available:

- **Qwen3 ASR Realtime** (recommended) — 27 languages with excellent CJK performance, 5 Chinese dialect variants, server-side VAD, emotion recognition, and context injection
- **Deepgram Nova-3** — sub-300 ms latency, 47+ languages, real-time multilingual auto-detection (note: no Chinese support, limited Japanese/Korean accuracy)

### Hybrid Subtitle Segmentation

Two modes controlled by `use_llm_segmenter` in config:

- **LLM mode** (default) — a heuristic splitter proposes candidate segments, then an LLM reviews them: merging short fragments, holding incomplete segments when the ASR draft suggests more words are coming, and translating confirmed ones in a single call. Slightly higher latency, but handles edge cases (mid-sentence decimals, trailing abbreviations, numbering artifacts) that pure heuristics miss.
- **Heuristic-only mode** — only the rule-based splitter runs, each segment translated separately. Lowest latency, but occasional awkward breaks.

### Context-aware Translation

A sliding context window (capped by token count) feeds recent source/translation pairs into every request, keeping terminology consistent across sentences. Powered by any OpenAI-compatible Chat Completions API. Supports configurable temperature, extra body parameters, and reasoning-model `<think>` tag stripping.

### Single-window macOS-native UI

- Unified PyQt6 window with play/pause/stop controls
- Settings popover with provider presets (DeepSeek, Google Gemini, Custom)
- Pushpin button for always-on-top, visible across all macOS Spaces via PyObjC
- Soft pause/resume (keeps WebSocket alive) and automatic reconnection with exponential backoff

<details>
<summary><h2>Audio Routing Setup</h2></summary>

To capture system audio you need [BlackHole](https://existential.audio/blackhole/) (`brew install blackhole-2ch`) and a Multi-Output Device that mirrors sound to both your speakers and BlackHole.

1. Open **Audio MIDI Setup** (in /Applications/Utilities/)
2. Click **+** → **Create Multi-Output Device**
3. Check both **BlackHole 2ch** and your output device (e.g. MacBook Pro Speakers)
4. Set **Primary Device** to **BlackHole 2ch**, sample rate **48.0 kHz**
5. Right-click the Multi-Output Device → **Use This Device For Sound Output**

![Multi-Output Device setup](demo/how_to_set_blackhole.png)

> You can also skip BlackHole and point `device_index` at a physical microphone to transcribe live speech instead.

</details>

## Usage

Run `python app.py`. Use **Play** / **Pause** / **Stop** to control the pipeline, **Gear** for settings, **Pin** for always-on-top. Advanced settings (`use_llm_segmenter`, `temperature`, `extra_body`, VAD) require editing `config.ini`. Saving settings restarts the pipeline.

## Configuration

All settings are stored in `config.ini` and can be edited either in the settings popover or by hand. Copy `config.ini.example` as a starting point:

```bash
cp config.ini.example config.ini
```

### `[transcription]` — ASR backend

| Key | Description | Default |
|:---|:---|:---|
| `backend` | `deepgram_stream` or `qwen3_asr_realtime` | `qwen3_asr_realtime` |
| `source_language` | Language hint (`auto` = auto-detect) | `auto` |
| `deepgram_model` | Deepgram model name | `nova-3` |
| `qwen3_asr_realtime_model` | Qwen3 model name | `qwen3-asr-flash-realtime` |
| `qwen3_asr_realtime_ws_url` | WebSocket endpoint — Beijing: `wss://dashscope.aliyuncs.com/api-ws/v1/realtime`, Singapore: `wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime` (API keys are region-specific and not interchangeable) | Beijing endpoint |
| `qwen3_asr_realtime_api_key_env` | Env var name holding the API key | `DASHSCOPE_API_KEY` |
| `qwen3_asr_realtime_api_key` | API key value directly (takes precedence over env var) | *(empty)* |
| `qwen3_asr_realtime_server_vad` | Enable server-side voice activity detection | `true` |
| `qwen3_asr_realtime_vad_threshold` | VAD sensitivity (`0.0` = server default, higher = less sensitive) | `0.0` |
| `qwen3_asr_realtime_silence_duration_ms` | Silence before utterance is considered finished | `400` |

> **Note on Deepgram API keys**: the Deepgram SDK reads `DEEPGRAM_API_KEY` directly from the environment. Unlike Qwen3 and the translation LLM, Deepgram keys cannot be set via `config.ini` or the settings UI — you must `export DEEPGRAM_API_KEY` in your shell.

### `[translation]` — LLM translation

| Key | Description | Default |
|:---|:---|:---|
| `base_url` | OpenAI-compatible API endpoint | `https://api.deepseek.com/v1` |
| `api_key_env` | Env var name holding the API key (see below) | `DEEPSEEK_API_KEY` |
| `api_key` | API key value directly (takes precedence over `api_key_env`) | *(empty)* |
| `model` | Model identifier | `deepseek-chat` |
| `target_lang` | Target language for translation | `Simplified Chinese` |
| `use_llm_segmenter` | Use LLM for hybrid segmentation + translation (see below) | `true` |
| `temperature` | Sampling temperature | `1.0` |
| `extra_body` | Extra JSON merged into API calls (e.g. `{"thinking": {"type": "disabled"}}`) | *(empty)* |

> **API key resolution**: the app looks up the key in this order: `api_key` in config (literal value) → environment variable named by `api_key_env`. In the settings UI, you can type either a raw key (`sk-...`) or an env var reference prefixed with `$` (e.g. `$DEEPSEEK_API_KEY`), and the app will store it accordingly.

### `[audio]` / `[display]`

| Key | Section | Description | Default |
|:---|:---|:---|:---|
| `device_index` | audio | `auto` (detect BlackHole) or a specific device index | `auto` |
| `sample_rate` | audio | Sample rate in Hz | `16000` |
| `streaming_step_size` | audio | Audio frame duration in seconds | `0.2` |
| `always_on_top` | display | Start with window pinned on top | `true` |

## Troubleshooting

<details>
<summary><b>No audio captured</b></summary>

- Run `python core/audio_capture.py` to list devices and test capture
- Ensure BlackHole is installed and Multi-Output Device is set as system output
- Check `device_index = auto` in `config.ini` (or set the correct index manually)
</details>

<details>
<summary><b>ASR not connecting</b></summary>

- Verify your API key environment variable is exported
- Deepgram returns 401/403 for invalid keys; Qwen3 returns an error event
- The app retries up to 6 times with exponential backoff
</details>

<details>
<summary><b>Translation not appearing</b></summary>

- Confirm `[translation] base_url`, `api_key_env`, and `model` are set correctly
- The env var named in `api_key_env` must be exported (e.g. `export DEEPSEEK_API_KEY=...`)
- Check the console for `[Translator]` error logs
</details>

<details>
<summary><b>High latency</b></summary>

- Try a faster translation model (e.g. DeepSeek Chat or Gemini Flash)
- Reduce `streaming_step_size` for more frequent audio frames
- For Qwen3, lower `qwen3_asr_realtime_silence_duration_ms` for faster utterance finalization
</details>

## How It Works

The pipeline has three concurrent stages:

1. **Audio capture** — opens the configured input device via `sounddevice` (16 kHz mono, configurable step size). Auto-detects BlackHole by default; any input device can be selected via `device_index`.

2. **Streaming ASR** — the chosen backend establishes a WebSocket to the cloud, converts frames to PCM16, and streams continuously. Interim and final results feed into a `StreamingSegmenter` that accumulates text, tracks drafts, and dispatches translation at segment boundaries.

3. **Translation & display** — confirmed segments (with sliding context and optional trailing draft) are sent to the LLM endpoint. Translations arrive via Qt signals and appear as timestamped original/translation pairs with auto-scroll.

---

## Privacy & Data Flow

> **All data is cloud-processed.** Audio is streamed to a cloud ASR service; transcribed text is sent to an external LLM for translation. No data stays local. Be mindful of this in sensitive contexts — speech content passes through third-party servers subject to their privacy policies. An active internet connection is required.

## Roadmap

- **Local Qwen3 ASR** — run [Qwen3-ASR-1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B) on-device to eliminate cloud dependency and improve privacy

## Acknowledgments

Inspired by and forked from [Real-Time Translator](https://github.com/Van-Yo/realtime-subtitle) by Van (local ASR + dashboard/overlay architecture). This project replaces local ASR with cloud streaming, adds hybrid LLM segmentation, and consolidates the UI into a single macOS-native window.

## License

MIT
