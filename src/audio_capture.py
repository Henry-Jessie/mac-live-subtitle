"""
Audio capture module for Mac system audio using BlackHole virtual device.
"""
import sounddevice as sd
import numpy as np
import scipy.signal
import queue
import threading
import logging
from typing import Optional, Callable
import time

logger = logging.getLogger(__name__)


class MacSystemAudioCapture:
    """Captures system audio on macOS using virtual audio devices."""
    
    def __init__(
        self,
        device_name: str = "BlackHole 2ch",
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration: float = 0.5,
        buffer_size: int = 2048
    ):
        self.device_name = device_name
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_duration = chunk_duration
        self.buffer_size = buffer_size
        
        self.audio_queue = queue.Queue()
        self.is_recording = False
        self.capture_thread = None
        self.device_id = None
        
        # Callback for audio data
        self._audio_callback = None
        
    def find_device_id(self) -> Optional[int]:
        """Find the audio device ID by name."""
        devices = sd.query_devices()
        logger.info("Available audio devices:")
        
        for idx, device in enumerate(devices):
            logger.info(f"  {idx}: {device['name']} ({device['max_input_channels']} in, {device['max_output_channels']} out)")
            
            if self.device_name.lower() in device['name'].lower() and device['max_input_channels'] > 0:
                logger.info(f"Found target device: {device['name']} (ID: {idx})")
                return idx
                
        # If exact match not found, try BlackHole with any channel configuration
        for idx, device in enumerate(devices):
            if 'blackhole' in device['name'].lower() and \
               device['max_input_channels'] > 0:
                logger.warning(f"Using alternative BlackHole device: {device['name']} (ID: {idx})")
                return idx
                
        logger.error(f"Device '{self.device_name}' not found")
        return None
    
    def audio_callback(self, indata, frames, time_info, status):
        """Process incoming audio data."""
        if status:
            logger.warning(f"Audio callback status: {status}")
            
        if self.is_recording:
            # Handle 48kHz stereo to 16kHz mono conversion if needed
            audio_data = indata.copy()
            
            # Step 1: Stereo to mono (average both channels) if stereo
            if len(audio_data.shape) > 1 and audio_data.shape[1] == 2:
                audio_data = audio_data.mean(axis=1)
            
            # Step 2: Downsample from 48kHz to 16kHz if needed
            # BlackHole typically runs at 48kHz, but we need 16kHz for transcription
            if hasattr(self, 'device_sample_rate') and self.device_sample_rate == 48000 and self.sample_rate == 16000:
                # Downsample from 48kHz to 16kHz (ratio 3:1)
                audio_data = scipy.signal.resample_poly(audio_data, up=1, down=3)
            
            # Step 3: Convert float32 to int16 PCM format
            audio_int16 = (audio_data * 32767).astype(np.int16)
            
            # Put in queue for processing
            self.audio_queue.put(audio_int16.tobytes())
            
            # Call user callback if provided
            if self._audio_callback:
                self._audio_callback(audio_int16.tobytes())
    
    def set_audio_callback(self, callback: Callable[[bytes], None]):
        """Set a callback function to receive audio data."""
        self._audio_callback = callback
    
    def start_capture(self):
        """Start capturing system audio."""
        if self.is_recording:
            logger.warning("Audio capture already started")
            return
            
        self.device_id = self.find_device_id()
        if self.device_id is None:
            raise ValueError(f"Audio device '{self.device_name}' not found")
            
        self.is_recording = True
        self.capture_thread = threading.Thread(target=self._capture_loop)
        self.capture_thread.start()
        logger.info("Audio capture started")
    
    def _capture_loop(self):
        """Main capture loop running in separate thread."""
        try:
            # Get device info to determine its native sample rate
            device_info = sd.query_devices(self.device_id)
            self.device_sample_rate = int(device_info['default_samplerate'])
            
            # Capture at device's native rate (usually 48kHz for BlackHole)
            capture_sample_rate = self.device_sample_rate
            capture_channels = 2 if self.device_sample_rate == 48000 else self.channels
            
            # Calculate blocksize based on chunk_duration and capture rate
            blocksize = int(capture_sample_rate * self.chunk_duration)
            
            logger.info(f"Device native rate: {self.device_sample_rate}Hz, capturing at {capture_sample_rate}Hz with {capture_channels} channels")
            logger.info(f"Blocksize: {blocksize} samples ({self.chunk_duration}s chunks)")
            
            with sd.InputStream(
                device=self.device_id,
                channels=capture_channels,
                samplerate=capture_sample_rate,
                callback=self.audio_callback,
                dtype='float32',
                blocksize=blocksize
            ):
                logger.info(f"Capturing audio from device {self.device_id}")
                while self.is_recording:
                    time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Error in audio capture: {e}")
            self.is_recording = False
            raise
    
    def stop_capture(self):
        """Stop audio capture."""
        if not self.is_recording:
            return
            
        logger.info("Stopping audio capture...")
        self.is_recording = False
        
        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)
            
        # Clear queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
                
        logger.info("Audio capture stopped")
    
    def get_audio_data(self, timeout: float = 0.1) -> Optional[bytes]:
        """Get audio data from queue."""
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_volume_level(self, audio_data: bytes) -> float:
        """Calculate RMS volume level from audio data."""
        if not audio_data:
            return 0.0
            
        # Convert bytes back to numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        # Calculate RMS
        rms = np.sqrt(np.mean(audio_array.astype(float) ** 2))
        
        # Normalize to 0-1 range
        max_value = 32767.0
        normalized = rms / max_value
        
        return min(1.0, normalized * 10)  # Scale up for better visibility


def list_audio_devices():
    """Utility function to list all available audio devices."""
    print("\nAvailable Audio Devices:")
    print("-" * 60)
    
    devices = sd.query_devices()
    for idx, device in enumerate(devices):
        print(f"{idx:3d}: {device['name']}")
        print(f"     Channels: {device['max_input_channels']} in, {device['max_output_channels']} out")
        print(f"     Sample Rate: {device['default_samplerate']} Hz")
        print()


if __name__ == "__main__":
    # Test the audio capture
    import time
    
    logging.basicConfig(level=logging.INFO)
    
    # List available devices
    list_audio_devices()
    
    # Test capture
    capture = MacSystemAudioCapture()
    
    def test_callback(audio_data):
        volume = capture.get_volume_level(audio_data)
        print(f"\rVolume: {'█' * int(volume * 50):<50} {volume:.2f}", end='')
    
    capture.set_audio_callback(test_callback)
    
    try:
        print("\nStarting audio capture test...")
        print("Make sure BlackHole is configured as your audio output")
        print("Press Ctrl+C to stop\n")
        
        capture.start_capture()
        
        while True:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n\nStopping...")
        capture.stop_capture()
        print("Test completed")