"""The headless runner for a pile foundation (decision 85, ADR-0013): the stages and runners come from the input's 基礎形式, so
0500 of piles needs the JRSNAP runner (SOIL-JR) and a missing one is RUNNER_UNAVAILABLE before anything is calculated."""

import json
from pathlib import Path

import pytest

from webpier.core.integrity import sha256
from webpier.pipeline import generate, headless, jrsnap

FIXTURE = Path(__file__).parents[1] / "fixtures" / "inputs" / "pile.json"


def call(capsys, *arguments):
    code = headless.main([str(argument) for argument in arguments])
    return code, json.loads(capsys.readouterr().out)


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "0" * 64})


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "pre" / "input.json"
    path.parent.mkdir()
    path.write_bytes(FIXTURE.read_bytes())
    return path


def test_run_makes_the_stages_of_the_pile_foundation(tmp_path, capsys, source):
    code, envelope = call(capsys, "run", "--input", source, "--output-dir", tmp_path / "out")
    assert code == 0 and envelope["errors"] == []
    summary = envelope["summary"]
    assert summary["outputs"] == ["detailing", "ground_model", "reactions"]
    assert [(stage["id"], stage["stem"]) for stage in summary["stages"]] == [
        ("0400", "0400_照査の前提"), ("0500", "0500_杭基礎"), ("0600", "0600_上部工反力")]
    assert next(stage for stage in summary["stages"] if stage["id"] == "0500")["engineeringStatus"] == "not_evaluated"
    assert summary["runners"] == [{"engine": "jrsnap", "environmentVariable": "STRUCTURAL_MCP_JRSNAP_RUNNER",
                                   "engineVersions": ["fake-1"]}]
    by_kind = {item["kind"]: item for item in envelope["artifacts"]}
    assert {"0500-pdf", "0500-json", "0500-sdt", "0500-sdr", "0500-sdc", "0500-sdt-provenance"} <= set(by_kind)
    assert by_kind["0500-pdf"]["relativePath"] == "output/0500_杭基礎.pdf"
    assert by_kind["0500-sdt"]["relativePath"] == "post/杭基礎.sdt"
    sdt = (tmp_path / "out" / "post" / "杭基礎.sdt").read_bytes()
    assert (by_kind["0500-sdt"]["bytes"], by_kind["0500-sdt"]["sha256"]) == (len(sdt), sha256(sdt))
    assert summary["input"]["sha256"] == sha256(source.read_bytes())


def test_validate_names_the_runner_of_the_ground_stage_without_calling_it(tmp_path, capsys, source, monkeypatch):
    monkeypatch.delenv(jrsnap.RUNNER_KEY)
    monkeypatch.setattr(jrsnap, "ENV_FILE", tmp_path / "no.env")
    code, envelope = call(capsys, "validate", "--input", source)
    assert code == 0
    assert envelope["summary"]["outputs"] == ["detailing", "ground_model", "reactions"]
    assert envelope["summary"]["stages"] == ["0400", "0500", "0600"]
    assert envelope["summary"]["requiredRunners"] == [
        {"engine": "jrsnap", "environmentVariable": "STRUCTURAL_MCP_JRSNAP_RUNNER", "available": False}]


def test_a_missing_runner_is_reported_before_anything_is_calculated(tmp_path, capsys, source, monkeypatch):
    monkeypatch.delenv(jrsnap.RUNNER_KEY)
    code, envelope = call(capsys, "run", "--input", source, "--output-dir", tmp_path / "out")
    assert code == 2 and not (tmp_path / "out").exists()
    (error,) = envelope["errors"]
    assert (error["category"], error["code"]) == ("engine_unavailable", "RUNNER_UNAVAILABLE")
    assert "jrsnap（STRUCTURAL_MCP_JRSNAP_RUNNER）" in error["message"]


def test_a_pile_input_for_an_item_it_cannot_make_is_an_input_error_at_the_item(tmp_path, capsys):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["outputs"]["longitudinal_seismic"] = True
    data["outputs"]["longitudinal_nonlinear_analysis"] = True  # 0711 is not made for piles yet
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    code, envelope = call(capsys, "validate", "--input", path)
    assert code == 2
    (error,) = envelope["errors"]
    assert (error["code"], error["path"]) == ("INPUT_ERROR", "outputs.longitudinal_nonlinear_analysis")
    assert "場所打ち杭は未対応です" in error["message"]
