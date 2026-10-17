"""The 鉄筋 section and the JRSNAP conditions: digits, choices, unknown keys; blanks stay blanks (decisions 5, 17, 19).

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
    first, second = column.main_rows
    assert first.diameter == mm(32, 0) and first.material is None
    assert (first.cover_mode, first.center, first.face_direction, first.layer) == ("自動", None, "線路", 1)
    assert first.per_face_count == 29 and first.endpoints == "含む"
    assert first.distribution.mode == "両端＋中央ピッチ"
    assert first.distribution.edge_center == mm(108) and first.distribution.pitch == mm(150)
    assert (second.cover_mode, second.center, second.face_direction) == ("指定", mm(102), "直角")
    assert second.distribution.mode == "中央ピッチ" and second.distribution.edge_center is None
    assert column.hoops.enclosing_diameter == mm(22, 0)
    rail, cross = column.hoops.rows
    assert (rail.direction, rail.diameter, rail.material, rail.effective_legs, rail.pitch) == (
        "線路", mm(22, 0), "SD390", 10, mm(150))
    assert (cross.direction, cross.effective_legs, cross.start, cross.end) == ("直角", 6, None, None)
    assert column.manual_positions == () and column.position_mode == "基本" and column.manual_basis is None


def test_beam_and_footing_drafts_keep_their_blanks():
    rebar = parse_input(data()).rebar
    beam = rebar.beam
    assert [(row.face, row.bar_type, row.layer, row.count, row.diameter) for row in beam.main_rows] == [
        ("上", "直筋", 1, None, None), ("下", "直筋", 1, None, None)]
    assert beam.pure_cover is None and beam.materials.main is None
    footing = rebar.footing
    assert [(row.direction, row.face, row.layers, row.stack_order) for row in footing.main_rows] == [
        ("線路", "上", 1, 1), ("線路", "下", 1, 1), ("直角", "上", 1, 2), ("直角", "下", 1, 2)]
    assert footing.main_rows[0].pitch is None and footing.position_mode == "基本"


def test_the_jrsnap_conditions_of_each_direction():
    jrsnap = parse_input(data()).jrsnap
    for conditions in (jrsnap.longitudinal, jrsnap.transverse):
        assert conditions.shear_factor_vcd == Printed(2.0, 2, "")
        assert conditions.shear_factor_vsd == Printed(1.3, 2, "")
        assert conditions.shear_factor_vdd == Printed(1.8, 2, "")
        assert conditions.aggregate_max == mm(25)


@pytest.mark.parametrize("key,steps,limited,target", [
    ("longitudinal", 300, 200, -0.3), ("transverse", 350, 300, 0.35)])  # Example2 10 / 11 NDU DataInfo
def test_the_analysis_settings_of_each_direction(key, steps, limited, target):
    conditions = getattr(parse_input(data()).jrsnap, key)
    assert (conditions.steps, conditions.limited_final_step) == (steps, limited)
    assert conditions.target_displacement == Printed(target, 3, "m")


@pytest.mark.parametrize("key,value,message", [
    ("analysis_steps", 0, "1～100000の整数が必要です"),
    ("analysis_steps", 300.0, "1～100000の整数が必要です"),
    ("limited_final_step", 301, "analysis_steps（300）以下が必要です"),
    ("limited_final_step", 0, "1～100000の整数が必要です"),
    ("target_displacement_m", 0, "0以外が必要です"),
    ("target_displacement_m", -0.3005, "小数3桁までで入力してください"),
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
    document["jrsnap_transverse"]["aggregate_max_mm"] = None
    assert parse_input(document).jrsnap.transverse.aggregate_max is None


@pytest.mark.parametrize("key,value,message", [
    ("shear_factor_vcd", 0, "正の数値が必要です"),
    ("shear_factor_vsd", 100.0, "99.99以下が必要です"),
    ("shear_factor_vdd", 1.255, "小数2桁までで入力してください"),
    ("aggregate_max_mm", 0.05, "小数1桁までで入力してください"),
    ("aggregate_max_mm", 1_000_000, "0.1～999999 mmが必要です"),
    ("aggregate_max_mm", 0, "0.1～999999 mmが必要です"),
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
    ("鉄筋",), ("鉄筋", "柱"), ("鉄筋", "柱", "materials"), ("鉄筋", "柱", "main_rows", 0),
    ("鉄筋", "柱", "main_rows", 0, "distribution"), ("鉄筋", "柱", "column_hoops"),
    ("鉄筋", "柱", "column_hoops", "direction_rows", 1), ("鉄筋", "梁", "main_rows", 1), ("鉄筋", "フーチング"),
    ("鉄筋", "フーチング", "main_rows", 3),
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
    (("鉄筋", "柱", "main_rows", 0), "endpoints"),
    (("鉄筋", "柱", "main_rows", 0), "distribution"),
    (("鉄筋", "柱"), "column_hoops"),
    (("鉄筋", "梁", "main_rows", 0), "bar_type"),
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


def test_rebar_format_version_must_be_2():
    document = data()
    document["鉄筋"]["version"] = 1
    fails(document, "鉄筋.version: 2～2の整数が必要です")


@pytest.mark.parametrize("key,value,message", [
    ("endpoints", "含まない", "「含む」「含めない」のいずれかを選んでください"),
    ("face_direction", "橋軸", "「線路」「直角」のいずれかを選んでください"),
    ("cover_mode", "手動", "「自動」「指定」のいずれかを選んでください"),
    ("material", "SD490", "「SD295」「SD345」「SD390」のいずれかを選んでください"),
    ("diameter_mm", 31.8, "小数0桁までで入力してください"),
    ("diameter_mm", 0, "正の数値が必要です"),
    ("clear_gap_mm", 40.25, "小数1桁までで入力してください"),
    ("per_face_count", 2.5, "0～10000の整数が必要です"),
    ("layer", 0, "1～100の整数が必要です"),
])
def test_column_main_row_values(key, value, message):
    document = data()
    document["鉄筋"]["柱"]["main_rows"][0][key] = value
    fails(document, f"鉄筋.柱.main_rows[0].{key}: {message}")


def test_distribution_mode_is_a_choice():
    document = data()
    document["鉄筋"]["柱"]["main_rows"][0]["distribution"]["mode"] = "端部ピッチ"
    fails(document, "鉄筋.柱.main_rows[0].distribution.mode: 「等分」「中央ピッチ」「両端＋中央ピッチ」のいずれか")


def test_edge_bars_need_at_least_two_bars_per_face():
    document = data()
    document["鉄筋"]["柱"]["main_rows"][0]["per_face_count"] = 1
    fails(document, "鉄筋.柱.main_rows[0].per_face_count: 両端＋中央ピッチの配列は2本以上が必要です")


def test_column_hoop_rows():
    document = data()
    row = document["鉄筋"]["柱"]["column_hoops"]["direction_rows"][0]
    row.update(start_mm=1000, end_mm=500)
    fails(document, "鉄筋.柱.column_hoops.direction_rows[0].end_mm: 開始位置以上が必要です")
    row.update(start_mm=None, end_mm=None, effective_legs=0)
    fails(document, "鉄筋.柱.column_hoops.direction_rows[0].effective_legs: 1～10000の整数が必要です")
    row.update(effective_legs=10, direction=None)
    assert parse_input(document).rebar.column.hoops.rows[0].direction is None


def test_column_side_and_band_rows_are_not_used():
    # The column is reinforced by main_rows and column_hoops; the editor keeps these two lists empty.
    for key in ("side_rows", "band_rows"):
        document = data()
        document["鉄筋"]["柱"][key] = [{}]
        fails(document, f"鉄筋.柱.{key}: 柱では使いません（帯鉄筋は column_hoops に入力します）")


def test_manual_positions_and_their_basis():
    document = data()
    column = document["鉄筋"]["柱"]
    column["position_mode"] = "指定"
    column["manual_positions"] = [{"x_mm": 108, "y_mm": 108, "diameter_mm": 32, "material": "SD390"},
                                  {"x_mm": None, "y_mm": None, "diameter_mm": None, "material": None}]
    column["manual_basis"] = {
        "generator_version": 1, "geometry": {"width_mm": 4500, "height_mm": 2700},
        "inputs": {key: deepcopy(column[key]) for key in ("main_rows", "materials", "pure_cover_mm", "column_hoops")}}
    parsed = parse_input(document).rebar.column
    assert parsed.position_mode == "指定"
    assert parsed.manual_positions[0].x == mm(108) and parsed.manual_positions[1].material is None
    basis = parsed.manual_basis
    assert (basis.width, basis.height) == (mm(4500), mm(2700))
    assert basis.main_rows == parsed.main_rows and basis.hoops == parsed.hoops
    assert basis.materials == parsed.materials and basis.pure_cover == parsed.pure_cover
    column["manual_basis"]["generator_version"] = 2
    fails(document, "鉄筋.柱.manual_basis.generator_version: 1～1の整数が必要です")
    column["manual_basis"]["generator_version"] = 1
    column["manual_basis"]["inputs"]["band_rows"] = []
    fails(document, "鉄筋.柱.manual_basis.inputs.band_rows: 未知の入力項目です")


def test_a_blank_basis_is_no_basis():
    document = data()
    document["鉄筋"]["柱"]["manual_basis"] = None
    assert parse_input(document).rebar.column.manual_basis is None


def test_position_mode_is_required_and_a_choice():
    document = data()
    document["鉄筋"]["梁"]["position_mode"] = None
    fails(document, "鉄筋.梁.position_mode: 空でない文字列が必要です")


def test_the_footing_has_no_detail_positions():
    document = data()
    document["鉄筋"]["フーチング"]["position_mode"] = "指定"
    fails(document, "鉄筋.フーチング.position_mode: フーチングは方向別の芯かぶり・重ね順で配置します")


def test_beam_side_and_band_rows():
    document = data()
    beam = document["鉄筋"]["梁"]
    beam["side_rows"] = [{"diameter_mm": 16, "material": "SD345", "per_face_count": 4, "columns": 2,
                          "column_pitch_mm": 60, "start_mm": 300, "pitch_mm": 250, "stirrup_position": "内側",
                          "cover_mode": "自動", "center_mm": None}]
    beam["band_rows"] = [{"type": "外巻き", "direction": "線路", "diameter_mm": 16, "material": None, "sets": 1.5,
                          "pitch_mm": 200, "start_mm": None, "end_mm": None, "legs_mode": "自動",
                          "effective_legs": None}]
    rebar = parse_input(document).rebar.beam
    side, = rebar.side_rows
    assert (side.per_face_count, side.columns, side.column_pitch, side.stirrup_position) == (4, 2, mm(60), "内側")
    band, = rebar.band_rows
    assert (band.type, band.sets, band.legs_mode, band.width_mode) == ("外巻き", Printed(1.5, 1, "組"), "自動", None)
    beam["side_rows"][0]["columns"] = 5
    fails(document, "鉄筋.梁.side_rows[0].columns: 片面本数以下が必要です")
    beam["side_rows"][0]["columns"] = 2
    beam["band_rows"][0]["sets"] = 1.3  # 2.6 legs
    fails(document, "鉄筋.梁.band_rows[0].sets: 有効脚数（1組＝2脚）が整数にならないため、有効脚数を指定してください")
    beam["band_rows"][0].update(legs_mode="指定", effective_legs=3)
    assert parse_input(document).rebar.beam.band_rows[0].effective_legs == 3
    beam["band_rows"][0]["width_pitch_mm"] = 200
    fails(document, "鉄筋.梁.band_rows[0].width_pitch_mm: 未知の入力項目です")


def test_footing_band_rows_have_a_width_distribution():
    document = data()
    document["鉄筋"]["フーチング"]["band_rows"] = [{
        "type": "内側", "direction": "直角", "diameter_mm": 13, "material": "SD345", "sets": None, "pitch_mm": 300,
        "start_mm": 0, "end_mm": 2700, "legs_mode": "指定", "effective_legs": 12, "distribution_mode": "密度",
        "width_pitch_mm": None, "density_per_m": 2.5}]
    band, = parse_input(document).rebar.footing.band_rows
    assert (band.width_mode, band.width_pitch, band.density) == ("密度", None, Printed(2.5, 1, "本/m"))
    document["鉄筋"]["フーチング"]["band_rows"][0]["distribution_mode"] = "本数"
    fails(document, "鉄筋.フーチング.band_rows[0].distribution_mode: 「間隔」「密度」のいずれか")


def test_footing_rows_need_positive_layers_and_order():
    document = data()
    document["鉄筋"]["フーチング"]["main_rows"][2]["stack_order"] = 0
    fails(document, "鉄筋.フーチング.main_rows[2].stack_order: 1～100の整数が必要です")


def test_rebar_parse_does_not_mutate_the_document():
    document = data()
    parse_input(document)
    assert document == CURRENT
