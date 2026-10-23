"""0611, 0612, 0621 and 0622 of a pile foundation (decision 89): the frame analysis of the pile frame, the column check of
Capacita and the 基礎の照査 of the pile heads and the footing top against the limits of SOIL-JR's .sdr. The runners are the
stand-ins of tests/fixtures (the .sdr of the SOIL-JR stand-in is the 5.2 sample's, the input is tests/fixtures/inputs/pile.json)."""

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
ITEMS = ("ground_model", "reactions", "longitudinal", "longitudinal_frame_analysis", "transverse",
         "transverse_frame_analysis")


def write(directory: Path, **changes) -> Path:
    """pile.json choosing the items of the frames and their checks, with each 'a/b/c' path replaced by its value."""
    data = deepcopy(PILE)
    data["outputs"] = {key: key in ITEMS for key in data["outputs"]}
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[part]
        node[key] = value
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "input.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    root = tmp_path_factory.mktemp("pile-check")
    return root, generate.generate(GenerationOptions(write(root / "pre"), root / "output", root / "post"))


def text(pdf: bytes) -> str:
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        return "".join(page.get_text() for page in document)


def test_a_pile_foundation_makes_the_checks_after_the_frames(made):
    root, generation = made
    assert generation.stages == ("0500", "0600", "0610", "0611", "0612", "0620", "0621", "0622")
    names = set(tree(root / "output"))
    assert {"0611_線路方向照査.pdf", "0612_線路方向基礎.pdf", "0621_直角方向照査.pdf", "0622_直角方向基礎.pdf"} <= names
    post = {name for name in tree(root / "post") if "provenance" not in name}
    assert {"線路方向.pik", "線路方向_ピックアップ変位量.csv", "線路方向_ピックアップ反力.csv", "線路方向.wdj"} <= post


def test_the_pile_check_reads_the_heads_and_the_footing_top(made):
    root, generation = made
    result = load_json((root / "output" / "0612_線路方向基礎.json").read_bytes())["result"]
    assert [member["piles"] for member in result["basis"]["members"]] == [3, 2, 3]
    first = result["columns"][0]
    assert first["name"] == "長期支持性能" and first["limits"]["rvd"] == 1694.7
    report = text((root / "output" / "0612_線路方向基礎.pdf").read_bytes())
    assert "8.11 基礎の照査" in report and "杭基礎の安定に対する検討" in report



def test_the_responses_are_those_of_the_stand_in_files(made):
    """Pickup 7 (長期支持) has a compression of 3000 + 10 m + 700 kN at the head of member m (the stand-in's), over the piles of
    its row; the footing top (node 4) moves at most 0.001 × (2 × 7 + 0.4) m, rotates 0.0001 × (14 + 0.4) rad."""
    root, _ = made
    result = load_json((root / "output" / "0612_線路方向基礎.json").read_bytes())["result"]
    long_term, short_term, safety = result["columns"]
    assert (long_term["vd"], long_term["vd_row"], long_term["vud"]) == (1895.0, 2, None)  # member 9, two piles: 3790 / 2
    assert (long_term["delta"], long_term["theta"]) == (14.4, 0.00144)
    assert (safety["pickup"], safety["vud"], safety["vud_row"]) == (6, 34.5, 2)  # the even pickups have a tension 60 + m: member 9, 69 / 2 piles
    assert short_term["limits"]["rud"] == 1671.3 and safety["limits"]["delta"] == 33.941
    assert result["engineering_status"] == "not_ok"  # the stand-in's responses exceed the long term limits


def test_the_transverse_direction_reads_the_other_tables_of_the_sdr(made):
    root, _ = made
    result = load_json((root / "output" / "0622_直角方向基礎.json").read_bytes())["result"]
    assert result["columns"][0]["limits"]["rvd"] == 1694.7  # the same values in both directions
    assert "9.11 基礎の照査" in text((root / "output" / "0622_直角方向基礎.pdf").read_bytes())


def test_a_failure_to_read_the_frame_analysis_stops_the_generation(monkeypatch, tmp_path):
    from webpier.calc.pile_check import PileResponseError
    from webpier.pipeline import stages

    def refuse(content, members):
        raise PileResponseError("読めません")

    monkeypatch.setattr(stages, "head_forces", refuse)
    with pytest.raises(generate.GenerationError, match="骨組解析の結果で0612の杭基礎の照査ができません: 読めません"):
        generate.generate(GenerationOptions(write(tmp_path / "pre"), tmp_path / "output", tmp_path / "post"))
    assert not (tmp_path / "output").exists() or not tree(tmp_path / "output")


def test_the_report_has_the_checks_the_table_and_the_grid_workbook(made, tmp_path):
    from webpier.reporting.stages import pile_check as report
    from webpier.reporting.stages.pile_check import LONGITUDINAL

    root, _ = made
    document = load_json((root / "output" / "0612_線路方向基礎.json").read_bytes())["result"]
    assert document["columns"][0]["name"] == "長期支持性能"
    # the report of the generation names the three requirements, the dash of the check with no tension and the judgement
    pdf = text((root / "output" / "0612_線路方向基礎.pdf").read_bytes())
    for words in ("長期支持", "短期支持", "安全性", "γi・Vud / Rud ≦ 1.0", "ＮＧ", "θLd (rad)", "0.00200"):
        assert words in pdf
    assert report.LONGITUDINAL.number == 8 and LONGITUDINAL.prefix == "0612/"


STEEL = {"下部構造/基礎形式": "鋼管ソイルセメント杭"}


def steel_options(root: Path, **changes) -> GenerationOptions:
    return GenerationOptions(write(root / "pre", **STEEL, **changes), root / "output", root / "post")


@pytest.fixture(scope="module")
def steel(tmp_path_factory):
    root = tmp_path_factory.mktemp("pile-body")
    return root, generate.generate(steel_options(root))


def test_the_pile_body_of_a_steel_pipe_pile_is_checked_by_steeldan(steel):
    """The stand-in of SteelDan calculates the formulas of Capacita/SteelDan PipePileVerifier from the WSJ WebPier wrote: D 798 and t 17
    (the input's 1.0 m pipe of 18 mm with a corrosion allowance of 1 mm: 1000 − 2, 18 − 1), SKK490."""
    root, _ = steel
    result = load_json((root / "output" / "0612_線路方向基礎.json").read_bytes())["result"]
    body = result["body"]
    assert (body["steel"]["grade"], body["steel"]["diameter"], body["steel"]["thickness"]) == ("SKK490", 998.0, 17.0)
    assert (body["steel"]["fsyk"], body["steel"]["fsvyk"], body["gamma_i"]) == (315.0, 180.0, 1.2)
    assert [row["row"] for row in body["rows"]] == [1, 2, 3] and [row["piles"] for row in body["rows"]] == [3, 2, 3]
    first = body["rows"][0]["cases"]
    assert [case["case"] for case in first] == [6, 7, 8]  # the largest bending moment, shear force and axial compression
    # row 1 (member 7, three piles): the stand-in's inner point has the moment 207 (largest) or −157 (smallest) kN m, the shear
    # force 307 or −257, the axial force −1007 … −4070 kN (compression negative); per pile, compression positive
    assert [(case["md"], case["vd"], case["nd"]) for case in first] == [(69.0, 6.7, 335.7), (16.7, 102.3, 666.7),
                                                                       (10.0, 13.3, 1356.7)]
    assert all(case["distance"] == 3.75 for case in first)
    resistance = body["resistance"]
    assert first[1]["shear"] == round(1.2 * 102.3 / resistance["shear"], 2)
    assert first[0]["ratio_compression"] == round(1.2 * (335.7 / resistance["compression"] + 69.0 / resistance["bending_compression"]), 2)
    assert body["engine_version"] == "fake-1" and len(body["wsj_sha256"]) == 64
    assert result["engineering_status"] in ("ok", "not_ok")


def test_the_pile_body_is_not_checked_for_a_cast_in_place_pile(made):
    root, _ = made
    assert load_json((root / "output" / "0612_線路方向基礎.json").read_bytes())["result"]["body"] is None



def test_a_pipe_too_thin_for_its_forces_fails_the_body_and_the_status(tmp_path):
    from webpier.pipeline.generate import GenerationOptions as Options

    thin = {"杭基礎/鋼管ソイルセメント杭/鋼管厚": 2.0}  # t = 2 − 1 = 1 mm of a 998 mm pipe
    generation = generate.generate(Options(write(tmp_path / "pre", **STEEL, **thin), tmp_path / "output", tmp_path / "post"))
    result = load_json((tmp_path / "output" / "0612_線路方向基礎.json").read_bytes())["result"]
    assert result["engineering_status"] == "not_ok" and result["body"]["steel"]["thickness"] == 1.0
    assert any(max(case["shear"], case["combined"], case["ratio_compression"]) > 1.0
               for row in result["body"]["rows"] for case in row["cases"])
    assert "ＮＧ" in text((tmp_path / "output" / "0612_線路方向基礎.pdf").read_bytes())
    assert generation.stages[-1] == "0622"


def test_the_pile_body_needs_the_grade_of_the_pipe(tmp_path):
    from webpier.core.errors import InputError

    with pytest.raises(InputError, match="杭基礎.鋼管ソイルセメント杭.鋼管材質: 杭体の照査に必要です"):
        generate.generate(steel_options(tmp_path, **{"杭基礎/鋼管ソイルセメント杭/鋼管材質": None}))
    assert not (tmp_path / "output").exists() or not tree(tmp_path / "output")


def test_a_failure_of_steeldan_stops_the_generation(monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_CAPACITA", "steel-fail")
    with pytest.raises(generate.GenerationError, match="pile.wsj で鋼管杭の杭体の照査ができません: .*SD-FORCE-CASE"):
        generate.generate(steel_options(tmp_path))
    assert not (tmp_path / "output").exists() or not tree(tmp_path / "output")
