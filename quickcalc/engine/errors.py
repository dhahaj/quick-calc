"""Error types raised by the engine. Every message is meant to be shown to the user as-is."""

from __future__ import annotations


class CalcError(Exception):
    """Base class for all user-facing calculation errors."""

    def __init__(self, message: str, pos: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.pos = pos

    def __str__(self) -> str:
        return self.message


class CalcSyntaxError(CalcError):
    """The input could not be tokenized or parsed (often just incomplete)."""


class EvalError(CalcError):
    """The input parsed fine but could not be evaluated."""


class UnitMismatchError(EvalError):
    """Units did not line up. The engine may retry with another reading of ambiguous symbols."""
