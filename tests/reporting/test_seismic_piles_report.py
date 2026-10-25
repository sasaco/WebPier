"""0710 and 0720 of a pile foundation (decision 93): the report is the direct foundation's, with nothing added for the piles (what
JRSNAP draws of the model is in its データ確認図), but for the combination table, whose 地盤抵抗TYPE is the direct foundation's.

The pile input is tests/fixtures/inputs/pile.json with the reinforcement of ``pile_cast_support`` and the .sdc SOIL-JR 5.2 returned
for it; the direct foundation's is current.json."""

from functools import cache
from pathlib import Path

import pytest
from pile_cast_support import cast_input

from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.calc.foundation import calculate_foundation
from webpier.calc.seismic_longitudinal import calculate_seismic_longitudinal
from webpier.calc.seismic_transverse import calculate_seismic_transverse
from webpier.core.integrity import load_json
from webpier.export.soiljr import parse_sdc
from webpier.inputs import parse_input
from webpier.reporting.stages import seismic_longitudinal, seismic_transverse

FIXTURES = Path(__file__).parents[1] / "fixtures"
CALCULATE = {"0710": calculate_seismic_longitudinal, "0720": calculate_seismic_transverse}
REPORT = {"0710": seismic_longitudinal, "0720": seismic_transverse}


@cache
def records(stage: str, piles: bool):
    if piles:
        pier = cast_input()
        foundation = PileFoundation(calculate_pile_ground(pier), parse_sdc((FIXTURES / "soiljr" / "pile_cast.sdc").read_bytes()))
    else:
        pier = parse_input(load_json((FIXTURES / "inputs" / "current.json").read_bytes()))
        foundation = calculate_foundation(pier)
    reaction = calculate_reaction(pier)
    result = CALCULATE[stage](pier, foundation, reaction)
    return {record["id"]: record["text"] for record in REPORT[stage].semantic_records(result, reaction, pier)}


@pytest.mark.parametrize("stage", ["0710", "0720"])
def test_the_ground_resistance_type_is_the_direct_foundations(stage):
    direct, piles = records(stage, False)[f"{stage}/combination"], records(stage, True)[f"{stage}/combination"]
    assert "地盤抵抗TYPE" in direct and "地盤抵抗TYPE" not in piles
    assert "荷重補正係数＋基本Case" in piles and piles.count("1 + 2 + 3") == piles.count("+ 2 + 3") > 0


@pytest.mark.parametrize("stage", ["0710", "0720"])
def test_the_rest_of_the_report_does_not_know_the_foundation(stage):
    direct, piles = records(stage, False), records(stage, True)
    assert set(direct) == set(piles)
    same = [key for key in direct if key != f"{stage}/combination" and direct[key] == piles[key]]
    assert f"{stage}/title" in same and f"{stage}/basic" in same and f"{stage}/model.heading" in same
