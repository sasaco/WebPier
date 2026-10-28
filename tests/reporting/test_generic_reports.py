"""The reports of a load model (decision 70): the application's parts as the train path prints them, the load model's
sections, the 支承作用 tables, the combinations and the zero case, nothing of the input's train; each report renders
to the same bytes twice."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from generic_report_support import cantilever, frame, generic_inputs, seismic
from jrsnap_pages_support import pages as jrsnap_pages
from load_diagram_support import REPORT as LOAD_DIAGRAM
from webpier.calc.frame import Direction
from webpier.reporting.stages.generic import cantilever as cantilever_report
from webpier.reporting.stages.generic import frame as frame_report
from webpier.reporting.stages.generic import reaction as reaction_report
from webpier.reporting.stages.generic import seismic as seismic_report

NO_COMBINATION = "該当する組合せなし（断面力0）"


def texts(found: list[dict[str, str]]) -> dict[str, str]:
    return {record["id"]: record["text"] for record in found}


def no_train(printed: dict[str, str]) -> None:
    """Nothing of the input's train, impact, curve or snow is printed (decision 70)."""
    for word in ("列車", "衝撃", "遠心", "雪荷重", "分担"):
        assert not [key for key, text in printed.items() if word in text], word


def rendered_twice(tmp_path: Path, render) -> pymupdf.Document:
    first, second = render(tmp_path / "a.pdf"), render(tmp_path / "b.pdf")
    assert Path(first).read_bytes() == Path(second).read_bytes()
    return pymupdf.open(first)


def test_0600_prints_the_dead_loads_and_the_self_weight(tmp_path):
    pier, _, reaction, _ = generic_inputs()
    printed = texts(reaction_report.semantic_records(reaction, pier))
    assert printed["0600/dead.heading"] == "6.1 死荷重"
    assert "5740.00" in printed["0600/dead.origin.sum.d1"] and "520.00" in printed["0600/dead.origin.sum.d2"]
    assert printed["0600/weight.heading"] == "6.2 橋脚自重"
    no_train(printed)
    document = rendered_twice(tmp_path, lambda path: reaction_report.render_dead_reaction(reaction, pier, path))
    assert document.page_count >= 3


def test_0610_prints_the_load_model(tmp_path):
    pier, reaction, result = frame(Direction.LONGITUDINAL)
    printed = texts(frame_report.semantic_records(result, reaction, pier))
    assert printed["0610/fixed.heading"] == "(1) 固定死荷重" and printed["0610/buoyancy.heading"] == "(3) 浮力"
    assert printed["0610/loadmodel.heading"] == "(4) 荷重モデルの作用の根拠"
    assert printed["0610/loadmodel.1.heading"] == "1) 車荷重の根拠"
    assert printed["0610/loadmodel.1.1"] == "車荷重の反力は設計資料の支承ごとの指定値とする。"
    assert printed["0610/bearings.heading"] == "(5) 荷重モデルの支承作用"
    assert printed["0610/bearings.L.heading"] == "1) 車荷重（L）"
    assert "起点側1300.00-0.325-97.50" in printed["0610/bearings.L"].replace("−", "-")
    assert printed["0610/bearings.L"].endswith("合計550.000.0071.25")
    assert "ZERO 断面力0" not in printed["0610/basic"] and printed["0610/basic"].endswith("8ZERO断面力01")
    assert "47-7制動荷重" in printed["0610/define"]
    assert printed["0610/extraction"].count(NO_COMBINATION) == 1 and "4変動作用7" in printed["0610/extraction"]
    no_train(printed)
    document = rendered_twice(tmp_path, lambda path: frame_report.render_generic_frame(result, reaction, pier, path,
                                                                                         LOAD_DIAGRAM))
    assert any("FAKE LOAD DIAGRAM" in page.get_text() for page in document)


def test_0620_prints_the_wind_on_the_pier(tmp_path):
    pier, reaction, result = frame(Direction.TRANSVERSE)
    printed = texts(frame_report.semantic_records(result, reaction, pier))
    assert printed["0620/wind.heading"] == "(4) 躯体の風荷重"
    assert printed["0620/wind.1.heading"] == "1) 風圧 3.0 kN/m2（PIER_WIND_1）"
    assert printed["0620/bearings.heading"] == "(5) 荷重モデルの支承作用"
    assert not any(key.startswith("0620/loadmodel.") for key in printed)
    no_train(printed)
    rendered_twice(tmp_path, lambda path: frame_report.render_generic_frame(result, reaction, pier, path,
                                                                            LOAD_DIAGRAM))


@pytest.mark.parametrize("direction", list(Direction))
def test_0710_and_0720_print_the_seismic_cases(tmp_path, direction):
    pier, reaction, result = seismic(direction)
    printed = texts(seismic_report.semantic_records(result, reaction, pier))
    prefix = "0710/" if direction is Direction.LONGITUDINAL else "0720/"
    assert printed[prefix + "combination"].endswith("1 + 2 + 3 + 4 + 5 + 6 + 71")
    assert "限定増分" in printed[prefix + "basic"] and "自重による地震時慣性力" in printed[prefix + "basic"]
    # Decision 80: each case of the load model under its name; no sections, 支承作用 tables or control weights.
    assert [printed[prefix + f"case.{case}.heading"] for case in ("LE", "EQ1", "EQL")] == [
        "(4) 地震時の車荷重", "(5) 上部工の慣性力", "(6) 活荷重慣性力"]
    assert printed[prefix + "inertia.heading"] == "(7) 自重による地震時慣性力"
    assert not [key for key in printed if "loadmodel" in key or "bearings" in key or "control" in key]
    flat = {key: text.replace("|", "").replace("−", "-") for key, text in printed.items()}
    if direction is Direction.LONGITUDINAL:
        # 90.00 × (−0.325) + 80.00 × 0.675 = −29.25 + 54.00
        assert flat[prefix + "case.LE.vertical"].endswith("合計170.0024.75")
        # Toward the earthquake positive, as 10-8 prints the bearing horizontal forces: 400.00 + 350.00 = 750.00.
        assert flat[prefix + "case.EQ1.horizontal"].endswith("1.0 EQ1400.00350.00750.00")
    else:
        assert flat[prefix + "case.LE.vertical"].endswith("合計170.00-106.00")  # −342.00 + 236.00
        # At the girder level 2.750 above the seat: 400.00 × (1.000 − 2.750), 350.00 × (1.200 − 2.750).
        assert "起点側　桁400.00-1.750-700.00終点側　桁350.00-1.550-542.50合計750.00" in flat[
            prefix + "case.EQ1.horizontal"]
    no_train(printed)
    rendered_twice(tmp_path, lambda path: seismic_report.render_generic_seismic(result, reaction, pier, path,
                                                                                jrsnap_pages(7)))


def test_0900_prints_the_combinations_and_the_zero_row(tmp_path):
    pier, result = cantilever()
    printed = texts(cantilever_report.semantic_records(result, pier))
    assert list(printed.items())[:2] == [("0900/title", "§13. 片持ち梁の照査"),
                                         ("0900/section.heading", "13.1 応答値の算定")]  # decision 117
    assert "Khmax = 0.552" in printed["0900/response.transverse"]
    assert printed["0900/adopted.table"].count("|－|－|0.00|0.00|0.00") == 3  # 復旧性（損傷）地震時以外: Md, Vd, Mt
    assert NO_COMBINATION in printed["0900/adopted.zero"]
    assert "EQ1|0.552|66.47|64.43|316.43" in printed["0900/left.combinations.table"]
    no_train(printed)
    rendered_twice(tmp_path, lambda path: cantilever_report.render_generic_cantilever(result, pier, path))


def test_the_optional_parts():
    from copy import deepcopy
    from dataclasses import replace

    from generic_report_support import CURRENT
    from webpier.calc.generic.frame import calculate_generic_frame
    from webpier.calc.generic.seismic import calculate_generic_seismic
    from webpier.calc.reaction import calculate_dead_reaction
    from webpier.inputs import parse_input
    from webpier.loadmodel import SeismicCombination

    pier, foundation, reaction, model = generic_inputs()
    bare = replace(model, sections={}, seismic_longitudinal=(SeismicCombination("死荷重", ("D1", "D2", "EQ2")),))
    frame_result = calculate_generic_frame(pier, foundation, reaction, bare, Direction.LONGITUDINAL, "0610")
    printed = texts(frame_report.semantic_records(frame_result, reaction, pier))
    assert "0610/loadmodel.heading" not in printed and printed["0610/bearings.heading"] == "(4) 荷重モデルの支承作用"
    assert frame_report.build_generic_frame(frame_result, reaction, pier).blocks
    seismic_result = calculate_generic_seismic(pier, foundation, reaction, bare, Direction.LONGITUDINAL)
    printed = texts(seismic_report.semantic_records(seismic_result, reaction, pier))
    assert "0710/bearings.heading" not in printed and printed["0710/inertia.heading"] == "(3) 自重による地震時慣性力"
    # Decision 78: only the dead cases the combinations use, numbered in turn; no buoyancy here.
    assert [printed["0710/fixed.heading"], printed["0710/additional.heading"]] == ["(1) 固定死荷重", "(2) 付加死荷重"]
    assert "0710/buoyancy.heading" not in printed
    assert seismic_report.build_generic_seismic(seismic_result, reaction, pier).blocks
    document = deepcopy(CURRENT)
    document["上部工反力"]["終点側"]["C支点"] = [None] * 10  # no bearing of the end girder on this pier
    pier = parse_input(document, load_model=True)
    printed = texts(reaction_report.semantic_records(calculate_dead_reaction(pier), pier))
    assert "0600/dead.end.bearings" not in printed and "0.00" in printed["0600/dead.end.sum.d1"]
