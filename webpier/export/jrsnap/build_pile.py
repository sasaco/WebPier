"""The NDU model of a pile foundation of a 0710 or 0720 result (decision 93, CONTEXT.md JRSNAP入力モデル).

The frame is the one of the direct foundation without its springs: the column with the micro member, the footing (rigid,
with the rigid member along its base through the heads of the pile rows), numbered from the top left; each pile row is one
member from its head down, cut into elements and given the ground springs of the .sdc as JRSNAP's 連携 gives them
(``build.pile_row_parts``). The pile starts at the head joint on the footing base, so there is no rigid part of it.

- **Which row is the first column.** The springs of the .sdc are by column, the first column being the front row of the push
  (JRSNAP's connection screen takes the column of the pile row by hand). The front row is the one the earthquake pushes
  toward: the smallest x for −x (0710) and the largest for +x (0720); a reversed (逆向) combination pushes the other way, so
  its NDU takes the columns the other way round (``reverse``). The distances of the rows from the front row must be the ones
  the .sdc lists.
- **Sections.** Section 1 is the column's. A section of the pile follows for each zone of the hoops from the head: the 2D zone,
  then the zones below it (鉄筋.杭.hoops.lower). The section of a pile element is the one of the zone its upper end is in; the
  last zone goes on to the tip. The main bars (all along: a 段落し is not made yet), the cover, the steels, f'ck of the pile
  and its 施工条件 (the code of the manual's 表2-30) are common; the axial force is not given (JRSNAP takes the one of the
  analysis, as for the column).
- **Combinations.** Those of the push of this NDU: the forward ones, or the reversed ones with ``reverse``.
- **Liquefaction (decision 95).** The NDU for the liquefaction (``liquefied``) is the same frame and piles with the springs of
  the .sdc for the liquefaction (the caller reads it) and the one combination of ρm 1.0 and αf 1.0 of its push: one Case.
- **The 応答変位法 (decision 97).** An NDU a Case (``response_ndu``): the frame, the piles and the springs of the push, the basic
  cases of the forward combination of ρm 1.0 and αf 1.0 with the inertia (the cases that are not fixed) times |ν| of the Case,
  and the 地盤変位 of the level at each pile node, times the Case's factor of it, in the direction of the push; the analysis is
  the load increment up to the 最大応答震度 of the level. A Case with a negative factor of the inertia (④ νL Ra + 1.0 f(z)) is
  the reversed push of |νL| Ra and −1.0 f(z), which JRSNAP turns around both (its NDU has the columns of the reversed push).
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

from ...calc._exact import d, put
from ...calc.column_rebar import ColumnLayout, yield_strength
from ...calc.frame import NodeRole
from ...calc.ground_displacement import GroundDisplacement
from ...calc.response_displacement import ResponseCase
from ...calc.seismic_longitudinal import Increment
from ...calc.pile_seismic import pile_row
from ...calc.pile_springs import SeismicSprings
from ...core.errors import InputError
from ...core.printed import LENGTH, Printed
from ...inputs import PierInput, choices
from ...inputs.rebar import LENGTH_MM
from . import build
from .model import Combination, Joint
from .pile_build import pile_row_parts, row_title
from .pile_model import (COLUMN, EDSPX, M_THETA, RIGID, FrameElement, GroundLoad, Member, NonLinear, PileNduModel,
                         PileSection)
from .pile_records import pile_section_records
from .profile import LOAD_DIVISIONS, NONLINEAR_TITLE, SAFETY_BEFORE, SAFETY_GBS, SAFETY_GBVO, SAFETY_K, Profile
from .records import column_section_records
from .section import column_section, need

REBAR = "鉄筋.杭"
# the code of the construction condition in the CTS and EC' fields of the pile's concrete (表2-30): 自然泥水 or the CMC stabiliser
# is -3, the bentonite one -4 (SOIL-JR's 安定液使用: taken to be it)
CONSTRUCTION = {"自然泥水": -3, "安定液使用": -4}
DISTANCE_TOLERANCE = Decimal("0.0005")


def _hoop(hoop, path: str):
    return (need(hoop.diameter, f"{path}.diameter_mm"), need(hoop.sets, f"{path}.sets"),
            need(hoop.pitch, f"{path}.pitch_mm"))


def pile_sections(pier: PierInput, profile: Profile, diameter: Printed) -> tuple[tuple[PileSection, ...], list[Decimal]]:
    """The sections of the zones of the hoops and where each zone ends (m below the head; the last one has no end)."""
    bars, cast = pier.rebar.pile, pier.piles.cast_in_place
    if bars.cutoff.main_diameter is not None or bars.cutoff.main_count is not None:
        raise InputError(f"{REBAR}.cutoff.main_bars: 段落しのある杭の NDU は未対応です（決定93）")
    main = need(bars.main_diameter, f"{REBAR}.main_bars.diameter_mm")
    count = need(bars.main_count, f"{REBAR}.main_bars.count")
    cover = need(bars.pure_cover, f"{REBAR}.pure_cover_mm")
    grade = need(bars.materials.main, f"{REBAR}.materials.main")
    transverse = need(bars.materials.transverse, f"{REBAR}.materials.transverse")
    condition = need(cast.condition, "杭基礎.場所打ち杭.施工条件")
    conditions = getattr(pier.jrsnap, profile.jrsnap)
    key = f"jrsnap_{profile.jrsnap}"
    factors = [need(getattr(conditions, name), f"{key}.{name}")
               for name in ("shear_factor_vcd", "shear_factor_vsd", "shear_factor_vdd")]
    safety = (*SAFETY_BEFORE, factors[0], factors[1], SAFETY_GBS, SAFETY_K, factors[2], SAFETY_GBVO)
    zones = [(f"{REBAR}.hoops.zone_2d", bars.hoops.zone_2d, put(LENGTH, 2 * d(diameter)))]
    for index, lower in enumerate(bars.hoops.lower):
        length = need(lower.length, f"{REBAR}.hoops.lower[{index}].length_m")
        zones.append((f"{REBAR}.hoops.lower[{index}]", lower.hoop, length))
    sections, ends, end = [], [], Decimal(0)
    for path, hoop, length in zones:
        hoop_diameter, sets, pitch = _hoop(hoop, path)
        end += d(length)
        ends.append(end)
        title = f"杭(φ{d(diameter) * 1000:.0f})：帯鉄筋ctc{pitch.value:g}"
        sections.append(PileSection(
            title=title, radius=put(LENGTH_MM, d(diameter) * 500), axial_force=None,
            fck=need(cast.fck, "杭基礎.場所打ち杭.f'ck"), construction=CONSTRUCTION[condition],
            aggregate_max=need(bars.aggregate_max, f"{REBAR}.aggregate_max_mm"), yield_strength=yield_strength(grade),
            center=put(LENGTH_MM, d(cover) + d(hoop_diameter) + d(main) / 2), diameter=main, count=count,
            hoop_yield=yield_strength(transverse), hoop_diameter=hoop_diameter, hoop_legs=2 * sets, hoop_pitch=pitch,
            safety=safety))
    return tuple(sections), ends[:-1]


def _front(profile: Profile, reverse: bool) -> int:
    """−1 when the front row of the push is the one at the smallest x, +1 at the largest."""
    return int(profile.earthquake) * (-1 if reverse else 1)


LIQUEFACTION_PATTERN = (Decimal("1.0"), Decimal("1.0"))  # the (ρm, αf) of the one combination of the NDU for the liquefaction


def _frame_elements(frame: Any) -> tuple[list[Any], dict[int, int], build._Elements]:
    """The nodes above the pile tips (from the top, at one height from the left), the number of each in the temporary
    numbering, and the elements of the members that are not piles."""
    top = frame.node(NodeRole.FOOTING_TOP)
    base = sorted((node for node in frame.nodes if NodeRole.PILE_TIP not in node.roles),
                  key=lambda node: (-node.y.value, node.x.value))
    temporary = {node.number: index for index, node in enumerate(base, 1)}
    joints = {temporary[node.number]: Joint(temporary[node.number], node.x, put(LENGTH, d(top.y) - d(node.y)))
              for node in base}
    elements = build._Elements(joints)
    for member in frame.members:
        if not member.pile:
            elements.add(replace(member, start=temporary[member.start], end=temporary[member.end]))
    return base, temporary, elements


def pile_node_depths(model: PileNduModel) -> tuple[Decimal, ...]:
    """The depth below the pile head (m) of each node of the piles of *model*, from the head down: the rows share them, as
    they are cut at the same layers (decision 97)."""
    joints = {joint.number: joint for joint in model.joints}
    elements = {element.number: element for element in model.elements}
    depths: set[Decimal] = set()
    for pile in model.piles:
        head = d(joints[elements[pile.first].i].y)
        for number in range(pile.first, pile.last + 1):
            depths.update(d(joints[node].y) - head for node in (elements[number].i, elements[number].j))
    return tuple(sorted(depths))


def element_numbers(frame: Any) -> dict[int, int]:
    """The element of the NDU (and so the member of Aggre-SE's pickup) that each member of *frame* that is not a pile
    becomes, by the frame's member number (a member the NDU splits has its first element; decision 96)."""
    return dict(_frame_elements(frame)[2].first)


def build_pile_ndu(profile: Profile, pier: PierInput, layout: ColumnLayout, seismic, springs: SeismicSprings, *,
                   reverse: bool = False, liquefied: bool = False,
                   combination: Combination | None = None) -> PileNduModel:
    """*seismic* is a SeismicLongitudinalResult or a SeismicTransverseResult of the same input on piles; *reverse* the NDU of
    the reversed (逆向) combinations; *liquefied* the NDU for the liquefaction, whose *springs* are those of the .sdc for it;
    *combination* the one combination of the NDU in place of those of *seismic* (the 応答変位法, decision 97)."""
    if pier.substructure.foundation != choices.CAST_IN_PLACE_PILE:
        raise InputError("地震時の杭基礎の NDU は場所打ち杭だけに対応します（鋼管ソイルセメント杭は未対応です、決定93）")
    frame = seismic.frame
    group = frame.piles
    assert group is not None  # the frame of a pile foundation
    combinations = (combination,) if combination is not None else tuple(
        Combination(rho_m=c.rho_m, alpha_f=c.alpha_f,
                    coefficients=tuple(int(action.case in c.cases) for action in seismic.basic_cases), reverse=c.reverse)
        for c in seismic.combinations if c.reverse == reverse
        and (not liquefied or (d(c.rho_m), d(c.alpha_f)) == LIQUEFACTION_PATTERN))
    if not combinations:
        raise InputError("向きを反転した（逆向の）組合せがありません" if reverse else "組合せがありません")
    top = frame.node(NodeRole.FOOTING_TOP)
    base, temporary, elements = _frame_elements(frame)
    # the joints of the frame and of the footing offset, from the top and the left, then those of the piles
    final = {joint.number: number for number, joint in enumerate(
        sorted(elements.joints.values(), key=lambda joint: (joint.y.value, joint.x.value)), 1)}
    placed = {final[joint.number]: replace(joint, number=final[joint.number]) for joint in elements.joints.values()}
    of_frame = {number: final[tmp] for number, tmp in temporary.items()}
    frame_elements = [FrameElement(e.number, final[e.i], final[e.j], COLUMN if e.nonlinear else RIGID,
                                   1 if e.nonlinear else 0) for e in elements.elements]
    members = [Member(e.number, e.title, final[e.i], final[e.j], e.length, ((e.length, 1),), nonlinear=True)
               for e in elements.elements]
    control = of_frame[build._control(frame, profile).number]
    column = column_section(profile, pier, layout, frame, build._control(frame, profile))
    nonlinear = [NonLinear(section=1, model=M_THETA, failure=2 if column.shear_failure else 1, ends=(1, 1),
                           depth_piles=1, title=NONLINEAR_TITLE)]
    diameter = group.section.diameter
    pile_sections_, boundaries = pile_sections(pier, profile, diameter)
    ends = [LENGTH(float(end)) for end in boundaries]

    def section(depth: Printed) -> int:
        return 2 + sum(1 for end in ends if depth.value >= end.value)

    direction = springs.direction(group.direction)
    rows = group.rows
    if direction.rows != len(rows):
        raise InputError(f".sdc の{group.direction}の杭列数（{direction.rows}）が入力の杭の列（{len(rows)}列）と違います")
    forward = _front(profile, reverse) < 0  # the front row is the first of the rows by x
    zone = put(LENGTH, 2 * d(diameter))
    piles, supports, next_joint = [], [], len(placed) + 1
    for index, (row, nodes) in enumerate(zip(rows, frame.pile_nodes)):
        column_number = index + 1 if forward else len(rows) - index
        front = rows[0].x if forward else rows[-1].x
        if abs(abs(d(row.x) - d(front)) - Decimal(repr(direction.distances[column_number - 1]))) > DISTANCE_TOLERANCE:
            raise InputError(f".sdc の{group.direction}の杭列 {column_number} の位置（先頭の列から"
                             f"{direction.distances[column_number - 1]} m）が入力の杭の列の位置と違います")
        if direction.depth_piles[column_number - 1] != row.piles:
            raise InputError(f".sdc の{group.direction}の杭列 {column_number} の奥行き本数"
                             f"（{direction.depth_piles[column_number - 1]}）が入力の杭の列（{row.piles}本）と違います")
        model = pile_row(direction, column_number, diameter)
        head = of_frame[nodes.head]
        parts = pile_row_parts(model, member=len(members) + 1, head_joint=head, first_joint=next_joint, x=row.x,
                               top=placed[head].y, rigid=None, first_element=len(frame_elements) + 1,
                               first_nonlinear=len(nonlinear) + 1, section=section, zone=zone, title=row_title(row.piles))
        next_joint += len(model.nodes) - 1
        placed.update({joint.number: joint for joint in parts.joints})
        members.append(parts.member)
        frame_elements += parts.elements
        nonlinear += parts.nonlinear
        piles.append(parts.pile)
        supports += parts.supports
    regions = {member.number: member.region for member in frame.members}
    cases = []
    for number, action in enumerate(seismic.basic_cases, 1):
        case = build._case(number, action, profile, elements, regions)
        loads = sorted((replace(load, node=of_frame[load.node]) for load in case.joint_loads), key=lambda load: load.node)
        cases.append(replace(case, joint_loads=tuple(loads)))
    sections = (tuple(column_section_records(1, column)),
                *(tuple(pile_section_records(number, s)) for number, s in enumerate(pile_sections_, 2)))
    return PileNduModel(
        profile=profile, analysis=build._analysis(pier, profile), control=control, origin=of_frame[top.number],
        joints=tuple(placed[number] for number in sorted(placed)), members=tuple(members), elements=tuple(frame_elements),
        nonlinear=tuple(nonlinear), sections=sections, piles=tuple(piles), supports=tuple(supports), cases=tuple(cases),
        combinations=combinations, shear_span=column.shear_span)


RESPONSE_PATTERN = (Decimal("1.0"), Decimal("1.0"))  # the (ρm, αf) of the inertia Case and of the 応答変位法 (decision 97)


def response_pattern(seismic) -> Any:
    """The forward combination of ρm 1.0 and αf 1.0 of *seismic*: the inertia Case the 応答変位法 takes Teq and Kh from, and
    whose basic cases its Cases take (decision 97)."""
    return next(c for c in seismic.combinations
                if not c.reverse and (d(c.rho_m), d(c.alpha_f)) == RESPONSE_PATTERN)


def response_ndu(profile: Profile, pier: PierInput, layout: ColumnLayout, seismic, springs: SeismicSprings,
                 ground: GroundDisplacement, head_depth: Decimal, case: ResponseCase) -> PileNduModel:
    """The NDU of the Case *case* of the 応答変位法 (decision 97): the pile heads are *head_depth* (m) below the ground surface."""
    pattern = response_pattern(seismic)
    reverse = case.inertia.value < 0
    inertia = abs(d(case.inertia))
    coefficients = tuple(
        (inertia if action.increment is not Increment.FIXED else 1) if action.case in pattern.cases else 0
        for action in seismic.basic_cases)
    model = build_pile_ndu(profile, pier, layout, seismic, springs, reverse=reverse,
                           combination=Combination(pattern.rho_m, pattern.alpha_f, coefficients, reverse))
    factor = d(case.displacement) * profile.earthquake * (-1 if reverse else 1)  # +: the way the push goes
    joints = {joint.number: joint for joint in model.joints}
    elements = {element.number: element for element in model.elements}
    rows: dict[int, Printed] = {}
    for pile in model.piles:
        head = d(joints[elements[pile.first].i].y)
        for number in range(pile.first, pile.last + 1):
            for node in (elements[number].i, elements[number].j):
                point = ground.at(head_depth + d(joints[node].y) - head)
                displacement = point.l1 if case.level == "L1" else point.l2
                rows[node] = put(EDSPX, d(displacement) / 1000 * factor)
    steps = int(d(case.kh) * LOAD_DIVISIONS)
    return replace(model, ground=GroundLoad(steps, tuple(sorted(rows.items()))))
