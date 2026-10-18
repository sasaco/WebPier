"""0611 柱の断面照査 (decision 48, ADR-0008): the conditions Capacita is given, from the input, the column layout and
0610.

The expected values are the independent transcription tests/fixtures/example2/column_section_check.json of the sample
08_線路/WebDan.wdj (its notes list the deliberate differences); nothing here is computed by the code under test. The
check point is the column bottom found from the roles of the frame, the bars come from the 方向別の鉄筋配置表 of the
bending direction (線路), the extraction cases from the 0610 extraction groups, and the safety factors, fsu, kr and k4
are named program constants. A layout the WDJ cannot express is an input error naming its path.
"""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.calc.column_check import K4, KR, SAFETY_FACTORS, calculate_column_check, tensile_strength
from webpier.calc.column_rebar import column_layout
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
SAMPLE = json.loads((FIXTURES / "example2" / "column_section_check.json").read_text(encoding="utf-8"))
MAIN = "鉄筋/柱/main_rows"
HOOPS = "鉄筋/柱/column_hoops/direction_rows"
CHECK = "柱の断面照査"
SAFETY_KEYS = ("M_rc", "M_rs", "M_rbs", "V_rc", "V_rs", "V_rbc", "V_rbs", "V_rbv", "T_rbt", "ri")


def document(**changes):
    """current.json with each 'a/b/0/c' path replaced by its value."""
    data = deepcopy(CURRENT)
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value
    return data


def check(data=None, **changes):
    pier = parse_input(data if data is not None else document(**changes))
    reaction = calculate_reaction(pier)
    return calculate_column_check(pier, calculate_longitudinal(pier, calculate_foundation(pier), reaction))


def fails(message, data=None, **changes):
    with pytest.raises(InputError, match=re.escape(message)):
        check(data, **changes)


@pytest.fixture(scope="module")
def example():
    return check()


def test_the_check_point_is_the_bottom_of_the_column(example):
    point = SAMPLE["check_point"]
    assert example.member == point["member"]
    assert example.length == Printed(point["position_m"], 3, "m")


def test_the_section_is_b_across_and_h_in_the_plane_of_bending(example):
    member = SAMPLE["member"]
    assert (example.width, example.depth) == (Printed(member["B"], 1, "mm"), Printed(member["H"], 1, "mm"))


@pytest.mark.parametrize("face,key", [("upper", "rebar1"), ("lower", "rebar2")])
def test_the_main_bars_of_each_face(example, face, key):
    bars, sample = getattr(example, face), SAMPLE["bar"][key]
    assert (bars.diameter.value, bars.count, bars.per_layer, bars.layers) == (
        sample["rebar_dia"], sample["rebar_n"], sample["rebar_n"], 1)
    assert (bars.cover.value, bars.spacing.value, bars.layer_spacing) == (sample["rebar_cover"], sample["rebar_ss"],
                                                                           None)


def test_the_side_bars(example):
    side, sample = example.side, SAMPLE["bar"]["sidebar1"]
    assert (side.diameter.value, side.count, side.first.value, side.spacing.value) == (
        sample["side_dia"], sample["side_n"], sample["side_cover"], sample["side_ss"])


def test_the_hoops_of_the_bending_direction(example):
    hoops, sample = example.hoops, SAMPLE["bar"]["stirrup"]
    assert (hoops.diameter.value, hoops.legs, hoops.pitch.value) == (
        sample["stirrup_dia"], sample["stirrup_n"], sample["stirrup_ss"])


def test_the_steels_and_the_concrete(example):
    steel = SAMPLE["material_bar"]
    for grade in (example.main_steel, example.side_steel, example.hoop_steel):
        assert grade.grade == steel["grade"]
        assert (grade.fsy.value, grade.fsu.value) == (steel["tensionBar"]["fsy"], steel["tensionBar"]["fsu"])
    concrete = SAMPLE["material_concrete"]
    assert (example.fck, example.aggregate_max) == (Printed(concrete["fck"], 1, "N/mm2"),
                                                    Printed(concrete["dmax"], 1, "mm"))


def test_the_tensile_strength_of_each_grade():
    """JIS G 3112 (the lower limits of the tensile strength), as Capacita's grade presets."""
    assert [tensile_strength(grade).value for grade in ("SD295", "SD345", "SD390")] == [440, 490, 560]


def test_the_crack_conditions_and_the_standard(example):
    crack, standard = SAMPLE["crack"], SAMPLE["standard"]
    assert (example.environment, example.environment_number) == ("一般の環境", crack["con_u"])
    assert example.appearance is crack["vis_u"]
    assert example.ecsd == Printed(crack["ecsd_u"], 0, "×10⁻⁶")
    assert (example.kr, example.k4) == (KR, K4) and (KR.value, K4.value) == (crack["kr"], crack["k4"])
    assert example.body == "運輸機構"
    assert (example.jr001, example.jr004) == (standard["conditions"]["JR-001"], standard["conditions"]["JR-004"])


def test_the_extraction_cases_follow_the_extraction_groups_of_0610(example):
    pickup = SAMPLE["pickup"]
    for name, cases in (("moment", example.moment_cases), ("shear_force", example.shear_cases),
                        ("torsional_moment", example.torsion_cases)):
        assert dict(cases) == {int(key): value for key, value in pickup[name].items()}, name


def test_the_safety_factors_are_the_constants_of_the_sample():
    assert [factors.id for factors in SAFETY_FACTORS] == [row["id"] for row in SAMPLE["safety_factor"]]
    for factors, row in zip(SAFETY_FACTORS, SAMPLE["safety_factor"]):
        values = [None if getattr(factors, key.lower()) is None else getattr(factors, key.lower()).value
                  for key in SAFETY_KEYS]
        assert values == [row[key] for key in SAFETY_KEYS], factors.id
        assert factors.range == row["range"] and factors.title


@pytest.mark.parametrize("body,gamma_i", [("運輸機構", 1.2), ("JR各社", 1.2), ("JR東日本", 1.0)])
def test_the_restorability_structure_factor_of_each_body(body, gamma_i):
    """Owner, 2026-10-18: 復旧性（地震時以外） γi = 1.2 (the 1.0 of the sample's 8-25 is an error, ADR-0001), except
    1.0 for JR東日本 as Capacita's defaults have it; every other factor is the same for every body."""
    safety = check(**{f"{CHECK}/適用基準の機関": body}).safety
    (restorability,) = [factors for factors in safety if factors.id == 6]
    assert (restorability.ri.value, restorability.ri.digits) == (gamma_i, 1)
    others = [(factors.id, factors) for factors in safety if factors.id != 6]
    assert others == [(factors.id, factors) for factors in SAFETY_FACTORS if factors.id != 6]
    assert [factors for factors in safety if factors.id == 6][0].m_rbs == [
        factors for factors in SAFETY_FACTORS if factors.id == 6][0].m_rbs


@pytest.mark.parametrize("key,value,attribute,expected", [
    ("鋼材の腐食に対する環境条件", "特に厳しい腐食性環境", "environment_number", 3),
    ("鋼材の腐食に対する環境条件", "腐食性環境", "environment_number", 2),
    ("外観の照査", "行わない", "appearance", False),
    ("適用基準の機関", "JR東日本", "body", "JR東日本"),
    ("JR-001", "適用しない", "jr001", False),
    ("JR-004", "適用する", "jr004", True),
])
def test_the_conditions_are_the_input(key, value, attribute, expected):
    assert getattr(check(**{f"{CHECK}/{key}": value}), attribute) == expected


@pytest.mark.parametrize("path", [f"{CHECK}/鋼材の腐食に対する環境条件", f"{CHECK}/外観の照査", f"{CHECK}/ε'csd",
                                  f"{CHECK}/適用基準の機関", f"{CHECK}/JR-001", f"{CHECK}/JR-004",
                                  "鉄筋/柱/aggregate_max_mm"])
def test_a_blank_condition_is_an_input_error(path):
    fails(f"{path.replace('/', '.')}: 値が必要です", **{path: None})


def two_layers(**second):
    data = document()
    rows = data["鉄筋"]["柱"]["main_rows"]
    layer = deepcopy(rows[0]) | {"layer": 2, "cover_mode": "自動", "center_mm": None, "clear_gap_mm": 50} | second
    rows.insert(1, layer)
    return data


def test_equal_layers_of_main_bars_are_one_face_with_its_layer_spacing():
    result = check(two_layers())
    for bars in (result.upper, result.lower):
        assert (bars.per_layer, bars.layers, bars.count, bars.cover.value) == (29, 2, 58, 108)
        assert bars.layer_spacing == Printed(82, 1, "mm")  # 108 + 16 + 50 + 16 (D32)


def test_layers_with_different_bars_are_an_input_error():
    fails("鉄筋.柱.main_rows", two_layers(per_face_count=27))


def test_two_kinds_of_side_bars_are_an_input_error():
    data = document()
    rows = data["鉄筋"]["柱"]["main_rows"]
    rows.append(deepcopy(rows[1]) | {"layer": 2, "diameter_mm": 16, "cover_mode": "自動", "center_mm": None,
                                     "clear_gap_mm": 40})
    fails("鉄筋.柱.main_rows", data)


def test_without_side_bars():
    data = document()
    del data["鉄筋"]["柱"]["main_rows"][1]
    assert check(data).side is None


def test_the_hoop_row_must_include_the_column_base():
    fails("鉄筋.柱.column_hoops.direction_rows", **{f"{HOOPS}/0/start_mm": 1000.0})
    data = document()
    rows = data["鉄筋"]["柱"]["column_hoops"]["direction_rows"]
    rows.append(deepcopy(rows[0]))
    fails("鉄筋.柱.column_hoops.direction_rows", data)


def test_the_hoop_row_from_the_base_is_used_when_the_column_has_sections():
    data = document()
    rows = data["鉄筋"]["柱"]["column_hoops"]["direction_rows"]
    rows[0] |= {"start_mm": 0.0, "end_mm": 2000.0}
    rows.append(deepcopy(rows[0]) | {"start_mm": 2000.0, "end_mm": None, "effective_legs": 6, "pitch_mm": 300.0})
    hoops = check(data).hoops
    assert (hoops.legs, hoops.pitch.value) == (10, 150)


def test_moved_detail_positions_are_an_input_error():
    data = document()
    column = data["鉄筋"]["柱"]
    bars = column_layout(parse_input(document())).bars
    column["position_mode"] = "指定"
    column["manual_positions"] = [{"x_mm": b.x.value, "y_mm": b.y.value, "diameter_mm": b.diameter.value,
                                   "material": b.material} for b in bars]
    source = document()["鉄筋"]["柱"]
    column["manual_basis"] = {"generator_version": 1, "geometry": {"width_mm": 4500, "height_mm": 2700},
                              "inputs": {key: deepcopy(source[key]) for key in
                                         ("main_rows", "materials", "pure_cover_mm", "column_hoops")}}
    assert check(deepcopy(data)).upper == check().upper
    column["manual_positions"][0]["x_mm"] = 120
    fails("鉄筋.柱.manual_positions: 移動した詳細位置は", data)


@pytest.mark.parametrize("changes,message", [
    # side bars at uneven centres (両端＋中央ピッチ: 350, then 300 apart in the middle)
    ({f"{MAIN}/1/distribution": {"mode": "両端＋中央ピッチ", "edge_center_mm": 350.0, "pitch_mm": 300.0}},
     "鉄筋.柱.main_rows: 側方鉄筋の間隔が一定ではないため表せません"),
    # a 直角 row outside the 線路 main bars (等分 from 60 mm, ends included)
    ({f"{MAIN}/1/distribution": {"mode": "等分", "edge_center_mm": 60.0, "pitch_mm": None}, f"{MAIN}/1/endpoints": "含む"},
     "鉄筋.柱.main_rows: 線路方向の表の先頭・末尾1行が線路の主鉄筋と一致しません"),
    # two edge bars only (両端＋中央ピッチ): no spacing along the face
    ({f"{MAIN}/0/per_face_count": 2},
     "鉄筋.柱.main_rows: 線路の主鉄筋の間隔が一つに定まりません"),
    # no hoop steel anywhere
    ({f"{HOOPS}/0/material": None, "鉄筋/柱/materials/transverse": None},
     "鉄筋.柱.column_hoops.direction_rows[0].material: 値が必要です"),
    ({f"{HOOPS}/0/pitch_mm": None}, "鉄筋.柱.column_hoops.direction_rows[0].pitch_mm: 値が必要です"),
])
def test_layouts_the_wdj_cannot_express(changes, message):
    fails(message, **changes)


def test_a_column_without_track_main_bars_is_an_input_error():
    data = document()
    del data["鉄筋"]["柱"]["main_rows"][0]
    fails("鉄筋.柱.main_rows: 線路の主鉄筋の行が必要です", data)


def test_two_layers_of_side_bars_are_an_input_error():
    data = document()
    rows = data["鉄筋"]["柱"]["main_rows"]
    rows.append(deepcopy(rows[1]) | {"layer": 2, "cover_mode": "自動", "center_mm": None, "clear_gap_mm": 40})
    fails("鉄筋.柱.main_rows: 側方鉄筋は各芯位置に左右の面で1本ずつだけ表せます", data)


def test_layers_at_uneven_spacing_are_an_input_error():
    data = two_layers()
    rows = data["鉄筋"]["柱"]["main_rows"]
    rows.insert(2, deepcopy(rows[1]) | {"layer": 3, "clear_gap_mm": 80})
    fails("鉄筋.柱.main_rows: 線路の主鉄筋の段の間隔が一定ではないため表せません", data)


def test_the_report_sections_follow_the_checks_asked_for(example):
    """Capacita's section ids (Capacita README); 使用性（外観） only with the appearance check (owner: no 8.8 without)."""
    assert example.sections == ("section_forces", "bending_safety_destruction", "shear_safety_destruction",
                                "bending_durability", "shear_durability", "bending_serviceability",
                                "bending_restorability", "shear_restorability")
    without = check(**{f"{CHECK}/外観の照査": "行わない"}).sections
    assert without == tuple(section for section in example.sections if section != "bending_serviceability")
