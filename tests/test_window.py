#!/usr/bin/env python3
"""Test subtitle window display with debug info."""
import sys
import os
import time
import threading

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.subtitle_display import SubtitleDisplay


def test_window(resizable=None, debug=True):
    """Test the subtitle window shows properly.
    
    Args:
        resizable: True/False to test with/without resizable, None to use default
        debug: Whether to print debug information
    """
    print(f"Testing subtitle window (resizable={resizable}, debug={debug})...")
    
    # Create display with specified resizable setting
    if resizable is not None:
        display = SubtitleDisplay(resizable=resizable)
        print(f"Created display with resizable={resizable}")
    else:
        display = SubtitleDisplay()
        print("Created display with default settings")
    
    # Schedule subtitle updates
    def schedule_updates():
        """Schedule subtitle updates after UI starts."""
        print("Scheduling updates...")
        time.sleep(0.5)  # Wait for UI to initialize
        
        if debug and display.root:
            # Print debug information
            print("\n=== Initial Window Debug Info ===")
            print(f"Window width: {display.window_width}")
            print(f"Window height: {display.window_height}")
            print(f"Resizable: {display.resizable}")
            
            # Get actual dimensions
            display.root.update_idletasks()
            print(f"Actual window width: {display.root.winfo_width()}")
            print(f"Actual window height: {display.root.winfo_height()}")
            
            # Get label info
            if display.original_label:
                print(f"Original label wraplength: {display.original_label.cget('wraplength')}")
            if display.chinese_label:
                print(f"Chinese label wraplength: {display.chinese_label.cget('wraplength')}")
            print("================================\n")
        
        # Show initial message
        display.update_subtitle(
            original_text="Window Test - It works!",
            chinese_text="窗口测试 - 成功!",
            duration=5.0
        )
        print("Window should be visible now with test message.")
        
        time.sleep(3)
        
        # Test with longer text
        long_text = "This is a much longer test message to check if the text wrapping is working correctly in the subtitle window. Let's make it even longer to see how it handles multiple lines of text."
        long_chinese = "这是一个更长的测试消息，用于检查字幕窗口中的文本换行是否正常工作。让我们把它变得更长，看看它如何处理多行文本。"
        
        display.update_subtitle(
            original_text=long_text,
            chinese_text=long_chinese,
            duration=10.0
        )
        print("Testing with longer text...")
        
        if debug and display.root:
            time.sleep(0.5)  # Let the update apply
            print("\n=== After Long Text Update ===")
            print(f"Window width: {display.root.winfo_width()}")
            print(f"Original label wraplength: {display.original_label.cget('wraplength')}")
            print(f"Chinese label wraplength: {display.chinese_label.cget('wraplength')}")
            
            # Check label actual width
            display.root.update_idletasks()
            print(f"Original label actual width: {display.original_label.winfo_width()}")
            print(f"Chinese label actual width: {display.chinese_label.winfo_width()}")
            print("==============================\n")
        
        # Keep updating
        for i in range(5):
            time.sleep(3)
            if not display.is_running:
                break
                
            # Alternate between short and long messages
            if i % 2 == 0:
                display.update_subtitle(
                    original_text=f"Short message {i+1}",
                    chinese_text=f"短消息 {i+1}",
                    duration=3.0
                )
            else:
                display.update_subtitle(
                    original_text=f"This is a longer test message number {i+1} to check text wrapping behavior",
                    chinese_text=f"这是第 {i+1} 个较长的测试消息，用于检查文本换行行为",
                    duration=3.0
                )
            print(f"Updated: Test message {i+1}")
        
        # Stop after all updates
        if display.is_running:
            time.sleep(2)
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
    import argparse
    
    parser = argparse.ArgumentParser(description='Test subtitle window display')
    parser.add_argument('--resizable', action='store_true', help='Test with resizable window')
    parser.add_argument('--no-resizable', action='store_true', help='Test without resizable window')
    parser.add_argument('--no-debug', action='store_true', help='Disable debug output')
    
    args = parser.parse_args()
    
    # Determine resizable setting
    resizable = None
    if args.resizable:
        resizable = True
    elif args.no_resizable:
        resizable = False
    
    # Run test
    test_window(resizable=resizable, debug=not args.no_debug)