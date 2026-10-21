"""Audamix's Qt Widgets main window."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QSettings, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollBar,
    QSlider,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .model import ProjectModel, Transport
from .real_backend import AudioProject, AudioTransport
from .theme import apply_theme
from .widgets import SelectionBar, TimelineRuler, ViewState, WaveformView


class EffectThread(QThread):
    result = Signal(bool, str)

    def __init__(self, project: ProjectModel, name: str, parameters: dict[str, float],
                 parent: QWidget) -> None:
        super().__init__(parent)
        self._project = project
        self._name = name
        self._parameters = parameters

    def run(self) -> None:
        self.result.emit(*self._project.apply_effect(self._name, self._parameters))


class MainWindow(QMainWindow):
    def __init__(self, project: ProjectModel | None = None, transport: Transport | None = None,
                 settings: QSettings | None = None) -> None:
        super().__init__()
        self.project: ProjectModel = project if project is not None else AudioProject()
        self.transport: Transport = transport if transport is not None else AudioTransport(self)
        self.settings = settings if settings is not None else QSettings("Audamix", "Frontend")
        self.theme = str(self.settings.value("theme", "dark"))
        if self.theme not in {"dark", "light"}:
            self.theme = "dark"
        app = cast(QApplication, QApplication.instance())
        apply_theme(app, self.theme)
        self.view = ViewState()
        self.selection = (0.0, 0.0)
        self.commands: dict[str, QAction] = {}
        self._effect_thread: EffectThread | None = None
        self.setWindowTitle("Audamix")
        self.setMinimumSize(800, 520)
        self.resize(1160, 720)
        self._create_actions()
        self._create_menus()
        self._create_toolbars()
        self._create_track_area()
        self._create_selection_dock()
        self.statusBar().showMessage("Open an audio file to begin")
        self.rate_label = QLabel("No project", self)
        self.statusBar().addPermanentWidget(self.rate_label)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(90)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        geometry = self.settings.value("geometry")
        state = self.settings.value("window_state")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state)
        saved_size = self.settings.value("size")
        if saved_size is not None:
            self.resize(saved_size)
        self._refresh()

    def _action(self, name: str, label: str, shortcut: str | None = None,
                checkable: bool = False) -> QAction:
        action = QAction(label, self)
        action.setObjectName(name)
        action.setCheckable(checkable)
        if shortcut is not None:
            action.setShortcut(shortcut)
        self.addAction(action)
        self.commands[name] = action
        return action

    def _create_actions(self) -> None:
        self._action("open", "Open…", "Ctrl+O").triggered.connect(self._open)
        self._action("export", "Export…", "Ctrl+Shift+E").triggered.connect(self._export)
        self._action("exit", "Exit", "Ctrl+Q").triggered.connect(self.close)
        self._action("undo", "Undo", "Ctrl+Z").triggered.connect(self._undo)
        self._action("select_all", "Select All", "Ctrl+A").triggered.connect(self._select_all)
        self._action("clear_selection", "Clear Selection", "Escape").triggered.connect(self._clear_selection)
        self._action("zoom_in", "Zoom In", "Ctrl+1").triggered.connect(self._zoom_in)
        self._action("zoom_out", "Zoom Out", "Ctrl+3").triggered.connect(self._zoom_out)
        self._action("fit_selection", "Fit Selection", "Ctrl+E").triggered.connect(self._fit_selection)
        self._action("fit_project", "Fit Project", "Ctrl+F").triggered.connect(self._fit_project)
        self._action("light_theme", "Light Theme", checkable=True).triggered.connect(self._toggle_theme)
        self.commands["light_theme"].setChecked(self.theme == "light")
        self._action("play_stop", "Play / Stop", "Space").triggered.connect(self._play_stop)
        self._action("pause", "Pause", "P").triggered.connect(self._pause)
        self._action("stop", "Stop").triggered.connect(self._stop)
        self._action("skip_start", "Skip to Start", "Home").triggered.connect(self._skip_start)
        self._action("skip_end", "Skip to End", "End").triggered.connect(self._skip_end)
        group = QActionGroup(self)
        group.setExclusive(True)
        for name, label in (("selection_tool", "Selection Tool"), ("zoom_tool", "Zoom Tool")):
            action = self._action(name, label, checkable=True)
            group.addAction(action)
            action.triggered.connect(self._tool_changed)
        self.commands["selection_tool"].setChecked(True)
        self._action("mute", "Mute", checkable=True).triggered.connect(self._controls_changed)
        self._action("solo", "Solo", checkable=True).triggered.connect(self._controls_changed)
        self._action("collapse", "Collapse Track", checkable=True).triggered.connect(self._collapse)
        self._action("close_track", "Close Track").triggered.connect(self._close_track)
        self._action("about", "About Audamix").triggered.connect(self._about)
        for name, label in (("gain", "Change Gain…"), ("lowpass", "Low-Pass Filter…"),
                            ("highpass", "High-Pass Filter…"), ("bandpass", "Band-Pass Filter…"),
                            ("classical_denoise", "Classical Denoise"),
                            ("ai_denoise", "AI Denoise"), ("ai_declip", "AI Declip")):
            self._action(name, label).triggered.connect(self._effect)

    def _create_menus(self) -> None:
        menus: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("File", ("open", "export", "exit")),
            ("Edit", ("undo",)),
            ("Select", ("select_all", "clear_selection", "selection_tool", "zoom_tool")),
            ("View", ("zoom_in", "zoom_out", "fit_selection", "fit_project", "light_theme")),
            ("Transport", ("play_stop", "pause", "stop", "skip_start", "skip_end")),
            ("Tracks", ("mute", "solo", "collapse", "close_track")),
            ("Effects", ("gain", "lowpass", "highpass", "bandpass", "classical_denoise",
                         "ai_denoise", "ai_declip")),
            ("Help", ("about",)),
        )
        for title, names in menus:
            menu = self.menuBar().addMenu(title)
            for name in names:
                menu.addAction(self.commands[name])

    def _create_toolbars(self) -> None:
        for title, names in (("Transport", ("pause", "play_stop", "stop", "skip_start", "skip_end")),
                             ("Tools", ("selection_tool", "zoom_tool")),
                             ("Edit", ("undo", "zoom_in", "zoom_out", "fit_selection", "fit_project"))):
            bar = QToolBar(title, self)
            bar.setObjectName(f"toolbar_{title.lower()}")
            bar.setMovable(True)
            for name in names:
                bar.addAction(self.commands[name])
            self.addToolBar(bar)

    def _create_track_area(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        ruler_row = QWidget(central)
        ruler_layout = QHBoxLayout(ruler_row)
        ruler_layout.setContentsMargins(0, 0, 0, 0)
        spacer = QWidget(ruler_row)
        spacer.setFixedWidth(195)
        ruler_layout.addWidget(spacer)
        self.ruler = TimelineRuler(self.view, ruler_row)
        ruler_layout.addWidget(self.ruler, 1)
        layout.addWidget(ruler_row)
        track_row = QWidget(central)
        row = QHBoxLayout(track_row)
        row.setContentsMargins(0, 0, 0, 0)
        panel = QWidget(track_row)
        panel.setFixedWidth(195)
        panel_layout = QVBoxLayout(panel)
        name_row = QHBoxLayout()
        self.track_name = QLabel("No track", panel)
        self.track_name.setWordWrap(True)
        name_row.addWidget(self.track_name, 1)
        dropdown = QToolButton(panel)
        dropdown.setText("▾")
        dropdown.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        dropdown_menu = QMenu(dropdown)
        for name in ("mute", "solo", "collapse", "close_track"):
            dropdown_menu.addAction(self.commands[name])
        dropdown.setMenu(dropdown_menu)
        name_row.addWidget(dropdown)
        self.collapse_button = QPushButton("−", panel)
        self.collapse_button.setToolTip("Collapse Track")
        self.collapse_button.setFixedWidth(25)
        self.collapse_button.clicked.connect(self.commands["collapse"].trigger)
        name_row.addWidget(self.collapse_button)
        self.close_button = QPushButton("×", panel)
        self.close_button.setToolTip("Close Track")
        self.close_button.setFixedWidth(25)
        self.close_button.clicked.connect(self.commands["close_track"].trigger)
        name_row.addWidget(self.close_button)
        panel_layout.addLayout(name_row)
        self.track_info = QLabel("", panel)
        self.track_info.setWordWrap(True)
        panel_layout.addWidget(self.track_info)
        self.mute_button = QToolButton(panel)
        self.mute_button.setDefaultAction(self.commands["mute"])
        self.solo_button = QToolButton(panel)
        self.solo_button.setDefaultAction(self.commands["solo"])
        buttons = QHBoxLayout()
        buttons.addWidget(self.mute_button)
        buttons.addWidget(self.solo_button)
        panel_layout.addLayout(buttons)
        self.gain_slider = QSlider(Qt.Orientation.Horizontal, panel)
        self.gain_slider.setRange(0, 200)
        self.gain_slider.setValue(100)
        self.pan_slider = QSlider(Qt.Orientation.Horizontal, panel)
        self.pan_slider.setRange(-100, 100)
        self.gain_slider.valueChanged.connect(self._controls_changed)
        self.pan_slider.valueChanged.connect(self._controls_changed)
        panel_layout.addWidget(QLabel("Gain", panel))
        panel_layout.addWidget(self.gain_slider)
        panel_layout.addWidget(QLabel("Pan", panel))
        panel_layout.addWidget(self.pan_slider)
        panel_layout.addStretch()
        row.addWidget(panel)
        self.waveform = WaveformView(self.view, track_row)
        self.waveform.selection_changed.connect(self._set_selection)
        self.waveform.seek_requested.connect(self._seek)
        self.waveform.zoom_requested.connect(self._zoom_requested)
        self.waveform.scroll_requested.connect(self._scroll_wheel)
        self.waveform.resized.connect(self._sync_view)
        row.addWidget(self.waveform, 1)
        layout.addWidget(track_row, 1)
        self.scrollbar = QScrollBar(Qt.Orientation.Horizontal, central)
        self.scrollbar.setRange(0, 0)
        self.scrollbar.valueChanged.connect(self._scroll_changed)
        layout.addWidget(self.scrollbar)
        self.setCentralWidget(central)

    def _create_selection_dock(self) -> None:
        dock = QDockWidget("Selection", self)
        dock.setObjectName("selection_dock")
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.selection_bar = SelectionBar(dock)
        self.selection_bar.selection_edited.connect(self._set_selection)
        dock.setWidget(self.selection_bar)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

    def _refresh(self) -> None:
        track = self.project.snapshot()
        loaded = track is not None
        self.waveform.set_track(track)
        self.track_name.setText(track.name if track else "No track")
        self.track_info.setText(
            f"{track.duration:.1f} s · {track.sample_count:,} samples" if track else ""
        )
        self.rate_label.setText(f"{track.sample_rate:,} Hz · {track.channels} ch" if track else "No project")
        self.collapse_button.setEnabled(loaded)
        self.close_button.setEnabled(loaded)
        for name in ("export", "select_all", "clear_selection", "play_stop", "pause", "stop",
                     "skip_start", "skip_end", "mute", "solo", "collapse", "close_track",
                     "gain", "lowpass", "highpass", "bandpass", "classical_denoise",
                     "ai_denoise", "ai_declip", "zoom_in", "zoom_out", "fit_project"):
            self.commands[name].setEnabled(loaded)
        self.gain_slider.setEnabled(loaded and self._effect_thread is None)
        self.pan_slider.setEnabled(loaded and self._effect_thread is None)
        self.commands["fit_selection"].setEnabled(loaded and self.selection[1] > self.selection[0])
        self.commands["undo"].setEnabled(self.project.can_undo())
        if self._effect_thread is not None:
            for name in ("open", "export", "undo", "play_stop", "pause", "stop", "close_track",
                         "mute", "solo",
                         "gain", "lowpass", "highpass", "bandpass", "classical_denoise",
                         "ai_denoise", "ai_declip"):
                self.commands[name].setEnabled(False)

    @Slot(bool)
    def _open(self, checked: bool = False) -> None:
        del checked
        path, _ = QFileDialog.getOpenFileName(self, "Open audio", "", "Audio (*.wav *.flac *.ogg *.aiff)")
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        if self._effect_thread is not None:
            return
        self.transport.load("")
        ok, message = self.project.open_file(path)
        self.statusBar().showMessage(message)
        if not ok:
            QMessageBox.warning(self, "Open failed", message)
            return
        track = self.project.snapshot()
        if track is not None:
            self.view.duration = track.duration
            self.gain_slider.setValue(100)
            self.pan_slider.setValue(0)
            self.commands["mute"].setChecked(False)
            self.commands["solo"].setChecked(False)
            self._controls_changed()
            self.transport.stop()
            self.selection = (0.0, 0.0)
            self.selection_bar.set_selection(0.0, 0.0)
            self._fit_project()
            self._refresh()

    @Slot(bool)
    def _export(self, checked: bool = False) -> None:
        del checked
        path, _ = QFileDialog.getSaveFileName(self, "Export audio", "", "WAV (*.wav)")
        if path:
            if not Path(path).suffix:
                path += ".wav"
            ok, message = self.project.export_file(path)
            self.statusBar().showMessage(message)
            if not ok:
                QMessageBox.warning(self, "Export unavailable", message)

    @Slot(bool)
    def _undo(self, checked: bool = False) -> None:
        del checked
        if self.project.undo():
            self.transport.load("")
            self.statusBar().showMessage("Last change undone")
        self._refresh()

    @Slot(bool)
    def _select_all(self, checked: bool = False) -> None:
        del checked
        self._set_selection(0.0, self.view.duration)

    @Slot(bool)
    def _clear_selection(self, checked: bool = False) -> None:
        del checked
        self._set_selection(self.selection[0], self.selection[0])

    @Slot(float, float)
    def _set_selection(self, start: float, end: float) -> None:
        start = min(self.view.duration, max(0.0, start))
        end = min(self.view.duration, max(start, end))
        self.selection = (start, end)
        self.waveform.set_selection(start, end)
        self.selection_bar.set_selection(start, end)
        self.commands["fit_selection"].setEnabled(end > start and self.project.snapshot() is not None)

    @Slot(float)
    def _seek(self, at: float) -> None:
        self.transport.seek(at)
        self.waveform.set_playhead(self.transport.position())

    @Slot()
    def _sync_view(self) -> None:
        max_offset = max(0.0, self.view.duration - self.waveform.width() * self.view.seconds_per_pixel)
        self.view.offset = min(max_offset, self.view.offset)
        self.scrollbar.blockSignals(True)
        self.scrollbar.setRange(0, round(max_offset * 1000))
        self.scrollbar.setPageStep(round(self.waveform.width() * self.view.seconds_per_pixel * 1000))
        self.scrollbar.setValue(round(self.view.offset * 1000))
        self.scrollbar.blockSignals(False)
        self.ruler.rebuild()
        self.waveform.rebuild()

    @Slot(float, float)
    def _zoom_requested(self, factor: float, x: float) -> None:
        self.view.zoom(factor, max(0.0, x), self.waveform.width())
        self._sync_view()

    @Slot(bool)
    def _zoom_in(self, checked: bool = False) -> None:
        del checked
        self._zoom_requested(2.0, self.waveform.width() / 2)

    @Slot(bool)
    def _zoom_out(self, checked: bool = False) -> None:
        del checked
        self._zoom_requested(0.5, self.waveform.width() / 2)

    @Slot(bool)
    def _fit_selection(self, checked: bool = False) -> None:
        del checked
        self.view.fit(*self.selection, self.waveform.width())
        self._sync_view()

    @Slot(bool)
    def _fit_project(self, checked: bool = False) -> None:
        del checked
        self.view.fit(0.0, self.view.duration, self.waveform.width())
        self._sync_view()

    @Slot(int)
    def _scroll_changed(self, value: int) -> None:
        self.view.offset = value / 1000
        self.ruler.rebuild()
        self.waveform.rebuild()

    @Slot(int)
    def _scroll_wheel(self, direction: int) -> None:
        self.scrollbar.setValue(self.scrollbar.value() + direction * max(100, self.scrollbar.pageStep() // 8))

    @Slot(bool)
    def _tool_changed(self, checked: bool = False) -> None:
        del checked
        self.waveform.tool = "zoom" if self.commands["zoom_tool"].isChecked() else "selection"

    @Slot(bool)
    def _toggle_theme(self, checked: bool = False) -> None:
        self.theme = "light" if checked else "dark"
        apply_theme(cast(QApplication, QApplication.instance()), self.theme)
        self.waveform.set_theme(self.theme)
        self.ruler.set_theme(self.theme)
        self.settings.setValue("theme", self.theme)

    @Slot(bool)
    def _play_stop(self, checked: bool = False) -> None:
        del checked
        if self.transport.is_playing():
            self.transport.stop()
            self.statusBar().showMessage("Stopped")
        else:
            try:
                position = self.transport.position()
                self.transport.load(self.project.preview_path())
                self.transport.seek(position)
            except (OSError, RuntimeError, ValueError) as exc:
                QMessageBox.warning(self, "Playback failed", str(exc))
                return
            self.transport.play()
            self.statusBar().showMessage("Playback requested")
        self.waveform.set_playhead(self.transport.position())

    @Slot(bool)
    def _pause(self, checked: bool = False) -> None:
        del checked
        if self.transport.is_paused():
            self.transport.play()
            self.statusBar().showMessage("Playback resumed")
        elif self.transport.is_playing():
            self.transport.pause()
            self.statusBar().showMessage("Paused")

    @Slot(bool)
    def _stop(self, checked: bool = False) -> None:
        del checked
        self.transport.stop()
        self.waveform.set_playhead(0.0)

    @Slot(bool)
    def _skip_start(self, checked: bool = False) -> None:
        del checked
        self._seek(0.0)

    @Slot(bool)
    def _skip_end(self, checked: bool = False) -> None:
        del checked
        self._seek(self.view.duration)

    @Slot()
    def _tick(self) -> None:
        self.transport.tick(0.05, self.view.duration)
        if self.transport.is_playing():
            self.waveform.set_playhead(self.transport.position())

    @Slot()
    @Slot(bool)
    @Slot(int)
    def _controls_changed(self, value: bool | int = False) -> None:
        del value
        self.project.set_controls(self.commands["mute"].isChecked(), self.commands["solo"].isChecked(),
                                  self.gain_slider.value() / 100, self.pan_slider.value() / 100)
        if self.transport.is_playing():
            position = self.transport.position()
            self.transport.load(self.project.preview_path())
            self.transport.seek(position)
            self.transport.play()

    @Slot(bool)
    def _collapse(self, checked: bool = False) -> None:
        self.waveform.setMinimumHeight(64 if checked else 190)
        self.waveform.setMaximumHeight(64 if checked else 16777215)

    @Slot(bool)
    def _close_track(self, checked: bool = False) -> None:
        del checked
        self.transport.load("")
        self.project.close()
        self.selection = (0.0, 0.0)
        self._refresh()

    @Slot(bool)
    def _effect(self, checked: bool = False) -> None:
        del checked
        if self._effect_thread is not None:
            return
        sender = self.sender()
        if not isinstance(sender, QAction):
            return
        name = sender.objectName()
        parameters: dict[str, float] = {}
        if name == "gain":
            value, accepted = QInputDialog.getDouble(self, "Gain", "Gain (dB)", 0.0, -60, 24, 1)
            if not accepted:
                return
            parameters["dB"] = value
        elif name in {"lowpass", "highpass", "bandpass"}:
            track = self.project.snapshot()
            maximum = max(1.0, track.sample_rate / 2 - 1) if track is not None else 22049.0
            value, accepted = QInputDialog.getDouble(
                self, "Filter", "Frequency (Hz)", min(2000.0, maximum), 1, maximum, 0,
            )
            if not accepted:
                return
            parameters["Hz"] = value
        if name == "ai_declip":
            QMessageBox.information(self, "AI Declip", "A reconstructed waveform would be an estimate.")
        self.transport.stop()
        self.progress.show()
        self.statusBar().showMessage(f"Applying {name}…")
        thread = EffectThread(self.project, name, parameters, self)
        self._effect_thread = thread
        thread.result.connect(self._finish_effect)
        thread.finished.connect(self._effect_finished)
        self._refresh()
        thread.start()

    @Slot(bool, str)
    def _finish_effect(self, ok: bool, message: str) -> None:
        self.progress.hide()
        self.statusBar().showMessage(message)
        if not ok:
            QMessageBox.warning(self, "Effect failed", message)
        else:
            self.transport.load("")
        self._refresh()

    @Slot()
    def _effect_finished(self) -> None:
        if self._effect_thread is not None:
            self._effect_thread.deleteLater()
            self._effect_thread = None
        self._refresh()

    @Slot(bool)
    def _about(self, checked: bool = False) -> None:
        del checked
        QMessageBox.information(self, "About Audamix", "Audamix audio editor")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._effect_thread is not None:
            event.ignore()
            self.statusBar().showMessage("Wait for the effect to finish before closing")
            return
        self.transport.load("")
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("window_state", self.saveState())
        self.settings.setValue("size", self.size())
        self.settings.setValue("theme", self.theme)
        self.settings.sync()
        super().closeEvent(event)
