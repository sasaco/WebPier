"""The 鉄筋 page's member 杭 (decisions 87 and 92): shown only for a pile foundation, the reinforcement of a cast-in-place pile on
cards bound to the field table, the f'ck shared with the 杭基礎 page; of a 鋼管ソイルセメント杭 the pipe (its grade and wall shared
with the 杭基礎 page) and its 段落し (decision 126)."""

from tkinter import ttk

import pytest

from webpier.gui import app as gui
from webpier.gui import pile_window, rebar_edit, rebar_page

PILE = ("鉄筋", "杭")
CAST = ("杭基礎", "場所打ち杭")


@pytest.fixture
def editor(tk_root, input_path, quiet):
    editor = gui.InputEditor(tk_root, input_path)
    editor.document.data["下部構造"]["基礎形式"] = "場所打ち杭"
    assert editor.select("鉄筋")
    tk_root.update()
    return editor


def page(editor) -> rebar_page.RebarPage:
    return editor.view


def cell(editor, *path):
    return editor.bindings.items[path].cell


def enter(editor, path, text):
    bound = editor.bindings.items[path]
    bound.cell.show(text)
    editor.bindings.entered(bound)
    editor.root.update()


def test_the_pile_is_a_member_only_for_a_pile_foundation(editor):
    assert page(editor).members() == ("梁", "柱", "フーチング", "杭")
    editor.document.data["下部構造"]["基礎形式"] = "鋼管ソイルセメント杭"
    assert rebar_edit.members(editor.document.data) == (*rebar_edit.MEMBERS, "杭")  # decision 126
    editor.document.data["下部構造"]["基礎形式"] = "直接基礎"
    assert rebar_edit.members(editor.document.data) == rebar_edit.MEMBERS


def test_a_pile_member_left_over_from_another_foundation_falls_back_to_the_column(editor):
    assert page(editor).select_member("杭")
    editor.document.data["下部構造"]["基礎形式"] = "直接基礎"
    assert editor.select("下部構造") and editor.select("鉄筋")
    assert page(editor).member == "柱" and page(editor).members() == rebar_edit.MEMBERS


def test_the_main_bars_group_has_the_steels_concrete_cover_and_the_main_bars(editor):
    assert page(editor).select_member("杭")
    shown = set(editor.bindings.items)
    assert {(*PILE, "materials", "main"), (*PILE, "materials", "transverse"), (*PILE, "pure_cover_mm"),
            (*PILE, "aggregate_max_mm"), (*PILE, "main_bars", "diameter_mm"), (*PILE, "main_bars", "count"),
            (*CAST, "f'ck")} <= shown
    assert not any(path[:2] == PILE and path[2] in ("hoops", "cutoff") for path in shown)
    assert cell(editor, *PILE, "aggregate_max_mm").widget.master.winfo_children()[0].cget("text") == "粗骨材の最大寸法 mm"


def test_the_fck_is_the_pile_foundations_one_value(editor):
    assert page(editor).select_member("杭")
    enter(editor, (*CAST, "f'ck"), "24.04")
    assert editor.document.data["杭基礎"]["場所打ち杭"]["f'ck"] == 24.0 and cell(editor, *CAST, "f'ck").get() == "24.0"


def test_the_values_are_entered_rounded_and_saved_in_the_rebar(editor):
    assert page(editor).select_member("杭")
    for path, text in (((*PILE, "materials", "main"), "SD345"), ((*PILE, "pure_cover_mm"), "100.04"),
                       ((*PILE, "aggregate_max_mm"), "25"), ((*PILE, "main_bars", "diameter_mm"), "32"),
                       ((*PILE, "main_bars", "count"), "20")):
        enter(editor, path, text)
    assert not editor.bindings.refused
    saved = editor.document.data["鉄筋"]["杭"]
    assert saved["materials"]["main"] == "SD345" and saved["pure_cover_mm"] == 100.0 and saved["main_bars"] == {
        "diameter_mm": 32, "count": 20}
    enter(editor, (*PILE, "main_bars", "count"), "2.5")
    assert (*PILE, "main_bars", "count") in editor.bindings.refused


def test_the_hoops_have_the_footing_the_2d_zone_and_up_to_three_zones_below(editor):
    assert page(editor).select_member("杭") and page(editor).select_group("hoops")
    editor.root.update()
    assert {(*PILE, "hoops", zone, key) for zone in ("footing", "zone_2d") for key in ("diameter_mm", "sets", "pitch_mm")} <= set(
        editor.bindings.items)
    for number in (1, 2, 3):
        assert page(editor).add_row((*PILE, "hoops", "lower"))
        assert len(editor.document.data["鉄筋"]["杭"]["hoops"]["lower"]) == number
        assert (*PILE, "hoops", "lower", number - 1, "length_m") in editor.bindings.items
    enter(editor, (*PILE, "hoops", "lower", 2, "pitch_mm"), "300")
    assert editor.document.data["鉄筋"]["杭"]["hoops"]["lower"][2]["pitch_mm"] == 300.0
    assert page(editor).remove_row((*PILE, "hoops", "lower"), 1)
    assert len(editor.document.data["鉄筋"]["杭"]["hoops"]["lower"]) == 2
    assert (*PILE, "hoops", "lower", 2, "length_m") not in editor.bindings.items


def test_the_cutoff_group_has_the_section_after_it_the_lengths_and_the_rules(editor):
    assert page(editor).select_member("杭") and page(editor).select_group("cutoff")
    editor.root.update()
    cutoff = (*PILE, "cutoff")
    assert {(*cutoff, "main_bars", "diameter_mm"), (*cutoff, "main_bars", "count"), (*cutoff, "hoops", "sets"),
            (*cutoff, "cutoff_length_mm"), (*cutoff, "joint_reduction"), (*cutoff, "no_joint", "from_head_mm"),
            (*cutoff, "margin_ratio", "moment")} <= set(editor.bindings.items)
    assert not {(*cutoff, "head_anchorage_mm"), (*cutoff, "anchorage_stirrup")} & set(editor.bindings.items)
    enter(editor, (*cutoff, "margin_ratio", "shear"), "1.1")
    assert editor.document.data["鉄筋"]["杭"]["cutoff"]["margin_ratio"]["shear"] == 1.1
    page(editor).refresh()
    assert page(editor).status.get() == ""


def test_the_pile_window_draws_the_zones_the_cutoff_and_the_section(editor):
    assert page(editor).select_member("杭")
    editor.document.data["杭基礎"]["場所打ち杭"]["杭径"] = 1.0
    assert page(editor).toggle_window()
    window = page(editor).window()
    assert window.notice.get() == "" or "空欄" in window.notice.get()  # the blank rebar: the section needs values
    for path, text in (((*PILE, "pure_cover_mm"), "100"), ((*PILE, "main_bars", "diameter_mm"), "32"),
                       ((*PILE, "main_bars", "count"), "20")):
        enter(editor, path, text)
    assert page(editor).select_group("hoops")
    for path, text in (((*PILE, "hoops", "zone_2d", "diameter_mm"), "16"), ((*PILE, "hoops", "zone_2d", "pitch_mm"), "200"),
                       ((*PILE, "hoops", "zone_2d", "sets"), "1"), ((*PILE, "hoops", "footing", "diameter_mm"), "16"),
                       ((*PILE, "hoops", "footing", "pitch_mm"), "100"), ((*PILE, "hoops", "footing", "sets"), "1")):
        enter(editor, path, text)
    editor.root.update()
    assert len(window.section.find_withtag("rebar")) == 20 and window.notice.get() == ""
    assert window.rows == ["主鉄筋 20-D32　帯鉄筋 D16", "芯かぶり 132.0 mm", "芯間隔 " + f"{pile_window.spacing(500 - 132, 20):.1f} mm"]
    assert len(window.side.find_withtag("zone")) >= 2 and not window.side.find_withtag("cutoff")
    assert page(editor).add_row((*PILE, "hoops", "lower"))
    editor.document.data["鉄筋"]["杭"]["cutoff"].update(cutoff_length_mm=5000.0)
    editor.document.data["鉄筋"]["杭"]["cutoff"]["main_bars"].update(diameter_mm=32, count=10)
    window.select("cutoff")
    assert "段落し後" in window.notice.get() and window.view == "cutoff"
    window.refresh()
    assert len(window.side.find_withtag("cutoff")) == 2
    assert page(editor).toggle_window() is False


def test_the_pile_section_helpers():
    assert pile_window.bar_ring(1000, 100, 16, 32) == (132.0, 368.0, 392.0)
    assert round(pile_window.spacing(368, 20), 1) == 115.1 and pile_window.spacing(368, 0) == 0.0


def test_the_members_are_children_of_the_rebar_page_in_the_tree(editor):
    assert editor.tree.get_children() == gui.PAGES  # the pages stay the top level
    assert editor.tree.get_children("鉄筋") == ("鉄筋/梁", "鉄筋/柱", "鉄筋/フーチング", "鉄筋/杭")
    assert [editor.tree.item(item, "text") for item in editor.tree.get_children("鉄筋")] == ["梁", "柱", "フーチング", "杭"]
    assert editor.tree.item("鉄筋", "open")
    assert editor.tree.selection() == (editor.tree_item,) == ("鉄筋/柱",)


def test_choosing_a_member_in_the_tree_shows_its_cards(editor):
    editor.tree.selection_set("鉄筋/杭")
    editor.root.update()
    assert editor.page == "鉄筋" and page(editor).member == "杭" and (*PILE, "main_bars", "count") in editor.bindings.items
    editor.tree.selection_set("鉄筋/梁")
    editor.root.update()
    assert page(editor).member == "梁" and ("鉄筋", "梁", "pure_cover_mm") in editor.bindings.items
    assert editor.tree.selection() == ("鉄筋/梁",)


def test_choosing_a_member_from_another_page_opens_the_rebar_page_at_it(editor):
    assert editor.select("下部構造")
    editor.tree.selection_set("鉄筋/フーチング")
    editor.root.update()
    assert editor.page == "鉄筋" and page(editor).member == "フーチング" and page(editor).group == "main"


def test_the_rebar_page_itself_opens_at_the_member_last_shown(editor):
    assert page(editor).select_member("梁")
    assert editor.select("上部構造") and editor.select("鉄筋")
    assert page(editor).member == "梁" and editor.tree.selection() == ("鉄筋/梁",)


def test_the_pile_leaves_and_joins_the_tree_with_the_foundation_type(editor):
    assert page(editor).select_member("杭")
    assert editor.select("下部構造")
    cell(editor, "下部構造", "基礎形式").type("直接基礎")
    assert editor.tree.get_children("鉄筋") == ("鉄筋/梁", "鉄筋/柱", "鉄筋/フーチング")
    cell(editor, "下部構造", "基礎形式").type("場所打ち杭")
    assert editor.tree.get_children("鉄筋") == ("鉄筋/梁", "鉄筋/柱", "鉄筋/フーチング", "鉄筋/杭")


def test_a_member_that_is_not_there_cannot_be_chosen(editor):
    editor.document.data["下部構造"]["基礎形式"] = "直接基礎"
    assert not editor.select_member("杭")
    assert editor.select_member("梁") and page(editor).member == "梁"


def test_a_refused_entry_keeps_the_page_when_a_member_is_chosen_in_the_tree(editor):
    assert page(editor).select_member("杭")
    enter(editor, (*PILE, "main_bars", "count"), "2.5")
    assert (*PILE, "main_bars", "count") in editor.bindings.refused
    assert not editor.select_member("梁")
    assert page(editor).member == "杭" and editor.tree.selection() == ("鉄筋/杭",)


# --- decision 126: the 鋼管ソイルセメント杭's member 杭: 鋼管・ソイルセメント and 段落し -------------------------------------

STEEL = ("杭基礎", "鋼管ソイルセメント杭")
CUT = (*STEEL, "段落し")


@pytest.fixture
def steel(editor):
    data = editor.document.data
    data["下部構造"]["基礎形式"] = "鋼管ソイルセメント杭"
    data["杭基礎"]["鋼管ソイルセメント杭"].update({"ソイルセメント径": 1.0, "鋼管外径": 0.8, "鋼管厚": 18.0, "腐食代": 1.0,
                                             "鋼管材質": "SKK490"})
    assert editor.select("下部構造") and editor.select("鉄筋")
    assert page(editor).select_member("杭")
    editor.root.update()
    return editor


def test_the_pile_is_a_member_of_a_steel_pile_foundation_too(steel):
    assert page(steel).members() == ("梁", "柱", "フーチング", "杭")
    assert list(page(steel).group_buttons) == ["pipe", "cutoff"] and page(steel).group == "pipe"


def test_the_pipe_group_binds_the_grade_and_the_wall_of_the_pile_page_and_shows_the_rest(steel):
    shown = set(steel.bindings.items)
    assert {(*STEEL, "鋼管材質"), (*STEEL, "鋼管厚")} <= shown
    assert not any(path[:2] == PILE for path in shown)
    assert not {(*STEEL, "鋼管外径"), (*STEEL, "腐食代"), (*STEEL, "ソイルセメント径")} & shown  # shown only
    assert page(steel).readouts[(*STEEL, "有効肉厚")].get() == "17.0"
    enter(steel, (*STEEL, "鋼管厚"), "19.04")
    assert steel.document.data["杭基礎"]["鋼管ソイルセメント杭"]["鋼管厚"] == 19.0  # one value with the 杭基礎 page
    page(steel).refresh()
    assert page(steel).readouts[(*STEEL, "有効肉厚")].get() == "18.0"
    assert steel.select("杭基礎") and steel.bindings.items[(*STEEL, "鋼管厚")].cell.get() == "19.0"


def test_the_cutoff_group_has_the_pipe_below_it_and_the_lengths_of_aggrese_s_check_8(steel):
    assert page(steel).select_group("cutoff")
    steel.root.update()
    assert {(*CUT, "段落し後の鋼管厚"), (*CUT, "段落し後の鋼管材質"), (*CUT, "上杭長"), (*CUT, "施工余裕長", "低止まり"),
            (*CUT, "施工余裕長", "高止まり"), (*CUT, "継手を設けない範囲_杭頭から")} <= set(steel.bindings.items)
    assert page(steel).readouts[(*CUT, "有効肉厚")].get() == "—"
    for path, text in (((*CUT, "段落し後の鋼管厚"), "14"), ((*CUT, "上杭長"), "9050.4"), ((*CUT, "施工余裕長", "低止まり"), "0")):
        enter(steel, path, text)
    assert not steel.bindings.refused
    saved = steel.document.data["杭基礎"]["鋼管ソイルセメント杭"]["段落し"]
    assert (saved["段落し後の鋼管厚"], saved["上杭長"], saved["施工余裕長"]["低止まり"]) == (14.0, 9050, 0)
    page(steel).refresh()
    assert page(steel).readouts[(*CUT, "有効肉厚")].get() == "13.0"


def test_a_steel_pile_has_no_window_of_the_bars(steel):
    buttons = [child for child in page(steel).frame.winfo_children()[0].winfo_children()
               if isinstance(child, ttk.Button)]
    assert all(button.cget("text") != "配筋略図" for button in buttons)
    assert page(steel).toggle_window() is False and page(steel).window() is None


def test_a_cast_in_place_pile_left_for_a_steel_one_opens_at_the_pipe(editor):
    assert page(editor).select_member("杭") and page(editor).select_group("cutoff")
    editor.document.data["下部構造"]["基礎形式"] = "鋼管ソイルセメント杭"
    assert editor.select("下部構造") and editor.select("鉄筋")
    assert page(editor).member == "杭" and page(editor).group in ("pipe", "cutoff")
    assert not any(path[:2] == PILE for path in editor.bindings.items)
