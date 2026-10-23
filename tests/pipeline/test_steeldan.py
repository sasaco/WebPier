"""The SteelDan runner of the pile body of a steel pipe pile (decision 89): the stand-in of tests/fixtures/capacita answers
``run-steel`` (its modes stand for the runner's failures); the calculation it stands for is Capacita's."""

import json
import sys
from pathlib import Path

import pytest

from webpier.pipeline.fempython import RunnerError
from webpier.pipeline.steeldan import check_pile

RUNNER = Path(__file__).parents[1] / "fixtures" / "capacita" / "fake_runner.py"


def wsj(rows=(1,)):
    """A WSJ of the pile rows *rows*: D 798, t 17, SKK490, the cases 6, 7 and 8 of one pile each."""
    def force(index):
        return {"index": index, "6_Md": 139.0, "6_Vd": 31.3, "6_Nd": 3480.9, "7_Md": 97.3, "7_Vd": 154.3, "7_Nd": 3784.8,
                "8_Md": 75.4, "8_Vd": 133.0, "8_Nd": 4609.4}

    document = {
        "members": [{"m_no": row, "n": 1} for row in rows], "points": [{"index": row, "m_no": row} for row in rows],
        "sections": [{"index": row, "h": 798.0, "t": 17.0} for row in rows], "force": [force(row) for row in rows],
        "safety": {"safety_factor": {"1": [{}, {"ri": 1.2, "rb_T": 1.05, "rb_C": 1.05, "rb_S": 1.05, "rs": 1.05}, {}]},
                   "material_steel": {"1": [{"fsyk": 315.0, "fsvyk": 180.0}] * 3}}}
    return json.dumps(document).encode("utf-8")


@pytest.fixture
def runner(tmp_path):
    """The stand-in as an executable the runner calls (a command file that runs the interpreter with the script)."""
    script = tmp_path / "run-steel-stand-in.cmd"
    script.write_text(f'@"{sys.executable}" "{RUNNER}" %*\r\n', encoding="utf-8")
    return script


def test_the_values_are_those_of_the_checks_by_row_case_and_kind(runner):
    values, version = check_pile(wsj((1, 2)), {1, 2}, runner)
    assert version == "fake-1" and len(values) == 2 * 3 * 3
    first = values[(1, 6, "bending")]
    assert (first["A"], first["I"], first["y"], first["Nud"], first["Mutd"]) == (0.04171, 0.00318176, 399.0, 11917.1, 2278.4)
    assert values[(1, 7, "shear")]["ratio"] == 0.03 and values[(2, 6, "combined")]["ratio"] == 0.15  # tables 3.2.7 and 3.2.9


@pytest.mark.parametrize("mode, message", [
    ("steel-fail", "SD-FORCE-CASE: 断面力がありません"),
    ("steel-engine", "やり取りの版が違います"),
    ("steel-version", "runner の版（engineVersion）がありません"),
    ("steel-artifacts", "成果物が計算結果の1つではありません"),
    ("steel-missing", "result.json がありません"),
    ("steel-sha", "SHA256・バイト数と一致しません"),
    ("steel-short", "計算結果の照査が杭列とケースの組に合いません"),
    ("steel-duplicate", "計算結果の照査が重複しています"),
    ("steel-text-value", "計算結果の値が数値ではありません"),
])
def test_a_runner_that_fails_or_answers_wrongly_stops_the_check(monkeypatch, runner, mode, message):
    monkeypatch.setenv("FAKE_CAPACITA", mode)
    with pytest.raises(RunnerError, match=f"pile.wsj で鋼管杭の杭体の照査ができません: .*{message}"):
        check_pile(wsj(), {1}, runner)


@pytest.mark.parametrize("mode, message", [("exit", "runner の応答が JSON ではありません"), ("text", "JSON ではありません"), ("list", "JSON のオブジェクトではありません")])
def test_a_runner_whose_answer_is_not_an_envelope_is_named(monkeypatch, runner, mode, message):
    monkeypatch.setenv("FAKE_CAPACITA", mode)
    with pytest.raises(RunnerError, match=message):
        check_pile(wsj(), {1}, runner)


def test_a_row_that_was_not_asked_for_is_an_error(runner):
    with pytest.raises(RunnerError, match="余分"):
        check_pile(wsj((1, 2)), {1}, runner)


def test_a_runner_that_cannot_be_started_is_named(tmp_path):
    with pytest.raises(RunnerError, match="runner を起動できません"):
        check_pile(wsj(), {1}, tmp_path / "missing.exe")


def crafted(tmp_path, result: bytes):
    """A runner that returns an envelope for *result* as its result.json whatever it is given."""
    import hashlib

    envelope = {"protocolVersion": 1, "engine": "steeldan", "engineVersion": "x", "ok": True, "executionStatus": "success",
                "messages": [], "artifacts": [{"kind": "result", "relativePath": "result.json", "bytes": len(result),
                                               "sha256": hashlib.sha256(result).hexdigest()}]}
    code = tmp_path / "crafted.py"
    code.write_text("import sys, json, pathlib\n"
                    "out = pathlib.Path(sys.argv[sys.argv.index('--output-dir') + 1])\n"
                    "out.mkdir(parents=True)\n"
                    f"(out / 'result.json').write_bytes({result!r})\n"
                    f"print(json.dumps({envelope!r}))\n", encoding="utf-8")
    script = tmp_path / "crafted.cmd"
    script.write_text(f'@"{sys.executable}" "{code}" %*\r\n', encoding="utf-8")
    return script


@pytest.mark.parametrize("result, message", [
    (b"not json", "計算結果が JSON ではありません"),
    (b"[]", "計算結果に verifications がありません"),
    (b'{"verifications": {}}', "計算結果に verifications がありません"),
    (b'{"verifications": [{"kind": "other", "pointIndex": 1, "values": {}}]}', "計算結果の照査が読めません"),
    (b'{"verifications": [{"kind": "pipePileShear", "pointIndex": "1", "values": {}}]}', "計算結果の照査が読めません"),
    (b'{"verifications": [3]}', "計算結果の照査が読めません"),
])
def test_a_result_that_is_not_the_verifications_of_the_check_is_named(tmp_path, result, message):
    with pytest.raises(RunnerError, match=message):
        check_pile(wsj(), {1}, crafted(tmp_path, result))


def test_a_runner_that_does_not_finish_is_named(monkeypatch, runner):
    import subprocess

    def hang(*arguments, **options):
        raise subprocess.TimeoutExpired(arguments[0], 1)

    monkeypatch.setattr(subprocess, "run", hang)
    with pytest.raises(RunnerError, match="1 秒で終わりませんでした"):
        check_pile(wsj(), {1}, runner, timeout=1)


def test_a_runner_that_fails_without_saying_why_is_named_by_its_exit_code(monkeypatch, runner):
    import subprocess

    def silent(arguments, **options):
        return subprocess.CompletedProcess(arguments, 7, stdout=json.dumps({
            "protocolVersion": 1, "engine": "steeldan", "ok": False, "executionStatus": "failed", "messages": []}).encode(), stderr=b"")

    monkeypatch.setattr(subprocess, "run", silent)
    with pytest.raises(RunnerError, match="終了コード 7"):
        check_pile(wsj(), {1}, runner)
