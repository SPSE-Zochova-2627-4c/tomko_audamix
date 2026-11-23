"""Custom timeline and waveform widgets plus selection controls."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QPoint, QRectF, QSignalBlocker, Qt, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QWidget

from .model import Label, TrackSnapshot
from .theme import color


def _heat_table() -> list[int]:
    """256-entry color table running black → blue → magenta → yellow → white."""
    stops = ((0.0, (8, 8, 24)), (0.35, (40, 60, 170)), (0.65, (200, 60, 120)),
             (0.85, (250, 190, 60)), (1.0, (255, 255, 235)))
    table = []
    for index in range(256):
        position = index / 255
        for (a, ca), (b, cb) in zip(stops, stops[1:], strict=False):
            if position <= b:
                f = (position - a) / (b - a)
                r, g, bl = (round(x + (y - x) * f) for x, y in zip(ca, cb, strict=True))
                table.append(0xFF000000 | (r << 16) | (g << 8) | bl)
                break
    return table


_HEAT = _heat_table()


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


AXIS_WIDTH = 34  # left margin of the waveform that holds the +1/−1 labels
EDGE_GRAB_PIXELS = 6


class TimelineRuler(QWidget):
    seek_requested = Signal(float)

    def __init__(self, view: ViewState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view = view
        self.theme = "dark"
        self._cache = QPixmap()
        self.playhead: float | None = None
        self.selection = (0.0, 0.0)
        self.setFixedHeight(31)

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.rebuild()

    def set_playhead(self, seconds: float | None) -> None:
        self.playhead = seconds
        self.update()

    def set_selection(self, start: float, end: float) -> None:
        self.selection = (start, end)
        self.update()

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
        while tick <= self.view.time_at(self.width() - AXIS_WIDTH):
            x = round(self.view.x_at(tick)) + AXIS_WIDTH
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
        start, end = self.selection
        if end > start:
            band = color(self.theme, "selection")
            band.setAlpha(80)
            x0 = round(self.view.x_at(start)) + AXIS_WIDTH
            x1 = round(self.view.x_at(end)) + AXIS_WIDTH
            painter.fillRect(x0, 0, max(1, x1 - x0), self.height(), band)
        # Playback marker: a small downward triangle, shown only while audio plays or is paused.
        if self.playhead is None:
            return
        x = round(self.view.x_at(self.playhead)) + AXIS_WIDTH
        if AXIS_WIDTH <= x <= self.width():
            marker = color(self.theme, "playhead")
            painter.setPen(marker)
            painter.setBrush(marker)
            painter.drawPolygon([QPoint(x - 5, self.height() - 12), QPoint(x + 5, self.height() - 12),
                                 QPoint(x, self.height() - 2)])
            painter.drawLine(x, self.height() - 2, x, self.height())

    def _seek_to(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.seek_requested.emit(self.view.time_at(max(0.0, event.position().x() - AXIS_WIDTH)))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._seek_to(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._seek_to(event)


class WaveformView(QWidget):
    selection_changed = Signal(float, float)
    zoom_requested = Signal(float, float)
    scroll_requested = Signal(int)
    resized = Signal()

    def __init__(self, view: ViewState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view = view
        self.theme = "dark"
        self.track: TrackSnapshot | None = None
        self.selection = (0.0, 0.0)
        self.playhead: float | None = None  # playback position; ``None`` while stopped
        self.tool = "selection"
        self._anchor: float | None = None  # fixed end of the selection being dragged
        self._spectrogram: QImage | None = None
        self._spectrogram_data: NDArray[np.uint8] | None = None
        self._cache = QPixmap()
        self._selection_color = color(self.theme, "selection")
        self._selection_color.setAlpha(95)
        self._playhead_pen = QPen(color(self.theme, "playhead"), 2)
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # so arrow keys leave the sliders

    def set_track(self, track: TrackSnapshot | None) -> None:
        self.track = track
        self.rebuild()

    def set_spectrogram(self, data: NDArray[np.uint8] | None) -> None:
        """Show *data* as a spectrogram, or the waveform when ``None``. Rebuilds on next set_track."""
        if data is self._spectrogram_data:
            return
        self._spectrogram_data = data
        if data is None:
            self._spectrogram = None
        else:
            stride = (data.shape[1] + 3) & ~3  # QImage scanlines are 32-bit aligned
            padded = np.zeros((data.shape[0], stride), dtype=np.uint8)
            padded[:, :data.shape[1]] = data
            image = QImage(padded.data, data.shape[1], data.shape[0], stride,
                           QImage.Format.Format_Indexed8)
            image.setColorTable(_HEAT)
            self._spectrogram = image.copy()  # detach from the NumPy buffer

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self._selection_color = color(theme, "selection")
        self._selection_color.setAlpha(95)
        self._playhead_pen = QPen(color(theme, "playhead"), 2)
        self.rebuild()

    def set_selection(self, start: float, end: float) -> None:
        self.selection = (start, end)
        self.update()

    def set_playhead(self, seconds: float | None) -> None:
        if seconds != self.playhead:
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
            ruler_width = AXIS_WIDTH
            track_end_x = ruler_width + round(
                (self.track.duration - self.view.offset) / self.view.seconds_per_pixel
            )
            visible_end_x = min(self.width(), max(ruler_width, track_end_x))
            # Do not render the final peak repeatedly across the empty area
            # after the actual audio. This area is deliberately distinct so
            # the end of the track remains obvious while zoomed out.
            if visible_end_x < self.width():
                empty_area = color(self.theme, "panel")
                empty_area.setAlpha(95)
                painter.fillRect(visible_end_x, 0, self.width() - visible_end_x,
                                 self.height(), empty_area)
            if self._spectrogram is not None and visible_end_x > ruler_width:
                columns = self._spectrogram.width()
                per_second = columns / max(self.track.duration, 1e-9)
                source_left = self.view.offset * per_second
                source_width = (visible_end_x - ruler_width) * self.view.seconds_per_pixel * per_second
                painter.drawImage(
                    QRectF(ruler_width, 0, visible_end_x - ruler_width, self.height()),
                    self._spectrogram,
                    QRectF(source_left, 0, source_width, self._spectrogram.height()),
                )
                painter.end()
                self.update()
                return
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
                for x in range(ruler_width, visible_end_x):
                    at = self.view.time_at(x - ruler_width)
                    index = min(count - 1, int(at / self.track.duration * count))
                    peak, rms = peaks_for_channel[index]
                    painter.setPen(QPen(color(self.theme, "wave")))
                    painter.drawLine(x, round(center_y - peak * scale), x, round(center_y + peak * scale))
                    painter.setPen(QPen(color(self.theme, "rms")))
                    painter.drawLine(x, round(center_y - rms * scale), x, round(center_y + rms * scale))
            if ruler_width <= track_end_x < self.width():
                end_pen = QPen(color(self.theme, "track_end"), 2)
                end_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(end_pen)
                painter.drawLine(track_end_x, 0, track_end_x, self.height())
                painter.setPen(color(self.theme, "track_end"))
                painter.drawText(track_end_x + 5, 16, "END")
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
            painter.fillRect(round(self.view.x_at(start)) + AXIS_WIDTH, 0,
                             round((end - start) / self.view.seconds_per_pixel), self.height(),
                             self._selection_color)
        # Two independent needles, as in Audacity: the edit cursor (thin line at the click point,
        # visible when nothing is selected) and the green playhead that only exists during playback.
        if end <= start:
            x = round(self.view.x_at(start)) + AXIS_WIDTH
            painter.setPen(QPen(color(self.theme, "text"), 1))
            painter.drawLine(x, 0, x, self.height())
        if self.playhead is not None:
            x = round(self.view.x_at(self.playhead)) + AXIS_WIDTH
            painter.setPen(self._playhead_pen)
            painter.drawLine(x, 0, x, self.height())

    def _time_at_event(self, event: QMouseEvent) -> float:
        return self.view.time_at(max(0.0, event.position().x() - AXIS_WIDTH))

    def _edge_at(self, x: float) -> str | None:
        """Return ``"start"``/``"end"`` when *x* is within grabbing distance of a selection edge."""
        start, end = self.selection
        if end <= start:
            return None
        near = {name: abs(self.view.x_at(value) + AXIS_WIDTH - x)
                for name, value in (("start", start), ("end", end))}
        name = min(near, key=lambda key: near[key])
        return name if near[name] <= EDGE_GRAB_PIXELS else None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self.track is None:
            return
        at = self._time_at_event(event)
        if self.tool == "zoom":
            factor = 0.5 if event.button() == Qt.MouseButton.RightButton else 2.0
            self.zoom_requested.emit(factor, event.position().x() - AXIS_WIDTH)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        start, end = self.selection
        edge = self._edge_at(event.position().x())
        if edge is not None:
            # Grab an edge: the opposite edge stays put.
            self._anchor = end if edge == "start" else start
        elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            # Extend: keep whichever end of the selection (or the needle) is farther away.
            if end > start:
                self._anchor = end if abs(at - start) < abs(at - end) else start
            else:
                self._anchor = start  # extend from the edit cursor
            self.selection_changed.emit(min(self._anchor, at), max(self._anchor, at))
        else:
            self._anchor = at
            self.selection_changed.emit(at, at)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._anchor is None:
            near_edge = self.tool == "selection" and self._edge_at(event.position().x()) is not None
            self.setCursor(Qt.CursorShape.SizeHorCursor if near_edge else Qt.CursorShape.IBeamCursor
                           if self.tool == "selection" and self.track is not None
                           else Qt.CursorShape.ArrowCursor)
            return
        x = event.position().x() - AXIS_WIDTH
        # Dragging past either side scrolls the view so the selection can keep growing.
        if x < 0:
            self.scroll_requested.emit(-1)
        elif x > self.width() - AXIS_WIDTH:
            self.scroll_requested.emit(1)
        at = self._time_at_event(event)
        self.selection_changed.emit(min(at, self._anchor), max(at, self._anchor))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        del event
        self._anchor = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Double-click selects the whole track, as double-clicking a clip does in Audacity."""
        if self.track is not None and self.tool == "selection" \
                and event.button() == Qt.MouseButton.LeftButton:
            self.selection_changed.emit(0.0, self.track.duration)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_requested.emit(1.25 if event.angleDelta().y() > 0 else 0.8,
                                     event.position().x() - AXIS_WIDTH)
        else:
            self.scroll_requested.emit(-1 if event.angleDelta().y() > 0 else 1)
        event.accept()


class LabelTrack(QWidget):
    """Strip showing text labels (points or regions) aligned with the waveform."""

    label_clicked = Signal(float, float)

    def __init__(self, view: ViewState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view = view
        self.theme = "dark"
        self.labels: tuple[Label, ...] = ()
        self.setFixedHeight(24)

    def set_labels(self, labels: tuple[Label, ...]) -> None:
        self.labels = labels
        self.update()

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), color(self.theme, "ruler"))
        accent = color(self.theme, "accent")
        region = QColor(accent)
        region.setAlpha(70)
        for label in self.labels:
            x0 = round(self.view.x_at(label.start)) + AXIS_WIDTH
            x1 = round(self.view.x_at(label.end)) + AXIS_WIDTH
            if x1 < 0 or x0 > self.width():
                continue
            painter.setPen(QPen(accent, 1))
            if x1 > x0:
                painter.fillRect(x0, 0, x1 - x0, self.height(), region)
                painter.drawLine(x1, 0, x1, self.height())
            painter.drawLine(x0, 0, x0, self.height())
            painter.setPen(color(self.theme, "text"))
            painter.drawText(x0 + 4, 16, label.text)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        at = self.view.time_at(max(0.0, event.position().x() - AXIS_WIDTH))
        for label in self.labels:
            if label.start - 2 * self.view.seconds_per_pixel <= at <= max(label.end, label.start) \
                    + 2 * self.view.seconds_per_pixel:
                self.label_clicked.emit(label.start, label.end)
                return


class LevelMeter(QWidget):
    """Peak meter (dBFS) with fast attack, slow release and a short peak hold."""

    FLOOR_DB = -60.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = "dark"
        self.levels: list[float] = [0.0, 0.0]
        self.held: list[float] = [0.0, 0.0]
        self.setFixedSize(130, 28)
        self.setToolTip("Playback level (dBFS)")

    def set_theme(self, theme: str) -> None:
        self.theme = theme
        self.update()

    def set_levels(self, peaks: tuple[float, ...]) -> None:
        values = list(peaks[:2]) if peaks else [0.0]
        if len(values) == 1:
            values = values * 2
        for index, value in enumerate(values):
            self.levels[index] = value if value >= self.levels[index] else self.levels[index] * 0.82
            self.held[index] = value if value >= self.held[index] else self.held[index] * 0.97
        self.update()

    @classmethod
    def fraction(cls, level: float) -> float:
        """Map a linear amplitude to 0‥1 along a -60…0 dBFS scale."""
        if level <= 0:
            return 0.0
        return max(0.0, min(1.0, (20 * math.log10(level) - cls.FLOOR_DB) / -cls.FLOOR_DB))

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), color(self.theme, "ruler"))
        for row, (level, hold) in enumerate(zip(self.levels, self.held, strict=True)):
            y = 4 + row * 10
            width = self.width() - 8
            fraction = self.fraction(level)
            bar = color(self.theme, "track_end" if fraction > 0.98 else "accent")
            painter.fillRect(4, y, round(width * fraction), 8, bar)
            painter.setPen(QPen(color(self.theme, "playhead"), 1))
            hold_x = 4 + round(width * self.fraction(hold))
            painter.drawLine(hold_x, y, hold_x, y + 8)
            painter.setPen(QPen(color(self.theme, "border"), 1))
            painter.drawRect(4, y, width, 8)


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
