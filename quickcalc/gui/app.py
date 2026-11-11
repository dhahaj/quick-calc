"""Application shell: tray icon, global hotkey, single instance, and persistence."""

from __future__ import annotations

import os
import sys
from dataclasses import fields

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QPalette
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import APP_NAME, config, winplatform
from .single_instance import SingleInstance
from .theme import app_icon, palette_for, stylesheet


class QuickCalcApp:
    def __init__(self, app: QApplication, start_hidden: bool, instance: SingleInstance) -> None:
        self.app = app
        self.instance = instance
        self.settings = config.load_settings()
        self.icon = app_icon()
        app.setWindowIcon(self.icon)
        self._apply_theme()

        # Tray first, so there is something on screen while Pint loads (~0.5 s).
        self.tray = QSystemTrayIcon(self.icon)
        self.tray.setToolTip(APP_NAME)
        self.menu = QMenu()
        self.menu.addAction("Show", self.show_window)
        self.menu.addAction("Settings…", self.open_settings)
        self.autostart_action = QAction("Start with Windows", self.menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.triggered.connect(self._toggle_autostart)
        self.menu.addAction(self.autostart_action)
        self.menu.addSeparator()
        self.menu.addAction("Quit", self.quit)
        self.menu.aboutToShow.connect(
            lambda: self.autostart_action.setChecked(winplatform.autostart_enabled())
        )
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        app.processEvents()

        from ..engine import Engine  # deferred: this import is the slow part of startup
        from .hotkey import GlobalHotkey
        from .window import MainWindow

        units_path = config.ensure_custom_units_file()
        self.engine = Engine(custom_units_path=units_path if units_path.exists() else None)
        self.history = config.load_history() if self.settings.persist_history else config.History()
        self.window = MainWindow(self.engine, self.settings, self.history)
        self.window.settings_requested.connect(self.open_settings)
        self.window.settings_changed.connect(self._save_settings_soon)
        self.window.history_changed.connect(self._save_history)
        self._settings_dialog = None
        # Create the native window and resolve styles now, so the first hotkey press
        # only has to show it.
        self.window.winId()
        self.window.ensurePolished()

        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(lambda: config.save_settings(self.settings))

        self.instance.listen(self._on_instance_message)
        self.hotkey = GlobalHotkey(self.toggle_window)
        self._register_hotkey()

        app.styleHints().colorSchemeChanged.connect(lambda _scheme: self._apply_theme(refresh_window=True))
        app.aboutToQuit.connect(self._shutdown)

        if self.engine.warnings:
            self._notify("Custom units", "\n".join(self.engine.warnings[:3]), warning=True)
        if not start_hidden:
            self.show_window()

    # ------------------------------------------------------------------ appearance

    def _apply_theme(self, refresh_window: bool = False) -> None:
        p = palette_for(self.settings.theme)
        palette = QPalette()
        for role, colour in (
            (QPalette.ColorRole.Window, p.window),
            (QPalette.ColorRole.Base, p.surface),
            (QPalette.ColorRole.AlternateBase, p.hover),
            (QPalette.ColorRole.Button, p.surface),
            (QPalette.ColorRole.ToolTipBase, p.surface),
            (QPalette.ColorRole.WindowText, p.text),
            (QPalette.ColorRole.Text, p.text),
            (QPalette.ColorRole.ButtonText, p.text),
            (QPalette.ColorRole.ToolTipText, p.text),
            (QPalette.ColorRole.PlaceholderText, p.dim),
            (QPalette.ColorRole.Highlight, p.accent),
            (QPalette.ColorRole.HighlightedText, p.accent_text),
        ):
            palette.setColor(role, QColor(colour))
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(p.dim))
        self.app.setPalette(palette)
        self.app.setStyleSheet(stylesheet(p))
        if refresh_window:
            self.window.apply_theme()

    def _notify(self, title: str, text: str, warning: bool = False) -> None:
        icon = QSystemTrayIcon.MessageIcon.Warning if warning else QSystemTrayIcon.MessageIcon.Information
        self.tray.showMessage(f"{APP_NAME}: {title}", text, icon, 8000)

    # ---------------------------------------------------------------------- actions

    def _on_instance_message(self, message: str) -> None:
        """A later launch of the program talks to this one: 'show' or 'quit'."""
        if message == "quit":
            self.quit()
        else:
            self.show_window()

    def show_window(self) -> None:
        self.window.summon()

    def toggle_window(self) -> None:
        self.window.toggle()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_window()

    def _register_hotkey(self) -> bool:
        ok = self.hotkey.register(self.settings.hotkey)
        if ok:
            self.tray.setToolTip(f"{APP_NAME} ({self.settings.hotkey})")
        else:
            self.tray.setToolTip(f"{APP_NAME} (no hotkey)")
            self._notify(
                "Hotkey unavailable",
                f"Couldn't register {self.settings.hotkey}. Another program is probably using it. "
                "Pick a different one in Settings; the tray icon still opens the calculator.",
                warning=True,
            )
        return ok

    def _toggle_autostart(self, checked: bool) -> None:
        if not winplatform.set_autostart(checked):
            self._notify("Start with Windows", "Couldn't update the startup entry.", warning=True)

    def open_settings(self) -> None:
        from .settings_dialog import SettingsDialog

        if self._settings_dialog is not None:
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        parent = self.window if self.window.isVisible() else None
        dialog = SettingsDialog(self.settings, parent)
        dialog.open_units_file.connect(self._open_units_file)
        dialog.clear_history.connect(self.window.clear_history)
        self._settings_dialog = dialog
        try:
            accepted = dialog.exec() == SettingsDialog.DialogCode.Accepted
        finally:
            self._settings_dialog = None
        if not accepted:
            return

        new = dialog.result_settings()
        old_hotkey, old_theme, old_persist = self.settings.hotkey, self.settings.theme, self.settings.persist_history
        # Copy into the existing object: the window holds a reference to it.
        for f in fields(config.Settings):
            if f.name != "last_offset":
                setattr(self.settings, f.name, getattr(new, f.name))
        self.settings.validate()

        if self.settings.hotkey != old_hotkey and not self._register_hotkey():
            self.settings.hotkey = old_hotkey
            self.hotkey.register(old_hotkey)
            self.tray.setToolTip(f"{APP_NAME} ({old_hotkey})")
        if self.settings.theme != old_theme:
            self._apply_theme()
        self.window.apply_settings()

        if dialog.autostart.isChecked() != winplatform.autostart_enabled():
            self._toggle_autostart(dialog.autostart.isChecked())
        if dialog.calculator_key.isEnabled() and dialog.calculator_key.isChecked() != winplatform.calculator_key_enabled():
            if not winplatform.set_calculator_key(dialog.calculator_key.isChecked()):
                self._notify("Calculator key", "Couldn't update the Calculator key setting.", warning=True)

        if self.settings.persist_history != old_persist:
            if self.settings.persist_history:
                self._save_history()
            else:
                config.delete_history_file()
        config.save_settings(self.settings)

    def _open_units_file(self) -> None:
        path = config.ensure_custom_units_file()
        try:
            os.startfile(path)  # noqa: S606 - opens the user's own text file in their editor
        except OSError:
            self._notify("Custom units", f"Couldn't open {path}", warning=True)

    # ------------------------------------------------------------------ persistence

    def _save_settings_soon(self) -> None:
        self._save_timer.start()

    def _save_history(self) -> None:
        if self.settings.persist_history:
            config.save_history(self.history)

    def _shutdown(self) -> None:
        self.hotkey.unregister()
        self._save_timer.stop()
        config.save_settings(self.settings)
        self._save_history()
        self.tray.hide()

    def quit(self) -> None:
        self.window.hide()
        self.app.quit()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    start_hidden = "--tray" in args

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")

    instance = SingleInstance()
    if "--quit" in args:
        if instance.already_running:
            instance.send("quit")
        return 0
    if instance.already_running:
        instance.send("show")
        return 0

    quickcalc = QuickCalcApp(app, start_hidden, instance)
    code = app.exec()
    del quickcalc
    return code
