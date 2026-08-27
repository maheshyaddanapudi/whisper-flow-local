"""In-memory fakes for the hardware/network seams (test support only)."""

from __future__ import annotations

from whisper_flow_local.audio import AudioBuffer
from whisper_flow_local.inject.base import InjectRequest
from whisper_flow_local.stt.base import Transcript


class FakeAudioSource:
    """Records start/stop and returns a preset buffer of a given duration."""

    def __init__(self, duration_s: float = 1.0, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self._duration_s = duration_s
        self._recording = False
        self.starts = 0
        self.stops = 0
        self.stop_raises = False

    def set_duration(self, duration_s: float) -> None:
        self._duration_s = duration_s

    def start(self) -> None:
        self._recording = True
        self.starts += 1

    def stop(self) -> AudioBuffer:
        self._recording = False
        self.stops += 1
        if self.stop_raises:
            raise RuntimeError("mic stop failed")
        n = int(self._duration_s * self.sample_rate)
        return AudioBuffer(data=[0.0] * n, sample_rate=self.sample_rate)

    @property
    def is_recording(self) -> bool:
        return self._recording


class FakeSTT:
    """Returns a preset transcript; can be made to raise."""

    def __init__(self, text: str = "hello world", *, raises: bool = False) -> None:
        self.text = text
        self.raises = raises
        self.calls: list[dict] = []
        self.unloaded = False

    def transcribe(self, audio: AudioBuffer, *, language=None, initial_prompt=None) -> Transcript:
        self.calls.append(
            {"duration": audio.duration_s, "language": language, "initial_prompt": initial_prompt}
        )
        if self.raises:
            raise RuntimeError("stt boom")
        return Transcript(text=self.text)

    def unload(self) -> None:
        self.unloaded = True


class FakeInjector:
    """Configurable injector for chain tests."""

    def __init__(self, name: str, *, ok: bool = True, avail: bool = True) -> None:
        self.name = name
        self._ok = ok
        self._avail = avail
        self.requests: list[InjectRequest] = []

    def available(self) -> bool:
        return self._avail

    def inject(self, req: InjectRequest) -> bool:
        self.requests.append(req)
        return self._ok


class FakeClipboard:
    """In-memory clipboard; can simulate a set failure."""

    def __init__(self, initial: str = "") -> None:
        self._text = initial
        self.fail_set = False
        self.fail_get = False
        self.sets: list[str] = []

    def get_text(self) -> str:
        if self.fail_get:
            raise RuntimeError("clipboard read failed")
        return self._text

    def set_text(self, text: str) -> None:
        if self.fail_set:
            raise RuntimeError("clipboard write failed")
        self._text = text
        self.sets.append(text)
