#!/usr/bin/env python3
"""
Deepgram Live Subtitle - Main Application
Real-time system audio transcription and translation with subtitle display.
"""
import asyncio
import logging
import os
import sys
import signal
import threading
import time
import click
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from audio_capture import MacSystemAudioCapture, list_audio_devices
from deepgram_transcriber import DeepgramTranscriber
from subtitle_display import SubtitleDisplay


class DeepgramLiveSubtitle:
    """Main application class."""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = self._load_config(config_path)
        self.api_key = None
        self.polish_api_key = None
        self.polish_base_url = None
        self.polish_model = None
        
        # Components
        self.audio_capture = None
        self.transcriber = None
        self.subtitle_display = None
        
        # Control flags
        self.is_running = False
        self.audio_task = None
        
        # Keep track of last Chinese translation
        self.last_chinese_translation = ""
        
        # Setup logging
        self._setup_logging()
        
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file."""
        config_file = Path(config_path)
        if not config_file.exists():
            logging.warning(f"Config file not found: {config_path}, using defaults")
            return self._get_default_config()
            
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def _get_default_config(self) -> dict:
        """Get default configuration."""
        return {
            'audio': {
                'device_name': 'BlackHole 2ch',
                'sample_rate': 16000,
                'channels': 1,
                'chunk_duration': 0.5,
                'buffer_size': 2048
            },
            'deepgram': {
                'model': 'nova-3',
                'language': 'multi',
                'interim_results': True,
                'polish': {
                    'model': 'google/gemini-2.5-flash',
                    'api_key_env': 'OPENROUTER_API_KEY',
                    'base_url': 'https://openrouter.ai/api/v1'
                }
            },
            'display': {
                'window_width': 800,
                'window_height': 300,
                'window_opacity': 0.9,
                'always_on_top': True,
                'position_y_offset': 100,
                'resizable': True
            },
            'logging': {
                'level': 'INFO',
                'file': 'logs/subtitle.log'
            }
        }
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_config = self.config.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO'))
        
        # Create logs directory
        log_file = log_config.get('file', 'logs/subtitle.log')
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        # Set specific loggers
        logging.getLogger('websockets').setLevel(logging.WARNING)
        logging.getLogger('asyncio').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
    
    def _load_api_keys(self):
        """Load API keys from environment."""
        load_dotenv(override=True)
        deepgram_api_key = os.getenv('DEEPGRAM_API_KEY')
        
        if not deepgram_api_key:
            logging.error("No DEEPGRAM_API_KEY found in environment")
            raise ValueError(
                "Please set DEEPGRAM_API_KEY in .env file for Deepgram transcription"
            )
        
        self.api_key = deepgram_api_key
        
        # Load polish model API key from configured env variable
        deepgram_config = self.config.get('deepgram', {})
        polish_config = deepgram_config.get('polish', {})
        polish_api_key_env = polish_config.get('api_key_env', 'OPENROUTER_API_KEY')
        self.polish_api_key = os.getenv(polish_api_key_env)
        self.polish_base_url = polish_config.get('base_url', 'https://openrouter.ai/api/v1')
        self.polish_model = polish_config.get('model', 'google/gemini-2.5-flash')
        
        logging.info(f"Using Deepgram transcriber with polish model: {self.polish_model}")
    
    async def initialize(self):
        """Initialize all components."""
        logging.info("Initializing Deepgram Live Subtitle...")
        
        # Load API keys
        self._load_api_keys()
        
        # Initialize audio capture
        audio_config = self.config['audio']
        self.audio_capture = MacSystemAudioCapture(
            device_name=audio_config['device_name'],
            sample_rate=audio_config['sample_rate'],
            channels=audio_config['channels'],
            chunk_duration=audio_config['chunk_duration'],
            buffer_size=audio_config['buffer_size']
        )
        
        # Initialize Deepgram transcriber
        deepgram_config = self.config.get('deepgram', {})
        self.transcriber = DeepgramTranscriber(
            api_key=self.api_key,
            model=deepgram_config.get('model', 'nova-3'),
            language=deepgram_config.get('language', 'multi'),
            interim_results=deepgram_config.get('interim_results', True),
            polish_api_key=self.polish_api_key,
            polish_base_url=self.polish_base_url if self.polish_api_key else None,
            polish_model=self.polish_model
        )
        logging.info(f"Using Deepgram transcriber with model: {self.transcriber.model_name}")
        
        # Set transcription callbacks
        self.transcriber.set_transcription_callback(self._on_transcription)
        self.transcriber.set_error_callback(self._on_error)
        
        # Initialize subtitle display (but don't start it yet)
        display_config = self.config['display']
        self.subtitle_display = SubtitleDisplay(
            window_width=display_config['window_width'],
            window_height=display_config['window_height'],
            window_opacity=display_config['window_opacity'],
            always_on_top=display_config['always_on_top'],
            position_y_offset=display_config['position_y_offset'],
            resizable=display_config.get('resizable', False)
        )
        
        # Start transcriber
        await self.transcriber.start()
        
        logging.info("Initialization complete")
    
    def _on_transcription(self, result):
        """Handle transcription results."""
        if not self.subtitle_display:
            return
            
        # Update subtitle display based on result type
        if result.is_final and result.chinese_translation:
            # Update Chinese translation
            self.last_chinese_translation = result.chinese_translation
            # Show translation for final results
            self.subtitle_display.update_subtitle(
                original_text=result.original_text,
                chinese_text=result.chinese_translation,
                duration=5.0
            )
            logging.info(f"[{result.original_text}] → [{result.chinese_translation}]")
        elif not result.is_final:
            # Show interim results with previous Chinese translation
            self.subtitle_display.update_subtitle(
                original_text=result.original_text,
                chinese_text=self.last_chinese_translation,  # Keep previous translation
                duration=2.0
            )
    
    def _on_error(self, error_msg: str):
        """Handle errors."""
        logging.error(f"Transcription error: {error_msg}")
        
        # Show error in subtitle
        if self.subtitle_display:
            self.subtitle_display.update_subtitle(
                original_text="Error",
                chinese_text=error_msg,
                duration=5.0
            )
    
    async def _audio_processing_loop(self):
        """Main audio processing loop."""
        logging.info("Starting audio processing...")
        
        # Start audio capture
        self.audio_capture.start_capture()
        
        try:
            while self.is_running:
                # Get audio from queue
                audio_data = self.audio_capture.get_audio_data(timeout=0.1)
                
                if audio_data:
                    # Send audio to Deepgram
                    self.transcriber.send_audio(audio_data)
                
                await asyncio.sleep(0.01)  # Small delay to prevent busy loop
                
        except Exception as e:
            logging.error(f"Error in audio processing: {e}")
            raise
        finally:
            self.audio_capture.stop_capture()
    
    def start(self):
        """Start the application with UI on main thread."""
        logging.info("Starting Deepgram Live Subtitle...")
        
        # Create event for initialization synchronization
        self.init_complete = threading.Event()
        self.async_thread = None
        
        try:
            # Start asyncio in background thread
            self.async_thread = threading.Thread(
                target=self._run_async_loop,
                daemon=True
            )
            self.async_thread.start()
            
            # Wait for initialization to complete
            if not self.init_complete.wait(timeout=10):
                raise TimeoutError("Initialization timeout")
            
            # Run UI on main thread (blocking)
            logging.info("Starting UI on main thread")
            if self.subtitle_display:
                self.subtitle_display.start()
            else:
                logging.error("Subtitle display not initialized")
            
        except KeyboardInterrupt:
            logging.info("Received interrupt signal")
        except Exception as e:
            logging.error(f"Application error: {e}")
            raise
        finally:
            self._cleanup()
    
    def _run_async_loop(self):
        """Run asyncio event loop in background thread."""
        try:
            asyncio.run(self._async_main())
        except Exception as e:
            logging.error(f"Async loop error: {e}")
            self.init_complete.set()  # Unblock main thread even on error
    
    async def _async_main(self):
        """Main async function running in background thread."""
        logging.info("Starting async components...")
        
        try:
            # Initialize components
            await self.initialize()
            
            # Signal that initialization is complete
            self.init_complete.set()
            
            # Set running flag
            self.is_running = True
            
            # Start audio processing
            self.audio_task = asyncio.create_task(self._audio_processing_loop())
            
            # Wait a bit for UI to initialize
            await asyncio.sleep(0.5)
            
            # Show initial message
            if self.subtitle_display:
                self.last_chinese_translation = "实时字幕已启动"
                self.subtitle_display.update_subtitle(
                    original_text="Deepgram Live Subtitle Started",
                    chinese_text="实时字幕已启动",
                    duration=5.0
                )
            
            logging.info("Async components started successfully")
            logging.info("Listening for system audio...")
            logging.info("Press Ctrl+C to stop")
            
            # Keep running until is_running becomes False
            while self.is_running:
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logging.error(f"Async main error: {e}")
            raise
        finally:
            await self._async_cleanup()
    
    async def _async_cleanup(self):
        """Cleanup async components."""
        logging.info("Cleaning up async components...")
        
        self.is_running = False
        
        # Stop audio task
        if self.audio_task:
            self.audio_task.cancel()
            try:
                await self.audio_task
            except asyncio.CancelledError:
                pass
        
        # Stop transcriber
        if self.transcriber:
            await self.transcriber.stop()
        
        # Stop audio capture
        if self.audio_capture:
            self.audio_capture.stop_capture()
        
        logging.info("Async cleanup complete")
    
    def _cleanup(self):
        """Cleanup all components."""
        logging.info("Stopping Deepgram Live Subtitle...")
        
        # Signal async loop to stop
        self.is_running = False
        
        # Stop subtitle display (if running)
        if self.subtitle_display and hasattr(self.subtitle_display, 'is_running') and self.subtitle_display.is_running:
            self.subtitle_display.stop()
        
        # Wait for async thread to finish
        if self.async_thread and self.async_thread.is_alive():
            self.async_thread.join(timeout=5)
        
        logging.info("Application stopped")


@click.command()
@click.option(
    '--config',
    '-c',
    default='config/config.yaml',
    help='Path to configuration file'
)
@click.option(
    '--list-devices',
    '-l',
    is_flag=True,
    help='List available audio devices and exit'
)
@click.option(
    '--device',
    '-d',
    help='Override audio device name from config'
)
def main(config, list_devices, device):
    """Deepgram Live Subtitle - Real-time transcription and translation."""
    
    # List devices if requested
    if list_devices:
        list_audio_devices()
        return
    
    # Create application
    app = DeepgramLiveSubtitle(config_path=config)
    
    # Override device if specified
    if device:
        app.config['audio']['device_name'] = device
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        _ = sig, frame  # Suppress unused warnings
        logging.info("Received signal, shutting down...")
        app.is_running = False
        # The UI will detect this and close
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run application (UI on main thread)
    try:
        app.start()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()