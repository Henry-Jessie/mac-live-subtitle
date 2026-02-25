# Mac Live Subtitle

<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="Mac Live Subtitle icon">
</p>

Real-time speech-to-text and translation with a floating subtitle window for macOS. Captures audio (system output via BlackHole, or any microphone) and streams it to a cloud ASR service, then displays translated subtitles on screen — perfect for meetings, lectures, videos, and gaming.

<video src="demo/demo.mp4" width="100%" autoplay muted loop></video>

https://github.com/user-attachments/assets/2faca983-a76b-4591-95a8-5a11c1233a83


## Quick Start

```bash
brew install blackhole-2ch                        # 1. install virtual audio driver
# 2. configure Multi-Output Device (see Audio Routing Setup below)
git clone https://github.com/Henry-Jessie/mac-live-subtitle.git && cd mac-live-subtitle
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt                   # 3. install dependencies
cp config.ini.example config.ini                  # 4. create config file
export DASHSCOPE_API_KEY="your-key"               # 5. set ASR key (Qwen3, China mainland)
# For international region, also set ws_url in config.ini — see below
export DEEPSEEK_API_KEY="your-key"                # 6. set translation LLM key
python app.py                                     # 7. launch
```

Step 2 details: [Audio Routing Setup](#audio-routing-setup)

Get API keys (required for the default setup):
[DashScope China](https://bailian.console.aliyun.com/) or [DashScope Intl](https://bailian.console.alibabacloud.com/) (Qwen3 ASR) |
[DeepSeek](https://platform.deepseek.com/) (translation LLM)

> DashScope China and International use different endpoints and API keys — see [Configuration](#configuration) for details.
> Other supported providers: [Deepgram](https://console.deepgram.com/) ($200 free credit), [Google AI Studio](https://aistudio.google.com/), [OpenAI](https://platform.openai.com/)

## Features

**Cloud-based streaming ASR** — no local model, no GPU required. Two backends available: Deepgram Nova-3 delivers sub-300 ms latency with 47+ languages and real-time multilingual auto-detection, though it lacks Chinese support and has limited Japanese/Korean accuracy. Qwen3 ASR Realtime covers 27 languages with excellent CJK performance (including 5 Chinese dialect variants), server-side VAD, emotion recognition, and context injection, making it the recommended default for most users.

**Hybrid subtitle segmentation** — two modes controlled by `use_llm_segmenter` in config. When **enabled** (default), a heuristic splitter first proposes candidate segments based on punctuation, abbreviations, and token counts, then an LLM reviews these candidates — merging short fragments, holding incomplete segments when the ASR draft suggests more words are coming, and translating confirmed segments in one call. This adds a small amount of latency but handles edge cases (mid-sentence decimals, trailing abbreviations, numbering artifacts) that pure heuristics miss. When **disabled**, only the heuristic splitter runs and each segment is translated separately, giving the lowest possible latency at the cost of occasional awkward breaks.

**Context-aware translation** — A sliding context window (capped by token count) feeds recent source/translation pairs into every request, keeping terminology consistent across sentences. Supports configurable temperature, extra body parameters, and reasoning-model `<think>` tag stripping.

**Single-window macOS-native UI** — a unified PyQt6 window with play/pause/stop controls, a settings popover with provider presets (DeepSeek, Google Gemini, Custom), and a pushpin for always-on-top. Visible across all macOS Spaces via PyObjC. Supports soft pause/resume (keeps WebSocket alive) and automatic reconnection with exponential backoff.

## Audio Routing Setup

To capture system audio you need [BlackHole](https://existential.audio/blackhole/) (`brew install blackhole-2ch`) and a Multi-Output Device that mirrors sound to both your speakers and BlackHole.

1. Open **Audio MIDI Setup** (in /Applications/Utilities/).
2. Click the **+** button at the bottom left, select **Create Multi-Output Device**.
3. Check both **BlackHole 2ch** and your regular output device (e.g. MacBook Pro Speakers).
4. Set the **Primary Device** (master clock) to **BlackHole 2ch**.
5. Keep the sample rate at **48.0 kHz** (default).
6. Right-click the Multi-Output Device and select **Use This Device For Sound Output**.

![Multi-Output Device setup](demo/how_to_set_blackhole.png)

> The Multi-Output Device mirrors audio to all checked devices. BlackHole acts as a loopback — the app reads from its input endpoint while you hear audio normally through your speakers. You can also skip BlackHole and point `device_index` at a physical microphone to transcribe live speech instead.

## Usage

```bash
python app.py
```

A floating subtitle window appears at the bottom of your screen. Click **Play** to start capturing and transcribing. Use the **gear icon** to open settings, where you can switch ASR providers, choose translation models, and adjust common options. Some advanced settings (e.g. `use_llm_segmenter`, `temperature`, `extra_body`, VAD parameters) are only available by editing `config.ini` directly. Saving settings automatically stops the current pipeline — click **Play** again to apply changes.

### Controls

| Button | Action |
|:---|:---|
| **Play** | Start transcription (or resume from pause) |
| **Pause** | Soft-pause the stream (keeps connection alive) |
| **Stop** | Full stop — tears down the pipeline and clears display |
| **Gear** | Open the settings popover |
| **Pin** | Toggle always-on-top |

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

### `[audio]` — Audio input

| Key | Description | Default |
|:---|:---|:---|
| `device_index` | `auto` (detect BlackHole) or a specific device index | `auto` |
| `sample_rate` | Sample rate in Hz | `16000` |
| `streaming_step_size` | Audio frame duration in seconds | `0.2` |

### `[display]` — Window behavior

| Key | Description | Default |
|:---|:---|:---|
| `always_on_top` | Start with window pinned on top | `true` |

## Troubleshooting

**No audio captured** — Run `python core/audio_capture.py` to list devices and test capture. Ensure BlackHole is installed and a Multi-Output Device is configured as system output. Check that `device_index = auto` in `config.ini` (or set the correct index manually).

**ASR not connecting** — Verify your API key environment variable is exported. Check the console for connection errors. Deepgram returns 401/403 for invalid keys; Qwen3 returns an error event. The app retries up to 6 times with backoff.

**Translation not appearing** — Confirm `[translation] base_url`, `api_key_env`, and `model` are correctly set. The env var named in `api_key_env` must be exported (e.g. `export DEEPSEEK_API_KEY=...`). Check the console for `[Translator]` error logs.

**Window not staying on top** — Click the pin button in the top-right of the window. For all-Spaces visibility, ensure `pyobjc-framework-Cocoa` is installed (`pip install pyobjc-framework-Cocoa`).

**High latency** — Try a faster translation model (e.g. DeepSeek Chat or Gemini Flash). Reduce `streaming_step_size` for more frequent audio frames. For Qwen3, lowering `qwen3_asr_realtime_silence_duration_ms` triggers faster utterance finalization.

## How It Works

The pipeline has three stages that run concurrently:

**1. Audio capture** — `core/audio_capture.py` opens the configured audio input device via `sounddevice`, reading 16 kHz mono float32 frames at a configurable step size (default 200 ms). By default the app auto-detects BlackHole for system audio capture, but any input device (including a physical microphone) can be selected via `device_index` in config or the settings UI. Frames are yielded from a generator to the ASR backend.

**2. Streaming ASR** — the chosen backend (`asr/deepgram_stream.py` or `asr/qwen3_asr_realtime.py`) establishes a WebSocket connection to the cloud service, converts float32 frames to PCM16, and streams them continuously. As interim and final transcription results arrive, they are fed into a `StreamingSegmenter` that accumulates confirmed text, tracks interim drafts, and dispatches translation when a segment boundary is detected.

**3. Translation & display** — the `Translator` sends confirmed segments (with sliding context and optional trailing draft for disambiguation) to the configured LLM endpoint. Translated text is emitted via Qt signals to the `SubtitleWindow`, where each segment appears as a timestamped original/translation pair with auto-scroll.

## Privacy & Data Flow

This app streams audio to a cloud ASR service and sends transcribed text to an external LLM for translation. No audio or text is processed locally (unlike the upstream project which uses on-device ASR models). Be mindful of this when using the app in sensitive contexts — all speech content passes through third-party servers subject to their respective privacy policies. An active internet connection is required at all times.

## Roadmap

- Local Qwen3 ASR model support — run `Qwen3-ASR` on-device to eliminate cloud dependency and improve privacy, leveraging the [open-source Qwen3-ASR weights](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)

## Acknowledgments

This project was inspired by and initially forked from [Real-Time Translator](https://github.com/Van-Yo/realtime-subtitle) by Van, which uses local ASR backends (faster-whisper, mlx-whisper, FunASR) with a dashboard + overlay two-window architecture. Mac Live Subtitle replaces the local ASR engines with cloud-based streaming services, introduces hybrid LLM segmentation, and consolidates the UI into a single macOS-native window.

## License

MIT
