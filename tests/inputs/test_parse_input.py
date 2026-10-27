"""The schema 2 input: one parse for every stage, nothing filled in (decisions 5, 6, 16-19)."""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import BrakingRule, parse_input
from webpier.inputs.fields import SNOW_KEYS

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))


def data():
    return deepcopy(CURRENT)


def fails(document, message):
    with pytest.raises(InputError, match=re.escape(message)):
        parse_input(document)


def test_current_input_reads_with_printed_digits():
    pier = parse_input(data())
    assert pier.substructure.b[1] == Printed(2.7, 3, "m")
    assert pier.substructure.b[9].value == 2.15
    assert pier.substructure.h[4].value == 4.9
    assert pier.substructure.unit_weight_body == Printed(24.5, 1, "kN/m3")
    assert pier.spans.origin.hs == Printed(2.952, 3, "m")
    assert pier.spans.origin.bearing == "可動" and pier.spans.end.bearing == "固定"
    assert pier.spans.end.recovery_brake_coefficient.value == 1.0
    assert pier.spans.origin.recovery_brake_coefficient is None
    assert pier.train.vehicle == "P-16" and pier.train.braking_rule is BrakingRule.AXLE
    assert pier.soil.layers[1].soil_type == "砂礫"
    assert pier.materials.column.value == 27.0


def test_empty_bearing_slots_are_absent_bearings():
    pier = parse_input(data())
    b = pier.reactions.b
    assert [slot is None for slot in b] == [False] * 4 + [True] * 6
    assert b[0].position.value == -3.8
    assert b[0].shares.l2.value == -0.02
    assert not hasattr(b[0].shares, "l3") and not hasattr(b[0].shares, "l4")
    assert pier.reactions.a.d1.value == 5740.0


@pytest.mark.parametrize("track", ["L3", "L4"])
def test_a_third_or_fourth_track_is_not_supported(track):
    # Decision 23: shares L3/L4 must stay blank; a value is an input error, not silently ignored.
    document = data()
    document["上部工反力"]["終点側"]["C支点"][1]["列車分担"][track] = 0.0
    fails(document, f"上部工反力.終点側.C支点[1].列車分担.{track}: 3線以上は未対応です")


def test_a_bearing_with_a_blank_value_is_an_error_not_zero():
    document = data()
    document["上部工反力"]["起点側"]["B支点"][0]["付加死荷重_D2"] = None
    fails(document, "上部工反力.起点側.B支点[0].付加死荷重_D2: 値が必要です")


def test_ten_bearing_slots_are_required():
    document = data()
    document["上部工反力"]["起点側"]["B支点"].pop()
    fails(document, "上部工反力.起点側.B支点: 10～10件の配列が必要です")


@pytest.mark.parametrize("path,key", [
    (("下部構造", "寸法", "側面"), "B9"),
    (("上部構造", "起点側"), "支承位置_f"),
    (("上部工反力", "起点側", "A支点"), "固定死荷重_D1"),
    (("上部工反力", "終点側", "D支点"), "付加死荷重_D2"),
    (("下部構造", "土かぶり"), "終点側_df2"),
    (("下部構造", "寸法", "高さ"), "H5"),
])
def test_retired_fallbacks_are_now_input_errors(path, key):
    document = data()
    node = document
    for part in path:
        node = node[part]
    node[key] = None
    fails(document, f"{'.'.join(path)}.{key}: 値が必要です")


def test_a_blank_snow_load_is_no_snow():
    # decision 62: blank is 0 kN at the girder ends and at the bearings; the other values stay required
    document = data()
    for side, end, support in (("起点側", "A支点", "B支点"), ("終点側", "D支点", "C支点")):
        reactions = document["上部工反力"][side]
        reactions[end] |= dict.fromkeys(SNOW_KEYS)
        for slot in reactions[support]:
            if slot is not None:
                slot |= dict.fromkeys(SNOW_KEYS)
    pier = parse_input(document)
    ends = (pier.reactions.a, pier.reactions.d)
    bearings = [b for b in (*pier.reactions.b, *pier.reactions.c) if b is not None]
    assert bearings and all(
        (item.snow2, item.snow10, item.snow30) == (Printed(0, 2, "kN"),) * 3 for item in (*ends, *bearings))


def test_surface_thickness_may_be_entered_and_middle_layers_need_theirs():
    # decision 64: 表層 may have a 層厚 (blank or absent: the rest of Df); a layer above 支持層 needs its 層厚
    document = data()
    document["地盤データ"]["層"][0]["層厚"] = 1.25
    assert parse_input(document).soil.surface.thickness == Printed(1.25, 3, "m")
    document["地盤データ"]["層"][0]["層厚"] = None
    assert parse_input(document).soil.surface.thickness is None
    middle = deepcopy(document["地盤データ"]["層"][0]) | {"層番": "ローム", "層厚": None}
    document["地盤データ"]["層"].insert(1, middle)
    fails(document, "地盤データ.層[1].層厚: 値が必要です")


def test_top_layer_wet_unit_weight_is_required():
    document = data()
    document["地盤データ"]["層"][0]["単位体積重量"]["湿潤"] = None
    fails(document, "地盤データ.層[0].単位体積重量.湿潤: 値が必要です")


def test_values_finer_than_the_printed_digits_are_rejected():
    document = data()
    document["上部構造"]["起点側"]["重心高_hs"] = 2.9520833333333334
    fails(document, "上部構造.起点側.重心高_hs: 小数3桁までで入力してください")


@pytest.mark.parametrize("vehicle", ["EA-17 ", "ＥＡ－１７", "M-18", "", None])
def test_vehicle_must_be_one_of_the_program_choices(vehicle):
    document = data()
    document["上部構造"]["列車"]["車両名"] = vehicle
    with pytest.raises(InputError, match="上部構造.列車.車両名"):
        parse_input(document)


def test_ea17_selects_the_ea17_braking_rule():
    document = data()
    document["上部構造"]["列車"]["車両名"] = "EA-17"
    document["上部構造"]["列車"]["編成数"] = None
    train = parse_input(document).train
    assert (train.braking_rule, train.cars) == (BrakingRule.EA17, None)


def test_the_cars_are_entered_only_for_a_vehicle_of_repeated_cars():
    """decision 101: the standard fixes EA-17's train; P-16 is repeated cars and needs how many."""
    document = data()
    document["上部構造"]["列車"]["車両名"] = "EA-17"
    fails(document, "上部構造.列車.編成数: EA-17 の編成は規定で決まるので空欄にしてください（入力: 10）")
    document = data()
    document["上部構造"]["列車"]["編成数"] = None
    fails(document, "上部構造.列車.編成数: 値が必要です")


@pytest.mark.parametrize("key", ["1両の長さ", "軸距", "軸重"])
def test_the_vehicle_definition_is_no_input(key):
    document = data()
    document["上部構造"]["列車"][key] = 20.0
    fails(document, f"上部構造.列車.{key}: 未知の入力項目です")


def test_soil_type_choices_follow_the_ground_reaction_equations():
    document = data()
    document["地盤データ"]["層"][1]["土質区分"] = "砂質土と粘性土の互層"
    assert parse_input(document).soil.layers[1].soil_type == "砂質土と粘性土の互層"
    document["地盤データ"]["層"][1]["土質区分"] = "安山岩"
    fails(document, "地盤データ.層[1].土質区分: 「砂質土」「砂礫」「粘性土」「砂質土と粘性土の互層」のいずれか")


def test_reserved_skew_fields_are_validated_but_kept():
    pier = parse_input(data())
    assert pier.reserved.skew_angle.value == 90
    document = data()
    document["下部構造"]["斜角"]["θ"] = 90.5
    fails(document, "下部構造.斜角.θ: 小数0桁までで入力してください")


@pytest.mark.parametrize("path,key", [
    (("下部構造", "寸法", "側面"), "B10"),
    (("上部構造", "列車"), "単位"),
    ((), "schema_version_typo"),
])
def test_unknown_or_derived_keys_are_rejected(path, key):
    document = data()
    node = document
    for part in path:
        node = node[part]
    node[key] = 1
    prefix = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path).lstrip(".")
    fails(document, f"{prefix + '.' if prefix else ''}{key}: 未知の入力項目です")


def test_schema_version_must_be_2():
    document = data()
    document["schema_version"] = 1
    fails(document, "schema_version: 2～2の整数が必要です")


def test_source_notes_are_free_form():
    document = data()
    document["出典"] = {"何でも": ["自由", 1]}
    parse_input(document)


def test_beam_must_be_wider_than_its_haunch_offsets():
    document = data()
    document["下部構造"]["寸法"]["側面"]["B4"] = 1.5
    document["下部構造"]["寸法"]["側面"]["B5"] = 1.2
    fails(document, "下部構造.寸法.側面.B1: B4+B5より大きい値が必要です")


def test_exactly_one_supporting_layer_and_the_top_layer_first():
    document = data()
    document["地盤データ"]["層"][1]["層番"] = "中間層"
    fails(document, "地盤データ.層: 層番「支持層」の行をちょうど1行指定してください")
    document = data()
    document["地盤データ"]["層"][0]["層番"] = "盛土"
    fails(document, "地盤データ.層[0].層番: 先頭は「表層」としてください")


def test_parse_does_not_mutate_the_document():
    document = data()
    parse_input(document)
    assert document == CURRENT


@pytest.mark.parametrize("key", ["使用性", "安全性(破壊)", "安全性(疲労)"])
@pytest.mark.parametrize("value", [0.0, -0.5])
def test_load_factors_must_be_positive(key, value):
    # Decision 37: a load factor of 0 would remove the train from its combinations; it is an input error.
    document = data()
    document["上部構造"]["列車"]["荷重修正係数"][key] = value
    fails(document, f"上部構造.列車.荷重修正係数.{key}: 正の数値が必要です")


def test_friction_angles_of_any_layer_stay_below_90_degrees():
    document = data()
    document["地盤データ"]["層"][0]["内部摩擦角_φd"] = 90.0
    fails(document, "地盤データ.層[0].内部摩擦角_φd: 90度未満が必要です")


def test_support_friction_angle_is_within_the_bearing_factor_table():
    document = data()
    document["地盤データ"]["層"][1]["内部摩擦角_φd"] = 24.9
    fails(document, "地盤データ.層[1].内部摩擦角_φd: 25度以上90度未満が必要です")
