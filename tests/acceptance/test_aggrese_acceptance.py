"""The Aggre-SE acceptance record still belongs to the current generator (decision 49, CONTEXT.md 耐震照査の入力).

tests/fixtures/acceptance/aggrese holds what scripts/accept_aggrese_project.py recorded: the projects of a real 0711 /
0721 generation, which the Aggre-SE runner read and calculated with their JRSNAP results and which Aggre-SE saved again
to the same bytes, and record.json. These tests run neither JRSNAP nor Aggre-SE. They fail (never skip) when the input
or the project WebPier writes for the recorded DB1 is no longer the accepted one: then the acceptance must be redone
with ``uv run --project "." --locked python -X utf8 scripts/accept_aggrese_project.py --overwrite``.
"""

import json
from pathlib import Path

import pytest

from recorded_input_support import input_sha256s
from webpier.core.integrity import load_json, sha256
from webpier.export.aggrese import BATCH_VERSION
from webpier.inputs import parse_input
from webpier.pipeline.generate import project_bytes

ROOT = Path(__file__).parents[2]
EVIDENCE = ROOT / "tests" / "fixtures" / "acceptance" / "aggrese"
RECORD = json.loads((EVIDENCE / "record.json").read_text(encoding="utf-8"))
REDO = ("受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_aggrese_project.py "
        "--overwrite")
STAGES = ("0711", "0721")


@pytest.fixture(scope="module")
def pier():
    data = (ROOT / RECORD["input"]["path"]).read_bytes()
    assert RECORD["input"]["sha256"] in input_sha256s(data), f"受入時の入力から変わっています。{REDO}"
    return parse_input(load_json(data))


def test_the_record_is_aggre_se_reading_calculating_and_saving_without_judging():
    assert RECORD["kind"] == "aggrese_project_acceptance" and RECORD["schema_version"] == 1
    assert RECORD["application"]["batch"]["file_version"] == BATCH_VERSION
    assert RECORD["seismic_check_judged"] is False and RECORD["gui_operated"] is False
    assert set(RECORD["directions"]) == set(STAGES)


@pytest.mark.parametrize("helper", sorted(RECORD["helpers"]))
def test_the_recorded_helpers_are_the_files_of_this_checkout(helper):
    """The helpers are stored with LF (.gitattributes), so their SHA-256 does not depend on core.autocrlf."""
    assert sha256((ROOT / helper).read_bytes()) == RECORD["helpers"][helper], f"{helper} が受入時から変わっています。{REDO}"


@pytest.mark.parametrize("stage", STAGES)
def test_the_accepted_project_is_what_the_generator_writes_now(pier, stage):
    direction = RECORD["directions"][stage]
    stored = (EVIDENCE / direction["candidate"]["path"]).read_bytes()
    assert sha256(stored) == direction["candidate"]["sha256"]
    assert sha256(project_bytes(pier, stage, direction["databases"])) == direction["candidate"]["sha256"], (
        f"{stage} の Aggre-SE のプロジェクトが変わりました。{REDO}")


@pytest.mark.parametrize("stage", STAGES)
def test_aggre_se_read_every_case_and_saved_the_same_bytes(stage):
    direction = RECORD["directions"][stage]
    cases = direction["run"]["cases"]
    assert len(cases) == len(direction["databases"]) == {"0711": 1, "0721": 2}[stage]
    assert all(case["selected"] and case["aggregated"] for case in cases)
    assert {"summary.xlsx", "report.pdf"} <= set(direction["run"]["outputs"])
    assert direction["roundtrip_identical"] is True
