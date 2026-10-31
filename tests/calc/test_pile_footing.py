"""0800 of a pile foundation (decision 96): the sections of the footing, their effective widths and the section forces.

The input is tests/fixtures/inputs/pile_seismic.json (the SOIL-JR 5.2 sample E: a 場所打ち杭 of two rows of piles along the track, three
across it). The widths are recomputed here from the input's own values; the forces are made up lines of the PIK, so that each
choice (the sense of the moment, the side, the case of the shear) can be checked by hand. The 鋼管ソイルセメント杭 of Example橋脚4
(decision 124) is checked against the independent transcriptions of its 第V編 (tests/fixtures/example4/footing_*.json) and
the hand calculations of decision 124."""

import json
import math
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from webpier.calc import pile_footing as pf
from webpier.calc.footing import LONGITUDINAL, TRANSVERSE
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.pile_body import PileResponseError, PointForces, SectionForce
from webpier.calc.pile_footing import Case, FootingBasis
from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.calc.seismic_longitudinal import calculate_seismic_longitudinal
from webpier.calc.transverse import calculate_transverse
from webpier.core.errors import InputError
from webpier.core.integrity import load_json
from webpier.export.soiljr import parse_sdc
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
EXAMPLE4 = {name: json.loads((FIXTURES / "example4" / f"footing_{name}.json").read_text(encoding="utf-8"))
            for name in ("longitudinal", "transverse")}


@pytest.fixture(scope="module")
def pier():
    return parse_input(load_json((FIXTURES / "inputs" / "pile_seismic.json").read_bytes()))


@pytest.fixture(scope="module")
def frames(pier):
    found = PileFoundation(calculate_pile_ground(pier), parse_sdc((FIXTURES / "soiljr" / "pile_cast.sdc").read_bytes()))
    reaction = calculate_reaction(pier)
    return calculate_longitudinal(pier, found, reaction), calculate_transverse(pier, found, reaction)


@pytest.fixture(scope="module")
def basis(pier, frames) -> FootingBasis:
    return pf.prepare(pier, frames[0], LONGITUDINAL)


def mm(value) -> Decimal:
    return Decimal(repr(value.value)) * 1000


def test_the_sections_are_the_face_and_the_pile_position_each_side(basis):
    names = [(point.key, point.name, point.bending, point.deep_beam) for point in basis.points]
    assert names == [("face_lower", "く体前面（下側引張）", True, None), ("face_upper", "く体前面（上側引張）", True, None),
                     ("pile_lower", "杭位置（下側引張）", True, None), ("pile_upper", "杭位置（上側引張）", True, None),
                     ("face_shear", "く体前面（下側引張）", False, "lower_tension"),
                     ("pile_shear", "杭位置（上側引張）", False, "upper_tension")]
    face, pile = basis.points[0].ends, basis.points[2].ends
    # the rows are at ±3 m and the faces of the column at ±1.35 m: the left member runs pile → face (its J end is the face)
    assert [(end.side, end.point, end.x.value) for end in face] == [("左", "JTAN", -1.35), ("右", "ITAN", 1.35)]
    assert [(end.side, end.point, end.x.value) for end in pile] == [("左", "ITAN", -3.0), ("右", "JTAN", 3.0)]
    assert basis.members == tuple(sorted({end.member for end in (*face, *pile)})) and len(basis.members) == 2


def test_the_effective_widths_are_the_rules_of_the_sample_from_the_inputs_own_values(pier, basis):
    sub = pier.substructure
    h = mm(sub.h[6])
    column = mm(sub.w[6])  # across the plane of the longitudinal direction
    full = mm(sub.w[7]) + column + mm(sub.w[9])
    diameter = mm(pier.piles.cast_in_place.diameter)
    d_lower = h - Decimal(str(basis.bars[0].centroid.value))
    d_upper = h - Decimal(str(basis.bars[1].centroid.value))
    widths = {point.key: point.width for point in basis.points}
    assert Decimal(str(widths["face_lower"].be.value)) == min(column + 2 * d_lower, full).quantize(Decimal(1), ROUND_HALF_UP)
    a = Decimal("1650")  # the nearest row (x = 3) to the face (1.35)
    expected = min(diameter + 2 * (d_upper / 2 + a), full).quantize(Decimal(1), ROUND_HALF_UP)
    assert Decimal(str(widths["face_upper"].be.value)) == expected
    across = [mm(x) for x in pier.piles.layout.across]
    # the shear (decision 124): each pile of the row at x = 3 m, 1650 beyond the face; the end piles (±3000) are outside the
    # column's width (±2250), 750 beyond its side face, the middle one within: a1 = √(1650² + 750²) = 1812 and 1650,
    # be = 0.65√(a1² + d1²) + D = 3060 and 3002; the sum 9122 is limited to Lp + D = 7000
    shear = widths["face_shear"]
    assert column / 2 == Decimal(2250) and d_lower == Decimal(2600) and diameter == Decimal(1000)
    assert [(share.a1.value, share.be.value, share.corner) for share in shear.shares] == [
        (1812.0, 3060.0, True), (1650.0, 3002.0, False), (1812.0, 3060.0, True)]
    assert round(math.hypot(1650, 750)) == 1812 and round(0.65 * math.hypot(1812, 2600) + 1000) == 3060
    assert round(0.65 * math.hypot(1650, 2600) + 1000) == 3002
    assert shear.be.value == min(3060 + 3002 + 3060, max(across) - min(across) + diameter) == 7000
    # the widths D + d of the piles overlap (the spacing is smaller): the width is that from the first pile to the last, limited to B
    assert diameter + d_lower > across[1] - across[0]
    assert Decimal(str(widths["pile_lower"].be.value)) == min(max(across) - min(across) + diameter + d_lower, full)
    # Vsd (decision 124): the footing's whole width B, its own point with the shear alone
    assert widths["pile_shear"].be.value == float(full) and widths["pile_shear"].rule == pf.FULL_WIDTH == "B"
    assert all(width.full.value == float(full) for width in widths.values())


def test_the_stirrups_within_d_across_the_width_are_counted_down(basis):
    point = next(item for item in basis.points if item.deep_beam == "upper_tension")
    assert point.key == "pile_shear" and point.width.be == point.width.full  # across B (decision 124)
    across = int(Decimal(str(point.width.be.value)) // Decimal(str(basis.stirrup_spacing.value)))
    rows = int(Decimal(str(point.depth.value)) // Decimal(str(basis.stirrups.pitch.value)))
    assert point.stirrup_count == across * rows


def line(focus, point, largest, smallest):
    return PointForces(focus, point, 0.0, SectionForce(*largest), SectionForce(*smallest))


def lines(point, *, m, s):
    """M and S lines of a member end: (md, vd, nd, combination) of the largest and the smallest case of each focus (the
    other end of the member has no force)."""
    other = "ITAN" if point == "JTAN" else "JTAN"
    zero = ((0.0, 0.0, 0.0, 1), (0.0, 0.0, 0.0, 1))
    return [line("M", point, *m), line("S", point, *s), line("M", other, *zero), line("S", other, *zero)]


def run(basis, frame_forces):
    """The points' forces when every case reads the lines *frame_forces* (by member) as its own and as the earthquake's."""
    shared = {(pickup, member): found for pickup in basis.pickups.values() for member, found in frame_forces.items()}
    elements = {member: member + 100 for member in basis.members}
    seismic = {elements[member]: found for member, found in frame_forces.items()}
    return pf.complete(basis, shared, seismic, elements).points


def test_a_lower_tension_takes_the_largest_sagging_moment_of_the_side_that_has_it(basis):
    left, right = basis.points[0].ends
    forces = run(basis, {
        left.member: lines("JTAN", m=((900.0, -50.0, 0.0, 3), (-100.0, 40.0, 0.0, 4)),
                           s=((900.0, -50.0, 0.0, 3), (-100.0, 40.0, 0.0, 4))),
        right.member: lines("ITAN", m=((1200.0, 70.0, 0.0, 5), (-300.0, -20.0, 0.0, 6)),
                            s=((1200.0, 70.0, 0.0, 5), (-300.0, -20.0, 0.0, 6)))})
    safety = forces[0].force(Case.SAFETY)  # the 安全性（破壊） times the 応答値係数 γR 1.2 (decision 104): 1.2 × 1200
    assert (safety.md.value, safety.md_combination, safety.end.side, safety.end.member) == (1440.0, 5, "右", right.member)
    assert safety.vd is None  # no deep beam shear at this point
    upper = forces[1].force(Case.SAFETY)  # the upper tension: the largest hogging moment, the left side's −100 and the right's −300
    assert (upper.md.value, upper.md_combination, upper.end.side) == (-360.0, 6, "右")
    # the earthquake reads the same through the elements of the NDU (no γR: Aggre-SE's nonlinear analysis), and reports the
    # frame's member
    seismic = forces[0].force(Case.SEISMIC)
    assert (seismic.md.value, seismic.end.member, seismic.pickup) == (1200.0, right.member, pf.SEISMIC_PICKUP)


def test_a_moment_of_the_wrong_sense_is_no_demand(basis):
    left, right = basis.points[0].ends
    upper = run(basis, {
        left.member: lines("JTAN", m=((10.0, 1.0, 0.0, 1), (5.0, 1.0, 0.0, 2)), s=((10.0, 1.0, 0.0, 1), (5.0, 1.0, 0.0, 2))),
        right.member: lines("ITAN", m=((20.0, 1.0, 0.0, 3), (8.0, 1.0, 0.0, 4)),
                            s=((20.0, 1.0, 0.0, 3), (8.0, 1.0, 0.0, 4)))})[1].force(Case.SAFETY)
    assert upper.md.value == 0.0  # the smallest moment is +8, a sagging one: the upper tension has no moment


def test_the_shear_is_that_of_the_sense_of_the_tension_side_with_the_moment_of_its_case(basis):
    """Decision 124: Vsd (upper tension) takes the largest shear that pulls the pile of its side, with the M of its case at
    the same end. Only the left side pulls in the frame and only the right in the earthquake: FEMPython's S is -dM/dx
    along i -> j (the left pile pulled by a positive S), Aggre-SE's dM/dx (pulled by a negative S on the left, a positive
    one on the right)."""
    pile_left, pile_right = basis.points[3].ends
    forces = run(basis, {
        pile_left.member: lines("ITAN", m=((5.0, 1.0, 0.0, 1), (-40.0, -2.0, 0.0, 2)),
                                s=((-30.0, 800.0, 0.0, 7), (-60.0, 300.0, 0.0, 8))),
        pile_right.member: lines("JTAN", m=((5.0, 1.0, 0.0, 1), (-10.0, -2.0, 0.0, 2)),
                                 s=((20.0, 900.0, 0.0, 9), (-5.0, 100.0, 0.0, 10)))})
    safety = forces[5].force(Case.SAFETY)  # 杭位置（上側引張）の Vsd, times γR 1.2: the left's 800, not the right's 900
    assert (safety.vd.value, safety.vd_combination, safety.vd_md.value, safety.vd_end.side) == (960.0, 7, -36.0, "左")
    seismic = forces[5].force(Case.SEISMIC)  # the earthquake: the right's 900 pulls, the left has no pull
    assert (seismic.vd.value, seismic.vd_combination, seismic.vd_md.value, seismic.vd_end.side,
            seismic.vd_end.member) == (900.0, 9, 20.0, "右", pile_right.member)
    bending = forces[3].force(Case.SAFETY)  # the bending of the pile position is its own point, without the shear
    assert bending.md.value == -48.0 and bending.vd is None  # its own extreme


def test_a_case_without_a_shear_of_the_sense_has_no_vd(basis):
    """Decision 124: the push of the face is a negative S on the left and a positive one on the right in the frame
    (FEMPython), the opposite in the earthquake (Aggre-SE); a case with no shear of the needed sense on either side has
    no Vd (never 0)."""
    left, right = basis.points[4].ends  # the face ends
    moment = ((5.0, 1.0, 0.0, 1), (-5.0, 1.0, 0.0, 2))
    forces = run(basis, {left.member: lines(left.point, m=moment, s=((5.0, 70.0, 0.0, 1), (-5.0, 10.0, 0.0, 2))),
                         right.member: lines(right.point, m=moment, s=((5.0, 60.0, 0.0, 3), (-5.0, 20.0, 0.0, 4)))})
    face = forces[4]
    # every S positive: the frame's push is the right's 60 (x γR 1.2), the earthquake's the left's 70
    assert (face.force(Case.SAFETY).vd.value, face.force(Case.SAFETY).vd_end.side) == (72.0, "右")
    assert (face.force(Case.SEISMIC).vd.value, face.force(Case.SEISMIC).vd_end.side) == (70.0, "左")
    forces = run(basis, {left.member: lines(left.point, m=moment, s=((5.0, -10.0, 0.0, 1), (-5.0, -70.0, 0.0, 2))),
                         right.member: lines(right.point, m=moment, s=((5.0, -20.0, 0.0, 3), (-5.0, -60.0, 0.0, 4)))})
    # every S negative: the frame pushes on the left (70), the earthquake on the right (60)
    assert (forces[4].force(Case.SAFETY).vd.value, forces[4].force(Case.SAFETY).vd_end.side) == (84.0, "左")
    assert (forces[4].force(Case.SEISMIC).vd.value, forces[4].force(Case.SEISMIC).vd_end.side) == (60.0, "右")
    # the pile ends of these members have no force (0): no shear of either sense, no Vd of any case
    for force in forces[5].forces:
        assert (force.vd, force.vd_end, force.vd_combination, force.vd_md) == (None, None, None, None)


def _pickup(*rows):
    """Lines transcribed by hand from a pickup: (focus, point, (Md, Vd, Nd) of the largest, its case, (Md, Vd, Nd) of the
    smallest, its case)."""
    return [line(focus, point, (*largest, big), (*smallest, small)) for focus, point, largest, big, smallest, small in rows]


# Example橋脚4 .claude/docs/Example橋脚4/post/線路方向_Aggre-SE.pik, pickup 2 (復旧性L2), read by hand from the file: element 7
# (left pile -> left face) and 10 (right face -> right pile)
EXAMPLE4_SEISMIC_ALONG = {
    7: _pickup(("M", "ITAN", (486.57, 16496.13, -2316.44), 10, (-8124.01, 22585.53, -3777.20), 9),
               ("M", "JTAN", (27491.61, 25087.89, -4144.92), 2, (-3431.76, 248.19, 2084.12), 11),
               ("S", "ITAN", (-3868.25, 25087.89, -4144.92), 2, (-3742.00, 248.19, 2084.12), 11),
               ("S", "JTAN", (27491.61, 25087.89, -4144.92), 2, (-3431.76, 248.19, 2084.12), 11)),
    10: _pickup(("M", "ITAN", (21170.38, -13673.29, -1979.28), 11, (-10907.99, 11166.41, 3935.22), 2),
                ("M", "JTAN", (4996.84, 4956.04, 2244.50), 9, (-372.47, 2474.16, 2324.26), 10),
                ("S", "ITAN", (-10907.99, 11166.41, 3935.22), 2, (21170.38, -13673.29, -1979.28), 11),
                ("S", "JTAN", (3050.02, 11166.41, 3935.22), 2, (4078.77, -13673.29, -1979.28), 11))}
# 線路直角方向_Aggre-SE.pik, pickup 2: element 8 (left) and 11 (right)
EXAMPLE4_SEISMIC_ACROSS = {
    8: _pickup(("M", "ITAN", (2809.36, 9157.59, -1033.09), 15, (-2736.14, 21630.56, -2902.86), 6),
               ("M", "JTAN", (24302.06, 21630.56, -2902.86), 6, (-15124.07, -13152.28, 2572.99), 2),
               ("S", "ITAN", (-2736.14, 21630.56, -2902.86), 6, (1316.28, -13152.28, 2572.99), 2),
               ("S", "JTAN", (24302.06, 21630.56, -2902.86), 6, (-15124.07, -13152.28, 2572.99), 2)),
    11: _pickup(("M", "ITAN", (24302.06, -21630.56, -2902.86), 2, (-15124.07, 13152.28, 2572.99), 6),
                ("M", "JTAN", (1735.59, 11798.75, 2510.52), 6, (-4344.65, -17360.23, -2081.38), 13),
                ("S", "ITAN", (-15124.07, 13152.28, 2572.99), 6, (24302.06, -21630.56, -2902.86), 2),
                ("S", "JTAN", (1316.28, 13152.28, 2572.99), 6, (-2736.14, -21630.56, -2902.86), 2))}
# 線路方向.pik (FEMPython), pickup 1 (安全性（破壊）), read by hand: the frame's members 6 (left) and 10 (right)
EXAMPLE4_FRAME_ALONG = {
    6: _pickup(("M", "ITAN", (511.98, -4557.68, 381.18), 16, (-473.62, -9045.58, -381.48), 13),
               ("M", "JTAN", (13146.87, -10805.26, -299.12), 1, (5910.01, -4346.31, 367.68), 18),
               ("S", "ITAN", (477.12, -4346.31, 367.68), 18, (-406.35, -10825.36, -334.44), 19),
               ("S", "JTAN", (5910.01, -4346.31, 367.68), 18, (13125.35, -10825.36, -334.44), 19)),
    10: _pickup(("M", "ITAN", (12660.31, 10460.01, -299.12), 1, (5818.81, 4463.32, 208.32), 17),
                ("M", "JTAN", (472.28, 4309.71, 381.18), 16, (-513.33, 8797.61, -381.48), 13),
                ("S", "ITAN", (12657.69, 10493.61, -334.44), 19, (5859.41, 4309.71, 381.18), 16),
                ("S", "JTAN", (-459.33, 10493.61, -334.44), 19, (472.28, 4309.71, 381.18), 16))}


def _shears(found, case):
    points = {item.point.key: item.force(case) for item in found.points}
    return [None if force.vd is None else (force.vd.value, force.vd_combination, force.vd_md.value, force.vd_end.side)
            for force in (points["face_shear"], points["pile_shear"])]


@pytest.mark.parametrize("direction,elements,pickup,expected", [
    # 線路方向: Vfdd max(25087.9 the left's push, 13673.3 the right's); Vsd the right's pull 11166.4 (the left's S is
    # positive in both its cases, 25087.89 and 248.19: no pull)
    ("longitudinal", {6: 7, 10: 10}, EXAMPLE4_SEISMIC_ALONG, [(25087.9, 2, 27491.6, "左"), (11166.4, 2, 3050.0, "右")]),
    # 線路直角方向: the push 21630.6 and the pull 13152.3 are as large on both sides: the left's is kept
    ("transverse", {6: 8, 11: 11}, EXAMPLE4_SEISMIC_ACROSS, [(21630.6, 6, 24302.1, "左"), (13152.3, 2, 1316.3, "左")]),
])
def test_the_deep_beam_shear_of_example4s_earthquake_is_that_of_the_sense(example4, direction, elements, pickup, expected):
    """Decision 124 on the pickups of Aggre-SE of Example橋脚4 (the expected values are a hand reading of those files): the
    largest shear at the left face (element 7, 25087.89) is of the same Case 2 as its largest sagging moment 27491.61, so
    a positive S pushes the left pile; Vsd is no longer the push's 25087.9 of the largest |S| (γi·Vd/Vsd 1.17, NG)."""
    basis = example4[direction]
    assert basis.members == tuple(elements)
    found = pf.complete(basis, None, {element: pickup[element] for element in elements.values()}, elements)
    assert _shears(found, Case.SEISMIC) == expected


def test_the_frames_shear_of_example4_has_the_sense_of_fempython(example4):
    """Decision 124 on FEMPython's PIK of Example橋脚4 (a hand reading of 線路方向.pik, pickup 1): the largest sagging moment at
    the left face, 13146.87, has S -10805.26 (FEMPython's S is -dM/dx along i -> j), so Vfdd is the left's push 10825.36
    times γR 1.2; every S of the left side is negative and of the right side positive, nothing pulls: no Vsd of 安全性."""
    basis = example4["longitudinal"]
    assert basis.members == (6, 10)
    shared = {(pickup, member): found for pickup in basis.pickups.values() for member, found in EXAMPLE4_FRAME_ALONG.items()}
    assert _shears(pf.complete(basis, shared, None, None), Case.SAFETY) == [(12990.4, 19, 15750.4, "左"), None]
    assert round(1.2 * 10825.36, 1) == 12990.4 and round(1.2 * 13125.35, 1) == 15750.4


def test_a_missing_line_is_a_response_error(basis):
    with pytest.raises(PileResponseError, match="断面力がありません"):
        run(basis, {basis.members[0]: []})


def test_the_transverse_direction_has_sections_too(pier, frames):
    # rows at -3, 0, 3 m under a column of 2.7 m (across the track): the middle row is inside the faces, the outer ones outside
    transverse = pf.prepare(pier, frames[1], TRANSVERSE)
    assert [point.key for point in transverse.points] == ["face_lower", "face_upper", "pile_lower", "pile_upper", "face_shear",
                                                          "pile_shear"]


def changed(**paths):
    """pile_seismic.json with each 'a/b/c' path replaced by its value."""
    data = json.loads((FIXTURES / "inputs" / "pile_seismic.json").read_text(encoding="utf-8"))
    for path, value in paths.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[part]
        node[key] = value
    return parse_input(data)


def frames_of(found):
    foundation = PileFoundation(calculate_pile_ground(found), parse_sdc((FIXTURES / "soiljr" / "pile_cast.sdc").read_bytes()))
    return calculate_longitudinal(found, foundation, calculate_reaction(found))


def test_the_union_of_the_widths_of_piles_is_its_pieces():
    centres = [Decimal(-3000), Decimal(0), Decimal(3000)]
    assert pf._union(centres, Decimal(500), Decimal(4500)) == (Decimal(1000),) * 3  # three widths of 1000, apart
    assert pf._union(centres, Decimal(1000), Decimal(4500)) == (Decimal(2000),) * 3  # three widths of 2000, with gaps between
    assert pf._union(centres, Decimal(2000), Decimal(4000)) == (Decimal(8000),)  # overlapping: from the first to the last, cut at B
    assert pf._union([Decimal(-2500), Decimal(2500)], Decimal("1521.5"), Decimal(3500)) == (Decimal("2521.5"),) * 2


def test_a_frame_without_piles_cannot_have_the_footing_checked(pier):
    from longitudinal_support import chain  # noqa: PLC0415

    direct_pier, _, frame = chain()
    with pytest.raises(InputError, match="杭の骨組が必要です"):
        pf.prepare(direct_pier, frame, LONGITUDINAL)


@pytest.fixture(scope="module")
def example4():
    """The sections of both directions of the 鋼管ソイルセメント杭 of Example橋脚4 (decision 124)."""
    from test_pile_frame import example4 as example4_input  # noqa: PLC0415

    steel = example4_input()
    foundation = PileFoundation(calculate_pile_ground(steel), parse_sdc((FIXTURES / "soiljr" / "pile_steel_grid.sdc").read_bytes()))
    reaction = calculate_reaction(steel)
    return {"longitudinal": pf.prepare(steel, calculate_longitudinal(steel, foundation, reaction), LONGITUDINAL),
            "transverse": pf.prepare(steel, calculate_transverse(steel, foundation, reaction), TRANSVERSE)}


def test_a_steel_pile_takes_the_soil_cement_diameter_as_d(example4):
    """Decision 124: D is the ソイルセメント径 1.0 m (the sample V-114, V-139: 1000), not the pipe's 800."""
    for basis in example4.values():
        assert {point.pile_diameter.value for point in basis.points} == {1000.0}
    sample = EXAMPLE4["longitudinal"]["checks"]
    assert sample["表2.4.2"]["D_mm"] == 1000 and EXAMPLE4["transverse"]["checks"]["表3.4.2"]["columns"][
        "線路直角方向 く体前面（下側引張）"]["D_mm"] == 1000


def _widths(basis):
    return {point.key: point.width for point in basis.points}


def test_the_widths_of_example4_along_the_track_are_the_samples(example4):
    """V-113〜V-118 and V-127: the bending widths of the rules of decision 96, the shear width of decision 124."""
    widths, sample = _widths(example4["longitudinal"]), EXAMPLE4["longitudinal"]["effective_widths"]
    bending = sample["bending"]
    assert [widths[key].be.value for key in ("face_lower", "face_upper", "pile_lower", "pile_upper")] == [
        bending["front_lower_adopted_mm"], bending["front_upper_adopted_mm"], bending["pile_lower"]["be_mm"],
        bending["pile_upper"]["be_mm"]] == [7650, 5614, 8000, 8000]
    assert widths["pile_lower"].pieces == () and widths["pile_upper"].pieces == ()  # the piles' widths overlap
    # the shear: the row at 2.5 m, 1250 beyond the face (1.25); its end piles (±3000) are 1250 beyond the column's side
    # faces (±1750): a1b = √(1250² + 1250²) = 1768, be = 0.65√(1768² + 2075²) + 1000 = 2772; the middle one a1a = 1250, 2575
    assert round(math.hypot(1250, 1250)) == 1768 and round(0.65 * math.hypot(1768, 2075) + 1000) == 2772
    assert round(0.65 * math.hypot(1250, 2075) + 1000) == 2575
    shear = sample["shear"]
    assert [(item.a1.value, item.be.value, item.corner) for item in widths["face_shear"].shares] == [
        (shear["end_pile"]["a1b_mm"], shear["end_pile"]["be_mm"], True),
        (shear["middle_pile"]["a1a_mm"], shear["middle_pile"]["be_mm"], False),
        (shear["end_pile"]["a1b_mm"], shear["end_pile"]["be_mm"], True)] == [
        (1768, 2772, True), (1250, 2575, False), (1768, 2772, True)]
    # Σ 8119 is limited to Lp + D = 6000 + 1000
    assert widths["face_shear"].be.value == min(2772 + 2575 + 2772, 6000 + 1000) == shear["be_mm"] == 7000
    assert dict(widths["face_shear"].terms)["Lp"].value == 6000
    face = next(point for point in example4["longitudinal"].points if point.deep_beam == "lower_tension")
    assert face.a1.value == EXAMPLE4["longitudinal"]["checks"]["表2.4.2"]["a1_mm"] == 1768  # the largest a1 of the row
    assert face.depth.value == shear["end_pile"]["d1_mm"] == 2075


def test_the_widths_of_example4_across_the_track_are_the_samples(example4):
    """V-151〜V-156 and V-165: the piles' widths at the pile position do not overlap, so each pile's is rounded to mm and
    they are summed (decision 124); the face's upper tension is 5582 (the sample's 4582 is a slip, decision 124)."""
    widths, sample = _widths(example4["transverse"]), EXAMPLE4["transverse"]["effective_widths"]
    bending = sample["bending"]
    assert widths["face_lower"].be.value == bending["column_face_lower_tension"]["adopted_be_mm"] == 6586
    assert widths["face_upper"].be.value == bending["column_face_upper_tension"]["from_pile"]["be_raw_mm"] == 5582
    # each pile at ±2500: 500 to the footing's edge (3500) + D 1000 + d/2 → 500 + 1000 + 1021.5 = 2521.5 → 2522, and
    # 500 + 1000 + 1041 = 2541
    for key, tension, each in (("pile_lower", "pile_lower_tension", 2522), ("pile_upper", "pile_upper_tension", 2541)):
        assert [piece.value for piece in widths[key].pieces] == [bending[tension]["be_per_pile_mm"]] * 2 == [each] * 2
        assert widths[key].be.value == bending[tension]["be_mm"] == 2 * each
        assert dict(widths[key].terms)["be(1)"].value == each
    # the shear: two end piles, a1b = 1768 each, be = 0.65√(1768² + 2043²) + 1000 = 2756; Σ 5512 < Lp + D = 6000
    assert round(0.65 * math.hypot(1768, 2043) + 1000) == 2756
    shear = sample["shear"]
    assert [(item.a1.value, item.be.value, item.corner) for item in widths["face_shear"].shares] == [
        (shear["a1b_mm"], shear["be_one_pile_mm"], True)] * 2 == [(1768, 2756, True)] * 2
    assert widths["face_shear"].be.value == shear["be_mm"] == 5512
    assert dict(widths["face_shear"].terms)["Lp"].value + 1000 == shear["end_pile_spacing_mm"] == 6000
    face = next(point for point in example4["transverse"].points if point.deep_beam == "lower_tension")
    assert face.a1.value == 1768 and face.depth.value == shear["d1_mm"] == 2043


@pytest.mark.parametrize("centre,full,a1,pile,be", [
    # outside the column's side face (1750): a1b = √(1250² + 1250²) = 1768, 0.65√(1768² + 2075²) + 1000 = 2772
    (3000, 8000, 1768, 2772, 2772),
    # within the column's width: a1a = 1250, 0.65√(1250² + 2075²) + 1000 = 2575
    (0, 8000, 1250, 2575, 2575),
    # not more than B
    (3000, 2500, 1768, 2772, 2500),
])
def test_the_shear_width_of_a_row_of_one_pile_is_its_be(centre, full, a1, pile, be):
    """Decision 128: a row of one pile has no centre spacing Lp, so its be is not limited to D (Lp + D) but to B only."""
    assert round(0.65 * math.hypot(1768, 2075) + 1000) == 2772 and round(0.65 * math.hypot(1250, 2075) + 1000) == 2575
    width = pf._shear_width(Decimal(1250), [Decimal(centre)], (Decimal(-1750), Decimal(1750)), Decimal(2075),
                            Decimal(1000), Decimal(full))
    assert [(share.a1.value, share.be.value) for share in width.shares] == [(a1, pile)]
    assert width.be.value == be
    assert width.rule == "0.65√(a1² + d1²) + D"
    assert [name for name, _ in width.terms] == ["d1", "D", "a1(1)", "be(1)"]


@pytest.mark.parametrize("name,table,stirrups", [
    # 8000 // 450 = 17 across, 2114 // 300 = 7 within d: 119 (the sample 120, a known (3) of decision 124)
    ("longitudinal", ("表2.3.11", "表2.4.3"), 17 * 7),
    # 7000 // 450 = 15, 2082 // 300 = 6: 90 (the sample 98); the bending's pile position is 5082, not 7000
    ("transverse", ("表3.3.11", "表3.4.3"), 15 * 6),
])
def test_the_vsd_of_example4_is_of_the_footings_whole_width(example4, name, table, stirrups):
    """Decision 124: the Vsd at the pile position (upper tension) takes the footing's whole width B (the sample's tables
    of 安全性（破壊） and 復旧性（地震時）), a point of its own; its stirrups are counted across B."""
    checks = EXAMPLE4[name]["checks"]
    sample = [checks[key] if "be_mm" in checks[key] else checks[key]["columns"]["杭位置（上側引張）"] for key in table]
    points = {point.key: point for point in example4[name].points}
    shear, bending = points["pile_shear"], points["pile_upper"]
    assert (shear.bending, shear.deep_beam, shear.position, shear.tension) == (False, "upper_tension", "杭位置", "上側引張")
    assert [item["be_mm"] for item in sample] == [shear.width.be.value] * 2 == [shear.width.full.value] * 2
    assert [item["d_mm"] for item in sample] == [shear.depth.value] * 2
    assert shear.stirrup_count == stirrups and bending.stirrup_count is None and bending.deep_beam is None
    # the sample's stirrups 450mm当り1本 ctc300mm: the input's width pitch 450 is 2.22 legs per 1 m, b1 = 1000 / 2.22 =
    # 450.5 (calc.footing_rebar), which floors B to the same count as 450
    assert (example4[name].stirrup_spacing.value, example4[name].stirrups.pitch.value) == (450.5, 300)
    assert int(shear.width.be.value // 450.5) == int(shear.width.be.value // 450)


def test_the_shear_row_is_the_nearer_one_and_the_left_when_both_are_as_near(pier, frames):
    """Decision 124: with rows beyond both faces the nearer row's piles make the shear width (as a is the nearest row's);
    equally near, the left one's (a pile left out of it changes the width of that row only; the frame, whose rows are
    bundled, is the input's)."""
    found = changed(**{"杭基礎/配置/抜く杭": [{"線路方向の列": 1, "線路直角方向の列": 1}]})
    shear = next(point.width for point in pf.prepare(found, frames[0], LONGITUDINAL).points if point.key == "face_shear")
    assert len(shear.shares) == 2  # the left row (x = −3) without its first pile
    nearer = changed(**{"杭基礎/配置/線路方向の列の位置": [-3.0, 0.0, 2.5]})
    shear = next(point.width for point in pf.prepare(nearer, frames_of(nearer), LONGITUDINAL).points
                 if point.key == "face_shear")
    assert [share.a1.value for share in shear.shares] == [1373.0, 1150.0, 1373.0]  # the right row, 2.5 − 1.35 from the face
    assert round(math.hypot(1150, 750)) == 1373


def test_the_column_across_is_where_the_frame_of_the_other_direction_puts_it():
    """An asymmetric overhang across (W7 2.75, W9 1.75; B 9.0): the column's side faces are −4.5 + 2.75 = −1.75 and 2.75 m,
    the faces of the column the transverse frame (the plane across the track) cuts its base at, around its axis
    (W7 − W9) / 2 = 0.5. The end piles of the row at x = 3 m (1650 beyond the face) are 1250 and 250 beyond the side faces:
    a1b = √(1650² + 1250²) = 2070 and √(1650² + 250²) = 1669; the middle pile (0) is within, a1a = 1650."""
    from webpier.calc.frame import NodeRole  # noqa: PLC0415

    found = changed(**{"下部構造/寸法/正面/W7": 2.75, "下部構造/寸法/正面/W9": 1.75})
    foundation = PileFoundation(calculate_pile_ground(found), parse_sdc((FIXTURES / "soiljr" / "pile_cast.sdc").read_bytes()))
    reaction = calculate_reaction(found)
    along, across = calculate_longitudinal(found, foundation, reaction), calculate_transverse(found, foundation, reaction)
    faces = sorted(node.x.value for node in across.frame.nodes if NodeRole.COLUMN_FACE in node.roles)
    assert faces == [-1.75, 2.75] and across.frame.node(NodeRole.FOOTING_TOP).x.value == 0.5
    shear = next(point.width for point in pf.prepare(found, along, LONGITUDINAL).points if point.key == "face_shear")
    assert round(math.hypot(1650, 1250)) == 2070 and round(math.hypot(1650, 250)) == 1669
    assert [(share.a1.value, share.corner) for share in shear.shares] == [(2070.0, True), (1650.0, False), (1669.0, True)]


def test_rows_inside_the_faces_of_the_column_leave_no_footing_to_check():
    found = changed(**{"杭基礎/配置/線路方向の列の位置": [-1.0, 0.0, 1.0]})
    with pytest.raises(InputError, match="く体前面より外側に杭の列がありません"):
        pf.prepare(found, frames_of(found), LONGITUDINAL)


def test_a_side_whose_outer_row_is_inside_its_face_has_no_sections():
    found = changed(**{"杭基礎/配置/線路方向の列の位置": [-3.0, 0.0, 0.5]})
    basis = pf.prepare(found, frames_of(found), LONGITUDINAL)
    assert {end.side for point in basis.points for end in point.ends} == {"左"}
    assert len(basis.members) == 1


def test_stirrups_that_do_not_reach_into_the_width_are_an_input_error():
    found = changed(**{"鉄筋/フーチング/stirrups/線路/pitch_mm": 5000})
    with pytest.raises(InputError, match="有効幅の中にスターラップがありません"):
        pf.prepare(found, frames_of(found), LONGITUDINAL)


def test_a_face_of_the_column_at_a_pile_row_is_that_nodes_too():
    from webpier.calc.frame import NodeRole  # noqa: PLC0415

    found = changed(**{"杭基礎/配置/線路方向の列の位置": [-3.0, -1.35, 3.0]})
    frame = frames_of(found).frame
    shared = next(node for node in frame.nodes if node.x.value == -1.35 and NodeRole.PILE_HEAD in node.roles)
    assert NodeRole.COLUMN_FACE in shared.roles
    basis = pf.prepare(found, frames_of(found), LONGITUDINAL)
    assert {(end.side, end.point, end.x.value) for end in basis.points[0].ends} == {("左", "JTAN", -1.35), ("右", "ITAN", 1.35)}


def test_the_seismic_part_alone_takes_the_sections_from_the_frame_of_0710(pier, basis):
    """Decision 110: without the frame analyses the sections come from the frame of 0710 (the same frame, cut at the faces
    of the column), with no pickup."""
    found = PileFoundation(calculate_pile_ground(pier), parse_sdc((FIXTURES / "soiljr" / "pile_cast.sdc").read_bytes()))
    seismic = calculate_seismic_longitudinal(pier, found, calculate_reaction(pier))
    alone = pf.prepare(pier, seismic, LONGITUDINAL, frames=False)
    assert alone.pickups == {}
    assert [(point.key, point.width, point.depth) for point in alone.points] == [
        (point.key, point.width, point.depth) for point in basis.points]
    assert [[(end.side, end.point, end.x) for end in point.ends] for point in alone.points] == [
        [(end.side, end.point, end.x) for end in point.ends] for point in basis.points]


def test_a_footing_of_one_part_has_the_cases_of_that_part_alone(basis):
    """Decision 110: the frame analysis alone has its three cases at every point; the earthquake alone its case at every
    point, with the deep beam shear of 復旧性（地震時） (decision 124)."""
    forces = {member: lines("JTAN", m=((900.0, -50.0, 0.0, 3), (-100.0, 40.0, 0.0, 4)),
                            s=((900.0, -50.0, 0.0, 3), (-100.0, 40.0, 0.0, 4))) for member in basis.members}
    shared = {(pickup, member): found for pickup in basis.pickups.values() for member, found in forces.items()}
    elements = {member: member + 100 for member in basis.members}
    seismic = {elements[member]: found for member, found in forces.items()}
    both = pf.complete(basis, shared, seismic, elements).points
    frames = pf.complete(basis, shared, None, None).points
    alone = pf.complete(basis, None, seismic, elements).points
    assert [item.point for item in frames] == [item.point for item in both]
    assert all([force.case for force in item.forces] == [Case.SAFETY, Case.SHORT_TERM, Case.LONG_TERM] for item in frames)
    assert [item.forces for item in frames] == [item.forces[:3] for item in both]
    assert [item.point for item in alone] == [item.point for item in both]
    assert all(item.force(Case.SAFETY) is None for item in alone)
    # the earthquake as with both, its shear at the points of the deep beam shear (decision 124)
    assert [item.forces for item in alone] == [item.forces[3:] for item in both]
    assert [item.point.key for item in alone if item.force(Case.SEISMIC).vd is not None] == ["face_shear", "pile_shear"]


def test_the_deep_beam_shear_is_of_safety_and_of_the_earthquake(basis):
    """Decision 124: the points of the deep beam shear have the shear of 安全性（破壊） and 復旧性（地震時）, not of 耐久性."""
    forces = {member: lines("JTAN", m=((900.0, -50.0, 0.0, 3), (-100.0, 40.0, 0.0, 4)),
                            s=((900.0, -50.0, 0.0, 3), (-100.0, 40.0, 0.0, 4))) for member in basis.members}
    face = run(basis, forces)[4]
    # the face's push (decision 124): the frame's -50 (x γR 1.2) of Case 3, the earthquake's +40 of Case 4, on the left
    assert [(force.case, None if force.vd is None else force.vd.value) for force in face.forces] == [
        (Case.SAFETY, 60.0), (Case.SHORT_TERM, None), (Case.LONG_TERM, None), (Case.SEISMIC, 40.0)]
    assert face.force(Case.SAFETY).vd_md.value == 1080.0 and face.force(Case.SEISMIC).vd_md.value == -100.0
