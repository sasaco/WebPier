"""A stage with a column section check (decision 48, ADR-0008): after its frame analysis, Capacita checks the WDJ the
stage builds (from its results and that analysis' PIK) with the same PIK; the report takes Capacita's pages and the
sections it skipped for zero forces, the completed WDJ is published under post/ with a sidecar naming the PIK, the
result JSON records that the check ran (not its judgement) and what was skipped, the stage is made only when the
input chooses its 出力項目 (decision 72), and a missing or failing runner, or a PIK without the check point, publishes
nothing.

The expected WDJ and pages are those the stand-in runner documents (tests/fixtures/capacita/fake_runner.py), written
out here from the given bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf
import pytest

from pipeline_support import LONGITUDINAL, Recorder, choose, copy_input, tree
from webpier.export.capacita import PickupError
from webpier.pipeline import capacita, fempython, generate
from webpier.pipeline.generate import GenerationError, GenerationOptions, planned
from webpier.pipeline.stages import Export, FrameAnalysis, Registry, SectionCheck, StageSpec

FRAMEWEB = json.dumps({"dimension": 2, "load": {"1": {}}}).encode()
PICKUPS = (("pik", "frame.pik"), ("displacement", "frame_変位量.csv"), ("reaction", "frame_反力.csv"))
WDJ = json.dumps({"crack": [{"vis_u": True}]}).encode()
# A and B are the 線路方向's items; D, with its frame analysis, its own (decision 72)
OUTPUTS = {"ground_model": ("A",), "longitudinal": ("B",), "longitudinal_frame_analysis": ("D",)}
SECTIONS = ("section_forces", "bending_safety_destruction", "shear_safety_destruction", "bending_durability",
            "shear_durability", "bending_serviceability", "bending_restorability", "shear_restorability")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def texts(pdf: bytes) -> list[str]:
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        return [page.get_text().strip() for page in document]


PIK = f"FAKE PIK frame.json {sha(FRAMEWEB)}\n".encode()  # tests/fixtures/fempython/fake_runner.py


def completed() -> bytes:
    """The stand-in's model.wdj for WDJ checked with PIK as frame.pik."""
    document = json.loads(WDJ)
    document["pickup_filename"], document["pickup_data"] = "frame.pik", {"fake": sha(PIK)}
    return json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")


def registry(recorder: Recorder, rendered: list, given: list | None = None) -> Registry:
    def wdj(results, pier, pik):
        if given is not None:
            given.append(pik)
        return recorder.export("D", WDJ)(results, pier)

    def render(results, pier, path, pages):
        recorder.log.append(("render", "D", tuple(results)))
        rendered.append(pages)
        Path(path).write_bytes(b"%PDF D")
        return path

    return Registry((
        StageSpec("A", "A_基礎", (), recorder.calculate("A"), recorder.render("A")),
        StageSpec("B", "B_荷重", ("A",), recorder.calculate("B"), recorder.render("B"),
                  (Export("frameweb", "frame.json", recorder.export("B", FRAMEWEB)),)),
        StageSpec("D", "D_照査", ("B",), recorder.calculate("D"), render,
                  frame_analysis=FrameAnalysis("B", "frameweb", PICKUPS),
                  section_check=SectionCheck("wdj", "frame.wdj", wdj, lambda results: SECTIONS)),
    ), outputs=OUTPUTS)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    monkeypatch.setattr(fempython, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(capacita, "ENV_FILE", tmp_path / ".env")
    recorder, rendered, given = Recorder(), [], []
    options = GenerationOptions(copy_input(tmp_path / "pre", *LONGITUDINAL, "longitudinal_frame_analysis"),
                                tmp_path / "output", tmp_path / "post")
    return options, recorder, rendered, registry(recorder, rendered, given), given


def sidecar(options: GenerationOptions, name: str) -> dict:
    return json.loads((Path(options.post_dir) / f"{name}.provenance.json").read_text(encoding="utf-8"))


def test_the_check_publishes_the_completed_wdj_and_the_report(env):
    options, recorder, rendered, stages, given = env
    generation = generate.generate(options, registry=stages)
    assert generation.stages == ("A", "B", "D")
    output, post = tree(Path(options.output_dir)), tree(Path(options.post_dir))
    assert "D_照査.pdf" in output and "D_照査.json" in output
    assert post["frame.wdj"] == completed() and post["frame.pik"] == PIK
    assert "model.wdj" not in post and not any(name.endswith(".xlsx") for name in post)
    (pages,) = rendered  # Capacita's pages of each section, by its id, as the report takes them
    assert list(pages) == list(SECTIONS)
    assert {section: [text.rsplit(" ", 2)[0] for text in texts(content)] for section, content in pages.items()} == {
        section: [f"FAKE CAPACITA {section}"] * (2 if section == "section_forces" else 1) for section in SECTIONS}
    assert recorder.actions("export") == ["B", "D"]  # each built once
    assert given == [PIK]  # the WDJ is built from the PIK of the same analysis (point_index)


def test_the_result_json_records_that_the_check_ran(env):
    options, recorder, rendered, stages, given = env
    generate.generate(options, registry=stages)
    document = json.loads((Path(options.output_dir) / "D_照査.json").read_text(encoding="utf-8"))
    assert document["section_check"] == {"engine": "webdan2", "engine_version": "fake-1",
                                         "engineering_status": "not_evaluated",
                                         "wdj": {"file": "frame.wdj", "sha256": sha(completed())},
                                         "skipped_sections": []}


def test_the_sidecar_names_the_pik_and_the_wdj_given(env):
    options, recorder, rendered, stages, given = env
    generate.generate(options, registry=stages)
    record = sidecar(options, "frame.wdj")
    assert (record["stage"], record["export"], record["file"], record["sha256"]) == (
        "D", "wdj", "frame.wdj", sha(completed()))
    assert record["section_check"] == {
        "engine": "webdan2", "engine_version": "fake-1", "engineering_status": "not_evaluated",
        "pik": {"stage": "D", "kind": "pik", "file": "frame.pik", "sha256": sha(PIK)},
        "wdj_given": {"sha256": sha(WDJ)}}


def test_planned_names_the_report_and_the_wdj(env):
    options, recorder, rendered, stages, given = env
    roles = [artifact.role for artifact in planned(options, generate.selection(options, registry=stages),
                                                   registry=stages)]
    assert {"D.pdf", "D.json", "D.wdj", "D.wdj.provenance", "D.pik"} <= set(roles)


def test_an_input_without_the_frame_analysis_needs_no_capacita(env, monkeypatch: pytest.MonkeyPatch):
    options, recorder, rendered, stages, given = env
    monkeypatch.setenv(capacita.RUNNER_KEY, "")
    generate.generate(GenerationOptions(choose(Path(options.input_path), *LONGITUDINAL), options.output_dir,
                                        options.post_dir), registry=stages)
    assert "frame.wdj" not in tree(Path(options.post_dir)) and rendered == []


def test_a_missing_runner_stops_before_anything_is_calculated(env, monkeypatch: pytest.MonkeyPatch):
    options, recorder, rendered, stages, given = env
    monkeypatch.setenv(capacita.RUNNER_KEY, "")
    with pytest.raises(GenerationError, match="Capacita の runner が設定されていません"):
        generate.generate(options, registry=stages)
    assert recorder.log == []
    for directory in (options.output_dir, options.post_dir):
        assert not Path(directory).exists() or tree(Path(directory)) == {}


@pytest.mark.parametrize("mode", ["fail", "sections"])
def test_a_failing_check_publishes_nothing(env, monkeypatch: pytest.MonkeyPatch, mode):
    options, recorder, rendered, stages, given = env
    monkeypatch.setenv("FAKE_CAPACITA", mode)
    with pytest.raises(GenerationError, match="frame.pik で柱の断面照査ができません"):
        generate.generate(options, registry=stages)
    for directory in (options.output_dir, options.post_dir):
        assert not Path(directory).exists() or tree(Path(directory)) == {}
    assert rendered == []


def test_the_registry_needs_a_report_for_a_check_and_allows_one_without_a_frame_analysis():
    """Decision 59: a section check without a frame analysis is a WDJ with its own forces (0910)."""
    check = SectionCheck("wdj", "frame.wdj", lambda results, pier, pik: WDJ, lambda results: SECTIONS)
    base = (StageSpec("A", "A_基礎", (), lambda pier, results: 1, lambda results, pier, path, pages: path,
                      (Export("frameweb", "frame.json", lambda results, pier: FRAMEWEB),)),)
    outputs = {"ground_model": ("A", "D")}
    without = Registry((*base, StageSpec("D", "D_照査", ("A",), lambda pier, results: 1,
                                         lambda results, pier, path, pages: path, section_check=check)), outputs=outputs)
    assert without.get("D").frame_analysis is None and without.get("D").section_check is check
    with pytest.raises(ValueError, match="計算書"):
        Registry((*base, StageSpec("D", "D_照査", ("A",), frame_analysis=FrameAnalysis("A", "frameweb", PICKUPS),
                                   section_check=check)), outputs=outputs)
    with pytest.raises(ValueError, match="出力ファイル名が重複"):
        Registry((*base, StageSpec("D", "D_照査", ("A",), lambda pier, results: 1,
                                   lambda results, pier, path, pages: path,
                                   frame_analysis=FrameAnalysis("A", "frameweb", PICKUPS),
                                   section_check=SectionCheck("wdj", "frame.pik", check.build, check.sections))),
                 outputs=outputs)


def test_the_sections_capacita_skipped_reach_the_report_and_the_result_json(env, monkeypatch: pytest.MonkeyPatch):
    options, recorder, rendered, stages, given = env
    monkeypatch.setenv("FAKE_CAPACITA", "skip")
    generate.generate(options, registry=stages)
    (pages,) = rendered  # a skipped section has no pages
    assert list(pages) == [section for section in SECTIONS
                           if section not in ("shear_durability", "bending_serviceability")]
    document = json.loads((Path(options.output_dir) / "D_照査.json").read_text(encoding="utf-8"))
    assert document["section_check"]["skipped_sections"] == ["shear_durability", "bending_serviceability"]


def test_a_pik_without_the_check_point_publishes_nothing(env, monkeypatch: pytest.MonkeyPatch):
    options, recorder, rendered, stages, given = env

    def missing(results, pier, pik):
        raise PickupError("PIK に部材3のJTANがちょうど1つありません（0個）")

    stages = Registry((*stages.stages[:2], StageSpec(
        "D", "D_照査", ("B",), recorder.calculate("D"), stages.stages[2].render,
        frame_analysis=FrameAnalysis("B", "frameweb", PICKUPS),
        section_check=SectionCheck("wdj", "frame.wdj", missing, lambda results: SECTIONS))), outputs=OUTPUTS)
    with pytest.raises(GenerationError, match="frame.pik で柱の断面照査の WDJ を作れません: PIK に部材3の"):
        generate.generate(options, registry=stages)
    for directory in (options.output_dir, options.post_dir):
        assert not Path(directory).exists() or tree(Path(directory)) == {}
