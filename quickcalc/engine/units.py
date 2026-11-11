"""The Pint unit registry plus the QuickCalc-specific layer on top of it:
friendly aliases, the user's custom units file, result simplification and unit symbols.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import pint

from .errors import EvalError, UnitMismatchError

Quantity = pint.Quantity
Unit = pint.Unit

# Pint is chatty about redefinitions; a calculator has nowhere useful to print that.
logging.getLogger("pint").setLevel(logging.ERROR)

CUSTOM_UNITS_TEMPLATE = """\
# QuickCalc custom units
#
# One definition per line, in Pint syntax:   name = value * unit [= alias1 = alias2]
# Lines starting with # are ignored. Restart QuickCalc after editing this file.
# A line that can't be read is skipped; it never stops the app from starting.
#
# Copper weight: 1 oz/ft^2 of copper is 1.37 mil thick.
#   2 oz_cu to mm   ->  0.069596 mm
oz_cu = 1.37 * thou

# More examples (remove the leading # to enable):
# smoot = 1.7018 * meter
# rack_unit = 1.75 * inch = RU
# furlong_per_fortnight = furlong / fortnight = fpf
"""

# Friendly spellings -> a Pint unit expression (always one of ours, never user text).
_ALIASES: dict[str, str] = {
    "mil": "thou",
    "mils": "thou",
    "b": "bit",
    "kb": "kilobit",
    "Kb": "kilobit",
    "Mb": "megabit",
    "Gb": "gigabit",
    "Tb": "terabit",
    "bps": "bit / second",
    "kbps": "kilobit / second",
    "Mbps": "megabit / second",
    "Gbps": "gigabit / second",
    "Ohm": "ohm",
    "ohms": "ohm",
    "Ohms": "ohm",
    "degK": "kelvin",
    "°K": "kelvin",
    "celsius": "degC",
    "fahrenheit": "degF",
    "hrs": "hour",
    "mins": "minute",
    "secs": "second",
    "wk": "week",
    "°": "degree",
    "sqft": "foot ** 2",
    "sqin": "inch ** 2",
    "sqm": "meter ** 2",
    "sqmi": "mile ** 2",
    "cuft": "foot ** 3",
    "cuin": "inch ** 3",
}

# Physical constants that Pint exposes under one letter. As bare symbols in a
# calculator they are far more likely to be typos or unset variables.
_BLOCKED = frozenset({"k", "u", "M", "R", "a"})

_TEMPERATURE_LETTERS = {"F": "degF", "C": "degC"}

_SYMBOL_OVERRIDES = {"thou": "mil", "degree": "°", "liter": "L", "milliliter": "mL", "microliter": "µL"}

_SUPERSCRIPTS = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")

# Named units to land on when a compound result has one of these dimensions.
_PREFERRED = ("ampere", "volt", "ohm", "siemens", "farad", "henry", "watt", "joule",
              "coulomb", "hertz", "newton", "pascal", "weber", "tesla", "second")  # fmt: skip

_DIMENSION_NAMES = {
    "meter": "length",
    "kilogram": "mass",
    "second": "time",
    "kelvin": "temperature",
    "ampere": "current",
    "mole": "amount of substance",
    "candela": "luminous intensity",
    "meter ** 2": "area",
    "meter ** 3": "volume",
    "meter / second": "speed",
    "meter / second ** 2": "acceleration",
    "kilogram / meter ** 3": "density",
    "newton": "force",
    "pascal": "pressure",
    "joule": "energy",
    "watt": "power",
    "hertz": "frequency",
    "volt": "voltage",
    "ohm": "resistance",
    "siemens": "conductance",
    "farad": "capacitance",
    "henry": "inductance",
    "coulomb": "charge",
    "weber": "magnetic flux",
    "tesla": "magnetic flux density",
}

# Units that get an automatic SI prefix on output: name -> (lowest, highest) power of ten.
_PREFIXABLE: dict[str, tuple[int, int]] = {
    "volt": (-15, 12),
    "ampere": (-15, 12),
    "ohm": (-15, 12),
    "siemens": (-15, 12),
    "farad": (-15, 12),
    "henry": (-15, 12),
    "watt": (-15, 12),
    "hertz": (-15, 12),
    "joule": (-15, 12),
    "pascal": (-15, 12),
    "newton": (-15, 12),
    "coulomb": (-15, 12),
    "weber": (-15, 12),
    "tesla": (-15, 12),
    "electron_volt": (-15, 12),
    "watt_hour": (-3, 12),
    "ampere_hour": (-6, 3),
    "second": (-15, 0),
    "meter": (-15, 3),
    "gram": (-9, 3),
    "liter": (-6, 0),
}

_PREFIX_NAMES = {
    -15: "femto", -12: "pico", -9: "nano", -6: "micro", -3: "milli", 0: "",
    3: "kilo", 6: "mega", 9: "giga", 12: "tera",
}  # fmt: skip
_PREFIX_EXPONENTS = {name: exp for exp, name in _PREFIX_NAMES.items()}


class Units:
    """Owns the Pint registry. One instance per engine."""

    def __init__(self, custom_units_path: Path | None = None) -> None:
        self.ureg = pint.UnitRegistry(autoconvert_offset_to_baseunit=True, on_redefinition="ignore")
        self.warnings: list[str] = []
        self._cache: dict[tuple[str, bool], Unit | None] = {}
        if custom_units_path is not None:
            self._load_custom(custom_units_path)
        if not self._defined("oz_cu"):
            self.ureg.define("oz_cu = 1.37 * thou")
        self._preferred = {self.ureg.Unit(n).dimensionality: self.ureg.Unit(n) for n in _PREFERRED}
        self._dim_names = {
            self.ureg.Unit(expr).dimensionality: name for expr, name in _DIMENSION_NAMES.items()
        }
        self._radian = self.ureg.Unit("radian")

    def quantity(self, magnitude: Any, units: Any) -> Quantity:
        """Build a quantity in *this* registry (Pint refuses to mix registries)."""
        return self.ureg.Quantity(magnitude, units)

    # ------------------------------------------------------------------ definitions

    def _defined(self, name: str) -> bool:
        try:
            return bool(self.ureg.get_name(name))
        except Exception:
            return False

    def _load_custom(self, path: Path) -> None:
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except OSError as exc:
            self.warnings.append(f"Couldn't read {path.name}: {exc.strerror or exc}")
            return
        for number, line in enumerate(lines, 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            try:
                self.ureg.define(line)
                # Force Pint to resolve the definition now so a bad one is caught here.
                self.ureg.Quantity(1, line.split("=", 1)[0].strip()).to_root_units()
            except Exception as exc:
                self.warnings.append(f"{path.name} line {number} skipped: {exc}")

    # ----------------------------------------------------------------------- lookup

    def lookup(self, name: str, temperature_letters: bool = False) -> Unit | None:
        """Resolve a symbol to a unit, or None if it isn't one."""
        key = (name, temperature_letters)
        if key not in self._cache:
            self._cache[key] = self._lookup(name, temperature_letters)
        return self._cache[key]

    def _lookup(self, name: str, temperature_letters: bool) -> Unit | None:
        if temperature_letters and name in _TEMPERATURE_LETTERS:
            return self.ureg.Unit(_TEMPERATURE_LETTERS[name])
        if name in _BLOCKED:
            return None
        if name in _ALIASES:
            return self.ureg.Unit(_ALIASES[name])
        try:
            canonical = self.ureg.get_name(name)
            if canonical:
                return self.ureg.Unit(canonical)
        except Exception:
            pass
        # Case-insensitive fallback, only when it is unambiguous (kOhm, MM is not).
        try:
            candidates = self.ureg.parse_unit_name(name, case_sensitive=False)
            if len(candidates) == 1:
                return self.ureg.Unit("".join(candidates[0]))
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ description

    def _root_units(self, units: Unit) -> Unit | None:
        try:
            return self.ureg.get_root_units(units)[1]
        except Exception:
            return None

    def dimension_name(self, value: Any) -> str:
        """A short human name for what a value measures: 'mass', 'length', ..."""
        if not isinstance(value, (Quantity, Unit)):
            return "a plain number"
        units = value.units if isinstance(value, Quantity) else value
        try:
            dim = units.dimensionality
        except Exception:
            return self.symbol(units)
        if not dim:
            root = self._root_units(units)
            names = set(root._units) if root is not None else set()
            if names == {"bit"}:
                return "data size"
            if names == {"radian"}:
                return "angle"
            if not names:
                return "a plain number"
            return self.symbol(units)
        return self._dim_names.get(dim) or self.symbol(units)

    def symbol(self, units: Unit) -> str:
        """Compact display form: kΩ, km/h, m², kg·m/s²."""
        top: list[str] = []
        bottom: list[str] = []
        for name, exp in units._units.items():
            sym = _SYMBOL_OVERRIDES.get(name)
            if sym is None:
                try:
                    sym = self.ureg.get_symbol(name)
                except Exception:
                    sym = name
            sym = sym.replace("μ", "µ")
            power = abs(exp)
            if power != 1:
                if float(power).is_integer():
                    sym += str(int(power)).translate(_SUPERSCRIPTS)
                else:
                    sym += f"^{power:g}"
            (top if exp > 0 else bottom).append(sym)
        if not bottom:
            return "·".join(top)
        denominator = bottom[0] if len(bottom) == 1 else "(" + "·".join(bottom) + ")"
        return ("·".join(top) or "1") + "/" + denominator

    # ------------------------------------------------------------------- conversion

    def same_kind(self, a: Unit, b: Unit) -> bool:
        """Dimension check that also keeps bytes, radians and plain numbers apart."""
        try:
            if a.dimensionality != b.dimensionality:
                return False
            if a.dimensionality:
                return True
        except Exception:
            return True  # let Pint decide (and complain) for exotic units
        ra, rb = self._root_units(a), self._root_units(b)
        return ra is None or rb is None or ra == rb

    def convert(self, value: Any, target: Unit) -> Quantity:
        if not isinstance(value, Quantity):
            raise UnitMismatchError(f"Can't convert a plain number to {self.dimension_name(target)}")
        if not self.same_kind(value.units, target):
            raise UnitMismatchError(
                f"Can't convert {self.dimension_name(value)} to {self.dimension_name(target)}"
            )
        try:
            result = value.to(target)
            turns = self._radian_power(value.units) - self._radian_power(target)
            if turns and value.units.dimensionality:
                # Pint counts a revolution as 2*pi radians, so rpm -> Hz comes out 2*pi
                # too big. Between a rotation rate and a plain rate, one turn is one cycle.
                result = self.quantity(result.magnitude / (2 * math.pi) ** turns, target)
            return result
        except pint.DimensionalityError:
            raise UnitMismatchError(
                f"Can't convert {self.dimension_name(value)} to {self.dimension_name(target)}"
            ) from None
        except pint.PintError as exc:
            raise EvalError(f"Can't convert to {self.symbol(target)}: {exc}") from None

    def _radian_power(self, units: Unit) -> float:
        root = self._root_units(units)
        return float(root._units.get("radian", 0)) if root is not None else 0.0

    def is_log(self, value: Any) -> bool:
        """True for dB-style quantities, which can be converted but not added or scaled."""
        if not isinstance(value, (Quantity, Unit)):
            return False
        units = value.units if isinstance(value, Quantity) else value
        return any(n.startswith(("decibel", "bel", "neper")) for n in units._units)

    def is_angle(self, units: Unit) -> bool:
        return self.same_kind(units, self._radian)

    def is_offset(self, units: Unit) -> bool:
        """True for °C / °F style units, where zero is not 'nothing'."""
        names = list(units._units)
        return len(names) == 1 and names[0] in ("degree_Celsius", "degree_Fahrenheit")

    # --------------------------------------------------------------- simplification

    def _candidates(self, container: Any) -> list[Unit]:
        """Units mentioned in a compound result, plus what they are defined from."""
        names: list[str] = []
        for name in container:
            names.append(name)
            try:
                _, base, _ = self.ureg.parse_unit_name(name)[0]
                definition = self.ureg._units.get(base)
                names.extend(getattr(definition, "reference", None) or ())
            except Exception:
                continue
        out: list[Unit] = []
        for name in names:
            try:
                out.append(self.ureg.Unit(name))
            except Exception:
                continue
        return out

    def _named_product(self, container: Any) -> Unit | None:
        """A x h and W x h have everyday names that beat coulombs and joules."""
        if len(container) != 2 or set(container.values()) != {1}:
            return None
        bases = set()
        for name in container:
            try:
                bases.add(self.ureg.parse_unit_name(name)[0][1])
            except Exception:
                return None
        if bases == {"ampere", "hour"}:
            return self.ureg.Unit("ampere_hour")
        if bases == {"watt", "hour"}:
            return self.ureg.Unit("watt_hour")
        return None

    def _reduce(self, q: Quantity) -> Quantity:
        """Merge units of the same dimension into the largest one: m*cm -> m², ft*in -> ft²."""
        groups: dict[Any, tuple[float, str]] = {}
        for name in q.units._units:
            unit = self.ureg.Unit(name)
            scale = abs(float(self.ureg.get_root_units(unit)[0]))
            key = (unit.dimensionality, self._root_units(unit))
            if key not in groups or scale > groups[key][0]:
                groups[key] = (scale, name)
        target = self.ureg.Unit("dimensionless")
        for name, exp in q.units._units.items():
            unit = self.ureg.Unit(name)
            keep = groups[(unit.dimensionality, self._root_units(unit))][1]
            target = target * self.ureg.Unit(keep) ** exp
        return q.to(target)

    def simplify(self, q: Quantity) -> Any:
        """Tidy a computed quantity: mph*h -> mi, V/kohm -> A, m/m -> plain number."""
        container = q.units._units
        if len(container) == 0:
            return q.magnitude
        if len(container) == 1 and next(iter(container.values())) == 1:
            return q
        try:
            dim = q.dimensionality
            if not dim:
                root = q.to_root_units()
                return root.magnitude if len(root.units._units) == 0 else self._reduce(q)
            root_units = self._root_units(q.units)
            if root_units is not None and {"bit", "radian"} & set(root_units._units):
                # Data rates and angular rates are not hertz, whatever their dimension says.
                return self._reduce(q)
            named = self._named_product(container)
            if named is not None:
                return q.to(named)
            for candidate in self._candidates(container):
                if candidate.dimensionality == dim:
                    return q.to(candidate)
            if dim in self._preferred:
                return q.to(self._preferred[dim])
            return self._reduce(q)
        except Exception:
            return q

    # ------------------------------------------------------------------ SI prefixes

    def prefix_info(self, units: Unit) -> tuple[str, int, int] | None:
        """(base unit name, lowest exponent, highest exponent) if ``units`` is a single
        SI unit that may be re-prefixed for display, else None."""
        container = units._units
        if len(container) != 1:
            return None
        name, exp = next(iter(container.items()))
        if exp != 1:
            return None
        try:
            prefix, base, suffix = self.ureg.parse_unit_name(name)[0]
        except Exception:
            return None
        if suffix or base not in _PREFIXABLE or prefix not in _PREFIX_EXPONENTS:
            return None
        low, high = _PREFIXABLE[base]
        return base, low, high

    def with_prefix(self, base: str, exponent: int) -> Unit:
        return self.ureg.Unit(_PREFIX_NAMES[exponent] + base)
