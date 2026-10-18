"""A stage with a frame analysis (decision 46): FEMPython analyzes the FrameWeb file of its dependency, the pickup
files are published as they are returned with sidecars that name the analyzed bytes, the stage is left out of all
unless asked for, and a failing analysis publishes nothing.

The expected pickup bytes are those the stand-in runner documents (tests/fixtures/fempython/fake_runner.py), written
out here from the analyzed bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipeline_support import Recorder, copy_input, fake_reactions, tree
from webpier.core.errors import InputError
from webpier.pipeline import fempython, generate
from webpier.pipeline.generate import GenerationError, GenerationOptions, planned
from webpier.pipeline.stages import FRAME_ANALYSIS, Export, FrameAnalysis, Registry, StageSpec

FRAMEWEB = json.dumps({"dimension": 2, "load": {"1": {}, "2": {}, "3": {}}}).encode()
PICKUPS = (("pik", "frame.pik"), ("displacement", "frame_変位量.csv"), ("reaction", "frame_反力.csv"))
PICKUP_FILES = ["frame.pik", "frame_変位量.csv", "frame_反力.csv"]


def registry(recorder: Recorder, *, load_diagram: bool = False, pages: list | None = None) -> Registry:
    def render(results, pier, path, *drawn):
        recorder.log.append(("render", "B", tuple(results)))
        if pages is not None:
            pages.append(drawn)
        Path(path).write_bytes(b"%PDF B")
        return path

    return Registry((
        StageSpec("A", "A_基礎", (), recorder.calculate("A"), recorder.render("A")),
        StageSpec("B", "B_荷重", ("A",), recorder.calculate("B"), render,
                  (Export("frameweb", "frame.json", recorder.export("B", FRAMEWEB)),),
                  load_diagram="frameweb" if load_diagram else ""),
        StageSpec("D", "D_照査", ("B",), opt_in=FRAME_ANALYSIS, frame_analysis=FrameAnalysis("B", "frameweb", PICKUPS)),
    ))


def expected(word: str) -> bytes:
    """The stand-in's file for *word* (PIK, DISPLACEMENT, REACTION) of an analysis of FRAMEWEB as frame.json."""
    if word == "REACTION":
        return fake_reactions(FRAMEWEB)
    return f"FAKE {word} frame.json {hashlib.sha256(FRAMEWEB).hexdigest()}\n".encode("utf-8")


def sidecar(options: GenerationOptions, name: str) -> dict:
    return json.loads((Path(options.post_dir) / f"{name}.provenance.json").read_text(encoding="utf-8"))


def published(options: GenerationOptions) -> list[Path]:
    return [path for directory in (options.output_dir, options.post_dir) if Path(directory).exists()
            for path in Path(directory).iterdir()]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    monkeypatch.setattr(fempython, "ENV_FILE", tmp_path / ".env")
    recorder = Recorder()
    options = GenerationOptions(copy_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post")
    return options, recorder, registry(recorder)


def with_(options: GenerationOptions, **changes) -> GenerationOptions:
    return GenerationOptions(**{**options.__dict__, **changes})


def test_all_leaves_the_analysis_out_and_needs_no_runner(env, monkeypatch: pytest.MonkeyPatch):
    options, recorder, stages = env
    monkeypatch.setenv(fempython.RUNNER_KEY, "")
    generate.generate(options, registry=stages)
    assert sorted(tree(Path(options.post_dir))) == ["frame.json", "frame.json.provenance.json"]


def test_the_frame_analysis_publishes_the_pickup_files_as_returned(env):
    options, recorder, stages = env
    generation = generate.generate(with_(options, frame_analysis=True), registry=stages)
    assert generation.stages == ("A", "B", "D")
    output, post = tree(Path(options.output_dir)), tree(Path(options.post_dir))
    assert sorted(output) == ["A_基礎.json", "A_基礎.pdf", "B_荷重.json", "B_荷重.pdf"]  # D has no report
    assert sorted(post) == sorted(["frame.json", *PICKUP_FILES,
                                   *(name + ".provenance.json" for name in ["frame.json", *PICKUP_FILES])])
    assert (post["frame.pik"], post["frame_変位量.csv"], post["frame_反力.csv"]) == (
        expected("PIK"), expected("DISPLACEMENT"), expected("REACTION"))
    assert post["frame.json"] == FRAMEWEB
    assert recorder.actions("export") == ["B"]  # built once: the staged file is the file analyzed


def test_the_sidecar_of_a_pickup_file_names_the_analyzed_frameweb_file(env):
    options, _, stages = env
    generate.generate(with_(options, frame_analysis=True), registry=stages)
    document = sidecar(options, "frame.pik")
    assert {key: document[key] for key in ("stage", "export", "file", "sha256", "selected_stages")} == {
        "stage": "D", "export": "pik", "file": "frame.pik", "sha256": hashlib.sha256(expected("PIK")).hexdigest(),
        "selected_stages": ["A", "B", "D"]}
    assert document["frame_analysis"] == {
        "engine": "fempython", "engine_version": "fake-1",
        "frameweb": {"stage": "B", "export": "frameweb", "file": "frame.json",
                     "sha256": hashlib.sha256(FRAMEWEB).hexdigest()}, "stages": ["D"]}
    assert "metadata" not in document and "load_diagram" not in document
    assert sorted(item["role"] for item in document["artifacts"]) == sorted(
        ["A.pdf", "A.json", "B.pdf", "B.json", "B.frameweb", "D.pik", "D.displacement", "D.reaction"])
    assert sidecar(options, "frame_反力.csv")["export"] == "reaction"
    assert "frame_analysis" not in sidecar(options, "frame.json")


def test_a_stage_chosen_alone_is_analyzed_with_its_dependencies_calculated(env):
    options, recorder, stages = env
    generate.generate(with_(options, stage="D"), registry=stages)
    assert not Path(options.output_dir).exists()
    post = tree(Path(options.post_dir))
    assert sorted(post) == sorted([*PICKUP_FILES, *(name + ".provenance.json" for name in PICKUP_FILES)])
    assert post["frame.pik"] == expected("PIK")
    assert recorder.actions("calculate") == ["A", "B"] and recorder.actions("render") == []
    document = sidecar(options, "frame.pik")
    # frame.json is not of this generation: the sidecar's SHA256 is what binds the analysis to it.
    assert document["frame_analysis"]["frameweb"]["sha256"] == hashlib.sha256(FRAMEWEB).hexdigest()
    assert sorted(item["role"] for item in document["artifacts"]) == ["D.displacement", "D.pik", "D.reaction"]


def test_the_load_diagram_and_the_analysis_are_separate_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    pages: list = []
    stages = registry(Recorder(), load_diagram=True, pages=pages)
    options = GenerationOptions(copy_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post",
                                frame_analysis=True)
    generate.generate(options, registry=stages)
    ((drawn,),) = pages
    assert drawn.startswith(b"%PDF")
    assert (tmp_path / "post" / "frame.pik").read_bytes() == expected("PIK")
    assert sidecar(options, "frame.json")["load_diagram"]["engine_version"] == "fake-1"


def test_a_failing_analysis_stops_before_any_report_and_publishes_nothing(env, monkeypatch: pytest.MonkeyPatch):
    options, recorder, stages = env
    monkeypatch.setenv("FAKE_FEMPYTHON", "analysis-fail")
    with pytest.raises(GenerationError, match="frame.json を FEMPython で骨組解析できません: EMPTY_PIK"):
        generate.generate(with_(options, frame_analysis=True), registry=stages)
    assert recorder.actions("render") == [] and published(options) == []


def test_without_a_runner_nothing_is_read_or_published(env, monkeypatch: pytest.MonkeyPatch):
    options, _, stages = env
    monkeypatch.setenv(fempython.RUNNER_KEY, "")
    read = []
    monkeypatch.setattr(generate, "parse_input", lambda data: read.append(data))
    with pytest.raises(GenerationError, match="runner が設定されていません"):
        generate.generate(with_(options, stage="D"), registry=stages)
    assert read == [] and published(options) == []


def test_a_generation_without_the_analysis_keeps_the_earlier_pickup_files(env):
    options, _, stages = env
    generate.generate(with_(options, frame_analysis=True), registry=stages)
    before = {name: content for name, content in tree(Path(options.post_dir)).items() if not name.startswith("frame.json")}
    generate.generate(with_(options, overwrite=True), registry=stages)
    after = tree(Path(options.post_dir))
    assert {name: after[name] for name in before} == before


def test_the_planned_files_follow_the_frame_analysis_option(env):
    options, _, stages = env
    roles = [artifact.role for artifact in planned(with_(options, frame_analysis=True), registry=stages)]
    assert roles == ["A.pdf", "A.json", "B.pdf", "B.json", "B.frameweb", "D.pik", "D.displacement", "D.reaction",
                     "B.frameweb.provenance", "D.pik.provenance", "D.displacement.provenance",
                     "D.reaction.provenance"]
    assert [artifact.path.name for artifact in planned(with_(options, stage="D"), registry=stages)] == [
        *PICKUP_FILES, *(name + ".provenance.json" for name in PICKUP_FILES)]
    assert "D.pik" not in [artifact.role for artifact in planned(options, registry=stages)]
    with pytest.raises(InputError, match="--frame-analysis は --stage all と使います"):
        planned(with_(options, stage="B", frame_analysis=True), registry=stages)
