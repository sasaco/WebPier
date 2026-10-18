"""The JRSNAP runner that draws the データ確認図 of 0710 (decision 50) and does the static nonlinear analysis of 0711
(decision 47, ADR-0007).

The runner is found from STRUCTURAL_MCP_JRSNAP_RUNNER (environment, then .env) and called with the NDU under its own
name; its envelope and the files of its output folder are checked as the Headless protocol states. Every case uses
the stand-in of tests/fixtures/jrsnap/fake_runner.py (tests/conftest.py); the real runner needs JRSNAP and shows its
windows, so it is checked only in the real-app acceptance.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf
import pytest

from webpier.pipeline import jrsnap
from webpier.pipeline.fempython import RunnerError
from webpier.pipeline.jrsnap import RUNNER_KEY, analyze_nonlinear, draw_data_check, runner_path

CASE = "線路方向(Case1_ρm10_αf1_正向)"


def expected(name: str, document: bytes) -> dict[str, bytes]:
    """What the stand-in returns for *document* as *name* (its docstring), written out without the implementation."""
    digest = hashlib.sha256(document).hexdigest()
    return {f"{CASE}.{suffix}": f"FAKE {word} {name} {digest}\n".encode("utf-8")
            for suffix, word in (("ndt", "NDT"), ("DB1", "DB1"), ("LOG", "LOG"), ("OUT", "OUT"))}


def test_the_environment_comes_before_the_env_file(tmp_path: Path):
    runner, other = tmp_path / "runner.exe", tmp_path / "other.exe"
    runner.write_bytes(b""), other.write_bytes(b"")
    env = tmp_path / ".env"
    env.write_text(f"{RUNNER_KEY}='{other}'\nSTRUCTURAL_MCP_FEMPYTHON_RUNNER=x\n", encoding="utf-8")
    assert runner_path({RUNNER_KEY: str(runner)}, env) == runner
    assert runner_path({RUNNER_KEY: ""}, env) == other
    assert runner_path({}, env) == other


@pytest.mark.parametrize("setting,message", [(None, "JRSNAP の runner が設定されていません"), ("", "設定されていません"),
                                             ("runner.exe", "絶対パス"), ("missing", "ありません")])
def test_a_runner_that_is_not_set_up_is_an_error(tmp_path: Path, setting, message):
    env = tmp_path / ".env"
    if setting is not None:
        value = str(tmp_path / "missing.exe") if setting == "missing" else setting
        env.write_text(f"{RUNNER_KEY}={value}\n", encoding="utf-8")
    with pytest.raises(RunnerError, match=message):
        runner_path({}, env)


def test_the_process_environment_is_used_by_default(monkeypatch: pytest.MonkeyPatch, fake_jrsnap_runner: Path):
    monkeypatch.setenv(RUNNER_KEY, str(fake_jrsnap_runner))
    assert runner_path() == fake_jrsnap_runner


def test_the_stand_in_analyzes_the_given_bytes(fake_jrsnap_runner: Path):
    document = b"Virsion=5.2.3.S.4\r\n"
    solved = analyze_nonlinear("線路方向.ndu", document, fake_jrsnap_runner)
    assert solved.engine_version == "fake-1"
    assert dict(solved.files) == expected("線路方向.ndu", document)
    assert solved.summary["jrsnap"] == {"product": "5.2-L03", "assemblyVersion": "5.2.3.1"}
    assert solved.messages == ({"level": "warning", "code": "LOG_WARNING", "text": "FAKE WARNING"},)


@pytest.mark.parametrize("mode,message", [
    ("fail", "ANALYSIS_FAILED: S_ANALYSIS.exe ended with exit code 1"), ("exit", "JSON ではありません"),
    ("text", "JSON ではありません"), ("list", "オブジェクトではありません"), ("protocol", "やり取りの版が違います"),
    ("version", "engineVersion"), ("summary", "summary・messages がありません"),
    ("artifacts", "解析用データと解析結果のファイルではありません"), ("kind", "解析用データと解析結果のファイルではありません"),
    ("nested", "解析用データと解析結果のファイルではありません"), ("nondt", "解析用データと解析結果のファイルではありません"),
    ("missing", "出力先のファイルが成果物の一覧と一致しません"), ("extra", "出力先のファイルが成果物の一覧と一致しません"),
    ("sha", r"\.OUT が runner の応答の SHA256・バイト数と一致しません"),
])
def test_a_runner_that_does_not_analyze_the_ndu_is_an_error(fake_jrsnap_runner: Path, monkeypatch: pytest.MonkeyPatch,
                                                             mode, message):
    monkeypatch.setenv("FAKE_JRSNAP", mode)
    with pytest.raises(RunnerError, match=f"線路方向.ndu を JRSNAP で静的非線形解析できません: .*{message}"):
        analyze_nonlinear("線路方向.ndu", b"NDU", fake_jrsnap_runner)


def test_a_runner_without_an_output_folder_returned_nothing(fake_jrsnap_runner: Path, monkeypatch: pytest.MonkeyPatch):
    """An envelope that lists files the runner never wrote, not even a folder."""
    monkeypatch.setattr(jrsnap.subprocess, "run", lambda *args, **kwargs: jrsnap.subprocess.CompletedProcess(
        args, 0, ('{"protocolVersion": 1, "engine": "jrsnap", "engineVersion": "x", "ok": true, "executionStatus": '
                  '"success", "summary": {}, "messages": [], "artifacts": [{"kind": "ndt", "relativePath": "a.ndt", '
                  '"bytes": 0, "sha256": ""}]}').encode(), b""))
    with pytest.raises(RunnerError, match=r"出力先のファイルが成果物の一覧と一致しません（\[\]）"):
        analyze_nonlinear("線路方向.ndu", b"NDU", fake_jrsnap_runner)


def test_an_analysis_that_cannot_start_or_does_not_finish_is_an_error(tmp_path: Path, fake_jrsnap_runner: Path,
                                                                     monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(RunnerError, match="線路方向.ndu を JRSNAP で静的非線形解析できません: runner を起動できません"):
        analyze_nonlinear("線路方向.ndu", b"NDU", tmp_path / "missing.exe")
    monkeypatch.setenv("FAKE_JRSNAP", "slow")
    with pytest.raises(RunnerError, match="秒で終わりませんでした"):
        analyze_nonlinear("線路方向.ndu", b"NDU", fake_jrsnap_runner, timeout=0.5)


def test_webpier_waits_longer_than_the_runner_gives_the_analysis():
    assert (jrsnap.ANALYSIS_TIMEOUT, jrsnap.TIMEOUT) == (1800, 1860)


def test_the_stand_in_draws_each_figure_of_the_data_check_in_order(fake_jrsnap_runner: Path):
    """Decision 50: the pages of the five figures, for the given bytes, in the order of the report."""
    document = b"Virsion=5.2.3.S.4\r\nSNAPConbNum=2\r\n"
    drawn = draw_data_check("線路直角方向.ndu", document, fake_jrsnap_runner)
    digest = hashlib.sha256(document).hexdigest()
    with pymupdf.open(stream=drawn.pdf, filetype="pdf") as pdf:
        assert [page.get_text().strip() for page in pdf] == [
            f"FAKE DATA CHECK {figure} {digest[:16]}" for figure in jrsnap.DATA_CHECK_FIGURES]
    assert jrsnap.DATA_CHECK_FIGURES == ("nonlinear-numbers", "section-numbers", "element-table", "section-detail",
                                         "node-springs")
    assert drawn.engine_version == "fake-1"
    assert drawn.summary["case"] == {"case": 1, "ndt": "線路直角方向(Case1_ρm10_αf1_正向).ndt", "sha256": digest}


@pytest.mark.parametrize("mode,message", [
    ("fail", "UNKNOWN_DIALOG: S_DataCheck showed"), ("exit", "JSON ではありません"), ("text", "JSON ではありません"),
    ("protocol", "やり取りの版が違います"), ("summary", "summary・messages がありません"),
    ("order", "データ確認図の図ごとの PDFではありません"), ("kind", "データ確認図の図ごとの PDFではありません"),
    ("missing", "出力先のファイルが成果物の一覧と一致しません"),
    ("sha", r"node-springs\.pdf が runner の応答の SHA256・バイト数と一致しません"),
    ("empty", r"node-springs\.pdf にページがありません"), ("broken", r"node-springs\.pdf を読めません"),
])
def test_a_runner_that_does_not_draw_the_data_check_is_an_error(fake_jrsnap_runner: Path,
                                                                monkeypatch: pytest.MonkeyPatch, mode, message):
    monkeypatch.setenv("FAKE_JRSNAP_DATA_CHECK", mode)
    with pytest.raises(RunnerError, match=f"線路方向.ndu のデータ確認図を JRSNAP で描けません: .*{message}"):
        draw_data_check("線路方向.ndu", b"NDU", fake_jrsnap_runner)


def test_a_data_check_that_does_not_finish_is_an_error(fake_jrsnap_runner: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_JRSNAP_DATA_CHECK", "slow")
    with pytest.raises(RunnerError, match="データ確認図を JRSNAP で描けません: 0.5 秒で終わりませんでした"):
        draw_data_check("線路方向.ndu", b"NDU", fake_jrsnap_runner, timeout=0.5)
    assert (jrsnap.DATA_CHECK_TIMEOUT, jrsnap.DATA_CHECK_WAIT) == (300, 360)
