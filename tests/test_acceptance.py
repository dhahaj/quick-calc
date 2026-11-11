"""Every row of the acceptance table in the spec, plus the other examples it mentions."""

from __future__ import annotations

import pytest

from .conftest import Calc

approx = pytest.approx


def test_implicit_multiplication(calc: Calc) -> None:
    assert calc.num("2(3+4)") == 14
    assert calc.text("2(3+4)") == "14"


def test_power_and_sqrt(calc: Calc) -> None:
    assert calc.num("3^2 + sqrt(16)") == 13
    assert calc.text("3^2 + sqrt(16)") == "13"


def test_percent_of(calc: Calc) -> None:
    assert calc.num("80 * 15%") == approx(12)
    assert calc.text("80 * 15%") == "12"


def test_percent_add(calc: Calc) -> None:
    assert calc.num("200 + 10%") == 220
    assert calc.text("200 + 10%") == "220"


def test_parallel(calc: Calc) -> None:
    assert calc.num("4.7k || 10k") == approx(3197.2789, rel=1e-6)
    calc.fmt(mode="eng", sig_figs=4)
    assert calc.text("4.7k || 10k") == "3.197 k"


def test_engineering_mode(calc: Calc) -> None:
    assert calc.num("3.3 / 4.7k") == approx(702.1277e-6, rel=1e-6)
    calc.fmt(mode="eng", sig_figs=4)
    assert calc.text("3.3 / 4.7k") == "702.1 µ"


def test_ohms_law_with_units(calc: Calc) -> None:
    calc.fmt(sig_figs=4)
    assert calc.text("9 V / 4.7 kohm") == "1.915 mA"
    calc.fmt(mode="eng", sig_figs=4)
    assert calc.text("9 V / 4.7 kohm") == "1.915 mA"


def test_speed_times_time(calc: Calc) -> None:
    assert calc.text("60 mph * 2 h") == "120 mi"


def test_mil_to_mm(calc: Calc) -> None:
    assert calc.text("10 mil to mm") == "0.254 mm"


def test_mm_to_mil(calc: Calc) -> None:
    assert calc.num("1.6 mm to mil") == approx(62.99, abs=0.005)
    calc.fmt(sig_figs=4)
    assert calc.text("1.6 mm to mil") == "62.99 mil"


def test_fahrenheit_to_celsius(calc: Calc) -> None:
    assert calc.num("72 F to C") == approx(22.2222, abs=1e-4)
    calc.fmt(sig_figs=4)
    assert calc.text("72 F to C") == "22.22 °C"


def test_mph_to_kmh(calc: Calc) -> None:
    assert calc.num("60 mph to km/h") == approx(96.56064)
    calc.fmt(sig_figs=4)
    assert calc.text("60 mph to km/h") == "96.56 km/h"


def test_gib_to_mb(calc: Calc) -> None:
    assert calc.num("1 GiB to MB") == approx(1073.741824)
    calc.fmt(sig_figs=6)
    assert calc.text("1 GiB to MB") == "1073.74 MB"


def test_hex_plus_binary(calc: Calc) -> None:
    assert calc.num("0xFF + 0b1010") == 265
    assert calc.text("0xFF + 0b1010") == "265"


def test_to_hex(calc: Calc) -> None:
    assert calc.text("255 to hex") == "0xFF"
    assert calc.text("0x3F to bin") == "0b111111"
    assert calc.text("42 to oct") == "0o52"


def test_leading_operator_uses_ans(calc: Calc) -> None:
    calc.ok("0xFF + 0b1010")
    assert calc.num("*2") == 530
    assert calc.num("/3") == approx(530 / 3)


def test_division_by_zero_is_inline_error(calc: Calc) -> None:
    assert calc.err("1/0") == "Division by zero"
    assert calc.num("1+1") == 2  # still alive


def test_incompatible_conversion(calc: Calc) -> None:
    assert calc.err("5 kg to m") == "Can't convert mass to length"


def test_parallel_with_units(calc: Calc) -> None:
    assert calc.text("10 kohm || 10 kohm") == "5 kΩ"


def test_in_is_inch_or_keyword(calc: Calc) -> None:
    assert calc.text("5 in in mm") == "127 mm"
    assert calc.text("5 in to mm") == "127 mm"
    assert calc.num("5 mm in in") == approx(5 / 25.4)
    assert calc.text("5 in") == "5 in"
    assert calc.text("5 in * 2") == "10 in"
    assert calc.text("2 in + 3 in") == "5 in"


def test_compound_units(calc: Calc) -> None:
    assert calc.text("5 ft 3 in to cm") == "160.02 cm"
    assert calc.text("1 h 30 min to min") == "90 min"


def test_si_suffix_examples(calc: Calc) -> None:
    assert calc.num("4.7k") == 4700
    assert calc.num("100n") == approx(100e-9)
    assert calc.num("2.2u") == approx(2.2e-6)
    assert calc.num("2.2µ") == approx(2.2e-6)
    assert calc.num("10M") == 10_000_000
    assert calc.num("1G") == 1_000_000_000
    assert calc.num("33p") == approx(33e-12)


def test_m_is_milli_or_metre(calc: Calc) -> None:
    assert calc.num("10m") == approx(0.01)
    assert calc.text("10 m") == "10 m"
    assert calc.num("10 m to ft") == approx(32.8084, rel=1e-5)
    assert calc.num("10m to ft") == approx(32.8084, rel=1e-5)


def test_number_formats(calc: Calc) -> None:
    assert calc.num("0xFF") == 255
    assert calc.num("0b1010") == 10
    assert calc.num("0o17") == 15
    assert calc.num("1e-6") == approx(1e-6)
    assert calc.num("1_000_000") == 1_000_000


def test_float_noise_is_trimmed(calc: Calc) -> None:
    assert calc.text("0.1+0.2") == "0.3"


def test_variables(calc: Calc) -> None:
    assert calc.num("r1 = 4.7k") == 4700
    assert calc.num("r1 || 10k") == approx(3197.2789, rel=1e-6)


def test_copper_weight(calc: Calc) -> None:
    assert calc.num("1 oz_cu to mil") == approx(1.37)
    assert calc.num("2 oz_cu to mm") == approx(0.069596)


def test_dbm(calc: Calc) -> None:
    assert calc.num("20 dBm to mW") == approx(100)
    assert calc.num("100 mW to dBm") == approx(20)
    assert calc.num("0 dBm to mW") == approx(1)
