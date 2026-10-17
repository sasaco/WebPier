"""0620 independent full-content ledger, including every case coefficient."""

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


def body_reference() -> dict[str, Any]:
    reference = read("semantic/0620.json")
    reference["records"] = [record for record in reference["records"] if record["role"] == "body"]
    return reference


def test_all_old_spans_are_mapped_with_only_exact_page_counter_exception() -> None:
    reference = read("semantic/0620.json")
    validate_source_coverage(reference, read("baseline/display/0620.json"))
    assert sum(len(row["source_ids"]) for row in reference["records"]) == 1583
    assert len(reference["records"]) == 13
    counters = [row for row in reference["records"] if row["role"] == "page_counter"]
    assert len(counters) == 1 and len(counters[0]["source_ids"]) == 12
    for item in counters[0]["source_locations"]:
        assert item["bbox"][2] == pytest.approx(547, abs=.01)
        assert item["origin"][1] == 815 and item["size"] == 7


@pytest.mark.parametrize("mutation", ("sign", "factor", "order", "unit", "omission", "case_duplicate"))
def test_independent_semantic_ledger_rejects_drift(mutation: str) -> None:
    reference = body_reference()
    actual = [{"id": row["id"], "text": reference_text(row)} for row in reference["records"]]
    if mutation == "order":
        actual[0], actual[1] = actual[1], actual[0]
    elif mutation == "omission":
        actual.pop()
    elif mutation == "case_duplicate":
        actual[-2] = deepcopy(actual[-3])
    else:
        target = next(row for row in actual if row["id"] == "0620/water_snow")
        before, after = {"sign": ("−10", "+10"), "factor": ("7.00", "7.01"), "unit": ("kN", "MN")}[mutation]
        assert before in target["text"]
        target["text"] = target["text"].replace(before, after, 1)
    with pytest.raises(SemanticMismatch):
        compare_semantics(reference, actual)


def test_native_stage_retains_all_ordered_body_content_without_recalculation() -> None:
    path = ROOT / "src/reporting/stages/transverse.py"
    assert path.is_file(), "native 0620 stage is not implemented"
    stage = importlib.import_module("src.reporting.stages.transverse")
    result = read("baseline/results/0620.json")
    before = deepcopy(result)
    compare_semantics(body_reference(), stage.semantic_records(result))
    assert result == before


def test_native_stage_renders_all_pages_with_actual_footer_sequence(tmp_path: Path) -> None:
    import pymupdf
    stage = importlib.import_module("src.reporting.stages.transverse")
    result = read("baseline/results/0620.json")
    document = stage.build_report(result)
    pages = document.layout()
    path = tmp_path / "0620.pdf"
    stage.render(result, path)
    with pymupdf.open(path) as pdf:
        assert len(pdf) == len(pages) > 1
        for index, page in enumerate(pdf, 1):
            assert not page.get_images()
            footer = page.get_text(clip=pymupdf.Rect(48, 800, 576, 842)).strip()
            assert footer.endswith(str(index))
            assert footer.count("0620 直角方向荷重") == 1


def test_actual_native_audit_covers_every_authored_unit(tmp_path: Path) -> None:
    path = ROOT / "scripts/reporting_frame_audit.py"
    assert path.is_file(), "frame source/manuscript/scene/native audit is missing"
    audit = importlib.import_module("scripts.reporting_frame_audit")
    from gridlayoutpdf import render_pdf
    stage = importlib.import_module("src.reporting.stages.transverse")
    result = read("baseline/results/0620.json")
    document = stage.build_report(result)
    pages = document.layout()
    output = tmp_path / "0620.pdf"
    render_pdf(pages, output, document.fonts)
    proof = audit.audit_frame_native(read("semantic/0620.json"), result, document, pages, output)
    assert proof["native_glyph_count"] > 1000
    assert {row["id"] for row in proof["units"]} == {unit.identifier for unit in stage.content(result)}
    assert sum(len(row["source_ids"]) for row in proof["records"]) == 1583


def test_wind_condition_and_matrix_rows_preserve_the_reference_rhythm() -> None:
    stage = importlib.import_module("src.reporting.stages.transverse")
    result = read("baseline/results/0620.json")
    units = stage.content(result)
    pages = stage.build_report(result).layout()
    owners: dict[str, set[int]] = {}
    for number, page in enumerate(pages, 1):
        for placement in page.metadata["placements"]:
            owners.setdefault(placement["block_id"], set()).add(number)
            if placement["block_id"].startswith("0620/combinations/"):
                for part in placement["parts"]:
                    for allocation in part["metadata"].get("row_allocations", []):
                        assert allocation["allocated_height_pt"] == pytest.approx(12.84, abs=.12)
    wind = [unit for unit in units if unit.section == "0620/wind_unloaded"]
    assert len(set.union(*(owners[unit.identifier] for unit in wind))) == 1
