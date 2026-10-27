"""One validator for every input path, with the full Japanese path in each error."""

import math
import re

import pytest

from webpier.core.errors import InputError
from webpier.core.printed import LENGTH, Printed
from webpier.core.reader import AbsentAsBlank, Reader

DATA = {
    "下部構造": {"寸法": {"B1": 2.7, "B2": 0, "B9": None, "負": -1.5, "真": True, "文字": "2"},
                "層": [{"名前": "表層", "空白": " 表層", "空": ""}, None]},
    "編成数": 10,
}


def read(*keys):
    return Reader(DATA).at(*keys)


def test_at_walks_dicts_and_lists_and_builds_the_path():
    reader = read("下部構造", "層", 0, "名前")
    assert (reader.value, reader.path) == ("表層", "下部構造.層[0].名前")


@pytest.mark.parametrize("keys,path", [
    (("下部構造", "無い"), "下部構造.無い"),
    (("下部構造", "層", 5), "下部構造.層[5]"),
    (("下部構造", "寸法", "B1", "x"), "下部構造.寸法.B1.x"),
    (("下部構造", "層", "x"), "下部構造.層.x"),
])
def test_missing_items_name_the_full_path(keys, path):
    with pytest.raises(InputError, match=re.escape(f"入力項目がありません: {path}")):
        read(*keys)


def test_number_defaults_to_non_negative():
    assert read("下部構造", "寸法", "B1").number() == 2.7
    assert read("下部構造", "寸法", "B2").number() == 0.0
    with pytest.raises(InputError, match="下部構造.寸法.負: 0以上"):
        read("下部構造", "寸法", "負").number()


def test_number_sign_options():
    assert read("下部構造", "寸法", "負").number(sign="any") == -1.5
    with pytest.raises(InputError, match="正の数値"):
        read("下部構造", "寸法", "B2").number(sign="positive")


@pytest.mark.parametrize("key,message", [
    ("B9", "値が必要です"),
    ("真", "有限の数値"),
    ("文字", "有限の数値"),
])
def test_number_rejects_null_bool_and_text(key, message):
    with pytest.raises(InputError, match=f"下部構造.寸法.{key}: {message}"):
        read("下部構造", "寸法", key).number()


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 10 ** 400])
def test_number_rejects_non_finite_and_huge(value):
    with pytest.raises(InputError, match="x: 有限の数値"):
        Reader({"x": value}).at("x").number(sign="any")


def test_number_rejects_an_unknown_sign_option():
    with pytest.raises(ValueError):
        read("下部構造", "寸法", "B1").number(sign="negative")


def test_printed_accepts_values_already_at_the_printed_digits():
    assert read("下部構造", "寸法", "B1").printed(LENGTH) == Printed(2.7, 3, "m")
    with pytest.raises(InputError, match="h: 小数3桁までで入力してください"):
        Reader({"h": 2.9520833333333334}).at("h").printed(LENGTH)


def test_printed_applies_the_sign_rule_too():
    with pytest.raises(InputError, match="0以上"):
        read("下部構造", "寸法", "負").printed(LENGTH)
    assert read("下部構造", "寸法", "負").printed(LENGTH, sign="any").value == -1.5


def test_optional_distinguishes_absent_from_present():
    dims = read("下部構造", "寸法")
    assert dims.optional("B9") is None
    assert dims.optional("無い") is None
    assert dims.optional("B1").number() == 2.7
    assert read("下部構造", "層", 1).is_null


def test_integer_range():
    assert read("編成数").integer(1, 200) == 10
    with pytest.raises(InputError, match="編成数: 1～5の整数"):
        read("編成数").integer(1, 5)
    with pytest.raises(InputError, match="1～200の整数"):
        Reader({"編成数": 10.0}).at("編成数").integer(1, 200)
    with pytest.raises(InputError, match="1～200の整数"):
        Reader({"編成数": True}).at("編成数").integer(1, 200)


def test_text_requires_non_empty_without_surrounding_spaces():
    assert read("下部構造", "層", 0, "名前").text() == "表層"
    with pytest.raises(InputError, match="空白"):
        read("下部構造", "層", 0, "空白").text()
    with pytest.raises(InputError, match="空でない文字列"):
        read("下部構造", "層", 0, "空").text()
    with pytest.raises(InputError, match="空でない文字列"):
        read("下部構造", "寸法", "B1").text()


def test_choice_lists_the_valid_options():
    assert read("下部構造", "層", 0, "名前").choice(("表層", "支持層")) == "表層"
    with pytest.raises(InputError, match="「表層」「支持層」のいずれか"):
        Reader({"x": "砂"}).at("x").choice(("表層", "支持層"))


def test_items_reads_a_list_with_indexed_paths():
    items = read("下部構造", "層").items()
    assert [item.path for item in items] == ["下部構造.層[0]", "下部構造.層[1]"]
    with pytest.raises(InputError, match="下部構造.寸法: 配列が必要です"):
        read("下部構造", "寸法").items()
    assert len(read("下部構造", "層").items(minimum=2, maximum=3)) == 2
    with pytest.raises(InputError, match=re.escape("a: 2～3件の配列が必要です")):
        Reader({"a": [1]}).at("a").items(minimum=2, maximum=3)


def test_mapping_requires_an_object():
    assert read("下部構造").mapping() is DATA["下部構造"]
    with pytest.raises(InputError, match="編成数: オブジェクトが必要です"):
        read("編成数").mapping()


def test_input_error_is_a_value_error():
    assert issubclass(InputError, ValueError)


def test_only_rejects_unknown_keys_by_full_path():
    reader = Reader({"寸法": {"B1": 1, "B10": 2}}).at("寸法")
    assert reader.only("B1", "B10") is reader
    with pytest.raises(InputError, match=re.escape("寸法.B10: 未知の入力項目です")):
        reader.only("B1", "B2")


def test_only_requires_an_object():
    with pytest.raises(InputError, match="オブジェクトが必要です"):
        Reader({"a": 1}).at("a").only("x")


def test_absent_as_blank_reads_an_absent_item_as_blank():
    """Decision 107: a part the input does not use (杭基礎 of a 直接基礎) may lack items."""
    reader = AbsentAsBlank(DATA)
    assert reader.at("杭基礎", "杭長").is_null and reader.at("杭基礎", "杭長").path == "杭基礎.杭長"
    assert reader.at("無い").path == "無い" and reader.at("下部構造", "層", 5).path == "下部構造.層[5]"
    assert reader.at("杭基礎").mapping() == {} and reader.at("杭基礎", "配置").items() == []
    assert reader.at("杭基礎").only("杭長") is not None and reader.at("下部構造").optional("無い") is None


def test_absent_as_blank_reads_what_is_written_as_strictly_as_reader():
    reader = AbsentAsBlank(DATA)
    assert reader.at("下部構造", "寸法", "B1").number() == 2.7
    assert [item.value for item in reader.at("下部構造", "層").items()][1] is None
    with pytest.raises(InputError, match=re.escape("下部構造.寸法.文字: 有限の数値が必要です")):
        reader.at("下部構造", "寸法", "文字").number()
    with pytest.raises(InputError, match=re.escape("下部構造.寸法.未知: 未知の入力項目です")):
        AbsentAsBlank({"下部構造": {"寸法": {"未知": 1}}}).at("下部構造", "寸法").only("B1")
    with pytest.raises(InputError, match=re.escape("編成数: オブジェクトが必要です")):
        reader.at("編成数").mapping()
