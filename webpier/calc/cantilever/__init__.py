"""0900 片持ち梁の応答値の算定・設計作用の組合せ (decision 59, CONTEXT.md 片持ち梁の照査).

``calculate_cantilever`` gives everything the input and 0600 decide: the geometry of each cantilever that carries a
bearing (geometry), the three train loadings and the train on every bearing (loads), the torques of the vehicle
lateral load, the wind and the seismic train, and the cracking moment of the beam section (crack). It fails on an
input the check cannot use before any runner is called. ``complete_cantilever`` adds what needs the 最大応答震度 of
0711 and 0721 (response): the seismic inertia of the girders across the track, the bearing forces along it
(bearings), then the action tables of each cantilever (actions), the 31 combinations (combinations), the governing
case of either side for each check and ε'csd (crack). The 0910 check is ``check.calculate_cantilever_section``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.errors import InputError
from ...inputs import PierInput
from ..moving_load import Girder
from ..materials import concrete
from ..reaction import ReactionResult
from .actions import Action, actions
from .bearings import BearingCase, bearing_cases, label
from .combinations import (COLUMNS, DEFINITIONS, CaseResult, LimitState, Quantity, Selection, adopt,
                           evaluate_all)
from .crack import Cracking, CrackingMoment, cracking, cracking_moment
from .geometry import Geometry, GirderBearings, Side, geometry, numbered
from .loads import (Loading, LoadingResult, SeismicTrainLoad, Torque, Wind, lateral_torques, seismic_girder_torques,
                    seismic_train, seismic_train_torques, train_loadings, wind_torques)
from .response import MaxResponse, ResponseError, read_max_response
from ...core.printed import Precision
from .._exact import d, put

MM = Precision(0, "mm")


@dataclass(frozen=True)
class CantileverBasis:
    """What the input and 0600 decide, before the 最大応答震度 is known."""

    girders: dict[Girder, GirderBearings]
    sides: dict[Side, Geometry]  # the cantilevers that carry a bearing, left first
    loadings: tuple[LoadingResult, ...]
    seismic_train: dict[Girder, tuple[SeismicTrainLoad, ...]]
    lateral: dict[Loading, dict[Girder, Torque]]
    wind: dict[Wind, dict[Girder, Torque]]
    seismic_train_torque: dict[Girder, Torque]
    cracking_moment: CrackingMoment


@dataclass(frozen=True)
class SideResult:
    geometry: Geometry
    actions: tuple[Action, ...]
    cases: tuple[CaseResult, ...]


@dataclass(frozen=True)
class CantileverResult:
    basis: CantileverBasis
    longitudinal: MaxResponse  # the 最大応答震度 along the track (0711)
    transverse: MaxResponse  # across it (0721)
    seismic_girder: dict[Girder, Torque]  # the girder inertia across the track at the transverse Kh
    bearing_cases: tuple[BearingCase, ...]  # the four LR + B combinations and the seismic case along the track
    sides: dict[Side, SideResult]
    selections: tuple[Selection, ...]  # the governing case of each check, both sides pooled
    cracking: Cracking

    def selection(self, row: int, quantity: Quantity) -> Selection | None:
        return next((item for item in self.selections if item.row == row and item.quantity == quantity), None)


def calculate_cantilever(pier: PierInput, reaction: ReactionResult) -> CantileverBasis:
    dead = reaction.dead
    girders = numbered(dead)
    sides = {side: geometry(pier, dead, side) for side in Side}
    sides = {side: item for side, item in sides.items() if item.bearings}
    if not sides:
        raise InputError("上部工反力: はりの張出し（|支承位置| > W6/2）に支承がないため、片持ち梁の照査ができません")
    loadings = train_loadings(pier, reaction.train, girders)
    s = pier.substructure
    beam = pier.rebar.beam
    if beam.aggregate_max is None:
        raise InputError("鉄筋.梁.aggregate_max_mm: 値が必要です")
    moment = cracking_moment(put(MM, d(s.b[1]) * 1000), put(MM, (d(s.h[2]) + d(s.h[3])) * 1000),
                             concrete(pier.materials.beam, "鉄筋.梁.concrete_strength_mpa"), beam.aggregate_max)
    return CantileverBasis(girders, sides, loadings, seismic_train(reaction.train, girders),
                           lateral_torques(loadings, reaction.transverse, girders),
                           wind_torques(reaction.transverse, girders),
                           seismic_train_torques(reaction.transverse, girders), moment)


def complete_cantilever(pier: PierInput, reaction: ReactionResult, basis: CantileverBasis,
                        longitudinal: MaxResponse, transverse: MaxResponse) -> CantileverResult:
    any_side = next(iter(basis.sides.values()))
    seismic_girder = seismic_girder_torques(reaction.transverse, transverse.kh, basis.girders)
    cases = bearing_cases(pier, reaction.longitudinal, longitudinal.kh, any_side.torsion_arm)
    labels = {case.case: case.label for case in cases if case.case is not None}
    sides = {}
    for side, item in basis.sides.items():
        tables = actions(item, basis.loadings, basis.seismic_train, basis.lateral, basis.wind, seismic_girder,
                         basis.seismic_train_torque, cases, snow=reaction.dead.snow)
        sides[side] = SideResult(item, tables, evaluate_all(pier, tables, labels))
    selections = adopt({side: result.cases for side, result in sides.items()})
    permanent = next(item for item in selections if item.row == 1 and item.quantity is Quantity.BENDING)
    failure = next(item for item in selections if item.row == 5 and item.quantity is Quantity.BENDING)
    self_weight = max((result.geometry.self_weight.moment for result in sides.values()), key=lambda m: m.value)
    return CantileverResult(basis, longitudinal, transverse, seismic_girder, cases, sides, selections,
                            cracking(basis.cracking_moment, self_weight, permanent.md, failure.md))


__all__ = ["COLUMNS", "DEFINITIONS", "CantileverBasis", "CantileverResult", "Cracking", "LimitState", "MaxResponse",
           "Quantity", "ResponseError", "Selection", "Side", "SideResult", "calculate_cantilever",
           "complete_cantilever", "label", "read_max_response"]
