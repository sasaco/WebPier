"""The generation mechanics of decision 60: a stage that reads both analyses finishes its result with the files of the
frame analyses and of the seismic checks of its dependencies (``seismic_file``: "<stage>/<kind>"), after every runner
ran and before any report; its 出力項目 is chosen with the items of both directions of either analysis, and a stage of
one part reads that part's analyses alone (decisions 72 and 110).

The analyses and checks are the stand-ins' (tests/fixtures/fempython, jrsnap, aggrese)."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from pipeline_support import SEISMIC, Recorder, choose, copy_input, fake_reactions, footing_input, tree
from webpier.calc.footing import StepsError
from webpier.calc.foundation_check import ReactionError
from webpier.core.errors import InputError
from webpier.core.integrity import load_json
from webpier.export.aggrese import databases
from webpier.inputs.outputs import OUTPUT_KEYS
from webpier.pipeline import aggrese, fempython, generate, jrsnap
from webpier.pipeline.generate import GenerationError, GenerationOptions
from webpier.pipeline.generate import planned
from webpier.pipeline.stages import (STAGES, Export, FrameAnalysis, NonlinearAnalysis, Project, Registry, SeismicCheck,
                                     StageSpec, seismic_file)
from webpier.reporting.stages.seismic_check import render_seismic_check

FRAMEWEB = json.dumps({"dimension": 2, "load": {"1": {}}, "node": {"1": {}, "2": {}},
                       "fix_node": {"1": [{"n": "2"}]}, "pickup": {"1": {"C1": 1, "C2": 2}}}).encode()
PICKUPS = (("pik", "frame.pik"), ("displacement", "frame_変位量.csv"), ("reaction", "frame_反力.csv"))
NDU = b"Virsion=5.2.3.S.4\r\n"
FOLDER = "model_JRSNAP"
# The items of the fake stages (decision 72): F, the footing, uses the items of D and E (and of both directions).
OUTPUTS = {"ground_model": ("A",), "longitudinal": ("B",), "longitudinal_frame_analysis": ("D",),
           "longitudinal_seismic": ("C",), "longitudinal_nonlinear_analysis": ("E",), "footing": ("F",)}
FOOTING = tuple(key for key in OUTPUT_KEYS if key != "cantilever")  # footing with every item it uses
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
        StageSpec("D", "D_照査", ("B",), frame_analysis=FrameAnalysis("B", "frameweb", PICKUPS)),
        StageSpec("C", "C_地震", ("A",), recorder.calculate("C"), recorder.render("C"),
                  (Export("jrsnap", "model.ndu", recorder.export("C", NDU)),)),
        StageSpec("E", "E_解析", ("C",), render=lambda results, pier, path, pages: render_seismic_check(path, pages),
                  nonlinear_analysis=NonlinearAnalysis(
                      "C", "jrsnap", "jrsnap", FOLDER,
                      Project("aggrese", "model.xml", lambda results, pier: project, {"target": "Aggre-SE"})),
                  seismic_check=SeismicCheck(FILES)),
        StageSpec("F", "F_フーチング", ("A", "B", "D", "E"), recorder.calculate("F"), recorder.render("F"),
                  complete=finish_f),
    ), outputs=OUTPUTS)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    for module in (fempython, jrsnap, aggrese):
        monkeypatch.setattr(module, "ENV_FILE", tmp_path / ".env")
    recorder = Recorder()
    options = GenerationOptions(copy_input(tmp_path / "pre", *FOOTING), tmp_path / "output", tmp_path / "post")
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


@pytest.mark.parametrize("analyses,expected", [
    ((), ("A", "B", "C")), (("longitudinal_frame_analysis",), ("A", "B", "D", "C")),
    (("longitudinal_nonlinear_analysis",), ("A", "B", "C", "E")),
])
def test_the_stage_is_made_only_when_the_input_chooses_its_item(env, analyses, expected):
    options, recorder = env
    choose(Path(options.input_path), *SEISMIC, *analyses)
    assert generate.generate(options, registry=registry(recorder)).stages == expected


def test_the_footing_is_chosen_only_with_a_whole_group_of_analyses(env):
    """Decision 110: footing uses the frame analyses of both directions or their static nonlinear analyses."""
    options, recorder = env
    choose(Path(options.input_path), *SEISMIC, "longitudinal_frame_analysis", "longitudinal_nonlinear_analysis",
           "footing")
    with pytest.raises(InputError, match="outputs.footing: outputs.longitudinal_frame_analysis・"
                                         "outputs.transverse_frame_analysis か、"):
        generate.generate(options, registry=registry(recorder))
    assert recorder.log == [] and not Path(options.output_dir).exists()


@pytest.mark.parametrize("analyses,stages,read", [
    (("transverse", "longitudinal_frame_analysis", "transverse_frame_analysis"), ("A", "B", "D", "C", "F"),
     ("D/displacement", "D/pik", "D/reaction")),
    (("transverse_seismic", "longitudinal_nonlinear_analysis", "transverse_nonlinear_analysis"), ("A", "B", "C", "E", "F"),
     ("E/pik", "E/steps", "E/xlsx")),
])
def test_a_footing_of_one_part_reads_that_part_alone(env, analyses, stages, read):
    """Decision 110: the stage of the part made replaces F (Registry.for_input) and reads only its analysis."""
    options, recorder = env
    full = registry(recorder, lambda result, files, pier, results: Finished(tuple(sorted(files)), ""))
    f = full.get("F")
    parts = {"frames": replace(f, depends_on=("A", "B", "D")), "seismic": replace(f, depends_on=("A", "C", "E"))}
    stages_with_parts = replace(full, stages=tuple(replace(stage, parts=parts) if stage.id == "F" else stage
                                                   for stage in full.stages))
    choose(Path(options.input_path), *SEISMIC, *analyses, "footing")
    generation = generate.generate(options, registry=stages_with_parts)
    assert generation.stages == stages and generation.results["F"].read == read


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
    source = choose(footing_input(root / "pre"), *OUTPUT_KEYS)
    options = GenerationOptions(source, root / "output", root / "post")
    return root, options, generate.generate(options)


def test_every_item_adds_the_footing_stages_with_their_reports_and_wdjs(footing_generation):
    """Decision 60 with the real registry: 0800 reads the reactions of 0612・0622 and the step tables of 0711・0721
    (the 地震時 column is the Case with the largest |M|: the stand-in adds 100 kN m per Case), 0810・0820 publish the
    WDJ WebPier wrote and record the check as not evaluated; 0800 has no engineering status of its own."""
    root, options, generation = footing_generation
    assert generation.stages == STAGES.ids and planned(options, generation.stages) == generation.artifacts
    output, post = tree(root / "output"), tree(root / "post")
    for stem in ("0800_フーチング", "0810_線路方向フーチング照査", "0820_直角方向フーチング照査"):
        assert output[f"{stem}.pdf"].startswith(b"%PDF-")
    result = load_json(output["0800_フーチング.json"])
    assert "section_check" not in result and "engineering_status" not in result["result"]
    # The stand-in's M grows with the Case index; decision 76 takes the largest of the αf 1.0 Cases: along the track
    # Case2 (ρm 1.2), across it Case6 (the down track, ρm 1.2), not the αf 2.0 ones after them.
    for direction, case_index in (("longitudinal", 1), ("transverse", 5)):
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


def test_the_footing_without_the_cantilever_makes_every_other_stage(tmp_path):
    """Decision 72: footing chosen with every item it uses publishes the stages of those items with 0800〜0820 (the
    frame analyses of 0612・0622, the seismic checks of 0711・0721), and nothing of 0900・0910."""
    source = choose(footing_input(tmp_path / "pre"), *FOOTING)
    options = GenerationOptions(source, tmp_path / "output", tmp_path / "post")
    generation = generate.generate(options)
    assert generation.stages == tuple(stage for stage in STAGES.ids if stage not in ("0900", "0910"))
    output, post = tree(tmp_path / "output"), tree(tmp_path / "post")
    assert sorted(name for name in output if name.endswith(".pdf")) == sorted(
        f"{STAGES.get(stage).stem}.pdf" for stage in generation.stages)
    for name in ("線路方向_ピックアップ反力.csv", "線路直角方向_Aggre-SE_直接基礎.csv", "線路方向フーチング.wdj", "線路方向.xml",
                 "線路直角方向フーチング.wdj"):
        assert name in post, name
    assert "片持ち梁.wdj" not in post
    assert planned(options, generation.stages) == generation.artifacts


SEISMIC_FOOTING = ("ground_model", "reactions", "longitudinal_seismic", "longitudinal_nonlinear_analysis",
                   "transverse_seismic", "transverse_nonlinear_analysis", "footing")
FRAMES_FOOTING = ("ground_model", "reactions", "longitudinal", "longitudinal_frame_analysis", "transverse",
                  "transverse_frame_analysis", "footing")


@pytest.mark.parametrize("items,stages,columns,frames", [
    (SEISMIC_FOOTING, ("0500", "0600", "0710", "0711", "0720", "0721", "0800", "0810", "0820"), ["seismic"], False),
    (FRAMES_FOOTING, ("0500", "0600", "0610", "0611", "0612", "0620", "0621", "0622", "0800", "0810", "0820"),
     ["safety_moment", "safety_shear", "short_term", "long_term"], True),
])
def test_a_footing_of_one_part_is_made_without_the_other_analyses(tmp_path, items, stages, columns, frames):
    """Decision 110 with the real registry: the footing of the analyses chosen, the other analyses not calculated; the
    files are those planned."""
    source = choose(footing_input(tmp_path / "pre"), *items)
    options = GenerationOptions(source, tmp_path / "output", tmp_path / "post")
    generation = generate.generate(options)
    assert generation.stages == stages and planned(options, generation.stages) == generation.artifacts
    output = tree(tmp_path / "output")
    result = load_json(output["0800_フーチング.json"])["result"]
    for direction in ("longitudinal", "transverse"):
        assert [column["key"] for column in result[direction]["columns"]] == columns
    for stage in ("0810", "0820"):
        check = load_json(output[f"{STAGES.get(stage).stem}.json"])
        assert check["section_check"]["skipped_sections"] == []
        assert (check["result"]["safety"] is not None, check["result"]["seismic"] is not None) == (frames, not frames)
