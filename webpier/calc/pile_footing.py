"""0800 フーチングの応答値 of a pile foundation (decision 96, Example橋脚4 第V編 2・3): the design section forces of the
footing at the column face (く体前面) and at the outermost pile (杭位置), and the effective widths they are checked with.

The footing of the frame of a pile foundation is a rigid base member between the heads of the pile rows, cut at the faces
of the column (``calc.frame``, NodeRole.COLUMN_FACE), so a section force of the footing is the force at the end of a
member, as FEMPython's PIK and Aggre-SE's pickup give it (nothing is interpolated):

- the face section is the end at the column face of the member next to it, the pile section the end at the outermost
  pile head of the chain of members from the face outwards; each side of the column has its own, and a case takes the
  side with the larger demand;
- the cases of the check are those of the frame analysis (安全性（破壊）, 耐久性の 永久＋変動 and 永久: the PIK of the
  extraction groups of 0612 / 0622) and, for the 復旧性（地震時）, the pickup of 復旧性L2 of Aggre-SE's check of 0711 / 0721
  (the largest and the smallest M, S and N of each member end over its Cases);
- the bending moment of a section is the largest sagging moment (the PIK's M is positive for a lower tension) for the
  lower tension and the largest hogging moment for the upper tension, 0 when the footing has none of that sense; the
  shear force is the largest |Vd| of the section with the moment of its case.

The effective widths are WebPier's (the sample 2.3.1; the check itself is Capacita's, ADR-0008). With d the effective
depth to the tensile bars of the face (the footing height less their centroid), D the pile diameter, a the distance from
the column face to the centre of the nearest pile row beyond it, B the width of the footing across the plane:

- face, lower tension: b + 2 d, b the column width across, not more than B;
- face, upper tension: D + 2 (d/2 + a), not more than B;
- pile position (either tension): the piles of the row each take D + d; when they overlap, the width is that from the
  first to the last of the piles (the widths of the overlapping piles joined), not more than B;
- the deep beam shear at the face (lower tension): the piles across, centre to centre, plus D, not more than B; at the
  pile position (upper tension) the width of the pile position.

Only a 場所打ち杭 is made (0711 and 0721 are). Everything here is calculated from the printed values of the input and of the
files, and every number is a ``Printed`` (ADR-0003).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput, choices
from ._exact import d, put
from .footing import Direction as FootingDirectionKind, LONGITUDINAL, TRANSVERSE
from .footing_rebar import MainBars, Stirrups, main_bars, stirrup_width, stirrups
from .frame import Frame, NodeRole, Region
from .longitudinal.combinations import ExtractionGroup
from .pile_body import PileResponseError, PointForces, SectionForce
from .pile_ground import has_pile

MILLI = Decimal(1000)
LENGTH_MM = Precision(1, "mm")
WIDTH = Precision(0, "mm")
FORCE = Precision(1, "kN")
MOMENT = Precision(1, "kN・m")
SEISMIC_PICKUP = 2  # Aggre-SE's pickup of 復旧性L2 (decision 96)
LOWER, UPPER = "下側引張", "上側引張"
FACE, PILE = "く体前面", "杭位置"


class Case(Enum):
    """A check of the footing and the design forces it takes: the key is the name of the forces' use in Capacita's WDJ."""

    SAFETY = "安全性（破壊）"
    SHORT_TERM = "耐久性 永久＋変動"
    LONG_TERM = "耐久性 永久"
    SEISMIC = "復旧性（地震時）"


# (the case, the extraction group of the frame analysis; None for the earthquake)
CASES = ((Case.SAFETY, ExtractionGroup.FAILURE), (Case.SHORT_TERM, ExtractionGroup.PERMANENT_VARIABLE),
         (Case.LONG_TERM, ExtractionGroup.PERMANENT), (Case.SEISMIC, None))


@dataclass(frozen=True)
class End:
    """The end of a base member that is a section of one side: the member, the point of its PIK lines and its x (m)."""

    side: str  # 左 / 右 (by x)
    member: int
    point: str  # ITAN / JTAN
    x: Printed


@dataclass(frozen=True)
class Width:
    """An effective width (mm) with what it is made of, for the report."""

    rule: str  # the formula as the report prints it
    be: Printed
    full: Printed  # B, the footing width across, mm
    terms: tuple[tuple[str, Printed], ...]  # the quantities of the rule, in order


@dataclass(frozen=True)
class Point:
    """One point of the WDJ: a section, its tension side and what Capacita is asked to check there."""

    key: str
    name: str  # the point's name: く体前面（下側引張）
    position: str  # FACE / PILE
    tension: str  # LOWER / UPPER
    ends: tuple[End, ...]
    width: Width
    height: Printed  # H, mm
    depth: Printed  # d, mm, to the centroid of the tensile bars
    bending: bool  # the bending checks are asked
    deep_beam: str | None  # the deep beam shear: "lower_tension" (Vdd) / "upper_tension" (Vsd) / None
    a1: Printed | None  # mm, from the column face to the nearest pile row
    pile_diameter: Printed  # D, mm
    stirrup_count: int | None  # the stirrups within d across the width (Vsd)


@dataclass(frozen=True)
class FootingBasis:
    """What 0800 of one direction reads before the analyses: the sections, the bars and the pickups."""

    direction: str  # 線路 / 直角
    points: tuple[Point, ...]
    bars: tuple[MainBars, MainBars]  # (lower, upper), per 1 m of width
    stirrups: Stirrups
    stirrup_spacing: Printed  # b1, mm, across the width
    fck: Printed
    pickups: Mapping[Case, int]  # the extraction number of each case of the frame analysis
    members: tuple[int, ...]  # the base members of the sections
    chain: Mapping[int, tuple[Printed, Printed]]  # member -> (x of its i end, x of its j end), of the frame


@dataclass(frozen=True)
class Force:
    """The design forces of one case at a point: where they come from and their values (the bending moment signed, the
    shear force absolute)."""

    case: Case
    pickup: int
    end: End
    md: Printed
    md_combination: int
    vd: Printed | None
    vd_end: End | None
    vd_combination: int | None
    vd_md: Printed | None  # the bending moment of the case of Vd


@dataclass(frozen=True)
class SectionForces:
    point: Point
    forces: tuple[Force, ...]  # in the order of CASES

    def force(self, case: Case) -> Force:
        return next(force for force in self.forces if force.case is case)


@dataclass(frozen=True)
class FootingDirection:
    basis: FootingBasis
    points: tuple[SectionForces, ...]


@dataclass(frozen=True)
class FootingResult:
    """0800: both directions."""

    longitudinal: FootingDirection
    transverse: FootingDirection


@dataclass(frozen=True)
class FootingBases:
    longitudinal: FootingBasis
    transverse: FootingBasis


# --- the sections -----------------------------------------------------------------------------------------------------


def _side_ends(frame: Frame, side: str) -> tuple[End | None, End | None]:
    """The face end and the pile end of *side* (左 / 右) of the base of *frame*; None for both when no pile is outside the face."""
    axis = frame.node(NodeRole.FOOTING_TOP).x.value
    left = side == "左"
    # a face beyond the outermost pile head has no node (calc.frame): that side has no footing to check
    faces = [node for node in frame.nodes if NodeRole.COLUMN_FACE in node.roles and (node.x.value < axis) == left]
    heads = sorted((node for node in frame.nodes if NodeRole.PILE_HEAD in node.roles), key=lambda node: node.x.value)
    outer = heads[0] if left else heads[-1]
    if not faces or ((outer.x.value >= faces[0].x.value) if left else (outer.x.value <= faces[0].x.value)):
        return None, None
    face = faces[0]
    base = [member for member in frame.members if member.region is Region.FOOTING_BASE]
    nodes = {node.number: node for node in frame.nodes}

    def find(node_number: int, start: bool) -> int:
        return next(member.number for member in base if (member.start if start else member.end) == node_number)

    # the base members are numbered by the frame; their ends are left (start) and right (end) by construction
    if left:
        return (End(side, find(face.number, False), "JTAN", face.x), End(side, find(outer.number, True), "ITAN", outer.x))
    return (End(side, find(face.number, True), "ITAN", face.x), End(side, find(outer.number, False), "JTAN", outer.x))


def _pile_positions(pier: PierInput, direction: FootingDirectionKind, row: int) -> tuple[Decimal, ...]:
    """The positions across (m from the footing centre) of the piles of the row *row* (1 from the first)."""
    layout = pier.piles.layout
    staggered = layout.pattern == choices.STAGGERED
    removed = set(layout.removed)
    if direction.name == "線路":
        return tuple(d(x) for j, x in enumerate(layout.across, 1)
                     if has_pile(staggered, row, j) and (row, j) not in removed)
    return tuple(d(x) for i, x in enumerate(layout.along, 1) if has_pile(staggered, i, row) and (i, row) not in removed)


def _union(centres: Sequence[Decimal], half: Decimal, edge: Decimal) -> Decimal:
    """The length of the union of the intervals centre ± half, within -edge … +edge."""
    total, end = Decimal(0), None
    for low, high in sorted((max(c - half, -edge), min(c + half, edge)) for c in centres):  # equal widths: no interval is inside another
        total += high - low if end is None or low > end else high - end
        end = high
    return total


def _printed(value: Decimal) -> Printed:
    return put(WIDTH, value)


def _width(rule: str, be: Decimal, full: Decimal, *terms: tuple[str, Decimal]) -> Width:
    return Width(rule, _printed(min(be, full)), _printed(full), tuple((name, put(LENGTH_MM, item)) for name, item in terms))


def prepare(pier: PierInput, frame_result, direction: FootingDirectionKind) -> FootingBasis:
    """The sections of the footing in *direction* from the frame of 0610 / 0620 and the input (before any runner); an input
    that cannot be checked is an input error naming it."""
    frame = frame_result.frame
    if frame.piles is None:
        raise InputError("杭基礎のフーチングには杭の骨組が必要です（基礎形式が杭基礎ではありません）")
    if pier.substructure.foundation != choices.CAST_IN_PLACE_PILE:
        raise InputError("杭基礎のフーチングの照査は場所打ち杭だけに対応します（鋼管ソイルセメント杭は未対応です、決定96）")
    sub = pier.substructure
    rebar_name = direction.name
    lower, upper = main_bars(pier, rebar_name, choices.BEAM_FACES[1]), main_bars(pier, rebar_name, choices.BEAM_FACES[0])
    height = d(sub.h[6]) * MILLI
    depth = {LOWER: height - d(lower.centroid), UPPER: height - d(upper.centroid)}
    column, left, right = direction.across(sub)
    full = (d(left) + d(column) + d(right)) * MILLI
    diameter = d(pier.piles.cast_in_place.diameter) * MILLI
    group = frame.piles
    # the piles across the plane: the union of every row's (the section is the footing's whole width)
    across = sorted({x for row in group.rows for x in _pile_positions(pier, direction, row.number)})
    centres = [x * MILLI for x in across]
    across_span = (max(centres) - min(centres)) + diameter
    half = full / 2
    sides = {side: _side_ends(frame, side) for side in ("左", "右")}
    if all(face is None for face, _ in sides.values()):
        raise InputError("杭基礎のフーチング: く体前面より外側に杭の列がありません（フーチングの照査は、く体前面と杭位置の間にフーチングがある杭の配置だけに対応します）")
    face_ends = tuple(face for face, _ in sides.values() if face is not None)
    pile_ends = tuple(end for _, end in sides.values() if end is not None)
    # a: the face to the centre of the nearest row beyond it, per side; the smaller is taken (the nearest row)
    row_x = [d(row.x) for row in group.rows]
    a_values = []
    for end in face_ends:
        beyond = [abs(x - d(end.x)) for x in row_x if (x < d(end.x) if end.side == "左" else x > d(end.x))]
        a_values.append(min(beyond))
    a1 = min(a_values) * MILLI
    # the width of each section
    centres_rows = [_pile_positions(pier, direction, row.number) for row in group.rows]
    each = {LOWER: diameter + depth[LOWER], UPPER: diameter + depth[UPPER]}
    pile_centres = [x * MILLI for row in centres_rows for x in row]
    # the width of a pile position: the union over all the piles of every row across (the rows share the piles' positions)
    union_lower = _union(sorted(set(pile_centres)), each[LOWER] / 2, half)
    union_upper = _union(sorted(set(pile_centres)), each[UPPER] / 2, half)
    column_mm = d(column) * MILLI
    widths = {
        "face_lower": _width("b + 2d", column_mm + 2 * depth[LOWER], full, ("b", column_mm), ("d", depth[LOWER])),
        "face_upper": _width("D + 2(d/2 + a)", diameter + 2 * (depth[UPPER] / 2 + a1), full,
                             ("D", diameter), ("d", depth[UPPER]), ("a", a1)),
        "pile_lower": _width("Σ(D + d)", union_lower, full, ("D", diameter), ("d", depth[LOWER])),
        "pile_upper": _width("Σ(D + d)", union_upper, full, ("D", diameter), ("d", depth[UPPER])),
        "face_shear": _width("Lp + D", across_span, full, ("Lp", across_span - diameter), ("D", diameter)),
    }
    spacing = stirrup_width(pier.rebar.footing, rebar_name)[1]
    web = stirrups(pier.rebar.footing, rebar_name)
    stirrup_rows = int(depth[UPPER] // d(web.pitch))
    stirrup_across = int(d(widths["pile_upper"].be) // d(spacing))
    count = stirrup_across * stirrup_rows
    if count < 1:
        raise InputError("鉄筋.フーチング.stirrups: 有効幅の中にスターラップがありません（柱面方向の間隔・幅の間隔を確かめてください）")
    ends = {"face": face_ends, "pile": pile_ends}

    def point(key: str, position: str, tension: str, bending: bool, deep_beam: str | None, wkey: str) -> Point:
        return Point(key, f"{position}（{tension}）", position, tension, ends["face" if position == FACE else "pile"],
                     widths[wkey], put(LENGTH_MM, height), put(LENGTH_MM, depth[tension]), bending, deep_beam,
                     put(LENGTH_MM, a1) if position == FACE else None, put(LENGTH_MM, diameter),
                     count if deep_beam == "upper_tension" else None)

    points = (point("face_lower", FACE, LOWER, True, None, "face_lower"),
              point("face_upper", FACE, UPPER, True, None, "face_upper"),
              point("pile_lower", PILE, LOWER, True, None, "pile_lower"),
              point("pile_upper", PILE, UPPER, True, "upper_tension", "pile_upper"),
              point("face_shear", FACE, LOWER, False, "lower_tension", "face_shear"))
    numbers = {extraction.group: extraction.number for extraction in frame_result.extractions}
    pickups = {case: numbers[group] for case, group in CASES if group is not None}
    chain = {member.number: (frame.nodes[member.start - 1].x, frame.nodes[member.end - 1].x)
             for member in frame.members if member.region is Region.FOOTING_BASE}
    members = tuple(sorted({end.member for end in (*face_ends, *pile_ends)}))
    return FootingBasis(rebar_name, points, (lower, upper), web, spacing, pier.materials.footing, pickups, members, chain)


# --- the section forces -----------------------------------------------------------------------------------------------


def _lines(forces: Mapping[int, Sequence[PointForces]], end: End, focus: str, what: str) -> PointForces:
    found = next((line for line in forces.get(end.member, ()) if line.focus == focus and line.point == end.point), None)
    if found is None:
        raise PileResponseError(f"{what}の部材 {end.member}（{end.point}）の {focus} の断面力がありません")
    return found


def _bending(forces: Mapping[int, Sequence[PointForces]], ends: Sequence[End], lower: bool, what: str
             ) -> tuple[End, SectionForce]:
    """The end and the case with the largest sagging (lower tension) or hogging (upper) moment."""
    best: tuple[End, SectionForce] | None = None
    for end in ends:
        line = _lines(forces, end, "M", what)
        found = line.largest if lower else line.smallest
        if best is None or ((found.md > best[1].md) if lower else (found.md < best[1].md)):
            best = (end, found)
    assert best is not None
    return best


def _shear(forces: Mapping[int, Sequence[PointForces]], ends: Sequence[End], what: str) -> tuple[End, SectionForce]:
    best: tuple[End, SectionForce] | None = None
    for end in ends:
        line = _lines(forces, end, "S", what)
        for found in (line.largest, line.smallest):
            if best is None or abs(found.vd) > abs(best[1].vd):
                best = (end, found)
    assert best is not None
    return best


def _force(case: Case, pickup: int, point: Point, forces: Mapping[int, Sequence[PointForces]], what: str) -> Force:
    lower = point.tension == LOWER
    end, moment = _bending(forces, point.ends, lower, what)
    md = moment.md if (moment.md >= 0 if lower else moment.md <= 0) else 0.0
    vd = vd_end = vd_combination = vd_md = None
    if point.deep_beam is not None:
        vd_end, shear = _shear(forces, point.ends, what)
        vd, vd_combination, vd_md = FORCE(abs(shear.vd)), shear.combination, MOMENT(shear.md)
    return Force(case, pickup, end, MOMENT(md), moment.combination, vd, vd_end, vd_combination, vd_md)


def complete(basis: FootingBasis, frame_forces: Mapping[tuple[int, int], Sequence[PointForces]],
             seismic_forces: Mapping[int, Sequence[PointForces]], seismic_elements: Mapping[int, int]) -> FootingDirection:
    """The forces of every point and case.

    *frame_forces* are the PIK lines by (pickup, member) of the frame analysis; *seismic_forces* the pickup lines of
    Aggre-SE by its member number and *seismic_elements* the number of its element of each base member of the frame
    (``PileResponseError`` when a line is missing)."""
    points = []
    for point in basis.points:
        forces = []
        for case, _ in CASES:
            if case is Case.SEISMIC:
                ends = tuple(End(end.side, seismic_elements[end.member], end.point, end.x) for end in point.ends)
                mapped = replace(point, ends=ends)
                found = _force(case, SEISMIC_PICKUP, mapped, seismic_forces, "地震時のピックアップ")
                # report the frame's member of each end, not the element of the NDU
                back = {seismic_elements[end.member]: end for end in point.ends}
                found = Force(found.case, found.pickup, back[found.end.member], found.md, found.md_combination,
                              found.vd, None if found.vd_end is None else back[found.vd_end.member],
                              found.vd_combination, found.vd_md)
            else:
                pickup = basis.pickups[case]
                lines = {member: frame_forces[(pickup, member)] for member in basis.members
                         if (pickup, member) in frame_forces}
                found = _force(case, pickup, point, lines, f"骨組解析のピックアップ {pickup}")
            forces.append(found)
        points.append(SectionForces(point, tuple(forces)))
    return FootingDirection(basis, tuple(points))


def calculate_footing(pier: PierInput, longitudinal_frame, transverse_frame) -> FootingBases:
    """Both directions from the input and the frames of 0610 and 0620, before any runner."""
    return FootingBases(prepare(pier, longitudinal_frame, LONGITUDINAL), prepare(pier, transverse_frame, TRANSVERSE))


def complete_footing(bases: FootingBases, longitudinal: tuple, transverse: tuple) -> FootingResult:
    """Both directions finished with (frame_forces, seismic_forces, seismic_elements) of each."""
    return FootingResult(complete(bases.longitudinal, *longitudinal), complete(bases.transverse, *transverse))
