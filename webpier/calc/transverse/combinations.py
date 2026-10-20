"""0620 Define cases, combinations and extraction groups (Example2 09 pp.9-13 to 9-15).

The coefficient table of 9-14 addresses the 15 Define cases, not the 17 basic
cases, and holds the nominal coefficients as printed. Define 9 (single-track
train) and 11 (single-track impact) each have the up and down basic cases as
alternatives; Define 13 to 15 (vehicle lateral, wind with and without the
train) have both signs. Each combination is resolved into actions per
alternative: a component is its factor times the printed basic action, every
N, H, M, q and wind line load rounded once to its digits.

A choice of the combination (``Combination.variants``) takes one track for all
its single-track components, so an up train never goes with a down impact, and
each reversible horizontal component in either sign independently (decision 35).

On a curve the centrifugal load adds Define 16 (single track: up or down) and
17 (double track), with the coefficient of L single and L double of the same
combination: it enters exactly the combinations that hold L, on the track of L
(decision 33). It acts toward the outside of the curve only, so it has one sign.

As in 0610, the basic impact uses the girder coefficients of safety and
restorability (decision 26), so there the factor is the nominal coefficient;
in the serviceability combinations the 0.75 is already in the 0600
serviceability girder coefficient, and only ρ remains. The vehicle lateral
load is 0.2 P without ρf (07 7-14), so it takes ρ (1.23) or 1.1 ρ (1.35) of
9-14 like the train.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from itertools import product

from ...core.printed import FORCE, LINE_LOAD, MOMENT, Printed
from .._exact import d, put
from ..frame import Frame, LineLoad, PointLoad
from ..longitudinal.actions import bearing_point
from ..longitudinal.combinations import CONSTANT, Basis, CombinationFactors, Usage
from .actions import IMPACT_CASES, TRACKS, BasicAction, BasicCase, ImpactSet, Track
from .wind import MemberLoad

WIND_SAFETY = CONSTANT.exact(1.2)  # W2 in 風最大 (9-14 combinations 3 and 12)


class Define(Enum):
    """The 15 Define cases of 9-13, by number."""

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
    LATERAL = 13
    WIND_WITH_TRAIN = 14
    WIND_WITHOUT_TRAIN = 15
    CENTRIFUGAL_SINGLE = 16  # only on a curve (decision 33)
    CENTRIFUGAL_DOUBLE = 17


_DEFINE_CASES = {
    Define.TRAIN_SINGLE: (BasicCase.TRAIN_UP, BasicCase.TRAIN_DOWN),
    Define.TRAIN_DOUBLE: (BasicCase.TRAIN_DOUBLE,),
    Define.IMPACT_SINGLE: (BasicCase.IMPACT_UP, BasicCase.IMPACT_DOWN),
    Define.IMPACT_DOUBLE: (BasicCase.IMPACT_DOUBLE,),
    Define.LATERAL: (BasicCase.LATERAL,),
    Define.WIND_WITH_TRAIN: (BasicCase.WIND_WITH_TRAIN,),
    Define.WIND_WITHOUT_TRAIN: (BasicCase.WIND_WITHOUT_TRAIN,),
    Define.CENTRIFUGAL_SINGLE: (BasicCase.CENTRIFUGAL_UP, BasicCase.CENTRIFUGAL_DOWN),
    Define.CENTRIFUGAL_DOUBLE: (BasicCase.CENTRIFUGAL_DOUBLE,),
}
_CENTRIFUGAL = {Define.CENTRIFUGAL_SINGLE: Define.TRAIN_SINGLE, Define.CENTRIFUGAL_DOUBLE: Define.TRAIN_DOUBLE}
_REVERSIBLE = frozenset({Define.LATERAL, Define.WIND_WITH_TRAIN, Define.WIND_WITHOUT_TRAIN})


class Check(Enum):
    """The 16 combinations of 9-14, in order."""

    FAILURE_TRAIN_MAX = 1
    FAILURE_LATERAL_MAX = 2
    FAILURE_WIND_MAX = 3
    FAILURE_SNOW_MAX = 4
    CRACK_PERMANENT_VARIABLE = 5
    CRACK_PERMANENT = 6
    CRACK_VARIABLE = 7
    DAMAGE_TRAIN_MAX = 8
    DAMAGE_SNOW_MAX = 9
    STABILITY_TRAIN_MAX = 10
    STABILITY_LATERAL_MAX = 11
    STABILITY_WIND_MAX = 12
    STABILITY_SNOW_MAX = 13
    SUPPORT_LONG_TERM = 14
    SUPPORT_SHORT_TERM_LOW_WATER = 15
    SUPPORT_SHORT_TERM_HIGH_WATER = 16


@dataclass(frozen=True)
class DefineCase:
    number: int  # 9-13 No: the position among the Define cases made (decision 69)
    define: Define
    cases: tuple[BasicCase, ...]  # alternatives: up and down for Define 9 and 11
    signs: tuple[int, ...]  # (1,) or both directions (1, −1) for Define 13-15


@dataclass(frozen=True)
class ResolvedAction:
    case: BasicCase
    nominal: Printed  # coefficient of the table
    factor: Printed  # applied to the basis
    basis: Basis
    source: BasicAction  # the action the factor applies to, unscaled and in the positive direction
    sign: int  # 1, or −1 for the reversed horizontal action
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...]
    member_loads: tuple[MemberLoad, ...]

    @property
    def track(self) -> Track | None:
        return TRACKS.get(self.case)


@dataclass(frozen=True)
class Component:
    define: Define
    nominal: Printed
    alternatives: tuple[ResolvedAction, ...]  # by basic case, then sign


@dataclass(frozen=True)
class Combination:
    number: int
    check: Check
    usage: Usage
    coefficients: tuple[Printed | None, ...]  # by Define case, in the order made; None prints '－'
    components: tuple[Component, ...]  # the Define cases with a coefficient, in order

    def variants(self) -> tuple[tuple[ResolvedAction, ...], ...]:
        """Every choice of one alternative per component with a single track throughout."""
        single = (Track.UP, Track.DOWN)
        return tuple(choice for choice in product(*(c.alternatives for c in self.components))
                     if len({a.track for a in choice if a.track in single}) <= 1)

    def component(self, define: Define) -> Component:
        for component in self.components:
            if component.define is define:
                return component
        raise KeyError(define)


# 9-14 by Define case 1-15: "-" none, "1" 1.0, "D1" 1.1, "D2" 1.2, "W" 1.2 (wind), "U" ρ, "X" 1.1 ρ, "S" ρs,
# "SI" 0.75 ρs.
_TABLE = {
    Check.FAILURE_TRAIN_MAX: "D1 D2 - - - - 1 - - X - X U 1 -",
    Check.FAILURE_LATERAL_MAX: "D1 D2 - - - - 1 - - U - U X 1 -",
    Check.FAILURE_WIND_MAX: "D1 D2 - - - 1 - - - - - - - - W",
    Check.FAILURE_SNOW_MAX: "D1 D2 - - - - - 1 - - - - - - -",
    Check.CRACK_PERMANENT_VARIABLE: "1 1 - - - 1 - - - S - SI - - -",
    Check.CRACK_PERMANENT: "1 1 - - - 1 - - - - - - - - -",
    Check.CRACK_VARIABLE: "- - - - - - - - S - SI - - - -",
    Check.DAMAGE_TRAIN_MAX: "1 1 - - - - 1 - - U - U U 1 -",
    Check.DAMAGE_SNOW_MAX: "1 1 - - - - - 1 - - - - - 1 -",  # W1 without the train, as printed (notes item 9)
    Check.STABILITY_TRAIN_MAX: "D1 D2 - - 1 - 1 - - X - X U 1 -",
    Check.STABILITY_LATERAL_MAX: "D1 D2 - - 1 - 1 - - U - U X 1 -",
    Check.STABILITY_WIND_MAX: "D1 D2 - - 1 1 - - - - - - - - W",
    Check.STABILITY_SNOW_MAX: "D1 D2 - - 1 - - 1 - - - - - - -",
    Check.SUPPORT_LONG_TERM: "1 1 - 1 - 1 - - - - - - - - -",
    Check.SUPPORT_SHORT_TERM_LOW_WATER: "1 1 - - 1 1 - - S - SI - - - -",
    Check.SUPPORT_SHORT_TERM_HIGH_WATER: "1 1 1 - - 1 - - S - SI - - - -",
}
_SERVICE_CHECKS = frozenset({Check.CRACK_PERMANENT_VARIABLE, Check.CRACK_PERMANENT, Check.CRACK_VARIABLE,
                             Check.SUPPORT_LONG_TERM, Check.SUPPORT_SHORT_TERM_LOW_WATER,
                             Check.SUPPORT_SHORT_TERM_HIGH_WATER})


def define_cases(basic_cases: tuple[BasicAction, ...]) -> tuple[DefineCase, ...]:
    """The Define cases whose basic cases are made (centrifugal on a curve, snow with snow: decisions 33, 69),
    numbered in order."""
    made = {basic.case for basic in basic_cases}
    cases = {define: _DEFINE_CASES.get(define, (BasicCase(define.value),)) for define in Define}
    defines = [define for define in Define if set(cases[define]) <= made]
    return tuple(DefineCase(number=number, define=define, cases=cases[define],
                            signs=(1, -1) if define in _REVERSIBLE else (1,))
                 for number, define in enumerate(defines, 1))


def _scaled_point(point: PointLoad, factor: Decimal, sign: Decimal) -> PointLoad:
    return replace(point, n=put(FORCE, factor * d(point.n)), h=put(FORCE, sign * factor * d(point.h)),
                   m=put(MOMENT, sign * factor * d(point.m)))


def _scaled_line(line: LineLoad, factor: Decimal) -> LineLoad:
    return replace(line, n=put(LINE_LOAD, factor * d(line.n)), h=put(LINE_LOAD, factor * d(line.h)))


def _scaled_member(load: MemberLoad, factor: Decimal) -> MemberLoad:
    return replace(load, h_start=put(LINE_LOAD, factor * d(load.h_start)), h_end=put(LINE_LOAD, factor * d(load.h_end)))


def _resolve(basic: BasicAction, sign: int, nominal: Printed, usage: Usage, service: ImpactSet, frame: Frame,
             factors: CombinationFactors) -> ResolvedAction:
    if usage is Usage.SERVICE and basic.case in IMPACT_CASES:
        basis, factor = Basis.SERVICE_IMPACT, factors.service
        impact = service.table(basic.track)  # type: ignore[arg-type]
        source = replace(basic, points=(bearing_point(frame, impact.n, impact.m),))
    else:
        basis, factor, source = Basis.BASIC, nominal, basic
    f, s = d(factor), Decimal(sign)
    return ResolvedAction(case=basic.case, nominal=nominal, factor=factor, basis=basis, source=source, sign=sign,
                          points=tuple(_scaled_point(p, f, s) for p in source.points),
                          line_loads=tuple(_scaled_line(line, f) for line in source.line_loads),
                          member_loads=tuple(_scaled_member(m, s * f) for m in source.member_loads))


def resolve_combinations(frame: Frame, basic_cases: tuple[BasicAction, ...], defines: tuple[DefineCase, ...],
                         service: ImpactSet, factors: CombinationFactors) -> tuple[Combination, ...]:
    symbols: Mapping[str, Printed] = {
        "1": factors.one, "D1": factors.d1_safety, "D2": factors.d2_safety, "W": WIND_SAFETY, "U": factors.ultimate,
        "X": factors.maximum, "S": factors.service, "SI": factors.service_impact}
    made = {basic.case: basic for basic in basic_cases}
    combinations = []
    for check, row in _TABLE.items():
        usage = Usage.SERVICE if check in _SERVICE_CHECKS else Usage.ULTIMATE
        printed = dict(zip(Define, row.split(), strict=False))  # Define 1-15; the cases not made have no column (decision 69)
        printed |= {centrifugal: printed[train] for centrifugal, train in _CENTRIFUGAL.items()}
        coefficients = tuple(None if printed[d.define] == "-" else symbols[printed[d.define]] for d in defines)
        components = tuple(
            Component(define=define.define, nominal=nominal, alternatives=tuple(
                _resolve(made[case], sign, nominal, usage, service, frame, factors)
                for case in define.cases for sign in define.signs))
            for define, nominal in zip(defines, coefficients, strict=True) if nominal is not None)
        combinations.append(Combination(number=check.value, check=check, usage=usage, coefficients=coefficients,
                                        components=components))
    return tuple(combinations)


__all__ = ["Check", "Combination", "Component", "Define", "DefineCase", "ResolvedAction", "WIND_SAFETY",
           "define_cases", "resolve_combinations"]
