"""Card inputs bound to the field table (gui.cards): entered, rounded and marked like table cells (decision 68)."""

from tkinter import ttk

import pytest

from webpier.gui import app as gui
from webpier.gui import cards
from webpier.gui.form import Form
from webpier.gui.grid import EDITABLE, MISSING, REFUSED

COLUMN = ("鉄筋", "柱")
RAIL = (*COLUMN, "main_bars", "線路")


@pytest.fixture
def form(tk_root, input_path, quiet):
    editor = gui.InputEditor(tk_root, input_path)
    assert editor.select("上部構造")  # a page with table cells; the cards are built beside them
    frame = ttk.Frame(editor.form)
    frame.pack()
    return Form(editor, frame)


def data(form):
    return form.editor.document.data


def test_an_entry_is_rounded_and_written_when_entered(form):
    bound = cards.entry(form, form.parent, (*COLUMN, "pure_cover_mm"), "純かぶり")
    assert bound.cell.get() == "70.0" and bound.cell.widget.cget("justify") == "right"
    caption = bound.cell.widget.master.winfo_children()[0]
    assert caption.cget("text") == "純かぶり mm"
    bound.cell.show("70.04")
    assert form.editor.bindings.pending
    assert bound.cell.widget.bind("<Return>")
    form.editor.bindings.entered(bound)
    assert data(form)["鉄筋"]["柱"]["pure_cover_mm"] == 70.0 and bound.cell.get() == "70.0"
    assert not form.editor.bindings.pending


def test_refused_text_is_marked_and_the_document_kept(form):
    bindings = form.editor.bindings
    bound = cards.entry(form, form.parent, (*COLUMN, "pure_cover_mm"), "純かぶり")
    bound.cell.show("abc")
    bindings.commit()  # what saving does first: the open text is entered
    assert bindings.refused[(*COLUMN, "pure_cover_mm")] == "数値を入力してください"
    assert bound.cell.widget.cget("background") == REFUSED
    assert data(form)["鉄筋"]["柱"]["pure_cover_mm"] == 70


def test_a_needed_blank_is_marked(form):
    bound = cards.entry(form, form.parent, (*COLUMN, "concrete_strength_mpa"), "コンクリート強度")
    assert bound.cell.widget.cget("background") == EDITABLE
    bound.cell.show("")
    form.editor.bindings.entered(bound)
    assert data(form)["鉄筋"]["柱"]["concrete_strength_mpa"] is None
    assert bound.cell.widget.cget("background") == MISSING


def test_a_segment_enters_the_pressed_choice(form):
    calls = []
    bound = cards.segment(form, form.parent, (*RAIL, "cover_mode"), "芯かぶり", labels={"自動": "自動計算"},
                          selected=lambda: calls.append(bound.cell.get()))
    cell = bound.cell
    assert list(cell.buttons) == ["自動", "指定"] and cell.buttons["自動"].cget("text") == "自動計算"
    assert cell.get() == "自動"
    cell.buttons["指定"].invoke()
    assert data(form)["鉄筋"]["柱"]["main_bars"]["線路"]["cover_mode"] == "指定" and calls == ["指定"]
    cell.color(MISSING)
    assert cell.frame.cget("highlightbackground") == MISSING
    cell.color(EDITABLE)
    assert cell.frame.cget("highlightthickness") == 1


def test_a_size_is_chosen_by_its_name_and_saved_in_mm(form):
    bound = cards.size(form, form.parent, (*RAIL, "diameter_mm"), "径")
    widget = bound.cell.widget
    assert widget.get() == "D32" and bound.cell.get() == "32" and "D51" in widget.cget("values")
    widget.set("D29")
    widget.event_generate("<<ComboboxSelected>>")
    assert data(form)["鉄筋"]["柱"]["main_bars"]["線路"]["diameter_mm"] == 29
    bound.cell.show("")
    assert widget.get() == ""
    bound.cell.color(MISSING)
    assert widget.cget("style") == "Cfde8e8.TCombobox"


def test_a_segment_without_a_follow_up(form):
    bound = cards.segment(form, form.parent, (*RAIL, "endpoints"), "e の位置に鉄筋",
                          labels={"含む": "置く", "含めない": "置かない"})
    bound.cell.buttons["含めない"].invoke()
    assert data(form)["鉄筋"]["柱"]["main_bars"]["線路"]["endpoints"] == "含めない"


def test_cards_are_focused_like_cells(form):
    for build, path in ((cards.entry, (*COLUMN, "pure_cover_mm")), (cards.segment, (*RAIL, "cover_mode")),
                        (cards.size, (*RAIL, "diameter_mm"))):
        build(form, cards.line(form.parent), path, "x").cell.focus()


def test_a_table_cell_is_still_entered_beside_cards(form):
    bindings = form.editor.bindings
    cards.entry(form, form.parent, (*COLUMN, "pure_cover_mm"), "純かぶり")
    table = next(bound for bound in bindings.items.values() if hasattr(bound.cell, "sheet"))
    table.cell.type(table.cell.get())  # the modified event passes over the widgets
    assert not bindings.refused


def test_help_opens_beside_its_button_and_closes(form):
    shown = []
    help_ = cards.Help(form.parent, "芯かぶりの求め方", lambda body: shown.append(ttk.Label(body, text="70 + 22")))
    help_.button.pack()
    help_.button.invoke()
    assert help_.window is not None and help_.window.title() == "芯かぶりの求め方" and len(shown) == 1
    help_.toggle()
    assert help_.window is None


def test_a_card_has_its_title(form):
    assert cards.card(form.parent, "線路方向の段").cget("text") == "線路方向の段"
