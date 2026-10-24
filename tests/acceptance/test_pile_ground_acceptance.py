"""The real-app acceptance of 0500 for a pile foundation still belongs to the current generator (decision 85, ADR-0013).

tests/fixtures/acceptance/pile_ground/record.json is what scripts/accept_pile_ground.py recorded with the real JRSNAP runner
and the real SOIL-JR 5.2-L03: the .sdt WebPier wrote for tests/fixtures/inputs/pile.json (the SOIL-JR sample RC橋脚（杭基礎）サンプル
データE.sdt) was calculated to the sample's own .sdr and .sdc but for the title. These tests do not run SOIL-JR. They fail
(never skip) when the input or the .sdt WebPier writes for it is no longer the accepted one: then redo the acceptance with
``uv run --project "." --locked python -X utf8 scripts/accept_pile_ground.py --overwrite``.
"""

import json
from pathlib import Path

from recorded_input_support import input_sha256s
from webpier.core.integrity import load_json, sha256
from webpier.inputs import parse_input
from webpier.pipeline.generate import export_bytes

ROOT = Path(__file__).parents[2]
RECORD = json.loads((ROOT / "tests" / "fixtures" / "acceptance" / "pile_ground" / "record.json").read_text(encoding="utf-8"))
REDO = "受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_pile_ground.py --overwrite"


def test_the_record_is_accepted():
    assert (RECORD["kind"], RECORD["schema_version"], RECORD["accepted"], RECORD["failures"]) == (
        "pile_ground_acceptance", 1, True, [])
    assert RECORD["soil_jr_judged"] is False
    assert RECORD["same_as_sample_but_for_the_title"] == {"sdr": True, "sdc": True}
    assert RECORD["written"]["report_pages"] == RECORD["sample_result"]["report_pages"] > 1


def test_the_input_is_the_one_accepted():
    data = (ROOT / RECORD["input"]["path"]).read_bytes()
    assert RECORD["input"]["sha256"] in input_sha256s(data), f"受入時の入力から変わっています。{REDO}"


def test_the_generator_still_writes_the_sdt_that_was_calculated():
    pier = parse_input(load_json((ROOT / RECORD["input"]["path"]).read_bytes()))
    assert sha256(export_bytes(pier, "0500", "sdt")) == RECORD["written"]["sdt_sha256"], f".sdt が受入時から変わっています。{REDO}"


def test_the_runner_was_the_one_that_runs_soil_jr_5_2():
    summary = RECORD["runner"]["summary"]
    assert summary["jrsnap"]["product"] == "5.2-L03" and summary["jrsnap"]["soilVersion"] == "5.2.3.0"
    assert summary["input"]["sha256"] == RECORD["written"]["sdt_sha256"] and summary["liquefaction"] is False
    assert RECORD["sample"]["runner_summary"]["jrsnap"] == summary["jrsnap"]


def test_the_fixture_of_the_sample_result_is_what_soil_jr_returned_for_the_sample():
    sdr = (ROOT / "tests" / "fixtures" / "soiljr" / "pile_cast.sdr").read_bytes()
    assert sha256(sdr) == RECORD["sample_result"]["sdr_sha256"]
