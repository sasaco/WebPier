"""The Capacita runner of the joint of a steel pipe pile (decision 90): the stand-in of tests/fixtures/capacita answers
``run-pile-joint`` (its modes stand for the runner's failures); the calculation it stands for is HsCalc's, in Capacita."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from webpier.calc.pile_body import steel
from webpier.calc.pile_joint import section, select
from webpier.export.capacita.pile_joint import build, row_id, write
from webpier.pipeline.fempython import RunnerError
from webpier.pipeline.pilejoint import check_joint
from pile_joint_support import ROWS, example4_input, head_line

RUNNER = Path(__file__).parents[1] / "fixtures" / "capacita" / "fake_runner.py"
IDS = {"1", "2"}


def content():
    pier = example4_input()
    return write(section(pier, steel(pier)), [select(row, row + 6, 3, [head_line(*ROWS[row])]) for row in (1, 2)])


@pytest.fixture
def runner(tmp_path):
    script = tmp_path / "run-pile-joint-stand-in.cmd"
    script.write_text(f'@"{sys.executable}" "{RUNNER}" %*\r\n', encoding="utf-8")
    return script


def test_the_input_is_the_section_the_safety_factors_and_the_axial_force_of_each_side():
    pier = example4_input()
    found = build(section(pier, steel(pier)), [select(row, row + 6, 3, [head_line(*ROWS[row])]) for row in (1, 2)])
    assert found["pipe"] == {"outerDiameter": 798.0, "thickness": 17.0, "fsyk": 315.0}
    assert found["rebar"] == {"diameter": 38.0, "count": 16, "fsyk": 390.0, "edgeDistance": 75.0}
    assert found["concrete"] == {"fck": 27.0} and found["safety"] == {"gammaC": 1.3, "gammaS": 1.0, "gammaPipe": 1.0}
    assert found["rows"] == [{"id": "1", "axialForce": 1338.1}, {"id": "2", "axialForce": 3847.9}]
    assert row_id(2) == "2" and json.loads(content()) == found


def test_the_moments_are_those_of_the_runner_by_row(runner):
    moments, version = check_joint(content(), IDS, runner)
    assert version == "fake-1" and moments == {"1": 2594.0, "2": 2957.9}


@pytest.mark.parametrize("mode, message", [
    ("joint-fail", "HsCalc が計算できません"),
    ("joint-engine", "やり取りの版が違います"),
    ("joint-version", "runner の版（engineVersion）がありません"),
    ("joint-artifacts", "成果物が計算結果の1つではありません"),
    ("joint-missing", "result.json がありません"),
    ("joint-sha", "SHA256・バイト数と一致しません"),
    ("joint-short", "計算結果の行が依頼に合いません"),
    ("joint-duplicate", "計算結果の行が重複しています"),
    ("joint-text-value", "計算結果の行が読めません"),
])
def test_a_runner_that_fails_or_answers_wrongly_stops_the_check(monkeypatch, runner, mode, message):
    monkeypatch.setenv("FAKE_CAPACITA", mode)
    with pytest.raises(RunnerError, match=f"pile-joint.json で鋼管杭の結合部の照査ができません: .*{message}"):
        check_joint(content(), IDS, runner)


def _answer(monkeypatch, *, stdout=None, result=None, error=None):
    """Replace the process: it raises *error*, or answers *stdout*, or answers the envelope of a result.json of *result*."""
    def run(command, **options):
        if error is not None:
            raise error
        if result is not None:
            output = Path(command[command.index("--output-dir") + 1])
            output.mkdir(parents=True)
            (output / "result.json").write_bytes(result)
            artifact = {"kind": "result", "relativePath": "result.json", "bytes": len(result),
                        "sha256": hashlib.sha256(result).hexdigest()}
            body = {"protocolVersion": 1, "engine": "webdan2", "ok": True, "executionStatus": "success",
                    "engineVersion": "fake-1", "artifacts": [artifact]}
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(body).encode(), stderr=b"")
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")
    monkeypatch.setattr("webpier.pipeline.pilejoint.subprocess.run", run)


@pytest.mark.parametrize("answer, message", [
    ({"error": subprocess.TimeoutExpired("runner", 5)}, "秒で終わりませんでした"),
    ({"error": OSError("no such file")}, "runner を起動できません"),
    ({"stdout": b"\xff"}, "runner の応答が JSON ではありません"),
    ({"stdout": b"[]"}, "runner の応答が JSON のオブジェクトではありません"),
    ({"result": b"\xff"}, "計算結果が JSON ではありません"),
    ({"result": b"[]"}, "計算結果に rows がありません"),
])
def test_a_process_that_does_not_start_or_does_not_answer_in_json_stops_the_check(monkeypatch, runner, answer, message):
    _answer(monkeypatch, **answer)
    with pytest.raises(RunnerError, match=f"pile-joint.json で鋼管杭の結合部の照査ができません: .*{message}"):
        check_joint(content(), IDS, runner)
