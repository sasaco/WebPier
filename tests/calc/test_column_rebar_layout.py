"""Column main bar layout (CONTEXT.md 柱の配筋): positions from the basic input, the direction tables, detail positions.

Expected values: tests/fixtures/column_rebar_example2.json (independent transcription of Example2 10-6 / 11-6,
both tables and the 76 physical bars) and hand calculations in Decimal. Nothing missing is filled in (decision 5).
"""

import json
import re
from copy import deepcopy
from decimal import Decimal

import pytest

from reaction_support import FIXTURES, document, q
from webpier.calc.column_rebar import column_layout, table, yield_strength
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import parse_input

EXAMPLE = json.loads((FIXTURES / "column_rebar_example2.json").read_text(encoding="utf-8"))
ROW0, ROW1 = "鉄筋/柱/main_rows/0", "鉄筋/柱/main_rows/1"


def layout(**changes):
    return column_layout(parse_input(document(**changes)))


def mm(value):
    return Printed(float(value), 1, "mm")


def fails(message, **changes):
    with pytest.raises(InputError, match=re.escape(message)):
        layout(**changes)


def rows_of(result_table):
    return [{"center_mm": row.center.value, "diameter_mm": row.diameter.value, "count": row.count,
             "material": row.material} for row in result_table]


def physical(bars):
    return sorted((bar.x.value, bar.y.value, bar.diameter.value, bar.material) for bar in bars)


def test_current_input_reproduces_both_example2_tables():
    result = layout()
    assert (result.width, result.height) == (mm(4500), mm(2700))
    assert len(result.bars) == EXAMPLE["totals"]["all"] == 76
    assert physical(result.bars) == sorted((b["x_mm"], b["y_mm"], b["diameter_mm"], b["material"])
                                           for b in EXAMPLE["physical_bars"])
    for direction in ("線路", "直角"):
        assert rows_of(table(result.bars, direction)) == EXAMPLE["directional_rows"][direction]
    assert result.manual is None and result.bars is result.automatic


def test_face_rows_by_hand():
    first, second = layout().rows
    # D32, cover automatic: 純かぶり 70 + enclosing hoop 22 + 32/2 = 108 (主鉄筋の芯かぶり).
    assert (first.index, first.direction, first.center, first.material) == (0, "線路", mm(108), "SD390")
    # Edge bars at 108 / 4500 − 108; 27 interior bars at 150 centred: (4500 − 26 × 150) / 2 = 300.
    assert [p.value for p in first.positions] == [108, *range(300, 4201, 150), 4392]
    assert first.pitch == mm(150)
    # D19 given at 102; 9 bars at 250 centred on 2700: (2700 − 8 × 250) / 2 = 350.
    assert (second.direction, second.center) == ("直角", mm(102))
    assert [p.value for p in second.positions] == list(range(350, 2351, 250)) and second.pitch == mm(250)


def test_bar_rows_record_the_basic_input_row():
    bars = layout().bars
    assert {bar.rows for bar in bars if bar.diameter.value == 32} == {(0,)}
    assert {bar.rows for bar in bars if bar.diameter.value == 19} == {(1,)}


@pytest.mark.parametrize("endpoints,count,expected,pitch", [
    ("含む", 5, ["108", "1179", "2250", "3321", "4392"], "1071"),  # (4500 − 2 × 108) / 4
    ("含めない", 5, ["822", "1536", "2250", "2964", "3678"], "714"),  # (4500 − 216) / 6, from the edge + 1 step
])
def test_equal_division(endpoints, count, expected, pitch):
    row = layout(**{f"{ROW0}/distribution/mode": "等分", f"{ROW0}/endpoints": endpoints,
                    f"{ROW0}/per_face_count": count}).rows[0]
    assert [p.value for p in row.positions] == [float(value) for value in expected]
    assert row.pitch == mm(pitch)


def test_equal_division_rounds_each_position_to_the_printed_digits():
    row = layout(**{f"{ROW0}/distribution/mode": "等分", f"{ROW0}/distribution/edge_center_mm": 100,
                    f"{ROW0}/per_face_count": 4}).rows[0]
    spacing = Decimal(4300) / 3
    assert [p.value for p in row.positions] == [float(q(100 + i * spacing, 1)) for i in range(4)]
    assert row.positions[1] == mm("1533.3") and row.pitch == mm("1433.3")


def test_one_bar_sits_at_the_middle_of_the_face():
    row = layout(**{f"{ROW1}/per_face_count": 1}).rows[1]
    assert row.positions == (mm(1350),) and row.pitch is None


def test_two_edge_bars_have_no_pitch():
    row = layout(**{f"{ROW0}/per_face_count": 2}).rows[0]
    assert row.positions == (mm(108), mm(4392)) and row.pitch is None


def test_a_second_layer_is_built_up_from_the_first():
    second = {"diameter_mm": 25, "material": "SD345", "cover_mode": "自動", "center_mm": None, "clear_gap_mm": 40,
              "face_direction": "線路", "layer": 2, "per_face_count": 10, "endpoints": None,
              "distribution": {"mode": "中央ピッチ", "edge_center_mm": None, "pitch_mm": 300}}
    rows = deepcopy(document()["鉄筋"]["柱"]["main_rows"]) + [second]
    result = layout(**{"鉄筋/柱/main_rows": rows})
    added = result.rows[2]
    # 108 + 32/2 + 40 + 25/2 = 176.5 from each 線路 face; (4500 − 9 × 300) / 2 = 900.
    assert added.center == mm("176.5") and added.material == "SD345"
    assert [p.value for p in added.positions] == list(range(900, 3601, 300))
    rail = rows_of(table(result.bars, "線路"))
    assert {"center_mm": 176.5, "diameter_mm": 25, "count": 10, "material": "SD345"} in rail
    assert {"center_mm": 2523.5, "diameter_mm": 25, "count": 10, "material": "SD345"} in rail
    assert len(result.bars) == 96


def test_a_second_layer_needs_one_first_layer_and_its_gap():
    second = deepcopy(document()["鉄筋"]["柱"]["main_rows"][0]) | {"layer": 2, "clear_gap_mm": None}
    rows = deepcopy(document()["鉄筋"]["柱"]["main_rows"]) + [second]
    fails("鉄筋.柱.main_rows[2].clear_gap_mm: 値が必要です", **{"鉄筋/柱/main_rows": rows})
    third = deepcopy(second) | {"layer": 3, "clear_gap_mm": 40}
    fails("鉄筋.柱.main_rows[2].layer: 同じ面の2段目の行がちょうど1行必要です",
          **{"鉄筋/柱/main_rows": deepcopy(document()["鉄筋"]["柱"]["main_rows"]) + [third]})


def test_shared_corner_bars_count_once():
    # 直角 D32 bars at the 108 corners coincide with the 線路 corner bars: one physical bar for both rows.
    result = layout(**{f"{ROW1}/diameter_mm": 32, f"{ROW1}/center_mm": 108, f"{ROW1}/per_face_count": 2,
                       f"{ROW1}/distribution/mode": "両端＋中央ピッチ", f"{ROW1}/distribution/edge_center_mm": 108})
    assert len(result.bars) == 58
    corners = [bar for bar in result.bars if bar.rows == (0, 1)]
    assert sorted((b.x.value, b.y.value) for b in corners) == [(108, 108), (108, 2592), (4392, 108), (4392, 2592)]


def test_bars_at_one_position_must_be_the_same_bar():
    shared = {f"{ROW1}/center_mm": 108, f"{ROW1}/per_face_count": 2, f"{ROW1}/distribution/mode": "両端＋中央ピッチ",
              f"{ROW1}/distribution/edge_center_mm": 108}
    fails("鉄筋.柱.main_rows[1]: 同じ位置に径または材質の異なる鉄筋があります", **shared)
    rows = deepcopy(document()["鉄筋"]["柱"]["main_rows"])
    fails("鉄筋.柱.main_rows[2]: 同じ方向の鉄筋が同じ位置に重複しています", **{"鉄筋/柱/main_rows": rows + rows[:1]})


def test_overlapping_bars_are_rejected():
    # 直角 D19 at (108, 110) against the 線路 D32 corner (108, 108): 2 mm apart, 25.5 mm needed.
    fails("鉄筋.柱.main_rows[0]・[1]: 鉄筋が重なっています", **{f"{ROW1}/center_mm": 108,
                                                              f"{ROW1}/distribution/pitch_mm": 310})


def test_touching_bars_are_allowed():
    # (2700 − 2 × p) / 2 = 108 + 25.5 puts the first 直角 D19 at (32 + 19) / 2 = 25.5 from the D32 corner bar.
    result = layout(**{f"{ROW1}/center_mm": 108, f"{ROW1}/per_face_count": 3, f"{ROW1}/distribution/pitch_mm": 1216.5})
    assert [p.value for p in result.rows[1].positions] == [133.5, 1350, 2566.5]


def test_an_inactive_row_places_nothing():
    result = layout(**{f"{ROW1}/per_face_count": 0, f"{ROW1}/diameter_mm": None})
    assert len(result.rows) == 1 and len(result.bars) == 58


@pytest.mark.parametrize("path,value,message", [
    (f"{ROW0}/per_face_count", None, "鉄筋.柱.main_rows[0].per_face_count: 値が必要です"),
    (f"{ROW0}/diameter_mm", None, "鉄筋.柱.main_rows[0].diameter_mm: 値が必要です"),
    (f"{ROW0}/face_direction", None, "鉄筋.柱.main_rows[0].face_direction: 値が必要です"),
    (f"{ROW0}/cover_mode", None, "鉄筋.柱.main_rows[0].cover_mode: 値が必要です"),
    (f"{ROW1}/center_mm", None, "鉄筋.柱.main_rows[1].center_mm: 値が必要です"),
    (f"{ROW0}/layer", None, "鉄筋.柱.main_rows[0].layer: 値が必要です"),
    ("鉄筋/柱/pure_cover_mm", None, "鉄筋.柱.pure_cover_mm: 値が必要です"),
    ("鉄筋/柱/column_hoops/enclosing_diameter_mm", None, "鉄筋.柱.column_hoops.enclosing_diameter_mm: 値が必要です"),
    (f"{ROW0}/distribution/mode", None, "鉄筋.柱.main_rows[0].distribution.mode: 値が必要です"),
    (f"{ROW0}/distribution/edge_center_mm", None, "鉄筋.柱.main_rows[0].distribution.edge_center_mm: 値が必要です"),
    (f"{ROW0}/distribution/pitch_mm", None, "鉄筋.柱.main_rows[0].distribution.pitch_mm: 値が必要です"),
    (f"{ROW1}/distribution/pitch_mm", None, "鉄筋.柱.main_rows[1].distribution.pitch_mm: 値が必要です"),
    ("鉄筋/柱/materials/main", None, "鉄筋.柱.main_rows[0].material: 値が必要です（行と鉄筋.柱.materials.main が空欄）"),
])
def test_missing_values_are_errors_not_defaults(path, value, message):
    fails(message, **{path: value})


def test_equal_division_needs_the_endpoint_rule():
    fails("鉄筋.柱.main_rows[0].endpoints: 値が必要です",
          **{f"{ROW0}/distribution/mode": "等分", f"{ROW0}/endpoints": None})


def test_a_row_material_overrides_the_shared_material():
    result = layout(**{"鉄筋/柱/materials/main": None, f"{ROW0}/material": "SD345", f"{ROW1}/material": "SD345"})
    assert {bar.material for bar in result.bars} == {"SD345"}


@pytest.mark.parametrize("changes,message", [
    ({f"{ROW1}/distribution/pitch_mm": 340},
     "鉄筋.柱.main_rows[1].distribution.pitch_mm: 中央ピッチの配置幅（(本数−1)×ピッチ）が面内寸法に収まりません"),
    ({f"{ROW0}/distribution/pitch_mm": 170},  # (4500 − 26 × 170) / 2 = 40 < 108
     "鉄筋.柱.main_rows[0].distribution.pitch_mm: 内部の鉄筋が両端の鉄筋の間に収まりません"),
    ({f"{ROW0}/distribution/edge_center_mm": 2250},
     "鉄筋.柱.main_rows[0].distribution.edge_center_mm: 両端の芯位置が面内寸法の半分以上です"),
    ({f"{ROW0}/distribution/edge_center_mm": 15},
     "鉄筋.柱.main_rows[0].distribution.edge_center_mm: 鉄筋の半径より小さく、鉄筋が断面の外に出ます"),
    ({f"{ROW1}/center_mm": 2250}, "鉄筋.柱.main_rows[1]: 芯かぶり 2250 mm が断面の半分以上です"),
    ({"鉄筋/柱/pure_cover_mm": 1400}, "鉄筋.柱.main_rows[0]: 芯かぶり 1438 mm が断面の半分以上です"),
    ({f"{ROW1}/center_mm": 9}, "鉄筋.柱.main_rows[1]: 芯かぶり 9 mm が鉄筋の半径より小さく"),
])
def test_bounds_of_the_basic_layout(changes, message):
    fails(message, **changes)


def test_centre_pitch_may_reach_the_bar_radius():
    # 9 bars at 340: (2700 − 8 × 340) / 2 = −10 < 9.5 fails; at 335 the first bar is at 10.
    assert layout(**{f"{ROW1}/distribution/pitch_mm": 335}).rows[1].positions[0] == mm(10)


MANUAL = "鉄筋/柱"


def manual_document(bars=None, basis=True, **changes):
    data = document(**changes)
    column = data["鉄筋"]["柱"]
    auto = column_layout(parse_input(document()))
    column["position_mode"] = "指定"
    column["manual_positions"] = bars if bars is not None else [
        {"x_mm": bar.x.value, "y_mm": bar.y.value, "diameter_mm": bar.diameter.value, "material": bar.material}
        for bar in auto.bars]
    if basis:
        source = document()["鉄筋"]["柱"]
        column["manual_basis"] = {"generator_version": 1, "geometry": {"width_mm": 4500, "height_mm": 2700},
                                  "inputs": {key: deepcopy(source[key]) for key in
                                             ("main_rows", "materials", "pure_cover_mm", "column_hoops")}}
    return data


def test_detail_positions_from_the_current_basis():
    result = column_layout(parse_input(manual_document()))
    assert result.manual is not None and result.bars is result.manual
    assert physical(result.manual) == physical(result.automatic)
    assert all(bar.rows == () for bar in result.manual)
    assert result.manual_basis_current is True


def test_detail_positions_without_or_with_a_changed_basis():
    assert column_layout(parse_input(manual_document(basis=False))).manual_basis_current is False
    changed = manual_document(**{f"{ROW1}/distribution/pitch_mm": 240})
    assert column_layout(parse_input(changed)).manual_basis_current is False
    assert layout().manual_basis_current is False


def test_moved_detail_positions_are_kept():
    data = manual_document()
    data["鉄筋"]["柱"]["manual_positions"][0]["x_mm"] = 120
    result = column_layout(parse_input(data))
    assert physical(result.manual) != physical(result.automatic)
    assert rows_of(table(result.bars, "線路"))[0]["count"] == 29


@pytest.mark.parametrize("bar,message", [
    ({"x_mm": None, "y_mm": 500, "diameter_mm": 19, "material": "SD390"},
     "鉄筋.柱.manual_positions[0].x_mm: 値が必要です"),
    ({"x_mm": 500, "y_mm": 500, "diameter_mm": 19, "material": None},
     "鉄筋.柱.manual_positions[0].material: 値が必要です"),
    ({"x_mm": 5, "y_mm": 500, "diameter_mm": 19, "material": "SD390"},
     "鉄筋.柱.manual_positions[0]: 鉄筋が断面の外に配置されます"),
    ({"x_mm": 500, "y_mm": 2695, "diameter_mm": 19, "material": "SD390"},
     "鉄筋.柱.manual_positions[0]: 鉄筋が断面の外に配置されます"),
])
def test_detail_position_values(bar, message):
    with pytest.raises(InputError, match=re.escape(message)):
        column_layout(parse_input(manual_document([bar])))


def test_detail_positions_must_not_coincide_or_overlap():
    bar = {"x_mm": 500, "y_mm": 500, "diameter_mm": 19, "material": "SD390"}
    with pytest.raises(InputError, match=re.escape("鉄筋.柱.manual_positions[1]: 同じ位置の鉄筋が重複しています")):
        column_layout(parse_input(manual_document([bar, dict(bar)])))
    with pytest.raises(InputError, match=re.escape("鉄筋.柱.manual_positions[0]・[1]: 鉄筋が重なっています")):
        column_layout(parse_input(manual_document([bar, bar | {"x_mm": 510}])))


def test_direction_tables_group_by_centre_diameter_and_material():
    bars = layout(**{f"{ROW1}/material": "SD345"}).bars
    cross = table(bars, "直角")
    assert (cross[0].center, cross[0].count, cross[0].material) == (mm(102), 9, "SD345")
    assert [row.center.value for row in cross] == sorted(row.center.value for row in cross)


def test_yield_strength_is_the_grade_number():
    assert yield_strength("SD390") == Printed(390, 0, "N/mm2")
    assert yield_strength("SD295").value == 295
