"""The 0711 / 0721 report acceptance record still belongs to the current generator (decision 56, ADR-0009).

tests/fixtures/acceptance/aggrese_report/record.json holds what scripts/accept_aggrese_report.py recorded: a real 0711
/ 0721 generation with the real JRSNAP and Aggre-SE runners, whose reports are Aggre-SE's, and the response values of
each Case read from them. These tests run neither JRSNAP nor Aggre-SE. They fail (never skip) when the input or the
project WebPier writes for the recorded DB1 is no longer the accepted one: then the acceptance must be redone with
``uv run --project "." --locked python -X utf8 scripts/accept_aggrese_report.py --overwrite``.
"""

import json
from pathlib import Path

import pytest

from webpier.core.integrity import load_json, sha256
from webpier.inputs import parse_input
from webpier.pipeline.generate import project_bytes
from webpier.pipeline.stages import STAGES

ROOT = Path(__file__).parents[2]
RECORD = json.loads((ROOT / "tests" / "fixtures" / "acceptance" / "aggrese_report" / "record.json")
                    .read_text(encoding="utf-8"))
REDO = ("受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_aggrese_report.py "
        "--overwrite")
STAGES_ACCEPTED = ("0711", "0721")


@pytest.fixture(scope="module")
def pier():
    data = (ROOT / RECORD["input"]["path"]).read_bytes()
    assert sha256(data) == RECORD["input"]["sha256"], f"受入時の入力から変わっています。{REDO}"
    return parse_input(load_json(data))


def test_the_record_is_aggre_ses_report_without_a_judgement():
    assert RECORD["kind"] == "aggrese_report_acceptance" and RECORD["schema_version"] == 1
    assert RECORD["seismic_check_judged"] is False
    assert set(RECORD["directions"]) == set(STAGES_ACCEPTED)


@pytest.mark.parametrize("helper", sorted(RECORD["helpers"]))
def test_the_recorded_helpers_are_the_files_of_this_checkout(helper):
    """The helpers are stored with LF (.gitattributes), so their SHA-256 does not depend on core.autocrlf."""
    assert sha256((ROOT / helper).read_bytes()) == RECORD["helpers"][helper], f"{helper} が受入時から変わっています。{REDO}"


@pytest.mark.parametrize("stage", STAGES_ACCEPTED)
def test_the_checked_project_is_what_the_generator_writes_now(pier, stage):
    direction = RECORD["directions"][stage]
    assert direction["seismic_check"]["project"]["sha256"] == direction["project"]["sha256"]
    assert sha256(project_bytes(pier, stage, direction["project"]["databases"])) == direction["project"]["sha256"], (
        f"{stage} の Aggre-SE のプロジェクトが変わりました。{REDO}")


@pytest.mark.parametrize("stage", STAGES_ACCEPTED)
def test_aggre_se_checked_every_case_into_the_report(stage):
    direction = RECORD["directions"][stage]
    checked = direction["seismic_check"]
    spec = STAGES.get(stage)
    assert (checked["engine"], checked["engineering_status"]) == ("aggrese", "not_evaluated")
    assert checked["jrsnap"] == {"file": spec.nonlinear_analysis.folder, "sha256": direction["jrsnap"]["sha256"]}
    assert len(checked["cases"]) == len(direction["cases"]) == len(direction["project"]["databases"]) == {
        "0711": 1, "0721": 2}[stage]
    assert all(case["aggregated"] for case in checked["cases"])
    assert direction["report"]["file"] == f"{spec.stem}.pdf" and direction["report"]["pages"] > len(direction["cases"])


@pytest.mark.parametrize("stage", STAGES_ACCEPTED)
def test_aggre_se_returned_the_pickup_of_the_three_earthquakes(stage):
    """Decision 57: Batch's default pickups 1 L1, 2 restorability L2, 3 safety L2, each the envelope of every Case."""
    direction = RECORD["directions"][stage]
    pik = direction["pik"]
    assert pik["file"] == dict(STAGES.get(stage).seismic_check.files)["pik"]
    assert direction["seismic_check"]["files"]["pik"] == {"file": pik["file"], "sha256": pik["sha256"]}
    assert (pik["header"], pik["pickups"]) == ("Batch ver1.0.0", [1, 2, 3])


@pytest.mark.parametrize("stage", STAGES_ACCEPTED)
def test_aggre_se_returned_the_summary_workbook_of_the_report(stage):
    """Decision 58: the workbook's sheets are the last four pages of the report; its bytes differ each run."""
    direction = RECORD["directions"][stage]
    xlsx = direction["xlsx"]
    assert xlsx["file"] == dict(STAGES.get(stage).seismic_check.files)["xlsx"]
    assert direction["seismic_check"]["files"]["xlsx"]["file"] == xlsx["file"]
    assert xlsx["sheets"] == ["応答値一覧表", "設計総括表", "安全率一覧表", "直接基礎"]


def test_the_longitudinal_response_is_example2s():
    """Example2 10-14: Kheq 0.368, δeq 30.5, safety μ 9.32 and δr 284.3, restorability μ 5.78 and δr 176.3."""
    direction = RECORD["directions"]["0711"]
    assert direction["example2"]["matches"] is True
    assert direction["cases"] == [{"kheq": 0.368, "delta_eq": 30.5,
                                   "safety": {"mu": 9.32, "delta_r": 284.3, "khr": 0.386},
                                   "restorability": {"mu": 5.78, "delta_r": 176.3, "khr": 0.385}}]
