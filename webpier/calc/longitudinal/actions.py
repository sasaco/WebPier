"""0610 basic actions on the longitudinal frame (Example2 08 pp.8-3 to 8-9).

Every action is computed from the printed 0600 and input values (decision 2):
the girder loads at B and C have the lever −f (origin side) and +f (end side)
from the column axis and act at the bearing seat, the beam top or, with a
pedestal, the pedestal top (decision 29), where their moment is taken about
the seat. The 0600 pier parts act at the beam top with their own centroids. Footing, soil and water act at the footing centroid, with the lever
from the footing centre (0600). Tables print N and M to 2 decimals and the
lever to 3; every moment is N × lever of its own row and every total is the
sum of the printed rows (ADR-0003).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...core.printed import FORCE, LENGTH, LINE_LOAD, MOMENT, Printed
from ...inputs import PierInput
from .._exact import d, put, total
from ..frame import Frame, LineLoad, NodeRole, PointLoad, column_line_load, point_load
from ..reaction import ReactionResult
from ..reaction.longitudinal import LongitudinalCase
from ..reaction.self_weight import Body
from ..reaction.train import GirderImpact


class Item(Enum):
    ORIGIN = "origin"  # RB: the bearings of the origin girder on this pier
    END = "end"  # RC: the bearings of the end girder on this pier
    PEDESTAL = "pedestal"  # 桁受け (0600)
    BEAM = "beam"  # はり: prism and haunch (0600)
    FOOTING = "footing"
    OVERBURDEN = "overburden"
    WATER = "water"


@dataclass(frozen=True)
class Row:
    item: Item
    n: Printed  # vertical force, downward positive
    arm: Printed  # lever along the track
    m: Printed  # N × arm


@dataclass(frozen=True)
class TopTable:
    """Loads at the beam top, one row per source (8-3, 8-4)."""

    rows: tuple[Row, ...]
    n: Printed  # Σ N
    m: Printed  # Σ M

    def row(self, item: Item) -> Row:
        return next(row for row in self.rows if row.item is item)


@dataclass(frozen=True)
class FixedDead:
    """D1 (8-3): girder, pedestal and beam at the beam top, the column as a line load, the footing at its centroid."""

    table: TopTable  # RB, RC, pedestal (H1 > 0), beam
    column_q: Printed  # q = W6 × B6 × γ, over the column line from the beam top to the footing top
    overlap: Printed  # H2 + H3: where q runs through the beam already weighed in the table
    n: Printed  # N = Σ N − q × (H2 + H3)
    m: Printed  # Σ M (the column line load has no lever)
    footing: Row  # P at the footing centroid


@dataclass(frozen=True)
class AdditionalDead:
    """D2 (8-3): girder loads at the beam top, the overburden soil at the footing centroid."""

    table: TopTable
    soil: Row


@dataclass(frozen=True)
class Trains:
    """Train load without load factors (8-4)."""

    single: TopTable  # RB, RC of one track (0600 moving load)
    double: TopTable  # × the loaded tracks of the girder (0600 track total)


@dataclass(frozen=True)
class ImpactRow:
    item: Item
    train: Printed  # train load of the support
    coefficient: Printed  # 0600 girder impact coefficient (07 7-2)
    n: Printed  # train × coefficient
    arm: Printed
    m: Printed


@dataclass(frozen=True)
class ImpactTable:
    rows: tuple[ImpactRow, ...]
    n: Printed
    m: Printed

    def row(self, item: Item) -> ImpactRow:
        return next(row for row in self.rows if row.item is item)


@dataclass(frozen=True)
class Impacts:
    """Impact with the girder coefficients as they are (decision 26, Example2 8-5)."""

    ultimate_single: ImpactTable  # safety and restorability coefficients: basic case 11
    ultimate_double: ImpactTable  # i × (1 − L/200): basic case 12
    service_single: ImpactTable  # serviceability coefficients, 0.75 i (07 7-2)
    service_double: ImpactTable


@dataclass(frozen=True)
class HorizontalRow:
    """Bearing horizontal forces of one 0600 case (8-5): the basic cases 13-20 at the beam top."""

    case: LongitudinalCase
    origin: Printed  # H at B (origin girder)
    end: Printed  # H at C (end girder)
    total: Printed  # H_B + H_C


class BasicCase(Enum):
    """The 20 basic cases of 8-9, by number."""

    D1 = 1
    D2 = 2
    BUOYANCY_HIGH = 3
    BUOYANCY_NORMAL = 4
    BUOYANCY_LOW = 5
    SNOW2 = 6
    SNOW10 = 7
    SNOW30 = 8
    TRAIN_SINGLE = 9
    TRAIN_DOUBLE = 10
    IMPACT_SINGLE = 11
    IMPACT_DOUBLE = 12
    SERVICE_LR08 = 13
    SERVICE_LR10 = 14
    SAFETY_LR10_B = 15
    SAFETY_LR11_B = 16
    SAFETY_LR10_BMAX = 17
    SAFETY_LR10 = 18
    RESTORABILITY_LR10_B = 19
    RESTORABILITY_LR10 = 20


# The horizontal basic cases are the 0600 bearing cases (8-5 / 07 7-5 to 7-12); B10 prints as 1.23B, B11 as 1.35B.
HORIZONTAL_CASES = {
    BasicCase.SERVICE_LR08: LongitudinalCase.SERVICE_LR08,
    BasicCase.SERVICE_LR10: LongitudinalCase.SERVICE_LR10,
    BasicCase.SAFETY_LR10_B: LongitudinalCase.SAFETY_LR10_B10,
    BasicCase.SAFETY_LR11_B: LongitudinalCase.SAFETY_LR11_B10,
    BasicCase.SAFETY_LR10_BMAX: LongitudinalCase.SAFETY_LR10_B11,
    BasicCase.SAFETY_LR10: LongitudinalCase.SAFETY_LR10,
    BasicCase.RESTORABILITY_LR10_B: LongitudinalCase.RESTORABILITY_LR10_B10,
    BasicCase.RESTORABILITY_LR10: LongitudinalCase.RESTORABILITY_LR10,
}


class SpringTerm(Enum):
    LONG = "long_term"  # バネ 1 of 8-9
    SHORT = "short_term"  # バネ 2


_SHORT_TERM = frozenset({BasicCase.TRAIN_SINGLE, BasicCase.TRAIN_DOUBLE, BasicCase.IMPACT_SINGLE,
                         BasicCase.IMPACT_DOUBLE, BasicCase.SAFETY_LR10_B, BasicCase.SAFETY_LR11_B,
                         BasicCase.SAFETY_LR10_BMAX, BasicCase.RESTORABILITY_LR10_B})  # 8-9 バネ 2


@dataclass(frozen=True)
class BasicAction:
    case: BasicCase
    spring: SpringTerm
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...]

    @property
    def horizontal(self) -> bool:
        return self.case in HORIZONTAL_CASES


@dataclass(frozen=True)
class Actions:
    fixed: FixedDead
    additional: AdditionalDead
    buoyancy: tuple[Row, Row, Row]  # high, normal, low water
    snow: tuple[TopTable, TopTable, TopTable]  # 2, 10, 30 year
    train: Trains
    impact: Impacts
    horizontal: tuple[HorizontalRow, ...]  # in LongitudinalCase order = basic cases 13-20
    basic_cases: tuple[BasicAction, ...]


def _row(item: Item, n: Printed, arm: Printed) -> Row:
    return Row(item=item, n=n, arm=arm, m=put(MOMENT, d(n) * d(arm)))


def _table(rows: list[Row]) -> TopTable:
    return TopTable(rows=tuple(rows), n=put(FORCE, total(row.n for row in rows)),
                    m=put(MOMENT, total(row.m for row in rows)))


def _bearings(origin: Printed, end: Printed, arms: tuple[Printed, Printed]) -> list[Row]:
    return [_row(Item.ORIGIN, origin, arms[0]), _row(Item.END, end, arms[1])]


def _body(item: Item, body: Body) -> Row:
    return _row(item, body.weight, body.x_l)


def _impact(train: TopTable, origin: GirderImpact, end: GirderImpact, double: bool) -> ImpactTable:
    rows = []
    for item, girder in ((Item.ORIGIN, origin), (Item.END, end)):
        load = train.row(item)
        coefficient = girder.double if double else girder.single
        n = put(FORCE, d(load.n) * d(coefficient))
        rows.append(ImpactRow(item=item, train=load.n, coefficient=coefficient, n=n, arm=load.arm,
                              m=put(MOMENT, d(n) * d(load.arm))))
    return ImpactTable(rows=tuple(rows), n=put(FORCE, total(row.n for row in rows)),
                       m=put(MOMENT, total(row.m for row in rows)))


def bearing_point(frame: Frame, n: Printed, m: Printed = MOMENT(0), h: Printed = FORCE(0)) -> PointLoad:
    """Bearing loads at the seat; M (about the column axis) moves to the seat as M − N × offset."""
    seat = frame.bearing_seat
    offset = frame.bearing_offset
    if offset.value:
        m = put(MOMENT, d(m) - d(n) * d(offset))
    return PointLoad(anchor=NodeRole.PEDESTAL_TOP if NodeRole.PEDESTAL_TOP in seat.roles else NodeRole.CAP_TOP,
                     node=seat.number, n=n, h=h, m=m)


def calculate_actions(pier: PierInput, frame: Frame, reaction: ReactionResult) -> Actions:
    s, spans = pier.substructure, pier.spans
    dead, weights, train = reaction.dead, reaction.self_weight, reaction.train
    arms = (put(LENGTH, -d(spans.origin.f)), spans.end.f)
    origin, end = dead.origin.pier, dead.end.pier

    def loads(field: str) -> list[Row]:
        return _bearings(getattr(origin, field), getattr(end, field), arms)

    parts = ([_body(Item.PEDESTAL, weights.pedestal)] if s.h[1].value > 0 else []) + [_body(Item.BEAM, weights.beam)]
    table = _table(loads("d1") + parts)
    q = put(LINE_LOAD, d(s.w[6]) * d(s.b[6]) * d(s.unit_weight_body))
    overlap = LENGTH.total((s.h[2], s.h[3]))
    fixed = FixedDead(table=table, column_q=q, overlap=overlap, n=put(FORCE, d(table.n) - d(q) * d(overlap)),
                      m=table.m, footing=_body(Item.FOOTING, weights.footing))
    additional = AdditionalDead(table=_table(loads("d2")), soil=_body(Item.OVERBURDEN, weights.overburden))
    buoyancy = tuple(_body(Item.WATER, water.body)
                     for water in (weights.buoyancy_high, weights.buoyancy_normal, weights.buoyancy_low))
    snow = tuple(_table(loads(field)) for field in ("snow2", "snow10", "snow30"))
    single = _table(_bearings(train.loading.rb, train.loading.rc, arms))
    double = _table(_bearings(put(FORCE, d(train.loading.rb) * d(dead.origin.track_total)),
                              put(FORCE, d(train.loading.rc) * d(dead.end.track_total)), arms))
    ultimate, service = train.ultimate, train.service
    impact = Impacts(
        ultimate_single=_impact(single, ultimate.origin_impact, ultimate.end_impact, double=False),
        ultimate_double=_impact(double, ultimate.origin_impact, ultimate.end_impact, double=True),
        service_single=_impact(single, service.origin_impact, service.end_impact, double=False),
        service_double=_impact(double, service.origin_impact, service.end_impact, double=True))
    bearing_cases = {basic: reaction.longitudinal.case(case) for basic, case in HORIZONTAL_CASES.items()}
    horizontal = tuple(HorizontalRow(case=c.case, origin=c.origin.force, end=c.end.force, total=c.total)
                       for c in bearing_cases.values())

    def top(n: Printed, m: Printed) -> PointLoad:
        return bearing_point(frame, n, m)

    def footing(row: Row) -> PointLoad:
        return point_load(frame, NodeRole.FOOTING_CENTROID, n=row.n, m=row.m)

    if frame.bearing_seat.number == frame.node(NodeRole.CAP_TOP).number:
        d1: tuple[PointLoad, ...] = (point_load(frame, NodeRole.CAP_TOP, n=fixed.n, m=fixed.m),)
    else:  # the bearings on the pedestal; the pier parts, less the column-line overlap, at the beam top
        bearings, body = table.rows[:2], table.rows[2:]
        d1 = (bearing_point(frame, put(FORCE, total(r.n for r in bearings)), put(MOMENT, total(r.m for r in bearings))),
              point_load(frame, NodeRole.CAP_TOP, n=put(FORCE, total(r.n for r in body) - d(q) * d(overlap)),
                         m=put(MOMENT, total(r.m for r in body))))
    points: dict[BasicCase, tuple[PointLoad, ...]] = {
        BasicCase.D1: (*d1, footing(fixed.footing)),
        BasicCase.D2: (top(additional.table.n, additional.table.m), footing(additional.soil)),
        BasicCase.BUOYANCY_HIGH: (footing(buoyancy[0]),),
        BasicCase.BUOYANCY_NORMAL: (footing(buoyancy[1]),),
        BasicCase.BUOYANCY_LOW: (footing(buoyancy[2]),),
        BasicCase.SNOW2: (top(snow[0].n, snow[0].m),),
        BasicCase.SNOW10: (top(snow[1].n, snow[1].m),),
        BasicCase.SNOW30: (top(snow[2].n, snow[2].m),),
        BasicCase.TRAIN_SINGLE: (top(single.n, single.m),),
        BasicCase.TRAIN_DOUBLE: (top(double.n, double.m),),
        BasicCase.IMPACT_SINGLE: (top(impact.ultimate_single.n, impact.ultimate_single.m),),
        BasicCase.IMPACT_DOUBLE: (top(impact.ultimate_double.n, impact.ultimate_double.m),),
    }
    for basic, forces in bearing_cases.items():
        points[basic] = (bearing_point(frame, FORCE(0), h=forces.total),)
    basic_cases = tuple(
        BasicAction(case=case, spring=SpringTerm.SHORT if case in _SHORT_TERM else SpringTerm.LONG,
                    points=points[case],
                    line_loads=(column_line_load(frame, n=q),) if case is BasicCase.D1 else ())
        for case in BasicCase)
    return Actions(fixed=fixed, additional=additional, buoyancy=buoyancy, snow=snow,  # type: ignore[arg-type]
                   train=Trains(single, double), impact=impact, horizontal=horizontal, basic_cases=basic_cases)


__all__ = ["Actions", "AdditionalDead", "BasicAction", "BasicCase", "FixedDead", "HorizontalRow", "ImpactRow",
           "ImpactTable", "Impacts", "Item", "Row", "SpringTerm", "TopTable", "Trains", "bearing_point",
           "calculate_actions"]
