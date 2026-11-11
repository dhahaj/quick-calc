"""Settings/history persistence and hotkey parsing. None of this needs Qt."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quickcalc import config
from quickcalc.config import History, HistoryEntry, Settings
from quickcalc.engine import Engine
from quickcalc.winplatform import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, launch_command, parse_hotkey


def test_settings_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "QuickCalc" / "settings.json"
    settings = Settings(hotkey="Ctrl+Shift+Space", show_keypad=True, sig_figs=6, last_offset=[10, 20], theme="dark")
    assert config.save_settings(settings, path)
    assert config.load_settings(path) == settings


def test_missing_or_corrupt_settings_fall_back_to_defaults(tmp_path: Path) -> None:
    assert config.load_settings(tmp_path / "nope.json") == Settings()
    bad = tmp_path / "settings.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert config.load_settings(bad) == Settings()
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    assert config.load_settings(bad) == Settings()


def test_bad_values_are_ignored_or_clamped(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "sig_figs": 99,
                "fixed_decimals": -3,
                "theme": "neon",
                "format_mode": "roman",
                "show_keypad": "yes",  # wrong type: ignored
                "hotkey": "  ",
                "last_offset": [1, "two"],
                "unknown_key": 1,
                "angle_mode": "deg",
            }
        ),
        encoding="utf-8",
    )
    settings = config.load_settings(path)
    assert settings.sig_figs == 15
    assert settings.fixed_decimals == 0
    assert settings.theme == "system"
    assert settings.format_mode == "auto"
    assert settings.show_keypad is False
    assert settings.hotkey == config.DEFAULT_HOTKEY
    assert settings.last_offset is None
    assert settings.angle_mode == "deg"


def test_defaults_match_the_spec() -> None:
    s = Settings()
    assert s.hotkey == "Ctrl+Alt+C"
    assert s.format_mode == "auto"
    assert s.sig_figs == 10
    assert s.persist_history is True
    assert s.copy_on_enter is True
    assert s.theme == "system"


def test_format_settings_bridge() -> None:
    fmt = Settings(format_mode="eng", sig_figs=4, thousands_sep=True, show_int_bases=True).format_settings()
    assert (fmt.mode, fmt.sig_figs, fmt.thousands_sep, fmt.show_int_bases) == ("eng", 4, True, True)


def test_history_roundtrip_and_cap(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    history = History()
    for i in range(config.HISTORY_LIMIT + 50):
        history.add(HistoryEntry(f"{i}+1", str(i + 1)))
    assert len(history.entries) == config.HISTORY_LIMIT
    assert history.entries[0].expr == "50+1"
    assert config.save_history(history, path)
    loaded = config.load_history(path)
    assert loaded.entries == history.entries


def test_history_tolerates_junk(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    path.write_text(json.dumps([{"expr": "1+1", "result": "2"}, {"expr": 5}, "x", None]), encoding="utf-8")
    assert config.load_history(path).entries == [HistoryEntry("1+1", "2")]
    path.write_text("garbage", encoding="utf-8")
    assert config.load_history(path).entries == []
    config.delete_history_file(path)
    assert not path.exists()
    config.delete_history_file(path)  # deleting twice is fine


def test_custom_units_file_is_created_once(tmp_path: Path) -> None:
    path = tmp_path / "QuickCalc" / "units.txt"
    assert config.ensure_custom_units_file(path) == path
    assert "oz_cu" in path.read_text(encoding="utf-8")
    path.write_text("smoot = 1.7018 * meter\n", encoding="utf-8")
    config.ensure_custom_units_file(path)
    assert path.read_text(encoding="utf-8") == "smoot = 1.7018 * meter\n"  # never overwritten
    assert Engine(custom_units_path=path).evaluate("1 smoot to m").text == "1.7018 m"


def test_app_dir_follows_appdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.settings_path() == tmp_path / "QuickCalc" / "settings.json"
    assert config.history_path().parent == config.custom_units_path().parent == tmp_path / "QuickCalc"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ctrl+Alt+C", (MOD_CONTROL | MOD_ALT, ord("C"))),
        ("ctrl+alt+c", (MOD_CONTROL | MOD_ALT, ord("C"))),
        ("Ctrl + Shift + Space", (MOD_CONTROL | MOD_SHIFT, 0x20)),
        ("Win+Shift+F1", (MOD_WIN | MOD_SHIFT, 0x70)),
        ("Meta+Alt+9", (MOD_WIN | MOD_ALT, ord("9"))),
        ("F12", (0, 0x7B)),
        ("Ctrl+Alt+PgUp", (MOD_CONTROL | MOD_ALT, 0x21)),
        ("Ctrl+Alt+Return", (MOD_CONTROL | MOD_ALT, 0x0D)),
        ("Ctrl+Alt+=", (MOD_CONTROL | MOD_ALT, 0xBB)),
        ("Ctrl++", (MOD_CONTROL, 0xBB)),
        ("Alt+`", (MOD_ALT, 0xC0)),
    ],
)
def test_parse_hotkey(text: str, expected: tuple[int, int]) -> None:
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize("text", ["", "C", "5", "Space", "Ctrl+", "Ctrl+Alt", "Hyper+C", "Ctrl+Nope", "Ctrl+F25", "Ctrl++C"])
def test_parse_hotkey_rejects(text: str) -> None:
    assert parse_hotkey(text) is None


def test_launch_command_from_source() -> None:
    command = launch_command("--tray")
    assert command.endswith(" --tray")
    assert "__main__.py" in command and command.startswith('"')
