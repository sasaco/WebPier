from __future__ import annotations

import copy
import json
from pathlib import Path
import tkinter as tk

import pytest

from src import editor_gui as gui
from src.reaction_inputs import SNOW_LOAD_CASES

# Fixed historical input from fa27cca^, independent of the working input.
SOURCE = Path(__file__).resolve().parent / "fixtures" / "baseline_input.json"


@pytest.fixture
def app(tmp_path, monkeypatch):
    path = tmp_path / "input.json"
    path.write_bytes(SOURCE.read_bytes())
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    editor = gui.InputEditor(root, path, output_dir=tmp_path / "output")
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *a, **k: None)
    yield editor
    try:
        root.destroy()
    except tk.TclError:
        pass


def field(app, path):
    return next(item for item in app.fields if item.path == path)


def button_labels(widget: tk.Misc) -> list[str]:
    labels = [str(widget.cget("text"))] if isinstance(widget, gui.ttk.Button) else []
    for child in widget.winfo_children():
        labels.extend(button_labels(child))
    return labels


def test_every_navigation_form_opens_without_changes(app):
    before = app.document.path.read_bytes()
    assert set(app.paths.values()) == {("下部構造",), ("上部構造",), ("上部工反力",), ("地盤データ",), gui.CALCULATION_PAGE, gui.REBAR_PAGE}
    for path in list(app.paths.values()):
        app.select_path(path)
        app.root.update()
        assert app.flush_fields()
        labels = "\n".join(button_labels(app.root))
        assert "元のPDFを開く" not in labels
        assert "詳細データ編集" not in labels
    assert not app.dirty
    assert app.save()
    assert app.document.path.read_bytes() == before


def test_superstructure_has_only_existing_inertia_inputs(app):
    app.select_path(("上部構造",))
    assert all("直角地震時慣性力" not in item.path for item in app.fields)
    for side in ("起点側", "終点側"):
        hs = app.grid_cells[("上部構造", side, "重心高_hs")]
        assert "重心高 hs" in hs.sheet.get_header_data(hs.column)
        assert "一括法" not in hs.sheet.get_header_data(hs.column)


def test_recovery_brake_optional_cells_preserve_missing_and_save_only_edited_side(app):
    app.select_path(("上部構造",))
    paths = [("上部構造", "支承データ", side, "復旧性制動係数") for side in ("起点側", "終点側")]
    before = app.document.path.read_bytes()
    assert all(field(app, path).text.get() == "" for path in paths)
    assert app.save()
    assert app.document.path.read_bytes() == before
    field(app, paths[1]).text.set("1.0")
    assert app.save()
    saved = json.loads(app.document.path.read_text("utf-8"))["上部構造"]["支承データ"]
    assert "復旧性制動係数" not in saved["起点側"]
    assert saved["終点側"]["復旧性制動係数"] == 1.0
    field(app, paths[1]).text.set("")
    assert app.save()
    assert app.document.data["上部構造"]["支承データ"]["終点側"]["復旧性制動係数"] is None


def test_numeric_nullable_and_invalid_input_navigation(app):
    path = ("下部構造", "寸法", "側面", "B8")
    field(app, path).text.set("abc")
    assert app.dirty
    app.select_path(("地盤データ",))
    assert app.current_path == ("下部構造",)
    assert not app.save()
    field(app, path).text.set("6.25")
    assert app.save()
    assert json.loads(app.document.path.read_text("utf-8"))["下部構造"]["寸法"]["側面"]["B8"] == 6.25
    app.select_path(("地盤データ",))
    angle = field(app, ("地盤データ", "層", 0, "内部摩擦角_φd"))
    angle.text.set("35")
    assert app.flush_fields()
    assert app.document.data["地盤データ"]["層"][0]["内部摩擦角_φd"] == 35
    assert type(app.document.data["地盤データ"]["層"][0]["内部摩擦角_φd"]) is int
    angle.text.set("")
    assert app.flush_fields()
    assert app.document.data["地盤データ"]["層"][0]["内部摩擦角_φd"] is None


def test_dirty_open_and_close_cancel_save_failure_and_discard(app, tmp_path, monkeypatch):
    other = tmp_path / "other.json"
    other.write_bytes(SOURCE.read_bytes())
    original = app.document.path
    item = field(app, ("下部構造", "寸法", "側面", "B8"))
    item.text.set("invalid")
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **k: str(other))
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *a, **k: None)
    assert not app.open_file()
    assert not app.close()
    assert app.document.path == original
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *a, **k: True)
    assert not app.open_file()
    assert not app.close()
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *a, **k: False)
    assert app.open_file()
    assert app.document.path == other
    assert not app.dirty


def test_failed_open_preserves_current_edits(app, tmp_path, monkeypatch):
    invalid = tmp_path / "bad.json"
    invalid.write_text("broken")
    item = field(app, ("下部構造", "寸法", "側面", "B8"))
    item.text.set("6")
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **k: str(invalid))
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *a, **k: False)
    assert not app.open_file()
    assert item.text.get() == "6"
    assert app.dirty


def test_ground_row_operations_preserve_unknown_multiline(app, monkeypatch):
    extension = {"複数行": "line1\nline2", "文字列番号": "001"}
    app.document.data["地盤データ"]["層"][0]["拡張"] = copy.deepcopy(extension)
    app.select_path(("地盤データ",))
    app.soil_selected.set(0)
    app.soil_duplicate()
    assert len(app.document.data["地盤データ"]["層"]) == 3
    assert app.document.data["地盤データ"]["層"][1]["拡張"] == extension
    field(app, ("地盤データ", "層", 1, "層番")).text.set("複製層")
    app.soil_move(1)
    assert app.document.data["地盤データ"]["層"][2]["層番"] == "複製層"
    assert app.document.data["地盤データ"]["層"][2]["拡張"] == extension
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: True)
    app.soil_delete()
    assert len(app.document.data["地盤データ"]["層"]) == 2
    assert app.save()
    saved = json.loads(app.document.path.read_text("utf-8"))
    assert saved["地盤データ"]["層"][0]["拡張"] == extension


def test_other_foundation_type_is_editable_and_saveable(app):
    item = field(app, ("下部構造", "杭種", "選択値"))
    item.text.set("場所打ち杭")
    assert app.save()
    assert not app.check_calculation()


def test_choice_fields_accept_candidates_and_clear_to_null(app):
    path = ("下部構造", "場所打ち杭の施工条件", "選択値")
    item = field(app, path)
    from src.editor_grid import SheetCell
    assert isinstance(item.widget, SheetCell)
    cell = item.widget
    dropdown = cell.sheet.get_dropdowns()[(cell.row, cell.column)]
    assert "ベントナイト泥水" in dropdown["values"]
    assert dropdown["state"] == "normal"
    assert not dropdown["validate_input"]
    # Paste goes through tksheet's own dropdown validation path.
    paste_cells(app, cell.sheet, "ベントナイト泥水", cell.row, cell.column)
    assert app.flush_fields()
    assert app.document.data["下部構造"]["場所打ち杭の施工条件"]["選択値"] == "ベントナイト泥水"
    paste_cells(app, cell.sheet, "", cell.row, cell.column)
    assert app.flush_fields()
    assert app.document.data["下部構造"]["場所打ち杭の施工条件"]["選択値"] is None


def test_save_as_and_external_change_keeps_unsaved_edits(app, tmp_path, monkeypatch):
    app.document.path.write_bytes(b'{"external": true}')
    field(app, ("下部構造", "寸法", "側面", "B8")).text.set("6")
    assert not app.save()
    assert app.dirty
    destination = tmp_path / "new.json"
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **k: str(destination))
    assert app.save_as()
    assert app.document.path == destination
    assert not app.dirty


def test_reaction_table_edits_survive_navigation_and_reopen(app, monkeypatch):
    origin = ("上部工反力", "起点側", "B支点", "支承", 0)
    end = ("上部工反力", "終点側", "C支点", "支承", 0)
    app.select_path(("上部工反力",))

    # The ordinary table must distinguish blank, zero, and an inapplicable
    # value without requiring the user to manipulate JSON types.
    load = field(app, origin + ("固定死荷重_D1",))
    load.text.set("-")
    assert app.flush_fields()
    assert app.document.data["上部工反力"]["起点側"]["B支点"]["支承"][0]["固定死荷重_D1"] == "-"
    load.text.set("475.5")
    field(app, origin + ("列車分担", "L2")).text.set("0")
    field(app, end + ("支承位置",)).text.set("-2.0")
    field(app, end + ("付加死荷重_D2",)).text.set("")
    app.select_path(("上部構造",))
    field(app, ("上部構造", "起点側", "桁長", "スパン長")).text.set("28.25")
    assert app.save()

    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **k: str(app.document.path))
    assert app.open_file()
    app.select_path(("上部工反力",))
    b = app.document.data["上部工反力"]["起点側"]["B支点"]["支承"][0]
    c = app.document.data["上部工反力"]["終点側"]["C支点"]["支承"][0]
    assert b["固定死荷重_D1"] == 475.5
    assert type(b["固定死荷重_D1"]) is float
    assert b["列車分担"]["L2"] == 0
    assert type(b["列車分担"]["L2"]) is int
    assert c["支承位置"] == -2.0
    assert type(c["支承位置"]) is float
    assert c["付加死荷重_D2"] is None
    assert app.document.data["上部構造"]["起点側"]["桁長"]["スパン長"] == 28.25
    for side, points in (("起点側", ("B支点",)), ("終点側", ("C支点",))):
        assert all("合計" not in app.document.data["上部工反力"][side].get(point, {}) for point in points)
    assert field(app, origin + ("固定死荷重_D1",)).text.get() == "475.5"
    assert field(app, origin + ("列車分担", "L2")).text.get() == "0"
    assert not app.dirty


def test_invalid_table_cell_prevents_partial_updates(app):
    app.select_path(("地盤データ",))
    before = copy.deepcopy(app.document.data)
    thickness = field(app, ("地盤データ", "層", 1, "層厚"))
    friction = field(app, ("地盤データ", "層", 1, "内部摩擦角_φd"))
    thickness.text.set("4.5")
    friction.text.set("invalid")
    assert not app.flush_fields()
    assert app.document.data == before
    app.select_path(("下部構造",))
    assert app.current_path == ("地盤データ",)
    assert thickness.text.get() == "4.5"
    assert friction.text.get() == "invalid"
    friction.text.set("35")
    assert app.save()
    saved = json.loads(app.document.path.read_text("utf-8"))
    assert saved["地盤データ"]["層"][1]["層厚"] == 4.5
    assert saved["地盤データ"]["層"][1]["内部摩擦角_φd"] == 35
    assert saved["地盤データ"]["層"][0]["層厚"] == 4.0


def test_sheet_editing_preserves_extensions_and_metadata(app):
    dimensions = app.document.data["下部構造"]["寸法"]["側面"]
    dimensions["施工メモ"] = "第1案\n仮設定"
    app.document.data["拡張"] = {"文字列番号": "001", "有効": True, "未定": None}
    expected = copy.deepcopy(app.document.data)
    expected["下部構造"]["寸法"]["側面"]["B8"] = 6.25
    app.refresh_tree(("下部構造",))
    field(app, ("下部構造", "寸法", "側面", "B8")).text.set("6.25")
    app.select_path(("地盤データ",))
    assert app.save()
    saved = json.loads(app.document.path.read_text("utf-8"))
    assert saved == expected


def test_ground_table_row_operations_keep_edits_and_recover_from_empty(app, monkeypatch):
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: True)
    app.select_path(("地盤データ",))
    surface_weight = ("地盤データ", "層", 0, "単位体積重量", "湿潤")
    field(app, surface_weight).text.set("19.5")
    app.soil_selected.set(0)
    app.soil_duplicate()
    layers = app.document.data["地盤データ"]["層"]
    assert len(layers) == 3
    assert layers[0]["単位体積重量"]["湿潤"] == 19.5
    assert layers[1]["単位体積重量"]["湿潤"] == 19.5

    field(app, ("地盤データ", "層", 1, "単位体積重量", "湿潤")).text.set("22")
    app.soil_move(1)
    assert layers[0]["単位体積重量"]["湿潤"] == 19.5
    assert layers[1]["層番"] == "支持層"
    assert layers[2]["単位体積重量"]["湿潤"] == 22
    app.soil_delete()
    assert len(layers) == 2
    assert layers[1]["層番"] == "支持層"
    while layers:
        app.soil_selected.set(0)
        app.soil_delete()
    app.soil_add()
    assert len(layers) == 1
    assert layers[0]["層厚"] == 4.0
    assert layers[0]["N値"] is None
    assert layers[0]["単位体積重量"] == {"湿潤": None, "水中": None}
    field(app, ("地盤データ", "層", 0, "層番")).text.set("再入力層")
    field(app, ("地盤データ", "層", 0, "土質区分")).text.set("砂質土")
    field(app, ("地盤データ", "層", 0, "N値")).text.set("0")
    assert app.save()
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **k: str(app.document.path))
    assert app.open_file()
    app.select_path(("地盤データ",))
    loaded = app.document.data["地盤データ"]["層"]
    assert len(loaded) == 1
    assert loaded[0]["層番"] == "再入力層"
    assert loaded[0]["土質区分"] == "砂質土"
    assert loaded[0]["N値"] == 0
    assert type(loaded[0]["N値"]) is int
    assert loaded[0]["層厚"] == 4.0
    assert field(app, ("地盤データ", "層", 0, "層番")).text.get() == "再入力層"
    assert not app.dirty


def test_text_cells_can_replace_hyphen_after_reopening(app, monkeypatch):
    train_name = ("上部構造", "列車", "車両名")
    layer_name = ("地盤データ", "層", 1, "層番")
    for path in (train_name, layer_name):
        app.select_path((path[0],))
        field(app, path).text.set("-")
    assert app.save()
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **k: str(app.document.path))
    assert app.open_file()
    for path, name in ((train_name, "EA-17"), (layer_name, "支持層")):
        app.select_path((path[0],))
        cell = field(app, path)
        assert cell.text.get() == "-"
        cell.text.set(name)
    assert app.save()
    assert app.open_file()
    for path, name in ((train_name, "EA-17"), (layer_name, "支持層")):
        app.select_path((path[0],))
        assert field(app, path).text.get() == name
    assert not app.dirty


def ground_sheet(app):
    from tksheet import Sheet

    app.select_path(("地盤データ",))
    assert hasattr(app, "grids"), "InputEditor must manage real Sheet widgets"
    assert len(app.grids) == 1
    sheet = app.grids[0]
    assert isinstance(sheet, Sheet)
    return sheet


def paste_cells(app, sheet, text, row=0, column=0):
    app.root.clipboard_clear()
    app.root.clipboard_append(text)
    sheet.select_cell(row, column)
    sheet.paste()


def pending_text(app, sheet, text, row=1, column=1):
    app.root.deiconify()
    app.root.update()
    sheet.select_cell(row, column)
    sheet.open_cell()
    editor = sheet.get_text_editor_widget()
    assert editor is not None
    editor.delete("1.0", "end")
    editor.insert("1.0", text)
    # Process drawing and focus events before a test moves focus away.
    app.root.update()


def withdraw_without_focus(app):
    # Withdrawal alone may retain Windows keyboard focus. A second Tcl
    # interpreter gives a real focus loss while tksheet keeps its editor open.
    other = tk.Tk()
    try:
        other.geometry("120x50+10+10")
        other.update()
        other.focus_force()
        other.update()
        app.root.update()
        app.root.withdraw()
        app.root.update()
    finally:
        other.destroy()
    app.root.update()


def test_ground_clipboard_range_undo_redo_and_reopen(app, monkeypatch):
    sheet = ground_sheet(app)
    before = copy.deepcopy(sheet.get_sheet_data())
    paste_cells(app, sheet, "表層\t999\t砂質土\t12\n支持層\t4.5\t粘性土\t0")
    assert sheet.get_sheet_data()[0][:4] == ["表層", "4", "砂質土", "12"]
    assert app.dirty
    sheet.undo()
    assert sheet.get_sheet_data() == before
    assert not app.dirty
    sheet.redo()
    assert app.save()
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **k: str(app.document.path))
    assert app.open_file()
    layers = app.document.data["地盤データ"]["層"]
    assert layers[0]["層厚"] == 4.0
    assert layers[0]["N値"] == 12
    assert layers[1]["層厚"] == 4.5
    assert layers[1]["N値"] == 0


def test_ground_invalid_paste_is_atomic_and_fixed_size(app):
    sheet = ground_sheet(app)
    before = copy.deepcopy(app.document.data)
    paste_cells(app, sheet, "4.5\t砂質土\t12\ninvalid\t粘性土\t20", column=1)
    assert not app.flush_fields()
    assert app.document.data == before
    paste_cells(app, sheet, "\n".join(["\t".join(["0"] * 12)] * 5))
    assert len(sheet.get_sheet_data()) == 2
    assert all(len(row) == 9 for row in sheet.get_sheet_data())


@pytest.mark.parametrize("action", ["save", "navigation", "close"])
@pytest.mark.parametrize("clear_focus", [False, True])
def test_ground_pending_editor_commits_before_actions(app, monkeypatch, action, clear_focus):
    sheet = ground_sheet(app)
    pending_text(app, sheet, "7.25")
    if clear_focus:
        withdraw_without_focus(app)
        assert app.root.focus_get() is None
        assert sheet.MT.text_editor.open
    assert app.dirty
    if action == "save":
        assert app.save()
    elif action == "navigation":
        app.select_path(("下部構造",))
        assert app.current_path == ("下部構造",)
    else:
        asked = []
        monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *a, **k: asked.append(True) or None)
        assert not app.close()
        assert asked == [True]
        assert app.flush_fields()
    assert app.document.data["地盤データ"]["層"][1]["層厚"] == 7.25


def test_focusless_invalid_editor_blocks_atomic_flush_and_retains_undo(app):
    sheet = ground_sheet(app)
    before = copy.deepcopy(app.document.data)
    paste_cells(app, sheet, "18", row=1, column=3)
    pending_text(app, sheet, "invalid")
    withdraw_without_focus(app)
    assert app.root.focus_get() is None
    assert sheet.MT.text_editor.open
    assert not app.flush_fields()
    assert app.document.data == before
    assert not sheet.MT.text_editor.open
    sheet.undo()
    assert sheet.get_cell_data(1, 1) == ""
    assert app.flush_fields()
    assert app.document.data["地盤データ"]["層"][1]["N値"] == 18


def test_real_control_v_z_y_bindings(app):
    sheet = ground_sheet(app)
    app.root.deiconify()
    app.root.update()
    original = sheet.get_cell_data(1, 1)
    app.root.clipboard_clear()
    app.root.clipboard_append("7.25")
    sheet.select_cell(1, 1)
    sheet.MT.focus_force()
    app.root.update()
    sheet.MT.event_generate("<Control-v>")
    app.root.update()
    assert sheet.get_cell_data(1, 1) == "7.25"
    sheet.MT.event_generate("<Control-z>")
    app.root.update()
    assert sheet.get_cell_data(1, 1) == original
    sheet.MT.event_generate("<Control-y>")
    app.root.update()
    assert sheet.get_cell_data(1, 1) == "7.25"


@pytest.mark.parametrize("geometry", ["980x640", "1360x900"])
def test_fixed_reaction_labels_and_last_total_visible_together(app, geometry):
    from src.editor_grid import SheetCell

    app.root.deiconify()
    app.root.geometry(geometry)
    app.root.update()
    app.select_path(("上部工反力",))
    detail, _, _, outer_column = reaction_table(app, "終点側", "C支点", "D支点")
    cell = SheetCell(detail.sheet, 10, outer_column, app._changed)
    cell.focus_set()
    app.root.update()
    sheet = cell.sheet
    assert sheet.get_index_data(cell.row) == "列車4 分担 L4"
    left = app.canvas.winfo_rootx()
    right = left + app.canvas.winfo_width()
    top = app.canvas.winfo_rooty()
    bottom = top + app.canvas.winfo_height()
    x1, y1, x2, y2 = cell.bounds()
    assert left <= sheet.RI.winfo_rootx() < x1 < x2 <= right
    assert top <= y1 < y2 <= bottom


def test_wheel_routes_short_table_to_outer_and_long_table_to_inner(app):
    app.root.attributes("-topmost", True)
    app.root.deiconify()
    app.root.geometry("980x640")
    app.root.update()
    short = field(app, ("下部構造", "寸法", "側面", "B1")).widget.sheet
    app.canvas.yview_moveto(0)
    app.root.update()
    before = app.canvas.yview()
    table_wheel(app, short)
    app.root.update()
    assert app.canvas.yview() != before
    assert short.MT.yview() == (0.0, 1.0)

    app.select_path(("上部構造",))
    cell = field(app, ("上部構造", "列車", "車両名")).widget
    cell.focus_set()
    app.root.update()
    long = cell.sheet
    outer_before = app.canvas.yview()
    inner_before = long.MT.yview()
    table_wheel(app, long)
    app.root.update()
    assert long.MT.yview() != inner_before
    assert app.canvas.yview() == outer_before


def table_wheel(app, sheet, *, state=0):
    table = sheet.MT
    rootx, rooty = table.winfo_rootx() + 10, table.winfo_rooty() + 10
    assert app.root.winfo_containing(rootx, rooty) == table
    table.event_generate("<MouseWheel>", delta=-120, state=state,
                         x=10, y=10, rootx=rootx, rooty=rooty)


@pytest.mark.parametrize("state", [0x0001, 0x0004], ids=["shift", "control"])
def test_modified_wheel_does_not_scroll_outer_canvas(app, state):
    app.root.attributes("-topmost", True)
    app.root.deiconify()
    app.root.geometry("980x640")
    app.root.update()
    app.select_path(("上部構造",))
    cell = field(app, ("上部構造", "起点側", "桁長", "L1")).widget
    cell.focus_set()
    app.root.update()
    outer_before = app.canvas.yview()
    horizontal_before = cell.sheet.MT.xview()
    table_wheel(app, cell.sheet, state=state)
    app.root.update()
    assert app.canvas.yview() == outer_before
    if state == 0x0001:
        assert cell.sheet.MT.xview() != horizontal_before


def test_ground_selection_controls_layer_operations_and_keeps_unknowns(app):
    layers = app.document.data["地盤データ"]["層"]
    layers[1]["拡張"] = {"code": "001", "memo": "a\nb"}
    sheet = ground_sheet(app)
    sheet.select_cell(1, 2)
    assert app.soil_selected.get() == 1
    app.soil_duplicate()
    assert len(layers) == 3
    assert layers[2]["拡張"] == {"code": "001", "memo": "a\nb"}
    assert app.soil_selected.get() == 2
    assert app.grids[0].get_currently_selected().row == 2


def test_ground_missing_and_container_cells_are_readonly(app):
    layers = app.document.data["地盤データ"]["層"]
    del layers[0]["N値"]
    layers[1]["N値"] = {"unknown": 7}
    layers[0]["土質区分"] = "未知の土質"
    sheet = ground_sheet(app)
    assert sheet.get_cell_data(0, 2) == "未知の土質"
    paste_cells(app, sheet, "99\n88", column=3)
    assert app.save()
    assert "N値" not in layers[0]
    assert layers[1]["N値"] == {"unknown": 7}
    assert layers[0]["土質区分"] == "未知の土質"


@pytest.mark.parametrize("section", ["下部構造", "上部構造", "上部工反力", "地盤データ"])
def test_all_inputs_are_sheet_cells_and_preserve_existing_paths(app, section):
    from src.editor_grid import SheetCell
    from tksheet import Sheet

    expected = json.loads((Path(__file__).parent / "fixtures" / "editor_field_paths.json").read_text("utf-8"))
    app.select_path((section,))
    from src.input_formulas import FORMULAS_BY_PATH
    paths = {tuple(path) for path in expected[section]}
    assert {item.path for item in app.fields} == paths.difference(FORMULAS_BY_PATH)
    assert app.grid_cells.keys() == paths
    assert all(isinstance(item.text, SheetCell) and isinstance(item.widget.sheet, Sheet) for item in app.fields)


def test_reaction_range_paste_keeps_special_values_and_automatic_totals(app):
    app.select_path(("上部工反力",))
    base = ("上部工反力", "起点側", "B支点", "支承")
    cell = field(app, base + (0, "固定死荷重_D1")).widget
    assert hasattr(cell, "sheet"), "reaction inputs must use a Sheet"
    paste_cells(app, cell.sheet, "-\t0\n\t123.5", cell.row, cell.column)
    _, _, inner, outer = reaction_table(app)
    for column in (inner,):
        assert float(cell.sheet.get_cell_data(cell.row, column)) == 0
        assert float(cell.sheet.get_cell_data(cell.row + 1, column)) == 123.5
    assert app.save()
    bearings = app.document.data["上部工反力"]["起点側"]["B支点"]["支承"]
    assert bearings[0]["固定死荷重_D1"] == "-"
    assert bearings[1]["固定死荷重_D1"] == 0
    assert bearings[0]["付加死荷重_D2"] is None
    assert bearings[1]["付加死荷重_D2"] == 123.5
    for side, points in (("起点側", ("B支点",)), ("終点側", ("C支点",))):
        assert all("合計" not in app.document.data["上部工反力"][side].get(point, {}) for point in points)


def reaction_table(app, side="起点側", support="B支点", outer="A支点"):
    base = ("上部工反力", side, support, "支承")
    cell = field(app, base + (0, "固定死荷重_D1")).widget
    sheet = cell.sheet
    headers = sheet.headers()
    bearings = app.document.data["上部工反力"][side][support]["支承"]
    inner_column = cell.column + len(bearings)
    outer_column = headers.index(outer)
    assert headers[inner_column] == support
    return cell, bearings, inner_column, outer_column


def numeric_reaction_sum(bearings, *keys):
    values = []
    for bearing in bearings:
        value = bearing
        for key in keys:
            value = value[key]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(value)
    return sum(values)


@pytest.mark.parametrize(
    "side,support,outer",
    [("起点側", "B支点", "A支点"), ("終点側", "C支点", "D支点")],
)
def test_reaction_bc_totals_are_automatic_and_ad_dead_totals_are_inputs(app, side, support, outer):
    for point in (support, outer):
        app.document.data["上部工反力"][side].setdefault(point, {})["合計"] = {
            "支承位置": 99999,
            "固定死荷重_D1": 99999,
            "付加死荷重_D2": 99999,
            **{key: 99999 for key, _ in SNOW_LOAD_CASES},
            "列車分担": {f"L{i}": 99999 for i in range(1, 5)},
        }
    app.select_path(("上部工反力",))
    cell, bearings, inner, outer_column = reaction_table(app, side, support, outer)
    sheet = cell.sheet
    assert len(bearings) == 10
    assert (inner, outer_column) == ((11, 0) if side == "起点側" else (10, 11))
    assert sheet.get_cell_data(0, inner) == "合計 (自動)"
    assert sheet.get_cell_data(0, outer_column) == "合計 (入力)"
    for column in (inner, outer_column):
        assert sheet.get_cell_data(1, column) == "-"
    for row, key in ((2, "固定死荷重_D1"), (3, "付加死荷重_D2")):
        assert float(sheet.get_cell_data(row, inner)) == pytest.approx(numeric_reaction_sum(bearings, key))
        assert float(sheet.get_cell_data(row, outer_column)) == 99999
        assert not sheet.MT.cell_options[(row, outer_column)].get("readonly")
    for row in range(11):
        assert sheet.MT.cell_options[(row, inner)].get("readonly") is True
        if row not in (2, 3, 4, 5, 6):
            assert sheet.MT.cell_options[(row, outer_column)].get("readonly") is True
    for row, index in enumerate(range(1, 5), start=7):
        assert float(sheet.get_cell_data(row, inner)) == pytest.approx(
            numeric_reaction_sum(bearings, "列車分担", f"L{index}")
        )
        assert sheet.get_cell_data(row, outer_column) == "-"
    assert {item.path for item in app.fields if "合計" in item.path} == gui.MANUAL_REACTION_TOTAL_PATHS
    assert {path for path in app.grid_cells if "合計" in path} == gui.MANUAL_REACTION_TOTAL_PATHS


@pytest.mark.parametrize("side,support,outer", [("起点側", "B支点", "A支点"), ("終点側", "C支点", "D支点")])
def test_manual_reaction_totals_survive_detail_undo_navigation_save_and_reopen(app, monkeypatch, side, support, outer):
    from src.reaction_calculator import calculate_reactions
    from src.reaction_inputs import parse_reaction_input

    app.select_path(("上部工反力",))
    cell, bearings, inner, outer_column = reaction_table(app, side, support, outer)
    sheet = cell.sheet
    assert [sheet.get_cell_data(row, outer_column) for row in (2, 3)] == ["", ""]
    initial_total = copy.deepcopy(app.document.data["上部工反力"][side].get(outer, {}).get("合計", {}))
    assert not app.dirty
    paste_cells(app, sheet, "0\n-12.5", 2, outer_column)
    paste_cells(app, sheet, "600\n25", cell.row, cell.column)
    assert [sheet.get_cell_data(row, outer_column) for row in (2, 3)] == ["0", "-12.5"]
    sheet.undo()
    assert [sheet.get_cell_data(row, outer_column) for row in (2, 3)] == ["0", "-12.5"]
    sheet.redo()
    assert [sheet.get_cell_data(row, outer_column) for row in (2, 3)] == ["0", "-12.5"]
    app.select_path(("上部構造",))
    assert app.save()
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **k: str(app.document.path))
    assert app.open_file()
    app.select_path(("上部工反力",))
    total = app.document.data["上部工反力"][side][outer]["合計"]
    assert total == {**initial_total, "固定死荷重_D1": 0, "付加死荷重_D2": -12.5}
    assert type(total["固定死荷重_D1"]) is int
    assert type(total["付加死荷重_D2"]) is float
    assert field(app, ("上部工反力", side, outer, "合計", "固定死荷重_D1")).text.get() == "0"
    _, bearings, inner, outer_column = reaction_table(app, side, support, outer)
    sheet = field(app, ("上部工反力", side, outer, "合計", "固定死荷重_D1")).widget.sheet
    assert float(sheet.get_cell_data(2, inner)) == pytest.approx(numeric_reaction_sum(bearings, "固定死荷重_D1"))
    assert not app.dirty
    result = calculate_reactions(parse_reaction_input(app.document.data))
    assert result["dead_loads"]["points"][outer[0]] == {"D1": 0, "D2": -12.5, "total": -12.5}


def test_clearing_manual_reaction_total_restores_blank_fallback_without_changing_other_input(app):
    from src.reaction_inputs import parse_reaction_input

    app.select_path(("上部工反力",))
    before = copy.deepcopy(app.document.data)
    item = field(app, ("上部工反力", "起点側", "A支点", "合計", "固定死荷重_D1"))
    item.text.set("0")
    assert app.flush_fields()
    assert parse_reaction_input(app.document.data).dead.a.d1 == 0
    item.text.set("")
    assert app.save()
    saved = json.loads(app.document.path.read_text("utf-8"))
    expected = before["上部工反力"]["起点側"].get("A支点", {}).get("合計", {})
    assert saved["上部工反力"]["起点側"]["A支点"]["合計"] == {**expected, "固定死荷重_D1": None}
    result = parse_reaction_input(saved)
    assert result.dead.a.d1 == sum(row.d1 for row in result.dead.b)
    assert saved["上部工反力"]["終点側"].get("D支点") == before["上部工反力"]["終点側"].get("D支点")


def test_reaction_automatic_totals_follow_paste_delete_undo_redo(app):
    app.select_path(("上部工反力",))
    cell, bearings, inner, outer = reaction_table(app)
    original = copy.deepcopy(bearings)
    before = numeric_reaction_sum(bearings, "固定死荷重_D1")
    after = before - numeric_reaction_sum(bearings[:2], "固定死荷重_D1") + 300
    sheet = cell.sheet

    def assert_total(expected):
        for column in (inner,):
            assert float(sheet.get_cell_data(cell.row, column)) == pytest.approx(expected)

    paste_cells(app, sheet, "100\t200", cell.row, cell.column)
    assert_total(after)
    assert bearings == original  # Totals update before document flush.
    sheet.undo()
    assert_total(before)
    sheet.redo()
    assert_total(after)
    sheet.select_cell(cell.row, cell.column)
    sheet.delete()
    assert sheet.get_cell_data(cell.row, cell.column) == ""
    assert_total(after - 100)
    sheet.undo()
    assert sheet.get_cell_data(cell.row, cell.column) == "100"
    assert_total(after)


def test_reaction_automatic_totals_skip_blank_and_inapplicable(app):
    app.select_path(("上部工反力",))
    cell, bearings, inner, outer = reaction_table(app)
    expected_d1 = numeric_reaction_sum(bearings[3:], "固定死荷重_D1")
    expected_d2 = numeric_reaction_sum(bearings[3:], "付加死荷重_D2") + 123.5
    sheet = cell.sheet
    paste_cells(app, sheet, "-\t0\t\n\t123.5\t0", cell.row, cell.column)
    assert sheet.get_sheet_data()[cell.row][cell.column:cell.column + 3] == ["-", "0", ""]
    assert sheet.get_sheet_data()[cell.row + 1][cell.column:cell.column + 3] == ["", "123.5", "0"]
    for column in (inner,):
        assert float(sheet.get_cell_data(cell.row, column)) == pytest.approx(expected_d1)
        assert float(sheet.get_cell_data(cell.row + 1, column)) == pytest.approx(expected_d2)
    assert app.save()
    saved = json.loads(app.document.path.read_text("utf-8"))
    saved_bearings = saved["上部工反力"]["起点側"]["B支点"]["支承"]
    assert [bearing["固定死荷重_D1"] for bearing in saved_bearings[:3]] == ["-", 0, None]
    assert [bearing["付加死荷重_D2"] for bearing in saved_bearings[:3]] == [None, 123.5, 0]


def test_reaction_invalid_detail_preview_and_atomic_flush(app):
    app.select_path(("上部工反力",))
    cell, bearings, inner, outer = reaction_table(app)
    before = copy.deepcopy(app.document.data)
    initial_d1 = numeric_reaction_sum(bearings, "固定死荷重_D1")
    initial_d2 = numeric_reaction_sum(bearings, "付加死荷重_D2")
    expected_d2 = numeric_reaction_sum(bearings[1:], "付加死荷重_D2") + 123.5
    sheet = cell.sheet
    paste_cells(app, sheet, "invalid\n123.5", cell.row, cell.column)
    for column in (inner,):
        assert sheet.get_cell_data(cell.row, column) == "入力エラー"
        assert float(sheet.get_cell_data(cell.row + 1, column)) == pytest.approx(expected_d2)
    assert not app.flush_fields()
    assert app.document.data == before
    assert sheet.get_cell_data(cell.row, cell.column) == "invalid"
    assert sheet.get_cell_data(cell.row + 1, cell.column) == "123.5"
    sheet.undo()
    for column in (inner,):
        assert float(sheet.get_cell_data(cell.row, column)) == pytest.approx(initial_d1)
        assert float(sheet.get_cell_data(cell.row + 1, column)) == pytest.approx(initial_d2)
    paste_cells(app, sheet, "600\n123.5", cell.row, cell.column)
    assert app.flush_fields()
    for column in (inner,):
        assert float(sheet.get_cell_data(cell.row, column)) == pytest.approx(
            numeric_reaction_sum(bearings, "固定死荷重_D1")
        )
        assert float(sheet.get_cell_data(cell.row + 1, column)) == pytest.approx(expected_d2)


def test_reaction_decimal_totals_are_readable_without_rounding_inputs(app):
    app.select_path(("上部工反力",))
    cell, bearings, inner, outer = reaction_table(app)
    for index in range(len(bearings)):
        field(app, ("上部工反力", "起点側", "B支点", "支承", index, "固定死荷重_D1")).text.set("")
    paste_cells(app, cell.sheet, "0.1\t0.2", cell.row, cell.column)
    for column in (inner,):
        assert cell.sheet.get_cell_data(cell.row, column) == "0.3"
    assert app.save()
    saved = json.loads(app.document.path.read_text(encoding="utf-8"))
    saved_bearings = saved["上部工反力"]["起点側"]["B支点"]["支承"]
    assert [bearing["固定死荷重_D1"] for bearing in saved_bearings[:2]] == [0.1, 0.2]
    for side, points in (("起点側", ("B支点",)), ("終点側", ("C支点",))):
        assert all("合計" not in saved["上部工反力"][side].get(point, {}) for point in points)


def open_legacy_snow_input(app):
    from src.editor_model import encode
    from test_editor_model import snow_free_input

    data = snow_free_input()
    data["上部工反力"]["起点側"]["B支点"]["追加情報"] = {"合計": "保持", "雪荷重_100年確率": 123}
    app.document.path.write_bytes(encode(data))
    app.document = gui.EditorDocument.open(app.document.path)
    app.refresh_tree(("上部工反力",))
    return data


def test_all_legacy_snow_inputs_are_virtual_editable_blanks_and_noop_save(app):
    data = open_legacy_snow_input(app)
    original = app.document.path.read_bytes()
    snow_paths = {item.path for item in app.fields if item.path[-1] in {key for key, _ in SNOW_LOAD_CASES}}
    assert len(snow_paths) == 66
    assert all(field(app, path).text.get() == "" for path in snow_paths)
    assert not app.dirty
    assert app.save()
    assert app.document.data == data
    assert app.document.path.read_bytes() == original
    for side, support, outer in (("起点側", "B支点", "A支点"), ("終点側", "C支点", "D支点")):
        detail, _, inner, outer_column = reaction_table(app, side, support, outer)
        sheet = detail.sheet
        assert [sheet.get_index_data(row) for row in range(11)] == [
            "支承名称", "支承位置 (m)", "固定死荷重 D1", "付加死荷重 D2",
            "雪荷重 2年確率", "雪荷重 10年確率", "雪荷重 30年確率",
            "列車1 分担 L1", "列車2 分担 L2", "列車3 分担 L3", "列車4 分担 L4",
        ]
        for row in (4, 5, 6):
            assert sheet.get_cell_data(row, inner) == "0"
            assert sheet.MT.cell_options[(row, inner)]["readonly"] is True
            assert not sheet.MT.cell_options[(row, outer_column)].get("readonly")
            assert sheet.get_cell_data(row, outer_column) == ""


@pytest.mark.parametrize("path", [
    ("上部工反力", "起点側", "A支点", "合計", "雪荷重_10年確率"),
    ("上部工反力", "終点側", "C支点", "支承", 9, "雪荷重_30年確率"),
])
def test_legacy_single_snow_edit_materializes_only_edited_key(app, path):
    data = open_legacy_snow_input(app)
    expected = copy.deepcopy(data)
    gui.set_at(expected, path, 0)
    field(app, path).text.set("0")
    assert app.save()
    assert json.loads(app.document.path.read_text("utf-8")) == expected
    assert not app.dirty
    reopened = gui.EditorDocument.open(app.document.path)
    assert reopened.data == expected
    assert not reopened.dirty


@pytest.mark.parametrize("side,support,outer", [("起点側", "B支点", "A支点"), ("終点側", "C支点", "D支点")])
def test_snow_rectangle_totals_follow_paste_delete_undo_redo_and_typed_save(app, side, support, outer, monkeypatch):
    from src.reaction_calculator import calculate_reactions
    from src.reaction_inputs import parse_reaction_input

    open_legacy_snow_input(app)
    detail, _, inner, outer_column = reaction_table(app, side, support, outer)
    sheet = detail.sheet
    cell = field(app, ("上部工反力", side, support, "支承", 0, "雪荷重_2年確率")).widget
    assert cell.row == 4
    paste_cells(app, sheet, "1\t2\n10\t20\n100\t200", cell.row, cell.column)
    assert [sheet.get_cell_data(row, inner) for row in (4, 5, 6)] == ["3", "30", "300"]
    sheet.undo()
    assert [sheet.get_cell_data(row, inner) for row in (4, 5, 6)] == ["0", "0", "0"]
    assert not app.dirty
    sheet.redo()
    assert [sheet.get_cell_data(row, inner) for row in (4, 5, 6)] == ["3", "30", "300"]
    sheet.select_cell(cell.row, cell.column)
    sheet.delete()
    assert sheet.get_cell_data(4, inner) == "2"
    sheet.undo()
    assert sheet.get_cell_data(4, inner) == "3"
    paste_cells(app, sheet, "0\n-7.5", 4, outer_column)
    before = [sheet.get_cell_data(row, inner) for row in (4, 5, 6)]
    paste_cells(app, sheet, "999\n999\n999", 4, inner)
    assert [sheet.get_cell_data(row, inner) for row in (4, 5, 6)] == before
    assert app.save()
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kwargs: str(app.document.path))
    assert app.open_file()
    app.select_path(("上部工反力",))
    assert not app.dirty
    saved = app.document.data["上部工反力"][side]
    assert "合計" not in saved[support]
    assert saved[outer]["合計"] == {"雪荷重_2年確率": 0, "雪荷重_10年確率": -7.5}
    assert type(saved[outer]["合計"]["雪荷重_2年確率"]) is int
    assert type(saved[outer]["合計"]["雪荷重_10年確率"]) is float
    result = calculate_reactions(parse_reaction_input(app.document.data))["snow_loads"]["points"]
    assert result[support[0]] == {"雪荷重_2年確率": 3, "雪荷重_10年確率": 30, "雪荷重_30年確率": 300}
    assert result[outer[0]] == {"雪荷重_2年確率": 0, "雪荷重_10年確率": -7.5, "雪荷重_30年確率": 300}


@pytest.mark.parametrize("path", [
    ("上部工反力", "起点側", "B支点", "支承", 0, "雪荷重_2年確率"),
    ("上部工反力", "終点側", "D支点", "合計", "雪荷重_30年確率"),
])
def test_snow_dash_can_be_saved_and_is_rejected_by_calculation(app, path):
    from src.inputs import InputError
    from src.reaction_inputs import parse_reaction_input

    open_legacy_snow_input(app)
    field(app, path).text.set("-")
    assert app.save()
    saved = json.loads(app.document.path.read_text("utf-8"))
    assert gui.get_at(saved, path) == "-"
    with pytest.raises(InputError, match=path[-1]):
        parse_reaction_input(saved)


def test_invalid_snow_edit_blocks_atomic_save_and_preserves_other_pending_edits(app):
    open_legacy_snow_input(app)
    before = copy.deepcopy(app.document.data)
    raw = app.document.path.read_bytes()
    base = ("上部工反力", "起点側", "B支点", "支承", 0)
    cell = field(app, base + ("雪荷重_2年確率",)).widget
    paste_cells(app, cell.sheet, "5\nbroken\n9", cell.row, cell.column)
    _, _, inner, _ = reaction_table(app)
    assert cell.sheet.get_cell_data(5, inner) == "入力エラー"
    assert not app.save()
    assert app.document.data == before
    assert app.document.path.read_bytes() == raw
    assert field(app, base + ("雪荷重_30年確率",)).text.get() == "9"


def test_property_grid_paste_cannot_overwrite_labels_or_units(app):
    cell = field(app, ("下部構造", "土かぶり", "起点側_df1")).widget
    assert hasattr(cell, "sheet"), "property inputs must use a Sheet"
    sheet = cell.sheet
    label, _, unit = sheet.get_sheet_data()[cell.row]
    before_units = copy.deepcopy(app.document.data["下部構造"].get("単位"))
    paste_cells(app, sheet, "bad label\t6.25\tbad unit", cell.row, 0)
    assert sheet.get_sheet_data()[cell.row] == [label, "6.25", unit]
    assert app.save()
    assert app.document.data["下部構造"].get("単位") == before_units
    assert app.document.data["下部構造"]["土かぶり"]["起点側_df1"] == 6.25


class PendingCalculation(gui.CalculationController):
    """A controllable completion boundary; real CLI coverage lives with the runner."""

    def __init__(self, output_dir):
        super().__init__(output_dir)
        self.calls = []
        self.completion = None

    def mark_stale(self):
        if self.state == "success":
            self.state = "stale"

    def start(self, path, expected_sha256, *, jrsnap=False):
        from src.editor_calculation import CalculationJob

        self.calls.append((path, expected_sha256))
        self.job = CalculationJob("test-run", path, self.output_dir, expected_sha256, jrsnap=jrsnap)
        self.running = True
        self.state = "running"
        return self.job

    def poll(self):
        if self.completion is None:
            return None
        self.result, self.completion = self.completion, None
        self.state = "success" if self.result.success else "failed"
        from src.editor_calculation import _regular_snapshot
        self._verified_outputs = {
            path: _regular_snapshot(path) for pdf in self.result.pdf_paths
            for path in (pdf, pdf.with_suffix(".json")) if path.is_file()
        }
        self.running = False
        return self.result


def controlled_calculation(app):
    controller = PendingCalculation(app.calculation.output_dir)
    app.calculation = controller
    return controller


def complete_calculation(app, controller, *, success=True, paths=()):
    from src.editor_calculation import CalculationResult

    controller.completion = CalculationResult(controller.job, success, "完了" if success else "計算失敗", stderr="" if success else "入力を確認してください\n" * 40, returncode=0 if success else 2, pdf_paths=tuple(paths))
    if app._calculation_after is not None:
        app.root.after_cancel(app._calculation_after)
    app._poll_calculation()


def make_preview_pdf(path, *, pages=2):
    import pymupdf

    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as pdf:
        for index in range(pages):
            pdf.new_page().insert_text((50, 50), f"Page {index + 1}")
        pdf.save(path)


def pdf_labels(app):
    if app.pdf_dialog is None:
        return tuple(entry.label for entry in app._pdf_catalog().entries)
    listing = app.pdf_dialog.pdf_list
    return tuple(listing.item(node, "text") for node in listing.get_children())


def choose_pdf(app, path):
    assert app.pdf_dialog is not None
    listing = app.pdf_dialog.pdf_list
    listing.selection_set(listing.get_children()[app._pdf_paths.index(path)])
    listing.event_generate("<<TreeviewSelect>>")
    app.root.update_idletasks()
    assert app._selected_pdf == path
    assert app.pdf_dialog.selected_path == path


def test_calculation_page_exists_without_input_sections(app):
    app.document.data.clear()
    app.refresh_tree()
    assert set(app.paths.values()) == {gui.CALCULATION_PAGE, gui.REBAR_PAGE}
    assert app.current_path is gui.CALCULATION_PAGE
    assert app.heading.get() == "計算・印刷"
    assert "保存して計算・PDF出力" in button_labels(app.root)
    assert app.document.data == {}


@pytest.mark.parametrize("namespace", ["jrsnap_longitudinal", "jrsnap_transverse"])
def test_jrsnap_settings_display_blank_and_edit_save_reload_without_defaults(app, namespace):
    app.select_path(gui.CALCULATION_PAGE)
    before = app.document.path.read_bytes()
    assert app.jrsnap_enabled.get() is False
    keys = ("shear_factor_vcd", "shear_factor_vsd", "shear_factor_vdd", "aggregate_max_mm")
    assert all(field(app, (namespace, key)).text.get() == "" for key in keys)
    assert "部材係数 γb（Vcd）" in str(app.jrsnap_grids[namespace].get_sheet_data())
    assert app.save()
    assert app.document.path.read_bytes() == before
    assert all(name not in app.document.data for name in ("jrsnap_longitudinal", "jrsnap_transverse"))
    for key, value in zip(keys, ("2", "1.3", "1.8", "25.5"), strict=True):
        field(app, (namespace, key)).text.set(value)
    assert app.save()
    expected = dict(zip(keys, (2, 1.3, 1.8, 25.5), strict=True))
    loaded = gui.EditorDocument.open(app.document.path)
    assert loaded.data[namespace] == expected
    other = "jrsnap_transverse" if namespace == "jrsnap_longitudinal" else "jrsnap_longitudinal"
    assert other not in loaded.data
    app.document = loaded
    app.render_fields()
    assert field(app, (namespace, "aggregate_max_mm")).text.get() == "25.5"
    field(app, (namespace, "shear_factor_vcd")).text.set("")
    assert app.save()
    assert json.loads(app.document.path.read_text("utf-8"))[namespace]["shear_factor_vcd"] is None


def test_jrsnap_selection_is_captured_and_saved_input_survives_failed_generation(app):
    controller = controlled_calculation(app)
    app.select_path(gui.CALCULATION_PAGE)
    field(app, ("jrsnap_longitudinal", "aggregate_max_mm")).text.set("30")
    field(app, ("jrsnap_transverse", "aggregate_max_mm")).text.set("35")
    app.jrsnap_enabled.set(True)
    assert app.start_calculation()
    assert controller.job.jrsnap is True
    assert app.jrsnap_checkbox.instate(["disabled"])
    bindings = ("edit_cell_enabled", "cut_enabled", "paste_enabled", "delete_key_enabled", "undo_enabled")
    for grid in app.jrsnap_grids.values():
        assert all(not getattr(grid.MT, name) for name in bindings)
    saved = app.document.path.read_bytes()
    assert json.loads(saved)["jrsnap_longitudinal"]["aggregate_max_mm"] == 30
    assert json.loads(saved)["jrsnap_transverse"]["aggregate_max_mm"] == 35
    app.jrsnap_enabled.set(False)
    assert controller.job.jrsnap is True
    complete_calculation(app, controller, success=False)
    assert app.document.path.read_bytes() == saved
    assert app.jrsnap_checkbox.instate(["!disabled"])
    for grid in app.jrsnap_grids.values():
        assert all(getattr(grid.MT, name) for name in bindings)


@pytest.mark.parametrize("namespace", ["jrsnap_longitudinal", "jrsnap_transverse"])
def test_invalid_jrsnap_setting_blocks_save_without_partial_changes(app, namespace):
    app.select_path(gui.CALCULATION_PAGE)
    before = app.document.path.read_bytes()
    field(app, (namespace, "shear_factor_vcd")).text.set("2")
    field(app, (namespace, "aggregate_max_mm")).text.set("0")
    assert not app.save()
    assert app.document.path.read_bytes() == before
    assert namespace not in app.document.data


@pytest.mark.parametrize("geometry", ["980x640", "1360x900"])
def test_calculation_preview_is_modal_and_input_toolbar_restores(app, geometry):
    app.root.deiconify()
    app.root.geometry(geometry)
    app.select_path(gui.CALCULATION_PAGE)
    app.root.update()
    assert not app.toolbar.winfo_ismapped()
    assert not app.global_path_label.winfo_ismapped()
    assert app.pdf_dialog is None
    assert "PDFプレビュー" in button_labels(app.root)
    assert not hasattr(app, "pdf_choice")
    assert app.open_pdf_preview()
    dialog = app.pdf_dialog
    app.root.update()
    assert app.root.grab_current() is dialog
    assert dialog.preview.canvas.winfo_height() >= 230
    assert dialog.pdf_list.winfo_rootx() < dialog.preview.winfo_rootx()
    app.select_path(("下部構造",))
    app.root.update()
    assert app.pdf_dialog is None
    assert not dialog.winfo_exists()
    assert app.root.grab_current() is None
    assert app.toolbar.winfo_ismapped()
    assert app.global_path_label.winfo_ismapped()


@pytest.mark.parametrize("action", ["navigate", "calculate"])
def test_calculation_actions_flush_pending_grid_editor(app, action):
    controller = controlled_calculation(app)
    sheet = ground_sheet(app)
    pending_text(app, sheet, "7.25")
    if action == "navigate":
        app.select_path(gui.CALCULATION_PAGE)
        assert app.current_path is gui.CALCULATION_PAGE
        assert app.dirty
    else:
        assert app.start_calculation()
        assert json.loads(app.document.path.read_text("utf-8"))["地盤データ"]["層"][1]["層厚"] == 7.25
        assert controller.calls[0][1] == app.document._fingerprint
        complete_calculation(app, controller)
    assert app.document.data["地盤データ"]["層"][1]["層厚"] == 7.25
    app.select_path(("地盤データ",))
    assert field(app, ("地盤データ", "層", 1, "層厚")).text.get() == "7.25"


def test_invalid_pending_value_blocks_navigation_and_calculation(app):
    controller = controlled_calculation(app)
    sheet = ground_sheet(app)
    pending_text(app, sheet, "invalid")
    app.select_path(gui.CALCULATION_PAGE)
    assert app.current_path == ("地盤データ",)
    assert not app.start_calculation()
    assert controller.calls == []
    assert not app._calculation_busy


@pytest.mark.parametrize("failure", ["save", "clean_external_change", "after_save_change"])
def test_calculation_never_spawns_after_save_or_fingerprint_failure(app, monkeypatch, failure):
    controller = controlled_calculation(app)
    assert app.save()
    app.select_path(gui.CALCULATION_PAGE)
    assert app.open_pdf_preview()
    dialog = app.pdf_dialog
    before = app.document.path.read_bytes()
    if failure == "save":
        def fail_save(*args, **kwargs):
            raise OSError("保存失敗")
        monkeypatch.setattr(app.document, "save", fail_save)
    elif failure == "clean_external_change":
        app.document.path.write_bytes(before + b"\n")
        assert not app.dirty
    else:
        original_save = app.save
        def modify_after_save():
            result = original_save()
            app.document.path.write_bytes(before + b"\n")
            return result
        monkeypatch.setattr(app, "save", modify_after_save)
    assert not app.start_calculation()
    assert controller.calls == []
    assert not app._calculation_busy
    assert app.pdf_dialog is dialog
    assert dialog.winfo_exists()
    assert app.root.grab_current() is dialog


def test_calculation_guards_every_entry_until_completion_and_keeps_events_running(app, monkeypatch):
    controller = controlled_calculation(app)
    app.select_path(gui.CALCULATION_PAGE)
    assert app.open_pdf_preview()
    previous_dialog = app.pdf_dialog
    original_start = controller.start
    def guarded_start(path, sha):
        assert app._calculation_busy  # Guard is acquired before process dispatch.
        assert all(button.instate(["disabled"]) for button in app._toolbar_buttons)
        assert app.calculate_button.instate(["disabled"])
        assert app.preview_button.instate(["disabled"])
        assert app.pdf_dialog is None
        assert not previous_dialog.winfo_exists()
        assert app.root.grab_current() is None
        return original_start(path, sha)
    monkeypatch.setattr(controller, "start", guarded_start)
    assert app.start_calculation()
    for method in (app.open_file, app.save, app.save_as, app.check_calculation,
                   app.confirm_discard, app.flush_fields, app.start_calculation,
                   app.open_pdf_preview, app.close):
        assert method() is False
    app.select_path(("下部構造",))
    assert app.current_path is gui.CALCULATION_PAGE
    previous_data = copy.deepcopy(app.document.data)
    app.soil_add()
    assert app.document.data == previous_data
    def forbidden_dialog(**kwargs):
        pytest.fail("A keyboard shortcut bypassed the running guard")
    monkeypatch.setattr(gui.filedialog, "askopenfilename", forbidden_dialog)
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", forbidden_dialog)
    app.root.deiconify()
    app.root.focus_force()
    app.root.update()
    for event in ("<Control-o>", "<Control-s>", "<Control-Shift-S>"):
        app.root.event_generate(event)
    heartbeat = []
    app.root.after(0, lambda: heartbeat.append(True))
    app.root.update()
    assert heartbeat == [True]
    assert len(controller.calls) == 1
    assert app.root.winfo_exists()
    complete_calculation(app, controller, success=False)
    assert not app._calculation_busy
    assert all(not button.instate(["disabled"]) for button in app._toolbar_buttons)
    assert "失敗" in app.calculation_status.get()
    assert app.pdf_dialog is None
    assert app.calculate_button.instate(["!disabled"])
    assert app.preview_button.instate(["!disabled"])
    assert not app.calculation_progress.winfo_manager()
    assert app.calculation_log.get("1.0", "end").count("入力を確認") == 40
    app.select_path(("下部構造",))
    assert app.current_path == ("下部構造",)
    assert app.save()
    assert app.close()


def test_pdf_selection_order_current_labels_and_state_survive_navigation(app):
    controller = controlled_calculation(app)
    generated = [controller.output_dir / f"{stem}.pdf" for stem in gui.OUTPUT_STEMS]
    extra = controller.output_dir / "追加の長い日本語ファイル名.pdf"
    for path in [extra, *reversed(generated)]:
        make_preview_pdf(path)
    (controller.output_dir / "directory.pdf").mkdir()
    app.select_path(gui.CALCULATION_PAGE)
    assert app._pdf_paths == [*generated, extra]
    assert "6帳票" in app.hint.get()
    assert app.pdf_dialog is None
    assert all("今回未計算" in label for label in pdf_labels(app))
    assert app.open_pdf_preview()
    choose_pdf(app, generated[2])
    assert app.start_calculation()
    assert app.pdf_dialog is None
    complete_calculation(app, controller, paths=generated)
    assert app.pdf_dialog is not None
    assert app._selected_pdf == generated[2]
    assert tuple(path.stem[:4] for path in generated) == ("0500", "0600", "0610", "0620", "0710", "0720")
    assert all("今回の計算結果" in label for label in pdf_labels(app)[:6])
    assert "今回未計算" in pdf_labels(app)[6]
    completed_status = app.calculation_status.get()
    assert "6帳票" in completed_status
    app._changed()
    assert app.calculation_status.get() == completed_status
    old_preview = app.pdf_dialog
    app.select_path(("地盤データ",))
    assert not old_preview.winfo_exists()
    app.select_path(gui.CALCULATION_PAGE)
    assert app.pdf_dialog is None
    assert app.calculation_status.get() == completed_status
    assert app._selected_pdf == generated[2]
    app.select_path(("地盤データ",))
    field(app, ("地盤データ", "層", 1, "層厚")).text.set("7.25")
    assert controller.state == "stale"
    app.select_path(gui.CALCULATION_PAGE)
    assert all("今回未計算" in label for label in pdf_labels(app))
    assert "再計算" in app.calculation_status.get()


@pytest.mark.parametrize("stage,page_count", [("0710", 3), ("0720", 4)])
def test_seismic_report_is_selected_and_all_pages_can_be_previewed(app, stage, page_count):
    controller = controlled_calculation(app)
    paths = [controller.output_dir / f"{stem}.pdf" for stem in gui.OUTPUT_STEMS]
    for path in paths:
        make_preview_pdf(path, pages=page_count if path.stem.startswith(stage + "_") else 1)
    selected = next(path for path in paths if path.stem.startswith(stage + "_"))
    app.select_path(gui.CALCULATION_PAGE)
    assert app.open_pdf_preview()
    choose_pdf(app, selected)
    assert app.start_calculation()
    complete_calculation(app, controller, paths=paths)
    preview = app.pdf_dialog.preview
    assert app._selected_pdf == selected
    assert preview.path.name == selected.name
    assert preview.page_count == page_count
    for page in range(page_count):
        preview.go_to_page(page)
        preview._render()
        assert preview.page_index == page
        assert preview._photo is not None


def test_failed_rerun_marks_remaining_pdf_old_and_can_retry(app):
    controller = controlled_calculation(app)
    pdf = controller.output_dir / f"{gui.OUTPUT_STEMS[0]}.pdf"
    make_preview_pdf(pdf)
    assert app.start_calculation()
    complete_calculation(app, controller, paths=[pdf])
    assert "今回の計算結果" in pdf_labels(app)[0]
    assert app.start_calculation()
    assert app.pdf_dialog is None
    complete_calculation(app, controller, success=False)
    assert pdf.is_file()
    assert app.pdf_dialog is None
    assert "今回未計算" in pdf_labels(app)[0]
    assert app.open_pdf_preview()
    assert app.pdf_dialog.preview.path == pdf
    assert app.start_calculation()
    complete_calculation(app, controller, paths=[pdf])
    assert controller.state == "success"
    assert app.pdf_dialog is not None


def test_clean_external_change_invalidates_previous_success_before_spawn(app):
    controller = controlled_calculation(app)
    pdf = controller.output_dir / f"{gui.OUTPUT_STEMS[0]}.pdf"
    make_preview_pdf(pdf)
    assert app.start_calculation()
    complete_calculation(app, controller, paths=[pdf])
    dialog = app.pdf_dialog
    dialog.preview.go_to_page(1)
    app.document.path.write_bytes(app.document.path.read_bytes() + b"\n")
    assert not app.dirty
    assert not app.start_calculation()
    assert len(controller.calls) == 1
    assert controller.state == "stale"
    assert app.pdf_dialog is dialog
    assert dialog.preview.page_index == 1
    assert dialog.preview.path == pdf
    assert "今回未計算" in pdf_labels(app)[0]


def test_dispatch_exception_restores_controls_and_retains_previous_files(app, monkeypatch):
    controller = controlled_calculation(app)
    pdf = controller.output_dir / f"{gui.OUTPUT_STEMS[0]}.pdf"
    make_preview_pdf(pdf)
    def fail_dispatch(*args, **kwargs):
        raise RuntimeError("起動できません")
    monkeypatch.setattr(controller, "start", fail_dispatch)
    assert not app.start_calculation()
    assert not app._calculation_busy
    assert app.calculate_button.instate(["!disabled"])
    assert "起動できません" in app.calculation_log.get("1.0", "end")
    assert app.pdf_dialog is None
    assert "今回未計算" in pdf_labels(app)[0]
    assert pdf.exists()


def test_preview_failure_keeps_successful_calculation_independent(app, monkeypatch):
    from src import pdf_preview

    controller = controlled_calculation(app)
    pdf = controller.output_dir / f"{gui.OUTPUT_STEMS[0]}.pdf"
    make_preview_pdf(pdf)
    assert app.start_calculation()
    def render_failure(*args, **kwargs):
        raise pdf_preview.PdfPreviewError("描画だけ失敗")
    monkeypatch.setattr(pdf_preview, "render_pdf_page", render_failure)
    complete_calculation(app, controller, paths=[pdf])
    app.root.deiconify()
    app.root.update()
    preview = app.pdf_dialog.preview
    preview._cancel_render()
    preview._render()
    assert "描画だけ失敗" in preview.status.get()
    assert controller.state == "success"
    assert "完了" in app.calculation_status.get()


def test_opening_new_input_invalidates_result_without_modifying_output(app, monkeypatch, tmp_path):
    controller = controlled_calculation(app)
    pdf = controller.output_dir / f"{gui.OUTPUT_STEMS[0]}.pdf"
    make_preview_pdf(pdf)
    before = pdf.read_bytes()
    assert app.start_calculation()
    complete_calculation(app, controller, paths=[pdf])
    other = tmp_path / "other.json"
    other.write_bytes(app.document.path.read_bytes())
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kwargs: str(other))
    assert app.open_file()
    app.select_path(gui.CALCULATION_PAGE)
    assert controller.state == "stale"
    assert app.pdf_dialog is None
    assert "今回未計算" in pdf_labels(app)[0]
    assert pdf.read_bytes() == before


@pytest.mark.parametrize("action", ["refresh", "reload", "page", "zoom"])
def test_external_pdf_replacement_invalidates_current_labels_on_display_action(app, monkeypatch, action):
    controller = controlled_calculation(app)
    pdf = controller.output_dir / f"{gui.OUTPUT_STEMS[0]}.pdf"
    make_preview_pdf(pdf)
    assert app.start_calculation()
    complete_calculation(app, controller, paths=[pdf])
    app.pdf_dialog.preview._render()
    assert controller.state == "success"
    assert "今回の計算結果" in pdf_labels(app)[0]
    replacement = pdf.with_name("replacement.pdf")
    make_preview_pdf(replacement, pages=3)
    replacement.replace(pdf)
    preview = app.pdf_dialog.preview
    if action != "refresh":
        def forbid_refresh(**kwargs):
            pytest.fail("A preview callback reentered a complete list refresh")
        monkeypatch.setattr(app, "_refresh_pdf_list", forbid_refresh)
    if action == "refresh":
        app.pdf_dialog.refresh()
    elif action == "reload":
        preview.reload()
    elif action == "page":
        preview.go_to_page(1)
    else:
        preview.set_zoom(1.25)
    preview._render()
    assert app.pdf_dialog.preview is preview
    assert controller.state == "stale"
    assert "今回未計算" in pdf_labels(app)[0]
    assert "再計算" in app.calculation_status.get()
    assert preview.page_count == 3


@pytest.mark.parametrize("change", ["delete", "corrupt", "unreadable", "json_changed"])
def test_unavailable_or_changed_verified_artifact_invalidates_on_reload(app, monkeypatch, change):
    controller = controlled_calculation(app)
    pdf = controller.output_dir / f"{gui.OUTPUT_STEMS[0]}.pdf"
    make_preview_pdf(pdf)
    result_json = pdf.with_suffix(".json")
    result_json.write_text('{"result":1}', encoding="utf-8")
    assert app.start_calculation()
    complete_calculation(app, controller, paths=[pdf])
    app.pdf_dialog.preview._render()
    if change == "delete":
        pdf.unlink()
    elif change == "corrupt":
        pdf.write_bytes(b"broken PDF")
    elif change == "json_changed":
        result_json.write_text('{"result":2}', encoding="utf-8")
    else:
        original_open = Path.open
        def denied(target, *args, **kwargs):
            if target == pdf:
                raise PermissionError("output read denied")
            return original_open(target, *args, **kwargs)
        monkeypatch.setattr(Path, "open", denied)
    app.pdf_dialog.preview.reload()
    app.pdf_dialog.preview._render()
    assert controller.state == "stale"
    assert "今回未計算" in pdf_labels(app)[0]
    assert "再計算" in app.calculation_status.get()


def test_unchanged_refresh_and_extra_pdf_changes_keep_current_success(app):
    controller = controlled_calculation(app)
    pdf = controller.output_dir / f"{gui.OUTPUT_STEMS[0]}.pdf"
    make_preview_pdf(pdf)
    assert app.start_calculation()
    complete_calculation(app, controller, paths=[pdf])
    app.pdf_dialog.refresh()
    app.pdf_dialog.preview.reload()
    app.pdf_dialog.preview._render()
    assert controller.state == "success"
    assert "今回の計算結果" in pdf_labels(app)[0]
    extra = controller.output_dir / "extra.pdf"
    make_preview_pdf(extra, pages=3)
    app.pdf_dialog.refresh()
    choose_pdf(app, extra)
    extra.write_bytes(b"externally corrupted extra PDF")
    app.pdf_dialog.preview.reload()
    assert controller.state == "success"
    assert "完了" in app.calculation_status.get()
    assert "今回未計算" in pdf_labels(app)[-1]


def test_manual_preview_reuses_singleton_and_reopens_selected_pdf_from_start(app):
    first, second = (app.calculation.output_dir / name for name in ("a.pdf", "b.pdf"))
    for path in (first, second):
        make_preview_pdf(path)
    app.select_path(gui.CALCULATION_PAGE)
    assert app.pdf_dialog is None  # An initial page visit never opens a modal.
    assert app.open_pdf_preview()
    dialog = app.pdf_dialog
    choose_pdf(app, second)
    dialog.preview.go_to_page(1)
    assert dialog.preview.page_index == 1
    assert app.open_pdf_preview()
    assert app.pdf_dialog is dialog
    assert dialog.preview.page_index == 1
    assert [child for child in app.root.winfo_children() if isinstance(child, tk.Toplevel)] == [dialog]
    dialog.close()
    assert app.pdf_dialog is None
    assert app._selected_pdf == second
    assert app.open_pdf_preview()
    assert app.pdf_dialog is not dialog
    assert app.pdf_dialog.selected_path == second
    assert app.pdf_dialog.preview.path == second
    assert app.pdf_dialog.preview.page_index == 0


def test_host_catalog_refresh_returns_snapshot_without_reloading_dialog(app, monkeypatch):
    first, extra = (app.calculation.output_dir / name for name in ("a.pdf", "追加.pdf"))
    make_preview_pdf(first)
    app.select_path(gui.CALCULATION_PAGE)
    assert app.open_pdf_preview()
    dialog = app.pdf_dialog
    original_show = dialog.preview.show_pdf
    loads = []

    def record_show(path):
        loads.append(path)
        original_show(path)

    monkeypatch.setattr(dialog.preview, "show_pdf", record_show)
    make_preview_pdf(extra)
    catalog = app._refresh_pdf_list()
    assert tuple(entry.path for entry in catalog.entries) == (first, extra)
    assert dialog.selected_path == first
    assert len(dialog.pdf_list.get_children()) == 1
    assert loads == []
    dialog.refresh()
    assert len(dialog.pdf_list.get_children()) == 2
    assert loads == [first]


def test_success_opens_only_after_verification_and_busy_release(app, monkeypatch):
    controller = controlled_calculation(app)
    pdf = controller.output_dir / f"{gui.OUTPUT_STEMS[0]}.pdf"
    make_preview_pdf(pdf)
    dialog_class = gui.PdfPreviewDialog
    original_poll = controller.poll
    calls = []

    def verified_poll():
        assert app._calculation_busy
        assert app.pdf_dialog is None
        assert app.preview_button.instate(["disabled"])
        return original_poll()

    def open_after_verification(*args, **kwargs):
        assert not app._calculation_busy
        assert not controller.running
        assert controller.state == "success"
        assert pdf in controller._verified_outputs
        assert app.preview_button.instate(["!disabled"])
        assert not app.calculation_progress.winfo_manager()
        calls.append(True)
        return dialog_class(*args, **kwargs)

    monkeypatch.setattr(controller, "poll", verified_poll)
    monkeypatch.setattr(gui, "PdfPreviewDialog", open_after_verification)
    assert app.start_calculation()
    assert calls == []
    app.root.after_cancel(app._calculation_after)
    app._poll_calculation()
    assert calls == []
    complete_calculation(app, controller, paths=[pdf])
    assert calls == [True]
    assert app.pdf_dialog is not None


@pytest.mark.parametrize("failure", ["construct", "transient", "grab"])
def test_auto_preview_open_failure_preserves_success_and_allows_button_retry(app, monkeypatch, failure):
    controller = controlled_calculation(app)
    pdf = controller.output_dir / f"{gui.OUTPUT_STEMS[0]}.pdf"
    make_preview_pdf(pdf)
    assert app.start_calculation()
    with monkeypatch.context() as failing:
        def fail_setup(*args, **kwargs):
            raise tk.TclError(f"{failure}失敗")
        if failure == "construct":
            failing.setattr(gui.PdfPreviewDialog, "_build_widgets", fail_setup)
        elif failure == "transient":
            failing.setattr(gui.PdfPreviewDialog, "transient", fail_setup)
        else:
            grab_set = gui.PdfPreviewDialog.grab_set
            def fail_after_grab(dialog):
                grab_set(dialog)
                raise tk.TclError("grab失敗")
            failing.setattr(gui.PdfPreviewDialog, "grab_set", fail_after_grab)
        complete_calculation(app, controller, paths=[pdf])
    assert app.pdf_dialog is None
    assert app.root.grab_current() is None
    assert not any(isinstance(child, tk.Toplevel) for child in app.root.winfo_children())
    assert controller.state == "success"
    assert "完了" in app.calculation_status.get()
    assert "プレビューを開けません" in app.calculation_log.get("1.0", "end")
    assert app.preview_button.instate(["!disabled"])
    app.preview_button.invoke()
    assert app.pdf_dialog is not None
    assert app.pdf_dialog.preview.path == pdf


def test_initial_pdf_read_invalidates_labels_after_host_assignment(app, monkeypatch):
    controller = controlled_calculation(app)
    pdf = controller.output_dir / f"{gui.OUTPUT_STEMS[0]}.pdf"
    make_preview_pdf(pdf)
    assert app.start_calculation()
    complete_calculation(app, controller, paths=[pdf])
    app.pdf_dialog.close()
    original_catalog = app._refresh_pdf_list

    def replace_after_catalog(**kwargs):
        catalog = original_catalog(**kwargs)
        replacement = pdf.with_name("replacement.pdf")
        make_preview_pdf(replacement, pages=3)
        replacement.replace(pdf)
        return catalog

    monkeypatch.setattr(app, "_refresh_pdf_list", replace_after_catalog)
    assert app.open_pdf_preview()
    assert controller.state == "stale"
    assert "今回未計算" in pdf_labels(app)[0]
    assert "再計算" in app.calculation_status.get()
    assert app.pdf_dialog.preview.page_count == 3


@pytest.mark.parametrize("outcome", ["saved", "cancelled", "failed"])
def test_save_as_closes_preview_only_after_successful_path_switch(app, monkeypatch, tmp_path, outcome):
    pdf = app.calculation.output_dir / "existing.pdf"
    make_preview_pdf(pdf)
    app.select_path(gui.CALCULATION_PAGE)
    assert app.open_pdf_preview()
    dialog = app.pdf_dialog
    dialog.preview.go_to_page(1)
    previous_path = app.document.path
    destination = tmp_path / "renamed.json"
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **k: "" if outcome == "cancelled" else str(destination))
    if outcome == "failed":
        def fail_save(*args, **kwargs):
            raise OSError("保存失敗")
        monkeypatch.setattr(app.document, "save", fail_save)
    assert app.save_as() is (outcome == "saved")
    assert app._selected_pdf == pdf
    if outcome == "saved":
        assert app.document.path == destination
        assert app.pdf_dialog is None
        assert not dialog.winfo_exists()
        assert app.root.grab_current() is None
    else:
        assert app.document.path == previous_path
        assert app.pdf_dialog is dialog
        assert dialog.preview.page_index == 1
        assert dialog.winfo_exists()
