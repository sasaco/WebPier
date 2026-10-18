"""The FEMPython runner that draws the 0610 / 0620 load diagrams (decision 44, ADR-0005).

The runner is found from STRUCTURAL_MCP_FEMPYTHON_RUNNER (environment, then .env) and called with the FrameWeb
file; its envelope and report.pdf are checked as the Headless protocol states. Every case uses the stand-in of
tests/fixtures/fempython/fake_runner.py (tests/conftest.py) except the last, which calls the runner the user set
up and is skipped without one.
"""

from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from webpier.core.integrity import load_json
from webpier.inputs import parse_input
from webpier.pipeline import fempython
from webpier.pipeline.fempython import RUNNER_KEY, RunnerError, draw_load_diagram, read_env, runner_path
from webpier.pipeline.generate import export_bytes

CURRENT = Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json"


def frameweb(directory: Path, cases: int = 3) -> Path:
    path = directory / "線路方向.json"
    path.write_text(json.dumps({"dimension": 2, "load": {str(n): {} for n in range(1, cases + 1)}}),
                    encoding="utf-8")
    return path


def test_env_file_lines(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("\ufeff# runners\n\nA='C:\\a b\\x.exe'\nB = \"q\"\nC=plain value\nD=\n", encoding="utf-8")
    assert read_env(env) == {"A": "C:\\a b\\x.exe", "B": "q", "C": "plain value", "D": ""}


@pytest.mark.parametrize("text,message", [("no separator", "1 行目"), ("1A=x", "1 行目"), ("A=1\nA=2", "A が重複")])
def test_env_file_errors(tmp_path: Path, text: str, message: str):
    env = tmp_path / ".env"
    env.write_text(text, encoding="utf-8")
    with pytest.raises(RunnerError, match=message):
        read_env(env)


def test_the_environment_comes_before_the_env_file(tmp_path: Path):
    runner, other = tmp_path / "runner.exe", tmp_path / "other.exe"
    runner.write_bytes(b""), other.write_bytes(b"")
    env = tmp_path / ".env"
    env.write_text(f"{RUNNER_KEY}='{other}'\nOTHER=1\n", encoding="utf-8")
    assert runner_path({RUNNER_KEY: str(runner)}, env) == runner
    assert runner_path({RUNNER_KEY: ""}, env) == other
    assert runner_path({}, env) == other


@pytest.mark.parametrize("setting,message", [(None, "設定されていません"), ("", "設定されていません"),
                                             ("runner.exe", "絶対パス"), ("missing", "ありません")])
def test_a_runner_that_is_not_set_up_is_an_error(tmp_path: Path, setting, message):
    env = tmp_path / ".env"
    if setting is not None:
        value = str(tmp_path / "missing.exe") if setting == "missing" else setting
        env.write_text(f"{RUNNER_KEY}={value}\n", encoding="utf-8")
    with pytest.raises(RunnerError, match=message):
        runner_path({}, env)


def test_the_stand_in_draws_two_cases_a_page(tmp_path: Path, fake_fempython_runner: Path):
    drawn = draw_load_diagram(frameweb(tmp_path, 5), fake_fempython_runner)
    pages = PdfReader(BytesIO(drawn.pdf)).pages
    assert drawn.engine_version == "fake-1"
    assert [page.extract_text().strip().partition(" CASES ")[2] for page in pages] == ["1 2", "3 4", "5"]


@pytest.mark.parametrize("mode,message", [
    ("fail", "LOAD_DIAGRAM_REQUIRES_2D: 2D only"), ("exit", "JSON ではありません"), ("text", "JSON ではありません"),
    ("list", "オブジェクトではありません"), ("protocol", "やり取りの版が違います"), ("version", "engineVersion"),
    ("artifacts", "PDF 1つではありません"), ("missing", "report.pdf がありません"), ("sha", "SHA256・バイト数"),
    ("badpdf", "PDF を読めません"), ("empty", "ページがありません"),
])
def test_a_runner_that_does_not_draw_the_load_diagram_is_an_error(tmp_path: Path, fake_fempython_runner: Path,
                                                                  monkeypatch: pytest.MonkeyPatch, mode, message):
    monkeypatch.setenv("FAKE_FEMPYTHON", mode)
    with pytest.raises(RunnerError, match=f"線路方向.json の荷重図を FEMPython で描けません: .*{message}"):
        draw_load_diagram(frameweb(tmp_path), fake_fempython_runner)


def test_an_exit_code_without_errors_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runner = tmp_path / "runner.cmd"
    runner.write_text('@echo {"protocolVersion": 1, "engine": "fempython", "ok": true}\r\n@exit /b 4\r\n',
                      encoding="ascii")
    with pytest.raises(RunnerError, match="終了コード 4"):
        draw_load_diagram(frameweb(tmp_path), runner)


def test_a_runner_that_cannot_start_or_does_not_finish_is_an_error(tmp_path: Path, fake_fempython_runner: Path):
    with pytest.raises(RunnerError, match="起動できません"):
        draw_load_diagram(frameweb(tmp_path), tmp_path / "missing.exe")
    with pytest.raises(RunnerError, match="秒で終わりませんでした"):
        draw_load_diagram(frameweb(tmp_path), fake_fempython_runner, timeout=0.001)


def test_the_arguments_are_those_of_the_decision():
    # Decision 44: the load diagram alone (no calculation), A4 portrait, no axis page, two cases a page.
    assert fempython.ARGUMENTS == ("--generate-pik", "false", "--pdf-sections", "load_diagram", "--pdf-paper", "A4",
                                   "--pdf-orientation", "vertical", "--load-diagram-layout", "split_horizontal",
                                   "--load-diagram-axis", "false")


def expected_analysis(name: str, document: bytes) -> dict[str, bytes]:
    """What the stand-in returns for a frame analysis (its docstring), written out without the implementation."""
    digest = hashlib.sha256(document).hexdigest()
    return {kind: f"FAKE {word} {name} {digest}\n".encode("utf-8")
            for kind, word in (("pik", "PIK"), ("displacement", "DISPLACEMENT"), ("reaction", "REACTION"))}


def test_the_stand_in_analyzes_the_given_bytes(fake_fempython_runner: Path):
    document = b'{"dimension": 2, "load": {"1": {}}}\n'
    analysed = fempython.analyze_frame("線路方向.json", document, fake_fempython_runner)
    assert analysed.engine_version == "fake-1"
    assert dict(analysed.files) == expected_analysis("線路方向.json", document)  # result.json is not kept


@pytest.mark.parametrize("mode,message", [
    ("fail", "EMPTY_PIK: PIK output contains no data rows"), ("exit", "JSON ではありません"),
    ("text", "JSON ではありません"), ("list", "オブジェクトではありません"), ("protocol", "やり取りの版が違います"),
    ("version", "engineVersion"), ("artifacts", "解析結果・PIK・変位量と反力の CSV の4つではありません"),
    ("missing", "pickup-reaction.csv がありません"), ("sha", "pickup-reaction.csv が runner の応答の SHA256・バイト数"),
])
def test_a_runner_that_does_not_analyze_the_frame_is_an_error(fake_fempython_runner: Path,
                                                               monkeypatch: pytest.MonkeyPatch, mode, message):
    monkeypatch.setenv("FAKE_FEMPYTHON", mode)
    with pytest.raises(RunnerError, match=f"線路方向.json を FEMPython で骨組解析できません: .*{message}"):
        fempython.analyze_frame("線路方向.json", b"{}", fake_fempython_runner)


def test_an_analysis_mode_of_the_stand_in_leaves_the_load_diagram_alone(tmp_path: Path, fake_fempython_runner: Path,
                                                                        monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAKE_FEMPYTHON", "analysis-fail")
    assert draw_load_diagram(frameweb(tmp_path), fake_fempython_runner).engine_version == "fake-1"
    with pytest.raises(RunnerError, match="EMPTY_PIK"):
        fempython.analyze_frame("線路方向.json", b"{}", fake_fempython_runner)


def test_an_analysis_that_cannot_start_or_does_not_finish_is_an_error(tmp_path: Path, fake_fempython_runner: Path):
    with pytest.raises(RunnerError, match="線路方向.json を FEMPython で骨組解析できません: runner を起動できません"):
        fempython.analyze_frame("線路方向.json", b"{}", tmp_path / "missing.exe")
    with pytest.raises(RunnerError, match="秒で終わりませんでした"):
        fempython.analyze_frame("線路方向.json", b"{}", fake_fempython_runner, timeout=0.001)


def test_the_analysis_arguments_are_those_of_the_decision():
    # Decision 46: no PDF, the PIK and both node pickup CSVs.
    assert fempython.ANALYSIS_ARGUMENTS == ("--generate-pdf", "false", "--generate-pik", "true",
                                            "--generate-pickup-displacement-csv", "true",
                                            "--generate-pickup-reaction-csv", "true")


@pytest.mark.parametrize("stage", ["0610", "0620"])
def test_the_real_runner_draws_the_generated_file(tmp_path: Path, real_fempython_runner: Path, stage: str):
    """Only that it runs and returns pages: the drawing is FEMPython's (decision 44)."""
    document = tmp_path / f"{stage}.json"
    document.write_bytes(export_bytes(parse_input(load_json(CURRENT.read_bytes())), stage, "frameweb"))
    drawn = draw_load_diagram(document, real_fempython_runner)
    assert len(PdfReader(BytesIO(drawn.pdf)).pages) >= 1
    assert drawn.engine_version


@pytest.mark.parametrize("stage", ["0610", "0620"])
def test_the_real_runner_analyzes_the_generated_file(real_fempython_runner: Path, stage: str):
    """Only that it runs and returns the three files: their content is FEMPython's (decision 46)."""
    document = export_bytes(parse_input(load_json(CURRENT.read_bytes())), stage, "frameweb")
    analysed = fempython.analyze_frame(f"{stage}.json", document, real_fempython_runner)
    assert sorted(analysed.files) == ["displacement", "pik", "reaction"]
    assert all(analysed.files.values())
    assert analysed.engine_version
