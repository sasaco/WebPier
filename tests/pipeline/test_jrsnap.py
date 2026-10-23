"""The JRSNAP runner that draws the データ確認図 and the 荷重図 of 0710 and 0720 (decisions 50, 51) and does the static
nonlinear analysis of 0711 and 0721 (decision 47, ADR-0007).

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
from webpier.pipeline.jrsnap import RUNNER_KEY, SOIL_REPORT, analyze_nonlinear, calculate_ground, draw_figures, runner_path
from webpier.reporting.stages.insertion import DATA_CHECK, LOAD_DIAGRAM

CASE = "線路方向(Case1_ρm10_αf1_正向)"
# 0720: two combinations and nine basic cases; CASE-6 (the down track) is drawn from combination 2 (decision 51).
TRANSVERSE = b"Virsion=5.2.3.S.4\r\nLoadNum=9\r\nSNAPConbNum=2\r\n"
TRANSVERSE_CASES = tuple((case, 2 if case == 6 else 1) for case in range(1, 10))
# One combination and two basic cases, for the errors.
SMALL = b"NDU\r\nLoadNum=2\r\n"
SMALL_CASES = ((1, 1), (2, 1))


def texts(pdf: bytes) -> list[str]:
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        return [page.get_text().strip() for page in document]


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


def test_the_headless_runner_reads_only_the_environment(tmp_path: Path):
    """Decision 61: without dotenv a runner set only in the .env file is not set."""
    runner, other = tmp_path / "runner.exe", tmp_path / "other.exe"
    runner.write_bytes(b""), other.write_bytes(b"")
    env = tmp_path / ".env"
    env.write_text(f"{RUNNER_KEY}='{other}'\n", encoding="utf-8")
    assert runner_path({RUNNER_KEY: str(runner)}, env, dotenv=False) == runner
    with pytest.raises(RunnerError, match=f"環境変数 {RUNNER_KEY} に JRSNAP.Headless.exe の絶対パスを設定してください"):
        runner_path({}, env, dotenv=False)


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


def test_the_stand_in_draws_the_figures_and_each_case_from_its_combination(fake_jrsnap_runner: Path):
    """Decisions 50, 51 (0720): the pages of the five figures in the order of the report, then one load diagram page
    per basic case in case order, CASE-6 from combination 2 and the others from combination 1."""
    figures = draw_figures("線路直角方向.ndu", TRANSVERSE, fake_jrsnap_runner, TRANSVERSE_CASES)
    digest = hashlib.sha256(TRANSVERSE).hexdigest()[:16]
    assert texts(figures.data_check) == [f"FAKE DATA CHECK {figure} {digest}" for figure in jrsnap.DATA_CHECK_FIGURES]
    assert texts(figures.load_diagram) == [f"FAKE LOAD DIAGRAM COMB {2 if case == 6 else 1} CASE {case} {digest}"
                                           for case in range(1, 10)]
    assert figures.pages == {DATA_CHECK: figures.data_check, LOAD_DIAGRAM: figures.load_diagram}
    assert figures.load_cases == TRANSVERSE_CASES
    assert figures.engine_version == "fake-1"
    sha = hashlib.sha256(TRANSVERSE).hexdigest()
    assert figures.summary["dataCheck"] == {
        "combination": 1, "ndt": "線路直角方向(Case1_ρm10_αf1_正向).ndt", "sha256": sha,
        "figures": [{"figure": figure, "file": f"{figure}.pdf", "pages": 1} for figure in jrsnap.DATA_CHECK_FIGURES]}
    assert [(item["combination"], item["file"], [page["case"] for page in item["pages"]])
            for item in figures.summary["loadDiagram"]] == [
        (1, "load-diagram-1.pdf", list(range(1, 10))), (2, "load-diagram-2.pdf", list(range(1, 10)))]
    assert figures.summary["loadDiagram"][1]["pages"][5] == {"page": 6, "case": 6, "title": "CASE-6 FAKE"}


def test_the_figures_are_asked_for_once_with_the_time_of_every_combination(fake_jrsnap_runner: Path,
                                                                           monkeypatch: pytest.MonkeyPatch):
    calls = []
    run = jrsnap.subprocess.run

    def recording(command, **kwargs):
        calls.append((command[1], command[6:], kwargs["timeout"]))
        return run(command, **kwargs)

    monkeypatch.setattr(jrsnap.subprocess, "run", recording)
    draw_figures("線路直角方向.ndu", TRANSVERSE, fake_jrsnap_runner, TRANSVERSE_CASES)
    draw_figures("線路方向.ndu", SMALL, fake_jrsnap_runner, SMALL_CASES, timeout=100)
    figures = ",".join(jrsnap.DATA_CHECK_FIGURES)
    assert calls == [
        ("figures", ["--data-check", figures, "--data-check-combination", "1", "--load-diagram", "1,2",
                     "--timeout-seconds", "540"], 600),
        ("figures", ["--data-check", figures, "--data-check-combination", "1", "--load-diagram", "1",
                     "--timeout-seconds", "420"], 100)]
    assert (jrsnap.DATA_CHECK_COMBINATION, jrsnap.FIGURES_TIMEOUT, jrsnap.LOAD_DIAGRAM_TIMEOUT) == (1, 300, 120)
    assert jrsnap.DATA_CHECK_FIGURES == ("nonlinear-numbers", "section-numbers", "element-table", "section-detail",
                                         "node-springs")


def test_the_load_diagram_pages_follow_the_order_of_the_cases_asked_for(fake_jrsnap_runner: Path):
    """Only the combinations named are drawn, and the pages are taken in the order given."""
    figures = draw_figures("線路直角方向.ndu", TRANSVERSE, fake_jrsnap_runner, ((6, 2), (5, 2)))
    digest = hashlib.sha256(TRANSVERSE).hexdigest()[:16]
    assert texts(figures.load_diagram) == [f"FAKE LOAD DIAGRAM COMB 2 CASE {case} {digest}" for case in (6, 5)]
    assert [item["combination"] for item in figures.summary["loadDiagram"]] == [2]


@pytest.mark.parametrize("load_cases", [(), ((1, 1), (1, 2)), ((1, 0),), ((1, 1), (2, -1))])
def test_cases_that_cannot_be_drawn_are_a_programming_error(fake_jrsnap_runner: Path, load_cases):
    with pytest.raises(ValueError, match="荷重図のケースと組合せが不正です"):
        draw_figures("線路方向.ndu", SMALL, fake_jrsnap_runner, load_cases)


@pytest.mark.parametrize("mode,message", [
    ("fail", "UNKNOWN_DIALOG: S_DataCheck showed"), ("exit", "JSON ではありません"), ("text", "JSON ではありません"),
    ("protocol", "やり取りの版が違います"), ("summary", "summary・messages がありません"),
    ("order", "データ確認図の図ごとの PDF と組合せごとの荷重図の PDFではありません"),
    ("kind", "データ確認図の図ごとの PDF と組合せごとの荷重図の PDFではありません"),
    ("nocomb", "データ確認図の図ごとの PDF と組合せごとの荷重図の PDFではありません"),
    ("missing", "出力先のファイルが成果物の一覧と一致しません"),
    ("sha", r"load-diagram-1\.pdf が runner の応答の SHA256・バイト数と一致しません"),
    ("empty", r"node-springs\.pdf にページがありません"), ("broken", r"node-springs\.pdf を読めません"),
    ("nodiagram", r"組合せ 1 の荷重図のページ（summary\.loadDiagram）がありません"),
    ("pages", r"load-diagram-1\.pdf のページが runner の応答（summary\.loadDiagram）と一致しません"),
    ("nocase", "組合せ 1 の荷重図に CASE-2 のページがありません"),
])
def test_a_runner_that_does_not_draw_the_figures_is_an_error(fake_jrsnap_runner: Path,
                                                             monkeypatch: pytest.MonkeyPatch, mode, message):
    monkeypatch.setenv("FAKE_JRSNAP_FIGURES", mode)
    with pytest.raises(RunnerError, match=f"線路方向.ndu のデータ確認図と荷重図を JRSNAP で描けません: .*{message}"):
        draw_figures("線路方向.ndu", SMALL, fake_jrsnap_runner, SMALL_CASES)


def test_a_combination_the_ndu_does_not_have_is_an_error(fake_jrsnap_runner: Path):
    with pytest.raises(RunnerError, match="データ確認図と荷重図を JRSNAP で描けません: COMBINATION_NOT_FOUND"):
        draw_figures("線路方向.ndu", SMALL, fake_jrsnap_runner, ((1, 1), (2, 2)))


def test_figures_that_do_not_finish_are_an_error(fake_jrsnap_runner: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_JRSNAP_FIGURES", "slow")
    with pytest.raises(RunnerError, match="データ確認図と荷重図を JRSNAP で描けません: 0.5 秒で終わりませんでした"):
        draw_figures("線路方向.ndu", SMALL, fake_jrsnap_runner, SMALL_CASES, timeout=0.5)


# --- SOIL-JR's calculation of the ground of a pile foundation (decision 85, ADR-0013) -----------------------------------

def soil_input(liquefied: bool = False) -> bytes:
    """What the stand-in reads of an .sdt: the pile's columns, the basic condition and the liquefaction flag."""
    return ("\r\n".join(["Ver.5.2.3.T08", "●基本条件●", "t", " 1 ", "d", " 1 ", "1,1", " 8 ", "", "●杭条件●",
                         "1,3,3,3,3,3,3,3,3,1,1,0,0,1,0,0", "19,0,1,2.8,-1,22.4,1,-1,-1,-1,-1,0.785398,0.049087,24.5",
                         "", "●液状化の低減係数", " 1 " if liquefied else " 0 ", "1,1", ""]) + "\r\n").encode("cp932")


def test_the_stand_in_calculates_the_given_sdt(fake_jrsnap_runner: Path):
    document = soil_input()
    found = calculate_ground("杭基礎.sdt", document, fake_jrsnap_runner, liquefaction=False)
    digest = hashlib.sha256(document).hexdigest()
    assert sorted(found.files) == ["sdc", "sdr"] and found.files["sdc"].decode("cp932").split("\r\n")[4] == f"FAKE SDC {digest}"
    assert f"FAKE SOIL-JR REPORT {digest[:16]}" in texts(found.report)[0]
    assert found.pages == {SOIL_REPORT: found.report}
    assert found.engine_version == "fake-1" and found.summary["input"] == {"name": "杭基礎.sdt", "sha256": digest}
    assert found.messages == ({"level": "warning", "code": "SOIL_WARNING", "text": "FAKE SOIL WARNING"},)


def test_the_files_for_the_liquefaction_are_asked_for_and_returned_with_the_input_that_considers_it(
        fake_jrsnap_runner: Path):
    found = calculate_ground("杭基礎.sdt", soil_input(True), fake_jrsnap_runner, liquefaction=True)
    assert sorted(found.files) == ["liquefiedsdc", "liquefiedsdr", "sdc", "sdr"]
    assert found.summary["liquefaction"] is True
    with pytest.raises(RunnerError, match="一覧と一致しません|渡した .sdt と違います|成果物が"):
        calculate_ground("杭基礎.sdt", soil_input(True), fake_jrsnap_runner, liquefaction=False)
    with pytest.raises(RunnerError, match="一覧と一致しません|渡した .sdt と違います|成果物が"):
        calculate_ground("杭基礎.sdt", soil_input(False), fake_jrsnap_runner, liquefaction=True)


@pytest.mark.parametrize("mode,message", [
    ("fail", "UNKNOWN_DIALOG: SOIL_JR showed"), ("input", "SDT_REJECTED: SOIL-JR rejected the .sdt"),
    ("exit", "JSON ではありません"), ("text", "JSON ではありません"), ("protocol", "やり取りの版が違います"),
    ("summary", "summary・messages がありません"), ("kind", "SOIL-JR の連携ファイルと帳票ではありません"),
    ("missing", "出力先のファイルが成果物の一覧と一致しません"), ("extra", "出力先のファイルが成果物の一覧と一致しません"),
    ("sha", "が runner の応答の SHA256・バイト数と一致しません"), ("name", "渡した .sdt と違います"),
    ("digest", "渡した .sdt と違います"), ("liquefaction", "渡した .sdt と違います"), ("pdf", "杭基礎.pdf にページがありません"),
    ("broken", "杭基礎.pdf を読めません"),
])
def test_a_runner_that_does_not_calculate_the_sdt_is_an_error(fake_jrsnap_runner: Path, monkeypatch: pytest.MonkeyPatch,
                                                               mode, message):
    monkeypatch.setenv("FAKE_JRSNAP_SOIL", mode)
    with pytest.raises(RunnerError, match=f"杭基礎.sdt を SOIL-JR で計算できません: .*{message}"):
        calculate_ground("杭基礎.sdt", soil_input(), fake_jrsnap_runner, liquefaction=False)


def test_a_calculation_that_does_not_finish_is_an_error(fake_jrsnap_runner: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_JRSNAP_SOIL", "slow")
    with pytest.raises(RunnerError, match="杭基礎.sdt を SOIL-JR で計算できません: 1 秒で終わりませんでした"):
        calculate_ground("杭基礎.sdt", soil_input(), fake_jrsnap_runner, liquefaction=False, timeout=1)


def test_the_stand_in_refuses_arguments_it_was_not_given_as_the_runner_takes_them(fake_jrsnap_runner: Path, tmp_path: Path):
    import subprocess
    source = tmp_path / "杭基礎.sdt"
    source.write_bytes(soil_input())
    done = subprocess.run([str(fake_jrsnap_runner), "soil", "--input", str(source), "--output-dir", str(tmp_path / "o"),
                           "--timeout-seconds", "60"], capture_output=True, check=False)
    assert done.returncode == 1 and "INVALID_ARGUMENT" in done.stdout.decode("utf-8")
    (tmp_path / "full").mkdir()
    (tmp_path / "full" / "x").write_bytes(b"")
    done = subprocess.run([str(fake_jrsnap_runner), "soil", "--input", str(source), "--output-dir", str(tmp_path / "full"),
                           "--timeout-seconds", "600"], capture_output=True, check=False)
    assert done.returncode == 1 and "OUTPUT_NOT_EMPTY" in done.stdout.decode("utf-8")
