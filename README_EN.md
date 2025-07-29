# Deepgram Live Caption

English | [中文](./README.md)

Real-time system audio transcription and translation with floating subtitles for macOS.

## Features

- **Ultra-low latency transcription** using Deepgram's streaming API (<500ms)
- **Real-time translation** to Chinese with context awareness
- **Floating subtitle window** that stays on top of other applications
- **Automatic language detection** (Chinese, Japanese, English, etc.)
- **Intelligent subtitle polishing** with error correction
- **Resizable subtitle window** with customizable appearance
- **Automatic reconnection** on connection failures


## How It Works

### Deepgram Streaming ASR

Deepgram provides real‑time automatic speech recognition (ASR). The client streams short audio frames to Deepgram's cloud over WebSocket and receives the corresponding transcription within a few hundred milliseconds. This project simply forwards the captured system audio to Deepgram and renders the returned captions—no local speech‑to‑text model is required.

#### Deepgram Nova-3 Multi Pricing
- Real-time streaming transcription: $0.0092/minute ($0.552/hour)
- Supports automatic multi-language detection (Chinese, Japanese, English, etc.)
- $200 free credit allows for approximately 362 hours of usage

### BlackHole Virtual Audio Device

BlackHole is an open‑source virtual audio driver for macOS built on Core Audio DriverKit. It allocates a kernel‑space **ring buffer** that is exposed both as an output endpoint (where the OS writes PCM samples) and as an input endpoint (from which capture applications can read).

By creating a **Multi‑Output Device** in Audio MIDI Setup, system audio is mirrored to both your physical speakers and BlackHole. The `audio_capture.py` module opens BlackHole’s input endpoint, grabs the 48 kHz stereo stream, down‑samples it to 16 kHz mono, and streams it to Deepgram—enabling hardware‑free, near‑zero‑latency system audio capture.

### Intelligent Translation & Polish

The translation system works in two stages:

1. **Real-time Transcription**: Deepgram provides both interim (partial) and final transcription results. Interim results update continuously as the audio is being captured, providing immediate visual feedback.

2. **Context-aware Translation**: 
   - Translations are triggered either when Deepgram marks a segment as "final" or after 1 second of continuous speech
   - The polish model (configurable, default: Gemini 2.5 Flash via OpenRouter) receives the transcribed text along with recent context
   - The model performs three tasks simultaneously:
     - **Error Correction**: Fixes common ASR errors (e.g., "P vs MP" → "P vs NP")
     - **Context Enhancement**: Uses conversation history to improve accuracy
     - **Translation**: Produces natural Chinese translations while preserving technical terms
   
3. **Display Logic**:
   - Original text updates in real-time with every interim result
   - Chinese translation remains stable and only updates when new translation is received
   - This prevents flickering and maintains readability

## Requirements

- macOS (tested on macOS 15.5)
- Python 3.10+
- BlackHole virtual audio device (for system audio capture)
- Deepgram API key
- OpenRouter API key (or other LLM provider for translation)

## Setup

### 1. Install dependencies

Install required system dependencies via Homebrew:

```bash
# Install BlackHole for audio capture
brew install blackhole-2ch

# Install Python tkinter (if not already installed)
brew install python-tk
```

Or download BlackHole from: https://existential.audio/blackhole/

### 2. Clone the repository

```bash
git clone https://github.com/Henry-Jessie/mac-live-subtitle.git
cd mac-live-subtitle
```

### 3. Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure API keys

Create a `.env` file in the project root:

```bash
# Required
DEEPGRAM_API_KEY=your_deepgram_api_key_here

# For translation (choose one)
OPENROUTER_API_KEY=your_openrouter_api_key_here
# Or use OpenAI directly
OPENAI_API_KEY=your_openai_api_key_here
```

Get your API keys from:
- Deepgram: https://console.deepgram.com/
- OpenRouter: https://openrouter.ai/
- OpenAI: https://platform.openai.com/

### 6. Configure audio routing

1. Open **Audio MIDI Setup** (found in /Applications/Utilities/)
2. Click the "+" button at the bottom left and select "Create Multi-Output Device"
3. Check both "BlackHole 2ch" and your regular output device (e.g., "MacBook Pro Speakers"). Set the master output device at the top to the actual output device (e.g., 'MacBook Pro Speakers'), not 'BlackHole 2ch'
4. Set sample rate to 48.0 kHz(which is the default sample rate, most of the time you don't need to change it)
5. Right-click the Multi-Output Device and select "Use This Device For Sound Output"

This allows you to hear audio normally while the app captures it.

## Configuration

Edit `config/config.yaml` to customize:

```yaml
# Audio settings
audio:
  device_name: "BlackHole 2ch"  # Virtual audio device name
  sample_rate: 16000
  channels: 1
  chunk_duration: 0.5
  buffer_size: 2048

# Deepgram settings
deepgram:
  model: "nova-3"  # Best model for real-time transcription
  language: "multi"  # Auto-detect zh/ja/en
  interim_results: true  # Show partial results
  
  # Translation model settings
  polish:
    model: "google/gemini-2.5-flash"  # Fast and accurate
    api_key_env: "OPENROUTER_API_KEY"  # Which env var to use
    base_url: "https://openrouter.ai/api/v1"

# Display settings
display:
  window_width: 800
  window_height: 150
  window_opacity: 0.9
  always_on_top: true
  position_y_offset: 100  # Distance from bottom
  resizable: true  # Allow window resizing
```

See `config/config.yaml` for the full configuration options.

## Usage

### Basic usage

```bash
python main.py
```

### Command line options

```bash
# List available audio devices
python main.py --list-devices

# Use a different audio device
python main.py --device "Your Device Name"

# Use a different config file
python main.py --config path/to/config.yaml
```

### Keyboard shortcuts

- **Drag window**: Click and drag the subtitle window to reposition
- **Resize window**: Drag window edges (if resizable is enabled)
- **Hide window**: Press `Esc` when window is focused
- **Exit**: Press `Ctrl+C` in terminal

## Project Structure

```
gemini-live-subtitle/
├── main.py                      # Main application entry point
├── requirements.txt             # Python dependencies
├── config/
│   └── config.yaml              # Main configuration file
├── src/
│   ├── audio_capture.py         # macOS audio capture module
│   ├── deepgram_transcriber.py  # Deepgram streaming transcription
│   └── subtitle_display.py      # Subtitle window UI
├── tests/                       # Test utilities
│   ├── test_audio_capture.py    # Audio capture testing
│   ├── test_deepgram_transcriber.py  # Transcription pipeline testing
│   └── test_window.py           # Subtitle window testing
└── logs/
    └── subtitle.log             # Application logs
```

## Troubleshooting

### No audio is being captured

1. Check that BlackHole is installed and visible in Audio MIDI Setup
2. Ensure your Multi-Output Device includes both BlackHole and your speakers
3. Run `python main.py --list-devices` to verify BlackHole is detected

### Subtitles not appearing

1. Check the logs in `logs/subtitle.log` for errors
2. Verify your API keys are correctly set in `.env`
3. Ensure the subtitle window isn't hidden behind other windows

### High latency or delays

1. Check your internet connection
2. Consider using a faster translation model in config
3. Reduce `chunk_duration` in audio settings (may increase CPU usage)

### WebSocket connection errors

The app automatically reconnects on connection failures. If issues persist:
1. Check your Deepgram API key is valid
2. Verify your internet connection is stable
3. Check Deepgram service status

### Test Tools

The `tests/` directory contains utilities to help diagnose issues:

#### 1. **test_audio_capture.py** - Test system audio capture
```bash
python tests/test_audio_capture.py
```
- Tests if BlackHole is properly configured and receiving audio
- Shows real-time volume levels and audio statistics
- Converts 48kHz stereo input to 16kHz mono output
- Use this when: Audio is not being captured or you see no volume activity

#### 2. **test_deepgram_transcriber.py** - Test transcription pipeline
```bash
python tests/test_deepgram_transcriber.py
```
- Tests the complete transcription and translation pipeline
- Shows real-time transcription (interim results) and Chinese translations
- Verifies Deepgram API connection and polish model functionality
- Use this when: Transcription is not working or translations are not appearing

#### 3. **test_window.py** - Test subtitle display window
```bash
python tests/test_window.py

# Test with resizable window
python tests/test_window.py --resizable

# Test without resizable window
python tests/test_window.py --no-resizable

# Disable debug output
python tests/test_window.py --no-debug
```
- Tests if the subtitle window displays correctly
- Shows test messages in both English and Chinese, and tests long text wrapping
- Verifies window positioning, update functionality, and resizing behavior
- Outputs window dimensions and wraplength debug information
- Use this when: The subtitle window is not appearing, updating properly, or has resizing issues

## License

MIT License - see LICENSE file for details