"""Windows glue that needs no Qt: hotkey parsing and the per-user registry entries.

Everything here lives under HKEY_CURRENT_USER, so no admin rights are ever needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "QuickCalc"
# Explorer's per-user override for the keyboard's dedicated Calculator key (app key 18).
APPKEY_CALC = r"Software\Microsoft\Windows\CurrentVersion\Explorer\AppKey\18"

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000

_MODIFIERS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT,
    "win": MOD_WIN, "meta": MOD_WIN, "super": MOD_WIN,
}  # fmt: skip

_NAMED_KEYS = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "backspace": 0x08, "ins": 0x2D, "insert": 0x2D, "del": 0x2E, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pgup": 0x21, "pageup": 0x21, "pgdown": 0x22, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "pause": 0x13, "print": 0x2C,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA,
    "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "+": 0xBB,
}  # fmt: skip


def parse_hotkey(text: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+C' -> (modifier flags, virtual-key code), or None if it isn't usable.

    A plain key with no modifier is refused (it would swallow normal typing) unless
    it is a function key.
    """
    text = text.strip()
    if not text:
        return None
    if text.endswith("++") or text == "+":
        parts = [p for p in text[:-1].split("+") if p] + ["+"]
    else:
        parts = [p.strip() for p in text.split("+")]
    if not all(parts):
        return None
    *mods, key = parts
    flags = 0
    for mod in mods:
        flag = _MODIFIERS.get(mod.lower())
        if flag is None:
            return None
        flags |= flag
    name = key.lower()
    is_function_key = False
    if len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key.upper())
    elif name[:1] == "f" and name[1:].isdigit() and 1 <= int(name[1:]) <= 24:
        vk = 0x70 + int(name[1:]) - 1
        is_function_key = True
    elif name in _NAMED_KEYS:
        vk = _NAMED_KEYS[name]
    else:
        return None
    if not flags and not is_function_key:
        return None
    return flags, vk


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def launch_command(*args: str) -> str:
    """The command line that starts this copy of QuickCalc."""
    if is_frozen():
        parts = [sys.executable]
    else:
        exe = Path(sys.executable)
        pythonw = exe.with_name("pythonw.exe")
        entry = Path(__file__).resolve().parent / "__main__.py"
        parts = [str(pythonw if pythonw.exists() else exe), str(entry)]
    return " ".join([f'"{p}"' for p in parts] + list(args))


def _winreg():  # type: ignore[no-untyped-def]
    import winreg

    return winreg


def _read(key_path: str, value: str) -> str | None:
    try:
        winreg = _winreg()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            data, _ = winreg.QueryValueEx(key, value)
            return data if isinstance(data, str) else None
    except (OSError, ImportError):
        return None


def autostart_enabled() -> bool:
    return _read(RUN_KEY, RUN_VALUE) is not None


def set_autostart(enabled: bool) -> bool:
    """Add or remove the HKCU Run entry. Returns True on success."""
    try:
        winreg = _winreg()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, launch_command("--tray"))
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except (OSError, ImportError):
        return False


def calculator_key_supported() -> bool:
    """The override stores a single program path, so it only works for the built exe."""
    return is_frozen()


def calculator_key_enabled() -> bool:
    target = _read(APPKEY_CALC, "ShellExecute")
    return target is not None and is_frozen() and Path(target) == Path(sys.executable)


def set_calculator_key(enabled: bool) -> bool:
    """Point the keyboard's Calculator key at QuickCalc, or restore the Windows default
    by deleting the override key again."""
    try:
        winreg = _winreg()
        if enabled:
            if not calculator_key_supported():
                return False
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, APPKEY_CALC) as key:
                winreg.SetValueEx(key, "ShellExecute", 0, winreg.REG_SZ, sys.executable)
        else:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, APPKEY_CALC)
            except FileNotFoundError:
                pass
        return True
    except (OSError, ImportError):
        return False
