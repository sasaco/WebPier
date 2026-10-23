"""The NDU model of a 0710 or 0720 result, by its profile (CONTEXT.md JRSNAP入力モデル).

- Joints: the frame nodes, y turned downward from the footing top (the origin, JointOrg), numbered from the top,
  left to right at one height (JRSNAP 2.1.6).
- Elements: one per frame member, i at the upper (or left) end; the micro member is the automatic M-θ element,
  every other member a rigid region. An inclined rigid member (the offset of an asymmetric footing) is a vertical
  and a horizontal element through a new joint; an inclined elastic member is not supported.
- Section: ``section.column_section``.
- Supports: the short-term Ks / Kv of 0500 at the footing base and FootInfo, from which JRSNAP derives the
  nonlinear rotational spring of the direct foundation (B in the plane, kv, Df, γ1, γ2, φ, c = 0). The 0500 Kr
  is not added: FootInfo is that spring.
- Load cases: the basic cases in order, with their fixed / incremental / limited incremental kind. A point load
  keeps N (downward), H (+x) and M (N × +x lever) of the frame: JRSNAP's y down and M clockwise give the same
  signs. A horizontal load along a member is −h on the local y of the top-to-bottom element; the D1 column
  and pedestal weights are axial loads (the pedestal's titled 桁受け自重, decision 81). A load without a
  component has no row.
- Combinations: one per calc combination, coefficient 1 for its cases and 0 for the others, with its ρm, αf and
  whether it is reversed (逆向, decision 76).

Values come from the results as they are printed; nothing is recalculated.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ...calc._exact import d, put
from ...calc.column_rebar import ColumnLayout
from ...calc.embedment import EmbedmentResult
from ...calc.foundation import FoundationResult
from ...calc.frame import Frame, Member, Node, NodeRole, Region
from ...calc.seismic_longitudinal import Increment
from ...core.errors import InputError
from ...core.printed import LENGTH, Printed
from ...inputs import PierInput
from .model import (
    AXIAL, LOCAL_Y, Analysis, Combination, Element, Footing, Joint, JointLoad, LoadCase, MemberLoad, NduModel, Spring,
)
from .profile import REGION_TITLES, SANDY_SOILS, Profile
from .section import column_section, need

INCREMENTS = {Increment.FIXED: 0, Increment.INCREMENTAL: 1, Increment.LIMITED: 4}
PEDESTAL_WEIGHT = "桁受け自重"  # the title of the D1 pedestal line load (decision 81)
HORIZONTAL, VERTICAL = 1, 2


def _negative(value: Printed) -> Printed:
    return Printed(-value.value, value.digits, value.unit)


class _Elements:
    """Elements numbered in member order; an inclined rigid member becomes two (decision 40).

    The rigid offset of an asymmetric footing (footing top on the column axis to the centroid at the footing
    centre) is written as a vertical rigid element down to a new joint at the centroid level, then a horizontal
    one to the centroid: the same rigid connection, in the vertical and horizontal elements JRSNAP is given.
    """

    def __init__(self, joints: dict[int, Joint]) -> None:
        self.joints = joints
        self.elements: list[Element] = []
        self.first: dict[int, int] = {}  # member number -> its (first) element number
        self.reversed: dict[int, bool] = {}  # member number -> i is the member end node

    def _add(self, member: Member, start: Joint, end: Joint) -> bool:
        first, second = sorted((start, end), key=lambda joint: (joint.y.value, joint.x.value))
        length = put(LENGTH, abs(d(end.x) - d(start.x)) + abs(d(end.y) - d(start.y)))  # one of the two is zero
        self.elements.append(Element(number=len(self.elements) + 1, i=first.number, j=second.number, length=length,
                                     nonlinear=not member.rigid, title=REGION_TITLES[member.region]))
        return first is not start

    def add(self, member: Member) -> None:
        start, end = self.joints[member.start], self.joints[member.end]
        self.first[member.number] = len(self.elements) + 1
        if start.x != end.x and start.y != end.y:
            if not member.rigid:
                raise InputError(f"骨組の部材{member.number}（{REGION_TITLES[member.region]}）が斜めの弾性部材です。"
                                 "JRSNAP 出力は斜めの剛部材だけを鉛直・水平に分けられます")
            corner = Joint(len(self.joints) + 1, start.x, end.y)
            self.joints[corner.number] = corner
            self._add(member, start, corner)
            self._add(member, corner, end)
            self.reversed[member.number] = False  # only the footing offset is inclined: it carries no member load
        else:
            self.reversed[member.number] = self._add(member, start, end)


def _analysis(pier: PierInput, profile: Profile) -> Analysis:
    conditions, key = getattr(pier.jrsnap, profile.jrsnap), f"jrsnap_{profile.jrsnap}"
    magnitude = need(conditions.target_displacement, f"{key}.target_displacement_m")
    # The input is a magnitude; the displacement is toward the earthquake of the calculation (decision 43).
    target = put(LENGTH, d(magnitude) * profile.earthquake)
    return Analysis(steps=need(conditions.steps, f"{key}.analysis_steps"),
                    limited_final_step=need(conditions.limited_final_step, f"{key}.limited_final_step"), target=target)


def _control(frame: Frame, profile: Profile) -> Node:
    return next(node for node in frame.nodes if profile.control <= node.roles)


def _footing(pier: PierInput, foundation: FoundationResult, embedment: EmbedmentResult, profile: Profile,
             node: int) -> Footing:
    support = pier.soil.support
    path = f"地盤データ.層[{pier.soil.layers.index(support)}]"
    if support.soil_type not in SANDY_SOILS:
        raise InputError(f"{path}.土質区分: JRSNAP の直接基礎（砂質土系）は{'・'.join(SANDY_SOILS)}だけに対応します"
                         f"（入力 {support.soil_type}）")
    # decision 63 (read as c, decision 80): a blank c is 0
    if support.cohesion is not None and support.cohesion.value != 0:
        raise InputError(f"{path}.粘着力_c: c = 0 または空欄が必要です（砂質土系の直接基礎は c = 0）")
    if support.unit_weight_submerged is None:
        raise InputError(f"{path}.単位体積重量.水中: 値が必要です（γ1）")
    b, l = (getattr(foundation, name) for name in profile.plan)
    assert support.friction_angle is not None  # required by parse_input
    return Footing(node=node, b=b, l=l, kv=foundation.short_term.kv, depth=embedment.depth,
                   gamma1=support.unit_weight_submerged, gamma2=embedment.unit_weight, phi=support.friction_angle)


def _case(number: int, action: Any, profile: Profile, elements: _Elements, regions: dict[int, Region]) -> LoadCase:
    members = []
    for line in action.line_loads:
        pedestal = all(regions[member] is Region.PEDESTAL for member in line.members)
        for element in (elements.first[member] for member in line.members):
            if line.n.value:
                members.append(MemberLoad(element, AXIAL, line.n, None,
                                          PEDESTAL_WEIGHT if pedestal else profile.member_labels[action.case]))
            if line.h.value:
                h = _negative(line.h)
                members.append(MemberLoad(element, LOCAL_Y, h, h, profile.member_labels[action.case]))
    for load in action.member_loads:
        start, end = (load.end, load.start) if elements.reversed[load.member] else (load.start, load.end)
        members.append(MemberLoad(elements.first[load.member], LOCAL_Y, _negative(start), _negative(end),
                                  profile.member_labels[action.case]))
    joints = []
    for point in sorted(action.points, key=lambda point: point.node):  # from the top, as JRSNAP numbers them
        if point.n.value or point.h.value or point.m.value:
            labels = profile.footing_labels if point.anchor is NodeRole.FOOTING_CENTROID else profile.seat_labels
            joints.append(JointLoad(point.node, point.h, point.n, point.m, labels[action.case]))
    if not members and not joints and action.points:
        # Decision 62: a case with no load (no snow) keeps one zero row where it acts. JRSNAP's 荷重図 leaves out a
        # case without rows and gives the next page its title (P7, 2026-10-20); its own NDT writes zeros the same way.
        point = action.points[0]
        labels = profile.footing_labels if point.anchor is NodeRole.FOOTING_CENTROID else profile.seat_labels
        joints.append(JointLoad(point.node, point.h, point.n, point.m, labels[action.case]))
    return LoadCase(number=number, title=profile.case_titles[action.case], increment=INCREMENTS[action.increment],
                    member_loads=tuple(members), joint_loads=tuple(joints))


def build_ndu(profile: Profile, pier: PierInput, foundation: FoundationResult, embedment: EmbedmentResult,
              layout: ColumnLayout, seismic: Any) -> NduModel:
    """*seismic* is a SeismicLongitudinalResult or a SeismicTransverseResult of the same input."""
    frame: Frame = seismic.frame
    top = frame.node(NodeRole.FOOTING_TOP)
    joints = {node.number: Joint(node.number, node.x, put(LENGTH, d(top.y) - d(node.y))) for node in frame.nodes}
    elements = _Elements(joints)
    for member in frame.members:
        elements.add(member)
    control = _control(frame, profile)
    section = column_section(profile, pier, layout, frame, control)
    support = frame.support
    springs = (Spring(support.node, HORIZONTAL, support.short_term.ks), Spring(support.node, VERTICAL,
                                                                                support.short_term.kv))
    regions = {member.number: member.region for member in frame.members}
    cases = tuple(_case(number, action, profile, elements, regions)
                  for number, action in enumerate(seismic.basic_cases, 1))
    order = [action.case for action in seismic.basic_cases]
    combinations = tuple(Combination(rho_m=c.rho_m, alpha_f=c.alpha_f,
                                     coefficients=tuple(int(case in c.cases) for case in order), reverse=c.reverse)
                         for c in seismic.combinations)
    return _from_the_upper_left(NduModel(
        profile=profile, analysis=_analysis(pier, profile), control=control.number, origin=top.number,
        joints=tuple(joints.values()), elements=tuple(elements.elements), section=section, springs=springs,
        footing=_footing(pier, foundation, embedment, profile, support.node), cases=cases, combinations=combinations))


def _from_the_upper_left(model: NduModel) -> NduModel:
    """Joints numbered from the top, left to right at one height (JRSNAP 5.2-L03 操作説明書 2.1.6): the frame is
    numbered so already, and the corner joint of an inclined rigid member takes its place among them. An element
    keeps i at its upper (or left) end, which is then the smaller number."""
    order = sorted(model.joints, key=lambda joint: (joint.y.value, joint.x.value))
    new = {joint.number: number for number, joint in enumerate(order, 1)}
    if all(old == number for old, number in new.items()):
        return model
    return replace(
        model, control=new[model.control], origin=new[model.origin],
        joints=tuple(replace(joint, number=new[joint.number]) for joint in order),
        elements=tuple(replace(e, i=new[e.i], j=new[e.j]) for e in model.elements),
        springs=tuple(replace(spring, node=new[spring.node]) for spring in model.springs),  # type: ignore[arg-type]
        footing=replace(model.footing, node=new[model.footing.node]),
        cases=tuple(replace(case, joint_loads=tuple(replace(load, node=new[load.node]) for load in case.joint_loads))
                    for case in model.cases))
