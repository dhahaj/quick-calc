"""System-wide hotkey through Win32 RegisterHotKey and a Qt native event filter.

No keyboard hook is installed, so nothing here looks like a keylogger to antivirus tools.
"""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

from ..winplatform import MOD_NOREPEAT, parse_hotkey

WM_HOTKEY = 0x0312
_HOTKEY_ID = 0x5143  # arbitrary, unique within this process


class GlobalHotkey(QAbstractNativeEventFilter):
    """Owns one registered hotkey. The callback runs on the GUI thread."""

    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__()
        self._callback = callback
        self._registered = False
        self._installed = False
        self._user32 = ctypes.windll.user32 if sys.platform == "win32" else None

    def register(self, text: str) -> bool:
        """Replace the current hotkey with ``text``. False if Windows refuses it,
        which nearly always means another program already owns that combination."""
        self.unregister()
        parsed = parse_hotkey(text)
        if parsed is None or self._user32 is None:
            return False
        modifiers, vk = parsed
        if not self._installed:
            app = QCoreApplication.instance()
            assert app is not None
            app.installNativeEventFilter(self)
            self._installed = True
        # hWnd is NULL: WM_HOTKEY is posted to this thread's queue, which Qt pumps.
        self._registered = bool(self._user32.RegisterHotKey(None, _HOTKEY_ID, modifiers | MOD_NOREPEAT, vk))
        return self._registered

    def unregister(self) -> None:
        if self._registered and self._user32 is not None:
            self._user32.UnregisterHotKey(None, _HOTKEY_ID)
        self._registered = False

    def nativeEventFilter(self, event_type, message):  # type: ignore[no-untyped-def]  # noqa: N802
        if self._registered and event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                self._callback()
                return True, 0
        return False, 0
