"""Shared helpers for the 0900 / 0910 tests: the current input, its variants, the responses and hand rounding."""

from __future__ import annotations

import json
from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

from webpier.calc.cantilever import CantileverResult, calculate_cantilever, complete_cantilever
from webpier.calc.cantilever.response import MaxResponse, ResponseValue
from webpier.calc.reaction import ReactionResult, calculate_reaction
from webpier.core.printed import Precision
from webpier.inputs import PierInput, parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
SAMPLE = json.loads((FIXTURES / "example2" / "cantilever.json").read_text(encoding="utf-8"))
KH = Precision(3, "")


def document(**changes):
    """current.json with each 'a/b/0/c' path replaced by its value."""
    data = deepcopy(CURRENT)
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value
    return data


def pier(**changes) -> PierInput:
    return parse_input(document(**changes))


def response(kh: float, *, case: int = 1, block: str = "安全性", file: str = "x_Aggre-SE.xlsx") -> MaxResponse:
    """A 最大応答震度 of one Case, as read from the summary workbook."""
    value = ResponseValue(case, f"Case{case}", block, KH(kh))
    return MaxResponse(file, (value,), value)


def workbook(cases: dict[int, tuple[str, str]], *, sheet: str = "応答値一覧表", with_blocks: bool = True,
             with_cases: bool = True, band: int = 12) -> bytes:
    """A summary workbook with the layout of Aggre-SE's: *cases* maps the Case number to its (復旧性, 安全性) Khmax
    texts, *band* Cases a band of 19 rows (Aggre-SE wraps every 12 Cases: each band has its title, No / 名称 rows and
    blocks); the No / 名称 rows and the block labels can be left out for the error tests."""
    book = Workbook()
    ws = book.active
    ws.title = sheet
    ws["A1"] = "地盤区分"
    placed = {number: divmod(index, band) for index, number in enumerate(sorted(cases))}  # (band, column - 4)
    for start in sorted({19 * part for part, _ in placed.values()} or {0}):
        ws.cell(row=start + 3, column=1, value="応答値一覧表")
        if with_cases:
            ws.cell(row=start + 4, column=1, value="解析ケース")
            ws.cell(row=start + 4, column=2, value="No")
            ws.cell(row=start + 5, column=2, value="名称")
        for row, a, b, c in ((8, "降伏点", "初期降伏震度", "Khy"), (13, "復旧性", "応答塑性率", "μ"), (15, None, "最大応答震度", "Khmax"),
                             (17, "安全性", "応答塑性率", "μ"), (19, None, "最大応答震度", "Khmax")):
            if a is not None and (with_blocks or a == "降伏点"):
                ws.cell(row=start + row, column=1, value=a)
            ws.cell(row=start + row, column=2, value=b)
            ws.cell(row=start + row, column=3, value=c)
    for number, (restorability, safety) in cases.items():
        part, offset = placed[number]
        start, column = 19 * part, 4 + offset
        if with_cases:
            ws.cell(row=start + 4, column=column, value=number)
            ws.cell(row=start + 5, column=column, value=f"線路方向(Case{number}_ρm10_αf1_正向)")
        ws.cell(row=start + 15, column=column, value=restorability)
        ws.cell(row=start + 19, column=column, value=safety)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def reaction_of(pier_input: PierInput) -> ReactionResult:
    return calculate_reaction(pier_input)


def result_of(pier_input: PierInput | None = None, *, longitudinal: float = 0.386, transverse: float = 0.552,
              **changes) -> tuple[PierInput, ReactionResult, CantileverResult]:
    """The completed 0900 result for the current input (or *pier_input*, or the input with *changes*)."""
    pier_input = pier_input or pier(**changes)
    reaction = calculate_reaction(pier_input)
    basis = calculate_cantilever(pier_input, reaction)
    completed = complete_cantilever(pier_input, reaction, basis, response(longitudinal), response(transverse))
    return pier_input, reaction, completed


def D(value) -> Decimal:
    """The decimal a person reads from a printed number."""
    return Decimal(repr(float(value)))


def q(value, digits: int) -> Decimal:
    """Hand rounding, 0.5 away from zero."""
    return Decimal(value).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def value(printed) -> Decimal:
    return Decimal(repr(printed.value))


# 13-1 a) B支点最大 (a known difference, decision 125): the sample puts P-16's four axles from the bearing B (levers
# 18.850, 16.650, 13.850, 11.650: RB 517.77). The axle at the joint (the origin girder's end, 18.850 + 0.575 = 19.425
# from A) is counted on the origin girder when RB alone is maximised, and the car of P-16 (axles 2.2, 2.8, 2.2 apart and
# 20 - 2.8 - 2 x 2.2 = 12.8 to the next car's) gives five axles on it, one on the far overhang:
ORIGIN_MAX_LEVERS = [Decimal("19.425"), Decimal("17.225"), Decimal("14.425"), Decimal("12.225"), Decimal("-0.575")]
ORIGIN_MAX_RB = q(160 * sum(ORIGIN_MAX_LEVERS) / Decimal("18.85"), 2)  # 160 x 62.725 / 18.85 = 532.4085
ORIGIN_MAX_RA = 160 * 5 - ORIGIN_MAX_RB  # 267.59


def origin_max_bearing(share: str) -> Decimal:
    """The train on an origin bearing in B支点最大: RB x its share."""
    return q(ORIGIN_MAX_RB * Decimal(share), 2)
