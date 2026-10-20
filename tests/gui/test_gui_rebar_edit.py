"""Editing the 鉄筋 section: blank items from the field table, the column preview; checks come from inputs/calc."""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

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
    ("鉄筋", "柱", "column_hoops", "direction_rows"), ("鉄筋", "柱", "table_overrides", "線路"),
    ("鉄筋", "梁", "faces", "上", "inner_layers"), ("鉄筋", "梁", "faces", "下", "inner_layers"),
    ("鉄筋", "フーチング", "faces", "下", "直角", "inner_layers")])
def test_a_new_row_is_blank_and_reads_as_not_entered(path):
    document = data()
    index = rebar_edit.add_row(document, path)
    row = rebar_edit.items(document, path)[index]
    assert row and all(value is None for value in row.values())
    if path[2] != "table_overrides":  # a change of nothing is an input error (rebar._overrides)
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
    assert len(layout.bars) == 76 and layout.unmatched == ()
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


def test_the_table_lines_group_the_generated_rows():
    layout = rebar_edit.column_preview(data())
    rail = rebar_edit.table_lines(layout, "線路")
    assert len(rail) == 11 and rail[0].source == (108.0, 32.0) and rail[0].count == 29
    assert rail[0].layers == (("線路", 1),) and not rail[0].changed
    cross = rebar_edit.table_lines(layout, "直角")
    assert cross[0].source == (102.0, 19.0) and cross[0].count == 9 and len(cross) == 31


def test_a_table_change_is_written_undone_and_removed():
    document = data()
    source = (102.0, 19.0)  # the 直角 D19 bars at 102 from the left face
    rebar_edit.change_table(document, "直角", source, "center_mm", 110.0)
    rows = document["鉄筋"]["柱"]["table_overrides"]["直角"]
    assert rows == [{"source_center_mm": 102.0, "source_diameter_mm": 19.0, "center_mm": 110.0, "diameter_mm": None}]
    line = rebar_edit.table_lines(rebar_edit.column_preview(document), "直角")[1]
    assert (line.source, line.center, line.count, line.changed) == (source, 110.0, 9, True)
    rebar_edit.change_table(document, "直角", source, "diameter_mm", 22.0)
    assert rows[0]["diameter_mm"] == 22.0 and len(rows) == 1
    rebar_edit.change_table(document, "直角", source, "center_mm", 102.0)  # back to the generated centre
    assert rows[0]["center_mm"] is None
    rebar_edit.change_table(document, "直角", source, "diameter_mm", None)  # blank: nothing changed any more
    assert rows == []
    rebar_edit.change_table(document, "直角", source, "center_mm", 110.0)
    other = (350.0, 32.0)
    rebar_edit.change_table(document, "直角", other, "diameter_mm", 29.0)  # another row, before the undone one
    rows.insert(0, rows.pop())
    assert rebar_edit.undo_change(document, "直角", source) and rows == [
        {"source_center_mm": 350.0, "source_diameter_mm": 32.0, "center_mm": None, "diameter_mm": 29.0}]
    assert not rebar_edit.undo_change(document, "直角", source)


def test_changes_without_their_bars_are_removed():
    document = data()
    changes = document["鉄筋"]["柱"]["table_overrides"]
    changes["線路"] = [{"source_center_mm": 999.0, "source_diameter_mm": 32.0, "center_mm": 110.0, "diameter_mm": None}]
    changes["直角"] = [{"source_center_mm": 102.0, "source_diameter_mm": 19.0, "center_mm": 110.0, "diameter_mm": None}]
    assert rebar_edit.remove_unmatched(document, rebar_edit.column_preview(document)) == 1
    assert changes["線路"] == [] and len(changes["直角"]) == 1


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


LOST = {"source_center_mm": 999.0, "source_diameter_mm": 32.0, "center_mm": 110.0, "diameter_mm": None}
COLUMN_WARNING = "柱：配置表の変更のうち 1 件は、元の芯位置・径の鉄筋がないため使われていません（計算でも使いません）。"
BEAM_WARNING = "梁：鉄筋が 2 か所で重なっています。05 鉄筋の梁の配筋略図で赤い鉄筋を確かめてください（計算は止めません）。"


def test_the_warnings_of_the_input_check():
    document = data()
    assert rebar_edit.warnings(document) == []
    document["鉄筋"]["柱"]["table_overrides"]["線路"] = [dict(LOST)]
    assert rebar_edit.warnings(document) == [COLUMN_WARNING]
    document = data()
    document["鉄筋"]["梁"]["side_bars"]["start_mm"] = 108  # the top side bars on the upper face's outermost bars
    assert rebar_edit.warnings(document) == [BEAM_WARNING]
    document["鉄筋"]["柱"]["table_overrides"]["線路"] = [dict(LOST)]
    assert rebar_edit.warnings(document) == [COLUMN_WARNING, BEAM_WARNING]


@pytest.mark.parametrize("group,key,left", [("側面", "B1", [COLUMN_WARNING]), ("正面", "W6", [BEAM_WARNING])])
def test_a_member_without_its_layout_has_no_warning(group, key, left):
    document = data()
    document["鉄筋"]["柱"]["table_overrides"]["線路"] = [dict(LOST)]
    document["鉄筋"]["梁"]["side_bars"]["start_mm"] = 108
    document["下部構造"]["寸法"][group][key] = None  # an input error of the calculation, not a warning
    assert rebar_edit.warnings(document) == left
