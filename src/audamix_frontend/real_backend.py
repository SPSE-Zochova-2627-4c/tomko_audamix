"""Adapters between the Qt frontend and the existing audio-processing code."""

from __future__ import annotations

import tempfile
import warnings
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from audamix.data.audio_data import AudioData
from audamix.dsp.signal_processor import SignalProcessor

from .model import TrackSnapshot


class AudioProject:
    """One editable track, with a non-destructive in-memory undo stack."""

    def __init__(self) -> None:
        self._audio: AudioData | None = None
        self._source: Path | None = None
        self._history: list[AudioData] = []
        self._revision = 0
        self._snapshot: TrackSnapshot | None = None
        self._controls = (False, False, 1.0, 0.0)
        self._preview_dir: tempfile.TemporaryDirectory[str] | None = None
        self._preview_key: tuple[int, tuple[bool, bool, float, float]] | None = None
        self._preview_file = ""

    def snapshot(self) -> TrackSnapshot | None:
        return self._snapshot

    def open_file(self, path: str) -> tuple[bool, str]:
        try:
            audio = AudioData.load(path)
            if audio.samples is None or not audio.samples.size:
                return False, "The audio file is empty."
            if audio.samples.ndim > 2 or (audio.samples.ndim == 2 and audio.samples.shape[1] > 2):
                return False, "Only mono and stereo audio are supported."
        except Exception as exc:
            return False, f"Could not open audio: {exc}"
        previous_audio = self._audio
        previous_snapshot = self._snapshot
        previous_key = self._preview_key
        self._audio = audio
        self._revision += 1
        try:
            self._rebuild_snapshot()
        except Exception as exc:
            self._audio = previous_audio
            self._snapshot = previous_snapshot
            self._preview_key = previous_key
            self._revision -= 1
            return False, f"Could not prepare waveform: {exc}"
        self._source = Path(path).resolve()
        self._history.clear()
        self._controls = (False, False, 1.0, 0.0)
        return True, f"Opened {Path(path).name}"

    def _rebuild_snapshot(self) -> None:
        audio = self._audio
        if audio is None or audio.samples is None:
            self._snapshot = None
            return
        samples = audio.samples[:, None] if audio.samples.ndim == 1 else audio.samples
        channels: list[tuple[tuple[float, float], ...]] = []
        count = min(2048, samples.shape[0])
        boundaries = np.linspace(0, samples.shape[0], count + 1, dtype=np.int64)
        for channel in samples.T:
            absolute = np.abs(channel)
            squares = np.square(channel)
            peaks = np.maximum.reduceat(absolute, boundaries[:-1])
            sums = np.add.reduceat(squares, boundaries[:-1])
            rms = np.sqrt(sums / np.diff(boundaries))
            channels.append(tuple(zip(peaks.tolist(), rms.tolist(), strict=True)))
        self._snapshot = TrackSnapshot(
            str(audio.metadata.get("filename", "Untitled")), audio.get_duration(),
            int(audio.metadata["sample_rate"]), samples.shape[1], samples.shape[0],
            channels[0], self._revision, tuple(channels),
        )
        self._preview_key = None

    def apply_effect(self, name: str, parameters: dict[str, float]) -> tuple[bool, str]:
        if self._audio is None:
            return False, "Open an audio file first."
        try:
            with warnings.catch_warnings(record=True) as notices:
                warnings.simplefilter("always")
                processor = SignalProcessor(self._audio)
                if name == "gain":
                    output = processor.adjust_volume(10 ** (parameters["dB"] / 20))
                elif name in {"lowpass", "highpass", "bandpass"}:
                    output = processor.apply_filter(name, parameters["Hz"])
                elif name == "classical_denoise":
                    output = processor.classical_denoise()
                elif name in {"ai_denoise", "ai_declip"}:
                    from audamix.ai.audio_ai import AudioAI

                    ai = AudioAI()
                    if name == "ai_denoise":
                        output, message = ai.denoise(self._audio)
                    else:
                        output, message = ai.declip(self._audio)
                    if name == "ai_declip" and not output.metadata.get("declipped", False):
                        return False, message
                else:
                    return False, f"Unknown effect: {name}"
        except Exception as exc:
            return False, f"{name} failed: {exc}"
        self._history.append(self._audio)
        self._audio = output
        self._revision += 1
        self._rebuild_snapshot()
        message = f"Applied {name.replace('_', ' ')}"
        if notices:
            message += "; " + "; ".join(str(notice.message) for notice in notices)
        return True, message

    def undo(self) -> bool:
        if not self._history:
            return False
        self._audio = self._history.pop()
        self._revision += 1
        self._rebuild_snapshot()
        return True

    def can_undo(self) -> bool:
        return bool(self._history)

    def _render(self) -> AudioData:
        if self._audio is None or self._audio.samples is None:
            raise ValueError("No audio loaded")
        mute, _solo, gain, pan = self._controls
        samples = np.asarray(self._audio.samples, dtype=np.float64).copy()
        samples *= 0.0 if mute else gain
        if samples.ndim == 2 and samples.shape[1] == 2:
            samples[:, 0] *= min(1.0, 1.0 - pan)
            samples[:, 1] *= min(1.0, 1.0 + pan)
        samples = np.clip(samples, -1.0, 1.0)
        result = AudioData()
        result.samples = samples
        result.metadata = self._audio.metadata.copy()
        return result

    def export_file(self, path: str) -> tuple[bool, str]:
        if self._audio is None:
            return False, "Open an audio file first."
        if self._source is not None and Path(path).resolve() == self._source:
            return False, "Choose an output path different from the source file."
        try:
            self._render().save(path)
        except Exception as exc:
            return False, f"Export failed: {exc}"
        return True, f"Exported {Path(path).name}"

    def set_controls(self, mute: bool, solo: bool, gain: float, pan: float) -> None:
        controls = (mute, solo, gain, pan)
        if controls != self._controls:
            self._controls = controls
            self._preview_key = None

    def preview_path(self) -> str:
        if self._audio is None:
            return ""
        if self._preview_dir is None:
            self._preview_dir = tempfile.TemporaryDirectory(prefix="audamix-preview-")
        key = (self._revision, self._controls)
        if key != self._preview_key:
            number = len(list(Path(self._preview_dir.name).iterdir()))
            path = Path(self._preview_dir.name) / f"preview-{self._revision}-{number}.wav"
            self._render().save(str(path), format="WAV")
            self._preview_file = str(path)
            self._preview_key = key
        return self._preview_file

    def close(self) -> None:
        self._audio = None
        self._source = None
        self._history.clear()
        self._snapshot = None
        self._preview_key = None
        self._preview_file = ""
        if self._preview_dir is not None:
            self._preview_dir.cleanup()
            self._preview_dir = None


class AudioTransport(QObject):
    """Qt Multimedia playback adapter, owned by the main window."""

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.player: QMediaPlayer | None = None
        self.output: QAudioOutput | None = None
        self._source = ""
        self._position = 0.0

    def _ensure_player(self) -> QMediaPlayer:
        if self.player is None:
            self.player = QMediaPlayer(self)
            self.output = QAudioOutput(self)
            self.player.setAudioOutput(self.output)
            self.player.seekableChanged.connect(self._seekable_changed)
        return self.player

    @Slot(bool)
    def _seekable_changed(self, seekable: bool) -> None:
        if seekable and self.player is not None:
            self.player.setPosition(round(self._position * 1000))

    def load(self, path: str) -> None:
        if path != self._source:
            if path:
                player = self._ensure_player()
                player.stop()
                player.setSource(QUrl.fromLocalFile(path))
            elif self.player is not None:
                self.player.stop()
                self.player.setSource(QUrl())
            self._source = path
            self._position = 0.0

    def play(self) -> None:
        if self._source:
            self._ensure_player().play()

    def pause(self) -> None:
        if self.player is not None:
            self.player.pause()

    def stop(self) -> None:
        if self.player is not None:
            self.player.stop()
        self._position = 0.0

    def seek(self, seconds: float) -> None:
        self._position = max(0.0, seconds)
        if self.player is not None and self.player.isSeekable():
            self.player.setPosition(round(seconds * 1000))

    def tick(self, seconds: float, duration: float) -> None:
        del seconds, duration

    def position(self) -> float:
        if self.player is not None and self.player.isSeekable():
            return self.player.position() / 1000
        return self._position

    def is_playing(self) -> bool:
        return self.player.isPlaying() if self.player is not None else False

    def is_paused(self) -> bool:
        return (self.player is not None
                and self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState)
