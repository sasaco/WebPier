"""0800 of a pile foundation (decision 96): the sections of the footing, their effective widths and the section forces.

The input is tests/fixtures/inputs/pile_seismic.json (the SOIL-JR 5.2 sample E: a 場所打ち杭 of two rows of piles along the track, three
across it). The widths are recomputed here from the input's own values; the forces are made up lines of the PIK, so that each
choice (the sense of the moment, the side, the case of the shear) can be checked by hand."""

import json
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
                     ("pile_lower", "杭位置（下側引張）", True, None), ("pile_upper", "杭位置（上側引張）", True, "upper_tension"),
                     ("face_shear", "く体前面（下側引張）", False, "lower_tension")]
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
    assert Decimal(str(widths["face_shear"].be.value)) == min(max(across) - min(across) + diameter, full)
    # the widths D + d of the piles overlap (the spacing is smaller): the width is that from the first pile to the last, limited to B
    assert diameter + d_lower > across[1] - across[0]
    assert Decimal(str(widths["pile_lower"].be.value)) == min(max(across) - min(across) + diameter + d_lower, full)
    assert all(width.full.value == float(full) for width in widths.values())


def test_the_stirrups_within_d_across_the_width_are_counted_down(basis):
    point = next(item for item in basis.points if item.deep_beam == "upper_tension")
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


def test_the_shear_is_the_largest_absolute_force_of_the_section_with_the_moment_of_its_case(basis):
    pile_left, pile_right = basis.points[3].ends
    forces = run(basis, {
        pile_left.member: lines("ITAN", m=((5.0, 1.0, 0.0, 1), (-40.0, -2.0, 0.0, 2)),
                                s=((-30.0, 800.0, 0.0, 7), (-60.0, -950.0, 0.0, 8))),
        pile_right.member: lines("JTAN", m=((5.0, 1.0, 0.0, 1), (-10.0, -2.0, 0.0, 2)),
                                 s=((20.0, 900.0, 0.0, 9), (-5.0, -100.0, 0.0, 10)))})
    safety = forces[3].force(Case.SAFETY)  # 杭位置（上側引張）: Vsd, times γR 1.2
    assert (safety.vd.value, safety.vd_combination, safety.vd_md.value, safety.vd_end.side) == (1140.0, 8, -72.0, "左")
    assert safety.md.value == -48.0  # the bending moment of the same point is its own extreme


def test_a_missing_line_is_a_response_error(basis):
    with pytest.raises(PileResponseError, match="断面力がありません"):
        run(basis, {basis.members[0]: []})


def test_the_transverse_direction_has_sections_too(pier, frames):
    # rows at -3, 0, 3 m under a column of 2.7 m (across the track): the middle row is inside the faces, the outer ones outside
    transverse = pf.prepare(pier, frames[1], TRANSVERSE)
    assert [point.key for point in transverse.points] == ["face_lower", "face_upper", "pile_lower", "pile_upper", "face_shear"]


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


def test_the_union_of_the_widths_of_piles_that_do_not_overlap_is_the_sum():
    centres = [Decimal(-3000), Decimal(0), Decimal(3000)]
    assert pf._union(centres, Decimal(500), Decimal(4500)) == Decimal(3000)  # three widths of 1000
    assert pf._union(centres, Decimal(1000), Decimal(4500)) == Decimal(6000)  # three widths of 2000, with gaps between
    assert pf._union(centres, Decimal(2000), Decimal(4000)) == Decimal(8000)  # overlapping: from the first to the last, cut at B


def test_a_frame_without_piles_cannot_have_the_footing_checked(pier):
    from longitudinal_support import chain  # noqa: PLC0415

    direct_pier, _, frame = chain()
    with pytest.raises(InputError, match="杭の骨組が必要です"):
        pf.prepare(direct_pier, frame, LONGITUDINAL)


def test_a_steel_pile_foundation_is_refused(pier):
    from test_pile_frame import example4  # noqa: PLC0415

    steel = example4()
    foundation = PileFoundation(calculate_pile_ground(steel), parse_sdc((FIXTURES / "soiljr" / "pile_steel_grid.sdc").read_bytes()))
    frame = calculate_longitudinal(steel, foundation, calculate_reaction(steel))
    with pytest.raises(InputError, match="場所打ち杭だけ"):
        pf.prepare(steel, frame, LONGITUDINAL)


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
    """Decision 110: the frame analysis alone has its three cases at every point; the earthquake alone its case at the
    bending points, without the shear (of 安全性（破壊） alone): the point of the shear at the face is not made."""
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
    assert [item.point.key for item in alone] == ["face_lower", "face_upper", "pile_lower", "pile_upper"]
    assert all(item.point.deep_beam is None for item in alone) and all(item.force(Case.SAFETY) is None for item in alone)
    # the bending of the earthquake as with both (with both, the point of the pile position also reads a shear of the
    # earthquake, which nothing uses: the deep beam checks are of 安全性（破壊）)
    assert [[(force.case, force.md, force.end) for force in item.forces] for item in alone] == [
        [(force.case, force.md, force.end) for force in item.forces[3:]] for item in both if item.point.bending]
