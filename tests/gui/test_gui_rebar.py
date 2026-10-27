"""The 鉄筋 page: values through the field table, the column in its section and table window (decision 68)."""

from types import SimpleNamespace

import pytest

from gui_support import blank_footing
from webpier.gui import app as gui
from webpier.gui import beam_cards, column_cards, footing_cards, rebar_page

COLUMN = ("鉄筋", "柱")
RAIL = (*COLUMN, "main_bars", "線路")


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


CROSS = (*COLUMN, "main_bars", "直角")


def enter(editor, path, text):
    """Type *text* into the card input of *path* and leave it, as a person would."""
    bound = editor.bindings.items[path]
    bound.cell.show(text)
    editor.bindings.entered(bound)
    editor.root.update()


def press(editor, path, value):
    """Press the button of *value* in the segment of *path*; a choice that shows other inputs rebuilds the page."""
    editor.bindings.items[path].cell.buttons[value].invoke()
    editor.root.update()


def helps(widget):
    """The (?) buttons under *widget*."""
    found = [widget] if widget.winfo_class() == "Button" and widget.cget("text") == "?" else []
    for child in widget.winfo_children():
        found += helps(child)
    return found


def window(editor):
    view = page(editor)
    if view.window() is None:
        assert view.toggle_window()
    editor.root.update()
    return view.window()


def bars(editor):
    return window(editor).section.canvas.find_withtag("rebar")


def test_the_column_is_drawn_from_the_calculated_layout(editor):
    assert len(bars(editor)) == 76
    window(editor).select("線路")
    assert len(window(editor).shown.rows) == 11
    window(editor).select("直角")
    assert len(window(editor).shown.rows) == 31
    assert window(editor).section.canvas.find_withtag("hoop")


def test_a_bar_may_have_its_colour_and_a_ring(editor):
    from webpier.gui.rebar_canvas import Circle
    view = window(editor).section
    view.show([(0, 0), (1000, 0), (1000, 800), (0, 800)], [Circle(500, 400, 32, fill="#d27a22", ring="#7c3aed")])
    editor.root.update()
    (bar,) = view.canvas.find_withtag("rebar")
    assert view.canvas.itemcget(bar, "fill") == "#d27a22" and view.canvas.find_withtag("ring")


def test_rebar_values_are_rounded_at_entry(editor):
    enter(editor, (*COLUMN, "pure_cover_mm"), "70.04")
    assert cell(editor, *COLUMN, "pure_cover_mm").get() == "70.0"
    enter(editor, (*RAIL, "diameter_mm"), "31.6")
    assert cell(editor, *RAIL, "diameter_mm").get() == "32"
    assert editor.document.data["鉄筋"]["柱"]["main_bars"]["線路"]["diameter_mm"] == 32


def test_edits_redraw_the_layout_and_errors_name_the_path(editor):
    enter(editor, (*RAIL, "per_face_count"), "27")
    assert len(bars(editor)) == 72
    enter(editor, (*RAIL, "per_face_count"), "")
    assert not bars(editor)
    assert page(editor).status.get() == "鉄筋.柱.main_bars.線路.per_face_count: 値が必要です"


def test_choices_of_the_rebar_cards(editor):
    assert list(cell(editor, *RAIL, "cover_mode").buttons) == ["自動", "指定"]
    assert list(cell(editor, *RAIL, "distribution", "mode").buttons) == ["等分", "中央ピッチ", "両端＋中央ピッチ"]
    assert list(cell(editor, *COLUMN, "materials", "main").buttons) == ["SD295", "SD345", "SD390", "SD490"]


def test_layers_inside_can_be_added_and_deleted(editor):
    layers = (*RAIL, "inner_layers")
    assert page(editor).add_row(layers)
    rows = editor.document.data["鉄筋"]["柱"]["main_bars"]["線路"]["inner_layers"]
    assert rows == [{"per_face_count": None, "clear_gap_mm": None}]
    assert "鉄筋.柱.main_bars.線路.inner_layers[0].per_face_count: 値が必要です" in page(editor).status.get()
    enter(editor, (*layers, 0, "per_face_count"), "27")
    enter(editor, (*layers, 0, "clear_gap_mm"), "40")
    assert len(bars(editor)) == 76 + 2 * 27
    assert page(editor).readouts[("線路", 2)].get() == "180.0"  # 108 + 32 + 40
    assert page(editor).remove_layers(layers, 0)
    assert rows == [] and len(bars(editor)) == 76


def test_the_hoop_group(editor):
    assert page(editor).select_group("hoops")
    assert cell(editor, *COLUMN, "column_hoops", "enclosing_diameter_mm").get() == "22"
    assert cell(editor, *COLUMN, "column_hoops", "direction_rows", 1, "effective_legs").get() == "6"
    assert page(editor).add_row(("鉄筋", "柱", "column_hoops", "direction_rows"))
    assert len(editor.document.data["鉄筋"]["柱"]["column_hoops"]["direction_rows"]) == 3


def test_the_member_is_kept_when_the_page_is_reopened(editor):
    page(editor).select_member("梁")
    editor.select("上部構造")
    editor.select("鉄筋")
    assert page(editor).member == "梁"
    assert not page(editor).select_member("杭")


def test_a_missing_dimension_is_shown(editor):
    editor.document.data["下部構造"]["寸法"]["正面"]["W6"] = None
    page(editor).refresh()
    assert "下部構造.寸法.正面.W6: 値が必要です" in page(editor).status.get()
    assert window(editor).section.canvas.find_withtag("empty")


def test_the_window_stays_open_while_the_page_is_rebuilt_and_closes_when_left(editor):
    assert window(editor) is not None
    assert page(editor).add_row(("鉄筋", "柱", "main_bars", "線路", "inner_layers"))  # the page is rebuilt
    assert page(editor).window() is not None
    assert not page(editor).toggle_window() and page(editor).window() is None  # closed by its button
    assert page(editor).toggle_window()
    assert page(editor).select_member("梁")
    editor.root.update()
    assert editor.rebar_state["window"] is None  # left the column: the window closes


def test_the_beam_side_bars_are_removed_and_added(editor):
    assert page(editor).select_member("梁")
    assert page(editor).set_side_bars(False)
    assert editor.document.data["鉄筋"]["梁"]["side_bars"] is None
    assert ("鉄筋", "梁", "side_bars", "diameter_mm") not in editor.bindings.items
    assert page(editor).set_side_bars(True)
    assert cell(editor, "鉄筋", "梁", "side_bars", "diameter_mm").get() == ""


def test_two_tables_with_other_bars_are_a_warning(editor):
    """Decision 111: the 線路 table by hand with 2 bars fewer; the calculation goes on."""
    tables = editor.document.data["鉄筋"]["柱"]["custom_tables"]
    tables["線路"] = {"tension_rows": 1, "rows": [{"center_mm": 108, "diameter_mm": 32, "count": 27},
                                                 {"center_mm": 2592, "diameter_mm": 32, "count": 29}]}
    page(editor).refresh()
    assert len(bars(editor)) == 76
    assert "警告：線路方向と直角方向の配置表で鉄筋の本数が違います" in page(editor).status.get()


def test_editing_the_main_bars_of_a_direction_makes_its_table_again(editor):
    tables = editor.document.data["鉄筋"]["柱"]["custom_tables"]
    tables["直角"] = {"tension_rows": 1, "rows": [{"center_mm": 102, "diameter_mm": 19, "count": 9},
                                                 {"center_mm": 4398, "diameter_mm": 19, "count": 9}]}
    enter(editor, (*COLUMN, "main_bars", "線路", "distribution", "pitch_mm"), "140")
    assert tables["直角"] is not None  # the other direction's main bars: its table stays
    enter(editor, (*COLUMN, "main_bars", "直角", "distribution", "pitch_mm"), "300")
    assert tables["直角"] is None
    assert "直角方向の主鉄筋を変えたので、手直しした配置表を主鉄筋の入力から作り直しました。" in page(editor).status.get()


def test_the_column_concrete_has_its_aggregate_size(editor):
    """Decision 48: Dmax belongs to the column concrete; 0611 and the JRSNAP export both read it."""
    size = cell(editor, *COLUMN, "aggregate_max_mm")
    assert size.get() == "25.0"
    assert size.widget.master.winfo_children()[0].cget("text") == "粗骨材の最大寸法 mm"
    enter(editor, (*COLUMN, "aggregate_max_mm"), "20.04")
    assert size.get() == "20.0" and editor.document.data["鉄筋"]["柱"]["aggregate_max_mm"] == 20.0


def test_the_beam_and_the_footing_have_their_own_aggregate_sizes(editor):
    """Decisions 59, 60: the cantilever beam's Dmax is the beam concrete's and the footing's the footing concrete's."""
    page(editor).select_member("梁")
    assert ("鉄筋", "梁", "aggregate_max_mm") in editor.bindings.items
    page(editor).select_member("フーチング")
    assert ("鉄筋", "フーチング", "aggregate_max_mm") in editor.bindings.items


def test_the_column_check_conditions_group(editor):
    """Decision 48: the 柱の断面照査 conditions are entered with the column; one set for both directions."""
    assert tuple(page(editor).group_buttons) == ("main", "hoops", "check")
    assert page(editor).select_group("check")
    environment = cell(editor, "柱の断面照査", "水掛かりの程度")
    assert environment.get() == "常時乾燥"
    assert environment.sheet.get_dropdown_values(environment.row, environment.column) == [
        "", "常時乾燥", "乾湿繰返し", "常時湿潤"]
    shrinkage = cell(editor, "柱の断面照査", "ε'csd")
    assert shrinkage.get() == "300" and shrinkage.sheet.get_cell_data(shrinkage.row, 2) == "×10⁻⁶"
    assert cell(editor, "柱の断面照査", "外観の照査").get() == "行う"
    assert cell(editor, "柱の断面照査", "適用基準の機関").get() == "運輸機構"
    assert (cell(editor, "柱の断面照査", "JR-001").get(), cell(editor, "柱の断面照査", "JR-004").get()) == (
        "適用する", "適用しない")
    body = cell(editor, "柱の断面照査", "適用基準の機関")
    body.type("JR東日本")
    assert editor.document.data["柱の断面照査"]["適用基準の機関"] == "JR東日本"


def test_the_cover_choice_shows_the_centre_or_its_calculated_value(editor):
    assert (*RAIL, "center_mm") not in editor.bindings.items
    assert page(editor).readouts[("線路", 1)].get() == "108.0"  # 70 + 22 + 32 / 2
    press(editor, (*RAIL, "cover_mode"), "指定")
    assert (*RAIL, "center_mm") in editor.bindings.items and ("線路", 1) not in page(editor).readouts


def test_the_distribution_shows_only_the_values_it_uses(editor):
    items = editor.bindings.items
    assert (*CROSS, "distribution", "edge_center_mm") not in items  # 中央ピッチ: p only
    press(editor, (*CROSS, "distribution", "mode"), "等分")
    assert (*CROSS, "distribution", "edge_center_mm") in items and (*CROSS, "endpoints") in items
    assert (*CROSS, "distribution", "pitch_mm") not in items


def test_an_odd_rest_is_named_beside_the_centre(editor):
    layers = (*RAIL, "inner_layers")
    page(editor).add_row(layers)
    enter(editor, (*layers, 0, "per_face_count"), "28")
    enter(editor, (*layers, 0, "clear_gap_mm"), "40")
    assert page(editor).readouts[("線路", 2)].get() == "180.0（左右対称になりません）"


def test_the_helps_give_the_formula_and_the_spacing(editor):
    view = page(editor)
    assert column_cards.cover_lines(view, "線路") == [
        "純かぶり　70", "＋ 外側の帯鉄筋の径　22", "＋ 主鉄筋の径／2　16", "芯かぶり　108.0"]
    assert column_cards.spacing_line(view, "線路") == "端の鉄筋と隣の鉄筋の芯間隔 192.0 mm"  # 300 − 108
    assert column_cards.spacing_line(view, "直角") == "面の端から最初の鉄筋まで 350.0 mm"
    editor.document.data["鉄筋"]["柱"]["main_bars"]["線路"]["distribution"]["mode"] = "等分"
    view.refresh()
    assert column_cards.spacing_line(view, "線路") == "芯間隔 153.0 mm"  # (4500 − 2 × 108) / 28
    editor.document.data["鉄筋"]["柱"]["main_bars"]["線路"]["per_face_count"] = None
    view.refresh()
    assert column_cards.spacing_line(view, "線路") == "" and column_cards.readout(view, ("線路", 1)) == "—"
    found = helps(view.inputs)
    assert len(found) == 5  # 純かぶり, and 芯かぶり and 並べ方 of both directions
    for button in found:
        button.invoke()
    assert all(any(child.winfo_class() == "Toplevel" for child in button.winfo_children()) for button in found)


def test_different_corner_sizes_offer_to_match_them(editor):
    cross = editor.document.data["鉄筋"]["柱"]["main_bars"]["直角"]
    cross.update(center_mm=108, per_face_count=2)
    cross["distribution"].update(mode="両端＋中央ピッチ", edge_center_mm=108)
    page(editor).refresh()
    view = page(editor)
    assert "径の異なる鉄筋" in view.status.get()
    assert view.fix_corner.winfo_manager() == "pack" and view.fix_corner.cget("text") == "直角1段目を D32 にする"
    view.match_corner_sizes()
    assert cross["diameter_mm"] == 32 and view.status.get() == "" and view.fix_corner.winfo_manager() == ""


def test_hoop_ranges_are_added_and_removed(editor):
    assert page(editor).select_group("hoops")
    rows = editor.document.data["鉄筋"]["柱"]["column_hoops"]["direction_rows"]
    assert page(editor).add_hoop("直角")
    assert len(rows) == 3 and rows[2]["direction"] == "直角" and rows[2]["effective_legs"] is None
    assert (*COLUMN, "column_hoops", "direction_rows", 2, "effective_legs") in editor.bindings.items
    assert page(editor).remove_row((*COLUMN, "column_hoops", "direction_rows"), 2) and len(rows) == 2
    helps(page(editor).inputs)[-1].invoke()  # 効く脚


BEAM = ("鉄筋", "梁")
UPPER, LOWER = (*BEAM, "faces", "上"), (*BEAM, "faces", "下")


@pytest.fixture
def beam(editor):
    assert page(editor).select_member("梁")
    editor.root.update()
    return editor


def buttons(widget, text):
    """The buttons under *widget* with *text*."""
    found = [widget] if widget.winfo_class() in ("TButton", "Button") and widget.cget("text") == text else []
    for child in widget.winfo_children():
        found += buttons(child, text)
    return found


def test_the_beam_is_entered_on_cards_without_the_outline(beam):
    view = page(beam)
    assert tuple(view.group_buttons) == ("main", "check")
    assert (*UPPER, "bar_type") in beam.bindings.items and (*LOWER, "bar_type") not in beam.bindings.items
    assert view.status.get() == "" and len(view.layout.bars) == 77


def test_the_lower_layers_inside_are_kept_but_not_shown(beam):
    beam.document.data["鉄筋"]["梁"]["faces"]["下"]["inner_layers"] = [{"count": 18, "clear_gap_mm": 30}]
    page(beam)._rebuild()
    assert (*LOWER, "inner_layers", 0, "count") not in beam.bindings.items
    assert not buttons(page(beam).inputs, "＋ 2段目を追加")  # the upper face's button says 3段目
    enter(beam, (*BEAM, "concrete_strength_mpa"), "30")
    assert beam.document.data["鉄筋"]["梁"]["faces"]["下"]["inner_layers"] == [{"count": 18, "clear_gap_mm": 30}]


def test_the_beam_readouts(beam):
    view = page(beam)
    assert view.readouts[("上", 2)].get() == "172.0（左右対称になりません）"  # 17 − 8 = 9 left over
    assert ("側面", 1) not in view.readouts  # the side bars' centre is given (指定)
    press(beam, (*UPPER, "cover_mode"), "自動")
    assert page(beam).readouts[("上", 1)].get() == "—"  # no pure cover yet
    assert page(beam).status.get() == "鉄筋.梁.pure_cover_mm: 値が必要です"
    enter(beam, (*BEAM, "pure_cover_mm"), "70")
    assert page(beam).readouts[("上", 1)].get() == "108.0"  # 70 + 22 + 32 / 2
    assert beam_cards.cover_lines(page(beam), "上") == [
        "純かぶり　70", "＋ スターラップの径　22", "＋ 主鉄筋の径／2　16", "芯かぶり　108.0"]
    assert beam_cards.readout(page(beam), ("上", 3)) == "—"


def test_the_side_bars_centre_is_read_out_when_automatic(beam):
    press(beam, (*BEAM, "side_bars", "cover_mode"), "自動")
    enter(beam, (*BEAM, "pure_cover_mm"), "70")
    assert page(beam).readouts[("側面", 1)].get() == "103.0"  # 70 + 22 (inside the stirrups) + 22 / 2
    assert page(beam).set_side_bars(False)
    assert beam_cards.readout(page(beam), ("側面", 1)) == "—"
    assert buttons(page(beam).inputs, "側面筋を入れる")


def over(editor, monkeypatch, widget, delta=-120):
    """A wheel event with the pointer over *widget*. Tk's own events do not reach the tests and the withdrawn window
    is not on the screen, so the widget under the pointer is given."""
    monkeypatch.setattr(editor.root, "winfo_containing", lambda x, y: widget, raising=False)
    return SimpleNamespace(x_root=0, y_root=0, delta=delta, state=0)


def test_the_wheel_scrolls_the_cards(beam, monkeypatch):
    view = page(beam)
    card = beam.bindings.items[(*BEAM, "concrete_strength_mpa")].cell.widget
    before = view.inputs_canvas.yview()
    assert view.wheel(over(beam, monkeypatch, card)) and view.inputs_canvas.yview() != before
    assert view.wheel(over(beam, monkeypatch, card, delta=120)) and view.inputs_canvas.yview() == before
    beam._wheel(over(beam, monkeypatch, card))  # the editor hands the wheel to the page
    assert view.inputs_canvas.yview() != before
    assert not view.wheel(over(beam, monkeypatch, beam.tree))  # outside the page
    assert not view.wheel(over(beam, monkeypatch, None))  # outside the editor


def test_the_wheel_leaves_a_table_to_scroll_itself(beam, monkeypatch):
    assert page(beam).select_group("check")
    view = page(beam)
    sheet = cell(beam, "片持ち梁の照査", "外観の照査").sheet  # the conditions are a table (Form.properties)
    before = view.inputs_canvas.yview()
    assert not view.wheel(over(beam, monkeypatch, sheet.winfo_children()[0]))
    assert view.inputs_canvas.yview() == before


def test_the_side_bars_take_the_main_sizes(beam):
    values = cell(beam, *BEAM, "side_bars", "diameter_mm").widget.cget("values")
    assert tuple(values) == ("", *(f"D{size}" for size in beam_cards.MAIN_SIZES)) and values[1] == "D16"


def test_overlapping_bars_are_a_warning(beam):
    enter(beam, (*BEAM, "side_bars", "start_mm"), "108")
    assert "2 か所で重なっています" in page(beam).status.get()


def test_a_blank_the_beam_layout_needs_is_named(beam):
    enter(beam, (*UPPER, "diameter_mm"), "")
    assert page(beam).status.get() == "鉄筋.梁.faces.上.diameter_mm: 値が必要です"
    assert page(beam).readouts[("上", 2)].get() == "—"  # no layout: no centre


def test_upper_layers_are_added_and_removed(beam):
    rows = beam.document.data["鉄筋"]["梁"]["faces"]["上"]["inner_layers"]
    (add,) = buttons(page(beam).inputs, "＋ 3段目を追加")
    add.invoke()
    beam.root.update()
    assert len(rows) == 2 and (*UPPER, "inner_layers", 1, "count") in beam.bindings.items
    (remove, _) = buttons(page(beam).inputs, "×")  # the 2nd layer's: it and the layers inside it go
    remove.invoke()
    beam.root.update()
    assert rows == []


def test_the_beam_helps(beam):
    found = helps(page(beam).inputs)
    assert len(found) == 5  # 純かぶり, 芯かぶり of both faces, 側面筋, 効く脚
    for button in found:
        button.invoke()
    assert all(any(child.winfo_class() == "Toplevel" for child in button.winfo_children()) for button in found)


def test_the_beam_check_group_holds_only_the_conditions(beam):
    assert page(beam).select_group("check")
    assert (*BEAM, "aggregate_max_mm") not in beam.bindings.items
    assert ("片持ち梁の照査", "外観の照査") in beam.bindings.items


FOOTING = ("鉄筋", "フーチング")
F_LOWER, F_UPPER = (*FOOTING, "faces", "下"), (*FOOTING, "faces", "上")


@pytest.fixture
def footing(editor):
    """The footing page with 純かぶり 70, on the lower face 線路 D25@125 and 直角 D29@125 (自動, 線路 outside), the
    upper face blank, and the stirrups D16 @250: 線路 at 130 across the width, 直角 2 per 1 m."""
    data = editor.document.data["鉄筋"]["フーチング"] = blank_footing()
    data["pure_cover_mm"] = 70
    data["faces"]["下"]["線路"].update(diameter_mm=25, pitch_mm=125)
    data["faces"]["下"]["直角"].update(diameter_mm=29, pitch_mm=125)
    data["stirrups"]["線路"].update(diameter_mm=16, pitch_mm=250, distribution_mode="間隔", width_pitch_mm=130)
    data["stirrups"]["直角"].update(diameter_mm=16, pitch_mm=250, distribution_mode="密度", density_per_m=2)
    assert page(editor).select_member("フーチング")
    editor.root.update()
    return editor


def titles(widget):
    """The titles of the cards under *widget*."""
    found = [widget.cget("text")] if widget.winfo_class() == "TLabelframe" else []
    for child in widget.winfo_children():
        found += titles(child)
    return found


def test_the_footing_is_entered_on_cards(footing):
    view = page(footing)
    assert tuple(view.group_buttons) == ("main",)
    assert (*F_LOWER, "outer_direction") in footing.bindings.items
    assert (*F_UPPER, "outer_direction") not in footing.bindings.items  # kept in the data, not shown
    assert view.readouts[("下", "線路", 1)].get() == "82.5"  # 70 + 25 / 2
    assert view.readouts[("下", "直角", 1)].get() == "109.5"  # 70 + 25 + 29 / 2
    assert view.readouts[("per_m", "下", "線路", 1)].get() == "8"
    assert view.readouts[("上", "線路", 1)].get() == "—" and view.status.get() == ""  # the upper face is not read
    assert "線路方向　1段目は外側" in titles(view.inputs) and "直角方向　1段目は内側" in titles(view.inputs)
    enter(footing, (*FOOTING, "concrete_strength_mpa"), "30")
    assert footing.document.data["鉄筋"]["フーチング"]["faces"]["上"]["outer_direction"] == "線路"


def test_the_direction_outside_is_chosen_on_the_lower_face(footing):
    press(footing, (*F_LOWER, "outer_direction"), "直角")
    view = page(footing)
    assert view.readouts[("下", "直角", 1)].get() == "84.5"  # 70 + 29 / 2
    assert view.readouts[("下", "線路", 1)].get() == "111.5"  # 70 + 29 + 25 / 2
    assert "直角方向　1段目は外側" in titles(view.inputs)


def test_a_footing_layer_inside_and_its_crossing(footing):
    rows = footing.document.data["鉄筋"]["フーチング"]["faces"]["下"]["線路"]["inner_layers"]
    add = buttons(page(footing).inputs, "＋ 2段目を追加")[2]  # 上面 線路, 上面 直角, 下面 線路, 下面 直角
    add.invoke()
    footing.root.update()
    assert rows == [{"pitch_mm": None, "clear_gap_mm": None}]
    assert page(footing).status.get() == "下面：鉄筋.フーチング.faces.下.線路.inner_layers[0].pitch_mm: 値が必要です"
    layer = (*F_LOWER, "線路", "inner_layers", 0)
    enter(footing, (*layer, "pitch_mm"), "125")
    enter(footing, (*layer, "clear_gap_mm"), "25")
    view = page(footing)
    assert view.readouts[("下", "線路", 2)].get() == "芯かぶり 132.5・1 m 当たり 8 本・ほかの段と交差"  # 82.5 + 25 + 25
    assert view.readouts[("per_m", "下", "直角", 1)].get() == "8・ほかの段と交差"  # |132.5 − 109.5| < 27
    assert view.status.get() == "警告：下面で段が 1 か所で交差しています。配筋略図で確かめてください（計算は止めません）。"
    assert footing_cards.readout(view, ("下", "線路", 3)) == "—"
    (remove,) = buttons(view.inputs, "×")
    remove.invoke()
    footing.root.update()
    assert rows == []


def test_a_blank_the_lower_face_needs_is_named(footing):
    enter(footing, (*F_LOWER, "線路", "diameter_mm"), "")
    assert page(footing).status.get() == "下面：鉄筋.フーチング.faces.下.線路.diameter_mm: 値が必要です"
    assert page(footing).readouts[("下", "直角", 1)].get() == "—"


def test_what_the_footing_reader_refuses_is_named(footing):
    footing.document.data["鉄筋"]["フーチング"]["materials"]["main"] = "SD999"
    page(footing).refresh()
    assert page(footing).status.get().startswith("鉄筋.フーチング.materials.main:")
    assert page(footing).readouts[("下", "線路", 1)].get() == "—"


def test_the_stirrups_across_the_width(footing):
    view = page(footing)
    assert view.readouts[("stirrup", "線路")].get() == "1 m 当たり 7.69 本"  # 1000／130
    assert view.readouts[("stirrup", "直角")].get() == "間隔 500.0 mm 相当"  # 1000／2
    assert (*FOOTING, "stirrups", "線路", "width_pitch_mm") in footing.bindings.items
    press(footing, (*FOOTING, "stirrups", "線路", "distribution_mode"), "密度")
    assert (*FOOTING, "stirrups", "線路", "density_per_m") in footing.bindings.items
    assert (*FOOTING, "stirrups", "線路", "width_pitch_mm") not in footing.bindings.items
    assert page(footing).readouts[("stirrup", "線路")].get() == "—"  # no bars per 1 m yet


def test_a_stirrup_without_its_mode_has_no_width_input(footing):
    footing.document.data["鉄筋"]["フーチング"]["stirrups"]["直角"]["distribution_mode"] = None
    page(footing)._rebuild()
    stirrups = (*FOOTING, "stirrups", "直角")
    assert (*stirrups, "density_per_m") not in footing.bindings.items
    assert (*stirrups, "width_pitch_mm") not in footing.bindings.items
    assert ("stirrup", "直角") not in page(footing).readouts


def test_the_footing_helps(footing):
    found = helps(page(footing).inputs)
    assert len(found) == 2  # 純かぶりと芯かぶり, スターラップ
    for button in found:
        button.invoke()
    assert all(any(child.winfo_class() == "Toplevel" for child in button.winfo_children()) for button in found)


def test_the_footing_sizes(footing):
    assert tuple(cell(footing, *F_LOWER, "線路", "diameter_mm").widget.cget("values"))[1:] == tuple(
        f"D{size}" for size in footing_cards.MAIN_SIZES) == ("D13", "D16", "D19", "D22", "D25", "D29", "D32", "D35")
    assert tuple(cell(footing, *FOOTING, "stirrups", "線路", "diameter_mm").widget.cget("values"))[-1] == "D25"


def test_a_given_footing_cover_is_entered(footing):
    press(footing, (*F_LOWER, "直角", "cover_mode"), "指定")
    assert (*F_LOWER, "直角", "center_mm") in footing.bindings.items
    assert ("下", "直角", 1) not in page(footing).readouts
    assert page(footing).status.get() == "下面：鉄筋.フーチング.faces.下.直角.center_mm: 値が必要です"
