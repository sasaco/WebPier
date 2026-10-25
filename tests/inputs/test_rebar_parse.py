"""The 鉄筋 section, the 耐震設計条件 and the JRSNAP conditions: digits, choices, unknown keys; blanks stay blanks
(decisions 5, 17, 19, 49).

The editor saves a member before all its values are entered, so a blank (null) parses as "not entered yet". Only
the column layout and the JRSNAP export ask for the values they use (tests/calc/test_column_rebar_layout.py).
"""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import parse_input

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))


def data():
    return deepcopy(CURRENT)


def fails(document, message):
    with pytest.raises(InputError, match=re.escape(message)):
        parse_input(document)


def mm(value, digits=1):
    return Printed(value, digits, "mm")


def test_the_column_of_the_current_input():
    column = parse_input(data()).rebar.column
    assert column.materials.main == "SD390" and column.materials.transverse == "SD390"
    assert column.pure_cover == mm(70)
    rail, cross = column.main_bars["線路"], column.main_bars["直角"]
    assert (rail.diameter, rail.per_face_count, rail.cover_mode, rail.center, rail.endpoints) == (
        mm(32, 0), 29, "自動", None, "含む")
    assert rail.distribution.mode == "両端＋中央ピッチ"
    assert rail.distribution.edge_center == mm(108) and rail.distribution.pitch == mm(150)
    assert rail.inner_layers == ()
    assert (cross.cover_mode, cross.center) == ("指定", mm(102))
    assert cross.distribution.mode == "中央ピッチ" and cross.distribution.edge_center is None
    assert column.overrides == {"線路": (), "直角": ()}
    assert column.hoops.enclosing_diameter == mm(22, 0)
    hoop_rail, hoop_cross = column.hoops.rows
    assert (hoop_rail.direction, hoop_rail.diameter, hoop_rail.effective_legs, hoop_rail.pitch) == (
        "線路", mm(22, 0), 10, mm(150))
    assert (hoop_cross.direction, hoop_cross.effective_legs, hoop_cross.start, hoop_cross.end) == ("直角", 6, None, None)


def test_the_beam_and_the_footing_bars_of_the_current_input():
    """Example2 13_片持ち梁照査/WebDan.wdj: 上側 D32 × 25 in two layers (17 at 108, 8 at 172), 下側 D19 × 18 at 121,
    side bars D22 × 17 from 350 at 125, stirrups D22 with 4 legs at 125 (decision 59). The footing is Example2 06 6.1
    and 6.2 (decision 73): 上 線路 D25 at 125 with its centre at 78.5, 直角 D25 at 103.5; 下 線路 D25 at 100, 直角 D29
    at 127; stirrups D16, 2 per 1 m, at 250."""
    rebar = parse_input(data()).rebar
    beam = rebar.beam
    upper, lower = beam.faces["上"], beam.faces["下"]
    assert (upper.diameter, upper.count, upper.bar_type, upper.cover_mode, upper.center) == (
        mm(32, 0), 17, "直筋", "指定", mm(108))
    assert [(layer.count, layer.clear_gap) for layer in upper.inner_layers] == [(8, mm(32))]  # 108 + 32 + 32 = 172
    assert (lower.diameter, lower.count, lower.bar_type, lower.center, lower.inner_layers) == (
        mm(19, 0), 18, None, mm(121), ())
    assert beam.pure_cover is None and beam.materials.main == "SD390" and beam.aggregate_max == mm(25)
    side = beam.side
    assert (side.diameter, side.per_face_count, side.start, side.pitch, side.stirrup_position, side.center) == (
        mm(22, 0), 17, mm(350), mm(125), "内側", mm(184))
    assert (beam.stirrups.diameter, beam.stirrups.effective_legs, beam.stirrups.pitch) == (mm(22, 0), 4, mm(125))
    footing = rebar.footing
    assert [footing.faces[face].outer_direction for face in ("上", "下")] == ["線路", "線路"]
    bars = {(face, direction): footing.faces[face].bars[direction] for face in ("上", "下") for direction in ("線路", "直角")}
    assert {key: (item.diameter, item.pitch, item.cover_mode, item.center, item.inner_layers)
            for key, item in bars.items()} == {
        ("上", "線路"): (mm(25, 0), mm(125), "指定", mm(79), ()), ("上", "直角"): (mm(25, 0), mm(125), "指定", mm(104), ()),
        ("下", "線路"): (mm(25, 0), mm(125), "指定", mm(100), ()), ("下", "直角"): (mm(29, 0), mm(125), "指定", mm(127), ())}
    stirrups = footing.stirrups["直角"]
    assert (stirrups.diameter, stirrups.pitch, stirrups.width_mode, stirrups.density) == (
        mm(16, 0), mm(250), "密度", Printed(2, 1, "本/m"))


def test_the_jrsnap_conditions_of_each_direction():
    jrsnap = parse_input(data()).jrsnap
    for conditions in (jrsnap.longitudinal, jrsnap.transverse):
        assert conditions.shear_factor_vcd == Printed(2.0, 2, "")
        assert conditions.shear_factor_vsd == Printed(1.3, 2, "")
        assert conditions.shear_factor_vdd == Printed(1.8, 2, "")


@pytest.mark.parametrize("key,steps,limited,target", [
    ("longitudinal", 300, 200, 0.3), ("transverse", 350, 300, 0.35)])  # Example2 10 / 11 NDU DataInfo (magnitudes)
def test_the_analysis_settings_of_each_direction(key, steps, limited, target):
    conditions = getattr(parse_input(data()).jrsnap, key)
    assert (conditions.steps, conditions.limited_final_step) == (steps, limited)
    assert conditions.target_displacement == Printed(target, 3, "m")


@pytest.mark.parametrize("key,value,message", [
    ("analysis_steps", 0, "1～100000の整数が必要です"),
    ("analysis_steps", 300.0, "1～100000の整数が必要です"),
    ("limited_final_step", 301, "analysis_steps（300）以下が必要です"),
    ("limited_final_step", 0, "1～100000の整数が必要です"),
    ("target_displacement_m", 0, "正の数値が必要です"),  # a magnitude (decision 43)
    ("target_displacement_m", -0.3, "正の数値が必要です"),
    ("target_displacement_m", 0.3005, "小数3桁までで入力してください"),
])
def test_analysis_setting_values(key, value, message):
    document = data()
    document["jrsnap_longitudinal"][key] = value
    fails(document, f"jrsnap_longitudinal.{key}: {message}")


@pytest.mark.parametrize("key", ["analysis_steps", "limited_final_step", "target_displacement_m"])
def test_analysis_settings_are_required_keys(key):
    document = data()
    del document["jrsnap_transverse"][key]
    fails(document, f"入力項目がありません: jrsnap_transverse.{key}")


def test_a_blank_step_count_skips_the_limited_step_check():
    document = data()
    document["jrsnap_longitudinal"]["analysis_steps"] = None
    conditions = parse_input(document).jrsnap.longitudinal
    assert conditions.steps is None and conditions.limited_final_step == 200


def test_jrsnap_conditions_may_be_blank_until_exported():
    document = data()
    document["jrsnap_transverse"]["shear_factor_vcd"] = None
    assert parse_input(document).jrsnap.transverse.shear_factor_vcd is None


@pytest.mark.parametrize("key,value,message", [
    ("shear_factor_vcd", 0, "正の数値が必要です"),
    ("shear_factor_vsd", 100.0, "99.99以下が必要です"),
    ("shear_factor_vdd", 1.255, "小数2桁までで入力してください"),
])
def test_jrsnap_condition_ranges(key, value, message):
    document = data()
    document["jrsnap_longitudinal"][key] = value
    fails(document, f"jrsnap_longitudinal.{key}: {message}")


def test_jrsnap_conditions_reject_unknown_keys():
    document = data()
    document["jrsnap_transverse"]["gamma_c"] = 1.3
    fails(document, "jrsnap_transverse.gamma_c: 未知の入力項目です")


@pytest.mark.parametrize("path", [
    ("鉄筋",), ("鉄筋", "柱"), ("鉄筋", "柱", "materials"), ("鉄筋", "柱", "main_bars"), ("鉄筋", "柱", "main_bars", "線路"),
    ("鉄筋", "柱", "main_bars", "線路", "distribution"), ("鉄筋", "柱", "table_overrides"), ("鉄筋", "柱", "column_hoops"),
    ("鉄筋", "柱", "column_hoops", "direction_rows", 1), ("鉄筋", "梁", "faces", "上"),
    ("鉄筋", "梁", "faces", "上", "inner_layers", 0), ("鉄筋", "梁", "side_bars"), ("鉄筋", "梁", "stirrups"),
    ("鉄筋", "フーチング"),
    ("鉄筋", "フーチング", "faces", "下", "直角"), ("鉄筋", "フーチング", "faces", "上"),
    ("鉄筋", "フーチング", "stirrups", "線路"),
])
def test_unknown_rebar_keys_are_rejected(path):
    document = data()
    node = document
    for part in path:
        node = node[part]
    node["typo_mm"] = 1
    prefix = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path).lstrip(".")
    fails(document, f"{prefix}.typo_mm: 未知の入力項目です")


@pytest.mark.parametrize("path,key", [
    (("鉄筋", "柱", "main_bars", "線路"), "endpoints"),
    (("鉄筋", "柱", "main_bars", "直角"), "distribution"),
    (("鉄筋", "柱", "main_bars", "線路"), "inner_layers"),
    (("鉄筋", "柱", "main_bars"), "直角"),
    (("鉄筋", "柱", "table_overrides"), "線路"),
    (("鉄筋", "柱"), "column_hoops"),
    (("鉄筋", "梁", "faces", "上"), "bar_type"),
    (("鉄筋", "梁"), "side_bars"),
    (("鉄筋", "フーチング", "faces", "上"), "outer_direction"),
    (("鉄筋",), "フーチング"),
])
def test_every_rebar_key_is_required(path, key):
    # The editor writes every key; a missing one is not read as a default (decision 5).
    document = data()
    node = document
    for part in path:
        node = node[part]
    del node[key]
    prefix = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path).lstrip(".")
    fails(document, f"入力項目がありません: {prefix}.{key}")


def test_rebar_format_version_must_be_3():
    document = data()
    document["鉄筋"]["version"] = 2
    fails(document, "鉄筋.version: 3～3の整数が必要です")


@pytest.mark.parametrize("key,value,message", [
    ("endpoints", "含まない", "「含む」「含めない」のいずれかを選んでください"),
    ("cover_mode", "手動", "「自動」「指定」のいずれかを選んでください"),
    ("diameter_mm", 31.8, "小数0桁までで入力してください"),
    ("diameter_mm", 0, "正の数値が必要です"),
    ("per_face_count", 2.5, "0～10000の整数が必要です"),
])
def test_column_main_bar_values(key, value, message):
    document = data()
    document["鉄筋"]["柱"]["main_bars"]["線路"][key] = value
    fails(document, f"鉄筋.柱.main_bars.線路.{key}: {message}")


def test_distribution_mode_is_a_choice():
    document = data()
    document["鉄筋"]["柱"]["main_bars"]["線路"]["distribution"]["mode"] = "端部ピッチ"
    fails(document, "鉄筋.柱.main_bars.線路.distribution.mode: 「等分」「中央ピッチ」「両端＋中央ピッチ」のいずれか")


def test_edge_bars_need_at_least_two_bars_per_face():
    document = data()
    document["鉄筋"]["柱"]["main_bars"]["線路"]["per_face_count"] = 1
    fails(document, "鉄筋.柱.main_bars.線路.per_face_count: 両端＋中央ピッチの配列は2本以上が必要です")


def test_layers_inside_take_only_their_count_and_gap():
    document = data()
    document["鉄筋"]["柱"]["main_bars"]["線路"]["inner_layers"] = [
        {"per_face_count": 27, "clear_gap_mm": 40}, {"per_face_count": None, "clear_gap_mm": None}]
    inner = parse_input(document).rebar.column.main_bars["線路"].inner_layers
    assert [(layer.per_face_count, layer.clear_gap) for layer in inner] == [(27, mm(40)), (None, None)]
    layer = document["鉄筋"]["柱"]["main_bars"]["線路"]["inner_layers"][0]
    layer["per_face_count"] = 0
    fails(document, "鉄筋.柱.main_bars.線路.inner_layers[0].per_face_count: 1～10000の整数が必要です")
    layer["per_face_count"] = 27
    layer["diameter_mm"] = 32
    fails(document, "鉄筋.柱.main_bars.線路.inner_layers[0].diameter_mm: 未知の入力項目です")


def test_table_overrides():
    document = data()
    changes = document["鉄筋"]["柱"]["table_overrides"]["線路"]
    changes.append({"source_center_mm": 180, "source_diameter_mm": 32, "center_mm": None, "diameter_mm": 29})
    (change,) = parse_input(document).rebar.column.overrides["線路"]
    assert (change.source_center, change.source_diameter, change.center, change.diameter) == (
        mm(180), mm(32, 0), None, mm(29, 0))
    changes.append({"source_center_mm": 180, "source_diameter_mm": 32, "center_mm": 190, "diameter_mm": None})
    fails(document, "鉄筋.柱.table_overrides.線路[1]: 同じ元の芯位置・径の変更がほかの行にあります")
    changes[1] = {"source_center_mm": 300, "source_diameter_mm": 32, "center_mm": None, "diameter_mm": None}
    fails(document, "鉄筋.柱.table_overrides.線路[1]: 芯位置か径の変更が必要です")
    changes[1] = {"source_center_mm": None, "source_diameter_mm": 32, "center_mm": 310, "diameter_mm": None}
    fails(document, "鉄筋.柱.table_overrides.線路[1].source_center_mm: 値が必要です")


def test_column_hoop_rows():
    document = data()
    row = document["鉄筋"]["柱"]["column_hoops"]["direction_rows"][0]
    row.update(start_mm=1000, end_mm=500)
    fails(document, "鉄筋.柱.column_hoops.direction_rows[0].end_mm: 開始位置以上が必要です")
    row.update(start_mm=None, end_mm=None, effective_legs=0)
    fails(document, "鉄筋.柱.column_hoops.direction_rows[0].effective_legs: 1～10000の整数が必要です")
    row.update(effective_legs=10, direction=None)
    assert parse_input(document).rebar.column.hoops.rows[0].direction is None


def test_beam_side_bars_may_be_none_and_the_lower_face_has_no_shape():
    document = data()
    beam = document["鉄筋"]["梁"]
    beam["side_bars"] = None
    assert parse_input(document).rebar.beam.side is None
    beam["side_bars"] = {"diameter_mm": 16, "per_face_count": 4, "start_mm": 300, "pitch_mm": 250,
                         "stirrup_position": "外側", "cover_mode": "自動", "center_mm": None}
    side = parse_input(document).rebar.beam.side
    assert (side.per_face_count, side.stirrup_position, side.cover_mode, side.center) == (4, "外側", "自動", None)
    beam["side_bars"]["columns"] = 1
    fails(document, "鉄筋.梁.side_bars.columns: 未知の入力項目です")
    del beam["side_bars"]["columns"]
    beam["stirrups"]["effective_legs"] = 0
    fails(document, "鉄筋.梁.stirrups.effective_legs: 1～10000の整数が必要です")
    beam["stirrups"]["effective_legs"] = 4
    beam["faces"]["下"]["bar_type"] = "直筋"
    fails(document, "鉄筋.梁.faces.下.bar_type: 未知の入力項目です")


def test_footing_stirrups_have_a_width_distribution():
    document = data()
    document["鉄筋"]["フーチング"]["stirrups"]["直角"] = {
        "diameter_mm": 13, "pitch_mm": 300, "distribution_mode": "密度", "width_pitch_mm": None, "density_per_m": 2.5}
    stirrups = parse_input(document).rebar.footing.stirrups["直角"]
    assert (stirrups.width_mode, stirrups.width_pitch, stirrups.density) == ("密度", None, Printed(2.5, 1, "本/m"))
    document["鉄筋"]["フーチング"]["stirrups"]["直角"]["distribution_mode"] = "本数"
    fails(document, "鉄筋.フーチング.stirrups.直角.distribution_mode: 「間隔」「密度」のいずれか")


def test_the_footing_face_names_a_direction_outside():
    document = data()
    document["鉄筋"]["フーチング"]["faces"]["下"]["outer_direction"] = "橋軸"
    fails(document, "鉄筋.フーチング.faces.下.outer_direction: 「線路」「直角」のいずれかを選んでください")


def test_rebar_parse_does_not_mutate_the_document():
    document = data()
    parse_input(document)
    assert document == CURRENT


def test_the_seismic_design_conditions_of_the_current_input():
    """Decision 49: Example2 is C地域 and G2地盤 (10_線路(耐震)/P1_線路.xml; 10-24 G2地盤（地域別係数:0.70））."""
    design = parse_input(data()).seismic_design
    assert (design.region, design.ground_class) == ("C地域", "G2地盤")


def test_the_seismic_design_conditions_may_be_blank_until_a_nonlinear_analysis():
    document = data()
    document["耐震設計条件"] = {"地域別": None, "地盤区分": None}
    design = parse_input(document).seismic_design
    assert (design.region, design.ground_class) == (None, None)


@pytest.mark.parametrize("key,value,message", [
    ("地域別", "D地域", "「A地域」「B地域」「C地域」のいずれかを選んでください（入力: 'D地域'）"),
    ("地盤区分", "G6地盤", "「G0地盤」「G1地盤」「G2地盤」「G3地盤」「G4地盤」「G5地盤」のいずれかを選んでください"),
    ("地盤区分", "応答塑性率の直接入力", "「G5地盤」のいずれかを選んでください（入力: '応答塑性率の直接入力'）"),  # no μ
])
def test_the_seismic_design_conditions_are_choices(key, value, message):
    document = data()
    document["耐震設計条件"][key] = value
    with pytest.raises(InputError, match=re.escape(f"耐震設計条件.{key}: ") + ".*" + re.escape(message)):
        parse_input(document)


def test_the_liquefaction_index_is_an_optional_choice_and_blank_without_it():
    """Decision 95: 5<PL<20 or 20<PL for the Cases for the liquefaction; an input without the key is blank there."""
    document = data()
    assert parse_input(document).seismic_design.liquefaction_index is None
    for value in ("5<PL<20", "20<PL", None):
        document["耐震設計条件"]["液状化指数"] = value
        assert parse_input(document).seismic_design.liquefaction_index == value
    document["耐震設計条件"]["液状化指数"] = "PL=10"
    with pytest.raises(InputError, match=re.escape("耐震設計条件.液状化指数: ") + ".*「5<PL<20」「20<PL」のいずれかを選んでください"):
        parse_input(document)


def test_the_seismic_design_conditions_are_one_section_with_two_keys():
    document = data()
    document["耐震設計条件"]["スペクトル"] = "Ⅰ,Ⅱ"  # WebPier's condition, not an input
    fails(document, "耐震設計条件.スペクトル: 未知の入力項目です")
    document = data()
    del document["耐震設計条件"]["地盤区分"]
    fails(document, "入力項目がありません: 耐震設計条件.地盤区分")
    document = data()
    del document["耐震設計条件"]
    fails(document, "入力項目がありません: 耐震設計条件")
