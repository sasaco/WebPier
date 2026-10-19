"""The horizontal forces at the bearings and their share on the cantilever (decision 59; Example2 13-16 .. 13-22,
13-28, 13-29): rubber bearings and stoppers of each girder, the four combinations and the seismic case."""

from __future__ import annotations

import re

import pytest

from cantilever_support import KH, SAMPLE, D, pier, q, reaction_of, value
from webpier.calc.cantilever.bearings import COMBINATIONS, SEISMIC, bearing_cases, label, seismic_girder_force
from webpier.calc.moving_load import Girder
from webpier.calc.reaction.longitudinal import BearingType, LongitudinalCase
from webpier.core.errors import InputError
from webpier.core.printed import LENGTH

Y = LENGTH(1.35)


@pytest.fixture(scope="module")
def cases():
    pier_input = pier()
    reaction = reaction_of(pier_input)
    return reaction, bearing_cases(pier_input, reaction.longitudinal, KH(0.386), Y)


def test_the_four_combinations_and_the_seismic_case_in_report_order(cases):
    reaction, found = cases
    assert [case.case for case in found] == [*COMBINATIONS, None]
    assert [case.label for case in found] == ["1.0 LR + 1.23B", "1.1 LR + 1.23B", "1.0 LR + 1.35B", "1.0 LR", SEISMIC]
    assert label(LongitudinalCase.SAFETY_LR10, reaction.longitudinal) == "1.0 LR"


def test_the_movable_origin_girder_loads_its_rubber_bearings_by_friction(cases):
    reaction, found = cases
    first = found[0]
    expected = SAMPLE["bearing_forces"]["1.0 LR + 1.23B"]["origin"]
    origin = first.origin
    assert origin.girder is Girder.ORIGIN and origin.bearing is BearingType.MOVABLE
    assert origin.applied.value == expected["T"] and origin.vertical.value == expected["Rm"]  # 0600's Rm
    assert origin.friction.value == expected["Hbd"] and origin.candidate is None
    assert origin.rubber.total.value == expected["Hbd"] and origin.stopper.total.value == expected["Hsd"]
    assert (origin.rubber.count, origin.rubber.on_cantilever) == (4, 1)
    assert origin.rubber.each.value == expected["per_rubber"]  # 857.70 / 4
    assert value(origin.rubber.each) == q(D(857.70) / 4, 2)
    assert origin.rubber.force.value == expected["per_rubber"] and origin.rubber.arm == Y
    assert value(origin.rubber.moment) == q(D(214.43) * D(1.35), 2) == D(SAMPLE["bearing_forces"]["cantilever_moments"]["1.0 LR + 1.23B"]["Mt"])
    assert (origin.stopper.count, origin.stopper.on_cantilever, origin.stopper.each.value, origin.stopper.force.value) == (
        3, 1, 0.0, 0.0)
    # the values are 0600's
    force = reaction.longitudinal.case(LongitudinalCase.SAFETY_LR10_B10).origin
    assert (origin.applied, origin.vertical, origin.friction, origin.share) == (
        force.applied, force.vertical, force.friction, force.share)


def test_the_fixed_end_girder_loads_its_stoppers(cases):
    reaction, found = cases
    end = found[0].end
    expected = SAMPLE["bearing_forces"]["1.0 LR + 1.23B"]["end"]
    assert end.bearing is BearingType.FIXED and end.applied.value == expected["T"]
    assert end.vertical.value == expected["Rm"] and end.friction is None
    assert end.candidate.value == expected["candidate"] and end.share.value == expected["share"]
    assert end.stopper.total.value == expected["Hsd"] == max(expected["candidate"], expected["share"])
    assert end.rubber.total.value == 0.0 and end.rubber.each.value == 0.0 and end.rubber.count == 2
    assert (end.stopper.count, end.stopper.each.value, end.stopper.on_cantilever, end.stopper.force.value) == (
        7, expected["per_stopper"], 0, 0.0)
    assert value(end.stopper.each) == q(D(175.03) / 7, 2)
    force = reaction.longitudinal.case(LongitudinalCase.SAFETY_LR10_B10).end
    assert end.stopper.total == force.force and end.candidate == force.fixed_candidate


@pytest.mark.parametrize("index,name", [(1, "1.1 LR + 1.23B"), (2, "1.0 LR + 1.35B"), (3, "1.0 LR")])
def test_the_other_combinations(cases, index, name):
    _, found = cases
    expected = SAMPLE["bearing_forces"][name]
    case = found[index]
    assert case.label == name
    assert case.origin.rubber.total.value == expected["origin"]["Hbd"]
    assert case.origin.rubber.each.value == expected["origin"]["per_rubber"]
    assert case.end.stopper.total.value == expected["end"]["Hsd"]
    assert case.end.stopper.each.value == expected["end"]["per_stopper"]
    moments = SAMPLE["bearing_forces"]["cantilever_moments"][name]
    assert (case.force.value, case.moment.value) == (moments["H"], moments["Mt"])


def test_the_seismic_case_loads_the_stoppers_with_the_kh_along_the_track(cases):
    reaction, found = cases
    case = found[4]
    expected = SAMPLE["bearing_forces"]["地震時"]
    assert case.case is None and case.label == SEISMIC
    origin, end = case.origin, case.end
    assert origin.applied.value == expected["origin"]["T"] and end.applied.value == expected["end"]["T"]
    assert value(origin.applied) == q(D("0.386") * D(13580) + D(128), 2)
    assert seismic_girder_force(reaction.longitudinal, Girder.ORIGIN, KH(0.386)).value == expected["origin"]["girder_inertia"]
    assert seismic_girder_force(reaction.longitudinal, Girder.END, KH(0.386)).value == expected["end"]["girder_inertia"]
    assert reaction.longitudinal.origin.seismic_train.value == expected["origin"]["train_inertia"]
    assert origin.vertical is None and origin.friction is None and origin.candidate is None
    assert origin.share.value == expected["origin"]["Hsd"]  # T / n at the movable end
    assert value(origin.share) == q(D(5369.88) / 2, 2)
    assert origin.stopper.total.value == expected["origin"]["Hsd"] and origin.rubber.total.value == 0.0
    assert origin.stopper.each.value == expected["origin"]["per_stopper"]  # 2684.94 / 3
    assert end.stopper.total.value == expected["end"]["Hsd"] == expected["end"]["T"]  # T at the fixed end
    assert end.stopper.each.value == expected["end"]["per_stopper"] and end.rubber.total.value == 0.0
    moments = SAMPLE["bearing_forces"]["cantilever_moments"]["地震時"]
    assert (case.force.value, case.moment.value) == (moments["H"], moments["Mt"])
    assert value(case.moment) == q(D(894.98) * D(1.35), 2)


def test_a_larger_kh_scales_the_seismic_forces_only():
    pier_input = pier()
    reaction = reaction_of(pier_input)
    low, high = (bearing_cases(pier_input, reaction.longitudinal, KH(kh), Y) for kh in (0.386, 0.772))
    assert low[:4] == high[:4]
    assert value(high[4].origin.applied) == q(D("0.772") * D(13580) + D(128), 2)


def test_a_fixed_origin_and_a_movable_end_swap_the_roles():
    pier_input = pier(**{"上部構造/支承データ/起点側/支承名": "固定", "上部構造/支承データ/終点側/支承名": "可動",
                       "上部構造/支承データ/終点側/復旧性制動係数": None})
    reaction = reaction_of(pier_input)
    found = bearing_cases(pier_input, reaction.longitudinal, KH(0.386), Y)
    first, seismic = found[0], found[4]
    assert first.origin.bearing is BearingType.FIXED and first.origin.rubber.total.value == 0.0
    assert first.origin.stopper.total == reaction.longitudinal.case(LongitudinalCase.SAFETY_LR10_B10).origin.force
    assert first.end.bearing is BearingType.MOVABLE
    assert first.end.rubber.total == reaction.longitudinal.case(LongitudinalCase.SAFETY_LR10_B10).end.friction
    assert first.end.stopper.total.value == 0.0
    assert seismic.origin.stopper.total == seismic.origin.applied  # T at the fixed end
    assert seismic.end.stopper.total == seismic.end.share  # T / n at the movable end


@pytest.mark.parametrize("key,message", [
    ("ゴム支承の箇所数", "上部構造.支承データ.起点側.ゴム支承の箇所数: 値が必要です"),
    ("ストッパーの箇所数", "上部構造.支承データ.起点側.ストッパーの箇所数: 値が必要です"),
    ("片持ち梁上のゴム支承", "上部構造.支承データ.起点側.片持ち梁上のゴム支承: 値が必要です"),
    ("片持ち梁上のストッパー", "上部構造.支承データ.起点側.片持ち梁上のストッパー: 値が必要です"),
])
def test_a_blank_count_is_an_input_error(key, message):
    pier_input = pier(**{f"上部構造/支承データ/起点側/{key}": None})
    with pytest.raises(InputError, match=re.escape(message)):
        bearing_cases(pier_input, reaction_of(pier_input).longitudinal, KH(0.386), Y)


def test_more_devices_on_the_cantilever_than_on_the_girder_is_an_input_error():
    pier_input = pier(**{"上部構造/支承データ/終点側/片持ち梁上のストッパー": 8})
    with pytest.raises(InputError, match=re.escape("上部構造.支承データ.終点側.片持ち梁上のストッパー: ストッパーの箇所数（7）以下が"
                                                   "必要です（8）")):
        bearing_cases(pier_input, reaction_of(pier_input).longitudinal, KH(0.386), Y)


def test_a_zero_count_is_an_input_error_only_when_the_device_carries_a_force():
    # the end girder is fixed: its rubber bearings carry nothing, so none of them is fine
    pier_input = pier(**{"上部構造/支承データ/終点側/ゴム支承の箇所数": 0, "上部構造/支承データ/終点側/片持ち梁上のゴム支承": 0})
    found = bearing_cases(pier_input, reaction_of(pier_input).longitudinal, KH(0.386), Y)
    assert found[0].end.rubber.count == 0 and found[0].end.rubber.each.value == 0.0 and found[0].end.rubber.force.value == 0.0
    # but its stoppers carry 175.03
    pier_input = pier(**{"上部構造/支承データ/終点側/ストッパーの箇所数": 0, "上部構造/支承データ/終点側/片持ち梁上のストッパー": 0})
    with pytest.raises(InputError, match=re.escape("上部構造.支承データ.終点側.ストッパーの箇所数: ストッパーに水平荷重 175.03 kN "
                                                   "が働くのに箇所数が 0 です")):
        bearing_cases(pier_input, reaction_of(pier_input).longitudinal, KH(0.386), Y)
