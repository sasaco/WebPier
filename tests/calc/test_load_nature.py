"""Decision 36: the spring set of a load case follows the nature of its loads, for every direction."""

import pytest

from longitudinal_support import SECTIONS, longitudinal
from webpier.calc.load_nature import LONG_TERM_NATURES, Nature, SpringTerm, spring_term
from webpier.calc.longitudinal import BasicCase
from webpier.calc.longitudinal.actions import NATURES

N = Nature


@pytest.mark.parametrize("natures,expected", [
    ({N.LONG_RAIL}, SpringTerm.LONG),  # long rail: long-term
    ({N.LONG_RAIL, N.BRAKING}, SpringTerm.SHORT),  # braking / starting with it: short-term
    ({N.TRAIN}, SpringTerm.SHORT), ({N.IMPACT}, SpringTerm.SHORT), ({N.BRAKING}, SpringTerm.SHORT),
    ({N.CENTRIFUGAL}, SpringTerm.SHORT), ({N.LATERAL}, SpringTerm.SHORT),
    # Not live loads: as the Example2 FrameWeb files (08 / 09) save them.
    ({N.DEAD}, SpringTerm.LONG), ({N.WATER}, SpringTerm.LONG), ({N.SNOW}, SpringTerm.LONG),
    ({N.WIND}, SpringTerm.SHORT),
])
def test_rule(natures, expected):
    assert spring_term(frozenset(natures)) is expected


def test_every_nature_has_a_term():
    assert LONG_TERM_NATURES < set(Nature)
    with pytest.raises(ValueError):
        spring_term(frozenset())


def test_0610_cases_by_nature():
    lr, b = {N.LONG_RAIL}, {N.LONG_RAIL, N.BRAKING}
    # decision 120: the reduced 1.1 LR + 1.0 B and 1.0 LR + 1.1 B follow their twins, braking with the long rail
    assert [set(NATURES[case]) for case in BasicCase] == [
        {N.DEAD}, {N.DEAD}, {N.WATER}, {N.WATER}, {N.WATER}, {N.SNOW}, {N.SNOW}, {N.SNOW}, {N.TRAIN}, {N.TRAIN},
        {N.IMPACT}, {N.IMPACT}, lr, lr, b, b, b, b, b, lr, b, lr]


def test_0610_springs_follow_the_rule_and_8_9():
    # The rule agrees with every バネ printed on 8-9 (1 long-term, 2 short-term), including 14, 18 and 20 (1),
    # which the Example2 FrameWeb file saves as 2.
    printed = {row["no"]: row["spring"] for row in SECTIONS["basic_cases"]["rows"]}
    # The reduced cases of decision 120 are not in Example2: each has its twin's nature, so its twin's バネ (2).
    twin = {BasicCase.SAFETY_LR11_B_REDUCED: BasicCase.SAFETY_LR11_B,
            BasicCase.SAFETY_LR10_BMAX_REDUCED: BasicCase.SAFETY_LR10_BMAX}
    for action in longitudinal().basic_cases:
        assert action.spring is spring_term(NATURES[action.case])
        case = twin.get(action.case, action.case)
        assert action.spring is {1: SpringTerm.LONG, 2: SpringTerm.SHORT}[printed[case.value]]
