"""0910: what Capacita is given to check the beam (decision 59): the section, the bars of 鉄筋.梁, the conditions,
the fatigue trains, the safety factors, the section forces of 0900, and the inputs the WDJ cannot hold."""

from __future__ import annotations

import re

import pytest

from cantilever_support import SAMPLE, D, document, q, result_of, value
from webpier.calc.cantilever import Quantity
from webpier.calc.cantilever.check import (GAMMA1_MAIN, GAMMA1_STIRRUP, SA_RATIO, SB_RATIO, SECTIONS,
                                           calculate_cantilever_section)
from webpier.calc.column_check import SAFETY_FACTORS, JR_EAST_SAFETY_FACTORS
from webpier.core.errors import InputError
from webpier.inputs import parse_input

BEAM = "鉄筋/梁"
CHECK = "片持ち梁の照査"


@pytest.fixture(scope="module")
def current():
    pier, _, result = result_of()
    return pier, result, calculate_cantilever_section(pier, result)


def section_of(**changes):
    pier, _, result = result_of(**changes)
    return calculate_cantilever_section(pier, result)


def test_the_section_and_the_shear_span(current):
    _, result, section = current
    assert (section.width.value, section.depth.value) == (2700, 2700)  # B1, H2 + H3 in mm
    assert section.shear_span.value == 1.55 and section.shear_span.unit == "m"  # the farthest cantilever bearing
    assert section.fck.value == 27.0 and section.aggregate_max.value == 25.0
    assert section.cracking is result.cracking and section.ecsd.value == 300
    assert section.selections == result.selections
    assert section.selection(5, Quantity.TORSION) is result.selection(5, Quantity.TORSION)


def test_the_bars_of_the_beam(current):
    _, _, section = current
    expected = SAMPLE["wdj"]["bar"]
    upper, lower = section.upper, section.lower
    assert (upper.diameter.value, upper.count, upper.per_layer, upper.layers) == (32, 25, 17, 2)
    assert (upper.cover.value, upper.layer_spacing.value) == (108.0, 64.0)  # 172 − 108
    assert upper.spacing.value == 145.8  # (2700 − 2 × 184) / 16 = 145.75 at 1 decimal
    assert value(upper.spacing) == q((D(2700) - 2 * D(184)) / 16, 1)
    assert (lower.diameter.value, lower.count, lower.per_layer, lower.layers, lower.cover.value) == (
        expected["rebar2"]["rebar_dia"], expected["rebar2"]["rebar_n"], 18, 1, expected["rebar2"]["rebar_cover"])
    assert lower.layer_spacing is None and value(lower.spacing) == q((D(2700) - 2 * D(184)) / 17, 1)
    side = section.side
    assert (side.diameter.value, side.count, side.first.value, side.spacing.value) == (
        expected["sidebar1"]["side_dia"], expected["sidebar1"]["side_n"], expected["sidebar1"]["side_cover"],
        expected["sidebar1"]["side_ss"])
    assert (section.stirrups.diameter.value, section.stirrups.legs, section.stirrups.pitch.value) == (
        expected["stirrup"]["stirrup_dia"], expected["stirrup"]["stirrup_n"], expected["stirrup"]["stirrup_ss"])
    assert (section.main_steel.grade, section.main_steel.fsy.value, section.main_steel.fsu.value) == ("SD390", 390, 560)
    assert section.side_steel.grade == "SD390" and section.stirrup_steel.grade == "SD390"


def test_the_conditions_of_the_check(current):
    _, _, section = current
    assert section.environments == {"上面": "腐食性環境", "下面": "一般の環境", "側面": "腐食性環境"}
    assert section.environment_numbers == {"上面": 2, "下面": 1, "側面": 2}
    assert section.appearance is False
    assert (section.body, section.jr001, section.jr004) == ("運輸機構", True, False)
    assert section.safety == SAFETY_FACTORS and [factors.id for factors in section.safety] == [0, 2, 5, 6, 7, 8]
    fatigue = next(factors for factors in section.safety if factors.id == 2)
    assert (fatigue.m_rs.value, fatigue.ri.value, fatigue.t_rbt.value) == (1.05, 1.1, 1.0)
    assert all(factors.t_rbt is not None and factors.t_rbt.value == 1.0 for factors in section.safety if factors.id != 8)
    assert (section.kr.value, section.k4.value) == (0.5, 0.85)


def test_the_fatigue_trains(current):
    _, _, section = current
    fatigue = section.fatigue
    assert (fatigue.passenger_trains, fatigue.freight_trains, fatigue.service_life) == (60, 0, 100)
    assert [item.value for item in (fatigue.na06, fatigue.na12, fatigue.nb06, fatigue.nb12)] == [10.39] * 4
    assert (fatigue.sa_ratio, fatigue.sb_ratio, fatigue.gamma1_main, fatigue.gamma1_stirrup) == (
        SA_RATIO, SB_RATIO, GAMMA1_MAIN, GAMMA1_STIRRUP)
    assert (SA_RATIO.value, SB_RATIO.value, GAMMA1_MAIN.value, GAMMA1_STIRRUP.value) == (1.0, 1.0, 1.0, 0.65)


def test_the_sections_capacita_is_asked_for(current):
    _, _, section = current
    assert section.sections == tuple(name for name in SECTIONS if name != "bending_serviceability")
    assert len(section.sections) == 14 and "torsion_restorability_eq" in section.sections
    with_appearance = section_of(**{f"{CHECK}/外観の照査": "行う"})
    assert with_appearance.sections == SECTIONS and with_appearance.appearance is True
    assert SECTIONS.index("bending_serviceability") == 8  # Capacita's report order


def test_jr_east_takes_its_own_safety_factors():
    section = section_of(**{"柱の断面照査/適用基準の機関": "JR東日本"})
    assert section.body == "JR東日本" and section.safety == JR_EAST_SAFETY_FACTORS


def test_an_automatic_cover_from_the_pure_cover_and_the_stirrup():
    changes = {f"{BEAM}/pure_cover_mm": 70, f"{BEAM}/main_rows/0/cover_mode": "自動", f"{BEAM}/main_rows/0/center_mm": None,
               f"{BEAM}/main_rows/1/cover_mode": "自動", f"{BEAM}/main_rows/1/center_mm": None,
               f"{BEAM}/main_rows/1/clear_gap_mm": 32}
    section = section_of(**changes)
    assert section.upper.cover.value == 108.0  # 70 + 22 + 32/2
    assert section.upper.layer_spacing.value == 64.0  # 108 + 32 + 32 = 172


def test_without_side_rows_the_spacing_is_measured_from_the_cover():
    section = section_of(**{f"{BEAM}/side_rows": []})
    assert section.side is None and section.side_steel is None
    assert value(section.upper.spacing) == q((D(2700) - 2 * D(108)) / 16, 1)
    automatic = section_of(**{f"{BEAM}/side_rows/0/cover_mode": "自動", f"{BEAM}/side_rows/0/center_mm": None})
    assert value(automatic.upper.spacing) == q((D(2700) - 2 * D(108)) / 16, 1)
    one = section_of(**{f"{BEAM}/side_rows/0/per_face_count": 1})
    assert one.side.count == 1 and one.side.spacing is None


def test_a_row_material_overrides_the_shared_one():
    section = section_of(**{f"{BEAM}/main_rows/0/material": "SD345", f"{BEAM}/main_rows/1/material": "SD345",
                            f"{BEAM}/main_rows/2/material": "SD345", f"{BEAM}/side_rows/0/material": "SD295",
                            f"{BEAM}/band_rows/0/material": "SD345"})
    assert (section.main_steel.grade, section.side_steel.grade, section.stirrup_steel.grade) == ("SD345", "SD295", "SD345")


@pytest.mark.parametrize("changes,message", [
    ({f"{BEAM}/main_rows/1/layer": 3}, "鉄筋.梁.main_rows: 面「上」の段は 1 から順に1行ずつ必要です（1・3）"),
    ({f"{BEAM}/main_rows/1/layer": None}, "鉄筋.梁.main_rows[1].layer: 値が必要です"),
    ({f"{BEAM}/main_rows/1/diameter_mm": 29}, "鉄筋.梁.main_rows: 面「上」の主鉄筋の径が1種類ではありません"),
    ({f"{BEAM}/main_rows/0/diameter_mm": None}, "鉄筋.梁.main_rows[0].diameter_mm: 値が必要です"),
    ({f"{BEAM}/main_rows/1/material": "SD345"}, "鉄筋.梁.main_rows: 面「上」の主鉄筋の材質が1種類ではありません"),
    ({f"{BEAM}/materials/main": None, f"{BEAM}/side_rows/0/material": "SD390"},
     "鉄筋.梁.main_rows: 面「上」の主鉄筋の材質が必要です（行と鉄筋.梁.materials.main が空欄）"),
    ({f"{BEAM}/main_rows/0/count": None}, "鉄筋.梁.main_rows[0].count: 値が必要です"),
    ({f"{BEAM}/main_rows/0/cover_mode": None}, "鉄筋.梁.main_rows[0].cover_mode: 値が必要です"),
    ({f"{BEAM}/main_rows/0/center_mm": None}, "鉄筋.梁.main_rows[0].center_mm: 値が必要です"),
    ({f"{BEAM}/main_rows/0/cover_mode": "自動", f"{BEAM}/main_rows/0/center_mm": None},
     "鉄筋.梁.pure_cover_mm: 値が必要です"),
    ({f"{BEAM}/main_rows/1/cover_mode": "自動", f"{BEAM}/main_rows/1/center_mm": None},
     "鉄筋.梁.main_rows[1].clear_gap_mm: 値が必要です"),
    ({f"{BEAM}/main_rows/0/count": 1}, "鉄筋.梁.main_rows: 面「上」の1段目は2本以上が必要です"),
    ({f"{BEAM}/main_rows/2/material": "SD345"}, "鉄筋.梁.main_rows: 主鉄筋の材質が1種類ではありません（SD345・SD390）"),
    ({f"{BEAM}/side_rows/0/material": None, f"{BEAM}/materials/main": None, f"{BEAM}/main_rows/0/material": "SD390",
      f"{BEAM}/main_rows/1/material": "SD390", f"{BEAM}/main_rows/2/material": "SD390"},
     "鉄筋.梁.side_rows[0].material: 値が必要です（行と鉄筋.梁.materials.main が空欄）"),
    ({f"{BEAM}/side_rows/0/columns": 2}, "鉄筋.梁.side_rows[0].columns: 側面筋は1列だけ表せます（2列）"),
    ({f"{BEAM}/side_rows/0/per_face_count": None}, "鉄筋.梁.side_rows[0].per_face_count: 値が必要です"),
    ({f"{BEAM}/side_rows/0/start_mm": None}, "鉄筋.梁.side_rows[0].start_mm: 値が必要です"),
    ({f"{BEAM}/band_rows/0/material": None, f"{BEAM}/materials/transverse": None},
     "鉄筋.梁.band_rows[0].material: 値が必要です（行と鉄筋.梁.materials.transverse が空欄）"),
    ({f"{BEAM}/band_rows/0/legs_mode": "自動"}, "鉄筋.梁.band_rows[0].legs_mode: 有効本数は「指定」で入力してください"),
    ({f"{BEAM}/band_rows/0/effective_legs": None}, "鉄筋.梁.band_rows[0].effective_legs: 値が必要です"),
    ({f"{CHECK}/鋼材の腐食に対する環境条件/側面": None}, "片持ち梁の照査.鋼材の腐食に対する環境条件.側面: 値が必要です"),
    ({f"{CHECK}/外観の照査": None}, "片持ち梁の照査.外観の照査: 値が必要です"),
    ({"柱の断面照査/適用基準の機関": None}, "柱の断面照査.適用基準の機関: 値が必要です"),
    ({"柱の断面照査/JR-001": None}, "柱の断面照査.JR-001: 値が必要です"),
    ({"柱の断面照査/JR-004": None}, "柱の断面照査.JR-004: 値が必要です"),
    ({f"{CHECK}/疲労/旅客列車本数": None}, "片持ち梁の照査.疲労.旅客列車本数: 値が必要です"),
    ({f"{CHECK}/疲労/等価繰返し回数/B列車/k=0.12": None}, "片持ち梁の照査.疲労.等価繰返し回数.B列車.k=0.12: 値が必要です"),
])
def test_what_the_wdj_cannot_hold_is_an_input_error(changes, message):
    with pytest.raises(InputError, match=re.escape(message)):
        section_of(**changes)


def test_a_face_without_a_row_is_an_input_error():
    rows = document()["鉄筋"]["梁"]["main_rows"]
    with pytest.raises(InputError, match=re.escape("鉄筋.梁.main_rows: 面「下」の主鉄筋の行が必要です")):
        section_of(**{f"{BEAM}/main_rows": rows[:2]})


def test_the_layers_must_be_equally_spaced():
    rows = document()["鉄筋"]["梁"]["main_rows"]
    third = dict(rows[1], layer=3, center_mm=300)
    with pytest.raises(InputError, match=re.escape("鉄筋.梁.main_rows: 面「上」の段の間隔が一定ではないため表せません")):
        pier = parse_input(document(**{f"{BEAM}/main_rows": [rows[0], rows[1], third, rows[2]]}))
        _, _, result = result_of(pier)
        calculate_cantilever_section(pier, result)


@pytest.mark.parametrize("rows,message", [
    ([], "鉄筋.梁.band_rows: スターラップの行がちょうど1行必要です（0行）"),
    (2, "鉄筋.梁.band_rows: スターラップの行がちょうど1行必要です（2行）"),
])
def test_exactly_one_stirrup_row(rows, message):
    band = document()["鉄筋"]["梁"]["band_rows"][0]
    with pytest.raises(InputError, match=re.escape(message)):
        section_of(**{f"{BEAM}/band_rows": rows if isinstance(rows, list) else [band, band]})


def test_at_most_one_side_row():
    side = document()["鉄筋"]["梁"]["side_rows"][0]
    with pytest.raises(InputError, match=re.escape("鉄筋.梁.side_rows: 側面筋は1行だけ表せます（2行）")):
        section_of(**{f"{BEAM}/side_rows": [side, side]})


def test_the_beam_aggregate_size_is_the_beam_concretes(current):
    _, _, section = current
    assert section.aggregate_max.value == 25.0 and section.cracking.cracking_moment.aggregate_max == section.aggregate_max
