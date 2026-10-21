"""The 柱の断面照査 section and the column's 粗骨材最大寸法 (decision 48, CONTEXT.md 柱の断面照査).

One set of conditions for the column, shared by both directions: the corrosion environment (one for the column, not
per face), whether the appearance is checked, ε'csd, the body whose standard applies, and whether JR-001 and JR-004
are adopted. The choices belong to the program (decision 6). Every value may stay blank until 0611 asks for it, but
the section and its keys are required. Dmax is a property of the column concrete (鉄筋.柱.aggregate_max_mm) and, for the
cantilever beam, of the beam concrete (鉄筋.梁.aggregate_max_mm, decision 59); the JRSNAP conditions no longer hold it
(no compatibility reading).
"""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import choices, parse_input

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
SECTION = "柱の断面照査"
KEYS = ("鋼材の腐食に対する環境条件", "外観の照査", "ε'csd", "適用基準の機関", "JR-001", "JR-004")


def data():
    return deepcopy(CURRENT)


def fails(document, message):
    with pytest.raises(InputError, match=re.escape(message)):
        parse_input(document)


def test_the_column_check_conditions_of_the_current_input():
    """Example2 08_線路/WebDan.wdj: con 1 (一般の環境), vis true, ecsd 300, 運輸機構, JR-001 yes, JR-004 no."""
    check = parse_input(data()).column_check
    assert check.environment == "一般の環境"
    assert check.appearance == "行う"
    assert check.ecsd == Printed(300, 0, "×10⁻⁶")
    assert check.body == "運輸機構"
    assert (check.jr001, check.jr004) == ("適用する", "適用しない")


def test_the_choices_belong_to_the_program():
    assert choices.CORROSION_ENVIRONMENTS == ("一般の環境", "腐食性環境", "特に厳しい腐食性環境")
    assert choices.APPEARANCE_CHECKS == ("行う", "行わない")
    assert choices.STANDARD_BODIES == ("運輸機構", "JR各社", "JR東日本")
    assert choices.ADOPTIONS == ("適用する", "適用しない")


def test_the_conditions_may_be_blank_until_the_column_is_checked():
    document = data()
    document[SECTION] = dict.fromkeys(KEYS)
    check = parse_input(document).column_check
    assert (check.environment, check.appearance, check.ecsd, check.body, check.jr001, check.jr004) == (None,) * 6


@pytest.mark.parametrize("key,value,message", [
    ("鋼材の腐食に対する環境条件", "厳しい環境", "「一般の環境」「腐食性環境」「特に厳しい腐食性環境」のいずれかを選んでください"),
    ("外観の照査", True, "空でない文字列が必要です"),  # a choice, not a boolean
    ("適用基準の機関", "JR西日本", "「運輸機構」「JR各社」「JR東日本」のいずれかを選んでください"),
    ("JR-001", "する", "「適用する」「適用しない」のいずれかを選んでください"),
    ("JR-004", False, "空でない文字列が必要です"),
])
def test_the_conditions_are_choices(key, value, message):
    document = data()
    document[SECTION][key] = value
    with pytest.raises(InputError, match=re.escape(f"{SECTION}.{key}: ") + ".*" + re.escape(message)):
        parse_input(document)


@pytest.mark.parametrize("value,message", [
    (-1, "0以上の数値が必要です"),
    (300.5, "小数0桁までで入力してください"),
])
def test_ecsd_is_a_nonnegative_whole_number(value, message):
    document = data()
    document[SECTION]["ε'csd"] = value
    fails(document, f"{SECTION}.ε'csd: {message}")


def test_the_conditions_are_one_required_section_of_six_keys():
    document = data()
    document[SECTION]["JR-003"] = "適用する"  # 円形断面: not an input (the column is rectangular)
    fails(document, f"{SECTION}.JR-003: 未知の入力項目です")
    for key in KEYS:
        document = data()
        del document[SECTION][key]
        fails(document, f"入力項目がありません: {SECTION}.{key}")
    document = data()
    del document[SECTION]
    fails(document, f"入力項目がありません: {SECTION}")


def test_the_aggregate_size_is_a_property_of_the_column_concrete():
    assert parse_input(data()).rebar.column.aggregate_max == Printed(25, 1, "mm")
    document = data()
    document["鉄筋"]["柱"]["aggregate_max_mm"] = None
    assert parse_input(document).rebar.column.aggregate_max is None
    document = data()
    del document["鉄筋"]["柱"]["aggregate_max_mm"]
    fails(document, "入力項目がありません: 鉄筋.柱.aggregate_max_mm")


@pytest.mark.parametrize("value,message", [
    (0.05, "小数1桁までで入力してください"),
    (1_000_000, "0.1～999999 mmが必要です"),
    (0, "0.1～999999 mmが必要です"),
])
def test_the_aggregate_size_range(value, message):
    document = data()
    document["鉄筋"]["柱"]["aggregate_max_mm"] = value
    fails(document, f"鉄筋.柱.aggregate_max_mm: {message}")


def test_the_beam_concrete_has_its_own_aggregate_size():
    """Decision 59: the cantilever beam's Dmax is the beam concrete's, not the column's."""
    assert parse_input(data()).rebar.beam.aggregate_max == Printed(25, 1, "mm")
    document = data()
    document["鉄筋"]["梁"]["aggregate_max_mm"] = None
    assert parse_input(document).rebar.beam.aggregate_max is None
    document = data()
    del document["鉄筋"]["梁"]["aggregate_max_mm"]
    fails(document, "入力項目がありません: 鉄筋.梁.aggregate_max_mm")


def test_the_footing_concrete_has_its_own_aggregate_size():
    """Decision 60 (owner 2026-10-19): the footing's Dmax is the footing concrete's, not the column's; the fixture
    has the 25 of pre/input.json (decision 73: the footing bars of 0400) and may leave it blank."""
    assert parse_input(data()).rebar.footing.aggregate_max == Printed(25, 1, "mm")
    document = data()
    document["鉄筋"]["フーチング"]["aggregate_max_mm"] = None
    assert parse_input(document).rebar.footing.aggregate_max is None
    document = data()
    del document["鉄筋"]["フーチング"]["aggregate_max_mm"]
    fails(document, "入力項目がありません: 鉄筋.フーチング.aggregate_max_mm")


@pytest.mark.parametrize("path", [("jrsnap_longitudinal",), ("jrsnap_transverse",)])
def test_no_other_place_holds_an_aggregate_size(path):
    document = data()
    node = document
    for part in path:
        node = node[part]
    node["aggregate_max_mm"] = 25
    fails(document, f"{'.'.join(path)}.aggregate_max_mm: 未知の入力項目です")
