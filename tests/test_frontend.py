"""Qt smoke tests; run with pytest-qt and QT_QPA_PLATFORM=offscreen."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from audamix_frontend.model import SUPPORTED_AUDIO_FILTER, StubProject, StubTransport
from audamix_frontend.real_backend import AudioProject
from audamix_frontend.widgets import ViewState
from audamix_frontend.window import MainWindow


def make_audio(path: Path) -> None:
    rate = 8000
    times = np.arange(rate * 20) / rate
    sf.write(path, 0.25 * np.sin(2 * np.pi * 440 * times), rate)


def test_window_and_action_state(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert not window.commands["undo"].isEnabled()
    assert not window.commands["export"].isEnabled()
    path = tmp_path / "voice.wav"
    make_audio(path)
    window.open_path(str(path))
    assert window.commands["export"].isEnabled()
    assert window.track_name.text() == "voice.wav"
    assert not window.commands["fit_selection"].isEnabled()
    window._set_selection(1.0, 3.0)
    assert window.commands["fit_selection"].isEnabled()
    window.project.apply_effect("gain", {"dB": 3.0})
    window._refresh()
    assert window.commands["undo"].isEnabled()
    window.commands["undo"].trigger()
    assert not window.commands["undo"].isEnabled()


def test_window_accepts_audio_drop_and_exposes_all_formats(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.acceptDrops()
    for extension in (".wav", ".flac", ".ogg", ".opus", ".aiff", ".au", ".caf", ".mp3"):
        assert f"*{extension}" in SUPPORTED_AUDIO_FILTER


def test_selection_and_zoom_math(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    path = tmp_path / "voice.wav"
    make_audio(path)
    window.open_path(str(path))
    window._set_selection(5.0, 10.0)
    window.commands["fit_selection"].trigger()
    assert abs(window.view.offset - 5.0) < 0.01
    assert abs(window.view.time_at(window.waveform.width()) - 10.0) < 0.01
    old_scale = window.view.seconds_per_pixel
    window.commands["zoom_in"].trigger()
    assert window.view.seconds_per_pixel < old_scale


def test_settings_round_trip(qtbot: QtBot, tmp_path: Path) -> None:
    path = str(tmp_path / "settings.ini")
    first = MainWindow(settings=QSettings(path, QSettings.Format.IniFormat))
    qtbot.addWidget(first)
    first.resize(980, 610)
    first.commands["light_theme"].trigger()
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


def test_real_audio_edit_undo_and_export(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    target = tmp_path / "target.wav"
    make_audio(source)
    project = AudioProject()
    ok, _ = project.open_file(str(source))
    assert ok
    before = project.snapshot()
    assert before is not None
    assert before.duration == 20
    assert before.channels == 1
    assert len(before.peaks) > 100
    ok, _ = project.apply_effect("gain", {"dB": -6.0})
    assert ok and project.can_undo()
    ok, _ = project.export_file(str(target))
    assert ok and target.exists()
    original, _ = sf.read(source)
    changed, _ = sf.read(target)
    assert np.max(np.abs(changed)) < np.max(np.abs(original)) * 0.6
    assert project.undo()
    assert not project.can_undo()
    assert Path(project.preview_path()).is_file()
    project.close()


def test_pause_resumes_transport(qtbot: QtBot, tmp_path: Path) -> None:
    transport = StubTransport()
    window = MainWindow(
        project=StubProject(), transport=transport,
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
    )
    qtbot.addWidget(window)
    path = tmp_path / "sample.wav"
    path.write_bytes(b"stub")
    window.open_path(str(path))
    window.commands["play"].trigger()
    assert transport.is_playing()
    window.commands["pause"].trigger()
    assert transport.is_paused()
    window.commands["pause"].trigger()
    assert transport.is_playing()


def test_playback_starts_and_stops_at_selection(qtbot: QtBot, tmp_path: Path) -> None:
    transport = StubTransport()
    window = MainWindow(
        project=StubProject(), transport=transport,
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
    )
    qtbot.addWidget(window)
    path = tmp_path / "sample.wav"
    path.write_bytes(b"stub")
    window.open_path(str(path))
    window._set_selection(10.0, 10.2)

    window.commands["play"].trigger()
    assert transport.is_playing()
    assert transport.position() == 10.0

    for _ in range(5):
        window._tick()
    assert not transport.is_playing()
    assert transport.position() == 10.2


def test_playhead_auto_scrolls_when_zoomed_in(qtbot: QtBot, tmp_path: Path) -> None:
    transport = StubTransport()
    window = MainWindow(
        project=StubProject(), transport=transport,
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
    )
    qtbot.addWidget(window)
    path = tmp_path / "sample.wav"
    path.write_bytes(b"stub")
    window.open_path(str(path))
    window.view.seconds_per_pixel = 0.01
    window.view.offset = 0.0
    window._sync_view()
    window._follow_playhead(50.0)

    viewport_seconds = window.waveform.width() * window.view.seconds_per_pixel
    assert window.view.offset > 0.0
    assert window.view.offset <= 50.0 <= window.view.offset + viewport_seconds
