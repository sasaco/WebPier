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
             with_cases: bool = True) -> bytes:
    """A summary workbook with the layout of Aggre-SE's: *cases* maps the Case number to its (復旧性, 安全性) Khmax
    texts; the No / 名称 rows and the block labels can be left out for the error tests."""
    book = Workbook()
    ws = book.active
    ws.title = sheet
    ws["A1"], ws["A3"] = "地盤区分", "応答値一覧表"
    columns = {number: 4 + index for index, number in enumerate(sorted(cases))}
    if with_cases:
        ws["A4"], ws["B4"], ws["B5"] = "解析ケース", "No", "名称"
        for number, column in columns.items():
            ws.cell(row=4, column=column, value=number)
            ws.cell(row=5, column=column, value=f"線路方向(Case{number}_ρm10_αf1_正向)")
    ws["A8"], ws["B8"], ws["C8"] = "降伏点", "初期降伏震度", "Khy"
    if with_blocks:
        ws["A13"], ws["A17"] = "復旧性", "安全性"
    ws["B13"], ws["C13"] = "応答塑性率", "μ"
    ws["B15"], ws["C15"], ws["B19"], ws["C19"] = "最大応答震度", "Khmax", "最大応答震度", "Khmax"
    for number, (restorability, safety) in cases.items():
        ws.cell(row=15, column=columns[number], value=restorability)
        ws.cell(row=19, column=columns[number], value=safety)
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
