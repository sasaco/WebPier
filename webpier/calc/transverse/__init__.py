"""0620 transverse actions (non-seismic): Example2 09 pp.9-1 to 9-15.

``calculate_transverse`` builds the transverse frame with its materials and
0500 springs, every basic action from the 0600 result (decision 2) with the
wind on the pier body (decision 12), the nominal combination table of the
Define cases and the actions of each combination resolved by use. No
structural analysis and no member check is done here.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...inputs import PierInput
from ..foundation import FoundationResult
from ..pile_frame import PileFoundation
from ..frame import Direction, Frame, build_frame
from ..longitudinal.combinations import (
    Basis, CombinationFactors, Extraction, ExtractionGroup, Usage, combination_factors, placed_extractions,
)
from ..materials import calculate_materials
from ..reaction import ReactionResult
from .actions import (
    AdditionalDead, BasicAction, BasicCase, CentrifugalRow, Centrifugals, CentrifugalTable, FixedDead, HorizontalRow, ImpactRow, Impacts, ImpactSet, ImpactTable,
    Item, Lateral, Row, TopTable, Track, TrainRow, Trains, TrainTable, Wind, calculate_actions,
)
from .combinations import (
    EXTRACTIONS, WIND_SAFETY, Check, Combination, Component, Define, DefineCase, Loading, ResolvedAction, define_cases,
    resolve_combinations,
)
from .wind import MemberLoad, PierWind, WindSegment


@dataclass(frozen=True)
class TransverseResult:
    frame: Frame  # 9-1 / 9-2: nodes, members, sections, materials and springs
    fixed: FixedDead  # 9-3 D1
    additional: AdditionalDead  # 9-3 D2
    buoyancy: tuple[Row, Row, Row]  # 9-4: high, normal, low water
    snow: tuple[TopTable, TopTable, TopTable] | None  # 9-4: 2, 10, 30 year; None without snow (decision 69)
    train: Trains  # 9-5: up, down, double
    impact: Impacts  # 9-6 (coefficients on the pier body, decision 77), and the serviceability tables
    lateral: Lateral  # 9-7
    wind_with_train: Wind  # 9-7
    wind_without_train: Wind  # 9-8
    centrifugal: Centrifugals | None  # on a curve only (decision 33); None on a straight track
    basic_cases: tuple[BasicAction, ...]  # 9-9 to 9-13: the 18 basic cases (+ 3 centrifugal on a curve, − 3 snow)
    define_cases: tuple[DefineCase, ...]  # 9-13: the 16 Define cases (+ 2 centrifugal on a curve, − 3 snow)
    factors: CombinationFactors
    combinations: tuple[Combination, ...]  # 9-14 for 複線 and 単線 (decision 106), with the resolved actions
    extractions: tuple[Extraction, ...]  # 9-15 (the same groups as 8-11, of every combination of their checks)

    def basic(self, case: BasicCase) -> BasicAction:
        for action in self.basic_cases:
            if action.case is case:
                return action
        raise KeyError(case)


def calculate_transverse(pier: PierInput, foundation: FoundationResult | PileFoundation,
                        reaction: ReactionResult) -> TransverseResult:
    frame = build_frame(pier, reaction.self_weight, foundation, calculate_materials(pier), Direction.TRANSVERSE)
    actions = calculate_actions(pier, frame, reaction)
    factors = combination_factors(pier)
    defines = define_cases(actions.basic_cases)
    combinations = resolve_combinations(frame, actions.basic_cases, defines, actions.impact.service, factors)
    return TransverseResult(
        frame=frame, fixed=actions.fixed, additional=actions.additional, buoyancy=actions.buoyancy,
        snow=actions.snow, train=actions.train, impact=actions.impact, lateral=actions.lateral,
        wind_with_train=actions.wind_with_train, wind_without_train=actions.wind_without_train,
        centrifugal=actions.centrifugal, basic_cases=actions.basic_cases, define_cases=defines, factors=factors,
        combinations=combinations,
        extractions=placed_extractions(combinations, EXTRACTIONS),  # type: ignore[arg-type]
    )


__all__ = [
    "AdditionalDead", "BasicAction", "BasicCase", "Basis", "CentrifugalRow", "CentrifugalTable", "Centrifugals", "Check", "Combination", "CombinationFactors", "Component",
    "Define", "DefineCase", "Extraction", "ExtractionGroup", "FixedDead", "HorizontalRow", "ImpactRow", "ImpactSet", "Loading",
    "ImpactTable", "Impacts", "Item", "Lateral", "MemberLoad", "PierWind", "ResolvedAction", "Row", "TopTable",
    "Track", "TrainRow", "TrainTable", "Trains", "TransverseResult", "Usage", "WIND_SAFETY", "Wind", "WindSegment",
    "calculate_transverse",
]
