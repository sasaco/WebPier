"""The 最大応答震度 of a direction, read from Aggre-SE's summary workbook (decisions 58, 59, 125; CONTEXT.md 最大応答震度).

0711 and 0721 publish the workbook Aggre-SE returns (post/線路方向_Aggre-SE.xlsx, post/線路直角方向_Aggre-SE.xlsx); the
same generation reads the bytes the runner returned, never the published file. Its sheet 応答値一覧表 has one column
per Case (from column D), 12 Cases a band (calc.aggrese_summary), and in each band, in column B, the rows 最大応答震度
(Khmax) of the 復旧性 block (column A 復旧性) and of the 安全性 block; the values are text (0.386). The largest of them
over the Cases used and both blocks is the 最大応答震度 of the direction, at 3 decimals (Example2 13-13: 0.552, the
安全性 value of Case 1; 13-15: 0.386).

The Cases of the 応答変位法 (decision 97: from the stage's ``first_case`` on, after the inertia and liquefaction Cases)
are not used (decision 125): they push the inertia force up to a 最大応答震度 given beforehand, so theirs is not the
pier's response (L1 '-----', L2 a copy of an inertia Case's). They are not read at all. The rows are found by their
headings, not by their numbers, and a workbook without them, or with a value of a used Case that is not a number,
stops the generation (ResponseError).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ...core.printed import Precision, Printed
from .._exact import put
from ..aggrese_summary import SHEET, summary_bands

HEADING = "最大応答震度"
BLOCKS = ("復旧性", "安全性")
KH = Precision(3, "")


class ResponseError(ValueError):
    """The workbook does not hold the 最大応答震度 as decision 59 expects."""


@dataclass(frozen=True)
class ResponseValue:
    """One 最大応答震度 of the workbook: of a Case and a block."""

    case: int  # the Case number (the sheet's No row)
    name: str  # the Case name (the sheet's 名称 row)
    block: str  # 復旧性 or 安全性
    kh: Printed


@dataclass(frozen=True)
class MaxResponse:
    file: str  # the published workbook the values come from (the stage's file name)
    # the Khmax of every Case used (all but those of the 応答変位法), 復旧性 Case by Case, then 安全性
    values: tuple[ResponseValue, ...]
    adopted: ResponseValue  # the largest; the earlier one on a tie

    @property
    def kh(self) -> Printed:
        return self.adopted.kh


def _number(text: str, where: str) -> Printed:
    try:
        return put(KH, Decimal(text))
    except InvalidOperation as exc:
        raise ResponseError(f"{where} の最大応答震度 {text!r} を数値として読めません") from exc


def read_max_response(xlsx: bytes, file: str, response_from: int | None = None) -> MaxResponse:
    """The 最大応答震度 of the summary workbook bytes *xlsx*, published as *file*, of the Cases before *response_from*
    (the first Case of the 応答変位法; None: every Case)."""
    bands = summary_bands(xlsx, file, ResponseError)
    if not bands or any(band.row("名称") is None for band in bands):
        raise ResponseError(f"{file} の「{SHEET}」に Case の行（No・名称）がありません")
    used = [(band, index, number) for band in bands for index, number in band.cases
            if response_from is None or number < response_from]
    if not used:
        raise ResponseError(f"{file} の「{SHEET}」に Case がありません")
    values: list[ResponseValue] = []
    for block in BLOCKS:
        for band, index, number in used:
            row = band.row(HEADING, block)
            if row is None:
                raise ResponseError(f"{file} の「{SHEET}」に {'・'.join(BLOCKS)} の「{HEADING}」の行がありません")
            values.append(ResponseValue(number, band.row("名称")[index], block,
                                        _number(row[index], f"{file} Case{number} {block}")))
    adopted = max(values, key=lambda value: value.kh.value)  # the first of equal values
    return MaxResponse(file, tuple(values), adopted)
