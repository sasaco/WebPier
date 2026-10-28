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
from ..pile_frame import PileFoundation
from ..frame import Direction, Frame, build_frame
from ..materials import calculate_materials
from ..reaction import ReactionResult
from ..reaction.longitudinal import LongitudinalCase
from ..reaction.train import Layout
from .actions import (
    AdditionalDead, BasicAction, BasicCase, FixedDead, HorizontalRow, ImpactRow, ImpactTable, Impacts, Item,
    LayoutActions, Row, SpringTerm, TopTable, Trains, calculate_actions,
)
from .combinations import (
    Basis, Check, Combination, CombinationFactors, DefineCase, Extraction, ExtractionGroup, ResolvedAction, Usage,
    Water, combination_factors, define_cases, placed_extractions, resolve_combinations,
)


@dataclass(frozen=True)
class LongitudinalResult:
    frame: Frame  # 8-1 / 8-2: nodes, members, sections, materials and springs
    fixed: FixedDead  # 8-3 D1
    additional: AdditionalDead  # 8-3 D2
    buoyancy: tuple[Row, Row, Row]  # 8-3: high, normal, low water
    snow: tuple[TopTable, TopTable, TopTable] | None  # 8-4: 2, 10, 30 year; None without snow (decision 69)
    train: Trains  # 8-4
    impact: Impacts  # 8-5 (coefficients on the pier body, decision 77)
    horizontal: tuple[HorizontalRow, ...]  # 8-5: bearing horizontal forces of the 0600 cases (①)
    one_girder: tuple[LayoutActions, LayoutActions]  # ② and ③: train, impact and bearing forces (decision 102)
    basic_cases: tuple[BasicAction, ...]  # 8-6 to 8-9: the basic cases (decision 69, a LAYOUT_DEPENDENT one ×3)
    define_cases: tuple[DefineCase, ...]  # 8-9
    factors: CombinationFactors
    combinations: tuple[Combination, ...]  # Example橋脚4 表2.3.2 (decision 120), with the resolved actions
    extractions: tuple[Extraction, ...]  # 表2.3.3: the 8 groups of 8-11

    def basic(self, case: BasicCase, layout: Layout = Layout.BOTH) -> BasicAction:
        for action in self.basic_cases:
            if action.case is case and action.layout in (None, layout):
                return action
        raise KeyError(case)


def calculate_longitudinal(pier: PierInput, foundation: FoundationResult | PileFoundation,
                           reaction: ReactionResult) -> LongitudinalResult:
    frame = build_frame(pier, reaction.self_weight, foundation, calculate_materials(pier), Direction.LONGITUDINAL)
    actions = calculate_actions(pier, frame, reaction)
    factors = combination_factors(pier)
    impacts = {Layout.BOTH: actions.impact, **{placed.layout: placed.impact for placed in actions.one_girder}}
    combinations = resolve_combinations(frame, actions.basic_cases, impacts, factors)
    return LongitudinalResult(
        frame=frame, fixed=actions.fixed, additional=actions.additional, buoyancy=actions.buoyancy,
        snow=actions.snow, train=actions.train, impact=actions.impact, horizontal=actions.horizontal,
        one_girder=actions.one_girder, basic_cases=actions.basic_cases, define_cases=define_cases(actions.basic_cases),
        factors=factors, combinations=combinations, extractions=placed_extractions(combinations),
    )


__all__ = [
    "AdditionalDead", "BasicAction", "BasicCase", "Basis", "Check", "Combination", "CombinationFactors",
    "DefineCase", "Extraction", "ExtractionGroup", "FixedDead", "HorizontalRow", "ImpactRow", "ImpactTable",
    "Impacts", "Item", "Layout", "LayoutActions", "LongitudinalCase", "LongitudinalResult", "ResolvedAction", "Row",
    "SpringTerm", "TopTable",
    "Trains", "Usage", "Water", "calculate_longitudinal",
]
