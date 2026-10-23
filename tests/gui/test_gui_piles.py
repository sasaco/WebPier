"""The 杭基礎 page, the 基礎形式 and the layers' c and De (decision 84), and the 出力項目 a pile foundation cannot make yet."""

import json
from pathlib import Path

import pytest
from conftest import CURRENT

from gui_support import InProcessRunner, registry
from webpier.gui import app as gui
from webpier.gui import calculation_page, grid
from webpier.gui.calculation import CalculationController
from webpier.inputs import outputs, parse_input
from webpier.inputs.outputs import OUTPUT_KEYS

FOUNDATION = ("下部構造", "基礎形式")
PILES = ("杭基礎",)
LAYOUT = (*PILES, "配置")
NOTHING_MADE = ()


@pytest.fixture
def editor(tk_root, input_path, quiet):
    return gui.InputEditor(tk_root, input_path)


def cell(editor, *path):
    return editor.bindings.items[path].cell


def type_in(editor, path, text):
    cell(editor, *path).type(text)


def choose(editor, kind):
    """Set the 基礎形式 as a person does on the 下部構造 page, then go to the 杭基礎 page."""
    editor.select("下部構造")
    type_in(editor, FOUNDATION, kind)
    assert editor.select("杭基礎")


def test_the_pile_page_follows_the_substructure_and_the_ground_page(editor):
    assert gui.PAGES.index("杭基礎") == gui.PAGES.index("地盤データ") + 1
    assert "杭基礎" in gui.INPUT_PAGES and "杭基礎" in gui.HINTS


def test_a_direct_foundation_shows_no_pile_item(editor):
    assert editor.select("杭基礎")
    assert not any(path[:1] == PILES for path in editor.bindings.items)


def test_the_foundation_type_is_a_choice_of_the_programs_list(editor):
    editor.select("下部構造")
    target = cell(editor, *FOUNDATION)
    assert target.get() == "直接基礎"
    assert target.sheet.get_dropdown_values(target.row, target.column) == ["直接基礎", "場所打ち杭", "鋼管ソイルセメント杭"]
    type_in(editor, FOUNDATION, "鋼管杭")
    assert FOUNDATION in editor.bindings.refused
    type_in(editor, FOUNDATION, "直接基礎")
    assert not editor.bindings.refused


def test_the_reserved_pile_items_are_gone_from_the_substructure_page(editor):
    editor.select("下部構造")
    shown = {path for path in editor.bindings.items}
    assert ("下部構造", "杭種") not in shown and ("下部構造", "単位体積重量", "杭", "鉛直重量") not in shown
    assert FOUNDATION in shown and ("下部構造", "斜角", "θ") in shown


def test_a_cast_in_place_pile_foundation_shows_its_own_items(editor):
    choose(editor, "場所打ち杭")
    shown = {path for path in editor.bindings.items if path[:1] == PILES}
    assert {(*PILES, "杭長"), (*PILES, "杭の単位体積重量"), (*PILES, "場所打ち杭", "杭径"), (*PILES, "場所打ち杭", "f'ck"),
            (*PILES, "場所打ち杭", "施工条件"), (*LAYOUT, "形式")} <= shown
    assert not any(path[1:2] == ("鋼管ソイルセメント杭",) for path in shown)
    condition = cell(editor, *PILES, "場所打ち杭", "施工条件")
    assert condition.sheet.get_dropdown_values(condition.row, condition.column) == ["", "自然泥水", "安定液使用"]


def test_a_steel_soil_cement_pile_foundation_shows_its_own_items(editor):
    choose(editor, "鋼管ソイルセメント杭")
    shown = {path for path in editor.bindings.items if path[:1] == PILES}
    assert {(*PILES, "鋼管ソイルセメント杭", key) for key in ("ソイルセメント径", "鋼管外径", "鋼管厚", "腐食代")} <= shown
    assert not any(path[1:2] == ("場所打ち杭",) for path in shown)


def test_the_pile_values_are_rounded_to_their_printed_digits_and_saved(editor):
    choose(editor, "場所打ち杭")
    type_in(editor, (*PILES, "杭長"), "19.0004")
    assert cell(editor, *PILES, "杭長").get() == "19.000"
    type_in(editor, (*PILES, "場所打ち杭", "施工条件"), "自然泥水")
    type_in(editor, (*PILES, "杭の単位体積重量"), "24.5")
    assert editor.document.data["杭基礎"]["杭長"] == 19.0 and editor.document.data["杭基礎"]["場所打ち杭"]["施工条件"] == "自然泥水"
    assert editor.save()
    assert json.loads(editor.document.path.read_text(encoding="utf-8"))["杭基礎"]["杭長"] == 19.0


def test_columns_of_piles_are_added_entered_and_deleted(editor):
    choose(editor, "場所打ち杭")
    positions = editor.document.data["杭基礎"]["配置"]["線路方向の列の位置"]
    assert positions == []
    for _ in range(3):
        assert pile_change(editor, "線路方向の列の位置", "add")
    assert positions == [None, None, None]
    assert color(editor, *LAYOUT, "線路方向の列の位置", 0) == grid.MISSING
    for index, text in enumerate(("-3", "0", "3.0004")):
        type_in(editor, (*LAYOUT, "線路方向の列の位置", index), text)
    assert positions == [-3.0, 0.0, 3.0] and cell(editor, *LAYOUT, "線路方向の列の位置", 2).get() == "3.000"
    assert pile_change(editor, "線路方向の列の位置", "delete")
    assert editor.document.data["杭基礎"]["配置"]["線路方向の列の位置"] == [-3.0, 0.0]
    assert pile_change(editor, "線路直角方向の列の位置", "add")
    assert editor.document.data["杭基礎"]["配置"]["線路直角方向の列の位置"] == [None]


def test_piles_left_out_are_added_entered_and_deleted(editor):
    choose(editor, "場所打ち杭")
    assert pile_change(editor, "抜く杭", "add")
    assert editor.document.data["杭基礎"]["配置"]["抜く杭"] == [{"線路方向の列": None, "線路直角方向の列": None}]
    type_in(editor, (*LAYOUT, "抜く杭", 0, "線路方向の列"), "2")
    type_in(editor, (*LAYOUT, "抜く杭", 0, "線路直角方向の列"), "2")
    assert editor.document.data["杭基礎"]["配置"]["抜く杭"] == [{"線路方向の列": 2, "線路直角方向の列": 2}]
    type_in(editor, (*LAYOUT, "抜く杭", 0, "線路方向の列"), "0")
    assert (*LAYOUT, "抜く杭", 0, "線路方向の列") in editor.bindings.refused
    type_in(editor, (*LAYOUT, "抜く杭", 0, "線路方向の列"), "2")
    assert pile_change(editor, "抜く杭", "delete")
    assert editor.document.data["杭基礎"]["配置"]["抜く杭"] == []
    assert not pile_change(editor, "抜く杭", "delete")


def test_a_refused_entry_blocks_adding_a_column(editor, quiet):
    choose(editor, "場所打ち杭")
    type_in(editor, (*PILES, "杭長"), "abc")
    assert not pile_change(editor, "線路方向の列の位置", "add")
    assert editor.document.data["杭基礎"]["配置"]["線路方向の列の位置"] == []


def test_the_ground_page_has_c_and_de_for_each_layer(editor):
    editor.select("地盤データ")
    for index in range(2):
        assert ("地盤データ", "層", index, "粘着力_c") in editor.bindings.items
        assert ("地盤データ", "層", index, "De") in editor.bindings.items
        assert ("地盤データ", "層", index, "一軸圧縮強度_qu") not in editor.bindings.items
    assert cell(editor, "地盤データ", "層", 1, "粘着力_c").get() == "0"
    type_in(editor, ("地盤データ", "層", 1, "De"), "0.3334")
    assert cell(editor, "地盤データ", "層", 1, "De").get() == "0.333"
    type_in(editor, ("地盤データ", "層", 1, "De"), "1.5")
    assert editor.bindings.message(("地盤データ", "層", 1, "De")) == "0～1 が必要です"


def test_a_new_layer_has_the_keys_of_c_and_de(editor):
    editor.select("地盤データ")
    from webpier.gui import pages
    assert set(pages.blank_layer()) >= {"粘着力_c", "De"} and "一軸圧縮強度_qu" not in pages.blank_layer()


def test_a_pile_input_with_every_value_entered_parses(editor, monkeypatch):
    monkeypatch.setattr(outputs, "PILE_OUTPUT_KEYS", ("detailing", "ground_model", "reactions"))
    from webpier.inputs import parse
    monkeypatch.setattr(parse, "PILE_OUTPUT_KEYS", ("detailing", "ground_model", "reactions"))
    choose(editor, "場所打ち杭")
    data = editor.document.data
    data["杭基礎"].update(杭長=19.0, 杭の単位体積重量=24.5)
    data["杭基礎"]["場所打ち杭"].update(杭径=1.0, **{"f'ck": 24.0}, 施工条件="自然泥水")
    data["杭基礎"]["配置"].update(形式="格子", 線路方向の列の位置=[-3.0, 3.0], 線路直角方向の列の位置=[-3.0, 3.0])
    data["outputs"] = {key: key in ("detailing", "ground_model", "reactions") for key in OUTPUT_KEYS}
    assert parse_input(data).piles.layout.pattern == "格子"


def color(editor, *path):
    target = cell(editor, *path)
    return target.sheet.props(target.row, target.column, "highlight")[0]


def pile_change(editor, key, action):
    from webpier.gui import pages
    from webpier.gui.form import Form
    return pages.pile_change(Form(editor, editor.form), key, action)


# 計算・印刷: the items a pile foundation cannot make yet ------------------------------------------------------------

@pytest.fixture
def calculation(tk_root, input_path, quiet, tmp_path):
    runner = InProcessRunner(registry())
    controller = CalculationController(tmp_path / "output", runner, registry=runner.registry)
    editor = gui.InputEditor(tk_root, input_path, calculation=controller)
    return editor


def states(editor):
    editor.select("計算・印刷")
    page = editor.view
    return page, {key: "disabled" in page.output_boxes[key].state() for key in OUTPUT_KEYS}


def test_a_direct_foundation_has_every_item_selectable_and_no_note(calculation):
    page, disabled = states(calculation)
    assert page.foundation_note.get() == ""
    chosen = calculation.document.data["outputs"]  # current.json chooses 0500, 0610 and 0710
    assert all(disabled[key] == (not all(chosen[item] for item in outputs.requires(key))) for key in OUTPUT_KEYS)
    assert not disabled["longitudinal_frame_analysis"] and disabled["footing"]


def test_a_pile_foundation_cannot_choose_an_item_it_cannot_make_yet(calculation):
    calculation.select("下部構造")
    type_in(calculation, FOUNDATION, "場所打ち杭")
    page, disabled = states(calculation)
    chosen = calculation.document.data["outputs"]
    for key in OUTPUT_KEYS:
        if key in outputs.PILE_OUTPUT_KEYS:
            assert not disabled[key]
        else:  # an item cannot be added, but one already chosen can be taken out
            assert disabled[key] == (not chosen[key])
    assert "場所打ち杭で選べる項目は、対応した段階から広がります" in page.foundation_note.get()


def test_a_checked_item_stays_enabled_so_that_it_can_be_unchecked(calculation):
    calculation.select("下部構造")
    type_in(calculation, FOUNDATION, "鋼管ソイルセメント杭")
    page, disabled = states(calculation)
    assert disabled["longitudinal"] is False  # current.json chooses 0500, 0610 and 0710 ...
    assert disabled["ground_model"] is False and disabled["longitudinal_seismic"] is False
    page.outputs["longitudinal"].set(False)
    page._output_changed("longitudinal")
    assert calculation.document.data["outputs"]["longitudinal"] is False
    assert "disabled" in page.output_boxes["longitudinal"].state()


def test_the_note_names_the_items_a_pile_foundation_can_make(calculation, monkeypatch):
    monkeypatch.setattr(outputs, "PILE_OUTPUT_KEYS", ("detailing", "ground_model", "reactions"))
    monkeypatch.setattr(calculation_page, "PILE_OUTPUT_KEYS", ("detailing", "ground_model", "reactions"))
    calculation.select("下部構造")
    type_in(calculation, FOUNDATION, "場所打ち杭")
    page, disabled = states(calculation)
    assert "いま選べる項目: detailing・ground_model・reactions" in page.foundation_note.get()
    assert not disabled["detailing"] and not disabled["reactions"] and disabled["longitudinal_frame_analysis"]
