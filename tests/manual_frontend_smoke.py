"""Offline Qt smoke check: QT_QPA_PLATFORM=offscreen python tests/manual_frontend_smoke.py."""

from __future__ import annotations

import tempfile
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from PySide6.QtCore import QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QToolBar

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audamix_frontend.window import MainWindow


def main() -> None:
    app = QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        audio = Path(directory) / "voice.wav"
        rate = 8000
        times = np.arange(rate * 20) / rate
        sf.write(audio, 0.25 * np.sin(2 * np.pi * 440 * times), rate)
        settings_path = str(Path(directory) / "settings.ini")
        first = MainWindow(settings=QSettings(settings_path, QSettings.Format.IniFormat))
        first.show()
        assert not first.commands["undo"].isEnabled()
        assert not first.commands["export"].isEnabled()
        first.open_path(str(audio))
        assert first.commands["export"].isEnabled()
        first._set_selection(5.0, 10.0)
        first.commands["fit_selection"].trigger()
        assert abs(first.view.offset - 5.0) < 0.01
        first.commands["zoom_in"].trigger()
        assert first.view.seconds_per_pixel < 0.01
        first.commands["classical_denoise"].trigger()
        loop = QEventLoop()
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
        assert first.commands["undo"].isEnabled()
        first.commands["undo"].trigger()
        assert not first.commands["undo"].isEnabled()
        first.commands["light_theme"].trigger()
        first.resize(980, 610)
        transport_bar = first.findChild(QToolBar, "toolbar_transport")
        assert transport_bar is not None
        first.addToolBarBreak()
        first.close()
        second = MainWindow(settings=QSettings(settings_path, QSettings.Format.IniFormat))
        second.show()
        assert second.theme == "light"
        assert second.size().width() == 980 and second.size().height() == 610
        shortcuts = [action.shortcut().toString() for action in second.commands.values()
                     if not action.shortcut().isEmpty()]
        assert len(shortcuts) == len(set(shortcuts))
        second.close()
    print("Frontend offscreen smoke passed")


if __name__ == "__main__":
    main()
