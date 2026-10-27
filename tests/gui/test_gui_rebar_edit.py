"""Editing the 鉄筋 section: blank items from the field table, the column preview; checks come from inputs/calc."""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from gui_support import blank_footing
from webpier.calc.column_rebar import table
from webpier.core.reader import Reader
from webpier.gui import rebar_edit
from webpier.gui.document import EditorError
from webpier.inputs.rebar import parse_rebar

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))


def data():
    return deepcopy(CURRENT)


@pytest.mark.parametrize("path", [
    ("鉄筋", "柱", "main_bars", "線路", "inner_layers"), ("鉄筋", "柱", "main_bars", "直角", "inner_layers"),
    ("鉄筋", "柱", "column_hoops", "direction_rows"),
    ("鉄筋", "梁", "faces", "上", "inner_layers"), ("鉄筋", "梁", "faces", "下", "inner_layers"),
    ("鉄筋", "フーチング", "faces", "下", "直角", "inner_layers")])
def test_a_new_row_is_blank_and_reads_as_not_entered(path):
    document = data()
    index = rebar_edit.add_row(document, path)
    row = rebar_edit.items(document, path)[index]
    assert row and all(value is None for value in row.values())
    parse_rebar(Reader(document))
    assert rebar_edit.delete_row(document, path, index)
    assert not rebar_edit.delete_row(document, path, index + 5)


def test_a_blank_object_has_the_fields_of_the_field_table():
    assert rebar_edit.blank(("鉄筋", "柱", "main_bars", "線路")) == {
        "diameter_mm": None, "per_face_count": None, "cover_mode": None, "center_mm": None, "endpoints": None,
        "distribution": {"mode": None, "edge_center_mm": None, "pitch_mm": None}, "inner_layers": []}
    assert rebar_edit.blank(("鉄筋", "梁", "stirrups")) == {"diameter_mm": None, "effective_legs": None, "pitch_mm": None}


def test_side_bars_are_added_blank_or_removed():
    document = data()
    rebar_edit.set_side_bars(document, False)
    assert document["鉄筋"]["梁"]["side_bars"] is None
    assert parse_rebar(Reader(document)).beam.side is None
    rebar_edit.set_side_bars(document, True)
    assert set(document["鉄筋"]["梁"]["side_bars"]) == {"diameter_mm", "per_face_count", "start_mm", "pitch_mm",
                                                       "stirrup_position", "cover_mode", "center_mm"}
    assert parse_rebar(Reader(document)).beam.side.diameter is None


def test_the_preview_is_the_calculated_layout():
    layout = rebar_edit.column_preview(data())
    assert len(layout.bars) == 76 and not layout.customized
    assert len(table(layout.bars, "線路")) == 11 and len(table(layout.bars, "直角")) == 31


def test_a_blank_the_layout_needs_is_reported_with_its_path():
    document = data()
    rebar_edit.add_row(document, ("鉄筋", "柱", "main_bars", "線路", "inner_layers"))
    with pytest.raises(EditorError, match=r"鉄筋.柱.main_bars.線路.inner_layers\[0\].per_face_count: 値が必要です"):
        rebar_edit.column_preview(document)
    document = data()
    document["下部構造"]["寸法"]["正面"]["W6"] = None
    with pytest.raises(EditorError, match="下部構造.寸法.正面.W6: 値が必要です"):
        rebar_edit.column_preview(document)


TABLES = ("鉄筋", "柱", "custom_tables")


def test_a_hand_made_table_starts_from_the_table_in_use():
    document = data()
    layout = rebar_edit.column_preview(document)
    made = rebar_edit.customize(document, layout, "線路")
    assert made is rebar_edit.items(document, TABLES)["線路"] and rebar_edit.items(document, TABLES)["直角"] is None
    assert made["tension_rows"] == 1 and len(made["rows"]) == 11
    assert made["rows"][0] == {"center_mm": 108.0, "diameter_mm": 32.0, "count": 29}
    assert rebar_edit.customize(document, layout, "線路") is made  # once made, kept
    table = rebar_edit.direction_view(rebar_edit.column_preview(document), "線路")
    assert table.custom and table.rows == rebar_edit.direction_view(layout, "線路").rows


def test_the_cells_rows_and_tension_of_a_hand_made_table():
    document = data()
    layout = rebar_edit.column_preview(document)
    rebar_edit.set_cell(document, layout, "直角", 0, "center_mm", 110.0)  # starts the table
    rows = rebar_edit.items(document, TABLES)["直角"]["rows"]
    assert rows[0] == {"center_mm": 110.0, "diameter_mm": 19.0, "count": 9}
    assert rebar_edit.insert_row(document, layout, "直角", 0) == 1 and rows[1] == rows[0] and rows[1] is not rows[0]
    rows[1]["center_mm"] = 200.0
    assert rebar_edit.move_row(document, layout, "直角", 1, -1) == 0 and rows[0]["center_mm"] == 200.0
    assert rebar_edit.move_row(document, layout, "直角", 0, -1) is None
    assert rebar_edit.move_row(document, layout, "直角", len(rows) - 1, 1) is None
    assert rebar_edit.delete_table_row(document, layout, "直角", 0) and rows[0]["center_mm"] == 110.0
    assert not rebar_edit.delete_table_row(document, layout, "直角", len(rows))
    rebar_edit.set_tension(document, layout, "直角", 2)
    assert rebar_edit.direction_view(rebar_edit.column_preview(document), "直角").tension == 2
    assert rebar_edit.reset_table(document, "直角") and not rebar_edit.reset_table(document, "直角")
    assert rebar_edit.items(document, TABLES)["直角"] is None


def test_the_last_row_of_a_hand_made_table_stays():
    document = data()
    layout = rebar_edit.column_preview(document)
    rebar_edit.customize(document, layout, "線路")["rows"][1:] = []
    assert not rebar_edit.delete_table_row(document, layout, "線路", 0)


def test_a_table_that_cannot_be_made_is_an_editor_error():
    document = data()
    document["鉄筋"]["柱"]["main_bars"]["線路"]["per_face_count"] = 2  # 両端＋中央ピッチ with its two edge bars
    document["鉄筋"]["柱"]["main_bars"]["直角"]["distribution"] = {"mode": "等分", "edge_center_mm": 60.0, "pitch_mm": None}
    document["鉄筋"]["柱"]["main_bars"]["直角"]["endpoints"] = "含む"
    with pytest.raises(EditorError, match="線路方向の表で、線路の主鉄筋の段が1段ずつの行になっていません"):
        rebar_edit.direction_view(rebar_edit.column_preview(document), "線路")


def test_editing_the_main_bars_of_a_direction_makes_its_table_again():
    document = data()
    before = rebar_edit.main_bars(document)
    layout = rebar_edit.column_preview(document)
    for direction in ("線路", "直角"):
        rebar_edit.customize(document, layout, direction)
    assert rebar_edit.reset_changed(document, before) == []
    document["鉄筋"]["柱"]["main_bars"]["線路"]["distribution"]["pitch_mm"] = 140.0
    assert rebar_edit.reset_changed(document, before) == ["線路"]
    tables = rebar_edit.items(document, TABLES)
    assert tables["線路"] is None and tables["直角"] is not None
    assert before["線路"]["distribution"]["pitch_mm"] == 150.0  # a copy, not the document


def test_the_beam_preview_is_the_calculated_layout():
    layout = rebar_edit.beam_preview(data())
    assert (layout.width.value, layout.depth.value) == (2700.0, 2700.0) and len(layout.bars) == 77


@pytest.mark.parametrize("path,message", [
    (("下部構造", "寸法", "高さ", "H3"), "下部構造.寸法.高さ.H3: 値が必要です"),
    (("鉄筋", "梁", "faces", "上", "count"), "鉄筋.梁.faces.上.count: 値が必要です"),
])
def test_a_blank_the_beam_preview_needs_is_reported_with_its_path(path, message):
    document = data()
    rebar_edit.items(document, path[:-1])[path[-1]] = None
    with pytest.raises(EditorError, match=re.escape(message)):
        rebar_edit.beam_preview(document)


COLUMN_WARNING = ("柱：線路方向と直角方向の配置表で鉄筋の本数が違います（線路 D19 18本 D32 56本・直角 D19 18本 D32 58本）。"
                  "05 鉄筋の柱の配置表を確かめてください（計算は止めません）。")


def fewer(document):
    """The 線路 table by hand, with 27 bars in its first row instead of 29: 2 bars fewer than the 直角 table's."""
    rebar_edit.set_cell(document, rebar_edit.column_preview(document), "線路", 0, "count", 27)
BEAM_WARNING = "梁：鉄筋が 2 か所で重なっています。05 鉄筋の梁の配筋略図で赤い鉄筋を確かめてください（計算は止めません）。"


def test_the_warnings_of_the_input_check():
    document = data()
    assert rebar_edit.warnings(document) == []
    fewer(document)
    assert rebar_edit.warnings(document) == [COLUMN_WARNING]
    document = data()
    document["鉄筋"]["梁"]["side_bars"]["start_mm"] = 108  # the top side bars on the upper face's outermost bars
    assert rebar_edit.warnings(document) == [BEAM_WARNING]
    fewer(document)
    assert rebar_edit.warnings(document) == [COLUMN_WARNING, BEAM_WARNING]


@pytest.mark.parametrize("group,key,left", [("側面", "B1", [COLUMN_WARNING]), ("正面", "W6", [BEAM_WARNING])])
def test_a_member_without_its_layout_has_no_warning(group, key, left):
    document = data()
    fewer(document)
    document["鉄筋"]["梁"]["side_bars"]["start_mm"] = 108
    document["下部構造"]["寸法"][group][key] = None  # an input error of the calculation, not a warning
    assert rebar_edit.warnings(document) == left



def automatic_footing():
    """current.json with the footing's lower face filled: 純かぶり 70, 線路 D25@125 outside, 直角 D29@125, and the
    stirrups of 線路 at 130 across the width; the upper face and the stirrups of 直角 blank."""
    document = data()
    footing = document["鉄筋"]["フーチング"] = blank_footing()
    footing["pure_cover_mm"] = 70
    footing["faces"]["下"]["線路"].update(diameter_mm=25, pitch_mm=125)
    footing["faces"]["下"]["直角"].update(diameter_mm=29, pitch_mm=125)
    footing["stirrups"]["線路"].update(distribution_mode="間隔", width_pitch_mm=130)
    return document


def test_the_footing_preview_keeps_each_face_and_direction():
    preview = rebar_edit.footing_preview(automatic_footing())
    assert [layer.center.value for layer in preview.faces["下"].layers] == [82.5, 109.5]
    assert preview.faces["上"] is None and set(preview.problems) == {"上"}
    assert preview.problems["上"] == "鉄筋.フーチング.faces.上.線路.diameter_mm: 値が必要です"
    legs, spacing = preview.stirrups["線路"]
    assert (legs.value, spacing.value) == (7.69, 130.0) and preview.stirrups["直角"] is None


def test_what_the_footing_reader_refuses_is_an_editor_error():
    document = data()
    document["鉄筋"]["フーチング"]["materials"]["main"] = "SD999"
    with pytest.raises(EditorError, match="鉄筋.フーチング.materials.main"):
        rebar_edit.footing_preview(document)
    assert rebar_edit.warnings(document) == []  # an input error, not a warning


def test_crossing_footing_layers_are_a_warning():
    document = automatic_footing()
    document["鉄筋"]["フーチング"]["faces"]["下"]["線路"]["inner_layers"] = [{"pitch_mm": 125, "clear_gap_mm": 25}]
    assert rebar_edit.warnings(document) == [
        "フーチング：下面で段が 1 か所で交差しています。05 鉄筋のフーチングの配筋略図で確かめてください（計算は止めません）。"]
