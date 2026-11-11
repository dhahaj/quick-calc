"""The calculator window: input line, live result, history and the optional keypad.

It is built once at startup and only ever shown or hidden, so summoning it is instant.
"""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QEvent, QModelIndex, QPersistentModelIndex, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QKeyEvent, QKeySequence, QMouseEvent, QPainter, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import History, HistoryEntry, Settings
from ..engine import Engine, FormatSettings
from .keypad import Keypad
from .theme import Palette, palette_for

CONTENT_WIDTH = 384
HISTORY_HEIGHT = 170
_ROW_HEIGHT = 24


class ElideLabel(QLabel):
    """A label that truncates with an ellipsis instead of forcing the window wider."""

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, self.fontMetrics().height() + 4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, rect.width())
        flags = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        self.style().drawItemText(painter, rect, int(flags), self.palette(), True, text, self.foregroundRole())


class HistoryDelegate(QStyledItemDelegate):
    """Paints one history row: the expression on the left, '= result' on the right."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.palette_: Palette = palette_for("system")

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:  # noqa: N802
        return QSize(0, _ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        entry: HistoryEntry = index.data(Qt.ItemDataRole.UserRole)
        p = self.palette_
        rect: QRect = option.rect  # type: ignore[attr-defined]
        state = option.state  # type: ignore[attr-defined]
        painter.save()
        if state & (QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_Selected):
            painter.fillRect(rect, QColor(p.hover))
        inner = rect.adjusted(8, 0, -8, 0)
        painter.setFont(option.font)  # type: ignore[attr-defined]
        metrics = painter.fontMetrics()
        result = "= " + entry.result
        # A few pixels of slack: text advance is fractional and would otherwise elide.
        result_width = min(metrics.horizontalAdvance(result) + 6, int(inner.width() * 0.62))
        result_rect = QRect(inner.right() - result_width + 1, inner.top(), result_width, inner.height())
        expr_rect = QRect(inner.left(), inner.top(), inner.width() - result_width - 12, inner.height())
        align = Qt.AlignmentFlag.AlignVCenter
        painter.setPen(QColor(p.dim))
        painter.drawText(
            expr_rect,
            int(align | Qt.AlignmentFlag.AlignLeft),
            metrics.elidedText(entry.expr, Qt.TextElideMode.ElideRight, expr_rect.width()),
        )
        painter.setPen(QColor(p.text))
        painter.drawText(
            result_rect,
            int(align | Qt.AlignmentFlag.AlignRight),
            metrics.elidedText(result, Qt.TextElideMode.ElideLeft, result_rect.width()),
        )
        painter.restore()


class InputLine(QLineEdit):
    commit = Signal()
    previous = Signal()
    next = Signal()
    escape = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.commit.emit()
        elif key == Qt.Key.Key_Up:
            self.previous.emit()
        elif key == Qt.Key.Key_Down:
            self.next.emit()
        elif key == Qt.Key.Key_Escape:
            self.escape.emit()
        else:
            super().keyPressEvent(event)


class TitleBar(QWidget):
    """Thin strip at the top; drag it to move the frameless window."""

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()


class MainWindow(QWidget):
    settings_requested = Signal()
    settings_changed = Signal()  # a toggle in the window changed a persisted setting
    history_changed = Signal()

    def __init__(self, engine: Engine, settings: Settings, history: History) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.engine = engine
        self.settings = settings
        self.history = history
        self._nav_index: int | None = None  # position while cycling with Up/Down
        self._draft = ""
        self._showing_result = False
        self._rounded = False

        self.setObjectName("root")
        self.setWindowTitle("QuickCalc")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 10)
        layout.setSpacing(6)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        # --- title bar
        bar = TitleBar()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(2, 0, 0, 0)
        bar_layout.setSpacing(2)
        title = QLabel("QuickCalc")
        title.setObjectName("title")
        bar_layout.addWidget(title)
        bar_layout.addStretch(1)
        self.history_button = self._tool_button("\ue81c", "Show or hide history (Ctrl+H)", checkable=True)
        self.keypad_button = self._tool_button("\ue75f", "Show or hide the keypad (Ctrl+B)", checkable=True)
        settings_button = self._tool_button("\ue713", "Settings (Ctrl+,)")
        hide_button = self._tool_button("\ue8bb", "Hide (Esc)")
        for button in (self.history_button, self.keypad_button, settings_button, hide_button):
            bar_layout.addWidget(button)
        layout.addWidget(bar)

        # --- history
        self.history_list = QListWidget()
        self.history_list.setObjectName("history")
        self.history_list.setFixedHeight(HISTORY_HEIGHT)
        self.history_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.history_list.setMouseTracking(True)
        self.history_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._delegate = HistoryDelegate(self.history_list)
        self.history_list.setItemDelegate(self._delegate)
        layout.addWidget(self.history_list)

        # --- input and result
        self.input = InputLine()
        self.input.setObjectName("input")
        self.input.setFixedWidth(CONTENT_WIDTH)
        self.input.setPlaceholderText("Type a calculation…")
        self.input.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.input)

        self.result_label = ElideLabel()
        self.result_label.setObjectName("result")
        self.result_label.setProperty("state", "preview")
        layout.addWidget(self.result_label)

        self.alt_label = ElideLabel()
        self.alt_label.setObjectName("alt")
        layout.addWidget(self.alt_label)

        # --- keypad
        self.keypad = Keypad()
        layout.addWidget(self.keypad)

        # --- wiring
        self.input.textChanged.connect(self._on_text_changed)
        self.input.commit.connect(self.commit)
        self.input.previous.connect(lambda: self._navigate(-1))
        self.input.next.connect(lambda: self._navigate(1))
        self.input.escape.connect(self.hide)
        self.history_list.itemClicked.connect(self._on_history_clicked)
        self.history_list.customContextMenuRequested.connect(self._history_menu)
        self.keypad.insert.connect(self._insert)
        self.keypad.clear.connect(self._clear_input)
        self.keypad.backspace.connect(self.input.backspace)
        self.keypad.equals.connect(self.commit)
        self.keypad_button.clicked.connect(self.toggle_keypad)
        self.history_button.clicked.connect(self.toggle_history)
        settings_button.clicked.connect(self.settings_requested)
        hide_button.clicked.connect(self.hide)

        for sequence, slot in (
            ("Ctrl+B", self.toggle_keypad),
            ("Ctrl+H", self.toggle_history),
            ("Ctrl+L", self.clear_history),
            ("Ctrl+,", self.settings_requested.emit),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(slot)

        for entry in history.entries:
            self._add_history_item(entry)
        self.history_list.scrollToBottom()
        self.apply_settings()

    @staticmethod
    def _tool_button(text: str, tip: str, checkable: bool = False) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tip)
        button.setCheckable(checkable)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    # --------------------------------------------------------------------- settings

    def apply_settings(self) -> None:
        """Bring the window and the engine in line with ``self.settings``."""
        s = self.settings
        self.engine.format = s.format_settings()
        self.engine.degrees = s.angle_mode == "deg"
        self.keypad.setVisible(s.show_keypad)
        self.keypad_button.setChecked(s.show_keypad)
        self.history_list.setVisible(s.show_history)
        self.history_button.setChecked(s.show_history)
        self.alt_label.setVisible(s.show_int_bases)
        self.apply_theme()
        self._refresh_preview()

    def apply_theme(self) -> None:
        self._delegate.palette_ = palette_for(self.settings.theme)
        self.history_list.viewport().update()

    def toggle_keypad(self) -> None:
        self.settings.show_keypad = not self.settings.show_keypad
        self.keypad.setVisible(self.settings.show_keypad)
        self.keypad_button.setChecked(self.settings.show_keypad)
        self.settings_changed.emit()

    def toggle_history(self) -> None:
        self.settings.show_history = not self.settings.show_history
        self.history_list.setVisible(self.settings.show_history)
        self.history_button.setChecked(self.settings.show_history)
        self.settings_changed.emit()

    # ------------------------------------------------------------- show / hide / move

    def toggle(self) -> None:
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            self.summon()

    def summon(self) -> None:
        """Show on the monitor under the mouse and take keyboard focus."""
        if not self.isVisible():
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
            area = screen.availableGeometry()
            size = self.sizeHint()
            offset = self.settings.last_offset
            if self.settings.position == "last" and offset is not None:
                x, y = area.x() + offset[0], area.y() + offset[1]
            else:
                x = area.x() + (area.width() - size.width()) // 2
                y = area.y() + (area.height() - size.height()) // 2
            x = max(area.left(), min(x, area.right() - size.width() + 1))
            y = max(area.top(), min(y, area.bottom() - size.height() + 1))
            self.move(QPoint(x, y))
            self.show()
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":
            ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
        self.input.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.input.selectAll()

    def showEvent(self, event: object) -> None:  # noqa: N802
        if not self._rounded and sys.platform == "win32":
            self._rounded = True
            try:  # Windows 11 rounded corners; silently unavailable on Windows 10
                preference = ctypes.c_int(2)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    int(self.winId()), 33, ctypes.byref(preference), ctypes.sizeof(preference)
                )
            except Exception:
                pass

    def hideEvent(self, event: object) -> None:  # noqa: N802
        screen = self.screen()
        if screen is not None:
            area = screen.availableGeometry()
            offset = [self.x() - area.x(), self.y() - area.y()]
            if offset != self.settings.last_offset:
                self.settings.last_offset = offset
                self.settings_changed.emit()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        if (
            event.type() == QEvent.Type.ActivationChange
            and self.settings.hide_on_focus_loss
            and not self.isActiveWindow()
        ):
            QTimer.singleShot(60, self._hide_if_app_inactive)
        super().changeEvent(event)

    def _hide_if_app_inactive(self) -> None:
        # Focus moving to our own settings dialog or a menu doesn't count.
        if self.isVisible() and QApplication.activeWindow() is None and QApplication.activePopupWidget() is None:
            self.hide()

    # ------------------------------------------------------------ input and results

    def _set_result(self, text: str, state: str, alt: str | None = None) -> None:
        self.result_label.setText(text)
        self.result_label.setToolTip(text if len(text) > 30 else "")
        if self.result_label.property("state") != state:
            self.result_label.setProperty("state", state)
            self.result_label.style().unpolish(self.result_label)
            self.result_label.style().polish(self.result_label)
        self.alt_label.setText(alt or "")
        self.result_label.update()

    def _on_text_changed(self, text: str) -> None:
        if self._showing_result and not text:
            return  # keep the committed result on screen until typing resumes
        self._showing_result = False
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self._showing_result:
            return
        text = self.input.text()
        preview = self.engine.preview(text) if text.strip() else None
        if preview is None or preview.text == text.strip():
            self._set_result("", "preview")
        else:
            self._set_result("= " + preview.text, "preview", preview.alt)

    def commit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        result = self.engine.evaluate(text)
        if not result.ok:
            self._showing_result = False
            self._set_result(result.display, "error")
            return
        entry = HistoryEntry(result.expr, result.text, result.alt)
        self.history.add(entry)
        self._add_history_item(entry)
        while self.history_list.count() > len(self.history.entries):
            self.history_list.takeItem(0)
        self.history_list.scrollToBottom()
        self.history_changed.emit()
        self._nav_index = None
        self._draft = ""
        self._showing_result = True
        self.input.clear()
        self._set_result("= " + result.text, "result", result.alt)
        if self.settings.copy_on_enter:
            plain = FormatSettings(
                self.engine.format.mode, self.engine.format.sig_figs, self.engine.format.fixed_decimals
            )
            QGuiApplication.clipboard().setText(self.engine.format_result(result, plain))

    def _insert(self, text: str) -> None:
        self.input.insert(text)
        self.input.setFocus()

    def _clear_input(self) -> None:
        self._showing_result = False
        self.input.clear()
        self._set_result("", "preview")
        self.input.setFocus()

    def _navigate(self, step: int) -> None:
        """Up / Down through earlier inputs, shell-style; the unfinished line is kept."""
        entries = self.history.entries
        if not entries:
            return
        if self._nav_index is None:
            if step > 0:
                return
            self._draft = self.input.text()
            index = len(entries) - 1
        else:
            index = self._nav_index + step
        if index < 0:
            return
        if index >= len(entries):
            self._nav_index = None
            self.input.setText(self._draft)
            return
        self._nav_index = index
        self.input.setText(entries[index].expr)

    # ---------------------------------------------------------------------- history

    def _add_history_item(self, entry: HistoryEntry) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, entry)
        tip = f"{entry.expr}\n= {entry.result}"
        item.setToolTip(tip + (f"\n{entry.alt}" if entry.alt else ""))
        self.history_list.addItem(item)

    def _on_history_clicked(self, item: QListWidgetItem) -> None:
        entry: HistoryEntry = item.data(Qt.ItemDataRole.UserRole)
        self._nav_index = None
        self.input.setText(entry.expr)
        self.input.setFocus()
        self.history_list.clearSelection()

    def _history_menu(self, pos: QPoint) -> None:
        item = self.history_list.itemAt(pos)
        menu = QMenu(self)
        if item is not None:
            entry: HistoryEntry = item.data(Qt.ItemDataRole.UserRole)
            menu.addAction("Insert result", lambda: self._insert(entry.result))
            menu.addAction("Copy result", lambda: QGuiApplication.clipboard().setText(entry.result))
            menu.addAction("Copy expression", lambda: QGuiApplication.clipboard().setText(entry.expr))
            menu.addSeparator()
        clear = menu.addAction("Clear history\tCtrl+L", self.clear_history)
        clear.setEnabled(bool(self.history.entries))
        menu.exec(self.history_list.viewport().mapToGlobal(pos))

    def clear_history(self) -> None:
        self.history.clear()
        self.history_list.clear()
        self._nav_index = None
        self.history_changed.emit()
        self.input.setFocus()
