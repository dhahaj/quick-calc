"""Session behaviour: ans, variables, live preview, error handling, and engine/GUI separation."""

from __future__ import annotations

import subprocess
import sys

import pytest

from quickcalc.engine import Engine

from .conftest import Calc

approx = pytest.approx


def test_ans(calc: Calc) -> None:
    assert "No previous result" in calc.err("ans")
    calc.ok("6 * 7")
    assert calc.num("ans") == 42
    assert calc.num("ans + 1") == 43
    assert calc.num("2ans") == 86
    assert calc.num("sqrt(ans)") == approx(86**0.5)


def test_ans_keeps_units(calc: Calc) -> None:
    calc.ok("9 V / 4.7 kohm")
    assert calc.text("ans * 1 kohm").endswith(" V")
    assert calc.text("ans to mV") == "1914.893617 mV"


def test_errors_do_not_change_ans(calc: Calc) -> None:
    calc.ok("5")
    calc.err("1/0")
    calc.err("1 +")
    assert calc.num("ans") == 5


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("*2", 20),
        ("/4", 2.5),
        ("+5", 15),
        ("^2", 100),
        ("**2", 100),
        ("|| 10", 5),
        ("& 2", 2),
        ("| 1", 11),
        ("<< 1", 20),
        (">> 1", 5),
        ("xor 3", 9),
        ("mod 3", 1),
    ],
)
def test_leading_operator(calc: Calc, line: str, expected: float) -> None:
    calc.ok("10")
    assert calc.num(line) == approx(expected)


def test_leading_minus_is_a_negative_number(calc: Calc) -> None:
    calc.ok("10")
    assert calc.num("-5") == -5
    assert calc.num("-5 + 3") == -2


def test_leading_operator_without_ans(calc: Calc) -> None:
    assert "No previous result" in calc.err("*2")


def test_variables(calc: Calc) -> None:
    result = calc.ok("r1 = 4.7k")
    assert result.name == "r1"
    assert result.value == 4700
    assert calc.num("r1") == 4700
    assert calc.num("r1 * 2") == 9400
    calc.ok("r2 = 10k")
    assert calc.num("r1 || r2") == approx(3197.2789, rel=1e-6)
    assert calc.num("vout = 3.3 * r2 / (r1 + r2)") == approx(2.2449, rel=1e-4)
    assert calc.num("vout") == approx(2.2449, rel=1e-4)


def test_variables_with_units(calc: Calc) -> None:
    calc.ok("v = 3.3 V")
    calc.ok("r = 330 ohm")
    assert calc.text("v / r") == "10 mA"
    calc.ok("w = 5 in to mm")
    assert calc.text("w") == "127 mm"


def test_variable_reassignment_and_ans(calc: Calc) -> None:
    calc.ok("x = 1")
    calc.ok("x = x + 1")
    assert calc.num("x") == 2
    calc.ok("y = 10")
    assert calc.num("ans") == 10


@pytest.mark.parametrize("name", ["pi", "e", "ans", "sqrt", "sin", "in", "hex", "max"])
def test_reserved_names(calc: Calc, name: str) -> None:
    assert "reserved" in calc.err(f"{name} = 5")


def test_keywords_cannot_be_assigned(calc: Calc) -> None:
    for name in ("to", "xor", "mod"):
        assert not calc.run(f"{name} = 5").ok


def test_unknown_symbol(calc: Calc) -> None:
    assert calc.err("foo + 1") == "Unknown name 'foo'"
    assert calc.err("r9 * 2") == "Unknown name 'r9'"


def test_clear(calc: Calc) -> None:
    calc.ok("x = 5")
    calc.engine.clear()
    assert "Unknown name 'x'" in calc.err("x")
    assert "No previous result" in calc.err("ans")


def test_preview_has_no_side_effects(calc: Calc) -> None:
    calc.ok("5")
    preview = calc.engine.preview("x = ans * 2")
    assert preview is not None and preview.text == "10"
    assert calc.num("ans") == 5
    assert "Unknown name 'x'" in calc.err("x")


@pytest.mark.parametrize("text", ["", "1 +", "2 *", "(", "sqrt(", "foo", "1/0", "5 kg to m", "5 m to", "4.7 k"])
def test_preview_is_silent_on_invalid_input(calc: Calc, text: str) -> None:
    assert calc.engine.preview(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1", "1"), ("1+", None), ("1+2", "3"), ("1+2*", None), ("1+2*(", None), ("1+2*(3", "7"), ("1+2*(3)", "7")],
)
def test_preview_while_typing(calc: Calc, text: str, expected: str | None) -> None:
    preview = calc.engine.preview(text)
    assert (preview.text if preview else None) == expected


def test_result_fields(calc: Calc) -> None:
    good = calc.run("  1 + 1  ")
    assert (good.ok, good.expr, good.text, good.display, good.error) == (True, "1 + 1", "2", "2", None)
    bad = calc.run("1/0")
    assert (bad.ok, bad.text, bad.display, bad.incomplete) == (False, "", "Division by zero", False)
    assert calc.run("1 +").incomplete is True


def test_engines_are_independent() -> None:
    a, b = Engine(), Engine()
    a.evaluate("x = 1")
    assert not b.evaluate("x").ok
    assert a.evaluate("5 m + 3 ft").ok and b.evaluate("5 m + 3 ft").ok


def test_engine_does_not_import_qt() -> None:
    code = (
        "import sys; import quickcalc.engine as e; e.Engine().evaluate('1 in to mm'); "
        "bad = [m for m in sys.modules if m.startswith(('PySide6', 'shiboken6', 'quickcalc.gui'))]; "
        "sys.exit(1 if bad else 0)"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0
