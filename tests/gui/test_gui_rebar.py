"""The 鉄筋 page: values through the field table, the column drawn from calc.column_rebar (provisional, decision 68)."""

import pytest

from webpier.gui import app as gui
from webpier.gui import rebar_page

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


def bars(editor):
    canvas = page(editor).section.canvas
    return canvas.find_withtag("rebar")


def direction_rows(editor):
    return page(editor).direction_sheet.get_sheet_data()


def test_the_column_is_drawn_from_the_calculated_layout(editor):
    assert len(bars(editor)) == 76
    assert len(direction_rows(editor)) == 11
    page(editor).select_direction("直角")
    assert len(direction_rows(editor)) == 31
    assert direction_rows(editor)[0] == ["102.0", "19", "2", "SD390"] or direction_rows(editor)[0][1] in ("32", "19")
    assert page(editor).section.canvas.find_withtag("hoop")


def test_rebar_values_are_rounded_at_entry(editor):
    cover = (*COLUMN, "pure_cover_mm")
    cell(editor, *cover).type("70.04")
    assert cell(editor, *cover).get() == "70.0"
    diameter = (*RAIL, "diameter_mm")
    cell(editor, *diameter).type("31.6")
    assert cell(editor, *diameter).get() == "32"
    assert editor.document.data["鉄筋"]["柱"]["main_bars"]["線路"]["diameter_mm"] == 32


def test_edits_redraw_the_layout_and_errors_name_the_path(editor):
    count = (*RAIL, "per_face_count")
    cell(editor, *count).type("27")
    assert len(bars(editor)) == 72
    cell(editor, *count).type("")
    assert not bars(editor)
    assert page(editor).section.notice.cget("text") == "鉄筋.柱.main_bars.線路.per_face_count: 値が必要です"
    assert page(editor).direction_sheet.get_sheet_data() == []


def test_choices_of_the_rebar_tables(editor):
    target = cell(editor, *RAIL, "distribution", "mode")
    assert target.sheet.get_dropdown_values(target.row, target.column) == ["", "等分", "中央ピッチ", "両端＋中央ピッチ"]
    material = cell(editor, *COLUMN, "materials", "main")
    assert material.sheet.get_dropdown_values(material.row, material.column) == ["", "SD295", "SD345", "SD390"]


def test_layers_inside_can_be_added_and_deleted(editor):
    layers = (*RAIL, "inner_layers")
    assert page(editor).add_row(layers)
    rows = editor.document.data["鉄筋"]["柱"]["main_bars"]["線路"]["inner_layers"]
    assert rows == [{"per_face_count": None, "clear_gap_mm": None}]
    assert "鉄筋.柱.main_bars.線路.inner_layers[0].per_face_count: 値が必要です" in page(editor).section.notice.cget("text")
    cell(editor, *layers, 0, "per_face_count").type("27")
    cell(editor, *layers, 0, "clear_gap_mm").type("40")
    assert len(bars(editor)) == 76 + 2 * 27
    assert page(editor).delete_row(layers)
    assert rows == [] and len(bars(editor)) == 76
    assert not page(editor).delete_row(layers)  # nothing selected


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
    assert page(editor).section.canvas.find_withtag("section-outline") and not bars(editor)
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
    assert page(editor).section.notice.cget("text") == "下部構造.寸法.正面.W6: 値が必要です"
    assert page(editor).section.canvas.find_withtag("empty")


def test_selecting_a_layer_from_the_drawing(editor):
    page(editor).bar_clicked(0)  # (108, 108): the 線路 layer 1 corner
    assert page(editor).selected == ("layer", (("線路", 1),))
    assert len(page(editor).section.canvas.find_withtag("selected")) == 58


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
    assert "警告：配置表の変更のうち 1 件は" in page(editor).section.notice.cget("text")


def test_the_column_concrete_has_its_aggregate_size(editor):
    """Decision 48: Dmax belongs to the column concrete; 0611 and the JRSNAP export both read it."""
    size = cell(editor, *COLUMN, "aggregate_max_mm")
    assert size.get() == "25.0"
    assert size.sheet.get_cell_data(size.row, 0) == "粗骨材の最大寸法 Dmax"
    assert size.sheet.get_cell_data(size.row, 2) == "mm"
    size.type("20.04")
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
