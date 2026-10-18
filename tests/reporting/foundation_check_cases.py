"""The 0612 / 0622 基礎の照査 results the report tests lay out (decision 54).

current.json with the supporting layer sandy and the cover's submerged unit weight 9.0 (as pre/input.json), checked
with the reactions of the independent hand calculation (tests/fixtures/example2/foundation_check.json: FEMPython's
reactions of Example2), or with a given reaction in every column.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from webpier.calc import foundation_check as fc
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.inputs import parse_input
from webpier.reporting.stages.foundation_check import LONGITUDINAL, TRANSVERSE, Chapter

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
HAND = json.loads((FIXTURES / "example2" / "foundation_check.json").read_text(encoding="utf-8"))
CHAPTERS = {"0612": LONGITUDINAL, "0622": TRANSVERSE}


def basis(stage: str) -> fc.Basis:
    data = deepcopy(CURRENT)
    data["地盤データ"]["層"][1]["土質区分"] = "砂質土"
    data["地盤データ"]["層"][0]["単位体積重量"]["水中"] = 9.0
    pier = parse_input(data)
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    if stage == "0612":
        return fc.prepare(pier, foundation, calculate_longitudinal(pier, foundation, reaction), fc.LONGITUDINAL)
    return fc.prepare(pier, foundation, calculate_transverse(pier, foundation, reaction), fc.TRANSVERSE)


def result(stage: str, extreme: fc.SupportReaction | None = None) -> fc.FoundationCheckResult:
    """The check of *stage* with the hand calculation's reactions, or *extreme* in every column."""
    found = basis(stage)
    reactions = {}
    for spec in fc.COLUMNS:
        given = HAND["inputs"]["reactions"][stage][spec.key]
        column = extreme or fc.SupportReaction(given["combination"], float(given["fx"]), float(given["fy"]),
                                               float(given["mz"]))
        reactions[(found.pickups[spec.key], spec.focus.value)] = (column, column)
    return fc.check(found, reactions)


def chapter(stage: str) -> Chapter:
    return CHAPTERS[stage]
