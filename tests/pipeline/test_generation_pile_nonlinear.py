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


def liquefying(**changes):
    """The input with a layer that liquefies (De 0.5) and the 液状化指数 20<PL, as the owner's sample R-7 has it."""
    layers = deepcopy(PILE["地盤データ"]["層"])
    layers[2]["De"] = 0.5
    return {"地盤データ/層": layers, "耐震設計条件/液状化指数": "20<PL", **changes}


@pytest.fixture(scope="module")
def wet(tmp_path_factory):
    root = tmp_path_factory.mktemp("pile-liquefied")
    return root, make(root, (*LONGITUDINAL, "transverse_seismic", "transverse_nonlinear_analysis"), **liquefying())


def test_an_input_that_liquefies_has_the_ndus_for_the_liquefaction_with_the_springs_of_the_sdc_for_it(wet):
    root, generation = wet
    post = {name for name in tree(root / "post") if "provenance" not in name}
    assert {"線路方向_液状化.ndu", "線路直角方向_液状化.ndu", "線路直角方向_液状化_逆向.ndu"} <= post
    normal, liquefied = (dict(line.split("=", 1) for line in (root / "post" / name).read_bytes().decode("cp932").split("\r\n")
                             if "=" in line) for name in ("線路方向.ndu", "線路方向_液状化.ndu"))
    assert liquefied["SNAPConbNum"] == "1" and normal["SNAPConbNum"] == "4"  # one combination: ρm 1.0, αf 1.0
    assert liquefied["SNAPConb1"] == normal["SNAPConb1"]
    assert liquefied["SuppotNum"] == normal["SuppotNum"] and liquefied["ElementNum"] == normal["ElementNum"]
    assert liquefied["JibanShogenInfo11"] != normal["JibanShogenInfo11"]  # the springs are those of the liquefaction
    assert any(liquefied[key] != normal[key] for key in liquefied if key.startswith("SuppotInfo"))
    sidecar = load_json((root / "post" / "線路方向_液状化.ndu.provenance.json").read_bytes())
    assert sidecar["metadata"]["target_version"] and "jrsnap_figures" not in sidecar  # no figures of its own


def test_the_folder_and_the_project_of_0711_have_the_case_for_the_liquefaction_last(wet):
    root, _ = wet
    folder = {path.name for path in (root / "post" / "線路方向_JRSNAP").iterdir()}
    assert "線路方向_液状化(Case1_ρm10_αf1_正向).DB1" in folder
    xml = project(root / "post" / "線路方向.xml")
    assert database_names(xml) == [f"線路方向_JRSNAP/線路方向({name}).DB1" for name in FORWARD] + [
        "線路方向_JRSNAP/線路方向_液状化(Case1_ρm10_αf1_正向).DB1"]
    assert [items(xml, f"dgCaseList_{number}")[4] for number in range(1, 10)] == [
        "0", "-1", "-1", "0", "-1", "0", "-1", "0", "-1"]  # ②③⑤⑦⑨
    for tag in ("dgEkijoCase21", "dgEkijoCase2"):
        assert [index for index, flag in enumerate(items(xml, tag)) if flag == "-1"] == [4]
    assert set(items(xml, "dgEkijoCase1")) == {"0"}
    assert items(xml, "_rbEkijo") == ["false", "true"]  # 20<PL


def test_the_project_of_0721_has_the_cases_for_the_liquefaction_in_the_order_of_the_ndus(wet):
    root, _ = wet
    xml = project(root / "post" / "線路直角方向.xml")
    assert database_names(xml)[8:] == ["線路直角方向_JRSNAP/線路直角方向_液状化(Case1_ρm10_αf1_正向).DB1",
                                       "線路直角方向_JRSNAP/線路直角方向_液状化_逆向(Case1_ρm10_αf1_逆向).DB1"]
    assert [index for index, flag in enumerate(items(xml, "dgEkijoCase2")) if flag == "-1"] == [8, 9]
    folder = {path.name for path in (root / "post" / "線路直角方向_JRSNAP").iterdir()}
    assert {"線路直角方向_液状化(Case1_ρm10_αf1_正向).DB1", "線路直角方向_液状化_逆向(Case1_ρm10_αf1_逆向).DB1"} <= folder
    text = pdf_text(root / "output" / "0721_線路直角方向非線形解析.pdf")
    assert text.count("FAKE AGGRESE Case") == 10


def test_aggrese_takes_the_limits_of_the_sdr_for_the_liquefaction_too(wet):
    root, _ = wet
    liquefied = (root / "post" / "杭基礎(液状化時用).sdr").read_bytes()
    text = pdf_text(root / "output" / "0711_線路方向非線形解析.pdf")
    assert f"FAKE AGGRESE LIMITS LIQUEFIED {sha256(liquefied)[:16]}" in text
    sidecar = load_json((root / "post" / "線路方向_Aggre-SE.pik.provenance.json").read_bytes())
    assert sidecar["seismic_check"]["limits"]["liquefied_sha256"] == sha256(liquefied)
    facts = load_json((root / "post" / "線路方向_JRSNAP.provenance.json").read_bytes())["nonlinear_analysis"]
    assert [item["export"] for item in facts["also_ndus"]] == ["jrsnapliquefied"]
    assert len(facts["runner_summary"]["also"]) == 1


def test_an_input_that_does_not_liquefy_has_none_of_it(longitudinal):
    root, _ = longitudinal
    assert not [name for name in tree(root / "post") if "液状化" in name]
    xml = project(root / "post" / "線路方向.xml")
    assert items(xml, "_rbEkijo") == ["true", "false"] and "<int>-1</int>" not in re.search(
        r"<dgEkijoCase2>([\s\S]*?)</dgEkijoCase2>", xml)[1]


@pytest.mark.parametrize("items_", [LONGITUDINAL, TRANSVERSE])
def test_a_layer_that_liquefies_needs_the_liquefaction_index_for_0711_and_0721(tmp_path, items_):
    path = write(tmp_path / "pre", items_, **liquefying(**{"耐震設計条件/液状化指数": None}))
    with pytest.raises(InputError, match="耐震設計条件.液状化指数: 液状化する地層がある杭基礎の0711|0721には値が必要です"):
        generate.validate(GenerationOptions(path, tmp_path / "output", tmp_path / "post"))
    assert not (tmp_path / "output").exists() and not (tmp_path / "post").exists()


@pytest.mark.parametrize("items_", [("ground_model", "reactions", "longitudinal_seismic"),
                                    ("ground_model", "reactions", "transverse_seismic")])
def test_0710_and_0720_of_a_layer_that_liquefies_need_no_index(tmp_path, items_):
    make(tmp_path, items_, **liquefying(**{"耐震設計条件/液状化指数": None}))
    assert [name for name in tree(tmp_path / "post") if name.endswith("液状化.ndu") or name.endswith("液状化_逆向.ndu")]


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


# --- decision 98: 杭頭反力の最大値から定める最小鉄筋量 and ⑧ 杭の段落し ---------------------------------------------------

CUTOFF = {"鉄筋/杭/cutoff/main_bars": {"diameter_mm": 25, "count": 16},
          "鉄筋/杭/cutoff/hoops": {"diameter_mm": 13, "sets": 1, "pitch_mm": 300.0},
          "鉄筋/杭/cutoff/cutoff_length_mm": 6000.0, "鉄筋/杭/cutoff/cutoff_anchorage_mm": 1200.0,
          "鉄筋/杭/cutoff/joint_reduction": 0.7, "鉄筋/杭/cutoff/margin_mm": 100.0,
          "鉄筋/杭/cutoff/no_joint": {"from_head_mm": 2000.0, "above_mm": 500.0, "below_mm": 500.0},
          "鉄筋/杭/cutoff/margin_ratio": {"moment": 1.1, "shear": 1.2}}


@pytest.fixture(scope="module")
def anchored(tmp_path_factory):
    root = tmp_path_factory.mktemp("pile-0711-cutoff")
    return root, make(root, LONGITUDINAL, **CUTOFF)


def head_reaction(xml: str) -> float:
    """Pvmax the stand-in's pickup gives (tests/fixtures/aggrese/fake_runner.py axial_forces): (3000 + 10 × the first element)
    of the row's bundle, per pile, the largest of the rows the project's 段落し情報 names."""
    rows = zip(items(xml, "dgMemberFirst"), items(xml, "dgMemberNumber"))
    return max((3000 + 10 * int(first)) / float(piles) for first, piles in rows)


def test_0711_of_a_cast_in_place_pile_prints_the_minimum_bars_after_aggrese_s_report(longitudinal):
    root, _ = longitudinal
    text = pdf_text(root / "output" / "0711_線路方向非線形解析.pdf")
    assert text.index("FAKE AGGRESE SUMMARY") < text.index("杭頭反力の最大値から定める最小鉄筋量")
    assert "Ｌ２応答時：線路方向" in text and "FAKE AGGRESE ANCHOR BAR" not in text
    minimum = load_json((root / "output" / "0711_線路方向非線形解析.json").read_bytes())["result"]["minimum"]
    assert minimum["direction"] == "線路方向" and minimum["ok"] is True and minimum["pvmax"] > 0


def test_0721_prints_the_minimum_bars_of_its_direction(transverse):
    root, _ = transverse
    text = pdf_text(root / "output" / "0721_線路直角方向非線形解析.pdf")
    assert text.index("FAKE AGGRESE SUMMARY") < text.index("Ｌ２応答時：線路直角方向")


def test_a_cut_off_has_aggrese_check_8_with_the_bars_after_it_and_the_calculated_head_anchorage(anchored):
    from webpier.calc.detailing.pile import head_anchorage, section
    root, _ = anchored
    xml = project(root / "post" / "線路方向.xml")
    assert [column[0] for column in ([items(xml, f"dgCaseList_{number}")[:4] for number in range(1, 10)])] == [
        "-1", "-1", "-1", "0", "0", "-1", "-1", "-1", "-1"]  # ρm 1.0, αf 1.0 with ⑧
    assert [items(xml, "dgCaseList_8")[index] for index in range(4)] == ["-1", "-1", "0", "0"]  # αf 1.0 only
    pier = parse_input(json.loads((root / "pre" / "input.json").read_text(encoding="utf-8")))
    length = head_anchorage(pier, section(pier)).length.value
    values = {tag: scalar(xml, tag) for tag in ("_D1", "_n1", "_D2", "_Aw", "_Ss", "_PileHeadLength", "_ParagraphLength",
                                                "_ReductionCoefficient", "_PileMidLength", "_DesignMarginLength",
                                                "_DisabledFromPileHead", "_DisabledUpwardFromCutOffPoint",
                                                "_DisabledDownwardFromCutOffPoint", "MudCoefficient", "VudCoefficient")}
    assert values == {"_D1": "25", "_n1": "16", "_D2": "13", "_Aw": "1", "_Ss": "300", "_PileHeadLength": f"{length:g}",
                      "_ParagraphLength": "6000", "_ReductionCoefficient": "0.7", "_PileMidLength": "1200",
                      "_DesignMarginLength": "100", "_DisabledFromPileHead": "2000", "_DisabledUpwardFromCutOffPoint": "500",
                      "_DisabledDownwardFromCutOffPoint": "500", "MudCoefficient": "1.1", "VudCoefficient": "1.2"}
    assert scalar(xml, "D1") == "25" and scalar(xml, "PileHeadLength") == f"{length:g}"  # the property as the field
    assert len(items(xml, "dgMemberFirst")) == len(items(xml, "dgMemberLast")) == len(items(xml, "dgMemberNumber")) >= 2


def test_a_cut_off_appends_aggrese_s_calculation_of_it_after_the_minimum_bars(anchored):
    root, _ = anchored
    xml = project(root / "post" / "線路方向.xml")
    text = pdf_text(root / "output" / "0711_線路方向非線形解析.pdf")
    rows = "-".join(items(xml, "dgMemberFirst"))
    assert text.index("杭頭反力の最大値から定める最小鉄筋量") < text.index(f"FAKE AGGRESE ANCHOR BAR D25-16 {rows}")
    minimum = load_json((root / "output" / "0711_線路方向非線形解析.json").read_bytes())["result"]["minimum"]
    assert minimum["pvmax"] == round(head_reaction(xml), 2)


def test_a_cut_off_with_a_blank_item_aggrese_needs_is_an_input_error(tmp_path):
    with pytest.raises(InputError, match=r"鉄筋\.杭\.cutoff\.cutoff_anchorage_mm: 杭の段落しの照査（Aggre-SE の ⑧）に必要です"):
        make(tmp_path, LONGITUDINAL, **{**CUTOFF, "鉄筋/杭/cutoff/cutoff_anchorage_mm": None})
