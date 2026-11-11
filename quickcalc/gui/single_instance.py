"""One running copy per login session. A later launch tells the first one to show
itself (or quit) and then exits.

Implemented with a named Win32 mutex and a registered window message, so the app
needs no sockets, pipes or networking libraries at all.
"""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

_MUTEX_NAME = "Local\\QuickCalc.SingleInstance"
_ERROR_ALREADY_EXISTS = 183
_HWND_BROADCAST = 0xFFFF
_ASFW_ANY = 0xFFFFFFFF
_COMMANDS = ("show", "quit")


class SingleInstance(QAbstractNativeEventFilter):
    def __init__(self) -> None:
        super().__init__()
        self.already_running = False
        self._callback: Callable[[str], None] | None = None
        self._messages: dict[int, str] = {}
        self._mutex = None
        if sys.platform != "win32":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.RegisterWindowMessageW.argtypes = (wintypes.LPCWSTR,)
        self._user32.RegisterWindowMessageW.restype = wintypes.UINT
        # The mutex lives as long as this process; Windows releases it on exit or crash.
        self._mutex = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
        self.already_running = ctypes.get_last_error() == _ERROR_ALREADY_EXISTS
        for command in _COMMANDS:
            self._messages[self._user32.RegisterWindowMessageW(f"QuickCalc.{command}")] = command

    def send(self, command: str = "show") -> None:
        """Ask the copy that is already running to do something."""
        if not self._messages:
            return
        message = next(mid for mid, name in self._messages.items() if name == command)
        # We were just started by the user, so we may pass on the right to take focus.
        self._user32.AllowSetForegroundWindow(_ASFW_ANY)
        self._user32.PostMessageW(_HWND_BROADCAST, message, 0, 0)

    def listen(self, callback: Callable[[str], None]) -> None:
        """Call ``callback('show' | 'quit')`` when a later launch asks for it."""
        self._callback = callback
        app = QCoreApplication.instance()
        assert app is not None
        app.installNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):  # type: ignore[no-untyped-def]  # noqa: N802
        if self._callback is not None and event_type == b"windows_generic_MSG":
            command = self._messages.get(wintypes.MSG.from_address(int(message)).message)
            if command is not None:
                self._callback(command)
                return True, 0
        return False, 0
