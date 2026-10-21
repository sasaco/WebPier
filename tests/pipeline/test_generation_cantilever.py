"""The generation mechanics of decision 59: a stage finishes its result with the files of the seismic checks of its
dependencies (``seismic_file``), a dependent stage finishes with that finished result alone, and a section check
without a frame analysis has Capacita calculate the stage's WDJ as given (``run-rc`` without ``--pickup``): the WDJ
WebPier wrote is published with a sidecar that names no PIK, the result JSON records the check without a PIK, and a
failing completion or runner publishes nothing.

The analyses and checks are the stand-ins' (tests/fixtures/jrsnap, aggrese, capacita)."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import pymupdf
import pytest

from pipeline_support import SEISMIC, Recorder, copy_input, tree
from webpier.calc.cantilever import ResponseError
from webpier.core.integrity import load_json
from webpier.export.aggrese import databases
from webpier.pipeline import aggrese, capacita, generate, jrsnap
from webpier.pipeline.generate import GenerationError, GenerationOptions, planned
from webpier.pipeline.stages import (Export, NonlinearAnalysis, Project, Registry, SectionCheck, SeismicCheck, StageSpec,
                                     seismic_file)
from webpier.reporting.stages.seismic_check import render_seismic_check

NDU = b"Virsion=5.2.3.S.4\r\n"
FOLDER = "model_JRSNAP"
FILES = (("pik", "model_Aggre-SE.pik"), ("xlsx", "model_Aggre-SE.xlsx"), ("steps", "model_Aggre-SE_直接基礎.csv"))
# A WDJ whose force table asks for the three 安全性（破壊） checks (the stand-in derives the sections from the rows).
WDJ = json.dumps({"crack": [{"vis_u": False}],
                  "force": [{"index": 1, "Md5_Md": -5942.86, "Vd5_Vd": 5249.37, "Mt5_Mt": 1058.28}]}).encode()
# The items of the fake stages (decision 72): G and H are the cantilever's, which uses both static nonlinear analyses.
OUTPUTS = {"ground_model": ("A",), "longitudinal_seismic": ("C",), "longitudinal_nonlinear_analysis": ("E",),
           "cantilever": ("G", "H")}
CANTILEVER = (*SEISMIC, "longitudinal_nonlinear_analysis", "transverse", "transverse_seismic",
              "transverse_nonlinear_analysis", "cantilever")
SECTIONS = ("bending_safety_destruction", "shear_safety_destruction", "torsion_safety_destruction")


@dataclass(frozen=True)
class Finished:
    """G's result after its completion: what it read of E's seismic check."""

    read: tuple[str, ...]  # the keys of the files it was given
    workbook_sha256: str


@dataclass(frozen=True)
class Checked:
    """H's result: the sections it asks Capacita for."""

    from_g: str
    sections: tuple[str, ...]


def project(folder: str, names) -> bytes:
    items = "".join(f"<string>{path}</string>" for path in databases(folder, names, 1))
    return (f'<?xml version="1.0" encoding="utf-16"?>\r\n<Datas><SNAP><SnapDBPath>{items}</SnapDBPath></SNAP>'
            "</Datas>").encode("cp932")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def registry(recorder: Recorder, rendered: list, complete_g=None) -> Registry:
    def finish_g(result, files, pier, results):
        recorder.log.append(("complete", "G", tuple(sorted(files))))
        if complete_g is not None:
            return complete_g(result, files, pier, results)
        return Finished(tuple(sorted(files)), sha(files[seismic_file("E", "xlsx")]))

    def finish_h(result, files, pier, results):
        recorder.log.append(("complete", "H", tuple(sorted(files))))
        assert result is None and isinstance(results["G"], Finished)
        return Checked(results["G"].workbook_sha256, SECTIONS)

    def render_h(results, pier, path, pages):
        recorder.log.append(("render", "H", tuple(results)))
        rendered.append(pages)
        Path(path).write_bytes(b"%PDF H")
        return path

    return Registry((
        StageSpec("A", "A_基礎", (), recorder.calculate("A"), recorder.render("A")),
        StageSpec("C", "C_地震", ("A",), recorder.calculate("C"), recorder.render("C"),
                  (Export("jrsnap", "model.ndu", recorder.export("C", NDU)),)),
        StageSpec("E", "E_解析", ("C",), render=lambda results, pier, path, pages: render_seismic_check(path, pages),
                  nonlinear_analysis=NonlinearAnalysis(
                      "C", "jrsnap", "jrsnap", FOLDER,
                      Project("aggrese", "model.xml", lambda results, pier: project, {"target": "Aggre-SE"})),
                  seismic_check=SeismicCheck(FILES)),
        StageSpec("G", "G_片持ち梁", ("A", "E"), recorder.calculate("G"), recorder.render("G"),
                  complete=finish_g),
        StageSpec("H", "H_照査", ("G",), None, render_h,
                  section_check=SectionCheck("wdj", "beam.wdj", lambda results, pier, pik: WDJ,
                                             lambda results: results["H"].sections),
                  complete=finish_h),
    ), outputs=OUTPUTS)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    for module in (jrsnap, aggrese, capacita):
        monkeypatch.setattr(module, "ENV_FILE", tmp_path / ".env")
    recorder, rendered = Recorder(), []
    options = GenerationOptions(copy_input(tmp_path / "pre", *CANTILEVER), tmp_path / "output", tmp_path / "post")
    return options, recorder, rendered


def test_a_stage_finishes_with_the_seismic_check_files_and_the_next_with_its_result(env):
    options, recorder, rendered = env
    stages = registry(recorder, rendered)
    generation = generate.generate(options, registry=stages)
    assert generation.stages == ("A", "C", "E", "G", "H")
    post = tree(Path(options.post_dir))
    # G and H read every file of E's check by seismic_file(stage, kind) (E is in both closures), after Aggre-SE ran
    # and before any report; H finishes with G's finished result.
    keys = tuple(sorted(seismic_file("E", kind) for kind, _ in FILES))
    assert keys == ("E/pik", "E/steps", "E/xlsx")
    first_completion = recorder.log.index(("complete", "G", keys))
    assert first_completion < recorder.log.index(("complete", "H", keys)) < recorder.log.index(("render", "H", ("G", "H")))
    assert all(action != "render" for action, _, _ in recorder.log[:first_completion])
    result_g = load_json((Path(options.output_dir) / "G_片持ち梁.json").read_bytes())
    assert result_g["result"]["workbook_sha256"] == sha(post["model_Aggre-SE.xlsx"])
    result_h = load_json((Path(options.output_dir) / "H_照査.json").read_bytes())
    assert result_h["result"] == {"from_g": sha(post["model_Aggre-SE.xlsx"]), "sections": list(SECTIONS)}
    assert planned(options, generation.stages, registry=stages) == generation.artifacts


def test_the_wdj_with_its_forces_is_calculated_as_given_and_published_as_written(env):
    options, recorder, rendered = env
    stages = registry(recorder, rendered)
    generate.generate(options, registry=stages)
    output, post = tree(Path(options.output_dir)), tree(Path(options.post_dir))
    assert post["beam.wdj"] == WDJ  # no completed WDJ comes back without a pickup
    # The pages of the three sections the force table asked for, cut from the stand-in's report.
    (pages,) = rendered
    assert tuple(pages) == SECTIONS
    digest = sha(WDJ)[:16]
    for section, count in zip(SECTIONS, (1, 2, 3)):
        with pymupdf.open(stream=pages[section], filetype="pdf") as document:
            assert [page.get_text().strip() for page in document] == [
                f"FAKE CAPACITA {section} {index}/{count} {digest}" for index in range(1, count + 1)]
    document = load_json(output["H_照査.json"])
    assert document["section_check"] == {"engine": "webdan2", "engine_version": "fake-1",
                                         "engineering_status": "not_evaluated",
                                         "wdj": {"file": "beam.wdj", "sha256": sha(WDJ)}, "skipped_sections": []}
    sidecar = load_json(post["beam.wdj.provenance.json"])
    assert (sidecar["stage"], sidecar["export"], sidecar["file"], sidecar["sha256"]) == ("H", "wdj", "beam.wdj", sha(WDJ))
    assert sidecar["section_check"] == {"engine": "webdan2", "engine_version": "fake-1",
                                        "engineering_status": "not_evaluated", "wdj_given": {"sha256": sha(WDJ)}}
    assert "pik" not in sidecar["section_check"]


def test_a_completion_that_cannot_read_the_workbook_publishes_nothing(env):
    options, recorder, rendered = env

    def failing(result, files, pier, results):
        raise ResponseError("最大応答震度の行がありません")

    with pytest.raises(GenerationError, match="Gの片持ち梁の照査ができません: 最大応答震度の行がありません"):
        generate.generate(options, registry=registry(recorder, rendered, failing))
    for directory in (options.output_dir, options.post_dir):
        assert not Path(directory).exists() or tree(Path(directory)) == {}
    assert rendered == [] and ("complete", "H", ()) not in recorder.log


@pytest.mark.parametrize("mode,message", [("fail", "RcDanが計算を完了できませんでした"), ("sections", "計算書の節（reportSections）がありません")])
def test_a_failing_section_check_publishes_nothing(env, monkeypatch: pytest.MonkeyPatch, mode, message):
    options, recorder, rendered = env
    monkeypatch.setenv("FAKE_CAPACITA", mode)
    with pytest.raises(GenerationError, match=f"beam.wdj で断面照査ができません: .*{message}"):
        generate.generate(options, registry=registry(recorder, rendered))
    for directory in (options.output_dir, options.post_dir):
        assert not Path(directory).exists() or tree(Path(directory)) == {}
    assert rendered == []


def test_without_a_capacita_runner_nothing_runs(env, monkeypatch: pytest.MonkeyPatch):
    options, recorder, rendered = env
    monkeypatch.setenv(capacita.RUNNER_KEY, "")
    with pytest.raises(GenerationError, match="Capacita の runner が設定されていません"):
        generate.generate(options, registry=registry(recorder, rendered))
    assert recorder.actions("calculate") == []
