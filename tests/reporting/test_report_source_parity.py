"""Independent old-output baselines; no new report builder creates expectations."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from scripts.reporting_baseline import (
    BaselineMismatch, STAGES, assert_records_equal, canonical, extract_pdf_records,
    file_sha256, read_json, result_records, verify_fixture, write_json,
)


BASELINE = Path(__file__).resolve().parents[1] / "fixtures/reporting/baseline"


@pytest.fixture(scope="module")
def calculated() -> dict:
    from src.cli import _calculate_stages

    raw = (BASELINE / "input.json").read_bytes()
    return _calculate_stages(read_json(BASELINE / "input.json"), STAGES, "input.json",
                             hashlib.sha256(raw).hexdigest())


def test_baseline_file_set_and_bytes_are_unchanged() -> None:
    manifest = verify_fixture(BASELINE)
    assert manifest["origin"] == "pre-migration old-code result/PDF capture"
    summary = read_json(BASELINE / "capture-summary.json")
    assert summary["published"] is False
    assert summary["no_candidate_destinations_published"] is True
    assert summary["frozen_source_drift_after_capture"] == []
    assert summary["protected_original_drift_after_capture"] == []


@pytest.mark.parametrize("stage", STAGES)
def test_every_current_calculation_leaf_matches_old_result(stage: str, calculated: dict) -> None:
    expected = read_json(BASELINE / "result-records" / f"{stage}.json")
    assert_records_equal(expected, result_records(stage, calculated[stage]))
    assert canonical(calculated[stage]) == canonical(read_json(BASELINE / "results" / f"{stage}.json"))


@pytest.mark.parametrize("stage", STAGES)
def test_every_native_old_pdf_span_has_exactly_one_stable_record(stage: str) -> None:
    expected = read_json(BASELINE / "display" / f"{stage}.json")
    actual = extract_pdf_records(BASELINE / "pdfs" / f"{stage}.pdf", stage)
    assert actual == expected
    records = expected["body"] + expected["decorations"]
    assert {row["id"] for row in records} == {row["id"] for row in expected["locations"]}
    assert len(records) == len(expected["locations"])
    assert all(page["width"] == 595 and page["height"] == 842 for page in expected["pages"])


def test_all_reaction_display_values_keep_double_and_single_boundaries(calculated: dict) -> None:
    from src.reaction_report_values import build_display_values

    expected = read_json(BASELINE / "reaction-display.json")
    before = canonical(calculated["0600"])
    assert canonical(build_display_values(calculated["0600"])) == canonical(expected["values"])
    assert canonical(calculated["0600"]["public_values"]) == canonical(expected["public_values_double"])
    assert canonical(calculated["0600"]["macro_handoff_single"]) == canonical(expected["macro_handoff_single"])
    assert canonical(calculated["0600"]["cells"]) == canonical(expected["result_cells_double"])
    assert canonical(calculated["0600"]) == before
    changed_handoff = deepcopy(calculated["0600"])
    changed_handoff["macro_handoff_single"] = {"sentinel": 987654321.123}
    assert canonical(build_display_values(changed_handoff)) == canonical(expected["values"])


def test_reaction_cell_formats_captions_and_formula_dependencies_are_frozen() -> None:
    from src.reaction_report_layout import format_value, load_layout

    expected = read_json(BASELINE / "reaction-display.json")
    layout = load_layout()
    assert layout["formulas"] == expected["formulas"]
    assert layout["constants"] == expected["constants"]
    ids = [row["id"] for row in expected["formatted_cells"]]
    assert len(ids) == len(set(ids))
    assert len(expected["values"]) == 5
    for cell in expected["formatted_cells"]:
        assert format_value(cell["value"], cell["number_format"]) == cell["formatted"], cell["id"]


def test_frameweb_native_meaning_matches_before_pdf_migration(calculated: dict) -> None:
    from src.frameweb_export import build_frameweb_input

    for stage in ("0610", "0620"):
        actual = build_frameweb_input(calculated[stage]).document
        expected = read_json(BASELINE / f"{stage}-native.json")
        assert canonical(actual) == canonical(expected)


def test_record_guard_rejects_reordered_rows() -> None:
    expected = read_json(BASELINE / "display/0600.json")["body"]
    changed = deepcopy(expected)
    changed[4], changed[5] = changed[5], changed[4]
    with pytest.raises(BaselineMismatch, match="differs"):
        assert_records_equal(expected, changed)


def test_record_guard_rejects_sign_change() -> None:
    expected = read_json(BASELINE / "result-records/0710.json")
    changed = deepcopy(expected)
    row = next(row for row in changed if row["kind"] == "number" and row["value"] < 0)
    row["value"] = -row["value"]
    with pytest.raises(BaselineMismatch, match="differs"):
        assert_records_equal(expected, changed)


def test_record_guard_rejects_missing_formula_factor() -> None:
    expected = read_json(BASELINE / "result-records/0720.json")
    changed = deepcopy(expected)
    index = next(index for index, row in enumerate(changed) if "/formulas/" in row["id"] and "/factors/" in row["id"])
    del changed[index]
    with pytest.raises(BaselineMismatch, match="record count"):
        assert_records_equal(expected, changed)


def test_record_guard_rejects_changed_printed_unit() -> None:
    expected = read_json(BASELINE / "display/0710.json")["body"]
    changed = deepcopy(expected)
    row = next(row for row in changed if "kN" in row["text"])
    row["text"] = row["text"].replace("kN", "MN", 1)
    with pytest.raises(BaselineMismatch, match="differs"):
        assert_records_equal(expected, changed)


def test_record_guard_rejects_duplicate_id_and_same_count_omission() -> None:
    expected = read_json(BASELINE / "display/0610.json")["body"]
    changed = deepcopy(expected)
    changed[5] = deepcopy(changed[4])
    with pytest.raises(BaselineMismatch, match="duplicate stable IDs"):
        assert_records_equal(expected, changed)


def test_result_paths_preserve_array_order_zero_null_and_empty_types() -> None:
    expected = result_records("test", {"a/b": [None, 0, -0.25], "~empty": [], "obj": {}})
    assert [row["id"] for row in expected] == [
        "test/result/a~1b/0", "test/result/a~1b/1", "test/result/a~1b/2",
        "test/result/obj", "test/result/~0empty",
    ]
    for value in ({"a/b": [0, None, -0.25], "~empty": [], "obj": {}},
                  {"a/b": [None, 0, -0.25], "~empty": {}, "obj": {}}):
        with pytest.raises(BaselineMismatch):
            assert_records_equal(expected, result_records("test", value))


@pytest.mark.parametrize("mutation", ["changed", "missing", "extra"])
def test_frozen_fixture_rejects_tampered_missing_and_extra_files(tmp_path: Path, mutation: str) -> None:
    data = tmp_path / "expected.json"
    write_json(data, {"value": -123.45, "unit": "kN"})
    write_json(tmp_path / "manifest.json", {"files": [{"path": "expected.json", "sha256": file_sha256(data)}]})
    verify_fixture(tmp_path)
    if mutation == "changed":
        data.write_text('{"value":123.45,"unit":"kN"}', encoding="utf-8")
    elif mutation == "missing":
        data.unlink()
    else:
        (tmp_path / "unexpected.json").write_text("{}", encoding="utf-8")
    with pytest.raises(BaselineMismatch, match="fixture"):
        verify_fixture(tmp_path)
