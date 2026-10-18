"""The NDU model of a 0710 or 0720 result, by its profile (CONTEXT.md JRSNAP入力モデル).

- Joints: the frame nodes, y turned downward from the footing top (the origin, JointOrg).
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
  weight is an axial load. A load without a component has no row.
- Combinations: one per calc combination, coefficient 1 for its cases and 0 for the others.

Values come from the results as they are printed; nothing is recalculated.
"""

from __future__ import annotations

from typing import Any

from ...calc._exact import d, put
from ...calc.column_rebar import ColumnLayout
from ...calc.embedment import EmbedmentResult
from ...calc.foundation import FoundationResult
from ...calc.frame import Frame, Member, Node, NodeRole
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
    for node in frame.nodes:
        if profile.control <= node.roles:
            return node
    raise InputError("上部構造: 起点側と終点側の桁の高さ h1+h2 が異なり、制御節点と La が一つに定まりません（未対応）")


def _footing(pier: PierInput, foundation: FoundationResult, embedment: EmbedmentResult, profile: Profile,
             node: int) -> Footing:
    support = pier.soil.support
    path = f"地盤データ.層[{pier.soil.layers.index(support)}]"
    if support.soil_type not in SANDY_SOILS:
        raise InputError(f"{path}.土質区分: JRSNAP の直接基礎（砂質土系）は{'・'.join(SANDY_SOILS)}だけに対応します"
                         f"（入力 {support.soil_type}）")
    if support.compressive_strength is None or support.compressive_strength.value != 0:
        raise InputError(f"{path}.一軸圧縮強度_qu: qu = 0 が必要です（砂質土系の直接基礎は c = 0）")
    if support.unit_weight_submerged is None:
        raise InputError(f"{path}.単位体積重量.水中: 値が必要です（γ1）")
    b, l = (getattr(foundation, name) for name in profile.plan)
    assert support.friction_angle is not None  # required by parse_input
    return Footing(node=node, b=b, l=l, kv=foundation.short_term.kv, depth=embedment.depth,
                   gamma1=support.unit_weight_submerged, gamma2=embedment.unit_weight, phi=support.friction_angle)


def _case(number: int, action: Any, profile: Profile, elements: _Elements) -> LoadCase:
    members = []
    for line in action.line_loads:
        for element in (elements.first[member] for member in line.members):
            if line.n.value:
                members.append(MemberLoad(element, AXIAL, line.n, None, profile.member_labels[action.case]))
            if line.h.value:
                h = _negative(line.h)
                members.append(MemberLoad(element, LOCAL_Y, h, h, profile.member_labels[action.case]))
    for load in action.member_loads:
        start, end = (load.end, load.start) if elements.reversed[load.member] else (load.start, load.end)
        members.append(MemberLoad(elements.first[load.member], LOCAL_Y, _negative(start), _negative(end),
                                  profile.member_labels[action.case]))
    joints = []
    for point in action.points:
        if point.n.value or point.h.value or point.m.value:
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
    cases = tuple(_case(number, action, profile, elements) for number, action in enumerate(seismic.basic_cases, 1))
    order = [action.case for action in seismic.basic_cases]
    combinations = tuple(Combination(rho_m=c.rho_m, alpha_f=c.alpha_f,
                                     coefficients=tuple(int(case in c.cases) for case in order))
                         for c in seismic.combinations)
    return NduModel(profile=profile, analysis=_analysis(pier, profile), control=control.number, origin=top.number,
                    joints=tuple(joints.values()), elements=tuple(elements.elements), section=section, springs=springs,
                    footing=_footing(pier, foundation, embedment, profile, support.node), cases=cases,
                    combinations=combinations)
