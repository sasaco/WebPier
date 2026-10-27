"""0611 / 0621 柱の断面照査 (decision 48, ADR-0008): the conditions Capacita is given, from the input, the column
layout and 0610 / 0620.

The expected values are the independent transcriptions tests/fixtures/example2/column_section_check.json of the
sample 08_線路/WebDan.wdj and column_section_check_09.json of 09_直角/WebDan.wdj (their notes list the deliberate
differences); nothing here is computed by the code under test. The check point is the column bottom found from the
roles of the frame, the bars come from the 方向別の鉄筋配置表 of the bending direction (線路 for 0611, 直角 for
0621), the extraction cases from the extraction groups of 0610 / 0620, and the safety factors, fsu, kr and k4 are
named program constants. A layout the WDJ cannot express is an input error naming its path. Decision 103 counts the
corner bars in the main bars by area and spreads uneven side bars: those values are worked out here by hand (0621 of
Example2 differs from its sample there; Example4's bars are its III-139 and III-214).
"""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.calc.column_check import (K4, KR, LONGITUDINAL, SAFETY_FACTORS, TRANSVERSE, calculate_column_check,
                                       column_bars, corner_bars, tensile_strength)
from webpier.calc.column_rebar import TableRow, column_layout
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import parse_input
from example4_support import EXAMPLE4_INPUT

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
SAMPLE = json.loads((FIXTURES / "example2" / "column_section_check.json").read_text(encoding="utf-8"))
SAMPLE_09 = json.loads((FIXTURES / "example2" / "column_section_check_09.json").read_text(encoding="utf-8"))
MAIN = "鉄筋/柱/main_bars"
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


def check(data=None, *, transverse=False, **changes):
    pier = parse_input(data if data is not None else document(**changes))
    reaction, foundation = calculate_reaction(pier), calculate_foundation(pier)
    if transverse:
        return calculate_column_check(pier, calculate_transverse(pier, foundation, reaction), TRANSVERSE)
    return calculate_column_check(pier, calculate_longitudinal(pier, foundation, reaction), LONGITUDINAL)


def fails(message, data=None, **changes):
    with pytest.raises(InputError, match=re.escape(message)):
        check(data, **changes)


@pytest.fixture(scope="module")
def example():
    return check()


@pytest.fixture(scope="module")
def across():
    return check(transverse=True)


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
    assert (bars.diameter.value, bars.count.value, bars.per_layer.value, bars.layers) == (
        sample["rebar_dia"], sample["rebar_n"], sample["rebar_n"], 1)
    assert (bars.cover.value, bars.spacing.value, bars.layer_spacing) == (sample["rebar_cover"], sample["rebar_ss"],
                                                                           None)


def test_the_side_bars(example):
    side, sample = example.side, SAMPLE["bar"]["sidebar1"]
    assert (side.diameter.value, side.count.value, side.first.value, side.spacing.value) == (
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
    assert [tensile_strength(grade).value for grade in ("SD295", "SD345", "SD390", "SD490")] == [440, 490, 560, 620]


def test_the_crack_conditions_and_the_standard(example):
    crack, standard = SAMPLE["crack"], SAMPLE["standard"]
    assert (example.environment, example.environment_number) == ("常時乾燥", crack["con_u"])
    assert example.appearance is crack["vis_u"]
    assert example.ecsd == Printed(crack["ecsd_u"], 0, "×10⁻⁶")
    assert (example.kr, example.k4) == (KR, K4) and (KR.value, K4.value) == (crack["kr"], crack["k4"])
    assert example.body == "運輸機構"
    assert (example.jr001, example.jr004) == (standard["conditions"]["JR-001"], standard["conditions"]["JR-004"])


def test_the_extraction_cases_follow_the_extraction_groups_of_0610(example):
    """The sample's, and the row 8 (最小鉄筋量, blank in the sample) the permanent action 3 (decision 73)."""
    pickup = SAMPLE["pickup"]
    assert pickup["moment"]["8"] is None and pickup["moment"]["1"] == 3
    for name, cases in (("moment", example.moment_cases), ("shear_force", example.shear_cases),
                        ("torsional_moment", example.torsion_cases)):
        expected = {int(key): value for key, value in pickup[name].items()}
        assert dict(cases) == (expected | {8: 3} if name == "moment" else expected), name


# WebDanforJS safety-factors-material-strengths.service.ts default_safety_factor for the railway bodies (decision 73,
# transcribed from the source): id: (M_rc, M_rs, M_rbs, V_rc, V_rs, V_rbc, V_rbs, V_rbv, T_rbt, ri, range).
R5_DEFAULTS = {0: (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, None, 1.0, 1.0, 1),
               2: (1.3, 1.05, 1.0, 1.3, 1.05, 1.3, 1.0, None, None, 1.1, 2),
               5: (1.3, 1.0, 1.1, 1.3, 1.0, 1.3, 1.1, 1.2, 1.3, 1.2, 2),
               6: (1.3, 1.0, 1.0, 1.3, 1.0, 1.3, 1.1, 1.2, 1.3, 1.2, 3),
               7: (1.3, 1.0, 1.0, 1.3, 1.0, 1.3, 1.1, 1.2, 1.3, 1.0, 3),
               8: (1.3, 1.0, 1.0, None, None, None, None, None, None, 1.0, 3)}


def test_the_safety_factors_are_the_r5_defaults_of_webdanforjs():
    """But the 安全性（破壊） counts all the axial bars, the side bars too (range 3, decision 105)."""
    assert [factors.id for factors in SAFETY_FACTORS] == list(R5_DEFAULTS)
    for factors in SAFETY_FACTORS:
        values = [None if getattr(factors, key.lower()) is None else getattr(factors, key.lower()).value
                  for key in SAFETY_KEYS]
        expected = R5_DEFAULTS[factors.id]
        assert (*values, factors.range) == (expected[:-1] + (3,) if factors.id == 5 else expected), factors.id
        assert factors.title
    assert [factors.title for factors in SAFETY_FACTORS if factors.id in (6, 7)] == ["使用性（損傷）", "復旧性（損傷）地震時"]


def test_the_r5_factors_differ_from_the_samples_h16_only_by_torsion_and_the_seismic_vsd():
    """Example2 08_線路/WebDan.wdj (H16): γb of torsion 1.0 (none for fatigue in R5) and γb of Vsd 1.0 of the row 7."""
    for factors, row in zip(SAFETY_FACTORS, SAMPLE["safety_factor"]):
        values = dict(zip(SAFETY_KEYS, R5_DEFAULTS[factors.id]))
        changed = {key for key in SAFETY_KEYS if values[key] != row[key]}
        expected = ({"T_rbt"} if factors.id in (2, 5, 6, 7) else set()) | ({"V_rbs"} if factors.id == 7 else set())
        assert changed == expected, factors.id


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
    ("水掛かりの程度", "常時湿潤", "environment_number", 3),
    ("水掛かりの程度", "乾湿繰返し", "environment_number", 2),
    ("外観の照査", "行わない", "appearance", False),
    ("適用基準の機関", "JR東日本", "body", "JR東日本"),
    ("JR-001", "適用しない", "jr001", False),
    ("JR-004", "適用する", "jr004", True),
])
def test_the_conditions_are_the_input(key, value, attribute, expected):
    assert getattr(check(**{f"{CHECK}/{key}": value}), attribute) == expected


@pytest.mark.parametrize("path", [f"{CHECK}/水掛かりの程度", f"{CHECK}/外観の照査", f"{CHECK}/ε'csd",
                                  f"{CHECK}/適用基準の機関", f"{CHECK}/JR-001", f"{CHECK}/JR-004",
                                  "鉄筋/柱/aggregate_max_mm"])
def test_a_blank_condition_is_an_input_error(path):
    fails(f"{path.replace('/', '.')}: 値が必要です", **{path: None})


def two_layers(**second):
    data = document()
    data["鉄筋"]["柱"]["main_bars"]["線路"]["inner_layers"] = [{"per_face_count": 29, "clear_gap_mm": 50} | second]
    return data


def test_equal_layers_of_main_bars_are_one_face_with_its_layer_spacing():
    result = check(two_layers())
    for bars in (result.upper, result.lower):
        assert (bars.per_layer.value, bars.layers, bars.count.value, bars.cover.value) == (29, 2, 58, 108)
        assert bars.layer_spacing == Printed(82, 1, "mm")  # 108 + 16 + 50 + 16 (D32)


def test_the_last_layer_may_have_fewer_bars():
    """Capacita splits the total by layer 1's count (decision 103): 29 + 27 is 56 in layers of 29."""
    bars = check(two_layers(per_face_count=27)).upper
    assert (bars.per_layer.value, bars.layers, bars.count.value) == (29, 2, 56)


def test_layers_capacita_cannot_split_are_an_input_error():
    """29, 27, 29: fewer in a layer before the last (more than layer 1 in a layer is refused by the input already)."""
    data = two_layers(per_face_count=27)
    data["鉄筋"]["柱"]["main_bars"]["線路"]["inner_layers"].append({"per_face_count": 29, "clear_gap_mm": 50})
    fails("鉄筋.柱.main_bars: 線路の主鉄筋の段の本数は、最後の段のほかは1段目と同じ、最後の段は1段目以下でなければ表せません",
          data)


def test_two_kinds_of_side_bars_are_an_input_error():
    data = document()
    # the 直角 bars at x = 102 become D16 in the 直角 table; those at 4398 stay D19
    data["鉄筋"]["柱"]["table_overrides"]["直角"] = [
        {"source_center_mm": 102, "source_diameter_mm": 19, "center_mm": None, "diameter_mm": 16}]
    fails("鉄筋.柱.main_bars: 側方鉄筋の径・材質が1種類ではありません（D16 SD390・D19 SD390）", data)


def test_without_side_bars():
    data = document()
    data["鉄筋"]["柱"]["main_bars"]["直角"]["per_face_count"] = 0
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


def test_a_table_change_is_in_the_checked_section():
    data = document()
    # the 線路 bars at 108 from the upper face become D29: the upper face only
    data["鉄筋"]["柱"]["table_overrides"]["線路"] = [
        {"source_center_mm": 108, "source_diameter_mm": 32, "center_mm": None, "diameter_mm": 29}]
    result = check(data)
    assert (result.upper.diameter, result.lower.diameter) == (Printed(29, 0, "mm"), Printed(32, 0, "mm"))
    assert (result.upper.per_layer, result.upper.cover) == (Printed(29, 2, "本"), Printed(108, 1, "mm"))


@pytest.mark.parametrize("changes,message", [
    # a 直角 row outside the 線路 main bars (等分 from 60 mm, ends included)
    ({f"{MAIN}/直角/distribution": {"mode": "等分", "edge_center_mm": 60.0, "pitch_mm": None},
      f"{MAIN}/直角/endpoints": "含む"},
     "鉄筋.柱.main_bars: 線路方向の表で、線路の主鉄筋の段が1段ずつの行になっていません"),
    # two edge bars only (両端＋中央ピッチ): no spacing along the face
    ({f"{MAIN}/線路/per_face_count": 2},
     "鉄筋.柱.main_bars: 線路の主鉄筋の間隔が一つに定まりません"),
    # no hoop steel anywhere
    ({"鉄筋/柱/materials/transverse": None}, "鉄筋.柱.materials.transverse: 値が必要です"),
    ({f"{HOOPS}/0/pitch_mm": None}, "鉄筋.柱.column_hoops.direction_rows[0].pitch_mm: 値が必要です"),
])
def test_layouts_the_wdj_cannot_express(changes, message):
    fails(message, **changes)


def test_a_column_without_track_main_bars_is_an_input_error():
    data = document()
    data["鉄筋"]["柱"]["main_bars"]["線路"]["per_face_count"] = 0
    fails("鉄筋.柱.main_bars: 線路の主鉄筋が必要です", data)


def test_side_bars_at_uneven_centres_are_spread_from_the_first_to_the_last():
    """両端＋中央ピッチ: 350, 450 … 2250, 2350 (100, then 300 apart): nine on each face, (2350 − 350)／8 = 250 apart."""
    data = document(**{f"{MAIN}/直角/distribution": {"mode": "両端＋中央ピッチ", "edge_center_mm": 350.0,
                                                    "pitch_mm": 300.0}})
    side = check(data).side
    assert (side.count, side.first, side.spacing) == (Printed(9, 2, "本"), Printed(350, 1, "mm"),
                                                      Printed(250, 1, "mm"))


def test_two_layers_of_side_bars_are_one_spread_layer():
    """The 直角 rows of nine at 102 and nine inside them, at the same centres: eighteen on each face, (2350 − 350)／17
    = 117.6 apart."""
    data = document()
    data["鉄筋"]["柱"]["main_bars"]["直角"]["inner_layers"] = [{"per_face_count": 9, "clear_gap_mm": 40}]
    side = check(data).side
    assert (side.count, side.first, side.spacing) == (Printed(18, 2, "本"), Printed(350, 1, "mm"),
                                                      Printed(117.6, 1, "mm"))


def test_side_bars_between_the_layers_of_main_bars():
    """Decision 108 (P7): the inner layer at 108 + 32 + 250 = 390, inside the 直角 bars at 350; the side bars are the
    rows between the layers too, nine on each face from 350, 250 apart."""
    data = two_layers(per_face_count=27, clear_gap_mm=250)
    result = check(data)
    upper, side = result.upper, result.side
    assert (upper.layers, upper.per_layer, upper.count, upper.cover, upper.layer_spacing) == (
        2, Printed(29, 2, "本"), Printed(56, 2, "本"), Printed(108, 1, "mm"), Printed(282, 1, "mm"))
    assert result.lower == upper
    assert (side.count, side.first, side.spacing) == (Printed(9, 2, "本"), Printed(350, 1, "mm"),
                                                      Printed(250, 1, "mm"))


def test_layers_at_uneven_spacing_are_an_input_error():
    data = two_layers()
    data["鉄筋"]["柱"]["main_bars"]["線路"]["inner_layers"].append({"per_face_count": 29, "clear_gap_mm": 80})
    fails("鉄筋.柱.main_bars: 線路の主鉄筋の段の間隔が一定ではないため表せません", data)


def test_the_report_sections_follow_the_checks_asked_for(example):
    """Capacita's section ids (Capacita README); 使用性（外観） only with the appearance check (owner: no 8.8 without)."""
    assert example.sections == ("section_forces", "bending_safety_destruction", "shear_safety_destruction",
                                "bending_durability", "shear_durability", "bending_serviceability",
                                "bending_restorability", "shear_restorability", "bending_rebar_amount")
    without = check(**{f"{CHECK}/外観の照査": "行わない"}).sections
    assert without == tuple(section for section in example.sections if section != "bending_serviceability")


# --- 0621: across the track (the sample 09_直角/WebDan.wdj) -----------------------------------------------------------


def test_across_the_track_the_check_point_is_the_bottom_of_the_column_of_0620(across):
    point = SAMPLE_09["check_point"]
    assert (across.direction, across.member, across.length) == (TRANSVERSE, point["member"],
                                                                 Printed(point["position_m"], 3, "m"))


def test_across_the_track_the_section_is_turned(across):
    member = SAMPLE_09["member"]
    assert (across.width, across.depth) == (Printed(member["B"], 1, "mm"), Printed(member["H"], 1, "mm"))


@pytest.mark.parametrize("face,key", [("upper", "rebar1"), ("lower", "rebar2")])
def test_across_the_track_the_main_bars_are_the_cross_rows_with_the_corner_bars(across, face, key):
    """Decision 103: the D19 × 9 at 102 and the track rows' corner D32 × 2 at 108 as D19 by area,
    (9 × 286.5 + 2 × 794.2)／286.5 = 14.54, at (2578.5 × 102 + 1588.4 × 108)／4166.9 = 104.3. The sample writes
    D19 × 9 at 102 and the corner bars with the side bars."""
    bars, sample = getattr(across, face), SAMPLE_09["bar"][key]
    assert (bars.diameter.value, bars.count, bars.layers) == (sample["rebar_dia"], Printed(14.54, 2, "本"), 1)
    assert (bars.cover, bars.spacing.value) == (Printed(104.3, 1, "mm"), sample["rebar_ss"])


def test_across_the_track_the_side_bars_are_those_between_the_corner_bars(across):
    """The track rows' D32 at 300 … 4200, 150 apart: 27 on each face (the sample: 29 with the corner bars)."""
    side = across.side
    assert (side.diameter.value, side.count, side.first, side.spacing) == (
        SAMPLE_09["bar"]["sidebar1"]["side_dia"], Printed(27, 2, "本"), Printed(300, 1, "mm"), Printed(150, 1, "mm"))


def test_across_the_track_the_hoops_are_the_cross_row(across):
    hoops, sample = across.hoops, SAMPLE_09["bar"]["stirrup"]
    assert (hoops.diameter.value, hoops.legs, hoops.pitch.value) == (
        sample["stirrup_dia"], sample["stirrup_n"], sample["stirrup_ss"])


def test_across_the_track_the_cases_and_conditions_are_those_of_08(across, example):
    """The sample's two WDJ files share them (same_as_08); 0620 has the extraction groups of 0610 (9-15)."""
    assert "pickup" in SAMPLE_09["same_as_08"] and "crack" in SAMPLE_09["same_as_08"]
    for name in ("moment_cases", "shear_cases", "torsion_cases", "safety", "environment", "appearance", "ecsd", "body",
                 "kr", "k4", "fck", "aggregate_max", "main_steel", "hoop_steel", "sections"):
        assert getattr(across, name) == getattr(example, name), name


@pytest.mark.parametrize("rows,expected", [
    (((100, 2), (250, 2), (400, 2)), (3, 100, 150)),  # one on each face at each centre, equally spaced: as they are
    (((100, 2), (250, 2), (450, 2)), (3, 100, 175)),  # uneven: spread from the first to the last
    (((100, 2), (250, 4), (400, 2)), (4, 100, 100)),  # two on each face at 250: four on each face
    (((100, 2), (200, 3)), (2.5, 100, 50)),  # Capacita's three centres for 2.5 on each face
    (((100, 1),), (0.5, 100, None)),  # one centre
])
def test_side_bars_are_half_of_the_bars_on_each_face(rows, expected):
    from webpier.calc.column_check import _side
    table_rows = tuple(TableRow(Printed(centre, 1, "mm"), Printed(32, 0, "mm"), count, "SD390")
                       for centre, count in rows)
    side, grade = _side(table_rows, "線路")
    count, first, spacing = expected
    assert (side.count, side.first, side.spacing, grade) == (
        Printed(count, 2, "本"), Printed(first, 1, "mm"), None if spacing is None else Printed(spacing, 1, "mm"),
        "SD390")


def test_side_bars_at_one_centre_cannot_be_spread():
    from webpier.calc.column_check import _side
    with pytest.raises(InputError, match=re.escape("鉄筋.柱.main_bars: 線路の側方鉄筋は1つの芯位置にしかなく")):
        _side((TableRow(Printed(100, 1, "mm"), Printed(32, 0, "mm"), 4, "SD390"),), "線路")


def test_the_corner_bars_are_the_end_bars_of_a_row_at_its_own_cover():
    layout = column_layout(parse_input(document()))
    upper, lower = corner_bars(layout, TRANSVERSE)  # the track rows' D32 at 108 from both faces
    assert sorted((bar.x.value, bar.y.value) for bar in upper) == [(108, 108), (108, 2592)]
    assert sorted((bar.x.value, bar.y.value) for bar in lower) == [(4392, 108), (4392, 2592)]
    assert corner_bars(layout, LONGITUDINAL) == ((), ())  # the cross rows' D19 from 350: not at the corners


# --- Example4 (decision 103): III-139 along the track, III-214 across it ------------------------------------------------


@pytest.fixture(scope="module")
def example4():
    return column_layout(parse_input(json.loads(EXAMPLE4_INPUT.read_text(encoding="utf-8"))))


def test_example4_along_the_track_the_layers_of_23_and_11(example4):
    """III-139: D38-34本, centroid (23 × 84 + 11 × 179)／34 = 114.7: layers of 23 at 84, then 95 apart."""
    upper, lower, (side, side_grade), grade = column_bars(example4, LONGITUDINAL)
    for bars in (upper, lower):
        assert (bars.diameter.value, bars.count, bars.per_layer, bars.layers) == (38, Printed(34, 2, "本"),
                                                                                  Printed(23, 2, "本"), 2)
        assert (bars.cover, bars.layer_spacing) == (Printed(84, 1, "mm"), Printed(95, 1, "mm"))
    assert (side.diameter.value, side.count, side.first, side.spacing) == (  # III-139: D19-14本 (7 on each face)
        19, Printed(7, 2, "本"), Printed(350, 1, "mm"), Printed(300, 1, "mm"))
    assert (grade, side_grade) == ("SD490", "SD490")


def test_example4_across_the_track_the_corner_bars_by_area_and_the_side_bars_spread(example4):
    """III-214: D38-2本 + D19-7本 (4285.5 mm2) as D19 (286.5): 4285.5／286.5 = 14.96, at
    (2005.5 × 74.5 + 2280 × 84)／4285.5 = 79.6 (the sample: 84.0 for both). 側方鉄筋 D38-32本 on each face: 21 at 250
    … 3250 and 11 at 1000 … 2500, spread (3250 − 250)／31 = 96.8 apart."""
    upper, lower, (side, _), _ = column_bars(example4, TRANSVERSE)
    for bars in (upper, lower):
        assert (bars.diameter.value, bars.count, bars.layers, bars.cover) == (19, Printed(14.96, 2, "本"), 1,
                                                                              Printed(79.6, 1, "mm"))
    assert (side.diameter.value, side.count, side.first, side.spacing) == (
        38, Printed(32, 2, "本"), Printed(250, 1, "mm"), Printed(96.8, 1, "mm"))
