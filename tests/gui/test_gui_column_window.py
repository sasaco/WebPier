"""The column's section and 方向別の鉄筋配置表 window (decisions 68, 111): colours, the tables, the 配置表の手直し
and its warnings."""

import pytest

from webpier.gui import app as gui
from webpier.gui.column_window import COLORS, ColumnWindow, bands

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


def tables(editor):
    return column(editor)["custom_tables"]


def test_the_section_colours_the_bars_by_direction(window):
    canvas = window.section.canvas
    bars = canvas.find_withtag("rebar")
    assert len(bars) == 76
    assert {canvas.itemcget(bar, "fill") for bar in bars} == set(COLORS.values())
    assert window.footer.get() == "物理本数 76 本" and "青：線路方向の段" in window.section.notice.cget("text")
    assert "手直し" not in window.section.notice.cget("text")
    assert window.table.winfo_manager() == "" and window.section.winfo_manager() == "pack"


def test_a_table_lists_the_rows_of_a_direction_in_use(window):
    window.select("線路")
    window.editor.root.update()
    data = window.sheet.get_sheet_data()
    assert data[0] == ["108", "D32", "29", "引張（上）"] and data[-1] == ["2592", "D32", "29", "引張（下）"]
    assert data[1][3] == "" and len(data) == 11 and window.sheet.headers()[0] == "上面からの芯位置 mm"
    assert window.tension.get() == "1" and window.state.get() == "主鉄筋の入力から作った表"
    assert len(window.strip.canvas.find_withtag("band")) == 11
    assert window.editor.rebar_state["window_view"] == "線路"


def test_the_bands_label_the_tension_rows_and_a_change_of_count():
    from webpier.calc.column_rebar import DirectionTable, TableRow
    from webpier.core.printed import Printed

    def row(centre, count):
        return TableRow(Printed(centre, 1, "mm"), Printed(19, 0, "mm"), count, "SD345")

    table = DirectionTable("直角", (row(150, 27), row(291, 2), row(475, 2), row(3100, 4), row(6850, 27)), 1, True)
    found = bands(table, 7000, 3900)
    assert [band.label for band in found] == ["D19×27", "2", "", "4", "D19×27"]
    assert found[0].start == (150, 0.0) and found[0].end == (150, 3900)
    assert found[1].color != found[0].color


def test_a_value_typed_into_the_table_makes_it_by_hand(window, editor):
    window.select("直角")
    type_cell(window, 0, 0, "110")  # the 9 D19 bars at 102 from the left face
    made = tables(editor)["直角"]
    assert made["rows"][0] == {"center_mm": 110.0, "diameter_mm": 19.0, "count": 9} and len(made["rows"]) == 31
    assert tables(editor)["線路"] is None and editor.document.dirty
    assert window.state.get() == "手直しした表（計算はこの表を使います）"
    type_cell(window, 0, 1, "D22")
    type_cell(window, 0, 2, "8")
    assert made["rows"][0] == {"center_mm": 110.0, "diameter_mm": 22.0, "count": 8}
    window.select("section")
    assert "手直しした配置表があります" in window.section.notice.cget("text")
    assert "2つの配置表で鉄筋の本数が違います" in window.footer.get()


@pytest.mark.parametrize("text,message", [("abc", "数値を入力してください"), ("5", "断面の外に出ます")])
def test_a_value_that_cannot_be_entered_or_placed_is_refused(window, editor, text, message):
    window.select("直角")
    type_cell(window, 0, 0, text)
    assert message in window.message.get() and tables(editor)["直角"] is None
    assert window.sheet.get_sheet_data()[0][0] == "102"


def test_the_same_text_changes_nothing(window, editor):
    window.select("直角")
    type_cell(window, 0, 0, "102")  # what the cell shows: no change, no message
    window.edited()  # set_data of the same text emits no <<SheetModified>>
    assert tables(editor)["直角"] is None and window.message.get() == ""


def test_rows_are_added_moved_and_deleted(window, editor):
    window.select("直角")
    assert window.add() is None and "行を選んで" in window.message.get()  # nothing selected
    assert not window.delete() and window.move(1) is None
    window.sheet.select_cell(0, 0)
    assert window.add() == 1
    rows = tables(editor)["直角"]["rows"]
    assert len(rows) == 32 and rows[1] == rows[0]
    window.sheet.select_cell(1, 0)
    type_cell(window, 1, 0, "200")
    window.sheet.select_cell(1, 0)
    assert window.move(-1) == 0 and rows[0]["center_mm"] == 200.0
    window.sheet.select_cell(0, 0)
    assert window.move(-1) is None
    assert window.delete() and len(rows) == 31 and rows[0]["center_mm"] == 102.0


def test_the_tension_rows_are_entered(window, editor):
    window.select("線路")
    window.tension.set("2")
    window.set_tension()
    assert tables(editor)["線路"]["tension_rows"] == 2
    assert [row[3] for row in window.sheet.get_sheet_data()[:3]] == ["引張（上）", "引張（上）", ""]
    window.set_tension()  # the same number again: nothing to do
    window.tension.set("x")
    window.set_tension()
    assert "整数" in window.message.get()
    window.tension.set("6")  # 12 rows of 11
    window.set_tension()
    assert "より多くなります" in window.message.get() and tables(editor)["線路"]["tension_rows"] == 2


def test_the_table_is_made_from_the_main_bars_again(window, editor):
    window.select("線路")
    assert not window.reset()  # not hand-made
    type_cell(window, 0, 2, "27")
    assert window.reset() and tables(editor)["線路"] is None
    assert window.sheet.get_sheet_data()[0][2] == "29"
    window.select("section")
    assert not window.reset()


def test_a_table_that_cannot_be_made_is_named(window, editor):
    bars = column(editor)["main_bars"]
    bars["線路"]["per_face_count"] = 2  # 両端＋中央ピッチ with its two edge bars; 直角 from 60: a bar outside them
    bars["直角"]["distribution"] = {"mode": "等分", "edge_center_mm": 60.0, "pitch_mm": None}
    bars["直角"]["endpoints"] = "含む"
    window.select("線路")
    assert "主鉄筋の段が1段ずつの行になっていません" in window.strip.notice.cget("text")
    assert window.shown is None and window.sheet.get_sheet_data() == [] and window.tension.get() == ""
    window.edited()  # nothing shown: nothing to read
    window.select("section")
    assert window._apply(lambda data, layout: 1) is None and tables(editor)["線路"] is None


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
