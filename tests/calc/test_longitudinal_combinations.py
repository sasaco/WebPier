"""0610 Define cases, the combination table and the resolved actions: Example2 08 pp.8-9 to 8-11, hand calculations."""

import pytest

from longitudinal_support import SECTIONS, longitudinal
from reaction_support import D, pier, q, value
from webpier.calc.frame import NodeRole
from webpier.calc.longitudinal import Basis, BasicCase, Usage

B = BasicCase
TABLE = SECTIONS["combinations"]["combination_table"]["rows"]
SERVICE_TRAIN = {(5, 10), (7, 9), (15, 9), (16, 9)}  # (combination, basic case) of the serviceability train L


def test_8_9_define_cases():
    printed = SECTIONS["define_cases"]["rows"]
    result = longitudinal()
    assert [(define.number, define.case.value) for define in result.define_cases] == [
        (row["no"], row["C"][0]) for row in printed]
    assert [tuple(sign * define.case.value for sign in define.signs) for define in result.define_cases] == [
        tuple(row["C"]) for row in printed]  # 13-20 both signs of the horizontal case


def test_8_10_combination_table_values():
    result = longitudinal()
    assert [combination.number for combination in result.combinations] == [row["no"] for row in TABLE]
    for combination, row in zip(result.combinations, TABLE, strict=True):
        assert [None if c is None else c.value for c in combination.coefficients] == row["coefficients"]


def test_8_10_combination_table_digits():
    result = longitudinal()
    for combination, row in zip(result.combinations, TABLE, strict=True):
        for case, (ours, printed) in enumerate(zip(combination.coefficients, row["digits"], strict=True), 1):
            if (combination.number, case) in SERVICE_TRAIN:
                # Example2 prints the serviceability train factor ρ = 1.0 with 1 decimal; the factor comes from the
                # input load factor and is printed like every ρ-derived factor, with 2 decimals (1.00).
                assert (printed, ours.digits) == (1, 2)
            else:
                assert (None if ours is None else ours.digits) == printed


def test_usage_by_requirement():
    usages = [combination.usage for combination in longitudinal().combinations]
    service = {5, 6, 7, 14, 15, 16}  # 耐久性・使用性 and 使用性 (支持)
    assert usages == [Usage.SERVICE if n in service else Usage.ULTIMATE for n in range(1, 17)]


def test_8_11_extraction_cases():
    printed = SECTIONS["extraction_cases"]["rows"]
    assert [(e.number, e.combinations) for e in longitudinal().extractions] == [
        (row["no"], tuple(row["combinations"])) for row in printed]


def test_factors_follow_the_input_load_factors():
    factors = longitudinal(pier(**{"上部構造/列車/荷重修正係数/安全性(破壊)": 1.25,
                                   "上部構造/列車/荷重修正係数/使用性": 0.9})).factors
    # 1.25 -> 1.25; 1.1 × 1.25 = 1.375 -> 1.38; 0.900 -> 0.90; 0.75 × 0.900 = 0.675 -> 0.68 (half up)
    assert [factors.ultimate.value, factors.maximum.value, factors.service.value, factors.service_impact.value] == [
        1.25, 1.38, 0.9, 0.68]
    assert [factors.d1_safety.value, factors.d2_safety.value, factors.one.value] == [1.1, 1.2, 1.0]


def scaled(factor, basic):
    """Each printed N, H, M (and q) of the basic action times the factor, rounded once to its digits."""
    return ([(p.anchor, q(D(factor) * value(p.n), 2), q(D(factor) * value(p.h), 2), q(D(factor) * value(p.m), 2))
             for p in basic.points],
            [(line.members, q(D(factor) * value(line.n), 2)) for line in basic.line_loads])


def resolved(component):
    return ([(p.anchor, value(p.n), value(p.h), value(p.m)) for p in component.points],
            [(line.members, value(line.n)) for line in component.line_loads])


@pytest.mark.parametrize("number", range(1, 17))
def test_every_component_is_its_factor_times_the_printed_basic_action(number):
    result = longitudinal()
    combination = result.combinations[number - 1]
    assert [c.case.value for c in combination.components] == [
        n for n, c in enumerate(combination.coefficients, 1) if c is not None]
    for component in combination.components:
        assert component.nominal == combination.coefficients[component.case.value - 1]
        if component.basis is Basis.SERVICE_IMPACT:
            impact = (result.impact.service_single if component.case is B.IMPACT_SINGLE
                      else result.impact.service_double)
            basic = [(NodeRole.CAP_TOP, impact.n, impact.m)]
            assert resolved(component) == ([(anchor, q(D(component.factor.value) * value(n), 2), D(0),
                                             q(D(component.factor.value) * value(m), 2)) for anchor, n, m in basic], [])
        else:
            assert component.factor == component.nominal
            assert resolved(component) == scaled(component.factor.value, result.basic(component.case))
        assert component.reversible is (component.case.value >= 13)


def test_combination_1_by_hand():
    combination = longitudinal().combinations[0]
    d1 = combination.component(B.D1)
    cap, footing = d1.points
    assert (cap.n.value, cap.m.value) == (9129.48, -671.0)  # 1.1 × 8299.53 = 9129.483; 1.1 × −610.00
    assert footing.n.value == 4584.2  # 1.1 × 4167.45 = 4584.195 -> 4584.20
    assert d1.line_loads[0].n.value == 327.45  # 1.1 × 297.68 = 327.448
    d2 = combination.component(B.D2)
    assert [(p.n.value, p.m.value) for p in d2.points] == [(936.0, 7.8), (2196.72, 0.0)]
    train = combination.component(B.TRAIN_DOUBLE).points[0]
    assert (train.n.value, train.m.value) == (1531.95, 298.39)  # 1.35 × 1134.78 = 1531.953; 1.35 × 221.03 = 298.3905
    assert combination.component(B.IMPACT_DOUBLE).basis is Basis.BASIC  # girder impact × 1.35
    rail = combination.component(B.SAFETY_LR10_B).points[0]
    assert (rail.n.value, rail.h.value, rail.m.value) == (0.0, 473.43, 0.0)


def test_serviceability_impact_comes_from_the_serviceability_girder_coefficient():
    result = longitudinal()
    for number, case, impact in ((5, B.IMPACT_DOUBLE, result.impact.service_double),
                                 (7, B.IMPACT_SINGLE, result.impact.service_single),
                                 (15, B.IMPACT_SINGLE, result.impact.service_single),
                                 (16, B.IMPACT_SINGLE, result.impact.service_single)):
        component = result.combinations[number - 1].component(case)
        # The printed 0.75 = ρ × 0.75 is already in the 0600 serviceability girder coefficient
        # (07 7-2: 0.245 × 0.75 = 0.184); only ρ (1.00) remains.
        assert (component.nominal.value, component.factor.value, component.basis) == (0.75, 1.0, Basis.SERVICE_IMPACT)
        assert (component.points[0].n, component.points[0].m) == (impact.n, impact.m)


def test_signed_variants_reverse_only_the_horizontal_action():
    combination = longitudinal().combinations[0]
    assert combination.signs == (1, -1)
    forward, backward = combination.signed(1), combination.signed(-1)
    assert forward == combination.components
    for a, b in zip(forward, backward, strict=True):
        if a.reversible:
            assert [(p.n, p.h.value, p.m.value) for p in b.points] == [(p.n, -p.h.value, -p.m.value + 0.0)
                                                                       for p in a.points]
        else:
            assert a == b
    assert longitudinal().combinations[13].signs == (1,)  # 14: long-term support, no horizontal case
    assert longitudinal().combinations[13].signed(-1) == longitudinal().combinations[13].components


def test_unknown_component_lookup():
    with pytest.raises(KeyError):
        longitudinal().combinations[13].component(B.TRAIN_DOUBLE)
