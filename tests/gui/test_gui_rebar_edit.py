"""Editing the 鉄筋 section: blank rows, the copied detail positions and their basis; checks come from inputs/calc."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.calc.column_rebar import table
from webpier.core.reader import Reader
from webpier.gui import rebar_edit
from webpier.gui.document import EditorError
from webpier.inputs import parse_input
from webpier.inputs.rebar import parse_rebar

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))


def data():
    return deepcopy(CURRENT)


@pytest.mark.parametrize("member,family", [
    ("柱", "main_rows"), ("梁", "main_rows"), ("フーチング", "main_rows"), ("梁", "side_rows"), ("梁", "band_rows"),
    ("フーチング", "side_rows"), ("フーチング", "band_rows"), ("柱", "direction_rows"), ("柱", "manual_positions"),
    ("梁", "manual_positions")])
def test_a_new_row_is_blank_and_reads_as_not_entered(member, family):
    document = data()
    index = rebar_edit.add_row(document, member, family)
    row = rebar_edit.rows_of(document, member, family)[index]
    assert all(value is None for key, value in row.items() if key != "distribution")
    parse_rebar(Reader(document))
    assert rebar_edit.delete_row(document, member, family, index)
    assert not rebar_edit.delete_row(document, member, family, index + 5)


def test_a_new_column_row_has_its_distribution():
    assert rebar_edit.blank_row("柱", "main_rows")["distribution"] == {"mode": None, "edge_center_mm": None,
                                                                         "pitch_mm": None}
    assert "density_per_m" in rebar_edit.blank_row("フーチング", "band_rows")
    assert "density_per_m" not in rebar_edit.blank_row("梁", "band_rows")


def test_the_preview_is_the_calculated_layout():
    layout = rebar_edit.column_preview(data())
    assert len(layout.bars) == 76 and layout.manual is None
    assert len(table(layout.bars, "線路")) == 11 and len(table(layout.bars, "直角")) == 31


def test_a_blank_the_layout_needs_is_reported_with_its_path():
    document = data()
    rebar_edit.add_row(document, "柱", "main_rows")
    with pytest.raises(EditorError, match=r"鉄筋.柱.main_rows\[2\].per_face_count: 値が必要です"):
        rebar_edit.column_preview(document)
    document = data()
    document["下部構造"]["寸法"]["正面"]["W6"] = None
    with pytest.raises(EditorError, match="下部構造.寸法.正面.W6: 値が必要です"):
        rebar_edit.column_preview(document)


def test_copying_the_automatic_layout_records_its_basis():
    document = data()
    rebar_edit.copy_automatic(document)
    column = document["鉄筋"]["柱"]
    assert column["position_mode"] == "指定" and len(column["manual_positions"]) == 76
    assert column["manual_positions"][0] == {"x_mm": 108.0, "y_mm": 108.0, "diameter_mm": 32, "material": "SD390"}
    layout = rebar_edit.column_preview(document)
    assert layout.manual is not None and layout.manual_basis_current
    parse_input(document)
    column["pure_cover_mm"] = 80
    assert not rebar_edit.column_preview(document).manual_basis_current  # reported, not repaired


def test_the_confirmed_comparison_must_still_hold():
    document = data()
    shown = rebar_edit.comparison(document)
    assert not shown.detailed and shown.current == shown.candidate
    document["鉄筋"]["柱"]["pure_cover_mm"] = 75
    with pytest.raises(EditorError, match="比較し直してください"):
        rebar_edit.copy_automatic(document, shown)
    rebar_edit.copy_automatic(document, rebar_edit.comparison(document))
    assert rebar_edit.comparison(document).detailed


def test_switching_modes_keeps_both_inputs():
    document = data()
    with pytest.raises(EditorError, match="詳細位置がありません"):
        rebar_edit.use_mode(document, "指定")
    rebar_edit.copy_automatic(document)
    rebar_edit.use_mode(document, "基本")
    assert document["鉄筋"]["柱"]["position_mode"] == "基本" and len(document["鉄筋"]["柱"]["manual_positions"]) == 76
    rebar_edit.use_mode(document, "指定")
    assert rebar_edit.column_preview(document).manual is not None


def test_adding_a_bar_copies_the_automatic_layout_first_and_is_checked_by_the_calculation():
    document = data()
    index = rebar_edit.add_bar(document, {"x_mm": 2250.0, "y_mm": 1350.0, "diameter_mm": 32, "material": "SD390"})
    assert index == 76 and document["鉄筋"]["柱"]["position_mode"] == "指定"
    before = deepcopy(document["鉄筋"]["柱"])
    with pytest.raises(EditorError, match="鉄筋が重なっています"):
        rebar_edit.add_bar(document, {"x_mm": 2260.0, "y_mm": 1350.0, "diameter_mm": 32, "material": "SD390"})
    assert document["鉄筋"]["柱"] == before
    with pytest.raises(EditorError, match="X・Y・径をすべて入力してください"):
        rebar_edit.add_bar(document, {"x_mm": None, "y_mm": 1.0, "diameter_mm": 32})


def test_deleting_a_bar():
    document = data()
    assert not rebar_edit.delete_bar(document, 76)
    assert document["鉄筋"]["柱"]["position_mode"] == "基本"
    assert rebar_edit.delete_bar(document, 0)
    assert len(document["鉄筋"]["柱"]["manual_positions"]) == 75
    assert rebar_edit.delete_bar(document, 74) and not rebar_edit.delete_bar(document, 74)
