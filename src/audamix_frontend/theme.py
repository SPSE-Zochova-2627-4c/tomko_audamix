"""All frontend colors and palette construction live here."""

from __future__ import annotations

from importlib.resources import files

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

COLORS: dict[str, dict[str, str]] = {
    "dark": {
        "background": "#202329", "panel": "#2d323a", "control": "#39404a",
        "border": "#505a68", "text": "#e8edf4", "muted": "#8994a4",
        "accent": "#5a9de6", "accent_soft": "#344f70", "wave": "#4484d0",
        "rms": "#8dbbef", "selection": "#3b5e83", "playhead": "#f2d16c",
        "center": "#6b7582", "ruler": "#252a32",
    },
    "light": {
        "background": "#f0f2f5", "panel": "#dce1e7", "control": "#ffffff",
        "border": "#a7b0bd", "text": "#182432", "muted": "#5f6b78",
        "accent": "#2c70bd", "accent_soft": "#bdd7f4", "wave": "#266bb6",
        "rms": "#74a4d5", "selection": "#c2d8f0", "playhead": "#bd6a19",
        "center": "#8794a3", "ruler": "#e4e8ed",
    },
}


def color(theme: str, role: str) -> QColor:
    return QColor(COLORS[theme][role])


def apply_theme(app: QApplication, theme: str) -> None:
    values = COLORS[theme]
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, color(theme, "background"))
    palette.setColor(QPalette.ColorRole.WindowText, color(theme, "text"))
    palette.setColor(QPalette.ColorRole.Base, color(theme, "control"))
    palette.setColor(QPalette.ColorRole.Text, color(theme, "text"))
    palette.setColor(QPalette.ColorRole.Button, color(theme, "panel"))
    palette.setColor(QPalette.ColorRole.ButtonText, color(theme, "text"))
    palette.setColor(QPalette.ColorRole.Highlight, color(theme, "accent"))
    palette.setColor(QPalette.ColorRole.HighlightedText, color(theme, "text"))
    app.setPalette(palette)
    template = files("audamix_frontend").joinpath("resources/dark.qss").read_text(encoding="utf-8")
    for role, value in values.items():
        template = template.replace(f"@{role}@", value)
    app.setStyleSheet(template)
