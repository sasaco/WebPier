"""The real-app acceptance of the NDU of a pile foundation still belongs to the current writer (decision 93).

tests/fixtures/acceptance/pile_ndu/record.json is what scripts/accept_pile_ndu.py recorded with the real JRSNAP runner: the NDU
WebPier writes for the model of the JRSNAP sample RC橋脚L (``pile_ndu_support.sample_model``), exported by JRSNAP as an NDT, is the
NDT JRSNAP wrote for the sample but for the names, the loads the model does not have, the flags of the DA card and two ties of
Kv2 (2086.25). These tests do not run JRSNAP. They fail (never skip) when the NDU WebPier writes is no longer the accepted one:
then redo the acceptance with ``uv run --project "." --locked python -X utf8 scripts/accept_pile_ndu.py --overwrite``.
"""

import json
from pathlib import Path

from pile_ndu_support import SAMPLE_NDU, sample_model

from webpier.core.integrity import sha256
from webpier.export.jrsnap.writer import write_pile_ndu

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
RECORD = json.loads((FIXTURES / "acceptance" / "pile_ndu" / "record.json").read_text(encoding="utf-8"))
REDO = "受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_pile_ndu.py --overwrite"


def test_the_record_is_accepted_and_no_analysis_was_run():
    assert (RECORD["kind"], RECORD["schema_version"], RECORD["accepted"], RECORD["failures"]) == (
        "pile_ndu_acceptance", 1, True, [])
    assert RECORD["analyzed"] is False and RECORD["runner"]["summary"]["analyzed"] is False
    assert RECORD["runner"]["summary"]["jrsnap"]["product"] == "5.2-L03"


def test_the_ndt_differs_from_the_samples_only_where_it_should():
    regions = [item["region"] for item in RECORD["differences"]]
    assert sorted(set(regions)) == ["header", "loads", "tie"]
    assert [item["sample_lines"] for item in RECORD["differences"] if item["region"] == "tie"] == [[173, 173], [207, 207]]


def test_the_writer_still_writes_the_ndu_that_was_accepted():
    assert sha256(write_pile_ndu(sample_model())) == RECORD["written"]["ndu_sha256"], f"NDU が受入時から変わっています。{REDO}"


def test_the_sample_is_the_one_the_acceptance_compared_with():
    assert sha256(SAMPLE_NDU.read_bytes()) == RECORD["sample"]["ndu_sha256"]
    assert sha256((FIXTURES / "jrsnap" / "pile_s_case1.ndt").read_bytes()) == RECORD["sample"]["ndt_sha256"]
