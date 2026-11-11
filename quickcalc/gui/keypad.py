"""The optional on-screen keypad. Buttons never take focus, so typing keeps working."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QPushButton, QWidget

# (label, text to insert or action name, role)
_KEYS: list[list[tuple[str, str, str]]] = [
    [("C", "<clear>", "clear"), ("(", "(", "op"), (")", ")", "op"), ("⌫", "<back>", "op"), ("÷", "/", "op")],
    [("7", "7", ""), ("8", "8", ""), ("9", "9", ""), ("√", "sqrt(", "op"), ("×", "*", "op")],
    [("4", "4", ""), ("5", "5", ""), ("6", "6", ""), ("^", "^", "op"), ("−", "-", "op")],
    [("1", "1", ""), ("2", "2", ""), ("3", "3", ""), ("π", "pi", "op"), ("+", "+", "op")],
    [("0", "0", ""), (".", ".", ""), ("%", "%", "op"), ("ans", "ans", "op"), ("=", "<equals>", "equals")],
]


class Keypad(QWidget):
    insert = Signal(str)
    clear = Signal()
    backspace = Signal()
    equals = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("keypad")
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for row, keys in enumerate(_KEYS):
            for col, (label, action, role) in enumerate(keys):
                button = QPushButton(label)
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.setProperty("role", role)
                button.setAutoRepeat(action == "<back>")
                button.clicked.connect(lambda _=False, a=action: self._press(a))
                grid.addWidget(button, row, col)

    def _press(self, action: str) -> None:
        if action == "<clear>":
            self.clear.emit()
        elif action == "<back>":
            self.backspace.emit()
        elif action == "<equals>":
            self.equals.emit()
        else:
            self.insert.emit(action)
