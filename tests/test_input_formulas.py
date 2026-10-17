"""The input workbook's formulas remain formulas after JSON import."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from src.inputs import InputError, parse_input
from src.calculator import calculate
from src.reaction_inputs import parse_reaction_input
from src.reaction_calculator import calculate_reactions


# Fixed historical input from fa27cca^, independent of the working input.
SOURCE = Path(__file__).resolve().parent / "fixtures" / "baseline_input.json"
B9 = ("下部構造", "寸法", "側面", "B9")
SURFACE = ("地盤データ", "層", 0, "層厚")
SOIL = ("下部構造", "単位体積重量", "土", "排除した土")
DERIVED = [SURFACE, SOIL]


@pytest.fixture
def source():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def parent(data, path):
    for key in path[:-1]:
        data = data[key]
    return data


def put(data, path, value):
    parent(data, path)[path[-1]] = value


@pytest.mark.parametrize("path", DERIVED, ids=lambda p: ".".join(map(str, p)))
@pytest.mark.parametrize("cached", ["missing", None, 999999, "invalid", True, {"bad": 1}])
def test_derived_cache_is_never_an_input(source, path, cached):
    foundation = replace(parse_input(source), warnings=())
    reaction = parse_reaction_input(source)
    if cached == "missing":
        del parent(source, path)[path[-1]]
    else:
        put(source, path, cached)
    unchanged = deepcopy(source)
    assert replace(parse_input(source), warnings=()) == foundation
    assert parse_reaction_input(source) == reaction
    assert source == unchanged


def test_parser_formulas_track_sources_while_explicit_values_are_preserved(source):
    baseline = calculate_reactions(parse_reaction_input(source))
    positions = tuple(source["上部構造"][side]["支承位置_f"] for side in ("起点側", "終点側"))
    heights = tuple(source["上部構造"][side]["高さ"]["h4"] for side in ("起点側", "終点側"))
    centers = tuple(source["上部構造"][side]["重心高_hs"] for side in ("起点側", "終点側"))
    bearing_positions = tuple(source["上部工反力"][side][point]["支承"][1]["支承位置"]
                              for side, point in (("起点側", "B支点"), ("終点側", "C支点")))
    del parent(source, B9)[B9[-1]]  # absent B9 retains the original B7 fallback
    source["下部構造"]["寸法"]["側面"]["B7"] = 0.25
    source["下部構造"]["寸法"]["高さ"].update(H5=0.2, H6=2.5)
    source["下部構造"]["土かぶり"].update(起点側_df1=1.5, 終点側_df2=2.5)
    source["地盤データ"]["層"][0]["単位体積重量"]["湿潤"] = 19.5
    for side, point, d1, l1, l2 in (("起点側", "B支点", -3, 0.6, 0.8),
                                  ("終点側", "C支点", -4, 0.7, 0.9)):
        span = source["上部構造"][side]
        span["高さ"].update(h1=0.5, h2=0.7, h3=0.4)
        span["桁長"].update(L1=l1, L2=l2)
        source["上部工反力"][side][point]["支承"][0]["支承位置"] = d1
    unchanged = deepcopy(source)
    foundation = parse_input(source)
    reaction = parse_reaction_input(source)
    assert foundation.b_parts == (0.25, 5.5, 0.25)
    assert foundation.layers[0].thickness == pytest.approx(4.2)
    assert calculate(foundation)["foundation"]["B"] == 6
    assert reaction.geometry.b9 == 0.25
    assert reaction.geometry.unit_weight_displaced_soil == 19.5
    assert (reaction.spans.b.hs, reaction.spans.c.hs) == centers
    assert (reaction.spans.b.h4, reaction.spans.c.h4) == heights
    assert (reaction.spans.b.f, reaction.spans.c.f) == positions
    assert (reaction.dead.b[1].position, reaction.dead.c[1].position) == bearing_positions
    assert calculate_reactions(reaction)["weights"] != baseline["weights"]
    assert source == unchanged


@pytest.mark.parametrize("parser", (parse_input, parse_reaction_input))
@pytest.mark.parametrize("explicit", (0, 0.2, 0.4))
def test_explicit_b9_takes_priority_over_b7_formula(source, parser, explicit):
    source["下部構造"]["寸法"]["側面"].update(B7=0.35, B9=explicit)
    unchanged = deepcopy(source)
    parsed = parser(source)
    actual = parsed.b_parts[2] if parser is parse_input else parsed.geometry.b9
    assert actual == explicit
    assert source == unchanged


@pytest.mark.parametrize("parser", (parse_input, parse_reaction_input))
@pytest.mark.parametrize("cached", ("missing", None))
def test_missing_or_null_b9_is_computed_from_b7(source, parser, cached):
    source["下部構造"]["寸法"]["側面"]["B7"] = 0.35
    if cached == "missing":
        del parent(source, B9)[B9[-1]]
    else:
        put(source, B9, cached)
    unchanged = deepcopy(source)
    parsed = parser(source)
    actual = parsed.b_parts[2] if parser is parse_input else parsed.geometry.b9
    assert actual == 0.35
    assert source == unchanged


@pytest.mark.parametrize("parser", (parse_input, parse_reaction_input))
@pytest.mark.parametrize("bad", (True, False, "0.2", -1, float("nan"), float("inf"), {}, []))
def test_explicit_b9_is_validated_without_falling_back(source, parser, bad):
    put(source, B9, bad)
    with pytest.raises(InputError, match="B9"):
        parser(source)


def test_one_bearing_position_does_not_move_other_bearing_positions(source):
    baseline = parse_reaction_input(source)
    source["上部工反力"]["起点側"]["B支点"]["支承"][0]["支承位置"] = -7
    changed = parse_reaction_input(source)
    assert changed.dead.b[0].position == -7
    assert changed.dead.b[1:] == baseline.dead.b[1:]
    assert changed.dead.c == baseline.dead.c


def test_ground_wet_weight_changes_displaced_soil_without_changing_overburden(source):
    baseline = parse_reaction_input(source)
    source["地盤データ"]["層"][0]["単位体積重量"]["湿潤"] = 20.5
    changed = parse_reaction_input(source)
    assert changed.geometry.unit_weight_displaced_soil == 20.5
    assert changed.geometry.unit_weight_soil == baseline.geometry.unit_weight_soil


@pytest.mark.parametrize("path", [
    ("下部構造", "寸法", "側面", "B7"),
    ("下部構造", "寸法", "高さ", "H5"),
    ("下部構造", "寸法", "高さ", "H6"),
    ("下部構造", "土かぶり", "起点側_df1"),
    ("上部構造", "起点側", "高さ", "h1"),
    ("上部構造", "終点側", "高さ", "h2"),
    ("上部構造", "起点側", "高さ", "h3"),
    ("上部構造", "起点側", "桁長", "L2"),
    ("上部構造", "終点側", "桁長", "L1"),
])
@pytest.mark.parametrize("bad", [None, "bad", True, -1, float("inf")])
def test_independently_required_sources_are_still_validated(source, path, bad):
    put(source, path, bad)
    parser = parse_input if path[0] == "下部構造" else parse_reaction_input
    with pytest.raises(InputError):
        parser(source)


@pytest.mark.parametrize("path", [
    ("地盤データ", "層", 0, "単位体積重量", "湿潤"),
    ("上部工反力", "起点側", "B支点", "支承", 0, "支承位置"),
    ("上部工反力", "終点側", "C支点", "支承", 0, "支承位置"),
])
@pytest.mark.parametrize("bad", ["missing", "bad", True, float("inf")])
def test_input_sources_do_not_fall_back_to_cached_values(source, path, bad):
    if bad == "missing":
        del parent(source, path)[path[-1]]
    else:
        put(source, path, bad)
    with pytest.raises(InputError):
        parse_reaction_input(source)


def test_optional_blank_cell_references_are_zero(source):
    positions = tuple(source["上部工反力"][side][point]["支承"][1]["支承位置"]
                      for side, point in (("起点側", "B支点"), ("終点側", "C支点")))
    source["地盤データ"]["層"][0]["単位体積重量"]["湿潤"] = None
    for side, point in (("起点側", "B支点"), ("終点側", "C支点")):
        source["上部工反力"][side][point]["支承"][0]["支承位置"] = None
    result = parse_reaction_input(source)
    assert result.geometry.unit_weight_displaced_soil == 0
    assert result.dead.b[0].position is None
    assert result.dead.c[0].position is None
    assert (result.dead.b[1].position, result.dead.c[1].position) == positions


def test_0600_needs_only_first_ground_row_wet_unit_weight(source):
    expected = parse_reaction_input(source)
    wet = source["地盤データ"]["層"][0]["単位体積重量"]["湿潤"]
    source["地盤データ"] = {"層": [{"単位体積重量": {"湿潤": wet}}]}
    assert parse_reaction_input(source) == expected
    source["地盤データ"]["層"] = []
    with pytest.raises(InputError, match="地盤データ"):
        parse_reaction_input(source)
