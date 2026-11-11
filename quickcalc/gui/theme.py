"""Dark and light palettes, the stylesheet, and the app icon."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon

ICON_PATH = Path(__file__).with_name("qc.ico")


@dataclass(frozen=True, slots=True)
class Palette:
    window: str
    surface: str
    hover: str
    pressed: str
    border: str
    text: str
    dim: str
    accent: str
    accent_text: str
    error: str


DARK = Palette(
    window="#1f2023", surface="#2a2c31", hover="#363940", pressed="#42464e", border="#3a3d44",
    text="#e8e9ec", dim="#8d929c", accent="#4c9aff", accent_text="#0b1220", error="#ff7b72",
)  # fmt: skip
LIGHT = Palette(
    window="#f6f6f8", surface="#ffffff", hover="#ececf0", pressed="#dfe0e6", border="#d0d2d9",
    text="#1c1d21", dim="#737884", accent="#1a6dd6", accent_text="#ffffff", error="#c62828",
)  # fmt: skip

MONO = '"Cascadia Mono", "Cascadia Code", Consolas, "Courier New", monospace'


def system_is_dark() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def palette_for(theme: str) -> Palette:
    if theme == "dark":
        return DARK
    if theme == "light":
        return LIGHT
    return DARK if system_is_dark() else LIGHT


def stylesheet(p: Palette) -> str:
    return f"""
    QWidget {{ color: {p.text}; font-family: "Segoe UI Variable", "Segoe UI", sans-serif; font-size: 10pt; }}
    #root {{ background: {p.window}; border: 1px solid {p.border}; }}
    QDialog {{ background: {p.window}; }}
    #title {{ color: {p.dim}; font-size: 9pt; font-weight: 600; }}

    QToolButton {{ background: transparent; border: none; border-radius: 4px; padding: 5px 7px; color: {p.dim};
        font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets"; font-size: 10pt; }}
    QToolButton:hover {{ background: {p.hover}; color: {p.text}; }}
    QToolButton:checked {{ color: {p.accent}; }}

    #input {{
        background: {p.surface}; border: 1px solid {p.border}; border-radius: 6px;
        padding: 7px 9px; font-family: {MONO}; font-size: 14pt;
        selection-background-color: {p.accent}; selection-color: {p.accent_text};
    }}
    #input:focus {{ border-color: {p.accent}; }}

    #result {{ font-family: {MONO}; font-size: 13pt; padding: 0 3px; }}
    #result[state="preview"] {{ color: {p.dim}; }}
    #result[state="result"] {{ color: {p.text}; }}
    #result[state="error"] {{ color: {p.error}; font-size: 10pt; }}
    #alt {{ color: {p.dim}; font-family: {MONO}; font-size: 9pt; padding: 0 3px; }}

    #history {{
        background: {p.surface}; border: 1px solid {p.border}; border-radius: 6px;
        font-family: {MONO}; font-size: 10pt; outline: none;
    }}
    #history::item {{ padding: 0; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {p.pressed}; border-radius: 3px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

    #keypad QPushButton {{
        background: {p.surface}; border: 1px solid {p.border}; border-radius: 5px;
        font-family: "Segoe UI Variable", "Segoe UI", sans-serif; font-size: 12pt; min-height: 30px;
    }}
    #keypad QPushButton:hover {{ background: {p.hover}; }}
    #keypad QPushButton:pressed {{ background: {p.pressed}; }}
    #keypad QPushButton[role="op"] {{ color: {p.accent}; }}
    #keypad QPushButton[role="clear"] {{ color: {p.error}; }}
    #keypad QPushButton[role="equals"] {{ background: {p.accent}; color: {p.accent_text}; border-color: {p.accent}; }}

    QMenu {{ background: {p.surface}; border: 1px solid {p.border}; padding: 4px; }}
    QMenu::item {{ padding: 5px 22px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {p.hover}; }}
    QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 6px; }}

    QDialog QPushButton {{
        background: {p.surface}; border: 1px solid {p.border}; border-radius: 5px; padding: 5px 14px;
    }}
    QDialog QPushButton:hover {{ background: {p.hover}; }}
    QDialog QPushButton:default {{ border-color: {p.accent}; }}
    QComboBox, QSpinBox, QKeySequenceEdit QLineEdit {{
        background: {p.surface}; border: 1px solid {p.border}; border-radius: 4px; padding: 4px 8px; min-height: 18px;
    }}
    QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border};
        selection-background-color: {p.hover}; selection-color: {p.text}; }}
    QGroupBox {{ border: 1px solid {p.border}; border-radius: 6px; margin-top: 10px; padding-top: 8px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {p.dim}; }}
    #hint {{ color: {p.dim}; font-size: 9pt; }}
    #hint[warn="true"] {{ color: {p.error}; }}
    """


def app_icon() -> QIcon:
    """The app and tray icon, loaded from the qc.ico shipped next to this module."""
    return QIcon(str(ICON_PATH))
