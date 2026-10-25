"""0800, 0810 and 0820 of a pile foundation (decision 96): the section forces of the footing from the PIK of the frame analyses and the
pickup of Aggre-SE, and Capacita's check of the five points. The runners are the stand-ins of tests/fixtures: the PIK has, at an end of a
base member, a sagging moment 1000 + 100 × the pickup + the member (kN m) and a hogging one −(50 + pickup + member); the pickup of
Aggre-SE 2000 + the element and −(80 + element) (tests/fixtures/fempython/fake_runner.py, aggrese/fake_runner.py)."""

import json
from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest

from pipeline_support import FIXTURES, tree
from webpier.core.errors import InputError
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
    assert safety["md"] == 1000.0 + 100.0 * safety["pickup"] + max(members)
    seismic = next(force for force in face if force["case"] == "復旧性（地震時）")
    assert seismic["pickup"] == 2 and seismic["md"] > 2000.0  # 2000 + the element of the NDU
    upper = next(force for force in points["face_upper"]["forces"] if force["case"] == "安全性（破壊）")
    assert upper["md"] < 0  # the smallest moment of the PIK: −(50 + pickup + member)
    deep = next(force for force in points["pile_upper"]["forces"] if force["case"] == "安全性（破壊）")
    assert deep["vd"] > 0 and deep["vd_combination"] is not None


def test_capacita_checks_the_five_points_with_the_deep_beam_sections(made):
    root, _ = made
    wdj = json.loads((root / "post" / "線路方向フーチング.wdj").read_bytes().decode("utf-8"))
    assert [point["p_name"] for point in wdj["points"]] == ["く体前面（下側引張）", "く体前面（上側引張）", "杭位置（下側引張）",
                                                            "杭位置（上側引張）", "く体前面（下側引張）"]
    assert [row["index"] for row in wdj["shear"] if "deep_beam" in row] == [4, 5]
    report = pdf_text(root / "output" / "0810_線路方向フーチング照査.pdf")
    for section in ("bending_safety_destruction", "shear_deep_beam_safety_destruction", "bending_durability",
                    "bending_restorability_eq", "bending_rebar_amount"):
        assert f"FAKE CAPACITA {section}" in report
    assert "FAKE CAPACITA shear_safety_destruction" not in report
    assert "2) せん断力に対する照査" in report and "12.2 安全性の照査" in report
    assert "12.6 安全性の照査" in pdf_text(root / "output" / "0820_直角方向フーチング照査.pdf")


def test_0800_prints_the_widths_and_the_forces_of_each_point(made):
    root, _ = made
    report = pdf_text(root / "output" / "0800_フーチング.pdf")
    assert "(1) 線路方向の計算" in report and "(2) 線路直角方向の計算" in report
    assert "有効幅" in report and "設計断面力" in report and "く体前面（上側引張）" in report and "杭位置（上側引張）" in report


def test_a_steel_pile_foundation_is_refused_for_the_footing(tmp_path):
    data = deepcopy(PILE)
    data["下部構造"]["基礎形式"] = "鋼管ソイルセメント杭"
    data["outputs"] = {key: key in ITEMS for key in data["outputs"]}
    with pytest.raises(InputError, match="footing"):
        from webpier.inputs import parse_input
        parse_input(data)
