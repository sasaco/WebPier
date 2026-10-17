"""0610 longitudinal actions (non-seismic): Example2 08 pp.8-1 to 8-11.

``calculate_longitudinal`` builds the longitudinal frame with its materials and
0500 springs, every basic action from the 0600 result (decision 2), the
nominal combination table and the actions of each combination resolved by use.
No structural analysis and no member check is done here.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...inputs import PierInput
from ..foundation import FoundationResult
from ..frame import Direction, Frame, build_frame
from ..materials import calculate_materials
from ..reaction import ReactionResult
from ..reaction.longitudinal import LongitudinalCase
from .actions import (
    AdditionalDead, BasicAction, BasicCase, FixedDead, HorizontalRow, ImpactRow, ImpactTable, Impacts, Item, Row,
    SpringTerm, TopTable, Trains, calculate_actions,
)
from .combinations import (
    Basis, Check, Combination, CombinationFactors, DefineCase, Extraction, ExtractionGroup, ResolvedAction, Usage,
    combination_factors, define_cases, extractions, resolve_combinations,
)


@dataclass(frozen=True)
class LongitudinalResult:
    frame: Frame  # 8-1 / 8-2: nodes, members, sections, materials and springs
    fixed: FixedDead  # 8-3 D1
    additional: AdditionalDead  # 8-3 D2
    buoyancy: tuple[Row, Row, Row]  # 8-3: high, normal, low water
    snow: tuple[TopTable, TopTable, TopTable]  # 8-4: 2, 10, 30 year
    train: Trains  # 8-4
    impact: Impacts  # 8-5 (girder coefficients, decision 26)
    horizontal: tuple[HorizontalRow, ...]  # 8-5: bearing horizontal forces of the 0600 cases
    basic_cases: tuple[BasicAction, ...]  # 8-6 to 8-9: the 20 basic cases
    define_cases: tuple[DefineCase, ...]  # 8-9
    factors: CombinationFactors
    combinations: tuple[Combination, ...]  # 8-10, with the resolved actions
    extractions: tuple[Extraction, ...]  # 8-11

    def basic(self, case: BasicCase) -> BasicAction:
        return self.basic_cases[case.value - 1]


def calculate_longitudinal(pier: PierInput, foundation: FoundationResult,
                           reaction: ReactionResult) -> LongitudinalResult:
    frame = build_frame(pier, reaction.self_weight, foundation, calculate_materials(pier), Direction.LONGITUDINAL)
    actions = calculate_actions(pier, frame, reaction)
    factors = combination_factors(pier)
    return LongitudinalResult(
        frame=frame, fixed=actions.fixed, additional=actions.additional, buoyancy=actions.buoyancy,
        snow=actions.snow, train=actions.train, impact=actions.impact, horizontal=actions.horizontal,
        basic_cases=actions.basic_cases, define_cases=define_cases(), factors=factors,
        combinations=resolve_combinations(frame, actions.basic_cases, actions.impact, factors),
        extractions=extractions(),
    )


__all__ = [
    "AdditionalDead", "BasicAction", "BasicCase", "Basis", "Check", "Combination", "CombinationFactors",
    "DefineCase", "Extraction", "ExtractionGroup", "FixedDead", "HorizontalRow", "ImpactRow", "ImpactTable",
    "Impacts", "Item", "LongitudinalCase", "LongitudinalResult", "ResolvedAction", "Row", "SpringTerm", "TopTable",
    "Trains", "Usage", "calculate_longitudinal",
]
