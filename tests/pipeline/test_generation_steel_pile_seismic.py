"""0710 and 0711 of a 鋼管ソイルセメント杭 (decision 122): the NDU has the joint (501) and the pipe (8, 鋼管杭) of the piles, JRSNAP
analyzes it, Aggre-SE checks the piles, and the report has no page of 杭頭反力の最大値から定める最小鉄筋量 (a 場所打ち杭's,
decision 98). The runners are the stand-ins of tests/fixtures (the input is tests/fixtures/inputs/pile.json made a 鋼管ソイルセメント杭
with the pipe and the joint of Example橋脚4; the SOIL-JR stand-in returns the .sdc of the sample E)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest

from pipeline_support import FIXTURES, tree
from webpier.core.integrity import load_json
from webpier.pipeline import generate
from webpier.pipeline.generate import GenerationOptions

PILE = json.loads((FIXTURES / "inputs" / "pile.json").read_text(encoding="utf-8"))
STEEL = {"ソイルセメント径": 1.0, "鋼管外径": 0.8, "鋼管厚": 18.0, "腐食代": 1.0, "鋼管材質": "SKK490",
         "結合部": {"軸方向鉄筋": {"径": 38, "本数": 16, "材質": "SD390", "重心位置": 75.0}, "中詰めコンクリート_f'ck": 27.0,
                  "粗骨材の最大寸法": 25}}
ITEMS = ("ground_model", "reactions", "longitudinal_seismic", "longitudinal_nonlinear_analysis")


def write(directory: Path) -> Path:
    data = deepcopy(PILE)
    data["下部構造"]["基礎形式"] = "鋼管ソイルセメント杭"
    data["杭基礎"]["鋼管ソイルセメント杭"] = deepcopy(STEEL)
    data["outputs"] = {key: key in ITEMS for key in data["outputs"]}
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
