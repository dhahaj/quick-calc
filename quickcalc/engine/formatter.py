"""Turns values into display strings according to the user's format settings."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .units import Quantity, Units

MODES = ("auto", "eng", "sci", "fixed")

_SI_LETTERS = {-15: "f", -12: "p", -9: "n", -6: "µ", -3: "m", 0: "", 3: "k", 6: "M", 9: "G", 12: "T"}

# Auto mode shows plain decimals inside this range and engineering notation outside it.
_AUTO_MIN = 1e-4
_AUTO_MAX = 1e12
_EXACT_INT_DIGITS = 21


@dataclass(slots=True)
class FormatSettings:
    mode: str = "auto"  # auto | eng | sci | fixed
    sig_figs: int = 10
    fixed_decimals: int = 4
    thousands_sep: bool = False
    show_int_bases: bool = False


def _digits(x: int | float, sig: int) -> tuple[str, int]:
    """Round to ``sig`` significant figures. Returns (digit string, power of ten of the
    first digit), so 0.000702 at 4 figures gives ("7020", -4)."""
    sig = max(1, min(sig, 17))
    text = f"{Decimal(abs(x)):.{sig - 1}e}"
    mantissa, exp = text.split("e")
    return mantissa.replace(".", ""), int(exp)


def _place(digits: str, point: int) -> str:
    """Put a decimal point after ``point`` digits and trim trailing zeros."""
    if point <= 0:
        text = "0." + "0" * (-point) + digits
    elif point >= len(digits):
        return digits + "0" * (point - len(digits))
    else:
        text = digits[:point] + "." + digits[point:]
    return text.rstrip("0").rstrip(".")


def _group(text: str) -> str:
    """Insert thousands separators into the integer part of a plain decimal string."""
    sign = "-" if text.startswith("-") else ""
    body = text[len(sign) :]
    whole, dot, frac = body.partition(".")
    if not whole.isdigit():
        return text
    return f"{sign}{int(whole):,}{dot}{frac}"


def _is_zero(x: int | float) -> bool:
    return x == 0


def format_number(x: int | float, s: FormatSettings, si_letters: bool = True) -> str:
    """Format a bare number. ``si_letters`` allows 'k', 'µ' ... in engineering mode."""
    if isinstance(x, float) and not math.isfinite(x):
        return "undefined" if math.isnan(x) else ("-∞" if x < 0 else "∞")
    sign = "-" if x < 0 else ""
    grouped = _group if s.thousands_sep else (lambda t: t)

    if s.mode == "fixed":
        text = f"{Decimal(x):.{max(0, s.fixed_decimals)}f}"
        if text.lstrip("-0.") == "":
            text = text.lstrip("-")
        return grouped(text)

    if _is_zero(x):
        return "0"

    if s.mode == "sci":
        digits, exp = _digits(x, s.sig_figs)
        return f"{sign}{_place(digits, 1)}e{exp}"

    if s.mode == "eng":
        return sign + _engineering(x, s.sig_figs, si_letters)

    # auto
    if isinstance(x, int):
        if len(str(abs(x))) <= _EXACT_INT_DIGITS:
            return grouped(str(x))
        return sign + _engineering(x, s.sig_figs, False)
    magnitude = abs(x)
    if x.is_integer() and magnitude < 1e15:
        return grouped(str(int(x)))
    if _AUTO_MIN <= magnitude < _AUTO_MAX:
        whole_digits = len(str(int(magnitude))) if magnitude >= 1 else 0
        digits, exp = _digits(x, max(s.sig_figs, whole_digits))
        return grouped(sign + _place(digits, exp + 1))
    return sign + _engineering(x, s.sig_figs, False)


def _engineering(x: int | float, sig: int, si_letters: bool) -> str:
    digits, exp = _digits(x, sig)
    exp3 = 3 * math.floor(exp / 3)
    mantissa = _place(digits, exp - exp3 + 1)
    if exp3 == 0:
        return mantissa
    if si_letters and exp3 in _SI_LETTERS:
        return f"{mantissa} {_SI_LETTERS[exp3]}"
    return f"{mantissa}e{exp3}"


def format_base(n: int, base: str) -> str:
    sign = "-" if n < 0 else ""
    n = abs(n)
    if base == "hex":
        return f"{sign}0x{n:X}"
    if base == "bin":
        return f"{sign}0b{n:b}"
    if base == "oct":
        return f"{sign}0o{n:o}"
    return f"{sign}{n}"


def _as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer() and abs(value) < 2**53:
        return int(value)
    return None


def _reprefix(q: Quantity, units: Units, sig: int) -> Quantity:
    """Pick the SI prefix that puts the magnitude in [1, 1000): 0.001915 A -> 1.915 mA."""
    info = units.prefix_info(q.units)
    if info is None or q.magnitude == 0:
        return q
    base, low, high = info
    try:
        in_base = q.to(units.with_prefix(base, 0))
        _, exp = _digits(in_base.magnitude, sig)
        exp3 = max(low, min(high, 3 * math.floor(exp / 3)))
        target = units.with_prefix(base, exp3)
        return q if target == q.units else in_base.to(target)
    except Exception:
        return q


def format_value(
    value: Any,
    s: FormatSettings,
    units: Units,
    locked: bool = False,
    base: str | None = None,
) -> tuple[str, str | None]:
    """Format a result. Returns (main text, optional secondary text).

    ``locked`` means the user asked for this exact unit, so no prefix is substituted.
    ``base`` is 'hex' / 'bin' / 'oct' / 'dec' for an explicit base conversion.
    """
    if base is not None:
        return format_base(int(value), base), (None if base == "dec" else str(int(value)))

    if isinstance(value, Quantity):
        q = value
        prefixed = False
        if not locked and s.mode in ("auto", "eng"):
            q = _reprefix(q, units, s.sig_figs)
            prefixed = units.prefix_info(q.units) is not None
        if prefixed and s.mode == "eng":
            # The unit prefix already carries the exponent.
            plain = FormatSettings("auto", s.sig_figs, s.fixed_decimals, s.thousands_sep)
            number = format_number(q.magnitude, plain)
        else:
            number = format_number(q.magnitude, s, si_letters=False)
        symbol = units.symbol(q.units)
        if not symbol:
            return number, None
        return (number + symbol if symbol == "°" else f"{number} {symbol}"), None

    text = format_number(value, s)
    alt: str | None = None
    if s.show_int_bases:
        n = _as_int(value)
        if n is not None and abs(n) < 2**64:
            alt = f"{format_base(n, 'hex')}  {format_base(n, 'bin')}"
    return text, alt
