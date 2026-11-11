"""Walks the AST and computes a value: an int, a float, or a Pint quantity."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pint

from .errors import EvalError, UnitMismatchError
from .parser import (
    FUNCTION_NAMES,
    SI_PREFIXES,
    Binary,
    Call,
    Ident,
    Implicit,
    Node,
    Num,
    Percent,
    Unary,
)
from .units import Quantity, Unit, Units

# Prefix letters that are also unit symbols: metre, gauss, tesla.
GLUED_UNIT_LETTERS = frozenset({"m", "G", "T"})

_MAX_INT_BITS = 20_000
_CONSTANTS: dict[str, float] = {"pi": math.pi, "e": math.e}


@dataclass(frozen=True, slots=True)
class Flags:
    """How to read the genuinely ambiguous symbols on this attempt."""

    temperature_letters: bool = False  # F and C are °F and °C rather than farad and coulomb
    glued_units: bool = False  # 10m is ten metres rather than ten milli


def walk(node: Node) -> Iterator[Node]:
    yield node
    if isinstance(node, (Unary, Percent)):
        yield from walk(node.operand)
    elif isinstance(node, Binary):
        yield from walk(node.left)
        yield from walk(node.right)
    elif isinstance(node, Call):
        for arg in node.args:
            yield from walk(arg)
    elif isinstance(node, Implicit):
        for factor in node.factors:
            yield from walk(factor)


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _snap(result: float, a: float, b: float) -> float:
    """Kill float residue from cancellation, so 0.3 - 0.1 - 0.2 is 0 and not -2.8e-17."""
    if isinstance(result, float) and result != 0.0:
        if abs(result) < max(abs(a), abs(b)) * 1e-14:
            return 0.0
    return result


class Evaluator:
    def __init__(
        self,
        units: Units,
        variables: Mapping[str, Any],
        ans: Any,
        degrees: bool,
        flags: Flags = Flags(),
        unit_only: bool = False,
    ) -> None:
        self.units = units
        self.variables = variables
        self.ans = ans
        self.degrees = degrees
        self.flags = flags
        self.unit_only = unit_only

    # --------------------------------------------------------------------- dispatch

    def eval(self, node: Node) -> Any:
        if isinstance(node, Num):
            return self._num(node)
        if isinstance(node, Ident):
            return self.resolve(node.name)
        if isinstance(node, Implicit):
            return self._implicit(node)
        if isinstance(node, Binary):
            return self._binary(node)
        if isinstance(node, Unary):
            value = self.eval(node.operand)
            if node.op == "+":
                return value
            if node.op == "-":
                # Negate the magnitude directly so -40 °F stays -40 °F.
                if isinstance(value, Quantity):
                    return self.units.quantity(-value.magnitude, value.units)
                return self.mul(-1, value)
            return ~self._int(value)
        if isinstance(node, Percent):
            return self.div(self.eval(node.operand), 100)
        if isinstance(node, Call):
            return self._call(node)
        raise EvalError("Couldn't understand that expression")

    def is_unit_name(self, name: str) -> bool:
        """True if ``name`` would resolve to a unit (not a variable or constant)."""
        if name in self.variables or name == "ans" or name in _CONSTANTS:
            return False
        return self.units.lookup(name, self.flags.temperature_letters) is not None

    def resolve(self, name: str) -> Any:
        if self.unit_only:
            unit = self.units.lookup(name, self.flags.temperature_letters)
            if unit is None:
                raise EvalError(f"Unknown unit '{name}'")
            return unit
        if name in self.variables:
            return self.variables[name]
        if name == "ans":
            if self.ans is None:
                raise EvalError("No previous result yet")
            return self.ans
        if name in _CONSTANTS:
            return _CONSTANTS[name]
        unit = self.units.lookup(name, self.flags.temperature_letters)
        if unit is not None:
            return unit
        if name in FUNCTION_NAMES:
            raise EvalError(f"{name} needs parentheses, as in {name}(...)")
        raise EvalError(f"Unknown name '{name}'")

    def _num(self, node: Num) -> Any:
        if node.suffix is None or self.unit_only:
            return node.value
        if self.flags.glued_units and node.suffix in GLUED_UNIT_LETTERS:
            unit = self.units.lookup(node.suffix)
            if unit is not None:
                return self.units.quantity(node.value, unit)
        exp = SI_PREFIXES[node.suffix]
        if isinstance(node.value, int) and exp >= 0:
            return node.value * 10**exp
        return float(Decimal(repr(node.value)).scaleb(exp))

    def _implicit(self, node: Implicit) -> Any:
        compound = self._compound(node)
        if compound is not None:
            return compound
        result = self.eval(node.factors[0])
        for factor in node.factors[1:]:
            result = self.mul(result, self.eval(factor))
        return result

    def _compound(self, node: Implicit) -> Any:
        """``5 ft 3 in`` style input: number/unit pairs of one kind are added up."""
        factors = node.factors
        if len(factors) < 4 or len(factors) % 2:
            return None
        parts: list[Quantity] = []
        for i in range(0, len(factors), 2):
            number, ident = factors[i], factors[i + 1]
            if not (isinstance(number, Num) and number.suffix is None and isinstance(ident, Ident)):
                return None
            if not self.is_unit_name(ident.name):
                return None
            unit = self.resolve(ident.name)
            if parts and not self.units.same_kind(parts[0].units, unit):
                return None
            parts.append(self.units.quantity(number.value, unit))
        total = parts[0]
        for part in parts[1:]:
            total = self.add(total, part, 1)
        return total

    def _binary(self, node: Binary) -> Any:
        op = node.op
        left = self.eval(node.left)
        if op in ("+", "-"):
            sign = 1 if op == "+" else -1
            if isinstance(node.right, Percent):
                # Calculator-style: 200 + 10% is 200 plus 10% of 200.
                pct = self.number(self.eval(node.right.operand), "A percentage")
                return self.add(left, self.div(self.mul(left, pct), 100), sign)
            return self.add(left, self.eval(node.right), sign)
        right = self.eval(node.right)
        if op == "*":
            return self.mul(left, right)
        if op == "/":
            return self.div(left, right)
        if op == "^":
            return self.power(left, right)
        if op == "||":
            return self.parallel(left, right)
        if op == "mod":
            return self.modulo(left, right)
        a, b = self._int(left), self._int(right)
        if op == "&":
            return a & b
        if op == "|":
            return a | b
        if op == "xor":
            return a ^ b
        if b < 0:
            raise EvalError("Can't shift by a negative amount")
        if op == ">>":
            return a >> b
        if b + a.bit_length() > _MAX_INT_BITS:
            raise EvalError("Result is too large")
        return a << b

    # ------------------------------------------------------------------- arithmetic

    def _q(self, x: Any) -> Any:
        return self.units.quantity(1, x) if isinstance(x, Unit) else x

    def _pint(self, fn: Callable[[], Any], verb: str, a: Any, b: Any) -> Any:
        if self.units.is_log(a) or self.units.is_log(b):
            raise EvalError("Can't do arithmetic on dB values; convert to linear units first")
        try:
            return fn()
        except pint.DimensionalityError:
            names = f"{self.units.dimension_name(a)} and {self.units.dimension_name(b)}"
            raise UnitMismatchError(f"Can't {verb} {names}") from None
        except pint.OffsetUnitCalculusError:
            raise EvalError("Can't do that with °C/°F directly; convert to K first") from None
        except pint.LogarithmicUnitCalculusError:
            raise EvalError("Can't do arithmetic on dB values; convert to linear units first") from None

    def number(self, x: Any, what: str = "This") -> int | float:
        """Coerce to a plain number; angles and pure ratios are accepted."""
        x = self._q(x)
        if _is_num(x):
            return x
        if isinstance(x, Quantity) and x.dimensionless:
            root = x.to_root_units()
            if set(root.units._units) <= {"radian"}:
                return root.magnitude
        raise UnitMismatchError(f"{what} must be a plain number, not {self.units.dimension_name(x)}")

    def _int(self, x: Any) -> int:
        if isinstance(x, int) and not isinstance(x, bool):
            return x
        if isinstance(x, float) and x.is_integer() and abs(x) < 2**63:
            return int(x)
        raise EvalError("Bitwise and base operations need whole numbers")

    def add(self, a: Any, b: Any, sign: int) -> Any:
        a, b = self._q(a), self._q(b)
        verb = "add" if sign > 0 else "subtract"
        if _is_num(a) and _is_num(b):
            return _snap(a + sign * b, a, b)
        if _is_num(a) or _is_num(b):
            names = f"{self.units.dimension_name(a)} and {self.units.dimension_name(b)}"
            raise UnitMismatchError(f"Can't {verb} {names}")
        if not self.units.same_kind(a.units, b.units):
            names = f"{self.units.dimension_name(a)} and {self.units.dimension_name(b)}"
            raise UnitMismatchError(f"Can't {verb} {names}")
        if self.units.is_offset(a.units) and self.units.is_offset(b.units):
            # 20 °C + 5 °C: read the second value as a difference, not a second thermometer.
            if a.units != b.units:
                raise EvalError("Use the same temperature unit on both sides")
            if sign > 0:
                return self.units.quantity(a.magnitude + b.magnitude, a.units)
            delta = self.units.ureg.Unit("delta_" + next(iter(a.units._units)))
            return self.units.quantity(a.magnitude - b.magnitude, delta)
        result = self._pint(lambda: a + b if sign > 0 else a - b, verb, a, b)
        return result

    def mul(self, a: Any, b: Any) -> Any:
        if _is_num(a) and _is_num(b):
            return a * b
        if _is_num(a) and isinstance(b, Unit):
            return self.units.quantity(a, b)
        if isinstance(a, Unit) and _is_num(b):
            return self.units.quantity(b, a)
        return self._pint(lambda: a * b, "multiply", a, b)

    def div(self, a: Any, b: Any) -> Any:
        divisor = b.magnitude if isinstance(b, Quantity) else b
        if _is_num(divisor) and divisor == 0:
            raise EvalError("Division by zero")
        if _is_num(a) and _is_num(b):
            if isinstance(a, int) and isinstance(b, int) and a % b == 0:
                return a // b
            return a / b
        return self._pint(lambda: a / b, "divide", a, b)

    def modulo(self, a: Any, b: Any) -> Any:
        a, b = self._q(a), self._q(b)
        divisor = b.magnitude if isinstance(b, Quantity) else b
        if divisor == 0:
            raise EvalError("Division by zero")
        if _is_num(a) != _is_num(b):
            names = f"{self.units.dimension_name(a)} and {self.units.dimension_name(b)}"
            raise UnitMismatchError(f"Can't take the remainder of {names}")
        return self._pint(lambda: a % b, "take the remainder of", a, b)

    def power(self, base: Any, exponent: Any) -> Any:
        exp = self.number(exponent, "An exponent")
        if not _is_num(base):
            return self._pint(lambda: base**exp, "raise", base, exp)
        if isinstance(base, int) and isinstance(exp, int) and exp >= 0:
            if abs(base) > 1 and exp * base.bit_length() > _MAX_INT_BITS:
                return float(base) ** exp  # raises OverflowError when truly enormous
            return base**exp
        if base == 0 and exp < 0:
            raise EvalError("Division by zero")
        result = base**exp
        if isinstance(result, complex):
            raise EvalError("Result is not a real number")
        return result

    def parallel(self, a: Any, b: Any) -> Any:
        a, b = self._q(a), self._q(b)
        if _is_num(a) and _is_num(b):
            if a + b == 0:
                raise EvalError("Division by zero")
            return a * b / (a + b)
        if _is_num(a) or _is_num(b) or not self.units.same_kind(a.units, b.units):
            names = f"{self.units.dimension_name(a)} and {self.units.dimension_name(b)}"
            raise UnitMismatchError(f"Can't put {names} in parallel")
        am = a.magnitude
        bm = self._pint(lambda: b.to(a.units), "combine", a, b).magnitude
        if am + bm == 0:
            raise EvalError("Division by zero")
        return self.units.quantity(am * bm / (am + bm), a.units)

    # -------------------------------------------------------------------- functions

    def _call(self, node: Call) -> Any:
        name = node.name
        low, high = _ARITY[name]
        count = len(node.args)
        if count < low or (high is not None and count > high):
            if high is None:
                expected = f"at least {low}"
            elif low == high:
                expected = str(low)
            else:
                expected = f"{low} or {high}"
            noun = "argument" if expected == "1" else "arguments"
            raise EvalError(f"{name} takes {expected} {noun}")
        args = [self._q(self.eval(arg)) for arg in node.args]
        return getattr(self, "_fn_" + name)(*args)

    def _on_magnitude(self, x: Any, fn: Callable[[Any], Any]) -> Any:
        if isinstance(x, Quantity):
            return self.units.quantity(fn(x.magnitude), x.units)
        return fn(x)

    def _fn_sqrt(self, x: Any) -> Any:
        if isinstance(x, Quantity):
            if x.magnitude < 0:
                raise EvalError("Can't take the square root of a negative number")
            return self._pint(lambda: x**0.5, "take the root of", x, 2)
        if x < 0:
            raise EvalError("Can't take the square root of a negative number")
        if isinstance(x, int):
            root = math.isqrt(x)
            if root * root == x:
                return root
        return math.sqrt(x)

    def _fn_cbrt(self, x: Any) -> Any:
        if isinstance(x, Quantity):
            return self._pint(lambda: x ** (1 / 3), "take the root of", x, 3)
        result = math.cbrt(x)
        if isinstance(x, int) and round(result) ** 3 == x:
            return round(result)
        return result

    def _fn_abs(self, x: Any) -> Any:
        return self._on_magnitude(x, abs)

    def _fn_floor(self, x: Any) -> Any:
        return self._on_magnitude(x, math.floor)

    def _fn_ceil(self, x: Any) -> Any:
        return self._on_magnitude(x, math.ceil)

    def _fn_round(self, x: Any, digits: Any = 0) -> Any:
        places = self._int(self.number(digits, "The number of decimals"))
        if places <= 0:
            return self._on_magnitude(x, lambda m: int(round(m, places)))
        return self._on_magnitude(x, lambda m: round(m, places))

    def _positive(self, x: Any, name: str) -> float:
        value = self.number(x, f"The argument of {name}")
        if value <= 0:
            raise EvalError(f"{name} needs a positive number")
        return value

    def _fn_log(self, x: Any, base: Any = 10) -> Any:
        value = self._positive(x, "log")
        b = self._positive(base, "log")
        if b == 10:
            return math.log10(value)
        if b == 1:
            raise EvalError("log base can't be 1")
        return math.log(value, b)

    def _fn_ln(self, x: Any) -> Any:
        return math.log(self._positive(x, "ln"))

    def _fn_log2(self, x: Any) -> Any:
        return math.log2(self._positive(x, "log2"))

    def _fn_exp(self, x: Any) -> Any:
        return math.exp(self.number(x, "The argument of exp"))

    def _angle(self, x: Any, name: str) -> float:
        if isinstance(x, Quantity):
            if not self.units.is_angle(x.units):
                raise UnitMismatchError(
                    f"{name} needs an angle or a plain number, not {self.units.dimension_name(x)}"
                )
            return x.to("radian").magnitude
        return math.radians(x) if self.degrees else x

    def _fn_sin(self, x: Any) -> Any:
        return round(math.sin(self._angle(x, "sin")), 15)

    def _fn_cos(self, x: Any) -> Any:
        return round(math.cos(self._angle(x, "cos")), 15)

    def _fn_tan(self, x: Any) -> Any:
        angle = self._angle(x, "tan")
        if abs(math.cos(angle)) < 1e-15:
            raise EvalError("tan is undefined at that angle")
        return round(math.tan(angle), 15)

    def _from_radians(self, value: float) -> float:
        return round(math.degrees(value), 12) if self.degrees else value

    def _unit_interval(self, x: Any, name: str) -> float:
        value = self.number(x, f"The argument of {name}")
        if not -1 <= value <= 1:
            raise EvalError(f"{name} needs a value between -1 and 1")
        return value

    def _fn_asin(self, x: Any) -> Any:
        return self._from_radians(math.asin(self._unit_interval(x, "asin")))

    def _fn_acos(self, x: Any) -> Any:
        return self._from_radians(math.acos(self._unit_interval(x, "acos")))

    def _fn_atan(self, x: Any) -> Any:
        return self._from_radians(math.atan(self.number(x, "The argument of atan")))

    def _fn_atan2(self, y: Any, x: Any) -> Any:
        if isinstance(y, Quantity) and isinstance(x, Quantity):
            x = self._pint(lambda: x.to(y.units), "compare", y, x).magnitude
            y = y.magnitude
        return self._from_radians(
            math.atan2(self.number(y, "The argument of atan2"), self.number(x, "The argument of atan2"))
        )

    def _extreme(self, args: tuple[Any, ...], pick: Callable[..., Any], name: str) -> Any:
        if all(_is_num(a) for a in args):
            return pick(args)
        if any(_is_num(a) for a in args):
            raise UnitMismatchError(f"{name} can't mix plain numbers and units")
        first = args[0]
        keyed = [self._pint(lambda a=a: a.to(first.units), "compare", first, a).magnitude for a in args]
        return args[keyed.index(pick(keyed))]

    def _fn_min(self, *args: Any) -> Any:
        return self._extreme(args, min, "min")

    def _fn_max(self, *args: Any) -> Any:
        return self._extreme(args, max, "max")


_ARITY: dict[str, tuple[int, int | None]] = {
    "sqrt": (1, 1), "cbrt": (1, 1), "abs": (1, 1), "round": (1, 2), "floor": (1, 1),
    "ceil": (1, 1), "log": (1, 2), "ln": (1, 1), "log2": (1, 1), "exp": (1, 1),
    "sin": (1, 1), "cos": (1, 1), "tan": (1, 1), "asin": (1, 1), "acos": (1, 1),
    "atan": (1, 1), "atan2": (2, 2), "min": (1, None), "max": (1, None),
}  # fmt: skip
