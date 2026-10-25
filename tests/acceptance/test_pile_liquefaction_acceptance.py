"""The record of scripts/accept_pile_liquefaction.py (decision 95): the real JRSNAP analyzed the NDUs for the liquefaction of a
pile foundation whose third layer liquefies and the real Aggre-SE checked every Case. Here the generator must still write the
projects it checked, byte for byte, from the input and the .sdc and the .sdc for the liquefaction SOIL-JR returned (kept beside
the record). The analyses and the checks are not run again (they need JRSNAP and Aggre-SE)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.calc.seismic_longitudinal import calculate_seismic_longitudinal
from webpier.calc.seismic_transverse import calculate_seismic_transverse
from webpier.core.integrity import file_sha256, load_json, sha256
from webpier.export.soiljr import parse_sdc
from webpier.inputs import choices, parse_input
from webpier.pipeline.stages import STAGES

ROOT = Path(__file__).parents[2]
EVIDENCE = ROOT / "tests" / "fixtures" / "acceptance" / "pile_liquefaction"
RECORD = json.loads((EVIDENCE / "record.json").read_text(encoding="utf-8"))
REDO = ("受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_pile_liquefaction.py "
        "--overwrite")
PILES = STAGES.for_foundation(choices.CAST_IN_PLACE_PILE)


def test_the_record_was_accepted_and_is_of_the_input_kept_beside_it():
    assert RECORD["kind"] == "pile_liquefaction_acceptance" and RECORD["schema_version"] == 1
    assert RECORD["accepted"] is True and RECORD["failures"] == [] and RECORD["seismic_check_judged"] is False
    assert RECORD["input"]["sha256"] == file_sha256(ROOT / RECORD["input"]["path"]), f"入力が変わっています。{REDO}"
    assert RECORD["input"]["kept_sha256"] == file_sha256(EVIDENCE / RECORD["input"]["kept"])
    assert set(RECORD["stages"]) == {"0711", "0721"}


@pytest.mark.parametrize("helper", sorted(RECORD["helpers"]))
def test_the_recorded_helpers_are_the_files_of_this_checkout(helper):
    assert sha256((ROOT / helper).read_bytes()) == RECORD["helpers"][helper], f"{helper} が変わっています。{REDO}"


@pytest.mark.parametrize("stage,cases,wet", [("0711", 5, [4]), ("0721", 10, [8, 9])])
def test_every_case_was_aggregated_and_analyzed_and_the_ones_for_the_liquefaction_are_last(stage, cases, wet):
    item = RECORD["stages"][stage]
    assert len(item["cases"]) == len(item["project"]["databases"]) == item["analysis_ok_messages"] == cases
    assert item["liquefaction_cases"] == wet and item["liquefaction_response_pages"] == len(wet)
    assert all("液状化" in item["cases"][index] for index in wet)
    assert item["limits"]["direction"] == {"0711": "axial", "0721": "transverse"}[stage]
    assert item["limits"]["liquefied_sha256"]  # the .sdr for the liquefaction was given to the runner


def test_the_runner_imported_the_limits_of_the_sdr_for_the_liquefaction():
    imported = RECORD["limits_import"]
    assert imported["found"] is True and imported["ordinary_absent"] is True
    assert imported["level2_rvd_liquefied"] != imported["level2_rvd_ordinary"]


def test_the_case_for_the_liquefaction_is_the_samples_but_for_the_pile_anchor():
    sample = RECORD["sample"]
    assert sample["items_equal_but_for_8"] is True and sample["index"] == sample["sample_index"] == ["false", "true"]
    assert sample["sample_items"][7] == -1 and sample["items"][7] == 0  # ⑧ 杭の段落し: no check of it


@pytest.mark.parametrize("stage", ["0711", "0721"])
def test_the_checked_project_is_what_the_generator_writes_now(stage):
    pier = parse_input(load_json((EVIDENCE / RECORD["input"]["kept"]).read_bytes()))
    ordinary, liquefied = (EVIDENCE / "ground.sdc").read_bytes(), (EVIDENCE / "ground_liquefied.sdc").read_bytes()
    foundation = PileFoundation(calculate_pile_ground(pier), parse_sdc(ordinary))
    reaction = calculate_reaction(pier)
    results = {"0500": SimpleNamespace(sdc=ordinary, liquefied_sdc=liquefied),
               "0710": calculate_seismic_longitudinal(pier, foundation, reaction),
               "0720": calculate_seismic_transverse(pier, foundation, reaction)}
    analysis = PILES.get(stage).nonlinear_analysis
    recorded = RECORD["stages"][stage]
    written = analysis.project.build(results, pier)(analysis.folder, recorded["project"]["databases"])
    assert sha256(written) == recorded["project"]["sha256"], f"{stage} の Aggre-SE のプロジェクトが変わりました。{REDO}"
