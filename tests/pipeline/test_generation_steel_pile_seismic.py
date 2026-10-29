"""0710 and 0711 of a 鋼管ソイルセメント杭 (decision 122): the NDU has the joint (501) and the pipe (8, 鋼管杭) of the piles, JRSNAP
analyzes it, Aggre-SE checks the piles, and the report has no page of 杭頭反力の最大値から定める最小鉄筋量 (a 場所打ち杭's,
decision 98). The runners are the stand-ins of tests/fixtures (the input is tests/fixtures/inputs/pile.json made a 鋼管ソイルセメント杭
with the pipe and the joint of Example橋脚4; the SOIL-JR stand-in returns the .sdc of the sample E)."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest

from pipeline_support import FIXTURES, tree
from webpier.calc.detailing.steel_pile import JointAxial, steel_pile_detailing, with_joint_forces
from webpier.core.errors import InputError
from webpier.core.integrity import load_json
from webpier.core.printed import Printed
from webpier.export.drawing import drawing_dxf
from webpier.inputs import parse_input
from webpier.pipeline import generate
from webpier.pipeline.generate import GenerationOptions, export_bytes, planned
from webpier.pipeline.stages import STAGES

PILE = json.loads((FIXTURES / "inputs" / "pile.json").read_text(encoding="utf-8"))
STEEL = {"ソイルセメント径": 1.0, "鋼管外径": 0.8, "鋼管厚": 18.0, "腐食代": 1.0, "鋼管材質": "SKK490",
         "結合部": {"軸方向鉄筋": {"径": 38, "本数": 16, "材質": "SD390", "重心位置": 75.0}, "中詰めコンクリート_f'ck": 27.0,
                  "粗骨材の最大寸法": 25}}
ITEMS = ("ground_model", "reactions", "longitudinal_seismic", "longitudinal_nonlinear_analysis")


def write(directory: Path, items: tuple[str, ...] = ITEMS) -> Path:
    data = deepcopy(PILE)
    data["下部構造"]["基礎形式"] = "鋼管ソイルセメント杭"
    data["杭基礎"]["鋼管ソイルセメント杭"] = deepcopy(STEEL)
    data["outputs"] = {key: key in items for key in data["outputs"]}
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "input.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    root = tmp_path_factory.mktemp("steel-0711")
    return root, generate.generate(GenerationOptions(write(root / "pre"), root / "output", root / "post"))


def test_a_steel_pile_foundation_makes_0710_and_0711(made):
    root, generation = made
    assert generation.stages == ("0500", "0600", "0710", "0711")
    post = {name for name in tree(root / "post") if "provenance" not in name}
    assert {"線路方向.ndu", "線路方向.xml", "線路方向_Aggre-SE.pik", "線路方向_Aggre-SE.xlsx"} <= post
    assert (root / "output" / "0711_線路方向非線形解析.pdf").is_file()


def test_the_ndu_has_the_joint_and_the_pipe(made):
    root, _ = made
    text = (root / "post" / "線路方向.ndu").read_bytes().decode("cp932")
    lines = dict(line.split("=", 1) for line in text.split("\r\n") if "=" in line)
    assert lines["SectNum"] == "3"
    assert lines["SectInfo2"] == "1,501,0,1,400,17,0,0,0,0,-3.402823E+38,0,0,0"
    assert lines["SectInfo3"] == "1,8,1,1,798,17,0,0,0,0,-3.402823E+38,0,0,0"


def test_the_report_of_0711_has_no_minimum_bars_of_a_cast_in_place_pile(made):
    root, _ = made
    with pymupdf.open(root / "output" / "0711_線路方向非線形解析.pdf") as document:
        text = "".join(page.get_text() for page in document)
    assert "最小鉄筋量" not in text
    document = load_json((root / "output" / "0711_線路方向非線形解析.json").read_bytes())
    assert document["seismic_check"]["engine"] == "aggrese"


# --- 0400 of a 鋼管ソイルセメント杭 (decision 123): the ずれ止め by the axial forces of the piles of 0711 and 0721 -----------
#
# By hand from the stand-in's pickup (tests/fixtures/aggrese/fake_runner.py: pickup 2 the largest N 500 + 10m, pickup 1 the
# smallest N −(20000 + 100m), the bundle of the element m) at the head elements of the NDUs' KGInfo (線路方向 11, 38, 65 with
# 3, 2, 3 piles in the depth; 線路直角方向 12, 39, 66, the same in its NDU of the reversed push):
# - Nd: 線路方向 610／3, 880／2 = 440, 1150／3; 線路直角方向 620／3, 890／2 = 445.00, 1160／3 → 445.00 kN (線路直角方向);
# - Np: 線路方向 21100／3, 23800／2 = 11900, 26500／3; 線路直角方向 21200／3, 23900／2 = 11950.00, 26600／3 → 11950.00 kN;
# - at n = 2 (Ld 500) 11950000／(π × 766 × 500 × 8.06 ＋ 918436) = 11950000／10616469.7 = 1.126 > 1.00, at n = 3 (Ld 750)
#   11950000／(14547050.5 ＋ 918436) = 0.773 → 0.77 and 445000／14547050.5 = 0.0306 → 0.03: three steps (the most is 5).
SEISMIC = ("detailing", "ground_model", "reactions", "longitudinal_seismic", "longitudinal_nonlinear_analysis",
           "transverse_seismic", "transverse_nonlinear_analysis")


@pytest.fixture(scope="module")
def detailed(tmp_path_factory):
    root = tmp_path_factory.mktemp("steel-0400")
    options = GenerationOptions(write(root / "pre", SEISMIC), root / "output", root / "post", export_dir=root / "export")
    return root, options, generate.generate(options)


def test_0400_of_a_steel_pile_comes_after_the_seismic_checks(detailed):
    root, options, generation = detailed
    assert generation.stages == ("0500", "0600", "0710", "0711", "0720", "0721", "0400")
    pier = parse_input(load_json((root / "pre" / "input.json").read_bytes()))
    assert planned(options, generation.stages, pier=pier) == generation.artifacts
    for name in ("0400_照査の前提.pdf", "0400_照査の前提.json"):
        assert (root / "output" / name).is_file()
    assert (root / "export" / "0400_照査の前提.xlsx").is_file()


def test_0400_takes_nd_and_np_of_both_directions(detailed):
    root, _, _ = detailed
    result = load_json((root / "output" / "0400_照査の前提.json").read_bytes())["result"]
    joint = result["steel_pile"]["joint"]
    bond = joint["bond"]
    assert (bond["tension"], bond["compression"]) == ({"value": 445.0, "direction": "線路直角方向"},
                                                      {"value": 11950.0, "direction": "線路直角方向"})
    assert (bond["tension_n"], bond["compression_n"]) == (445000, 11950000)
    assert (bond["steps"], bond["length"], bond["tension_ratio"], bond["compression_ratio"], bond["most"]) == (
        3, 750, 0.03, 0.77, 5)
    assert (joint["ribs"]["steps"], joint["ribs"]["bottom"]) == (3, 850)  # 1550 − (200 ＋ 2 × 250)
    # the rest of its 杭の構造細目 is the input's (decision 99): D 1000, so lc = max(1500, 1522) → 1550
    assert result["pile"] is None and joint["filling"]["length"] == 1550
    # (its status is every check's: the column and the beam of pile.json are not all ok, which the bond does not change)


def test_the_dxf_of_0400_has_the_finished_steps(detailed):
    root, _, _ = detailed
    pier = parse_input(load_json((root / "pre" / "input.json").read_bytes()))
    alone = steel_pile_detailing(pier)
    finished = with_joint_forces(alone, JointAxial(Printed(445.0, 2, "kN"), "線路直角方向"),
                                 JointAxial(Printed(11950.0, 2, "kN"), "線路直角方向"))
    assert finished.joint.ribs.steps == 3
    data = (root / "post" / "配筋図.dxf").read_bytes()
    assert data == drawing_dxf(pier, finished) and data != drawing_dxf(pier, alone)
    assert "杭（杭頭の結合部・断面と杭先端部）".encode("utf-8") in data
    sidecar = load_json((root / "post" / "配筋図.dxf.provenance.json").read_bytes())
    assert sidecar["stage"] == "0400" and sidecar["sha256"] == hashlib.sha256(data).hexdigest()


def test_its_dxf_is_made_only_by_a_generation(detailed):
    root, _, _ = detailed
    pier = parse_input(load_json((root / "pre" / "input.json").read_bytes()))
    with pytest.raises(InputError, match="0400の「dxf」は、0711・0721の結果で0400を仕上げてから作るので、生成のときだけ作れます"):
        export_bytes(pier, "0400", "dxf")


def test_validating_a_steel_pile_0400_needs_no_runner(detailed):
    root, options, _ = detailed
    assert generate.validate(options) == ("0500", "0600", "0710", "0711", "0720", "0721", "0400")


def test_0400_of_a_steel_pile_alone_is_an_input_error(tmp_path):
    with pytest.raises(InputError, match="outputs.detailing: outputs.longitudinal_nonlinear_analysis・"
                                         "outputs.transverse_nonlinear_analysis も true が必要です"):
        generate.generate(GenerationOptions(write(tmp_path / "pre", ("detailing", "reactions")), tmp_path / "output",
                                            tmp_path / "post"))


def test_only_the_steel_pile_moves_0400():
    """The 鋼管ソイルセメント杭's 0400 reads 0711 and 0721, so it is registered after 0721; the direct foundation's and the
    場所打ち杭's keep their order (decision 98: 0500 → 0400 → 0600)."""
    order = ("0500", "0400", "0600", "0610", "0611", "0612", "0620", "0621", "0622", "0710", "0711", "0720", "0721",
             "0800", "0810", "0820", "0900", "0910")
    assert STAGES.ids == STAGES.for_foundation("場所打ち杭").ids == order
    steel = STAGES.for_foundation("鋼管ソイルセメント杭")
    assert steel.ids == (*order[:1], *order[2:13], "0400", *order[13:])
    assert steel.get("0400").depends_on == ("0711", "0721")
    assert [item.kind for item in steel.finished("0400")] == ["dxf"]
    assert STAGES.for_foundation("場所打ち杭").finished("0400") == () == STAGES.finished("0400")
    assert STAGES.for_foundation("場所打ち杭").finished("0500") == ()  # SOIL-JR's .sdt is read by the runner
