"""0610 / 0620 with a load model (decision 70): the cases, the Defines, the combinations and the extraction groups.

The test load model (addin_support) has no combination of 変動作用: that group gets the zero case.
"""

from dataclasses import replace

from addin_support import CURRENT, chain
from webpier.calc.bearing_actions import bearing_table
from webpier.calc.foundation import calculate_foundation
from webpier.calc.frame import Direction, NodeRole
from webpier.calc.generic.frame import NO_COMBINATION, ZERO, calculate_generic_frame
from webpier.calc.longitudinal import BasicCase, calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import BasicCase as TransverseCase, calculate_transverse
from webpier.calc.transverse.wind import pier_wind
from webpier.core.printed import PRESSURE
from webpier.inputs import parse_input
from webpier.loadmodel import ExtractionGroup as G, SpringTerm


def generic(direction: Direction, stage: str):
    p, foundation, reaction, model = chain()
    return p, model, calculate_generic_frame(p, foundation, reaction, model, direction, stage)


def train(direction: Direction):
    p = parse_input(CURRENT)
    reaction = calculate_reaction(p)
    calculate = calculate_longitudinal if direction is Direction.LONGITUDINAL else calculate_transverse
    return calculate(p, calculate_foundation(p), reaction)


def test_the_longitudinal_cases():
    p, model, result = generic(Direction.LONGITUDINAL, "0610")
    assert [(c.number, c.id, c.spring) for c in result.basic_cases] == [
        (1, "D1", SpringTerm.LONG), (2, "D2", SpringTerm.LONG), (3, "WP_HIGH", SpringTerm.LONG),
        (4, "WP_NORMAL", SpringTerm.LONG), (5, "WP_LOW", SpringTerm.LONG), (6, "L", SpringTerm.SHORT),
        (7, "BR", SpringTerm.SHORT), (8, ZERO, SpringTerm.LONG)]
    assert [c.name for c in result.basic_cases[:5]] == ["固定死荷重", "付加死荷重", "浮力（高水位）", "浮力（平水位）",
                                                       "浮力（低水位）"]
    # The application's cases are those of the train path.
    old = train(Direction.LONGITUDINAL)
    for case, kind in (("D1", BasicCase.D1), ("D2", BasicCase.D2), ("WP_HIGH", BasicCase.BUOYANCY_HIGH),
                       ("WP_NORMAL", BasicCase.BUOYANCY_NORMAL), ("WP_LOW", BasicCase.BUOYANCY_LOW)):
        assert (result.basic(case).points, result.basic(case).line_loads) == (old.basic(kind).points,
                                                                               old.basic(kind).line_loads)
    assert result.dead.fixed == old.fixed and result.dead.buoyancy == old.buoyancy
    # The load model's cases are their 支承作用 on the frame.
    case = next(c for c in model.cases if c.id == "L")
    table = bearing_table(p, result.frame, case)
    assert result.basic("L").bearings == table and result.basic("L").points == (table.point,)
    zero = result.basic(ZERO)
    assert zero.zero and zero.name == "断面力0" and len(zero.points) == 1
    point = zero.points[0]
    assert (point.node, point.n.value, point.h.value, point.m.value) == (
        result.frame.node(NodeRole.CAP_TOP).number, 0.0, 0.0, 0.0)
    assert [c.id for c in result.basic_cases if c.bearings is None] == ["D1", "D2", "WP_HIGH", "WP_NORMAL", "WP_LOW",
                                                                        ZERO]


def test_the_longitudinal_defines_combinations_and_extractions():
    _, _, result = generic(Direction.LONGITUDINAL, "0610")
    assert [(d.number, d.candidates) for d in result.define_cases] == [
        (1, (("D1", 1),)), (2, (("D2", 1),)), (3, (("L", 1),)), (4, (("BR", 1), ("BR", -1))),
        (5, (("WP_NORMAL", 1),)), (6, (("WP_LOW", 1),)), (7, ((ZERO, 1),))]
    first = result.combinations[0]
    assert (first.number, first.name) == (1, "破壊 車最大")
    assert [(t.define, t.factor.value, t.factor.digits) for t in first.terms] == [
        (1, 1.1, 1), (2, 1.2, 1), (3, 1.35, 2), (4, 1.0, 1)]
    last = result.combinations[-1]
    assert (last.number, last.name, last.zero, last.groups) == (7, NO_COMBINATION, True, frozenset({G.VARIABLE}))
    assert [(t.define, t.factor.value) for t in last.terms] == [(7, 1.0)]
    assert [(e.number, e.group, e.combinations) for e in result.extractions] == [
        (1, G.FAILURE, (1,)), (2, G.PERMANENT_VARIABLE, (2,)), (3, G.PERMANENT, (3,)), (4, G.VARIABLE, (7,)),
        (5, G.DAMAGE, (4,)), (6, G.STABILITY, (1,)), (7, G.SUPPORT_LONG_TERM, (5,)), (8, G.SUPPORT_SHORT_TERM, (6,))]
    assert result.empty == frozenset({G.VARIABLE})
    assert [section.title for section in result.sections] == ["車荷重の根拠"]


def test_the_transverse_cases_with_the_wind_on_the_pier():
    p, _, result = generic(Direction.TRANSVERSE, "0620")
    assert [(c.number, c.id) for c in result.basic_cases] == [
        (1, "D1"), (2, "D2"), (3, "WP_HIGH"), (4, "WP_NORMAL"), (5, "WP_LOW"), (6, "PIER_WIND_1"), (7, "L"), (8, "WG"),
        (9, ZERO)]
    wind = result.basic("PIER_WIND_1")
    expected = pier_wind(p, result.frame, PRESSURE(3.0))
    assert (wind.name, wind.spring, wind.points, wind.member_loads) == (
        "躯体の風（3.0 kN/m2）", SpringTerm.SHORT, (), expected.member_loads)
    assert result.winds == (expected,)
    old = train(Direction.TRANSVERSE)
    assert result.basic("D1").points == old.basic(TransverseCase.D1).points
    assert [(d.number, d.candidates) for d in result.define_cases] == [
        (1, (("D1", 1),)), (2, (("D2", 1),)), (3, (("WG", 1), ("WG", -1))),
        (4, (("PIER_WIND_1", 1), ("PIER_WIND_1", -1))), (5, (("L", 1),)), (6, (("WP_NORMAL", 1),)),
        (7, (("WP_LOW", 1),)), (8, ((ZERO, 1),))]
    assert result.sections == ()


def test_every_group_with_a_combination_has_no_zero_case():
    p, foundation, reaction, model = chain()
    full = replace(model, longitudinal=tuple(replace(c, groups=c.groups | {G.VARIABLE}) if c.name == "ひび割れ 永久"
                                             else c for c in model.longitudinal))
    result = calculate_generic_frame(p, foundation, reaction, full, Direction.LONGITUDINAL, "0610")
    assert ZERO not in [c.id for c in result.basic_cases] and result.empty == frozenset()
    assert result.extractions[3].combinations == (3,)
