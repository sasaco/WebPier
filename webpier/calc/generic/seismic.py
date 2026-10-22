"""0710 / 0720 with a load model (decision 70): the seismic frame, its basic cases and the load model's combinations.

The frame is that of the train path: the 0.010 m column-base micro member the only member with a section, and across
the track the girder levels of each side with the control node (decision 65), weighted here by the 支承作用 across
the track of the incremental seismic cases of the combinations, summed for each side (the limited incremental ones
are not counted).

The application's cases are D1, D2 and the buoyancy at the normal water level of the generic 0610 / 0620 put on this
frame (as calc.seismic_longitudinal ``_on_frame``), and EQ2, the pier self-weight inertia of the train path
(``self_weight_inertia``, ``self_weight_loads``). The load model's cases are their 支承作用 on this frame, the
horizontal forces of a case acting toward the earthquake signed toward it (−x along the track, +x across). The
cases of the NDU are those the combinations use: D1, D2, the buoyancy, the load model's in its order, then EQ2.
Each combination of the load model is made for each 照査パターン (ρm, αf), together, pushed toward the earthquake or,
when it is reversed, away from it (decision 76).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ...core.printed import FORCE, Printed
from ...inputs import PierInput
from ...loadmodel import (
    D1, D2, EQ2, WP_NORMAL, Increment as ModelIncrement, LoadModelResult, Section, SeismicDirection, Side,
)
from .._exact import put, total
from ..bearing_actions import BearingTable, bearing_table
from ..foundation import FoundationResult
from ..frame import Direction, Frame, LineLoad, NodeRole, PointLoad, Region, build_frame, column_line_load, point_load
from ..materials import calculate_materials
from ..reaction import DeadReactionResult
from ..seismic_longitudinal import (
    EARTHQUAKE as TOWARD_ORIGIN, GROUND_RESISTANCE_TYPE, PATTERNS, REVERSED, ActionDirection, Increment, MemberLoad,
    SelfWeightInertia, self_weight_inertia, self_weight_loads, toward,
)
from ..seismic_transverse import EARTHQUAKE as TOWARD_W9
from .frame import GenericFrameResult

INCREMENTS = {ModelIncrement.FIXED: Increment.FIXED, ModelIncrement.INCREMENTAL: Increment.INCREMENTAL,
              ModelIncrement.LIMITED: Increment.LIMITED}
# The application's cases: name, direction, increment.
_APPLICATION = {D1: ("固定死荷重", ActionDirection.DOWNWARD, Increment.FIXED),
                D2: ("付加死荷重", ActionDirection.DOWNWARD, Increment.FIXED),
                WP_NORMAL: ("浮力", ActionDirection.UPWARD, Increment.FIXED)}
EQ2_NAME = "自重による地震時慣性力"


@dataclass(frozen=True)
class SeismicCase:
    number: int  # its case in the NDU
    id: str
    name: str
    direction: ActionDirection
    increment: Increment
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...] = ()
    member_loads: tuple[MemberLoad, ...] = ()
    bearings: BearingTable | None = None  # a load model's case: its 支承作用 on this frame

    @property
    def case(self) -> str:  # the key the NDU profile and the combinations name it by
        return self.id


@dataclass(frozen=True)
class GenericSeismicCombination:
    number: int
    name: str
    alpha_f: Printed
    rho_m: Printed
    direction: ActionDirection  # of the push
    cases: tuple[str, ...]  # the ids it loads, in case order
    ground_resistance_type: int
    reverse: bool = False  # 逆向 (decision 76)


@dataclass(frozen=True)
class GenericSeismicResult:
    frame: Frame
    earthquake: Decimal  # ±1 in x
    girder_weights: tuple[Printed, Printed] | None  # 0720: the weights of the control node (origin, end)
    self_weight: SelfWeightInertia  # EQ2
    basic_cases: tuple[SeismicCase, ...]
    combinations: tuple[GenericSeismicCombination, ...]
    sections: tuple[Section, ...] = field(default=())

    def basic(self, case: str) -> SeismicCase:
        return next(item for item in self.basic_cases if item.id == case)


def _on_frame(frame: Frame, point: PointLoad) -> PointLoad:
    return point_load(frame, point.anchor, n=point.n, h=point.h, m=point.m)


def girder_weights(model: LoadModelResult, used: set[str]) -> tuple[Printed, Printed]:
    """Σ of the 支承作用 across the track of the incremental seismic cases *used*, origin and end (decision 65)."""
    sums = {Side.ORIGIN: [], Side.END: []}
    for case in model.cases:
        if case.id in used and case.seismic is not None and case.seismic.increment is ModelIncrement.INCREMENTAL:
            for action in case.actions:
                sums[action.bearing.side].append(FORCE(float(action.transverse)))
    return put(FORCE, total(sums[Side.ORIGIN])), put(FORCE, total(sums[Side.END]))


def calculate_generic_seismic(pier: PierInput, foundation: FoundationResult, reaction: DeadReactionResult,
                              frame_result: GenericFrameResult, model: LoadModelResult, direction: Direction,
                              stage: str) -> GenericSeismicResult:
    along = direction is Direction.LONGITUDINAL
    combinations = model.seismic_longitudinal if along else model.seismic_transverse
    used = {case for combination in combinations for case in combination.cases}
    weights = None if along else girder_weights(model, used)
    frame = build_frame(pier, reaction.self_weight, foundation, calculate_materials(pier), direction,
                        column_base_micro_member=True, elastic_regions={Region.COLUMN_BASE}, girder_levels=weights)
    earthquake = TOWARD_ORIGIN if along else TOWARD_W9
    toward_earthquake = ActionDirection.TOWARD_ORIGIN if along else ActionDirection.TOWARD_W9
    self_weight = self_weight_inertia(pier, reaction)  # type: ignore[arg-type]  # reads the self weight only
    cases: list[SeismicCase] = []

    def add(**values) -> None:
        cases.append(SeismicCase(number=len(cases) + 1, **values))

    for case, (name, kind, increment) in _APPLICATION.items():
        if case in used:
            action = frame_result.basic(case)
            add(id=case, name=name, direction=kind, increment=increment,
                points=tuple(_on_frame(frame, p) for p in action.points),
                line_loads=tuple(column_line_load(frame, n=line.n, h=line.h) for line in action.line_loads))
    for case in model.cases:
        if case.id in used:
            assert case.seismic is not None  # loadmodel.validate
            sign = earthquake if case.seismic.direction is SeismicDirection.EARTHQUAKE else Decimal(1)
            table = bearing_table(pier, frame, case, sign)
            add(id=case.id, name=case.name, increment=INCREMENTS[case.seismic.increment], points=(table.point,),
                direction=toward_earthquake if case.seismic.direction is SeismicDirection.EARTHQUAKE
                else ActionDirection.DOWNWARD, bearings=table)
    if EQ2 in used:
        add(id=EQ2, name=EQ2_NAME, direction=toward_earthquake, increment=Increment.INCREMENTAL,
            points=(point_load(frame, NodeRole.FOOTING_CENTROID, h=toward(self_weight.footing.force, earthquake)),),
            member_loads=self_weight_loads(frame, self_weight, earthquake))
    order = [case.id for case in cases]
    found = tuple(GenericSeismicCombination(
        number=number, name=c.name, alpha_f=alpha_f, rho_m=rho_m,
        direction=REVERSED[toward_earthquake] if c.reverse else toward_earthquake,
        cases=tuple(case for case in order if case in c.cases), ground_resistance_type=GROUND_RESISTANCE_TYPE,
        reverse=c.reverse)
        for number, (c, (rho_m, alpha_f)) in enumerate(((c, pattern) for c in combinations for pattern in PATTERNS), 1))
    return GenericSeismicResult(frame=frame, earthquake=earthquake, girder_weights=weights, self_weight=self_weight,
                                basic_cases=tuple(cases), combinations=found,
                                sections=tuple(model.sections.get(stage, ())))
