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
  the footing centroid H = V × (γ − γ') × Kh, γ' the displaced soil (the wet unit weight of the layers in
  the footing height, decision 64; Example2 表層).

The earthquake acts toward the origin side (← on 10-11/10-12), which is −x of
the frame; the tables keep the printed magnitudes, the frame loads the sign.
The one combination of the cases is made for each 照査パターン (ρm, αf), pushed
toward the earthquake (decision 76). No structural analysis is done here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from ..core.errors import InputError
from ..core.printed import FORCE, LENGTH, LINE_LOAD, MOMENT, Precision, Printed
from ..inputs import PierInput
from ._exact import d, put, total
from .embedment import Displaced, displaced_soil
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
CONSTANT = Precision(1, "")  # 10-12: αf, ρm
# Decision 76: the 照査パターン (ρm, αf) of every combination, a Case each in this order (Example2 10-12 has the first).
PATTERNS = tuple((CONSTANT.exact(rho_m), CONSTANT.exact(alpha_f)) for alpha_f in (1.0, 2.0) for rho_m in (1.0, 1.2))
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
    TOWARD_END = "toward_end"  # → along the track: a reversed (逆向) combination of a load model (decision 76)
    TOWARD_W9 = "toward_w9"  # → across the track (0720), +x of the transverse frame
    TOWARD_W1 = "toward_w1"  # ← across the track: a reversed (逆向) combination of 0720 (decision 76)


# The push of a reversed (逆向) combination: the incremental cases and the target displacement turn around.
REVERSED = {ActionDirection.TOWARD_ORIGIN: ActionDirection.TOWARD_END,
            ActionDirection.TOWARD_W9: ActionDirection.TOWARD_W1}


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
    displaced: Printed  # γ' of the displaced soil: the wet unit weight of the layers in the footing height
    soil: Displaced  # the layers of γ' (decision 64; Example2: 表層 alone)
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
    number: int  # 10-12 Case: the position among the cases made (decision 69)
    case: SeismicCase
    direction: ActionDirection
    increment: Increment
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...]  # uniform loads (the D1 column line)
    member_loads: tuple[MemberLoad, ...]  # horizontal self-weight inertia


@dataclass(frozen=True)
class SeismicCombination:
    """One combination of 10-12: every basic case once, with no printed factor, for one 照査パターン."""

    number: int
    alpha_f: Printed
    rho_m: Printed
    direction: ActionDirection  # of the push: toward the earthquake, or away from it when reversed
    cases: tuple[SeismicCase, ...]
    ground_resistance_type: int
    reverse: bool = False  # 逆向 (decision 76)


@dataclass(frozen=True)
class SeismicLongitudinalResult:
    frame: Frame  # 10-1 to 10-7
    fixed: FixedDead  # 0610 D1
    additional: AdditionalDead  # 0610 D2
    buoyancy: Row  # 0610 buoyancy at the normal water level
    snow: TopTable | None  # 0610 2-year snow; None without snow (decision 69)
    train: TopTable  # 10-8 (1): seismic train, one track
    girder_inertia: Inertia  # 10-8 (2) 1.0 EQ (桁荷重)
    train_inertia: Inertia  # 10-8 (2) 1.0 EQ (列車荷重)
    self_weight: SelfWeightInertia  # 10-8 (3)
    basic_cases: tuple[SeismicAction, ...]  # 10-9 to 10-12 (without snow, 7: decision 69)
    combinations: tuple[SeismicCombination, ...]  # 10-12

    def basic(self, case: SeismicCase) -> SeismicAction:
        return made(self.basic_cases, case)


def made(basic_cases: tuple[Any, ...], case: Enum) -> Any:
    """The action of *case* among the basic cases made; ``KeyError`` when it is not made (snow, decision 69)."""
    for action in basic_cases:
        if action.case is case:
            return action
    raise KeyError(case)


def _row(item: Item, n: Printed, arm: Printed) -> Row:
    return Row(item=item, n=n, arm=arm, m=put(MOMENT, d(n) * d(arm)))


def _intensity(along: Printed, across: Printed, unit_weight: Printed) -> Intensity:
    return Intensity(along=along, across=across, unit_weight=unit_weight, kh=PIER_KH,
                     value=put(LINE_LOAD, d(along) * d(across) * d(unit_weight) * d(PIER_KH)))


def self_weight_inertia(pier: PierInput, reaction: ReactionResult) -> SelfWeightInertia:
    """10-8 (3), and 11-8 (8) of 0720: the sizes b × w are the same in both directions."""
    s = pier.substructure
    b, w, gamma = s.b, s.w, s.unit_weight_body
    footing = reaction.self_weight.footing
    soil = displaced_soil(pier, reaction.self_weight.footing_height)
    displaced = soil.unit_weight
    if s.unit_weight_footing.value < displaced.value:  # decision 32; γ = γ' gives H = 0, a valid zero load
        source = "・".join(f"地盤データ.層[{layer.index}]" for layer, _ in soil.parts)
        raise InputError(f"下部構造.単位体積重量.フーチング（{s.unit_weight_footing.value} kN/m3）が "
                         f"{source}.単位体積重量.湿潤（排除した土 γ' {displaced.value} kN/m3）より小さく、"
                         "フーチングの慣性力 V×(γ−γ')×Kh が地震と逆向きになります")
    return SelfWeightInertia(
        kh=PIER_KH,
        beam_top=_intensity(b[1], w[1], gamma),
        beam_bottom=_intensity(put(LENGTH, d(b[1]) - d(b[4]) - d(b[5])), put(LENGTH, d(w[1]) - d(w[4]) - d(w[5])),
                               gamma),
        column=_intensity(b[6], w[6], gamma),
        pedestal=_intensity(b[3], w[3], gamma) if s.h[1].value > 0 else None,
        footing=FootingInertia(
            volume=footing.volume, unit_weight=s.unit_weight_footing, displaced=displaced, soil=soil, kh=PIER_KH,
            force=put(FORCE, d(footing.volume) * (d(s.unit_weight_footing) - d(displaced)) * d(PIER_KH))),
    )


def toward(value: Printed, earthquake: Decimal = EARTHQUAKE) -> Printed:
    """A printed magnitude as a frame component in the direction of the earthquake (±1, exact)."""
    return Printed(float(earthquake * d(value)), value.digits, value.unit)


def self_weight_loads(frame: Frame, inertia: SelfWeightInertia, earthquake: Decimal = EARTHQUAKE
                      ) -> tuple[MemberLoad, ...]:
    """Hw along the beam, the haunch (linear, decision 31), the column with its micro member and the pedestal."""
    top, bottom, column = (toward(i.value, earthquake) for i in (inertia.beam_top, inertia.beam_bottom,
                                                                 inertia.column))
    ends = {Region.BEAM: (top, top), Region.HAUNCH: (top, bottom), Region.COLUMN: (column, column),
            Region.COLUMN_BASE: (column, column)}
    if inertia.pedestal is not None:
        pedestal = toward(inertia.pedestal.value, earthquake)
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
    self_weight = self_weight_inertia(pier, reaction)

    vertical = {case: longitudinal.basic(basic) for case, basic in _FROM_0610.items()
                if case is not SeismicCase.SNOW or longitudinal.snow is not None}  # decision 69
    points: dict[SeismicCase, tuple[PointLoad, ...]] = {
        case: tuple(_on_frame(frame, p) for p in action.points) for case, action in vertical.items()}
    lines: dict[SeismicCase, tuple[LineLoad, ...]] = {
        case: tuple(column_line_load(frame, n=line.n, h=line.h) for line in action.line_loads)
        for case, action in vertical.items()}
    points[SeismicCase.TRAIN] = (bearing_point(frame, train.n, train.m),)
    points[SeismicCase.GIRDER_INERTIA] = (bearing_point(frame, FORCE(0), h=toward(girder.forces.total)),)
    points[SeismicCase.TRAIN_INERTIA] = (bearing_point(frame, FORCE(0), h=toward(train_inertia.forces.total)),)
    points[SeismicCase.SELF_INERTIA] = (
        point_load(frame, NodeRole.FOOTING_CENTROID, h=toward(self_weight.footing.force)),)
    basic_cases = tuple(
        SeismicAction(number=number, case=case, direction=_KINDS[case][0], increment=_KINDS[case][1],
                      points=points[case], line_loads=lines.get(case, ()),
                      member_loads=self_weight_loads(frame, self_weight) if case is SeismicCase.SELF_INERTIA else ())
        for number, case in enumerate((case for case in SeismicCase if case in points), 1))
    cases = tuple(action.case for action in basic_cases)
    combinations = tuple(
        SeismicCombination(number=number, alpha_f=alpha_f, rho_m=rho_m, direction=ActionDirection.TOWARD_ORIGIN,
                           cases=cases, ground_resistance_type=GROUND_RESISTANCE_TYPE)
        for number, (rho_m, alpha_f) in enumerate(PATTERNS, 1))
    return SeismicLongitudinalResult(
        frame=frame, fixed=longitudinal.fixed, additional=longitudinal.additional,
        buoyancy=longitudinal.buoyancy[1], snow=longitudinal.snow[0] if longitudinal.snow else None, train=train,
        girder_inertia=girder, train_inertia=train_inertia, self_weight=self_weight,
        basic_cases=basic_cases, combinations=combinations)


__all__ = [
    "PATTERNS", "REVERSED", "ActionDirection", "FootingInertia", "Increment", "Inertia", "Intensity", "MemberLoad",
    "SeismicAction",
    "SeismicCase", "SeismicCombination", "SeismicLongitudinalResult", "SelfWeightInertia",
    "calculate_seismic_longitudinal", "made", "self_weight_inertia", "self_weight_loads", "toward",
]
