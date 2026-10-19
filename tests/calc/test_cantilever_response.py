"""The 最大応答震度 read from Aggre-SE's summary workbook (decisions 58, 59): the largest Khmax of both blocks over
every Case, found by the headings, and the workbooks that cannot be read."""

from __future__ import annotations

import re

import pytest

from cantilever_support import workbook
from webpier.calc.cantilever.response import HEADING, SHEET, ResponseError, ResponseValue, read_max_response


def test_the_largest_khmax_of_both_blocks_and_every_case():
    found = read_max_response(workbook({1: ("0.547", "0.552"), 2: ("0.565", "0.571")}), "線路直角方向_Aggre-SE.xlsx")
    assert found.file == "線路直角方向_Aggre-SE.xlsx"
    assert found.values == (
        ResponseValue(1, "線路方向(Case1_ρm10_αf1_正向)", "復旧性", found.values[0].kh),
        ResponseValue(2, "線路方向(Case2_ρm10_αf1_正向)", "復旧性", found.values[1].kh),
        ResponseValue(1, "線路方向(Case1_ρm10_αf1_正向)", "安全性", found.values[2].kh),
        ResponseValue(2, "線路方向(Case2_ρm10_αf1_正向)", "安全性", found.values[3].kh))
    assert [value.kh.value for value in found.values] == [0.547, 0.565, 0.552, 0.571]
    assert found.adopted == found.values[3] and found.kh.value == 0.571 and found.kh.digits == 3


def test_one_case_and_a_tie_keeps_the_earlier_value():
    found = read_max_response(workbook({1: ("0.385", "0.386")}), "線路方向_Aggre-SE.xlsx")
    assert (found.adopted.case, found.adopted.block, found.kh.value) == (1, "安全性", 0.386)
    tie = read_max_response(workbook({1: ("0.400", "0.400"), 2: ("0.400", "0.300")}), "x.xlsx")
    assert (tie.adopted.case, tie.adopted.block) == (1, "復旧性")


def test_the_values_are_read_at_three_decimals():
    found = read_max_response(workbook({1: ("0.3855", "0.38649")}), "x.xlsx")
    assert [value.kh.value for value in found.values] == [0.386, 0.386]
    assert found.adopted.block == "復旧性"


def test_a_workbook_that_is_not_a_zip():
    with pytest.raises(ResponseError, match=re.escape("x.xlsx が xlsx（zip）ではありません")):
        read_max_response(b"not a zip", "x.xlsx")


def test_a_zip_that_is_not_a_workbook():
    import io
    import zipfile
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("fake.txt", "FAKE XLSX")
    with pytest.raises(ResponseError, match=re.escape("x.xlsx を読めません")):
        read_max_response(stream.getvalue(), "x.xlsx")


def test_a_workbook_without_the_sheet():
    with pytest.raises(ResponseError, match=re.escape(f"x.xlsx にシート「{SHEET}」がありません")):
        read_max_response(workbook({1: ("0.3", "0.4")}, sheet="設計総括表"), "x.xlsx")


def test_a_sheet_without_the_case_rows():
    with pytest.raises(ResponseError, match=re.escape(f"x.xlsx の「{SHEET}」に Case の行（No・名称）がありません")):
        read_max_response(workbook({1: ("0.3", "0.4")}, with_cases=False), "x.xlsx")


def test_a_sheet_without_a_case():
    with pytest.raises(ResponseError, match=re.escape(f"x.xlsx の「{SHEET}」に Case がありません")):
        read_max_response(workbook({}), "x.xlsx")


def test_a_sheet_without_the_block_headings():
    with pytest.raises(ResponseError, match=re.escape(f"x.xlsx の「{SHEET}」に 復旧性・安全性 の「{HEADING}」の行がありません")):
        read_max_response(workbook({1: ("0.3", "0.4")}, with_blocks=False), "x.xlsx")


def test_a_value_that_is_not_a_number():
    with pytest.raises(ResponseError, match=re.escape("x.xlsx Case2 安全性 の最大応答震度 '-' を数値として読めません")):
        read_max_response(workbook({1: ("0.3", "0.4"), 2: ("0.3", "-")}), "x.xlsx")
