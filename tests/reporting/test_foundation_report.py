"""0500 native migration: independent old-source semantics and long tables."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, is_dataclass, replace
import importlib
import json
from pathlib import Path
import sys
from typing import Any

import pymupdf
import pytest

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts"))
from reporting_semantic_audit import SemanticMismatch, audit_foundation_native, compare_semantics, reference_text, validate_source_coverage

BASELINE = PROJECT / "tests/fixtures/reporting/baseline"
REFERENCE = PROJECT / "tests/fixtures/reporting/semantic/0500.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_reviewed_mapping_covers_every_old_body_span_once() -> None:
    reference = read_json(REFERENCE)
    validate_source_coverage(reference, read_json(BASELINE / "display/0500.json"))
    assert len(reference["records"]) == 70
    assert sum(len(record["source_ids"]) for record in reference["records"]) == 440


@pytest.mark.parametrize("mutation", ["sign", "factor", "factor_order", "order", "unit", "missing", "root"])
def test_semantic_audit_rejects_meaning_changes(mutation: str) -> None:
    reference = read_json(REFERENCE)
    actual = [{"id": row["id"], "text": reference_text(row)} for row in reference["records"]]
    item = next(row for row in actual if row["id"] == "0500/kv.long_term")
    if mutation == "sign":
        item["text"] = item["text"].replace("-1/2", "1/2")
    elif mutation == "factor":
        item["text"] = item["text"].replace("0.5", "")
    elif mutation == "factor_order":
        item["text"] = item["text"].replace("165760", "TEMP").replace("7.937", "165760").replace("TEMP", "7.937")
    elif mutation == "order":
        actual[0], actual[1] = actual[1], actual[0]
    elif mutation == "unit":
        item["text"] = item["text"].replace("kN/m", "N/m")
    elif mutation == "root":
        item = next(row for row in actual if row["id"] == "0500/kv.width")
        item["text"] = item["text"].replace("√63.000", "63.000")
    else:
        actual.pop()
    with pytest.raises(SemanticMismatch):
        compare_semantics(reference, actual)


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "text"])
def test_source_mapping_rejects_incomplete_or_changed_coverage(mutation: str) -> None:
    reference = read_json(REFERENCE)
    if mutation == "duplicate":
        reference["records"][0]["source_ids"].append(reference["records"][1]["source_ids"][0])
    elif mutation == "missing":
        reference["records"][0]["source_ids"].clear()
    else:
        reference["records"][0]["source_text"] += "missing-factor"
    with pytest.raises(SemanticMismatch):
        validate_source_coverage(reference, read_json(BASELINE / "display/0500.json"))


def test_numeric_root_evidence_is_in_the_old_pdf_vector_paths() -> None:
    record = next(item for item in read_json(REFERENCE)["records"] if item["id"] == "0500/kv.width")
    atom = record["vector_atoms"][0]
    assert atom["text"] == "√"
    with pymupdf.open(BASELINE / "pdfs/0500.pdf") as pdf:
        lines = [pdf[atom["source_page"] - 1].get_drawings()[index]["items"][0]
                 for index in atom["source_drawing_indices"]]
        assert [line[0] for line in lines] == ["l"] * 3
        assert lines[0][2] == lines[1][1] and lines[1][2] == lines[2][1]
        assert lines[2][1].y == lines[2][2].y
        assert lines[2][1].x < lines[2][2].x


def test_new_foundation_content_matches_independent_old_semantics() -> None:
    path = PROJECT / "src/reporting/stages/foundation.py"
    assert path.is_file(), "native foundation stage is not implemented"
    module = importlib.import_module("src.reporting.stages.foundation")
    result = read_json(BASELINE / "results/0500.json")
    before = deepcopy(result)
    compare_semantics(read_json(REFERENCE), module.semantic_records(result))
    assert result == before


def test_public_renderer_uses_native_grid_instead_of_legacy_canvas(tmp_path: Path) -> None:
    from src import report
    from src.reporting.stages import foundation

    # The old Canvas path is removed, not merely bypassed.
    assert not hasattr(report, "Canvas") and report.render is foundation.render
    destination = tmp_path / "0500.pdf"
    report.render_report(read_json(BASELINE / "results/0500.json"), destination)
    with pymupdf.open(destination) as pdf:
        assert all(not page.get_images() for page in pdf)
        assert "地盤のモデル化" in "".join(page.get_text() for page in pdf)


def test_direct_renderer_preserves_every_long_soil_table_row(tmp_path: Path) -> None:
    from src.report import render_report

    result = read_json(BASELINE / "results/0500.json")
    template = result["layers"][0]
    result["layers"] = [{**template, "name": f"層{index:03d}"} for index in range(90)]
    result["layers"][40]["soil_type"] = "砂質土と粘性土の互層を含む区分"
    destination = tmp_path / "0500-long.pdf"
    render_report(result, destination)
    with pymupdf.open(destination) as pdf:
        text = "".join(page.get_text() for page in pdf)
        assert len(pdf) > 3
        for index in range(90):
            assert text.count(f"層{index:03d}") == 1
        assert "砂質土と粘性土の互層を含む区分" in text.replace("\n", "")


def test_input_parser_keeps_existing_eleven_layer_contract() -> None:
    from src import parse_input

    document = read_json(BASELINE / "input.json")
    document["地盤データ"]["層"] *= 6
    with pytest.raises(ValueError):
        parse_input(document)


def test_long_soil_names_wrap_without_shrinking_or_losing_characters(tmp_path: Path) -> None:
    from src.report import render_report

    result = read_json(BASELINE / "results/0500.json")
    name = "長い地層名称と砂礫を含む地層"
    soil_type = "砂質土と粘性土の互層を含む区分"
    result["layers"][0].update(name=name, soil_type=soil_type)
    path = tmp_path / "long-names.pdf"
    render_report(result, path)
    with pymupdf.open(path) as pdf:
        text = "".join(page.get_text() for page in pdf).replace("\n", "")
        assert text.count(name) == 1 and text.count(soil_type) == 1
        for page in pdf:
            body = [line.strip() for line in page.get_text().splitlines() if line.strip() and not line.startswith("5 -")]
            assert body[-1] not in ("・長期", "・短期")
            for direction, label in (("longitudinal", "線路方向"), ("transverse", "線路直角方向")):
                if label in page.get_text():
                    last_result = f"{result['short_term']['Kr_' + direction]:,.0f}"
                    assert last_result in page.get_text().replace(" ", "")
        samples = [span for page in pdf for block in page.get_text("dict")["blocks"]
                   for line in block.get("lines", []) for span in line["spans"]]
        assert all(span["size"] == pytest.approx(9.9, abs=.1)
                   for span in samples if span["text"] and span["text"] in name)


def test_unbreakable_numeric_overflow_preserves_previous_target(tmp_path: Path) -> None:
    from gridlayoutpdf import LayoutError
    from src.report import render_report

    result = read_json(BASELINE / "results/0500.json")
    result["layers"][0]["thickness"] = 1e100
    path = tmp_path / "previous.pdf"
    path.write_bytes(b"previous-published-bytes")
    with pytest.raises(LayoutError):
        render_report(result, path)
    assert path.read_bytes() == b"previous-published-bytes"


def test_manuscript_uses_structured_fraction_root_script_and_double_values() -> None:
    from gridlayoutpdf import Fraction, Root, Script
    from src.reporting.stages.foundation import content, semantic_records

    def classes(value: Any) -> set[type]:
        found = {type(value)}
        if is_dataclass(value):
            for field in fields(value):
                found.update(classes(getattr(value, field.name)))
        elif isinstance(value, (tuple, list)):
            for item in value:
                found.update(classes(item))
        return found

    result = read_json(BASELINE / "results/0500.json")
    assert {Fraction, Root, Script} <= classes(content(result))
    expected = semantic_records(result)
    result["macro_handoff_single"] = {"sentinel": -1234567}
    assert semantic_records(result) == expected


def test_source_semantic_units_reach_native_pdf_and_vectors(tmp_path: Path) -> None:
    from gridlayoutpdf import render_pdf
    from src.reporting.stages.foundation import build_report

    result = read_json(BASELINE / "results/0500.json")
    document = build_report(result)
    pages = document.layout()
    path = tmp_path / "native.pdf"
    render_pdf(pages, path, document.fonts)
    audit = audit_foundation_native(read_json(REFERENCE), result, document, pages, path)
    assert len(audit["records"]) == 70
    assert audit["native_glyph_count"] > 1400
    assert all(record["native_glyph_ids"] for record in audit["records"])


@pytest.mark.parametrize("mutation", ["numeric_glyph", "root_vector"])
def test_native_audit_rejects_actual_pdf_content_loss(tmp_path: Path, mutation: str) -> None:
    from gridlayoutpdf import Polyline, Text, render_pdf
    from src.reporting.stages.foundation import build_report

    result = read_json(BASELINE / "results/0500.json")
    document = build_report(result)
    pages = document.layout()
    commands = list(pages[0].commands)
    if mutation == "root_vector":
        index = next(index for index, item in enumerate(commands) if isinstance(item, Polyline))
        commands.pop(index)
    else:
        index = next(index for index, item in enumerate(commands) if isinstance(item, Text) and item.text == "202988")
        commands[index] = replace(commands[index], text="209288")
    damaged = (replace(pages[0], commands=tuple(commands)), *pages[1:])
    path = tmp_path / "changed.pdf"
    render_pdf(damaged, path, document.fonts)
    with pytest.raises(SemanticMismatch, match="native"):
        audit_foundation_native(read_json(REFERENCE), result, document, pages, path)


@pytest.mark.parametrize("mutation", ["factor", "unit", "root", "fraction"])
def test_manuscript_audit_rejects_loss_shared_by_scene_and_pdf(tmp_path: Path, mutation: str) -> None:
    from gridlayoutpdf import Line, Polyline, Text, render_pdf
    from src.reporting.stages.foundation import build_report

    result = read_json(BASELINE / "results/0500.json")
    document = build_report(result)
    pages = document.layout()
    page_index = 1 if mutation == "fraction" else 0
    commands = list(pages[page_index].commands)
    if mutation in ("factor", "unit"):
        target = "165760" if mutation == "factor" else "kN/m"
        index = next(index for index, item in enumerate(commands) if isinstance(item, Text) and item.text == target)
    else:
        vector_type = Polyline if mutation == "root" else Line
        index = next(index for index, item in enumerate(commands)
                     if isinstance(item, vector_type) and item.width == pytest.approx(.495))
    commands.pop(index)
    damaged = tuple(replace(page, commands=tuple(commands)) if index == page_index else page
                    for index, page in enumerate(pages))
    path = tmp_path / "scene-and-pdf-missing.pdf"
    render_pdf(damaged, path, document.fonts)
    with pytest.raises(SemanticMismatch, match="manuscript/scene"):
        audit_foundation_native(read_json(REFERENCE), result, document, damaged, path)


def test_current_native_typography_and_table_match_independent_reference_roles(tmp_path: Path) -> None:
    from gridlayoutpdf import render_pdf
    from reportlab.pdfbase.ttfonts import TTFont
    from src.reporting.stages.foundation import build_report
    from reporting_appearance import monochrome_errors, native_rules, painted_rule_bands, role_errors, table_errors, text_samples

    result = read_json(BASELINE / "results/0500.json")
    reference = read_json(PROJECT / "tests/fixtures/reporting/appearance/reference-style.json")
    document = build_report(result)
    path = tmp_path / "appearance.pdf"
    render_pdf(document.layout(), path, document.fonts)
    faces = {TTFont(f"verify-{name}", str(face.path), subfontIndex=face.face_index).face.name.decode("ascii"): face
             for name in ("body", "heading") for face in (document.fonts.resolve(name),)}
    with pymupdf.open(path) as pdf:
        samples = [sample for page in pdf for sample in text_samples(page)]
        for role_name in ("chapter", "section", "body", "subsection", "subsubsection",
                          "table_header", "table_header_compressive", "table_value",
                          "symbolic_equals", "substitution_equals", "result_equals"):
            role = reference["roles"]["foundation." + role_name]
            selector = role["source"]["selector_exact_text"]
            if role_name == "table_value":
                selector = f"{result['layers'][0]['thickness']:.3f}"
            matches = [sample for sample in samples if sample.text.startswith(selector)]
            if "equals" in role_name:
                target = role["source"]["selector_x_pt"]
                matches = [sample for sample in matches if abs(sample.x - target) < .5]
            assert matches, role_name
            sample = matches[0]
            face = faces[role["font"]]
            assert len(sample.font) >= 20 and face.pdf_name.startswith(sample.font)
            assert role_errors(replace(sample, font=role["font"]), role, anchor_x=93.96) == [], role_name
        normal_header = next(sample for sample in samples if sample.text == "層番")
        assert role_errors(replace(normal_header, font="MS-Gothic", size=8.9),
                           reference["roles"]["foundation.table_header"])
        compressive = next(sample for sample in samples if sample.text == "一軸圧縮強度")
        assert role_errors(replace(compressive, font="MS-Gothic", size=9.9),
                           reference["roles"]["foundation.table_header_compressive"])
        unit = next(sample for sample in samples if sample.text == "qu(kN/m")
        assert unit.size == pytest.approx(9.9, abs=.1)
        suffix = next(sample for sample in samples if sample.text == "2" and sample.page == unit.page
                      and abs(sample.baseline - unit.baseline + 4.92) < .06 and 0 < sample.x - unit.x < 50)
        assert suffix.size == pytest.approx(6.5, abs=.1)
        rules = native_rules(pdf[0])
        vertical = [rule for rule in rules if rule.axis == "v" and abs(rule.coordinate - 76.92) <= .5]
        assert vertical
        bands = [band for band in painted_rule_bands(rules, axis="h", crossing=310)
                 if min(rule.start for rule in vertical) - .5 <= band.coordinate <= max(rule.end for rule in vertical) + .5]
        bounds = [band.coordinate for band in bands]
        contract = reference["tables"]["foundation.soil"]
        assert table_errors(bounds, [contract["nominal_row_height_pt"]] * (2 + len(result["layers"]))) == []
        assert {round(rule.width, 2) for rule in rules if rule.axis == "v"} == {0.12, 0.96}
        assert bands[0].width == pytest.approx(contract["thick_rule_pt"], abs=.001)
        assert bands[-1].width == pytest.approx(contract["thick_rule_pt"], abs=.001)
        assert bands[1].width == pytest.approx(contract["thin_rule_pt"], abs=.001)
        # Public Table draws shared part boundaries separately. Preserve and
        # report the actual .24pt union; never claim it equals the source .12.
        assert all(band.width == pytest.approx(2 * contract["thin_rule_pt"], abs=.001)
                   for band in bands[2:-1])
        assert all(monochrome_errors(page) == [] for page in pdf)
