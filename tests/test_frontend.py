"""Qt smoke tests; run with pytest-qt and QT_QPA_PLATFORM=offscreen."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from audamix_frontend.window import MainWindow
from audamix_frontend.widgets import ViewState


def test_window_and_action_state(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert not window.actions["undo"].isEnabled()
    assert not window.actions["export"].isEnabled()
    path = tmp_path / "voice.wav"
    path.write_bytes(b"stub")
    window.open_path(str(path))
    assert window.actions["export"].isEnabled()
    assert window.track_name.text() == "voice.wav"
    assert not window.actions["fit_selection"].isEnabled()
    window._set_selection(1.0, 3.0)
    assert window.actions["fit_selection"].isEnabled()
    window.project.apply_effect("gain", {"dB": 3.0})
    window._refresh()
    assert window.actions["undo"].isEnabled()
    window.actions["undo"].trigger()
    assert not window.actions["undo"].isEnabled()


def test_selection_and_zoom_math(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    path = tmp_path / "voice.wav"
    path.write_bytes(b"stub")
    window.open_path(str(path))
    window._set_selection(5.0, 10.0)
    window.actions["fit_selection"].trigger()
    assert abs(window.view.offset - 5.0) < 0.01
    assert abs(window.view.time_at(window.waveform.width()) - 10.0) < 0.01
    old_scale = window.view.seconds_per_pixel
    window.actions["zoom_in"].trigger()
    assert window.view.seconds_per_pixel < old_scale


def test_settings_round_trip(qtbot: QtBot, tmp_path: Path) -> None:
    path = str(tmp_path / "settings.ini")
    first = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(first)
    first.resize(980, 610)
    first.actions["light_theme"].trigger()
    first.close()
    second = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(second)
    assert second.theme == "light"
    assert second.size() == first.size()
    second.close()


def test_mapping_clamps_zoom_and_cursor() -> None:
    view = ViewState()
    view.duration = 10.0
    assert view.time_at(-50.0) == 0.0
    assert view.time_at(10000.0) == 10.0
    view.zoom(2.0, 50.0, 100)
    assert view.seconds_per_pixel == 0.075
