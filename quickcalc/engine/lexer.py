"""Tokenizer: turns a line of text into a flat list of tokens."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import CalcSyntaxError

NUM = "NUM"
IDENT = "IDENT"
OP = "OP"
KW = "KW"
LP = "LP"
RP = "RP"
COMMA = "COMMA"
END = "END"

KEYWORDS = frozenset({"to", "xor", "mod"})

# Characters people paste or type from other tools, mapped onto the plain grammar.
_TRANSLATE = {
    "×": "*",
    "·": "*",
    "⋅": "*",
    "÷": "/",
    "−": "-",
    "–": "-",
    "→": "->",
    "²": "^2",
    "³": "^3",
    "Ω": "Ω",  # OHM SIGN -> GREEK CAPITAL OMEGA
    "μ": "µ",  # GREEK SMALL MU -> MICRO SIGN
}

_HEX = re.compile(r"0[xX][0-9a-fA-F][0-9a-fA-F_]*")
_BIN = re.compile(r"0[bB][01][01_]*")
_OCT = re.compile(r"0[oO][0-7][0-7_]*")
_DEC = re.compile(r"(?:\d[\d_]*\.?(?:\d[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?\d+)?")
_OPS = ("**", "||", "<<", ">>", "->", "+", "-", "*", "/", "^", "%", "&", "|", "~", "=", "√")


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    text: str
    pos: int
    value: int | float | None = None
    space_before: bool = False


def _is_ident_start(ch: str) -> bool:
    return ch != "π" and (ch.isalpha() or ch in "_°")


def _is_ident_char(ch: str) -> bool:
    return ch != "π" and (ch.isalnum() or ch == "_")


def tokenize(text: str) -> list[Token]:
    """Split ``text`` into tokens. The END token is not included."""
    for src, dst in _TRANSLATE.items():
        if src in text:
            text = text.replace(src, dst)

    tokens: list[Token] = []
    i = 0
    n = len(text)
    space = False
    while i < n:
        ch = text[i]
        if ch.isspace():
            space = True
            i += 1
            continue

        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            m = _HEX.match(text, i) or _BIN.match(text, i) or _OCT.match(text, i)
            value: int | float
            if m:
                raw = m.group().replace("_", "")
                value = int(raw, 0)
            else:
                m = _DEC.match(text, i)
                assert m is not None
                raw = m.group().replace("_", "")
                value = float(raw) if any(c in raw for c in ".eE") else int(raw)
            tokens.append(Token(NUM, raw, i, value, space))
            i = m.end()
        elif ch == "π":
            tokens.append(Token(IDENT, "pi", i, None, space))
            i += 1
        elif _is_ident_start(ch):
            j = i + 1
            while j < n and _is_ident_char(text[j]):
                j += 1
            word = text[i:j]
            tokens.append(Token(KW if word in KEYWORDS else IDENT, word, i, None, space))
            i = j
        elif ch == "(":
            tokens.append(Token(LP, ch, i, None, space))
            i += 1
        elif ch == ")":
            tokens.append(Token(RP, ch, i, None, space))
            i += 1
        elif ch == ",":
            tokens.append(Token(COMMA, ch, i, None, space))
            i += 1
        else:
            for op in _OPS:
                if text.startswith(op, i):
                    tokens.append(Token(OP, op, i, None, space))
                    i += len(op)
                    break
            else:
                raise CalcSyntaxError(f"Unexpected character '{ch}'", i)
        space = False
    return tokens
