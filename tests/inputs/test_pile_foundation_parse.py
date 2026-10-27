"""The pile foundation of the input (decision 84, ADR-0013): 基礎形式, 杭基礎, and the layers' c and De.

A pile foundation reads only the items of its type; the rest are read as to form and digits and kept. The rules between
them are CONTEXT.md 杭の配置 / 千鳥配置 and the SOIL-JR input it is written for. Which output items a pile foundation
can make is widened a stage at a time (inputs.outputs.PILE_OUTPUT_KEYS): the tests choose the three of the first one.
"""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.inputs import outputs, parse, parse_input

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
MADE = ("detailing", "ground_model", "reactions")


@pytest.fixture(autouse=True)
def made(monkeypatch):
    """A pile foundation that can make the items of the first stage, so that the pile rules are the last thing read."""
    monkeypatch.setattr(outputs, "PILE_OUTPUT_KEYS", MADE)
    monkeypatch.setattr(parse, "PILE_OUTPUT_KEYS", MADE)


def pile_input(kind="場所打ち杭"):
    data = deepcopy(CURRENT)
    data["下部構造"]["基礎形式"] = kind
    data["outputs"] = {key: key in MADE for key in data["outputs"]}
    piles = data["杭基礎"]
    piles["杭長"] = 19.0
    piles["杭の単位体積重量"] = 24.5
    piles["場所打ち杭"] = {"杭径": 1.0, "f'ck": 24.0, "施工条件": "自然泥水"}
    piles["鋼管ソイルセメント杭"] = {"ソイルセメント径": 1.2, "鋼管外径": 1.0, "鋼管厚": 18.0, "腐食代": 1.0,
                                  "鋼管材質": "SKK490",
                                  "結合部": {"軸方向鉄筋": {"径": 38, "本数": 16, "材質": "SD390", "重心位置": 75.0},
                                          "中詰めコンクリート_f'ck": 27.0}}
    piles["配置"] = {"形式": "格子", "線路方向の列の位置": [-3.0, 0.0, 3.0], "線路直角方向の列の位置": [-3.0, 0.0, 3.0],
                   "抜く杭": [{"線路方向の列": 2, "線路直角方向の列": 2}]}
    return data


def fails(document, message):
    with pytest.raises(InputError, match=re.escape(message)):
        parse_input(document)


def test_the_current_input_is_a_direct_foundation_with_nothing_entered_for_piles():
    pier = parse_input(deepcopy(CURRENT))
    assert pier.substructure.foundation == "直接基礎"
    assert pier.piles.length is None and pier.piles.layout.along == () and pier.piles.layout.removed == ()
    assert pier.soil.layers[1].cohesion.value == 0 and pier.soil.layers[1].reduction is None


def test_a_cast_in_place_pile_foundation_reads_its_values():
    pier = parse_input(pile_input())
    piles = pier.piles
    assert pier.substructure.foundation == "場所打ち杭"
    assert (piles.length.value, piles.unit_weight.value) == (19.0, 24.5)
    assert (piles.cast_in_place.diameter.value, piles.cast_in_place.fck.value, piles.cast_in_place.condition) == (
        1.0, 24.0, "自然泥水")
    assert piles.layout.pattern == "格子"
    assert [position.value for position in piles.layout.along] == [-3.0, 0.0, 3.0]
    assert [position.value for position in piles.layout.across] == [-3.0, 0.0, 3.0]
    assert piles.layout.removed == ((2, 2),)


def test_a_steel_soil_cement_pile_foundation_reads_its_values():
    piles = parse_input(pile_input("鋼管ソイルセメント杭")).piles
    steel = piles.steel_soil_cement
    assert (steel.soil_cement_diameter.value, steel.steel_diameter.value) == (1.2, 1.0)
    assert (steel.thickness.value, steel.corrosion.value) == (18.0, 1.0)


def test_a_staggered_layout_has_piles_where_the_column_numbers_add_to_an_even_number():
    data = pile_input()
    data["杭基礎"]["配置"].update(形式="千鳥", 抜く杭=[{"線路方向の列": 3, "線路直角方向の列": 3}])
    assert parse_input(data).piles.layout.pattern == "千鳥"


@pytest.mark.parametrize("kind,item", [("場所打ち杭", "鋼管ソイルセメント杭"), ("鋼管ソイルセメント杭", "場所打ち杭")])
def test_the_values_of_the_other_pile_type_are_not_needed(kind, item):
    data = pile_input(kind)
    data["杭基礎"][item] = {key: None for key in data["杭基礎"][item]}
    if item == "鋼管ソイルセメント杭":
        data["杭基礎"][item]["結合部"] = {"軸方向鉄筋": {"径": None, "本数": None, "材質": None, "重心位置": None},
                                    "中詰めコンクリート_f'ck": None}
    parse_input(data)


@pytest.mark.parametrize("path,message", [
    (("杭長",), "杭基礎.杭長: 値が必要です"),
    (("杭の単位体積重量",), "杭基礎.杭の単位体積重量: 値が必要です"),
    (("場所打ち杭", "杭径"), "杭基礎.場所打ち杭.杭径: 値が必要です"),
    (("場所打ち杭", "f'ck"), "杭基礎.場所打ち杭.f'ck: 値が必要です"),
    (("場所打ち杭", "施工条件"), "杭基礎.場所打ち杭.施工条件: 値が必要です"),
    (("配置", "形式"), "杭基礎.配置.形式: 値が必要です"),
])
def test_a_cast_in_place_pile_foundation_needs_its_values(path, message):
    data = pile_input()
    node = data["杭基礎"]
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = None
    fails(data, message)


@pytest.mark.parametrize("key", ["ソイルセメント径", "鋼管外径", "鋼管厚", "腐食代"])
def test_a_steel_soil_cement_pile_foundation_needs_its_values(key):
    data = pile_input("鋼管ソイルセメント杭")
    data["杭基礎"]["鋼管ソイルセメント杭"][key] = None
    fails(data, f"杭基礎.鋼管ソイルセメント杭.{key}: 値が必要です")


@pytest.mark.parametrize("change,message", [
    ({"ソイルセメント径": 1.0}, "杭基礎.鋼管ソイルセメント杭.ソイルセメント径: 鋼管外径より大きい値が必要です"),
    ({"鋼管厚": 500.0}, "杭基礎.鋼管ソイルセメント杭.鋼管厚: 鋼管外径の半分より小さい値が必要です"),
    ({"腐食代": 18.1}, "杭基礎.鋼管ソイルセメント杭.腐食代: 鋼管厚（腐食代を含む）以下が必要です"),
])
def test_the_steel_pipe_must_fit_in_the_soil_cement_and_its_wall(change, message):
    data = pile_input("鋼管ソイルセメント杭")
    data["杭基礎"]["鋼管ソイルセメント杭"].update(change)
    fails(data, message)


def test_a_corrosion_allowance_may_be_nothing():
    data = pile_input("鋼管ソイルセメント杭")
    data["杭基礎"]["鋼管ソイルセメント杭"]["腐食代"] = 0.0
    assert parse_input(data).piles.steel_soil_cement.corrosion.value == 0


@pytest.mark.parametrize("key,message", [
    ("線路方向の列の位置", "杭基礎.配置.線路方向の列の位置: 1列以上の位置が必要です"),
    ("線路直角方向の列の位置", "杭基礎.配置.線路直角方向の列の位置: 1列以上の位置が必要です"),
])
def test_each_direction_needs_a_column(key, message):
    data = pile_input()
    data["杭基礎"]["配置"][key] = []
    data["杭基礎"]["配置"]["抜く杭"] = []
    fails(data, message)


@pytest.mark.parametrize("key", ["線路方向の列の位置", "線路直角方向の列の位置"])
def test_the_columns_are_in_order_of_position(key):
    data = pile_input()
    data["杭基礎"]["配置"][key] = [-3.0, 3.0, 3.0]
    fails(data, f"杭基礎.配置.{key}[2]: 前の列（3 m）より大きい位置が必要です")


def test_there_are_at_most_99_columns():
    data = pile_input()
    data["杭基礎"]["配置"]["線路方向の列の位置"] = [index / 10 for index in range(100)]
    fails(data, "杭基礎.配置.線路方向の列の位置: 0～99件の配列が必要です（100件）")


@pytest.mark.parametrize("along,across", [([0.0, 3.0], [-3.0, 0.0, 3.0]), ([-3.0, 0.0, 3.0], [0.0, 3.0])])
def test_a_staggered_layout_needs_an_odd_number_of_columns_each_way(along, across):
    data = pile_input()
    data["杭基礎"]["配置"].update(形式="千鳥", 線路方向の列の位置=along, 線路直角方向の列の位置=across, 抜く杭=[])
    fails(data, f"杭基礎.配置.形式: 千鳥配置は両方向とも奇数列が必要です（線路方向 {len(along)}列、線路直角方向 {len(across)}列）")


def test_a_pile_left_out_is_where_the_layout_has_one():
    data = pile_input()
    data["杭基礎"]["配置"].update(形式="千鳥", 抜く杭=[{"線路方向の列": 1, "線路直角方向の列": 2}])
    fails(data, "杭基礎.配置.抜く杭[0]: 千鳥配置の杭のない位置は抜けません")


@pytest.mark.parametrize("hole,message", [
    ({"線路方向の列": 4, "線路直角方向の列": 1}, "杭基礎.配置.抜く杭[1].線路方向の列: 線路方向の列は 1～3 が必要です"),
    ({"線路方向の列": 1, "線路直角方向の列": 4}, "杭基礎.配置.抜く杭[1].線路直角方向の列: 線路直角方向の列は 1～3 が必要です"),
    ({"線路方向の列": 2, "線路直角方向の列": 2}, "杭基礎.配置.抜く杭[1]: 同じ位置が重なっています"),
])
def test_a_pile_left_out_is_a_place_of_the_layout_once(hole, message):
    data = pile_input()
    data["杭基礎"]["配置"]["抜く杭"].append(hole)
    fails(data, message)


def test_a_column_keeps_a_pile():
    data = pile_input()
    data["杭基礎"]["配置"]["抜く杭"] = [{"線路方向の列": 1, "線路直角方向の列": index} for index in (1, 2, 3)]
    fails(data, "杭基礎.配置.線路方向の列の位置[0]: この列の杭がすべてなくなります")
    data["杭基礎"]["配置"]["抜く杭"] = [{"線路方向の列": index, "線路直角方向の列": 3} for index in (1, 2, 3)]
    fails(data, "杭基礎.配置.線路直角方向の列の位置[2]: この列の杭がすべてなくなります")


def test_a_direct_foundation_reads_the_pile_items_as_to_form_and_digits_only():
    data = deepcopy(CURRENT)
    data["杭基礎"]["配置"]["線路方向の列の位置"] = [3.0, 0.0]  # not in order, not read as a layout
    data["杭基礎"]["配置"]["形式"] = "千鳥"
    assert [position.value for position in parse_input(data).piles.layout.along] == [3.0, 0.0]
    data["杭基礎"]["杭長"] = 19.0005
    fails(data, "杭基礎.杭長: 小数3桁までで入力してください")


@pytest.mark.parametrize("path,value,message", [
    (("杭基礎", "杭長"), -1.0, "杭基礎.杭長: 正の数値が必要です"),
    (("杭基礎", "場所打ち杭", "施工条件"), "ベントナイト泥水", "杭基礎.場所打ち杭.施工条件: 「自然泥水」「安定液使用」のいずれか"),
    (("杭基礎", "配置", "形式"), "三角", "杭基礎.配置.形式: 「格子」「千鳥」のいずれか"),
    (("下部構造", "基礎形式"), "鋼管杭", "下部構造.基礎形式: 「直接基礎」「場所打ち杭」「鋼管ソイルセメント杭」のいずれか"),
])
def test_the_values_of_the_pile_items_are_their_choices_and_ranges(path, value, message):
    data = pile_input()
    node = data
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value
    fails(data, message)


def test_an_unknown_pile_key_is_an_input_error():
    data = pile_input()
    data["杭基礎"]["本数"] = 9
    fails(data, "杭基礎.本数: 未知の入力項目です")
    data = pile_input()
    data["杭基礎"]["配置"]["抜く杭"][0]["列"] = 1
    fails(data, "杭基礎.配置.抜く杭[0].列: 未知の入力項目です")


def test_the_pile_items_are_not_removable():
    data = pile_input()
    del data["杭基礎"]
    fails(data, "入力項目がありません: 杭基礎")


@pytest.mark.parametrize("key", [key for key in outputs.OUTPUT_KEYS if key not in MADE])
def test_a_pile_foundation_makes_only_the_items_it_can_so_far(key):
    data = pile_input()
    data["outputs"][key] = True  # the items it uses are not chosen: the item the foundation cannot make is named first
    fails(data, f"outputs.{key}: 場所打ち杭は未対応です（場所打ち杭で選べる出力項目: detailing・ground_model・reactions）")


def test_a_pile_foundation_makes_no_item_before_one_is_supported(monkeypatch):
    monkeypatch.setattr(outputs, "PILE_OUTPUT_KEYS", ())
    monkeypatch.setattr(parse, "PILE_OUTPUT_KEYS", ())
    fails(pile_input("鋼管ソイルセメント杭"), "outputs.detailing: 鋼管ソイルセメント杭は未対応です（鋼管ソイルセメント杭で選べる出力項目: なし）")


def test_a_direct_foundation_makes_every_item():
    assert all(outputs.foundation_makes("直接基礎", key) for key in outputs.OUTPUT_KEYS)
    assert all(outputs.foundation_makes(None, key) for key in outputs.OUTPUT_KEYS)
    assert [key for key in outputs.OUTPUT_KEYS if outputs.foundation_makes("場所打ち杭", key)] == list(MADE)


def test_the_layers_of_a_pile_foundation_are_not_named_surface_and_support():
    data = pile_input()
    for index, layer in enumerate(data["地盤データ"]["層"]):
        layer["層番"] = f"第{index + 1}層"
    pier = parse_input(data)
    assert [layer.name for layer in pier.soil.layers] == ["第1層", "第2層"]


def test_a_direct_foundation_keeps_the_surface_and_support_layers():
    data = deepcopy(CURRENT)
    data["地盤データ"]["層"][0]["層番"] = "第1層"
    fails(data, "地盤データ.層[0].層番: 先頭は「表層」としてください")


def test_a_pile_foundation_takes_forty_layers_and_a_direct_foundation_eleven():
    data = pile_input()
    layers = data["地盤データ"]["層"]
    data["地盤データ"]["層"] = [deepcopy(layers[1]) for _ in range(40)]
    assert len(parse_input(data).soil.layers) == 40
    data["地盤データ"]["層"].append(deepcopy(layers[1]))
    fails(data, "地盤データ.層: 1～40件の配列が必要です（41件）")
    direct = deepcopy(CURRENT)
    direct["地盤データ"]["層"] = [deepcopy(direct["地盤データ"]["層"][0])] + [
        deepcopy(direct["地盤データ"]["層"][1]) for _ in range(11)]
    fails(direct, "地盤データ.層: 1～11件の配列が必要です（12件）")


@pytest.mark.parametrize("value,message", [(1.5, "地盤データ.層[1].De: 0～1 が必要です"), (-0.1, "地盤データ.層[1].De: 0以上の数値が必要です"),
                                           (0.3333, "地盤データ.層[1].De: 小数3桁までで入力してください")])
def test_the_reduction_coefficient_of_a_layer_is_from_0_to_1_at_three_digits(value, message):
    data = pile_input()
    data["地盤データ"]["層"][1]["De"] = value
    fails(data, message)


def test_a_layer_may_leave_de_blank_or_enter_it():
    data = pile_input()
    data["地盤データ"]["層"][1]["De"] = 0.333
    assert parse_input(data).soil.layers[1].reduction.value == 0.333
    data["地盤データ"]["層"][1]["De"] = None
    assert parse_input(data).soil.layers[1].reduction is None


def test_the_cohesion_of_a_layer_is_its_c():
    data = pile_input()
    data["地盤データ"]["層"][1]["粘着力_c"] = 150
    assert parse_input(data).soil.layers[1].cohesion.value == 150
    data["地盤データ"]["層"][1]["一軸圧縮強度_qu"] = 300
    fails(data, "地盤データ.層[1].一軸圧縮強度_qu: 未知の入力項目です")


def test_the_grade_of_the_steel_pipe_is_one_of_the_grades_and_may_stay_blank():
    data = pile_input("鋼管ソイルセメント杭")
    assert parse_input(data).piles.steel_soil_cement.grade == "SKK490"
    data["杭基礎"]["鋼管ソイルセメント杭"]["鋼管材質"] = None
    assert parse_input(data).piles.steel_soil_cement.grade is None  # the pile body asks for it (decision 89)
    data["杭基礎"]["鋼管ソイルセメント杭"]["鋼管材質"] = "SS400"
    fails(data, "杭基礎.鋼管ソイルセメント杭.鋼管材質")


def test_the_joint_of_the_steel_pipe_pile_is_read_and_may_stay_blank():
    data = pile_input("鋼管ソイルセメント杭")
    joint = parse_input(data).piles.steel_soil_cement.joint
    assert (joint.bar_diameter.value, joint.bar_count, joint.bar_grade) == (38, 16, "SD390")
    assert (joint.bar_centroid.value, joint.fill_fck.value) == (75.0, 27.0)
    blank = {"軸方向鉄筋": {"径": None, "本数": None, "材質": None, "重心位置": None}, "中詰めコンクリート_f'ck": None}
    data["杭基礎"]["鋼管ソイルセメント杭"]["結合部"] = blank
    joint = parse_input(data).piles.steel_soil_cement.joint
    assert joint.bar_diameter is None and joint.bar_count is None and joint.fill_fck is None  # the joint check asks


@pytest.mark.parametrize("path, value", [
    (("軸方向鉄筋", "径"), 0), (("軸方向鉄筋", "本数"), 0), (("軸方向鉄筋", "本数"), 1.5), (("軸方向鉄筋", "材質"), "SD685"),
    (("軸方向鉄筋", "重心位置"), -1.0), (("中詰めコンクリート_f'ck",), 0)])
def test_a_value_of_the_joint_outside_its_range_is_an_input_error(path, value):
    data = pile_input("鋼管ソイルセメント杭")
    node = data["杭基礎"]["鋼管ソイルセメント杭"]["結合部"]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    fails(data, "杭基礎.鋼管ソイルセメント杭.結合部." + ".".join(path))


def test_the_bars_of_the_cast_in_place_pile_are_no_item_of_the_pile_foundation_but_of_the_rebar():
    data = pile_input()
    data["杭基礎"]["場所打ち杭"]["軸方向鉄筋"] = {"径": None, "本数": None, "材質": None, "純かぶり": None}
    fails(data, "杭基礎.場所打ち杭.軸方向鉄筋: 未知の入力項目です")
