"""Units: conversions, aliases, temperature, ambiguity rules, simplification, custom file."""

from __future__ import annotations

from pathlib import Path

import pytest

from quickcalc.engine import CUSTOM_UNITS_TEMPLATE, Engine

from .conftest import Calc

approx = pytest.approx


@pytest.mark.parametrize(
    ("text", "expected", "unit"),
    [
        # length
        ("1 in to mm", 25.4, "mm"),
        ("1 inch to mm", 25.4, "mm"),
        ("1 ft to in", 12, "in"),
        ("1 mi to km", 1.609344, "km"),
        ("1 yd to m", 0.9144, "m"),
        ("100 thou to mm", 2.54, "mm"),
        ("100 mils to mm", 2.54, "mm"),
        ("1 nmi to km", 1.852, "km"),
        ("1 um to nm", 1000, "nm"),
        # area and volume
        ("1 acre to m^2", 4046.8564224, "m²"),
        ("1 m^2 to ft^2", 10.76391041671, "ft²"),
        ("1 sqft to sqin", 144, "in²"),
        ("1 gal to L", 3.785411784, "L"),
        ("1 L to mL", 1000, "mL"),
        ("1 cup to floz", 8, "floz"),
        ("1 m^3 to L", 1000, "L"),
        # mass
        ("1 lb to kg", 0.45359237, "kg"),
        ("1 oz to g", 28.349523125, "g"),
        ("1 kg to lb", 2.2046226218, "lb"),
        # time
        ("1 h to min", 60, "min"),
        ("1 day to h", 24, "h"),
        ("1 week to day", 7, "d"),
        ("90 s to min", 1.5, "min"),
        # speed
        ("60 mph to km/h", 96.56064, "km/h"),
        ("100 km/h to mph", 62.1371192237, "mph"),
        ("1 knot to km/h", 1.852, "km/h"),
        ("10 m/s to km/h", 36, "km/h"),
        ("100 kph to m/s", 27.7777777778, "m/s"),
        # pressure
        ("1 atm to psi", 14.6959487755, "psi"),
        ("1 bar to kPa", 100, "kPa"),
        ("1 psi to kPa", 6.89475729317, "kPa"),
        # energy and power
        ("1 kWh to MJ", 3.6, "MJ"),
        ("1 cal to J", 4.184, "J"),
        ("1 BTU to J", 1055.056, "J"),
        ("1 hp to W", 745.699871582, "W"),
        ("1 eV to J", 1.602176634e-19, "J"),
        # force
        ("1 lbf to N", 4.4482216152605, "N"),
        ("1 kgf to N", 9.80665, "N"),
        # angle
        ("180 deg to rad", 3.14159265359, "rad"),
        ("pi rad to deg", 180, "°"),
        ("1 turn to deg", 360, "°"),
        # frequency
        ("60 rpm to Hz", 1, "Hz"),
        ("1 Hz to rpm", 60, "rpm"),
        ("1 kHz to Hz", 1000, "Hz"),
        ("60 rpm to rad/s", 6.28318530718, "rad/s"),
        # data
        ("1 GiB to MB", 1073.741824, "MB"),
        ("1 kB to B", 1000, "B"),
        ("1 KiB to B", 1024, "B"),
        ("1 MB to MiB", 0.95367431640625, "MiB"),
        ("1 B to bit", 8, "bit"),
        ("1 MB to Mb", 8, "Mbit"),
        ("100 Mbps to MB/s", 12.5, "MB/s"),
        # electrical
        ("1 kohm to ohm", 1000, "Ω"),
        ("4.7 kΩ to Ω", 4700, "Ω"),
        ("100 nF to uF", 0.1, "µF"),
        ("100 nF to µF", 0.1, "µF"),
        ("1 mAh to C", 3.6, "C"),
    ],
)
def test_conversions(calc: Calc, text: str, expected: float, unit: str) -> None:
    result = calc.ok(text)
    assert result.value.magnitude == approx(expected, rel=1e-9)
    assert result.text.rsplit(" ", 1)[-1] == unit or result.text.endswith(unit)


@pytest.mark.parametrize("keyword", ["to", "in", "->", "→"])
def test_conversion_keywords(calc: Calc, keyword: str) -> None:
    assert calc.text(f"1 ft {keyword} mm") == "304.8 mm"


def test_conversion_chain(calc: Calc) -> None:
    assert calc.text("1 ft to in to mm") == "304.8 mm"


def test_conversion_applies_to_whole_expression(calc: Calc) -> None:
    assert calc.text("1 ft + 6 in to mm") == "457.2 mm"
    assert calc.text("2 * 5 in to mm") == "254 mm"


def test_conversion_inside_parentheses_is_rejected(calc: Calc) -> None:
    assert "parentheses" in calc.err("(5 in to mm) * 2")


@pytest.mark.parametrize(
    ("text", "expected", "symbol"),
    [
        ("72 F to C", 22.2222222222, "°C"),
        ("72 degF to degC", 22.2222222222, "°C"),
        ("72 °F to °C", 22.2222222222, "°C"),
        ("72 fahrenheit to celsius", 22.2222222222, "°C"),
        ("100 C to F", 212, "°F"),
        ("0 C to K", 273.15, "K"),
        ("300 K to C", 26.85, "°C"),
        ("-40 F to C", -40, "°C"),
        ("-40 C to F", -40, "°F"),
        ("32 F to K", 273.15, "K"),
        ("72 F in C", 22.2222222222, "°C"),
        ("0 K to F", -459.67, "°F"),
    ],
)
def test_temperature(calc: Calc, text: str, expected: float, symbol: str) -> None:
    result = calc.ok(text)
    assert result.value.magnitude == approx(expected, abs=1e-8)
    assert result.text.endswith(" " + symbol)


def test_f_and_c_are_farad_and_coulomb_otherwise(calc: Calc) -> None:
    assert calc.text("100n F") == "100 nF"
    assert calc.text("1 C / 1 s") == "1 A"
    assert calc.text("10 uF to nF") == "10000 nF"
    assert calc.text("1 F to uF") == "1000000 µF"


def test_temperature_arithmetic(calc: Calc) -> None:
    assert calc.text("20 degC + 5 degC") == "25 °C"
    assert calc.text("25 degC - 20 degC") == "5 Δ°C"
    assert "same temperature unit" in calc.err("20 degC + 5 degF")


def test_in_edge_cases(calc: Calc) -> None:
    assert calc.text("1 in") == "1 in"
    assert calc.text("12 in to ft") == "1 ft"
    assert calc.text("1 ft in in") == "12 in"
    assert calc.text("1 m/s in in/s").endswith(" in/s")
    assert calc.text("3 in * 2 in") == "6 in²"
    assert calc.num("(2 in) / (1 in)") == 2
    assert "plain number" in calc.err("2 in mm")  # 'in' here is the keyword


def test_leading_conversion_uses_ans(calc: Calc) -> None:
    calc.ok("1 ft")
    assert calc.text("to mm") == "304.8 mm"
    assert calc.text("in in") == "12 in"
    assert calc.text("-> m") == "0.3048 m"
    calc.ok("255")
    assert calc.text("to hex") == "0xFF"


def test_base_conversion(calc: Calc) -> None:
    assert calc.text("255 to hex") == "0xFF"
    assert calc.text("255 to bin") == "0b11111111"
    assert calc.text("8 to oct") == "0o10"
    assert calc.text("0xFF to dec") == "255"
    assert calc.text("-255 to hex") == "-0xFF"
    assert calc.text("2^8 - 1 to hex") == "0xFF"
    assert calc.text("510 / 2 to hex") == "0xFF"
    assert calc.text("255 in hex") == "0xFF"
    assert calc.text("255 -> hex") == "0xFF"
    assert "whole numbers" in calc.err("1.5 to hex")
    assert "whole numbers" in calc.err("5 V to hex")
    assert calc.num("255 to hex") == 255  # ans stays a number
    assert calc.num("ans + 1") == 256


def test_compound_input(calc: Calc) -> None:
    assert calc.num("5 ft 3 in") == approx(5.25)
    assert calc.text("5 ft 3 in") == "5.25 ft"
    assert calc.text("5 ft 3 in to cm") == "160.02 cm"
    assert calc.text("1 h 30 min") == "1.5 h"
    assert calc.text("1 h 30 min 30 s to s") == "5430 s"
    assert calc.text("2 lb 8 oz to lb") == "2.5 lb"
    # Different kinds of unit side by side are still multiplied.
    assert calc.text("2 N 3 m") == "6 J"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("9 V / 4.7 kohm", "1.914893617 mA"),
        ("5 V * 2 mA", "10 mW"),
        ("12 V / 0.5 A", "24 Ω"),
        ("2 A * 10 ohm", "20 V"),
        ("3.3 V / 10 kΩ", "330 µA"),
        ("(5 V)^2 / 100 ohm", "250 mW"),
        ("1 / (1 kHz)", "1 ms"),
        ("1 / (2 pi * 1 kohm * 100 nF)", "1.591549431 kHz"),
        ("1 kohm * 1 uF", "1 ms"),
        ("60 mph * 2 h", "120 mi"),
        ("100 km / 2 h", "50 km/h"),
        ("120 mi / 2 h", "60 mi/h"),
        ("3 ft * 2 ft", "6 ft²"),
        ("2 m * 50 cm", "1 m²"),
        ("10 m / 2 m", "5"),
        ("1 kohm / 1 ohm", "1000"),
        ("1 GiB / 1 MiB", "1024"),
        ("100 MB / 4 s", "25 MB/s"),
        ("10 Mbps * 60 s to MB", "75 MB"),
        ("5 mm * 5 cm", "2.5 cm²"),
        ("1 kohm * 1 uF", "1 ms"),
        ("500 mA * 2 h", "1 Ah"),
        ("100 W * 3 h", "300 Wh"),
        ("1 kWh / 2 h", "500 W"),
        ("5 psi * 2 in^2", "10 lbf"),
        ("10 N * 2 m", "20 J"),
        ("1 kg * 9.81 m/s^2", "9.81 N"),
        ("sqrt(16 m^2)", "4 m"),
        ("2 * 3 V", "6 V"),
        ("1 V + 500 mV", "1.5 V"),
        ("1 ft + 1 in", "1.083333333 ft"),
        ("-5 V", "-5 V"),
        ("abs(-5 V)", "5 V"),
        ("max(1 ft, 10 in)", "1 ft"),
        ("min(1 ft, 10 in)", "10 in"),
        ("200 V + 10%", "220 V"),
        ("10 m^2", "10 m²"),
        ("5 kg m/s^2", "5 N"),
    ],
)
def test_unit_arithmetic(calc: Calc, text: str, expected: str) -> None:
    assert calc.text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.5 V", "500 mV"),
        ("4700 ohm", "4.7 kΩ"),
        ("0.0000001 F", "100 nF"),
        ("2.4e9 Hz", "2.4 GHz"),
        ("1500 m", "1.5 km"),
        ("0.5 km", "500 m"),
        ("5000 kg", "5000 kg"),  # no megagrams
        ("3600 s", "3600 s"),  # no kiloseconds
        ("0.001 s", "1 ms"),
        ("2.54 cm", "2.54 cm"),  # centi is left alone
        ("0.5 mi", "0.5 mi"),  # not an SI unit
        ("5 kΩ", "5 kΩ"),
        ("0 V", "0 V"),
    ],
)
def test_auto_prefix(calc: Calc, text: str, expected: str) -> None:
    assert calc.text(text) == expected


def test_explicit_target_is_never_reprefixed(calc: Calc) -> None:
    assert calc.text("10 mil to mm") == "0.254 mm"
    assert calc.text("1 km to m") == "1000 m"
    assert calc.text("1 mA to A") == "0.001 A"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("5 kg to m", "Can't convert mass to length"),
        ("5 V to A", "Can't convert voltage to current"),
        ("1 GiB to m", "Can't convert data size to length"),
        ("30 deg to m", "Can't convert angle to length"),
        ("1 MB to rad", "Can't convert data size to angle"),
        ("5 to m", "Can't convert a plain number to length"),
        ("5 m + 3", "Can't add length and a plain number"),
        ("3 - 5 m", "Can't subtract a plain number and length"),
        ("5 m + 3 s", "Can't add length and time"),
        ("5 m to xyz", "Unknown unit 'xyz'"),
        ("5 xyz", "Unknown name 'xyz'"),
        ("2 ^ (3 m)", "An exponent must be a plain number, not length"),
    ],
)
def test_unit_errors(calc: Calc, text: str, message: str) -> None:
    assert calc.err(text) == message


def test_glued_m_g_t(calc: Calc) -> None:
    # With no other units on the line, a glued m / G / T is an SI prefix.
    assert calc.num("10m") == approx(0.01)
    assert calc.num("3.3 / 10m") == approx(330)
    assert calc.num("1G") == 1e9
    # With other units on the line, it is the unit.
    assert calc.text("10m/s") == "10 m/s"
    assert calc.text("3m + 20cm") == "3.2 m"
    assert calc.text("10m to ft").endswith(" ft")
    assert calc.text("5m * 2 m") == "10 m²"
    # Unambiguous spellings never depend on context.
    assert calc.text("10mm") == "10 mm"
    assert calc.text("4.7kohm") == "4.7 kΩ"
    assert calc.text("10mA") == "10 mA"
    assert calc.text("5V") == "5 V"
    assert calc.text("100n F") == "100 nF"
    assert calc.text("4.7k ohm") == "4.7 kΩ"


def test_single_letter_constants_are_not_units(calc: Calc) -> None:
    for name in ("k", "u", "M", "R", "a"):
        assert calc.err(name) == f"Unknown name '{name}'"


def test_variables_shadow_units(calc: Calc) -> None:
    calc.ok("m = 3")
    assert calc.num("2 m") == 6
    assert calc.text("2 mm") == "2 mm"


def test_speed_of_light(calc: Calc) -> None:
    assert calc.num("c / 2.4 GHz to cm") == approx(12.4913524, rel=1e-8)


def test_db_arithmetic_is_refused(calc: Calc) -> None:
    assert "dB" in calc.err("10 dBm + 3 dBm")
    assert "dB" in calc.err("2 * 10 dBm")


# ----------------------------------------------------------------- custom units file


def test_custom_units_file(tmp_path: Path) -> None:
    path = tmp_path / "units.txt"
    path.write_text("# comment\nsmoot = 1.7018 * meter\nrack_unit = 1.75 * inch = RU\n", encoding="utf-8")
    engine = Engine(custom_units_path=path)
    assert engine.warnings == []
    assert engine.evaluate("1 smoot to m").text == "1.7018 m"
    assert engine.evaluate("2 RU to in").text == "3.5 in"
    assert engine.evaluate("1 oz_cu to mil").text == "1.37 mil"  # built-in fallback


def test_custom_units_template_is_valid(tmp_path: Path) -> None:
    path = tmp_path / "units.txt"
    path.write_text(CUSTOM_UNITS_TEMPLATE, encoding="utf-8")
    engine = Engine(custom_units_path=path)
    assert engine.warnings == []
    assert engine.evaluate("1 oz_cu to mil").text == "1.37 mil"


def test_custom_units_can_redefine_copper_weight(tmp_path: Path) -> None:
    path = tmp_path / "units.txt"
    path.write_text("oz_cu = 1.4 * thou\n", encoding="utf-8")
    engine = Engine(custom_units_path=path)
    assert engine.evaluate("1 oz_cu to mil").text == "1.4 mil"


def test_bad_custom_units_lines_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "units.txt"
    path.write_text("this is not a definition\nbroken = 3 * nosuchunit\nsmoot = 1.7018 * meter\n", encoding="utf-8")
    engine = Engine(custom_units_path=path)
    assert len(engine.warnings) == 2
    assert "line 1" in engine.warnings[0]
    assert "line 2" in engine.warnings[1]
    assert engine.evaluate("1 smoot to m").text == "1.7018 m"
    assert engine.evaluate("1 + 1").text == "2"


def test_missing_custom_units_file_is_not_fatal(tmp_path: Path) -> None:
    engine = Engine(custom_units_path=tmp_path / "nope.txt")
    assert len(engine.warnings) == 1
    assert engine.evaluate("1 + 1").text == "2"
