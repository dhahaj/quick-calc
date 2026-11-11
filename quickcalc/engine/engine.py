"""The calculator session: parses a line, evaluates it, remembers ``ans`` and variables."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pint

from .errors import CalcError, CalcSyntaxError, EvalError, UnitMismatchError
from .evaluator import GLUED_UNIT_LETTERS, Evaluator, Flags, walk
from .formatter import FormatSettings, format_value
from .parser import Ident, Node, Num, Statement, parse
from .units import Quantity, Unit, Units


@dataclass(slots=True)
class Result:
    """Outcome of one input line. ``ok`` is False when ``error`` is set."""

    expr: str
    ok: bool
    text: str = ""  # formatted result, ready to display
    alt: str | None = None  # secondary line, e.g. hex/bin of an integer
    error: str | None = None
    value: Any = None
    name: str | None = None  # variable that was assigned, if any
    incomplete: bool = False  # the input didn't parse (as opposed to failing to evaluate)
    locked: bool = False
    base: str | None = None

    @property
    def display(self) -> str:
        return self.text if self.ok else (self.error or "")


@dataclass(slots=True)
class _Computed:
    value: Any
    locked: bool = False
    base: str | None = None


@dataclass(slots=True)
class Engine:
    """Evaluate lines of text. Safe to call with anything; never raises."""

    custom_units_path: Path | None = None
    format: FormatSettings = field(default_factory=FormatSettings)
    degrees: bool = False
    variables: dict[str, Any] = field(default_factory=dict)
    ans: Any = None
    units: Units = field(init=False)

    def __post_init__(self) -> None:
        self.units = Units(self.custom_units_path)

    @property
    def warnings(self) -> list[str]:
        """Problems found while loading the custom units file."""
        return self.units.warnings

    # ------------------------------------------------------------------- public API

    def evaluate(self, text: str) -> Result:
        """Evaluate and commit: updates ``ans`` and any assigned variable."""
        result = self._evaluate(text)
        if result.ok:
            self.ans = result.value
            if result.name:
                self.variables[result.name] = result.value
        return result

    def preview(self, text: str) -> Result | None:
        """Evaluate without side effects. None if the text isn't a valid expression (yet)."""
        result = self._evaluate(text)
        return result if result.ok else None

    def format_result(self, result: Result, settings: FormatSettings | None = None) -> str:
        """Re-format an earlier result, e.g. without thousands separators for the clipboard."""
        if not result.ok:
            return result.display
        return format_value(result.value, settings or self.format, self.units, result.locked, result.base)[0]

    def clear(self) -> None:
        self.variables.clear()
        self.ans = None

    # -------------------------------------------------------------------- internals

    def _evaluate(self, text: str) -> Result:
        expr = text.strip()
        try:
            statement = parse(expr)
        except CalcSyntaxError as exc:
            return Result(expr, False, error=exc.message, incomplete=True)
        except RecursionError:
            return Result(expr, False, error="Expression is too deeply nested", incomplete=True)
        try:
            computed = self._run(statement)
            shown, alt = format_value(computed.value, self.format, self.units, computed.locked, computed.base)
        except CalcError as exc:
            return Result(expr, False, error=exc.message)
        except ZeroDivisionError:
            return Result(expr, False, error="Division by zero")
        except OverflowError:
            return Result(expr, False, error="Result is too large")
        except RecursionError:
            return Result(expr, False, error="Expression is too deeply nested")
        except (ValueError, ArithmeticError):
            return Result(expr, False, error="Not defined for that input")
        except pint.PintError as exc:
            return Result(expr, False, error=str(exc))
        except Exception as exc:  # last line of defence: the app must never crash on input
            return Result(expr, False, error=f"Couldn't calculate that ({type(exc).__name__})")
        return Result(
            expr,
            True,
            text=shown,
            alt=alt,
            value=computed.value,
            name=statement.assign,
            locked=computed.locked,
            base=computed.base,
        )

    def _run(self, statement: Statement) -> _Computed:
        """Evaluate, trying the alternative readings of ambiguous symbols on a unit mismatch."""
        nodes: list[Node] = list(walk(statement.expr))
        for conversion in statement.conversions:
            if conversion.unit is not None:
                nodes.extend(walk(conversion.unit))

        probe = Evaluator(self.units, self.variables, self.ans, self.degrees)
        idents = [n.name for n in nodes if isinstance(n, Ident)]
        has_temp = any(name in ("F", "C") and name not in self.variables for name in idents)
        has_glued = any(isinstance(n, Num) and n.suffix in GLUED_UNIT_LETTERS for n in nodes)
        units_present = any(probe.is_unit_name(name) for name in idents) or any(
            isinstance(self.ans, Quantity) for name in idents if name == "ans"
        )

        glued = has_glued and units_present
        attempts = [Flags(False, glued)]
        if has_temp:
            attempts.append(Flags(True, glued))
        if has_glued:
            attempts.append(Flags(False, not glued))
            if has_temp:
                attempts.append(Flags(True, not glued))

        first_error: UnitMismatchError | None = None
        for flags in attempts:
            try:
                return self._run_with(statement, flags)
            except UnitMismatchError as exc:
                first_error = first_error or exc
        assert first_error is not None
        raise first_error

    def _run_with(self, statement: Statement, flags: Flags) -> _Computed:
        evaluator = Evaluator(self.units, self.variables, self.ans, self.degrees, flags)
        value = evaluator.eval(statement.expr)
        if isinstance(value, Unit):
            value = self.units.quantity(1, value)

        locked = False
        base: str | None = None
        for conversion in statement.conversions:
            if conversion.base is not None:
                if isinstance(value, Quantity):
                    raise EvalError(f"Only plain whole numbers can be shown in {conversion.base}")
                value = evaluator._int(value)
                base, locked = conversion.base, False
            else:
                assert conversion.unit is not None
                target = self._target_unit(conversion.unit, flags)
                value = self.units.convert(value, target)
                base, locked = None, True

        if isinstance(value, Quantity) and not locked:
            value = self.units.simplify(value)
        self._check_finite(value)
        return _Computed(value, locked, base)

    def _target_unit(self, node: Node, flags: Flags) -> Unit:
        evaluator = Evaluator(self.units, {}, None, self.degrees, flags, unit_only=True)
        target = evaluator.eval(node)
        if isinstance(target, Quantity) and target.magnitude == 1:
            target = target.units
        if not isinstance(target, Unit):
            raise EvalError("Expected a unit to convert to")
        return target

    @staticmethod
    def _check_finite(value: Any) -> None:
        magnitude = value.magnitude if isinstance(value, Quantity) else value
        if isinstance(magnitude, complex):
            raise EvalError("Result is not a real number")
        if isinstance(magnitude, float):
            if math.isnan(magnitude):
                raise EvalError("Result is undefined")
            if math.isinf(magnitude):
                raise EvalError("Result is too large")
