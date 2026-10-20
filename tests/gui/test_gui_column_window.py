"""The column's section and 方向別の鉄筋配置表 window (decision 68): colours, the table, its changes and warnings."""

import pytest

from webpier.gui import app as gui
from webpier.gui.column_window import COLORS, ColumnWindow

COLUMN = ("鉄筋", "柱")


@pytest.fixture
def editor(tk_root, input_path, quiet):
    editor = gui.InputEditor(tk_root, input_path)
    assert editor.select("鉄筋")
    tk_root.update()
    return editor


@pytest.fixture
def window(editor):
    closed = []
    window = ColumnWindow(editor, lambda: closed.append(True))
    window.closed = closed
    editor.root.update()
    yield window
    if window.window.winfo_exists():
        window.window.destroy()


def column(editor):
    return editor.document.data["鉄筋"]["柱"]


def type_cell(window, row, col, text):
    window.sheet.set_data((row, col), data=text, undo=True, emit_event=True)
    window.editor.root.update()
    window.refresh()


def test_the_section_colours_the_bars_by_direction(window):
    canvas = window.section.canvas
    bars = canvas.find_withtag("rebar")
    assert len(bars) == 76
    assert {canvas.itemcget(bar, "fill") for bar in bars} == set(COLORS.values())
    assert window.footer.get() == "物理本数 76 本" and "紫の輪" in window.section.notice.cget("text")
    assert window.table.winfo_manager() == "" and window.section.winfo_manager() == "pack"


def test_a_table_lists_the_rows_of_a_direction(window):
    window.select("線路")
    window.editor.root.update()
    assert window.sheet.get_sheet_data()[0] == ["108.0", "D32", "29", "線路1段目", ""]
    assert len(window.lines) == 11 and window.sheet.headers()[0] == "上面からの芯位置 mm"
    assert window.editor.rebar_state["window_view"] == "線路"


def test_a_centre_and_a_size_typed_into_the_table_change_the_row(window, editor):
    window.select("直角")
    type_cell(window, 0, 0, "110")  # the 9 D19 bars at 102 from the left face
    changes = column(editor)["table_overrides"]["直角"]
    assert changes == [{"source_center_mm": 102.0, "source_diameter_mm": 19.0, "center_mm": 110.0,
                        "diameter_mm": None}]
    row = next(r for r, line in enumerate(window.lines) if line.changed)
    assert window.sheet.get_sheet_data()[row][4] == "元：102.0・D19" and editor.document.dirty
    type_cell(window, row, 1, "D22")
    assert changes[0]["diameter_mm"] == 22
    window.select("section")
    assert window.section.canvas.find_withtag("ring")


@pytest.mark.parametrize("text,message", [("abc", "数値を入力してください"), ("5", "断面の外に出ます")])
def test_a_change_that_cannot_be_entered_or_placed_is_refused(window, editor, text, message):
    window.select("直角")
    type_cell(window, 0, 0, text)
    assert message in window.message.get() and column(editor)["table_overrides"]["直角"] == []
    assert window.sheet.get_sheet_data()[0][0] == "102.0"


def test_the_same_text_changes_nothing(window, editor):
    window.select("直角")
    type_cell(window, 0, 0, "102.0")  # what the cell shows: no change, no message
    window.edited()  # set_data of the same text emits no <<SheetModified>>
    assert column(editor)["table_overrides"]["直角"] == [] and window.message.get() == ""


def test_undo_takes_back_the_change_of_the_selected_row(window, editor):
    window.select("直角")
    type_cell(window, 0, 0, "110")
    row = next(r for r, line in enumerate(window.lines) if line.changed)
    window.sheet.select_cell(0, 0)
    assert not window.undo()  # an unchanged row
    window.sheet.select_cell(row, 0)
    assert window.undo() and column(editor)["table_overrides"]["直角"] == []
    window.refresh()
    window.sheet.select_cell(30, 0)
    window.lines = window.lines[:2]  # a stale selection past the rows
    assert not window.undo()
    window.select("section")
    assert not window.undo()


def test_changes_without_their_bars_are_named_and_removed(window, editor):
    column(editor)["table_overrides"]["線路"] = [
        {"source_center_mm": 999.0, "source_diameter_mm": 32.0, "center_mm": 110.0, "diameter_mm": None}]
    window.refresh()
    window.editor.root.update()
    assert "1 件" in window.unmatched_text.get() and window.unmatched.winfo_manager() == "pack"
    assert window.remove_unmatched() == 1 and column(editor)["table_overrides"]["線路"] == []


def test_a_picked_bar_is_named(window):
    window.pick(0)
    assert window.footer.get().startswith("物理本数 76 本　X 108.0・Y 108.0・D32・線路1段目")
    assert window.section.canvas.find_withtag("ring")


def test_what_cannot_be_drawn_is_named(window, editor):
    column(editor)["main_bars"]["線路"]["per_face_count"] = None
    window.refresh()
    assert window.section.notice.cget("text") == "鉄筋.柱.main_bars.線路.per_face_count: 値が必要です"
    column(editor)["pure_cover_mm"] = None  # no hoop line without the cover
    window.refresh()
    assert not window.section.canvas.find_withtag("hoop")
    editor.document.data["下部構造"]["寸法"]["正面"]["W6"] = None
    window.refresh()
    assert window.section.notice.cget("text") == "下部構造.寸法.正面.W6: 値が必要です" and window.footer.get() == ""


def test_closing_tells_the_page(window):
    window.close()
    assert window.closed == [True] and not window.window.winfo_exists()
    window.refresh()  # after closing: nothing to draw
