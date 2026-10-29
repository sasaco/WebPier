"""The SOIL-JR 5.2.3 input (.sdt) of a pile foundation (decision 85, ADR-0013).

``tests/fixtures/soiljr/pile_cast.sdt`` is what the writer gives for tests/fixtures/inputs/pile.json, the SOIL-JR 5.2 sample
RC橋脚（杭基礎）サンプルデータE.sdt: with the real SOIL-JR it returned the sample's own .sdr and .sdc byte for byte
(scripts/accept_pile_ground.py), so the file is the sample's model as WebPier writes it (the ground resistance
coefficients and the modulus columns are written in the form SOIL-JR finds them itself from: the empty mark, Ex = Ed).
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.calc.pile_ground import calculate_pile_ground
from webpier.export.soiljr import SOIL_JR_VERSION, build_sdt
from webpier.export.soiljr.sdt import EMPTY, number, spaced, zone
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
PILE = json.loads((FIXTURES / "inputs" / "pile.json").read_text(encoding="utf-8"))
GOLDEN = (FIXTURES / "soiljr" / "pile_cast.sdt").read_bytes()
TITLE, DESCRIPTION = "RC橋脚（杭基礎）サンプルデータ", "場所打ち杭 3×3 中抜き"


def sdt(changes=None, *, title=TITLE, description=DESCRIPTION) -> str:
    data = deepcopy(PILE)
    for path, value in (changes or {}).items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value
    return build_sdt(calculate_pile_ground(parse_input(data)), title=title, description=description).decode("cp932")


def lines(text: str) -> list[str]:
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    return text.split("\r\n")[:-1]


def test_the_sample_is_written_byte_for_byte():
    assert sdt().encode("cp932") == GOLDEN
    assert GOLDEN.startswith(SOIL_JR_VERSION.encode("ascii") + b"\r\n")


def test_every_line_ends_with_crlf_and_the_text_is_shift_jis():
    text = GOLDEN.decode("cp932")
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    assert lines(text)[:3] == ["Ver.5.2.3.T08", "●基本条件●", TITLE]


def test_numbers_as_a_comma_separated_line_and_alone_on_a_line():
    assert [number(value) for value in (19.0, 0.785398, 2.8, 0, -0.0, 24.5, -3.0)] == [
        "19", "0.785398", "2.8", "0", "0", "24.5", "-3"]
    assert (spaced(8), spaced(0), spaced(-1)) == (" 8 ", " 0 ", "-1 ")
    assert zone(0, 0) == " 0             0 "  # the first fills a zone of 14 characters


def test_the_sections_are_in_the_order_soil_jr_reads_them():
    marks = [line for line in lines(sdt()) if line.startswith("●")]
    assert marks == ["●基本条件●", "●フーチング形状●", "●杭条件●", "●地盤条件●", "●地盤抵抗係数", "●液状化の低減係数"]


def test_the_ground_resistance_coefficients_are_left_for_soil_jr_to_find():
    body = lines(sdt())
    start = body.index("●地盤抵抗係数") + 1
    assert body[start:start + 5] == [",".join([EMPTY] * 11 + ["0"])] * 5
    assert body[start + 5] == f"{EMPTY},{EMPTY},0"


def test_the_footing_shape_has_no_value():
    body = lines(sdt())
    assert body[body.index("●フーチング形状●") + 1] == ",".join([EMPTY] * 5)
    assert body[body.index("●基本条件●") + 4:body.index("●基本条件●") + 7] == [" 1 ", "1,1", " 8 "]  # B_Kind, フーチング, n


def test_the_pile_lines_of_a_cast_in_place_pile():
    body = lines(sdt())
    start = body.index("●杭条件●") + 1
    assert body[start] == "1,3,3,3,3,3,3,3,3,1,1,0,0,1,0,0"
    assert body[start + 1] == f"19,0,1,2.8,{EMPTY},22.4,1,{EMPTY},{EMPTY},{EMPTY},{EMPTY},0.785398,0.049087,24.5"
    assert body[start + 3:start + 12] == [" 1 ", "橋軸方向", "3,0", "2,3", "3,6", "直角方向", "3,0", "2,3", "3,6"]
    assert body[start + 12:start + 16] == ["", " 1 ", "2,2", ""]


def test_the_pile_lines_of_a_steel_soil_cement_pile():
    body = lines(sdt({"下部構造/基礎形式": "鋼管ソイルセメント杭", "outputs/detailing": False}))  # (decision 123)
    start = body.index("●杭条件●") + 1
    assert body[start] == "1,3,3,3,3,3,3,3,3,5,7,0,0,0,0,0"
    assert body[start + 1] == f"19,0,1.2,2.8,200,{EMPTY},1.2,1,18,{EMPTY},1,1.130973,0.006304,24.5"


def test_a_staggered_layout_and_its_holes_as_soil_jr_takes_them():
    layout = {"形式": "千鳥", "線路方向の列の位置": [0.0, 2.0, 4.0], "線路直角方向の列の位置": [0.0, 3.0, 6.0],
              "抜く杭": [{"線路方向の列": 3, "線路直角方向の列": 1}]}
    body = lines(sdt({"杭基礎/配置": layout}))
    start = body.index("●杭条件●") + 1
    # 千鳥, the intervals 2 and 3: Lm Ln of the line direction (4, 3) and of the cross direction (3, 4)
    assert body[start] == "2,3,3,2,3,4,3,3,4,1,1,0,0,1,0,0"
    assert body[start + 3:start + 12] == [" 1 ", "橋軸方向", "2,0", "1,2", "1,4", "直角方向", "1,0", "1,3", "2,6"]
    assert body[start + 13:start + 16] == [" 1 ", "1,3", ""]  # the pile at (along 3, across 1) → SOIL-JR's (across, along)


def test_the_ground_rows_of_the_sample():
    body = lines(sdt())
    start = body.index("●地盤条件●") + 1
    assert body[start:start + 7] == [
        "5,0", "2.8,0,0,0,0,18,8,0,0,0,0,2,0", "2.6,1,10,0,29,18,8,14286,1,1,14286,1,0",
        "5,1,15,0,31,18,8,21429,1,1,21429,1,0", "4,2,4,50,0,15,5,2857,1,1,2857,0,0",
        "6.4,2,10,100,0,16,6,4464,1,1,4464,0,0", "1,1,50,0,38,20,10,71429,1,1,71429,1,0"]
    assert body[start + 7:start + 9] == [zone(0, 0), " 0 "]  # qbuk's method and value; qsuk's method


def test_the_liquefaction_flag_and_the_reduction_of_each_layer():
    layers = deepcopy(PILE["地盤データ"]["層"])
    layers[2]["De"] = 0.5
    layers[4]["De"] = 0.333
    body = lines(sdt({"地盤データ/層": layers}))
    start = body.index("●液状化の低減係数")
    assert body[start + 1:start + 7] == [" 1 ", "1,1", "2,0.5", "3,1", "4,0.333", "5,1"]
    assert body[start + 7:] == ["", "", "0,2,1,0"]
    assert lines(sdt())[lines(sdt()).index("●液状化の低減係数") + 1] == " 0 "


def test_the_description_lines_are_counted():
    body = lines(sdt(description="一行目\r\n二行目\r\n三行目"))
    assert body[3:7] == [" 3 ", "一行目", "二行目", "三行目"]
    assert lines(sdt(description=""))[3:5] == [" 1 ", ""]


@pytest.mark.parametrize("kwargs,message", [
    ({"title": "あ" * 65}, "タイトルは128バイト以内"),
    ({"description": "い" * 257}, "説明は512バイト以内"),
    ({"title": "🙂"}, "タイトルを Shift-JIS で書けません"),
    ({"description": "一\r二"}, "説明は512バイト以内"),
])
def test_a_title_or_description_soil_jr_cannot_take_is_refused(kwargs, message):
    with pytest.raises(ValueError, match=message):
        sdt(**kwargs)
