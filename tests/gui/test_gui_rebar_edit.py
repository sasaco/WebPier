"""Editing the 鉄筋 section: blank items from the field table, the column preview; checks come from inputs/calc."""

import json
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
