import numpy as np
import sounddevice as sd


BLACKHOLE_PREFIX = "blackhole"


def select_blackhole_device(devices) -> int:
    candidates = []
    input_names = []
    for index, device in enumerate(devices):
        name = str(device["name"]).strip()
        input_channels = int(device["max_input_channels"])
        if input_channels <= 0:
            continue
        input_names.append(name)
        normalized = name.casefold()
        if normalized.startswith(BLACKHOLE_PREFIX):
            candidates.append((index, name, input_channels))

    if not candidates:
        detected = ", ".join(input_names) if input_names else "none"
        raise RuntimeError(
            "BlackHole input device not found. Install BlackHole 2ch and "
            "configure a Multi-Output Device. "
            f"Detected input devices: {detected}"
        )

    candidates.sort(
        key=lambda candidate: (
            candidate[1].casefold() != "blackhole 2ch",
            candidate[2] != 2,
            candidate[2],
            candidate[1].casefold(),
            candidate[0],
        )
    )
    return candidates[0][0]


class BlackHoleAudioCapture:
    """Capture BlackHole input and yield mono float32 ASR frames."""

    def __init__(self, sample_rate=16000, step_size=0.2):
        self.sample_rate = int(sample_rate)
        self.step_size = float(step_size)
        self.running = False
        self.last_error = None
        self._block_size = int(self.sample_rate * self.step_size)
        if self._block_size <= 0:
            raise ValueError(
                f"Invalid step_size={self.step_size} for sample_rate={self.sample_rate}"
            )

    def stop(self):
        self.running = False

    def _negotiate_channels(self, device_index: int) -> int:
        failures = []
        for channels in (1, 2):
            try:
                sd.check_input_settings(
                    device=device_index,
                    channels=channels,
                    samplerate=self.sample_rate,
                )
            except (ValueError, sd.PortAudioError) as exc:
                failures.append(str(exc))
            else:
                return channels
        raise RuntimeError(
            "BlackHole cannot open at "
            f"{self.sample_rate} Hz with 1 or 2 input channels: "
            + "; ".join(failures)
            + ". Check Microphone permission and the BlackHole Multi-Output "
            "Device configuration."
        )

    def generator(self):
        self.last_error = None
        self.running = True
        try:
            devices = sd.query_devices()
            device_index = select_blackhole_device(devices)
            device_name = str(devices[device_index]["name"]).strip()
            channels = self._negotiate_channels(device_index)
            print(
                "[BlackHole] Capturing system audio "
                f"(device={device_name!r}, sr={self.sample_rate}, "
                f"step={self.step_size}s, channels={channels})"
            )
            with sd.InputStream(
                device=device_index,
                channels=channels,
                samplerate=self.sample_rate,
                blocksize=self._block_size,
                dtype="float32",
            ) as stream:
                while self.running:
                    data, overflowed = stream.read(self._block_size)
                    if overflowed:
                        print("[BlackHole] Input overflow")
                    if channels == 1:
                        yield data.reshape(-1)
                    else:
                        yield data.mean(axis=1, dtype=np.float32)
        except sd.PortAudioError as exc:
            self.last_error = (
                f"PortAudioError: {exc}. Allow Microphone access for Mac "
                "Live Subtitle and verify the BlackHole Multi-Output Device."
            )
            print(f"[BlackHole] ERROR: {self.last_error}")
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            print(f"[BlackHole] ERROR: {self.last_error}")
        finally:
            self.running = False
            print("[BlackHole] Generator stopped.")
