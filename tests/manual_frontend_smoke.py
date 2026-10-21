"""Offline Qt smoke check: QT_QPA_PLATFORM=offscreen python tests/manual_frontend_smoke.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QToolBar

from audamix_frontend.window import MainWindow


def main() -> None:
    app = QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        audio = Path(directory) / "voice.wav"
        audio.write_bytes(b"stub")
        settings_path = str(Path(directory) / "settings.ini")
        first = MainWindow(settings=QSettings(settings_path, QSettings.Format.IniFormat))
        first.show()
        assert not first.actions["undo"].isEnabled()
        assert not first.actions["export"].isEnabled()
        first.open_path(str(audio))
        assert first.actions["export"].isEnabled()
        first._set_selection(5.0, 10.0)
        first.actions["fit_selection"].trigger()
        assert abs(first.view.offset - 5.0) < 0.01
        first.actions["zoom_in"].trigger()
        assert first.view.seconds_per_pixel < 0.01
        first.actions["classical_denoise"].trigger()
        loop = QEventLoop()
        QTimer.singleShot(250, loop.quit)
        loop.exec()
        assert first.actions["undo"].isEnabled()
        first.actions["undo"].trigger()
        assert not first.actions["undo"].isEnabled()
        first.actions["light_theme"].trigger()
        first.resize(980, 610)
        transport_bar = first.findChild(QToolBar, "toolbar_transport")
        assert transport_bar is not None
        first.addToolBarBreak()
        first.close()
        second = MainWindow(settings=QSettings(settings_path, QSettings.Format.IniFormat))
        second.show()
        assert second.theme == "light"
        assert second.size().width() == 980 and second.size().height() == 610
        shortcuts = [action.shortcut().toString() for action in second.actions.values()
                     if not action.shortcut().isEmpty()]
        assert len(shortcuts) == len(set(shortcuts))
        second.close()
    print("Frontend offscreen smoke passed")


if __name__ == "__main__":
    main()
