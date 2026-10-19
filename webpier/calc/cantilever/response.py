"""The 最大応答震度 of a direction, read from Aggre-SE's summary workbook (decisions 58, 59; CONTEXT.md 最大応答震度).

0711 and 0721 publish the workbook Aggre-SE returns (post/線路方向_Aggre-SE.xlsx, post/線路直角方向_Aggre-SE.xlsx); the
same generation reads the bytes the runner returned, never the published file. Its sheet 応答値一覧表 has one column
per Case (from column D) and, in column B, the rows 最大応答震度 (Khmax) of the 復旧性 block (column A 復旧性) and of
the 安全性 block; the values are text (0.386). The largest of them over every Case and both blocks is the 最大応答震度
of the direction, at 3 decimals (Example2 13-13: 0.552, the 安全性 value of Case 1; 13-15: 0.386). The rows are found
by their headings, not by their numbers, and a workbook without them, or with a value that is not a number, stops the
generation (ResponseError).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
import zipfile

from openpyxl import load_workbook

from ...core.printed import Precision, Printed
from .._exact import put

SHEET = "応答値一覧表"
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
    values: tuple[ResponseValue, ...]  # every Khmax of the sheet, Case by Case, 復旧性 then 安全性
    adopted: ResponseValue  # the largest; the earlier one on a tie

    @property
    def kh(self) -> Printed:
        return self.adopted.kh


def _text(cell) -> str:
    return "" if cell.value is None else str(cell.value).strip()


def _number(text: str, where: str) -> Printed:
    try:
        return put(KH, Decimal(text))
    except InvalidOperation as exc:
        raise ResponseError(f"{where} の最大応答震度 {text!r} を数値として読めません") from exc


def read_max_response(xlsx: bytes, file: str) -> MaxResponse:
    """The 最大応答震度 of the summary workbook bytes *xlsx*, published as *file*."""
    if not zipfile.is_zipfile(BytesIO(xlsx)):
        raise ResponseError(f"{file} が xlsx（zip）ではありません")
    try:
        workbook = load_workbook(BytesIO(xlsx), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises several kinds for a damaged workbook
        raise ResponseError(f"{file} を読めません（{exc}）") from exc
    if SHEET not in workbook.sheetnames:
        raise ResponseError(f"{file} にシート「{SHEET}」がありません")
    rows = list(workbook[SHEET].iter_rows(min_col=1, max_col=workbook[SHEET].max_column))
    workbook.close()
    numbers = next((row for row in rows if _text(row[1]) == "No"), None)
    names = next((row for row in rows if _text(row[1]) == "名称"), None)
    if numbers is None or names is None:
        raise ResponseError(f"{file} の「{SHEET}」に Case の行（No・名称）がありません")
    cases = [(index, int(float(_text(cell))), _text(names[index])) for index, cell in enumerate(numbers)
             if index >= 3 and _text(cell)]
    if not cases:
        raise ResponseError(f"{file} の「{SHEET}」に Case がありません")
    values: list[ResponseValue] = []
    block = ""
    for row in rows:
        if _text(row[0]) in BLOCKS:
            block = _text(row[0])
        if _text(row[1]) != HEADING or not block:
            continue
        for index, number, name in cases:
            values.append(ResponseValue(number, name, block, _number(_text(row[index]), f"{file} Case{number} {block}")))
    if {value.block for value in values} != set(BLOCKS):
        raise ResponseError(f"{file} の「{SHEET}」に {'・'.join(BLOCKS)} の「{HEADING}」の行がありません")
    adopted = max(values, key=lambda value: value.kh.value)  # the first of equal values
    return MaxResponse(file, tuple(values), adopted)
