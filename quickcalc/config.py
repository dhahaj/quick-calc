"""Settings and history on disk, in %APPDATA%\\QuickCalc. No Qt, no network."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .engine import CUSTOM_UNITS_TEMPLATE, MODES, FormatSettings

HISTORY_LIMIT = 500
DEFAULT_HOTKEY = "Ctrl+Alt+C"


def app_dir() -> Path:
    base = os.environ.get("APPDATA")
    return (Path(base) if base else Path.home() / "AppData" / "Roaming") / "QuickCalc"


def settings_path() -> Path:
    return app_dir() / "settings.json"


def history_path() -> Path:
    return app_dir() / "history.json"


def custom_units_path() -> Path:
    return app_dir() / "units.txt"


@dataclass(slots=True)
class Settings:
    hotkey: str = DEFAULT_HOTKEY
    position: str = "center"  # center | last
    last_offset: list[int] | None = None  # window offset from its screen's top-left corner
    hide_on_focus_loss: bool = False
    theme: str = "system"  # system | dark | light
    copy_on_enter: bool = True
    show_keypad: bool = False
    show_history: bool = True
    persist_history: bool = True
    angle_mode: str = "rad"  # rad | deg
    format_mode: str = "auto"  # auto | eng | sci | fixed
    sig_figs: int = 10
    fixed_decimals: int = 4
    thousands_sep: bool = False
    show_int_bases: bool = False

    def format_settings(self) -> FormatSettings:
        return FormatSettings(
            self.format_mode, self.sig_figs, self.fixed_decimals, self.thousands_sep, self.show_int_bases
        )

    def validate(self) -> None:
        """Clamp anything out of range back to a sane value (hand-edited files happen)."""
        defaults = Settings()
        if self.position not in ("center", "last"):
            self.position = defaults.position
        if self.theme not in ("system", "dark", "light"):
            self.theme = defaults.theme
        if self.angle_mode not in ("rad", "deg"):
            self.angle_mode = defaults.angle_mode
        if self.format_mode not in MODES:
            self.format_mode = defaults.format_mode
        self.sig_figs = max(1, min(15, self.sig_figs))
        self.fixed_decimals = max(0, min(12, self.fixed_decimals))
        if not self.hotkey.strip():
            self.hotkey = defaults.hotkey
        offset = self.last_offset
        if not (isinstance(offset, list) and len(offset) == 2 and all(type(v) is int for v in offset)):
            self.last_offset = None


def _write_json(path: Path, data: Any) -> bool:
    """Write atomically so a crash mid-write can't leave a half-written file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_settings(path: Path | None = None) -> Settings:
    settings = Settings()
    data = _read_json(path or settings_path())
    if isinstance(data, dict):
        for f in fields(Settings):
            if f.name not in data:
                continue
            value = data[f.name]
            default = getattr(settings, f.name)
            # Only accept a value of the same type as the default; ignore the rest.
            if default is None or value is None or type(value) is type(default):
                setattr(settings, f.name, value)
    settings.validate()
    return settings


def save_settings(settings: Settings, path: Path | None = None) -> bool:
    return _write_json(path or settings_path(), asdict(settings))


@dataclass(slots=True)
class HistoryEntry:
    expr: str
    result: str
    alt: str | None = None


@dataclass(slots=True)
class History:
    entries: list[HistoryEntry] = field(default_factory=list)

    def add(self, entry: HistoryEntry) -> None:
        self.entries.append(entry)
        del self.entries[:-HISTORY_LIMIT]

    def clear(self) -> None:
        self.entries.clear()


def load_history(path: Path | None = None) -> History:
    history = History()
    data = _read_json(path or history_path())
    if isinstance(data, list):
        for item in data[-HISTORY_LIMIT:]:
            if isinstance(item, dict) and isinstance(item.get("expr"), str) and isinstance(item.get("result"), str):
                alt = item.get("alt")
                history.entries.append(HistoryEntry(item["expr"], item["result"], alt if isinstance(alt, str) else None))
    return history


def save_history(history: History, path: Path | None = None) -> bool:
    return _write_json(path or history_path(), [asdict(e) for e in history.entries])


def delete_history_file(path: Path | None = None) -> None:
    try:
        (path or history_path()).unlink(missing_ok=True)
    except OSError:
        pass


def ensure_custom_units_file(path: Path | None = None) -> Path:
    """Create the custom units file with commented examples the first time round."""
    path = path or custom_units_path()
    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(CUSTOM_UNITS_TEMPLATE, encoding="utf-8")
        except OSError:
            pass
    return path
