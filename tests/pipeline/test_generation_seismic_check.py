"""A stage with a 耐震性能照査 (decisions 56〜58, ADR-0009): after JRSNAP's analysis, Aggre-SE checks with the staged
project and the staged folder beside it; its report is the stage's report byte for byte, its pickup and summary
workbook are published under post/ as they are with a sidecar each, the result JSON records the check without a
judgement, the project's sidecar names the report, and a missing, failing or meddling runner publishes nothing.

The analysis and the check are the stand-ins' (tests/fixtures/jrsnap/fake_runner.py, tests/fixtures/aggrese/
fake_runner.py)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf
import pytest

from pipeline_support import Recorder, copy_input, tree
from webpier.core.integrity import content_sha256
from webpier.export.aggrese import databases
from webpier.pipeline import aggrese, generate, jrsnap
from webpier.pipeline.generate import GenerationError, GenerationOptions, planned
from webpier.pipeline.stages import (NONLINEAR_ANALYSIS, Export, NonlinearAnalysis, Project, Registry, SeismicCheck,
                                     StageSpec)
from webpier.reporting.stages.seismic_check import render_seismic_check

NDU = b"Virsion=5.2.3.S.4\r\n"
FOLDER = "model_JRSNAP"
CASE = "model(Case1_ρm10_αf1_正向)"
PIK, XLSX = "model_Aggre-SE.pik", "model_Aggre-SE.xlsx"


def project(folder: str, names) -> bytes:
    """A project naming the DB1 of Case 1 as Aggre-SE writes it: Shift-JIS, declared utf-16."""
    items = "".join(f"<string>{path}</string>" for path in databases(folder, names, 1))
    return (f'<?xml version="1.0" encoding="utf-16"?>\r\n<Datas><SNAP><SnapDBPath>{items}</SnapDBPath></SNAP>'
            "</Datas>").encode("cp932")


def registry(recorder: Recorder) -> Registry:
    return Registry((
        StageSpec("A", "A_基礎", (), recorder.calculate("A"), recorder.render("A")),
        StageSpec("C", "C_地震", ("A",), recorder.calculate("C"), recorder.render("C"),
                  (Export("jrsnap", "model.ndu", recorder.export("C", NDU)),)),
        StageSpec("E", "E_解析", ("C",), render=lambda results, pier, path, pages: render_seismic_check(path, pages),
                  opt_in=NONLINEAR_ANALYSIS,
                  nonlinear_analysis=NonlinearAnalysis(
                      "C", "jrsnap", "jrsnap", FOLDER,
                      Project("aggrese", "model.xml", lambda results, pier: project, {"target": "Aggre-SE"})),
                  seismic_check=SeismicCheck((("pik", PIK), ("xlsx", XLSX)))),
    ))


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    monkeypatch.setattr(jrsnap, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(aggrese, "ENV_FILE", tmp_path / ".env")
    recorder = Recorder()
    options = GenerationOptions(copy_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post",
                                nonlinear_analysis=True)
    return options, recorder, registry(recorder)


def checking(monkeypatch: pytest.MonkeyPatch) -> list[aggrese.SeismicCheckPages]:
    """Each check the generation has the runner make, as the runner module returned it."""
    made, original = [], aggrese.check_seismic

    def check(project, runner, **kwargs):
        made.append(original(project, runner, **kwargs))
        return made[-1]
    monkeypatch.setattr(aggrese, "check_seismic", check)
    return made


def test_the_report_is_aggre_ses_report_as_it_is(env, monkeypatch: pytest.MonkeyPatch):
    options, recorder, stages = env
    made = checking(monkeypatch)
    generation = generate.generate(options, registry=stages)
    assert generation.stages == ("A", "C", "E")
    output, post = tree(Path(options.output_dir)), tree(Path(options.post_dir))
    assert output["E_解析.pdf"] == made[0].pdf
    with pymupdf.open(stream=output["E_解析.pdf"], filetype="pdf") as document:
        pages = [page.get_text().strip() for page in document]
    assert pages == [f"FAKE AGGRESE Case1 {hashlib.sha256(post[f'{FOLDER}/{CASE}.DB1']).hexdigest()[:16]}",
                     f"FAKE AGGRESE SUMMARY {hashlib.sha256(post['model.xml']).hexdigest()[:16]}"]
    assert recorder.actions("render") == ["A", "C"] and recorder.actions("calculate") == ["A", "C"]
    assert [artifact.role for artifact in generation.artifacts if artifact.role.startswith("E")] == [
        "E.pdf", "E.json", "E.jrsnap", "E.aggrese", "E.pik", "E.xlsx", "E.jrsnap.provenance",
        "E.aggrese.provenance", "E.pik.provenance", "E.xlsx.provenance"]
    assert post[PIK] == made[0].files["pik"] == (
        f"Batch ver1.0.0\r\nFAKE PIK {hashlib.sha256(post['model.xml']).hexdigest()[:16]}\r\n".encode("cp932"))
    assert post[XLSX] == made[0].files["xlsx"]
    assert planned(options, registry=stages) == generation.artifacts


def test_the_result_records_the_check_and_its_files_without_a_judgement(env):
    options, _, stages = env
    generate.generate(options, registry=stages)
    post = tree(Path(options.post_dir))
    document = json.loads((Path(options.output_dir) / "E_解析.json").read_text(encoding="utf-8"))
    assert (document["stage"], document["result"]) == ("E", None)
    assert document["seismic_check"] == {
        "engine": "aggrese", "engine_version": "fake-1", "engineering_status": "not_evaluated",
        "cases": [{"caseNumber": 1, "name": CASE, "aggregated": True}],
        "project": {"file": "model.xml", "sha256": hashlib.sha256(post["model.xml"]).hexdigest()},
        "jrsnap": {"file": FOLDER, "sha256": content_sha256(Path(options.post_dir) / FOLDER)},
        "files": {"pik": {"file": PIK, "sha256": hashlib.sha256(post[PIK]).hexdigest()},
                  "xlsx": {"file": XLSX, "sha256": hashlib.sha256(post[XLSX]).hexdigest()}}}
    pik = json.loads((Path(options.post_dir) / f"{PIK}.provenance.json").read_text(encoding="utf-8"))
    assert (pik["stage"], pik["export"], pik["file"], pik["sha256"]) == (
        "E", "pik", PIK, hashlib.sha256(post[PIK]).hexdigest())
    assert pik["seismic_check"] == {
        "report": "E.pdf", "engine": "aggrese", "engine_version": "fake-1", "engineering_status": "not_evaluated",
        "project": {"file": "model.xml", "sha256": hashlib.sha256(post["model.xml"]).hexdigest()},
        "jrsnap": {"file": FOLDER, "sha256": content_sha256(Path(options.post_dir) / FOLDER)},
        "pickups": {"1": "L1地震動", "2": "復旧性L2地震動", "3": "安全性L2地震動"}}
    xlsx = json.loads((Path(options.post_dir) / f"{XLSX}.provenance.json").read_text(encoding="utf-8"))
    assert (xlsx["stage"], xlsx["export"], xlsx["file"], xlsx["sha256"]) == (
        "E", "xlsx", XLSX, hashlib.sha256(post[XLSX]).hexdigest())
    assert xlsx["seismic_check"] == {key: value for key, value in pik["seismic_check"].items() if key != "pickups"}
    sidecar = json.loads((Path(options.post_dir) / "model.xml.provenance.json").read_text(encoding="utf-8"))
    assert sidecar["seismic_check"] == {"report": "E.pdf", "engine": "aggrese", "engine_version": "fake-1"}
    folder = json.loads((Path(options.post_dir) / f"{FOLDER}.provenance.json").read_text(encoding="utf-8"))
    assert "seismic_check" not in folder


def test_a_generation_without_the_check_needs_no_runner(env, monkeypatch: pytest.MonkeyPatch):
    options, _, stages = env
    monkeypatch.setenv(aggrese.RUNNER_KEY, "")
    generate.generate(GenerationOptions(options.input_path, options.output_dir, options.post_dir), registry=stages)
    assert sorted(tree(Path(options.output_dir))) == ["A_基礎.json", "A_基礎.pdf", "C_地震.json", "C_地震.pdf"]


def test_without_a_runner_nothing_is_read_or_published(env, monkeypatch: pytest.MonkeyPatch):
    options, _, stages = env
    monkeypatch.setenv(aggrese.RUNNER_KEY, "")
    read = []
    monkeypatch.setattr(generate, "parse_input", lambda data: read.append(data))
    with pytest.raises(GenerationError, match="Aggre-SE の runner が設定されていません"):
        generate.generate(options, registry=stages)
    assert read == [] and not Path(options.post_dir).exists() and not Path(options.output_dir).exists()


@pytest.mark.parametrize("mode,message", [
    ("fail", "model.xml で耐震性能照査ができません: CALCULATION_FAILED"),
    ("unaggregated", "model.xml で耐震性能照査ができません: 全 1 ケースが集計されていません"),
    ("noxlsx", "model.xml で耐震性能照査ができません: runner の成果物が結果・計算書・ピックアップ・総括表の4つではありません"),
    ("write", f"Aggre-SE の runner が model.xml か {FOLDER} を変更しました"),
])
def test_a_failing_check_stops_before_any_report_and_publishes_nothing(env, monkeypatch: pytest.MonkeyPatch, mode,
                                                                      message):
    options, recorder, stages = env
    monkeypatch.setenv("FAKE_AGGRESE", mode)
    with pytest.raises(GenerationError, match=message):
        generate.generate(options, registry=stages)
    assert recorder.actions("render") == []
    assert not Path(options.post_dir).exists() and not Path(options.output_dir).exists()


def test_a_failing_check_keeps_the_previous_generation(env, monkeypatch: pytest.MonkeyPatch):
    options, _, stages = env
    generate.generate(options, registry=stages)
    before = (tree(Path(options.output_dir)), tree(Path(options.post_dir)))
    monkeypatch.setenv("FAKE_AGGRESE", "fail")
    with pytest.raises(GenerationError, match="耐震性能照査ができません"):
        generate.generate(GenerationOptions(**{**options.__dict__, "overwrite": True}), registry=stages)
    assert (tree(Path(options.output_dir)), tree(Path(options.post_dir))) == before
