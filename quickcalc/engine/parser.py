"""Recursive-descent parser. Produces a small AST; nothing is evaluated here.

Precedence, loosest to tightest::

    name = ...                assignment (statement level)
    to / in / ->              conversion (statement level)
    |                         bitwise or
    xor                       bitwise xor
    &                         bitwise and
    << >>                     shifts
    + -                       add, subtract
    * / mod %                 multiply, divide, modulo
    ||                        parallel
    - + ~                     unary
    (adjacency)               implicit multiplication: 2pi, 2(3+4), 9 V
    ^ **                      power (right associative)
    %                         postfix percent
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import CalcSyntaxError
from .lexer import COMMA, END, IDENT, KW, LP, NUM, OP, RP, Token, tokenize

# Exponent of ten for each single-letter SI prefix accepted directly after a number.
SI_PREFIXES: dict[str, int] = {
    "f": -15,
    "p": -12,
    "n": -9,
    "u": -6,
    "µ": -6,
    "m": -3,
    "k": 3,
    "M": 6,
    "G": 9,
    "T": 12,
}

FUNCTION_NAMES = frozenset(
    {
        "sqrt", "cbrt", "abs", "round", "floor", "ceil", "log", "ln", "log2", "exp",
        "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "min", "max",
    }
)  # fmt: skip
CONSTANT_NAMES = frozenset({"pi", "e", "ans"})
BASE_TARGETS = frozenset({"hex", "bin", "oct", "dec"})
RESERVED_NAMES = FUNCTION_NAMES | CONSTANT_NAMES | BASE_TARGETS | {"in", "to", "xor", "mod"}

# A line starting with one of these is applied to the previous answer.
_LEADING_OPS = frozenset({"*", "/", "+", "^", "**", "||", "&", "|", "<<", ">>"})
_LEADING_KWS = frozenset({"to", "xor", "mod"})
_TARGET_OPS = frozenset({"*", "/", "^", "**", "-"})


# ----------------------------------------------------------------------------- AST


@dataclass(frozen=True, slots=True)
class Num:
    value: int | float
    raw: str
    suffix: str | None = None  # glued single-letter SI prefix, e.g. the k in 4.7k


@dataclass(frozen=True, slots=True)
class Ident:
    name: str


@dataclass(frozen=True, slots=True)
class Unary:
    op: str
    operand: Node


@dataclass(frozen=True, slots=True)
class Binary:
    op: str
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class Percent:
    operand: Node


@dataclass(frozen=True, slots=True)
class Call:
    name: str
    args: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class Implicit:
    """Operands written next to each other: implicit multiplication."""

    factors: tuple[Node, ...]


Node = Num | Ident | Unary | Binary | Percent | Call | Implicit


@dataclass(frozen=True, slots=True)
class Conversion:
    """One ``to <target>`` step. Exactly one of ``base`` / ``unit`` is set."""

    base: str | None = None
    unit: Node | None = None


@dataclass(frozen=True, slots=True)
class Statement:
    expr: Node
    assign: str | None = None
    conversions: tuple[Conversion, ...] = field(default=())


# -------------------------------------------------------------------------- parsing


def _is_op(tok: Token, *ops: str) -> bool:
    return tok.kind == OP and tok.text in ops


def _valid_target(tokens: list[Token]) -> bool:
    """True if ``tokens`` look like a unit expression such as ``km/h`` or ``m^2``."""
    if not tokens or tokens[0].kind not in (IDENT, LP):
        return False
    for tok in tokens:
        if tok.kind in (IDENT, NUM, LP, RP):
            continue
        if tok.kind == OP and tok.text in _TARGET_OPS:
            continue
        return False
    return True


def _find_conversion(tokens: list[Token]) -> int | None:
    """Index of the rightmost top-level conversion keyword, or None.

    ``to`` and ``->`` are always keywords. ``in`` is a keyword only when something
    comes before it and a plain unit expression follows it; otherwise it is the inch.
    """
    depth = 0
    best: int | None = None
    for i, tok in enumerate(tokens):
        if tok.kind == LP:
            depth += 1
        elif tok.kind == RP:
            depth -= 1
        elif (tok.kind == KW and tok.text == "to") or _is_op(tok, "->"):
            if depth > 0:
                raise CalcSyntaxError("Conversions can't go inside parentheses", tok.pos)
            best = i
        elif tok.kind == IDENT and tok.text == "in" and depth == 0 and i > 0:
            if _valid_target(tokens[i + 1 :]):
                best = i
    return best


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        end_pos = tokens[-1].pos + len(tokens[-1].text) if tokens else 0
        self.toks = [*tokens, Token(END, "", end_pos)]
        self.i = 0

    # -- helpers
    @property
    def tok(self) -> Token:
        return self.toks[self.i]

    def peek(self, offset: int = 1) -> Token:
        return self.toks[min(self.i + offset, len(self.toks) - 1)]

    def advance(self) -> Token:
        tok = self.toks[self.i]
        if tok.kind != END:
            self.i += 1
        return tok

    def at_op(self, *ops: str) -> bool:
        return _is_op(self.tok, *ops)

    def at_kw(self, word: str) -> bool:
        return self.tok.kind == KW and self.tok.text == word

    @staticmethod
    def starts_operand(tok: Token) -> bool:
        return tok.kind in (NUM, IDENT, LP) or _is_op(tok, "√")

    def fail(self, message: str) -> CalcSyntaxError:
        return CalcSyntaxError(message, self.tok.pos)

    # -- grammar
    def parse_all(self) -> Node:
        node = self.expr()
        if self.tok.kind != END:
            raise self.fail(f"Unexpected '{self.tok.text}'")
        return node

    def expr(self) -> Node:
        return self.bit_or()

    def bit_or(self) -> Node:
        node = self.bit_xor()
        while self.at_op("|"):
            self.advance()
            node = Binary("|", node, self.bit_xor())
        return node

    def bit_xor(self) -> Node:
        node = self.bit_and()
        while self.at_kw("xor"):
            self.advance()
            node = Binary("xor", node, self.bit_and())
        return node

    def bit_and(self) -> Node:
        node = self.shift()
        while self.at_op("&"):
            self.advance()
            node = Binary("&", node, self.shift())
        return node

    def shift(self) -> Node:
        node = self.additive()
        while self.at_op("<<", ">>"):
            op = self.advance().text
            node = Binary(op, node, self.additive())
        return node

    def additive(self) -> Node:
        node = self.multiplicative()
        while self.at_op("+", "-"):
            op = self.advance().text
            node = Binary(op, node, self.multiplicative())
        return node

    def multiplicative(self) -> Node:
        node = self.parallel()
        while True:
            if self.at_op("*", "/"):
                op = self.advance().text
            elif self.at_kw("mod") or self.at_op("%"):
                self.advance()
                op = "mod"
            else:
                return node
            node = Binary(op, node, self.parallel())

    def parallel(self) -> Node:
        node = self.unary()
        while self.at_op("||"):
            self.advance()
            node = Binary("||", node, self.unary())
        return node

    def unary(self) -> Node:
        if self.at_op("-", "+", "~"):
            op = self.advance().text
            return Unary(op, self.unary())
        return self.implicit()

    def implicit(self) -> Node:
        factors = [self.power()]
        while self.starts_operand(self.tok):
            if self.tok.kind == NUM and isinstance(factors[-1], Num) and self.peek(-1).kind != RP:
                raise self.fail("Missing operator between numbers")
            factors.append(self.power())
        return factors[0] if len(factors) == 1 else Implicit(tuple(factors))

    def power(self) -> Node:
        base = self.postfix()
        if self.at_op("^", "**"):
            self.advance()
            return Binary("^", base, self.exponent())
        return base

    def exponent(self) -> Node:
        if self.at_op("-", "+"):
            op = self.advance().text
            return Unary(op, self.exponent())
        return self.power()

    def postfix(self) -> Node:
        node = self.atom()
        # '%' is percent unless an operand follows it, in which case it is modulo.
        while self.at_op("%") and not self.starts_operand(self.peek()):
            self.advance()
            node = Percent(node)
        return node

    def atom(self) -> Node:
        tok = self.tok
        if tok.kind == NUM:
            self.advance()
            assert tok.value is not None
            nxt = self.tok
            if nxt.kind == IDENT and not nxt.space_before and nxt.text in SI_PREFIXES:
                self.advance()
                return Num(tok.value, tok.text, nxt.text)
            return Num(tok.value, tok.text)
        if tok.kind == IDENT:
            self.advance()
            if tok.text in FUNCTION_NAMES and self.tok.kind == LP:
                self.advance()
                args: list[Node] = []
                if self.tok.kind != RP:
                    args.append(self.expr())
                    while self.tok.kind == COMMA:
                        self.advance()
                        args.append(self.expr())
                self.close_paren()
                return Call(tok.text, tuple(args))
            return Ident(tok.text)
        if tok.kind == LP:
            self.advance()
            node = self.expr()
            self.close_paren()
            return node
        if _is_op(tok, "√"):
            self.advance()
            return Call("sqrt", (self.power(),))
        if tok.kind == END:
            raise self.fail("Incomplete expression")
        raise self.fail(f"Unexpected '{tok.text}'")

    def close_paren(self) -> None:
        # A missing ')' at the very end is forgiven, like on a pocket calculator.
        if self.tok.kind == RP:
            self.advance()
        elif self.tok.kind != END:
            raise self.fail(f"Expected ')' but found '{self.tok.text}'")


def _parse_target(tokens: list[Token], keyword: Token) -> Conversion:
    if not tokens:
        raise CalcSyntaxError(f"Expected a unit after '{keyword.text}'", keyword.pos)
    if len(tokens) == 1 and tokens[0].kind == IDENT and tokens[0].text in BASE_TARGETS:
        return Conversion(base=tokens[0].text)
    if not _valid_target(tokens):
        raise CalcSyntaxError(f"Expected a unit after '{keyword.text}'", keyword.pos)
    return Conversion(unit=_Parser(tokens).parse_all())


def parse(text: str) -> Statement:
    """Parse one line of input into a Statement."""
    tokens = tokenize(text)
    if not tokens:
        raise CalcSyntaxError("Nothing to calculate", 0)

    assign: str | None = None
    if len(tokens) >= 2 and tokens[0].kind == IDENT and _is_op(tokens[1], "="):
        assign = tokens[0].text
        if assign in RESERVED_NAMES:
            raise CalcSyntaxError(f"'{assign}' is reserved and can't be used as a variable name", 0)
        tokens = tokens[2:]
        if not tokens:
            raise CalcSyntaxError("Incomplete expression", 0)
    elif any(_is_op(t, "=") for t in tokens):
        bad = next(t for t in tokens if _is_op(t, "="))
        raise CalcSyntaxError("'=' can only follow a variable name, as in r1 = 4.7k", bad.pos)

    first = tokens[0]
    leading = (
        (first.kind == OP and (first.text in _LEADING_OPS or first.text == "->"))
        or (first.kind == KW and first.text in _LEADING_KWS)
        or (first.kind == IDENT and first.text == "in" and _valid_target(tokens[1:]))
    )
    if leading:
        tokens = [Token(IDENT, "ans", first.pos), *tokens]

    conversions: list[Conversion] = []
    while (split := _find_conversion(tokens)) is not None:
        conversions.append(_parse_target(tokens[split + 1 :], tokens[split]))
        tokens = tokens[:split]
        if not tokens:
            raise CalcSyntaxError("Nothing to convert", 0)
    conversions.reverse()

    if any(_is_op(t, "=") for t in tokens):
        raise CalcSyntaxError("Unexpected '='", 0)
    return Statement(_Parser(tokens).parse_all(), assign, tuple(conversions))
