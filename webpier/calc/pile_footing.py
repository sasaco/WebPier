"""0800 フーチングの応答値 of a pile foundation (decision 96, Example橋脚4 第V編 2・3): the design section forces of the
footing at the column face (く体前面) and at the outermost pile (杭位置), and the effective widths they are checked with.

The footing of the frame of a pile foundation is a rigid base member between the heads of the pile rows, cut at the faces
of the column (``calc.frame``, NodeRole.COLUMN_FACE), so a section force of the footing is the force at the end of a
member, as FEMPython's PIK and Aggre-SE's pickup give it (nothing is interpolated):

- the face section is the end at the column face of the member next to it, the pile section the end at the outermost
  pile head of the chain of members from the face outwards; each side of the column has its own, and a case takes the
  side with the larger demand;
- the cases of the check are those of the frame analysis (安全性（破壊）, 耐久性の 永久＋変動 and 永久: the PIK of the
  extraction groups of 0612 / 0622; the 安全性（破壊） times the 応答値係数 γR 1.2 of the linear frame, decision 104) and, for the 復旧性（地震時）, the pickup of 復旧性L2 of Aggre-SE's check of 0711 / 0721
  (the largest and the smallest M, S and N of each member end over its Cases);
- the bending moment of a section is the largest sagging moment (the PIK's M is positive for a lower tension) for the
  lower tension and the largest hogging moment for the upper tension, 0 when the footing has none of that sense;
- the deep beam shear force (decision 124) is, over the sides, the largest shear of the sense that makes that side's column
  face sag (the pile of that side pushed up) for the lower tension (Vfdd), and of the sense that makes it hog (the pile
  pulled down) for the upper tension (Vsd), with the moment of its case at the same end; a case with no shear of that
  sense on any side has no Vd at the point (none is given to Capacita, which then does not check the case). The sense of
  S differs by the source: Aggre-SE's pickup has S = dM/dx along i → j (the push is a positive S on the left side, a
  negative one on the right), FEMPython's PIK S = −dM/dx (the push is a negative S on the left, a positive one on the
  right); both with M positive for a lower tension (Example橋脚4: Aggre-SE's element 7 has its largest S 25087.89 and its
  largest M 27491.61 at the left face in the same Case 2, FEMPython's member 6 its largest M 13146.87 at the left face
  with S −10805.26).

The effective widths are WebPier's (the sample 2.3.1 and 2.3.2 (2), RC標準 8.8.5.2; the check itself is Capacita's,
ADR-0008). With d the effective depth to the tensile bars of the face (the footing height less their centroid), D the pile
diameter (a 場所打ち杭's 杭径, a 鋼管ソイルセメント杭's ソイルセメント径: the sample V-114, decision 124), a the distance from the
column face to the centre of the nearest pile row beyond it, B the width of the footing across the plane:

- face, lower tension: b + 2 d, b the column width across, not more than B;
- face, upper tension: D + 2 (d/2 + a), not more than B;
- pile position (either tension): the piles of every row each take D + d around their centre across, cut at the edges
  of the footing; where they overlap they are joined, and the width is the sum of the pieces, each rounded to mm
  (ADR-0003: the sample prints the width of one pile, 2522, and the sum 5044), not more than B (decision 124);
- the deep beam shear at the face (lower tension, decision 124): each pile of the nearest row beyond the face takes
  0.65 √(a1² + d1²) + D, d1 the d of the lower tension, a1 from the pile centre to the column face (a1a = ax) or, for a
  pile outside the column's width across, to its corner (a1b = √(ax² + ay²), ay from the column's side face); each a1
  and each width is rounded to mm, and the width is their sum, not more than the end piles' centre distance Lp plus D
  (nor B). Capacita's a1 of Vfdd is the largest a1 of the row. When both sides of the column have a row beyond the face
  the nearer is taken (as for a), the left one when they are equally near. The column is placed across by its
  overhangs, the first on the negative side;
- the deep beam shear at the pile position (upper tension, Vsd, decision 124): the footing's whole width B (the sample
  tables 2.3.11, 2.4.3, 3.3.11 and 3.4.3: the shear is taken as even across, V-127, V-165), not the pile position's
  width of the bending, so it is a point of its own; its stirrups are those within d across B.

The cases are those of the parts the input chooses (decision 110, inputs.outputs.footing_parts): those of the frame analysis,
the 復旧性（地震時）, or all four. The deep beam shear is checked for 安全性（破壊） and for 復旧性（地震時） (decision 124), so a
point of it has the shear of those cases (none of 耐久性); without the frame analyses the sections come from the frame of
0710 / 0720 (the same frame, cut at the faces of the column too) and the points of the shear carry the earthquake alone.

Everything here is calculated from the printed values of the input and of the files, and every number is a ``Printed``
(ADR-0003).
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
from .pile_body import PileResponseError, PointForces, SectionForce, factored
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
# the cases of the deep beam shear (decision 124; that of 耐久性 is omitted, as the direct footing's of a 面部材)
SHEAR_CASES = frozenset((Case.SAFETY, Case.SEISMIC))


@dataclass(frozen=True)
class End:
    """The end of a base member that is a section of one side: the member, the point of its PIK lines and its x (m)."""

    side: str  # 左 / 右 (by x)
    member: int
    point: str  # ITAN / JTAN
    x: Printed


FULL_WIDTH = "B"  # the rule of the width of Vsd: the footing's whole width (decision 124)


@dataclass(frozen=True)
class PileShare:
    """The share of one pile of the shear width of the face (decision 124): a1 to the column face (a1a) or to its corner
    (a1b, ``corner``), and 0.65 √(a1² + d1²) + D, both mm."""

    a1: Printed
    be: Printed
    corner: bool


@dataclass(frozen=True)
class Width:
    """An effective width (mm) with what it is made of, for the report."""

    rule: str  # the formula as the report prints it
    be: Printed
    full: Printed  # B, the footing width across, mm
    terms: tuple[tuple[str, Printed], ...]  # the quantities of the rule, in order
    pieces: tuple[Printed, ...] = ()  # a pile position's: the widths of its pieces when they are apart (decision 124)
    shares: tuple[PileShare, ...] = ()  # the shear at the face: each pile's of its row (decision 124)


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
    a1: Printed | None  # mm, of the deep beam shear of the face (Vfdd): the largest a1 of its row (decision 124)
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
    shear force absolute; None when the point has no deep beam shear, or the case none of the point's sense)."""

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
    forces: tuple[Force, ...]  # in the order of CASES, those of the parts made (decision 110)

    def force(self, case: Case) -> Force | None:
        """The forces of *case*, or None when its part is not made."""
        return next((force for force in self.forces if force.case is case), None)


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


def _union(centres: Sequence[Decimal], half: Decimal, edge: Decimal) -> tuple[Decimal, ...]:
    """The lengths of the pieces of the union of the intervals centre ± half, within -edge … +edge, from the left (one
    piece when they all overlap)."""
    pieces: list[list[Decimal]] = []
    for low, high in sorted((max(c - half, -edge), min(c + half, edge)) for c in centres):  # equal widths: no interval is inside another
        if pieces and low <= pieces[-1][1]:
            pieces[-1][1] = high
        else:
            pieces.append([low, high])
    return tuple(high - low for low, high in pieces)


def _printed(value: Decimal) -> Printed:
    return put(WIDTH, value)


def _width(rule: str, be: Decimal, full: Decimal, *terms: tuple[str, Decimal]) -> Width:
    return Width(rule, _printed(min(be, full)), _printed(full), tuple((name, put(LENGTH_MM, item)) for name, item in terms))


def _pile_width(pieces: Sequence[Decimal], full: Decimal, diameter: Decimal, depth: Decimal) -> Width:
    """The width of a pile position (decision 124): each piece rounded to mm, then summed, not more than B; the pieces are
    listed when they are apart."""
    rounded = tuple(_printed(piece) for piece in pieces)
    width = _width("Σ(D + d)", sum((d(piece) for piece in rounded), Decimal(0)), full, ("D", diameter), ("d", depth))
    if len(rounded) == 1:
        return width
    return replace(width, terms=(*width.terms, *((f"be({index})", piece) for index, piece in enumerate(rounded, 1))),
                   pieces=rounded)


def _shear_width(ax: Decimal, centres: Sequence[Decimal], column: tuple[Decimal, Decimal], depth: Decimal,
                 diameter: Decimal, full: Decimal) -> Width:
    """The width of the deep beam shear at the face (decision 124, RC標準 8.8.5.2, the sample V-127): each pile of the row
    at *centres* (mm across) takes 0.65 √(a1² + d1²) + D, a1 = ax for a pile within the column's width *column* (its two
    side faces, mm across) and the diagonal to the corner, √(ax² + ay²), for one outside; the sum, not more than Lp + D
    (nor B). A row of one pile has no Lp: its be, not more than B (decision 128)."""
    shares = []
    for centre in centres:
        ay = max(column[0] - centre, centre - column[1], Decimal(0))
        a1 = _printed((ax * ax + ay * ay).sqrt())
        shares.append(PileShare(a1, _printed(Decimal("0.65") * (d(a1) ** 2 + depth * depth).sqrt() + diameter), ay > 0))
    terms = (("d1", put(LENGTH_MM, depth)), ("D", put(LENGTH_MM, diameter)),
             *((f"a1({index})", share.a1) for index, share in enumerate(shares, 1)),
             *((f"be({index})", share.be) for index, share in enumerate(shares, 1)))
    total = sum((d(share.be) for share in shares), Decimal(0))
    if len(shares) == 1:
        return Width("0.65√(a1² + d1²) + D", _printed(min(total, full)), _printed(full), terms, shares=tuple(shares))
    span = max(centres) - min(centres)
    return Width("Σ{0.65√(a1² + d1²) + D}\n≦ Lp + D", _printed(min(total, span + diameter, full)), _printed(full),
                 (*terms, ("Lp", put(LENGTH_MM, span))), shares=tuple(shares))


def prepare(pier: PierInput, frame_result, direction: FootingDirectionKind, frames: bool = True) -> FootingBasis:
    """The sections of the footing in *direction* from the frame of 0610 / 0620 and the input (before any runner); an input
    that cannot be checked is an input error naming it. Without the frame analyses (*frames* false, decision 110)
    *frame_result* is the result of 0710 / 0720, whose frame has the same sections, and there is no pickup."""
    frame = frame_result.frame
    if frame.piles is None:
        raise InputError("杭基礎のフーチングには杭の骨組が必要です（基礎形式が杭基礎ではありません）")
    sub = pier.substructure
    rebar_name = direction.name
    lower, upper = main_bars(pier, rebar_name, choices.BEAM_FACES[1]), main_bars(pier, rebar_name, choices.BEAM_FACES[0])
    height = d(sub.h[6]) * MILLI
    depth = {LOWER: height - d(lower.centroid), UPPER: height - d(upper.centroid)}
    column, left, right = direction.across(sub)
    full = (d(left) + d(column) + d(right)) * MILLI
    piles = pier.piles
    diameter = d(piles.cast_in_place.diameter if sub.foundation == choices.CAST_IN_PLACE_PILE
                 else piles.steel_soil_cement.soil_cement_diameter) * MILLI
    group = frame.piles
    half = full / 2
    # the column's side faces across (mm from the footing centre; the first overhang on the negative side), as the frame of
    # the other direction (and its NDU) places the column: its axis is the column's centroid (B7 − B9) / 2 or (W7 − W9) / 2
    # (calc.reaction.self_weight, calc.frame), the faces ± B6 / 2 or W6 / 2 from it; the piles across are on the same axis
    side_face = -half + d(left) * MILLI
    column_faces = (side_face, side_face + d(column) * MILLI)
    sides = {side: _side_ends(frame, side) for side in ("左", "右")}
    if all(face is None for face, _ in sides.values()):
        raise InputError("杭基礎のフーチング: く体前面より外側に杭の列がありません（フーチングの照査は、く体前面と杭位置の間にフーチングがある杭の配置だけに対応します）")
    face_ends = tuple(face for face, _ in sides.values() if face is not None)
    pile_ends = tuple(end for _, end in sides.values() if end is not None)
    # a: the face to the centre of the nearest row beyond it, per side; the nearest of the sides is taken (the left one
    # when they are equally near), and its row is that of the shear at the face (decision 124)
    nearest = []
    for end in face_ends:
        nearest.append(min((abs(d(row.x) - d(end.x)), row.number) for row in group.rows
                           if (d(row.x) < d(end.x) if end.side == "左" else d(row.x) > d(end.x))))
    a, shear_row = min(nearest, key=lambda found: found[0])
    a1 = a * MILLI
    # the width of each section
    each = {LOWER: diameter + depth[LOWER], UPPER: diameter + depth[UPPER]}
    # the width of a pile position: the union over all the piles of every row across (the rows share the piles' positions)
    pile_centres = sorted({x * MILLI for row in group.rows for x in _pile_positions(pier, direction, row.number)})
    column_mm = d(column) * MILLI
    shear = _shear_width(a1, [x * MILLI for x in _pile_positions(pier, direction, shear_row)], column_faces,
                         depth[LOWER], diameter, full)
    widths = {
        "face_lower": _width("b + 2d", column_mm + 2 * depth[LOWER], full, ("b", column_mm), ("d", depth[LOWER])),
        "face_upper": _width("D + 2(d/2 + a)", diameter + 2 * (depth[UPPER] / 2 + a1), full,
                             ("D", diameter), ("d", depth[UPPER]), ("a", a1)),
        "pile_lower": _pile_width(_union(pile_centres, each[LOWER] / 2, half), full, diameter, depth[LOWER]),
        "pile_upper": _pile_width(_union(pile_centres, each[UPPER] / 2, half), full, diameter, depth[UPPER]),
        "face_shear": shear,
        "pile_shear": _width(FULL_WIDTH, full, full, ("B", full)),
    }
    # the a1 of Capacita's Vfdd: the largest of the row's (the sample 1768, decision 124)
    shear_a1 = max(share.a1.value for share in shear.shares)
    spacing = stirrup_width(pier.rebar.footing, rebar_name)[1]
    web = stirrups(pier.rebar.footing, rebar_name)
    stirrup_rows = int(depth[UPPER] // d(web.pitch))
    stirrup_across = int(d(widths["pile_shear"].be) // d(spacing))
    count = stirrup_across * stirrup_rows
    if count < 1:
        raise InputError("鉄筋.フーチング.stirrups: 有効幅の中にスターラップがありません（柱面方向の間隔・幅の間隔を確かめてください）")
    ends = {"face": face_ends, "pile": pile_ends}

    def point(key: str, position: str, tension: str, bending: bool, deep_beam: str | None) -> Point:
        return Point(key, f"{position}（{tension}）", position, tension, ends["face" if position == FACE else "pile"],
                     widths[key], put(LENGTH_MM, height), put(LENGTH_MM, depth[tension]), bending, deep_beam,
                     LENGTH_MM(shear_a1) if deep_beam == "lower_tension" else None, put(LENGTH_MM, diameter),
                     count if deep_beam == "upper_tension" else None)

    points = (point("face_lower", FACE, LOWER, True, None),
              point("face_upper", FACE, UPPER, True, None),
              point("pile_lower", PILE, LOWER, True, None),
              point("pile_upper", PILE, UPPER, True, None),
              point("face_shear", FACE, LOWER, False, "lower_tension"),
              point("pile_shear", PILE, UPPER, False, "upper_tension"))
    numbers = {extraction.group: extraction.number for extraction in frame_result.extractions} if frames else {}
    pickups = {case: numbers[group] for case, group in CASES if group is not None and frames}
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


# the sign of the shear that pushes the pile of the left side up (its column face sagging), by the source of the forces
# (decision 124): Aggre-SE's pickup S = dM/dx along i → j, FEMPython's PIK S = −dM/dx; the right side's is the opposite
SEISMIC_PUSH, FRAME_PUSH = 1, -1


def _shear(forces: Mapping[int, Sequence[PointForces]], ends: Sequence[End], push: bool, left_push: int, what: str
           ) -> tuple[End, SectionForce] | None:
    """The end and the case of the largest shear of the sense that pushes (*push*) or pulls the pile of its side, None when
    no side has a shear of that sense (decision 124)."""
    best: tuple[End, SectionForce] | None = None
    for end in ends:
        line = _lines(forces, end, "S", what)
        sense = left_push * (1 if end.side == "左" else -1) * (1 if push else -1)
        for found in (line.largest, line.smallest):
            if found.vd * sense > 0 and (best is None or abs(found.vd) > abs(best[1].vd)):
                best = (end, found)
    return best


def _force(case: Case, pickup: int, point: Point, forces: Mapping[int, Sequence[PointForces]], left_push: int, what: str
           ) -> Force:
    lower = point.tension == LOWER
    end, moment = _bending(forces, point.ends, lower, what)
    md = moment.md if (moment.md >= 0 if lower else moment.md <= 0) else 0.0
    vd = vd_end = vd_combination = vd_md = None
    if point.deep_beam is not None and case in SHEAR_CASES:
        # Vfdd (lower tension) takes the push, Vsd (upper tension) the pull
        found = _shear(forces, point.ends, point.deep_beam == "lower_tension", left_push, what)
        if found is not None:
            vd_end, shear = found
            vd, vd_combination, vd_md = FORCE(abs(shear.vd)), shear.combination, MOMENT(shear.md)
    return Force(case, pickup, end, MOMENT(md), moment.combination, vd, vd_end, vd_combination, vd_md)


def complete(basis: FootingBasis, frame_forces: Mapping[tuple[int, int], Sequence[PointForces]] | None,
             seismic_forces: Mapping[int, Sequence[PointForces]] | None,
             seismic_elements: Mapping[int, int] | None) -> FootingDirection:
    """The forces of every point and case.

    *frame_forces* are the PIK lines by (pickup, member) of the frame analysis; *seismic_forces* the pickup lines of
    Aggre-SE by its member number and *seismic_elements* the number of its element of each base member of the frame
    (``PileResponseError`` when a line is missing). None for a part not made (decision 110): without the frame analysis
    the points of the deep beam shear carry the earthquake alone (decision 124)."""
    points = []
    for point in basis.points:
        forces = []
        for case, _ in CASES:
            if (seismic_forces if case is Case.SEISMIC else frame_forces) is None:
                continue
            if case is Case.SEISMIC:
                assert seismic_forces is not None and seismic_elements is not None  # the same part
                ends = tuple(End(end.side, seismic_elements[end.member], end.point, end.x) for end in point.ends)
                mapped = replace(point, ends=ends)
                found = _force(case, SEISMIC_PICKUP, mapped, seismic_forces, SEISMIC_PUSH, "地震時のピックアップ")
                # report the frame's member of each end, not the element of the NDU
                back = {seismic_elements[end.member]: end for end in point.ends}
                found = replace(found, end=back[found.end.member],
                                vd_end=None if found.vd_end is None else back[found.vd_end.member])
            else:
                assert frame_forces is not None  # the cases of the frame analysis are made with its forces
                pickup = basis.pickups[case]
                lines = {member: (factored(frame_forces[(pickup, member)]) if case is Case.SAFETY
                                  else frame_forces[(pickup, member)])
                         for member in basis.members if (pickup, member) in frame_forces}
                found = _force(case, pickup, point, lines, FRAME_PUSH, f"骨組解析のピックアップ {pickup}")
            forces.append(found)
        points.append(SectionForces(point, tuple(forces)))
    return FootingDirection(basis, tuple(points))


def calculate_footing(pier: PierInput, longitudinal_frame, transverse_frame, frames: bool = True) -> FootingBases:
    """Both directions from the input and the frames of 0610 and 0620 (of 0710 and 0720 without the frame analyses,
    *frames* false, decision 110), before any runner."""
    return FootingBases(prepare(pier, longitudinal_frame, LONGITUDINAL, frames),
                        prepare(pier, transverse_frame, TRANSVERSE, frames))


def complete_footing(bases: FootingBases, longitudinal: tuple, transverse: tuple) -> FootingResult:
    """Both directions finished with (frame_forces, seismic_forces, seismic_elements) of each (None for a part not made)."""
    return FootingResult(complete(bases.longitudinal, *longitudinal), complete(bases.transverse, *transverse))
