#!/usr/bin/env python3
"""Test Deepgram streaming transcriber."""

import asyncio
import os
import sys
import yaml
import logging
from dotenv import load_dotenv

# Minimal logging
logging.basicConfig(level=logging.WARNING)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.deepgram_transcriber import DeepgramTranscriber
from src.audio_capture import MacSystemAudioCapture

async def test_deepgram_transcriber():
    """Test Deepgram transcriber with system audio."""
    # Load environment
    load_dotenv(override=True)
    
    api_key = os.environ.get('DEEPGRAM_API_KEY')
    if not api_key:
        print("Error: DEEPGRAM_API_KEY not set in .env file")
        print("Please sign up at https://deepgram.com and add your API key to .env")
        return
    
    
    # print("\n=== Testing Deepgram Streaming Transcriber ===")
    
    # Load config
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Get polish model config (reuse from OpenAI config)
    openai_config = config.get('openai', {})
    polish_model = openai_config.get('polish_model', 'gpt-4o-mini')
    
    # Check if polish model is from OpenRouter
    polish_api_key = None
    polish_base_url = None
    if polish_model and not polish_model.startswith('gpt-'):
        # Likely an OpenRouter model
        openrouter_key = os.getenv('OPENROUTER_API_KEY')
        if openrouter_key:
            polish_api_key = openrouter_key
            polish_base_url = "https://openrouter.ai/api/v1"
            # print(f"Using OpenRouter for polish model: {polish_model}")
        else:
            # Use OpenAI key as fallback
            polish_api_key = os.getenv('OPENAI_API_KEY')
            if polish_api_key:
                pass
                # print(f"Using OpenAI API for polish model: {polish_model}")
            else:
                print(f"Warning: No API key found for polish model '{polish_model}'")
    else:
        # OpenAI model
        polish_api_key = os.getenv('OPENAI_API_KEY')
    
    # Initialize transcriber
    transcriber = DeepgramTranscriber(
        api_key=api_key,
        model="nova-3",  # Nova-3 with multi-language support
        language="multi",  # Multi-language mode for zh/ja/en
        polish_model=polish_model,
        polish_api_key=polish_api_key,
        polish_base_url=polish_base_url,
        interim_results=True  # Show partial results
    )
    
    # Set callbacks
    def on_transcription(result):
        if result.is_final:
            # Only show translation for final results
            if result.chinese_translation:
                print(f"\n→ {result.chinese_translation}")
        else:
            # Show interim results inline
            print(f"\r{result.original_text:<80}", end='', flush=True)
    
    def on_error(error_msg):
        print(f"\nError: {error_msg}")
    
    transcriber.set_transcription_callback(on_transcription)
    transcriber.set_error_callback(on_error)
    
    # Start transcriber
    await transcriber.start()
    print("Deepgram transcriber started. Listening...\n")
    
    # Initialize audio capture
    audio_capture = MacSystemAudioCapture(
        device_name="BlackHole 2ch",
        sample_rate=16000,
        chunk_duration=0.1,  # 100ms chunks for low latency
        channels=1,
        buffer_size=1024
    )
    
    # print("Starting audio capture...")
    audio_capture.start_capture()
    
    try:
        
        audio_sent = 0
        while True:
            # Get audio data
            audio_data = audio_capture.get_audio_data(timeout=0.05)
            if audio_data:
                # Send directly to Deepgram
                transcriber.send_audio(audio_data)
                audio_sent += 1
            
            await asyncio.sleep(0.01)  # Small sleep to prevent CPU spinning
            
    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        # Stop audio capture
        audio_capture.stop_capture()
        
        # Stop transcriber
        await transcriber.stop()
        
    # print("\nTest completed.")

if __name__ == "__main__":
    asyncio.run(test_deepgram_transcriber())