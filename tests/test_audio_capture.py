#!/usr/bin/env python3
"""
Test audio capture with new 48kHz to 16kHz conversion.
"""
import sys
import os
import logging
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.audio_capture import MacSystemAudioCapture, list_audio_devices

def test_audio_capture():
    """Test the updated audio capture with conversion."""
    logging.basicConfig(level=logging.INFO)
    
    print("Audio Capture Test with 48kHz -> 16kHz conversion")
    print("=" * 50)
    
    # List available devices
    list_audio_devices()
    
    # Create capture instance
    capture = MacSystemAudioCapture()
    
    # Variables to track audio stats
    sample_count = 0
    last_report_time = 0
    
    def test_callback(audio_data):
        nonlocal sample_count, last_report_time
        
        # Convert bytes back to numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        # Calculate stats
        sample_count += len(audio_array)
        current_time = sample_count / 16000  # 16kHz target rate
        
        # Report every second
        if int(current_time) > last_report_time:
            last_report_time = int(current_time)
            
            # Calculate volume
            rms = np.sqrt(np.mean(audio_array.astype(float) ** 2))
            volume = min(1.0, (rms / 32767.0) * 10)
            
            print(f"\rTime: {current_time:.1f}s | "
                  f"Samples: {len(audio_array)} | "
                  f"Volume: {'█' * int(volume * 20):<20} {volume:.2f}", 
                  end='', flush=True)
    
    capture.set_audio_callback(test_callback)
    
    try:
        print("\nStarting audio capture test...")
        print("Input: 48kHz stereo (BlackHole) -> Output: 16kHz mono")
        print("Make sure BlackHole is configured as your audio output")
        print("Press Ctrl+C to stop\n")
        
        capture.start_capture()
        
        # Run for a while
        import time
        while True:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n\nStopping...")
        capture.stop_capture()
        
        # Final stats
        total_duration = sample_count / 16000
        print(f"\nTest completed")
        print(f"Total duration: {total_duration:.2f} seconds")
        print(f"Total samples at 16kHz: {sample_count:,}")

if __name__ == "__main__":
    test_audio_capture()