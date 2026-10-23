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


def write(directory: Path) -> Path:
    data = deepcopy(PILE)
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
