"""The Settings dialog. It edits a copy; the caller applies it only on OK."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import winplatform
from ..config import DEFAULT_HOTKEY, Settings


def _combo(options: list[tuple[str, str]], current: str) -> QComboBox:
    box = QComboBox()
    for value, label in options:
        box.addItem(label, value)
    box.setCurrentIndex(max(0, box.findData(current)))
    return box


class SettingsDialog(QDialog):
    open_units_file = Signal()
    clear_history = Signal()

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("QuickCalc settings")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self._original = settings

        root = QVBoxLayout(self)
        root.setSpacing(10)

        # --- window
        window_box = QGroupBox("Window")
        form = QFormLayout(window_box)
        form.setHorizontalSpacing(14)
        self.hotkey = QKeySequenceEdit(QKeySequence(settings.hotkey))
        self.hotkey.setMaximumSequenceLength(1)
        reset = QPushButton("Default")
        reset.clicked.connect(lambda: self.hotkey.setKeySequence(QKeySequence(DEFAULT_HOTKEY)))
        row = QHBoxLayout()
        row.addWidget(self.hotkey, 1)
        row.addWidget(reset)
        form.addRow("Global hotkey", row)
        self.hotkey_hint = QLabel("Click the box and press the new combination.")
        self.hotkey_hint.setObjectName("hint")
        form.addRow("", self.hotkey_hint)
        self.hotkey.keySequenceChanged.connect(self._check_hotkey)

        self.position = _combo([("center", "Centre of the screen"), ("last", "Where I left it")], settings.position)
        form.addRow("Open at", self.position)
        self.theme = _combo([("system", "Follow Windows"), ("dark", "Dark"), ("light", "Light")], settings.theme)
        form.addRow("Theme", self.theme)
        self.hide_on_focus_loss = QCheckBox("Hide when the window loses focus")
        self.hide_on_focus_loss.setChecked(settings.hide_on_focus_loss)
        form.addRow("", self.hide_on_focus_loss)
        self.show_keypad = QCheckBox("Show the button keypad (Ctrl+B)")
        self.show_keypad.setChecked(settings.show_keypad)
        form.addRow("", self.show_keypad)
        self.show_history = QCheckBox("Show history (Ctrl+H)")
        self.show_history.setChecked(settings.show_history)
        form.addRow("", self.show_history)
        root.addWidget(window_box)

        # --- calculation
        calc_box = QGroupBox("Calculation and output")
        form = QFormLayout(calc_box)
        form.setHorizontalSpacing(14)
        self.angle_mode = _combo([("rad", "Radians"), ("deg", "Degrees")], settings.angle_mode)
        form.addRow("Angles", self.angle_mode)
        self.format_mode = _combo(
            [
                ("auto", "Auto"),
                ("eng", "Engineering / SI prefixes"),
                ("sci", "Scientific"),
                ("fixed", "Fixed decimals"),
            ],
            settings.format_mode,
        )
        form.addRow("Number format", self.format_mode)
        self.sig_figs = QSpinBox()
        self.sig_figs.setRange(1, 15)
        self.sig_figs.setValue(settings.sig_figs)
        form.addRow("Significant figures", self.sig_figs)
        self.fixed_decimals = QSpinBox()
        self.fixed_decimals.setRange(0, 12)
        self.fixed_decimals.setValue(settings.fixed_decimals)
        form.addRow("Decimals (Fixed)", self.fixed_decimals)
        self.thousands_sep = QCheckBox("Thousands separators (1,234,567)")
        self.thousands_sep.setChecked(settings.thousands_sep)
        form.addRow("", self.thousands_sep)
        self.show_int_bases = QCheckBox("Show hex and binary next to whole numbers")
        self.show_int_bases.setChecked(settings.show_int_bases)
        form.addRow("", self.show_int_bases)
        self.copy_on_enter = QCheckBox("Copy the result to the clipboard on Enter")
        self.copy_on_enter.setChecked(settings.copy_on_enter)
        form.addRow("", self.copy_on_enter)
        self.format_mode.currentIndexChanged.connect(self._sync_enabled)
        root.addWidget(calc_box)

        # --- system
        system_box = QGroupBox("History and Windows")
        box = QVBoxLayout(system_box)
        self.persist_history = QCheckBox("Remember history between sessions")
        self.persist_history.setChecked(settings.persist_history)
        box.addWidget(self.persist_history)
        self.autostart = QCheckBox("Start with Windows")
        self.autostart.setChecked(winplatform.autostart_enabled())
        box.addWidget(self.autostart)
        self.calculator_key = QCheckBox("Open QuickCalc with the keyboard's Calculator key")
        self.calculator_key.setChecked(winplatform.calculator_key_enabled())
        box.addWidget(self.calculator_key)
        if not winplatform.calculator_key_supported():
            self.calculator_key.setEnabled(False)
            note = QLabel("The Calculator key option needs the built QuickCalc.exe (see the README).")
            note.setObjectName("hint")
            note.setWordWrap(True)
            box.addWidget(note)
        buttons_row = QHBoxLayout()
        units_button = QPushButton("Edit custom units…")
        units_button.clicked.connect(self.open_units_file)
        clear_button = QPushButton("Clear history")
        clear_button.clicked.connect(self.clear_history)
        buttons_row.addWidget(units_button)
        buttons_row.addWidget(clear_button)
        buttons_row.addStretch(1)
        box.addLayout(buttons_row)
        root.addWidget(system_box)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        self._sync_enabled()

    def _sync_enabled(self) -> None:
        fixed = self.format_mode.currentData() == "fixed"
        self.fixed_decimals.setEnabled(fixed)
        self.sig_figs.setEnabled(not fixed)

    def hotkey_text(self) -> str:
        text = self.hotkey.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        return text.replace("Meta", "Win")

    def _check_hotkey(self) -> None:
        text = self.hotkey_text()
        valid = bool(text) and winplatform.parse_hotkey(text) is not None
        if valid:
            message = "Click the box and press the new combination."
        elif not text:
            message = "No hotkey set; the previous one will be kept."
        else:
            message = "Use at least one of Ctrl, Alt, Shift or Win plus a key."
        self.hotkey_hint.setText(message)
        self.hotkey_hint.setProperty("warn", "true" if text and not valid else "false")
        self.hotkey_hint.style().unpolish(self.hotkey_hint)
        self.hotkey_hint.style().polish(self.hotkey_hint)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid or not text)

    def result_settings(self) -> Settings:
        """The edited settings (a new object; the original is untouched)."""
        hotkey = self.hotkey_text()
        return replace(
            self._original,
            hotkey=hotkey if hotkey and winplatform.parse_hotkey(hotkey) else self._original.hotkey,
            position=self.position.currentData(),
            theme=self.theme.currentData(),
            hide_on_focus_loss=self.hide_on_focus_loss.isChecked(),
            show_keypad=self.show_keypad.isChecked(),
            show_history=self.show_history.isChecked(),
            angle_mode=self.angle_mode.currentData(),
            format_mode=self.format_mode.currentData(),
            sig_figs=self.sig_figs.value(),
            fixed_decimals=self.fixed_decimals.value(),
            thousands_sep=self.thousands_sep.isChecked(),
            show_int_bases=self.show_int_bases.isChecked(),
            copy_on_enter=self.copy_on_enter.isChecked(),
            persist_history=self.persist_history.isChecked(),
        )
