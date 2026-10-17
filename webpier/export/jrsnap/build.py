"""The NDU model of a 0710 or 0720 result, by its profile (CONTEXT.md JRSNAP入力モデル).

- Joints: the frame nodes, y turned downward from the footing top (the origin, JointOrg).
- Elements: one per frame member, i at the upper (or left) end; the micro member is the automatic M-θ element,
  every other member a rigid region. Only vertical and horizontal members are supported.
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
    AXIAL, LOCAL_Y, Combination, Element, Footing, Joint, JointLoad, LoadCase, MemberLoad, NduModel, Spring,
)
from .profile import REGION_TITLES, SANDY_SOILS, Profile
from .section import column_section

INCREMENTS = {Increment.FIXED: 0, Increment.INCREMENTAL: 1, Increment.LIMITED: 4}
HORIZONTAL, VERTICAL = 1, 2


def _negative(value: Printed) -> Printed:
    return Printed(-value.value, value.digits, value.unit)


def _element(member: Member, joints: dict[int, Joint]) -> tuple[Element, bool]:
    """The element of a member and whether its ends are reversed (i is the upper, or left, end)."""
    start, end = joints[member.start], joints[member.end]
    if start.x != end.x and start.y != end.y:
        raise InputError(f"骨組の部材{member.number}（{REGION_TITLES[member.region]}）が斜めです。"
                         "JRSNAP 出力は鉛直・水平の部材だけに対応します（非対称なフーチングなど）")
    first, second = sorted((start, end), key=lambda joint: (joint.y.value, joint.x.value))
    length = put(LENGTH, d(member.height) + abs(d(member.offset)))  # one of the two is zero
    element = Element(number=member.number, i=first.number, j=second.number, length=length,
                      nonlinear=not member.rigid, title=REGION_TITLES[member.region])
    return element, first is not start


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


def _case(number: int, action: Any, profile: Profile, reversed_ends: dict[int, bool]) -> LoadCase:
    members = []
    for line in action.line_loads:
        for element in line.members:
            if line.n.value:
                members.append(MemberLoad(element, AXIAL, line.n, None, profile.member_labels[action.case]))
            if line.h.value:
                h = _negative(line.h)
                members.append(MemberLoad(element, LOCAL_Y, h, h, profile.member_labels[action.case]))
    for load in action.member_loads:
        start, end = (load.end, load.start) if reversed_ends[load.member] else (load.start, load.end)
        members.append(MemberLoad(load.member, LOCAL_Y, _negative(start), _negative(end),
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
    built = [_element(member, joints) for member in frame.members]
    reversed_ends = {element.number: flipped for element, flipped in built}
    control = _control(frame, profile)
    section = column_section(profile, pier, layout, frame, control)
    support = frame.support
    springs = (Spring(support.node, HORIZONTAL, support.short_term.ks), Spring(support.node, VERTICAL,
                                                                                support.short_term.kv))
    cases = tuple(_case(number, action, profile, reversed_ends) for number, action in enumerate(seismic.basic_cases, 1))
    order = [action.case for action in seismic.basic_cases]
    combinations = tuple(Combination(rho_m=c.rho_m, alpha_f=c.alpha_f,
                                     coefficients=tuple(int(case in c.cases) for case in order))
                         for c in seismic.combinations)
    return NduModel(profile=profile, control=control.number, origin=top.number, joints=tuple(joints.values()),
                    elements=tuple(element for element, _ in built), section=section, springs=springs,
                    footing=_footing(pier, foundation, embedment, profile, support.node), cases=cases,
                    combinations=combinations)
