"""Column main bar layout (CONTEXT.md 柱の配筋): positions from the main bars and the layers inside them, the
direction tables and their changes (decision 68).

Expected values: tests/fixtures/column_rebar_example2.json (independent transcription of Example2 10-6 / 11-6,
both tables and the 76 physical bars) and hand calculations in Decimal. Nothing missing is filled in (decision 5).
"""

import json
import re
from decimal import Decimal

import pytest

from reaction_support import FIXTURES, document, q
from webpier.calc.column_rebar import column_layout, table, yield_strength
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import parse_input

EXAMPLE = json.loads((FIXTURES / "column_rebar_example2.json").read_text(encoding="utf-8"))
RAIL, CROSS, CHANGES = "鉄筋/柱/main_bars/線路", "鉄筋/柱/main_bars/直角", "鉄筋/柱/table_overrides"


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
    assert result.bars == result.generated and result.unmatched == ()


def test_face_rows_by_hand():
    first, second = layout().rows
    # D32, cover automatic: 純かぶり 70 + enclosing hoop 22 + 32/2 = 108 (主鉄筋の芯かぶり).
    assert (first.key, first.center, first.material) == (("線路", 1), mm(108), "SD390")
    # Edge bars at 108 / 4500 − 108; 27 interior bars at 150 centred: (4500 − 26 × 150) / 2 = 300.
    assert [p.value for p in first.positions] == [108, *range(300, 4201, 150), 4392]
    assert first.pitch == mm(150)
    # D19 given at 102; 9 bars at 250 centred on 2700: (2700 − 8 × 250) / 2 = 350.
    assert (second.key, second.center) == (("直角", 1), mm(102))
    assert [p.value for p in second.positions] == list(range(350, 2351, 250)) and second.pitch == mm(250)


def test_bar_rows_record_the_layer():
    bars = layout().bars
    assert {bar.rows for bar in bars if bar.diameter.value == 32} == {(("線路", 1),)}
    assert {bar.rows for bar in bars if bar.diameter.value == 19} == {(("直角", 1),)}


@pytest.mark.parametrize("endpoints,count,expected,pitch", [
    ("含む", 5, ["108", "1179", "2250", "3321", "4392"], "1071"),  # (4500 − 2 × 108) / 4
    ("含めない", 5, ["822", "1536", "2250", "2964", "3678"], "714"),  # (4500 − 216) / 6, from the edge + 1 step
])
def test_equal_division(endpoints, count, expected, pitch):
    row = layout(**{f"{RAIL}/distribution/mode": "等分", f"{RAIL}/endpoints": endpoints,
                    f"{RAIL}/per_face_count": count}).rows[0]
    assert [p.value for p in row.positions] == [float(value) for value in expected]
    assert row.pitch == mm(pitch)


def test_equal_division_rounds_each_position_to_the_printed_digits():
    row = layout(**{f"{RAIL}/distribution/mode": "等分", f"{RAIL}/distribution/edge_center_mm": 100,
                    f"{RAIL}/per_face_count": 4}).rows[0]
    spacing = Decimal(4300) / 3
    assert [p.value for p in row.positions] == [float(q(100 + i * spacing, 1)) for i in range(4)]
    assert row.positions[1] == mm("1533.3") and row.pitch == mm("1433.3")


def test_one_bar_sits_at_the_middle_of_the_face():
    row = layout(**{f"{CROSS}/per_face_count": 1}).rows[1]
    assert row.positions == (mm(1350),) and row.pitch is None


def test_two_edge_bars_have_no_pitch():
    row = layout(**{f"{RAIL}/per_face_count": 2}).rows[0]
    assert row.positions == (mm(108), mm(4392)) and row.pitch is None


def test_a_layer_inside_takes_the_middle_of_the_first():
    result = layout(**{f"{RAIL}/inner_layers": [{"per_face_count": 27, "clear_gap_mm": 40}]})
    inner = result.rows[1]
    # 108 + 32 + 40 = 180 from each 線路 face; the 27 middle bars of layer 1 (its 27 interior bars at 150).
    assert (inner.key, inner.center, inner.diameter) == (("線路", 2), mm(180), Printed(32, 0, "mm"))
    assert [p.value for p in inner.positions] == list(range(300, 4201, 150)) and inner.pitch == mm(150)
    rail = rows_of(table(result.bars, "線路"))
    assert {"center_mm": 180, "diameter_mm": 32, "count": 27, "material": "SD390"} in rail
    assert {"center_mm": 2520, "diameter_mm": 32, "count": 27, "material": "SD390"} in rail
    assert len(result.bars) == 76 + 2 * 27


def test_an_odd_rest_leaves_the_far_end_bar_out():
    inner = layout(**{f"{RAIL}/inner_layers": [{"per_face_count": 28, "clear_gap_mm": 40}]}).rows[1]
    # 29 − 28 = 1 left over: the first 28 of layer 1, from the edge bar at 108 to 4200; gaps 192 and 150, no pitch.
    assert (inner.positions[0], inner.positions[-1], inner.pitch) == (mm(108), mm(4200), None)


def test_a_layer_inside_needs_its_gap_and_bars_of_the_first():
    fails("鉄筋.柱.main_bars.線路.inner_layers[0].clear_gap_mm: 値が必要です",
          **{f"{RAIL}/inner_layers": [{"per_face_count": 27, "clear_gap_mm": None}]})
    fails("鉄筋.柱.main_bars.線路.inner_layers[0].per_face_count: 1段目の29本より多くできません",
          **{f"{RAIL}/inner_layers": [{"per_face_count": 30, "clear_gap_mm": 40}]})
    fails("鉄筋.柱.main_bars.線路.inner_layers: 1段目に鉄筋がありません",
          **{f"{RAIL}/per_face_count": 0, f"{RAIL}/inner_layers": [{"per_face_count": 3, "clear_gap_mm": 40}]})


def test_shared_corner_bars_count_once():
    # 直角 D32 bars at the 108 corners coincide with the 線路 corner bars: one physical bar for both rows.
    result = layout(**{f"{CROSS}/diameter_mm": 32, f"{CROSS}/center_mm": 108, f"{CROSS}/per_face_count": 2,
                       f"{CROSS}/distribution/mode": "両端＋中央ピッチ", f"{CROSS}/distribution/edge_center_mm": 108})
    assert len(result.bars) == 58
    corners = [bar for bar in result.bars if bar.rows == (("線路", 1), ("直角", 1))]
    assert sorted((b.x.value, b.y.value) for b in corners) == [(108, 108), (108, 2592), (4392, 108), (4392, 2592)]


def test_bars_at_one_position_must_be_the_same_bar():
    shared = {f"{CROSS}/center_mm": 108, f"{CROSS}/per_face_count": 2, f"{CROSS}/distribution/mode": "両端＋中央ピッチ",
              f"{CROSS}/distribution/edge_center_mm": 108}
    fails("鉄筋.柱.main_bars.直角: 直角1段目の鉄筋と同じ位置に線路1段目の径の異なる鉄筋があります", **shared)


def test_overlapping_bars_are_rejected():
    # 直角 D19 at (108, 110) against the 線路 D32 corner (108, 108): 2 mm apart, 25.5 mm needed.
    fails("鉄筋.柱.main_bars: 直角1段目・線路1段目の鉄筋が重なっています（X 108・Y 110）",
          **{f"{CROSS}/center_mm": 108, f"{CROSS}/distribution/pitch_mm": 310})


def test_touching_bars_are_allowed():
    # (2700 − 2 × p) / 2 = 108 + 25.5 puts the first 直角 D19 at (32 + 19) / 2 = 25.5 from the D32 corner bar.
    result = layout(**{f"{CROSS}/center_mm": 108, f"{CROSS}/per_face_count": 3,
                       f"{CROSS}/distribution/pitch_mm": 1216.5})
    assert [p.value for p in result.rows[1].positions] == [133.5, 1350, 2566.5]


def test_an_inactive_row_places_nothing():
    result = layout(**{f"{CROSS}/per_face_count": 0, f"{CROSS}/diameter_mm": None})
    assert len(result.rows) == 1 and len(result.bars) == 58


@pytest.mark.parametrize("path,value,message", [
    (f"{RAIL}/per_face_count", None, "鉄筋.柱.main_bars.線路.per_face_count: 値が必要です"),
    (f"{RAIL}/diameter_mm", None, "鉄筋.柱.main_bars.線路.diameter_mm: 値が必要です"),
    (f"{RAIL}/cover_mode", None, "鉄筋.柱.main_bars.線路.cover_mode: 値が必要です"),
    (f"{CROSS}/center_mm", None, "鉄筋.柱.main_bars.直角.center_mm: 値が必要です"),
    ("鉄筋/柱/pure_cover_mm", None, "鉄筋.柱.pure_cover_mm: 値が必要です"),
    ("鉄筋/柱/column_hoops/enclosing_diameter_mm", None, "鉄筋.柱.column_hoops.enclosing_diameter_mm: 値が必要です"),
    (f"{RAIL}/distribution/mode", None, "鉄筋.柱.main_bars.線路.distribution.mode: 値が必要です"),
    (f"{RAIL}/distribution/edge_center_mm", None, "鉄筋.柱.main_bars.線路.distribution.edge_center_mm: 値が必要です"),
    (f"{RAIL}/distribution/pitch_mm", None, "鉄筋.柱.main_bars.線路.distribution.pitch_mm: 値が必要です"),
    (f"{CROSS}/distribution/pitch_mm", None, "鉄筋.柱.main_bars.直角.distribution.pitch_mm: 値が必要です"),
    ("鉄筋/柱/materials/main", None, "鉄筋.柱.materials.main: 値が必要です"),
])
def test_missing_values_are_errors_not_defaults(path, value, message):
    fails(message, **{path: value})


def test_equal_division_needs_the_endpoint_rule():
    fails("鉄筋.柱.main_bars.線路.endpoints: 値が必要です",
          **{f"{RAIL}/distribution/mode": "等分", f"{RAIL}/endpoints": None})


@pytest.mark.parametrize("changes,message", [
    ({f"{CROSS}/distribution/pitch_mm": 340},
     "鉄筋.柱.main_bars.直角.distribution.pitch_mm: 中央ピッチの配置幅（(本数−1)×ピッチ）が面内寸法に収まりません"),
    ({f"{RAIL}/distribution/pitch_mm": 170},  # (4500 − 26 × 170) / 2 = 40 < 108
     "鉄筋.柱.main_bars.線路.distribution.pitch_mm: 内部の鉄筋が両端の鉄筋の間に収まりません"),
    ({f"{RAIL}/distribution/edge_center_mm": 2250},
     "鉄筋.柱.main_bars.線路.distribution.edge_center_mm: 両端の芯位置が面内寸法の半分以上です"),
    ({f"{RAIL}/distribution/edge_center_mm": 15},
     "鉄筋.柱.main_bars.線路.distribution.edge_center_mm: 鉄筋の半径より小さく、鉄筋が断面の外に出ます"),
    ({f"{CROSS}/center_mm": 2250}, "鉄筋.柱.main_bars.直角: 芯かぶり 2250 mm が断面の半分以上です"),
    ({"鉄筋/柱/pure_cover_mm": 1400}, "鉄筋.柱.main_bars.線路: 芯かぶり 1438 mm が断面の半分以上です"),
    ({f"{CROSS}/center_mm": 9}, "鉄筋.柱.main_bars.直角: 芯かぶり 9 mm が鉄筋の半径より小さく"),
])
def test_bounds_of_the_basic_layout(changes, message):
    fails(message, **changes)


def test_centre_pitch_may_reach_the_bar_radius():
    # 9 bars at 340: (2700 − 8 × 340) / 2 = −10 < 9.5 fails; at 335 the first bar is at 10.
    assert layout(**{f"{CROSS}/distribution/pitch_mm": 335}).rows[1].positions[0] == mm(10)


def change(direction, source, diameter, center=None, size=None):
    return {f"{CHANGES}/{direction}": [{"source_center_mm": source, "source_diameter_mm": diameter,
                                        "center_mm": center, "diameter_mm": size}]}


def test_a_table_change_resizes_the_bars_of_a_row():
    result = layout(**{f"{RAIL}/inner_layers": [{"per_face_count": 27, "clear_gap_mm": 40}]},
                    **change("線路", 180, 32, size=29))
    rail = rows_of(table(result.bars, "線路"))
    assert {"center_mm": 180, "diameter_mm": 29, "count": 27, "material": "SD390"} in rail
    assert {"center_mm": 2520, "diameter_mm": 32, "count": 27, "material": "SD390"} in rail  # the other face: 2520
    moved = [bar for bar in result.bars if bar.diameter.value == 29]
    assert len(moved) == 27 and {bar.origin[2].value for bar in moved} == {32}
    assert result.unmatched == ()


def test_a_table_change_moves_the_bars_of_a_row():
    result = layout(**change("直角", 102, 19, center=110))
    cross = rows_of(table(result.bars, "直角"))
    assert {"center_mm": 110, "diameter_mm": 19, "count": 9, "material": "SD390"} in cross
    assert all(row["center_mm"] != 102 for row in cross)


def test_a_change_without_its_generated_bars_is_returned_not_applied():
    result = layout(**change("線路", 999, 32, center=110))
    assert result.unmatched == (("線路", 0),) and result.bars == result.generated


@pytest.mark.parametrize("changes,message", [
    ({f"{RAIL}/inner_layers": [{"per_face_count": 27, "clear_gap_mm": 40}], **change("線路", 180, 32, center=108)},
     "鉄筋.柱.table_overrides: X 300・Y 108 の鉄筋が配置表の変更でほかの鉄筋と同じ位置になります"),
    (change("直角", 102, 19, center=5), "鉄筋.柱.table_overrides: X 5・Y 350 の鉄筋が断面の外に出ます"),
])
def test_changed_bars_must_stay_apart_and_inside(changes, message):
    fails(message, **changes)


def test_direction_tables_group_by_centre_diameter_and_material():
    bars = layout(**{"鉄筋/柱/materials/main": "SD345"}).bars
    cross = table(bars, "直角")
    assert (cross[0].center, cross[0].count, cross[0].material) == (mm(102), 9, "SD345")
    assert [row.center.value for row in cross] == sorted(row.center.value for row in cross)


def test_yield_strength_is_the_grade_number():
    assert yield_strength("SD390") == Printed(390, 0, "N/mm2")
    assert yield_strength("SD295").value == 295
