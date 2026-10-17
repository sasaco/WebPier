"""0610 content is audited against frozen original spans before native rollout."""

from __future__ import annotations

from copy import deepcopy
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.reporting_semantic_audit import (
    SemanticMismatch, compare_semantics, reference_text, validate_source_coverage,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/reporting"


def read(path: str) -> Any:
    return json.loads((FIXTURES / path).read_text("utf-8"))


def test_all_old_spans_are_mapped_and_only_document_title_is_repeated() -> None:
    reference, source = read("semantic/0610.json"), read("baseline/display/0610.json")
    validate_source_coverage(reference, source)
    assert sum(len(row["source_ids"]) for row in reference["records"]) == 1015
    headers = [row for row in reference["records"] if row["role"] == "repeated_header"]
    assert len(headers) == 1 and len(headers[0]["source_ids"]) == 7
    assert headers[0]["source_text"] == headers[0]["text"] * 7
    assert headers[0]["render_contract"]["count_per_page"] == 1
    assert [row["id"] for row in reference["records"] if row["role"] == "body"] == [
        "0610/" + name for name in ("model", "conditions", "dead_water", "snow_train",
                                    "impact_horizontal", "definitions", "matrix", "extractions")]


@pytest.mark.parametrize("mutation", ("sign", "factor", "order", "unit", "omission", "header_exemption"))
def test_independent_semantic_ledger_rejects_drift(mutation: str) -> None:
    reference = read("semantic/0610.json")
    if mutation == "header_exemption":
        reference["records"][0]["source_ids"].append(reference["records"][1]["source_ids"].pop())
        with pytest.raises(SemanticMismatch):
            validate_source_coverage(reference, read("baseline/display/0610.json"))
        return
    reference["records"] = [row for row in reference["records"] if row["role"] == "body"]
    actual = [{"id": row["id"], "text": reference_text(row)} for row in reference["records"]]
    if mutation == "order":
        actual[0], actual[1] = actual[1], actual[0]
    elif mutation == "omission":
        actual.pop()
    else:
        target = next(row for row in actual if row["id"] == "0610/dead_water")
        before, after = {"sign": ("−", "+"), "factor": ("297.68", "297.69"), "unit": ("kN/m", "N/m")}[mutation]
        assert before in target["text"]
        target["text"] = target["text"].replace(before, after, 1)
    with pytest.raises(SemanticMismatch):
        compare_semantics(reference, actual)


def test_native_stage_retains_all_ordered_body_content_without_recalculation() -> None:
    path = ROOT / "src/reporting/stages/longitudinal.py"
    assert path.is_file(), "native 0610 stage is not implemented"
    stage = importlib.import_module("src.reporting.stages.longitudinal")
    result = read("baseline/results/0610.json")
    before = deepcopy(result)
    reference = read("semantic/0610.json")
    reference["records"] = [row for row in reference["records"] if row["role"] == "body"]
    compare_semantics(reference, stage.semantic_records(result))
    assert result == before


def test_native_stage_renders_complete_variable_pages_without_bitmap_body(tmp_path: Path) -> None:
    import pymupdf
    stage = importlib.import_module("src.reporting.stages.longitudinal")
    result = read("baseline/results/0610.json")
    document = stage.build_report(result)
    pages = document.layout()
    assert len(pages) > 1
    path = tmp_path / "0610.pdf"
    stage.render(result, path)
    with pymupdf.open(path) as pdf:
        assert len(pdf) == len(pages)
        for index, page in enumerate(pdf, 1):
            assert not page.get_images()
            assert page.get_text().count("0610 線路方向荷重") == 1
            assert f"8-{index}" in page.get_text()
        text = "".join(page.get_text() for page in pdf)
        assert "組合せケースの対応" in text and "S30" in text


def test_short_tables_and_matrix_introduction_stay_with_their_content() -> None:
    stage = importlib.import_module("src.reporting.stages.longitudinal")
    result = read("baseline/results/0610.json")
    units = stage.content(result)
    pages = stage.build_report(result).layout()
    owners: dict[str, set[int]] = {}
    for number, page in enumerate(pages, 1):
        for placement in page.metadata["placements"]:
            owners.setdefault(placement["block_id"], set()).add(number)
    for unit in units:
        if unit.kind == "table":
            assert len(owners[unit.identifier]) == 1, unit.identifier
    intro = [unit for unit in units if unit.section == "0610/matrix"][:4]
    assert len(set.union(*(owners[unit.identifier] for unit in intro))) == 1
    for index, unit in enumerate(units):
        if unit.section == "0610/dead_water" and unit.value in ("高水位", "平水位", "低水位"):
            assert len(set.union(*(owners[part.identifier] for part in units[index:index + 3]))) == 1


def test_actual_native_audit_covers_every_authored_unit(tmp_path: Path) -> None:
    path = ROOT / "scripts/reporting_frame_audit.py"
    assert path.is_file(), "frame source/manuscript/scene/native audit is missing"
    audit = importlib.import_module("scripts.reporting_frame_audit")
    from gridlayoutpdf import render_pdf
    stage = importlib.import_module("src.reporting.stages.longitudinal")
    result = read("baseline/results/0610.json")
    document = stage.build_report(result)
    pages = document.layout()
    output = tmp_path / "0610.pdf"
    render_pdf(pages, output, document.fonts)
    proof = audit.audit_frame_native(read("semantic/0610.json"), result, document, pages, output)
    assert proof["native_glyph_count"] > 1000
    assert {row["id"] for row in proof["units"]} == {unit.identifier for unit in stage.content(result)}
    assert sum(len(row["source_ids"]) for row in proof["records"]) == 1015
