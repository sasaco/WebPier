"""A stage with a column section check (decision 48, ADR-0008): after its frame analysis, Capacita checks the WDJ the
stage builds with the PIK of that analysis; the report takes Capacita's pages, the completed WDJ is published under
post/ with a sidecar naming the PIK, the result JSON records that the check ran (not its judgement), the stage is left
out of all unless asked for, and a missing or failing runner publishes nothing.

The expected WDJ and pages are those the stand-in runner documents (tests/fixtures/capacita/fake_runner.py), written
out here from the given bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipeline_support import Recorder, copy_input, tree
from webpier.pipeline import capacita, fempython, generate
from webpier.pipeline.capacita import ColumnCheckPages
from webpier.pipeline.generate import GenerationError, GenerationOptions, planned
from webpier.pipeline.stages import FRAME_ANALYSIS, Export, FrameAnalysis, Registry, SectionCheck, StageSpec

FRAMEWEB = json.dumps({"dimension": 2, "load": {"1": {}}}).encode()
PICKUPS = (("pik", "frame.pik"), ("displacement", "frame_変位量.csv"), ("reaction", "frame_反力.csv"))
WDJ = json.dumps({"crack": [{"vis_u": True}]}).encode()
SECTIONS = ("section_forces", "bending_safety_destruction", "shear_safety_destruction", "bending_durability",
            "shear_durability", "bending_serviceability", "bending_restorability", "shear_restorability")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


PIK = f"FAKE PIK frame.json {sha(FRAMEWEB)}\n".encode()  # tests/fixtures/fempython/fake_runner.py


def completed() -> bytes:
    """The stand-in's model.wdj for WDJ checked with PIK as frame.pik."""
    document = json.loads(WDJ)
    document["pickup_filename"], document["pickup_data"] = "frame.pik", {"fake": sha(PIK)}
    return json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")


def registry(recorder: Recorder, rendered: list) -> Registry:
    def render(results, pier, path, pages):
        recorder.log.append(("render", "D", tuple(results)))
        rendered.append(pages)
        Path(path).write_bytes(b"%PDF D")
        return path

    return Registry((
        StageSpec("A", "A_基礎", (), recorder.calculate("A"), recorder.render("A")),
        StageSpec("B", "B_荷重", ("A",), recorder.calculate("B"), recorder.render("B"),
                  (Export("frameweb", "frame.json", recorder.export("B", FRAMEWEB)),)),
        StageSpec("D", "D_照査", ("B",), recorder.calculate("D"), render, opt_in=FRAME_ANALYSIS,
                  frame_analysis=FrameAnalysis("B", "frameweb", PICKUPS),
                  section_check=SectionCheck("wdj", "frame.wdj", recorder.export("D", WDJ), lambda results: SECTIONS)),
    ))


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    monkeypatch.setattr(fempython, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(capacita, "ENV_FILE", tmp_path / ".env")
    recorder, rendered = Recorder(), []
    options = GenerationOptions(copy_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post",
                                frame_analysis=True)
    return options, recorder, rendered, registry(recorder, rendered)


def sidecar(options: GenerationOptions, name: str) -> dict:
    return json.loads((Path(options.post_dir) / f"{name}.provenance.json").read_text(encoding="utf-8"))


def test_the_check_publishes_the_completed_wdj_and_the_report(env):
    options, recorder, rendered, stages = env
    generation = generate.generate(options, registry=stages)
    assert generation.stages == ("A", "B", "D")
    output, post = tree(Path(options.output_dir)), tree(Path(options.post_dir))
    assert "D_照査.pdf" in output and "D_照査.json" in output
    assert post["frame.wdj"] == completed() and post["frame.pik"] == PIK
    assert "model.wdj" not in post and not any(name.endswith(".xlsx") for name in post)
    (pages,) = rendered
    assert isinstance(pages, ColumnCheckPages) and [section.id for section in pages.sections] == list(SECTIONS)
    assert pages.wdj == completed()
    assert recorder.actions("export") == ["B", "D"]  # each built once


def test_the_result_json_records_that_the_check_ran(env):
    options, recorder, rendered, stages = env
    generate.generate(options, registry=stages)
    document = json.loads((Path(options.output_dir) / "D_照査.json").read_text(encoding="utf-8"))
    assert document["section_check"] == {"engine": "webdan2", "engine_version": "fake-1",
                                         "engineering_status": "not_evaluated",
                                         "wdj": {"file": "frame.wdj", "sha256": sha(completed())}}


def test_the_sidecar_names_the_pik_and_the_wdj_given(env):
    options, recorder, rendered, stages = env
    generate.generate(options, registry=stages)
    record = sidecar(options, "frame.wdj")
    assert (record["stage"], record["export"], record["file"], record["sha256"]) == (
        "D", "wdj", "frame.wdj", sha(completed()))
    assert record["section_check"] == {
        "engine": "webdan2", "engine_version": "fake-1", "engineering_status": "not_evaluated",
        "pik": {"stage": "D", "kind": "pik", "file": "frame.pik", "sha256": sha(PIK)},
        "wdj_given": {"sha256": sha(WDJ)}}


def test_planned_names_the_report_and_the_wdj(env):
    options, recorder, rendered, stages = env
    roles = [artifact.role for artifact in planned(options, registry=stages)]
    assert {"D.pdf", "D.json", "D.wdj", "D.wdj.provenance", "D.pik"} <= set(roles)


def test_all_without_the_switch_needs_no_capacita(env, monkeypatch: pytest.MonkeyPatch):
    options, recorder, rendered, stages = env
    monkeypatch.setenv(capacita.RUNNER_KEY, "")
    generate.generate(GenerationOptions(**{**options.__dict__, "frame_analysis": False}), registry=stages)
    assert "frame.wdj" not in tree(Path(options.post_dir)) and rendered == []


def test_a_missing_runner_stops_before_anything_is_calculated(env, monkeypatch: pytest.MonkeyPatch):
    options, recorder, rendered, stages = env
    monkeypatch.setenv(capacita.RUNNER_KEY, "")
    with pytest.raises(GenerationError, match="Capacita の runner が設定されていません"):
        generate.generate(options, registry=stages)
    assert recorder.log == []
    for directory in (options.output_dir, options.post_dir):
        assert not Path(directory).exists() or tree(Path(directory)) == {}


@pytest.mark.parametrize("mode", ["fail", "sections"])
def test_a_failing_check_publishes_nothing(env, monkeypatch: pytest.MonkeyPatch, mode):
    options, recorder, rendered, stages = env
    monkeypatch.setenv("FAKE_CAPACITA", mode)
    with pytest.raises(GenerationError, match="frame.pik で柱の断面照査ができません"):
        generate.generate(options, registry=stages)
    for directory in (options.output_dir, options.post_dir):
        assert not Path(directory).exists() or tree(Path(directory)) == {}
    assert rendered == []


def test_the_registry_needs_a_frame_analysis_and_a_report_for_a_check():
    check = SectionCheck("wdj", "frame.wdj", lambda results, pier: WDJ, lambda results: SECTIONS)
    base = (StageSpec("A", "A_基礎", (), lambda pier, results: 1, lambda results, pier, path: path,
                      (Export("frameweb", "frame.json", lambda results, pier: FRAMEWEB),)),)
    with pytest.raises(ValueError, match="骨組解析"):
        Registry((*base, StageSpec("D", "D_照査", ("A",), lambda pier, results: 1,
                                   lambda results, pier, path, pages: path, opt_in=FRAME_ANALYSIS,
                                   section_check=check)))
    with pytest.raises(ValueError, match="計算書"):
        Registry((*base, StageSpec("D", "D_照査", ("A",), opt_in=FRAME_ANALYSIS,
                                   frame_analysis=FrameAnalysis("A", "frameweb", PICKUPS), section_check=check)))
    with pytest.raises(ValueError, match="出力ファイル名が重複"):
        Registry((*base, StageSpec("D", "D_照査", ("A",), lambda pier, results: 1,
                                   lambda results, pier, path, pages: path, opt_in=FRAME_ANALYSIS,
                                   frame_analysis=FrameAnalysis("A", "frameweb", PICKUPS),
                                   section_check=SectionCheck("wdj", "frame.pik", check.build, check.sections))))
