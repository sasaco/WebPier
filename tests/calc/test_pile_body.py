"""The pile body of a steel pipe pile (decision 89, Example橋脚4 III-3.2.2): the pipe from the input, the design force cases WebPier chooses
and the result it holds of SteelDan's values (tests of SteelDan's formulas against the example's tables 3.2.5, 3.2.7 and 3.2.9 are Capacita's)."""

from copy import deepcopy

import pytest

from webpier.calc.pile_body import (Case, PileResponseError, PointForces, SectionForce, assemble, select, steel)
from webpier.core.errors import InputError
from webpier.core.integrity import load_json
from webpier.inputs import parse_input
from example4_support import EXAMPLE4_INPUT


def example4(**changes):
    data = deepcopy(load_json(EXAMPLE4_INPUT.read_bytes()))
    data["杭基礎"]["鋼管ソイルセメント杭"]["段落し"]["段落し後の鋼管厚"] = None  # the body check takes the head's pipe (decision 126)
    for key, value in changes.items():
        data["杭基礎"]["鋼管ソイルセメント杭"][key] = value
    return parse_input(data)


def test_the_pipe_is_the_outer_diameter_and_the_thickness_less_the_corrosion_allowance():
    pipe = steel(example4())
    assert (pipe.grade, pipe.fsyk.value, pipe.fsvyk.value) == ("SKK490", 315.0, 180.0)  # 表 3.2.2
    assert (pipe.diameter.value, pipe.thickness.value) == (798.0, 17.0)  # 800 − 2 × 1, 18 − 1: 図 3.2.1, 表 3.2.5
    assert steel(example4(鋼管材質="SKK400")).fsyk.value == 235.0
    assert steel(example4(鋼管材質="SKK400")).fsvyk.value == 135.0
    assert steel(example4(腐食代=0.0)).diameter.value == 800.0


def test_a_missing_grade_is_named():
    with pytest.raises(InputError, match="杭基礎.鋼管ソイルセメント杭.鋼管材質: 杭体の照査に必要です"):
        steel(example4(鋼管材質=None))


def line(focus, point, distance, largest, smallest):
    return PointForces(focus, point, distance, SectionForce(*largest), SectionForce(*smallest))


LINES = [
    line("M", "ITAN", 0.0, (900.0, 30.0, -100.0, 1), (-950.0, -30.0, -200.0, 2)),  # the head is the joint's: not the pile body
    line("N", "ITAN", 0.0, (10.0, 10.0, -50.0, 3), (10.0, 10.0, -9000.0, 4)),
    line("M", "1", 3.75, (140.0, 31.0, -1500.0, 5), (-20.0, 1.0, -1400.0, 6)),
    line("M", "2", 11.25, (50.0, 3.0, -1000.0, 7), (-190.0, -4.0, -1100.0, 8)),  # |−190| is the largest below the head
    line("S", "1", 3.75, (60.0, 120.0, -2000.0, 9), (-60.0, -150.0, -1900.0, 10)),  # |−150|
    line("S", "JTAN", 26.5, (0.0, 90.0, -500.0, 11), (0.0, -10.0, -400.0, 12)),
    line("N", "1", 3.75, (70.0, 40.0, 100.0, 13), (60.0, 30.0, -4000.0, 14)),  # the smallest Nd is the largest compression
    line("N", "2", 11.25, (10.0, 5.0, -300.0, 15), (12.0, 6.0, -3000.0, 16)),
]


def test_the_cases_are_the_largest_moment_shear_and_compression_below_the_head():
    row = select(2, 8, 3, LINES)
    assert (row.row, row.member, row.piles) == (2, 8, 3)
    moment, shear, axial = (row.cases[case] for case in Case)
    assert (moment.md, moment.vd, moment.nd, moment.combination) == (-190.0, -4.0, -1100.0, 8)
    assert (shear.md, shear.vd, shear.nd, shear.combination) == (-60.0, -150.0, -1900.0, 10)
    assert (axial.md, axial.vd, axial.nd, axial.combination) == (60.0, 30.0, -4000.0, 14)
    assert [row.distances[case] for case in Case] == [11.25, 3.75, 3.75]  # where of the pile each case is


@pytest.mark.parametrize("focus", ["M", "S", "N"])
def test_a_case_with_no_point_below_the_head_is_named(focus):
    lines = [item for item in LINES if item.focus != focus]
    with pytest.raises(PileResponseError, match="杭列 2（部材 8）の杭頭より下の断面力"):
        select(2, 8, 3, lines)


def values(**changes):
    """SteelDan's values of one check: the same for every kind, the keys the result reads."""
    found = {"Md": 69.0, "Nd": 335.7, "Vd": 6.7, "ratio": 0.05, "ratio_tension": -0.2, "ratio_compression": 0.05, "A": 0.04171,
             "I": 0.00318176, "y": 399.0, "fsyd": 300.0, "fsvyd": 171.0, "Nud": 11917.1, "Nu0d": 11917.1, "Mutd": 2278.4,
             "Mucd": 2278.4, "Vyd": 6792.8}
    return {**found, **changes}


def assembled(changes=None):
    pipe = steel(example4())
    rows = [select(1, 7, 3, LINES)]
    found = {(1, case.value, kind): values() for case in Case for kind in ("bending", "shear", "combined")}
    found.update(changes or {})
    return assemble(pipe, rows, found, "1.0.0", "a" * 64)


def test_the_result_holds_what_steeldan_returned_rounded_to_its_printed_digits():
    body = assembled()
    first = body.rows[0].cases[0]
    assert (first.case, first.combination, first.distance.value) == (Case.MOMENT, 8, 11.25)
    assert (first.md.value, first.nd.value, first.vd.value) == (69.0, 335.7, 6.7)
    assert (first.ratio_tension.value, first.ratio_compression.value, first.shear.value, first.combined.value) == (
        -0.2, 0.05, 0.05, 0.05)
    assert first.bending.value == 0.05 and first.ok  # the larger of the two sides
    resistance = body.resistance
    assert (resistance.area.value, resistance.inertia.value, resistance.distance.value) == (0.04171, 0.00318176, 399.0)
    assert (resistance.tension.value, resistance.compression.value, resistance.shear.value) == (11917.1, 11917.1, 6792.8)
    assert (body.gamma_i.value, body.gamma_s.value, body.gamma_b.value) == (1.2, 1.05, 1.05)
    assert body.engine_version == "1.0.0" and body.wsj_sha256 == "a" * 64 and body.ok


def test_a_ratio_above_one_is_not_ok():
    body = assembled({(1, 7, "combined"): values(ratio=1.01)})
    assert not body.rows[0].cases[1].ok and not body.ok
    assert body.rows[0].cases[0].ok


def test_the_tension_side_may_govern():
    body = assembled({(1, 6, "bending"): values(ratio_tension=1.2, ratio_compression=0.5)})
    assert body.rows[0].cases[0].bending.value == 1.2 and not body.ok


def test_a_check_that_is_missing_from_the_result_is_named():
    pipe = steel(example4())
    rows = [select(1, 7, 3, LINES)]
    found = {(1, case.value, kind): values() for case in Case for kind in ("bending", "shear", "combined")}
    del found[(1, 8, "combined")]
    with pytest.raises(PileResponseError, match="杭列 1 のケース 8 の .*combined.* がありません"):
        assemble(pipe, rows, found, "1.0.0", "b" * 64)
    found = {(1, case.value, kind): values() for case in Case for kind in ("bending", "shear", "combined")}
    found[(1, 6, "bending")] = {key: item for key, item in values().items() if key != "ratio_tension"}
    with pytest.raises(PileResponseError, match="ratio_tension がありません"):
        assemble(pipe, rows, found, "1.0.0", "b" * 64)
