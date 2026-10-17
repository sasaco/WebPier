"""Dedicated column inputs participate in the existing atomic editor transaction."""

from copy import deepcopy
import tkinter as tk

import pytest

from src import editor_gui as gui, rebar_model
from test_editor_gui import app, paste_cells, pending_text, withdraw_without_focus
from test_rebar_ui import (
    bar_locations, cell, column_member, direction_records, install_document,
    invented_document, open_rebar, put, saved, visible_text,
)


def editor(view):
    component = getattr(view, "column_editor", None)
    assert component is not None, "Column requires its dedicated editor component"
    return component


def install_column(app, member=None):
    install_document(app, invented_document(app, members={"柱": member or column_member()}))
    return open_rebar(app)


def test_column_basic_distribution_fields_preserve_legacy_until_edited(app):
    view = install_column(app)
    editor(view)
    original = deepcopy(app.document.data)
    for key in ("mode", "edge_center_mm", "pitch_mm"):
        assert ("main_rows", 0, "distribution", key) in view.cells
    assert not app.dirty
    assert app.save()
    assert app.document.data == original
    put(app, view, ("main_rows", 0, "distribution", "mode"), "中央ピッチ")
    put(app, view, ("main_rows", 0, "distribution", "pitch_mm"), "200")
    assert {bar[0] for bar in bar_locations(view)} == {300, 500, 700, 900}
    assert app.save()
    assert saved(app)["鉄筋"]["version"] == 2
    assert "column_hoops" not in saved(app)["鉄筋"]["柱"]
    assert saved(app)["鉄筋"]["柱"]["main_rows"][0]["future_row"] == {"keep": [None, 0]}


def test_column_reference_can_be_entered_through_basic_and_direct_hoop_controls(app):
    data = invented_document(app, members={"柱": rebar_model.blank_member("柱")})
    data["下部構造"]["寸法"]["正面"]["W6"] = 4.5
    data["下部構造"]["寸法"]["側面"]["B6"] = 2.7
    install_document(app, data)
    view = open_rebar(app)
    component = editor(view)
    put(app, view, ("pure_cover_mm",), "70")
    put(app, view, ("materials", "main"), "SD390")
    put(app, view, ("materials", "transverse"), "SD390")
    assert view.select_group("bands")
    assert component.enable_hoops()
    put(app, view, ("column_hoops", "enclosing_diameter_mm"), "22")
    for i, legs in enumerate((10, 6)):
        for key, value in (("diameter_mm", "22"), ("effective_legs", str(legs)), ("pitch_mm", "150")):
            put(app, view, ("column_hoops", "direction_rows", i, key), value)
    assert view.select_group("main")
    rows = [
        {"diameter_mm": "32", "per_face_count": "29", "cover_mode": "自動",
         "distribution": {"mode": "両端＋中央ピッチ", "edge_center_mm": "108", "pitch_mm": "150"}},
        {"diameter_mm": "19", "per_face_count": "9", "cover_mode": "指定", "center_mm": "102",
         "distribution": {"mode": "中央ピッチ", "pitch_mm": "250"}},
    ]
    for i, values in enumerate(rows):
        for key, value in values.items():
            if key == "distribution":
                for field, text in value.items():
                    put(app, view, ("main_rows", i, key, field), text)
            else:
                put(app, view, ("main_rows", i, key), value)
    assert len(view.preview_bars) == 76
    assert view.effective_centers == [108, 102]
    assert view.select_direction("線路")
    assert len(direction_records(view)) == 11
    assert view.select_direction("直角")
    assert len(direction_records(view)) == 31
    assert app.save()
    hoops = saved(app)["鉄筋"]["柱"]["column_hoops"]
    assert [row["effective_legs"] for row in hoops["direction_rows"]] == [10, 6]
    assert all(row["start_mm"] is None and row["end_mm"] is None for row in hoops["direction_rows"])


def test_detail_first_actual_cell_edit_snapshots_and_switches_source_atomically(app):
    view = install_column(app)
    editor(view)
    original = deepcopy(app.document.data)
    before = bar_locations(view)
    assert view.select_group("placement")
    assert not app.dirty
    assert view.draft["position_mode"] == "基本"
    control = cell(view, "manual_positions", 0, "x_mm")
    pending_text(app, control.sheet, "65", control.row, control.column)
    withdraw_without_focus(app)
    assert app.save()
    member = saved(app)["鉄筋"]["柱"]
    assert member["position_mode"] == "指定"
    assert member["manual_positions"][0]["x_mm"] == 65
    assert "manual_basis" in member
    assert all(row["material"] == "SD345" for row in member["manual_positions"])
    assert member["main_rows"] == original["鉄筋"]["柱"]["main_rows"]
    assert bar_locations(view) != before


def test_incomplete_column_explains_missing_inputs_and_cannot_start_detail(app):
    member = column_member(automatic=True)
    member["band_rows"] = []
    view = install_column(app, member)
    component = editor(view)
    assert "帯" in view.preview_error
    assert view.select_group("placement")
    assert not component.begin_regeneration()
    assert view.draft["position_mode"] == "基本"
    assert not view.draft["manual_positions"]
    assert app.save(), "Incomplete basic inputs remain saveable"


@pytest.mark.parametrize("window", ["980x640", "1360x900"])
def test_column_figure_and_direction_review_remain_available_in_basic_screen(app, window):
    app.root.deiconify()
    app.root.geometry(window)
    view = install_column(app)
    editor(view)
    app.root.update()
    assert view.preview_canvas.winfo_height() >= 140
    assert view._derived_sheet.winfo_ismapped()
    assert direction_records(view)
    assert "片面本数" in list(cell(view, "main_rows", 0, "per_face_count").sheet.headers())
    assert "コピー後も" not in "\n".join(visible_text(view.frame))


def detail_with_changed_basic(app):
    view = install_column(app)
    component = editor(view)
    assert view.select_group("placement")
    put(app, view, ("manual_positions", 0, "x_mm"), "65")
    assert view.select_group("main")
    detail = deepcopy(view.draft["manual_positions"])
    put(app, view, ("main_rows", 0, "per_face_count"), "5")
    assert view.draft["manual_positions"] == detail
    return view, component, detail


def test_regeneration_comparison_cancel_then_apply_keeps_detail_source(app):
    view, component, detail = detail_with_changed_basic(app)
    before = deepcopy(view.draft)
    assert component.begin_regeneration(), "Completed automatic placement requires a comparison dialog"
    assert component.dialog is not None
    assert len(component.comparison["old_bars"]) == 8
    assert len(component.comparison["candidate_bars"]) == 10
    assert "現在" in "\n".join(visible_text(component.dialog))
    assert "候補" in "\n".join(visible_text(component.dialog))
    assert component.cancel_regeneration()
    assert view.draft == before
    assert component.begin_regeneration()
    assert component.apply_regeneration()
    assert component.dialog is None
    assert view.draft["position_mode"] == "指定"
    assert len(view.draft["manual_positions"]) == 10
    assert view.draft["manual_positions"] != detail
    put(app, view, ("main_rows", 0, "per_face_count"), "6")
    assert len(view.preview_bars) == 10
    assert "未反映" in component.status.cget("text")
    assert app.save()


def test_stale_regeneration_cannot_apply_and_keeps_positions(app):
    view, component, detail = detail_with_changed_basic(app)
    original = deepcopy(app.document.data)
    assert component.begin_regeneration()
    # Deliberate non-UI mutation simulates an external callback while the grab is held.
    cell(view, "main_rows", 0, "per_face_count").set("6")
    assert not component.apply_regeneration()
    assert view.draft["manual_positions"] == detail
    assert app.document.data == original
    assert component.dialog is not None
    assert "変更" in component.dialog_error.get()
    assert component.cancel_regeneration()


def test_explicit_auto_switch_preserves_inactive_detail_and_restore(app):
    view, component, detail = detail_with_changed_basic(app)
    basis = deepcopy(view.draft["manual_basis"])
    assert component.begin_regeneration(to_auto=True)
    assert component.apply_regeneration()
    assert view.draft["position_mode"] == "基本"
    assert len(view.preview_bars) == 10
    assert view.draft["manual_positions"] == detail
    assert view.draft["manual_basis"] == basis
    assert component.restore_detail()
    assert view.draft["position_mode"] == "指定"
    assert view.draft["manual_positions"] == detail
    assert len(view.preview_bars) == 8


def test_comparison_blocks_host_file_actions_and_busy_blocks_column_operations(app, monkeypatch):
    view, component, _ = detail_with_changed_basic(app)
    assert component.begin_regeneration()
    original = deepcopy(app.document.data)
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kw: pytest.fail("modal permitted file chooser"))
    assert not app.open_file()
    assert not app.confirm_discard()
    assert not app.save()
    assert not view.select_member("梁")
    assert not view.select_group("placement")
    assert app.document.data == original
    assert component.cancel_regeneration()
    app._calculation_busy = True
    try:
        assert not component.begin_regeneration()
        assert not component.enable_hoops()
        assert not component.restore_detail()
        assert not component.delete_position(0)
        assert not component.add_position({"x_mm": 100, "y_mm": 100, "diameter_mm": 20, "material": "SD345"})
    finally:
        app._calculation_busy = False


def test_first_detail_delete_and_complete_add_are_atomic(app):
    view = install_column(app)
    component = editor(view)
    assert view.select_group("placement")
    original = deepcopy(app.document.data)
    first = {key: view.preview_bars[0][key] for key in ("x_mm", "y_mm", "diameter_mm", "material")}
    delete = getattr(component, "delete_position", None)
    assert callable(delete), "Physical detail table needs snapshot-aware delete"
    assert delete(0)
    assert view.draft["position_mode"] == "指定"
    assert len(view.preview_bars) == 7
    before = deepcopy(view.draft)
    assert not component.add_position({**first, "x_mm": -10})
    assert view.draft == before
    assert component.add_position(first)
    assert len(view.preview_bars) == 8
    assert app.document.data == original
    assert app.save()


def test_detail_add_dialog_cancel_does_not_create_incomplete_rows(app):
    view = install_column(app)
    component = editor(view)
    assert view.select_group("placement")
    before = deepcopy(view.draft)
    add = getattr(component, "add_position", None)
    assert callable(add), "Physical detail table needs an atomic complete-position add dialog"
    assert add()
    assert component.dialog is not None
    for key, value in (("x_mm", "300"), ("y_mm", "300"), ("diameter_mm", "20"), ("material", "SD345")):
        component.position_controls[key].set(value)
    assert component.cancel_regeneration()
    assert view.draft == before and not app.dirty
    assert component.add_position()
    for key, value in (("x_mm", "300"), ("y_mm", "300"), ("diameter_mm", "20"), ("material", "SD345")):
        component.position_controls[key].set(value)
    assert component.apply_position()
    assert len(view.preview_bars) == 9
    assert view.draft["position_mode"] == "指定"


def test_return_to_legacy_hoops_requires_explicit_confirm_and_keeps_detail(app, monkeypatch):
    view = install_column(app, column_member(automatic=True))
    component = editor(view)
    assert view.select_group("placement")
    put(app, view, ("manual_positions", 0, "x_mm"), "65")
    detail = deepcopy(view.draft["manual_positions"])
    assert view.select_group("bands")
    legacy = deepcopy(view.draft["band_rows"])
    assert component.enable_hoops()
    put(app, view, ("column_hoops", "enclosing_diameter_mm"), "22")
    assert app.save()
    before = deepcopy(view.draft)
    operation = getattr(component, "use_legacy_hoops", None)
    assert callable(operation), "Hoop source can explicitly return to preserved legacy rows"
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **kw: False)
    assert not operation()
    assert view.draft == before
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **kw: True)
    assert operation()
    assert "column_hoops" not in view.draft
    assert view.draft["band_rows"] == legacy
    assert view.draft["manual_positions"] == detail
    assert app.save()
    assert saved(app)["鉄筋"]["version"] == 2
    assert "column_hoops" not in saved(app)["鉄筋"]["柱"]


def test_invalid_pending_detail_cell_blocks_save_and_navigation_without_partial_changes(app):
    view = install_column(app)
    editor(view)
    assert view.select_group("placement")
    original = deepcopy(app.document.data)
    control = cell(view, "manual_positions", 0, "x_mm")
    pending_text(app, control.sheet, "invalid", control.row, control.column)
    withdraw_without_focus(app)
    assert not app.save()
    assert not view.select_member("梁")
    assert app.document.data == original
    assert cell(view, "manual_positions", 0, "x_mm").get() == "invalid"


def test_virtual_detail_selection_highlights_one_physical_bar_before_editing(app):
    view = install_column(app)
    editor(view)
    assert view.select_group("placement")
    view.select_row("manual_positions", 0)
    app.root.update()
    selected = set(view.preview_canvas.find_withtag("selected")) & set(view.preview_canvas.find_withtag("rebar"))
    assert len(selected) == 1, "Virtual detail selection must identify one physical bar before snapshotting"
    assert not app.dirty


def test_dialog_setup_failures_release_grab_and_preserve_draft(app, monkeypatch):
    view = install_column(app)
    component = editor(view)
    assert view.select_group("placement")
    original = deepcopy(view.draft)
    dialog_type = tk.Toplevel
    original_grab = dialog_type.grab_set
    for operation in (component.begin_regeneration, component.add_position):
        for stage in ("transient", "grab_set"):
            with monkeypatch.context() as failing:
                def fail(dialog, *args, **kwargs):
                    if stage == "grab_set":
                        original_grab(dialog)
                    raise tk.TclError(f"{stage} failed")
                failing.setattr(dialog_type, stage, fail)
                try:
                    result = operation()
                except tk.TclError:
                    pytest.fail("Dialog setup error escaped without releasing the column editor")
                assert not result
                assert component.dialog is None
                assert app.root.grab_current() is None
                assert not any(isinstance(child, dialog_type) for child in app.root.winfo_children())
                assert view.draft == original
    assert component.begin_regeneration()
    assert component.cancel_regeneration()


def test_copy_active_detail_requires_readonly_comparison_before_replacement(app):
    from tksheet import Sheet

    view, component, _ = detail_with_changed_basic(app)
    before = deepcopy(view.draft)
    assert view.copy_basic_positions()
    assert view.draft == before, "Compatibility copy must not overwrite active detail before comparison"
    assert component.dialog is not None
    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)
    sheets = [widget for widget in walk(component.dialog) if isinstance(widget, Sheet)]
    assert len(sheets) == 2
    for sheet in sheets:
        original = deepcopy(sheet.get_sheet_data())
        paste_cells(app, sheet, "999", 0, 0)
        assert sheet.get_sheet_data() == original
    assert component.cancel_regeneration()
    assert view.draft == before


def test_virtual_detail_tracks_common_changes_and_snapshots_latest_automatic_positions(app):
    member = column_member(automatic=True)
    member["pure_cover_mm"] = 70
    view = install_column(app, member)
    editor(view)
    assert view.select_group("placement")
    put(app, view, ("pure_cover_mm",), "80")
    put(app, view, ("materials", "main"), "SD390")
    latest = rebar_model.column_layout(view.draft, view.preview_geometry)["bars"]
    for i, bar in enumerate(latest):
        assert float(cell(view, "manual_positions", i, "x_mm").get()) == bar["x_mm"]
        assert float(cell(view, "manual_positions", i, "y_mm").get()) == bar["y_mm"]
        assert cell(view, "manual_positions", i, "material").get() == "SD390"
    put(app, view, ("manual_positions", 0, "x_mm"), str(latest[0]["x_mm"] + 5))
    assert app.save()
    member = saved(app)["鉄筋"]["柱"]
    for i, (row, automatic) in enumerate(zip(member["manual_positions"], latest)):
        assert row["x_mm"] == automatic["x_mm"] + (5 if i == 0 else 0)
        assert row["y_mm"] == automatic["y_mm"]
        assert row["material"] == "SD390"
    assert rebar_model.column_detail_status(member, view.preview_geometry) == "一致"


def test_common_change_preserves_invalid_pending_detail_then_uses_latest_basis(app):
    view = install_column(app, column_member(automatic=True))
    editor(view)
    assert view.select_group("placement")
    original = deepcopy(app.document.data)
    control = cell(view, "manual_positions", 0, "x_mm")
    pending_text(app, control.sheet, "invalid", control.row, control.column)
    cell(view, "pure_cover_mm").set("50")
    app.root.update()
    assert control.sheet.MT.text_editor.open
    assert control.sheet.get_text_editor_value() == "invalid"
    assert not app.save()
    assert app.document.data == original
    cell(view, "manual_positions", 0, "x_mm").set("75")
    assert app.save()
    rows = saved(app)["鉄筋"]["柱"]["manual_positions"]
    assert {row["y_mm"] for row in rows} == {70, 1930}
    assert rows[0]["x_mm"] == 75


def test_active_enclosing_hoop_schematic_ignores_preserved_legacy_rows_and_leg_counts(app):
    view = install_column(app, column_member(automatic=True))
    component = editor(view)
    assert view.select_group("bands")
    legacy = deepcopy(view.draft["band_rows"])
    assert component.enable_hoops()
    put(app, view, ("column_hoops", "enclosing_diameter_mm"), "22")
    canvas = view.preview_canvas
    polygons = [item for item in canvas.find_withtag("column-hoop-schematic") if canvas.type(item) == "polygon"]
    assert len(polygons) == 1, "Only the active current-section enclosing hoop should be drawn"
    assert not canvas.find_withtag("rebar:band_rows:0")
    assert getattr(view, "band_schematic", None) is None
    outline = canvas.coords(canvas.find_withtag("section-outline")[0])
    scale = (outline[2] - outline[0]) / 1200
    hoop = canvas.coords(polygons[0])
    assert hoop[0] == pytest.approx(outline[0] + 51 * scale)
    text = "\n".join(canvas.itemcget(item, "text") for item in canvas.find_all() if canvas.type(item) == "text")
    assert "現在断面" in text and "模式図" in text
    before = list(hoop)
    put(app, view, ("column_hoops", "direction_rows", 0, "effective_legs"), "10")
    put(app, view, ("column_hoops", "direction_rows", 1, "effective_legs"), "6")
    polygons = [item for item in canvas.find_withtag("column-hoop-schematic") if canvas.type(item) == "polygon"]
    assert canvas.coords(polygons[0]) == before
    assert view.draft["band_rows"] == legacy


def test_column_direction_arrows_and_missing_detail_archive_are_explicit(app):
    view = install_column(app)
    component = editor(view)
    canvas = view.preview_canvas
    x_axis, y_axis = canvas.find_withtag("axis-x"), canvas.find_withtag("axis-y")
    assert x_axis and y_axis, "Column diagram requires X/transverse and Y/rail direction arrows"
    for item in (x_axis[0], y_axis[0]):
        assert canvas.itemcget(item, "arrow") == "last"
    x, y = canvas.coords(x_axis[0]), canvas.coords(y_axis[0])
    assert x[2] > x[0] and x[3] == x[1]
    assert y[3] > y[1] and y[2] == y[0]
    before = deepcopy(view.draft)
    assert component.action_buttons["restore"].instate(["disabled"])
    assert not component.restore_detail()
    assert view.draft == before and view.draft["position_mode"] == "基本"


@pytest.mark.parametrize("distribution", [{}, {"pitch_mm": 200, "future": {"null": None, "zero": 0}},
                                         {"mode": None, "pitch_mm": 200}])
def test_present_incomplete_distribution_preserves_missing_mode_until_explicit_choice(app, distribution):
    member = column_member()
    member["main_rows"][0]["distribution"] = deepcopy(distribution)
    data = invented_document(app, members={"柱": member})
    data["鉄筋"]["version"] = 2
    install_document(app, data)
    original = deepcopy(app.document.data)
    view = open_rebar(app)
    editor(view)
    assert view.draft["main_rows"][0]["distribution"] == distribution, "Opening incomplete input must not select a distribution mode"
    assert cell(view, "main_rows", 0, "distribution", "mode").get() == ""
    assert not rebar_model.column_layout(view.draft, view.preview_geometry)["complete"]
    assert not app.dirty
    assert app.save()
    assert app.document.data == original and saved(app) == original
    put(app, view, ("main_rows", 0, "distribution", "mode"), "中央ピッチ")
    put(app, view, ("main_rows", 0, "distribution", "pitch_mm"), "200")
    assert rebar_model.column_layout(view.draft, view.preview_geometry)["complete"]
    assert len(view.preview_bars) == 8
    assert app.save()
    expected = {**distribution, "mode": "中央ピッチ", "pitch_mm": 200}
    assert saved(app)["鉄筋"]["柱"]["main_rows"][0]["distribution"] == expected


def test_direction_selector_reverts_after_invalid_pending_cell_and_recovers(app):
    view = install_column(app)
    editor(view)
    assert view.select_group("placement")
    original = deepcopy(app.document.data)
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    selector = next(widget for widget in descendants(view.frame)
                    if widget.winfo_class() == "TCombobox"
                    and str(widget.cget("textvariable")) == str(view.direction_var))
    control = cell(view, "manual_positions", 0, "x_mm")
    pending_text(app, control.sheet, "invalid", control.row, control.column)
    selector.set("直角")
    selector.event_generate("<<ComboboxSelected>>")
    app.root.update()
    assert view.direction == "線路"
    assert selector.get() == "線路", "A refused direction change must keep its visible label aligned"
    assert cell(view, "manual_positions", 0, "x_mm").get() == "invalid"
    assert app.document.data == original
    put(app, view, ("manual_positions", 0, "x_mm"), "75")
    selector.set("直角")
    selector.event_generate("<<ComboboxSelected>>")
    app.root.update()
    assert view.direction == selector.get() == "直角"
    expected = rebar_model.directional_rows(view.preview_bars, "直角")
    assert direction_records(view) == [tuple(row[key] for key in ("center_mm", "diameter_mm", "count", "material"))
                                       for row in expected]


def test_legacy_band_selection_keeps_live_direction_table_after_diameter_edit(app):
    view = install_column(app, column_member(automatic=True))
    editor(view)
    assert view.select_group("bands")
    table = view._derived_sheet
    assert direction_records(view) == [(60, 20, 4, "SD345"), (1940, 20, 4, "SD345")]
    put(app, view, ("band_rows", 0, "diameter_mm"), "20")
    assert {bar["y_mm"] for bar in view.preview_bars} == {70, 1930}
    assert direction_records(view) == [(70, 20, 4, "SD345"), (1930, 20, 4, "SD345")], "The visible review table must follow the current legacy-band diameter"
    assert view._derived_sheet is table and table.winfo_exists()
    assert view.select_direction("直角")
    expected = rebar_model.directional_rows(view.preview_bars, "直角")
    assert direction_records(view) == [tuple(row[key] for key in ("center_mm", "diameter_mm", "count", "material"))
                                       for row in expected]
    assert view._derived_sheet is table
    assert app.save()
    assert saved(app)["鉄筋"]["version"] == 1
    assert "column_hoops" not in saved(app)["鉄筋"]["柱"]


def test_comparison_footer_buttons_are_fully_visible_in_small_window(app):
    app.root.deiconify()
    app.root.geometry("980x640")
    _, component, _ = detail_with_changed_basic(app)
    assert component.begin_regeneration()
    app.root.update()
    dialog = component.dialog
    actions = component.apply_button.master
    buttons = [widget for widget in actions.winfo_children() if widget.winfo_class() == "TButton"]
    assert {button.cget("text") for button in buttons} == {"適用", "取消"}
    left, top = dialog.winfo_rootx(), dialog.winfo_rooty()
    right, bottom = left + dialog.winfo_width(), top + dialog.winfo_height()
    for button in buttons:
        assert button.winfo_ismapped()
        assert button.winfo_height() >= button.winfo_reqheight(), "Comparison footer must reserve full button height"
        assert left <= button.winfo_rootx() and top <= button.winfo_rooty()
        assert button.winfo_rootx() + button.winfo_width() <= right
        assert button.winfo_rooty() + button.winfo_height() <= bottom
        assert button.winfo_rooty() + button.winfo_height() <= actions.winfo_rooty() + actions.winfo_height()
    assert component.cancel_regeneration()
