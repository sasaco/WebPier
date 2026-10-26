"""The record of scripts/accept_pile_nonlinear.py (decision 94): the real JRSNAP analyzed the NDUs of tests/fixtures/inputs/
pile_seismic.json for 0711 and 0721 and the real Aggre-SE checked the piles with the limits of SOIL-JR's .sdr. Here the
generator must still write the projects it checked, byte for byte, so that the record keeps describing what it writes. The
analyses and the checks are not run again (they need JRSNAP and Aggre-SE)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from recorded_input_support import input_sha256s
from webpier.calc.column_rebar import column_layout
from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.calc.seismic_longitudinal import calculate_seismic_longitudinal
from webpier.calc.seismic_transverse import calculate_seismic_transverse
from webpier.core.integrity import file_sha256, load_json, sha256
from webpier.export.soiljr import parse_sdc
from webpier.inputs import parse_input, choices
from webpier.pipeline.stages import STAGES

FIXTURES = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).parents[2]
RECORD = json.loads((FIXTURES / "acceptance" / "pile_nonlinear" / "record.json").read_text(encoding="utf-8"))
REDO = ("受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_pile_nonlinear.py "
        "--overwrite")
SDC = FIXTURES / "acceptance" / "pile_seismic" / "pile_seismic.sdc"  # the .sdc SOIL-JR returned for the same input
PILES = STAGES.for_foundation(choices.CAST_IN_PLACE_PILE)


def test_the_record_was_accepted_and_is_of_the_input():
    assert RECORD["kind"] == "pile_nonlinear_acceptance" and RECORD["schema_version"] == 1
    assert RECORD["accepted"] is True and RECORD["failures"] == [] and RECORD["seismic_check_judged"] is False
    assert RECORD["input"]["sha256"] in input_sha256s((ROOT / RECORD["input"]["path"]).read_bytes()), f"入力が変わっています。{REDO}"
    assert set(RECORD["stages"]) == {"0711", "0721"}


@pytest.mark.parametrize("helper", sorted(RECORD["helpers"]))
def test_the_recorded_helpers_are_the_files_of_this_checkout(helper):
    assert sha256((ROOT / helper).read_bytes()) == RECORD["helpers"][helper], f"{helper} が変わっています。{REDO}"


@pytest.mark.parametrize("stage,cases", [("0711", 4), ("0721", 8)])
def test_every_case_was_aggregated_and_the_limits_are_those_of_the_sdr(stage, cases):
    item = RECORD["stages"][stage]
    assert len(item["cases"]) == len(item["project"]["databases"]) == cases
    # level 1 and the 地震時 table (安定レベル3) are in the report; level 2 is there when the report has it
    assert {"1", "3"} <= set(item["report"]["levels"])
    for name, found in item["limits"]["found"].items():
        assert found["in_report"] or found["level"] not in ("1", "3"), name
    assert item["limits"]["direction"] == {"0711": "axial", "0721": "transverse"}[stage]
    assert item["files"] == ["pik", "xlsx"]  # no step table of the direct foundation


def test_a_project_of_piles_gives_the_sample_the_same_level_1():
    sample = RECORD["sample"]
    assert sample["level1_text_equal"] is True and sample["level1_sample_chars"] == sample["level1_webpier_chars"] > 0


@pytest.mark.parametrize("stage", ["0711", "0721"])
def test_the_checked_project_is_what_the_generator_writes_now(stage):
    """From the .sdc SOIL-JR returned for the input (kept beside the record of 0710 and 0720), as the stage builds it."""
    data = SDC.read_bytes()
    pier = parse_input(load_json((ROOT / RECORD["input"]["path"]).read_bytes()))
    foundation = PileFoundation(calculate_pile_ground(pier), parse_sdc(data))
    reaction = calculate_reaction(pier)
    results = {"0500": SimpleNamespace(sdc=data), "0710": calculate_seismic_longitudinal(pier, foundation, reaction),
               "0720": calculate_seismic_transverse(pier, foundation, reaction)}
    analysis = PILES.get(stage).nonlinear_analysis
    recorded = RECORD["stages"][stage]
    written = analysis.project.build(results, pier)(analysis.folder, recorded["project"]["databases"])
    assert sha256(written) == recorded["project"]["sha256"], f"{stage} の Aggre-SE のプロジェクトが変わりました。{REDO}"
