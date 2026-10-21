"""Backend boundary and deterministic demonstration implementations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class TrackSnapshot:
    name: str
    duration: float
    sample_rate: int
    channels: int
    sample_count: int
    peaks: tuple[tuple[float, float], ...]
    revision: int = 0


class ProjectModel(Protocol):
    def snapshot(self) -> TrackSnapshot | None: ...

    def open_file(self, path: str) -> tuple[bool, str]: ...

    def apply_effect(self, name: str, parameters: dict[str, float]) -> tuple[bool, str]: ...

    def undo(self) -> bool: ...

    def can_undo(self) -> bool: ...

    def export_file(self, path: str) -> tuple[bool, str]: ...

    def close(self) -> None: ...

    def set_controls(self, mute: bool, solo: bool, gain: float, pan: float) -> None: ...


class Transport(Protocol):
    def play(self) -> None: ...

    def pause(self) -> None: ...

    def stop(self) -> None: ...

    def seek(self, seconds: float) -> None: ...

    def tick(self, seconds: float, duration: float) -> None: ...

    def position(self) -> float: ...

    def is_playing(self) -> bool: ...


class StubProject:
    def __init__(self) -> None:
        self._track: TrackSnapshot | None = None
        self._history: list[TrackSnapshot] = []
        self.controls = (False, False, 1.0, 0.0)

    def snapshot(self) -> TrackSnapshot | None:
        return self._track

    def open_file(self, path: str) -> tuple[bool, str]:
        if Path(path).suffix.lower() not in {".wav", ".flac", ".ogg", ".aiff"}:
            return False, "Demo backend accepts WAV, FLAC, OGG and AIFF names only."
        if not Path(path).is_file():
            return False, "The selected file does not exist."
        # This is deliberately generated data, not a decoded version of the file.
        peaks = tuple(
            (0.06 + 0.54 * abs(math.sin(i * 0.089) * math.sin(i * 0.013)),
             0.03 + 0.32 * abs(math.sin(i * 0.089) * math.sin(i * 0.013)))
            for i in range(2000)
        )
        self._track = TrackSnapshot(Path(path).name, 90.0, 44100, 2, 3_969_000, peaks)
        self._history.clear()
        return True, "Demo waveform loaded; file audio was not decoded."

    def apply_effect(self, name: str, parameters: dict[str, float]) -> tuple[bool, str]:
        if self._track is None:
            return False, "Open a file first."
        self._history.append(self._track)
        old = self._track
        self._track = TrackSnapshot(old.name, old.duration, old.sample_rate, old.channels,
                                    old.sample_count, old.peaks, old.revision + 1)
        detail = ", ".join(f"{key}={value:g}" for key, value in parameters.items())
        return True, f"Demo only: {name} ({detail}) recorded; audio is unchanged."

    def undo(self) -> bool:
        if not self._history:
            return False
        self._track = self._history.pop()
        return True

    def can_undo(self) -> bool:
        return bool(self._history)

    def export_file(self, path: str) -> tuple[bool, str]:
        del path
        return False, "Export unavailable: connect an audio backend first. No file was written."

    def close(self) -> None:
        self._track = None
        self._history.clear()

    def set_controls(self, mute: bool, solo: bool, gain: float, pan: float) -> None:
        self.controls = (mute, solo, gain, pan)


class StubTransport:
    def __init__(self) -> None:
        self._position = 0.0
        self._playing = False

    def play(self) -> None:
        self._playing = True

    def pause(self) -> None:
        self._playing = False

    def stop(self) -> None:
        self._playing = False
        self._position = 0.0

    def seek(self, seconds: float) -> None:
        self._position = max(0.0, seconds)

    def tick(self, seconds: float, duration: float) -> None:
        if self._playing:
            self._position = min(duration, self._position + seconds)
            if self._position >= duration:
                self._playing = False

    def position(self) -> float:
        return self._position

    def is_playing(self) -> bool:
        return self._playing
