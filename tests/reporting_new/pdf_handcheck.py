"""Hand-check a calculation report from the printed PDF alone (decision 15).

The reader looks only at the PDF: characters with their size and baseline,
fraction bars and radical strokes. It rebuilds each printed line as tokens
(numbers, operators, words, super/subscripts, fractions, roots), finds every
chain ``= numeric expression = result`` and recomputes the expression from
the printed numbers. The result must equal the recomputed value rounded half
away from zero to the result's printed decimals. Symbolic segments (with
words or subscripts) are skipped; only formulas made of printed numbers are
checked. It never imports the report implementation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pymupdf

MAIN_SIZE = 8.0          # body text is 9.9 pt, scripts 6.5 pt
GAP = 1.5                # a wider horizontal gap separates two runs (a space)
MATH_STROKE = (0.3, 0.9)  # fraction bars and radicals; table rules are 0.12/0.96 pt
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|[=×+\-−()/,]|\S")
FUNCTIONS = {"min": min, "max": max, "sqrt": math.sqrt}
# Evaluated in decimal arithmetic, as a person with a calculator: 14.517 × 0.5 + 0.100 is 7.3585, not 7.35849999.
_DECIMAL = {"min": min, "max": max, "sqrt": lambda value: value.sqrt(), "D": Decimal}
CONTINUATION = {"=", "+", "-", "−", "×", "/"}  # a wrapped formula continues on the next line with an operator

Token = tuple[Any, ...]


@dataclass(frozen=True)
class Char:
    c: str
    x0: float
    x1: float
    baseline: float
    size: float


@dataclass(frozen=True)
class FormulaCheck:
    page: int
    line: str
    expression: str
    printed: str
    computed: float
    ok: bool


@dataclass
class _Group:
    """Characters claimed by a fraction or root, placed as one token in a line."""

    kind: str
    x0: float
    anchor: float            # the baseline of the line the group belongs to
    parts: list[list[Char]]


def _chars(page: pymupdf.Page) -> list[Char]:
    found = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                for char in span["chars"]:
                    if not char["c"].isspace():
                        found.append(Char(char["c"], char["bbox"][0], char["bbox"][2], char["origin"][1], span["size"]))
    return found


def _strokes(page: pymupdf.Page) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    """Fraction bars (x0, x1, y) and radical overlines (x0, x1, y) drawn as math strokes."""
    bars, roots = [], []
    for drawing in page.get_drawings():
        width = drawing.get("width") or 0
        lines = [item for item in drawing["items"] if item[0] == "l"]
        if not (MATH_STROKE[0] <= width <= MATH_STROKE[1]) or len(lines) != len(drawing["items"]):
            continue
        last = lines[-1]
        horizontal = abs(last[1].y - last[2].y) < 0.01
        if len(lines) == 1 and horizontal:
            bars.append((min(last[1].x, last[2].x), max(last[1].x, last[2].x), last[1].y))
        elif len(lines) >= 3 and horizontal:
            roots.append((lines[0][1].x, max(last[1].x, last[2].x), last[1].y))
    return bars, roots


def _claim(chars: list[Char], x0: float, x1: float, top: float, bottom: float) -> list[Char]:
    return [char for char in chars if x0 - 0.5 <= (char.x0 + char.x1) / 2 <= x1 + 0.5 and top < char.baseline < bottom]


def _lines(chars: list[Char], groups: list[_Group]) -> list[tuple[float, list[Token]]]:
    """Group characters into lines by main baseline, attach scripts, then tokenize."""
    baselines: list[float] = []
    for char in sorted((char for char in chars if char.size >= MAIN_SIZE), key=lambda char: char.baseline):
        if not baselines or char.baseline - baselines[-1] > 0.6:
            baselines.append(char.baseline)
    items: dict[float, list[tuple[float, Any]]] = {baseline: [] for baseline in baselines}
    for char in chars:
        if not baselines:
            break
        if char.size >= MAIN_SIZE:
            line = min(baselines, key=lambda baseline: abs(baseline - char.baseline))
            role = "main"
        else:
            # superscripts sit up to 7 pt above the line's baseline, subscripts up to 4 pt below
            candidates = [baseline for baseline in baselines if -7 <= char.baseline - baseline <= 4]
            if not candidates:
                continue
            line = min(candidates, key=lambda baseline: abs(baseline - char.baseline))
            role = "sup" if char.baseline < line - 1 else "sub"
        items[line].append((char.x0, (role, char)))
    for group in groups:
        if baselines:
            line = min(baselines, key=lambda baseline: abs(baseline - group.anchor))
            if abs(line - group.anchor) <= 6:
                items[line].append((group.x0, ("group", group)))
    return [(baseline, _tokenize(sorted(items[baseline], key=lambda item: item[0]))) for baseline in baselines]


def _tokenize(items: list[tuple[float, Any]]) -> list[Token]:
    tokens: list[Token] = []
    run: list[Char] = []
    role = None

    def flush() -> None:
        nonlocal run
        if run:
            text = "".join(char.c for char in run)
            words = [("num", value) if value[0].isdigit() else ("op", value) if value in "=×+-−()/,"
                     else ("word", value) for value in TOKEN.findall(text)]
            tokens.extend(words if role == "main" else [(role, words)])
        run = []

    for _, (kind, value) in items:
        if kind == "group":
            flush()
            if value.kind == "frac":
                tokens.append(("frac", _inner(value.parts[0]), _inner(value.parts[1])))
            else:
                tokens.append(("root", _inner(value.parts[0])))
            role = None
            continue
        if run and (kind != role or value.x0 - run[-1].x1 > GAP):
            flush()
        role = kind
        run.append(value)
    flush()
    return tokens


def _inner(chars: list[Char]) -> list[Token]:
    lines = _lines(chars, [])
    return [token for _, tokens in lines for token in tokens]


def read_lines(page: pymupdf.Page) -> list[tuple[float, list[Token]]]:
    """The printed lines of *page* as tokens, top to bottom."""
    chars = _chars(page)
    bars, roots = _strokes(page)
    groups = []
    for x0, x1, y in bars:
        numerator = _claim(chars, x0, x1, y - 14, y)
        denominator = _claim(chars, x0, x1, y, y + 16)
        if not numerator or not denominator:
            continue  # a drawing stroke (an arrow with its label, an outline), not a fraction bar
        chars = [char for char in chars if char not in numerator and char not in denominator]
        groups.append(_Group("frac", x0, y + 2.5, [numerator, denominator]))
    for x0, x1, y in roots:
        body = _claim(chars, x0, x1, y, y + 14)
        if not body:
            continue  # a stroke with a horizontal end (a spring), not a radical
        chars = [char for char in chars if char not in body]
        anchor = max((char.baseline for char in body if char.size >= MAIN_SIZE), default=y + 9)
        groups.append(_Group("root", x0, anchor, [body]))
    lines: list[tuple[float, list[Token]]] = []
    for baseline, tokens in _lines(chars, groups):
        if lines and tokens and tokens[0][0] == "op" and tokens[0][1] in CONTINUATION:
            # A wrapped formula continues on the next line with its relation or an operator.
            lines[-1] = (lines[-1][0], lines[-1][1] + tokens)
        else:
            lines.append((baseline, tokens))
    return lines


def tokens_text(tokens: list[Token]) -> str:
    """A readable rendering of tokens, for messages."""
    out = []
    for token in tokens:
        if token[0] in ("num", "op", "word"):
            out.append(token[1])
        elif token[0] == "sup":
            out.append(f"^({tokens_text(token[1])})")
        elif token[0] == "sub":
            out.append(f"_({tokens_text(token[1])})")
        elif token[0] == "frac":
            out.append(f"({tokens_text(token[1])})/({tokens_text(token[2])})")
        else:
            out.append(f"√({tokens_text(token[1])})")
    return "".join(out)


def _expression(tokens: list[Token]) -> str | None:
    """Python text of a numeric expression, or None if a symbol is involved."""
    out = []
    for token in tokens:
        kind = token[0]
        if kind == "num":
            out.append(token[1].replace(",", ""))
        elif kind == "op":
            out.append({"×": "*", "−": "-"}.get(token[1], token[1]))
        elif kind == "word" and token[1] in FUNCTIONS:
            out.append(token[1])
        elif kind == "sup":
            inner = _expression(token[1])
            if inner is None:
                return None
            out.append(f"**({inner})")
        elif kind == "frac":
            numerator, denominator = _expression(token[1]), _expression(token[2])
            if numerator is None or denominator is None:
                return None
            out.append(f"(({numerator})/({denominator}))")
        elif kind == "root":
            inner = _expression(token[1])
            if inner is None:
                return None
            out.append(f"sqrt({inner})")
        else:
            return None
    return "".join(out)


def _evaluate(expression: str) -> Decimal:
    if not re.fullmatch(r"(?:[\d.+\-*/(),]|min|max|sqrt)+", expression):
        raise ValueError(f"not a numeric expression: {expression}")
    exact = re.sub(r"\d+(?:\.\d+)?", lambda match: f"D('{match.group()}')", expression)
    return Decimal(eval(exact, {"__builtins__": {}}, _DECIMAL))  # noqa: S307 - validated above


def _round(value: Decimal, decimals: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def formula_checks(path: str | Path) -> list[FormulaCheck]:
    """Every ``= expression = result`` chain of printed numbers in the PDF, recomputed."""
    checks = []
    with pymupdf.open(path) as pdf:
        for page in pdf:
            for _, tokens in read_lines(page):
                equals = [index for index, token in enumerate(tokens) if token == ("op", "=")]
                for start, end in zip(equals, equals[1:]):
                    segment = tokens[start + 1:end]
                    expression = _expression(segment)
                    result = tokens[end + 1:end + 3]
                    sign = ""
                    if result[:1] in ([("op", "-")], [("op", "−")]):  # a negative result
                        sign, result = "-", result[1:]
                    if (expression is None or not result or result[0][0] != "num"
                            or not re.search(r"[*/+\-]|min|max|sqrt", expression.lstrip("-"))):
                        continue
                    printed = sign + result[0][1]
                    decimals = len(printed.partition(".")[2])  # the sign is not a digit
                    computed = _evaluate(expression)
                    ok = _round(computed, decimals) == Decimal(printed.replace(",", ""))
                    checks.append(FormulaCheck(page.number + 1, tokens_text(tokens), expression, printed,
                                               float(computed), ok))
    return checks


CELL_GAP = 3.0  # table cells are separated by rules and padding; words within a cell by less
BODY_SIZE = 9.5  # body and table text is 9.9 pt; figure dimensions (8 pt) and scripts are not table cells


@dataclass(frozen=True)
class PrintedLine:
    page: int
    baseline: float
    cells: tuple[str, ...]


def printed_lines(path: str | Path) -> list[PrintedLine]:
    """Every printed line as its runs of main-size text (table cells), top to bottom, page by page.

    Scripts (units such as m3, subscripts of xL) and figure labels are left out; a run ends at a gap
    wider than a space, so each table cell is one run and a number is never split.
    """
    lines = []
    with pymupdf.open(path) as pdf:
        for page in pdf:
            chars = sorted((char for char in _chars(page) if char.size >= BODY_SIZE), key=lambda char: char.baseline)
            rows: list[list[Char]] = []
            for char in chars:
                if rows and abs(char.baseline - rows[-1][0].baseline) <= 0.6:
                    rows[-1].append(char)
                else:
                    rows.append([char])
            for row in rows:
                cells: list[str] = []
                previous = None
                for char in sorted(row, key=lambda char: char.x0):
                    if previous is None or char.x0 - previous.x1 > CELL_GAP:
                        cells.append(char.c)
                    else:
                        cells[-1] += char.c
                    previous = char
                lines.append(PrintedLine(page.number + 1, row[0].baseline, tuple(cells)))
    return lines


def decimal_of(text: str) -> Decimal | None:
    """A printed number as written, or None for anything else (a dash, a word)."""
    return Decimal(text.replace(",", "")) if re.fullmatch(r"-?\d[\d,]*(?:\.\d+)?", text) else None


def rounded_like(value: Decimal, printed: str) -> Decimal:
    """*value* rounded half away from zero to the decimals of *printed*."""
    return _round(value, len(printed.partition(".")[2]))
