"""0720 bearing-equation, source semantic and native migration gates."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
from typing import Any

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from reporting_semantic_audit import SemanticMismatch, compare_semantics, reference_text, validate_source_coverage
from reporting_seismic_audit import audit_seismic_native, _ownership

BASELINE = ROOT / "tests/fixtures/reporting/baseline"
REFERENCE = ROOT / "tests/fixtures/reporting/semantic/0720.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def stage_module():
    assert (ROOT / "src/reporting/stages/seismic_transverse.py").is_file(), "0720 native stage is not implemented"
    return importlib.import_module("src.reporting.stages.seismic_transverse")


def test_old_0720_meaning_map_covers_every_source_span_once() -> None:
    reference = read_json(REFERENCE)
    source = BASELINE / "display/0720.json"
    assert reference["source_display_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    validate_source_coverage(reference, read_json(source))
    assert len(reference["records"]) == 71
    assert sum(len(row["source_ids"]) for row in reference["records"]) == 196


@pytest.mark.parametrize("change", ["sign", "factor-order", "arm", "unit", "bearing-order", "missing-bearing"])
def test_0720_meaning_gate_rejects_loss_or_reordering_of_bearing_formulas(change: str) -> None:
    reference = read_json(REFERENCE)
    actual = [{"id": row["id"], "text": reference_text(row)} for row in reference["records"]]
    index = next(i for i, row in enumerate(actual) if row["id"] == "0720/train.up.row.B.1")
    row = actual[index]
    if change == "sign":
        row["text"] = row["text"].replace("-0.020", "0.020")
    elif change == "factor-order":
        row["text"] = row["text"].replace("320.00 × -0.020", "-0.020 × 320.00")
    elif change == "arm":
        row["text"] = row["text"].replace("-3.800", "-2.950")
    elif change == "unit":
        row = next(row for row in actual if row["id"] == "0720/girder.B.moment")
        row["text"] = row["text"].replace("kN・m", "kN")
    elif change == "bearing-order":
        actual[index], actual[index + 1] = actual[index + 1], actual[index]
    else:
        actual.pop(index)
    with pytest.raises(SemanticMismatch):
        compare_semantics(reference, actual)


def test_0720_new_stage_preserves_all_old_meaning_and_snapshot() -> None:
    module = stage_module()
    result = read_json(BASELINE / "results/0720.json")
    before = deepcopy(result)
    compare_semantics(read_json(REFERENCE), module.semantic_records(result))
    assert module.build_report(result).layout()
    assert result == before


def test_0720_native_semantics_keep_all_40_bearing_equations_and_own_arms() -> None:
    module = stage_module()
    from test_seismic_transverse_report import calculated

    def expanded(dead):
        return {side: tuple(replace(bearing, position=index + (.125 if side == "c" else 0))
                            for index, bearing in enumerate(getattr(dead, side)))
                for side in ("b", "c")}

    result = calculated(bearings=expanded)
    records = [row for row in module.semantic_records(result) if "/train." in row["id"] and ".row." in row["id"]]
    expected = [(track, row) for track in ("up", "down") for row in result["vertical"]["train"][track]["rows"]]
    assert len(records) == len(expected) == 40
    for record, (track, row) in zip(records, expected, strict=True):
        assert record["id"] == f"0720/train.{track}.row.{row['side']}.{row['bearing']}"
        numbers = re.findall(r"-?\d+(?:\.\d+)?", record["text"])
        bearing, source, rate, force, arm, moment = map(Decimal, numbers)
        assert bearing == row["bearing"]
        assert arm == Decimal(str(row["arm"]))
        assert force == Decimal(f"{row['N']:.2f}")
        assert moment == Decimal(f"{row['M']:.2f}")
        assert (source * rate).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) == force
        assert (source * rate * arm).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) == moment


def test_0720_public_render_uses_native_flow_with_chapter_page_numbers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    public = importlib.import_module("src.seismic_transverse_report")

    def forbidden_canvas(*args: Any, **kwargs: Any) -> None:
        pytest.fail("0720 still invokes the old fixed-page Canvas")

    monkeypatch.setattr(public, "Canvas", forbidden_canvas, raising=False)
    target = tmp_path / "0720.pdf"
    public.render_seismic_transverse_report(read_json(BASELINE / "results/0720.json"), target)
    with pymupdf.open(target) as pdf:
        assert len(pdf) > 0
        whole = "".join(page.get_text() for page in pdf)
        for heading in ("11.1 検討モデル", "11.2 作用の計算", "11.3 作用の組合せ"):
            assert heading in whole
        for index, page in enumerate(pdf, 1):
            assert f"11 - {index}" in page.get_text()
            assert not page.get_images()
            assert all(span["color"] == 0 for block in page.get_text("dict")["blocks"]
                       for line in block.get("lines", []) for span in line["spans"])


def test_0720_source_units_reach_actual_pdf_glyphs_and_physical_vectors(tmp_path: Path) -> None:
    module = stage_module()
    result = read_json(BASELINE / "results/0720.json")
    document = module.build_report(result)
    pages = document.layout()
    target = tmp_path / "native.pdf"
    module.render_pdf(pages, target, document.fonts)
    audit = audit_seismic_native(read_json(REFERENCE), result, document, pages, target)
    assert len(audit["records"]) == 71
    assert audit["physical_graph"]["node_count"] == 8
    assert all(record["source_ids"] and record["native_glyph_ids"] for record in audit["records"])


def test_0720_correct_ledger_cannot_hide_a_bearing_formula_removed_from_both_scene_and_pdf(tmp_path: Path) -> None:
    from gridlayoutpdf import Text

    module = stage_module()
    result = read_json(BASELINE / "results/0720.json")
    document = module.build_report(result)
    pages = document.layout()
    corrupt = []
    changed = False
    for page in pages:
        commands = []
        for command, owner in zip(page.commands, _ownership(page), strict=True):
            if owner == "0720/train.up.row.B.1" and isinstance(command, Text) and command.text == "320.00":
                command = replace(command, text="")
                changed = True
            commands.append(command)
        corrupt.append(replace(page, commands=tuple(commands)))
    assert changed
    compare_semantics(read_json(REFERENCE), module.semantic_records(result))
    target = tmp_path / "missing-bearing-formula.pdf"
    module.render_pdf(corrupt, target, document.fonts)
    with pytest.raises(SemanticMismatch, match="manuscript/scene mismatch"):
        audit_seismic_native(read_json(REFERENCE), result, document, corrupt, target)
