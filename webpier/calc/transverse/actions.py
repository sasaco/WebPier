"""0620 basic actions on the transverse frame (Example2 09 pp.9-3 to 9-13).

Every action is computed from the printed 0600 and input values (decision 2).
Each bearing of B (origin girder) and C (end girder) is a row of its own with
its entered position across the track as the lever from the column axis; the
loads act at the bearing seat, the beam top or, with a pedestal, the pedestal
top (decision 29), where their moment is taken about the seat. The 0600 pier
parts act at the beam top with their own centroids xC; footing, soil and water
act at the footing centroid with the lever from the footing centre. Tables
print N and M to 2 decimals and the lever to 3; every moment is N × lever of
its own row and every total is the sum of the printed rows (ADR-0003).

Tracks: up = L2, down = L1, double = L1 + L2 (Example2 9-5, consistent with
11-8 and decision 21). The train is the 0600 reaction of one track without ρf
times the share of the bearing; the impact is that train load times the girder
impact coefficient as it is (decision 26). The horizontal actions are the 0600
transverse forces at B and C: vehicle lateral, and wind with and without the
train together with the wind on the pier body (decision 12, ``wind``).

On a curve (R ≠ 0 on a side, decision 33) the centrifugal load is a basic case
per track like the train (cases 18-20; none on a straight track): the train
load of the track at the side (its 9-5 rows) times the 0600 α, at the 0600
centrifugal height above the seat. The 0600 centrifugal forces already carry
ρf, so they are not used here: ρ comes once, from the coefficient of L.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ...core.printed import FORCE, LENGTH, LINE_LOAD, MOMENT, Printed
from ...inputs import PierInput
from .._exact import d, put, total
from ..frame import Frame, LineLoad, NodeRole, PointLoad, column_line_load, point_load
from ..longitudinal.actions import SpringTerm, bearing_point
from ..reaction import ReactionResult
from ..reaction.dead import BearingLoads
from ..reaction.self_weight import Body
from ..reaction.train import GirderImpact, GroupTrain
from ..reaction.transverse import WIND_WITH_TRAIN, WIND_WITHOUT_TRAIN, TransverseForce, TransverseSide
from .wind import MemberLoad, PierWind, pier_wind


class Item(Enum):
    ORIGIN = "origin"  # a bearing of RB, the origin girder on this pier
    END = "end"  # a bearing of RC, the end girder on this pier
    PEDESTAL = "pedestal"  # 桁受け (0600)
    BEAM = "beam"  # はり: prism and haunch (0600)
    FOOTING = "footing"
    OVERBURDEN = "overburden"
    WATER = "water"


class Track(Enum):
    UP = "up"  # 上り線: share L2
    DOWN = "down"  # 下り線: share L1
    DOUBLE = "double"  # 複線: L1 + L2


@dataclass(frozen=True)
class Row:
    item: Item
    slot: int | None  # input slot (0..9) of a bearing; None for the pier parts
    n: Printed  # vertical force, downward positive
    arm: Printed  # lever across the track, +x toward W9
    m: Printed  # N × arm


@dataclass(frozen=True)
class TopTable:
    """Loads at the beam top, one row per bearing and pier part (9-3, 9-4)."""

    rows: tuple[Row, ...]
    n: Printed  # Σ N
    m: Printed  # Σ M

    def bearings(self, item: Item) -> tuple[Row, ...]:
        return tuple(row for row in self.rows if row.item is item)

    def row(self, item: Item) -> Row:
        return next(row for row in self.rows if row.item is item)


@dataclass(frozen=True)
class FixedDead:
    """D1 (9-3): bearings, pedestal and beam at the beam top, the column as a line load, the footing at its centroid."""

    table: TopTable  # bearings of RB and RC, pedestal (H1 > 0), beam
    column_q: Printed  # q = W6 × B6 × γ, over the column line from the beam top to the footing top
    overlap: Printed  # H2 + H3: where q runs through the beam already weighed in the table
    n: Printed  # N = Σ N − q × (H2 + H3)
    m: Printed  # Σ M
    footing: Row  # W3 at the footing centroid


@dataclass(frozen=True)
class AdditionalDead:
    """D2 (9-3): bearing loads at the beam top, the overburden soil at the footing centroid."""

    table: TopTable
    soil: Row


@dataclass(frozen=True)
class TrainRow:
    item: Item
    slot: int
    reaction: Printed  # 0600 reaction RB or RC of one track, without ρf (07 7-1)
    share: Printed  # L2 (up), L1 (down) or L1 + L2 (double) of the bearing
    n: Printed  # reaction × share
    arm: Printed  # bearing position
    m: Printed  # N × arm


@dataclass(frozen=True)
class TrainTable:
    """Train load per bearing without load factors (9-5)."""

    track: Track
    rows: tuple[TrainRow, ...]
    n: Printed
    m: Printed


@dataclass(frozen=True)
class Trains:
    up: TrainTable
    down: TrainTable
    double: TrainTable

    def table(self, track: Track) -> TrainTable:
        return {Track.UP: self.up, Track.DOWN: self.down, Track.DOUBLE: self.double}[track]


@dataclass(frozen=True)
class ImpactRow:
    item: Item
    slot: int
    train: Printed  # train load of the bearing (9-5)
    coefficient: Printed  # 0600 girder impact coefficient (07 7-2)
    n: Printed  # train × coefficient
    arm: Printed
    m: Printed


@dataclass(frozen=True)
class ImpactTable:
    track: Track
    rows: tuple[ImpactRow, ...]
    n: Printed
    m: Printed


@dataclass(frozen=True)
class ImpactSet:
    up: ImpactTable
    down: ImpactTable
    double: ImpactTable

    def table(self, track: Track) -> ImpactTable:
        return {Track.UP: self.up, Track.DOWN: self.down, Track.DOUBLE: self.double}[track]


@dataclass(frozen=True)
class Impacts:
    """Impact with the girder coefficients as they are (decision 26, Example2 9-6)."""

    ultimate: ImpactSet  # safety and restorability coefficients: basic cases 12-14
    service: ImpactSet  # serviceability coefficients, 0.75 i (07 7-2)


@dataclass(frozen=True)
class CentrifugalRow:
    item: Item  # ORIGIN (B) or END (C)
    train: Printed  # Σ N of the side's rows of the train table of the track, without ρf
    coefficient: Printed  # α = V² / (127 R) of the side (0600), 0 on a straight side
    h: Printed  # train × α
    y: Printed  # 0600 centrifugal height above the bearing seat
    m: Printed  # H × y


@dataclass(frozen=True)
class CentrifugalTable:
    track: Track
    rows: tuple[CentrifugalRow, CentrifugalRow]  # B and C
    h: Printed
    m: Printed


@dataclass(frozen=True)
class Centrifugals:
    up: CentrifugalTable
    down: CentrifugalTable
    double: CentrifugalTable

    def table(self, track: Track) -> CentrifugalTable:
        return {Track.UP: self.up, Track.DOWN: self.down, Track.DOUBLE: self.double}[track]


@dataclass(frozen=True)
class HorizontalRow:
    """A 0600 transverse force at B or C: H at the height y above the bearing seat."""

    item: Item  # ORIGIN (B) or END (C)
    h: Printed
    y: Printed
    m: Printed  # H × y (0600)


@dataclass(frozen=True)
class Lateral:
    """Vehicle lateral load (9-7)."""

    origin: HorizontalRow
    end: HorizontalRow
    h: Printed  # H_B + H_C
    m: Printed  # H_B × y_B + H_C × y_C, the printed one-line expression rounded once


@dataclass(frozen=True)
class Wind:
    """Wind with or without the train (9-7, 9-8): the girders at the seat and the pier body."""

    pressure: Printed  # ω1
    rows: tuple[HorizontalRow, HorizontalRow]  # B and C
    h: Printed  # Σ H
    m: Printed  # Σ M of the rows
    pier: PierWind  # line loads on the beam, haunch and column (decision 12)


class BasicCase(Enum):
    """The 17 basic cases of 9-13, by number."""

    D1 = 1
    D2 = 2
    BUOYANCY_HIGH = 3
    BUOYANCY_NORMAL = 4
    BUOYANCY_LOW = 5
    SNOW2 = 6
    SNOW10 = 7
    SNOW30 = 8
    TRAIN_UP = 9
    TRAIN_DOWN = 10
    TRAIN_DOUBLE = 11
    IMPACT_UP = 12
    IMPACT_DOWN = 13
    IMPACT_DOUBLE = 14
    LATERAL = 15
    WIND_WITH_TRAIN = 16
    WIND_WITHOUT_TRAIN = 17
    CENTRIFUGAL_UP = 18  # only on a curve (decision 33)
    CENTRIFUGAL_DOWN = 19
    CENTRIFUGAL_DOUBLE = 20


CENTRIFUGAL_CASES = {BasicCase.CENTRIFUGAL_UP: Track.UP, BasicCase.CENTRIFUGAL_DOWN: Track.DOWN,
                     BasicCase.CENTRIFUGAL_DOUBLE: Track.DOUBLE}
TRACKS = {**CENTRIFUGAL_CASES, BasicCase.TRAIN_UP: Track.UP, BasicCase.TRAIN_DOWN: Track.DOWN, BasicCase.TRAIN_DOUBLE: Track.DOUBLE,
          BasicCase.IMPACT_UP: Track.UP, BasicCase.IMPACT_DOWN: Track.DOWN, BasicCase.IMPACT_DOUBLE: Track.DOUBLE}
IMPACT_CASES = frozenset({BasicCase.IMPACT_UP, BasicCase.IMPACT_DOWN, BasicCase.IMPACT_DOUBLE})
HORIZONTAL = frozenset({BasicCase.LATERAL, BasicCase.WIND_WITH_TRAIN, BasicCase.WIND_WITHOUT_TRAIN,
                        *CENTRIFUGAL_CASES})
LONG_TERM = frozenset(BasicCase(n) for n in range(1, 9))  # 9-13 バネ 1 (long term); 2 for the train and after


@dataclass(frozen=True)
class BasicAction:
    case: BasicCase
    spring: SpringTerm  # 9-13 バネ: 1 long term (cases 1-8), 2 short term (9-17)
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...]
    member_loads: tuple[MemberLoad, ...]  # the wind on the pier body

    @property
    def horizontal(self) -> bool:
        return self.case in HORIZONTAL

    @property
    def track(self) -> Track | None:
        return TRACKS.get(self.case)


@dataclass(frozen=True)
class Actions:
    fixed: FixedDead
    additional: AdditionalDead
    buoyancy: tuple[Row, Row, Row]  # high, normal, low water
    snow: tuple[TopTable, TopTable, TopTable]  # 2, 10, 30 year
    train: Trains
    impact: Impacts
    lateral: Lateral
    wind_with_train: Wind
    wind_without_train: Wind
    centrifugal: Centrifugals | None  # None on a straight track
    basic_cases: tuple[BasicAction, ...]


def _row(item: Item, slot: int | None, n: Printed, arm: Printed) -> Row:
    return Row(item=item, slot=slot, n=n, arm=arm, m=put(MOMENT, d(n) * d(arm)))


def _table(rows: list[Row]) -> TopTable:
    return TopTable(rows=tuple(rows), n=put(FORCE, total(row.n for row in rows)),
                    m=put(MOMENT, total(row.m for row in rows)))


def _body(item: Item, body: Body) -> Row:
    return _row(item, None, body.weight, body.x_c)


Girders = tuple[tuple[Item, tuple[BearingLoads, ...]], ...]


def train_table(track: Track, girders: Girders, reactions: dict[Item, Printed]) -> TrainTable:
    """One track per bearing: girder reaction × share of the bearing (9-5; 11-8 with the seismic train)."""
    def share(bearing: BearingLoads) -> Printed:
        if track is Track.DOUBLE:
            return bearing.double
        return bearing.bearing.shares.l2 if track is Track.UP else bearing.bearing.shares.l1

    rows = []
    for item, bearings in girders:
        for bearing in bearings:
            n = put(FORCE, d(reactions[item]) * d(share(bearing)))
            arm = bearing.bearing.position
            rows.append(TrainRow(item=item, slot=bearing.slot, reaction=reactions[item], share=share(bearing), n=n,
                                 arm=arm, m=put(MOMENT, d(n) * d(arm))))
    return TrainTable(track=track, rows=tuple(rows), n=put(FORCE, total(r.n for r in rows)),
                      m=put(MOMENT, total(r.m for r in rows)))


def _impact(train: TrainTable, group: GroupTrain) -> ImpactTable:
    rows = []
    for load in train.rows:
        girder: GirderImpact = group.origin_impact if load.item is Item.ORIGIN else group.end_impact
        coefficient = girder.double if train.track is Track.DOUBLE else girder.single
        n = put(FORCE, d(load.n) * d(coefficient))
        rows.append(ImpactRow(item=load.item, slot=load.slot, train=load.n, coefficient=coefficient, n=n,
                              arm=load.arm, m=put(MOMENT, d(n) * d(load.arm))))
    return ImpactTable(track=train.track, rows=tuple(rows), n=put(FORCE, total(r.n for r in rows)),
                       m=put(MOMENT, total(r.m for r in rows)))


def _impacts(trains: Trains, group: GroupTrain) -> ImpactSet:
    return ImpactSet(*(_impact(trains.table(track), group) for track in Track))


def _horizontal(item: Item, force: TransverseForce) -> HorizontalRow:
    return HorizontalRow(item=item, h=force.force, y=force.height, m=force.moment)


def _centrifugal(train: TrainTable, sides: tuple[TransverseSide, TransverseSide]) -> CentrifugalTable:
    rows = []
    for item, side in zip((Item.ORIGIN, Item.END), sides, strict=True):
        load = put(FORCE, total(r.n for r in train.rows if r.item is item))
        h = put(FORCE, d(load) * d(side.centrifugal_coefficient))
        rows.append(CentrifugalRow(item=item, train=load, coefficient=side.centrifugal_coefficient, h=h,
                                   y=side.centrifugal_height, m=put(MOMENT, d(h) * d(side.centrifugal_height))))
    return CentrifugalTable(track=train.track, rows=(rows[0], rows[1]), h=put(FORCE, total(r.h for r in rows)),
                            m=put(MOMENT, total(r.m for r in rows)))


def calculate_actions(pier: PierInput, frame: Frame, reaction: ReactionResult) -> Actions:
    s = pier.substructure
    dead, weights, train, transverse = reaction.dead, reaction.self_weight, reaction.train, reaction.transverse
    girders: Girders = ((Item.ORIGIN, dead.origin.bearings), (Item.END, dead.end.bearings))

    def loads(field: str) -> list[Row]:
        return [_row(item, b.slot, getattr(b.bearing, field), b.bearing.position)
                for item, bearings in girders for b in bearings]

    parts = ([_body(Item.PEDESTAL, weights.pedestal)] if s.h[1].value > 0 else []) + [_body(Item.BEAM, weights.beam)]
    bearings_d1 = loads("d1")
    table = _table(bearings_d1 + parts)
    q = put(LINE_LOAD, d(s.w[6]) * d(s.b[6]) * d(s.unit_weight_body))
    overlap = LENGTH.total((s.h[2], s.h[3]))
    fixed = FixedDead(table=table, column_q=q, overlap=overlap, n=put(FORCE, d(table.n) - d(q) * d(overlap)),
                      m=table.m, footing=_body(Item.FOOTING, weights.footing))
    additional = AdditionalDead(table=_table(loads("d2")), soil=_body(Item.OVERBURDEN, weights.overburden))
    buoyancy = tuple(_body(Item.WATER, water.body)
                     for water in (weights.buoyancy_high, weights.buoyancy_normal, weights.buoyancy_low))
    snow = tuple(_table(loads(field)) for field in ("snow2", "snow10", "snow30"))
    reactions = {Item.ORIGIN: train.loading.rb, Item.END: train.loading.rc}
    trains = Trains(*(train_table(track, girders, reactions) for track in Track))
    impact = Impacts(ultimate=_impacts(trains, train.ultimate), service=_impacts(trains, train.service))
    origin, end = transverse.origin, transverse.end
    lateral_rows = (_horizontal(Item.ORIGIN, origin.vehicle_lateral), _horizontal(Item.END, end.vehicle_lateral))
    lateral = Lateral(origin=lateral_rows[0], end=lateral_rows[1], h=put(FORCE, total(r.h for r in lateral_rows)),
                      m=put(MOMENT, sum((d(r.h) * d(r.y) for r in lateral_rows), Decimal(0))))

    def wind(pressure: Printed, field: str) -> Wind:
        rows = (_horizontal(Item.ORIGIN, getattr(origin, field)), _horizontal(Item.END, getattr(end, field)))
        return Wind(pressure=pressure, rows=rows, h=put(FORCE, total(r.h for r in rows)),
                    m=put(MOMENT, total(r.m for r in rows)), pier=pier_wind(pier, frame, pressure))

    with_train, without_train = wind(WIND_WITH_TRAIN, "wind_with_train"), wind(WIND_WITHOUT_TRAIN, "wind_without_train")

    def top(n: Printed, m: Printed) -> PointLoad:
        return bearing_point(frame, n, m)

    def footing(row: Row) -> PointLoad:
        return point_load(frame, NodeRole.FOOTING_CENTROID, n=row.n, m=row.m)

    def seat(h: Printed, m: Printed) -> PointLoad:
        return bearing_point(frame, FORCE(0), m, h)

    if frame.bearing_seat.number == frame.node(NodeRole.CAP_TOP).number:
        d1: tuple[PointLoad, ...] = (point_load(frame, NodeRole.CAP_TOP, n=fixed.n, m=fixed.m),)
    else:  # the bearings on the pedestal; the pier parts, less the column-line overlap, at the beam top
        d1 = (top(put(FORCE, total(r.n for r in bearings_d1)), put(MOMENT, total(r.m for r in bearings_d1))),
              point_load(frame, NodeRole.CAP_TOP, n=put(FORCE, total(r.n for r in parts) - d(q) * d(overlap)),
                         m=put(MOMENT, total(r.m for r in parts))))
    c = BasicCase
    points: dict[BasicCase, tuple[PointLoad, ...]] = {
        c.D1: (*d1, footing(fixed.footing)),
        c.D2: (top(additional.table.n, additional.table.m), footing(additional.soil)),
        c.BUOYANCY_HIGH: (footing(buoyancy[0]),),
        c.BUOYANCY_NORMAL: (footing(buoyancy[1]),),
        c.BUOYANCY_LOW: (footing(buoyancy[2]),),
        c.SNOW2: (top(snow[0].n, snow[0].m),),
        c.SNOW10: (top(snow[1].n, snow[1].m),),
        c.SNOW30: (top(snow[2].n, snow[2].m),),
        c.LATERAL: (seat(lateral.h, lateral.m),),
        c.WIND_WITH_TRAIN: (seat(with_train.h, with_train.m),),
        c.WIND_WITHOUT_TRAIN: (seat(without_train.h, without_train.m),),
    }
    for case, track in TRACKS.items():
        if case not in CENTRIFUGAL_CASES:
            loaded: TrainTable | ImpactTable = (impact.ultimate.table(track) if case in IMPACT_CASES
                                                else trains.table(track))
            points[case] = (top(loaded.n, loaded.m),)
    centrifugal = None
    if pier.spans.origin.radius.value or pier.spans.end.radius.value:
        centrifugal = Centrifugals(*(_centrifugal(trains.table(track), (origin, end)) for track in Track))
        for case, track in CENTRIFUGAL_CASES.items():
            points[case] = (seat(centrifugal.table(track).h, centrifugal.table(track).m),)
    members = {c.WIND_WITH_TRAIN: with_train.pier.member_loads,
               c.WIND_WITHOUT_TRAIN: without_train.pier.member_loads}
    basic_cases = tuple(
        BasicAction(case=case, spring=SpringTerm.LONG if case in LONG_TERM else SpringTerm.SHORT, points=points[case],
                    line_loads=(column_line_load(frame, n=q),) if case is c.D1 else (),
                    member_loads=members.get(case, ()))
        for case in BasicCase if case in points)
    return Actions(fixed=fixed, additional=additional, buoyancy=buoyancy, snow=snow,  # type: ignore[arg-type]
                   train=trains, impact=impact, lateral=lateral, wind_with_train=with_train,
                   wind_without_train=without_train, centrifugal=centrifugal, basic_cases=basic_cases)


__all__ = ["CENTRIFUGAL_CASES", "IMPACT_CASES", "TRACKS", "Actions", "AdditionalDead", "CentrifugalRow",
           "CentrifugalTable", "Centrifugals", "BasicAction", "BasicCase", "FixedDead",
           "HorizontalRow", "ImpactRow", "ImpactSet", "ImpactTable", "Impacts", "Item", "Lateral", "Row", "TopTable",
           "TrainRow", "TrainTable", "Trains", "Track", "Wind", "calculate_actions", "train_table"]
