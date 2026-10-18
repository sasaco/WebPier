"""The Aggre-SE runner of the 0711 / 0721 耐震性能照査 (decision 56, ADR-0009).

The runner is found from STRUCTURAL_MCP_AGGRESE_RUNNER (environment, then .env; the name structural-mcp uses) and
called as ``run`` with the project XML where it is staged and the DB1 of each Case mapped as the XML names them. Its
envelope, its two files and the Cases it aggregated are checked as the Aggre-SE runner's README states; the report is
returned as it is. Every case uses the stand-in of tests/fixtures/aggrese/fake_runner.py (tests/conftest.py); the real
runner is accepted by scripts/accept_aggrese_report.py.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf
import pytest

from webpier.pipeline import aggrese
from webpier.pipeline.aggrese import RUNNER_KEY, check_seismic, runner_path, snap_map
from webpier.pipeline.fempython import RunnerError
from webpier.reporting.stages.seismic_check import SEISMIC_CHECK

FOLDER = "線路方向_JRSNAP"
NAMES = ("線路方向(Case1_ρm10_αf1_正向).DB1", "線路方向(Case2_ρm10_αf1_正向).DB1")


def project(directory: Path, names=NAMES) -> Path:
    """A project XML as Aggre-SE writes it (Shift-JIS, declared utf-16) naming *names* in the JRSNAP folder, and the
    folder with a DB1 for each; the array ends with nil items as Aggre-SE's does."""
    (directory / FOLDER).mkdir(parents=True)
    for name in names:
        (directory / FOLDER / name).write_bytes(f"FAKE DB1 {name}".encode("utf-8"))
    items = "".join(f"\r\n      <string>{FOLDER}/{name}</string>" for name in names)
    text = ('<?xml version="1.0" encoding="utf-16"?>\r\n<Datas xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"\r\n  <SNAP>\r\n    <SnapDBPath>{items}\r\n      <string xsi:nil=\"true\" />\r\n    </SnapDBPath>"
            "\r\n  </SNAP>\r\n</Datas>")
    path = directory / "線路方向.xml"
    path.write_bytes(text.encode("cp932"))
    return path


def texts(pdf: bytes) -> list[str]:
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        return [page.get_text().strip() for page in document]


def test_the_environment_comes_before_the_env_file(tmp_path: Path):
    runner, other = tmp_path / "runner.exe", tmp_path / "other.exe"
    runner.write_bytes(b""), other.write_bytes(b"")
    env = tmp_path / ".env"
    env.write_text(f"{RUNNER_KEY}='{other}'\nSTRUCTURAL_MCP_FEMPYTHON_RUNNER=x\n", encoding="utf-8")
    assert runner_path({RUNNER_KEY: str(runner)}, env) == runner
    assert runner_path({RUNNER_KEY: ""}, env) == other
    assert runner_path({}, env) == other


@pytest.mark.parametrize("setting,message", [(None, "Aggre-SE の runner が設定されていません"), ("", "設定されていません"),
                                             ("runner.exe", "絶対パス"), ("missing", "ありません")])
def test_a_runner_that_is_not_set_up_is_an_error(tmp_path: Path, setting, message):
    env = tmp_path / ".env"
    if setting is not None:
        value = str(tmp_path / "missing.exe") if setting == "missing" else setting
        env.write_text(f"{RUNNER_KEY}={value}\n", encoding="utf-8")
    with pytest.raises(RunnerError, match=message):
        runner_path({}, env)


def test_the_process_environment_is_used_by_default(monkeypatch: pytest.MonkeyPatch, fake_aggrese_runner: Path):
    monkeypatch.setenv(RUNNER_KEY, str(fake_aggrese_runner))
    assert runner_path() == fake_aggrese_runner


def test_the_snap_map_is_each_db1_the_xml_names_from_its_folder(tmp_path: Path):
    path = project(tmp_path)
    assert snap_map(path) == {str(index): str((tmp_path / FOLDER / name).resolve())
                              for index, name in enumerate(NAMES)}


@pytest.mark.parametrize("content,message", [
    (b'<?xml version="1.0" encoding="utf-16"?>\r\n<Datas><SNAP><SnapDBPath /></SNAP></Datas>', "SnapDBPath"),
    (b'<?xml version="1.0" encoding="utf-16"?>\r\n<Datas />', "SnapDBPath"),
    (b"<Datas>", "プロジェクトを読めません"), (b"\x82", "プロジェクトを読めません"),
])
def test_a_project_without_databases_is_an_error(tmp_path: Path, fake_aggrese_runner: Path, content, message):
    path = tmp_path / "線路方向.xml"
    path.write_bytes(content)
    with pytest.raises(RunnerError, match=f"線路方向.xml で耐震性能照査ができません: .*{message}"):
        check_seismic(path, fake_aggrese_runner)


def test_the_stand_in_checks_each_case_the_project_names(tmp_path: Path, fake_aggrese_runner: Path):
    path = project(tmp_path)
    checked = check_seismic(path, fake_aggrese_runner)
    assert checked.engine_version == "fake-1"
    assert [(case["caseNumber"], case["name"], case["aggregated"]) for case in checked.cases] == [
        (1, "線路方向(Case1_ρm10_αf1_正向)", True), (2, "線路方向(Case2_ρm10_αf1_正向)", True)]
    pages = texts(checked.pdf)
    assert pages == [*(f"FAKE AGGRESE Case{number} "
                       f"{hashlib.sha256((tmp_path / FOLDER / name).read_bytes()).hexdigest()[:16]}"
                       for number, name in enumerate(NAMES, 1)),
                     f"FAKE AGGRESE SUMMARY {hashlib.sha256(path.read_bytes()).hexdigest()[:16]}"]
    assert checked.pages == {SEISMIC_CHECK: checked.pdf}
    assert sorted(path.name for path in (tmp_path / FOLDER).iterdir()) == sorted(NAMES)


@pytest.mark.parametrize("mode,message", [
    ("fail", "CALCULATION_FAILED: 集計できませんでした。"),
    ("exit", "JSON ではありません"), ("text", "JSON ではありません"), ("list", "オブジェクトではありません"),
    ("protocol", "やり取りの版が違います"), ("engine", "やり取りの版が違います"), ("version", "engineVersion"),
    ("artifacts", "成果物が結果と計算書の2つではありません"),
    ("missing", "成果物 report.pdf がありません"), ("extra", "出力先のファイルが成果物の一覧と一致しません"),
    ("sha", r"report\.pdf が runner の応答の SHA256・バイト数と一致しません"),
    ("cases", r"解析ケース（summary\.cases）がありません"), ("unaggregated", "全 2 ケースが集計されていません"),
    ("broken", "計算書の PDF を読めません"), ("empty", "計算書の PDF にページがありません"),
])
def test_a_runner_that_does_not_check_is_an_error(tmp_path: Path, fake_aggrese_runner: Path,
                                                  monkeypatch: pytest.MonkeyPatch, mode, message):
    path = project(tmp_path)
    monkeypatch.setenv("FAKE_AGGRESE", mode)
    with pytest.raises(RunnerError, match=f"線路方向.xml で耐震性能照査ができません: .*{message}"):
        check_seismic(path, fake_aggrese_runner)


def test_a_missing_database_is_the_runners_error(tmp_path: Path, fake_aggrese_runner: Path):
    path = project(tmp_path)
    (tmp_path / FOLDER / NAMES[1]).unlink()
    with pytest.raises(RunnerError, match="SNAP_DB_NOT_FOUND"):
        check_seismic(path, fake_aggrese_runner)


def test_a_runner_that_cannot_start_is_an_error(tmp_path: Path):
    path = project(tmp_path)
    runner = tmp_path / "runner.exe"
    runner.write_bytes(b"not a program")
    with pytest.raises(RunnerError, match="runner を起動できません"):
        check_seismic(path, runner)


def test_a_runner_that_does_not_finish_is_an_error(tmp_path: Path, fake_aggrese_runner: Path,
                                                   monkeypatch: pytest.MonkeyPatch):
    path = project(tmp_path)
    monkeypatch.setattr(aggrese.subprocess, "run", _timeout)
    with pytest.raises(RunnerError, match="秒で終わりませんでした"):
        check_seismic(path, fake_aggrese_runner, timeout=1)


def _timeout(*args, **kwargs):
    raise aggrese.subprocess.TimeoutExpired(args[0], kwargs.get("timeout", 1))
