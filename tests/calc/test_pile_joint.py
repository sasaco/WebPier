"""The joint of a steel pipe pile with the footing (decision 90, Example橋脚4 III-3.2.2 (b), 杭体設計の手引き 2.4): the section
of the input, the confined concrete, the design forces WebPier chooses and the result it holds of Capacita's Mud (the
example's table 3.2.10 and 3.2.11; tests of Capacita's own calculation of Mud are Capacita's)."""

from copy import deepcopy
from dataclasses import replace

import pytest

from webpier.calc.pile_body import PileResponseError, PointForces, SectionForce, steel
from webpier.calc.pile_joint import Side, assemble, section, select
from webpier.core.errors import InputError
from webpier.core.integrity import load_json
from webpier.inputs import parse_input
from example4_support import EXAMPLE4_INPUT


def example4(**changes):
    data = deepcopy(load_json(EXAMPLE4_INPUT.read_bytes()))
    joint = data["杭基礎"]["鋼管ソイルセメント杭"]["結合部"]
    for key, value in changes.items():
        if key == "中詰めコンクリート_f'ck":
            joint[key] = value
        else:
            joint["軸方向鉄筋"][key] = value
    return parse_input(data)


def joint_section(**changes):
    pier = example4(**changes)
    return section(pier, steel(pier))


def test_the_section_is_what_the_example_prints_in_table_3_2_11():
    found = joint_section()
    assert (found.diameter.value, found.thickness.value, found.corrosion.value) == (798.0, 17.0, 1.0)
    assert (found.bar_count, found.bar_area.value, found.bar_strength.value) == (16, 18240.0, 390.0)  # D38-16本
    assert (found.centroid.value, found.fck.value, found.pipe_strength.value) == (75.0, 27.0, 315.0)


def test_the_bar_area_follows_the_diameter_and_the_count():
    assert joint_section(径=32, 本数=20).bar_area.value == 15884.0  # 794.2 × 20
    assert joint_section(材質="SD345").bar_strength.value == 345.0


@pytest.mark.parametrize("name", ["径", "本数", "材質", "重心位置"])
def test_a_blank_bar_item_is_named(name):
    with pytest.raises(InputError, match=f"杭基礎.鋼管ソイルセメント杭.結合部.軸方向鉄筋.{name}: 結合部の照査に必要です"):
        joint_section(**{name: None})


def test_a_blank_strength_of_the_filling_is_named():
    with pytest.raises(InputError, match="結合部.中詰めコンクリート_f'ck: 結合部の照査に必要です"):
        joint_section(**{"中詰めコンクリート_f'ck": None})


def test_a_bar_without_a_nominal_area_is_named():
    with pytest.raises(InputError, match="結合部.軸方向鉄筋.径: D40 の公称断面積がありません"):
        joint_section(径=40)


def line(focus, point, distance, largest, smallest):
    return PointForces(focus, point, distance, SectionForce(*largest), SectionForce(*smallest))


def test_the_forces_are_those_of_the_largest_bending_moment_of_the_head_for_one_pile():
    lines = [line("N", "ITAN", 0.0, (-60.0, 30.0, -3000.0, 21), (150.0, -20.0, -11700.0, 18)),
             line("M", "ITAN", 0.0, (900.0, 30.0, -3000.0, 1), (-1050.0, -30.0, -11700.0, 2)),
             line("M", "1", 3.75, (2000.0, 40.0, 100.0, 13), (60.0, 30.0, -4000.0, 14))]
    row = select(2, 8, 3, lines)
    assert (row.row, row.member, row.piles) == (2, 8, 3)
    assert (row.forces.md, row.forces.nd, row.forces.combination) == (350.0, 3900.0, 2)  # |−1050| / 3, 11700 / 3: compression positive
    other = select(2, 8, 3, [line("M", "ITAN", 0.0, (900.0, 0.0, -3000.0, 1), (-600.0, 0.0, -11700.0, 2))])
    assert (other.forces.md, other.forces.nd, other.forces.combination) == (300.0, 1000.0, 1)


@pytest.mark.parametrize("lines", [[], [line("M", "1", 3.75, (0.0, 0.0, 0.0, 1), (0.0, 0.0, 0.0, 1))]])
def test_a_member_without_a_head_line_is_an_error(lines):
    with pytest.raises(PileResponseError, match="杭列 1（部材 5）の杭頭の曲げモーメントの行が 0 行あります"):
        select(1, 5, 3, lines)


def head(md, nd, combination):
    return select(1, 3, 3, [line("M", "ITAN", 0.0, (md * 3, 0.0, -nd * 3, combination), (0.0, 0.0, 0.0, 1))])


def test_the_result_holds_the_resistance_and_the_ratio_of_the_example():
    """表 3.2.10 and 3.2.11: Md 284.6 and 284.0, N'd 3847.9 and 1338.1, Mud 2957.2 and 2449.8, γi・Md/Mud 0.12 and 0.14."""
    pull, push = head(284.0, 1338.1, 15), head(284.6, 3847.9, 18)
    rows = [replace(pull, row=1), replace(push, row=2)]
    result = assemble(joint_section(), rows, {1: 2449.8, 2: 2957.2}, "9.9", "abc")
    first, second = (row.check for row in result.rows)
    assert (first.side, first.md.value, first.nd.value, first.mud.value, first.ratio.value) == (
        Side.PULL, 284.0, 1338.1, 2449.8, 0.14)
    assert (second.side, second.md.value, second.nd.value, second.mud.value, second.ratio.value) == (
        Side.PUSH, 284.6, 3847.9, 2957.2, 0.12)
    assert result.ok and (result.engine_version, result.input_sha256) == ("9.9", "abc")
    assert (result.gamma_i.value, result.gamma_c.value, result.gamma_s.value, result.gamma_b.value) == (1.2, 1.3, 1.05, 1.3)


def test_the_sides_are_the_rows_of_the_largest_and_the_smallest_axial_force_and_a_middle_row_has_none():
    rows = [replace(head(100.0, nd, 1), row=number) for number, nd in ((1, 2000.0), (2, 3000.0), (3, 1000.0))]
    sides = [row.check.side for row in assemble(joint_section(), rows, {1: 1000.0, 2: 1000.0, 3: 1000.0}, "v", "w").rows]
    assert sides == [None, Side.PUSH, Side.PULL]
    single = assemble(joint_section(), rows[:1], {1: 1000.0}, "v", "w")
    assert single.rows[0].check.side is None
    equal = [replace(head(100.0, 2000.0, 1), row=number) for number in (1, 2)]
    assert [row.check.side for row in assemble(joint_section(), equal, {1: 1.0, 2: 1.0}, "v", "w").rows] == [None, None]


def test_the_judgement_is_by_the_printed_ratio():
    rows = [head(1000.0, 1000.0, 1)]
    ok = assemble(joint_section(), rows, {1: 1200.0}, "v", "w")
    assert ok.rows[0].check.ratio.value == 1.0 and ok.ok  # 1.2 × 1000 / 1200
    assert not assemble(joint_section(), rows, {1: 1190.0}, "v", "w").ok


def test_a_missing_resistance_is_named():
    with pytest.raises(PileResponseError, match="杭列 1 の Mud がありません"):
        assemble(joint_section(), [head(1.0, 1.0, 1)], {}, "v", "w")
