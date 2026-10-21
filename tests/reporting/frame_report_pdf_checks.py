"""Hand checks of the 0610/0710 tables from the printed PDF alone (decision 15).

pdf_handcheck checks every ``= expression = result`` line. The load tables
print their products in columns instead: N × アーム = M, 列車荷重 × 衝撃係数 =
鉛直力, and the 合計 row is the sum of the printed rows above it; the
horizontal summary prints 起点桁 + 終点桁 = 合計. This module reads those rows
from the PDF and recomputes them, rounding half away from zero to the printed
decimals. It never imports the report implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pymupdf
from gridlayoutpdf import A4_PORTRAIT_REFERENCE, FontRegistry

from pdf_handcheck import read_lines, tokens_text

ROW_WORDS = ("起点側", "終点側", "桁受け", "はり")


@dataclass(frozen=True)
class RowCheck:
    page: int
    line: str
    kind: str
    ok: bool


def _numbers(tokens) -> list[str]:
    """Signed printed numbers of a line (a minus sign directly before a number belongs to it)."""
    found, sign = [], ""
    for token in tokens:
        if token == ("op", "-") or token == ("op", "−"):
            sign = "-"
            continue
        if token[0] == "num":
            found.append(sign + token[1].replace(",", ""))
        sign = ""
    return found


def _round(value: Decimal, like: str) -> Decimal:
    places = len(like.partition(".")[2])
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _product(a: str, b: str, result: str) -> bool:
    return _round(Decimal(a) * Decimal(b), result) == Decimal(result)


def table_checks(path: str | Path) -> list[RowCheck]:
    checks: list[RowCheck] = []
    with pymupdf.open(path) as pdf:
        for page in pdf:
            rows: list[list[str]] = []
            for _, tokens in read_lines(page):
                words = [token[1] for token in tokens if token[0] == "word"]
                text = tokens_text(tokens)
                numbers = _numbers(tokens)
                if ("op", "=") in tokens or not tokens:
                    continue
                # N, arm, M of a bearing or a pier part; load, factor, N, arm, M of a bearing
                labelled = (text.startswith(ROW_WORDS) and len(numbers) == 3
                            or text.startswith(ROW_WORDS[:2]) and len(numbers) == 5)
                if labelled:
                    if len(numbers) == 3:
                        ok = _product(numbers[0], numbers[1], numbers[2])
                    else:
                        ok = _product(numbers[0], numbers[1], numbers[2]) and _product(numbers[2], numbers[3], numbers[4])
                    checks.append(RowCheck(page.number + 1, text, "row", ok))
                    rows.append(numbers)
                elif text.startswith("合計") and rows and len(numbers) in (2, 3):
                    # N and M under rows of N, arm, M; or under rows of load, factor, N, arm, M (Σ of the products)
                    columns = (0, 2, 4) if len(numbers) == 3 else (0, 2) if len(rows[0]) == 3 else (2, 4)
                    sums = [sum((Decimal(row[c]) for row in rows), Decimal(0)) for c in columns]
                    ok = all(total == Decimal(number) for total, number in zip(sums, numbers, strict=True))
                    checks.append(RowCheck(page.number + 1, text, "total", ok))
                    rows = []
                elif any("LR" in word or word.startswith("EQ") or word == "E" for word in words) and len(numbers) >= 3 \
                        and all(len(n.partition(".")[2]) == 2 for n in numbers[-3:]):
                    a, b, c = numbers[-3:]
                    checks.append(RowCheck(page.number + 1, text, "horizontal", Decimal(a) + Decimal(b) == Decimal(c)))
    return checks


# --- the common grid (GridLayoutPdf 0.2.0: A4, 16.08 × 15.48 pt, 30 columns × 47 rows) --------------------------------

GRID = A4_PORTRAIT_REFERENCE.grid
BODY, HEADING = "MS Mincho", "MS Gothic"


def column_x(column: int) -> float:
    """The paper x of the left edge of the body column *column*."""
    return GRID.origin_x + column * GRID.pitch_x


@dataclass(frozen=True)
class Span:
    """A drawn text span with the face it was drawn in (by the hash in GridLayoutPdf's PDF font name)."""

    text: str
    face: str
    size: float
    x0: float
    x1: float
    baseline: float
    page: int
    upright: bool


def spans(pdf) -> list[Span]:
    registry = FontRegistry()
    prefixes = {"GLP_" + registry.resolve(name).sha256: name for name in (BODY, HEADING)}
    found = []
    for page in pdf:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if not span["text"].strip():
                        continue
                    face = next((name for prefix, name in prefixes.items() if prefix.startswith(span["font"])),
                                span["font"])
                    found.append(Span(span["text"].strip(), face, round(span["size"], 2), span["bbox"][0],
                                      span["bbox"][2], span["origin"][1], page.number + 1,
                                      abs(line["dir"][0] - 1) < 1e-6))
    return found


def first(found: list[Span], text: str) -> Span:
    matches = [span for span in found if span.text == text]
    assert matches, text
    return matches[0]


def placement_errors(span: Span, column: int, face: str, size: float = 10.0) -> list[str]:
    """The span starts at the body column *column*, in *face* at *size* pt, its baseline on a grid row (the
    baseline of every body line is the same distance below its row's top)."""
    errors = []
    if abs(span.x0 - column_x(column)) > .5:
        errors.append(f"{span.text}: x {span.x0:.2f} != column {column} ({column_x(column):.2f})")
    if span.face != face or abs(span.size - size) > .01:
        errors.append(f"{span.text}: {span.face} {span.size} != {face} {size}")
    return errors


def row_offset(span: Span) -> float:
    """How far the span's baseline lies below the top of its grid row, pt."""
    return (span.baseline - GRID.origin_y) % GRID.pitch_y


def relation_centres(pdf, column: int) -> list[float]:
    """The centres of the 10 pt relations "=" (a span of its own, not one inside a line of text) drawn within 4 pt of
    the boundary before the body column *column*, as offsets from that boundary."""
    found = []
    for page in pdf:
        for block in page.get_text("rawdict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    if "".join(char["c"] for char in span["chars"]).strip() != "=":
                        continue
                    for char in span["chars"]:
                        centre = (char["bbox"][0] + char["bbox"][2]) / 2
                        if char["c"] == "=" and abs(span["size"] - 10) < .01 and abs(centre - column_x(column)) < 4:
                            found.append(centre - column_x(column))
    return found


def outside_body(page) -> list[str]:
    """Text and drawings beyond the body's 30 columns (a table or figure wider than the body)."""
    left, right = column_x(0) - 1, column_x(GRID.columns) + 1
    found = [f"text {span['text']!r} at {span['bbox'][0]:.1f}..{span['bbox'][2]:.1f}"
             for block in page.get_text("dict")["blocks"] for line in block.get("lines", [])
             for span in line["spans"] if span["text"].strip()
             and (span["bbox"][0] < left or span["bbox"][2] > right)]
    found += [f"drawing at {drawing['rect'].x0:.1f}..{drawing['rect'].x1:.1f}" for drawing in page.get_drawings()
              if drawing["rect"].x0 < left - 1 or drawing["rect"].x1 > right + 1]
    return found


def row_bands(page, crossing: float, top: float) -> list[float]:
    """The centres of the horizontal rules crossing the paper x *crossing* below *top*, top down."""
    found = set()
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                (x0, y0), (x1, y1) = (item[1].x, item[1].y), (item[2].x, item[2].y)
                if abs(y0 - y1) < .01 and min(x0, x1) - .01 <= crossing <= max(x0, x1) + .01 and y0 > top:
                    found.add(round(y0, 2))
            elif item[0] == "re":
                rect = item[1]
                if rect.height < 1.5 and rect.x0 <= crossing <= rect.x1 and rect.y0 > top:
                    found.add(round((rect.y0 + rect.y1) / 2, 2))
    merged: list[float] = []
    for y in sorted(found):
        if not merged or y - merged[-1] > .5:
            merged.append(y)
    return merged


def band_errors(bands: list[float], rows: list[int]) -> list[str]:
    """The rules *bands* bound rows of *rows* grid rows each, top down (within .6 pt: a frame's medium rule is
    drawn inside its boundary)."""
    if len(bands) < len(rows) + 1:
        return [f"{len(bands)} rules for {len(rows)} rows"]
    return [f"row {index}: {low - high:.2f} != {count} rows" for index, (high, low, count)
            in enumerate(zip(bands, bands[1:], rows)) if abs(low - high - count * GRID.pitch_y) > .6]


def drawn_order_errors(drawn: str, units) -> list[str]:
    """The drawn text (whitespace removed) is each unit's record in the order of the units; a table printed in parts
    (frame_report.TableParts: the coefficient tables) draws its parts' texts one after another, and its record is the
    whole table's (the parts hold the same cells, the cases repeated)."""
    from webpier.reporting.stages.frame_report import FigureSpec, TableParts, plain

    errors, position = [], 0
    for unit in units:
        parts = isinstance(unit.value, FigureSpec) and isinstance(unit.value.block, TableParts)
        want = "".join(plain(unit.value.block.specs if parts else unit.value).split())
        got = drawn[position:position + len(want)]
        position += len(want)
        if got != want:
            errors.append(f"{unit.key}: {got[:40]!r} != {want[:40]!r}")
    if position != len(drawn):
        errors.append(f"{len(drawn) - position} drawn characters after the last unit")
    return errors
