"""The beam's 配筋略図 window (decision 68): colours, overlaps, the stirrup, the picked bar and what cannot be drawn."""

import copy

import pytest

from webpier.gui import app as gui
from webpier.gui import rebar_edit
from webpier.gui.beam_window import COLORS, OVERLAP, BeamWindow, stirrup

BEAM = ("鉄筋", "梁")


@pytest.fixture
def editor(tk_root, input_path, quiet):
    editor = gui.InputEditor(tk_root, input_path)
    assert editor.select("鉄筋")
    assert editor.view.select_member("梁")
    tk_root.update()
    return editor


@pytest.fixture
def window(editor):
    closed = []
    window = BeamWindow(editor, lambda: closed.append(True))
    window.closed = closed
    editor.root.update()
    yield window
    if window.window.winfo_exists():
        window.window.destroy()


def beam(editor):
    return editor.document.data["鉄筋"]["梁"]


def fills(window):
    canvas = window.section.canvas
    return [canvas.itemcget(bar, "fill") for bar in canvas.find_withtag("rebar")]


def drawn_stirrup(data):
    return stirrup(rebar_edit.beam_preview(data), data["鉄筋"]["梁"])


def test_the_bars_are_coloured_by_their_group(window):
    shown = fills(window)
    assert len(shown) == 77  # 17 + 8 upper, 18 lower, 17 side bars on each side face
    assert shown == [COLORS["上"]] * 25 + [COLORS["下"]] * 18 + [COLORS["側面"]] * 34
    assert window.footer.get() == "物理本数 77 本"
    assert window.section.notice.cget("text") == ("青：上面の主鉄筋　橙：下面の主鉄筋　緑：側面筋　"
                                                  "灰：スターラップ（効く脚 4 本）　赤：重なり")
    assert window.window.title() == "配筋略図 — 梁（柱前面）" and window.member == "梁"


def test_overlapping_bars_are_red(window, editor):
    beam(editor)["side_bars"]["start_mm"] = 108  # the top side bars on the upper face's outermost bars
    window.refresh()
    assert fills(window).count(OVERLAP) == 4
    assert window.footer.get() == "物理本数 77 本・重なり 2 か所"


def test_the_stirrup_touches_the_outermost_bars(window, editor):
    data = editor.document.data
    rectangle, legs = drawn_stirrup(data)
    assert rectangle == [(162, 81), (2538, 81), (2538, 2599.5), (162, 2599.5)]  # 184 − 11 − 11, 108 − 16 − 11, …
    assert legs == [((954, 81), (954, 2599.5)), ((1746, 81), (1746, 2599.5))]  # 4 legs: 2 inside, equally spaced
    canvas = window.section.canvas
    assert len(canvas.find_withtag("hoop")) == 1 and len(canvas.find_withtag("leg")) == 2
    assert canvas.itemcget(canvas.find_withtag("leg")[0], "dash") == "4 3"


def test_two_legs_have_no_line_inside(editor):
    data = copy.deepcopy(editor.document.data)
    data["鉄筋"]["梁"]["stirrups"]["effective_legs"] = 2
    rectangle, legs = drawn_stirrup(data)
    assert rectangle and legs == []
    data["鉄筋"]["梁"]["stirrups"]["effective_legs"] = None
    assert drawn_stirrup(data) == (rectangle, [])


def test_the_side_of_the_stirrup_without_side_bars_inside_it(editor):
    data = copy.deepcopy(editor.document.data)
    data["鉄筋"]["梁"]["side_bars"]["stirrup_position"] = "外側"
    # the upper face's first bar 184 + 11 + 22 + 16 = 233 (inside the side bars and the stirrup), 233 − 16 − 11
    assert drawn_stirrup(data)[0][0] == (206, 81)
    data["鉄筋"]["梁"]["side_bars"] = None
    assert drawn_stirrup(data)[0][0] == (81, 81)  # its first bar at the cover 108 − 16 − 11


@pytest.mark.parametrize("key,value", [(("stirrups", "diameter_mm"), None), (("faces", "上", "center_mm"), 27)])
def test_no_stirrup_without_its_size_or_room(window, editor, key, value):
    data = beam(editor)
    *head, last = key
    for part in head:
        data = data[part]
    data[last] = value  # 27 − 16 − 11 = 0: no room above it
    assert drawn_stirrup(editor.document.data) == ([], [])
    window.refresh()
    canvas = window.section.canvas
    assert not canvas.find_withtag("hoop") and not canvas.find_withtag("leg") and canvas.find_withtag("rebar")


def test_a_blank_count_of_legs_is_shown_as_such(window, editor):
    beam(editor)["stirrups"]["effective_legs"] = None
    window.refresh()
    assert "効く脚 — 本" in window.section.notice.cget("text")


def test_a_picked_bar_is_named(window, editor):
    window.pick(0)
    assert window.footer.get() == "物理本数 77 本　上面1段目 D32・上面から 108.0・左面から 184.0"
    assert window.section.canvas.find_withtag("ring")
    window.pick(76)
    assert window.footer.get() == "物理本数 77 本　側面筋 D22・上面から 2350.0・左面から 2516.0"
    beam(editor)["side_bars"] = None  # the picked bar is gone
    window.refresh()
    assert window.footer.get() == "物理本数 43 本"


def test_what_cannot_be_drawn_is_named(window, editor):
    editor.document.data["下部構造"]["寸法"]["側面"]["B1"] = None
    window.refresh()
    assert window.section.notice.cget("text") == "下部構造.寸法.側面.B1: 値が必要です"
    assert window.footer.get() == "" and window.section.canvas.find_withtag("empty")


def test_closing_tells_the_page(window):
    window.close()
    assert window.closed == [True] and not window.window.winfo_exists()
    window.refresh()  # after closing: nothing to draw


def test_the_page_opens_the_window_and_keeps_it_while_rebuilt(editor):
    page = editor.view
    assert page.toggle_window() and isinstance(page.window(), BeamWindow)
    assert page.select_group("check") and editor.view.select_group("main")  # the page is rebuilt twice
    editor.root.update()
    assert isinstance(editor.view.window(), BeamWindow)
    beam(editor)["side_bars"]["start_mm"] = 108
    editor.view.refresh()  # an edit redraws the open window
    assert "重なり 2 か所" in editor.view.window().footer.get()
    assert editor.view.select_member("柱")
    editor.root.update()
    assert editor.rebar_state["window"] is None  # left the beam: the window closes
