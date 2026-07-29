import queue
import threading

import CoreAudio
import CoreMedia
import numpy as np
import objc
import ScreenCaptureKit
from Foundation import NSObject


_STOP = object()


def _error_text(error) -> str:
    if error is None:
        return ""
    description = getattr(error, "localizedDescription", None)
    if callable(description):
        return str(description())
    return str(error)


class _StreamOutput(
    NSObject,
    protocols=[
        objc.protocolNamed("SCStreamOutput"),
        objc.protocolNamed("SCStreamDelegate"),
    ],
):
    """Objective-C callback boundary for ScreenCaptureKit."""

    @objc.python_method
    def _fail(self, error: BaseException):
        try:
            self.owner._capture_failed(error, self.generation)
        except BaseException as callback_error:
            print(
                "[ScreenCaptureKit] ERROR: failed to report callback error: "
                f"{type(callback_error).__name__}: {callback_error}"
            )

    def stream_didOutputSampleBuffer_ofType_(self, stream, sample_buffer, output_type):
        try:
            if output_type == ScreenCaptureKit.SCStreamOutputTypeAudio:
                self.owner._receive_audio(sample_buffer, self.generation)
        except BaseException as exc:
            # Python exceptions must never cross an Objective-C delegate callback:
            # doing so terminates the process.
            self._fail(exc)

    def stream_didStopWithError_(self, stream, error):
        self._fail(
            RuntimeError(f"ScreenCaptureKit stopped: {_error_text(error)}")
        )


class AudioCapture:
    """Capture macOS system audio through ScreenCaptureKit.

    The ASR-facing generator yields mono float32 frames at ``sample_rate`` and
    ``step_size``.
    """

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

        self._frames = None
        self._pending = np.empty(0, dtype=np.float32)
        self._stream = None
        self._delegate = None
        self._generation = 0
        self._dropped_frames = 0

    def stop(self):
        self.running = False
        self._wake_generator()

    def _wake_generator(self):
        frames = self._frames
        if frames is None:
            return
        try:
            frames.put_nowait(_STOP)
        except queue.Full:
            try:
                frames.get_nowait()
            except queue.Empty:
                pass
            try:
                frames.put_nowait(_STOP)
            except queue.Full:
                pass

    def _capture_failed(self, error: BaseException, generation: int):
        if generation != self._generation or not self.running:
            return
        self.last_error = f"{type(error).__name__}: {error}"
        print(f"[ScreenCaptureKit] ERROR: {self.last_error}")
        self.running = False
        self._wake_generator()

    def _receive_audio(self, sample_buffer, generation: int):
        if generation != self._generation or not self.running:
            return
        if not CoreMedia.CMSampleBufferIsValid(sample_buffer):
            return

        format_description = CoreMedia.CMSampleBufferGetFormatDescription(sample_buffer)
        audio_format = CoreMedia.CMAudioFormatDescriptionGetStreamBasicDescription(
            format_description
        )
        if (
            audio_format.mFormatID != CoreAudio.kAudioFormatLinearPCM
            or not (audio_format.mFormatFlags & CoreAudio.kAudioFormatFlagIsFloat)
            or audio_format.mBitsPerChannel != 32
            or audio_format.mChannelsPerFrame != 1
        ):
            raise RuntimeError(f"Unexpected ScreenCaptureKit audio format: {audio_format}")

        data_buffer = CoreMedia.CMSampleBufferGetDataBuffer(sample_buffer)
        if data_buffer is None:
            return
        byte_count = CoreMedia.CMBlockBufferGetDataLength(data_buffer)
        status, raw = CoreMedia.CMBlockBufferCopyDataBytes(
            data_buffer, 0, byte_count, None
        )
        if status != 0:
            raise RuntimeError(f"CMBlockBufferCopyDataBytes failed with OSStatus {status}")

        sample_count = CoreMedia.CMSampleBufferGetNumSamples(sample_buffer)
        samples = np.frombuffer(raw, dtype=np.float32, count=sample_count)
        if self._pending.size:
            samples = np.concatenate((self._pending, samples))

        offset = 0
        while samples.size - offset >= self._block_size:
            frame = samples[offset : offset + self._block_size].copy()
            self._enqueue_frame(frame)
            offset += self._block_size
        self._pending = samples[offset:].copy()

    def _enqueue_frame(self, frame: np.ndarray):
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            try:
                self._frames.get_nowait()
            except queue.Empty:
                pass
            try:
                self._frames.put_nowait(frame)
            except queue.Full:
                pass
            self._dropped_frames += 1
            if self._dropped_frames == 1:
                print("[ScreenCaptureKit] Audio consumer is behind; dropping old frames.")

    def _start_capture(self) -> bool:
        content_ready = threading.Event()
        content_result = {}

        def on_content(content, error):
            content_result["content"] = content
            content_result["error"] = error
            content_ready.set()

        ScreenCaptureKit.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
            False,
            True,
            on_content,
        )
        if not content_ready.wait(timeout=10):
            raise TimeoutError("Timed out while requesting ScreenCaptureKit content")
        if content_result["error"] is not None:
            raise RuntimeError(
                "ScreenCaptureKit cannot access system audio: "
                f"{_error_text(content_result['error'])}. "
                "Grant Screen Recording (Screen & System Audio Recording on newer "
                "macOS versions) permission, then restart the app."
            )
        if not self.running:
            return False

        displays = list(content_result["content"].displays())
        if not displays:
            raise RuntimeError("ScreenCaptureKit found no active display")

        content_filter = (
            ScreenCaptureKit.SCContentFilter.alloc()
            .initWithDisplay_excludingApplications_exceptingWindows_(
                displays[0],
                [],
                [],
            )
        )
        configuration = ScreenCaptureKit.SCStreamConfiguration.alloc().init()
        configuration.setCapturesAudio_(True)
        configuration.setExcludesCurrentProcessAudio_(True)
        configuration.setSampleRate_(self.sample_rate)
        configuration.setChannelCount_(1)
        # No screen output is registered. Keep the unused video configuration
        # minimal so WindowServer does not allocate full-size frames.
        configuration.setWidth_(2)
        configuration.setHeight_(2)
        configuration.setQueueDepth_(1)
        configuration.setShowsCursor_(False)

        delegate = _StreamOutput.alloc().init()
        delegate.owner = self
        delegate.generation = self._generation
        stream = ScreenCaptureKit.SCStream.alloc().initWithFilter_configuration_delegate_(
            content_filter,
            configuration,
            delegate,
        )
        added, error = stream.addStreamOutput_type_sampleHandlerQueue_error_(
            delegate,
            ScreenCaptureKit.SCStreamOutputTypeAudio,
            None,
            None,
        )
        if not added:
            raise RuntimeError(
                f"Cannot register ScreenCaptureKit audio output: {_error_text(error)}"
            )

        self._delegate = delegate
        self._stream = stream
        started = threading.Event()
        start_result = {}

        def on_start(error):
            start_result["error"] = error
            started.set()

        stream.startCaptureWithCompletionHandler_(on_start)
        if not started.wait(timeout=10):
            raise TimeoutError("Timed out while starting ScreenCaptureKit")
        if start_result["error"] is not None:
            raise RuntimeError(
                f"Cannot start ScreenCaptureKit: {_error_text(start_result['error'])}"
            )
        if not self.running:
            return False

        print(
            "[ScreenCaptureKit] Capturing system audio "
            f"(sr={self.sample_rate}, step={self.step_size}s, channels=1)"
        )
        return True

    def _stop_capture(self):
        stream = self._stream
        self._stream = None
        if stream is None:
            return

        stopped = threading.Event()

        def on_stop(error):
            if error is not None:
                print(f"[ScreenCaptureKit] Stop warning: {_error_text(error)}")
            stopped.set()

        stream.stopCaptureWithCompletionHandler_(on_stop)
        stopped.wait(timeout=3)
        self._delegate = None

    def generator(self):
        """Yield fixed-size mono float32 system-audio frames."""
        self.last_error = None
        self._frames = queue.Queue(maxsize=16)
        self._pending = np.empty(0, dtype=np.float32)
        self._dropped_frames = 0
        self._generation += 1
        self.running = True

        try:
            if not self._start_capture():
                return
            while self.running:
                try:
                    frame = self._frames.get(timeout=0.25)
                except queue.Empty:
                    continue
                if frame is _STOP:
                    break
                yield frame
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            print(f"[ScreenCaptureKit] ERROR: {self.last_error}")
        finally:
            self.running = False
            self._stop_capture()
            self._frames = None
            print("[ScreenCaptureKit] Generator stopped.")
