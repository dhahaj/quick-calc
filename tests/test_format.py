"""Output formatting: auto / engineering / scientific / fixed, sig figs, separators, bases."""

from __future__ import annotations

import pytest

from quickcalc.engine import FormatSettings
from quickcalc.engine.formatter import format_number

from .conftest import Calc


def fmt(x: float, **kwargs: object) -> str:
    return format_number(x, FormatSettings(**kwargs))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (0.0, "0"),
        (-0.0, "0"),
        (14, "14"),
        (-14, "-14"),
        (2.0, "2"),
        (0.5, "0.5"),
        (-0.5, "-0.5"),
        (0.1 + 0.2, "0.3"),
        (1 / 3, "0.3333333333"),
        (2 / 3, "0.6666666667"),
        (3197.278911564626, "3197.278912"),
        (0.0001, "0.0001"),
        (0.00012345, "0.00012345"),
        (0.00001234, "12.34e-6"),
        (0.0007021276595744681, "0.0007021276596"),
        (123456789.123, "123456789.1"),
        (999999999999.0, "999999999999"),
        (123456789012345.0, "123456789012345"),
        (1e15, "1e15"),
        (1.5e20, "150e18"),
        (1e-9, "1e-9"),
        (-2.5e-7, "-250e-9"),
        (6.02214076e23, "602.214076e21"),
        (2**64, "18446744073709551616"),
        (10**30, "1e30"),
        (0.9999999999999999, "1"),
        (999.99999999999, "1000"),
    ],
)
def test_auto(value: float, expected: str) -> None:
    assert fmt(value) == expected


@pytest.mark.parametrize(
    ("value", "sig", "expected"),
    [
        (0.0007021276595744681, 4, "702.1 µ"),
        (3197.278911564626, 4, "3.197 k"),
        (4700, 10, "4.7 k"),
        (265, 10, "265"),
        (1, 10, "1"),
        (0, 10, "0"),
        (0.015, 10, "15 m"),
        (1e-9, 10, "1 n"),
        (3.3e-12, 10, "3.3 p"),
        (2.5e-15, 10, "2.5 f"),
        (2.2e6, 10, "2.2 M"),
        (1e9, 10, "1 G"),
        (1e12, 10, "1 T"),
        (1e15, 10, "1e15"),  # beyond the prefix range: plain exponent
        (1e-18, 10, "1e-18"),
        (-0.0047, 10, "-4.7 m"),
        (999.96, 4, "1 k"),  # rounding carries into the next prefix
        (12345, 3, "12.3 k"),
    ],
)
def test_engineering(value: float, sig: int, expected: str) -> None:
    assert fmt(value, mode="eng", sig_figs=sig) == expected


@pytest.mark.parametrize(
    ("value", "sig", "expected"),
    [
        (0.0007021276595744681, 4, "7.021e-4"),
        (12345, 3, "1.23e4"),
        (1, 10, "1e0"),
        (0, 10, "0"),
        (-1500, 10, "-1.5e3"),
        (6.02214076e23, 10, "6.02214076e23"),
    ],
)
def test_scientific(value: float, sig: int, expected: str) -> None:
    assert fmt(value, mode="sci", sig_figs=sig) == expected


@pytest.mark.parametrize(
    ("value", "decimals", "expected"),
    [
        (3.14159, 2, "3.14"),
        (2, 2, "2.00"),
        (0.1 + 0.2, 4, "0.3000"),
        (2.675, 0, "3"),
        (-0.0001, 2, "0.00"),
        (1234.5, 1, "1234.5"),
        (0, 3, "0.000"),
    ],
)
def test_fixed(value: float, decimals: int, expected: str) -> None:
    assert fmt(value, mode="fixed", fixed_decimals=decimals) == expected


@pytest.mark.parametrize(
    ("value", "sig", "expected"),
    [
        (1 / 3, 3, "0.333"),
        (1 / 3, 15, "0.333333333333333"),
        (2 / 3, 1, "0.7"),
        (123.456, 4, "123.5"),
        (123456.789, 3, "123457"),  # never rounds away integer digits
        (0.1 + 0.2, 17, "0.30000000000000004"),
    ],
)
def test_significant_figures(value: float, sig: int, expected: str) -> None:
    assert fmt(value, sig_figs=sig) == expected


@pytest.mark.parametrize(
    ("value", "kwargs", "expected"),
    [
        (1234567, {}, "1,234,567"),
        (-1234567.891, {}, "-1,234,567.891"),
        (999, {}, "999"),
        (1000, {}, "1,000"),
        (0.000123, {}, "0.000123"),
        (1234567.5, {"mode": "fixed", "fixed_decimals": 2}, "1,234,567.50"),
        (2**64, {}, "18,446,744,073,709,551,616"),
    ],
)
def test_thousands_separators(value: float, kwargs: dict[str, object], expected: str) -> None:
    assert fmt(value, thousands_sep=True, **kwargs) == expected


def test_integer_bases_alongside(calc: Calc) -> None:
    assert calc.ok("265").alt is None
    calc.fmt(show_int_bases=True)
    assert calc.ok("0xFF + 0b1010").alt == "0x109  0b100001001"
    assert calc.ok("6 / 3").alt == "0x2  0b10"
    assert calc.ok("-1").alt == "-0x1  -0b1"
    assert calc.ok("1.5").alt is None
    assert calc.ok("5 V").alt is None


def test_modes_with_units(calc: Calc) -> None:
    calc.fmt(mode="eng", sig_figs=4)
    assert calc.text("9 V / 4.7 kohm") == "1.915 mA"
    assert calc.text("0.000702 A") == "702 µA"
    assert calc.text("0.00001 mi") == "10e-6 mi"  # no SI letters on non-SI units
    calc.fmt(mode="sci", sig_figs=4)
    assert calc.text("9 V / 4.7 kohm") == "1.915e-3 A"
    calc.fmt(mode="fixed", fixed_decimals=2)
    assert calc.text("10 mil to mm") == "0.25 mm"
    assert calc.text("1/3") == "0.33"


def test_reformat_for_clipboard(calc: Calc) -> None:
    calc.fmt(thousands_sep=True)
    result = calc.ok("1234 * 1000")
    assert result.text == "1,234,000"
    assert calc.engine.format_result(result, FormatSettings()) == "1234000"


def test_unit_symbols(calc: Calc) -> None:
    assert calc.text("1 kohm") == "1 kΩ"
    assert calc.text("1 uF") == "1 µF"
    assert calc.text("5 mil") == "5 mil"
    assert calc.text("45 deg") == "45°"
    assert calc.text("1 m/s^2") == "1 m/s²"
    assert calc.text("1 degF") == "1 °F"
    assert calc.text("1 GiB") == "1 GiB"
