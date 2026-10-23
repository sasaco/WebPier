"""The 基礎照査連携用データ (.sdr) SOIL-JR 5.2.3 returns, read as tables (decision 85).

The three files are what the real SOIL-JR returned: the sample RC橋脚（杭基礎）サンプルデータE.sdt (``pile_cast``), and its
variant as a 鋼管ソイルセメント杭 with a layer that liquefies (``pile_steel`` and ``pile_steel_liquefaction``, the file
for the liquefaction).
"""

from pathlib import Path

import pytest

from webpier.export.soiljr import SdrError, SdrFile, parse_sdr

FIXTURES = Path(__file__).parents[1] / "fixtures" / "soiljr"


def sdr(name: str) -> SdrFile:
    return parse_sdr((FIXTURES / f"{name}.sdr").read_bytes())


def test_the_header_names_the_pile():
    found = sdr("pile_cast")
    assert found.version == "Ver.5.2.3" and found.title.startswith("RC橋脚（杭基礎）")
    assert found.pile == {"フーチング有無": 1, "杭種": 1, "杭長": 19, "杭径": 1.0, "橋軸杭本数": 3, "直角杭本数": 3,
                          "橋軸杭間隔": 3, "直角杭間隔": 3, "換算抵抗幅算定用杭本数": 8}


def test_every_direction_and_condition_has_its_tables():
    found = sdr("pile_steel")
    assert [(table.direction, table.condition, table.title) for table in found.tables[:5]] == [
        ("橋軸方向", None, "杭配置情報"), ("橋軸方向", "地震時以外", "設計鉛直支持力の算定"),
        ("橋軸方向", "地震時以外", "設計引き抜き抵抗力の算定"), ("橋軸方向", "地震時以外", "水平変位の照査"),
        ("橋軸方向", "地震時以外", "回転角の照査")]
    assert {table.direction for table in found.tables} == {"橋軸方向", "直角方向"}
    assert [table.title for table in found.tables if table.condition == "地震時" and table.direction == "直角方向"] == [
        "設計鉛直支持力の算定", "水平変位の照査", "回転角の照査"]


def test_the_design_limits_of_the_sample():
    vertical = sdr("pile_cast").table("橋軸方向", "地震時以外", "設計鉛直支持力の算定")
    assert vertical.columns[0] == "性能項目" and vertical.columns[-2:] == ("設計鉛直支持力Rvd(kN)", "地盤抵抗係数フラグ")
    assert [row[0] for row in vertical.rows] == ["長期支持性能", "短期支持性能", "安定(地震時以外)", "残留鉛直変位(L1)", "残留鉛直変位(L2)"]
    assert [row[-2] for row in vertical.rows] == [1694.7, 2253.2, 3260.3, 3007.4, 4513.9]
    uplift = sdr("pile_cast").table("直角方向", "地震時以外", "設計引き抜き抵抗力の算定")
    assert [row[-2] for row in uplift.rows][:2] == [216.4, 1671.3]
    horizontal = sdr("pile_cast").table("橋軸方向", "地震時以外", "水平変位の照査")
    assert horizontal.rows[0] == ("長期支持性能", 11.314, "0.4%L≦40mm", 2.828)
    rotation = sdr("pile_cast").table("橋軸方向", "地震時以外", "回転角の照査")
    assert [row[1] for row in rotation.rows] == [2.0, 2.0, 6.0, 10.0, 20.0]


def test_the_pile_layout_is_the_columns_soil_jr_used():
    layout = sdr("pile_cast").table("橋軸方向", None, "杭配置情報")
    assert layout.columns == ("番号", "1列目からの距離", "杭本数")
    assert layout.rows == ((1, 0, 3), (2, 3, 2), (3, 6, 3))


def test_a_table_of_the_seismic_condition_has_its_group_names():
    table = sdr("pile_steel").table("橋軸方向", "地震時", "設計鉛直支持力の算定")
    assert table.groups == (("杭先端支持力", "", "", "杭周面支持力", "", "", "鉛直支持力"),)
    assert len(table.columns) == 8 and table.columns[0] == "先端地盤修正係数frt" and table.columns[6] == ""
    assert table.rows == ((1.3, 8482.3, 11026.99, 1.3, 3417.9, 4443.3, 15470.3, 0),)
    assert sdr("pile_steel").table("橋軸方向", "地震時以外", "設計鉛直支持力の算定").groups == ()


def test_the_file_for_the_liquefaction_has_the_same_form():
    normal, liquefied = sdr("pile_steel"), sdr("pile_steel_liquefaction")
    assert [table.title for table in normal.tables] == [table.title for table in liquefied.tables]
    assert normal.table("橋軸方向", "地震時以外", "設計鉛直支持力の算定").rows != liquefied.table(
        "橋軸方向", "地震時以外", "設計鉛直支持力の算定").rows


def test_a_table_that_is_not_there_is_an_error():
    with pytest.raises(SdrError, match="橋軸方向・地震時 に【存在しない】がありません"):
        sdr("pile_cast").table("橋軸方向", "地震時", "存在しない")


@pytest.mark.parametrize("text,message", [
    ("Ver.5.3.1\r\nタイトル\r\nA,B\r\n1,2\r\n【表】\r\n見出し\r\n1\r\n", "SOIL-JR 5.2 の .sdr ではありません"),
    ("Ver.5.2.3\r\nタイトル\r\nA,B\r\n1\r\n【表】\r\nx\r\n1\r\n", "杭の見出しの項目数と値の数が違います"),
    ("Ver.5.2.3\r\nタイトル\r\nA\r\n1\r\n", ".sdr に表がありません"),
    ("Ver.5.2.3\r\nタイトル\r\nA\r\n1\r\n【表】", "表の見出しが不正です"),
    ("Ver.5.2.3\r\nタイトル\r\nA\r\n1\r\n【表\r\nx\r\n", "表の見出しが不正です"),
    ("Ver.5.2.3\r\nタイトル\r\nA\r\n1\r\n【表】\r\n\r\n", "【表】に見出しがありません"),
    ("Ver.5.2.3\r\nタイトル\r\nA\r\n1\r\n【表】\r\nx\r\n1,2\r\ny\r\n", "【表】の列の数が見出しと違います"),
])
def test_a_file_that_is_not_a_sdr_is_refused(text, message):
    with pytest.raises(SdrError, match=message):
        parse_sdr(text.encode("cp932"))


def test_text_that_is_not_shift_jis_is_refused():
    with pytest.raises(SdrError, match="CP932 として読めません"):
        parse_sdr("Ver.5.2.3\r\n".encode("cp932") + b"\x81")
