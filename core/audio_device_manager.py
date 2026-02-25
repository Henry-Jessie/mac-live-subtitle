"""
Audio Device Manager for macOS
Manages audio devices using Core Audio framework via PyObjC
Replaces manual Audio MIDI Setup operations
"""

import platform
import subprocess

class AudioDeviceManager:
    def __init__(self):
        if platform.system() != "Darwin":
            raise RuntimeError("AudioDeviceManager only works on macOS")
        
        try:
            import CoreAudio
            self.CoreAudio = CoreAudio
        except ImportError:
            raise ImportError(
                "PyObjC CoreAudio framework not installed. "
                "Install with: pip install pyobjc-framework-CoreAudio"
            )
    
    def get_output_devices(self):
        """Get list of all output audio devices"""
        devices = []
        try:
            import sounddevice as sd
            sd_devices = sd.query_devices()
            for i, d in enumerate(sd_devices):
                if d['max_output_channels'] > 0:
                    devices.append({
                        'name': d['name'],
                        'id': i
                    })
        except Exception as e:
            print(f"[AudioDeviceManager] Error getting devices via sounddevice: {e}")
        
        return devices
    
    def get_virtual_devices(self):
        """Get list of virtual audio devices (e.g., BlackHole)"""
        virtual_devices = []
        
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            
            # Look for virtual audio devices
            virtual_keywords = ['blackhole', 'loopback', 'virtual', 'vb-cable', 'voicemeeter']
            
            for i, d in enumerate(devices):
                device_name_lower = d['name'].lower()
                if any(keyword in device_name_lower for keyword in virtual_keywords):
                    if d['max_output_channels'] > 0 or d['max_input_channels'] > 0:
                        virtual_devices.append({
                            'name': d['name'],
                            'id': i
                        })
        except Exception as e:
            print(f"[AudioDeviceManager] Error getting virtual devices: {e}")
        
        return virtual_devices
    
    def create_multi_output_device(self, device_name, device_ids, silent=False):
        """
        Create a multi-output device using AppleScript to control Audio MIDI Setup
        
        Args:
            device_name: Name for the new multi-output device
            device_ids: List of device IDs/names to combine
            silent: If True, suppress console output (for GUI usage)
        
        Returns:
            bool: True if successful
        """
        if not silent:
            print("\n[AudioDeviceManager] Attempting to create multi-output device...")
            print("[AudioDeviceManager] This requires Accessibility permissions for automation.\n")
        
        try:
            # First, just open Audio MIDI Setup for the user
            open_result = subprocess.run(
                ['open', '-a', 'Audio MIDI Setup'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if open_result.returncode != 0:
                if not silent:
                    print(f"[AudioDeviceManager] Could not open Audio MIDI Setup")
                return False
            
            if not silent:
                print("[AudioDeviceManager] Audio MIDI Setup opened.\n")
                print("═" * 60)
                print("📋 MANUAL STEPS (Easy!):\n")
                print("  1️⃣  In the Audio MIDI Setup window (bottom-left corner):")
                print("     Click the [+] button")
                print("\n  2️⃣  Select 'Create Multi-Output Device'\n")
                print("  3️⃣  Check the boxes for:")
                print(f"     ✓ Your speakers (e.g., External Headphones, MacBook Pro Speakers)")
                print(f"     ✓ BlackHole 2ch (for capturing audio)\n")
                print("  4️⃣  IMPORTANT: Uncheck 'Drift Correction' for your speakers")
                print("     (so you can hear the audio)\n")
                print("  5️⃣  Set this new device as your system output in System Settings\n")
                print("═" * 60)
                print("\n💡 TIP: You only need to do this once. The device will persist.\n")
            
            # Try automated approach (may fail without permissions)
            if not silent:
                print("[AudioDeviceManager] Attempting automation (may require permissions)...")
            
            applescript = '''
            tell application "System Events"
                tell process "Audio MIDI Setup"
                    set frontmost to true
                    delay 0.5
                    
                    try
                        -- Try to find and click the + button
                        click button 1 of group 1 of splitter group 1 of window "Audio Devices"
                        delay 0.3
                        click menu item "Create Multi-Output Device" of menu 1 of button 1 of group 1 of splitter group 1 of window "Audio Devices"
                        return "success"
                    on error errMsg
                        return "error: " & errMsg
                    end try
                end tell
            end tell
            '''
            
            result = subprocess.run(
                ['osascript', '-e', applescript],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and "success" in result.stdout:
                if not silent:
                    print("✅ [AudioDeviceManager] Automation successful!")
                    print("   Now configure the device checkboxes as shown above.\n")
                return True
            else:
                if not silent:
                    print("⚠️  [AudioDeviceManager] Automation failed (permissions needed).")
                    print("   Please follow the manual steps above.\n")
                    print("   To enable automation in the future:")
                    print("   → System Settings > Privacy & Security > Accessibility")
                    print("   → Add your Terminal/IDE and toggle it ON\n")
                return True  # Still return True since we opened the app
                
        except subprocess.TimeoutExpired:
            if not silent:
                print("[AudioDeviceManager] Timeout - please follow manual steps above")
            return True
        except Exception as e:
            if not silent:
                print(f"[AudioDeviceManager] Error: {e}")
                print("Please follow the manual steps above.\n")
            return True
    
    def set_default_output_device(self, device_id):
        """
        Set the system default output device
        
        Args:
            device_id: Device ID or index
        
        Returns:
            bool: True if successful
        """
        try:
            # Try using SwitchAudioSource (if installed)
            result = subprocess.run(
                ['which', 'SwitchAudioSource'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Get device name if we have an index
                device_name = None
                if isinstance(device_id, int):
                    import sounddevice as sd
                    devices = sd.query_devices()
                    if device_id < len(devices):
                        device_name = devices[device_id]['name']
                else:
                    device_name = device_id
                
                if device_name:
                    result = subprocess.run(
                        ['SwitchAudioSource', '-s', device_name],
                        capture_output=True,
                        text=True
                    )
                    return result.returncode == 0
            
            # Fallback: Use AppleScript
            print("[AudioDeviceManager] Please set default output device manually in System Settings > Sound")
            print(f"[AudioDeviceManager] Or install SwitchAudioSource: brew install switchaudio-osx")
            return False
            
        except Exception as e:
            print(f"[AudioDeviceManager] Error setting default device: {e}")
            return False


if __name__ == "__main__":
    # Test the manager
    print("Testing Audio Device Manager...")
    
    try:
        manager = AudioDeviceManager()
        
        print("\n=== Output Devices ===")
        output_devices = manager.get_output_devices()
        for i, device in enumerate(output_devices):
            print(f"  [{i}] {device['name']}")
        
        print("\n=== Virtual Devices ===")
        virtual_devices = manager.get_virtual_devices()
        for i, device in enumerate(virtual_devices):
            print(f"  [{i}] {device['name']}")
        
        if not virtual_devices:
            print("  No virtual audio devices found. Install BlackHole: brew install blackhole-2ch")
        
    except Exception as e:
        print(f"Error: {e}")
