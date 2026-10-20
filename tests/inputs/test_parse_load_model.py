"""With a load model the items that belong to it are not read (decision 70): not checked, not needed, None."""

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.inputs import parse_input
from webpier.inputs.fields import SNOW_KEYS

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
SIDES = ("起点側", "終点側")
SPAN_KEYS = ("衝撃係数_単線終局", "曲線半径", "列車速度", "遠心作用方向")


def data():
    return deepcopy(CURRENT)


def _supports(document):
    reactions = document["上部工反力"]
    return [reactions["起点側"]["A支点"], reactions["終点側"]["D支点"]]


def _bearings(document):
    reactions = document["上部工反力"]
    return [slot for slots in (reactions["起点側"]["B支点"], reactions["終点側"]["C支点"]) for slot in slots if slot]


def test_the_load_model_items_are_none():
    pier = parse_input(data(), load_model=True)
    assert pier.train is None
    for span in (pier.spans.origin, pier.spans.end):
        assert (span.impact, span.radius, span.speed) == (None, None, None)
    assert pier.reserved.centrifugal_direction is None
    for end in (pier.reactions.a, pier.reactions.d):
        assert (end.snow2, end.snow10, end.snow30) == (None, None, None)
    bearings = [slot for slot in (*pier.reactions.b, *pier.reactions.c) if slot is not None]
    assert len(bearings) == 6
    for bearing in bearings:
        assert (bearing.snow2, bearing.snow10, bearing.snow30, bearing.shares) == (None, None, None, None)


def test_every_other_item_is_read_as_without_a_load_model():
    pier, train = parse_input(data(), load_model=True), parse_input(data())
    assert pier.substructure == train.substructure and pier.soil == train.soil and pier.rebar == train.rebar
    assert pier.spans.origin.f == train.spans.origin.f and pier.spans.end.hs == train.spans.end.hs
    assert pier.spans.end.mu == train.spans.end.mu
    assert (pier.reactions.a.d1, pier.reactions.d.d2) == (train.reactions.a.d1, train.reactions.d.d2)
    for mine, theirs in zip(pier.reactions.b, train.reactions.b, strict=True):
        assert (mine is None) == (theirs is None)
        if mine is not None:
            assert (mine.position, mine.d1, mine.d2) == (theirs.position, theirs.d1, theirs.d2)
    assert pier.reserved.skew_angle == train.reserved.skew_angle


def _garbled(document):
    """Values the train path rejects, left in the load model's items (P7: the editor keeps the train's values)."""
    document["上部構造"]["列車"] = {"車両名": "トラム", "未知": 1}
    for side in SIDES:
        span = document["上部構造"][side]
        span["衝撃係数_単線終局"], span["曲線半径"], span["列車速度"], span["遠心作用方向"] = 0.12345, -1, "速い", "↑"
    for support in _supports(document):
        support[SNOW_KEYS[0]] = 1.234
    for bearing in _bearings(document):
        bearing[SNOW_KEYS[1]] = "多い"
        bearing["列車分担"] = {"L1": 0.1234, "L3": 1.0}
    return document


def test_values_the_train_path_rejects_pass_with_a_load_model():
    with pytest.raises(InputError):
        parse_input(_garbled(data()))
    pier = parse_input(_garbled(data()), load_model=True)
    assert pier.train is None and pier.spans.origin.radius is None


def test_the_load_model_items_may_be_left_out():
    document = data()
    del document["上部構造"]["列車"]
    for side in SIDES:
        for key in SPAN_KEYS:
            del document["上部構造"][side][key]
    for item in (*_supports(document), *_bearings(document)):
        for key in SNOW_KEYS:
            del item[key]
    for bearing in _bearings(document):
        del bearing["列車分担"]
    with pytest.raises(InputError, match=re.escape("入力項目がありません: 上部構造.起点側.衝撃係数_単線終局")):
        parse_input(document)
    pier = parse_input(document, load_model=True)
    assert pier.train is None and pier.reactions.b[0].shares is None


def test_an_unknown_key_is_still_an_error():
    document = data()
    document["上部構造"]["起点側"]["列車荷重"] = 1.0
    with pytest.raises(InputError, match=re.escape("上部構造.起点側.列車荷重: 未知の入力項目です")):
        parse_input(document, load_model=True)
    document = data()
    document["上部工反力"]["終点側"]["C支点"][0]["雪"] = 1.0
    with pytest.raises(InputError, match=re.escape("上部工反力.終点側.C支点[0].雪: 未知の入力項目です")):
        parse_input(document, load_model=True)


def test_an_item_outside_the_load_model_is_still_checked():
    document = data()
    document["上部工反力"]["起点側"]["B支点"][0]["固定死荷重_D1"] = 1.234
    with pytest.raises(InputError, match=re.escape("上部工反力.起点側.B支点[0].固定死荷重_D1")):
        parse_input(document, load_model=True)
