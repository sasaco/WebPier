"""Decision 54: stages that analyze the same FrameWeb file share one analysis, and a stage may finish its result with
the returned files (the 基礎の照査 reads the support reactions) before any report is rendered."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from pipeline_support import FakeResult, Recorder, copy_input, fake_reactions, tree
from webpier.calc.foundation_check import ReactionError
from webpier.pipeline import fempython, generate
from webpier.pipeline.generate import GenerationError, GenerationOptions, planned
from webpier.pipeline.stages import FRAME_ANALYSIS, Export, FrameAnalysis, Registry, StageSpec

FRAMEWEB = json.dumps({"dimension": 2, "load": {"1": {}}, "node": {"1": {}, "2": {}},
                       "fix_node": {"1": [{"n": "2"}]}, "pickup": {"1": {"C1": 1, "C2": 2}}}).encode()
PICKUPS = (("pik", "frame.pik"), ("displacement", "frame_変位量.csv"), ("reaction", "frame_反力.csv"))
PICKUP_FILES = [name for _, name in PICKUPS]


def _complete(result: FakeResult, files, pier=None, results=None) -> FakeResult:
    return replace(result, read=(*result.read, "reaction " + hashlib.sha256(files["reaction"]).hexdigest()))


def registry(recorder: Recorder, complete=_complete) -> Registry:
    return Registry((
        StageSpec("A", "A_基礎", (), recorder.calculate("A"), recorder.render("A")),
        StageSpec("B", "B_荷重", ("A",), recorder.calculate("B"), recorder.render("B"),
                  (Export("frameweb", "frame.json", recorder.export("B", FRAMEWEB)),)),
        StageSpec("D", "D_照査", ("B",), opt_in=FRAME_ANALYSIS, frame_analysis=FrameAnalysis("B", "frameweb", PICKUPS)),
        StageSpec("E", "E_基礎", ("A", "B"), recorder.calculate("E"), recorder.render("E"), opt_in=FRAME_ANALYSIS,
                  frame_analysis=FrameAnalysis("B", "frameweb", PICKUPS), complete=complete),
    ))


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    monkeypatch.setattr(fempython, "ENV_FILE", tmp_path / ".env")
    calls: list[str] = []
    analyze = generate.analyze_frame
    monkeypatch.setattr(generate, "analyze_frame", lambda name, *args, **kwargs: (calls.append(name),
                                                                                  analyze(name, *args, **kwargs))[1])
    recorder = Recorder()
    options = GenerationOptions(copy_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post",
                                frame_analysis=True)
    return options, recorder, calls


def with_(options: GenerationOptions, **changes) -> GenerationOptions:
    return GenerationOptions(**{**options.__dict__, **changes})


def sidecar(options: GenerationOptions, name: str) -> dict:
    return json.loads((Path(options.post_dir) / f"{name}.provenance.json").read_text(encoding="utf-8"))


def test_two_stages_of_one_frameweb_file_share_one_analysis_and_one_set_of_files(env):
    options, recorder, calls = env
    generation = generate.generate(options, registry=registry(recorder))
    assert generation.stages == ("A", "B", "D", "E") and calls == ["frame.json"]
    post = tree(Path(options.post_dir))
    assert sorted(post) == sorted(["frame.json", *PICKUP_FILES,
                                   *(name + ".provenance.json" for name in ["frame.json", *PICKUP_FILES])])
    assert post["frame_反力.csv"] == fake_reactions(FRAMEWEB)
    document = sidecar(options, "frame.pik")
    assert (document["stage"], document["frame_analysis"]["stages"]) == ("D", ["D", "E"])
    assert [artifact.role for artifact in generation.artifacts if artifact.role.endswith(".reaction")] == ["D.reaction"]


def test_a_stage_finishes_its_result_with_the_returned_files_before_its_report(env):
    options, recorder, _ = env
    generation = generate.generate(options, registry=registry(recorder))
    finished = "reaction " + hashlib.sha256(fake_reactions(FRAMEWEB)).hexdigest()
    assert generation.results["E"].read == ("A", "B", finished)
    assert ("render", "E", ("A", "B", "E")) in recorder.log
    result = json.loads((Path(options.output_dir) / "E_基礎.json").read_text(encoding="utf-8"))["result"]
    assert result["read"] == ["A", "B", finished]


def test_the_stage_chosen_alone_publishes_the_shared_files_as_its_own(env):
    options, recorder, calls = env
    generate.generate(with_(options, stage="E", frame_analysis=False), registry=registry(recorder))
    assert calls == ["frame.json"]
    assert sorted(tree(Path(options.output_dir))) == ["E_基礎.json", "E_基礎.pdf"]
    assert sidecar(options, "frame.pik")["stage"] == "E"
    roles = [artifact.role for artifact in planned(with_(options, stage="E", frame_analysis=False),
                                                   registry=registry(recorder))]
    assert roles == ["E.pdf", "E.json", "E.pik", "E.displacement", "E.reaction", "E.pik.provenance",
                     "E.displacement.provenance", "E.reaction.provenance"]


def test_reactions_that_cannot_be_read_stop_the_generation_before_any_report(env):
    options, recorder, _ = env

    def broken(result, files, pier=None, results=None):
        raise ReactionError("支点の反力のピックアップ 7（fy）がありません")

    with pytest.raises(GenerationError, match="frame_反力.csv でEの基礎の照査ができません: 支点の反力のピックアップ 7"):
        generate.generate(options, registry=registry(recorder, broken))
    assert recorder.actions("render") == []
    assert not Path(options.output_dir).exists() and not Path(options.post_dir).exists()


def _stage(stage_id: str, **changes) -> StageSpec:
    recorder = Recorder()
    return StageSpec(stage_id, f"{stage_id}_x", ("B",), recorder.calculate(stage_id), recorder.render(stage_id),
                     opt_in=FRAME_ANALYSIS, frame_analysis=FrameAnalysis("B", "frameweb", PICKUPS), **changes)


def test_the_registry_checks_the_shared_analysis_and_the_finishing_step():
    recorder = Recorder()
    base = registry(recorder).stages[:2]
    other = (("pik", "other.pik"), ("displacement", "other_変位量.csv"), ("reaction", "other_反力.csv"))
    with pytest.raises(ValueError, match="FはBの骨組解析を共有するので、同じ出力が必要です"):
        Registry((*base, _stage("D"), replace(_stage("F"), frame_analysis=FrameAnalysis("B", "frameweb", other))))
    with pytest.raises(ValueError, match="Fの結果を仕上げるには、骨組解析か、耐震性能照査または仕上げる結果を持つ依存段階が必要です"):
        Registry((*base, replace(_stage("F"), frame_analysis=None, opt_in="", complete=_complete)))
    with pytest.raises(ValueError, match="Fの結果を仕上げるには計算書が必要です"):
        Registry((*base, replace(_stage("F"), render=None, complete=_complete)))
