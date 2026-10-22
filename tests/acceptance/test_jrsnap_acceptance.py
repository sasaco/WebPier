"""The JRSNAP 5.2-L03 acceptance record still belongs to the current generator (decision 4, CONTEXT.md NDUの受入記録).

tests/fixtures/acceptance/jrsnap_v52 holds what scripts/accept_jrsnap_ndu.py recorded with the installed
JRSNAP_Input.exe: our candidate NDUs, JRSNAP's saved copies and record.json. These tests do not run JRSNAP. They
fail (never skip) when the input or the generated NDU is no longer the one JRSNAP read: then the acceptance must be
redone with ``uv run --project "." --locked python -X utf8 scripts/accept_jrsnap_ndu.py --overwrite``.
"""

import json
from pathlib import Path

import pytest

from recorded_input_support import input_sha256s
from webpier.core.integrity import load_json, sha256
from webpier.export.jrsnap.readback import Normalized, compare_readback, compare_state, parse_records, summarize
from webpier.inputs import parse_input
from webpier.pipeline.generate import export_bytes

ROOT = Path(__file__).parents[2]
EVIDENCE = ROOT / "tests" / "fixtures" / "acceptance" / "jrsnap_v52"
RECORD = json.loads((EVIDENCE / "record.json").read_text(encoding="utf-8"))
REDO = "受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_jrsnap_ndu.py --overwrite"
STAGES = ("0710", "0720")


@pytest.fixture(scope="module")
def generated():
    data = (ROOT / RECORD["input"]["path"]).read_bytes()
    assert RECORD["input"]["sha256"] in input_sha256s(data), f"受入時の入力から変わっています。{REDO}"
    pier = parse_input(load_json(data))
    return {stage: export_bytes(pier, stage, "jrsnap") for stage in STAGES}


def test_the_record_is_a_readback_in_jrsnap_5_2_l03_without_analysis():
    assert RECORD["kind"] == "jrsnap_ndu_acceptance" and RECORD["schema_version"] == 1
    assert {key: RECORD["application"][key] for key in ("file_version", "product_version", "assembly_version")} == {
        "file_version": "5.2.3.0", "product_version": "5.2.3.0", "assembly_version": "5.2.3.1"}
    assert RECORD["analysis_run"] is False and RECORD["gui_operated"] is False
    assert set(RECORD["directions"]) == set(STAGES)


@pytest.mark.parametrize("helper", sorted(RECORD["helpers"]))
def test_the_recorded_helpers_are_the_files_of_this_checkout(helper):
    """The helpers are stored with LF (.gitattributes), so their SHA-256 does not depend on core.autocrlf."""
    assert sha256((ROOT / helper).read_bytes()) == RECORD["helpers"][helper], f"{helper} が受入時から変わっています。{REDO}"


@pytest.mark.parametrize("stage", STAGES)
def test_the_accepted_candidate_is_what_the_generator_writes_now(generated, stage):
    direction = RECORD["directions"][stage]
    stored = (EVIDENCE / direction["candidate"]["path"]).read_bytes()
    assert sha256(stored) == direction["candidate"]["sha256"]
    assert sha256(generated[stage]) == direction["candidate"]["sha256"], f"{stage} の NDU が変わりました。{REDO}"


@pytest.mark.parametrize("stage", STAGES)
def test_jrsnap_saved_what_we_wrote(stage):
    direction = RECORD["directions"][stage]
    candidate = (EVIDENCE / direction["candidate"]["path"]).read_bytes()
    saved = (EVIDENCE / direction["saved"]["path"]).read_bytes()
    assert sha256(saved) == direction["saved"]["sha256"]
    assert direction["read_code"] == 0 and direction["write_code"] == 0 and direction["second_save_identical"]
    assert saved.startswith(b"Virsion=5.2.3.S.4\r\n")
    readback = compare_readback(candidate, saved)
    assert readback.records == direction["candidate"]["records"]
    # The only differences are JRSNAP's own number format of GanmaA (1.2 → 1.20, 1 → 1.00).
    assert readback.normalized == tuple(Normalized(**item) for item in direction["normalized"])
    assert {item.key for item in readback.normalized} == {"GanmaA"}
    summary = summarize(parse_records(saved))
    assert (summary["counts"], summary["combinations"]) == (direction["counts"], direction["combinations"])
    compare_state(parse_records(candidate), direction["jrsnap_state"])


def test_jrsnap_reads_every_combination_with_its_pattern_and_direction():
    """Decision 40: JRSNAP 5.2 reads a 0720 NDU with several SNAPConb, so one NDU is kept; decision 76: the four
    照査パターン (ρm, αf) of each, the down track 逆向 (G_intConbHoko 1)."""
    patterns = [(1, 1), (1.2, 1), (1, 2), (1.2, 2)]
    state = RECORD["directions"]["0720"]["jrsnap_state"]
    assert state["counts"]["G_intConbNum"] == 8
    assert [(c["coefficients"], (c["rho_m"], c["alpha_f"]), c["direction"]) for c in state["combinations"]] == [
        *(([1, 1, 1, 1, 1, 0, 1, 1, 1], pattern, 0) for pattern in patterns),
        *(([1, 1, 1, 1, 0, 1, 1, 1, 1], pattern, 1) for pattern in patterns)]
    state = RECORD["directions"]["0710"]["jrsnap_state"]
    assert state["counts"]["G_intConbNum"] == 4
    assert [((c["rho_m"], c["alpha_f"]), c["direction"]) for c in state["combinations"]] == [
        (pattern, 0) for pattern in patterns]
