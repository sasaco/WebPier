"""0710 source-derived semantic migration gate, independent of page count."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from reporting_semantic_audit import SemanticMismatch, compare_semantics, reference_text, validate_source_coverage
from reporting_seismic_audit import audit_seismic_native, _ownership

BASELINE = ROOT / "tests/fixtures/reporting/baseline"
REFERENCE = ROOT / "tests/fixtures/reporting/semantic/0710.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def stage_module():
    assert (ROOT / "src/reporting/stages/seismic_longitudinal.py").is_file(), "0710 native stage is not implemented"
    return importlib.import_module("src.reporting.stages.seismic_longitudinal")


def test_old_0710_meaning_map_covers_every_source_span_once() -> None:
    reference = read_json(REFERENCE)
    source = BASELINE / "display/0710.json"
    assert reference["source_display_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    validate_source_coverage(reference, read_json(source))
    assert len(reference["records"]) == 44
    assert sum(len(row["source_ids"]) for row in reference["records"]) == 137


@pytest.mark.parametrize("change", ["sign", "factor-order", "unit", "case-order", "missing"])
def test_0710_meaning_gate_rejects_formula_and_order_changes(change: str) -> None:
    reference = read_json(REFERENCE)
    actual = [{"id": row["id"], "text": reference_text(row)} for row in reference["records"]]
    row = next(row for row in actual if row["id"] == "0710/inertia.footing")
    if change == "sign":
        row["text"] = row["text"].replace("-", "+")
    elif change == "factor-order":
        row["text"] = row["text"].replace("7.00 × 9.00", "9.00 × 7.00")
    elif change == "unit":
        row["text"] = row["text"].replace("kN", "N")
    elif change == "case-order":
        first = next(i for i, row in enumerate(actual) if row["id"] == "0710/cases.row.1")
        actual[first], actual[first + 1] = actual[first + 1], actual[first]
    else:
        actual.pop()
    with pytest.raises(SemanticMismatch):
        compare_semantics(reference, actual)


def test_0710_new_stage_preserves_all_old_meaning_and_snapshot() -> None:
    module = stage_module()
    result = read_json(BASELINE / "results/0710.json")
    before = deepcopy(result)
    compare_semantics(read_json(REFERENCE), module.semantic_records(result))
    document = module.build_report(result)
    assert document.layout()
    assert result == before


def test_0710_public_render_uses_native_flow_with_chapter_page_numbers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    public = importlib.import_module("src.seismic_longitudinal_report")

    def forbidden_canvas(*args: Any, **kwargs: Any) -> None:
        pytest.fail("0710 still invokes the old fixed-page Canvas")

    monkeypatch.setattr(public, "Canvas", forbidden_canvas, raising=False)
    target = tmp_path / "0710.pdf"
    public.render_seismic_longitudinal_report(read_json(BASELINE / "results/0710.json"), target)
    with pymupdf.open(target) as pdf:
        assert len(pdf) > 0
        whole = "".join(page.get_text() for page in pdf)
        for heading in ("10.1 検討モデル", "10.2 作用の計算", "10.3 作用の組合せ"):
            assert heading in whole
        for index, page in enumerate(pdf, 1):
            assert f"10 - {index}" in page.get_text()
            assert not page.get_images()
            assert all(span["color"] == 0 for block in page.get_text("dict")["blocks"]
                       for line in block.get("lines", []) for span in line["spans"])


def test_0710_source_units_reach_actual_pdf_glyphs_and_physical_vectors(tmp_path: Path) -> None:
    module = stage_module()
    result = read_json(BASELINE / "results/0710.json")
    document = module.build_report(result)
    pages = document.layout()
    target = tmp_path / "native.pdf"
    module.render_pdf(pages, target, document.fonts)
    audit = audit_seismic_native(read_json(REFERENCE), result, document, pages, target)
    assert len(audit["records"]) == 44
    assert audit["physical_graph"]["node_count"] == 7
    assert all(record["source_ids"] and record["native_glyph_ids"] for record in audit["records"])
    assert audit["appearance"]["actual_row_height_pt"] == pytest.approx(14.28, abs=.5)
    assert "common.chapter" in audit["appearance"]["roles"]


@pytest.mark.parametrize("omission", ["factor", "unit"])
def test_0710_correct_semantic_ledger_cannot_hide_scene_and_pdf_omissions(tmp_path: Path, omission: str) -> None:
    from dataclasses import replace
    from gridlayoutpdf import Text

    module = stage_module()
    result = read_json(BASELINE / "results/0710.json")
    document = module.build_report(result)
    pages = document.layout()
    needle = "7.00 × 9.00" if omission == "factor" else " kN/m"
    changed = False
    corrupt = []
    for page in pages:
        commands = []
        for command in page.commands:
            if not changed and isinstance(command, Text) and needle in command.text:
                command = replace(command, text=command.text.replace(needle, "", 1))
                changed = True
            commands.append(command)
        corrupt.append(replace(page, commands=tuple(commands)))
    assert changed
    compare_semantics(read_json(REFERENCE), module.semantic_records(result))
    target = tmp_path / "omitted-in-scene-and-pdf.pdf"
    module.render_pdf(corrupt, target, document.fonts)
    with pytest.raises(SemanticMismatch, match="manuscript/scene mismatch"):
        audit_seismic_native(read_json(REFERENCE), result, document, corrupt, target)


@pytest.mark.parametrize("change", ["font", "indent", "equals", "row-height", "physical-member"])
def test_0710_source_consistent_output_still_rejects_style_and_geometry_drift(tmp_path: Path, change: str) -> None:
    from dataclasses import replace
    from gridlayoutpdf import Line, Text

    module = stage_module()
    result = read_json(BASELINE / "results/0710.json")
    document = module.build_report(result)
    pages = document.layout()
    changed = False
    corrupt = []
    for page in pages:
        owners = _ownership(page)
        row_bottoms = [command.y1 for command, owner in zip(page.commands, owners, strict=True)
                       if owner == "0710/cases.row.1" and isinstance(command, Line) and command.y1 == command.y2]
        row_bottom = max(row_bottoms) if row_bottoms else None
        commands = []
        for command, owner in zip(page.commands, owners, strict=True):
            if not changed and owner == "0710/title" and isinstance(command, Text) and change in ("font", "indent"):
                command = replace(command, style=replace(command.style, font="body")) if change == "font" else command.translated(1.1, 0)
                changed = True
            elif not changed and change == "equals" and owner == "0710/inertia.beam" and isinstance(command, Text) and command.text == "=":
                command = command.translated(1.1, 0)
                changed = True
            elif change == "row-height" and row_bottom is not None and isinstance(command, Line) and command.y1 == command.y2 and abs(command.y1 - row_bottom) < .25:
                command = command.translated(0, 1.1)
                changed = True
            elif not changed and change == "physical-member" and owner == "0710/frame.geometry" and isinstance(command, Line) and command.width == .8:
                command = replace(command, y2=command.y2 + 1)
                changed = True
            commands.append(command)
        corrupt.append(replace(page, commands=tuple(commands)))
    assert changed
    target = tmp_path / (change + ".pdf")
    module.render_pdf(corrupt, target, document.fonts)
    with pytest.raises(SemanticMismatch, match="appearance|physical member"):
        audit_seismic_native(read_json(REFERENCE), result, document, corrupt, target)
