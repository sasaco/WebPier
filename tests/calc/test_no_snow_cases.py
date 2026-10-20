"""Decision 69: without snow on the pier no snow case is made from 0610 on; the cases after it move up."""

from functools import cache

from cantilever_support import result_of
from reaction_support import document
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import BasicCase as L
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import BasicCase as T
from webpier.calc.transverse import Define, calculate_transverse
from webpier.inputs import parse_input
from webpier.inputs.fields import SNOW_KEYS


def snowless(value=None):
    data = document()
    for side, far, slots in (("起点側", "A支点", "B支点"), ("終点側", "D支点", "C支点")):
        reactions = data["上部工反力"][side]
        reactions[far] |= dict.fromkeys(SNOW_KEYS, value)
        for slot in reactions[slots]:
            if slot is not None:
                slot |= dict.fromkeys(SNOW_KEYS, value)
    return parse_input(data)


@cache
def results(snow: bool):
    pier = parse_input(document()) if snow else snowless()
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    return (reaction, calculate_longitudinal(pier, foundation, reaction),
            calculate_transverse(pier, foundation, reaction))


def resolved(combination):
    """(case, nominal, factor, basis) of the components other than snow: what the numbering must not change."""
    return [(c.case, c.nominal, c.factor, c.basis) for c in combination.components
            if c.case not in (L.SNOW2, L.SNOW10, L.SNOW30)]


def test_snow_is_any_snow_on_a_bearing_of_this_pier():
    assert results(True)[0].dead.snow
    assert not results(False)[0].dead.snow
    assert not calculate_reaction(snowless(0.0)).dead.snow  # 0.00 everywhere is no snow, as blank is


def test_0610_has_17_basic_cases_numbered_without_the_snow_cases():
    full, result = results(True)[1], results(False)[1]
    assert result.snow is None
    made = [case for case in L if case not in (L.SNOW2, L.SNOW10, L.SNOW30)]
    assert [(a.number, a.case) for a in result.basic_cases] == list(enumerate(made, 1))
    # the same vertical actions as with snow (the bearing friction of the horizontal ones carries the snow)
    assert [(a.case, a.spring, a.points, a.line_loads) for a in result.basic_cases if not a.horizontal] == [
        (a.case, a.spring, a.points, a.line_loads) for a in full.basic_cases if a.case in made and not a.horizontal]
    # Define n is basic case n; the horizontal ones (now 10-17) in both directions
    assert [(d.number, d.case, d.signs) for d in result.define_cases] == [
        (n, case, (1, -1) if n >= 10 else (1,)) for n, case in enumerate(made, 1)]


def test_0610_combinations_keep_their_numbers_and_lose_the_snow_column():
    full, result = results(True)[1], results(False)[1]
    assert [c.number for c in result.combinations] == [c.number for c in full.combinations] == list(range(1, 17))
    for with_snow, without in zip(full.combinations, result.combinations, strict=True):
        assert without.coefficients == tuple(coefficient for case, coefficient in zip(L, with_snow.coefficients)
                                             if case not in (L.SNOW2, L.SNOW10, L.SNOW30))
        assert resolved(without) == resolved(with_snow)
    assert result.extractions == full.extractions


def test_0620_has_14_basic_cases_and_12_defines_without_the_snow_cases():
    full, result = results(True)[2], results(False)[2]
    assert result.snow is None
    snow = (T.SNOW2, T.SNOW10, T.SNOW30)
    assert [(a.number, a.case) for a in result.basic_cases] == list(enumerate(
        (case for case in T if case not in snow and case.value <= 17), 1))
    defines = [define for define in Define if define not in (Define.SNOW2, Define.SNOW10, Define.SNOW30)
               and define.value <= 15]
    assert [(d.number, d.define) for d in result.define_cases] == list(enumerate(defines, 1))
    assert [(d.define, d.cases, d.signs) for d in result.define_cases] == [
        (d.define, d.cases, d.signs) for d in full.define_cases if d.define in defines]
    for with_snow, without in zip(full.combinations, result.combinations, strict=True):
        assert without.number == with_snow.number
        assert without.coefficients == tuple(coefficient for d, coefficient in
                                             zip(full.define_cases, with_snow.coefficients) if d.define in defines)
        assert [(c.define, c.nominal) for c in without.components] == [
            (c.define, c.nominal) for c in with_snow.components if c.define in defines]


def test_0900_has_no_snow_action_and_its_cases_lose_the_snow_part():
    full, result = result_of()[2], result_of(snowless())[2]
    for side, item in result.sides.items():
        assert not [action for action in item.actions if action.key.kind == "S"]
        assert [action.key for action in item.actions] == [
            action.key for action in full.sides[side].actions if action.key.kind != "S"]
        for with_snow, without in zip(full.sides[side].cases, item.cases, strict=True):
            assert without.definition == with_snow.definition
            assert [part for part in without.contributions if part.column == "S"] == []
