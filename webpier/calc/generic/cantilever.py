"""0900 with a load model (decision 70): the actions on the cantilevers from the 支承作用, the load model's
combinations and the governing case of each row of Capacita's force table.

The geometry is that of the train path (calc.cantilever.geometry): the cantilevers that carry a bearing, X and e of
each bearing on them, Y and Σxi² of each girder. Every basic case the combinations use is an action of each cantilever
(calc.cantilever.actions ``Action``), its rows in this order:

- the vertical force N of each bearing on the cantilever: Md = N·X, Mt = N·e;
- the horizontal forces across the track of each girder, M = Σ H × y of its bearings (each row printed), which load
  each of its bearings with M·|xi| / Σxi² (calc.cantilever.loads, a magnitude taken downward): Md and Mt as N;
- the horizontal force along the track of each bearing on the cantilever: Mt = H·Y.

The application's D1 is the train path's (the bearings' D1 with the self weight of the cantilever), D2 its D2. A
combination multiplies the totals of each action by its factor, the 最大応答震度 of the direction it names read from
Aggre-SE (``complete_generic_cantilever``), and sums the printed products (ADR-0003). A row of the force table takes,
for each check, the governing combination of either cantilever among those the load model assigns to it (as
``adopt``); a row without one is the zero case 該当する組合せなし（断面力0）, which Capacita skips. The row 8 最小鉄筋量
(decision 73) has no CantileverRow of its own: it takes the combinations of 耐久性（永久荷重） (the row 1), the
permanent action as the train path's case 28.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from ...core.printed import FORCE, LENGTH, MOMENT, Printed
from ...inputs import PierInput
from ...loadmodel import (
    D1, D2, BasicCase, BearingRef, CantileverCombination, FrameDirection, LoadModelResult,
    MaxResponse as MaxResponseTerm, Section, Side as BearingSide,
)
from .._exact import d, put, total
from ..cantilever.actions import Action, ActionKey, Row, _action, _dead, _vertical_row
from ..cantilever.combinations import FORCE_ROWS, Contribution, Quantity, Selection, _factor_text, _measure
from ..cantilever import beam_cracking_moment, cantilever_sides
from ..cantilever.crack import Cracking, CrackingMoment, cracking
from ..cantilever.geometry import CantileverBearing, Geometry, GirderBearings, Side, numbered
from ..cantilever.loads import torque_verticals
from ..cantilever.response import MaxResponse
from ..moving_load import Girder
from ..reaction import DeadReactionResult

NO_COMBINATION = "該当する組合せなし（断面力0）"
BEARING = "支承作用"  # the row labels of an action table (its title is the case's name)
ACROSS = "直角方向 H"  # the vertical forces of the girder's moment Σ H × y across the track
ALONG = "線路方向 H"
_GIRDERS = {BearingSide.ORIGIN: Girder.ORIGIN, BearingSide.END: Girder.END}


@dataclass(frozen=True)
class GenericCantileverBasis:
    """What the input, 0600 and the load model decide, before the 最大応答震度 is known."""

    girders: dict[Girder, GirderBearings]
    sides: dict[Side, Geometry]  # the cantilevers that carry a bearing, left first
    cases: tuple[BasicCase, ...]  # the load model's cases the combinations use, in its order
    combinations: tuple[CantileverCombination, ...]
    cracking_moment: CrackingMoment
    sections: tuple[Section, ...] = ()  # the load model's sections of 0900


@dataclass(frozen=True)
class GenericCase:
    """A combination of the load model on one cantilever (as combinations.CaseResult)."""

    number: int
    name: str
    rows: frozenset[int]  # the rows of the force table it is assigned to
    contributions: tuple[Contribution, ...]  # column: the case id
    n: Printed  # Σ N = Vd
    md: Printed
    mt: Printed


@dataclass(frozen=True)
class GenericSide:
    geometry: Geometry
    actions: tuple[Action, ...]
    cases: tuple[GenericCase, ...]


@dataclass(frozen=True)
class GenericCantileverResult:
    basis: GenericCantileverBasis
    longitudinal: MaxResponse  # the 最大応答震度 along the track (0711)
    transverse: MaxResponse  # across it (0721)
    sides: dict[Side, GenericSide]
    selections: tuple[Selection, ...]
    cracking: Cracking

    def selection(self, row: int, quantity: Quantity) -> Selection | None:
        return next((item for item in self.selections if item.row == row and item.quantity == quantity), None)


def calculate_generic_cantilever(pier: PierInput, reaction: DeadReactionResult,
                                 model: LoadModelResult) -> GenericCantileverBasis:
    dead = reaction.dead
    sides, moment = cantilever_sides(pier, dead), beam_cracking_moment(pier)
    used = {term.case for combination in model.cantilever for term in combination.terms}
    return GenericCantileverBasis(numbered(dead), sides, tuple(case for case in model.cases if case.id in used),  # type: ignore[arg-type]
                                  model.cantilever, moment, tuple(model.sections.get("0900", ())))


def _ref(bearing: CantileverBearing) -> BearingRef:
    side = BearingSide.ORIGIN if bearing.girder is Girder.ORIGIN else BearingSide.END
    return BearingRef(side, bearing.bearing.loads.slot + 1)


def _action_of(case: BasicCase, item: Geometry, girders: dict[Girder, GirderBearings]) -> Action:
    actions = {action.bearing: action for action in case.actions}
    moments: dict[Girder, Printed] = {}
    for girder in Girder:
        parts = [put(MOMENT, d(FORCE(float(a.transverse))) * d(LENGTH(float(a.transverse_height))))
                 for a in case.actions if _GIRDERS[a.bearing.side] is girder]
        moments[girder] = put(MOMENT, total(parts))
    vertical, across, along = [], [], []
    for bearing in item.bearings:
        action = actions.get(_ref(bearing))
        if action is not None and action.vertical:
            vertical.append(_vertical_row(BEARING, bearing, FORCE(float(action.vertical))))
        if moments[bearing.girder].value:  # a girder without a moment loads nothing (and may have Σxi² = 0)
            torque = torque_verticals(girders[bearing.girder], moments[bearing.girder])[bearing.bearing.number - 1]
            across.append(_vertical_row(ACROSS, bearing, torque.force))
        if action is not None and action.longitudinal:
            h = FORCE(float(action.longitudinal))
            along.append(Row(ALONG, bearing.label, None, None, MOMENT(0), h,
                             item.torsion_arm, put(MOMENT, d(h) * d(item.torsion_arm))))
    return _action(ActionKey(case.id), case.name, [*vertical, *across, *along])


def _scaled(column: str, factor: Printed, action: Action) -> Contribution:
    return Contribution(column, _factor_text(factor), put(FORCE, d(action.n) * d(factor)),
                        put(MOMENT, d(action.md) * d(factor)), put(MOMENT, d(action.mt) * d(factor)))


def _printed(value: Decimal) -> Printed:
    return Printed(float(value), max(0, -value.as_tuple().exponent), "")  # type: ignore[operator]


def _case(number: int, combination: CantileverCombination, by_id: Mapping[str, Action],
          responses: Mapping[FrameDirection, MaxResponse]) -> GenericCase:
    parts = []
    for term in combination.terms:
        factor = (responses[term.factor.direction].kh if isinstance(term.factor, MaxResponseTerm)
                  else _printed(term.factor))
        parts.append(_scaled(term.case, factor, by_id[term.case]))
    return GenericCase(number, combination.name, frozenset(row.value for row in combination.rows), tuple(parts),
                       put(FORCE, total(p.n for p in parts)), put(MOMENT, total(p.md for p in parts)),
                       put(MOMENT, total(p.mt for p in parts)))


ZERO = GenericCase(0, NO_COMBINATION, frozenset(), (), FORCE(0), MOMENT(0), MOMENT(0))


# The rows pooled from another row's combinations: 最小鉄筋量 from 耐久性（永久荷重） (decision 73).
POOLED_AS = {8: 1}


def adopt_generic(cases: Mapping[Side, Sequence[GenericCase]]) -> tuple[Selection, ...]:
    """For each row and check the governing case of either cantilever among those assigned to the row (the left
    side and the earlier case win ties); the zero case for a row without one."""
    found = []
    for row in FORCE_ROWS:
        assigned = POOLED_AS.get(row.id, row.id)
        pooled = [(side, case) for side in Side if side in cases for case in cases[side] if assigned in case.rows]
        for quantity in row.quantities:
            side, case = max(pooled, key=lambda item: _measure(quantity, item[1])) if pooled else (Side.LEFT, ZERO)
            found.append(Selection(row.id, row.title, quantity, side, case))  # type: ignore[arg-type]
    return tuple(found)


def complete_generic_cantilever(pier: PierInput, reaction: DeadReactionResult, basis: GenericCantileverBasis,
                                longitudinal: MaxResponse, transverse: MaxResponse) -> GenericCantileverResult:
    responses = {FrameDirection.LONGITUDINAL: longitudinal, FrameDirection.TRANSVERSE: transverse}
    sides = {}
    for side, item in basis.sides.items():
        d1, d2 = _dead(item, snow=False)
        actions = (d1, d2, *(_action_of(case, item, basis.girders) for case in basis.cases))
        by_id = {D1: d1, D2: d2, **{action.key.kind: action for action in actions[2:]}}
        sides[side] = GenericSide(item, actions, tuple(_case(number, combination, by_id, responses)
                                                       for number, combination in enumerate(basis.combinations, 1)))
    selections = adopt_generic({side: result.cases for side, result in sides.items()})
    permanent = next(s for s in selections if s.row == 1 and s.quantity is Quantity.BENDING)
    failure = next(s for s in selections if s.row == 5 and s.quantity is Quantity.BENDING)
    self_weight = max((result.geometry.self_weight.moment for result in sides.values()), key=lambda m: m.value)
    return GenericCantileverResult(basis, longitudinal, transverse, sides, selections,
                                   cracking(basis.cracking_moment, self_weight, permanent.md, failure.md))


__all__ = ["ACROSS", "ALONG", "BEARING", "NO_COMBINATION", "GenericCantileverBasis", "GenericCantileverResult",
           "GenericCase", "GenericSide", "adopt_generic", "calculate_generic_cantilever", "complete_generic_cantilever"]
