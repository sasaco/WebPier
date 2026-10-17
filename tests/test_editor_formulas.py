"""Workbook formulas are readonly previews and refreshable JSON snapshots."""

from copy import deepcopy
import json
import math
from pathlib import Path
import sys

import pytest

from src import editor_model as model
from src.editor_gui import SUPPORT_POSITION_PATHS
from src.input_formulas import INPUT_FORMULAS, FORMULAS_BY_PATH, B9_PATH, SURFACE_THICKNESS_PATH
from test_editor_gui import app, field, paste_cells, pending_text, SOURCE


B7 = ("下部構造", "寸法", "側面", "B7")


@pytest.mark.parametrize("missing", [None, "missing"])
def test_document_keeps_explicit_asymmetric_f_and_fills_only_missing_f(tmp_path, missing):
    data = json.loads(SOURCE.read_text("utf-8"))
    origin, end = SUPPORT_POSITION_PATHS
    data["上部構造"]["起点側"]["桁長"]["L2"] = 0.575
    data["上部構造"]["終点側"]["桁長"]["L1"] = 0.375
    model.set_at(data, origin, 0.4)
    if missing == "missing":
        del data["上部構造"]["終点側"]["支承位置_f"]
    else:
        model.set_at(data, end, None)
    path = tmp_path / "input.json"
    path.write_bytes(model.encode(data))
    document = model.EditorDocument.open(path)
    assert model.get_at(document.data, origin) == 0.4
    assert model.get_at(document.data, end) == 0.55
    model.set_at(document.data, origin, 0.12345678901234567)
    model.set_at(document.data, end, 0.8265432109876543)
    document.save()
    reopened = model.EditorDocument.open(path)
    assert model.get_at(reopened.data, origin) == 0.12345678901234567
    assert model.get_at(reopened.data, end) == 0.8265432109876543
    assert not reopened.dirty


def test_finite_snapshot_does_not_overflow_when_rounded_for_display(tmp_path):
    data = json.loads(SOURCE.read_text("utf-8"))
    model.set_at(data, B7, sys.float_info.max)
    path = tmp_path / "input.json"
    path.write_bytes(model.encode(data))
    document = model.EditorDocument.open(path)
    assert math.isfinite(model.get_at(document.data, B9_PATH))
    assert document.dirty
    document.save()
    assert math.isfinite(model.get_at(model.EditorDocument.open(path).data, B9_PATH))


@pytest.mark.parametrize("mode", ["stale", "missing", "invalid"])
def test_document_refreshes_all_formula_snapshots_and_marks_migration_dirty(tmp_path, mode):
    data = json.loads(SOURCE.read_text("utf-8"))
    expected = deepcopy(data)
    for formula in INPUT_FORMULAS:
        owner = model.get_at(data, formula.path[:-1])
        if mode == "missing":
            del owner[formula.path[-1]]
        else:
            owner[formula.path[-1]] = 99999 if mode == "stale" else {"bad": True}
    path = tmp_path / "input.json"
    path.write_bytes(model.encode(data))
    document = model.EditorDocument.open(path)
    for formula in INPUT_FORMULAS:
        assert model.get_at(document.data, formula.path) == model.get_at(expected, formula.path)
    assert document.dirty
    document.save()
    assert not model.EditorDocument.open(path).dirty


def test_direct_save_normalizes_snapshots_atomically_and_preserves_noop(tmp_path, monkeypatch):
    path = tmp_path / "input.json"
    path.write_bytes(SOURCE.read_bytes())
    document = model.EditorDocument.open(path)
    before = path.read_bytes()
    assert not document.dirty
    assert document.save().backup is None
    assert path.read_bytes() == before
    model.set_at(document.data, B7, 0.75)
    original = deepcopy(document.data)
    saved, fingerprint = document._saved, document._fingerprint
    real_replace = model.os.replace
    monkeypatch.setattr(model.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("blocked")))
    with pytest.raises(OSError):
        document.save()
    assert document.data == original
    assert (document._saved, document._fingerprint) == (saved, fingerprint)
    assert path.read_bytes() == before
    monkeypatch.setattr(model.os, "replace", real_replace)
    document.save()
    assert model.get_at(model.EditorDocument.open(path).data, B9_PATH) == 0.75


@pytest.mark.parametrize("bad", ["0.5", True, {}, "missing"])
def test_invalid_source_clears_its_snapshot_without_inventing_parent_groups(tmp_path, bad):
    data = json.loads(SOURCE.read_text("utf-8"))
    if bad == "missing":
        del model.get_at(data, B7[:-1])[B7[-1]]
    else:
        model.set_at(data, B7, bad)
    path = tmp_path / "input.json"
    path.write_bytes(model.encode(data))
    document = model.EditorDocument.open(path)
    assert model.get_at(document.data, B9_PATH) is None
    document.save()
    assert model.get_at(model.EditorDocument.open(path).data, B9_PATH) is None
    minimal = {"schema_version": 1}
    path.write_bytes(model.encode(minimal))
    assert model.EditorDocument.open(path).data == minimal


@pytest.mark.parametrize("section", ["下部構造", "上部構造", "上部工反力", "地盤データ"])
def test_all_derived_cells_are_bound_but_readonly_and_not_editable_fields(app, section):
    app.select_path((section,))
    visible = {formula.path for formula in INPUT_FORMULAS
               if formula.path[0] == section and formula.path not in SUPPORT_POSITION_PATHS}
    assert visible <= app.grid_cells.keys()
    assert not visible.intersection(item.path for item in app.fields)
    for path in visible:
        cell = app.grid_cells[path]
        assert cell.sheet.MT.cell_options[(cell.row, cell.column)]["readonly"] is True


def test_dimension_preview_tracks_paste_undo_redo_and_keeps_document_unchanged(app):
    before = deepcopy(app.document.data)
    source, derived = app.grid_cells[B7], app.grid_cells[B9_PATH]
    paste_cells(app, source.sheet, "0.75", row=source.row, column=source.column)
    assert derived.get() == "0.75"
    assert app.document.data == before
    source.sheet.undo()
    assert float(derived.get()) == model.get_at(before, B7)
    assert not app.dirty
    source.sheet.redo()
    assert derived.get() == "0.75"
    assert app.save()
    assert model.get_at(model.EditorDocument.open(app.document.path).data, B9_PATH) == 0.75


def test_mixed_range_paste_changes_sources_and_keeps_formula_cell_derived(app):
    source, derived = app.grid_cells[B7], app.grid_cells[B9_PATH]
    before = deepcopy(app.document.data)
    paste_cells(app, source.sheet, "0.75\n6\n999", row=source.row, column=source.column)
    assert source.get() == "0.75"
    assert field(app, ("下部構造", "寸法", "側面", "B8")).text.get() == "6"
    assert derived.get() == "0.75"
    assert app.document.data == before
    source.sheet.undo()
    assert float(derived.get()) == model.get_at(before, B7)
    assert not app.dirty
    source.sheet.redo()
    assert derived.get() == "0.75"


@pytest.mark.parametrize("operation", ["paste", "delete", "cut"])
def test_readonly_formula_resists_range_operations(app, operation):
    cell = app.grid_cells[B9_PATH]
    before = cell.get()
    sheet = cell.sheet
    sheet.select_cell(cell.row, cell.column)
    if operation == "paste":
        paste_cells(app, sheet, "99999", row=cell.row, column=cell.column)
    elif operation == "cut":
        sheet.cut()
    else:
        sheet.delete()
    assert cell.get() == before
    assert not app.dirty


def test_superstructure_sources_update_the_correct_side_and_formula(app):
    app.select_path(("上部構造",))
    before = deepcopy(app.document.data)
    for side, l1, l2 in (("起点側", "0.6", "0.8"), ("終点側", "0.7", "0.9")):
        for key, value in (("L1", l1), ("L2", l2)):
            field(app, ("上部構造", side, "桁長", key)).text.set(value)
        for key, value in (("h1", "0.5"), ("h2", "0.7"), ("h3", "0.4")):
            field(app, ("上部構造", side, "高さ", key)).text.set(value)
        assert float(app.grid_cells[("上部構造", side, "高さ", "h4")].get()) == before["上部構造"][side]["高さ"]["h4"]
        assert float(app.grid_cells[("上部構造", side, "重心高_hs")].get()) == before["上部構造"][side]["重心高_hs"]
    for side in ("起点側", "終点側"):
        assert float(app.grid_cells[("上部構造", side, "支承位置_f")].get()) == before["上部構造"][side]["支承位置_f"]
    assert app.document.data == before


@pytest.mark.parametrize("side,attribute", [("起点側", "b"), ("終点側", "c")])
@pytest.mark.parametrize("value", [0, 0.8765432109876543])
def test_h4_is_editable_preserved_after_other_heights_and_saved_for_calculation(app, side, attribute, value):
    app.select_path(("上部構造",))
    path = ("上部構造", side, "高さ", "h4")
    other = "終点側" if side == "起点側" else "起点側"
    other_before = field(app, ("上部構造", other, "高さ", "h4")).text.get()
    target = field(app, path)
    cell = target.widget
    assert cell.sheet.MT.cell_options[(cell.row, cell.column)].get("readonly") is not True
    paste_cells(app, cell.sheet, str(value), row=cell.row, column=cell.column)
    for height, text in (("h1", "0.4"), ("h2", "0.8"), ("h3", "0.6")):
        field(app, ("上部構造", side, "高さ", height)).text.set(text)
    assert target.text.get() == str(value)
    assert field(app, ("上部構造", other, "高さ", "h4")).text.get() == other_before
    assert app.save()
    reopened = model.EditorDocument.open(app.document.path)
    assert model.get_at(reopened.data, path) == value
    from src.reaction_inputs import parse_reaction_input
    assert getattr(parse_reaction_input(reopened.data).spans, attribute).h4 == value
    app.select_path(("下部構造",))
    app.select_path(("上部構造",))
    assert field(app, path).parse() == value
    assert not app.dirty


def _girder_inertia(data):
    from src import calculate, parse_input
    from src.reaction_calculator import calculate_reactions
    from src.reaction_inputs import parse_reaction_input
    from src.transverse_calculator import calculate_transverse_legacy

    inputs = parse_reaction_input(data)
    reactions = calculate_reactions(inputs)
    transverse = calculate_transverse_legacy(inputs, calculate(parse_input(data)), reactions)
    aggregate = next(row for row in transverse["horizontal_aggregates"] if row["id"] == 7)
    return reactions["transverse"][6], (aggregate["H"], aggregate["M"])


@pytest.mark.parametrize("side", ["起点側", "終点側"])
@pytest.mark.parametrize("value", [0, 2.9520833333333334])
def test_hs_remains_editable_and_preserves_inertia_through_save_and_save_as(app, tmp_path, side, value):
    path = ("上部構造", side, "重心高_hs")
    model.set_at(app.document.data, path, value)
    expected = _girder_inertia(app.document.data)
    app.select_path(("上部構造",))
    target = field(app, path)
    assert target.parse() == value
    cell = target.widget
    assert cell.sheet.MT.cell_options[(cell.row, cell.column)].get("readonly") is not True
    for height, text in (("h1", "0.4"), ("h2", "0.8")):
        field(app, ("上部構造", side, "高さ", height)).text.set(text)
    assert target.parse() == value
    assert app.save()
    reopened = model.EditorDocument.open(app.document.path)
    assert model.get_at(reopened.data, path) == value
    assert _girder_inertia(reopened.data) == expected
    destination = tmp_path / "saved-as.json"
    reopened.save(destination)
    saved_as = model.EditorDocument.open(destination)
    assert model.get_at(saved_as.data, path) == value
    assert _girder_inertia(saved_as.data) == expected


def _current_transverse_actions(data):
    from src import calculate, parse_input
    from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
    from src.reaction_calculator import calculate_reactions
    from src.reaction_inputs import parse_reaction_input
    from src.transverse_calculator import calculate_transverse

    inputs = parse_reaction_input(data)
    transverse = calculate_transverse(
        inputs, calculate(parse_input(data)), calculate_reactions(inputs),
        design_conditions=parse_longitudinal_design_conditions(data),
    )
    return transverse["actions"], tuple(transverse["input"]["spans"][side]["hs"] for side in ("b", "c"))


def test_current_input_copy_preserves_inertia_after_editor_save_and_save_as(tmp_path):
    source = Path(__file__).resolve().parents[1] / "pre" / "input.json"
    before_bytes = source.read_bytes()
    copied = tmp_path / "current-input.json"
    copied.write_bytes(before_bytes)
    original = json.loads(before_bytes.decode("utf-8-sig"))
    expected = _girder_inertia(original)
    current_expected = _current_transverse_actions(original)
    document = model.EditorDocument.open(copied)
    document.save()
    reopened = model.EditorDocument.open(copied)
    assert _girder_inertia(reopened.data) == expected
    assert _current_transverse_actions(reopened.data) == current_expected
    destination = tmp_path / "current-saved-as.json"
    reopened.save(destination)
    saved_as = model.EditorDocument.open(destination).data
    assert _girder_inertia(saved_as) == expected
    assert _current_transverse_actions(saved_as) == current_expected
    assert source.read_bytes() == before_bytes


def test_h4_invalid_text_blocks_save_and_blank_is_preserved_without_fallback(app):
    app.select_path(("上部構造",))
    path = ("上部構造", "起点側", "高さ", "h4")
    before = deepcopy(app.document.data)
    target = field(app, path)
    target.text.set("broken")
    assert not app.save()
    assert app.document.data == before
    target.text.set("")
    assert app.save()
    reopened = model.EditorDocument.open(app.document.path)
    assert model.get_at(reopened.data, path) is None
    from src.inputs import InputError
    from src.reaction_inputs import parse_reaction_input
    with pytest.raises(InputError, match="上部構造.起点側.高さ.h4"):
        parse_reaction_input(reopened.data)


@pytest.mark.parametrize("side,other", [("起点側", "終点側"), ("終点側", "起点側")])
@pytest.mark.parametrize("text,expected", [("0.4", 0.55), ("0", 0.95), ("-0.2", 1.15)])
def test_support_position_updates_opposite_f_without_changing_lengths(app, side, other, text, expected):
    position = ("上部構造", side, "支承位置_f")
    opposite = ("上部構造", other, "支承位置_f")
    model.set_at(app.document.data, ("上部構造", "起点側", "桁長", "L2"), 0.575)
    model.set_at(app.document.data, ("上部構造", "終点側", "桁長", "L1"), 0.375)
    model.set_at(app.document.data, position, 0.12345678901234567)
    model.set_at(app.document.data, opposite, 0.8265432109876543)
    app.select_path(("上部構造",))
    assert app.save()
    before_document = deepcopy(app.document.data)
    before_cells = {path: cell.get() for path, cell in app.grid_cells.items()}
    source = field(app, position)
    for path in (position, opposite):
        cell = app.grid_cells[path]
        assert cell.sheet.MT.cell_options[(cell.row, cell.column)].get("readonly") is not True
    paste_cells(app, source.widget.sheet, text, row=source.widget.row, column=source.widget.column)
    assert app.grid_cells[position].get() == text
    assert float(app.grid_cells[opposite].get()) == pytest.approx(expected)
    assert app.document.data == before_document
    assert {path: cell.get() for path, cell in app.grid_cells.items()
            if path not in (position, opposite)} == {
                path: old for path, old in before_cells.items() if path not in (position, opposite)}
    assert app.dirty
    source.widget.sheet.undo()
    assert {path: cell.get() for path, cell in app.grid_cells.items()} == before_cells
    assert not app.dirty
    source.widget.sheet.redo()
    assert app.grid_cells[position].get() == text
    assert float(app.grid_cells[opposite].get()) == pytest.approx(expected)
    assert app.save()
    saved = model.EditorDocument.open(app.document.path)
    assert model.get_at(saved.data, position) == float(text)
    assert model.get_at(saved.data, opposite) == pytest.approx(expected)
    from src.reaction_inputs import parse_reaction_input
    parsed = parse_reaction_input(saved.data)
    actual = {"起点側": parsed.spans.b.f, "終点側": parsed.spans.c.f}
    assert actual[side] == float(text)
    assert actual[other] == pytest.approx(expected)
    app.select_path(("下部構造",))
    app.select_path(("上部構造",))
    assert float(app.grid_cells[position].get()) == float(text)
    assert float(app.grid_cells[opposite].get()) == pytest.approx(expected)
    assert not app.dirty


@pytest.mark.parametrize("bad", ["-", "broken", "NaN", "Infinity"])
def test_incomplete_support_position_keeps_opposite_and_blocks_save(app, bad):
    app.select_path(("上部構造",))
    position = ("上部構造", "起点側", "支承位置_f")
    opposite = ("上部構造", "終点側", "支承位置_f")
    before = deepcopy(app.document.data)
    opposite_before = app.grid_cells[opposite].get()
    field(app, position).text.set(bad)
    assert field(app, position).text.get() == bad
    assert app.grid_cells[opposite].get() == opposite_before
    assert not app.save()
    assert app.document.data == before
    field(app, position).text.set("0.925")
    total = sum(model.get_at(before, path) for path in (("上部構造", "起点側", "桁長", "L2"), ("上部構造", "終点側", "桁長", "L1")))
    assert float(app.grid_cells[opposite].get()) == pytest.approx(total - 0.925)
    assert app.save()


@pytest.mark.parametrize("operation", ["delete", "cut"])
def test_support_position_clear_keeps_other_and_uses_compatibility_default_on_save(app, operation):
    app.select_path(("上部構造",))
    position = ("上部構造", "終点側", "支承位置_f")
    opposite = ("上部構造", "起点側", "支承位置_f")
    cell = app.grid_cells[position]
    before = (cell.get(), app.grid_cells[opposite].get())
    cell.sheet.select_cell(cell.row, cell.column)
    getattr(cell.sheet, operation)()
    assert cell.get() == ""
    assert app.grid_cells[opposite].get() == before[1]
    cell.sheet.undo()
    assert (cell.get(), app.grid_cells[opposite].get()) == before
    cell.sheet.redo()
    assert app.save()
    saved = model.EditorDocument.open(app.document.path)
    assert model.get_at(saved.data, opposite) == float(before[1])
    total = sum(model.get_at(saved.data, path) for path in (("上部構造", "起点側", "桁長", "L2"), ("上部構造", "終点側", "桁長", "L1")))
    assert model.get_at(saved.data, position) == pytest.approx(total - float(before[1]))


def test_origin_f_wins_conflicting_range_paste_and_undo_is_atomic(app):
    app.select_path(("上部構造",))
    position = ("上部構造", "起点側", "支承位置_f")
    opposite = ("上部構造", "終点側", "支承位置_f")
    source, target = app.grid_cells[position], app.grid_cells[opposite]
    before = {path: cell.get() for path, cell in app.grid_cells.items()}
    paste_cells(app, source.sheet, "0.4\n0.9", row=source.row, column=source.column)
    assert source.get() == "0.4"
    total = sum(model.get_at(app.document.data, path) for path in (("上部構造", "起点側", "桁長", "L2"), ("上部構造", "終点側", "桁長", "L1")))
    assert float(target.get()) == pytest.approx(total - 0.4)
    source.sheet.undo()
    assert {path: cell.get() for path, cell in app.grid_cells.items()} == before


def test_pending_support_position_text_updates_opposite_on_save(app):
    app.select_path(("上部構造",))
    position = ("上部構造", "起点側", "支承位置_f")
    opposite = ("上部構造", "終点側", "支承位置_f")
    before = deepcopy(app.document.data)
    cell = app.grid_cells[position]
    pending_text(app, cell.sheet, "0.815", row=cell.row, column=cell.column)
    assert app.save()
    assert cell.get() == "0.815"
    saved = model.EditorDocument.open(app.document.path)
    assert model.get_at(saved.data, position) == 0.815
    total = sum(before["上部構造"][side]["桁長"][end] for side, end in (("起点側", "L2"), ("終点側", "L1")))
    assert model.get_at(saved.data, opposite) == pytest.approx(total - 0.815)
    for side in ("起点側", "終点側"):
        assert saved.data["上部構造"][side]["桁長"] == before["上部構造"][side]["桁長"]


@pytest.mark.parametrize("side,point,attribute", [("起点側", "B支点", "b"), ("終点側", "C支点", "c")])
@pytest.mark.parametrize("value", [1.8765432109876543, 0, -0.875, None])
def test_d2_position_is_editable_independent_and_preserved_for_calculation(app, side, point, attribute, value):
    app.select_path(("上部工反力",))
    base = ("上部工反力", side, point, "支承")
    path = (*base, 1, "支承位置")
    before = {key: cell.get() for key, cell in app.grid_cells.items() if key[-1] == "支承位置"}
    target = field(app, path)
    cell = target.widget
    assert cell.sheet.MT.cell_options[(cell.row, cell.column)].get("readonly") is not True
    if value is None:
        cell.sheet.select_cell(cell.row, cell.column)
        cell.sheet.delete()
    else:
        paste_cells(app, cell.sheet, str(value), row=cell.row, column=cell.column)
    for key, text in before.items():
        if key != path:
            assert app.grid_cells[key].get() == text
    field(app, (*base, 0, "支承位置")).text.set("-7")
    assert target.parse() == value
    field(app, (*base, 0, "支承位置")).text.set("")
    assert target.parse() == value
    assert app.save()
    reopened = model.EditorDocument.open(app.document.path)
    assert model.get_at(reopened.data, path) == value
    from src.reaction_inputs import parse_reaction_input
    assert getattr(parse_reaction_input(reopened.data).dead, attribute)[1].position == value
    app.select_path(("下部構造",))
    app.select_path(("上部工反力",))
    assert field(app, path).parse() == value
    assert not app.dirty


def test_d2_position_invalid_text_blocks_save_without_recalculating_it(app):
    app.select_path(("上部工反力",))
    path = ("上部工反力", "起点側", "B支点", "支承", 1, "支承位置")
    before = deepcopy(app.document.data)
    field(app, path).text.set("broken")
    field(app, ("上部工反力", "起点側", "B支点", "支承", 0, "支承位置")).text.set("-7")
    assert field(app, path).text.get() == "broken"
    assert not app.save()
    assert app.document.data == before


def test_bearing_positions_remain_independent_when_d1_changes_or_is_cleared(app):
    app.select_path(("上部工反力",))
    b = ("上部工反力", "起点側", "B支点", "支承")
    c = ("上部工反力", "終点側", "C支点", "支承")
    c_before = app.grid_cells[(*c, 1, "支承位置")].get()
    b_before = field(app, (*b, 1, "支承位置")).text.get()
    field(app, (*b, 0, "支承位置")).text.set("-7")
    assert field(app, (*b, 1, "支承位置")).text.get() == b_before
    assert app.grid_cells[(*c, 1, "支承位置")].get() == c_before
    field(app, (*b, 0, "支承位置")).text.set("")
    assert field(app, (*b, 1, "支承位置")).text.get() == b_before


def test_snow_row_insertion_preserves_d2_position_and_all_train_total_rows(app):
    app.select_path(("上部工反力",))
    base = ("上部工反力", "起点側", "B支点", "支承")
    source = field(app, (*base, 0, "支承位置"))
    position_before = field(app, (*base, 1, "支承位置")).text.get()
    source.text.set("-7")
    assert field(app, (*base, 1, "支承位置")).text.get() == position_before
    for index, value in enumerate(("2", "3", "4", "5"), 1):
        train = field(app, (*base, 9, "列車分担", f"L{index}"))
        before = float(train.widget.sheet.get_cell_data(train.widget.row, 11))
        old = float(train.text.get() or 0)
        train.text.set(value)
        assert train.widget.row == 6 + index
        assert float(train.widget.sheet.get_cell_data(train.widget.row, 11)) == pytest.approx(before - old + float(value))
    field(app, (*base, 0, "雪荷重_2年確率")).text.set("123")
    assert field(app, (*base, 1, "支承位置")).text.get() == position_before


def test_cross_page_ground_weight_and_surface_thickness_follow_sources(app):
    before_soil = model.get_at(app.document.data, ("下部構造", "単位体積重量", "土", "上載土"))
    field(app, ("下部構造", "寸法", "高さ", "H5")).text.set("0.5")
    field(app, ("下部構造", "寸法", "高さ", "H6")).text.set("2.5")
    field(app, ("下部構造", "土かぶり", "起点側_df1")).text.set("")
    field(app, ("下部構造", "土かぶり", "終点側_df2")).text.set("1.5")
    app.select_path(("地盤データ",))
    assert app.grid_cells[SURFACE_THICKNESS_PATH].get() == "4.5"
    field(app, ("地盤データ", "層", 0, "単位体積重量", "湿潤")).text.set("20.5")
    app.select_path(("下部構造",))
    assert app.grid_cells[("下部構造", "単位体積重量", "土", "排除した土")].get() == "20.5"
    assert field(app, ("下部構造", "単位体積重量", "土", "上載土")).parse() == before_soil


def test_invalid_source_only_marks_dependent_preview_and_blocks_atomic_save(app):
    before = deepcopy(app.document.data)
    field(app, B7).text.set("broken")
    assert app.grid_cells[B9_PATH].get() == "入力エラー"
    assert app.grid_cells[("下部構造", "単位体積重量", "土", "排除した土")].get() != "入力エラー"
    assert app.document.data == before
    assert not app.save()
    assert app.document.data == before


def test_unedited_numeric_string_source_is_not_silently_parsed(app):
    model.set_at(app.document.data, B7, "0.5")
    app.render_fields()
    assert app.grid_cells[B9_PATH].get() == "入力エラー"
    assert model.get_at(app.document.data, B7) == "0.5"
    assert app.save()
    saved = json.loads(app.document.path.read_text("utf-8"))
    assert model.get_at(saved, B7) == "0.5"
    assert model.get_at(saved, B9_PATH) is None


def test_blank_arithmetic_and_min_reference_endpoints_match_excel(app):
    app.select_path(("上部構造",))
    h4_before = field(app, ("上部構造", "起点側", "高さ", "h4")).text.get()
    hs_before = app.grid_cells[("上部構造", "起点側", "重心高_hs")].get()
    for tail in (("高さ", "h1"), ("高さ", "h2"), ("高さ", "h3"), ("桁長", "L2")):
        field(app, ("上部構造", "起点側", *tail)).text.set("")
    assert field(app, ("上部構造", "起点側", "高さ", "h4")).text.get() == h4_before
    assert app.grid_cells[("上部構造", "起点側", "重心高_hs")].get() == hs_before
    assert float(app.grid_cells[("上部構造", "起点側", "支承位置_f")].get()) == app.document.data["上部構造"]["起点側"]["支承位置_f"]
    app.select_path(("下部構造",))
    for tail in (("寸法", "高さ", "H5"), ("寸法", "高さ", "H6"),
                 ("土かぶり", "起点側_df1"), ("土かぶり", "終点側_df2")):
        field(app, ("下部構造", *tail)).text.set("")
    app.select_path(("地盤データ",))
    assert app.grid_cells[SURFACE_THICKNESS_PATH].get() == "0"
    app.select_path(("下部構造",))
    field(app, ("下部構造", "土かぶり", "起点側_df1")).text.set("0")
    field(app, ("下部構造", "土かぶり", "終点側_df2")).text.set("5")
    app.select_path(("地盤データ",))
    assert app.grid_cells[SURFACE_THICKNESS_PATH].get() == "0"
