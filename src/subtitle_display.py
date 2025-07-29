"""
Subtitle display window using tkinter.
Shows original text and Chinese translation in an overlay window.
"""
import tkinter as tk
from tkinter import font as tkfont
import threading
import queue
import time
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SubtitleUpdate:
    """Subtitle update data."""
    original_text: str
    chinese_text: str
    duration: float = 3.0  # Display duration in seconds


class SubtitleDisplay:
    """Manages the subtitle display window."""
    
    def __init__(
        self,
        window_width: int = 800,
        window_height: int = 150,
        window_opacity: float = 0.9,
        always_on_top: bool = True,
        position_y_offset: int = 100,
        resizable: bool = False
    ):
        self.window_width = window_width
        self.window_height = window_height
        self.window_opacity = window_opacity
        self.always_on_top = always_on_top
        self.position_y_offset = position_y_offset
        self.resizable = resizable
        
        # Threading
        self.root = None
        self.ui_thread = None
        self.update_queue = queue.Queue()
        self.is_running = False
        
        # UI elements
        self.original_label = None
        self.chinese_label = None
        self.main_frame = None
        
        # Auto-hide timer
        self.hide_timer = None
        self.current_display_duration = 3.0
        
    def start(self):
        """Start the subtitle display in a separate thread."""
        if self.is_running:
            logger.warning("Subtitle display already running")
            return
            
        self.is_running = True
        
        # On macOS, UI must run on main thread
        if threading.current_thread() is threading.main_thread():
            # If we're already on main thread, run directly
            self._run_ui()
        else:
            # Otherwise, start in a new thread (for non-macOS or when called from worker thread)
            self.ui_thread = threading.Thread(target=self._run_ui, daemon=True)
            self.ui_thread.start()
            # Wait for UI to initialize
            time.sleep(0.5)
            
        logger.info("Subtitle display started")
    
    def _run_ui(self):
        """Run the UI in a separate thread."""
        try:
            # Create root window
            self.root = tk.Tk()
            self.root.title("实时字幕 - Deepgram Live Subtitle")
            
            # Configure window
            self._configure_window()
            
            # Create UI elements
            self._create_ui()
            
            # Start update loop
            self._schedule_update()
            
            # Run main loop
            self.root.mainloop()
            
        except Exception as e:
            logger.error(f"Error in UI thread: {e}")
            self.is_running = False
    
    def _configure_window(self):
        """Configure the window properties."""
        # Set window attributes
        self.root.attributes('-topmost', self.always_on_top)
        
        # Set transparency (macOS specific)
        self.root.attributes('-alpha', self.window_opacity)
        
        # Set window resizable based on configuration
        self.root.resizable(self.resizable, self.resizable)
        
        # Set minimum window size if resizable
        if self.resizable:
            self.root.minsize(400, 100)  # Minimum width and height
        
        # Set background color
        self.root.configure(bg='black')
        
        # Calculate window position (bottom center)
        self._update_window_position()
        
        # Bind escape key to hide window
        self.root.bind('<Escape>', lambda e: self.hide())
        
        # Make window draggable
        self._make_draggable()
        
    def _update_window_position(self):
        """Update window position to bottom center of screen."""
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Calculate position
        x = (screen_width - self.window_width) // 2
        y = screen_height - self.window_height - self.position_y_offset
        
        # Set geometry
        self.root.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")
    
    def _make_draggable(self):
        """Make the window draggable."""
        def start_drag(event):
            self.root.x = event.x
            self.root.y = event.y
            
        def drag(event):
            x = self.root.winfo_x() + event.x - self.root.x
            y = self.root.winfo_y() + event.y - self.root.y
            self.root.geometry(f"+{x}+{y}")
            
        # Bind drag events
        self.root.bind('<Button-1>', start_drag)
        self.root.bind('<B1-Motion>', drag)
    
    def _create_ui(self):
        """Create UI elements."""
        # Main frame
        main_frame = tk.Frame(self.root, bg='black')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        
        # Configure grid to expand
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)
        
        # Store the main frame for later reference
        self.main_frame = main_frame
        
        # Original text label
        self.original_label = tk.Label(
            main_frame,
            text="",
            font=('Arial', 20),
            fg='white',
            bg='black',
            wraplength=self.window_width - 20,
            justify=tk.CENTER
        )
        self.original_label.grid(row=0, column=0, pady=(0, 5), sticky='ew', padx=10)
        
        # Chinese translation label
        self.chinese_label = tk.Label(
            main_frame,
            text="",
            font=('PingFang SC', 18),  # macOS Chinese font
            fg='#FFFF00',  # Yellow
            bg='black',
            wraplength=self.window_width - 20,
            justify=tk.CENTER
        )
        self.chinese_label.grid(row=1, column=0, pady=(5, 0), sticky='ew', padx=10)
        
        # Initially hide the window (will show on first update)
        self.root.withdraw()
        
        # Update initial wraplength after window is created
        self.root.update_idletasks()  # Force geometry calculation
        actual_width = main_frame.winfo_width()
        if actual_width > 1:  # Make sure we got a valid width
            wrap_width = actual_width - 40  # Account for padding
            self.original_label.config(wraplength=wrap_width)
            self.chinese_label.config(wraplength=wrap_width)
        
        # Flag to prevent resize during initialization
        self._init_complete = False
        
        # Bind resize event if window is resizable
        if self.resizable:
            self.root.bind('<Configure>', self._on_window_resize)
        
        # Mark initialization as complete after a short delay
        self.root.after(100, self._mark_init_complete)
    
    def _mark_init_complete(self):
        """Mark initialization as complete."""
        self._init_complete = True
        # Force correct initial wraplength setting
        if self.resizable and self.main_frame:
            self.main_frame.update_idletasks()
            actual_width = self.main_frame.winfo_width()
            if actual_width > 1:
                wrap_width = actual_width - 40  # Keep consistent padding
                self.original_label.config(wraplength=wrap_width)
                self.chinese_label.config(wraplength=wrap_width)
    
    def _on_window_resize(self, event):
        """Handle window resize event."""
        # Skip resize events during initialization
        if not self._init_complete:
            return
            
        # Only respond to root window resize events
        if event.widget == self.root and self.main_frame:
            # Use main frame width for more accurate calculation
            self.main_frame.update_idletasks()
            frame_width = self.main_frame.winfo_width()
            
            if frame_width > 1:  # Valid width
                new_wraplength = max(100, frame_width - 40)  # Consistent padding with init
                if self.original_label:
                    self.original_label.config(wraplength=new_wraplength)
                if self.chinese_label:
                    self.chinese_label.config(wraplength=new_wraplength)
    
    def _schedule_update(self):
        """Schedule periodic updates from queue."""
        if not self.is_running:
            return
            
        # Process updates from queue
        try:
            while True:
                update = self.update_queue.get_nowait()
                self._apply_update(update)
        except queue.Empty:
            pass
            
        # Schedule next update
        if self.root:
            self.root.after(50, self._schedule_update)  # 20 FPS
    
    def _apply_update(self, update: SubtitleUpdate):
        """Apply subtitle update to UI."""
        # Update labels
        self.original_label.config(text=update.original_text)
        self.chinese_label.config(text=update.chinese_text)
        
        # Show window if hidden
        if not self.root.winfo_viewable():
            self.root.deiconify()
        
        # Cancel previous hide timer
        if self.hide_timer:
            self.root.after_cancel(self.hide_timer)
        
        # Set new hide timer
        self.current_display_duration = update.duration
        self.hide_timer = self.root.after(
            int(update.duration * 1000),
            self.hide
        )
    
    def update_subtitle(
        self,
        original_text: str,
        chinese_text: str,
        duration: float = 3.0
    ):
        """Update the displayed subtitle."""
        if not self.is_running:
            logger.warning("Subtitle display not running")
            return
            
        # Clean up text
        original_text = original_text.strip()
        chinese_text = chinese_text.strip()
        
        # Skip empty updates
        if not original_text and not chinese_text:
            return
            
        # Queue update
        update = SubtitleUpdate(
            original_text=original_text,
            chinese_text=chinese_text,
            duration=duration
        )
        self.update_queue.put(update)
    
    def hide(self):
        """Hide the subtitle window."""
        if self.root:
            self.root.withdraw()
    
    def show(self):
        """Show the subtitle window."""
        if self.root:
            self.root.deiconify()
    
    def stop(self):
        """Stop the subtitle display."""
        self.is_running = False
        
        if self.root:
            # Schedule quit on the UI thread to avoid threading issues
            try:
                self.root.after(0, self.root.quit)
            except:
                # If root is already destroyed, ignore
                pass
            
        if self.ui_thread and self.ui_thread != threading.current_thread():
            self.ui_thread.join(timeout=2.0)
            
        logger.info("Subtitle display stopped")
    
    def set_opacity(self, opacity: float):
        """Set window opacity (0.0 to 1.0)."""
        self.window_opacity = max(0.1, min(1.0, opacity))
        if self.root:
            self.root.attributes('-alpha', self.window_opacity)
    
    def set_position_offset(self, offset: int):
        """Set vertical position offset from bottom."""
        self.position_y_offset = offset
        if self.root:
            self._update_window_position()


def test_subtitle_display():
    """Test the subtitle display."""
    import random
    
    logging.basicConfig(level=logging.INFO)
    
    # Create display
    display = SubtitleDisplay(resizable=True)
    
    # Test subtitles
    test_subtitles = [
        ("Hello, this is a test.", "你好，这是一个测试。"),
        ("How are you today?", "你今天好吗？"),
        ("The weather is nice.", "天气很好。"),
        ("Thank you for watching.", "感谢观看。"),
        ("This is a longer sentence to test word wrapping in the subtitle display window.",
         "这是一个较长的句子，用于测试字幕显示窗口中的自动换行功能。"),
    ]
    
    # Schedule subtitle updates
    def schedule_updates():
        """Schedule subtitle updates after UI starts."""
        print("Subtitle display test started.")
        print("Press Ctrl+C or close window to stop.")
        print()
        
        for i in range(20):
            if not display.is_running:
                break
            original, chinese = random.choice(test_subtitles)
            print(f"Showing: {original}")
            display.update_subtitle(original, chinese, duration=2.0)
            time.sleep(2.5)
        
        # Stop after all updates
        if display.is_running:
            display.stop()
    
    # Start update thread
    update_thread = threading.Thread(target=schedule_updates, daemon=True)
    update_thread.start()
    
    try:
        # Start UI on main thread (blocking)
        display.start()
    except KeyboardInterrupt:
        print("\nStopping test...")
    finally:
        print("Test completed.")


if __name__ == "__main__":
    test_subtitle_display()