"""The 鉄筋 page: values through the field table, the column in its section and table window (decision 68)."""

import pytest

from webpier.gui import app as gui
from webpier.gui import column_cards, rebar_page

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
    assert len(window(editor).lines) == 11
    window(editor).select("直角")
    assert len(window(editor).lines) == 31
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
    assert list(cell(editor, *COLUMN, "materials", "main").buttons) == ["SD295", "SD345", "SD390"]


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


@pytest.mark.parametrize("member,groups,layers", [
    ("梁", ("main", "check"), ("鉄筋", "梁", "faces", "上", "inner_layers")),
    ("フーチング", ("main",), ("鉄筋", "フーチング", "faces", "下", "線路", "inner_layers"))])
def test_beam_and_footing_show_their_tables_and_outline(editor, member, groups, layers):
    assert page(editor).select_member(member)
    assert tuple(page(editor).group_buttons) == groups
    assert page(editor).section.canvas.find_withtag("section-outline")
    assert not page(editor).section.canvas.find_withtag("rebar")
    assert page(editor).section.notice.cget("text") == rebar_page.OUTLINE_ONLY
    for group in groups:
        assert page(editor).select_group(group)
    assert page(editor).add_row(layers)
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


def test_the_footing_faces_name_the_direction_outside(editor):
    assert page(editor).select_member("フーチング")
    assert cell(editor, "鉄筋", "フーチング", "faces", "下", "outer_direction").get() == "線路"
    assert ("鉄筋", "フーチング", "stirrups", "直角", "density_per_m") in editor.bindings.items


def test_a_table_change_without_its_bars_is_a_warning(editor):
    editor.document.data["鉄筋"]["柱"]["table_overrides"]["線路"] = [
        {"source_center_mm": 999, "source_diameter_mm": 32, "center_mm": 110, "diameter_mm": None}]
    page(editor).refresh()
    assert len(bars(editor)) == 76
    assert "警告：配置表の変更のうち 1 件は" in page(editor).status.get()


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
    environment = cell(editor, "柱の断面照査", "鋼材の腐食に対する環境条件")
    assert environment.get() == "一般の環境"
    assert environment.sheet.get_dropdown_values(environment.row, environment.column) == [
        "", "一般の環境", "腐食性環境", "特に厳しい腐食性環境"]
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
