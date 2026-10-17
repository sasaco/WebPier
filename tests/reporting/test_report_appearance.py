"""Independent reference-derived appearance oracles and sensitivity checks."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pymupdf
import pytest


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "reporting" / "appearance"
REFERENCE = ROOT.parent / ".claude\docs\Example橋脚" / "output"
SPEC = importlib.util.spec_from_file_location("reporting_appearance", ROOT / "scripts" / "reporting_appearance.py")
assert SPEC is not None and SPEC.loader is not None
appearance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = appearance
SPEC.loader.exec_module(appearance)


@pytest.fixture(scope="module")
def style() -> dict[str, Any]:
    return json.loads((FIXTURES / "reference-style.json").read_text(encoding="utf-8"))


def test_reference_census_covers_all_pages_and_blank_pages() -> None:
    census = json.loads((FIXTURES / "reference-census.json").read_text(encoding="utf-8"))
    assert [len(doc["pages"]) for doc in census["documents"]] == [3, 37, 12, 17]
    assert sum(len(doc["pages"]) for doc in census["documents"]) == 69
    blank = []
    for document in census["documents"]:
        assert len(document["sha256"]) == 64
        for number, page in enumerate(document["pages"], 1):
            assert page["page"] == number
            assert page["size_pt"] == [595, 842]
            assert page["rotation"] == 0
            if page["rendered_blank"]:
                blank.append((document["file"][:4], number))
                assert page["characters"] == 0
    assert blank == [("0610", 8), ("0620", 14), ("0620", 15)]


def test_recorded_source_roles_satisfy_explicit_monochrome_transform(style: dict[str, Any]) -> None:
    for name, contract in style["roles"].items():
        source = contract["source"]
        sample = replace(appearance.TextSample(**source["sample"]), color=0)
        errors = appearance.role_errors(
            sample, contract, anchor_x=source.get("anchor_x_pt", 0),
            reference_baseline=source.get("reference_baseline_pt"),
        )
        assert not errors, (name, errors)


@pytest.mark.parametrize("field,value,expected", [
    ("font", "IPAexMincho", "font"),
    ("font", "MS-PMincho", "font"),
    ("size", 9.7, "size"),
    ("x", 118.0, "indent/equals"),
    ("color", 0xFF0000, "color"),
    ("color", 0x0000FF, "color"),
    ("size", float("nan"), "non-finite"),
])
def test_role_verifier_rejects_font_indent_size_and_color_mutations(
    style: dict[str, Any], field: str, value: Any, expected: str,
) -> None:
    contract = style["roles"]["common.body"]
    sample = appearance.TextSample(**contract["source"]["sample"])
    actual = replace(sample, **{field: value})
    errors = appearance.role_errors(actual, contract, anchor_x=58.92)
    assert any(expected in error for error in errors), errors


def test_equals_verifier_detects_column_shift_with_unchanged_text(style: dict[str, Any]) -> None:
    contract = style["roles"]["horizontal.result_equals"]
    sample = appearance.TextSample(**contract["source"]["sample"])
    errors = appearance.role_errors(replace(sample, x=sample.x + 1), contract, anchor_x=58.92)
    assert any("indent/equals" in error for error in errors)


@pytest.mark.parametrize("role", ["common.subscript", "common.superscript"])
def test_script_verifier_detects_baseline_shift(style: dict[str, Any], role: str) -> None:
    contract = style["roles"][role]
    sample = appearance.TextSample(**contract["source"]["sample"])
    errors = appearance.role_errors(replace(sample, baseline=sample.baseline - 1), contract,
                                    reference_baseline=565.558)
    assert "baseline: relative leading differs" in errors
    assert appearance.role_errors(sample, contract) == ["baseline: missing semantic reference"]


def test_native_subset_font_prefix_does_not_change_face_identity(style: dict[str, Any]) -> None:
    contract = style["roles"]["common.body"]
    sample = appearance.TextSample(**contract["source"]["sample"])
    assert not appearance.role_errors(replace(sample, font="ABCDEF+MS-Mincho"), contract, anchor_x=58.92)


def test_special_compressive_header_size_is_not_general_table_shrink(style: dict[str, Any]) -> None:
    special = style["roles"]["foundation.table_header_compressive"]
    ordinary = style["roles"]["foundation.table_header"]
    assert special["font"] == ordinary["font"] == "MS-Gothic"
    assert special["size_pt"] == 8.9
    assert ordinary["size_pt"] == 9.9
    sample = appearance.TextSample(**ordinary["source"]["sample"])
    assert any("size" in error for error in appearance.role_errors(replace(sample, size=8.9), ordinary))


def test_table_oracles_are_role_specific_and_fit_source(style: dict[str, Any]) -> None:
    assert {table["nominal_row_height_pt"] for table in style["tables"].values()} == {12.84, 14.28, 14.88, 23.04}
    for name, table in style["tables"].items():
        boundaries = table["source"]["boundaries_pt"]
        assert len(boundaries) >= 8
        expected = [table["nominal_row_height_pt"]] * (len(boundaries) - 1)
        assert not appearance.table_errors(boundaries, expected), name
        assert table["thin_rule_pt"] == 0.12
        assert table["thick_rule_pt"] == 0.96


@pytest.mark.parametrize("axis", ["h", "v"])
@pytest.mark.parametrize("stroke_width", [.06, .12])
def test_painted_border_union_preserves_combined_ink_width(axis: str, stroke_width: float) -> None:
    center = 100.0
    rules = [appearance.Rule(axis, center - stroke_width / 2, 20, 80, stroke_width),
             appearance.Rule(axis, center + stroke_width / 2, 20, 80, stroke_width)]
    bands = appearance.painted_rule_bands(rules, axis=axis, crossing=50)
    assert len(bands) == 1
    assert bands[0].coordinate == pytest.approx(center, abs=.00001)
    assert bands[0].width == pytest.approx(stroke_width * 2, abs=.00001)


def test_painted_border_union_does_not_hide_gaps_or_double_count_overprinting() -> None:
    rule = appearance.Rule("h", 100, 20, 80, .12)
    assert appearance.painted_rule_bands([rule, rule], axis="h", crossing=50)[0].width == pytest.approx(.12)
    separated = replace(rule, coordinate=100.13)  # 0.01pt real unpainted gap.
    assert len(appearance.painted_rule_bands([rule, separated], axis="h", crossing=50)) == 2
    assert appearance.painted_rule_bands([rule], axis="h", crossing=81) == []


@pytest.mark.parametrize("mutation", ["double-height", "missing-row", "one-row-drift", "non-finite", "reversed"])
def test_table_oracle_rejects_geometry_mutations(style: dict[str, Any], mutation: str) -> None:
    table = style["tables"]["foundation.soil"]
    boundaries = list(table["source"]["boundaries_pt"])
    heights = [14.28] * (len(boundaries) - 1)
    if mutation == "double-height":
        boundaries = [boundaries[0] + i * 28.56 for i in range(len(boundaries))]
    elif mutation == "missing-row":
        boundaries.pop(3)
    elif mutation == "one-row-drift":
        boundaries[3] += 1
    elif mutation == "non-finite":
        boundaries[3] = float("nan")
    else:
        boundaries.reverse()
    assert appearance.table_errors(boundaries, heights)


def test_source_measurements_are_reproducible_and_originals_unchanged(style: dict[str, Any]) -> None:
    if not REFERENCE.is_dir():
        pytest.skip("Reference PDFs are external read-only artifacts; fixture checks still run")
    for source in style["sources"]:
        path = REFERENCE / source["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
    assert appearance.build_style_contract(REFERENCE) == style


def test_reference_leading_indent_and_script_metrics_are_directly_measured(style: dict[str, Any]) -> None:
    if not REFERENCE.is_dir():
        pytest.skip("Read-only source PDF directory unavailable")
    with pymupdf.open(next(REFERENCE.glob("0600_*.pdf"))) as document:
        samples = appearance.text_samples(document[25])
        lhs = next(s for s in samples if s.text == "T / n")
        next_lhs = next(s for s in samples if s.text == "μ ・ Rm")
        assert next_lhs.baseline - lhs.baseline == pytest.approx(14.28, abs=.01)
        page_one = appearance.text_samples(document[0])
        chapter = next(s for s in page_one if s.text.startswith("§6."))
        section = next(s for s in page_one if s.text.startswith("6.1"))
        assert section.x - chapter.x == pytest.approx(14.52, abs=.01)
    for nominal in (12.84, 14.28, 14.52, 14.88, 23.04, 28.56):
        assert nominal / style["common_measures"]["measured_increment_pt"] == pytest.approx(round(nominal / .12))


def test_monochrome_verifier_detects_source_red_values_and_yellow_fill() -> None:
    if not REFERENCE.is_dir():
        pytest.skip("Read-only source PDF directory unavailable")
    with pymupdf.open(next(REFERENCE.glob("0500_*.pdf"))) as document:
        errors = appearance.monochrome_errors(document[0])
        assert any("colored text" in error for error in errors)
        assert any("fill:" in error for error in errors)


def test_census_scan_does_not_infer_table_structure_from_only_rule_count() -> None:
    """The mechanical classification is marked separately from semantic census."""
    census = json.loads((FIXTURES / "reference-census.json").read_text(encoding="utf-8"))
    page = census["documents"][1]["pages"][2]
    assert page["page"] == 3
    assert page["structure"] == "table-and-text"  # Drawing has many lines.
    semantic = json.loads((FIXTURES / "page-roles.json").read_text(encoding="utf-8"))
    assert semantic["0600"]["3"] == "dimensioned side/front pier diagrams"
    assert [len(semantic[stage]) for stage in ("0500", "0600", "0610", "0620")] == [3, 37, 12, 17]
