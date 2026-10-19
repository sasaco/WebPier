"""The generation mechanics of decision 60: a stage that opts into both switches finishes its result with the files
of the frame analyses and of the seismic checks of its dependencies (``seismic_file``: "<stage>/<kind>"), after every
runner ran and before any report; all includes it only with both switches.

The analyses and checks are the stand-ins' (tests/fixtures/fempython, jrsnap, aggrese)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from pipeline_support import Recorder, copy_input, fake_reactions, footing_input, tree
from webpier.calc.footing import StepsError
from webpier.calc.foundation_check import ReactionError
from webpier.core.integrity import load_json
from webpier.export.aggrese import databases
from webpier.pipeline import aggrese, fempython, generate, jrsnap
from webpier.pipeline.generate import GenerationError, GenerationOptions
from webpier.pipeline.generate import planned
from webpier.pipeline.stages import (FRAME_ANALYSIS, NONLINEAR_ANALYSIS, STAGES, Export, FrameAnalysis,
                                     NonlinearAnalysis, Project, Registry, SeismicCheck, StageSpec, seismic_file)
from webpier.reporting.stages.seismic_check import render_seismic_check

FRAMEWEB = json.dumps({"dimension": 2, "load": {"1": {}}, "node": {"1": {}, "2": {}},
                       "fix_node": {"1": [{"n": "2"}]}, "pickup": {"1": {"C1": 1, "C2": 2}}}).encode()
PICKUPS = (("pik", "frame.pik"), ("displacement", "frame_変位量.csv"), ("reaction", "frame_反力.csv"))
NDU = b"Virsion=5.2.3.S.4\r\n"
FOLDER = "model_JRSNAP"
FILES = (("pik", "model_Aggre-SE.pik"), ("xlsx", "model_Aggre-SE.xlsx"), ("steps", "model_Aggre-SE_直接基礎.csv"))


@dataclass(frozen=True)
class Finished:
    """F's result after its completion: the keys of the files it was given and the reaction CSV it read."""

    read: tuple[str, ...]
    reactions: str


def project(folder: str, names) -> bytes:
    items = "".join(f"<string>{path}</string>" for path in databases(folder, names, 1))
    return (f'<?xml version="1.0" encoding="utf-16"?>\r\n<Datas><SNAP><SnapDBPath>{items}</SnapDBPath></SNAP>'
            "</Datas>").encode("cp932")


def registry(recorder: Recorder, complete_f=None) -> Registry:
    def finish_f(result, files, pier, results):
        recorder.log.append(("complete", "F", tuple(sorted(files))))
        if complete_f is not None:
            return complete_f(result, files, pier, results)
        return Finished(tuple(sorted(files)), files[seismic_file("D", "reaction")].decode("utf-8-sig"))

    return Registry((
        StageSpec("A", "A_基礎", (), recorder.calculate("A"), recorder.render("A")),
        StageSpec("B", "B_荷重", ("A",), recorder.calculate("B"), recorder.render("B"),
                  (Export("frameweb", "frame.json", recorder.export("B", FRAMEWEB)),)),
        StageSpec("D", "D_照査", ("B",), opt_in=FRAME_ANALYSIS, frame_analysis=FrameAnalysis("B", "frameweb", PICKUPS)),
        StageSpec("C", "C_地震", ("A",), recorder.calculate("C"), recorder.render("C"),
                  (Export("jrsnap", "model.ndu", recorder.export("C", NDU)),)),
        StageSpec("E", "E_解析", ("C",), render=lambda results, pier, path, pages: render_seismic_check(path, pages),
                  opt_in=NONLINEAR_ANALYSIS,
                  nonlinear_analysis=NonlinearAnalysis(
                      "C", "jrsnap", "jrsnap", FOLDER,
                      Project("aggrese", "model.xml", lambda results, pier: project, {"target": "Aggre-SE"})),
                  seismic_check=SeismicCheck(FILES)),
        StageSpec("F", "F_フーチング", ("A", "B", "D", "E"), recorder.calculate("F"), recorder.render("F"),
                  opt_in=(FRAME_ANALYSIS, NONLINEAR_ANALYSIS), complete=finish_f),
    ))


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    for module in (fempython, jrsnap, aggrese):
        monkeypatch.setattr(module, "ENV_FILE", tmp_path / ".env")
    recorder = Recorder()
    options = GenerationOptions(copy_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post",
                                frame_analysis=True, nonlinear_analysis=True)
    return options, recorder


def test_a_stage_finishes_with_the_files_of_the_analyses_and_the_checks_of_its_dependencies(env):
    options, recorder = env
    stages = registry(recorder)
    generation = generate.generate(options, registry=stages)
    assert generation.stages == ("A", "B", "D", "C", "E", "F")
    keys = ("D/displacement", "D/pik", "D/reaction", "E/pik", "E/steps", "E/xlsx")
    assert keys == tuple(sorted([*(seismic_file("D", kind) for kind, _ in PICKUPS),
                                 *(seismic_file("E", kind) for kind, _ in FILES)]))
    completion = recorder.log.index(("complete", "F", keys))
    assert all(action != "render" for action, _, _ in recorder.log[:completion])
    assert completion < recorder.log.index(("render", "F", ("A", "B", "F")))
    post = tree(Path(options.post_dir))
    assert generation.results["F"].reactions == fake_reactions(FRAMEWEB).decode("utf-8-sig")
    assert post["frame_反力.csv"] == fake_reactions(FRAMEWEB)
    result = load_json((Path(options.output_dir) / "F_フーチング.json").read_bytes())
    assert result["result"]["read"] == list(keys)


@pytest.mark.parametrize("switches,expected", [
    ({}, ("A", "B", "C")), ({"frame_analysis": True}, ("A", "B", "D", "C")),
    ({"nonlinear_analysis": True}, ("A", "B", "C", "E")),
])
def test_all_leaves_the_stage_out_unless_both_switches_are_given(env, switches, expected):
    options, recorder = env
    options = GenerationOptions(**{**options.__dict__, "frame_analysis": False, "nonlinear_analysis": False,
                                   **switches})
    assert generate.generate(options, registry=registry(recorder)).stages == expected


@pytest.mark.parametrize("error,message", [
    (ReactionError("支点の反力のピックアップ 1（mz）がありません"),
     "依存段階の反力でFの結果を仕上げられません: 支点の反力のピックアップ 1"),
    (StepsError("どの Case も Rvd到達ステップがありません"), "直接基礎のステップ表でFの結果を仕上げられません: どの Case も"),
])
def test_a_completion_that_cannot_read_the_dependencies_files_stops_the_generation(env, error, message):
    options, recorder = env

    def broken(result, files, pier, results):
        raise error

    with pytest.raises(GenerationError, match=message):
        generate.generate(options, registry=registry(recorder, broken))
    assert recorder.actions("render") == []
    assert not Path(options.output_dir).exists() and not Path(options.post_dir).exists()


# --- the real registry with the stand-in runners -----------------------------------------------------------------


@pytest.fixture(scope="module")
def footing_generation(tmp_path_factory):
    root = tmp_path_factory.mktemp("footing")
    source = footing_input(root / "pre")
    options = GenerationOptions(source, root / "output", root / "post", frame_analysis=True, nonlinear_analysis=True)
    return root, options, generate.generate(options)


def test_both_switches_add_the_footing_stages_with_their_reports_and_wdjs(footing_generation):
    """Decision 60 with the real registry: 0800 reads the reactions of 0612・0622 and the step tables of 0711・0721
    (the 地震時 column is the Case with the largest |M|: the stand-in adds 100 kN m per Case), 0810・0820 publish the
    WDJ WebPier wrote and record the check as not evaluated; 0800 has no engineering status of its own."""
    root, options, generation = footing_generation
    assert generation.stages == STAGES.ids and planned(options) == generation.artifacts
    output, post = tree(root / "output"), tree(root / "post")
    for stem in ("0800_フーチング", "0810_線路方向フーチング照査", "0820_直角方向フーチング照査"):
        assert output[f"{stem}.pdf"].startswith(b"%PDF-")
    result = load_json(output["0800_フーチング.json"])
    assert "section_check" not in result and "engineering_status" not in result["result"]
    for direction, case_index in (("longitudinal", 0), ("transverse", 1)):
        columns = result["result"][direction]["columns"]
        assert [column["key"] for column in columns] == ["safety_moment", "safety_shear", "short_term", "long_term",
                                                          "seismic"]
        source = columns[-1]["source"]
        assert (source["case_index"], source["pickup"]) == (case_index, None) and source["step"] >= 1
        assert columns[0]["source"]["pickup"] is not None
    for stage, name in (("0810", "線路方向フーチング.wdj"), ("0820", "線路直角方向フーチング.wdj")):
        assert post[name].startswith(b"{") and load_json(post[name + ".provenance.json"])["stage"] == stage
        check = load_json(output[f"{STAGES.get(stage).stem}.json"])
        assert check["section_check"]["engineering_status"] == "not_evaluated"
        assert check["section_check"]["wdj"]["file"] == name and check["section_check"]["skipped_sections"] == []
        assert (check["result"]["name"], check["result"]["member"]) == (name.removesuffix("フーチング.wdj"), "フーチング")
        assert check["result"]["seismic"]["column"] == "seismic" and check["result"]["safety"]["la"] > 0


def test_a_footing_check_chosen_alone_brings_the_stages_whose_runners_it_reads(tmp_path):
    """Decision 60 (owner 2026-10-19): --stage 0810 generates and publishes 0612・0622 (the frame analyses),
    0711・0721 (the nonlinear analyses and seismic checks) and 0800 (the finished response values) with it; the plain
    stages are only calculated, and nothing of 0611・0621・0820 is written."""
    source = footing_input(tmp_path / "pre")
    options = GenerationOptions(source, tmp_path / "output", tmp_path / "post", stage="0810")
    generation = generate.generate(options)
    assert generation.stages == ("0612", "0622", "0711", "0721", "0800", "0810")
    output, post = tree(tmp_path / "output"), tree(tmp_path / "post")
    assert sorted(name for name in output if name.endswith(".pdf")) == sorted(
        f"{STAGES.get(stage).stem}.pdf" for stage in generation.stages)
    for name in ("線路方向_ピックアップ反力.csv", "線路直角方向_Aggre-SE_直接基礎.csv", "線路方向フーチング.wdj", "線路方向.xml"):
        assert name in post, name
    assert "線路直角方向フーチング.wdj" not in post and "線路方向.wdj" not in post and "線路方向.json" not in post
    assert planned(options) == generation.artifacts
