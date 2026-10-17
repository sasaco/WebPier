"""The input pages: entry rounding, choices, units, the explicit-value buttons, bearing slots, saving."""

import json

import pytest
from conftest import CURRENT

from webpier.core.integrity import load_json
from webpier.core.printed import Precision
from webpier.gui import app as gui
from webpier.gui import grid
from webpier.gui.document import MISSING
from webpier.inputs import fields, parse_input
from webpier.inputs.fields import field


@pytest.fixture
def editor(tk_root, input_path, quiet):
    return gui.InputEditor(tk_root, input_path)


def cell(editor, *path):
    return editor.bindings.items[path].cell


def type_in(editor, path, text):
    cell(editor, *path).type(text)


def color(editor, *path):
    target = cell(editor, *path)
    return target.sheet.props(target.row, target.column, "highlight")[0]


def saved(editor):
    return load_json(editor.document.path.read_bytes())


B1 = ("下部構造", "寸法", "側面", "B1")


def test_every_input_page_opens_without_changes(editor):
    before = editor.document.path.read_bytes()
    for page in gui.INPUT_PAGES:
        assert editor.select(page)
        editor.root.update()
        assert not editor.dirty
    assert editor.save()
    assert editor.document.path.read_bytes() == before


def test_values_are_shown_with_their_printed_digits_and_program_units(editor):
    assert cell(editor, *B1).get() == "2.700"
    editor.select("上部構造")
    sheet = cell(editor, "上部構造", "列車", "1両の長さ").sheet
    row = cell(editor, "上部構造", "列車", "1両の長さ").row
    assert sheet.get_cell_data(row, 0) == "1両の長さ" and sheet.get_cell_data(row, 2) == "m"
    assert cell(editor, "上部構造", "列車", "編成数").get() == "10"
    assert cell(editor, "上部構造", "列車", "荷重修正係数", "安全性(破壊)").get() == "1.231"


def test_a_value_is_rounded_to_the_printed_digits_when_entered(editor):
    type_in(editor, B1, "2.7004")
    assert cell(editor, *B1).get() == "2.700"
    type_in(editor, B1, "2.8005")
    assert cell(editor, *B1).get() == "2.801"
    assert editor.document.data["下部構造"]["寸法"]["側面"]["B1"] == 2.801
    assert editor.dirty
    assert editor.save()
    assert saved(editor)["下部構造"]["寸法"]["側面"]["B1"] == 2.801
    parse_input(saved(editor))


def test_undo_restores_the_previous_value(editor):
    target = cell(editor, *B1)
    type_in(editor, B1, "3.1")
    target.sheet.undo()
    assert target.get() == "2.700"
    assert editor.document.data["下部構造"]["寸法"]["側面"]["B1"] == 2.7
    assert not editor.dirty


def test_text_that_cannot_be_entered_is_kept_marked_and_blocks_saving(editor, quiet):
    calls, _ = quiet
    before = editor.document.path.read_bytes()
    type_in(editor, B1, "abc")
    assert cell(editor, *B1).get() == "abc"
    assert color(editor, *B1) == grid.REFUSED
    assert editor.document.data["下部構造"]["寸法"]["側面"]["B1"] == 2.7
    assert editor.dirty
    assert not editor.save()
    assert calls[-1][:3] == ("showerror", "入力値を確認してください", "下部構造.寸法.側面.B1: 数値を入力してください")
    assert not editor.select("上部構造") and editor.page == "下部構造"
    assert editor.document.path.read_bytes() == before
    type_in(editor, B1, "2.75")
    assert color(editor, *B1) == grid.EDITABLE
    assert editor.save() and editor.select("上部構造")


def test_a_needed_blank_is_saved_as_null_and_marked(editor):
    type_in(editor, B1, "")
    assert editor.document.data["下部構造"]["寸法"]["側面"]["B1"] is None
    assert color(editor, *B1) == grid.MISSING
    assert editor.bindings.message(B1) == "値が必要です"
    assert "要確認 1 件" in editor.status.get()
    target = cell(editor, *B1)
    target.sheet.select_cell(target.row, target.column)
    editor.cell_selected(target.sheet)
    assert editor.cell_message.get() == "下部構造.寸法.側面.B1: 値が必要です"
    assert editor.save()
    assert saved(editor)["下部構造"]["寸法"]["側面"]["B1"] is None


def test_the_sign_rule_of_the_table_applies(editor):
    type_in(editor, ("下部構造", "寸法", "側面", "B2"), "-0.5")
    assert editor.bindings.refused[("下部構造", "寸法", "側面", "B2")] == "0以上の数値が必要です"


def test_choices_are_the_programs_lists(editor):
    editor.select("上部構造")
    for path, values in ((("上部構造", "支承データ", "起点側", "支承名"), ["固定", "可動"]),
                         (("上部構造", "列車", "車両名"), ["EA-17", "P-16"])):
        target = cell(editor, *path)
        assert target.sheet.get_dropdown_values(target.row, target.column) == values
    editor.select("下部構造")
    condition = cell(editor, "下部構造", "場所打ち杭の施工条件")
    assert condition.sheet.get_dropdown_values(condition.row, condition.column) == [
        "", "自然泥水", "ベントナイト泥水", "気中施工", "設定しない"]
    type_in(editor, ("下部構造", "杭種"), "鋼管杭")
    assert ("下部構造", "杭種") in editor.bindings.refused
    type_in(editor, ("下部構造", "杭種"), "直接基礎")
    assert not editor.bindings.refused


def test_the_table_drives_the_editor(editor, monkeypatch):
    monkeypatch.setitem(fields.FIELDS, "下部構造.寸法.側面.B1", fields.number(Precision(1, "m"), "positive"))
    editor.render()
    assert cell(editor, *B1).get() == "2.7"
    type_in(editor, B1, "2.75")
    assert cell(editor, *B1).get() == "2.8"


def test_derived_values_have_no_cells(editor):
    paths = {path for page in gui.INPUT_PAGES if editor.select(page) for path in editor.bindings.items}
    assert ("地盤データ", "層", 0, "層厚") not in paths
    assert not any("排除した土" in path for path in paths)
    editor.select("地盤データ")
    assert editor.soil_sheet.get_cell_data(0, 1) == "（計算値）"


def test_b7_button_writes_b9(editor):
    type_in(editor, ("下部構造", "寸法", "側面", "B7"), "2.3")
    editor.b7_button.invoke()
    assert cell(editor, "下部構造", "寸法", "側面", "B9").get() == "2.300"
    assert editor.save()
    assert saved(editor)["下部構造"]["寸法"]["側面"]["B9"] == 2.3


def test_b7_button_reports_a_blank_b7(editor, quiet):
    calls, _ = quiet
    type_in(editor, ("下部構造", "寸法", "側面", "B7"), "")
    editor.b7_button.invoke()
    assert calls[-1][:3] == ("showerror", "B9 を書き込めません", "下部構造.寸法.側面.B7: 値が必要です")
    assert editor.document.data["下部構造"]["寸法"]["側面"]["B9"] == 2.15


def test_same_as_bearings_writes_the_end_totals(editor):
    editor.select("上部工反力")
    assert cell(editor, "上部工反力", "起点側", "A支点", "付加死荷重_D2").get() == "660.00"
    editor.same_buttons["起点側"].invoke()
    assert cell(editor, "上部工反力", "起点側", "A支点", "付加死荷重_D2").get() == "520.00"
    assert editor.save()
    assert saved(editor)["上部工反力"]["起点側"]["A支点"]["付加死荷重_D2"] == 520.0
    parse_input(saved(editor))


def test_same_as_bearings_reports_a_partial_bearing(editor, quiet):
    calls, _ = quiet
    editor.select("上部工反力")
    type_in(editor, ("上部工反力", "終点側", "C支点", 4, "支承位置"), "1")
    editor.same_buttons["終点側"].invoke()
    assert calls[-1][:2] == ("showerror", "合計を書き込めません")
    assert "上部工反力.終点側.C支点[4].固定死荷重_D1: 値が必要です" in calls[-1][2]


def test_empty_bearing_slots_are_valid_and_partial_ones_mark_the_blanks(editor):
    editor.select("上部工反力")
    slot = ("上部工反力", "起点側", "B支点", 4)
    assert editor.document.data["上部工反力"]["起点側"]["B支点"][4] is None
    assert color(editor, *slot, "固定死荷重_D1") == grid.EDITABLE
    assert not editor.bindings.problems()
    type_in(editor, (*slot, "支承位置"), "5.5")
    assert editor.document.data["上部工反力"]["起点側"]["B支点"][4]["支承位置"] == 5.5
    assert color(editor, *slot, "固定死荷重_D1") == grid.MISSING
    assert editor.bindings.message((*slot, "列車分担", "L2")) == "値が必要です"
    assert color(editor, *slot, "列車分担", "L3") == grid.DISABLED
    assert len(editor.bindings.problems()) == 7
    type_in(editor, (*slot, "支承位置"), "")
    assert editor.document.data["上部工反力"]["起点側"]["B支点"][4] is None
    assert not editor.bindings.problems()
    assert not editor.dirty


def test_third_and_fourth_tracks_are_disabled(editor):
    editor.select("上部工反力")
    target = cell(editor, "上部工反力", "終点側", "C支点", 0, "列車分担", "L4")
    assert target.sheet.props(target.row, target.column, "readonly")
    assert color(editor, "上部工反力", "終点側", "C支点", 0, "列車分担", "L4") == grid.DISABLED


def test_a_pasted_range_enters_every_cell(editor):
    editor.select("上部工反力")
    first = cell(editor, "上部工反力", "終点側", "C支点", 2, "支承位置")
    editor.root.clipboard_clear()
    editor.root.clipboard_append("1.2345\t-1.2345")
    first.sheet.select_cell(first.row, first.column)
    first.sheet.paste()
    slots = editor.document.data["上部工反力"]["終点側"]["C支点"]
    assert slots[2]["支承位置"] == 1.235 and slots[3]["支承位置"] == -1.235
    assert first.get() == "1.235"


def test_saving_round_trips_a_valid_schema_2_input(editor):
    edits = [(B1, "2.75"), (("下部構造", "斜角", "θ"), "89.6")]
    for path, text in edits:
        type_in(editor, path, text)
    editor.select("上部構造")
    type_in(editor, ("上部構造", "列車", "車両名"), "EA-17")
    type_in(editor, ("上部構造", "支承データ", "起点側", "復旧性制動係数"), "1.25")
    editor.select("地盤データ")
    type_in(editor, ("地盤データ", "層", 1, "N値"), "50.4")
    assert editor.save()
    data = saved(editor)
    pier = parse_input(data)
    assert pier.substructure.b[1].value == 2.75 and pier.reserved.skew_angle.value == 90
    assert pier.train.vehicle == "EA-17" and pier.spans.origin.recovery_brake_coefficient.value == 1.25
    assert data["地盤データ"]["層"][1]["N値"] == 50 and type(data["地盤データ"]["層"][1]["N値"]) is int
    assert data["出典"] == json.loads(CURRENT.read_text(encoding="utf-8"))["出典"]  # kept unchanged


def test_an_optional_key_is_created_only_when_entered(editor):
    editor.select("上部構造")
    path = ("上部構造", "支承データ", "起点側", "復旧性制動係数")
    assert editor.bindings.value(path) is MISSING and cell(editor, *path).get() == ""
    assert color(editor, *path) == grid.EDITABLE
    type_in(editor, path, "")
    assert "復旧性制動係数" not in editor.document.data["上部構造"]["支承データ"]["起点側"]


def test_soil_layers_can_be_added_moved_and_deleted(editor, quiet):
    _, answers = quiet
    editor.select("地盤データ")
    layers = editor.document.data["地盤データ"]["層"]
    editor.soil_selected = 1
    assert gui.pages.soil_change(gui.Form(editor, editor.form), "add")
    assert len(layers) == 3 and layers[2]["層厚"] is None and editor.soil_selected == 2
    assert editor.bindings.message(("地盤データ", "層", 2, "層番")).startswith("空でない文字列が必要です")
    type_in(editor, ("地盤データ", "層", 2, "層番"), "中間層")
    form = gui.Form(editor, editor.form)
    assert gui.pages.soil_change(form, "up")
    assert [layer["層番"] for layer in layers] == ["表層", "中間層", "支持層"]
    assert gui.pages.soil_change(form, "duplicate") and len(layers) == 4
    editor.soil_selected = 1
    assert gui.pages.soil_change(form, "up")
    assert "層厚" not in layers[0] and layers[1]["層厚"] is None  # 表層 thickness is calculated
    assert not gui.pages.soil_change(form, "up")
    editor.soil_selected = 3
    assert not gui.pages.soil_change(form, "down")
    answers["askyesno"] = False
    assert not gui.pages.soil_change(form, "delete")
    answers["askyesno"] = True
    assert gui.pages.soil_change(form, "delete") and len(layers) == 3
    editor.soil_selected = 9
    assert not gui.pages.soil_change(form, "duplicate")


def test_restructuring_waits_for_refused_text(editor, quiet):
    editor.select("地盤データ")
    type_in(editor, ("地盤データ", "層", 1, "N値"), "x")
    assert not gui.pages.soil_change(gui.Form(editor, editor.form), "add")
    assert len(editor.document.data["地盤データ"]["層"]) == 2
