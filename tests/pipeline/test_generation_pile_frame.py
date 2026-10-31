"""0610 and 0620 of a pile foundation (decision 88): the frame stands on the springs SOIL-JR returns, so it is calculated and its
FrameWeb file built only once 0500 is complete; FEMPython then draws its load diagram. The runners are the stand-ins of
tests/fixtures (the .sdc of the SOIL-JR stand-in is the 5.2 sample's, which is the input of tests/fixtures/inputs/pile.json)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest

from pipeline_support import FIXTURES, tree
from webpier.core.errors import InputError
from webpier.core.integrity import load_json
from webpier.inputs import outputs, parse, parse_input
from webpier.pipeline import generate
from webpier.pipeline.generate import GenerationOptions, export_bytes, planned, validate
from webpier.pipeline.stages import STAGES, Registry, StageSpec

PILE = json.loads((FIXTURES / "inputs" / "pile.json").read_text(encoding="utf-8"))
ITEMS = ("ground_model", "reactions", "longitudinal", "transverse")


def write(directory: Path, **changes) -> Path:
    """pile.json choosing the items of 0610 and 0620, with each 'a/b/0/c' path replaced by its value."""
    data = deepcopy(PILE)
    data["outputs"] = {key: key in ITEMS for key in data["outputs"]}
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "input.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})


def options(root: Path, **changes) -> GenerationOptions:
    return GenerationOptions(write(root / "pre", **changes), root / "output", root / "post")


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    root = tmp_path_factory.mktemp("pile-frame")
    return root, generate.generate(options(root))


def text(pdf: bytes) -> str:
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        return "".join(page.get_text() for page in document)


def test_a_pile_foundation_makes_the_frames_after_the_ground(made):
    root, generation = made
    assert generation.stages == ("0500", "0600", "0610", "0620")
    assert sorted(tree(root / "output")) == [
        "0500_杭基礎.json", "0500_杭基礎.pdf", "0600_上部工反力.json", "0600_上部工反力.pdf",
        "0610_線路方向荷重.json", "0610_線路方向荷重.pdf", "0620_直角方向荷重.json", "0620_直角方向荷重.pdf"]
    post = {name for name in tree(root / "post") if "provenance" not in name}
    assert post == {"杭基礎.sdt", "杭基礎.sdr", "杭基礎.sdc", "線路方向.json", "線路直角方向.json"}


def test_the_frameweb_file_is_the_one_built_from_the_springs_of_the_sdc(made):
    root, generation = made
    document = load_json((root / "post" / "線路方向.json").read_bytes())
    assert sorted(document["fix_member"]) == ["1", "2"] and sorted(document["fix_node"]) == ["1", "2"]
    first = document["fix_member"]["1"][0]
    assert (first["length"], first["ty"], first["tx"]) == (2.6, 18959, 13464)  # layer 1, row 1 of the sample's .sdc
    assert {case["fix_member"] for case in document["load"].values()} == {1, 2}


def test_the_report_has_the_pile_rows_and_their_springs(made):
    root, generation = made
    report = text((root / "output" / "0610_線路方向荷重.pdf").read_bytes())
    for words in ("杭列（橋軸方向）", "杭周面の地盤ばね（杭頭から）", "杭先端の地盤ばね", "杭先端（ばね）", "杭頭",
                  "杭（円形断面，全長で同じ断面）"):
        assert words in report
    assert "フーチング底面のばね" not in report
    assert "杭列（直角方向）" in text((root / "output" / "0620_直角方向荷重.pdf").read_bytes())


def test_the_result_holds_the_frame_on_the_piles(made):
    root, generation = made
    result = load_json((root / "output" / "0610_線路方向荷重.json").read_bytes())["result"]
    frame = result["frame"]
    assert frame["support"] is None and len(frame["pile_nodes"]) == 3
    assert [row["row"]["piles"] for row in frame["pile_nodes"]] == [3, 2, 3]


def test_a_generation_calculates_the_late_stages_after_the_ground_is_complete(monkeypatch, tmp_path):
    order: list[str] = []
    real = {stage_id: STAGES.get(stage_id) for stage_id in ("0500", "0610")}
    from webpier.pipeline import soiljr

    complete = soiljr.complete

    def completing(*arguments):
        order.append("0500 complete")
        return complete(*arguments)

    monkeypatch.setattr(soiljr, "complete", completing)
    from webpier.pipeline import stages

    original = stages._pile_foundation

    def foundation(results):
        order.append("0610 calculate")
        assert type(results["0500"]).__name__ == "PileGroundModel"  # the springs are there
        return original(results)

    monkeypatch.setattr(stages, "_pile_foundation", foundation)
    registry = Registry(tuple(
        (StageSpec(**{**vars(stage), "complete": completing}) if stage.id == "0500" and stage.complete else stage)
        for stage in STAGES.for_foundation("場所打ち杭").stages), foundation="場所打ち杭")
    generate.generate(options(tmp_path), registry=registry)
    assert order[:2] == ["0500 complete", "0610 calculate"] and real["0610"].after == ()


def test_the_input_is_checked_without_a_runner_as_far_as_it_is_decided_before_it(tmp_path):
    assert validate(options(tmp_path)) == ("0500", "0600", "0610", "0620")  # the frames wait for SOIL-JR's springs
    assert planned(options(tmp_path), ("0610",), pier=parse_input(load_json(write(tmp_path / "x").read_bytes())))


def test_a_file_of_a_stage_that_waits_cannot_be_built_without_the_runner(tmp_path):
    pier = parse_input(load_json(write(tmp_path).read_bytes()))
    with pytest.raises(InputError, match="0610の「frameweb」は、0500の SOIL-JR の結果から作るので、生成のときだけ作れます"):
        export_bytes(pier, "0610", "frameweb")


@pytest.mark.parametrize("change, message", [
    ({"杭基礎/杭長": 20.0}, "層厚の合計"),
    ({"杭基礎/配置/線路方向の列の位置": [-3.0, 3.0]}, "杭列数（3）が入力の杭の列（2列）と違います"),
])
def test_springs_that_do_not_match_the_input_stop_the_generation(tmp_path, change, message):
    with pytest.raises(InputError, match=message):
        generate.generate(options(tmp_path, **change))
    assert not (tmp_path / "output").exists() or not tree(tmp_path / "output")  # nothing is published


def test_a_load_model_has_no_frame_on_piles(tmp_path):
    addin = Path(__file__).parents[1] / "fixtures" / "addin" / "minimal"
    with pytest.raises(InputError, match="荷重モデル（--addin）の0610は、場所打ち杭では計算できません"):
        generate.generate(GenerationOptions(write(tmp_path / "pre"), tmp_path / "output", tmp_path / "post",
                                            addin=addin))


STEEL = {"ソイルセメント径": 1.0, "鋼管外径": 0.8, "鋼管厚": 18.0, "腐食代": 1.0, "鋼管材質": "SKK490",
         "結合部": {"軸方向鉄筋": {"径": 38, "本数": 16, "材質": "SD390", "重心位置": 75.0}, "中詰めコンクリート_f'ck": 27.0,
                  "粗骨材の最大寸法": 25},
         "段落し": {"段落し後の鋼管厚": None, "段落し後の鋼管材質": None, "上杭長": None,
                    "施工余裕長": {"低止まり": None, "高止まり": None}, "継手を設けない範囲_杭頭から": None}}  # (the pipe and the joint of Example橋脚4, as tests/pipeline/test_generation_steel_pile_seismic.py)


@pytest.mark.parametrize("foundation, items, changes", [
    ("場所打ち杭", ("ground_model", "reactions", "longitudinal_seismic"), {}),
    ("鋼管ソイルセメント杭", ("detailing", "ground_model", "reactions", "longitudinal_seismic",
                         "longitudinal_nonlinear_analysis", "transverse_seismic", "transverse_nonlinear_analysis"),
     {"下部構造/基礎形式": "鋼管ソイルセメント杭", "杭基礎/鋼管ソイルセメント杭": STEEL}),
])
def test_a_load_model_has_no_seismic_frame_on_piles(tmp_path, foundation, items, changes):
    """0710 / 0720 of a load model build no NDU of the piles, so the generation stops before anything is published (and
    0711 / 0721, which use 0710 / 0720, and a 鋼管ソイルセメント杭's 0400, which uses 0711 / 0721, decision 123, with it)."""
    addin = Path(__file__).parents[1] / "fixtures" / "addin" / "minimal"
    outputs = {key: key in items for key in PILE["outputs"]}
    with pytest.raises(InputError, match=f"荷重モデル（--addin）の0710は、{foundation}では計算できません"):
        generate.generate(GenerationOptions(write(tmp_path / "pre", outputs=outputs, **changes), tmp_path / "output",
                                            tmp_path / "post", addin=addin))
    assert not (tmp_path / "output").exists() or not tree(tmp_path / "output")  # nothing is published
    assert not (tmp_path / "post").exists() or not tree(tmp_path / "post")


def test_the_stages_that_are_not_made_yet_are_not_items_of_a_pile_foundation(tmp_path, monkeypatch):
    # since decision 125 a pile foundation makes every item: one it could not (0900 before it) is taken out of the table
    made = tuple(key for key in outputs.PILE_OUTPUT_KEYS if key != "cantilever")
    monkeypatch.setattr(outputs, "PILE_OUTPUT_KEYS", made)
    monkeypatch.setattr(parse, "PILE_OUTPUT_KEYS", made)
    data = deepcopy(PILE)
    chosen = (*ITEMS, "longitudinal_seismic", "transverse_seismic", "longitudinal_nonlinear_analysis",
              "transverse_nonlinear_analysis", "cantilever")
    data["outputs"] = {key: key in chosen for key in data["outputs"]}
    with pytest.raises(InputError, match="場所打ち杭は未対応です"):
        parse_input(data)
