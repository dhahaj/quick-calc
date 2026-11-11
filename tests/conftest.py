from __future__ import annotations

from typing import Any

import pytest

from quickcalc.engine import Engine, FormatSettings, Result
from quickcalc.engine.units import Quantity


class Calc:
    """Thin test helper around one shared Engine (building a Pint registry is slow)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def run(self, text: str) -> Result:
        return self.engine.evaluate(text)

    def ok(self, text: str) -> Result:
        result = self.engine.evaluate(text)
        assert result.ok, f"{text!r} failed: {result.error}"
        return result

    def num(self, text: str) -> Any:
        """Magnitude of the result, whatever its unit."""
        value = self.ok(text).value
        return value.magnitude if isinstance(value, Quantity) else value

    def text(self, text: str) -> str:
        return self.ok(text).text

    def err(self, text: str) -> str:
        result = self.engine.evaluate(text)
        assert not result.ok, f"{text!r} unexpectedly gave {result.text!r}"
        assert result.error
        return result.error

    def fmt(self, **kwargs: Any) -> None:
        self.engine.format = FormatSettings(**kwargs)


@pytest.fixture(scope="session")
def _engine() -> Engine:
    return Engine()


@pytest.fixture
def calc(_engine: Engine) -> Calc:
    _engine.clear()
    _engine.format = FormatSettings()
    _engine.degrees = False
    return Calc(_engine)
