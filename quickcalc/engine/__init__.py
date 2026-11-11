"""QuickCalc engine: parser, units and formatting. No GUI imports anywhere in this package."""

from .engine import Engine, Result
from .errors import CalcError, CalcSyntaxError, EvalError, UnitMismatchError
from .formatter import MODES, FormatSettings
from .units import CUSTOM_UNITS_TEMPLATE

__all__ = [
    "CUSTOM_UNITS_TEMPLATE",
    "MODES",
    "CalcError",
    "CalcSyntaxError",
    "Engine",
    "EvalError",
    "FormatSettings",
    "Result",
    "UnitMismatchError",
]
