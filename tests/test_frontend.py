"""Qt smoke tests; run with pytest-qt and QT_QPA_PLATFORM=offscreen."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from pytestqt.qtbot import QtBot

from audamix.dsp import effects
from audamix_frontend.dialogs import EffectDialog
from audamix_frontend.model import SUPPORTED_AUDIO_FILTER, StubProject, StubTransport
from audamix_frontend.real_backend import AudioProject, AudioTransport
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
    assert window.waveform.playhead is None  # the green playhead disappears when playback ends
    assert window.selection == (10.0, 10.2)  # the edit cursor / selection is untouched


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


def _window(qtbot: QtBot, tmp_path: Path, name: str = "voice.wav") -> MainWindow:
    window = MainWindow(settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    path = tmp_path / name
    make_audio(path)
    window.open_path(str(path))
    return window


def test_cut_paste_trim_redo_and_clipboard(qtbot: QtBot, tmp_path: Path) -> None:
    window = _window(qtbot, tmp_path)
    assert not window.commands["cut"].isEnabled()  # no selection yet
    window._set_selection(2.0, 6.0)
    assert window.commands["cut"].isEnabled() and not window.commands["paste"].isEnabled()
    window.commands["copy"].trigger()
    assert window.commands["paste"].isEnabled()
    window.commands["cut"].trigger()
    snapshot = window.project.snapshot()
    assert snapshot is not None and abs(snapshot.duration - 16.0) < 1e-6
    assert window.selection == (2.0, 2.0)
    window.commands["paste"].trigger()
    snapshot = window.project.snapshot()
    assert snapshot is not None and abs(snapshot.duration - 20.0) < 1e-6
    window.commands["undo"].trigger()
    assert window.commands["redo"].isEnabled()
    window.commands["redo"].trigger()
    snapshot = window.project.snapshot()
    assert snapshot is not None and abs(snapshot.duration - 20.0) < 1e-6
    window._set_selection(1.0, 3.0)
    window.commands["trim"].trigger()
    snapshot = window.project.snapshot()
    assert snapshot is not None and abs(snapshot.duration - 2.0) < 1e-6 and window.view.duration == 2.0


def test_new_edit_clears_redo_and_whole_track_delete_is_refused() -> None:
    project = AudioProject()
    assert project.edit("cut", {"start": 0, "end": 1})[0] is False  # nothing open
    ok, _ = project.edit("generate_tone", {"duration": 1.0, "frequency": 440.0, "amplitude": 0.5})
    assert ok and not project.can_undo()
    project.edit("generate_silence", {"duration": 1.0, "at": 0.5})
    assert project.can_undo()
    project.undo()
    assert project.can_redo()
    project.edit("generate_noise", {"duration": 0.5, "at": 0.0})
    assert not project.can_redo()
    ok, message = project.edit("delete", {"start": 0.0, "end": 100.0})
    assert not ok and "whole track" in message
    ok, message = project.edit("generate_tone", {"duration": -1.0})
    assert not ok and project.snapshot() is not None


def test_effect_applies_only_to_selection(tmp_path: Path) -> None:
    path = tmp_path / "voice.wav"
    make_audio(path)
    project = AudioProject()
    assert project.open_file(str(path))[0]
    ok, message = project.apply_effect("gain", {"dB": -20.0, "start": 5.0, "end": 10.0})
    assert ok and "selection" in message
    out = tmp_path / "out.wav"
    assert project.export_file(str(out))[0]
    data, rate = sf.read(out)
    loud = np.max(np.abs(data[: 5 * rate]))
    quiet = np.max(np.abs(data[5 * rate: 10 * rate]))
    assert abs(loud - 0.25) < 0.01 and abs(quiet - 0.025) < 0.005
    assert abs(np.max(np.abs(data[10 * rate:])) - 0.25) < 0.01


def test_silence_fade_and_labels_follow_edits(tmp_path: Path) -> None:
    path = tmp_path / "voice.wav"
    make_audio(path)
    project = AudioProject()
    project.open_file(str(path))
    project.add_label(8.0, 8.0, "late")
    project.add_label(1.0, 3.0, "early")
    project.edit("delete", {"start": 4.0, "end": 6.0})
    snapshot = project.snapshot()
    assert snapshot is not None
    assert [(item.text, item.start) for item in snapshot.labels] == [("early", 1.0), ("late", 6.0)]
    project.edit("delete", {"start": 0.5, "end": 2.0})  # clips the front of "early"
    snapshot = project.snapshot()
    assert snapshot is not None and [item.text for item in snapshot.labels] == ["early", "late"]
    assert (snapshot.labels[0].start, snapshot.labels[0].end) == (0.5, 1.5)
    project.edit("delete", {"start": 0.0, "end": 4.0})  # swallows "early" entirely
    snapshot = project.snapshot()
    assert snapshot is not None and [item.text for item in snapshot.labels] == ["late"]
    project.undo()
    assert project.remove_labels(0.0, 1.0) == 1
    project.undo()
    assert project.edit("silence", {"start": 1.0, "end": 2.0})[0]
    assert project.edit("fade_out", {"start": 3.0, "end": 4.0})[0]
    assert not project.edit("fade_in", {"start": 3.0, "end": 3.0})[0]
    ok, stats = project.analyze(1.0, 2.0)
    assert ok and isinstance(stats, dict) and stats["peak"] == 0.0


def test_paste_replaces_selection_and_converts_format(tmp_path: Path) -> None:
    path = tmp_path / "voice.wav"
    make_audio(path)
    project = AudioProject()
    project.open_file(str(path))
    assert not project.edit("paste", {})[0]
    project.edit("copy", {"start": 0.0, "end": 1.0})
    ok, _ = project.edit("paste", {"start": 10.0, "end": 12.0})
    snapshot = project.snapshot()
    assert ok and snapshot is not None and abs(snapshot.duration - 19.0) < 1e-6


def test_spectrogram_levels_and_mp3_export(qtbot: QtBot, tmp_path: Path) -> None:
    window = _window(qtbot, tmp_path)
    spectrogram_action = window.commands["spectrogram"]
    spectrogram_action.trigger()
    assert spectrogram_action.isChecked() and window.waveform._spectrogram is not None
    spectrogram_action.trigger()
    assert window.waveform._spectrogram is None
    levels = window.project.level_at(1.0)
    assert len(levels) == 1 and 0.2 < levels[0] <= 0.25
    window.project.set_controls(True, False, 1.0, 0.0)
    assert window.project.level_at(1.0) == (0.0,)
    window.project.set_controls(False, False, 1.0, 0.0)
    ok, message = window.project.export_file(str(tmp_path / "out.mp3"))
    assert ok, message
    assert sf.info(tmp_path / "out.mp3").format == "MP3"


def test_loop_restarts_selection_and_meter_decays(qtbot: QtBot, tmp_path: Path) -> None:
    transport = StubTransport()
    window = MainWindow(project=AudioProject(), transport=transport,
                        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    path = tmp_path / "voice.wav"
    make_audio(path)
    window.open_path(str(path))
    window._set_selection(1.0, 2.0)
    transport.seek(1.9)
    transport.play()
    window.commands["loop"].setChecked(True)
    for _ in range(4):
        window._tick()
    assert transport.is_playing() and 1.0 <= transport.position() < 2.0
    assert max(window.meter.levels) > 0.0
    window.commands["loop"].setChecked(False)
    transport.seek(1.99)
    window._tick()
    window._tick()
    assert not transport.is_playing()
    for _ in range(40):
        window._tick()
    assert max(window.meter.levels) < 0.01


def test_labels_generate_and_preferences_state(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    assert window.commands["generate_tone"].isEnabled() and not window.commands["add_label"].isEnabled()
    ok, _ = window.project.edit("generate_tone", {"duration": 2.0, "frequency": 440.0, "amplitude": 0.5})
    assert ok
    window.project.add_label(0.5, 1.0, "hit")
    window._after_structure_change()
    assert window.view.duration == 2.0
    assert [item.text for item in window.label_track.labels] == ["hit"]
    window._set_output_device("")
    assert window.settings.value("output_device") == ""
    assert window.commands["preferences"].isEnabled()


def _x(window: MainWindow, seconds: float) -> int:
    return round(window.view.x_at(seconds)) + 34


def test_selection_behaves_like_a_needle(qtbot: QtBot, tmp_path: Path) -> None:
    window = _window(qtbot, tmp_path)
    window.resize(1000, 600)
    window.show()
    wave = window.waveform
    y = wave.height() // 2
    # Click drops the needle and clears any selection.
    QTest.mouseClick(wave, Qt.MouseButton.LeftButton, pos=QPoint(_x(window, 4.0), y))
    assert window.selection == (4.0, 4.0) or abs(window.selection[0] - 4.0) < 0.05
    assert window.waveform.playhead is None  # nothing is playing, so there is no playhead
    # Dragging selects and the needle rests at the selection start.
    QTest.mousePress(wave, Qt.MouseButton.LeftButton, pos=QPoint(_x(window, 5.0), y))
    QTest.mouseMove(wave, QPoint(_x(window, 9.0), y))
    QTest.mouseRelease(wave, Qt.MouseButton.LeftButton, pos=QPoint(_x(window, 9.0), y))
    start, end = window.selection
    assert abs(start - 5.0) < 0.05 and abs(end - 9.0) < 0.05
    assert wave.playhead is None
    # Dragging backwards works too.
    QTest.mousePress(wave, Qt.MouseButton.LeftButton, pos=QPoint(_x(window, 12.0), y))
    QTest.mouseMove(wave, QPoint(_x(window, 10.0), y))
    QTest.mouseRelease(wave, Qt.MouseButton.LeftButton, pos=QPoint(_x(window, 10.0), y))
    assert abs(window.selection[0] - 10.0) < 0.05 and abs(window.selection[1] - 12.0) < 0.05
    # Grab the right edge and pull it out; the left edge must not move.
    left = window.selection[0]
    QTest.mousePress(wave, Qt.MouseButton.LeftButton, pos=QPoint(_x(window, 12.0) + 2, y))
    QTest.mouseMove(wave, QPoint(_x(window, 15.0), y))
    QTest.mouseRelease(wave, Qt.MouseButton.LeftButton, pos=QPoint(_x(window, 15.0), y))
    assert window.selection[0] == left and abs(window.selection[1] - 15.0) < 0.05
    # Shift-click extends toward the click from the far edge.
    QTest.mouseClick(wave, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier,
                     QPoint(_x(window, 18.0), y))
    assert window.selection[0] == left and abs(window.selection[1] - 18.0) < 0.05
    QTest.mouseClick(wave, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier,
                     QPoint(_x(window, 2.0), y))
    assert abs(window.selection[0] - 2.0) < 0.05 and abs(window.selection[1] - 18.0) < 0.05


def test_ruler_click_moves_needle_and_lines_up_with_waveform(qtbot: QtBot, tmp_path: Path) -> None:
    window = _window(qtbot, tmp_path)
    window.resize(1000, 600)
    window.show()
    window._set_selection(3.0, 8.0)
    QTest.mouseClick(window.ruler, Qt.MouseButton.LeftButton, pos=QPoint(_x(window, 6.0), 10))
    assert abs(window.selection[0] - 6.0) < 0.05 and window.selection[0] == window.selection[1]
    assert window.waveform.playhead is None  # stopped: only the edit cursor moves


def _audacity_window(qtbot: QtBot, tmp_path: Path) -> tuple[MainWindow, StubTransport]:
    transport = StubTransport()
    window = MainWindow(project=AudioProject(), transport=transport,
                        settings=QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    path = tmp_path / "voice.wav"
    make_audio(path)
    window.open_path(str(path))
    return window, transport


def test_two_needles_cursor_stays_while_playhead_moves(qtbot: QtBot, tmp_path: Path) -> None:
    window, transport = _audacity_window(qtbot, tmp_path)
    window._move_cursor(4.0)
    assert window.waveform.playhead is None
    window.commands["play"].trigger()  # Space starts at the edit cursor
    assert transport.is_playing() and transport.position() == 4.0
    for _ in range(10):
        window._tick()
    playhead = window.waveform.playhead
    assert playhead is not None and playhead > 4.0 and window.ruler.playhead == playhead
    assert window.selection == (4.0, 4.0)  # the edit cursor did not follow the playhead
    # Clicking the waveform during playback moves only the edit cursor.
    window.resize(1000, 600)
    window.show()
    QTest.mouseClick(window.waveform, Qt.MouseButton.LeftButton, pos=QPoint(_x(window, 12.0), 50))
    assert abs(window.selection[0] - 12.0) < 0.05
    assert transport.position() < 12.0 and transport.is_playing()
    window.commands["play"].trigger()  # Space again stops
    assert not transport.is_playing()
    assert window.waveform.playhead is None and window.ruler.playhead is None
    assert abs(window.selection[0] - 12.0) < 0.05  # cursor unchanged by Stop
    # Pause keeps the playhead visible; resuming continues from it.
    window.commands["play"].trigger()
    window.commands["pause"].trigger()
    window._tick()
    assert transport.is_paused() and window.waveform.playhead is not None


def test_ruler_click_seeks_playback_only_while_playing(qtbot: QtBot, tmp_path: Path) -> None:
    window, transport = _audacity_window(qtbot, tmp_path)
    window.resize(1000, 600)
    window.show()
    QTest.mouseClick(window.ruler, Qt.MouseButton.LeftButton, pos=QPoint(_x(window, 9.0), 10))
    assert abs(window.selection[0] - 9.0) < 0.05 and not transport.is_playing()
    window.commands["play"].trigger()
    QTest.mouseClick(window.ruler, Qt.MouseButton.LeftButton, pos=QPoint(_x(window, 15.0), 10))
    assert abs(transport.position() - 15.0) < 0.05 and abs(window.selection[0] - 15.0) < 0.05
    assert transport.is_playing()


def test_loop_play_is_one_shot(qtbot: QtBot, tmp_path: Path) -> None:
    window, transport = _audacity_window(qtbot, tmp_path)
    window._set_selection(1.0, 1.2)
    window.commands["loop_play"].trigger()
    for _ in range(12):
        window._tick()
    assert transport.is_playing() and 1.0 <= transport.position() < 1.2
    window.commands["loop_play"].trigger()  # toggles off
    window.commands["play"].trigger()
    for _ in range(12):
        window._tick()
    assert not transport.is_playing()  # normal play does not loop


def test_cursor_keys_and_selection_extension(qtbot: QtBot, tmp_path: Path) -> None:
    window, _ = _audacity_window(qtbot, tmp_path)
    window.resize(1000, 600)
    step = window._nudge_step()
    window._move_cursor(5.0)
    window.commands["cursor_right"].trigger()
    assert abs(window.selection[0] - (5.0 + step)) < 1e-6 and window.selection[0] == window.selection[1]
    window._move_cursor(5.0)
    window.commands["extend_right"].trigger()
    assert window.selection[0] == 5.0 and abs(window.selection[1] - (5.0 + step)) < 1e-6
    window.commands["extend_left"].trigger()
    assert abs(window.selection[0] - (5.0 - step)) < 1e-6
    window.commands["contract_left"].trigger()  # pulls the right edge in
    assert abs(window.selection[1] - 5.0) < 1e-6
    window.commands["cursor_left"].trigger()  # collapses to the start edge
    assert abs(window.selection[0] - (5.0 - step)) < 1e-6 and window.selection[0] == window.selection[1]
    window._move_cursor(8.0)
    window.commands["select_to_start"].trigger()
    assert window.selection == (0.0, 8.0)
    window.commands["select_to_end"].trigger()
    assert window.selection == (0.0, window.view.duration)


def test_double_click_selects_all_and_home_end_move_cursor(qtbot: QtBot, tmp_path: Path) -> None:
    window, _ = _audacity_window(qtbot, tmp_path)
    window.resize(1000, 600)
    window.show()
    QTest.mouseDClick(window.waveform, Qt.MouseButton.LeftButton, pos=QPoint(_x(window, 5.0), 50))
    assert window.selection == (0.0, window.view.duration)
    window.commands["skip_end"].trigger()
    assert window.selection == (window.view.duration, window.view.duration)
    window.commands["skip_start"].trigger()
    assert window.selection == (0.0, 0.0) and window.waveform.playhead is None


def test_first_play_after_loading_starts_at_the_requested_position(qtbot: QtBot, tmp_path: Path) -> None:
    """Regression: a seek issued before the media finished loading used to be lost."""
    path = tmp_path / "voice.wav"
    make_audio(path)
    host = MainWindow(settings=QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(host)
    transport = AudioTransport(host)
    transport.load(str(path))
    transport.seek(10.0)
    transport.play()
    assert transport.is_playing()  # reported as playing even while the media is still loading
    try:
        qtbot.waitUntil(lambda: transport.player is not None and transport.player.isPlaying(), timeout=5000)
    except Exception:
        transport.stop()
        pytest.skip("Qt Multimedia backend cannot play audio in this environment")
    qtbot.wait(150)
    assert transport.position() >= 9.9, transport.position()
    transport.stop()
    assert not transport.is_playing()


def test_delete_paste_and_silence_do_not_click(tmp_path: Path) -> None:
    path = tmp_path / "voice.wav"
    make_audio(path)  # 0.25 * sin(2π·440 t) at 8 kHz; no sample step exceeds ~0.087
    project = AudioProject()
    project.open_file(str(path))
    limit = 0.0865 * 1.1

    def worst_step() -> float:
        out = tmp_path / "check.wav"
        assert project.export_file(str(out))[0]
        data, _ = sf.read(out)
        return float(np.max(np.abs(np.diff(data))))

    assert project.edit("delete", {"start": 5.0, "end": 5.000625 + 1.3})[0]
    assert worst_step() < limit
    assert project.edit("silence", {"start": 2.0001, "end": 3.0003})[0]
    assert worst_step() < limit
    project.edit("copy", {"start": 6.0, "end": 6.0371})
    assert project.edit("paste", {"start": 9.0, "end": 9.0})[0]
    assert worst_step() < limit


def test_new_effects_are_menu_items_gated_on_a_loaded_track(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(settings=QSettings(str(tmp_path / "e.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    effects_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "Effects")
    submenus = {a.text(): a.menu() for a in effects_menu.actions() if a.menu() is not None}
    assert set(submenus) == {spec.group for spec in effects.SPECS.values()}
    in_menu = {a.objectName() for menu in submenus.values() for a in menu.actions()}
    assert in_menu == set(effects.SPECS)
    assert all(not window.commands[name].isEnabled() for name in effects.SPECS)  # nothing loaded
    path = tmp_path / "voice.wav"
    make_audio(path)
    window.open_path(str(path))
    assert all(window.commands[name].isEnabled() for name in effects.SPECS)


def test_effect_dialog_defaults_match_the_spec(qtbot: QtBot) -> None:
    for name, spec in effects.SPECS.items():
        if not spec.params:
            continue
        dialog = EffectDialog(spec)
        qtbot.addWidget(dialog)
        assert dialog.parameters() == {p.key: float(p.default) for p in spec.params}, name


def test_effects_run_through_the_project_on_a_selection_and_undo(tmp_path: Path) -> None:
    path = tmp_path / "voice.wav"
    make_audio(path)  # 440 Hz at 0.25
    project = AudioProject()
    project.open_file(str(path))
    ok, message = project.apply_effect("invert", {"start": 2.0, "end": 4.0})
    assert ok and "selection" in message
    ok, _ = project.apply_effect("normalize", {"target_db": -6.0})
    assert ok
    out = tmp_path / "out.wav"
    assert project.export_file(str(out))[0]
    data, rate = sf.read(out)
    assert abs(np.max(np.abs(data)) - 0.5) < 0.01  # -6 dBFS
    assert data[int(3.0 * rate) : int(3.0 * rate) + 5].tolist() != [0.0] * 5
    ok, message = project.apply_effect("compressor", {"ratio": 0.2})  # out of range
    assert not ok and "Ratio" in message
    assert project.undo() and project.undo() and not project.can_undo()
    ok, message = project.apply_effect("limiter", {"limit_db": -12.0})
    assert ok
    project.export_file(str(tmp_path / "lim.wav"))
    limited, _ = sf.read(tmp_path / "lim.wav")
    assert np.max(np.abs(limited)) <= 10 ** (-12 / 20) + 1e-3


def test_effect_action_runs_in_the_background_thread(qtbot: QtBot, tmp_path: Path) -> None:
    window = _window(qtbot, tmp_path)
    window._set_selection(1.0, 2.0)
    window.commands["reverse"].trigger()  # no parameters, so no dialog
    qtbot.waitUntil(lambda: window.commands["undo"].isEnabled(), timeout=5000)
    assert "reverse" in window.statusBar().currentMessage().lower()
