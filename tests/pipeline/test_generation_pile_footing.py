"""0800, 0810 and 0820 of a pile foundation (decision 96): the section forces of the footing from the PIK of the frame analyses and the
pickup of Aggre-SE, and Capacita's check of the six points. The runners are the stand-ins of tests/fixtures: the PIK has, at an end of a
base member, a sagging moment 1000 + 100 × the pickup + the member (kN m) and a hogging one −(50 + pickup + member); the pickup of
Aggre-SE 2000 + the element and −(80 + element) (tests/fixtures/fempython/fake_runner.py, aggrese/fake_runner.py)."""

import json
from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest

from pipeline_support import FIXTURES, tree
from webpier.core.integrity import load_json
from webpier.pipeline import generate
from webpier.pipeline.generate import GenerationOptions

PILE = json.loads((FIXTURES / "inputs" / "pile_seismic.json").read_text(encoding="utf-8"))
ITEMS = ("ground_model", "reactions", "longitudinal", "longitudinal_frame_analysis", "transverse", "transverse_frame_analysis",
         "longitudinal_seismic", "longitudinal_nonlinear_analysis", "transverse_seismic", "transverse_nonlinear_analysis",
         "footing")


def write(directory: Path, items=ITEMS, **changes) -> Path:
    data = deepcopy(PILE)
    data["outputs"] = {key: key in items for key in data["outputs"]}
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = deepcopy(value)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "input.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    root = tmp_path_factory.mktemp("pile-footing")
    return root, generate.generate(GenerationOptions(write(root / "pre"), root / "output", root / "post"))


def pdf_text(path: Path) -> str:
    with pymupdf.open(path) as document:
        return "".join(page.get_text() for page in document)


def test_a_cast_in_place_pile_foundation_makes_the_footing_after_the_checks_it_reads(made):
    root, generation = made
    assert {"0800", "0810", "0820"} <= set(generation.stages)
    assert generation.stages.index("0800") > generation.stages.index("0721") and generation.stages[-3:] == ("0800", "0810", "0820")
    names = set(tree(root / "output"))
    assert {"0800_フーチング.pdf", "0810_線路方向フーチング照査.pdf", "0820_直角方向フーチング照査.pdf"} <= names
    post = {name for name in tree(root / "post") if "provenance" not in name}
    assert {"線路方向フーチング.wdj", "線路直角方向フーチング.wdj"} <= post


def test_the_section_forces_are_those_of_the_ends_of_the_base_members(made):
    root, _ = made
    result = load_json((root / "output" / "0800_フーチング.json").read_bytes())["result"]["longitudinal"]
    points = {point["point"]["key"]: point for point in result["points"]}
    face = points["face_lower"]["forces"]
    safety = next(force for force in face if force["case"] == "安全性（破壊）")
    # the right member (the larger number) has the larger sagging moment: 1000 + 100 × pickup + member
    members = [end["member"] for end in points["face_lower"]["point"]["ends"]]
    assert safety["end"]["member"] == max(members)
    # the 安全性（破壊） times the 応答値係数 γR 1.2 (decision 104)
    assert safety["md"] == round(1.2 * (1000.0 + 100.0 * safety["pickup"] + max(members)), 1)
    seismic = next(force for force in face if force["case"] == "復旧性（地震時）")
    assert seismic["pickup"] == 2 and seismic["md"] > 2000.0  # 2000 + the element of the NDU
    upper = next(force for force in points["face_upper"]["forces"] if force["case"] == "安全性（破壊）")
    assert upper["md"] < 0  # the smallest moment of the PIK: −(50 + pickup + member)
    deep = next(force for force in points["pile_shear"]["forces"] if force["case"] == "安全性（破壊）")
    assert deep["vd"] > 0 and deep["vd_combination"] is not None


def test_capacita_checks_the_six_points_with_the_deep_beam_sections(made):
    root, _ = made
    wdj = json.loads((root / "post" / "線路方向フーチング.wdj").read_bytes().decode("utf-8"))
    assert [point["p_name"] for point in wdj["points"]] == ["く体前面（下側引張）", "く体前面（上側引張）", "杭位置（下側引張）",
                                                            "杭位置（上側引張）", "く体前面（下側引張）", "杭位置（上側引張）"]
    assert [row["index"] for row in wdj["shear"] if "deep_beam" in row] == [5, 6]
    report = pdf_text(root / "output" / "0810_線路方向フーチング照査.pdf")
    # the deep beam shear of 安全性（破壊） and 復旧性（地震時） (decision 124), not the ordinary shear
    for section in ("bending_safety_destruction", "shear_deep_beam_safety_destruction", "bending_durability",
                    "bending_restorability_eq", "shear_deep_beam_restorability_eq", "bending_rebar_amount"):
        assert f"FAKE CAPACITA {section}" in report
    assert "FAKE CAPACITA shear_safety_destruction" not in report and "FAKE CAPACITA shear_restorability_eq" not in report
    assert report.count("2) せん断力に対する照査") == 2 and "12.2 安全性の照査" in report
    assert "設計引抜せん断耐力Vsdを設計限界値として" in "".join(report.split())  # the sentence of the sample V-138
    force = {row["index"]: row for row in wdj["force"]}
    assert all(f"Vd{case}_Vd" in force[index] for index in (5, 6) for case in (5, 7))
    assert "12.6 安全性の照査" in pdf_text(root / "output" / "0820_直角方向フーチング照査.pdf")


def test_0800_prints_the_widths_and_the_forces_of_each_point(made):
    root, _ = made
    report = pdf_text(root / "output" / "0800_フーチング.pdf")
    assert "(1) 線路方向の計算" in report and "(2) 線路直角方向の計算" in report
    assert "有効幅" in report and "設計断面力" in report and "く体前面（上側引張）" in report and "杭位置（上側引張）" in report


def test_a_steel_pile_foundation_makes_the_footing_with_the_soil_cement_diameter(tmp_path):
    """Decision 124: a 鋼管ソイルセメント杭 makes 0800〜0820 as a 場所打ち杭, with its ソイルセメント径 as D (here 1.2 m, the pipe 0.8 m)."""
    steel = {"ソイルセメント径": 1.2, "鋼管外径": 0.8, "鋼管厚": 18.0, "腐食代": 1.0, "鋼管材質": "SKK490",
             "結合部": {"軸方向鉄筋": {"径": 38, "本数": 16, "材質": "SD390", "重心位置": 75.0}, "中詰めコンクリート_f'ck": 27.0,
                      "粗骨材の最大寸法": 25},
             "段落し": {"段落し後の鋼管厚": None, "段落し後の鋼管材質": None, "上杭長": None,
                        "施工余裕長": {"低止まり": None, "高止まり": None}, "継手を設けない範囲_杭頭から": None}}
    path = write(tmp_path / "pre", **{"下部構造/基礎形式": "鋼管ソイルセメント杭", "杭基礎/鋼管ソイルセメント杭": steel})
    generation = generate.generate(GenerationOptions(path, tmp_path / "output", tmp_path / "post"))
    assert generation.stages[-3:] == ("0800", "0810", "0820")
    result = load_json((tmp_path / "output" / "0800_フーチング.json").read_bytes())["result"]
    for direction in ("longitudinal", "transverse"):
        assert {point["point"]["pile_diameter"] for point in result[direction]["points"]} == {1200.0}
    wdj = json.loads((tmp_path / "post" / "線路方向フーチング.wdj").read_bytes().decode("utf-8"))
    assert [row["deep_beam"]["pile_diameter_mm"] for row in wdj["shear"]
            if row.get("deep_beam", {}).get("mode") == "lower_tension"] == [1200]
    assert "FAKE CAPACITA shear_deep_beam_restorability_eq" in pdf_text(tmp_path / "output" / "0820_直角方向フーチング照査.pdf")


@pytest.mark.parametrize("analyses,cases,shear", [
    (("longitudinal_frame_analysis", "transverse_frame_analysis"), ["安全性（破壊）", "耐久性 永久＋変動", "耐久性 永久"], 5),
    (("longitudinal_nonlinear_analysis", "transverse_nonlinear_analysis"), ["復旧性（地震時）"], 7),
])
def test_a_pile_footing_of_one_part_is_made_without_the_other_analyses(tmp_path, analyses, cases, shear):
    """Decision 110: the cases of the part made; the earthquake alone takes the sections from the frame of 0710 / 0720, and
    its points of the deep beam shear have the shear of 復旧性（地震時） (decision 124)."""
    items = ("ground_model", "reactions", "longitudinal", "transverse", "longitudinal_seismic", "transverse_seismic",
             *analyses, "footing")
    generation = generate.generate(GenerationOptions(write(tmp_path / "pre", items), tmp_path / "output", tmp_path / "post"))
    other = "0611" if "nonlinear" in analyses[0] else "0711"
    assert {"0800", "0810", "0820"} <= set(generation.stages) and other not in generation.stages
    result = load_json((tmp_path / "output" / "0800_フーチング.json").read_bytes())["result"]["longitudinal"]
    assert all([force["case"] for force in point["forces"]] == cases for point in result["points"])
    wdj = json.loads((tmp_path / "post" / "線路方向フーチング.wdj").read_bytes().decode("utf-8"))
    assert [point["p_name"] for point in wdj["points"]] == ["く体前面（下側引張）", "く体前面（上側引張）", "杭位置（下側引張）",
                                                            "杭位置（上側引張）", "く体前面（下側引張）", "杭位置（上側引張）"]
    assert [row["index"] for row in wdj["force"] if any(key.startswith("Vd") for key in row)] == [5, 6]
    assert all(f"Vd{shear}_Vd" in row and not any(key.startswith(f"Vd{12 - shear}") for key in row)
               for row in wdj["force"] if row["index"] in (5, 6))
