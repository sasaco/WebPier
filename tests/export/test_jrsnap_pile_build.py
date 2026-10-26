"""The NDU model of a pile foundation built from the 0710 and 0720 results (decision 93).

The input is tests/fixtures/inputs/pile.json (the SOIL-JR sample E: a 場所打ち杭 of 3 × 3 piles, the middle one left out, in rows of
3, 2 and 3) with the reinforcement of ``pile_cast_support``; the ground springs are those of the .sdc SOIL-JR 5.2 returned for it
(tests/fixtures/soiljr/pile_cast.sdc). The expected numbers come from the .sdc and the structure of the sample NDU of the
JRSNAP sample RC橋脚L (tests/export/test_jrsnap_pile_records.py): the rows in the NDU are the sample's, the columns of the .sdc go
to the rows by the push.
"""

from dataclasses import replace
from functools import cache
from pathlib import Path

import pytest
from pile_cast_support import cast_input

from webpier.calc.column_rebar import column_layout
from webpier.calc.frame import NodeRole
from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.pile_seismic import pile_row
from webpier.calc.reaction import calculate_reaction
from webpier.calc.seismic_longitudinal import calculate_seismic_longitudinal
from webpier.calc.seismic_transverse import calculate_seismic_transverse
from webpier.core.errors import InputError
from webpier.export.jrsnap import LONGITUDINAL, TRANSVERSE, write_pile_ndu
from webpier.export.jrsnap.build_pile import CONSTRUCTION, build_pile_ndu, pile_sections
from webpier.export.jrsnap.pile_model import PILE
from webpier.export.soiljr import parse_sdc
from webpier.export.soiljr.sdc_seismic import parse_seismic

SDC = (Path(__file__).parents[1] / "fixtures" / "soiljr" / "pile_cast.sdc").read_bytes()
SPRINGS = parse_seismic(SDC)


@cache
def chain(lower=False):
    rebar = {"hoops": {"lower": [{"length_m": 4.0, "diameter_mm": 16, "sets": 1, "pitch_mm": 300.0}]}} if lower else None
    pier = cast_input(rebar)
    foundation = PileFoundation(calculate_pile_ground(pier), parse_sdc(SDC))
    reaction = calculate_reaction(pier)
    return (pier, column_layout(pier), calculate_seismic_longitudinal(pier, foundation, reaction),
            calculate_seismic_transverse(pier, foundation, reaction))


def model(profile=LONGITUDINAL, reverse=False, lower=False, springs=SPRINGS):
    pier, layout, longitudinal, transverse = chain(lower)
    return build_pile_ndu(profile, pier, layout, longitudinal if profile is LONGITUDINAL else transverse, springs,
                          reverse=reverse)


def test_the_joints_of_the_frame_come_first_from_the_top_left_then_those_of_the_piles_row_by_row():
    found = model()
    joints = found.joints
    assert [j.number for j in joints] == list(range(1, 72))  # decision 96: two more, the faces of the column on the footing base
    frame = [(j.x.value, j.y.value) for j in joints[:11]]
    assert frame == sorted(frame, key=lambda xy: (xy[1], xy[0]))  # from the top, at one height from the left
    assert (joints[found.origin - 1].x.value, joints[found.origin - 1].y.value) == (0.0, 0.0)
    heads = [m.i for m in found.members if m.pile]
    assert [(joints[h - 1].x.value, joints[h - 1].y.value) for h in heads] == [(-3.0, 2.7), (0.0, 2.7), (3.0, 2.7)]
    # the nodes of the first row (below its head) are joints 12.. 31: x = -3, from the head down
    ys = [joints[n - 1].y.value for n in range(12, 32)]
    assert ys == sorted(ys) and ys[0] > 2.7 and {joints[n - 1].x.value for n in range(12, 32)} == {-3.0}


def test_each_pile_row_is_one_member_from_its_head_with_its_elements_after_those_of_the_frame():
    found = model()
    piles = [m for m in found.members if m.pile]
    assert [(m.title, m.depth_piles) for m in piles] == [("杭（３本杭）", 3), ("杭（２本杭）", 2), ("杭（３本杭）", 3)]
    assert [m.number for m in found.members] == list(range(1, 14)) and found.members[0].nonlinear
    assert [e.kind for e in found.elements[:10]].count(PILE) == 0 and len(found.elements) == 70
    assert [(p.first, p.last) for p in found.piles] == [(11, 30), (31, 50), (51, 70)]
    # no rigid element at the head: the member starts with its first pile element
    assert all(e.ground is not None for e in found.elements[10:]) and found.elements[10].i == piles[0].i


def test_the_section_of_an_element_is_the_one_of_the_zone_its_upper_end_is_in():
    found = model()
    sections = [row.section for row in found.nonlinear[1:21]]
    depths = [e.top.value for e in pile_row(SPRINGS.direction("橋軸方向"), 1, chain()[2].frame.piles.section.diameter).elements]
    assert sections == [2] * len(sections) and len(found.sections) == 2  # the 2D zone alone goes to the tip
    lower = model(lower=True)
    assert len(lower.sections) == 3
    expected = [2 if depth < 2.0 else (3 if depth < 6.0 else 3) for depth in depths]
    assert [row.section for row in lower.nonlinear[1:21]] == expected
    assert 3 in expected and 2 in expected


def test_the_first_column_of_the_sdc_is_the_front_row_of_the_push():
    along = SPRINGS.direction("橋軸方向")
    diameter = chain()[2].frame.piles.section.diameter
    first = lambda m, row: m.elements[m.piles[row].first - 1].ground.horizontal.value  # noqa: E731
    # 0710 pushes toward −x: the row at the smallest x is the first column
    forward = model()
    assert [first(forward, row) for row in range(3)] == [pile_row(along, c, diameter).elements[0].horizontal.value
                                                          for c in (1, 2, 3)]
    # 0720 pushes toward +x: the row at the largest x is the first column; its reversed combinations push the other way
    across = SPRINGS.direction("直角方向")
    pushed = model(TRANSVERSE)
    assert [first(pushed, row) for row in range(3)] == [pile_row(across, c, diameter).elements[0].horizontal.value
                                                         for c in (3, 2, 1)]
    turned = model(TRANSVERSE, reverse=True)
    assert [first(turned, row) for row in range(3)] == [pile_row(across, c, diameter).elements[0].horizontal.value
                                                         for c in (1, 2, 3)]


def test_an_ndu_has_the_combinations_of_its_push_only():
    forward, reverse = model(TRANSVERSE), model(TRANSVERSE, reverse=True)
    assert [c.reverse for c in forward.combinations] == [False] * 4 and [c.reverse for c in reverse.combinations] == [True] * 4
    assert len(forward.cases) == len(reverse.cases) == 9 or len(forward.cases) == len(reverse.cases)
    assert [c.reverse for c in model().combinations] == [False] * 4


def test_the_bytes_of_the_three_ndus_are_written_and_checked():
    for found in (model(), model(TRANSVERSE), model(TRANSVERSE, reverse=True)):
        data = write_pile_ndu(found)
        assert data.endswith(b"\r\n") and b"SRenkei" not in data


def test_the_sections_come_from_the_pile_reinforcement_and_the_conditions_of_the_input():
    pier = chain()[0]
    sections, ends = pile_sections(pier, LONGITUDINAL, chain()[2].frame.piles.section.diameter)
    (section,) = sections
    assert ends == [] and section.title == "杭(φ1000)：帯鉄筋ctc200" and section.radius.value == 500
    assert (section.diameter.value, section.count, section.hoop_legs, section.hoop_pitch.value) == (32, 20, 2, 200)
    assert section.center.value == 100 + 16 + 16 and section.construction == CONSTRUCTION["自然泥水"] == -3
    assert section.axial_force is None and section.fck.value == 18.8 and len(section.safety) == 12
    assert CONSTRUCTION["安定液使用"] == -4
    zoned, ends = pile_sections(chain(True)[0], LONGITUDINAL, chain()[2].frame.piles.section.diameter)
    assert [s.hoop_pitch.value for s in zoned] == [200, 300] and [float(end) for end in ends] == [2.0]


def test_what_the_ndu_cannot_express_is_an_input_error():
    pier, layout, longitudinal, _ = chain()
    steel = replace(pier, substructure=replace(pier.substructure, foundation="鋼管ソイルセメント杭"))
    with pytest.raises(InputError, match="場所打ち杭だけに対応"):
        build_pile_ndu(LONGITUDINAL, steel, layout, longitudinal, SPRINGS)
    with pytest.raises(InputError, match="逆向の）組合せがありません"):
        build_pile_ndu(LONGITUDINAL, pier, layout, longitudinal, SPRINGS, reverse=True)



def test_a_cut_off_keeps_the_section_of_the_head():
    """Decision 98: Aggre-SE's ⑧ calculates the capacity after the cut-off itself, so the NDU's piles are the head's."""
    pier, _, longitudinal, _ = chain()
    cut = cast_input({"cutoff": {"main_bars": {"diameter_mm": 25, "count": 10}}})
    diameter = longitudinal.frame.piles.section.diameter
    assert pile_sections(cut, LONGITUDINAL, diameter) == pile_sections(pier, LONGITUDINAL, diameter)


def test_the_rows_of_the_sdc_must_be_the_rows_of_the_input():
    along = SPRINGS.direction("橋軸方向")
    with pytest.raises(InputError, match="杭列数（2）が入力の杭の列（3列）と違います"):
        model(springs=replace(SPRINGS, directions=(replace(along, rows=2), *SPRINGS.directions[1:])))
    with pytest.raises(InputError, match="杭列 2 の位置"):
        model(springs=replace(SPRINGS, directions=(replace(along, distances=(0.0, 2.0, 6.0)), *SPRINGS.directions[1:])))
    with pytest.raises(InputError, match="杭列 2 の奥行き本数（3）が入力の杭の列（2本）と違います"):
        model(springs=replace(SPRINGS, directions=(replace(along, depth_piles=(3, 3, 3)), *SPRINGS.directions[1:])))


def test_the_frame_nodes_the_ndu_leaves_out_are_the_pile_tips():
    frame = chain()[2].frame
    assert len([n for n in frame.nodes if NodeRole.PILE_TIP in n.roles]) == 3 and len(model().joints) == 71


def test_the_ndu_for_the_liquefaction_has_the_one_combination_of_rho_m_1_and_alpha_f_1_of_its_push():
    """Decision 95: the same frame and piles; the springs are those of the .sdc for the liquefaction (read by the caller)."""
    pier, layout, longitudinal, transverse = chain()
    liquefied = parse_seismic((Path(__file__).parents[1] / "fixtures" / "soiljr" / "pile_cast_liquefaction.sdc").read_bytes(),
                              liquefied=True)
    for profile, result in ((LONGITUDINAL, longitudinal), (TRANSVERSE, transverse)):
        for reverse in (False, True) if profile is TRANSVERSE else (False,):
            normal = build_pile_ndu(profile, pier, layout, result, SPRINGS, reverse=reverse)
            found = build_pile_ndu(profile, pier, layout, result, liquefied, reverse=reverse, liquefied=True)
            assert len(found.combinations) == 1 and len(normal.combinations) == 4
            (only,) = found.combinations
            assert (only.rho_m.value, only.alpha_f.value, only.reverse) == (1.0, 1.0, reverse)
            assert (found.joints, found.members) == (normal.joints, normal.members)
            assert [(e.number, e.i, e.j, e.kind) for e in found.elements] == [(e.number, e.i, e.j, e.kind) for e in normal.elements]
            assert found.supports != normal.supports and found.sections == normal.sections
    stripped = replace(longitudinal, combinations=tuple(c for c in longitudinal.combinations if c.rho_m.value != 1.0))
    with pytest.raises(InputError, match="組合せがありません"):
        build_pile_ndu(LONGITUDINAL, pier, layout, stripped, liquefied, liquefied=True)
