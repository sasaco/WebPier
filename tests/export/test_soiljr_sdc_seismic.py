"""The seismic tables of the 解析連携データ (.sdc) that the JRSNAP model of a pile foundation takes (decision 93).

``pile_s53`` is what the real SOIL-JR 5.3 returned for its sample RC橋脚（杭基礎）サンプルデータS (the .sdc the JRSNAP sample
01_サンプル(V53)：RC橋脚L was linked to: L1 and L2 tables); ``pile_cast`` is what SOIL-JR 5.2 returned for the sample E (one table
of 地震時 for each side). The values are those printed in the files.
"""

from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.export.soiljr import SdcError
from webpier.export.soiljr.sdc_seismic import parse_seismic

FIXTURES = Path(__file__).parents[1] / "fixtures" / "soiljr"


def text(name: str) -> str:
    return (FIXTURES / f"{name}.sdc").read_bytes().decode("cp932")


def encoded(value: str) -> bytes:
    return value.encode("cp932")


def seismic(name: str):
    return parse_seismic((FIXTURES / f"{name}.sdc").read_bytes())


def test_the_l2_tables_of_sdc_5_3_are_the_ones_the_model_takes():
    found = seismic("pile_s53")
    assert found.version == "Ver.5.3.1" and found.title == "RC橋脚（杭基礎）サンプルデータ"
    assert [direction.name for direction in found.directions] == ["橋軸方向", "直角方向"]
    along = found.direction("橋軸方向")
    assert along.columns == ("1列目", "2列目", "3列目") and along.rows == 3 and along.depth_piles == (3, 2, 3)
    assert along.inverse_beta == 3.385
    layer = along.layers[1]
    assert (layer.number, layer.thickness) == (2, 5.0)
    assert layer.horizontal == (242671.0, 161780.0, 242671.0)  # 短期(非線形)
    assert (layer.pressure_upper, layer.pressure_lower) == ((1974.1, 1052.8, 1381.8), (3516.3, 1875.4, 2461.4))
    # the second table of each side (安定レベル2・3, L2): ⊿l = 4.215, the first and the second slope; 降伏点 and 終局点
    assert layer.push.length == 4.215 and layer.push.first == (86169.0, 57446.0, 86169.0)
    assert layer.push.second == (2350.0, 1567.0, 2350.0)
    assert layer.push.yield_load == (1153.6, 769.1, 1153.6) and layer.push.ultimate == (1357.2, 904.8, 1357.2)
    assert layer.pull == layer.push
    bottom = along.layers[4]
    assert (bottom.push.length, bottom.pull.length) == (1.0, 2.0)  # the least embedment is left out on the push side only
    assert (bottom.push.first, bottom.pull.first) == ((134640.0, 89760.0, 134640.0),) * 2
    assert along.layers[0].push.length == 0.0 and along.layers[0].push.first == (0.0, 0.0, 0.0)
    tip = along.tip
    assert tip.first == (235621.0, 157081.0, 235621.0) and tip.second == (67320.0, 44880.0, 67320.0)
    assert tip.yield_load == (3769.9, 2513.3, 3769.9) and tip.ultimate == (9424.8, 6283.2, 9424.8)
    assert tip.horizontal == (0.0, 0.0, 0.0) and tip.rotation == (0.0, 0.0, 0.0)


def test_the_one_table_of_sdc_5_2_has_the_same_values_in_the_same_form():
    found = seismic("pile_cast")
    assert found.version == "Ver.5.2.3"
    along = found.direction("橋軸方向")
    layer = along.layers[1]
    assert layer.horizontal == (113755.0, 75837.0, 113755.0)
    assert layer.push.length == 3.447 and layer.push.first == (40393.0, 26928.0, 40393.0)
    assert layer.push.second == (971.0, 647.0, 971.0) and layer.push.yield_load == (508.9, 339.3, 508.9)
    assert layer.pull.ultimate == (593.8, 395.8, 593.8)
    # SOIL-JR 5.2 gives the sample E a bottom layer within the least embedment: nothing on the push side
    assert (along.layers[4].push.length, along.layers[4].pull.length) == (0.0, 1.0)
    assert along.tip.second == (68962.0, 45974.0, 68962.0) and along.tip.yield_load == (4241.2, 2827.4, 4241.2)


def test_a_direction_the_file_does_not_have_is_an_error():
    with pytest.raises(InputError, match="斜め方向"):
        seismic("pile_s53").direction("斜め方向")


@pytest.mark.parametrize("name", ["pile_steel_grid", "pile_steel_staggered"])
def test_only_a_layout_that_lists_its_rows_is_read(name):
    with pytest.raises(SdcError, match="杭の列を並べた配置"):
        seismic(name)


def test_what_is_not_an_sdc_of_sdc_5_2_or_5_3_is_refused():
    with pytest.raises(SdcError, match="CP932"):
        parse_seismic(b"\x81")
    with pytest.raises(SdcError, match="5.2・5.3 の .sdc ではありません"):
        parse_seismic(b"")
    with pytest.raises(SdcError, match="5.2・5.3 の .sdc ではありません"):
        parse_seismic(encoded(text("pile_s53").replace("Ver.5.3.1", "Ver.5.4.0")))
    with pytest.raises(SdcError, match="【解析用地盤ばね値】がありません"):
        parse_seismic(encoded(text("pile_s53").replace("【解析用地盤ばね値】", "【別】")))
    with pytest.raises(SdcError, match="方向（（１）橋軸方向）がありません"):
        parse_seismic(encoded(text("pile_s53").replace("（１）橋軸方向", "").replace("（２）直角方向", "")))


def broken(old: str, new: str, count: int = 1) -> bytes:
    source = text("pile_s53")
    assert old in source, old
    return encoded(source.replace(old, new, count))


def test_a_section_the_model_needs_must_be_there():
    with pytest.raises(SdcError, match="橋軸方向: g）がありません"):
        parse_seismic(broken("g）杭先端の支持力", "x）杭先端の支持力", 1))


def test_the_sides_of_d_and_e_are_found_by_their_titles():
    with pytest.raises(SdcError, match="d）に【押込み側】または【引抜き側】がありません"):
        parse_seismic(broken("【押込み側】", "【別】", 1))
    source = text("pile_s53")
    start = source.index("【引抜き側】")
    stop = source.index("※粘着力度が10kN", start)
    without_rows = source[:start] + "【引抜き側】\r\n" + source[stop:]
    with pytest.raises(SdcError, match="d）に層の表がありません"):
        parse_seismic(encoded(without_rows))


def test_the_horizontal_table_must_have_its_layers():
    source = text("pile_s53")
    start, stop = source.index("b）水平地盤ばね値"), source.index("c）有効抵抗土圧力")
    lines = [line for line in source[start:stop].split("\r\n") if not line[:1].isdigit()]
    with pytest.raises(SdcError, match="b）または c）に層の表がありません"):
        parse_seismic(encoded(source[:start] + "\r\n".join(lines) + source[stop:]))


def test_the_tables_of_one_direction_must_have_the_same_layers():
    source = text("pile_s53")
    first = source.index("5, 2.000, 94794")  # the last row of b) of the first direction
    line_end = source.index("\r\n", first)
    with pytest.raises(SdcError, match="b）〜e）の層の数が違います"):
        parse_seismic(encoded(source[:first] + source[line_end + 2:]))


def test_the_rows_of_each_table_must_have_their_fields():
    with pytest.raises(SdcError, match="b）または c）の層 1 の項目数が違います"):
        parse_seismic(broken("1, 2.600, 47397, 31598, 47397, 94793, 63195, 94793, 189586, 126391, 189586",
                             "1, 2.600, 47397, 31598, 47397, 94793, 63195, 94793, 189586, 126391"))
    with pytest.raises(SdcError, match="d）押込み側の層 2 の項目数が違います"):
        parse_seismic(broken("2, 4.215, 86169, 57446, 86169, 2350, 1567, 2350", "2, 4.215, 86169, 57446, 86169, 2350"))
    with pytest.raises(SdcError, match="支持力）の層 2 の項目数が違います"):
        parse_seismic(broken("2, 5.000, 4.215, 1153.6, 769.1, 1153.6, 1357.2, 904.8, 1357.2",
                             "2, 5.000, 4.215, 1153.6, 769.1, 1153.6, 1357.2, 904.8"))
    with pytest.raises(SdcError, match="⊿l がばねの表"):
        parse_seismic(broken("2, 5.000, 4.215, 1153.6, 769.1, 1153.6, 1357.2, 904.8, 1357.2",
                             "2, 5.000, 4.000, 1153.6, 769.1, 1153.6, 1357.2, 904.8, 1357.2"))
    with pytest.raises(SdcError, match="数値でない値があります"):
        parse_seismic(broken("2, 4.215, 86169, 57446, 86169, 2350, 1567, 2350", "2, 4.215, 86169, 57446, 86169, x, 1567, 2350"))


def test_the_tip_blocks_must_be_there_with_their_values():
    with pytest.raises(SdcError, match="f）に杭先端の水平がありません"):
        parse_seismic(broken("杭先端の水平ばね値", "杭先端の別ばね値", 1))
    with pytest.raises(SdcError, match="f）の杭先端の鉛直の項目数が違います"):
        parse_seismic(broken("117810, 78540, 117810, 235621, 157081, 235621, 67320, 44880, 67320",
                             "117810, 78540, 117810, 235621, 157081, 235621, 67320, 44880"))


def test_the_sdc_for_the_liquefaction_is_read_with_the_title_of_its_tip_and_told_apart():
    """Decision 95: ``pile_cast_liquefaction`` is what SOIL-JR 5.2 returned for the same sample E with its layers liquefying:
    the same tables, with 液状化時 for the short-term nonlinear ones; the springs and the pressures are smaller."""
    normal = parse_seismic((FIXTURES / "pile_cast.sdc").read_bytes()).direction("橋軸方向")
    liquefied = parse_seismic((FIXTURES / "pile_cast_liquefaction.sdc").read_bytes(), liquefied=True).direction("橋軸方向")
    assert (liquefied.rows, liquefied.depth_piles) == (normal.rows, normal.depth_piles)
    assert liquefied.inverse_beta != normal.inverse_beta  # 1/β follows the springs
    assert normal.layers[0].horizontal == (75837.0, 50558.0, 75837.0)
    assert liquefied.layers[0].horizontal == (25026.0, 16684.0, 25026.0)
    assert liquefied.layers[0].pressure_upper == (390.8, 208.4, 273.6) and normal.layers[0].pressure_upper[0] == 1184.2
    assert liquefied.tip.first == normal.tip.first and len(liquefied.layers) == len(normal.layers)
    with pytest.raises(SdcError, match="液状化時：杭先端の鉛直がありません"):
        parse_seismic((FIXTURES / "pile_cast.sdc").read_bytes(), liquefied=True)
    with pytest.raises(SdcError, match="地震時：杭先端の鉛直がありません"):
        parse_seismic((FIXTURES / "pile_cast_liquefaction.sdc").read_bytes())
