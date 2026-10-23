"""The real-runner acceptance of the 0800 / 0810 / 0820 フーチングの照査 still belongs to the current generator
(decision 60).

tests/fixtures/acceptance/footing/record.json and input.json are what scripts/accept_footing.py recorded with the real
FrameWebforCS.Headless, JRSNAP.Headless, AggreSE.Headless and WebDanforCS.Headless. These tests do not run them. They
fail (never skip) when the input the acceptance was made from, or the FrameWeb and NDU files WebPier writes for it,
are no longer what the engines were given: then redo the acceptance with
``uv run --project "." --locked python -X utf8 scripts/accept_footing.py``.
"""

import json
from pathlib import Path

import pytest

from recorded_input_support import before_piles, upgrade_to_piles
from webpier.core.integrity import dump_json, load_json, sha256
from webpier.inputs import parse_input
from webpier.pipeline.generate import export_bytes

ROOT = Path(__file__).parents[2]
RECORDS = ROOT / "tests" / "fixtures" / "acceptance" / "footing"
REDO = "受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_footing.py"
SERVICE = ("short_term", "long_term")


@pytest.fixture(scope="module")
def accepted():
    record = json.loads((RECORDS / "record.json").read_text(encoding="utf-8"))
    raw = (ROOT / record["input"]["path"]).read_bytes()
    data = load_json(before_piles(raw) or raw)  # the input as it was recorded, before the pile foundation (decision 84)
    # Recorded before the input had the 出力項目, which are no condition of the calculation (decision 72, ADR-0011).
    chosen = data.pop("outputs")
    data["鉄筋"]["フーチング"] = record["input"]["footing_bars"]
    rebuilt = dump_json(data)
    assert sha256(rebuilt) == record["input"]["sha256"], f"受入時の入力から変わっています。{REDO}"
    assert sha256((RECORDS / record["input"]["file"]).read_bytes()) == record["input"]["sha256"]
    # ... and before the pile foundation (decision 84): the recorded file is read in the form of today.
    return record, parse_input(upgrade_to_piles({**load_json(rebuilt), "outputs": chosen}))


def test_the_record_is_accepted(accepted):
    record, _ = accepted
    assert (record["kind"], record["schema_version"], record["accepted"], record["failures"]) == (
        "footing_acceptance", 1, True, [])


def test_the_frameweb_and_ndu_files_are_what_the_generator_writes_now(accepted):
    record, pier = accepted
    for stage, name in (("0610", "線路方向.json"), ("0620", "線路直角方向.json")):
        assert sha256(export_bytes(pier, stage, "frameweb")) == record["engines"]["frameweb"][name], (
            f"{name} が受入時から変わっています。{REDO}")
    for stage, name in (("0710", "線路方向.ndu"), ("0720", "線路直角方向.ndu")):
        assert sha256(export_bytes(pier, stage, "jrsnap")) == record["engines"]["ndu"][name], (
            f"{name} が受入時から変わっています。{REDO}")


def test_the_recorded_columns_and_capacities_are_within_the_tolerances(accepted):
    """The four non-seismic columns of each direction against the sample (0.25 kN, the 使用性 Vd 0.5 kN), the seismic
    column at a step that reached Rvd, and the 線路方向 Mud of Capacita against the sample 255 within 0.2 %."""
    record, _ = accepted
    for direction, found in record["directions"].items():
        for key in ("safety_moment", "safety_shear", *SERVICE):
            column = found["columns"][key]
            for name in found["compared"]:
                limit = record["service_vd_tolerance"] if name == "vd" and key in SERVICE else record["tolerance"]
                assert abs(column["differences"][name]) <= limit, (direction, key, name)
        seismic = found["columns"]["seismic"]["ours"]
        assert seismic["step"] >= 1 and seismic["vd"] >= seismic["rvd"] and seismic["case_name"]
    mud = float(record["directions"]["longitudinal"]["check"]["sections"]["bending_safety_destruction"]["capacity"])
    assert abs(mud - record["sample_mud"]["0810"]) / record["sample_mud"]["0810"] < record["capacity_tolerance"]
