"""The schema 2 input: one parse for every stage, nothing filled in (decisions 5, 6, 16-19)."""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import BrakingRule, parse_input

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
    assert b[0].shares.l3 is None and b[0].shares.l4 is None
    assert pier.reactions.a.d1.value == 5740.0


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
    (("上部工反力", "終点側", "D支点"), "雪荷重_2年確率"),
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
    assert parse_input(document).train.braking_rule is BrakingRule.EA17


def test_soil_type_choices_follow_the_ground_reaction_equations():
    document = data()
    document["地盤データ"]["層"][1]["土質区分"] = "砂質土と粘性土の互層"
    assert parse_input(document).soil.layers[1].soil_type == "砂質土と粘性土の互層"
    document["地盤データ"]["層"][1]["土質区分"] = "安山岩"
    fails(document, "地盤データ.層[1].土質区分: 「砂質土」「砂礫」「粘性土」「砂質土と粘性土の互層」のいずれか")


def test_unsupported_foundation_type_is_reserved_but_rejected():
    document = data()
    document["下部構造"]["杭種"] = "場所打ち杭"
    fails(document, "下部構造.杭種: 場所打ち杭は未対応です")


def test_reserved_pile_and_skew_fields_are_validated_but_kept():
    pier = parse_input(data())
    assert pier.reserved.skew_angle.value == 90
    assert len(pier.reserved.piles) == 6
    document = data()
    document["下部構造"]["斜角"]["θ"] = 90.5
    fails(document, "下部構造.斜角.θ: 小数0桁までで入力してください")


@pytest.mark.parametrize("path,key", [
    (("下部構造", "寸法", "側面"), "B10"),
    (("上部構造", "列車"), "単位"),
    ((), "schema_version_typo"),
    (("地盤データ", "層", 0), "層厚"),       # derived: H6+H5+min(df1,df2)
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


def test_train_length_must_exceed_its_axle_spacing():
    document = data()
    document["上部構造"]["列車"]["1両の長さ"] = 7.2
    fails(document, "上部構造.列車.1両の長さ: a1_連結部+2×a2より大きい値が必要です")


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
