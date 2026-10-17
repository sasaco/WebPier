"""Entering a value: rounded to the printed digits at entry (decision 17), choices from the program (decision 6)."""

import pytest

from webpier.core.printed import Precision
from webpier.inputs import fields
from webpier.inputs.fields import field
from webpier.gui.entry import EntryError, display, enter, problem

LENGTH = field("下部構造.寸法.側面.B1")  # 3 digits, positive


@pytest.mark.parametrize("text,value", [
    ("2.7", 2.7), ("2.7004", 2.7), ("2.7005", 2.701), (" 2.70049 ", 2.7), ("２．７", 2.7), ("1e1", 10.0)])
def test_a_length_is_rounded_half_away_at_entry(text, value):
    assert enter(LENGTH, text) == value
    assert type(enter(LENGTH, text)) is float


def test_negative_values_round_away_from_zero_and_keep_their_sign_rule():
    position = field("上部工反力.起点側.B支点[0].支承位置")  # any sign
    assert enter(position, "-3.8005") == -3.801
    assert enter(position, "−1.5") == -1.5  # U+2212 from Japanese input
    with pytest.raises(EntryError, match="0以上の数値が必要です"):
        enter(field("下部構造.寸法.側面.B2"), "-0.01")
    assert enter(field("下部構造.寸法.側面.B2"), "-0.0004") == 0.0  # rounds to zero, which is allowed


def test_the_sign_rule_applies_to_the_rounded_value():
    with pytest.raises(EntryError, match="正の数値が必要です"):
        enter(LENGTH, "0.0004")


def test_zero_digit_numbers_are_stored_as_integers():
    speed = field("上部構造.起点側.列車速度")
    assert enter(speed, "349.5") == 350 and type(enter(speed, "349.5")) is int
    assert display(speed, 350) == "350"


def test_limits_of_the_table_apply_at_entry():
    with pytest.raises(EntryError, match="90度未満が必要です"):
        enter(field("地盤データ.層[1].内部摩擦角_φd"), "89.96")
    assert enter(field("jrsnap_longitudinal.shear_factor_vcd"), "99.994") == 99.99
    with pytest.raises(EntryError, match="99.99以下が必要です"):
        enter(field("jrsnap_longitudinal.shear_factor_vcd"), "99.995")


@pytest.mark.parametrize("text", ["abc", "nan", "inf", "1e999", "--1"])
def test_text_that_is_not_a_finite_number_is_refused(text):
    with pytest.raises(EntryError, match="数値を入力してください"):
        enter(LENGTH, text)


def test_a_blank_is_stored_as_null_and_reported_where_a_value_is_required():
    assert enter(LENGTH, "  ") is None
    assert problem(LENGTH, None) == "値が必要です"
    assert problem(field("上部構造.支承データ.起点側.復旧性制動係数"), None) is None


def test_integers():
    cars = field("上部構造.列車.編成数")
    assert enter(cars, "10") == 10
    assert enter(cars, "１０") == 10
    for text in ("10.5", "x"):
        with pytest.raises(EntryError, match="整数を入力してください"):
            enter(cars, text)
    with pytest.raises(EntryError, match="1～200の整数が必要です"):
        enter(cars, "0")
    assert display(cars, 10) == "10"


def test_choices_come_from_the_program():
    vehicle = field("上部構造.列車.車両名")
    assert enter(vehicle, "EA-17") == "EA-17"
    with pytest.raises(EntryError, match="「EA-17」「P-16」のいずれかを選んでください"):
        enter(vehicle, "M-18")


def test_text_is_trimmed():
    assert enter(field("地盤データ.層[0].層番"), " 表層 ") == "表層"


def test_blank_fields_cannot_be_given_a_value():
    track = field("上部工反力.起点側.B支点[0].列車分担.L3")
    assert enter(track, "") is None
    with pytest.raises(EntryError, match="3線以上は未対応です"):
        enter(track, "0.1")


def test_display_shows_the_printed_digits():
    assert display(LENGTH, 2.7) == "2.700"
    assert display(field("上部工反力.起点側.A支点.固定死荷重_D1"), 5740.0) == "5740.00"
    assert display(LENGTH, None) == ""
    # A hand-edited value finer than the digits is shown as it is, so the error is visible.
    assert display(LENGTH, 2.70049) == "2.70049"
    assert problem(LENGTH, 2.70049) == "小数3桁までで入力してください（入力: 2.70049）"
    assert display(LENGTH, "x") == "x"
    assert problem(LENGTH, 2.7) is None


def test_entry_follows_the_table(monkeypatch):
    monkeypatch.setitem(fields.FIELDS, "下部構造.寸法.側面.B1", fields.number(Precision(1, "m"), "positive"))
    assert enter(field("下部構造.寸法.側面.B1"), "2.75") == 2.8
