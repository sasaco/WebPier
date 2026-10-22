"""Which combination's .ndt each basic case of the 荷重図 is drawn from (decision 51): the first combination, by
number, that uses the case; a case no combination uses is an error."""

from dataclasses import replace
from functools import cache

import pytest
from hypothesis import given, strategies as st

import jrsnap_support
from webpier.export.jrsnap import diagram_combinations


@cache
def model(direction):
    return jrsnap_support.model(direction)


def test_along_the_track_every_case_is_drawn_from_combination_1():
    assert diagram_combinations(model("longitudinal")) == tuple((number, 1) for number in range(1, 9))


def test_across_the_track_case_6_the_down_track_is_drawn_from_combination_5():
    # Decision 76: combinations 1〜4 are the up track, 5〜8 the down track (逆向, which keeps the fixed CASE-6).
    expected = tuple((number, 5 if number == 6 else 1) for number in range(1, 10))
    assert diagram_combinations(model("transverse")) == expected


def test_a_case_no_combination_uses_is_an_error():
    base = model("transverse")
    unused = 3
    combinations = tuple(replace(combination, coefficients=tuple(
        0 if index == unused else coefficient for index, coefficient in enumerate(combination.coefficients)))
        for combination in base.combinations)
    case = base.cases[unused]
    with pytest.raises(ValueError, match=f"基本ケース{case.number}（{case.title}）を使う組合せがありません"):
        diagram_combinations(replace(base, combinations=combinations))


@st.composite
def usages(draw):
    """(combination count, a nonempty bit mask of the combinations using each case)."""
    count = draw(st.integers(min_value=1, max_value=4))
    masks = draw(st.lists(st.integers(min_value=1, max_value=2 ** count - 1), min_size=1, max_size=12))
    return count, masks


@given(usages())
def test_each_case_is_drawn_from_the_first_combination_that_uses_it(usage):
    count, masks = usage
    base = model("transverse")
    cases = tuple(replace(base.cases[0], number=index + 1, title=f"CASE-{index + 1}") for index in range(len(masks)))
    combinations = tuple(replace(base.combinations[0], coefficients=tuple((mask >> slot) & 1 for mask in masks))
                         for slot in range(count))
    found = diagram_combinations(replace(base, cases=cases, combinations=combinations))
    assert [number for number, _ in found] == [case.number for case in cases]
    for index, ((_, combination), mask) in enumerate(zip(found, masks, strict=True)):
        using = [slot + 1 for slot in range(count) if combinations[slot].coefficients[index] == 1]
        assert combination == min(using) == (mask & -mask).bit_length()  # the lowest set bit of the mask
