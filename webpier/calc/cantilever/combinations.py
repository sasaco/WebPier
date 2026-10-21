"""The design action combinations of the cantilever beam (0900 13.2, decision 59; Example2 13-30 to 13-37) and the
section forces each check of 0910 is given (the WDJ force table, decision 59).

The 31 cases are a program table, as Example2 13-30 to 13-37 have them: 1〜18 安全性（破壊）, 19〜22 使用性（損傷）,
23〜24 復旧性（地震時）, 25〜28 耐久性 and 29〜31 安全性（疲労）. A case multiplies the totals of each action
(actions.Action: N, Md, Mt) by its factor and sums the printed products (ADR-0003); the design shear force Vd is N.
The factor of the train and its impact is ρ × γ at the printed digits of 0600 (FACTOR: 1.231 × 1.1 → 1.35,
1.231 × 1.0 → 1.23; 使用性 ρ = 1.0), that of the vehicle lateral load ρu × γ; the others are written as the table
prints them. Not reproduced from the reference: its 使用性 impact copied from the 安全性 impact (13-26 (b),
ADR-0001).

Both cantilevers are combined, and for each row of Capacita's force table (its limit state) the governing case of
either side is adopted per check: the largest |Md| for bending, the largest Vd for shear and the largest Mt for
torsion, each with the Md, Vd and Mt of that case; equal values keep the left side and the earlier case (decision 59).
Md is written negative to Capacita (tension at the top of the beam).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ...core.printed import FORCE, MOMENT, Printed
from ...inputs import PierInput
from .._exact import d, put, total
from ..reaction.longitudinal import FACTOR, LongitudinalCase, Snow
from .actions import D1, D2, EQ_TRANSVERSE, Action, ActionKey, Group
from .bearings import COMBINATIONS
from .geometry import Side
from .loads import Loading, Wind



def factor(text: str) -> Printed:
    """A factor with the digits it is written with ("1.35" → 2 decimals)."""
    value = Decimal(text)
    return Printed(float(value), max(0, -value.as_tuple().exponent), "")


ONE, SAFETY_D1, SAFETY_D2 = factor("1.0"), factor("1.1"), factor("1.2")
GAMMA_HIGH = factor("1.1")  # γ of the leading variable action (L + I, or LF)
WIND_LEADING = factor("1.2")
COLUMNS = ("D1", "D2", "S", "L", "I", "LF", "W", "LR+B", "EQ")  # of the combination tables


class LimitState(Enum):
    SAFETY = "安全性(破壊)"
    SERVICEABILITY_DAMAGE = "使用性(損傷)"
    RESTORABILITY_EQ = "復旧性(地震時)"
    DURABILITY = "耐久性"
    FATIGUE = "安全性(疲労)"


@dataclass(frozen=True)
class TrainTerm:
    loading: Loading | None  # None: the seismic train
    group: Group  # the load factor ρ and the impact
    gamma: Printed
    impact: bool


@dataclass(frozen=True)
class CaseDefinition:
    number: int
    state: LimitState
    remark: str  # 備考: 列車最大, 車横最大, 風最大, 雪最大, 制動最大, ロング最大, 縁応力度
    d1: Printed | None
    d2: Printed | None
    snow: Snow | None
    train: TrainTerm | None
    lateral: Printed | None  # γ of LF (ρu applied)
    wind: tuple[Wind, Printed] | None
    bearing: LongitudinalCase | None  # the LR + B combination whose bearing forces twist the beam
    eq: str | None  # 直角 (the inertia across the track) or 線路 (the bearing forces along it)

    @property
    def note(self) -> str:
        """摘要: the loading, the direction, or 永久作用."""
        if self.eq is not None:
            return "線路直角方向" if self.eq == "直角" else "線路方向"
        if self.train is not None and self.train.loading is not None:
            return self.train.loading.value
        return "永久作用" if self.state is LimitState.DURABILITY else ""


def _train(loading: Loading, gamma: Printed, group: Group = Group.ULTIMATE, impact: bool = True) -> TrainTerm:
    return TrainTerm(loading, group, gamma, impact)


def _definitions() -> tuple[CaseDefinition, ...]:
    found: list[CaseDefinition] = []

    def add(state: LimitState, remark: str, d1, d2, snow, train=None, lateral=None, wind=None, bearing=None,
            eq=None) -> None:
        found.append(CaseDefinition(len(found) + 1, state, remark, d1, d2, snow, train, lateral, wind, bearing, eq))

    S = LimitState.SAFETY
    for loading in Loading:  # 1〜3: the train leads
        add(S, "列車最大", SAFETY_D1, SAFETY_D2, Snow.S10, _train(loading, GAMMA_HIGH), ONE, (Wind.WITH_TRAIN, ONE))
    for loading in Loading:  # 4〜6: the vehicle lateral load leads
        add(S, "車横最大", SAFETY_D1, SAFETY_D2, Snow.S10, _train(loading, ONE), GAMMA_HIGH, (Wind.WITH_TRAIN, ONE))
    add(S, "風最大", SAFETY_D1, SAFETY_D2, Snow.S2, wind=(Wind.WITHOUT_TRAIN, WIND_LEADING))  # 7
    add(S, "雪最大", SAFETY_D1, SAFETY_D2, Snow.S30)  # 8
    for loading in Loading:  # 9〜11: 1.0LR + 1.23B
        add(S, "列車最大", SAFETY_D1, SAFETY_D2, Snow.S10, _train(loading, GAMMA_HIGH),
            bearing=LongitudinalCase.SAFETY_LR10_B10)
    for loading in Loading:  # 12〜14: 1.0LR + 1.35B, the train without impact
        add(S, "制動最大", SAFETY_D1, SAFETY_D2, Snow.S10, _train(loading, ONE, impact=False),
            bearing=LongitudinalCase.SAFETY_LR10_B11)
    for loading in Loading:  # 15〜17: 1.1LR + 1.23B, no snow
        add(S, "ロング最大", SAFETY_D1, SAFETY_D2, None, _train(loading, ONE), bearing=LongitudinalCase.SAFETY_LR11_B10)
    add(S, "雪最大", SAFETY_D1, SAFETY_D2, Snow.S30, bearing=LongitudinalCase.SAFETY_LR10)  # 18
    R = LimitState.SERVICEABILITY_DAMAGE
    for loading in Loading:  # 19〜21
        add(R, "列車最大", ONE, ONE, Snow.S10, _train(loading, ONE), ONE, (Wind.WITH_TRAIN, ONE))
    add(R, "雪最大", ONE, ONE, Snow.S30)  # 22
    seismic = TrainTerm(None, Group.ULTIMATE, ONE, False)
    add(LimitState.RESTORABILITY_EQ, "〃", ONE, ONE, Snow.S2, seismic, eq="直角")  # 23
    add(LimitState.RESTORABILITY_EQ, "〃", ONE, ONE, Snow.S2, seismic, eq="線路")  # 24
    for loading in Loading:  # 25〜27
        add(LimitState.DURABILITY, "縁応力度", ONE, ONE, Snow.S2, _train(loading, ONE, Group.SERVICE))
    add(LimitState.DURABILITY, "縁応力度", ONE, ONE, Snow.S2)  # 28: 永久作用
    for loading in Loading:  # 29〜31: the variable actions alone
        add(LimitState.FATIGUE, "〃", None, None, None, _train(loading, ONE, Group.SERVICE))
    return tuple(found)


DEFINITIONS = _definitions()


@dataclass(frozen=True)
class Contribution:
    column: str  # one of COLUMNS
    factor: str  # as the table prints it: 1.1, 1.0S10, 1.0LR+1.23B …
    n: Printed
    md: Printed
    mt: Printed


@dataclass(frozen=True)
class CaseResult:
    definition: CaseDefinition
    contributions: tuple[Contribution, ...]
    n: Printed  # Σ N = Vd
    md: Printed
    mt: Printed

    @property
    def number(self) -> int:
        return self.definition.number

    def contribution(self, column: str) -> Contribution | None:
        return next((item for item in self.contributions if item.column == column), None)


def _factor_text(value: Printed) -> str:
    return f"{value.value:.{value.digits}f}"


def _scaled(column: str, text: str, by: Printed, action: Action) -> Contribution:
    return Contribution(column, text, put(FORCE, d(action.n) * d(by)), put(MOMENT, d(action.md) * d(by)),
                        put(MOMENT, d(action.mt) * d(by)))


def train_factor(pier: PierInput, term: TrainTerm) -> Printed:
    """ρ × γ at the printed digits (0600 FACTOR); the seismic train has no ρ."""
    if term.loading is None:
        return put(FACTOR, d(term.gamma))
    rho = pier.train.factor_ultimate if term.group is Group.ULTIMATE else pier.train.factor_service
    return put(FACTOR, d(rho) * d(term.gamma))


def evaluate(pier: PierInput, actions: Mapping[ActionKey, Action], definition: CaseDefinition,
             bearing_labels: Mapping[LongitudinalCase, str]) -> CaseResult:
    """One case from the action totals."""
    parts: list[Contribution] = []
    if definition.d1 is not None:
        parts.append(_scaled("D1", _factor_text(definition.d1), definition.d1, actions[D1]))
    if definition.d2 is not None:
        parts.append(_scaled("D2", _factor_text(definition.d2), definition.d2, actions[D2]))
    if definition.snow is not None and ActionKey.snow(definition.snow) in actions:  # no snow action: decision 69
        parts.append(_scaled("S", f"1.0{definition.snow.name}", ONE, actions[ActionKey.snow(definition.snow)]))
    if (term := definition.train) is not None:
        factor = train_factor(pier, term)
        parts.append(_scaled("L", _factor_text(factor), factor, actions[ActionKey.train(term.loading)]))
        if term.impact:
            assert term.loading is not None
            parts.append(_scaled("I", _factor_text(factor), factor, actions[ActionKey.impact(term.group, term.loading)]))
    if definition.lateral is not None:
        assert definition.train is not None and definition.train.loading is not None
        factor = put(FACTOR, d(pier.train.factor_ultimate) * d(definition.lateral))
        parts.append(_scaled("LF", _factor_text(factor), factor, actions[ActionKey.lateral(definition.train.loading)]))
    if definition.wind is not None:
        kind, gamma = definition.wind
        parts.append(_scaled("W", _factor_text(gamma), gamma, actions[ActionKey.wind(kind)]))
    if definition.bearing is not None:
        parts.append(_scaled("LR+B", bearing_labels[definition.bearing].replace(" ", ""), ONE,
                             actions[ActionKey.bearing(definition.bearing)]))
    if definition.eq == "直角":
        parts.append(_scaled("EQ", "1.0", ONE, actions[EQ_TRANSVERSE]))
    elif definition.eq == "線路":
        parts.append(_scaled("EQ", "1.0", ONE, actions[ActionKey.bearing(None)]))
    return CaseResult(definition, tuple(parts), put(FORCE, total(part.n for part in parts)),
                      put(MOMENT, total(part.md for part in parts)), put(MOMENT, total(part.mt for part in parts)))


def evaluate_all(pier: PierInput, actions: Sequence[Action],
                 bearing_labels: Mapping[LongitudinalCase, str]) -> tuple[CaseResult, ...]:
    by_key = {action.key: action for action in actions}
    assert set(COMBINATIONS) <= set(bearing_labels)
    return tuple(evaluate(pier, by_key, definition, bearing_labels) for definition in DEFINITIONS)


# --- the section forces of each check (Capacita's force table) ------------------------------------------------------


class Quantity(Enum):
    BENDING = "曲げ"
    SHEAR = "せん断"
    TORSION = "ねじり"


@dataclass(frozen=True)
class ForceRow:
    """One row of Capacita's force table: its limit state id, title, the checks it serves and the cases it pools."""

    id: int
    title: str
    quantities: tuple[Quantity, ...]
    pool: Callable[[CaseDefinition], bool]


def _state(*states: LimitState) -> Callable[[CaseDefinition], bool]:
    return lambda definition: definition.state in states


def _permanent(definition: CaseDefinition) -> bool:
    return definition.state is LimitState.DURABILITY and definition.train is None


def _variable(definition: CaseDefinition) -> bool:
    return definition.state is LimitState.DURABILITY and definition.train is not None


ALL = (Quantity.BENDING, Quantity.SHEAR, Quantity.TORSION)
FORCE_ROWS = (
    ForceRow(0, "耐久性 縁応力度検討用", ALL, _state(LimitState.DURABILITY)),
    ForceRow(1, "耐久性（永久荷重）", ALL, _permanent),
    ForceRow(2, "耐久性（変動荷重）", (Quantity.SHEAR,), _state(LimitState.FATIGUE)),
    ForceRow(3, "安全性（疲労破壊）永久作用", (Quantity.BENDING, Quantity.SHEAR), _permanent),
    ForceRow(4, "安全性（疲労破壊）永久＋変動", (Quantity.BENDING, Quantity.SHEAR), _variable),
    ForceRow(5, "安全性（破壊）", ALL, _state(LimitState.SAFETY)),
    ForceRow(6, "使用性（損傷）", ALL, _state(LimitState.SERVICEABILITY_DAMAGE)),
    ForceRow(7, "復旧性（損傷）地震時", ALL, _state(LimitState.RESTORABILITY_EQ)),
)


@dataclass(frozen=True)
class Selection:
    row: int  # the id of the ForceRow
    title: str  # its title
    quantity: Quantity
    side: Side
    case: CaseResult  # the governing case: its md, n (= Vd) and mt are written together

    @property
    def md(self) -> Printed:
        return self.case.md

    @property
    def vd(self) -> Printed:
        return self.case.n

    @property
    def mt(self) -> Printed:
        return self.case.mt


def _measure(quantity: Quantity, case: CaseResult) -> float:
    if quantity is Quantity.BENDING:
        return abs(case.md.value)
    return case.n.value if quantity is Quantity.SHEAR else case.mt.value


def adopt(cases: Mapping[Side, Sequence[CaseResult]]) -> tuple[Selection, ...]:
    """The governing case of either cantilever for each row and check; the left side and the earlier case win ties."""
    found = []
    for row in FORCE_ROWS:
        pooled = [(side, case) for side in Side if side in cases for case in cases[side] if row.pool(case.definition)]
        for quantity in row.quantities:
            side, case = max(pooled, key=lambda item: _measure(quantity, item[1]))
            found.append(Selection(row.id, row.title, quantity, side, case))
    return tuple(found)
