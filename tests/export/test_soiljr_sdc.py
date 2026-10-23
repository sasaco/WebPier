"""The 解析連携データ (.sdc) SOIL-JR 5.2.3 returns, read for the frame of a pile foundation (decision 88).

The three files are what the real SOIL-JR returned, in the three forms of its tables: the sample RC橋脚（杭基礎）サンプルデータE.sdt
(``pile_cast``: a 場所打ち杭 of 3 × 3 piles with the middle one left out, rows listed, a column for each), a 鋼管ソイルセメント杭
in a staggered layout (``pile_steel_staggered``: a column for the odd rows and one for the even) and the 鋼管ソイルセメント杭 of
Example橋脚4 in a grid (``pile_steel_grid``: one column for every row).
"""

from pathlib import Path

import pytest

from webpier.calc.pile_springs import ALL, EVEN, ODD
from webpier.export.soiljr import SdcError, parse_sdc
from webpier.core.errors import InputError

FIXTURES = Path(__file__).parents[1] / "fixtures" / "soiljr"


def sdc(name: str):
    return parse_sdc((FIXTURES / f"{name}.sdc").read_bytes())


def test_the_header_names_the_pile():
    found = sdc("pile_cast")
    assert found.version == "Ver.5.2.3" and found.title.startswith("RC橋脚（杭基礎）")
    assert found.pile["杭長"] == 19 and found.pile["突出長"] == 0 and found.pile["根入れ深さ"] == 1
    assert [direction.name for direction in found.directions] == ["橋軸方向", "直角方向"]


def test_a_sample_that_lists_its_rows_has_a_column_for_each_row():
    along = sdc("pile_cast").direction("橋軸方向")
    assert along.columns == ("1列目", "2列目", "3列目") and along.rows == 3 and along.inverse_beta == 4.153
    assert [(row.number, row.distance, row.piles) for row in along.listed_rows] == [(1, 0, 3), (2, 3, 2), (3, 6, 3)]
    assert along.depth_piles == (3, 2, 3)  # the middle pile of the middle row is left out
    assert [along.column(row) for row in (1, 2, 3)] == [0, 1, 2]
    layer = along.layers[0]
    assert (layer.thickness, layer.horizontal_long, layer.horizontal_short) == (
        2.6, (18959.0, 12639.0, 18959.0), (37918.0, 25279.0, 37918.0))
    assert (layer.shear_thickness, layer.shear_long, layer.shear_short) == (
        2.6, (13464.0, 8976.0, 13464.0), (26928.0, 17952.0, 26928.0))
    assert (along.tip_long, along.tip_short) == ((117810.0, 78540.0, 117810.0), (235621.0, 157081.0, 235621.0))
    assert along.tip_horizontal_long == (0.0, 0.0, 0.0) and along.tip_rotation_short == (0.0, 0.0, 0.0)


def test_the_shear_springs_are_those_of_the_push_side():
    """The bottom layer is within the least embedment into the bearing layer: the push side has no shear spring there
    (its 層厚 is 0), the pull side does (decision 88)."""
    layers = sdc("pile_cast").direction("橋軸方向").layers
    assert [layer.thickness for layer in layers] == [2.6, 5.0, 4.0, 6.4, 1.0]
    assert [layer.shear_thickness for layer in layers] == [2.6, 5.0, 4.0, 6.4, 0.0]
    assert layers[-1].shear_long == (0.0, 0.0, 0.0)


def test_a_staggered_layout_has_a_column_for_the_odd_rows_and_one_for_the_even():
    along = sdc("pile_steel_staggered").direction("橋軸方向")
    assert along.columns == (ODD, EVEN) and along.rows == 3 and along.depth_piles == (2, 1)
    assert along.listed_rows == ()
    assert [along.column(row) for row in (1, 2, 3)] == [0, 1, 0]
    assert (along.layers[0].horizontal_long, along.layers[0].shear_long) == ((21349.0, 10675.0), (24236.0, 12118.0))
    assert along.layers[3].thickness == 6.4 and along.layers[3].shear_thickness == 6.2  # the part with a shear spring
    assert along.tip_long == (563678.0, 281839.0)


def test_a_layout_of_equal_rows_has_one_column():
    """Example橋脚4: two rows of three piles along the track, three rows of two piles across it."""
    found = sdc("pile_steel_grid")
    along, across = found.direction("橋軸方向"), found.direction("直角方向")
    assert along.columns == (ALL,) and (along.rows, along.depth_piles, along.inverse_beta) == (2, (3,), 4.027)
    assert across.columns == (ALL,) and (across.rows, across.depth_piles, across.inverse_beta) == (3, (2,), 4.316)
    assert [along.column(row) for row in (1, 2)] == [0, 0]
    first = along.layers[0]
    assert (first.thickness, first.horizontal_long, first.horizontal_short) == (3.75, (14208.0,), (28417.0,))
    assert (first.shear_long, first.shear_short) == ((13534.0,), (27067.0,))
    assert (along.tip_long, along.tip_short) == ((532245.0,), (1064491.0,))
    assert across.tip_long == (354830.0,)


def test_the_springs_of_example4_are_those_of_its_summary_within_the_rounding():
    """Table III-21 (表1.4.9, 1.4.10 times 3): SOIL-JR 5.2 returns them a little different (at most 0.2 %): its own
    arithmetic of the same formulas, not a spring WebPier corrects."""
    import json

    expected = json.loads((FIXTURES.parent / "example4" / "frame_springs.json").read_text(encoding="utf-8"))
    rows = expected["spring_summary"]["longitudinal"]["②長期・短期地盤ばね値 (3本当り)"]["rows"]
    along = sdc("pile_steel_grid").direction("橋軸方向")
    for layer, row in zip(along.layers, rows, strict=True):
        assert layer.thickness == row["thickness_m"]
        assert layer.horizontal_long[0] == pytest.approx(row["kh_horizontal_kN_m2_long"], rel=0.002)
        assert layer.horizontal_short[0] == pytest.approx(row["kh_horizontal_kN_m2_short"], rel=0.002)
        if layer.shear_thickness:  # the last layer has no shear spring on the push side: the known difference
            assert layer.shear_long[0] == pytest.approx(row["kv_vertical_kN_m2_long"], rel=0.002)
            assert layer.shear_short[0] == pytest.approx(row["kv_vertical_kN_m2_short"], rel=0.002)
    assert along.layers[-1].shear_thickness == 0 and rows[-1]["kv_vertical_kN_m2_long"] == 119766
    tip = expected["spring_summary"]["longitudinal"]["②長期・短期地盤ばね値 (3本当り)"]["tip_vertical_node_spring_kN_m"]
    assert along.tip_long[0] == pytest.approx(tip["long"], rel=0.002)
    assert along.tip_short[0] == pytest.approx(tip["short"], rel=0.002)


def test_a_row_outside_the_file_is_an_input_error():
    along = sdc("pile_steel_grid").direction("橋軸方向")
    with pytest.raises(InputError, match="杭列 3 がありません"):
        along.column(3)


def test_a_direction_missing_from_the_file_is_an_error():
    with pytest.raises(InputError, match="直角方向 がありません"):
        sdc("pile_steel_grid").__class__(version="", title="", pile={}, directions=()).direction("直角方向")


def mutate(*pairs: str, name: str = "pile_steel_grid") -> bytes:
    """The file *name* with each (old, new) of *pairs* replaced once (lines as the file has them)."""
    text = (FIXTURES / f"{name}.sdc").read_bytes().decode("cp932")
    for old, new in zip(pairs[::2], pairs[1::2], strict=True):
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        assert old in text
        text = text.replace(old, new, 1)
    return text.encode("cp932")


@pytest.mark.parametrize("data, message", [
    (b"\x81\x20" * 20, "CP932 として読めません"),
    (b"not an sdc\n" * 12, "SOIL-JR 5.2 の .sdc ではありません"),
    (mutate("【解析用地盤ばね値】", "【地盤ばね値】"), "【解析用地盤ばね値】がありません"),
    (mutate("a）杭配置条件および1/β", "x）杭配置条件および1/β"), "a）がありません"),
    (mutate(",,長期,短期(線形解析),短期(非線形解析)", ",,地盤,短期"), "b）に列の見出しがありません"),
    (mutate("\n1, 3.750, 14208,", "\n1, 3.750, abc,"), "数値でない値があります"),
    (mutate("長期,短期\n532245, 1064491, 33290", "長期,短期\n532245, 1064491"), "杭先端の鉛直の項目数が違います"),
    (mutate("杭先端の水平ばね値(kN/m)", "杭先端のばね値(kN/m)"), "杭先端の水平がありません"),
    (mutate("杭長,突出長", "杭の長さ,突出長"), "【杭情報】に杭長の行がありません"),
    (mutate("26.5, 0, 1, 2.7, 200,,", "26.5, 0, 1, 2.7, 200,"), "杭の見出しの項目数と値の数が違います"),
    (mutate("杭列数,奥行き本数,,", "列数,奥行き本数,,"), "a）に杭列数の行がありません"),
    (mutate("2, 3, 3, 4.027", "2, 3, 4.027"), "a）の杭列数の行の項目数が違います"),
    (mutate("【押込み側】", "【押込】"), "d）に【押込み側】がありません"),
    (mutate("\n5, 0.000, 0, 0, 0, 0, 0\n", "\n"), "b）と d）の層の数が違います"),
    (mutate("1, 3.750, 14208, 28417, 56833", "1, 3.750, 14208, 28417"), "b）の層 1 の項目数が違います"),
    (mutate("1, 3.750, 13534, 27067, 0.000, 27067, 943", "1, 3.750, 13534, 27067, 0.000, 27067"),
     "d）の層 1 の項目数が違います"),
    (mutate(",,長期,短期(線形解析),短期(非線形解析)", ",,長期-a,短期(線形解析)-a,短期(非線形解析)-a"), "列の見出し（a）を読めません"),
    (mutate("2, 3, 3, 4.027", "2, 3, 2, 4.027"), "列が1つなのに奥行き本数が奇数列と偶数列で違います（3、2）"),
    (mutate("（１）橋軸方向", "橋軸方向", "（２）直角方向", "直角方向"), "方向（（１）橋軸方向）がありません"),
])


def test_a_file_that_is_not_what_the_frame_reads_is_refused(data, message):  # noqa: ANN001
    with pytest.raises(SdcError, match=message):
        parse_sdc(data)


@pytest.mark.parametrize("pairs, message", [
    (("3, 3, 2, 4.153", "2, 3, 2, 4.153"), "列の数（3）が杭列数（2）と違います"),
    (("\n3, 6, 3\n", "\n"), "杭列を並べた表（2 行）が杭列数（3）と違います"),
])
def test_the_rows_of_a_listed_layout_are_checked_against_its_columns(pairs, message):
    with pytest.raises(SdcError, match=message):
        parse_sdc(mutate(*pairs, name="pile_cast"))


def test_a_pull_side_table_that_is_missing_is_named():
    """The last layer takes the shear spring of the pull side (P5, owner), so d) must have both sides."""
    text = (FIXTURES / "pile_steel_grid.sdc").read_bytes().decode("cp932").replace("【引抜き側】", "【引抜】")
    with pytest.raises(SdcError, match="d）に【引抜き側】がありません"):
        parse_sdc(text.encode("cp932"))
