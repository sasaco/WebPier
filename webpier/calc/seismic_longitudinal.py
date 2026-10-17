"""0710 seismic longitudinal actions: Example2 10 pp.10-1 to 10-12.

The model is the longitudinal frame with the 0.010 m column-base micro member
(CONTEXT.md 柱下端の微小部材): only the micro member has a section; the beam,
haunch, column, footing (and pedestal) are rigid (10-5). The frame keeps the
0500 springs like every frame; no nonlinear constitutive data is made here.

The actions (10-8) are the 0610 D1, D2, buoyancy at the normal water level and
2-year snow, put on this frame ("§8 と同様"), and:

- the seismic train of one track, R = e × L / 2 of 0600 at the lever −f / +f;
- the 0600 bearing forces of the girder inertia (Kh = 1.00) and the seismic
  train (× 0.20), as H at the bearing seat with M = 0 (decision 10, 29);
- the pier self-weight inertia with Kh = 1.00: Hw = b × w × γ × Kh per metre
  for the beam top, the haunch bottom, the column (and the pedestal), and at
  the footing centroid H = V × (γ − γ') × Kh, γ' the displaced soil (表層の湿潤).

The earthquake acts toward the origin side (← on 10-11/10-12), which is −x of
the frame; the tables keep the printed magnitudes, the frame loads the sign.
No structural analysis is done here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..core.printed import FORCE, LENGTH, LINE_LOAD, MOMENT, Precision, Printed
from ..inputs import PierInput
from ._exact import d, put, total
from .foundation import FoundationResult
from .frame import (
    Direction, Frame, LineLoad, NodeRole, PointLoad, Region, build_frame, column_line_load, point_load,
)
from .longitudinal import BasicCase, LongitudinalResult
from .longitudinal.actions import AdditionalDead, FixedDead, Item, Row, TopTable, bearing_point
from .materials import calculate_materials
from .reaction import ReactionResult
from .reaction.longitudinal import ADHESION, SEISMIC_KH, SeismicForces

KH = Precision(2, "")  # seismic coefficients as printed (10-8, 10-11: Kh=1.00, Kh=0.20)
PIER_KH = KH.exact(1.00)  # self-weight inertia, a unit coefficient for the incremental analysis (10-8 (3))
CONSTANT = Precision(1, "")  # 10-12: αf = 1.0, ρm = 1.0
ALPHA_F = CONSTANT.exact(1.0)
RHO_M = CONSTANT.exact(1.0)
GROUND_RESISTANCE_TYPE = 1  # 10-12 地盤抵抗TYPE
EARTHQUAKE = Decimal(-1)  # toward the origin side: ← of 10-11 and 10-12, −x in the frame


class SeismicCase(Enum):
    """The 8 basic cases of 10-12, by number."""

    D1 = 1
    D2 = 2
    BUOYANCY = 3  # Wp, normal water level
    SNOW = 4  # Sw2
    TRAIN = 5  # L, seismic train
    GIRDER_INERTIA = 6  # EQ1
    TRAIN_INERTIA = 7  # EQL
    SELF_INERTIA = 8  # EQ2


class ActionDirection(Enum):
    DOWNWARD = "downward"  # ↓
    UPWARD = "upward"  # ↑
    TOWARD_ORIGIN = "toward_origin"  # ←


class Increment(Enum):
    """How the incremental analysis treats a basic case (10-12 荷重種別)."""

    FIXED = "fixed"  # 固定
    INCREMENTAL = "incremental"  # 増分
    LIMITED = "limited_incremental"  # 限定増分


# 10-8: the vertical cases are those of §8 (0610).
_FROM_0610 = {SeismicCase.D1: BasicCase.D1, SeismicCase.D2: BasicCase.D2,
              SeismicCase.BUOYANCY: BasicCase.BUOYANCY_NORMAL, SeismicCase.SNOW: BasicCase.SNOW2}
# 10-12 作用方向 and 荷重種別.
_KINDS = {
    SeismicCase.D1: (ActionDirection.DOWNWARD, Increment.FIXED),
    SeismicCase.D2: (ActionDirection.DOWNWARD, Increment.FIXED),
    SeismicCase.BUOYANCY: (ActionDirection.UPWARD, Increment.FIXED),
    SeismicCase.SNOW: (ActionDirection.DOWNWARD, Increment.FIXED),
    SeismicCase.TRAIN: (ActionDirection.DOWNWARD, Increment.FIXED),
    SeismicCase.GIRDER_INERTIA: (ActionDirection.TOWARD_ORIGIN, Increment.INCREMENTAL),
    SeismicCase.TRAIN_INERTIA: (ActionDirection.TOWARD_ORIGIN, Increment.LIMITED),
    SeismicCase.SELF_INERTIA: (ActionDirection.TOWARD_ORIGIN, Increment.INCREMENTAL),
}


@dataclass(frozen=True)
class Inertia:
    """Bearing horizontal forces of one seismic case (10-8 (2)), as computed by 0600."""

    kh: Printed  # printed in the case name: 1.00 girder, 0.20 train (already applied in 0600)
    forces: SeismicForces  # origin (B), end (C) and total


@dataclass(frozen=True)
class Intensity:
    """Self-weight inertia per metre of one part: Hw = b × w × γ × Kh (10-8 (3))."""

    along: Printed  # size along the track (B)
    across: Printed  # size across the track (W)
    unit_weight: Printed
    kh: Printed
    value: Printed  # kN/m


@dataclass(frozen=True)
class FootingInertia:
    """H = V × (γ − γ') × Kh at the footing centroid (10-8 (3))."""

    volume: Printed  # 0600 footing volume
    unit_weight: Printed  # γ of the footing
    displaced: Printed  # γ' of the displaced soil: wet unit weight of 表層
    kh: Printed
    force: Printed


@dataclass(frozen=True)
class SelfWeightInertia:
    kh: Printed
    beam_top: Intensity  # Hw1: B1 × W1
    beam_bottom: Intensity  # haunch bottom: (B1 − B4 − B5) × (W1 − W4 − W5)
    column: Intensity  # Hw2 (Hw3 on 10-8): B6 × W6
    pedestal: Intensity | None  # B3 × W3; None without a pedestal (H1 = 0)
    footing: FootingInertia


@dataclass(frozen=True)
class MemberLoad:
    """A horizontal load along one member, linear from its start to its end node, per metre in +x."""

    member: int
    start: Printed
    end: Printed


@dataclass(frozen=True)
class SeismicAction:
    case: SeismicCase
    direction: ActionDirection
    increment: Increment
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...]  # uniform loads (the D1 column line)
    member_loads: tuple[MemberLoad, ...]  # horizontal self-weight inertia


@dataclass(frozen=True)
class SeismicCombination:
    """One combination of 10-12: every basic case once, with no printed factor."""

    number: int
    alpha_f: Printed
    rho_m: Printed
    direction: ActionDirection
    cases: tuple[SeismicCase, ...]
    ground_resistance_type: int


@dataclass(frozen=True)
class SeismicLongitudinalResult:
    frame: Frame  # 10-1 to 10-7
    fixed: FixedDead  # 0610 D1
    additional: AdditionalDead  # 0610 D2
    buoyancy: Row  # 0610 buoyancy at the normal water level
    snow: TopTable  # 0610 2-year snow
    train: TopTable  # 10-8 (1): seismic train, one track
    girder_inertia: Inertia  # 10-8 (2) 1.0 EQ (桁荷重)
    train_inertia: Inertia  # 10-8 (2) 1.0 EQ (列車荷重)
    self_weight: SelfWeightInertia  # 10-8 (3)
    basic_cases: tuple[SeismicAction, ...]  # 10-9 to 10-12
    combinations: tuple[SeismicCombination, ...]  # 10-12

    def basic(self, case: SeismicCase) -> SeismicAction:
        return self.basic_cases[case.value - 1]


def _row(item: Item, n: Printed, arm: Printed) -> Row:
    return Row(item=item, n=n, arm=arm, m=put(MOMENT, d(n) * d(arm)))


def _intensity(along: Printed, across: Printed, unit_weight: Printed) -> Intensity:
    return Intensity(along=along, across=across, unit_weight=unit_weight, kh=PIER_KH,
                     value=put(LINE_LOAD, d(along) * d(across) * d(unit_weight) * d(PIER_KH)))


def _self_weight(pier: PierInput, reaction: ReactionResult) -> SelfWeightInertia:
    s = pier.substructure
    b, w, gamma = s.b, s.w, s.unit_weight_body
    footing = reaction.self_weight.footing
    displaced = pier.soil.surface.unit_weight_wet
    assert displaced is not None  # required by parse_input
    return SelfWeightInertia(
        kh=PIER_KH,
        beam_top=_intensity(b[1], w[1], gamma),
        beam_bottom=_intensity(put(LENGTH, d(b[1]) - d(b[4]) - d(b[5])), put(LENGTH, d(w[1]) - d(w[4]) - d(w[5])),
                               gamma),
        column=_intensity(b[6], w[6], gamma),
        pedestal=_intensity(b[3], w[3], gamma) if s.h[1].value > 0 else None,
        footing=FootingInertia(
            volume=footing.volume, unit_weight=s.unit_weight_footing, displaced=displaced, kh=PIER_KH,
            force=put(FORCE, d(footing.volume) * (d(s.unit_weight_footing) - d(displaced)) * d(PIER_KH))),
    )


def _toward(value: Printed) -> Printed:
    """A printed magnitude as a frame component in the direction of the earthquake (exact)."""
    return Printed(float(EARTHQUAKE * d(value)), value.digits, value.unit)


def _member_loads(frame: Frame, inertia: SelfWeightInertia) -> tuple[MemberLoad, ...]:
    top, bottom, column = (_toward(i.value) for i in (inertia.beam_top, inertia.beam_bottom, inertia.column))
    ends = {Region.BEAM: (top, top), Region.HAUNCH: (top, bottom), Region.COLUMN: (column, column),
            Region.COLUMN_BASE: (column, column)}
    if inertia.pedestal is not None:
        pedestal = _toward(inertia.pedestal.value)
        ends[Region.PEDESTAL] = (pedestal, pedestal)
    return tuple(MemberLoad(member=m.number, start=ends[m.region][0], end=ends[m.region][1])
                 for m in frame.members if m.region in ends)


def _on_frame(frame: Frame, point: PointLoad) -> PointLoad:
    """A 0610 point load at the same role of this frame (the node numbers differ)."""
    return point_load(frame, point.anchor, n=point.n, h=point.h, m=point.m)


def calculate_seismic_longitudinal(pier: PierInput, foundation: FoundationResult, reaction: ReactionResult,
                                   longitudinal: LongitudinalResult) -> SeismicLongitudinalResult:
    frame = build_frame(pier, reaction.self_weight, foundation, calculate_materials(pier), Direction.LONGITUDINAL,
                        column_base_micro_member=True, elastic_regions={Region.COLUMN_BASE})
    spans, seismic = pier.spans, reaction.train.seismic
    rows = (_row(Item.ORIGIN, seismic.origin, put(LENGTH, -d(spans.origin.f))),
            _row(Item.END, seismic.end, spans.end.f))
    train = TopTable(rows=rows, n=put(FORCE, total(row.n for row in rows)), m=put(MOMENT, total(row.m for row in rows)))
    girder = Inertia(kh=put(KH, SEISMIC_KH), forces=reaction.longitudinal.seismic_girder)
    train_inertia = Inertia(kh=put(KH, ADHESION), forces=reaction.longitudinal.seismic_train)
    self_weight = _self_weight(pier, reaction)

    points: dict[SeismicCase, tuple[PointLoad, ...]] = {
        case: tuple(_on_frame(frame, p) for p in longitudinal.basic(basic).points)
        for case, basic in _FROM_0610.items()}
    lines: dict[SeismicCase, tuple[LineLoad, ...]] = {
        case: tuple(column_line_load(frame, n=line.n, h=line.h) for line in longitudinal.basic(basic).line_loads)
        for case, basic in _FROM_0610.items()}
    points[SeismicCase.TRAIN] = (bearing_point(frame, train.n, train.m),)
    points[SeismicCase.GIRDER_INERTIA] = (bearing_point(frame, FORCE(0), h=_toward(girder.forces.total)),)
    points[SeismicCase.TRAIN_INERTIA] = (bearing_point(frame, FORCE(0), h=_toward(train_inertia.forces.total)),)
    points[SeismicCase.SELF_INERTIA] = (
        point_load(frame, NodeRole.FOOTING_CENTROID, h=_toward(self_weight.footing.force)),)
    basic_cases = tuple(
        SeismicAction(case=case, direction=_KINDS[case][0], increment=_KINDS[case][1], points=points[case],
                      line_loads=lines.get(case, ()),
                      member_loads=_member_loads(frame, self_weight) if case is SeismicCase.SELF_INERTIA else ())
        for case in SeismicCase)
    combination = SeismicCombination(number=1, alpha_f=ALPHA_F, rho_m=RHO_M, direction=ActionDirection.TOWARD_ORIGIN,
                                     cases=tuple(SeismicCase), ground_resistance_type=GROUND_RESISTANCE_TYPE)
    return SeismicLongitudinalResult(
        frame=frame, fixed=longitudinal.fixed, additional=longitudinal.additional,
        buoyancy=longitudinal.buoyancy[1], snow=longitudinal.snow[0], train=train,
        girder_inertia=girder, train_inertia=train_inertia, self_weight=self_weight,
        basic_cases=basic_cases, combinations=(combination,))


__all__ = [
    "ActionDirection", "FootingInertia", "Increment", "Inertia", "Intensity", "MemberLoad", "SeismicAction",
    "SeismicCase", "SeismicCombination", "SeismicLongitudinalResult", "SelfWeightInertia",
    "calculate_seismic_longitudinal",
]
