"""0711 and 0721 of a pile foundation (decision 94): JRSNAP analyzes the NDU of the piles (0721: the NDU of the forward push and the
one of the reversed push, into one folder), Aggre-SE checks the piles with one project of all the Cases and the limit values of
SOIL-JR's .sdr, and no step table of the direct foundation is made. The runners are the stand-ins of tests/fixtures (the input is
tests/fixtures/inputs/pile.json with the reinforcement of a pile, as test_generation_pile_seismic has it)."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest

from pipeline_support import FIXTURES, tree
from webpier.core.errors import InputError
from webpier.core.integrity import load_json, sha256
from webpier.inputs import parse_input
from webpier.pipeline import generate
from webpier.pipeline.generate import GenerationOptions

PILE = json.loads((FIXTURES / "inputs" / "pile.json").read_text(encoding="utf-8"))
CAST = {"鉄筋/杭/materials": {"main": "SD345", "transverse": "SD345"}, "鉄筋/杭/pure_cover_mm": 100.0,
        "鉄筋/杭/aggregate_max_mm": 25.0, "鉄筋/杭/main_bars": {"diameter_mm": 32, "count": 20},
        "鉄筋/杭/hoops/zone_2d": {"diameter_mm": 16, "sets": 1, "pitch_mm": 200.0}}
LONGITUDINAL = ("ground_model", "reactions", "longitudinal_seismic", "longitudinal_nonlinear_analysis")
TRANSVERSE = ("ground_model", "reactions", "transverse_seismic", "transverse_nonlinear_analysis")
FORWARD = ["Case1_ρm10_αf1_正向", "Case2_ρm12_αf1_正向", "Case3_ρm10_αf2_正向", "Case4_ρm12_αf2_正向"]
REVERSE = [name.replace("正向", "逆向") for name in FORWARD]


def write(directory: Path, items: tuple[str, ...], **changes) -> Path:
    data = deepcopy(PILE)
    data["outputs"] = {key: key in items for key in data["outputs"]}
    for path, value in {**CAST, **changes}.items():
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


def make(root: Path, items: tuple[str, ...], **changes):
    return generate.generate(GenerationOptions(write(root / "pre", items, **changes), root / "output", root / "post"))


@pytest.fixture(scope="module")
def longitudinal(tmp_path_factory):
    root = tmp_path_factory.mktemp("pile-0711")
    return root, make(root, LONGITUDINAL)


@pytest.fixture(scope="module")
def transverse(tmp_path_factory):
    root = tmp_path_factory.mktemp("pile-0721")
    return root, make(root, TRANSVERSE)


def pdf_text(path: Path) -> str:
    with pymupdf.open(path) as document:
        return "".join(page.get_text() for page in document)


def project(path: Path) -> str:
    return path.read_bytes().decode("cp932")


def database_names(xml: str) -> list[str]:
    block = re.search(r"<SnapDBPath>([\s\S]*?)</SnapDBPath>", xml)[1]
    return [name for name in re.findall(r"<string>([^<]*)</string>", block)]


def scalar(xml: str, tag: str) -> str:
    return re.search(rf"<{tag}>([^<]*)</{tag}>", xml)[1]


def items(xml: str, tag: str) -> list[str]:
    return re.findall(r"<(?:int|float|boolean|string)>([^<]*)</(?:int|float|boolean|string)>",
                      re.search(rf"<{tag}>([\s\S]*?)</{tag}>", xml)[1])


def test_0711_of_piles_has_the_files_of_the_analysis_and_the_check_but_no_step_table(longitudinal):
    root, generation = longitudinal
    assert generation.stages == ("0500", "0600", "0710", "0711")
    post = {name for name in tree(root / "post") if "provenance" not in name}
    assert {"線路方向.ndu", "線路方向.xml", "線路方向_Aggre-SE.pik", "線路方向_Aggre-SE.xlsx"} <= post
    assert not [name for name in post if "直接基礎" in name]
    assert (root / "output" / "0711_線路方向非線形解析.pdf").is_file()
    folder = {path.name for path in (root / "post" / "線路方向_JRSNAP").iterdir()}
    assert {f"線路方向({name}).DB1" for name in FORWARD} <= folder


def test_the_project_of_piles_names_the_piles_and_the_limits_are_left_to_the_runner(longitudinal):
    root, _ = longitudinal
    xml = project(root / "post" / "線路方向.xml")
    assert scalar(xml, "FoundationType") == "0"
    members = items(xml, "_dgLimitLevel_type")
    assert members[0] == "2" and set(members[1:]) == {"4"} and len(members) >= 2  # the column, then each section of the piles
    assert scalar(xml, "dgLimitLevel_typeCount") == str(len(members))
    assert "<string>" not in re.search(r"<dgLimitValue0>([\s\S]*?)</dgLimitValue0>", xml)[1]  # blank: Aggre-SE reads the .sdr
    assert database_names(xml) == [f"線路方向_JRSNAP/線路方向({name}).DB1" for name in FORWARD]
    checks = [items(xml, f"dgCaseList_{number}")[:4] for number in range(1, 10)]
    assert [column[0] for column in checks] == ["-1", "-1", "-1", "0", "0", "-1", "-1", "0", "-1"]  # ρm 1.0, αf 1.0 without ⑧


def test_aggrese_takes_the_limits_of_the_sdr_of_0500_in_the_direction_of_the_stage(longitudinal):
    root, _ = longitudinal
    sdr = (root / "post" / "杭基礎.sdr").read_bytes()
    assert f"FAKE AGGRESE LIMITS axial {sha256(sdr)[:16]}" in pdf_text(root / "output" / "0711_線路方向非線形解析.pdf")
    sidecar = load_json((root / "post" / "線路方向_Aggre-SE.pik.provenance.json").read_bytes())
    assert sidecar["seismic_check"]["limits"] == {"stage": "0500", "kind": "sdr", "sha256": sha256(sdr), "direction": "axial"}
    result = load_json((root / "output" / "0711_線路方向非線形解析.json").read_bytes())
    assert result["seismic_check"]["limits"]["sha256"] == sha256(sdr)
    assert sorted(result["seismic_check"]["files"]) == ["pik", "xlsx"]


def test_the_folder_of_0721_has_the_analysis_of_each_ndu_and_the_project_names_all_the_cases(transverse):
    root, generation = transverse
    assert generation.stages == ("0500", "0600", "0720", "0721")
    folder = {path.name for path in (root / "post" / "線路直角方向_JRSNAP").iterdir()}
    assert {f"線路直角方向({name}).DB1" for name in FORWARD} | {f"線路直角方向_逆向({name}).DB1" for name in REVERSE} <= folder
    xml = project(root / "post" / "線路直角方向.xml")
    assert database_names(xml) == ([f"線路直角方向_JRSNAP/線路直角方向({name}).DB1" for name in FORWARD]
                                       + [f"線路直角方向_JRSNAP/線路直角方向_逆向({name}).DB1" for name in REVERSE])
    text = pdf_text(root / "output" / "0721_線路直角方向非線形解析.pdf")
    assert text.count("FAKE AGGRESE Case") == 8 and "FAKE AGGRESE LIMITS transverse" in text


def test_the_folder_of_0721_records_both_ndus(transverse):
    root, _ = transverse
    sidecar = load_json((root / "post" / "線路直角方向_JRSNAP.provenance.json").read_bytes())
    facts = sidecar["nonlinear_analysis"]
    reverse = (root / "post" / "線路直角方向_逆向.ndu").read_bytes()
    assert facts["ndu"]["sha256"] == sha256((root / "post" / "線路直角方向.ndu").read_bytes())
    assert facts["also_ndus"] == [{"stage": "0720", "export": "jrsnapreverse", "file": "線路直角方向_逆向.ndu",
                                   "sha256": sha256(reverse)}]
    assert len(facts["runner_summary"]["also"]) == 1


def test_0711_has_no_also_ndu(longitudinal):
    root, _ = longitudinal
    facts = load_json((root / "post" / "線路方向_JRSNAP.provenance.json").read_bytes())["nonlinear_analysis"]
    assert "also_ndus" not in facts and "also" not in facts["runner_summary"]


@pytest.mark.parametrize("items_", [LONGITUDINAL, TRANSVERSE, ("ground_model", "reactions", "longitudinal_seismic"),
                                    ("ground_model", "reactions", "transverse_seismic")])
def test_a_layer_that_liquefies_is_refused_before_any_runner(tmp_path, items_):
    layers = deepcopy(PILE["地盤データ"]["層"])
    layers[2]["De"] = 0.5
    path = write(tmp_path / "pre", items_, **{"地盤データ/層": layers})
    with pytest.raises(InputError, match="液状化する地層.*未対応"):
        generate.validate(GenerationOptions(path, tmp_path / "output", tmp_path / "post"))
    assert not (tmp_path / "output").exists() and not (tmp_path / "post").exists()


def test_a_steel_pile_foundation_does_not_make_0711_or_0721():
    for items_ in (LONGITUDINAL, TRANSVERSE):
        data = deepcopy(PILE)
        data["下部構造"]["基礎形式"] = "鋼管ソイルセメント杭"
        data["outputs"] = {key: key in items_ for key in data["outputs"]}
        with pytest.raises(InputError, match="鋼管ソイルセメント杭は未対応です"):
            parse_input(data)


def test_the_input_chooses_the_limits_it_was_given_not_those_of_a_direct_foundation(longitudinal):
    root, _ = longitudinal
    document = load_json((root / "output" / "0711_線路方向非線形解析.json").read_bytes())
    assert document["seismic_check"]["engine"] == "aggrese"
    assert [case["name"] for case in document["seismic_check"]["cases"]] == [f"線路方向({name})" for name in FORWARD]


def test_the_empty_log_both_analyses_write_is_kept_once(tmp_path, monkeypatch):
    """The real S_ANALYSIS.exe writes 解析実行Err.log (empty) beside each analysis: one folder holds it once."""
    monkeypatch.setenv("FAKE_JRSNAP_ERRLOG", "same")
    make(tmp_path, TRANSVERSE)
    folder = [path.name for path in (tmp_path / "post" / "線路直角方向_JRSNAP").iterdir()]
    assert folder.count("解析実行Err.log") == 1 and (tmp_path / "post" / "線路直角方向_JRSNAP" / "解析実行Err.log").read_bytes() == b""


def test_two_analyses_that_write_different_logs_under_one_name_stop_the_generation(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_JRSNAP_ERRLOG", "differ")
    with pytest.raises(generate.GenerationError, match="内容が違います: 解析実行Err.log"):
        make(tmp_path, TRANSVERSE)
    assert not (tmp_path / "post").exists()
