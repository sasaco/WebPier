"""Bearing slots and the explicit "B7と同じ" / "B/Cと同じ" values (decision 5, CONTEXT.md 空き支承枠)."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.gui import bearings
from webpier.gui.document import EditorError
from webpier.inputs import parse_input

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))


def data():
    return deepcopy(CURRENT)


def test_typing_into_an_empty_slot_creates_the_bearing_with_blanks():
    document = data()
    bearings.set_value(document, "起点側", 5, ("支承位置",), 4.2)
    slot = document["上部工反力"]["起点側"]["B支点"][5]
    assert slot["支承位置"] == 4.2 and slot["固定死荷重_D1"] is None
    assert slot["列車分担"] == {"L1": None, "L2": None, "L3": None, "L4": None}
    assert bearings.state(slot) == "partial"
    assert bearings.missing(document, "起点側", 5) == [  # a blank snow load is 0, not missing (decision 62)
        ("上部工反力", "起点側", "B支点", 5, key) for key in ("固定死荷重_D1", "付加死荷重_D2")] + [
        ("上部工反力", "起点側", "B支点", 5, "列車分担", "L1"), ("上部工反力", "起点側", "B支点", 5, "列車分担", "L2")]
    with pytest.raises(Exception, match=r"上部工反力.起点側.B支点\[5\].固定死荷重_D1: 値が必要です"):
        parse_input(document)


def test_clearing_every_value_empties_the_slot_again():
    document = data()
    bearings.set_value(document, "終点側", 2, ("列車分担", "L1"), 0.5)
    bearings.set_value(document, "終点側", 2, ("列車分担", "L1"), None)
    assert document["上部工反力"]["終点側"]["C支点"][2] is None
    assert bearings.state(None) == "empty"
    assert bearings.missing(document, "終点側", 2) == []
    parse_input(document)


def test_a_complete_slot():
    document = data()
    assert bearings.state(document["上部工反力"]["起点側"]["B支点"][0]) == "complete"
    bearings.set_value(document, "起点側", 0, ("固定死荷重_D1",), 1600.0)
    assert document["上部工反力"]["起点側"]["B支点"][0]["固定死荷重_D1"] == 1600.0


def test_b9_same_as_b7_writes_the_value():
    document = data()
    document["下部構造"]["寸法"]["側面"]["B7"] = 2.3
    assert bearings.same_as_b7(document) == 2.3
    assert document["下部構造"]["寸法"]["側面"]["B9"] == 2.3
    document["下部構造"]["寸法"]["側面"]["B7"] = None
    with pytest.raises(EditorError, match="下部構造.寸法.側面.B7: 値が必要です"):
        bearings.same_as_b7(document)


def test_end_totals_same_as_the_bearings():
    document = data()
    document["上部工反力"]["起点側"]["A支点"] = dict.fromkeys(bearings.LOAD_KEYS)
    totals = bearings.same_as_bearings(document, "起点側")
    assert totals == {"固定死荷重_D1": 5740.0, "付加死荷重_D2": 520.0, "雪荷重_2年確率": 460.0,
                      "雪荷重_10年確率": 740.0, "雪荷重_30年確率": 820.0}
    assert document["上部工反力"]["起点側"]["A支点"] == totals
    assert bearings.same_as_bearings(document, "終点側")["固定死荷重_D1"] == 1860.0
    parse_input(document)


def test_end_totals_add_the_printed_values():
    document = data()
    document["上部工反力"]["終点側"]["C支点"][0]["固定死荷重_D1"] = 0.1
    document["上部工反力"]["終点側"]["C支点"][1]["固定死荷重_D1"] = 0.2
    assert bearings.same_as_bearings(document, "終点側")["固定死荷重_D1"] == 0.3


def test_end_totals_take_a_blank_snow_load_as_zero():
    # decision 62: one blank adds 0; every bearing blank leaves the total blank (no snow)
    document = data()
    slots = document["上部工反力"]["終点側"]["C支点"]
    expected = slots[0]["雪荷重_2年確率"]
    slots[1]["雪荷重_2年確率"] = None
    for slot in slots[:2]:
        slot["雪荷重_10年確率"] = None
    totals = bearings.same_as_bearings(document, "終点側")
    assert (totals["雪荷重_2年確率"], totals["雪荷重_10年確率"]) == (expected, None)
    assert bearings.state(slots[1]) == "complete" and bearings.missing(document, "終点側", 1) == []
    parse_input(document)


def test_end_totals_need_complete_bearings():
    document = data()
    document["上部工反力"]["終点側"]["C支点"][1]["付加死荷重_D2"] = None
    with pytest.raises(EditorError, match=r"上部工反力.終点側.C支点\[1\].付加死荷重_D2: 値が必要です"):
        bearings.same_as_bearings(document, "終点側")
    document["上部工反力"]["終点側"]["C支点"] = [None] * 10
    with pytest.raises(EditorError, match="上部工反力.終点側.C支点: 支承がありません"):
        bearings.same_as_bearings(document, "終点側")
    assert document["上部工反力"]["終点側"]["D支点"]["固定死荷重_D1"] == 1860.0  # nothing was written
