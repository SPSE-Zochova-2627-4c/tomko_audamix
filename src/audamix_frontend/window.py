"""Audamix's Qt Widgets main window."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QSettings, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtMultimedia import QMediaDevices
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

from audamix.data.audio_data import SUPPORTED_AUDIO_EXTENSIONS
from audamix.dsp.effects import SPECS as EFFECT_SPECS

from .dialogs import EffectDialog, GenerateDialog, PreferencesDialog, device_key, format_statistics
from .model import SUPPORTED_AUDIO_FILTER, ProjectModel, Transport
from .real_backend import AudioProject, AudioTransport
from .theme import apply_theme
from .widgets import LabelTrack, LevelMeter, SelectionBar, TimelineRuler, ViewState, WaveformView

EXPORT_FILTERS = {
    "WAV": "WAV (*.wav)", "FLAC": "FLAC (*.flac)", "OGG/Opus": "OGG/Opus (*.ogg *.oga *.opus)",
    "AIFF": "AIFF (*.aiff *.aif)", "AU": "AU (*.au *.snd)", "CAF": "CAF (*.caf)", "MP3": "MP3 (*.mp3)",
}
# Actions that need a non-empty selection / that change the audio structure.
SELECTION_EDITS = ("cut", "copy", "delete", "trim", "silence", "fade_in", "fade_out")
EFFECT_NAMES = ("gain", "lowpass", "highpass", "bandpass", "classical_denoise", "ai_denoise", "ai_declip",
                *EFFECT_SPECS)
GENERATORS = ("tone", "silence", "noise")


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
        self.setAcceptDrops(True)
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
        self._was_playing = False
        self._loop_once = False
        self._user_stopped = True
        self.output_device = str(self.settings.value("output_device", ""))
        self.export_format = str(self.settings.value("export_format", "WAV"))
        self.setWindowTitle("Audamix")
        self.setMinimumSize(800, 520)
        self.resize(1160, 720)
        self._create_actions()
        self._create_menus()
        self._create_toolbars()
        self._create_track_area()
        self._create_selection_dock()
        if self.output_device:
            self.transport.set_output_device(self.output_device)
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
        self._action("redo", "Redo", "Ctrl+Y").triggered.connect(self._redo)
        for name, label, shortcut in (
            ("cut", "Cut", "Ctrl+X"), ("copy", "Copy", "Ctrl+C"), ("paste", "Paste", "Ctrl+V"),
            ("delete", "Delete", "Delete"), ("trim", "Trim to Selection", "Ctrl+T"),
            ("silence", "Silence Selection", "Ctrl+L"), ("fade_in", "Fade In", None),
            ("fade_out", "Fade Out", None),
        ):
            self._action(name, label, shortcut).triggered.connect(self._edit)
        self._action("add_label", "Add Label at Selection…", "Ctrl+B").triggered.connect(self._add_label)
        self._action("remove_labels", "Remove Labels in Selection").triggered.connect(self._remove_labels)
        for kind in GENERATORS:
            self._action(f"generate_{kind}", f"{kind.capitalize()}…").triggered.connect(self._generate)
        self._action("statistics", "Statistics…", "Ctrl+I").triggered.connect(self._statistics)
        self._action("spectrogram", "Show Spectrogram", "Ctrl+Shift+S", checkable=True).triggered.connect(
            self._refresh_checked)
        self._action("loop", "Loop Playback", "Shift+L", checkable=True)
        self._action("preferences", "Preferences…", "Ctrl+,").triggered.connect(self._preferences)
        self._action("select_all", "Select All", "Ctrl+A").triggered.connect(self._select_all)
        self._action("clear_selection", "Clear Selection", "Escape").triggered.connect(self._clear_selection)
        self._action("zoom_in", "Zoom In", "Ctrl+1").triggered.connect(self._zoom_in)
        self._action("zoom_out", "Zoom Out", "Ctrl+3").triggered.connect(self._zoom_out)
        self._action("fit_selection", "Fit Selection", "Ctrl+E").triggered.connect(self._fit_selection)
        self._action("fit_project", "Fit Project", "Ctrl+F").triggered.connect(self._fit_project)
        self._action("light_theme", "Light Theme", checkable=True).triggered.connect(self._toggle_theme)
        self.commands["light_theme"].setChecked(self.theme == "light")
        self._action("play", "Play", "Space").triggered.connect(self._play_toggle)
        self._action("loop_play", "Loop Play", "Shift+Space").triggered.connect(self._loop_play)
        for name, label, shortcut in (
            ("cursor_left", "Cursor Left", "Left"), ("cursor_right", "Cursor Right", "Right"),
            ("extend_left", "Extend Selection Left", "Shift+Left"),
            ("extend_right", "Extend Selection Right", "Shift+Right"),
            ("contract_left", "Contract Selection from Right", "Ctrl+Shift+Left"),
            ("contract_right", "Contract Selection from Left", "Ctrl+Shift+Right"),
        ):
            self._action(name, label, shortcut).triggered.connect(self._nudge)
        self._action("select_to_start", "Selection to Start", "Shift+Home").triggered.connect(
            self._select_to_start)
        self._action("select_to_end", "Selection to End", "Shift+End").triggered.connect(self._select_to_end)
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
        for name, spec in EFFECT_SPECS.items():
            self._action(name, spec.title + ("…" if spec.params else "")).triggered.connect(self._effect)

    def _create_menus(self) -> None:
        menus: tuple[tuple[str, tuple[str | None, ...]], ...] = (
            ("File", ("open", "export", "exit")),
            ("Edit", ("undo", "redo", None, "cut", "copy", "paste", "delete", "trim", "silence", None,
                      "fade_in", "fade_out", None, "add_label", "remove_labels", None, "preferences")),
            ("Select", ("select_all", "clear_selection", "select_to_start", "select_to_end", None,
                        "cursor_left", "cursor_right", "extend_left", "extend_right",
                        "contract_left", "contract_right", None, "selection_tool", "zoom_tool")),
            ("View", ("zoom_in", "zoom_out", "fit_selection", "fit_project", "spectrogram", "light_theme")),
            ("Transport", ("play", "pause", "stop", "skip_start", "skip_end", "loop_play", "loop")),
            ("Tracks", ("mute", "solo", "collapse", "close_track")),
            ("Effects", ("gain", "lowpass", "highpass", "bandpass", "classical_denoise",
                         "ai_denoise", "ai_declip")),
            ("Generate", tuple(f"generate_{kind}" for kind in GENERATORS)),
            ("Analyze", ("statistics",)),
            ("Help", ("about",)),
        )
        for title, names in menus:
            menu = self.menuBar().addMenu(title)
            for name in names:
                if name is None:
                    menu.addSeparator()
                else:
                    menu.addAction(self.commands[name])
            if title == "Effects":
                menu.addSeparator()
                groups: dict[str, QMenu] = {}
                for name, spec in EFFECT_SPECS.items():
                    group = groups.get(spec.group) or groups.setdefault(spec.group, menu.addMenu(spec.group))
                    group.addAction(self.commands[name])
            if title == "Transport":
                self.device_menu = menu.addMenu("Output Device")
                self.device_menu.aboutToShow.connect(self._populate_devices)

    def _create_toolbars(self) -> None:
        for title, names in (("Transport", ("pause", "play", "stop", "skip_start", "skip_end")),
                             ("Tools", ("selection_tool", "zoom_tool")),
                             ("Edit", ("undo", "redo", "zoom_in", "zoom_out", "fit_selection",
                                       "fit_project"))):
            bar = QToolBar(title, self)
            bar.setObjectName(f"toolbar_{title.lower()}")
            bar.setMovable(True)
            for name in names:
                bar.addAction(self.commands[name])
            if title == "Transport":
                self.meter = LevelMeter(bar)
                bar.addWidget(self.meter)
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
        self.ruler.seek_requested.connect(self._ruler_seek)
        ruler_layout.addWidget(self.ruler, 1)
        layout.addWidget(ruler_row)
        label_row = QWidget(central)
        label_layout = QHBoxLayout(label_row)
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_name = QLabel("Labels", label_row)
        label_name.setFixedWidth(195)
        label_layout.addWidget(label_name)
        self.label_track = LabelTrack(self.view, label_row)
        self.label_track.label_clicked.connect(self._set_selection)
        label_layout.addWidget(self.label_track, 1)
        layout.addWidget(label_row)
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
        spectrogram_on = loaded and self.commands["spectrogram"].isChecked()
        self.waveform.set_spectrogram(self.project.spectrogram() if spectrogram_on else None)
        self.waveform.set_track(track)
        self.label_track.set_labels(track.labels if track else ())
        self.track_name.setText(track.name if track else "No track")
        self.track_info.setText(
            f"{track.duration:.1f} s · {track.sample_count:,} samples" if track else ""
        )
        self.rate_label.setText(f"{track.sample_rate:,} Hz · {track.channels} ch" if track else "No project")
        self.collapse_button.setEnabled(loaded)
        self.close_button.setEnabled(loaded)
        for name in ("export", "select_all", "clear_selection", "play", "loop_play", "pause", "stop",
                     "cursor_left", "cursor_right", "extend_left", "extend_right", "contract_left",
                     "contract_right", "select_to_start", "select_to_end",
                     "skip_start", "skip_end", "mute", "solo", "collapse", "close_track",
                     *EFFECT_NAMES, "zoom_in", "zoom_out", "fit_project"):
            self.commands[name].setEnabled(loaded)
        self.gain_slider.setEnabled(loaded and self._effect_thread is None)
        self.pan_slider.setEnabled(loaded and self._effect_thread is None)
        self.commands["fit_selection"].setEnabled(loaded and self.selection[1] > self.selection[0])
        self.commands["undo"].setEnabled(self.project.can_undo())
        self.commands["redo"].setEnabled(self.project.can_redo())
        self._update_edit_actions()
        if self._effect_thread is not None:
            for name in ("open", "export", "undo", "redo", "play", "loop_play", "pause", "stop",
                         "close_track",
                         "mute", "solo", *EFFECT_NAMES):
                self.commands[name].setEnabled(False)

    def _update_edit_actions(self) -> None:
        loaded = self.project.snapshot() is not None
        busy = self._effect_thread is not None
        has_selection = self.selection[1] > self.selection[0]
        for name in SELECTION_EDITS:
            self.commands[name].setEnabled(loaded and has_selection and not busy)
        self.commands["paste"].setEnabled(loaded and self.project.can_paste() and not busy)
        for name in ("add_label", "remove_labels", "statistics", "spectrogram"):
            self.commands[name].setEnabled(loaded and not busy)
        for kind in GENERATORS:
            self.commands[f"generate_{kind}"].setEnabled(not busy)
        self.commands["preferences"].setEnabled(not busy)

    @Slot(bool)
    def _refresh_checked(self, checked: bool = False) -> None:
        del checked
        self._refresh()

    @Slot(bool)
    def _open(self, checked: bool = False) -> None:
        del checked
        path, _ = QFileDialog.getOpenFileName(self, "Open audio", "", SUPPORTED_AUDIO_FILTER)
        if path:
            self.open_path(path)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if any(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower()
               in SUPPORTED_AUDIO_EXTENSIONS for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = [url.toLocalFile() for url in event.mimeData().urls()
                 if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower()
                 in SUPPORTED_AUDIO_EXTENSIONS]
        if not paths:
            event.ignore()
            return
        self.open_path(paths[0])
        if len(paths) > 1:
            self.statusBar().showMessage(
                f"Opened {Path(paths[0]).name}; ignored {len(paths) - 1} additional files"
            )
        event.acceptProposedAction()

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
        filters = (
            "WAV (*.wav);;FLAC (*.flac);;OGG/Opus (*.ogg *.oga *.opus);;"
            "AIFF (*.aiff *.aif);;AU (*.au *.snd);;CAF (*.caf);;MP3 (*.mp3)"
        )
        path, chosen = QFileDialog.getSaveFileName(
            self, "Export audio", "", filters, EXPORT_FILTERS.get(self.export_format, EXPORT_FILTERS["WAV"]),
        )
        if path:
            if not Path(path).suffix:
                path += "." + (chosen.split("*.")[1].split()[0].rstrip(")") if "*." in chosen else "wav")
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
    def _redo(self, checked: bool = False) -> None:
        del checked
        if self.project.redo():
            self.transport.load("")
            self.statusBar().showMessage("Change redone")
        self._after_structure_change()

    def _after_structure_change(self) -> None:
        """Resync duration, selection and view after the audio length may have changed."""
        track = self.project.snapshot()
        if track is not None and abs(track.duration - self.view.duration) > 1e-9:
            self.view.duration = track.duration
            self._set_selection(*self.selection)
            self._fit_project()
        self._refresh()

    @Slot(bool)
    def _edit(self, checked: bool = False) -> None:
        del checked
        sender = self.sender()
        if not isinstance(sender, QAction) or self._effect_thread is not None:
            return
        name = sender.objectName()
        start, end = self.selection
        self.transport.stop()
        ok, message = self.project.edit(
            name, {"start": start, "end": end, "at": start},
        )
        self.statusBar().showMessage(message)
        if not ok:
            QMessageBox.warning(self, "Edit failed", message)
            return
        if name != "copy":
            self.transport.load("")
        if name in {"cut", "delete", "trim", "paste"}:
            self._set_selection(start, start)
        self._after_structure_change()

    @Slot(bool)
    def _generate(self, checked: bool = False) -> None:
        del checked
        sender = self.sender()
        if not isinstance(sender, QAction):
            return
        kind = sender.objectName().removeprefix("generate_")
        dialog = GenerateDialog(kind, self)
        if dialog.exec() != GenerateDialog.DialogCode.Accepted:
            return
        start, end = self.selection
        parameters = {**dialog.parameters(), "start": start, "end": end, "at": start}
        self.transport.stop()
        ok, message = self.project.edit(f"generate_{kind}", parameters)
        self.statusBar().showMessage(message)
        if not ok:
            QMessageBox.warning(self, "Generate failed", message)
            return
        self.transport.load("")
        self._set_selection(start, start)
        self.view.duration = 0.0  # force a refit; the first generated track has a new length
        self._after_structure_change()

    @Slot(bool)
    def _add_label(self, checked: bool = False) -> None:
        del checked
        text, accepted = QInputDialog.getText(self, "Label", "Label text")
        if accepted and text.strip():
            start, end = self.selection
            if end <= start:
                start = end = self.transport.position()
            self.project.add_label(start, end, text.strip())
            self._refresh()

    @Slot(bool)
    def _remove_labels(self, checked: bool = False) -> None:
        del checked
        start, end = self.selection
        if end <= start:
            start = end = self.transport.position()
        removed = self.project.remove_labels(start, end)
        self.statusBar().showMessage(f"Removed {removed} label(s)")
        self._refresh()

    @Slot(bool)
    def _statistics(self, checked: bool = False) -> None:
        del checked
        start, end = self.selection
        ok, result = self.project.analyze(start, end)
        if not ok or isinstance(result, str):
            QMessageBox.warning(self, "Statistics", str(result))
            return
        scope = "selection" if end > start else "whole track"
        QMessageBox.information(self, f"Statistics ({scope})", format_statistics(result))

    @Slot()
    def _populate_devices(self) -> None:
        self.device_menu.clear()
        group = QActionGroup(self.device_menu)
        group.setExclusive(True)
        entries = [("System default", "")] + [
            (item.description(), device_key(item)) for item in QMediaDevices.audioOutputs()
        ]
        for label, device_id in entries:
            action = self.device_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(device_id == self.output_device)
            group.addAction(action)
            action.triggered.connect(lambda _checked=False, value=device_id: self._set_output_device(value))

    def _set_output_device(self, device_id: str) -> None:
        self.output_device = device_id
        self.settings.setValue("output_device", device_id)
        self.transport.set_output_device(device_id)

    @Slot(bool)
    def _preferences(self, checked: bool = False) -> None:
        del checked
        dialog = PreferencesDialog(self.theme, self.output_device, self.export_format, self)
        if dialog.exec() != PreferencesDialog.DialogCode.Accepted:
            return
        self.export_format = dialog.export_format.currentText()
        self.settings.setValue("export_format", self.export_format)
        self._set_output_device(str(dialog.device.currentData()))
        if dialog.theme.currentText() != self.theme:
            self.commands["light_theme"].setChecked(dialog.theme.currentText() == "light")
            self._toggle_theme(self.commands["light_theme"].isChecked())

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
        self.ruler.set_selection(start, end)
        self.selection_bar.set_selection(start, end)
        self.commands["fit_selection"].setEnabled(end > start and self.project.snapshot() is not None)
        self._update_edit_actions()

    def _set_playhead(self, seconds: float | None) -> None:
        """Show (or with ``None`` hide) the green playback needle on the waveform and ruler."""
        self.waveform.set_playhead(seconds)
        self.ruler.set_playhead(seconds)

    @Slot(float)
    def _ruler_seek(self, at: float) -> None:
        """Ruler click/drag: move the edit cursor, and the playhead too if audio is playing."""
        if self.project.snapshot() is None:
            return
        self._set_selection(at, at)
        if self.transport.is_playing() or self.transport.is_paused():
            self._seek(at)

    def _cursor_time(self) -> float:
        """The edit cursor: the start of the selection (a click is an empty selection)."""
        return self.selection[0]

    def _nudge_step(self) -> float:
        return max(0.001, self.view.seconds_per_pixel * 10)

    @Slot(bool)
    def _nudge(self, checked: bool = False) -> None:
        """Arrow keys: move the cursor, extend (Shift) or contract (Ctrl+Shift) the selection."""
        del checked
        sender = self.sender()
        if not isinstance(sender, QAction) or self.project.snapshot() is None:
            return
        kind = sender.objectName()
        step = self._nudge_step()
        start, end = self.selection
        has_selection = end > start
        cursor = self._cursor_time()
        if kind in {"cursor_left", "cursor_right"}:
            left = kind == "cursor_left"
            # With a selection the cursor collapses to the edge in that direction.
            target = (start if left else end) if has_selection else cursor + (-step if left else step)
            self._move_cursor(target)
            return
        if not has_selection:
            start = end = cursor
        if kind == "extend_left":
            start -= step
        elif kind == "extend_right":
            end += step
        elif kind == "contract_left":  # pull the right edge in
            end = max(start, end - step)
        elif kind == "contract_right":  # push the left edge in
            start = min(end, start + step)
        self._set_selection(start, end)

    def _move_cursor(self, at: float) -> None:
        at = min(self.view.duration, max(0.0, at))
        self._set_selection(at, at)

    def _skip(self, at: float) -> None:
        """Skip to Start/End: move the cursor and, during playback, the playhead as well."""
        self._move_cursor(at)
        if self.transport.is_playing() or self.transport.is_paused():
            self._seek(self.selection[0])

    @Slot(bool)
    def _select_to_start(self, checked: bool = False) -> None:
        del checked
        start, end = self.selection
        self._set_selection(0.0, end if end > start else self._cursor_time())

    @Slot(bool)
    def _select_to_end(self, checked: bool = False) -> None:
        del checked
        start, end = self.selection
        self._set_selection(start if end > start else self._cursor_time(), self.view.duration)

    @Slot(float)
    def _seek(self, at: float) -> None:
        self.transport.seek(at)
        self._follow_playhead(self.transport.position())
        self._set_playhead(self.transport.position())

    def _follow_playhead(self, position: float) -> None:
        """Keep the moving playhead visible while the timeline is zoomed in."""
        width = self.waveform.width()
        if width <= 0 or self.view.seconds_per_pixel <= 0:
            return
        viewport_seconds = width * self.view.seconds_per_pixel
        left = self.view.offset
        right = left + viewport_seconds
        # Keep a 15% margin so the view does not jump on every pixel.
        margin = viewport_seconds * 0.15
        if left + margin <= position <= right - margin:
            return
        max_offset = max(0.0, self.view.duration - viewport_seconds)
        self.view.offset = max(0.0, min(max_offset, position - viewport_seconds * 0.5))
        self._sync_view()

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
        self.label_track.set_theme(self.theme)
        self.meter.set_theme(self.theme)
        self.settings.setValue("theme", self.theme)

    @Slot(bool)
    def _play(self, checked: bool = False) -> None:
        del checked
        if self.transport.is_playing():
            self.statusBar().showMessage("Already playing")
            return
        try:
            selection_start, selection_end = self.selection
            has_selection = selection_end > selection_start
            # A paused transport resumes where it paused. A fresh Play starts at the edit
            # cursor / selection start and, without a selection, runs to the end of the track.
            position = self.transport.position() if self.transport.is_paused() else selection_start
            self.transport.load(self.project.preview_path())
            self.transport.seek(position)
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.warning(self, "Playback failed", str(exc))
            return
        self.transport.play()
        self._user_stopped = False
        self.statusBar().showMessage(
            "Playing selection" if has_selection else "Playback requested"
        )
        self._follow_playhead(self.transport.position())
        self._set_playhead(self.transport.position())

    @Slot(bool)
    def _play_toggle(self, checked: bool = False) -> None:
        """Space: stop if playing, otherwise play (Audacity behaviour)."""
        del checked
        if self.transport.is_playing():
            self._stop()
        else:
            self._loop_once = False
            self._play()

    @Slot(bool)
    def _loop_play(self, checked: bool = False) -> None:
        """Shift+Space: play looped for this playback only."""
        del checked
        if self.transport.is_playing():
            self._stop()
            return
        self._loop_once = True
        self._play()

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
        self._user_stopped = True
        self._loop_once = False
        self.transport.stop()
        self._set_playhead(None)  # the edit cursor stays exactly where it was

    @Slot(bool)
    def _skip_start(self, checked: bool = False) -> None:
        del checked
        self._skip(0.0)

    @Slot(bool)
    def _skip_end(self, checked: bool = False) -> None:
        del checked
        self._skip(self.view.duration)

    @Slot()
    def _tick(self) -> None:
        self.transport.tick(0.05, self.view.duration)
        position = self.transport.position()
        selection_start, selection_end = self.selection
        playing = self.transport.is_playing()
        looping = self.commands["loop"].isChecked() or self._loop_once
        if playing and selection_end > selection_start and position >= selection_end:
            if looping:
                self.transport.seek(selection_start)
                position = selection_start
                self._follow_playhead(position)
                self._set_playhead(position)
            else:
                self.transport.stop()
                self.statusBar().showMessage("Selection playback finished")
                playing = False
        elif playing:
            self._follow_playhead(position)
            self._set_playhead(position)
        elif (self._was_playing and looping and not self._user_stopped
              and not self.transport.is_paused() and self.view.duration > 0):
            # Playback ran off the end of the track: restart from the edit cursor.
            self.transport.seek(selection_start)
            self.transport.play()
            self._set_playhead(selection_start)
            playing = True
        self._was_playing = playing
        if not playing and not self.transport.is_paused():
            self._set_playhead(None)
        self.meter.set_levels(self.project.level_at(position) if playing else ())

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
        elif name in EFFECT_SPECS and EFFECT_SPECS[name].params:
            dialog = EffectDialog(EFFECT_SPECS[name], self)
            if dialog.exec() != EffectDialog.DialogCode.Accepted:
                return
            parameters.update(dialog.parameters())
        start, end = self.selection
        if end > start:
            parameters["start"] = start
            parameters["end"] = end
        if name == "ai_declip":
            QMessageBox.information(self, "AI Declip", "A reconstructed waveform would be an estimate.")
        self._user_stopped = True
        self.transport.stop()
        self.progress.show()
        self.statusBar().showMessage(
            f"Applying {name} to selection…" if "start" in parameters else f"Applying {name}…"
        )
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
