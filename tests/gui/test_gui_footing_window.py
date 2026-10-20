"""The footing's 配筋略図 window (decision 68): the section of each direction, crossings, stirrups, the column, the
zoom at true scale and what cannot be drawn."""

import pytest

from webpier.gui import app as gui
from webpier.gui.footing_window import CROSSING, ZOOM_SCALE, ZOOM_X, FootingWindow

FOOTING = ("鉄筋", "フーチング")


@pytest.fixture
def editor(tk_root, input_path, quiet):
    """純かぶり 70; on the lower face 線路 D25@125 (outside) and 直角 D29@125, on the upper face 線路 D19@250 (outside)
    and 直角 D19@250, all 自動; the stirrups at 250 along the overhang."""
    editor = gui.InputEditor(tk_root, input_path)
    data = editor.document.data["鉄筋"]["フーチング"]
    data["pure_cover_mm"] = 70
    data["faces"]["下"]["線路"].update(diameter_mm=25, pitch_mm=125)
    data["faces"]["下"]["直角"].update(diameter_mm=29, pitch_mm=125)
    data["faces"]["上"]["線路"].update(diameter_mm=19, pitch_mm=250)
    data["faces"]["上"]["直角"].update(diameter_mm=19, pitch_mm=250)
    for direction in ("線路", "直角"):
        data["stirrups"][direction].update(diameter_mm=16, pitch_mm=250)
    assert editor.select("鉄筋")
    assert editor.view.select_member("フーチング")
    tk_root.update()
    return editor


@pytest.fixture
def window(editor):
    closed = []
    window = FootingWindow(editor, lambda: closed.append(True))
    window.closed = closed
    editor.root.update()
    yield window
    if window.window.winfo_exists():
        window.window.destroy()


def footing(editor):
    return editor.document.data["鉄筋"]["フーチング"]


def items(canvas, tag):
    return canvas.find_withtag(tag)


def test_the_section_along_the_track(window):
    canvas = window.section
    assert window.window.title() == "配筋略図 — フーチング" and window.member == "フーチング"
    assert len(items(canvas, "band")) == 2  # the 線路 layers of both faces
    # the 直角 layers as dots in 7000 − 2 × 70: 125 → floor(6860／125) + 1 = 55, 250 → floor(6860／250) + 1 = 28
    assert len(items(canvas, "dot")) == 55 + 28
    assert len(items(canvas, "stirrup")) == 27  # floor((7000 − 400)／250) + 1
    assert [canvas.itemcget(item, "text") for item in items(canvas, "dimension")] == ["2150", "2700", "2150"]
    assert window.notice.get() == "" and items(canvas, "outline")
    assert not [item for item in canvas.find_all() if canvas.itemcget(item, "fill") == CROSSING]


def test_the_section_across_the_track_swaps_lines_and_dots(window, editor):
    window.select("直角")
    canvas = window.section
    assert editor.rebar_state["footing_view"] == "直角"
    assert len(items(canvas, "band")) == 2
    assert len(items(canvas, "dot")) == 71 + 36  # 9000 − 140: floor(8860／125) + 1, floor(8860／250) + 1
    assert len(items(canvas, "stirrup")) == 35  # floor((9000 − 400)／250) + 1
    assert [canvas.itemcget(item, "text") for item in items(canvas, "dimension")] == ["2250", "4500", "2250"]


@pytest.mark.parametrize("view,width", [("線路", 2700), ("直角", 4500)])
def test_the_column_is_drawn_to_scale(window, view, width):
    window.select(view)
    x1, y1, x2, y2 = window.section.coords(items(window.section, "column")[0])
    assert x2 - x1 == pytest.approx(width * window.scale)  # B6 or W6


def test_crossing_layers_are_red(window, editor):
    footing(editor)["faces"]["下"]["線路"]["inner_layers"] = [{"pitch_mm": 125, "clear_gap_mm": 25}]  # 132.5 by 109.5
    window.refresh()
    canvas = window.section
    assert len(items(canvas, "band")) == 3
    red = [item for item in canvas.find_all() if canvas.itemcget(item, "fill") == CROSSING]
    assert len(red) == 1 + 55  # the 2nd 線路 layer and the 直角 layer it crosses
    assert window.rows[-1] == "線路方向 2段目　D25 @125　芯かぶり 132.5（交差）"


def test_no_stirrups_without_their_pitch(window, editor):
    footing(editor)["stirrups"]["線路"]["pitch_mm"] = None
    window.refresh()
    assert not items(window.section, "stirrup")


def test_the_zoom_of_the_lower_face_is_at_true_scale(window):
    canvas = window.zoom_canvas
    assert len(items(canvas, "zoom-band")) == 1  # 線路 seen along the track
    centres = [(canvas.coords(item)[0] + canvas.coords(item)[2]) / 2 for item in items(canvas, "zoom-dot")]
    assert [round((x - ZOOM_X) / ZOOM_SCALE, 6) for x in centres] == [150, 275, 400, 525]  # 650 + 14.5 > 640
    assert window.rows == ["線路方向 1段目　D25 @125　芯かぶり 82.5", "直角方向 1段目　D29 @125　芯かぶり 109.5"]
    assert [canvas.itemcget(item, "text") for item in items(canvas, "pure") if canvas.type(item) == "text"] == ["70"]


def test_the_zoom_shows_the_upper_face(window, editor):
    window.select_zoom("上")
    assert editor.rebar_state["footing_zoom"] == "上"
    assert window.rows == ["線路方向 1段目　D19 @250　芯かぶり 79.5", "直角方向 1段目　D19 @250　芯かぶり 98.5"]
    assert len(items(window.zoom_canvas, "zoom-dot")) == 2  # 150, 400


def test_a_face_that_cannot_be_placed_is_named(window, editor):
    footing(editor)["faces"]["下"]["線路"]["diameter_mm"] = None
    window.refresh()
    assert window.notice.get() == "下面：鉄筋.フーチング.faces.下.線路.diameter_mm: 値が必要です"
    assert len(items(window.section, "band")) == 1 and window.rows == []  # the upper face's only


def test_what_the_reader_refuses_draws_nothing(window, editor):
    footing(editor)["materials"]["main"] = "SD999"
    window.refresh()
    assert window.notice.get().startswith("鉄筋.フーチング.materials.main:")
    assert window.section.find_all() == () and window.zoom_canvas.find_all() == () and window.rows == []


def test_closing_tells_the_page(window):
    window.close()
    assert window.closed == [True] and not window.window.winfo_exists()
    window.refresh()  # after closing: nothing to draw


def test_the_page_opens_the_window_and_keeps_it_while_rebuilt(editor):
    page = editor.view
    assert page.toggle_window() and isinstance(page.window(), FootingWindow)
    page._rebuild()
    editor.root.update()
    assert isinstance(editor.view.window(), FootingWindow)
    footing(editor)["stirrups"]["線路"]["pitch_mm"] = None
    editor.view.refresh()  # an edit redraws the open window
    assert not items(editor.view.window().section, "stirrup")
    assert editor.view.select_member("梁")
    editor.root.update()
    assert editor.rebar_state["window"] is None  # left the footing: the window closes
