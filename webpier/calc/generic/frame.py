"""0610 / 0620 with a load model (decision 70): the frame, its basic cases and the combinations the load model gives.

The application's cases are those of the train path (calc.longitudinal / calc.transverse ``dead_actions``): D1, D2
and the buoyancy at the high, normal and low water level, and across the track the wind on the pier body, one case per
pressure the load model lists (calc.transverse.wind). The load model's cases are its 支承作用 on the frame
(calc.bearing_actions), those the combinations of the stage use, in the load model's order.

A Define is a term's candidates: one case, or whichever governs of several (with the sign −1, the case reversed).
The Defines are numbered as the terms first use them, the combinations in the load model's order, and the extraction
groups are the 8 of 8-11 in their order, each with the combinations assigned to it. A group without a combination
gets the zero case: a case of one row of 0, which FEMPython keeps and whose pickup is 0 (2026-10-20), in one
combination 該当する組合せなし（断面力0）; a check that would divide by its Vd then names the group (decision 70).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ...core.printed import PRESSURE, Printed
from ...inputs import PierInput
from ...loadmodel import (
    D1, D2, WP_HIGH, WP_LOW, WP_NORMAL, Combination as ModelCombination, ExtractionGroup, LoadModelResult, Section,
    SpringTerm, pier_wind as wind_id,
)
from ..bearing_actions import BearingTable, bearing_table
from ..foundation import FoundationResult
from ..frame import Direction, Frame, LineLoad, NodeRole, PointLoad, build_frame, point_load
from ..longitudinal import actions as longitudinal
from ..longitudinal.combinations import Extraction
from ..materials import calculate_materials
from ..reaction import DeadReactionResult
from ..transverse import actions as transverse
from ..transverse.wind import MemberLoad, PierWind, pier_wind

ZERO = "ZERO"  # the id of the zero case
ZERO_NAME = "断面力0"
NO_COMBINATION = "該当する組合せなし（断面力0）"

# The application's cases on a frame: id, name, the case of dead_actions.
_DEAD = ((D1, "固定死荷重", "D1"), (D2, "付加死荷重", "D2"), (WP_HIGH, "浮力（高水位）", "BUOYANCY_HIGH"),
         (WP_NORMAL, "浮力（平水位）", "BUOYANCY_NORMAL"), (WP_LOW, "浮力（低水位）", "BUOYANCY_LOW"))


@dataclass(frozen=True)
class FrameCase:
    number: int  # its load case in FrameWeb
    id: str
    name: str
    spring: SpringTerm
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...] = ()
    member_loads: tuple[MemberLoad, ...] = ()  # the wind on the pier body
    bearings: BearingTable | None = None  # a load model's case: its 支承作用 on this frame
    zero: bool = False  # the zero case of the groups without a combination


@dataclass(frozen=True)
class FrameDefine:
    number: int
    candidates: tuple[tuple[str, int], ...]  # (case id, sign): one of them governs


@dataclass(frozen=True)
class FrameTerm:
    define: int
    factor: Printed


@dataclass(frozen=True)
class FrameCombination:
    number: int
    name: str
    terms: tuple[FrameTerm, ...]
    groups: frozenset[ExtractionGroup]
    zero: bool = False  # 該当する組合せなし（断面力0）


@dataclass(frozen=True)
class GenericFrameResult:
    frame: Frame
    dead: longitudinal.DeadActions | transverse.DeadActions  # D1, D2 and the buoyancy as the tables print them
    winds: tuple[PierWind, ...]  # 0620: the wind on the pier body of each pressure
    basic_cases: tuple[FrameCase, ...]
    define_cases: tuple[FrameDefine, ...]
    combinations: tuple[FrameCombination, ...]
    extractions: tuple[Extraction, ...]  # the 8 groups of 8-11
    sections: tuple[Section, ...] = field(default=())  # the load model's sections of this stage

    def basic(self, case: str) -> FrameCase:
        return next(item for item in self.basic_cases if item.id == case)

    @property
    def empty(self) -> frozenset[ExtractionGroup]:
        """The groups without a combination of the load model."""
        return frozenset(group for c in self.combinations if c.zero for group in c.groups)


def printed_factor(value: Decimal) -> Printed:
    """A factor with the digits it is written with (1.35 → 2 decimals)."""
    return Printed(float(value), max(0, -value.as_tuple().exponent), "")  # type: ignore[operator]


def _defines(combinations: tuple[ModelCombination, ...]) -> dict[tuple[tuple[str, int], ...], int]:
    numbers: dict[tuple[tuple[str, int], ...], int] = {}
    for combination in combinations:
        for term in combination.terms:
            numbers.setdefault(tuple((c.case, c.sign) for c in term.candidates), len(numbers) + 1)
    return numbers


def calculate_generic_frame(pier: PierInput, foundation: FoundationResult, reaction: DeadReactionResult,
                            model: LoadModelResult, direction: Direction, stage: str) -> GenericFrameResult:
    frame = build_frame(pier, reaction.self_weight, foundation, calculate_materials(pier), direction)
    along = direction is Direction.LONGITUDINAL
    dead = (longitudinal if along else transverse).dead_actions(pier, frame, reaction.dead, reaction.self_weight)
    combinations = model.longitudinal if along else model.transverse
    cases: list[FrameCase] = []

    def add(**values) -> None:
        cases.append(FrameCase(number=len(cases) + 1, **values))

    kinds = longitudinal.BasicCase if along else transverse.BasicCase
    for case, name, kind in _DEAD:
        add(id=case, name=name, spring=SpringTerm.LONG, points=dead.points[kinds[kind]],
            line_loads=dead.lines if case == D1 else ())
    winds = () if along else tuple(pier_wind(pier, frame, PRESSURE(float(p))) for p in model.pier_wind_pressures)
    for number, wind in enumerate(winds, 1):
        add(id=wind_id(number), name=f"躯体の風（{wind.pressure.value:.1f} kN/m2）", spring=SpringTerm.SHORT,
            points=(), member_loads=wind.member_loads)
    used = {c.case for combination in combinations for term in combination.terms for c in term.candidates}
    for case in model.cases:
        if case.id in used:
            table = bearing_table(pier, frame, case)
            add(id=case.id, name=case.name, spring=case.spring, points=table.points, bearings=table)
    defines = _defines(combinations)
    found = [FrameCombination(number, c.name, tuple(FrameTerm(defines[tuple((x.case, x.sign) for x in t.candidates)],
                                                              printed_factor(t.factor)) for t in c.terms), c.groups)
             for number, c in enumerate(combinations, 1)]
    empty = frozenset(ExtractionGroup) - {group for c in combinations for group in c.groups}
    if empty:
        add(id=ZERO, name=ZERO_NAME, spring=SpringTerm.LONG, points=(point_load(frame, NodeRole.CAP_TOP),), zero=True)
        defines[((ZERO, 1),)] = len(defines) + 1
        found.append(FrameCombination(len(found) + 1, NO_COMBINATION,
                                      (FrameTerm(len(defines), printed_factor(Decimal("1.0"))),), empty, zero=True))
    extractions = tuple(Extraction(number=group.value, group=group,
                                   combinations=tuple(c.number for c in found if group in c.groups))
                        for group in ExtractionGroup)
    return GenericFrameResult(
        frame=frame, dead=dead, winds=winds, basic_cases=tuple(cases),
        define_cases=tuple(FrameDefine(number, candidates) for candidates, number in defines.items()),
        combinations=tuple(found), extractions=extractions, sections=tuple(model.sections.get(stage, ())))
