"""Heading-defined semantic scopes, current geometry, and native snapshot rendering."""

import builtins
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
import io
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reporting_seismic_audit import audited_sections, owned_pdf_glyphs

import fitz
from pypdf import PdfReader
import pytest

from src.calculator import calculate
from src.inputs import parse_input
from src.longitudinal_calculator import calculate_longitudinal
from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from src.seismic_longitudinal_calculator import calculate_seismic_longitudinal
from src.seismic_longitudinal_report import render_seismic_longitudinal_report


REFERENCE = json.loads((Path(__file__).parent / "fixtures/seismic_longitudinal_example2.json").read_text(encoding="utf-8"))


def calculated(*, geometry=None, train=None):
    data = json.loads((Path(__file__).parent / "fixtures/seismic_longitudinal_input.json").read_text(encoding="utf-8"))
    inputs = parse_reaction_input(data)
    if geometry:
        inputs = replace(inputs, geometry=replace(inputs.geometry, **geometry))
    if train:
        inputs = replace(inputs, train=replace(inputs.train, **train))
    longitudinal = calculate_longitudinal(
        inputs, calculate(parse_input(data)), calculate_reactions(inputs),
        design_conditions=parse_longitudinal_design_conditions(data),
    )
    return calculate_seismic_longitudinal(longitudinal)


def render(result, path):
    render_seismic_longitudinal_report(result, path)
    pages = PdfReader(path).pages
    return pages, audited_sections(result, path)[0]


def assert_inside_page(pdf_path):
    """Check actual vector/text bounds, independently of the layout constants."""
    with fitz.open(pdf_path) as document:
        assert len(document) > 0
        for page in document:
            assert page.rect.width == 595 and page.rect.height == 842
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        bounds = fitz.Rect(span["bbox"])
                        assert bounds.x0 >= 47.5 and bounds.x1 <= 576.5
                        assert bounds.y0 >= 71.5 and bounds.y1 <= 824
                        assert any(abs(span["size"] - role) < .1 for role in (9.9, 6.5, 8.0))
                        assert span["color"] == 0
            for drawing in page.get_drawings():
                bounds = drawing["rect"]
                assert bounds.x0 >= 47.5 and bounds.x1 <= 576.5
                assert bounds.y0 >= 71.5 and bounds.y1 <= 824


def test_three_pages_match_reference_values_and_case_definitions(tmp_path):
    result = calculated()
    path = tmp_path / "earthquake.pdf"
    pages, texts = render(result, path)
    assert len(pages) > 0
    for number, (text, heading) in enumerate(zip(texts, ("10.1 検討モデル", "10.2 作用の計算", "10.3 作用の組合せ"), strict=True), 1):
        assert heading in text
    assert all(f"10 - {number}" in page.extract_text() for number, page in enumerate(pages, 1))
    actions = texts[1]
    assert "0610 線路方向荷重" in actions
    assert "単線載荷" in actions
    for row in (REFERENCE["train"]["B"], REFERENCE["train"]["C"]):
        for key, places in (("N", 2), ("arm", 3), ("M", 2)):
            assert f"{row[key]:.{places}f}" in actions
    for value in (480, 4, 6790, 4740, 64, 595.35, 297.68, 1105.65):
        assert f"{value:.2f}" in actions
    assert "4.50 × 2.70 × 24.5 × 1.00" in actions
    for unit in ("kN", "kN・m", "kN/m"):
        assert unit in actions
    assert "桁受け" not in actions and "はり下" not in actions
    cases = texts[2]
    assert [re.search(rf"\b{case['symbol']}\b", cases) is not None for case in REFERENCE["basic_cases"]] == [True] * 8
    assert "浮力（平水位）" in cases and "雪荷重（2年確率）" in cases
    assert "限定増分" in cases and "Kh=0.20" in cases
    assert "1 + 2 + 3 + 4 + 5 + 6 + 7 + 8" in cases
    assert cases.split("組合せCase", 1)[1].count("1.0") == 2
    assert "TYPE" in cases
    assert "kN" not in cases  # This is the requested case-definition table.
    whole = "\n".join(texts) + str(PdfReader(path).metadata)
    for forbidden in ("ばね", "バネ", "Kv", "Ks", "Kr", "spring", "固定端", "Example", "Double", "legacy"):
        assert forbidden not in whole
    assert_inside_page(path)


def test_model_retains_only_current_physical_nodes_and_dimensions(tmp_path):
    result = calculated()
    path = tmp_path / "model.pdf"
    _, texts = render(result, path)
    assert "7.000" in texts[0] and "6.000" not in texts[0]
    for dimension in ("2.000", "0.700", "4.890", "1.350", "7.590", "2.700", "2.150"):
        assert dimension in texts[0]
    assert texts[0].count("0.010") == 2
    assert "拡大" not in texts[0] and "詳細" not in texts[0]
    assert "4.900" not in texts[0] and "7.600" not in texts[0]
    with fitz.open(path) as document:
        page = document[0]
        nodes = [drawing for drawing in page.get_drawings()
                 if drawing.get("color") == (0, 0, 0) and drawing["width"] == pytest.approx(.48, abs=.002)
                 and drawing["rect"].width == pytest.approx(2.4, abs=.002)
                 and drawing["rect"].height == pytest.approx(2.4, abs=.002)]
        assert len(nodes) == len(result["frame"]["nodes"]) == 7
        centers = sorted(((drawing["rect"].x0 + drawing["rect"].x1) / 2,
                          (drawing["rect"].y0 + drawing["rect"].y1) / 2) for drawing in nodes)
        physical_y = sorted(node["y"] for node in result["frame"]["nodes"])
        assert physical_y[0] == 0 and physical_y[-1] == pytest.approx(10.3)
        ys = sorted(center[1] for center in centers)
        scale = (ys[-1] - ys[0]) / (physical_y[-1] - physical_y[0])
        assert ys == pytest.approx([ys[-1] - z * scale for z in reversed(physical_y)], abs=.002)
        filled = [drawing for drawing in page.get_drawings() if drawing.get("fill") == (0, 0, 0)]
        assert not filled  # Native marks are outlined; no ground/fixed-support polygon.
        spans = [span for block in page.get_text("dict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"]]
        node_labels = owned_pdf_glyphs(result, path, "0710/frame.nodes")
        member_labels = owned_pdf_glyphs(result, path, "0710/frame.members")
        assert [span["text"] for span in sorted(node_labels, key=lambda span: span["bbox"][1])] == list("1234567")
        assert [span["text"] for span in sorted(member_labels, key=lambda span: span["bbox"][1])] == list("123456")
        assert result["frame"]["node_ids"]["column_base_micro_top"] == 4
        assert result["frame"]["node_ids"]["footing_top"] == 5
        assert_inside_page(path)


def test_render_is_snapshot_only_and_never_mutates_result(tmp_path, monkeypatch):
    result = calculated()
    snapshot = deepcopy(result)
    original_builtin, original_io = builtins.open, io.open

    def guarded(original):
        def open_without_sources(file, mode="r", *args, **kwargs):
            if isinstance(file, (str, Path)) and not any(flag in mode for flag in "wax+"):
                path = Path(file)
                if path.suffix.lower() in (".json", ".pdf", ".xls", ".xlsx"):
                    pytest.fail(f"Renderer reopened a source instead of using its snapshot: {path}")
            return original(file, mode, *args, **kwargs)
        return open_without_sources

    monkeypatch.setattr(builtins, "open", guarded(original_builtin))
    monkeypatch.setattr(io, "open", guarded(original_io))
    render_seismic_longitudinal_report(result, tmp_path / "snapshot.pdf")
    assert result == snapshot


def test_micro_member_dimensions_and_numbering_follow_changed_column_geometry(tmp_path):
    result = calculated(geometry={"h4": 6.23, "h1": .8, "b2": .6, "b3": 1.2, "w2": .6, "w3": 1.8})
    path = tmp_path / "changed-column.pdf"
    _, texts = render(result, path)
    assert "6.220" in texts[0] and "8.920" in texts[0]
    assert texts[0].count("0.010") == 2
    assert "拡大" not in texts[0] and "詳細" not in texts[0]
    frame = result["frame"]
    identifier = frame["node_ids"]["column_base_micro_top"]
    assert identifier == 6  # Two H1 nodes are numbered before the column nodes.
    assert [node["id"] for node in sorted(frame["nodes"], key=lambda node: (-node["y"], node["x"]))] == list(range(1, 10))
    with fitz.open(path) as document:
        nodes = [drawing for drawing in document[0].get_drawings()
                 if drawing.get("color") == (0, 0, 0) and drawing["width"] == pytest.approx(.48, abs=.002)
                 and drawing["rect"].width == pytest.approx(2.4, abs=.002)
                 and drawing["rect"].height == pytest.approx(2.4, abs=.002)]
        assert len(nodes) == len(frame["nodes"]) == 9
        spans = [span for block in document[0].get_text("dict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"]]
        node_labels = {int(span["text"]): span for span in owned_pdf_glyphs(result, path, "0710/frame.nodes")}
        assert set(node_labels) == set(range(1, 10))
        assert node_labels[identifier]["bbox"][3] < node_labels[frame["node_ids"]["footing_top"]]["bbox"][1]
        micro_labels = [span for span in spans if span["text"] == "0.010" and span["bbox"][1] > 177]
        assert len(micro_labels) == 2
        screen_ys = [(drawing["rect"].y0 + drawing["rect"].y1) / 2 for drawing in nodes]
        physical_ys = [node["y"] for node in frame["nodes"]]
        scale = (max(screen_ys) - min(screen_ys)) / (max(physical_ys) - min(physical_ys))
        footing_top = next(node for node in frame["nodes"] if node["id"] == frame["node_ids"]["footing_top"])
        extension_y = max(screen_ys) - footing_top["y"] * scale
        for span in micro_labels:
            assert span["bbox"][3] < extension_y - 3
    assert_inside_page(path)


@pytest.mark.parametrize("geometry", [
    {"h1": .8, "b2": .6, "b3": 1.2, "w2": .6, "w3": 1.8,
     "b1": 3.1, "b4": .15, "b5": .15, "b7": 1.8, "b9": 3.8},
    {"h5": .5, "h6": 2.2, "b7": 1.8, "b9": 3.8},
])
def test_changed_geometry_and_active_inertia_rows_fit_three_pages(tmp_path, geometry):
    result = calculated(geometry=geometry)
    path = tmp_path / "changed-geometry.pdf"
    pages, texts = render(result, path)
    assert len(pages) > 0
    actions = texts[1]
    for key in ("beam_top", "beam_bottom", "column", "footing"):
        assert f"{result['inertia'][key]:.2f}" in actions
    if geometry.get("h1"):
        assert "桁受けに作用する水平力" in actions
        assert "はり上" in actions and "はり下" in actions
        for key in ("H", "M"):
            assert f"{result['inertia']['pedestal'][key]:.2f}" in actions
    if geometry.get("h5"):
        weight = result["formulas"]["footing"]["factors"]["weight"]
        assert f"H = {weight:.2f} /" in actions
    assert "8.300" in texts[0]
    assert_inside_page(path)


def test_changed_train_line_loads_are_rendered_without_reference_constants(tmp_path):
    baseline = calculated()
    result = calculated(train={"earthquake_load": 57})
    assert result["vertical"]["train"] != baseline["vertical"]["train"]
    path = tmp_path / "train-load.pdf"
    _, texts = render(result, path)
    for side in ("B", "C"):
        for key in ("N", "M"):
            assert f"{result['vertical']['train']['earthquake'][side][key]:.2f}" in texts[1]
        assert f"{result['horizontal']['train'][side]:.2f}" in texts[1]
    assert "320.00" not in texts[1] and "160.00" not in texts[1]
    assert_inside_page(path)


def test_nonround_formula_factors_reproduce_the_displayed_results(tmp_path):
    result = calculated(geometry={
        "b1": 3.113, "w1": 9.377, "b4": .131, "b5": .177, "w4": 1.671, "w5": 2.143,
        "b6": 2.719, "w6": 4.637, "h1": .837, "b2": .253, "b3": 1.217, "w2": 1.003, "w3": 2.137,
        "h5": .457, "unit_weight_body": 25.237, "unit_weight_footing": 26.173,
        "unit_weight_displaced_soil": 18.431,
    })
    path = tmp_path / "nonround.pdf"
    _, texts = render(result, path)
    actions = texts[1]

    def rounded(value):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    number = r"(\d+\.\d+)"
    lines = re.findall(rf"Hw[123] = {number} × {number} × {number} × {number} = {number} kN/m", actions)
    assert len(lines) == 3
    for row in lines:
        first, second, gamma, kh, expected = map(Decimal, row)
        assert rounded(first * second * gamma * kh) == expected
    assert "3.113 × 9.377 × 25.237 × 1.00 = 736.68" in actions
    for symbol in ("H", "M"):
        row = re.search(rf"(?m)^{symbol} = {number} × {number} = {number} kN", actions)
        assert row is not None
        first, second, expected = map(Decimal, row.groups())
        assert rounded(first * second) == expected
    row = re.search(rf"H = {number} / {number}\s+× \( {number} - {number} \) × {number} = {number} kN", actions)
    assert row is not None
    weight, gamma1, gamma2, displaced, kh, expected = map(Decimal, row.groups())
    assert gamma1 == gamma2
    assert rounded(weight / gamma1 * (gamma2 - displaced) * kh) == expected
    # Extra factor precision is meaningful rather than an unfiltered float tail.
    assert max(len(value.partition(".")[2]) for value in row.groups()) <= 5
    assert_inside_page(path)


def test_model_bearing_labels_follow_current_bearing_types(tmp_path):
    result = calculated()
    first, second = tmp_path / "bearings.pdf", tmp_path / "bearings-swapped.pdf"
    render_seismic_longitudinal_report(result, first)
    spans = result["input"]["spans"]
    spans["b"]["bearing"], spans["c"]["bearing"] = spans["c"]["bearing"], spans["b"]["bearing"]
    render_seismic_longitudinal_report(result, second)

    def labels(path):
        with fitz.open(path) as document:
            return [(round(word[0], 3), word[4]) for word in document[0].get_text("words") if word[4] in ("M", "F")]

    before, after = labels(first), labels(second)
    assert [label for _, label in before] == ["M", "F"]
    assert [label for _, label in after] == ["F", "M"]
    # Different glyph widths shift the word bbox slightly around the same circle.
    assert [x for x, _ in after] == pytest.approx([x for x, _ in before], abs=1)


def test_small_positive_formula_divisor_adds_precision_before_evaluation(tmp_path):
    result = calculated(geometry={"h5": .457, "unit_weight_footing": .04})
    path = tmp_path / "small-positive-divisor.pdf"
    _, texts = render(result, path)
    assert "/ 0.04" in texts[1]
    assert f"{result['inertia']['footing']:.2f} kN" in texts[1]
    assert_inside_page(path)


@pytest.mark.parametrize("existing", (False, True))
def test_unreadable_layout_is_explicit_and_leaves_output_untouched(tmp_path, existing):
    result = calculated()
    result["basic_cases"][0]["label"] = "荷重" * 10000
    path = tmp_path / "too-large.pdf"
    if existing:
        path.write_bytes(b"preserve previous report")
    from gridlayoutpdf import LayoutOverflowError
    with pytest.raises(LayoutOverflowError):
        render_seismic_longitudinal_report(result, path)
    assert path.read_bytes() == b"preserve previous report" if existing else not path.exists()

