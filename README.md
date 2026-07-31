# Mac Live Subtitle

English | [简体中文](README.zh-CN.md)

<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="Mac Live Subtitle icon">
</p>

<p align="center">
  <a href="https://github.com/Henry-Jessie/mac-live-subtitle/releases/latest"><img src="https://img.shields.io/github/v/release/Henry-Jessie/mac-live-subtitle?display_name=tag&sort=semver" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/macOS-13%2B-000000?logo=apple" alt="macOS 13 or later">
  <img src="https://img.shields.io/badge/Apple%20Silicon-arm64-333333" alt="Apple Silicon arm64">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
</p>

Real-time system-audio transcription and optional translation in a native
macOS menu-bar app. Mac Live Subtitle captures audio through
ScreenCaptureKit, sends it to FunASR Realtime, and keeps a resizable subtitle
panel above meetings, lectures, videos, and games.

### [Download the latest release →](https://github.com/Henry-Jessie/mac-live-subtitle/releases/latest)

The packaged app requires **macOS 13 or later** and an **Apple Silicon Mac**.
It does not require Python, BlackHole, a Multi-Output Device, or a local GPU.

<p align="center">
  <img src="docs/images/subtitle-window.png" width="760" alt="Floating Mac Live Subtitle window">
</p>

## Highlights

- Native AppKit menu-bar app with no Dock icon.
- Direct system-audio capture through ScreenCaptureKit.
- Streaming FunASR Realtime transcription with interim and final results.
- Optional translation through DeepSeek, Gemini, or a custom
  OpenAI-compatible endpoint.
- Floating black subtitle panel with play, pause, stop, pin, and settings
  controls.
- Adjustable background opacity and separate source/translation font sizes.
- English and Chinese settings interface.
- API keys stored locally without Keychain authorization prompts.

## Install

1. Download `Mac-Live-Subtitle-v0.1.0-macos-arm64.zip` from
   [GitHub Releases](https://github.com/Henry-Jessie/mac-live-subtitle/releases/latest).
2. Unzip it and move **Mac Live Subtitle.app** to `/Applications`.
3. Open the app once. Because the current release is self-signed and not
   notarized by Apple, macOS may block the first launch.
4. Open **System Settings → Privacy & Security**, scroll to **Security**, then
   choose **Open Anyway** for Mac Live Subtitle.
5. Open the app again. Its icon appears in the menu bar, and the subtitle
   window opens without starting capture.

The release page includes `SHA256SUMS.txt` so the downloaded archive can be
checked before installation:

```bash
shasum -a 256 -c SHA256SUMS.txt
```

## Configure services

Open **Settings** from either the menu-bar menu or the subtitle-window gear
button.

### Transcription

FunASR Realtime requires an Alibaba Cloud Model Studio API key:

- [China API key guide](https://help.aliyun.com/zh/model-studio/get-api-key)
- [International API key guide](https://www.alibabacloud.com/help/en/model-studio/get-api-key)

Enter the key under **Settings → Transcription**. The API key and WebSocket
endpoint must belong to the same Alibaba Cloud region. The built-in China and
International guide buttons open the same documentation.

Semantic punctuation gives more natural sentence boundaries but may produce
longer segments. Advanced settings also provide a VAD mode, a silence
threshold, multi-threshold VAD, and interim translation intervals.

### Translation

Translation is optional. Choose one of these providers under
**Settings → Translation**:

- **DeepSeek** — preconfigured for the DeepSeek OpenAI-compatible API;
  [create an API key](https://platform.deepseek.com/api_keys).
- **Gemini** — preconfigured for the Gemini OpenAI-compatible API;
  [create an API key in Google AI Studio](https://aistudio.google.com/app/apikey).
- **Custom** — enter any compatible Base URL and model name.

Select a target language, enter the provider API key, and use
**Test Connection** before saving. Turning translation off leaves the
original-language subtitles enabled.

<p align="center">
  <img src="docs/images/settings-translation.png" width="49%" alt="Translation settings">
  <img src="docs/images/settings-display.png" width="49%" alt="Display settings">
</p>

## Use

Press **Play** in the subtitle window to start capture. On first use, approve
the macOS system-audio prompt. If the permission was dismissed, enable
**Mac Live Subtitle** under:

**System Settings → Privacy & Security → Screen & System Audio Recording**

Quit and reopen the app after changing this permission.

| Control | Action |
|:--|:--|
| Play / Pause | Start capture, pause a live session, or resume it |
| Stop | Close the current ASR and translation session |
| Pin | Keep the subtitle panel above other windows |
| Settings | Open transcription, translation, and display settings |

The top strip of the subtitle panel moves the window. Its edges and corners
resize it. Closing the panel hides it; choose **Subtitle Window** from the
menu-bar menu to show it again.

## Privacy and data flow

- System audio is streamed to the configured Alibaba Cloud FunASR service.
- When translation is enabled, transcribed text is sent to the selected
  translation provider.
- Transcripts are not stored by default. The optional FunASR event log writes
  source text locally when explicitly enabled.
- API keys are stored at
  `~/Library/Application Support/Mac Live Subtitle/credentials.json`.
  The directory is limited to the current macOS user and the file uses mode
  `0600`.
- The credentials file is local plaintext. Other processes running as the
  same macOS user may be able to read it.
- The app does not read or modify existing Keychain items.

## Troubleshooting

<details>
<summary><b>The app cannot be opened</b></summary>

Try opening it once, then go to **System Settings → Privacy & Security** and
choose **Open Anyway**. The current public build uses a stable self-signed
certificate so macOS can recognize later updates, but it is not Apple
notarized.

</details>

<details>
<summary><b>Screen audio permission is enabled but capture is denied</b></summary>

Confirm that the permission belongs to **Mac Live Subtitle.app**, not Terminal
or a source-Python process. Quit the app completely after changing the
permission, then reopen it from `/Applications`.

</details>

<details>
<summary><b>FunASR does not connect</b></summary>

Check the API key and WebSocket endpoint under
**Settings → Transcription**. Region-specific keys cannot be used with an
endpoint from another region. Connection and server errors appear in the
subtitle-window banner.

</details>

<details>
<summary><b>Translation does not appear</b></summary>

Confirm that translation is enabled, the selected provider has an API key,
and the target language is filled in. For Custom providers, also verify the
Base URL and model name under Advanced.

</details>

<details>
<summary><b>Sentences are too long</b></summary>

Disable semantic punctuation to use VAD segmentation, then lower the
maximum-silence value. Multi-threshold VAD can further limit unusually long
segments. Interim translation can provide updates while a final sentence is
still growing.

</details>

## Run from source

Source development requires macOS, Python 3.10 or later, and
[uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/Henry-Jessie/mac-live-subtitle.git
cd mac-live-subtitle
uv sync --group build
uv run python app.py
```

Source and packaged runs use the same `NSUserDefaults` suite and local
credentials file. An existing `config.ini` is imported once on the first
native launch and is not rewritten.

Run the tests with:

```bash
uv run python -m unittest discover -s tests
```

## Build a release

The project uses py2app and a stable local signing identity. The release
script performs a clean build, signs the bundle, verifies it, creates the
macOS ZIP, writes its SHA-256 checksum, extracts it, and verifies the
extracted bundle again:

```bash
./scripts/package_release.sh 0.1.0
```

Artifacts are written to `release/v0.1.0/`. The signing identity defaults to
`Mac Live Subtitle Local Signing` and can be changed with
`CODESIGN_IDENTITY`.

The current public build is Apple Silicon only. Developer ID signing and
Apple notarization remain outside the `v0.1.0` release.

## How it works

1. **Capture** — ScreenCaptureKit supplies system audio as variable-sized
   sample buffers. The capture layer converts them into 16 kHz mono PCM
   frames.
2. **Transcription** — FunASR Realtime receives the PCM stream over WebSocket.
   Interim events update the current line and final events commit a sentence.
3. **Translation** — a serial translation executor sends committed text to
   the selected provider with a bounded context window, then dispatches UI
   updates back to AppKit's main thread.

## Acknowledgments

Inspired by and forked from
[Real-Time Translator](https://github.com/Vanyoo/realtime-subtitle) by Van.
Mac Live Subtitle replaces the original local-ASR and PyQt interface with
cloud streaming ASR, ScreenCaptureKit, and a native AppKit menu-bar app.

## License

[MIT](LICENSE)
