"""Real microphone capture via sounddevice (thin seam).

Captures mono float32 at the configured rate into an in-memory list of frames;
``stop`` concatenates them into an :class:`AudioBuffer`. Audio never touches
disk. Imported lazily so the core stays dependency-free.
"""

from __future__ import annotations

from typing import Any

from .audio import AudioBuffer


class SoundDeviceSource:
    def __init__(self, sample_rate: int = 16000, device: str = "") -> None:
        self._sample_rate = sample_rate
        self._device = device or None
        self._stream: Any = None
        self._frames: list[Any] = []
        self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    def _resolve_device(self) -> Any:
        if self._device is None:
            return None
        import sounddevice as sd

        for idx, info in enumerate(sd.query_devices()):
            if self._device.lower() in info["name"].lower() and info["max_input_channels"] > 0:
                return idx
        return None

    def start(self) -> None:
        import sounddevice as sd

        self._frames = []

        def callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
            self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            device=self._resolve_device(),
            callback=callback,
        )
        self._stream.start()
        self._recording = True

    def stop(self) -> AudioBuffer:
        import numpy as np

        self._recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._frames:
            return AudioBuffer(data=np.zeros(0, dtype=np.float32), sample_rate=self._sample_rate)
        data = np.concatenate(self._frames, axis=0).reshape(-1).astype(np.float32)
        return AudioBuffer(data=data, sample_rate=self._sample_rate)
