import sounddevice as sd
import numpy as np


class AudioCapture:
    def __init__(self, device_index=None, sample_rate=16000, step_size=0.2):
        self.device_index = device_index
        self.sample_rate = int(sample_rate)
        self.step_size = float(step_size)
        self.running = False
        # Set when the stream fails to open/read; backends surface this as a
        # pipeline error instead of silently stopping.
        self.last_error = None

    def stop(self):
        self.running = False

    def _negotiate_channels(self) -> int:
        """Pick a working channel count. Some virtual devices (e.g. multi-channel
        variants like BlackHole 16ch) reject mono capture; fall back to stereo
        and downmix."""
        for ch in (1, 2):
            try:
                sd.check_input_settings(
                    device=self.device_index, channels=ch, samplerate=self.sample_rate
                )
                return ch
            except Exception:
                continue
        return 1  # let the stream itself raise the real error

    def generator(self):
        """Yields small raw audio chunks (mono float32) for external accumulation logic."""
        block_size = int(self.sample_rate * self.step_size)
        if block_size <= 0:
            raise ValueError(f"Invalid step_size={self.step_size} for sample_rate={self.sample_rate}")

        channels = self._negotiate_channels()
        downmix = channels != 1

        print(
            "[Audio] Starting raw processing stream "
            f"(device={self.device_index}, sr={self.sample_rate}, step={self.step_size}s, "
            f"channels={channels}{', downmixing to mono' if downmix else ''})"
        )

        self.last_error = None
        self.running = True
        try:
            with sd.InputStream(
                device=self.device_index,
                channels=channels,
                samplerate=self.sample_rate,
                blocksize=block_size,
                dtype="float32",
            ) as stream:
                while self.running:
                    data, overflow = stream.read(block_size)
                    if overflow:
                        print("[Audio] Overflow")
                    if downmix:
                        yield data.mean(axis=1, dtype=np.float32)
                    else:
                        yield data.reshape(-1)
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            print(f"\n[ERROR] Audio Device Initialization Failed: {e}")
            print("Possible causes:")
            print("1. App does not have Microphone permissions (System Settings > Privacy & Security > Microphone)")
            print(f"2. Sample rate {self.sample_rate}Hz not supported (Try 44100 or 48000)")
            print("3. Invalid device_index in [audio] (Try 'auto' or run: python audio_capture.py)")
            self.running = False
            return
        finally:
            self.running = False
            print("[Audio] Generator stopped.")

if __name__ == "__main__":
    print("Available devices:")
    print(sd.query_devices())

    cap = AudioCapture()
    try:
        for i, frame in enumerate(cap.generator()):
            print(f"Frame {i}: {len(frame)} samples")
            if i >= 5:
                break
    except KeyboardInterrupt:
        pass
    finally:
        cap.stop()
