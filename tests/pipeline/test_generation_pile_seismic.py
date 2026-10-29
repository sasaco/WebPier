"""0710 of a pile foundation (decision 93): the frame on the piles, the NDU of the piles for JRSNAP and the figures JRSNAP draws of it.
The runners are the stand-ins of tests/fixtures (the SOIL-JR stand-in returns the 5.2 sample E's .sdc, the input is
tests/fixtures/inputs/pile.json with the reinforcement of a pile)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from pipeline_support import FIXTURES, tree
from webpier.core.errors import InputError
from webpier.core.integrity import load_json
from webpier.inputs import parse_input
from webpier.pipeline import generate
from webpier.pipeline.generate import GenerationOptions

PILE = json.loads((FIXTURES / "inputs" / "pile.json").read_text(encoding="utf-8"))
CAST = {"鉄筋/杭/materials": {"main": "SD345", "transverse": "SD345"}, "鉄筋/杭/pure_cover_mm": 100.0,
        "鉄筋/杭/aggregate_max_mm": 25.0, "鉄筋/杭/main_bars": {"diameter_mm": 32, "count": 20},
        "鉄筋/杭/hoops/zone_2d": {"diameter_mm": 16, "sets": 1, "pitch_mm": 200.0}}
ITEMS = ("ground_model", "reactions", "longitudinal_seismic")


def write(directory: Path, **changes) -> Path:
    data = deepcopy(PILE)
    data["outputs"] = {key: key in ITEMS for key in data["outputs"]}
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[part]
        node[key] = deepcopy(value)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "input.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    root = tmp_path_factory.mktemp("pile-seismic")
    return root, generate.generate(GenerationOptions(write(root / "pre", **CAST), root / "output", root / "post"))


def test_a_cast_in_place_pile_foundation_makes_0710(made):
    root, generation = made
    assert generation.stages == ("0500", "0600", "0710")
    assert "0710_線路方向荷重.pdf" in set(tree(root / "output"))
    assert "線路方向.ndu" in {name for name in tree(root / "post") if "provenance" not in name}


def test_the_ndu_is_the_one_of_the_piles(made):
    root, _ = made
    text = (root / "post" / "線路方向.ndu").read_bytes().decode("cp932")
    lines = dict(line.split("=", 1) for line in text.split("\r\n") if "=" in line)
    assert lines["KGNum"] == "3" and lines["SuppotNum"] == lines["SuppotRow"] and lines["FootRow"] == "0"
    assert lines["SRenkeiNum" if "SRenkeiNum" in lines else "FootRow"] == "0"
    assert [lines[f"MemberKUI{n}"] for n in (11, 12, 13)] == ["1", "1", "1"]


def test_a_steel_pile_foundation_may_choose_0710_and_0720():
    """Decision 122 (P10a): the NDU of a 鋼管ソイルセメント杭 has its joint and its pipe."""
    for chosen in (ITEMS, ("ground_model", "reactions", "transverse_seismic")):
        data = deepcopy(PILE)
        data["下部構造"]["基礎形式"] = "鋼管ソイルセメント杭"
        data["outputs"] = {key: key in chosen for key in data["outputs"]}
        assert parse_input(data).outputs


def test_0720_has_a_second_ndu_for_the_reversed_combinations(tmp_path):
    data = deepcopy(PILE)
    data["outputs"] = {key: key in ("ground_model", "reactions", "transverse_seismic") for key in data["outputs"]}
    for path, value in CAST.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[part]
        node[key] = deepcopy(value)
    (tmp_path / "pre").mkdir()
    (tmp_path / "pre" / "input.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    generation = generate.generate(GenerationOptions(tmp_path / "pre" / "input.json", tmp_path / "output", tmp_path / "post"))
    assert generation.stages == ("0500", "0600", "0720")
    post = {name for name in tree(tmp_path / "post") if "provenance" not in name}
    assert {"線路直角方向.ndu", "線路直角方向_逆向.ndu"} <= post
    forward = (tmp_path / "post" / "線路直角方向.ndu").read_bytes().decode("cp932")
    reverse = (tmp_path / "post" / "線路直角方向_逆向.ndu").read_bytes().decode("cp932")
    forward_lines, reverse_lines = (dict(line.split("=", 1) for line in text.split("\r\n") if "=" in line)
                                    for text in (forward, reverse))
    assert forward_lines["SNAPConbNum"] == reverse_lines["SNAPConbNum"] == "4"
    assert {line.split(",")[2] for key, line in forward_lines.items() if key.startswith("SNAPConb") and key[8:].isdigit()} == {"0"}
    assert {line.split(",")[2] for key, line in reverse_lines.items() if key.startswith("SNAPConb") and key[8:].isdigit()} == {"1"}
    assert any(forward_lines[key] != reverse_lines[key] for key in forward_lines if key.startswith("JibanShogenInfo"))  # the columns of the .sdc go the other way
    provenance = json.loads((tmp_path / "post" / "線路直角方向.ndu.provenance.json").read_text(encoding="utf-8"))
    assert provenance["jrsnap_figures"]["also"][0]["export"] == "jrsnapreverse"
