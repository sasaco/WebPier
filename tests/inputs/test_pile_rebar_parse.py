"""鉄筋.杭, the reinforcement of a cast-in-place pile (decisions 87 and 92): form, digits and choices only; a blank is a value
the pile body check asks for (calc.pile_cast), and the f'ck, the diameter and the construction condition are the 杭基礎's."""

import re
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.core.integrity import load_json
from webpier.inputs import parse_input

CURRENT = load_json((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_bytes())
HOOP = {"diameter_mm": 16, "sets": 1, "pitch_mm": 200.0}
FULL = {
    "materials": {"main": "SD345", "transverse": "SD390"}, "pure_cover_mm": 100.0, "aggregate_max_mm": 25.0,
    "main_bars": {"diameter_mm": 32, "count": 20},
    "hoops": {"footing": {"diameter_mm": 13, "sets": 2, "pitch_mm": 100.0}, "zone_2d": HOOP,
              "lower": [{"length_m": 2.5, "diameter_mm": 16, "sets": 1, "pitch_mm": 250.0},
                        {"length_m": 3.0, "diameter_mm": 13, "sets": 1, "pitch_mm": 300.0}]},
    "cutoff": {"main_bars": {"diameter_mm": 29, "count": 16}, "hoops": {"diameter_mm": 13, "sets": 1, "pitch_mm": 300.0},
               "head_anchorage_mm": 1500.0, "cutoff_length_mm": 6000.0, "cutoff_anchorage_mm": 1200.0,
               "joint_reduction": 0.7, "margin_mm": 100.0,
               "no_joint": {"from_head_mm": 2000.0, "above_mm": 500.0, "below_mm": 500.0},
               "margin_ratio": {"moment": 1.1, "shear": 1.1}, "anchorage_stirrup": "2D 区間"}}


def pile_rebar(**changes):
    data = deepcopy(CURRENT)
    data["鉄筋"]["杭"] = deepcopy(FULL)
    data["鉄筋"]["杭"].update(deepcopy(changes))
    return data


def set_at(data, path, value):
    node = data["鉄筋"]["杭"]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return data


def fails(data, message):
    with pytest.raises(InputError, match=re.escape(message)):
        parse_input(data)


def test_the_reinforcement_of_the_pile_is_read():
    bars = parse_input(pile_rebar()).rebar.pile
    assert (bars.materials.main, bars.materials.transverse) == ("SD345", "SD390")
    assert (bars.pure_cover.value, bars.aggregate_max.value, bars.main_diameter.value, bars.main_count) == (
        100.0, 25.0, 32, 20)
    assert (bars.hoops.footing.diameter.value, bars.hoops.footing.sets, bars.hoops.footing.pitch.value) == (13, 2, 100.0)
    assert (bars.hoops.zone_2d.diameter.value, bars.hoops.zone_2d.sets, bars.hoops.zone_2d.pitch.value) == (16, 1, 200.0)
    assert [(zone.length.value, zone.hoop.diameter.value, zone.hoop.sets, zone.hoop.pitch.value)
            for zone in bars.hoops.lower] == [(2.5, 16, 1, 250.0), (3.0, 13, 1, 300.0)]
    cutoff = bars.cutoff
    assert (cutoff.main_diameter.value, cutoff.main_count, cutoff.hoop.diameter.value) == (29, 16, 13)
    assert (cutoff.head_anchorage.value, cutoff.cutoff_length.value, cutoff.cutoff_anchorage.value) == (1500.0, 6000.0, 1200.0)
    assert (cutoff.joint_reduction.value, cutoff.margin.value) == (0.7, 100.0)
    assert (cutoff.no_joint_from_head.value, cutoff.no_joint_above.value, cutoff.no_joint_below.value) == (2000.0, 500.0, 500.0)
    assert (cutoff.margin_moment.value, cutoff.margin_shear.value, cutoff.anchorage_stirrup) == (1.1, 1.1, "2D 区間")


def test_the_current_input_has_nothing_entered_for_the_pile_reinforcement():
    bars = parse_input(deepcopy(CURRENT)).rebar.pile
    assert bars.pure_cover is None and bars.aggregate_max is None and bars.main_count is None
    assert bars.hoops.zone_2d.sets is None and bars.hoops.lower == () and bars.cutoff.main_diameter is None
    assert bars.materials.main is None and bars.cutoff.anchorage_stirrup is None


def test_every_item_may_stay_blank_while_it_is_entered():
    data = pile_rebar()
    for path in (("materials", "main"), ("pure_cover_mm",), ("aggregate_max_mm",), ("main_bars", "count"),
                 ("hoops", "zone_2d", "sets"), ("hoops", "lower", 0, "length_m"), ("cutoff", "anchorage_stirrup"),
                 ("cutoff", "margin_ratio", "shear")):
        set_at(data, path, None)
    bars = parse_input(data).rebar.pile
    assert bars.pure_cover is None and bars.hoops.zone_2d.sets is None and bars.hoops.lower[0].length is None


@pytest.mark.parametrize("path, value", [
    (("materials", "main"), "SD490"), (("materials", "transverse"), "SR235"), (("pure_cover_mm",), 0),
    (("aggregate_max_mm",), 0), (("main_bars", "diameter_mm"), 0), (("main_bars", "count"), 0),
    (("main_bars", "count"), 1.5), (("hoops", "zone_2d", "diameter_mm"), -16), (("hoops", "zone_2d", "sets"), 0),
    (("hoops", "zone_2d", "pitch_mm"), 0), (("hoops", "footing", "sets"), 1.5), (("hoops", "lower", 0, "length_m"), 0),
    (("cutoff", "joint_reduction"), 0), (("cutoff", "anchorage_stirrup"), "杭頭"), (("cutoff", "margin_ratio", "moment"), -1)])
def test_a_value_outside_its_range_or_choices_is_an_input_error(path, value):
    name = ".".join(f"[{part}]" if isinstance(part, int) else part for part in path).replace(".[", "[")
    fails(set_at(pile_rebar(), path, value), f"鉄筋.杭.{name}")


def test_at_most_three_zones_lie_below_the_2d_zone():
    data = pile_rebar()
    data["鉄筋"]["杭"]["hoops"]["lower"] = [{"length_m": 1.0, "diameter_mm": 13, "sets": 1, "pitch_mm": 300.0}] * 4
    fails(data, "鉄筋.杭.hoops.lower: 区間は3つまでです")


@pytest.mark.parametrize("path", [("hoops", "zone_3d"), ("main_bars", "grade"), ("cutoff", "hoops", "legs"),
                                  ("cutoff", "no_joint", "below")])
def test_an_unknown_item_is_an_input_error(path):
    node = pile_rebar()["鉄筋"]["杭"]
    data = pile_rebar()
    target = data["鉄筋"]["杭"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = 1
    fails(data, "未知の入力項目です")
    assert node  # the unchanged copy is valid
    parse_input(pile_rebar())


def test_the_pile_is_required_in_the_rebar_like_the_other_members():
    data = deepcopy(CURRENT)
    del data["鉄筋"]["杭"]
    fails(data, "鉄筋.杭")
