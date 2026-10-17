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
                labelled = text.startswith(ROW_WORDS)
                if labelled and len(numbers) in (3, 5):
                    if len(numbers) == 3:
                        ok = _product(numbers[0], numbers[1], numbers[2])
                    else:
                        ok = _product(numbers[0], numbers[1], numbers[2]) and _product(numbers[2], numbers[3], numbers[4])
                    checks.append(RowCheck(page.number + 1, text, "row", ok))
                    rows.append(numbers)
                elif text.startswith("合計") and rows and len(numbers) in (2, 3):
                    columns = (0, 2) if len(numbers) == 2 else (0, 2, 4)
                    sums = [sum((Decimal(row[c]) for row in rows), Decimal(0)) for c in columns]
                    ok = all(total == Decimal(number) for total, number in zip(sums, numbers, strict=True))
                    checks.append(RowCheck(page.number + 1, text, "total", ok))
                    rows = []
                elif any("LR" in word or word.startswith("EQ") or word == "E" for word in words) and len(numbers) >= 3 \
                        and all(len(n.partition(".")[2]) == 2 for n in numbers[-3:]):
                    a, b, c = numbers[-3:]
                    checks.append(RowCheck(page.number + 1, text, "horizontal", Decimal(a) + Decimal(b) == Decimal(c)))
    return checks
