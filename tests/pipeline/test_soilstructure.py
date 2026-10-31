"""The SoilStructure runner of the 地盤変位 (decision 97, CONTEXT.md 地盤変位).

The runner is found from STRUCTURAL_MCP_SOILSTRUCTURE_RUNNER (environment, then .env) and called as
``run-ground-displacement`` without its report and its JOT. Its envelope and its one file are checked as the
SoilStructure README states. Every case but the last uses the stand-in of tests/fixtures/soilstructure/fake_runner.py
(tests/conftest.py); the last runs the real runner on the layers of Example橋脚4 IV-4, only when one is set up.
"""

from __future__ import annotations

from decimal import Decimal
import json
import math
import os
from pathlib import Path
import subprocess

import pytest

from webpier.calc.ground_displacement import RunnerRow
from webpier.pipeline.fempython import RunnerError
from webpier.pipeline.soilstructure import RUNNER_KEY, calculate, document, runner_path

ROWS = (RunnerRow("1", Decimal("1.000"), Decimal("18.0"), Decimal("170")), RunnerRow("1", Decimal("1.800"), None, None),
        RunnerRow("2", Decimal("2.600"), Decimal("18.0"), Decimal("120")))


def test_the_environment_comes_before_the_env_file(tmp_path: Path):
    runner, other = tmp_path / "runner.exe", tmp_path / "other.exe"
    runner.write_bytes(b""), other.write_bytes(b"")
    env = tmp_path / ".env"
    env.write_text(f"{RUNNER_KEY}='{other}'\n", encoding="utf-8")
    assert runner_path({RUNNER_KEY: str(runner)}, env) == runner
    assert runner_path({}, env) == other


def test_the_headless_runner_reads_only_the_environment(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(f"{RUNNER_KEY}='{tmp_path / 'other.exe'}'\n", encoding="utf-8")
    with pytest.raises(RunnerError, match=f"環境変数 {RUNNER_KEY} に SoilStructure.Headless.exe の絶対パスを設定してください"):
        runner_path({}, env, dotenv=False)


@pytest.mark.parametrize("setting,message", [(None, "SoilStructure の runner が設定されていません"),
                                             ("runner.exe", "絶対パス"), ("missing", "ありません")])
def test_a_runner_that_is_not_set_up_is_an_error(tmp_path: Path, setting, message):
    env = tmp_path / ".env"
    if setting is not None:
        value = str(tmp_path / "missing.exe") if setting == "missing" else setting
        env.write_text(f"{RUNNER_KEY}={value}\n", encoding="utf-8")
    with pytest.raises(RunnerError, match=message):
        runner_path({}, env)


def test_the_process_environment_is_used_by_default(fake_soilstructure_runner: Path):
    assert runner_path() == Path(os.environ[RUNNER_KEY])


def test_the_document_has_the_rows_as_text_and_the_unused_pile_items_at_zero():
    content = json.loads(document(ROWS, Decimal("0.85")))
    ground = content["groundDisplacement"]
    assert content["schemaVersion"] == 1 and content["soilRows"] == [] and content["pile"]["diameterM"] == 0
    assert (ground["standardDesignSeismicCoefficient"], ground["regionalCoefficient"]) == (1.0, 0.85)
    assert (ground["includeL1"], ground["includeL2"], ground["l2Spectrum"]) == (True, True, 2)
    assert ground["rows"] == [
        {"layerNumber": "1", "thicknessM": "1.000", "unitWeightKnPerM3": "18.0", "shearWaveVelocityMPerSecond": "170"},
        {"layerNumber": "1", "thicknessM": "1.800", "unitWeightKnPerM3": None, "shearWaveVelocityMPerSecond": None},
        {"layerNumber": "2", "thicknessM": "2.600", "unitWeightKnPerM3": "18.0", "shearWaveVelocityMPerSecond": "120"}]


def test_the_stand_in_answers_tg_and_the_points_of_the_rows(fake_soilstructure_runner: Path):
    answer = calculate(ROWS, Decimal("1.0"), fake_soilstructure_runner)
    tg = 4 * (2.8 / 170 + 2.6 / 120)  # the stand-in's quarter wave (its docstring), by hand
    assert answer.period == pytest.approx(tg) and answer.engine_version == "1.3.0"
    assert [point["depthM"] for point in answer.points] == pytest.approx([0, 1.0, 2.8, 5.4])
    assert answer.points[0]["l2SpectrumTwoDisplacementMm"] == pytest.approx(0.413 * tg * 1000)
    assert answer.points[1]["l1DisplacementMm"] == pytest.approx(0.064 * tg ** 2.1 * 1000 * math.cos(math.pi / 10.8))
    assert answer.document == document(ROWS, Decimal("1.0")) and json.loads(answer.result)["points"] == list(answer.points)


@pytest.mark.parametrize("mode,message", [
    ("fail", "invalid_document: FAKE refused the document"), ("text", "応答が JSON ではありません"),
    ("protocol", "やり取りの版が違います"), ("version", "版（engineVersion）がありません"),
    ("artifacts", "結果（result.json）の1つではありません"), ("missing", "result.json がありません"),
    ("sha", "SHA256・バイト数と一致しません"), ("extra", "出力先のファイルが成果物の一覧と一致しません"),
    ("result", "固有周期（groundNaturalPeriodSeconds）と各点の地盤変位（points）がありません"),
    ("notjson", "result.json が JSON ではありません"), ("exit", "終了コード 4"),
])
def test_a_runner_that_does_not_answer_is_an_error(fake_soilstructure_runner: Path, monkeypatch: pytest.MonkeyPatch,
                                                   mode, message):
    monkeypatch.setenv("FAKE_SOILSTRUCTURE", mode)
    with pytest.raises(RunnerError, match=f"SoilStructure で地盤変位を算定できません: .*{message}"):
        calculate(ROWS, Decimal("1.0"), fake_soilstructure_runner)


def test_an_envelope_that_is_not_an_object_is_an_error(monkeypatch: pytest.MonkeyPatch, fake_soilstructure_runner: Path):
    monkeypatch.setattr(subprocess, "run",
                        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, b"[]", b""))
    with pytest.raises(RunnerError, match="JSON のオブジェクトではありません"):
        calculate(ROWS, Decimal("1.0"), fake_soilstructure_runner)


def test_a_runner_that_cannot_start_is_an_error(tmp_path: Path):
    runner = tmp_path / "runner.exe"
    runner.write_bytes(b"not a program")
    with pytest.raises(RunnerError, match="runner を起動できません"):
        calculate(ROWS, Decimal("1.0"), runner)


def test_a_runner_that_does_not_finish_is_an_error(fake_soilstructure_runner: Path, monkeypatch: pytest.MonkeyPatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout", 1))

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(RunnerError, match="秒で終わりませんでした"):
        calculate(ROWS, Decimal("1.0"), fake_soilstructure_runner, timeout=1)


# Example橋脚4 IV-4: the surface ground (layer, thickness m, γ kN/m3, Vs m/s) and IV-5・IV-6: f(z) at the top of each layer
EXAMPLE4 = (("1", "2.70", 17, 170), ("2", "3.75", 15, 120), ("3", "7.50", 16, 140), ("4", "1.95", 18, 180),
            ("5", "13.30", 18, 330), ("6", "5.00", 18, 330))
EXAMPLE4_L1 = (17.11, 16.81, 13.84, 6.05, 4.67, 1.36)
EXAMPLE4_L2 = (220.34, 216.49, 178.32, 77.96, 60.12, 17.56)


def test_the_real_runner_gives_the_example4_surface_ground(real_soilstructure_runner: Path):
    """Decision 97 受入 (1): Tg 0.5335 s; f(z) within 0.03 mm of ReDisp-JR's (SoilDisp works in single precision)."""
    rows = tuple(RunnerRow(number, Decimal(thickness), Decimal(gamma), Decimal(velocity))
                 for number, thickness, gamma, velocity in EXAMPLE4)
    answer = calculate(rows, Decimal("1.0"), real_soilstructure_runner)
    assert round(answer.period, 4) == 0.5335
    tops = [0.0, 2.7, 6.45, 13.95, 15.9, 29.2]
    found = {round(point["depthM"], 3): point for point in answer.points}
    assert [found[top]["l1DisplacementMm"] for top in tops] == pytest.approx(EXAMPLE4_L1, abs=0.03)
    assert [found[top]["l2SpectrumTwoDisplacementMm"] for top in tops] == pytest.approx(EXAMPLE4_L2, abs=0.03)
