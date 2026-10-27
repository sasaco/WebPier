"""The frame of a pile foundation (decision 88): the piles under the footing, bundled by row, on the springs SOIL-JR returned.

The input is Example橋脚4 (.claude/docs/Example橋脚4/pre/input.json: a 鋼管ソイルセメント杭, two rows of three piles along the
track, three rows of two across it) with the .sdc the real SOIL-JR 5.2 returned for it (tests/fixtures/soiljr/pile_steel_grid.sdc).
Expected values are those the figures and the tables of the example print (tests/fixtures/example4/frame_springs.json); the
.sdc of the 場所打ち杭 sample (pile.json) covers the rows that are listed and the springs of the odd and even rows.
"""

import json
from pathlib import Path

import pytest

from webpier.calc.frame import Direction, NodeRole, Region
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.pile_frame import LONGITUDINAL, TRANSVERSE, PileFoundation, pile_group, section
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.core.errors import InputError
from webpier.core.integrity import load_json
from webpier.export.soiljr import parse_sdc
from webpier.inputs import parse_input
from example4_support import EXAMPLE4_INPUT

FIXTURES = Path(__file__).parents[1] / "fixtures"
EXPECTED = json.loads((FIXTURES / "example4" / "frame_springs.json").read_text(encoding="utf-8"))


def example4(**changes):
    return parse_input(load_json(EXAMPLE4_INPUT.read_bytes()))


def foundation(pier, name="pile_steel_grid"):
    return PileFoundation(calculate_pile_ground(pier), parse_sdc((FIXTURES / "soiljr" / f"{name}.sdc").read_bytes()))


@pytest.fixture(scope="module")
def pier():
    return example4()


def test_the_pile_section_is_the_steel_pipe_less_the_corrosion_allowance(pier):
    found = section(pier, calculate_pile_ground(pier))
    printed = EXPECTED["member_properties"]["pile"]
    assert (found.kind, found.modulus.value) == ("鋼管", 2.0e8)
    assert found.area.value == printed["A_m2_per_pile"] == 0.04171  # 図 1.2.2
    assert found.inertia.value == printed["I_m4_per_pile"] == 0.00318


def test_a_cast_in_place_pile_is_the_circle(pier):
    from webpier.inputs import parse_input
    from pile_ground_support import pile_pier

    pile = pile_pier()
    found = section(pile, calculate_pile_ground(pile))
    assert (found.kind, found.diameter.value) == ("円形断面", 1.0)
    assert (found.area.value, found.inertia.value) == (0.78540, 0.04909)  # π/4 and π/64 of D = 1
    assert found.modulus.value == 2.24e7  # Ec 22.4 kN/mm2


@pytest.mark.parametrize("direction, rows, depth, spacing", [(LONGITUDINAL, 2, 3, 5.0), (TRANSVERSE, 3, 2, 3.0)])
def test_the_rows_stand_where_the_figure_puts_them(pier, direction, rows, depth, spacing):
    group = pile_group(pier, foundation(pier), direction)
    assert len(group.rows) == rows and {row.piles for row in group.rows} == {depth}
    assert [row.x.value for row in group.rows] == sorted(row.x.value for row in group.rows)
    assert group.rows[-1].x.value - group.rows[0].x.value == spacing * (rows - 1)
    assert group.length.value == 26.5
    for row in group.rows:  # the row is its piles in the depth: A and I times their number (表 III-21 is per row of 3)
        assert row.area.value == round(0.04171 * depth, 5) and row.inertia.value == round(0.00318 * depth, 5)


def test_the_intervals_are_the_layers_and_add_up_to_the_pile(pier):
    group = pile_group(pier, foundation(pier), LONGITUDINAL)
    row = group.rows[0]
    assert [interval.length.value for interval in row.long_term] == [3.75, 7.5, 1.95, 12.3, 1.0]
    assert sum(interval.length.value for interval in row.long_term) == pytest.approx(26.5)
    assert [interval.horizontal.value for interval in row.long_term][:2] == [14208, 19186]
    assert [interval.horizontal.value for interval in row.short_term][:2] == [28417, 38373]
    # the push side of the shear spring, but the last layer (within the least embedment) takes the pull side (P5, owner)
    assert [interval.shear.value for interval in row.long_term] == [13534, 18275, 35702, 119755, 119755]
    assert [interval.shear.value for interval in row.short_term][-1] == 239510


def test_a_layer_whose_shear_spring_ends_before_it_is_split(pier):
    group = pile_group(pier, foundation(pier), LONGITUDINAL)
    stagger = parse_sdc((FIXTURES / "soiljr" / "pile_steel_staggered.sdc").read_bytes())
    layers = stagger.direction("橋軸方向").layers
    from webpier.calc.pile_frame import _intervals

    rows = _intervals(stagger.direction("橋軸方向"), 0, True)
    # layer 4 is 6.4 m with a shear spring over 6.2 m, layer 5 has none on the push side but the pull side's: five layers become six intervals
    assert [(interval.length.value, interval.shear.value) for interval in rows][3:] == [
        (6.2, 7573), (0.2, 0), (1.0, 121176)]
    assert [interval.horizontal.value for interval in rows][3:] == [6671, 6671, 106745]
    assert layers[3].thickness == 6.4


def test_the_tip_has_the_vertical_spring_and_leaves_out_the_others(pier):
    row = pile_group(pier, foundation(pier), LONGITUDINAL).rows[0]
    summary = EXPECTED["spring_summary"]["longitudinal"]["②長期・短期地盤ばね値 (3本当り)"]["tip_vertical_node_spring_kN_m"]
    assert row.long_tip.vertical.value == pytest.approx(summary["long"], rel=0.002)
    assert row.short_tip.vertical.value == pytest.approx(summary["short"], rel=0.002)
    assert (row.long_tip.horizontal.value, row.long_tip.rotation.value) == (0, 0)


def test_the_springs_of_the_rows_of_a_staggered_layout_are_those_of_their_column():
    from pile_ground_support import pile_pier

    pile = pile_pier(**{"下部構造/基礎形式": "鋼管ソイルセメント杭", "杭基礎/配置/形式": "千鳥",
                        "杭基礎/配置/線路方向の列の位置": [-3.0, 0.0, 3.0], "杭基礎/配置/抜く杭": []})
    group = pile_group(pile, foundation(pile, "pile_steel_staggered"), LONGITUDINAL)
    assert [row.column for row in group.rows] == ["奇数列", "偶数列", "奇数列"]
    assert [row.piles for row in group.rows] == [2, 1, 2]
    assert [row.long_term[0].horizontal.value for row in group.rows] == [21349, 10675, 21349]
    assert group.rows[1].long_tip.vertical.value == 281839


def test_a_listed_row_has_its_own_springs():
    from pile_ground_support import pile_pier

    pile = pile_pier()
    group = pile_group(pile, foundation(pile, "pile_cast"), LONGITUDINAL)
    assert [row.column for row in group.rows] == ["1列目", "2列目", "3列目"]
    assert [row.piles for row in group.rows] == [3, 2, 3]
    assert [row.long_term[0].horizontal.value for row in group.rows] == [18959, 12639, 18959]


@pytest.mark.parametrize("change, message", [
    ({"杭基礎/配置/線路方向の列の位置": [-2.5, 0.0, 2.5]}, "杭列数（2）が入力の杭の列（3列）と違います"),
    ({"杭基礎/杭長": 20.0}, "層厚の合計"),
    ({"杭基礎/配置/抜く杭": [{"線路方向の列": 1, "線路直角方向の列": 1}]}, "奥行き本数"),
])
def test_an_sdc_that_does_not_match_the_input_is_refused(change, message):
    from copy import deepcopy

    data = load_json(EXAMPLE4_INPUT.read_bytes())
    for path, value in change.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[part]
        node[key] = value
    pier = parse_input(data)
    with pytest.raises(InputError, match=message):
        pile_group(pier, foundation(pier), LONGITUDINAL)


def test_a_shear_spring_over_more_than_its_layer_is_refused():
    pier = example4()
    found = foundation(pier)
    text = (FIXTURES / "soiljr" / "pile_steel_grid.sdc").read_bytes().decode("cp932")
    text = text.replace("1, 3.750, 13534,", "1, 5.000, 13534,", 1)
    with pytest.raises(InputError, match="せん断ばねの層厚が層厚より大きい"):
        pile_group(pier, PileFoundation(found.ground, parse_sdc(text.encode("cp932"))), LONGITUDINAL)


def test_a_pile_above_the_ground_is_not_modelled():
    pier = example4()
    found = foundation(pier)
    text = (FIXTURES / "soiljr" / "pile_steel_grid.sdc").read_bytes().decode("cp932")
    text = text.replace("26.5, 0, 1,", "26.5, 2, 1,", 1)
    with pytest.raises(InputError, match="突出長"):
        pile_group(pier, PileFoundation(found.ground, parse_sdc(text.encode("cp932"))), LONGITUDINAL)


@pytest.fixture(scope="module")
def longitudinal(pier):
    return calculate_longitudinal(pier, foundation(pier), calculate_reaction(pier))


def test_the_frame_stands_on_the_pile_rows(longitudinal):
    frame = longitudinal.frame
    assert frame.support is None and frame.piles is not None and len(frame.pile_nodes) == 2
    heads = [frame.nodes[n.head - 1] for n in frame.pile_nodes]
    tips = [frame.nodes[n.tip - 1] for n in frame.pile_nodes]
    assert [(n.x.value, n.y.value) for n in heads] == [(-2.5, 0.0), (2.5, 0.0)]
    assert [(n.x.value, n.y.value) for n in tips] == [(-2.5, -26.5), (2.5, -26.5)]
    assert NodeRole.PILE_HEAD in heads[0].roles and NodeRole.PILE_TIP in tips[0].roles
    assert NodeRole.FOOTING_BOTTOM in frame.node(NodeRole.FOOTING_BOTTOM).roles  # the centre of the base stays a node


def test_the_footing_base_is_rigid_and_each_pile_is_one_member(longitudinal):
    frame = longitudinal.frame
    base = [m for m in frame.members if m.region is Region.FOOTING_BASE]
    piles = [m for m in frame.members if m.region is Region.PILE]
    # decision 96: the base is cut at the faces of the column (く体前面), so that the footing's section forces at the face are those of
    # a member end; the column of the example is 2.5 m wide, the rows are ±2.5 m
    assert len(base) == 4 and all(m.rigid and m.height.value == 0 and m.offset.value == 1.25 for m in base)
    faces = [n for n in frame.nodes if NodeRole.COLUMN_FACE in n.roles]
    assert [(n.x.value, n.y.value) for n in faces] == [(-1.25, 0.0), (1.25, 0.0)]
    assert [frame.nodes[m.start - 1].x.value for m in sorted(base, key=lambda m: m.number)] == [-2.5, -1.25, 0.0, 1.25]
    assert len(piles) == 2 and not any(m.rigid for m in piles)
    assert all(m.height.value == 26.5 and m.modulus.value == 2.0e8 for m in piles)
    assert {m.section.area.value for m in piles} == {0.12513}
    assert [(n.member, n.row.number) for n in frame.pile_nodes] == [(piles[0].number, 1), (piles[1].number, 2)]


def test_a_row_under_the_footing_centre_shares_its_node():
    pier = example4()
    result = calculate_transverse(pier, foundation(pier), calculate_reaction(pier))
    frame = result.frame
    heads = [frame.nodes[n.head - 1] for n in frame.pile_nodes]
    assert [n.x.value for n in heads] == [-3.0, 0.0, 3.0]
    centre = frame.node(NodeRole.FOOTING_BOTTOM)
    assert {NodeRole.FOOTING_BOTTOM, NodeRole.PILE_HEAD} <= centre.roles and centre is heads[1]
    # the base is cut at the two faces of the column too (decision 96)
    assert len([m for m in frame.members if m.region is Region.FOOTING_BASE]) == 4
    assert sum(NodeRole.COLUMN_FACE in n.roles for n in frame.nodes) == 2


def test_the_upper_part_is_the_pier_of_the_input(longitudinal, pier):
    """The pier above the footing is built as it is on a direct foundation: beam, haunch, column and the footing as two
    rigid members through its centroid (the Example橋脚4 figure 1.2.3 numbers 1 to 5)."""
    h = pier.substructure.h
    upper = [(m.region, m.height.value) for m in longitudinal.frame.members
             if m.region not in (Region.PILE, Region.FOOTING_BASE)]
    assert [region for region, _ in upper] == [Region.BEAM, Region.HAUNCH, Region.COLUMN, Region.FOOTING_UPPER,
                                               Region.FOOTING_LOWER]
    assert [height for _, height in upper[:3]] == [h[2].value, h[3].value, h[4].value]
    assert longitudinal.frame.pier_height.value == 9.2  # 図 1.2.3
    assert longitudinal.frame.node(NodeRole.FOOTING_TOP).y.value == 2.2  # the footing thickness
