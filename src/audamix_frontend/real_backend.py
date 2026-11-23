"""Adapters between the Qt frontend and the existing audio-processing code."""

from __future__ import annotations

import tempfile
import warnings
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

from audamix.data.audio_data import AudioData
from audamix.dsp import editing, effects
from audamix.dsp.signal_processor import SignalProcessor

from .dialogs import device_key
from .model import Label, TrackSnapshot

_State = tuple[AudioData, tuple[Label, ...]]


def _remap_after_delete(labels: tuple[Label, ...], start: float, end: float) -> tuple[Label, ...]:
    """Move labels so they follow the audio after ``[start, end)`` is removed."""
    removed = end - start

    def move(value: float) -> float:
        return value if value <= start else start if value < end else value - removed

    kept = []
    for label in labels:
        point = label.end == label.start
        inside = label.start >= start and label.end <= end and (not point or label.start > start)
        if not inside:
            kept.append(Label(move(label.start), move(label.end), label.text))
    return tuple(kept)


def _remap_after_insert(labels: tuple[Label, ...], at: float, length: float) -> tuple[Label, ...]:
    return tuple(Label(item.start + length if item.start >= at else item.start,
                       item.end + length if item.end >= at else item.end, item.text) for item in labels)


class AudioProject:
    """One editable track, with a non-destructive in-memory undo stack."""

    def __init__(self) -> None:
        self._audio: AudioData | None = None
        self._source: Path | None = None
        self._history: list[_State] = []
        self._redo: list[_State] = []
        self._labels: tuple[Label, ...] = ()
        self._clipboard: tuple[NDArray[np.float64], int] | None = None
        self._spectrogram: tuple[int, NDArray[np.uint8]] | None = None
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
        previous_labels = self._labels
        self._audio = audio
        self._labels = ()
        self._revision += 1
        try:
            self._rebuild_snapshot()
        except Exception as exc:
            self._labels = previous_labels
            self._audio = previous_audio
            self._snapshot = previous_snapshot
            self._preview_key = previous_key
            self._revision -= 1
            return False, f"Could not prepare waveform: {exc}"
        self._source = Path(path).resolve()
        self._history.clear()
        self._redo.clear()
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
            channels[0], self._revision, tuple(channels), self._labels,
        )
        self._preview_key = None

    def _range(self, parameters: dict[str, float]) -> tuple[int, int] | None:
        """Sample range of the selection in ``parameters``, or ``None`` for the whole track."""
        assert self._audio is not None and self._audio.samples is not None
        frames = self._audio.samples.shape[0]
        rate = int(self._audio.metadata["sample_rate"])
        if "start" not in parameters or "end" not in parameters:
            return None
        start = editing.to_index(parameters["start"], rate, frames)
        end = editing.to_index(parameters["end"], rate, frames)
        return (start, end) if end > start and (start, end) != (0, frames) else None

    def _with_samples(self, samples: np.ndarray) -> AudioData:
        assert self._audio is not None
        result = AudioData()
        result.samples = np.asarray(samples, dtype=np.float64)
        result.metadata = self._audio.metadata.copy()
        result.metadata["duration"] = result.samples.shape[0] / int(result.metadata["sample_rate"])
        result.original_samples = self._audio.original_samples
        return result

    def _commit(self, audio: AudioData, labels: tuple[Label, ...] | None = None) -> None:
        assert self._audio is not None
        self._history.append((self._audio, self._labels))
        self._redo.clear()
        self._audio = audio
        if labels is not None:
            self._labels = labels
        self._revision += 1
        self._rebuild_snapshot()

    def apply_effect(self, name: str, parameters: dict[str, float]) -> tuple[bool, str]:
        if self._audio is None or self._audio.samples is None:
            return False, "Open an audio file first."
        region = self._range(parameters)
        source = self._audio
        if region is not None:
            source = self._with_samples(self._audio.samples[region[0]:region[1]])
        try:
            with warnings.catch_warnings(record=True) as notices:
                warnings.simplefilter("always")
                processor = SignalProcessor(source)
                if name == "gain":
                    output = processor.adjust_volume(10 ** (parameters["dB"] / 20))
                elif name in {"lowpass", "highpass", "bandpass"}:
                    output = processor.apply_filter(name, parameters["Hz"])
                elif name == "classical_denoise":
                    output = processor.classical_denoise()
                elif name in effects.SPECS:
                    rate = int(source.metadata["sample_rate"])
                    assert source.samples is not None
                    output = processor.from_samples(
                        effects.apply_effect(name, source.samples, rate, parameters))
                elif name in {"ai_denoise", "ai_declip"}:
                    from audamix.ai.audio_ai import AudioAI

                    ai = AudioAI()
                    if name == "ai_denoise":
                        output, message = ai.denoise(source)
                    else:
                        output, message = ai.declip(source)
                    if name == "ai_declip" and not output.metadata.get("declipped", False):
                        return False, message
                else:
                    return False, f"Unknown effect: {name}"
                if region is not None:
                    assert output.samples is not None
                    if output.samples.shape != source.samples.shape:
                        return False, f"{name} changed the length of the selection; nothing was applied."
                    merged = self._audio.samples.copy()
                    merged[region[0]:region[1]] = output.samples
                    output = self._with_samples(merged)
        except Exception as exc:
            return False, f"{name} failed: {exc}"
        self._commit(output)
        message = f"Applied {name.replace('_', ' ')}" + (" to selection" if region is not None else "")
        if notices:
            message += "; " + "; ".join(str(notice.message) for notice in notices)
        return True, message

    def edit(self, name: str, parameters: dict[str, float]) -> tuple[bool, str]:
        """Structural edits: cut/copy/paste/delete/trim/silence/fades and generators."""
        generator = name.startswith("generate_")
        if self._audio is None or self._audio.samples is None:
            if not generator:
                return False, "Open an audio file first."
            empty = AudioData()
            empty.samples = np.zeros(0)
            empty.metadata = {"filename": "Generated", "sample_rate": 44100, "channels": 1}
            self._audio = empty
            self._source = None
            self._history.clear()
            self._redo.clear()
            self._labels = ()
            created = True
        else:
            created = False
        samples = self._audio.samples
        assert samples is not None
        rate = int(self._audio.metadata["sample_rate"])
        channels = 1 if samples.ndim == 1 else samples.shape[1]
        frames = samples.shape[0]
        start = editing.to_index(parameters.get("start", 0.0), rate, frames)
        end = editing.to_index(parameters.get("end", 0.0), rate, frames)
        has_selection = end > start
        labels = self._labels
        try:
            if name == "copy":
                if not has_selection:
                    return False, "Select a region to copy."
                self._clipboard = (samples[start:end].copy(), rate)
                return True, f"Copied {(end - start) / rate:.2f} s"
            if name in {"cut", "delete"}:
                if not has_selection:
                    return False, f"Select a region to {name}."
                if end - start >= frames:
                    return False, "Cannot remove the whole track; close it instead."
                if name == "cut":
                    self._clipboard = (samples[start:end].copy(), rate)
                result = editing.smooth_join(editing.delete_range(samples, start, end), start, rate)
                labels = _remap_after_delete(labels, start / rate, end / rate)
                message = f"{name.capitalize()} {(end - start) / rate:.2f} s"
            elif name == "trim":
                if not has_selection:
                    return False, "Select the region to keep."
                result = editing.keep_range(samples, start, end)
                labels = _remap_after_delete(labels, end / rate, frames / rate)
                labels = _remap_after_delete(labels, 0.0, start / rate)
                message = "Trimmed to selection"
            elif name == "silence":
                if not has_selection:
                    return False, "Select a region to silence."
                result = editing.silence_range(samples, start, end)
                for edge in (start, end):  # the edges of the silenced region would click otherwise
                    result = editing.smooth_join(result, edge, rate)
                message = "Silenced selection"
            elif name in {"fade_in", "fade_out"}:
                if not has_selection:
                    return False, "Select a region to fade."
                result = editing.fade_range(samples, start, end, name.removeprefix("fade_"))
                message = f"Applied {name.replace('_', ' ')}"
            elif name == "paste" or generator:
                if generator:
                    clip = editing.generate(
                        name.removeprefix("generate_"), rate, channels, parameters["duration"],
                        parameters.get("frequency", 440.0), parameters.get("amplitude", 0.5),
                    )
                    message = f"Generated {name.removeprefix('generate_')}"
                else:
                    if self._clipboard is None:
                        return False, "Clipboard is empty."
                    clip = editing.match_clip(self._clipboard[0], self._clipboard[1], rate, channels)
                    message = f"Pasted {clip.shape[0] / rate:.2f} s"
                at = start if has_selection else editing.to_index(parameters.get("at", 0.0), rate, frames)
                base = samples
                if has_selection and end - start < frames:
                    base = editing.delete_range(samples, start, end)
                    labels = _remap_after_delete(labels, start / rate, end / rate)
                elif has_selection:
                    base, at = samples[:0], 0
                    labels = ()
                result = editing.insert_clip(base, at, clip)
                for seam in (at, at + clip.shape[0]):  # both ends of the inserted clip
                    result = editing.smooth_join(result, seam, rate)
                labels = _remap_after_insert(labels, at / rate, clip.shape[0] / rate)
            else:
                return False, f"Unknown edit: {name}"
        except Exception as exc:
            if created:
                self._audio = None
            return False, f"{name} failed: {exc}"
        output = self._with_samples(result)
        if created:
            # A generated track starts a new project; the empty placeholder is not an undo step.
            self._audio = output
            self._revision += 1
            self._controls = (False, False, 1.0, 0.0)
            self._rebuild_snapshot()
        else:
            self._commit(output, labels)
        return True, message

    def add_label(self, start: float, end: float, text: str) -> None:
        if self._audio is None:
            return
        duration = self._audio.get_duration()
        start = max(0.0, min(duration, start))
        end = max(start, min(duration, end))
        previous = self._labels
        self._history.append((self._audio, previous))
        self._redo.clear()
        self._labels = tuple(sorted((*previous, Label(start, end, text)), key=lambda item: item.start))
        self._rebuild_snapshot()

    def remove_labels(self, start: float, end: float) -> int:
        if self._audio is None:
            return 0
        kept = tuple(item for item in self._labels if not (item.end >= start and item.start <= end))
        removed = len(self._labels) - len(kept)
        if removed:
            self._history.append((self._audio, self._labels))
            self._redo.clear()
            self._labels = kept
            self._rebuild_snapshot()
        return removed

    def analyze(self, start: float, end: float) -> tuple[bool, dict[str, float] | str]:
        if self._audio is None or self._audio.samples is None:
            return False, "Open an audio file first."
        rate = int(self._audio.metadata["sample_rate"])
        frames = self._audio.samples.shape[0]
        a = editing.to_index(start, rate, frames)
        b = editing.to_index(end, rate, frames)
        data = self._audio.samples[a:b] if b > a else self._audio.samples
        try:
            return True, editing.analyze(data, rate)
        except ValueError as exc:
            return False, str(exc)

    def spectrogram(self) -> NDArray[np.uint8] | None:
        if self._audio is None or self._audio.samples is None:
            return None
        if self._spectrogram is None or self._spectrogram[0] != self._revision:
            image = editing.spectrogram_image(self._audio.samples, int(self._audio.metadata["sample_rate"]))
            self._spectrogram = (self._revision, image)
        return self._spectrogram[1]

    def level_at(self, seconds: float) -> tuple[float, ...]:
        """Peak level per channel (after Mute/Gain/Pan) in a 50 ms window starting at *seconds*."""
        if self._audio is None or self._audio.samples is None:
            return ()
        samples = self._audio.samples
        rate = int(self._audio.metadata["sample_rate"])
        a = editing.to_index(seconds, rate, samples.shape[0])
        window = samples[a:a + max(1, rate // 20)]
        if not window.size:
            return (0.0,) * (1 if samples.ndim == 1 else samples.shape[1])
        mute, _solo, gain, pan = self._controls
        peaks = np.max(np.abs(window.reshape(window.shape[0], -1)), axis=0) * (0.0 if mute else gain)
        if peaks.size == 2:
            peaks = peaks * (min(1.0, 1.0 - pan), min(1.0, 1.0 + pan))
        return tuple(float(min(1.0, value)) for value in peaks)

    def undo(self) -> bool:
        if not self._history or self._audio is None:
            return False
        self._redo.append((self._audio, self._labels))
        self._audio, self._labels = self._history.pop()
        self._revision += 1
        self._rebuild_snapshot()
        return True

    def redo(self) -> bool:
        if not self._redo or self._audio is None:
            return False
        self._history.append((self._audio, self._labels))
        self._audio, self._labels = self._redo.pop()
        self._revision += 1
        self._rebuild_snapshot()
        return True

    def can_undo(self) -> bool:
        return bool(self._history)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def can_paste(self) -> bool:
        return self._clipboard is not None

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
        self._redo.clear()
        self._labels = ()
        self._spectrogram = None
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
        self._play_pending = False  # Play was requested while the media was still loading
        self._device_id = ""

    def set_output_device(self, device_id: str) -> None:
        self._device_id = device_id
        self._apply_device()

    def _apply_device(self) -> None:
        if self.output is None or not self._device_id:
            return
        for device in QMediaDevices.audioOutputs():
            if device_key(device) == self._device_id:
                self.output.setDevice(device)
                return

    def _ensure_player(self) -> QMediaPlayer:
        if self.player is None:
            self.player = QMediaPlayer(self)
            self.output = QAudioOutput(self)
            self.player.setAudioOutput(self.output)
            self._apply_device()
            self.player.mediaStatusChanged.connect(self._status_changed)
        return self.player

    @staticmethod
    def _is_ready(player: QMediaPlayer) -> bool:
        return player.mediaStatus() in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
            QMediaPlayer.MediaStatus.EndOfMedia,
        )

    @Slot(QMediaPlayer.MediaStatus)
    def _status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        """Once a freshly loaded file is ready, apply the requested position and then play.

        Seeking before the media has loaded is silently lost (playback then starts at 0), so
        the first Play after loading a new source has to wait for this signal.
        """
        player = self.player
        if player is None or status not in (QMediaPlayer.MediaStatus.LoadedMedia,
                                            QMediaPlayer.MediaStatus.BufferedMedia):
            return
        if self._play_pending:
            self._play_pending = False
            player.setPosition(round(self._position * 1000))
            player.play()

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
            self._play_pending = False

    def play(self) -> None:
        if not self._source:
            return
        player = self._ensure_player()
        if self._is_ready(player):
            player.play()
        else:
            self._play_pending = True  # started by _status_changed with the right position

    def pause(self) -> None:
        self._play_pending = False
        if self.player is not None:
            self.player.pause()

    def stop(self) -> None:
        self._play_pending = False
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
        if self._play_pending:
            return True
        return self.player.isPlaying() if self.player is not None else False

    def is_paused(self) -> bool:
        return (self.player is not None
                and self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState)
