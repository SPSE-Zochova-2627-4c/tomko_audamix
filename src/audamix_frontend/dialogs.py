"""Small modal dialogs: generators, statistics and preferences."""

from __future__ import annotations

import math

from PySide6.QtMultimedia import QAudioDevice, QMediaDevices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from audamix.dsp.effects import EffectSpec


def device_key(device: QAudioDevice) -> str:
    """Stable string identifying an audio device, suitable for QSettings."""
    return str(device.id().toHex().data(), "ascii")


class EffectDialog(QDialog):
    """Parameter dialog generated from an :class:`audamix.dsp.effects.EffectSpec`."""

    def __init__(self, spec: EffectSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(spec.title)
        self._widgets: dict[str, QDoubleSpinBox | QCheckBox] = {}
        form = QFormLayout(self)
        for param in spec.params:
            widget: QDoubleSpinBox | QCheckBox
            if param.kind == "bool":
                widget = QCheckBox(self)
                widget.setChecked(bool(param.default))
            else:
                widget = QDoubleSpinBox(self)
                widget.setDecimals(param.decimals)
                widget.setRange(param.minimum, param.maximum)
                widget.setValue(param.default)
                widget.setSuffix(param.suffix)
                widget.setSingleStep(10 ** -param.decimals if param.decimals else 1)
            self._widgets[param.key] = widget
            form.addRow(param.label, widget)
        form.addRow(QLabel("Applies to the selection, or the whole track if nothing is selected.", self))
        buttons = QDialogButtonBox(_OK_CANCEL)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def parameters(self) -> dict[str, float]:
        return {key: float(widget.isChecked()) if isinstance(widget, QCheckBox) else widget.value()
                for key, widget in self._widgets.items()}


EXPORT_FORMATS = ("WAV", "FLAC", "OGG/Opus", "AIFF", "AU", "CAF", "MP3")


_OK_CANCEL = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel


class GenerateDialog(QDialog):
    """Parameters for Generate → Tone / Silence / Noise."""

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle(f"Generate {kind}")
        form = QFormLayout(self)
        self.frequency = QDoubleSpinBox(self)
        self.frequency.setRange(1, 96000)
        self.frequency.setValue(440)
        self.frequency.setSuffix(" Hz")
        self.duration = QDoubleSpinBox(self)
        self.duration.setRange(0.01, 3600)
        self.duration.setValue(1.0)
        self.duration.setDecimals(2)
        self.duration.setSuffix(" s")
        self.amplitude = QDoubleSpinBox(self)
        self.amplitude.setRange(-60, 0)
        self.amplitude.setValue(-6)
        self.amplitude.setSuffix(" dBFS")
        if kind == "tone":
            form.addRow("Frequency", self.frequency)
        form.addRow("Duration", self.duration)
        if kind != "silence":
            form.addRow("Amplitude", self.amplitude)
        buttons = QDialogButtonBox(_OK_CANCEL)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def parameters(self) -> dict[str, float]:
        return {"frequency": self.frequency.value(), "duration": self.duration.value(),
                "amplitude": 10 ** (self.amplitude.value() / 20)}


def format_statistics(stats: dict[str, float]) -> str:
    def db(value: float) -> str:
        return "−∞ dBFS" if math.isinf(value) else f"{value:.1f} dBFS"

    return (
        f"Duration: {stats['duration']:.3f} s\n"
        f"Peak: {stats['peak']:.4f} ({db(stats['peak_db'])})\n"
        f"RMS: {stats['rms']:.4f} ({db(stats['rms_db'])})\n"
        f"Crest factor: {stats['crest_db']:.1f} dB\n"
        f"DC offset: {stats['dc_offset']:+.5f}\n"
        f"Clipped samples (|x| ≥ 0.999): {int(stats['clipped_samples']):,}\n"
        f"Dominant frequency: {stats['dominant_hz']:.1f} Hz"
    )


class PreferencesDialog(QDialog):
    """Theme, output device and default export format."""

    def __init__(self, theme: str, device_id: str, export_format: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.theme = QComboBox(self)
        self.theme.addItems(["dark", "light"])
        self.theme.setCurrentText(theme)
        form.addRow("Theme", self.theme)
        self.device = QComboBox(self)
        self.device.addItem("System default", "")
        for item in QMediaDevices.audioOutputs():
            self.device.addItem(item.description(), device_key(item))
        index = self.device.findData(device_id)
        self.device.setCurrentIndex(max(0, index))
        form.addRow("Output device", self.device)
        self.export_format = QComboBox(self)
        self.export_format.addItems(EXPORT_FORMATS)
        self.export_format.setCurrentText(export_format if export_format in EXPORT_FORMATS else "WAV")
        form.addRow("Default export format", self.export_format)
        layout.addWidget(QLabel("Changes apply when you press OK.", self))
        buttons = QDialogButtonBox(_OK_CANCEL)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
