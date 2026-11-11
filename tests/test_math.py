"""Grammar and arithmetic: precedence, implicit multiplication, percent, functions, bitwise."""

from __future__ import annotations

import math

import pytest

from .conftest import Calc

approx = pytest.approx


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 + 2 * 3", 7),
        ("(1 + 2) * 3", 9),
        ("10 - 4 - 3", 3),
        ("2 ^ 3 ^ 2", 512),
        ("2 ** 10", 1024),
        ("-2 ^ 2", -4),
        ("(-2) ^ 2", 4),
        ("2 ^ -1", 0.5),
        ("--3", 3),
        ("(+5)", 5),
        ("6 / 3", 2),
        ("7 / 2", 3.5),
        ("1 - -1", 2),
        ("2 * -3", -6),
        (".5 + .5", 1),
        ("5.", 5),
        ("1e3", 1000),
        ("1E3", 1000),
        ("1.5e-3", 0.0015),
        ("10 mod 3", 1),
        ("10 % 3", 1),
        ("2 × 3", 6),
        ("6 ÷ 3", 2),
        ("5 − 2", 3),
        ("3²", 9),
        ("2³", 8),
    ],
)
def test_arithmetic(calc: Calc, text: str, expected: float) -> None:
    assert calc.num(text) == approx(expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2(3+4)", 14),
        ("(1+2)(3+4)", 21),
        ("2pi", 2 * math.pi),
        ("2 pi", 2 * math.pi),
        ("2π", 2 * math.pi),
        ("3sqrt(2)", 3 * math.sqrt(2)),
        ("(2)3", 6),
        ("2(3)(4)", 24),
        ("2pi^2", 2 * math.pi**2),  # power binds tighter than adjacency
        ("1/2pi", 1 / (2 * math.pi)),  # adjacency binds tighter than division
        ("-2pi", -2 * math.pi),
        ("2e", 2 * math.e),
        ("2 e", 2 * math.e),
    ],
)
def test_implicit_multiplication(calc: Calc, text: str, expected: float) -> None:
    assert calc.num(text) == approx(expected)


def test_implicit_with_variables(calc: Calc) -> None:
    calc.ok("x = 3")
    assert calc.num("2x") == 6
    assert calc.num("x x") == 9
    assert calc.num("2x^2") == 18
    assert calc.num("x(x+1)") == 12


def test_two_numbers_side_by_side_is_an_error(calc: Calc) -> None:
    assert "operator" in calc.err("2 3")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("80 * 15%", 12),
        ("200 + 10%", 220),
        ("200 - 10%", 180),
        ("15%", 0.15),
        ("50% * 50%", 0.25),
        ("100 * (5 + 5)%", 10),
        ("200 + 10% + 10%", 242),  # each percent applies to the running total
        ("10% + 5", 5.1),  # percent on the left is just 0.1
        ("1000 * 5% * 2", 100),
        ("200 / 50%", 400),
    ],
)
def test_percent(calc: Calc, text: str, expected: float) -> None:
    assert calc.num(text) == approx(expected)


def test_percent_keeps_integers_exact(calc: Calc) -> None:
    assert calc.ok("200 + 10%").value == 220
    assert isinstance(calc.ok("200 + 10%").value, int)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("sqrt(16)", 4),
        ("sqrt(2)", math.sqrt(2)),
        ("√16", 4),
        ("√(9+16)", 5),
        ("√16 + 9", 13),
        ("cbrt(27)", 3),
        ("cbrt(-8)", -2),
        ("abs(-3.5)", 3.5),
        ("round(2.5)", 2),
        ("round(3.14159, 2)", 3.14),
        ("round(1234, -2)", 1200),
        ("floor(2.7)", 2),
        ("floor(-2.7)", -3),
        ("ceil(2.1)", 3),
        ("log(1000)", 3),
        ("log(8, 2)", 3),
        ("ln(e)", 1),
        ("ln(e^2)", 2),
        ("log2(1024)", 10),
        ("exp(0)", 1),
        ("exp(1)", math.e),
        ("sin(0)", 0),
        ("sin(pi/2)", 1),
        ("sin(pi)", 0),
        ("cos(0)", 1),
        ("cos(pi/2)", 0),
        ("tan(pi/4)", 1),
        ("asin(1)", math.pi / 2),
        ("acos(1)", 0),
        ("atan(1)", math.pi / 4),
        ("atan2(1, 1)", math.pi / 4),
        ("atan2(1, -1)", 3 * math.pi / 4),
        ("min(3, 1, 2)", 1),
        ("max(3, 1, 2)", 3),
        ("max(2)", 2),
        ("min(1, 2) + max(3, 4)", 5),
    ],
)
def test_functions_radians(calc: Calc, text: str, expected: float) -> None:
    assert calc.num(text) == approx(expected, abs=1e-12)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("sin(30)", 0.5),
        ("cos(60)", 0.5),
        ("tan(45)", 1),
        ("sin(180)", 0),
        ("asin(0.5)", 30),
        ("acos(0.5)", 60),
        ("atan(1)", 45),
        ("atan2(1, 1)", 45),
        ("sin(pi rad)", 0),  # an explicit unit beats the degrees setting
        ("sin(30 deg)", 0.5),
    ],
)
def test_functions_degrees(calc: Calc, text: str, expected: float) -> None:
    calc.engine.degrees = True
    assert calc.num(text) == approx(expected, abs=1e-9)


def test_explicit_degrees_in_radian_mode(calc: Calc) -> None:
    assert calc.num("sin(30 deg)") == approx(0.5)
    assert calc.num("sin(30°)") == approx(0.5)
    assert calc.num("cos(60 deg)") == approx(0.5)


def test_integer_results_stay_integers(calc: Calc) -> None:
    for text in ("sqrt(16)", "6/3", "2^10", "abs(-4)", "floor(2.5)", "round(2.6)", "cbrt(27)"):
        assert isinstance(calc.ok(text).value, int), text


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("sqrt(-1)", "negative"),
        ("log(0)", "positive"),
        ("ln(-1)", "positive"),
        ("asin(2)", "between"),
        ("acos(-2)", "between"),
        ("tan(pi/2)", "undefined"),
        ("sqrt()", "1 argument"),
        ("sqrt(1, 2)", "1 argument"),
        ("atan2(1)", "2 arguments"),
        ("min()", "at least 1"),
        ("(-8)^(1/3)", "real"),
        ("0^-1", "zero"),
        ("5 mod 0", "zero"),
        ("sqrt", "parentheses"),
    ],
)
def test_function_errors(calc: Calc, text: str, fragment: str) -> None:
    assert fragment in calc.err(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0xF0 & 0x3C", 0x30),
        ("0xF0 | 0x0F", 0xFF),
        ("5 xor 3", 6),
        ("1 << 4", 16),
        ("256 >> 4", 16),
        ("~0", -1),
        ("~5 & 0xF", 10),
        ("1 << 4 | 1", 17),
        ("1 | 2 & 3", 3),  # & binds tighter than |
        ("1 + 1 << 2", 8),  # arithmetic binds tighter than shifts
        ("6 & 3 xor 1", 3),
        ("0xFF & ~0x0F", 0xF0),
        ("2^4 & 0xFF", 16),
    ],
)
def test_bitwise(calc: Calc, text: str, expected: int) -> None:
    assert calc.num(text) == expected


def test_bitwise_needs_integers(calc: Calc) -> None:
    assert "whole numbers" in calc.err("1.5 & 3")
    assert "whole numbers" in calc.err("3 << 0.5")
    assert "negative" in calc.err("1 << -1")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10 || 10", 5),
        ("4.7k || 10k", 3197.278911564626),
        ("1k || 1k || 1k", 1000 / 3),
        ("2 * 10 || 10", 10),  # || binds tighter than *
        ("10 + 10 || 10", 15),
        ("100 / 10 || 10", 20),
        ("0 || 5", 0),
    ],
)
def test_parallel(calc: Calc, text: str, expected: float) -> None:
    assert calc.num(text) == approx(expected)


def test_parallel_errors(calc: Calc) -> None:
    assert calc.err("5 || -5") == "Division by zero"
    assert "parallel" in calc.err("10 ohm || 10")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1f", 1e-15),
        ("1p", 1e-12),
        ("1n", 1e-9),
        ("1u", 1e-6),
        ("1µ", 1e-6),
        ("1m", 1e-3),
        ("1k", 1e3),
        ("1M", 1e6),
        ("1G", 1e9),
        ("1T", 1e12),
        ("4.7k", 4700),
        ("0.1u", 1e-7),
        ("1.5k + 500", 2000),
        ("2k * 3k", 6e6),
        ("3.3 / 4.7k", 3.3 / 4700),
        ("1 / 2k", 1 / 2000),
        ("2k^2", 4e6),
        ("10k(2)", 20000),
        ("1e3k", 1e6),
    ],
)
def test_si_suffixes(calc: Calc, text: str, expected: float) -> None:
    assert calc.num(text) == approx(expected, rel=1e-12)


def test_si_suffix_precision(calc: Calc) -> None:
    # Scaled as decimal text, not by float multiplication, so no stray digits appear.
    assert calc.ok("4.7k").value == 4700.0
    assert calc.ok("2.2u").value == 2.2e-6
    assert calc.ok("100n").value == 1e-7
    assert isinstance(calc.ok("10M").value, int)


def test_suffix_needs_no_space(calc: Calc) -> None:
    # With a space, k is no longer a suffix (and is not a unit either).
    assert "Unknown name 'k'" in calc.err("4.7 k")


def test_big_numbers_do_not_hang(calc: Calc) -> None:
    assert calc.err("9^9^9") == "Result is too large"
    assert calc.err("1 << 100000") == "Result is too large"
    assert calc.num("2^64") == 2**64
    assert calc.text("2^64") == "18446744073709551616"
    assert calc.err("10.0^400") == "Result is too large"


def test_cancellation_noise(calc: Calc) -> None:
    assert calc.num("0.3 - 0.1 - 0.2") == 0
    assert calc.num("1 - 0.9 - 0.1") == 0


@pytest.mark.parametrize(
    "text",
    ["", "   ", "1 +", "(", "2 *", "sqrt(", "1 + * 2", ")", "2 ) 3", "1 $ 2", "a b =", "= 5", "5 = 5", "1,2", "to"],
)
def test_bad_syntax_is_an_error_not_a_crash(calc: Calc, text: str) -> None:
    result = calc.run(text)
    assert not result.ok
    assert result.error


def test_missing_close_paren_is_forgiven(calc: Calc) -> None:
    assert calc.num("2(3+4") == 14
    assert calc.num("sqrt(16") == 4


def test_deep_nesting_does_not_crash(calc: Calc) -> None:
    result = calc.run("(" * 5000 + "1" + ")" * 5000)
    assert not result.ok
    assert calc.num("1+1") == 2


def test_garbage_never_raises(calc: Calc) -> None:
    for text in ["🙂", "1 ++ 2", "((((", "0x", "1e", "1..2", "@#!", "in", "to to", "a = b = 1", "\x00", "5 5 5", "%", "~", "||"]:
        calc.run(text)  # must simply return
