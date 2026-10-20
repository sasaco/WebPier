"""The field table: one definition of every scalar input, read by the parser and by the editor."""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.core.printed import Precision, Printed
from webpier.core.reader import Reader
from webpier.inputs import fields, parse_input
from webpier.inputs.fields import Field, field, path_text, pattern, read

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
NOT_FIELDS = ("出典", "schema_version", "鉄筋.version")


def data():
    return deepcopy(CURRENT)


def leaves(value, path=()):
    """Every scalar of the document with its key path."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaves(item, (*path, index))
    else:
        yield path, value


def scalar_leaves():
    for path, value in leaves(CURRENT):
        text = path_text(path)
        if not text.startswith(NOT_FIELDS) and value is not ...:
            if pattern(text) in fields.FIELDS:
                yield path, value


def put(document, path, value):
    owner = document
    for key in path[:-1]:
        owner = owner[key]
    owner[path[-1]] = value


def error_of(document):
    try:
        parse_input(document)
    except InputError as exc:
        return str(exc)
    return None


def test_paths_are_written_as_input_errors_name_them():
    assert path_text(("上部工反力", "起点側", "B支点", 3, "支承位置")) == "上部工反力.起点側.B支点[3].支承位置"
    assert path_text(()) == ""
    assert (pattern("鉄筋.柱.main_bars.線路.inner_layers[12].clear_gap_mm")
            == "鉄筋.柱.main_bars.線路.inner_layers[*].clear_gap_mm")


def test_a_field_is_found_by_text_or_keys_and_unknown_paths_are_named():
    assert field("上部構造.列車.1両の長さ") is field(("上部構造", "列車", "1両の長さ"))
    assert field(("上部工反力", "終点側", "C支点", 9, "列車分担", "L1")).precision == fields.RATIO
    with pytest.raises(KeyError, match="入力項目の定義がありません: 上部構造.列車.車両色"):
        field("上部構造.列車.車両色")


def test_every_scalar_of_the_input_has_a_field():
    missing = [path_text(path) for path, _ in leaves(CURRENT)
               if not path_text(path).startswith(NOT_FIELDS) and pattern(path_text(path)) not in fields.FIELDS]
    # An empty bearing slot is a null object, not a field (CONTEXT.md 空き支承枠).
    assert set(missing) == {f"上部工反力.起点側.B支点[{index}]" for index in range(4, 10)} | {
        f"上部工反力.終点側.C支点[{index}]" for index in range(2, 10)}


def test_units_come_from_the_program():
    assert field("下部構造.寸法.側面.B1").unit == "m"
    assert field("上部工反力.起点側.A支点.固定死荷重_D1").unit == "kN"
    assert field("鉄筋.柱.pure_cover_mm").unit == "mm"
    assert field("上部構造.支承データ.起点側.支承名").unit == ""
    assert not any("単位" in key.split(".") for key in fields.FIELDS)  # decision 19: no 単位 in the JSON


def test_reserved_fields_are_marked():
    reserved = {key for key, spec in fields.FIELDS.items() if spec.reserved}
    assert reserved == {
        "下部構造.斜角.θ", "下部構造.斜角.タイプ", "下部構造.単位体積重量.杭.鉛直重量", "下部構造.単位体積重量.杭.慣性力",
        "下部構造.杭種", "下部構造.場所打ち杭の施工条件", "下部構造.杭の配置[*].線路方向.X",
        "下部構造.杭の配置[*].線路方向.本数", "下部構造.杭の配置[*].線路直角方向.Y",
        "下部構造.杭の配置[*].線路直角方向.本数", "上部構造.起点側.遠心作用方向", "上部構造.終点側.遠心作用方向"}


def test_the_third_and_fourth_track_are_blank_fields():
    assert field("上部工反力.起点側.B支点[0].列車分担.L3").kind == "blank"
    assert field("上部工反力.終点側.C支点[4].列車分担.L4").message == "3線以上は未対応です"


# The parser reads every scalar through the table, so the table's rules are the parser's rules.

NUMBERS = [(path, value) for path, value in scalar_leaves()
           if field(path).kind == "number" and isinstance(value, (int, float))]


@pytest.mark.parametrize("path,value", NUMBERS, ids=lambda item: path_text(item) if isinstance(item, tuple) else "")
def test_a_value_finer_than_the_printed_digits_is_an_input_error(path, value):
    spec = field(path)
    document = data()
    finer = value + (1 if value >= 0 else -1) * 10 ** -(spec.precision.digits + 1) * 4
    put(document, path, finer)
    assert error_of(document).startswith(f"{path_text(path)}: 小数{spec.precision.digits}桁までで入力してください")


@pytest.mark.parametrize("path,value", NUMBERS, ids=lambda item: path_text(item) if isinstance(item, tuple) else "")
def test_the_sign_rule_of_each_number(path, value):
    spec = field(path)
    document = data()
    if spec.sign == "positive":
        put(document, path, 0)
        assert error_of(document) == f"{path_text(path)}: 正の数値が必要です"
    elif spec.sign == "nonnegative":
        put(document, path, -1)
        assert error_of(document) == f"{path_text(path)}: 0以上の数値が必要です"
    else:
        put(document, path, -1)
        assert not (error_of(document) or "").startswith(path_text(path) + ":")


# Blanks the table allows that the parser still asks for, because of the row they are on.
CONTEXT_REQUIRED = {"地盤データ.層[0].単位体積重量.湿潤", "地盤データ.層[0].単位体積重量.水中",
                    "地盤データ.層[1].内部摩擦角_φd", "地盤データ.層[1].変形係数_Ed"}


@pytest.mark.parametrize("path", [path for path, value in scalar_leaves() if value is not None],
                         ids=lambda item: path_text(item))
def test_a_blank_is_allowed_exactly_where_the_table_says(path):
    document = data()
    put(document, path, None)
    message = error_of(document)
    if field(path).nullable and path_text(path) not in CONTEXT_REQUIRED:
        assert message is None or not message.startswith(path_text(path) + ":")
    else:
        assert message.startswith(path_text(path) + ":")


CHOICES = [path for path, value in scalar_leaves() if field(path).kind == "choice" and value is not None]


@pytest.mark.parametrize("path", CHOICES, ids=lambda item: path_text(item))
def test_choices_are_the_programs_lists(path):
    document = data()
    put(document, path, "その他")
    listed = "".join(f"「{option}」" for option in field(path).choices)
    message = error_of(document)
    assert message == f"{path_text(path)}: {listed}のいずれかを選んでください（入力: 'その他'）" or (
        path_text(path) == "上部構造.列車.車両名" and message == "上部構造.列車.車両名: 「EA-17」「P-16」のいずれかを選んでください（入力: 'その他'）")


def test_the_table_drives_the_parser(monkeypatch):
    document = data()
    document["上部構造"]["列車"]["1両の長さ"] = 20.05
    assert error_of(document) is None
    monkeypatch.setitem(fields.FIELDS, "上部構造.列車.1両の長さ", fields.number(Precision(1, "m"), "positive"))
    assert error_of(document) == "上部構造.列車.1両の長さ: 小数1桁までで入力してください（入力: 20.05）"


# Field.read, one kind at a time.

def reader(value, path="x"):
    return Reader(value, path)


def test_read_a_number_at_its_digits_with_its_limit():
    spec = fields.number(fields.FRICTION_ANGLE, nullable=True, limit=fields.below(90, "90度未満が必要です"))
    assert spec.read(reader(42.2)) == Printed(42.2, 1, "°")
    assert spec.read(reader(None)) is None
    with pytest.raises(InputError, match=re.escape("x: 90度未満が必要です")):
        spec.read(reader(90))


def test_read_a_required_number_reports_the_blank():
    with pytest.raises(InputError, match="x: 値が必要です"):
        fields.number(fields.LENGTH).read(reader(None))


@pytest.mark.parametrize("limit,good,bad,message", [
    (fields.at_most(99.99), 99.99, 100, "99.99以下が必要です"),
    (fields.within(0.1, 999_999, "mm"), 0.1, 0, "0.1～999999 mmが必要です"),
])
def test_limits(limit, good, bad, message):
    spec = fields.number(Precision(2, ""), "any", limit=limit)
    assert spec.read(reader(good)).value == good
    with pytest.raises(InputError, match=re.escape(f"x: {message}")):
        spec.read(reader(bad))


def test_read_integers_choices_text_and_blank_fields():
    assert fields.integer(1, 200).read(reader(10)) == 10
    with pytest.raises(InputError, match="1～200の整数が必要です"):
        fields.integer(1, 200).read(reader(10.0))
    assert fields.choice(("固定", "可動")).read(reader("可動")) == "可動"
    assert fields.choice(("固定", "可動"), nullable=True).read(reader(None)) is None
    assert fields.TEXT.read(reader("表層")) == "表層"
    blank = Field("blank", message="3線以上は未対応です")
    assert blank.read(reader(None)) is None
    with pytest.raises(InputError, match="x: 3線以上は未対応です"):
        blank.read(reader(0.0))


def test_read_looks_the_field_up_by_the_path():
    root = Reader(data())
    assert read(root.at("上部構造", "列車", "編成数")) == 10
    assert read(root.at("上部工反力", "起点側", "B支点", 0, "支承位置")) == Printed(-3.8, 3, "m")


def test_rules_of_a_row_stay_in_the_parser():
    # The table lets 変形係数_Ed stay blank; the support layer needs a positive one.
    document = data()
    document["地盤データ"]["層"][1]["変形係数_Ed"] = 0
    assert error_of(document) == "地盤データ.層[1].変形係数_Ed: 正の数値が必要です"
    document["地盤データ"]["層"][1]["変形係数_Ed"] = None
    assert error_of(document) == "地盤データ.層[1].変形係数_Ed: 値が必要です"


def test_the_table_drives_the_rebar_parser(monkeypatch):
    document = data()
    document["鉄筋"]["柱"]["pure_cover_mm"] = 70.5
    assert error_of(document) is None
    monkeypatch.setitem(fields.FIELDS, "鉄筋.柱.pure_cover_mm", fields.number(Precision(0, "mm"), nullable=True))
    assert error_of(document) == "鉄筋.柱.pure_cover_mm: 小数0桁までで入力してください（入力: 70.5）"
