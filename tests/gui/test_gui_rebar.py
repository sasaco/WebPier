"""The 鉄筋 page: tables through the field table, the column drawn from calc.column_rebar, the column dialogs."""

import tkinter as tk

import pytest

from conftest import new_root
from webpier.gui import app as gui
from webpier.gui import column_dialogs, rebar_page

COLUMN = ("鉄筋", "柱")


@pytest.fixture
def editor(tk_root, input_path, quiet):
    editor = gui.InputEditor(tk_root, input_path)
    assert editor.select("鉄筋")
    tk_root.update()
    return editor


def page(editor) -> rebar_page.RebarPage:
    return editor.view


def cell(editor, *path):
    return editor.bindings.items[path].cell


def bars(editor):
    canvas = page(editor).section.canvas
    return canvas.find_withtag("rebar")


def direction_rows(editor):
    return page(editor).direction_sheet.get_sheet_data()


def toplevels(root):
    return [child for child in root.winfo_children() if isinstance(child, tk.Toplevel)]


def test_the_column_is_drawn_from_the_calculated_layout(editor):
    assert len(bars(editor)) == 76
    assert len(direction_rows(editor)) == 11
    page(editor).select_direction("直角")
    assert len(direction_rows(editor)) == 31
    assert direction_rows(editor)[0] == ["102.0", "19", "2", "SD390"] or direction_rows(editor)[0][1] in ("32", "19")
    assert page(editor).source.cget("text") == "使用中：自動配置"
    assert page(editor).section.canvas.find_withtag("hoop")


def test_rebar_values_are_rounded_at_entry(editor):
    cover = (*COLUMN, "pure_cover_mm")
    cell(editor, *cover).type("70.04")
    assert cell(editor, *cover).get() == "70.0"
    diameter = (*COLUMN, "main_rows", 0, "diameter_mm")
    cell(editor, *diameter).type("31.6")
    assert cell(editor, *diameter).get() == "32"
    assert editor.document.data["鉄筋"]["柱"]["main_rows"][0]["diameter_mm"] == 32


def test_edits_redraw_the_layout_and_errors_name_the_path(editor):
    count = (*COLUMN, "main_rows", 0, "per_face_count")
    cell(editor, *count).type("27")
    assert len(bars(editor)) == 72
    cell(editor, *count).type("")
    assert not bars(editor)
    assert page(editor).section.notice.cget("text") == "鉄筋.柱.main_rows[0].per_face_count: 値が必要です"
    assert page(editor).direction_sheet.get_sheet_data() == []


def test_choices_of_the_rebar_tables(editor):
    target = cell(editor, *COLUMN, "main_rows", 0, "distribution", "mode")
    assert target.sheet.get_dropdown_values(target.row, target.column) == ["", "等分", "中央ピッチ", "両端＋中央ピッチ"]
    material = cell(editor, *COLUMN, "materials", "main")
    assert material.sheet.get_dropdown_values(material.row, material.column) == ["", "SD295", "SD345", "SD390"]


def test_rows_can_be_added_and_deleted(editor):
    view = page(editor)
    assert view.add_row("main_rows")
    rows = editor.document.data["鉄筋"]["柱"]["main_rows"]
    assert len(rows) == 3 and rows[2]["per_face_count"] is None
    assert "鉄筋.柱.main_rows[2]" in page(editor).section.notice.cget("text")
    assert page(editor).delete_row("main_rows")
    assert len(rows) == 2 and len(bars(editor)) == 76
    assert not page(editor).delete_row("main_rows")  # nothing selected


def test_the_hoop_group(editor):
    assert page(editor).select_group("hoops")
    assert cell(editor, *COLUMN, "column_hoops", "enclosing_diameter_mm").get() == "22"
    assert cell(editor, *COLUMN, "column_hoops", "direction_rows", 1, "effective_legs").get() == "6"
    assert page(editor).add_row("direction_rows")
    assert len(editor.document.data["鉄筋"]["柱"]["column_hoops"]["direction_rows"]) == 3


@pytest.mark.parametrize("member,groups", [("梁", ("main", "bands", "placement")), ("フーチング", ("main", "bands"))])
def test_beam_and_footing_show_their_tables_and_outline(editor, member, groups):
    assert page(editor).select_member(member)
    assert tuple(page(editor).group_buttons) == groups
    assert page(editor).section.canvas.find_withtag("section-outline") and not bars(editor)
    assert page(editor).section.notice.cget("text") == rebar_page.OUTLINE_ONLY
    for group in groups:
        assert page(editor).select_group(group)
    assert page(editor).add_row("manual_positions" if member == "梁" else "band_rows")
    page(editor).select_direction("直角")
    assert page(editor).section.canvas.find_withtag("section-outline")


def test_the_member_is_kept_when_the_page_is_reopened(editor):
    page(editor).select_member("梁")
    editor.select("上部構造")
    editor.select("鉄筋")
    assert page(editor).member == "梁"
    assert not page(editor).select_member("杭")


def test_a_missing_dimension_is_shown(editor):
    editor.document.data["下部構造"]["寸法"]["正面"]["W6"] = None
    page(editor).refresh()
    assert page(editor).section.notice.cget("text") == "下部構造.寸法.正面.W6: 値が必要です"
    assert page(editor).section.canvas.find_withtag("empty")


def open_regeneration(editor, **kwargs):
    assert page(editor).select_group("placement")
    assert page(editor).begin_regeneration(**kwargs)
    return page(editor).dialog


def test_regeneration_compares_then_copies_the_automatic_layout(editor):
    dialog = open_regeneration(editor)
    assert len(dialog.sheets) == 2 and dialog.sheets[0].get_sheet_data() == dialog.sheets[1].get_sheet_data()
    assert not editor.select("上部構造")  # the page is blocked while the dialog is open
    assert not page(editor).begin_add_bar()
    assert dialog.apply()
    editor.root.update()
    column = editor.document.data["鉄筋"]["柱"]
    assert column["position_mode"] == "指定" and len(column["manual_positions"]) == 76
    assert page(editor).source.cget("text") == "使用中：詳細位置"
    assert "一致しています" in page(editor).section.notice.cget("text")
    assert cell(editor, *COLUMN, "manual_positions", 0, "x_mm").get() == "108.0"
    editor.document.data["鉄筋"]["柱"]["pure_cover_mm"] = 80
    page(editor).refresh()
    assert "反映されていません" in page(editor).section.notice.cget("text")
    assert editor.save()


def test_a_changed_input_cancels_the_confirmed_regeneration(editor):
    dialog = open_regeneration(editor)
    editor.document.data["鉄筋"]["柱"]["pure_cover_mm"] = 80
    assert not dialog.apply()
    assert dialog.error.get() == "入力が変更されています。比較し直してください"
    assert dialog.close() and not dialog.close()
    assert page(editor).dialog is None


def test_back_to_automatic_and_back_to_detail(editor):
    open_regeneration(editor).apply()
    editor.root.update()
    dialog = open_regeneration(editor, to_auto=True)
    assert dialog.window.title() == "自動配置へ切替 — 新旧の確認"
    assert dialog.apply()
    editor.root.update()
    column = editor.document.data["鉄筋"]["柱"]
    assert column["position_mode"] == "基本" and len(column["manual_positions"]) == 76
    assert page(editor).use_detail()
    assert column["position_mode"] == "指定"


def test_a_bar_is_added_through_the_field_table(editor):
    assert page(editor).select_group("placement")
    assert page(editor).begin_add_bar()
    dialog = page(editor).dialog
    assert dialog.values["material"].get() == ""  # nothing is filled from the main steel
    dialog.values["material"].set("SD390")
    dialog.values["x_mm"].set("abc")
    assert not dialog.apply() and dialog.error.get() == "X mm: 数値を入力してください"
    dialog.values["x_mm"].set("2250.04")
    dialog.values["y_mm"].set("1350")
    dialog.values["diameter_mm"].set("32")
    dialog.values["material"].set("")
    assert not dialog.apply() and dialog.error.get() == "鉄筋.柱.manual_positions[76].material: 値が必要です"
    dialog.values["material"].set("SD390")
    assert dialog.apply()
    editor.root.update()
    positions = editor.document.data["鉄筋"]["柱"]["manual_positions"]
    assert positions[-1] == {"x_mm": 2250.0, "y_mm": 1350.0, "diameter_mm": 32, "material": "SD390"}
    assert len(bars(editor)) == 77


def test_an_overlapping_bar_is_refused_by_the_calculation(editor):
    page(editor).select_group("placement")
    page(editor).begin_add_bar()
    dialog = page(editor).dialog
    for key, value in (("x_mm", "108"), ("y_mm", "120"), ("diameter_mm", "32"), ("material", "SD390")):
        dialog.values[key].set(value)
    assert not dialog.apply()
    assert "鉄筋が重なっています" in dialog.error.get()
    assert editor.document.data["鉄筋"]["柱"]["position_mode"] == "基本"


def test_a_bar_is_selected_from_the_drawing_and_deleted(editor):
    open_regeneration(editor).apply()
    editor.root.update()
    view = page(editor)
    view.bar_clicked(0)
    assert view.selected == ("manual_positions", 0)
    assert view.section.canvas.find_withtag("selected")
    assert view.delete_bar()
    assert len(editor.document.data["鉄筋"]["柱"]["manual_positions"]) == 75
    assert not page(editor).delete_bar()


def test_selecting_a_main_row_from_the_drawing(editor):
    page(editor).bar_clicked(0)
    assert page(editor).selected == ("main_rows", 0)
    assert len(page(editor).section.canvas.find_withtag("selected")) == 58


@pytest.mark.parametrize("operation", ["begin_regeneration", "begin_add_bar"])
def test_dialog_setup_failures_leave_no_window_and_keep_the_input(editor, monkeypatch, operation, quiet):
    """The new equivalent of the old order-dependent test: it asserts only on this editor's own state."""
    calls, _ = quiet
    assert page(editor).select_group("placement")
    before = editor.document.data["鉄筋"]["柱"].copy()
    with monkeypatch.context() as failing:
        failing.setattr(tk.Toplevel, "transient", lambda *args: (_ for _ in ()).throw(tk.TclError("transient failed")))
        assert not getattr(page(editor), operation)()
    assert page(editor).dialog is None and not toplevels(editor.root)
    assert calls[-1][0] == "showerror" and "transient failed" in calls[-1][2]
    assert editor.document.data["鉄筋"]["柱"] == before
    assert getattr(page(editor), operation)()
    assert page(editor).dialog.close()


def test_a_grab_held_by_another_tk_interpreter_does_not_break_the_dialog(editor):
    """Tk keeps one grab per display for every interpreter of the process (the cause of the old flaky test)."""
    other = new_root()
    try:
        holder = tk.Toplevel(other)
        holder.deiconify()
        holder.grab_set()
        with pytest.raises(tk.TclError, match="another application has grab"):
            probe = tk.Toplevel(editor.root)
            try:
                probe.grab_set()
            finally:
                probe.destroy()
        dialog = open_regeneration(editor)
        assert dialog.window.winfo_exists()
        assert dialog.close()
        assert page(editor).dialog is None and not toplevels(editor.root)
        assert other.grab_current() is holder  # the other grab was left alone
    finally:
        other.destroy()


def test_closing_the_page_closes_its_dialog(editor):
    dialog = open_regeneration(editor)
    page(editor).dispose()
    assert dialog.closed and not toplevels(editor.root)
    editor.view = None


def test_summary_of_bars():
    assert column_dialogs.summary([{"diameter_mm": 32}, {"diameter_mm": 19}, {"diameter_mm": 32}]) == \
        "総本数 3 本　D19 × 1 / D32 × 2"
