"""0710 / 0720 of a pile foundation on G3〜G5 (decision 97): SoilStructure calculates the 地盤変位 at the pile nodes.

The runners are the stand-ins of tests/fixtures: SOIL-JR returns the 5.2 sample E's .sdc and SoilStructure the quarter wave of
its docstring, so Tg and f(z) are recalculated here by hand from the layers. The input is tests/fixtures/inputs/pile.json with the
reinforcement of a pile, on G4 with a Vs for each layer above the base.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
from copy import deepcopy
from pathlib import Path

import pytest

from pipeline_support import FIXTURES
from webpier.core.errors import InputError
from webpier.pipeline import generate
from webpier.pipeline.generate import GenerationError, GenerationOptions, required_runners
from webpier.pipeline import soilstructure
from webpier.inputs import parse_input

PILE = json.loads((FIXTURES / "inputs" / "pile.json").read_text(encoding="utf-8"))
CAST = {"鉄筋/杭/materials": {"main": "SD345", "transverse": "SD345"}, "鉄筋/杭/pure_cover_mm": 100.0,
        "鉄筋/杭/aggregate_max_mm": 25.0, "鉄筋/杭/main_bars": {"diameter_mm": 32, "count": 20},
        "鉄筋/杭/hoops/zone_2d": {"diameter_mm": 16, "sets": 1, "pitch_mm": 200.0}}
VELOCITIES = (170, 120, 140, 180, 330)  # the layers above the base; the last layer (第6層) goes on below it
THICKNESSES = (2.8, 2.6, 5.0, 4.0, 6.4)
VS = "せん断弾性波速度_Vs"


def data(items=("ground_model", "reactions", "longitudinal_seismic"), ground_class="G4地盤", velocities=VELOCITIES):
    document = deepcopy(PILE)
    document["outputs"] = {key: key in items for key in document["outputs"]}
    document["耐震設計条件"]["地盤区分"] = ground_class
    for layer, velocity in zip(document["地盤データ"]["層"], velocities):
        layer[VS] = velocity
    for path, value in CAST.items():
        node = document
        *parents, key = path.split("/")
        for part in parents:
            node = node[part]
        node[key] = deepcopy(value)
    return document


def write(directory: Path, document) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "input.json"
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    root = tmp_path_factory.mktemp("ground-displacement")
    return root, generate.generate(GenerationOptions(write(root / "pre", data()), root / "output", root / "post"))


def test_the_result_has_the_ground_displacement_of_the_stand_in(made):
    root, generation = made
    ground = generation.results["0710"].ground_displacement
    tg = 4 * sum(h / v for h, v in zip(THICKNESSES, VELOCITIES))  # the stand-in's quarter wave
    assert ground.period.value == round(tg, 4) and ground.region_coefficient == Decimal("0.7")  # C地域
    assert [point.depth.value for point in ground.profile] == [0.0, 2.8, 5.4, 10.4, 14.4, 20.8]
    surface = 0.413 * tg * 1000 * 0.7 ** 0.9
    assert ground.profile[0].l2.value == pytest.approx(surface, abs=0.01)
    assert ground.profile[1].l2.value == pytest.approx(surface * math.cos(math.pi * 2.8 / (2 * 20.8)), abs=0.01)
    assert ground.profile[-1].l1.value == 0


def test_the_nodes_are_the_pile_nodes_below_the_ground_surface(made):
    _, generation = made
    ground = generation.results["0710"].ground_displacement
    depth = generation.results["0500"].ground.depth.value  # Df: the pile heads
    assert ground.nodes[0].depth.value == depth and ground.nodes[-1].depth.value == pytest.approx(depth + 19.0)
    assert [p.depth.value for p in ground.nodes] == sorted(p.depth.value for p in ground.nodes)
    assert all(p.l1.value == 0 for p in ground.nodes if p.depth.value >= 20.8)  # below the base


def test_the_result_json_records_the_runner_and_the_values(made):
    root, generation = made
    document = json.loads((root / "output" / "0710_線路方向荷重.json").read_text(encoding="utf-8"))
    facts = document["ground_displacement"]
    assert (facts["engine"], facts["engine_version"], facts["engineering_status"]) == ("soilstructure", "1.3.0",
                                                                                       "not_evaluated")
    assert set(facts) == {"engine", "engine_version", "engineering_status", "document_sha256", "result_sha256"}
    result = document["result"]["ground_displacement"]
    assert result["period"] == generation.results["0710"].ground_displacement.period.value
    assert [layer["velocity"] for layer in result["layers"]] == list(VELOCITIES)


def test_g2_does_not_call_soilstructure_and_its_result_has_no_ground_displacement(tmp_path, monkeypatch):
    monkeypatch.delenv(soilstructure.RUNNER_KEY)
    document = data(ground_class="G2地盤", velocities=())
    generation = generate.generate(GenerationOptions(write(tmp_path / "pre", document), tmp_path / "output",
                                                     tmp_path / "post"))
    assert generation.results["0710"].ground_displacement is None
    written = json.loads((tmp_path / "output" / "0710_線路方向荷重.json").read_text(encoding="utf-8"))
    assert "ground_displacement" not in written and "ground_displacement" not in written["result"]
    pier = parse_input(document)
    registry = generate.STAGES.for_foundation(pier.substructure.foundation)
    assert soilstructure not in required_runners(("0500", "0600", "0710"), registry=registry, pier=pier)
    assert soilstructure in required_runners(("0500", "0600", "0710"), registry=registry)


def test_0720_calls_soilstructure_with_the_same_layers_once(tmp_path, monkeypatch):
    calls = []
    real = soilstructure.calculate
    monkeypatch.setattr(soilstructure, "calculate", lambda *args, **kwargs: calls.append(args) or real(*args, **kwargs))
    document = data(items=("ground_model", "reactions", "longitudinal_seismic", "transverse_seismic"))
    generation = generate.generate(GenerationOptions(write(tmp_path / "pre", document), tmp_path / "output",
                                                     tmp_path / "post"))
    assert generation.results["0720"].ground_displacement == generation.results["0710"].ground_displacement
    assert len(calls) == 1  # both directions cut the piles at the same layers


def test_a_blank_vs_above_the_base_stops_before_any_runner(tmp_path, monkeypatch):
    monkeypatch.delenv(soilstructure.RUNNER_KEY)
    document = data(velocities=(170, None, 140, 180, 330))
    with pytest.raises(InputError, match=f"地盤データ.層\\[1\\].{VS}: 地盤変位の算定に必要です"):
        generate.generate(GenerationOptions(write(tmp_path / "pre", document), tmp_path / "output", tmp_path / "post"))
    assert not (tmp_path / "output").exists()


def test_a_failing_soilstructure_stops_the_generation(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SOILSTRUCTURE", "fail")
    with pytest.raises(GenerationError, match="SoilStructure で地盤変位を算定できません"):
        generate.generate(GenerationOptions(write(tmp_path / "pre", data()), tmp_path / "output", tmp_path / "post"))
    assert not (tmp_path / "output").exists()


def test_an_answer_without_a_node_stops_the_generation(tmp_path, monkeypatch):
    real = soilstructure.calculate

    def without_points(*args, **kwargs):
        answer = real(*args, **kwargs)
        return soilstructure.GroundAnswer(answer.period, answer.points[:1], answer.document, answer.result,
                                          answer.engine_version)

    monkeypatch.setattr(soilstructure, "calculate", without_points)
    with pytest.raises(GenerationError, match="SoilStructure の答えで0710の地盤変位を読めません: 深さ"):
        generate.generate(GenerationOptions(write(tmp_path / "pre", data()), tmp_path / "output", tmp_path / "post"))


@pytest.fixture(scope="module")
def checked(tmp_path_factory):
    """0711 of the same input: the inertia Cases, then the 応答変位法 (the stand-in's summary: Teq 0.982, Kheq 0.408,
    KhL1 0.321 and Khmax 0.386 at most for Case 1)."""
    root = tmp_path_factory.mktemp("response-displacement")
    items = ("ground_model", "reactions", "longitudinal_seismic", "longitudinal_nonlinear_analysis")
    options = GenerationOptions(write(root / "pre", data(items)), root / "output", root / "post", export_dir=root / "export")
    return root, generate.generate(options)


def test_0711_takes_teq_and_kh_of_the_forward_case_of_rho_10_and_alpha_10(checked):
    _, generation = checked
    result = generation.results["0711"]
    tg = generation.results["0710"].ground_displacement.period
    assert result.inertia.case == 1 and result.inertia.teq.value == 0.982 and result.inertia.kheq.value == 0.408
    assert (result.inertia.kh_l1.value, result.inertia.kh_l2.value) == (0.321, 0.386)
    l1, l2 = result.corrections
    assert l1.alpha.value == round(0.982 / (tg.value / 0.7), 3) and l2.alpha.value == round(0.982 / (tg.value / 0.5), 3)
    assert not l1.yielded and not l2.yielded  # 0.321 and 0.386 below 0.408
    assert result.first_case == 5  # the four inertia Cases of 0710 come first


def test_each_case_of_the_response_is_an_ndu_analyzed_and_published_in_the_folder(checked):
    root, generation = checked
    cases = generation.results["0711"].cases
    folder = root / "post" / "線路方向_JRSNAP"
    names = [f"線路方向_応答変位法_{case.level}-{case.number}.ndu" for case in cases]
    assert all((folder / name).is_file() for name in names)
    assert all(any(item.name.startswith(name.removesuffix(".ndu") + "(Case1_") and item.suffix == ".DB1"
                   for item in folder.iterdir()) for name in names)
    sidecar = json.loads((root / "post" / "線路方向_JRSNAP.provenance.json").read_text(encoding="utf-8"))
    listed = sidecar["facts"]["nonlinear_analysis"]["response_ndus"] if "facts" in sidecar else \
        sidecar["nonlinear_analysis"]["response_ndus"]
    assert [item["file"] for item in listed] == names
    text = (folder / names[0]).read_bytes().decode("cp932")
    lines = dict(line.split("=", 1) for line in text.split("\r\n") if "=" in line)
    assert lines["DataInfo"].split(",")[:2] == ["1", "2"] and int(lines["ELoadNum"]) > 0
    assert lines["DataInfo"].split(",")[7] == str(int(cases[0].kh.value * 1000))


def test_the_project_has_the_cases_of_the_response_after_the_others_and_aggrese_checked_it(checked):
    root, generation = checked
    xml = (root / "post" / "線路方向.xml").read_bytes().decode("cp932", errors="replace")
    assert xml.count(".DB1") == 4 + len(generation.results["0711"].cases)  # one DB1 a Case: the inertia ones, then these
    assert xml.index("線路方向(Case4_") < xml.index("線路方向_応答変位法_L1-1(Case1_") < xml.index("線路方向_応答変位法_L2-1(Case1_")
    control = dict(line.split("=", 1) for line in (root / "post" / "線路方向.ndu").read_bytes().decode("cp932").split("\r\n")
                   if "=" in line)["DataInfo"].split(",")[3]
    assert f"<_AtPoint>{control}</_AtPoint>" in xml  # the load increment keeps no control joint in its DB1 (decision 97)


def test_the_report_has_webpiers_pages_then_aggreses_and_a_workbook(checked):
    root, generation = checked
    import pymupdf
    with pymupdf.open(root / "output" / "0711_線路方向非線形解析.pdf") as document:
        texts = [page.get_text() for page in document]
    assert "応答変位法による設計応答値の算定" in texts[0]
    assert any("FAKE AGGRESE" in text for text in texts[1:]) and "FAKE AGGRESE" not in texts[0]
    assert not (root / "export" / "0711_線路方向非線形解析.xlsx").exists()  # Aggre-SE's summary has the role 0711.xlsx
    document = json.loads((root / "output" / "0711_線路方向非線形解析.json").read_text(encoding="utf-8"))
    assert document["result"]["first_case"] == 5 and len(document["result"]["cases"]) == len(
        generation.results["0711"].cases)


def test_without_the_ground_displacement_0711_is_aggreses_report_alone(tmp_path):
    items = ("ground_model", "reactions", "longitudinal_seismic", "longitudinal_nonlinear_analysis")
    options = GenerationOptions(write(tmp_path / "pre", data(items, ground_class="G2地盤", velocities=())),
                                tmp_path / "output", tmp_path / "post", export_dir=tmp_path / "export")
    generation = generate.generate(options)
    assert generation.results.get("0711") is None
    assert not (tmp_path / "export" / "0711_線路方向非線形解析.xlsx").exists()
    assert not any("応答変位法" in item.name for item in (tmp_path / "post" / "線路方向_JRSNAP").iterdir())
    assert "<_AtPoint>0</_AtPoint>" in (tmp_path / "post" / "線路方向.xml").read_bytes().decode("cp932", errors="replace")


ITEMS_0711 = ("ground_model", "reactions", "longitudinal_seismic", "longitudinal_nonlinear_analysis")


def test_a_summary_without_the_inertia_stops_the_generation(tmp_path, monkeypatch):
    from webpier.calc.response_displacement import ResponseError

    def unreadable(*args):
        raise ResponseError("FAKE")

    monkeypatch.setattr(generate, "read_inertia", unreadable)
    with pytest.raises(GenerationError, match="0711の応答変位法の慣性力を読めません: FAKE"):
        generate.generate(GenerationOptions(write(tmp_path / "pre", data(ITEMS_0711)), tmp_path / "output",
                                            tmp_path / "post"))
    assert not (tmp_path / "output").exists()


def test_a_response_analysis_that_cannot_join_the_folder_stops_the_generation(tmp_path, monkeypatch):
    # the stand-in's 解析実行Err.log names the NDU, so a second NDU in the folder disagrees with the first (decision 94)
    monkeypatch.setenv("FAKE_JRSNAP_ERRLOG", "differ")
    with pytest.raises(GenerationError, match="解析実行Err.log"):
        generate.generate(GenerationOptions(write(tmp_path / "pre", data(ITEMS_0711)), tmp_path / "output",
                                            tmp_path / "post"))
