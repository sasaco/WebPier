"""0600 with a load model (decision 70): the dead loads D1 and D2 and the self weight only; nothing of the train."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.calc.reaction import calculate_dead_reaction, calculate_reaction
from webpier.calc.reaction.self_weight import calculate_self_weight
from webpier.inputs import parse_input

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))


def pier():
    document = deepcopy(CURRENT)
    del document["上部構造"]["列車"]  # the load model's: not there at all
    return parse_input(document, load_model=True)


def test_the_bearing_sums_by_hand():
    # B: 1530 + 1340 + 1340 + 1530 = 5740.00, 160 + 100 + 100 + 160 = 520.00; C: 930 + 930, 130 + 130.
    dead = calculate_dead_reaction(pier()).dead
    assert (dead.origin.pier.d1.value, dead.origin.pier.d2.value) == (5740.0, 520.0)
    assert (dead.end.pier.d1.value, dead.end.pier.d2.value) == (1860.0, 260.0)
    assert dead.origin.pier.d1.digits == 2 and dead.origin.pier.d1.unit == "kN"
    # A and D are the entered totals of the far supports.
    assert (dead.origin.far.d1.value, dead.origin.far.d2.value) == (5740.0, 660.0)
    assert (dead.end.far.d1.value, dead.end.far.d2.value) == (1860.0, 260.0)


def test_the_bearings_keep_their_slots_and_positions():
    dead = calculate_dead_reaction(pier()).dead
    assert [item.slot for item in dead.origin.bearings] == [0, 1, 2, 3]
    assert [item.bearing.position.value for item in dead.end.bearings] == [-2.95, 2.95]


def test_the_same_dead_loads_and_self_weight_as_the_train_path():
    loaded, train = calculate_dead_reaction(pier()), calculate_reaction(parse_input(deepcopy(CURRENT)))
    for side in ("origin", "end"):
        mine, theirs = getattr(loaded.dead, side), getattr(train.dead, side)
        for where in ("far", "pier"):
            assert (getattr(mine, where).d1, getattr(mine, where).d2) == (getattr(theirs, where).d1,
                                                                          getattr(theirs, where).d2)
    assert loaded.self_weight == train.self_weight == calculate_self_weight(pier())


def test_a_value_too_large_is_an_input_error():
    document = deepcopy(CURRENT)
    del document["上部構造"]["列車"]
    dims = document["下部構造"]["寸法"]
    dims["側面"]["B1"] = dims["正面"]["W1"] = 1e200  # the beam volume B1 × W1 × H2 is beyond a double
    with pytest.raises(InputError, match="0600: 入力が大きすぎるため計算できません"):
        calculate_dead_reaction(parse_input(document, load_model=True))


def test_an_input_error_of_the_self_weight_is_not_wrapped():
    document = deepcopy(CURRENT)
    del document["上部構造"]["列車"]
    dims = document["下部構造"]["寸法"]
    dims["側面"]["B6"] = dims["正面"]["W6"] = 0.001  # B6 × W6 rounds to 0.000 m2
    with pytest.raises(InputError, match="^0600 柱: 小数3桁に丸めた面積が0以下になります"):
        calculate_dead_reaction(parse_input(document, load_model=True))
