"""0610 basic actions on the longitudinal frame (Example2 08 pp.8-3 to 8-9).

Every action is computed from the printed 0600 and input values (decision 2):
the girder loads at B and C have the lever −f (origin side) and +f (end side)
from the column axis and act at the seat of their girder (decision 81): the
beam top, or the pedestal top when the bearing line is on the pedestal. D1 and
D2 are tabled by seat, the lever on the pedestal taken from its centre, so each
table's M is the moment at its seat; the train path's other cases need both
girders on one seat (``bearing_point``: M′ = M − N × offset on an offset
pedestal). The beam acts at the beam top with its own centroid, the pedestal
and the column as line loads along their members (decision 81). Footing, soil
and water act at the footing centroid, with the lever from the footing centre
(0600). Tables print N and M to 2 decimals and the lever to 3; every moment is
N × lever of its own row and every total is the sum of the printed rows
(ADR-0003).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ...core.printed import FORCE, LENGTH, LINE_LOAD, MOMENT, Printed
from ...inputs import PierInput
from ...loadmodel import Side
from .._exact import d, put, total
from ..frame import Frame, LineLoad, NodeRole, PointLoad, column_line_load, pedestal_line_load, point_load
from ..load_nature import Nature, SpringTerm, spring_term
from ..reaction import ReactionResult
from ..reaction.longitudinal import LAYOUT_CASES, LongitudinalCase
from ..reaction.self_weight import Body, SelfWeightResult
from ..reaction.train import GirderImpact, Layout, LayoutTrain


class Item(Enum):
    ORIGIN = "origin"  # RB: the bearings of the origin girder on this pier
    END = "end"  # RC: the bearings of the end girder on this pier
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
    """D1 (8-3): the girders on the beam top and the beam at the beam top, the girders on the pedestal at its top, the
    pedestal and the column as line loads, the footing at its centroid (decision 81)."""

    table: TopTable  # at the beam top: RB / RC of the girders on it and the beam
    pedestal: TopTable | None  # at the pedestal top: RB / RC of the girders on it, the lever from the pedestal centre
    pedestal_q: Printed | None  # q = W3 × B3 × γ along the pedestal (H1 > 0)
    column_q: Printed  # q = W6 × B6 × γ, over the column line from the beam top to the footing top
    overlap: Printed  # H2 + H3: where q runs through the beam already weighed in the table
    n: Printed  # N at the beam top = Σ N − q × (H2 + H3)
    m: Printed  # Σ M of the beam-top table (the column line load has no lever)
    footing: Row  # P at the footing centroid


@dataclass(frozen=True)
class AdditionalDead:
    """D2 (8-3): the girder loads at their seats (decision 81), the overburden soil at the footing centroid."""

    table: TopTable  # at the beam top
    pedestal: TopTable | None  # at the pedestal top, the lever from the pedestal centre; None if no girder sits there
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
    coefficient: Printed  # 0600 impact coefficient on the pier body (decision 77)
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
    """Impact with the coefficients on the pier body (decision 77)."""

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
    """The 20 basic cases of 8-9, by their number with snow (without snow, 17: decision 69)."""

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


SNOW_CASES = (BasicCase.SNOW2, BasicCase.SNOW10, BasicCase.SNOW30)
# The basic cases made for each 列車の配置 (decision 102; Example橋脚4 表2.3.1): the train, its impact and the bearing
# forces with the train or braking; the others are one case.
LAYOUT_DEPENDENT = frozenset({BasicCase.TRAIN_SINGLE, BasicCase.TRAIN_DOUBLE, BasicCase.IMPACT_SINGLE,
                              BasicCase.IMPACT_DOUBLE,
                              *(basic for basic, case in HORIZONTAL_CASES.items() if case in LAYOUT_CASES)})

_N = Nature
_RAIL, _RAIL_BRAKING = frozenset({_N.LONG_RAIL}), frozenset({_N.LONG_RAIL, _N.BRAKING})
# What each basic case carries; its spring set follows from it (decision 36, load_nature).
NATURES: dict[BasicCase, frozenset[Nature]] = {
    BasicCase.D1: frozenset({_N.DEAD}), BasicCase.D2: frozenset({_N.DEAD}),
    BasicCase.BUOYANCY_HIGH: frozenset({_N.WATER}), BasicCase.BUOYANCY_NORMAL: frozenset({_N.WATER}),
    BasicCase.BUOYANCY_LOW: frozenset({_N.WATER}),
    BasicCase.SNOW2: frozenset({_N.SNOW}), BasicCase.SNOW10: frozenset({_N.SNOW}),
    BasicCase.SNOW30: frozenset({_N.SNOW}),
    BasicCase.TRAIN_SINGLE: frozenset({_N.TRAIN}), BasicCase.TRAIN_DOUBLE: frozenset({_N.TRAIN}),
    BasicCase.IMPACT_SINGLE: frozenset({_N.IMPACT}), BasicCase.IMPACT_DOUBLE: frozenset({_N.IMPACT}),
    BasicCase.SERVICE_LR08: _RAIL, BasicCase.SERVICE_LR10: _RAIL,
    BasicCase.SAFETY_LR10_B: _RAIL_BRAKING, BasicCase.SAFETY_LR11_B: _RAIL_BRAKING,
    BasicCase.SAFETY_LR10_BMAX: _RAIL_BRAKING, BasicCase.SAFETY_LR10: _RAIL,
    BasicCase.RESTORABILITY_LR10_B: _RAIL_BRAKING, BasicCase.RESTORABILITY_LR10: _RAIL,
}


@dataclass(frozen=True)
class BasicAction:
    number: int  # 8-9 No: the position among the cases made (decision 69)
    case: BasicCase
    spring: SpringTerm
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...]
    layout: Layout | None = None  # the 列車の配置 of a LAYOUT_DEPENDENT case (decision 102)

    @property
    def horizontal(self) -> bool:
        return self.case in HORIZONTAL_CASES


@dataclass(frozen=True)
class LayoutActions:
    """The train, its impact and the bearing forces with the train or braking of ② or ③ (decision 102)."""

    layout: Layout
    train: Trains
    impact: Impacts
    horizontal: tuple[HorizontalRow, ...]  # LAYOUT_CASES of the layout, in LongitudinalCase order


@dataclass(frozen=True)
class Actions:
    fixed: FixedDead
    additional: AdditionalDead
    buoyancy: tuple[Row, Row, Row]  # high, normal, low water
    snow: tuple[TopTable, TopTable, TopTable] | None  # 2, 10, 30 year; None without snow (decision 69)
    train: Trains  # ① (both girders)
    impact: Impacts
    horizontal: tuple[HorizontalRow, ...]  # in LongitudinalCase order = basic cases 13-20 (with snow), ①
    one_girder: tuple[LayoutActions, LayoutActions]  # ② and ③
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
    """The train path's bearing loads at the one seat of both girders; M (about the column axis) moves to the seat as
    M − N × offset. Girders on two seats are an input error (``Frame.bearing_seat``, decision 81)."""
    seat = frame.bearing_seat
    offset = frame.bearing_offset
    if offset.value:
        m = put(MOMENT, d(m) - d(n) * d(offset))
    return PointLoad(anchor=NodeRole.PEDESTAL_TOP if NodeRole.PEDESTAL_TOP in seat.roles else NodeRole.CAP_TOP,
                     node=seat.number, n=n, h=h, m=m)


def seat_lever(frame: Frame, side: Side, lever: Printed) -> Printed:
    """*lever* from the column axis as the lever from the axis of the seat of *side*: on the pedestal, from its centre
    (decision 81)."""
    offset = frame.seat_offset(side)
    return put(LENGTH, d(lever) - d(offset)) if offset.value else lever


def seat_points(frame: Frame, loads: Sequence[tuple[NodeRole, Printed, Printed]]) -> tuple[PointLoad, ...]:
    """N and M at each seat of *loads* (anchor, N, M about the seat), those with a load; without any, the zeros at the
    first, so that the case keeps a row where it acts."""
    found = tuple(point_load(frame, anchor, n=n, m=m) for anchor, n, m in loads if n.value or m.value)
    anchor, n, m = loads[0]
    return found or (point_load(frame, anchor, n=n, m=m),)


@dataclass(frozen=True)
class DeadActions:
    """The cases of the application on the longitudinal frame: D1, D2 and the buoyancy (decision 70)."""

    fixed: FixedDead
    additional: AdditionalDead
    buoyancy: tuple[Row, Row, Row]  # high, normal, low water
    points: dict[BasicCase, tuple[PointLoad, ...]]  # D1, D2, BUOYANCY_HIGH, BUOYANCY_NORMAL, BUOYANCY_LOW
    column: LineLoad  # the D1 column line load
    pedestal: LineLoad | None = None  # the D1 pedestal line load (H1 > 0, decision 81)

    @property
    def lines(self) -> tuple[LineLoad, ...]:
        """The D1 line loads, the pedestal first (from the top)."""
        return (*((self.pedestal,) if self.pedestal is not None else ()), self.column)


def _arms(pier: PierInput) -> tuple[Printed, Printed]:
    return put(LENGTH, -d(pier.spans.origin.f)), pier.spans.end.f


def dead_actions(pier: PierInput, frame: Frame, dead: Any, weights: SelfWeightResult) -> DeadActions:
    """D1, D2 and the buoyancy from the dead loads at B and C (*dead*: the DeadResult of 0600, or the
    DeadLoadsResult of a load model's 0600) and the pier parts, tabled by the seat of each girder (decision 81)."""
    s = pier.substructure
    arms = _arms(pier)
    girders = ((Side.ORIGIN, Item.ORIGIN, dead.origin.pier, arms[0]), (Side.END, Item.END, dead.end.pier, arms[1]))

    def loads(field: str, anchor: NodeRole) -> list[Row]:
        return [_row(item, getattr(load, field), seat_lever(frame, side, arm))
                for side, item, load, arm in girders if frame.seat_role(side) is anchor]

    cap, top = NodeRole.CAP_TOP, NodeRole.PEDESTAL_TOP
    table = _table(loads("d1", cap) + [_body(Item.BEAM, weights.beam)])
    pedestal = _table(rows) if (rows := loads("d1", top)) else None
    q = put(LINE_LOAD, d(s.w[6]) * d(s.b[6]) * d(s.unit_weight_body))
    pedestal_q = put(LINE_LOAD, d(s.w[3]) * d(s.b[3]) * d(s.unit_weight_body)) if s.h[1].value > 0 else None
    overlap = LENGTH.total((s.h[2], s.h[3]))
    fixed = FixedDead(table=table, pedestal=pedestal, pedestal_q=pedestal_q, column_q=q, overlap=overlap,
                      n=put(FORCE, d(table.n) - d(q) * d(overlap)), m=table.m,
                      footing=_body(Item.FOOTING, weights.footing))
    additional = AdditionalDead(table=_table(loads("d2", cap)),
                                pedestal=_table(rows) if (rows := loads("d2", top)) else None,
                                soil=_body(Item.OVERBURDEN, weights.overburden))
    buoyancy = tuple(_body(Item.WATER, water.body)
                     for water in (weights.buoyancy_high, weights.buoyancy_normal, weights.buoyancy_low))

    def footing(row: Row) -> PointLoad:
        return point_load(frame, NodeRole.FOOTING_CENTROID, n=row.n, m=row.m)

    d1 = (point_load(frame, cap, n=fixed.n, m=fixed.m),
          *((point_load(frame, top, n=pedestal.n, m=pedestal.m),) if pedestal is not None else ()))
    d2 = seat_points(frame, [(cap, additional.table.n, additional.table.m),
                             *(((top, additional.pedestal.n, additional.pedestal.m),)
                               if additional.pedestal is not None else ())])
    points: dict[BasicCase, tuple[PointLoad, ...]] = {
        BasicCase.D1: (*d1, footing(fixed.footing)),
        BasicCase.D2: (*d2, footing(additional.soil)),
        BasicCase.BUOYANCY_HIGH: (footing(buoyancy[0]),),
        BasicCase.BUOYANCY_NORMAL: (footing(buoyancy[1]),),
        BasicCase.BUOYANCY_LOW: (footing(buoyancy[2]),),
    }
    return DeadActions(fixed, additional, buoyancy, points, column_line_load(frame, n=q),  # type: ignore[arg-type]
                       pedestal_line_load(frame, n=pedestal_q) if pedestal_q is not None else None)


def snow_table(pier: PierInput, dead: Any, field: str) -> TopTable:
    """The snow of one return period at B and C (8-4): *field* is snow2, snow10 or snow30 of the 0600 dead loads."""
    return _table(_bearings(getattr(dead.origin.pier, field), getattr(dead.end.pier, field), _arms(pier)))


def calculate_actions(pier: PierInput, frame: Frame, reaction: ReactionResult) -> Actions:
    dead, weights, train = reaction.dead, reaction.self_weight, reaction.train
    arms = _arms(pier)
    app = dead_actions(pier, frame, dead, weights)
    fixed, additional, buoyancy = app.fixed, app.additional, app.buoyancy
    snow = tuple(snow_table(pier, dead, field) for field in ("snow2", "snow10", "snow30")) if dead.snow else None

    def top(n: Printed, m: Printed) -> PointLoad:
        return bearing_point(frame, n, m)

    def placed(layout: Layout) -> tuple[LayoutActions, dict[BasicCase, tuple[PointLoad, ...]]]:
        """The tables of one 列車の配置 and the points of its LAYOUT_DEPENDENT cases."""
        layout_train: LayoutTrain = train.layout(layout)
        loading = layout_train.loading
        single = _table(_bearings(loading.rb, loading.rc, arms))
        double = _table(_bearings(put(FORCE, d(loading.rb) * d(dead.origin.track_total)),
                                  put(FORCE, d(loading.rc) * d(dead.end.track_total)), arms))
        ultimate, service = layout_train.ultimate, layout_train.service
        impact = Impacts(
            ultimate_single=_impact(single, ultimate.origin_pier_impact, ultimate.end_pier_impact, double=False),
            ultimate_double=_impact(double, ultimate.origin_pier_impact, ultimate.end_pier_impact, double=True),
            service_single=_impact(single, service.origin_pier_impact, service.end_pier_impact, double=False),
            service_double=_impact(double, service.origin_pier_impact, service.end_pier_impact, double=True))
        forces = reaction.longitudinal if layout is Layout.BOTH else \
            reaction.longitudinal.one_girder[0 if layout is Layout.ORIGIN else 1]
        cases = {basic: forces.case(case) for basic, case in HORIZONTAL_CASES.items()
                 if layout is Layout.BOTH or basic in LAYOUT_DEPENDENT}
        horizontal = tuple(HorizontalRow(case=c.case, origin=c.origin.force, end=c.end.force, total=c.total)
                           for c in cases.values())
        points = {BasicCase.TRAIN_SINGLE: (top(single.n, single.m),),
                  BasicCase.TRAIN_DOUBLE: (top(double.n, double.m),),
                  BasicCase.IMPACT_SINGLE: (top(impact.ultimate_single.n, impact.ultimate_single.m),),
                  BasicCase.IMPACT_DOUBLE: (top(impact.ultimate_double.n, impact.ultimate_double.m),),
                  **{basic: (bearing_point(frame, FORCE(0), h=c.total),) for basic, c in cases.items()}}
        return LayoutActions(layout, Trains(single, double), impact, horizontal), points

    both, both_points = placed(Layout.BOTH)
    origin, origin_points = placed(Layout.ORIGIN)
    end, end_points = placed(Layout.END)
    points: dict[BasicCase, tuple[PointLoad, ...]] = {**app.points, **both_points}
    if snow is not None:
        for case, table in zip(SNOW_CASES, snow, strict=True):
            points[case] = (top(table.n, table.m),)
    layouts = {Layout.BOTH: both_points, Layout.ORIGIN: origin_points, Layout.END: end_points}
    # Decision 69: without snow the snow cases are not made, and the cases after them move up. Decision 102: a
    # LAYOUT_DEPENDENT case is made for ①, ② and ③ in turn.
    made = [(case, layout) for case in BasicCase if case in points
            for layout in (tuple(Layout) if case in LAYOUT_DEPENDENT else (None,))]
    basic_cases = tuple(
        BasicAction(number=number, case=case, spring=spring_term(NATURES[case]),
                    points=points[case] if layout is None else layouts[layout][case],
                    line_loads=app.lines if case is BasicCase.D1 else (), layout=layout)
        for number, (case, layout) in enumerate(made, 1))
    return Actions(fixed=fixed, additional=additional, buoyancy=buoyancy, snow=snow,  # type: ignore[arg-type]
                   train=both.train, impact=both.impact, horizontal=both.horizontal, one_girder=(origin, end),
                   basic_cases=basic_cases)


__all__ = ["Actions", "AdditionalDead", "BasicAction", "BasicCase", "DeadActions", "FixedDead", "HorizontalRow",
           "LAYOUT_DEPENDENT", "LayoutActions",
           "ImpactRow", "ImpactTable", "Impacts", "Item", "NATURES", "Row", "SNOW_CASES", "SpringTerm", "TopTable",
           "Trains", "bearing_point", "calculate_actions", "dead_actions", "seat_lever", "seat_points", "snow_table"]
