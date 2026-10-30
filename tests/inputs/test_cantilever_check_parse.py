"""The 片持ち梁の照査 section (decision 59, CONTEXT.md 片持ち梁の照査), and the bearing devices it no longer has
(decision 125).

The conditions of the cantilever beam check are one set for both overhangs: the corrosion environment of each face
(上面・下面・側面: the beam's faces differ, unlike the column's one environment), whether the appearance is checked,
and the trains of the fatigue check (列車本数, 設計耐用年数, the equivalent repetition count per train for each S-N
slope, which an external program gives). Every value may stay blank until 0900 asks for it, but the section and its
keys are required. The counts of rubber bearings and stoppers of each girder and those on the cantilever beam were
inputs of decision 59; decision 125 derives what the cantilever needs (the bearing slots and the geometry), so they
are unknown keys now.
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
SECTION = "片持ち梁の照査"
DEVICES = ("ゴム支承の箇所数", "ストッパーの箇所数", "片持ち梁上のゴム支承", "片持ち梁上のストッパー")


def data():
    return deepcopy(CURRENT)


def fails(document, message):
    with pytest.raises(InputError, match=re.escape(message)):
        parse_input(document)


def test_the_cantilever_check_conditions_of_the_current_input():
    """Example2 13_片持ち梁照査/WebDan.wdj: con_u 2, con_l 1, con_s 2, vis false; 60 and 0 trains a day, 100 years,
    10.39 repetitions per train for every slope."""
    check = parse_input(data()).cantilever_check
    assert check.environments == {"上面": "乾湿繰返し", "下面": "常時乾燥", "側面": "乾湿繰返し"}
    assert check.appearance == "行わない"
    fatigue = check.fatigue
    assert (fatigue.passenger_trains, fatigue.freight_trains, fatigue.service_life) == (60, 0, 100)
    assert fatigue.repetitions == {(train, slope): Printed(10.39, 2, "")
                                   for train in ("A列車", "B列車") for slope in ("k=0.06", "k=0.12")}


@pytest.mark.parametrize("side", ["起点側", "終点側"])
@pytest.mark.parametrize("key", DEVICES)
def test_the_bearing_device_counts_of_decision_59_are_unknown_keys(side, key):
    """Decision 125: no backward compatibility; an input that still has them is an input error."""
    assert set(CURRENT["上部構造"]["支承データ"][side]) <= {"支承名", "摩擦係数_μ", "復旧性制動係数"}
    document = data()
    document["上部構造"]["支承データ"][side][key] = None
    fails(document, f"上部構造.支承データ.{side}.{key}: 未知の入力項目です")


def test_the_conditions_may_be_blank_until_the_beam_is_checked():
    document = data()
    document[SECTION] = {"水掛かりの程度": dict.fromkeys(("上面", "下面", "側面")), "外観の照査": None,
                         "疲労": {"旅客列車本数": None, "貨物列車本数": None, "設計耐用年数": None,
                                "等価繰返し回数": {"A列車": {"k=0.06": None, "k=0.12": None},
                                             "B列車": {"k=0.06": None, "k=0.12": None}}}}
    pier = parse_input(document)
    check = pier.cantilever_check
    assert set(check.environments.values()) == {None} and check.appearance is None
    assert (check.fatigue.passenger_trains, check.fatigue.service_life) == (None, None)
    assert set(check.fatigue.repetitions.values()) == {None}


@pytest.mark.parametrize("path,value,message", [
    (("水掛かりの程度", "上面"), "厳しい環境", "「常時乾燥」「乾湿繰返し」「常時湿潤」のいずれかを選んでください"),
    (("外観の照査", ), True, "空でない文字列が必要です"),
    (("疲労", "旅客列車本数"), 60.5, "整数が必要です"),
    (("疲労", "旅客列車本数"), -1, "0～10000の整数が必要です"),
    (("疲労", "設計耐用年数"), 0, "1～1000の整数が必要です"),
    (("疲労", "等価繰返し回数", "A列車", "k=0.06"), 10.391, "小数2桁までで入力してください"),
    (("疲労", "等価繰返し回数", "B列車", "k=0.12"), -1, "0以上の数値が必要です"),
])
def test_the_conditions_are_choices_integers_and_printed_numbers(path, value, message):
    document = data()
    node = document[SECTION]
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value
    with pytest.raises(InputError, match=re.escape(f"{SECTION}.{'.'.join(path)}: ") + ".*" + re.escape(message)):
        parse_input(document)


@pytest.mark.parametrize("path", [(), ("疲労",), ("疲労", "等価繰返し回数", "A列車"), ("水掛かりの程度", "側面")])
def test_the_section_and_its_keys_are_required(path):
    document = data()
    node = document[SECTION]
    for part in path[:-1]:
        node = node[part]
    if path:
        del node[path[-1]]
    else:
        del document[SECTION]
    fails(document, f"入力項目がありません: {'.'.join((SECTION, *path))}")


def test_unknown_keys_are_rejected():
    document = data()
    document[SECTION]["疲労"]["等価繰返し回数"]["C列車"] = {"k=0.06": 1}
    fails(document, f"{SECTION}.疲労.等価繰返し回数.C列車: 未知の入力項目です")
    document = data()
    document["上部構造"]["支承データ"]["起点側"]["ゴム支承"] = 4
    fails(document, "上部構造.支承データ.起点側.ゴム支承: 未知の入力項目です")
