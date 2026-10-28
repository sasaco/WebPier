"""0610 Define cases, combinations and extraction groups (Example橋脚4 表2.3.2, 表2.3.3; Example2 08 pp.8-9 to 8-11).

Decision 120: the combinations are those of Example橋脚4 表2.3.2. Every safety check (列車最大, 制動最大, ロング最大,
雪最大) is made at low and at high water with the buoyancy of the level; 制動最大 and ロング最大 also with the reduced
dead loads 0.9 D1 + 0.8 D2 and the 0600 cases of the same reduction. The edge-stress (永久＋変動) and permanent checks
are made at low and at high water; the variable check takes the double-track train and impact; the damage checks take
the normal-water buoyancy. No combination takes the single-track train or impact. The order is check, water level
(low, high), placing (①②③): 48 combinations. Without snow the snow basic cases are not made, but the combinations
(their numbers and the name 雪最大) and the extractions do not change: a 雪最大 then has no snow term (decision 69).
安全性（安定） extracts the safety combinations and 短期支持性能 the edge-stress ones.

The table holds the nominal coefficients as printed. Each combination is also
resolved into actions (README 用途別解決): a component is its factor times the
printed basic action, every N, H, M and q rounded once to its digits.

The impact differs by use: the basic I (IMPACT_DOUBLE) uses the pier-body impact
coefficients of safety and restorability (decision 77), so in those
combinations the factor is the nominal coefficient (1.23, 1.35). The
serviceability 0.75 is already in the 0600 serviceability coefficient
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
from ...loadmodel import ExtractionGroup  # the 8 extraction groups of 8-11, the contract's (decision 70)
from .._exact import d, put
from ..frame import Frame, LineLoad, PointLoad
from ..reaction.train import Layout
from .actions import LAYOUT_DEPENDENT, BasicAction, BasicCase, ImpactTable, Impacts, bearing_point

FACTOR = Precision(2, "")  # factors from the load factors ρ (8-10: 1.35, 1.23, 0.75)
CONSTANT = Precision(1, "")  # fixed factors (8-10: 1.0, 1.1, 1.2; the reduced dead loads 0.9, 0.8 of 表2.3.2)
MAXIMUM_TRAIN = Decimal("1.1")  # 列車最大: 1.1 ρ (8-10: 1.231 × 1.1 -> 1.35)
SERVICE_IMPACT = Decimal("0.75")  # serviceability impact 3/4 (07 7-2), already in the 0600 service coefficient


class Usage(Enum):
    ULTIMATE = "ultimate"  # safety and restorability: ρ of safety (破壊)
    SERVICE = "service"  # serviceability and support: ρ of serviceability


class Check(Enum):
    """The 12 checks of Example橋脚4 表2.3.2, in the order made (decision 120)."""

    FAILURE_TRAIN_MAX = 1  # 列車最大
    FAILURE_BRAKING_MAX = 2  # 制動最大, 死荷重低減なし
    FAILURE_BRAKING_MAX_REDUCED = 3  # 制動最大, 死荷重低減あり
    FAILURE_RAIL_MAX = 4  # ロング最大, 死荷重低減なし
    FAILURE_RAIL_MAX_REDUCED = 5  # ロング最大, 死荷重低減あり
    FAILURE_SNOW_MAX = 6  # 雪最大 (also without snow, then with no snow term: decision 69)
    SUPPORT_LONG_TERM = 7  # 長期支持
    CRACK_PERMANENT_VARIABLE = 8  # 縁応力検討時・短期支持
    CRACK_PERMANENT = 9  # 永久作用時
    CRACK_VARIABLE = 10  # 変動作用時
    DAMAGE_TRAIN_MAX = 11
    DAMAGE_SNOW_MAX = 12  # also without snow (decision 69)


class Water(Enum):
    """The water level of a check made at low and at high water (decision 120)."""

    LOW = "低水位"
    HIGH = "高水位"


class Basis(Enum):
    BASIC = "basic"  # the basic action of the case
    SERVICE_IMPACT = "service_impact"  # the serviceability impact instead of the basic I


# The names of the extraction groups, as 8-11 prints them and FrameWeb names its pickups.
EXTRACTION_NAMES = {
    ExtractionGroup.FAILURE: "安全性（破壊）", ExtractionGroup.PERMANENT_VARIABLE: "永久＋変動",
    ExtractionGroup.PERMANENT: "永久作用", ExtractionGroup.VARIABLE: "変動作用", ExtractionGroup.DAMAGE: "使用性（損傷）",
    ExtractionGroup.STABILITY: "安全性（安定）", ExtractionGroup.SUPPORT_LONG_TERM: "長期支持性能",
    ExtractionGroup.SUPPORT_SHORT_TERM: "短期支持性能",
}


@dataclass(frozen=True)
class CombinationFactors:
    one: Printed  # 1.0
    d1_safety: Printed  # 1.1 on D1 (safety)
    d2_safety: Printed  # 1.2 on D2 (safety)
    d1_reduced: Printed  # 0.9 on D1: the reduced dead loads (decision 120)
    d2_reduced: Printed  # 0.8 on D2
    ultimate: Printed  # ρ of safety
    maximum: Printed  # 1.1 ρ: train maximum
    service: Printed  # ρ of serviceability
    service_impact: Printed  # 0.75 ρ of serviceability


@dataclass(frozen=True)
class DefineCase:
    number: int
    case: BasicCase
    signs: tuple[int, ...]  # (1,) or both directions (1, −1) for the horizontal cases
    layout: Layout | None = None  # of a LAYOUT_DEPENDENT case (decision 102)


@dataclass(frozen=True)
class ResolvedAction:
    case: BasicCase
    nominal: Printed  # coefficient of the table
    factor: Printed  # applied to the basis
    basis: Basis
    source: BasicAction  # the action the factor applies to, unscaled and in the positive direction
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...]
    reversible: bool  # horizontal: both signs (Define 13-20)


@dataclass(frozen=True)
class Combination:
    number: int  # in the order made: check, water level, then ①, ② and ③ with the train (decisions 102, 120)
    check: Check
    usage: Usage
    coefficients: tuple[Printed | None, ...]  # by basic case, in the order made (decision 69); None prints '－'
    components: tuple[ResolvedAction, ...]  # the cases with a coefficient, in case order
    layout: Layout | None = None  # 列車の配置 of a check with the train (decision 102)
    water: Water | None = None  # of a check made at low and at high water (decision 120)

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


_B = BasicCase
# 表2.3.2 by check, the coefficient of each case: "1" 1.0, "D1" 1.1, "D2" 1.2, "R1" 0.9, "R2" 0.8, "U" ρ, "X" 1.1 ρ,
# "S" ρs, "SI" 0.75 ρs. A case the pier does not make (snow) has no column (decision 69).
_TABLE: dict[Check, dict[BasicCase, str]] = {
    Check.FAILURE_TRAIN_MAX: {_B.D1: "D1", _B.D2: "D2", _B.SNOW10: "1", _B.TRAIN_DOUBLE: "X", _B.IMPACT_DOUBLE: "X",
                              _B.SAFETY_LR10_B: "1"},
    Check.FAILURE_BRAKING_MAX: {_B.D1: "D1", _B.D2: "D2", _B.SNOW10: "1", _B.TRAIN_DOUBLE: "U",
                                _B.SAFETY_LR10_BMAX: "1"},
    Check.FAILURE_BRAKING_MAX_REDUCED: {_B.D1: "R1", _B.D2: "R2", _B.SNOW10: "1", _B.TRAIN_DOUBLE: "U",
                                        _B.SAFETY_LR10_BMAX_REDUCED: "1"},
    Check.FAILURE_RAIL_MAX: {_B.D1: "D1", _B.D2: "D2", _B.SNOW10: "1", _B.TRAIN_DOUBLE: "U", _B.IMPACT_DOUBLE: "U",
                             _B.SAFETY_LR11_B: "1"},
    # 表2.3.2 cases 25〜30 print L 1.10: a misprint (cases 19〜24 and the 0600 twin take ρ), so ρ (decision 120)
    Check.FAILURE_RAIL_MAX_REDUCED: {_B.D1: "R1", _B.D2: "R2", _B.SNOW10: "1", _B.TRAIN_DOUBLE: "U",
                                     _B.IMPACT_DOUBLE: "U", _B.SAFETY_LR11_B_REDUCED: "1"},
    Check.FAILURE_SNOW_MAX: {_B.D1: "D1", _B.D2: "D2", _B.SNOW30: "1", _B.SAFETY_LR10: "1"},
    Check.SUPPORT_LONG_TERM: {_B.D1: "1", _B.D2: "1", _B.BUOYANCY_NORMAL: "1", _B.SNOW2: "1"},
    Check.CRACK_PERMANENT_VARIABLE: {_B.D1: "1", _B.D2: "1", _B.SNOW2: "1", _B.TRAIN_DOUBLE: "S",
                                     _B.IMPACT_DOUBLE: "SI", _B.SERVICE_LR10: "1"},
    Check.CRACK_PERMANENT: {_B.D1: "1", _B.D2: "1", _B.SNOW2: "1", _B.SERVICE_LR08: "1"},
    Check.CRACK_VARIABLE: {_B.TRAIN_DOUBLE: "S", _B.IMPACT_DOUBLE: "SI"},
    Check.DAMAGE_TRAIN_MAX: {_B.D1: "1", _B.D2: "1", _B.BUOYANCY_NORMAL: "1", _B.SNOW10: "1", _B.TRAIN_DOUBLE: "U",
                             _B.IMPACT_DOUBLE: "U", _B.RESTORABILITY_LR10_B: "1"},
    Check.DAMAGE_SNOW_MAX: {_B.D1: "1", _B.D2: "1", _B.BUOYANCY_NORMAL: "1", _B.SNOW30: "1",
                            _B.RESTORABILITY_LR10: "1"},
}
_SAFETY = frozenset({Check.FAILURE_TRAIN_MAX, Check.FAILURE_BRAKING_MAX, Check.FAILURE_BRAKING_MAX_REDUCED,
                     Check.FAILURE_RAIL_MAX, Check.FAILURE_RAIL_MAX_REDUCED, Check.FAILURE_SNOW_MAX})
# The checks made at low and then at high water, each with 1.0 × the buoyancy of the level (decision 120).
_BY_WATER = _SAFETY | {Check.CRACK_PERMANENT_VARIABLE, Check.CRACK_PERMANENT}
_BUOYANCY = {Water.LOW: _B.BUOYANCY_LOW, Water.HIGH: _B.BUOYANCY_HIGH}
_SERVICE_CHECKS = frozenset({Check.CRACK_PERMANENT_VARIABLE, Check.CRACK_PERMANENT, Check.CRACK_VARIABLE,
                             Check.SUPPORT_LONG_TERM})
# The checks of each group (表2.3.3): 安全性（安定） as 安全性（破壊）, 短期支持性能 as 永久＋変動 (decision 120).
EXTRACTIONS: dict[ExtractionGroup, frozenset[Enum]] = {
    ExtractionGroup.FAILURE: _SAFETY, ExtractionGroup.PERMANENT_VARIABLE: frozenset({Check.CRACK_PERMANENT_VARIABLE}),
    ExtractionGroup.PERMANENT: frozenset({Check.CRACK_PERMANENT}),
    ExtractionGroup.VARIABLE: frozenset({Check.CRACK_VARIABLE}),
    ExtractionGroup.DAMAGE: frozenset({Check.DAMAGE_TRAIN_MAX, Check.DAMAGE_SNOW_MAX}),
    ExtractionGroup.STABILITY: _SAFETY, ExtractionGroup.SUPPORT_LONG_TERM: frozenset({Check.SUPPORT_LONG_TERM}),
    ExtractionGroup.SUPPORT_SHORT_TERM: frozenset({Check.CRACK_PERMANENT_VARIABLE}),
}


def combination_factors(pier: PierInput) -> CombinationFactors:
    t = pier.train
    return CombinationFactors(
        one=CONSTANT.exact(1.0), d1_safety=CONSTANT.exact(1.1), d2_safety=CONSTANT.exact(1.2),
        d1_reduced=CONSTANT.exact(0.9), d2_reduced=CONSTANT.exact(0.8),
        ultimate=put(FACTOR, d(t.factor_ultimate)), maximum=put(FACTOR, d(t.factor_ultimate) * MAXIMUM_TRAIN),
        service=put(FACTOR, d(t.factor_service)), service_impact=put(FACTOR, d(t.factor_service) * SERVICE_IMPACT))


def define_cases(basic_cases: tuple[BasicAction, ...]) -> tuple[DefineCase, ...]:
    """One Define per basic case, with its number; the horizontal ones in both directions."""
    return tuple(DefineCase(number=basic.number, case=basic.case, signs=(1, -1) if basic.horizontal else (1,),
                            layout=basic.layout)
                 for basic in basic_cases)


def placed_extractions(combinations: tuple[Combination, ...],
                       table: Mapping[ExtractionGroup, frozenset[Enum]] = EXTRACTIONS) -> tuple[Extraction, ...]:
    """Each group's combinations: every combination made of its checks in *table* (0610's by default; 0620 passes its
    own), of each 列車の配置 and water level (0610, decisions 102, 120) or of 複線 and 単線 (0620, decision 106)."""
    return tuple(Extraction(number=group.value, group=group,
                            combinations=tuple(c.number for c in combinations if c.check in checks))
                 for group, checks in table.items())


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
        source = replace(basic, points=(bearing_point(frame, impact.n, impact.m),), line_loads=())
    else:
        basis, factor, source = Basis.BASIC, nominal, basic
    f = d(factor)
    return ResolvedAction(case=basic.case, nominal=nominal, factor=factor, basis=basis, source=source,
                          points=tuple(_scaled_point(p, f) for p in source.points),
                          line_loads=tuple(_scaled_line(line, f) for line in source.line_loads),
                          reversible=basic.horizontal)


def resolve_combinations(frame: Frame, basic_cases: tuple[BasicAction, ...], impacts: Mapping[Layout, Impacts],
                         factors: CombinationFactors) -> tuple[Combination, ...]:
    symbols: Mapping[str, Printed] = {
        "1": factors.one, "D1": factors.d1_safety, "D2": factors.d2_safety, "R1": factors.d1_reduced,
        "R2": factors.d2_reduced, "U": factors.ultimate, "X": factors.maximum, "S": factors.service,
        "SI": factors.service_impact}
    combinations: list[Combination] = []
    for check, row in _TABLE.items():
        usage = Usage.SERVICE if check in _SERVICE_CHECKS else Usage.ULTIMATE
        placed = any(case in row for case in LAYOUT_DEPENDENT)
        for water in (tuple(Water) if check in _BY_WATER else (None,)):
            printed = row if water is None else {**row, _BUOYANCY[water]: "1"}
            for layout in (tuple(Layout) if placed else (None,)):
                service_impacts = {BasicCase.IMPACT_DOUBLE: impacts[layout or Layout.BOTH].service_double}
                coefficients = tuple(None if basic.case not in printed or basic.layout not in (None, layout)
                                     else symbols[printed[basic.case]] for basic in basic_cases)
                components = tuple(
                    _resolve(basic, nominal, usage, service_impacts, frame, factors)
                    for basic, nominal in zip(basic_cases, coefficients, strict=True) if nominal is not None)
                combinations.append(Combination(number=len(combinations) + 1, check=check, usage=usage,
                                                coefficients=coefficients, components=components, layout=layout,
                                                water=water))
    return tuple(combinations)
