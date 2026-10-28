"""Column main bar layout (CONTEXT.md 柱の配筋): positions from the main bars and the layers inside them, and the
direction tables in use, made from them or by hand (decisions 68, 111), and the bars the 配筋図 draws from the tables
(decision 116).

Expected values: tests/fixtures/column_rebar_example2.json (independent transcription of Example2 10-6 / 11-6,
both tables and the 76 physical bars) and hand calculations in Decimal. Nothing missing is filled in (decision 5).
"""

import json
from copy import deepcopy
import re
from decimal import Decimal

import pytest

from reaction_support import FIXTURES, document, q
from webpier.calc.column_rebar import (column_layout, count_mismatch, direction_table, table, table_bars,
                                      yield_strength)
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import parse_input

EXAMPLE = json.loads((FIXTURES / "column_rebar_example2.json").read_text(encoding="utf-8"))
RAIL, CROSS, TABLES = "鉄筋/柱/main_bars/線路", "鉄筋/柱/main_bars/直角", "鉄筋/柱/custom_tables"


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
    assert result.custom == {"線路": None, "直角": None} and not result.customized


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


def custom(direction, tension, *rows):
    return {f"{TABLES}/{direction}": {"tension_rows": tension, "rows": [
        {"center_mm": center, "diameter_mm": diameter, "count": count} for center, diameter, count in rows]}}


def test_the_table_the_main_bars_make_has_their_layers_first_and_last():
    # decision 111: an inner layer at 108 + 32 + 300 = 440, beyond the first 直角 side bar (350): the side bars follow
    # the main layers, and N is the number of the layers, not the rows down to the innermost one (decision 108's)
    result = layout(**{f"{RAIL}/inner_layers": [{"per_face_count": 27, "clear_gap_mm": 300}]})
    rail = direction_table(result, "線路")
    centres = [row.center.value for row in rail.rows]
    assert not rail.custom and rail.tension == 2
    assert centres[:3] == [108, 440, 350] and centres[-2:] == [2700 - 440, 2700 - 108]
    assert [row.count for row in (*rail.upper, *rail.lower)] == [29, 27, 27, 29]
    assert sorted(rail.rows, key=lambda row: row.center.value) == list(table(result.bars, "線路"))
    assert [row.center.value for row in rail.others] == sorted(centres[2:-2])


def test_a_hand_made_table_is_its_rows_as_written():
    rows = ((100, 32, 29), (345, 32, 7), (167, 32, 2), (2355, 32, 7), (2600, 32, 29))
    result = layout(**custom("線路", 2, *rows))
    rail = direction_table(result, "線路")
    assert rail.custom and rail.tension == 2 and result.customized
    assert [(row.center.value, row.diameter.value, row.count, row.material) for row in rail.rows] == [
        (*row, "SD390") for row in rows]
    assert [row.center.value for row in rail.upper] == [100, 345]  # as written, not by centre (167 is not one)
    assert [row.center.value for row in rail.lower] == [2355, 2600]
    assert [row.center.value for row in rail.others] == [167]
    assert result.bars == layout().bars  # the bars the main bars make do not change
    assert not direction_table(result, "直角").custom


@pytest.mark.parametrize("changes,message", [
    (custom("線路", None, (100, 32, 29), (2600, 32, 29)), "鉄筋.柱.custom_tables.線路.tension_rows: 値が必要です"),
    (custom("線路", 2, (100, 32, 29), (2600, 32, 29)),
     "鉄筋.柱.custom_tables.線路.tension_rows: 引張鉄筋の段数 2 の上下 4 行が表の2行より多くなります"),
    (custom("線路", 1, (100, None, 29), (2600, 32, 29)), "鉄筋.柱.custom_tables.線路.rows[0].diameter_mm: 値が必要です"),
    (custom("線路", 1, (100, 32, 29), (2600, 32, None)), "鉄筋.柱.custom_tables.線路.rows[1].count: 値が必要です"),
    (custom("線路", 1, (15, 32, 29), (2600, 32, 29)),  # the radius 16
     "鉄筋.柱.custom_tables.線路.rows[0].center_mm: 芯位置 15 mm の鉄筋が断面の外に出ます"),
    (custom("直角", 1, (102, 19, 9), (4491, 19, 9)),  # W6 4500 − 9 < 9.5
     "鉄筋.柱.custom_tables.直角.rows[1].center_mm: 芯位置 4491 mm の鉄筋が断面の外に出ます"),
    (custom("線路", 1, (100, 30, 29), (2600, 32, 29)), "鉄筋.柱.custom_tables.線路.rows[0].diameter_mm: D30 の公称断面積"),
])
def test_a_hand_made_table_needs_its_values_inside_the_section(changes, message):
    fails(message, **changes)


def test_the_bars_of_the_two_tables_are_compared_by_size():
    assert count_mismatch(layout()) is None
    rows = [(row.center.value, row.diameter.value, row.count) for row in direction_table(layout(), "線路").rows]
    assert count_mismatch(layout(**custom("線路", 1, *rows))) is None  # the same rows by hand
    rows[0] = (rows[0][0], 29, rows[0][2])
    assert count_mismatch(layout(**custom("線路", 1, *rows))) == "線路 D19 18本 D29 29本 D32 29本・直角 D19 18本 D32 58本"


def placed(result):
    return {(bar.x.value, bar.y.value, bar.diameter.value)
            for bar in table_bars(direction_table(result, "線路"), direction_table(result, "直角"))}


@pytest.mark.parametrize("changes", [{}, {f"{RAIL}/inner_layers": [{"per_face_count": 27, "clear_gap_mm": 300}]},
                                     {f"{CROSS}/inner_layers": [{"per_face_count": 3, "clear_gap_mm": 100}]}])
def test_the_tables_the_main_bars_make_put_their_bars_back(changes):
    """Decision 116: the tables made from the main bars (a layer inside of 線路 or of 直角) give the bars they were
    made from, the corners shared."""
    result = layout(**changes)
    assert placed(result) == {(bar.x.value, bar.y.value, bar.diameter.value) for bar in result.bars}


# hand-made, both directions (W6 4500 × B6 2700, D32): a 2段目 of one bar at Y 400 and 2300, a corner bar at X 291 /
# 4209 and Y 167 / 2533 (the rows of 2 of both tables), the side bars of 線路 on the faces X 150 and 4350
CORNERS = {**custom("線路", 2, (100, 32, 3), (400, 32, 1), (167, 32, 2), (600, 32, 2), (1350, 32, 2), (2100, 32, 2),
                    (2533, 32, 2), (2300, 32, 1), (2600, 32, 3)),
           **custom("直角", 1, (150, 32, 3), (291, 32, 2), (1000, 32, 2), (2250, 32, 4), (3500, 32, 2), (4209, 32, 2),
                    (4350, 32, 3))}


def test_the_bars_of_hand_made_tables_by_hand():
    """2段目 first: Y 400 takes the middle one of the seven 直角 rows (2250), Y 2300 too. Layer 1: Y 100 the middle 3
    of the seven (1000, 2250, 3500), Y 2600 too (2250 is then full); X 150 the middle 3 of the five 線路 rows left
    (167, 600, 1350, 2100, 2533: 600, 1350, 2100), X 4350 too. The rest: Y 167 the two ends of the rows left (291,
    4209), Y 2533 too. 18 bars, as both tables."""
    expected = {(x, y) for y in (100, 2600) for x in (1000, 2250, 3500)} | {(2250, 400), (2250, 2300)}
    expected |= {(x, y) for x in (150, 4350) for y in (600, 1350, 2100)}
    expected |= {(x, y) for x in (291, 4209) for y in (167, 2533)}
    assert placed(layout(**CORNERS)) == {(x, y, 32) for x, y in expected}


def test_a_row_takes_crossings_of_its_size_and_draws_what_it_can():
    """A crossing holds a bar of one size: the D19 rows of 線路 only cross the D19 rows of 直角. A row with more bars
    than crossings left takes them all (decision 116, the tables do not agree): 直角 X 291 has 4 bars for the two of
    Y 167 and 2533."""
    changes = deepcopy(CORNERS)
    rail = changes[f"{TABLES}/線路"]["rows"]
    rail[2]["diameter_mm"] = rail[6]["diameter_mm"] = 19  # Y 167 and 2533
    cross = changes[f"{TABLES}/直角"]["rows"]
    cross[1].update(diameter_mm=19, count=4)  # X 291
    cross[5]["diameter_mm"] = 22  # X 4209: no D22 row of 線路
    bars = placed(layout(**changes))
    assert {(x, y, size) for x, y, size in bars if size != 32} == {(291, 167, 19), (291, 2533, 19)}
    assert len(bars) == 16


def test_direction_tables_group_by_centre_diameter_and_material():
    bars = layout(**{"鉄筋/柱/materials/main": "SD345"}).bars
    cross = table(bars, "直角")
    assert (cross[0].center, cross[0].count, cross[0].material) == (mm(102), 9, "SD345")
    assert [row.center.value for row in cross] == sorted(row.center.value for row in cross)


def test_yield_strength_is_the_grade_number():
    assert yield_strength("SD390") == Printed(390, 0, "N/mm2")
    assert yield_strength("SD295").value == 295


def test_tables_that_cannot_be_made_have_no_count_warning():
    # two edge bars of 線路 only and 直角 from 60: the 線路 table the main bars make has a bar outside its layers
    result = layout(**{f"{RAIL}/per_face_count": 2, f"{CROSS}/endpoints": "含む",
                       f"{CROSS}/distribution": {"mode": "等分", "edge_center_mm": 60.0, "pitch_mm": None}})
    with pytest.raises(InputError):
        direction_table(result, "線路")
    assert count_mismatch(result) is None
