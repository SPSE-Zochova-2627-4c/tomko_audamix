"""Custom timeline and waveform widgets plus selection controls."""

from __future__ import annotations

import math

from PySide6.QtCore import QSignalBlocker, Qt, Signal, Slot
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QWidget

from .model import TrackSnapshot
from .theme import color


class ViewState:
    """Shared time-to-pixel mapping for ruler and waveform."""

    def __init__(self) -> None:
        self.offset = 0.0
        self.seconds_per_pixel = 0.15
        self.duration = 90.0

    def time_at(self, x: float) -> float:
        return min(self.duration, max(0.0, self.offset + x * self.seconds_per_pixel))

    def x_at(self, seconds: float) -> float:
        return (seconds - self.offset) / self.seconds_per_pixel

    def zoom(self, factor: float, anchor_x: float, width: int) -> None:
        anchor_time = self.time_at(anchor_x)
        self.seconds_per_pixel = max(0.001, min(10.0, self.seconds_per_pixel / factor))
        self.offset = max(0.0, min(self.duration - width * self.seconds_per_pixel,
                                   anchor_time - anchor_x * self.seconds_per_pixel))

    def fit(self, start: float, end: float, width: int) -> None:
        span = max(0.1, end - start)
        self.seconds_per_pixel = span / max(1, width)
        self.offset = max(0.0, start)


class TimelineRuler(QWidget):
    def __init__(self, view: ViewState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view = view
        self.theme = "dark"
        self._cache = QPixmap()
        self.setFixedHeight(31)

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.rebuild()

    def rebuild(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        self._cache = QPixmap(self.size())
        self._cache.fill(color(self.theme, "ruler"))
        painter = QPainter(self._cache)
        painter.setPen(color(self.theme, "text"))
        target_pixels = 85
        rough = self.view.seconds_per_pixel * target_pixels
        power = 10 ** math.floor(math.log10(max(rough, 0.001)))
        step = min((power, 2 * power, 5 * power, 10 * power), key=lambda value: abs(value - rough))
        first = math.ceil(self.view.offset / step) * step
        tick = first
        while tick <= self.view.time_at(self.width()):
            x = round(self.view.x_at(tick))
            painter.drawLine(x, 20, x, 30)
            label = f"{tick:.1f}s" if step < 1 else f"{int(tick // 60):02d}:{int(tick % 60):02d}"
            painter.drawText(x + 3, 15, label)
            tick += step
        painter.end()
        self.update()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.rebuild()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cache)


class WaveformView(QWidget):
    selection_changed = Signal(float, float)
    seek_requested = Signal(float)
    zoom_requested = Signal(float, float)
    scroll_requested = Signal(int)
    resized = Signal()

    def __init__(self, view: ViewState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view = view
        self.theme = "dark"
        self.track: TrackSnapshot | None = None
        self.selection = (0.0, 0.0)
        self.playhead = 0.0
        self.tool = "selection"
        self._drag_start: float | None = None
        self._cache = QPixmap()
        self._selection_color = color(self.theme, "selection")
        self._selection_color.setAlpha(95)
        self._playhead_pen = QPen(color(self.theme, "playhead"), 2)
        self.setMinimumHeight(190)
        self.setMouseTracking(True)

    def set_track(self, track: TrackSnapshot | None) -> None:
        self.track = track
        self.rebuild()

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self._selection_color = color(theme, "selection")
        self._selection_color.setAlpha(95)
        self._playhead_pen = QPen(color(theme, "playhead"), 2)
        self.rebuild()

    def set_selection(self, start: float, end: float) -> None:
        self.selection = (start, end)
        self.update()

    def set_playhead(self, seconds: float) -> None:
        self.playhead = seconds
        self.update()

    def rebuild(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        self._cache = QPixmap(self.size())
        self._cache.fill(color(self.theme, "background"))
        painter = QPainter(self._cache)
        painter.setPen(QPen(color(self.theme, "border")))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if self.track is not None:
            ruler_width = 34
            channel_height = self.height() / self.track.channels
            painter.setPen(QPen(color(self.theme, "center")))
            for channel in range(self.track.channels):
                center_y = round(channel_height * (channel + 0.5))
                painter.drawLine(ruler_width, center_y, self.width(), center_y)
                painter.drawText(4, center_y - round(channel_height * 0.28), "+1")
                painter.drawText(4, center_y + round(channel_height * 0.30), "−1")
                if channel:
                    painter.drawLine(0, round(channel_height * channel), self.width(),
                                     round(channel_height * channel))
                scale = channel_height * 0.43
                # Peaks are precomputed once by the backend. This loop runs only
                # when the cache changes, never on playhead/selection repaints.
                peaks_for_channel = (self.track.channel_peaks[channel]
                                     if self.track.channel_peaks else self.track.peaks)
                count = len(peaks_for_channel)
                for x in range(ruler_width, self.width()):
                    at = self.view.time_at(x - ruler_width)
                    index = min(count - 1, int(at / self.track.duration * count))
                    peak, rms = peaks_for_channel[index]
                    painter.setPen(QPen(color(self.theme, "wave")))
                    painter.drawLine(x, round(center_y - peak * scale), x, round(center_y + peak * scale))
                    painter.setPen(QPen(color(self.theme, "rms")))
                    painter.drawLine(x, round(center_y - rms * scale), x, round(center_y + rms * scale))
        painter.end()
        self.update()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.rebuild()
        self.resized.emit()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cache)
        if self.track is None:
            return
        start, end = self.selection
        if end > start:
            painter.fillRect(round(self.view.x_at(start)) + 34, 0,
                             round((end - start) / self.view.seconds_per_pixel), self.height(),
                             self._selection_color)
        painter.setPen(self._playhead_pen)
        x = round(self.view.x_at(self.playhead)) + 34
        painter.drawLine(x, 0, x, self.height())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self.track is None:
            return
        at = self.view.time_at(max(0.0, event.position().x() - 34))
        if self.tool == "zoom":
            factor = 0.5 if event.button() == Qt.MouseButton.RightButton else 2.0
            self.zoom_requested.emit(factor, event.position().x() - 34)
        else:
            if event.button() != Qt.MouseButton.LeftButton:
                return
            self._drag_start = at
            self.selection_changed.emit(at, at)
            self.seek_requested.emit(at)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_start is not None:
            at = self.view.time_at(max(0.0, event.position().x() - 34))
            self.selection_changed.emit(min(at, self._drag_start), max(at, self._drag_start))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        del event
        self._drag_start = None

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_requested.emit(1.25 if event.angleDelta().y() > 0 else 0.8,
                                     event.position().x() - 34)
        else:
            self.scroll_requested.emit(-1 if event.angleDelta().y() > 0 else 1)
        event.accept()


class SelectionBar(QWidget):
    selection_edited = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        self.start = QDoubleSpinBox(self)
        self.end = QDoubleSpinBox(self)
        self.length = QDoubleSpinBox(self)
        for label, box in (("Start", self.start), ("End", self.end), ("Length", self.length)):
            box.setRange(0, 999999)
            box.setDecimals(3)
            box.setSuffix(" s")
            layout.addWidget(QLabel(label, self))
            layout.addWidget(box)
        self.start.valueChanged.connect(self._changed)
        self.end.valueChanged.connect(self._changed)
        self.length.valueChanged.connect(self._length_changed)

    def set_selection(self, start: float, end: float) -> None:
        blockers = (QSignalBlocker(self.start), QSignalBlocker(self.end), QSignalBlocker(self.length))
        self.start.setValue(start)
        self.end.setValue(end)
        self.length.setValue(max(0.0, end - start))
        del blockers

    @Slot(float)
    def _changed(self, value: float) -> None:
        del value
        self.selection_edited.emit(self.start.value(), self.end.value())

    @Slot(float)
    def _length_changed(self, value: float) -> None:
        self.selection_edited.emit(self.start.value(), self.start.value() + value)
