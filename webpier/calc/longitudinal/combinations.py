"""0610 Define cases, combinations and extraction groups (Example2 08 pp.8-9 to 8-11).

The table holds the nominal coefficients as printed. Each combination is also
resolved into actions (README 用途別解決): a component is its factor times the
printed basic action, every N, H, M and q rounded once to its digits.

The impact differs by use: the basic I (cases 11, 12) uses the girder impact
coefficients of safety and restorability (decision 26), so in those
combinations the factor is the nominal coefficient (1.23, 1.35). The
serviceability 0.75 is already in the 0600 serviceability girder coefficient
(07 7-2: 0.245 -> 0.184), so there the serviceability impact is taken and only
ρ remains (nominal 0.75 = ρ × 0.75).

Factors derived from the load factors ρ are printed with 2 decimals, like the
0600 effective factors (07 7-7: 1.231 × 1.1 = 1.3541 -> 1.35).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum

from ...core.printed import FORCE, LINE_LOAD, MOMENT, Precision, Printed
from ...inputs import PierInput
from .._exact import d, put
from ..frame import Frame, LineLoad, PointLoad
from .actions import BasicAction, BasicCase, ImpactTable, Impacts, bearing_point

FACTOR = Precision(2, "")  # factors from the load factors ρ (8-10: 1.35, 1.23, 0.75)
CONSTANT = Precision(1, "")  # fixed factors (8-10: 1.0, 1.1, 1.2)
MAXIMUM_TRAIN = Decimal("1.1")  # 列車最大: 1.1 ρ (8-10: 1.231 × 1.1 -> 1.35)
SERVICE_IMPACT = Decimal("0.75")  # serviceability impact 3/4 (07 7-2), already in the 0600 service coefficient


class Usage(Enum):
    ULTIMATE = "ultimate"  # safety and restorability: ρ of safety (破壊)
    SERVICE = "service"  # serviceability and support: ρ of serviceability


class Check(Enum):
    """The 16 combinations of 8-10, in order."""

    FAILURE_TRAIN_MAX = 1
    FAILURE_BRAKING_MAX = 2
    FAILURE_RAIL_MAX = 3
    FAILURE_SNOW_MAX = 4
    CRACK_PERMANENT_VARIABLE = 5
    CRACK_PERMANENT = 6
    CRACK_VARIABLE = 7
    DAMAGE_TRAIN_MAX = 8
    DAMAGE_SNOW_MAX = 9
    STABILITY_TRAIN_MAX = 10
    STABILITY_BRAKING_MAX = 11
    STABILITY_RAIL_MAX = 12
    STABILITY_SNOW_MAX = 13
    SUPPORT_LONG_TERM = 14
    SUPPORT_SHORT_TERM_LOW_WATER = 15
    SUPPORT_SHORT_TERM_HIGH_WATER = 16


class ExtractionGroup(Enum):
    """The 8 extraction groups of 8-11."""

    FAILURE = 1
    PERMANENT_VARIABLE = 2
    PERMANENT = 3
    VARIABLE = 4
    DAMAGE = 5
    STABILITY = 6
    SUPPORT_LONG_TERM = 7
    SUPPORT_SHORT_TERM = 8


class Basis(Enum):
    BASIC = "basic"  # the basic action of the case
    SERVICE_IMPACT = "service_impact"  # the serviceability impact instead of the basic I


@dataclass(frozen=True)
class CombinationFactors:
    one: Printed  # 1.0
    d1_safety: Printed  # 1.1 on D1 (safety)
    d2_safety: Printed  # 1.2 on D2 (safety)
    ultimate: Printed  # ρ of safety
    maximum: Printed  # 1.1 ρ: train maximum
    service: Printed  # ρ of serviceability
    service_impact: Printed  # 0.75 ρ of serviceability


@dataclass(frozen=True)
class DefineCase:
    number: int
    case: BasicCase
    signs: tuple[int, ...]  # (1,) or both directions (1, −1) for the horizontal cases


@dataclass(frozen=True)
class ResolvedAction:
    case: BasicCase
    nominal: Printed  # coefficient of the table
    factor: Printed  # applied to the basis
    basis: Basis
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...]
    reversible: bool  # horizontal: both signs (Define 13-20)


@dataclass(frozen=True)
class Combination:
    number: int
    check: Check
    usage: Usage
    coefficients: tuple[Printed | None, ...]  # by basic case 1-20; None prints '－'
    components: tuple[ResolvedAction, ...]  # the cases with a coefficient, in case order

    @property
    def signs(self) -> tuple[int, ...]:
        return (1, -1) if any(component.reversible for component in self.components) else (1,)

    def signed(self, sign: int) -> tuple[ResolvedAction, ...]:
        """The components with the horizontal actions in direction *sign*."""
        if sign == 1:
            return self.components
        return tuple(replace(c, points=tuple(_scaled_point(p, Decimal(sign)) for p in c.points)) if c.reversible
                     else c for c in self.components)

    def component(self, case: BasicCase) -> ResolvedAction:
        for component in self.components:
            if component.case is case:
                return component
        raise KeyError(case)


@dataclass(frozen=True)
class Extraction:
    number: int
    group: ExtractionGroup
    combinations: tuple[int, ...]


# 8-10 by basic case 1-20: "-" none, "1" 1.0, "D1" 1.1, "D2" 1.2, "U" ρ, "X" 1.1 ρ, "S" ρs, "SI" 0.75 ρs.
_TABLE = {
    Check.FAILURE_TRAIN_MAX: "D1 D2 - - - - 1 - - X - X - - 1 - - - - -",
    Check.FAILURE_BRAKING_MAX: "D1 D2 - - - - 1 - - U - - - - - - 1 - - -",
    Check.FAILURE_RAIL_MAX: "D1 D2 - - - - 1 - - U - U - - - 1 - - - -",
    Check.FAILURE_SNOW_MAX: "D1 D2 - - - - - 1 - - - - - - - - - 1 - -",
    Check.CRACK_PERMANENT_VARIABLE: "1 1 - - - 1 - - - S - SI - 1 - - - - - -",
    Check.CRACK_PERMANENT: "1 1 - - - 1 - - - - - - 1 - - - - - - -",
    Check.CRACK_VARIABLE: "- - - - - - - - S - SI - - - - - - - - -",
    Check.DAMAGE_TRAIN_MAX: "1 1 - - - - 1 - - U - U - - - - - - 1 -",
    Check.DAMAGE_SNOW_MAX: "1 1 - - - - - 1 - - - - - - - - - - - 1",
    Check.STABILITY_TRAIN_MAX: "D1 D2 - - 1 - 1 - - X - X - - 1 - - - - -",
    Check.STABILITY_BRAKING_MAX: "D1 D2 - - 1 - 1 - - U - - - - - - 1 - - -",
    Check.STABILITY_RAIL_MAX: "D1 D2 - - 1 - 1 - - U - U - - - 1 - - - -",
    Check.STABILITY_SNOW_MAX: "D1 D2 - - 1 - - 1 - - - - - - - - - 1 - -",
    Check.SUPPORT_LONG_TERM: "1 1 - 1 - 1 - - - - - - - - - - - - - -",
    Check.SUPPORT_SHORT_TERM_LOW_WATER: "1 1 - - 1 1 - - S - SI - - - - - - - - -",
    Check.SUPPORT_SHORT_TERM_HIGH_WATER: "1 1 1 - - 1 - - S - SI - - - - - - - - -",
}
_SERVICE_CHECKS = frozenset({Check.CRACK_PERMANENT_VARIABLE, Check.CRACK_PERMANENT, Check.CRACK_VARIABLE,
                             Check.SUPPORT_LONG_TERM, Check.SUPPORT_SHORT_TERM_LOW_WATER,
                             Check.SUPPORT_SHORT_TERM_HIGH_WATER})
_EXTRACTIONS = {
    ExtractionGroup.FAILURE: (1, 2, 3, 4), ExtractionGroup.PERMANENT_VARIABLE: (5,),
    ExtractionGroup.PERMANENT: (6,), ExtractionGroup.VARIABLE: (7,), ExtractionGroup.DAMAGE: (8, 9),
    ExtractionGroup.STABILITY: (10, 11, 12, 13), ExtractionGroup.SUPPORT_LONG_TERM: (14,),
    ExtractionGroup.SUPPORT_SHORT_TERM: (15, 16),
}


def combination_factors(pier: PierInput) -> CombinationFactors:
    t = pier.train
    return CombinationFactors(
        one=CONSTANT.exact(1.0), d1_safety=CONSTANT.exact(1.1), d2_safety=CONSTANT.exact(1.2),
        ultimate=put(FACTOR, d(t.factor_ultimate)), maximum=put(FACTOR, d(t.factor_ultimate) * MAXIMUM_TRAIN),
        service=put(FACTOR, d(t.factor_service)), service_impact=put(FACTOR, d(t.factor_service) * SERVICE_IMPACT))


def define_cases() -> tuple[DefineCase, ...]:
    return tuple(DefineCase(number=case.value, case=case, signs=(1, -1) if case.value >= 13 else (1,))
                 for case in BasicCase)


def extractions() -> tuple[Extraction, ...]:
    return tuple(Extraction(number=group.value, group=group, combinations=numbers)
                 for group, numbers in _EXTRACTIONS.items())


def _scaled_point(point: PointLoad, factor: Decimal) -> PointLoad:
    return replace(point, n=put(FORCE, factor * d(point.n)), h=put(FORCE, factor * d(point.h)),
                   m=put(MOMENT, factor * d(point.m)))


def _scaled_line(line: LineLoad, factor: Decimal) -> LineLoad:
    return replace(line, n=put(LINE_LOAD, factor * d(line.n)), h=put(LINE_LOAD, factor * d(line.h)))


def _resolve(basic: BasicAction, nominal: Printed, usage: Usage, service_impacts: Mapping[BasicCase, ImpactTable],
             frame: Frame, factors: CombinationFactors) -> ResolvedAction:
    if usage is Usage.SERVICE and basic.case in service_impacts:
        basis, factor = Basis.SERVICE_IMPACT, factors.service
        impact = service_impacts[basic.case]
        points: tuple[PointLoad, ...] = (bearing_point(frame, impact.n, impact.m),)
        lines: tuple[LineLoad, ...] = ()
    else:
        basis, factor, points, lines = Basis.BASIC, nominal, basic.points, basic.line_loads
    f = d(factor)
    return ResolvedAction(case=basic.case, nominal=nominal, factor=factor, basis=basis,
                          points=tuple(_scaled_point(p, f) for p in points),
                          line_loads=tuple(_scaled_line(line, f) for line in lines), reversible=basic.horizontal)


def resolve_combinations(frame: Frame, basic_cases: tuple[BasicAction, ...], impact: Impacts,
                         factors: CombinationFactors) -> tuple[Combination, ...]:
    symbols: Mapping[str, Printed] = {
        "1": factors.one, "D1": factors.d1_safety, "D2": factors.d2_safety, "U": factors.ultimate,
        "X": factors.maximum, "S": factors.service, "SI": factors.service_impact}
    service_impacts = {BasicCase.IMPACT_SINGLE: impact.service_single, BasicCase.IMPACT_DOUBLE: impact.service_double}
    combinations = []
    for check, row in _TABLE.items():
        usage = Usage.SERVICE if check in _SERVICE_CHECKS else Usage.ULTIMATE
        coefficients = tuple(None if symbol == "-" else symbols[symbol] for symbol in row.split())
        components = tuple(
            _resolve(basic, nominal, usage, service_impacts, frame, factors)
            for basic, nominal in zip(basic_cases, coefficients, strict=True) if nominal is not None)
        combinations.append(Combination(number=check.value, check=check, usage=usage, coefficients=coefficients,
                                        components=components))
    return tuple(combinations)
