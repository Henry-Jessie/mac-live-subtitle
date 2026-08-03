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

Mac Live Subtitle is a native macOS menu-bar app for real-time system-audio
transcription and optional translation. It keeps a resizable subtitle panel
above meetings, lectures, videos, and games.

### [Download the latest release →](https://github.com/Henry-Jessie/mac-live-subtitle/releases/latest)

Requires **macOS 13 or later** and an **Apple Silicon Mac**. Native capture
requires no Python, BlackHole, Multi-Output Device, or local GPU. BlackHole is
available as a compatibility mode for protected players such as Apple TV.

<p align="center">
  <img src="docs/images/subtitle-window.png" width="760" alt="Floating Mac Live Subtitle window">
</p>

## Highlights

- Native AppKit menu-bar app and floating subtitle panel.
- Native ScreenCaptureKit audio capture with optional BlackHole compatibility.
- Streaming FunASR Realtime transcription with interim and final results.
- Optional DeepSeek, Gemini, or custom OpenAI-compatible translation.
- Play, pause, stop, pin, opacity, font, and bilingual-settings controls.

## Demo

<p align="center">
  <img src="docs/images/demo.gif" width="760" alt="Live transcription, translation, and display controls">
</p>

## Install

1. Download the latest macOS arm64 ZIP from
   [GitHub Releases](https://github.com/Henry-Jessie/mac-live-subtitle/releases/latest).
2. Unzip it and move **Mac Live Subtitle.app** to `/Applications`.
3. Try to open the app once. macOS may block the first launch.
4. Open **System Settings → Privacy & Security**, scroll to **Security**, and
   choose **Open Anyway** for Mac Live Subtitle.
5. Open the app again. Its menu-bar icon and subtitle window will appear
   without starting capture.

## Configure

Open **Settings** from the menu-bar menu or the subtitle-window gear button.

### Transcription

FunASR Realtime requires an Alibaba Cloud Model Studio API key:

- [China API key guide](https://help.aliyun.com/zh/model-studio/get-api-key)
- [International API key guide](https://www.alibabacloud.com/help/en/model-studio/get-api-key)

Under **Settings → Transcription**, choose China (Beijing) or International
(Singapore), then enter a key from the same region. The app selects the
matching WebSocket endpoint automatically. Advanced settings control sentence
segmentation and the audio-capture backend. Interim translation is scheduled
automatically, while complete sentences are translated immediately.

### Translation

Translation is optional. Choose a target language and one provider:

- [DeepSeek](https://platform.deepseek.com/api_keys)
- [Gemini](https://aistudio.google.com/app/apikey)
- **Custom** — enter an OpenAI-compatible Base URL and model name.

Enter the provider API key and use **Test Connection** before saving. Turning
translation off leaves the original-language subtitles enabled.

Transcription, translation, service-region, and audio-capture changes take
effect the next time capture starts. Subtitle font, opacity, and pinning
changes apply immediately.

<p align="center">
  <img src="docs/images/settings-transcription.png" width="760" alt="Transcription settings">
</p>

<p align="center">
  <img src="docs/images/settings-translation.png" width="49%" alt="Translation settings">
  <img src="docs/images/settings-display.png" width="49%" alt="Display settings">
</p>

## Use

Press **Play** to start capture. Native capture requires permission under:

**System Settings → Privacy & Security → Screen & System Audio Recording**

Quit and reopen the app after changing this permission.

BlackHole Compatibility instead uses **Microphone** permission because macOS
treats the virtual input as a microphone device.

| Control | Action |
|:--|:--|
| Play / Pause | Start, pause, or resume the current session |
| Stop | Close the current ASR and translation session |
| Pin | Keep the subtitle panel above other windows |

Drag the panel's top strip to move it and its edges or corners to resize it.
Closing the panel hides it; choose **Subtitle Window** from the menu-bar menu
to show it again.

## Privacy

- System audio is streamed to Alibaba Cloud FunASR. When translation is
  enabled, transcribed text is sent to the selected translation provider.
- Transcripts are not stored by default. The optional FunASR event log writes
  source text locally only when explicitly enabled.
- API keys are stored as local plaintext at
  `~/Library/Application Support/Mac Live Subtitle/credentials.json`.
  The directory uses mode `0700` and the file uses `0600`; other processes
  running as the same macOS user may still be able to read it.
- The app does not read or modify existing Keychain items.

## Troubleshooting

<details>
<summary><b>Apple TV turns black during transcription</b></summary>

Protected Apple TV video is hidden while ScreenCaptureKit is active. To keep
Apple TV playback visible during transcription, install
[BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole), create a
Multi-Output Device containing the built-in output and BlackHole, make the
built-in output the primary device, select that Multi-Output Device as the
macOS sound output, and choose **BlackHole Compatibility** under
**Settings → Transcription → Advanced**. After use, switch the macOS sound
output back to the preferred device. The app detects BlackHole on each start;
no device number is saved.

</details>

<details>
<summary><b>Permission is enabled but capture is denied</b></summary>

Confirm that the permission belongs to **Mac Live Subtitle.app**, not Terminal
or a source-Python process. Quit the app completely after changing the
permission, then reopen it from `/Applications`.

</details>

<details>
<summary><b>FunASR does not connect</b></summary>

Check the API key and service region under **Settings → Transcription**.
Region-specific keys cannot be used with another service region.

</details>

<details>
<summary><b>Translation does not appear</b></summary>

Confirm that translation is enabled, the selected provider has an API key,
and the target language is filled in. Custom providers also require a Base
URL and model name under Advanced.

</details>

<details>
<summary><b>Sentences are too long</b></summary>

Disable semantic punctuation to use VAD segmentation, then lower maximum
silence. Multi-threshold VAD can further limit long segments; interim
translation can update the translation before the final sentence ends.

</details>

## For developers

Development requires macOS, Python 3.10 or later, and
[uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/Henry-Jessie/mac-live-subtitle.git
cd mac-live-subtitle
uv sync --group build
uv run python app.py
uv run python -m unittest discover -s tests
```

Release maintainers can build, sign, archive, and verify `v0.1.0` with
`./scripts/package_release.sh 0.1.0`; the configured signing identity is
required.

## Acknowledgments

Inspired by and forked from
[Real-Time Translator](https://github.com/Vanyoo/realtime-subtitle) by Van.

## License

[MIT](LICENSE)
