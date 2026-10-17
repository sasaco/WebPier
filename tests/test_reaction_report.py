"""Selectable calculation content and changed geometry in a newly drawn PDF."""

import importlib
from copy import deepcopy
from dataclasses import replace
import re

from pypdf import PdfReader
import pymupdf
import pytest

from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from legacy_reaction_oracle import load_legacy_reaction_oracle, parse_legacy_reaction_input


CASES = load_legacy_reaction_oracle("reaction_excel_oracle.json")["cases"]


def _compact(text):
    return re.sub(r"\s+", "", text)


def _page_with_heading(pages, heading):
    matches = [(index, text) for index, text in enumerate(pages) if _compact(heading) in _compact(text)]
    assert len(matches) == 1, heading
    return matches[0]


def _flow(pages):
    """Compact body text across content-driven page breaks, without footers."""
    return "".join(re.sub(r"6-\d+$", "", _compact(page)) for page in pages)


def _section(pages, start, end):
    text = _flow(pages)
    begin = text.index(_compact(start))
    return text[begin:text.index(_compact(end), begin + 1)]


def _within_frame(document):
    """Every native drawing stays inside the report frame (48, 72)-(576, 792)."""
    return all(47.5 <= drawing["rect"].x0 <= drawing["rect"].x1 <= 576.5
               and 71.5 <= drawing["rect"].y0 <= drawing["rect"].y1 <= 792.5
               for page in document for drawing in page.get_drawings())


@pytest.mark.parametrize("extra_snow, earthquake_load, expected", [
    (0, 32, (13580, 4740, 128, 64)),
    (7, 40, (13587, 4740, 160, 80)),
])
def test_longitudinal_introduction_shows_example_earthquake_workings(
        tmp_path, extra_snow, earthquake_load, expected):
    # Example 2, 07_荷重計算 pp. 4-5: independent loads and span lengths.
    # Keep the fixture local so later edits of pre/input.json cannot alter it.
    data = deepcopy(CASES[0]["input"])
    for side, local, remote, span, d1, d2, snow, remote_d2 in (
        ("起点側", "B支点", "A支点", 18.85, 5740, 520, 460, 660),
        ("終点側", "C支点", "D支点", 9.25, 1860, 260, 250, 260),
    ):
        end = .575 if side == "起点側" else .375
        data["上部構造"][side]["桁長"].update(L1=end, スパン長=span, L2=end)
        branch = data["上部工反力"][side]
        for index, row in enumerate(branch[local]["支承"]):
            row.update(固定死荷重_D1=d1 if index == 0 else 0,
                       付加死荷重_D2=d2 if index == 0 else 0,
                       雪荷重_2年確率=snow if index == 0 else 0)
        branch.setdefault(remote, {})["合計"] = {
            "固定死荷重_D1": d1, "付加死荷重_D2": remote_d2,
            "雪荷重_2年確率": snow + (extra_snow if remote == "A支点" else 0),
        }
    data["上部構造"]["列車"]["軸重"]["地震"]["値"] = earthquake_load
    result = calculate_reactions(parse_reaction_input(data))
    original = deepcopy(result)
    path = tmp_path / "longitudinal-introduction.pdf"
    importlib.import_module("src.reaction_report").render_reaction_report(result, path)
    pages = [page.extract_text() for page in PdfReader(path).pages]
    start, _ = _page_with_heading(pages, "6.3.1 線路方向に働く水平荷重")
    end = next(index for index in range(start + 1, len(pages))
               if "(2)支承に働く水平荷重" in _compact(pages[index]))
    introduction = _compact("\n".join(pages[start:end + 1])).split("(2)支承に働く水平荷重")[0]
    headings = ("1)ロングレール縦荷重", "2)制動荷重・始動荷重",
                "3)地震時慣性力荷重", "4)地震時列車荷重慣性力")
    positions = [introduction.index(heading) for heading in headings]
    assert positions == sorted(positions)
    girder, train = introduction[positions[2]:positions[3]], introduction[positions[3]:]
    for section, forces in ((girder, expected[:2]), (train, expected[2:])):
        for number, force in enumerate(forces, 1):
            assert re.search(rf"T{number}＝[^\n]*?＝{force:.2f}kN", section)
    assert "Kh＝1.00" in girder
    assert "μ＝0.20" in train
    assert result == original


def test_example2_bearing_report_uses_raw_verticals_and_side_recovery_coefficients(tmp_path):
    from test_reaction_load_rules import example2_horizontal_input

    result = calculate_reactions(parse_reaction_input(example2_horizontal_input()))
    path = tmp_path / "example2-bearings.pdf"
    importlib.import_module("src.reaction_report").render_reaction_report(result, path)
    pages = [page.extract_text() for page in PdfReader(path).pages]
    safety = _section(pages, "7) 安全性", "8) 復旧性")
    assert "1.35B" in safety and "L＋I" in safety and "187.01" in safety
    recovery = _section(pages, "8) 復旧性", "9) 地震時")
    b, c = recovery.split("【終点側C支点】")
    assert "1.23×160.00" in b
    assert "1.00×96.00" in c
    assert "165.31" in c
    text = _compact("\n".join(pages))
    assert "Lのみ（衝撃Iなし）" not in text
    for unwanted in ("Example", "原本", "明示値", "採用有効係数", "SHA256", "ROUND"):
        assert unwanted not in text


def test_equivalent_centroid_inertia_report_shows_six_decimal_heights(tmp_path):
    from test_reaction_load_rules import example2_horizontal_input

    data = example2_horizontal_input()
    # Independent inputs: 07 p.18 body moment plus 05 pp.3-4 reaction moments.
    for side, moment, force in (
        ("起点側", 15180 + 2 * (530 * 3.8 + 210 * 1.5), 5740 + 520 + 460),
        ("終点側", 4730 + 2 * 430 * 2.95, 1860 + 260 + 250),
    ):
        data["上部構造"][side]["重心高_hs"] = moment / force
    result = calculate_reactions(parse_reaction_input(data))
    for side, force, moment in (("B", 6720, 19838), ("C", 2370, 7267)):
        assert result["transverse"][6][side]["force"] == force
        assert result["transverse"][6][side]["moment"] == pytest.approx(moment)
    path = tmp_path / "equivalent-centroid.pdf"
    importlib.import_module("src.reaction_report").render_reaction_report(result, path)
    pages = [page.extract_text() for page in PdfReader(path).pages]
    text = _compact(_page_with_heading(pages, "(4) 地震時慣性力荷重")[1])
    for value in ("2.952083", "3.066245", "6720.00×2.952083", "2370.00×3.066245", "19838.00", "7267.00"):
        assert value in text
    for unwanted in ("シェルター", "合成作用高さ", "本体水平力", "Example", "SHA256", "ROUND"):
        assert unwanted not in _compact("\n".join(pages))


def test_pdf_preserves_precision_of_explicit_brake_and_service_live_coefficients(tmp_path):
    from test_reaction_load_rules import example2_horizontal_input

    data = example2_horizontal_input()
    data["上部構造"]["支承データ"]["終点側"]["復旧性制動係数"] = 1.234
    data["上部構造"]["列車"]["荷重修正係数"]["使用性"] = .87654
    path = tmp_path / "coefficients.pdf"
    result = calculate_reactions(parse_reaction_input(data))
    importlib.import_module("src.reaction_report").render_reaction_report(result, path)
    text = _compact("\n".join(page.extract_text() for page in PdfReader(path).pages))
    assert "1.234B" in text and "1.234×96.00" in text
    assert "0.87654×" in text


@pytest.mark.parametrize("changes, present", [
    ({"b3": 0}, False),
    ({"w3": 0}, False),
    ({"h1": 0}, False),
    ({}, True),
    ({"h1": 1e-7}, True),  # Displayed V and N round to zero, but V is positive.
    ({"unit_weight_body": 0}, True),
])
def test_pedestal_detail_depends_on_volume_and_keeps_complete_beam(tmp_path, changes, present):
    case = next(case for case in CASES if case["case"] == "pedestal_nonzero")
    inputs = parse_reaction_input(case["input"])
    inputs = replace(inputs, geometry=replace(inputs.geometry, **changes))
    result = calculate_reactions(inputs)
    original = deepcopy(result)
    assert (result["weights"]["cells"]["X63"] > 0) == present
    path = tmp_path / "pedestal.pdf"
    importlib.import_module("src.reaction_report").render_reaction_report(result, path)
    reader = PdfReader(path)
    pages = [page.extract_text() for page in reader.pages]
    detail = _section(pages, "(3) 橋脚自重の計算", "柱下端における重量")
    assert ("1)桁受け" in detail) == present
    for number, name in enumerate(("はり", "柱", "フーチング", "載荷土", "浮力"), 1 + present):
        assert detail.count(f"{number}){name}") == 1
    # Aggregate rows remain available after the component workings.
    assert "桁受け" in _flow(pages).split(_compact("柱下端における重量"), 1)[1]
    # The pedestal view exists exactly when its volume does; every view of
    # every geometry stays inside the native frame.
    from src.reporting.stages.reaction import content
    figures = [unit.key for unit in content(result) if unit.kind == "figure"]
    assert ("weights.pedestal.figure" in figures) == present
    with pymupdf.open(path) as document:
        assert _within_frame(document)
    assert result == original


@pytest.mark.parametrize("name", ["current_input", "geometry_water", "bearing_speed_height"])
def test_report_has_all_calculation_sections_and_current_values(tmp_path, name):
    case = next(case for case in CASES if case["case"] == name)
    # Keep the independent asymmetric slope/intersection drawing regression.
    # Other cases exercise the current parser-to-PDF path.
    parser = parse_legacy_reaction_input if name == "geometry_water" else parse_reaction_input
    result = calculate_reactions(parser(case["input"]))
    original = deepcopy(result)
    path = tmp_path / f"{name}.pdf"
    importlib.import_module("src.reaction_report").render_reaction_report(result, path)
    reader = PdfReader(path)
    pages = [page.extract_text() for page in reader.pages]
    text = "\n".join(pages)
    compact = _compact(text)
    for section in ("6.1 死荷重・雪荷重", "橋脚自重の計算", "桁受け", "はり", "柱", "フーチング",
                    "載荷土", "高水位", "平水位", "底水位", "柱下端における重量",
                    "6.2 列車荷重", "地震時列車", "疲労", "橋脚く体に対する衝撃荷重",
                    "6.3.1 線路方向", "固定支点", "可動支点", "6.3.2 線路直角方向", "車両横荷重"):
        assert section in text, section
    for component in ("はり", "柱", "フーチング", "高水位"):
        assert f'{result["weights"]["components"][component]["N"]:.2f}' in compact
    assert f'{result["moving_train"]["reactions"][1]:.2f}' in compact
    assert all(float(page.mediabox.width) == pytest.approx(595, abs=0.01) for page in reader.pages)
    assert all(float(page.mediabox.height) == pytest.approx(842, abs=0.01) for page in reader.pages)
    assert "6.1 死荷重・雪荷重" in pages[0]
    train_page, _ = _page_with_heading(pages, "6.2 列車荷重")
    transverse_page, _ = _page_with_heading(pages, "6.3.2")
    assert train_page < next(index for index, page in enumerate(pages) if "6.3.1" in page) < transverse_page
    # Native equations position operators without space characters.
    assert "0.1・T/n" not in compact
    assert "μ・T/n" in compact
    flow = _flow(pages)
    assert flow.index("2)柱") < flow.index("3)フーチング") < flow.index("4)載荷土")
    footing = _section(pages, "3) フーチング", "4) 載荷土")
    if name == "geometry_water":
        # The changed footing has a 0.6 m haunch and a 1.8 m base. Its
        # eccentric column intersects sloping soil at 2.010 m, not 2.000 m.
        assert "0.600" in footing
        assert "1.800" in footing
        assert "2.010" in _section(pages, "4) 載荷土", "5) 浮力")
    # Each soil/water calculation keeps its tables, result, and both views on
    # the same page, including the formerly split high-water bottom dimensions.
    geometry = result["input"]["geometry"]
    for heading, component in (("4) 載荷土", "上載土"), ("(a) 高水位", "高水位"),
                               ("(b) 平水位", "平水位"), ("(c) 底水位", "低水位")):
        index, content = _page_with_heading(pages, heading)
        assert "算式" in _compact(content)
        assert f'{result["weights"]["components"][component]["N"]:.2f}' in _compact(content)
        assert "xL" in content and "xC" in content
        for prefix in ("b", "w"):
            assert f'{sum(geometry[f"{prefix}{i}"] for i in (7, 8, 9)):.3f}' in content
    # An applied T1/T2 load and its final H must never cross a page boundary.
    # All twelve longitudinal cases have two complete support workings.
    total_workings = 0
    for content in pages:
        events = re.findall(r"※\s*(T[12]\s*＝|∴\s*H\s*＝)", content)
        assert len(events) % 2 == 0
        for applied, conclusion in zip(events[::2], events[1::2]):
            assert applied.startswith("T") and conclusion.startswith("∴")
            total_workings += 1
    assert total_workings == 24
    transverse = flow[flow.index("6.3.2"):]
    assert (transverse.index("(4)地震時慣性力荷重") < transverse.index("(5)地震時列車荷重慣性力荷重")
            < transverse.index("(6)支承に働く水平荷重のまとめ"))
    with pymupdf.open(path) as document:
        assert _within_frame(document)
    assert result == original


def test_single_handoff_values_are_not_used_for_report(tmp_path):
    result = calculate_reactions(parse_reaction_input(CASES[0]["input"]))
    result["macro_handoff_single"] = {"sentinel": 987654321.123}
    path = tmp_path / "report.pdf"
    importlib.import_module("src.reaction_report").render_reaction_report(result, path)
    assert "987654321" not in "\n".join(page.extract_text() for page in PdfReader(path).pages)


def test_changed_height_inputs_and_transverse_section_order(tmp_path):
    inputs = parse_reaction_input(CASES[0]["input"])
    inputs = replace(inputs, spans=replace(inputs.spans, b=replace(inputs.spans.b,
        h1=0.313, h2=0.777, h3=0.888, h4=0.999, hs=2.345)),
        train=replace(inputs.train, height_wind=5.678, height_centrifugal=1.789, height_seismic=1.678))
    path = tmp_path / "height_inputs.pdf"
    importlib.import_module("src.reaction_report").render_reaction_report(calculate_reactions(inputs), path)
    text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
    for value in (0.313, 0.777, 0.888, 0.999, 2.345, 5.678, 1.678):
        assert f"{value:.3f}" in text
    for value in (1.789,):
        assert f"{value:.2f}" in text
    section = text[text.index("6.3.2"):]
    assert section.index("(1) 遠心") < section.index("(2) 車両横") < section.index("(3) 風") < section.index("(4) 地震")


def test_display_substitutions_use_current_bearings_and_curve_conditions(tmp_path):
    inputs = parse_reaction_input(CASES[0]["input"])
    inputs = replace(inputs, spans=replace(inputs.spans,
        b=replace(inputs.spans.b, bearing="可動", radius=0),
        c=replace(inputs.spans.c, bearing="固定", radius=812, speed=71)))
    result = calculate_reactions(inputs)
    from src.reaction_report_values import build_display_values

    display = build_display_values(result)
    assert display["線路荷重"]["N4"] == "可動"
    assert display["線路荷重"]["N5"] == "固定"
    # The repeated workings must follow the recalculated load, not old xls caches.
    assert display["線路荷重"]["J501"] == result["longitudinal_base"]["B"]["earthquake_dead"]
    assert display["直角荷重"]["Q50"] == 71
    assert display["直角荷重"]["S51"] == 812
    path = tmp_path / "bearings_curves.pdf"
    importlib.import_module("src.reaction_report").render_reaction_report(result, path)
    text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
    assert text.count("直線区間のため") == 1
    assert f'{result["transverse_parameters"]["C"]["alpha"]:.3f}' in text


def test_previously_empty_bearing_slots_show_individual_loads_and_factors(tmp_path):
    inputs = parse_reaction_input(CASES[0]["input"])
    b, c = list(inputs.dead.b), list(inputs.dead.c)
    b[2] = replace(b[2], position=0, d1=312.3, d2=45.6, factors=(0.321, 0.456, 0, 0))
    c[9] = replace(c[9], position=-1, d1=987.6, d2=65.4, factors=(0.654, 0.123, 0, 0))
    inputs = replace(inputs, dead=replace(inputs.dead, b=tuple(b), c=tuple(c)))
    path = tmp_path / "new_bearing_slots.pdf"
    importlib.import_module("src.reaction_report").render_reaction_report(calculate_reactions(inputs), path)
    pages = [page.extract_text() for page in PdfReader(path).pages]
    # These are individual entries, distinct from all support totals. The
    # template's originally empty G3/G10 cells must still be drawable.
    girders = _section(pages, "(2) 主桁反力", "(3) 橋脚自重の計算")
    for value in ("312.3", "45.6", "987.6", "65.4", "0.321", "0.456", "0.654", "0.123"):
        assert value in girders
    end_side = _section(pages, "2) 終点側桁", "(3) 橋脚自重の計算")
    assert "G10" in end_side
    for value in ("987.6", "65.4", "0.654", "0.123", "0.777"):
        assert value in end_side
