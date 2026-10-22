"""0720 seismic transverse actions: Example2 11 pp.11-1 to 11-13.

The model is the transverse frame with the 0.010 m column-base micro member
(CONTEXT.md 柱下端の微小部材), the only member with a section (11-5), and the
girder level h1 + h2 of each side above the bearing seat (11-1 node 1, 2.750),
joined to the seat by a rigid member and loaded with nothing, with the control
node at the levels weighted by the girder inertia forces (decision 65). The frame keeps
the 0500 springs; no nonlinear constitutive data is made here.

The actions (11-8) are the 0620 D1, D2, buoyancy at the normal water level and
2-year snow, put on this frame ("§9 と同様"), and:

- the seismic train of each track, the 0600 R of the girder × the share of the
  bearing (up = L2, down = L1, decision 21), each bearing a row with its
  position from the column axis as the lever;
- the 0600 transverse forces of the girder inertia (Kh = 1.00, at the
  equivalent height hs) and the seismic train (Kh = 0.30, at the rail height +
  the seismic centroid), H at the bearing seat with M = Σ H × y (decision 29);
- the pier self-weight inertia of 0710 (the sizes b × w are the same across
  the track): Hw on the beam, haunch, column and pedestal, H = V × (γ − γ') × Kh
  at the footing centroid.

The earthquake acts in one direction, → (+x of the transverse frame, decision
30). Each track gets its own combination (decision 21) for each 照査パターン
(ρm, αf): the up track pushed toward the earthquake, the down track, on the
other side, reversed (逆向, decision 76). No structural analysis is done here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..core.printed import FORCE, MOMENT, Printed
from ..inputs import PierInput
from ._exact import put, total
from .foundation import FoundationResult
from .frame import Direction, Frame, LineLoad, NodeRole, PointLoad, Region, build_frame, column_line_load, point_load
from .longitudinal.actions import bearing_point
from .materials import calculate_materials
from .reaction import ReactionResult
from .reaction.transverse import SEISMIC_KH_GIRDER, SEISMIC_KH_TRAIN, TransverseForce
from .seismic_longitudinal import (
    GROUND_RESISTANCE_TYPE, KH, PATTERNS, REVERSED, ActionDirection, Increment, MemberLoad, SelfWeightInertia, made,
    self_weight_inertia, self_weight_loads, toward,
)
from .transverse import (
    AdditionalDead, BasicCase, FixedDead, HorizontalRow, Item, Row, TopTable, Track, TrainTable, TransverseResult,
)
from .transverse.actions import train_table

EARTHQUAKE = Decimal(1)  # → of 11-12 and 11-13, +x in the transverse frame (decision 30)


class SeismicCase(Enum):
    """The 9 basic cases of 11-13, by number."""

    D1 = 1
    D2 = 2
    BUOYANCY = 3  # Wp, normal water level
    SNOW = 4  # Sw2
    TRAIN_UP = 5  # L, up track (11-8, 11-11; 11-13 prints the names of 5 and 6 swapped)
    TRAIN_DOWN = 6  # L, down track
    GIRDER_INERTIA = 7  # EQ1
    TRAIN_INERTIA = 8  # EQL
    SELF_INERTIA = 9  # EQ2


TRAIN_CASES = {SeismicCase.TRAIN_UP: Track.UP, SeismicCase.TRAIN_DOWN: Track.DOWN}
# 11-8: the vertical cases are those of §9 (0620).
_FROM_0620 = {SeismicCase.D1: BasicCase.D1, SeismicCase.D2: BasicCase.D2,
              SeismicCase.BUOYANCY: BasicCase.BUOYANCY_NORMAL, SeismicCase.SNOW: BasicCase.SNOW2}
# 11-13 作用方向 and 荷重種別.
_KINDS = {
    SeismicCase.D1: (ActionDirection.DOWNWARD, Increment.FIXED),
    SeismicCase.D2: (ActionDirection.DOWNWARD, Increment.FIXED),
    SeismicCase.BUOYANCY: (ActionDirection.UPWARD, Increment.FIXED),
    SeismicCase.SNOW: (ActionDirection.DOWNWARD, Increment.FIXED),
    SeismicCase.TRAIN_UP: (ActionDirection.DOWNWARD, Increment.FIXED),
    SeismicCase.TRAIN_DOWN: (ActionDirection.DOWNWARD, Increment.FIXED),
    SeismicCase.GIRDER_INERTIA: (ActionDirection.TOWARD_W9, Increment.INCREMENTAL),
    SeismicCase.TRAIN_INERTIA: (ActionDirection.TOWARD_W9, Increment.LIMITED),
    SeismicCase.SELF_INERTIA: (ActionDirection.TOWARD_W9, Increment.INCREMENTAL),
}


@dataclass(frozen=True)
class HorizontalInertia:
    """Bearing forces of one seismic case across the track (11-8 (6), (7)), as computed by 0600."""

    kh: Printed  # printed in the case name: 1.00 girder, 0.30 train (already applied in 0600)
    rows: tuple[HorizontalRow, HorizontalRow]  # B and C: H at the height y above the seat, M = H × y
    h: Printed  # Σ H
    m: Printed  # Σ M of the rows


@dataclass(frozen=True)
class SeismicAction:
    number: int  # 11-13 Case: the position among the cases made (decision 69)
    case: SeismicCase
    direction: ActionDirection
    increment: Increment
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...]  # uniform loads (the D1 column line)
    member_loads: tuple[MemberLoad, ...]  # horizontal self-weight inertia

    @property
    def track(self) -> Track | None:
        return TRAIN_CASES.get(self.case)


@dataclass(frozen=True)
class SeismicCombination:
    """One combination of 11-13: the basic cases once each, with no printed factor, for one track and one
    照査パターン."""

    number: int
    track: Track
    alpha_f: Printed
    rho_m: Printed
    direction: ActionDirection  # of the push: → for the up track, ← for the reversed down track
    cases: tuple[SeismicCase, ...]
    ground_resistance_type: int
    reverse: bool = False  # 逆向 (decision 76): the down track


@dataclass(frozen=True)
class SeismicTransverseResult:
    frame: Frame  # 11-1 to 11-7
    fixed: FixedDead  # 0620 D1
    additional: AdditionalDead  # 0620 D2
    buoyancy: Row  # 0620 buoyancy at the normal water level
    snow: TopTable | None  # 0620 2-year snow; None without snow (decision 69)
    train_up: TrainTable  # 11-8 (5) 上り線載荷 (L2)
    train_down: TrainTable  # 11-8 (5) 下り線載荷 (L1)
    girder_inertia: HorizontalInertia  # 11-8 (6)
    train_inertia: HorizontalInertia  # 11-8 (7)
    self_weight: SelfWeightInertia  # 11-8 (8)
    basic_cases: tuple[SeismicAction, ...]  # 11-10 to 11-13
    combinations: tuple[SeismicCombination, ...]  # 11-13: up, then down, each by 照査パターン

    def basic(self, case: SeismicCase) -> SeismicAction:
        return made(self.basic_cases, case)

    def train(self, track: Track) -> TrainTable:
        return {Track.UP: self.train_up, Track.DOWN: self.train_down}[track]


def _inertia(kh: Decimal, origin: TransverseForce, end: TransverseForce) -> HorizontalInertia:
    rows = (HorizontalRow(Item.ORIGIN, origin.force, origin.height, origin.moment),
            HorizontalRow(Item.END, end.force, end.height, end.moment))
    return HorizontalInertia(kh=put(KH, kh), rows=rows, h=put(FORCE, total(r.h for r in rows)),
                             m=put(MOMENT, total(r.m for r in rows)))


def _on_frame(frame: Frame, point: PointLoad) -> PointLoad:
    """A 0620 point load at the same role of this frame (the node numbers differ)."""
    return point_load(frame, point.anchor, n=point.n, h=point.h, m=point.m)


def _seat(frame: Frame, inertia: HorizontalInertia) -> PointLoad:
    return bearing_point(frame, FORCE(0), toward(inertia.m, EARTHQUAKE), toward(inertia.h, EARTHQUAKE))


def calculate_seismic_transverse(pier: PierInput, foundation: FoundationResult, reaction: ReactionResult,
                                 transverse: TransverseResult) -> SeismicTransverseResult:
    sides = reaction.transverse.origin, reaction.transverse.end
    frame = build_frame(pier, reaction.self_weight, foundation, calculate_materials(pier), Direction.TRANSVERSE,
                        column_base_micro_member=True, elastic_regions={Region.COLUMN_BASE},
                        girder_levels=(sides[0].seismic_girder.force, sides[1].seismic_girder.force))
    dead, seismic = reaction.dead, reaction.train.seismic
    girders = ((Item.ORIGIN, dead.origin.bearings), (Item.END, dead.end.bearings))
    reactions = {Item.ORIGIN: seismic.origin, Item.END: seismic.end}
    trains = {track: train_table(track, girders, reactions) for track in TRAIN_CASES.values()}
    girder = _inertia(SEISMIC_KH_GIRDER, sides[0].seismic_girder, sides[1].seismic_girder)
    train_inertia = _inertia(SEISMIC_KH_TRAIN, sides[0].seismic_train, sides[1].seismic_train)
    self_weight = self_weight_inertia(pier, reaction)

    vertical = {case: transverse.basic(basic) for case, basic in _FROM_0620.items()
                if case is not SeismicCase.SNOW or transverse.snow is not None}  # decision 69
    points: dict[SeismicCase, tuple[PointLoad, ...]] = {
        case: tuple(_on_frame(frame, p) for p in action.points) for case, action in vertical.items()}
    lines: dict[SeismicCase, tuple[LineLoad, ...]] = {
        case: tuple(column_line_load(frame, n=line.n, h=line.h) for line in action.line_loads)
        for case, action in vertical.items()}
    for case, track in TRAIN_CASES.items():
        points[case] = (bearing_point(frame, trains[track].n, trains[track].m),)
    points[SeismicCase.GIRDER_INERTIA] = (_seat(frame, girder),)
    points[SeismicCase.TRAIN_INERTIA] = (_seat(frame, train_inertia),)
    points[SeismicCase.SELF_INERTIA] = (
        point_load(frame, NodeRole.FOOTING_CENTROID, h=toward(self_weight.footing.force, EARTHQUAKE)),)
    basic_cases = tuple(
        SeismicAction(number=number, case=case, direction=_KINDS[case][0], increment=_KINDS[case][1],
                      points=points[case], line_loads=lines.get(case, ()),
                      member_loads=(self_weight_loads(frame, self_weight, EARTHQUAKE)
                                    if case is SeismicCase.SELF_INERTIA else ()))
        for number, case in enumerate((case for case in SeismicCase if case in points), 1))
    tracks = [(track, track is Track.DOWN) for track in TRAIN_CASES.values()]
    combinations = tuple(
        SeismicCombination(number=number, track=track, alpha_f=alpha_f, rho_m=rho_m,
                           direction=REVERSED[ActionDirection.TOWARD_W9] if reverse else ActionDirection.TOWARD_W9,
                           cases=tuple(a.case for a in basic_cases if TRAIN_CASES.get(a.case, track) is track),
                           ground_resistance_type=GROUND_RESISTANCE_TYPE, reverse=reverse)
        for number, ((track, reverse), (rho_m, alpha_f)) in enumerate(
            ((side, pattern) for side in tracks for pattern in PATTERNS), 1))
    return SeismicTransverseResult(
        frame=frame, fixed=transverse.fixed, additional=transverse.additional, buoyancy=transverse.buoyancy[1],
        snow=transverse.snow[0] if transverse.snow else None, train_up=trains[Track.UP], train_down=trains[Track.DOWN],
        girder_inertia=girder, train_inertia=train_inertia, self_weight=self_weight,
        basic_cases=basic_cases, combinations=combinations)


__all__ = [
    "EARTHQUAKE", "TRAIN_CASES", "HorizontalInertia", "SeismicAction", "SeismicCase", "SeismicCombination",
    "SeismicTransverseResult", "calculate_seismic_transverse",
]
