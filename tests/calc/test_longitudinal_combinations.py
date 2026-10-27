"""0610 Define cases, the combination table and the resolved actions: Example2 08 pp.8-9 to 8-11, hand calculations.

Example2 has only the train on both girders (列車の配置 ①). WebPier makes the train, its impact and the bearing forces
with the train or braking for ②, ③ too and every check with the train for each placing (decision 102): ① alone —
the cases of ① and of every placing, the combinations of ① and those without the train — is the sample's table.
"""

import pytest

from longitudinal_support import SECTIONS, longitudinal
from reaction_support import D, pier, q, value
from webpier.calc.frame import NodeRole
from webpier.calc.longitudinal import Basis, BasicCase, Check, Layout, Usage
from webpier.calc.longitudinal.actions import LAYOUT_DEPENDENT

B = BasicCase
TABLE = SECTIONS["combinations"]["combination_table"]["rows"]
SERVICE_TRAIN = {(5, 10), (7, 9), (15, 9), (16, 9)}  # (combination, basic case) of the serviceability train L
FIRST = (None, Layout.BOTH)


def first(result):
    """The indices of ①'s basic cases and ①'s combinations, as Example2 numbers them."""
    return ([index for index, basic in enumerate(result.basic_cases) if basic.layout in FIRST],
            [combination for combination in result.combinations if combination.layout in FIRST])


def of_check(result, check, layout=Layout.BOTH):
    return next(c for c in result.combinations if c.check is check and c.layout in (layout, None))


def test_8_9_define_cases():
    printed = SECTIONS["define_cases"]["rows"]
    result = longitudinal()
    assert [define.number for define in result.define_cases] == list(range(1, 39))
    defines = [define for define in result.define_cases if define.layout in FIRST]
    assert [define.case.value for define in defines] == [row["C"][0] for row in printed]
    assert [tuple(sign * define.case.value for sign in define.signs) for define in defines] == [
        tuple(row["C"]) for row in printed]  # 13-20 both signs of the horizontal case


def test_a_case_of_the_train_is_made_for_each_placing_in_turn():
    result = longitudinal()
    made = [(basic.case, basic.layout) for basic in result.basic_cases]
    assert made == [(case, layout) for case in B for layout in (tuple(Layout) if case in LAYOUT_DEPENDENT else (None,))]
    assert {case.name for case in LAYOUT_DEPENDENT} == {
        "TRAIN_SINGLE", "TRAIN_DOUBLE", "IMPACT_SINGLE", "IMPACT_DOUBLE", "SERVICE_LR10", "SAFETY_LR10_B",
        "SAFETY_LR11_B", "SAFETY_LR10_BMAX", "RESTORABILITY_LR10_B"}


def test_8_10_combination_table_values():
    result = longitudinal()
    cases, combinations = first(result)
    assert len(combinations) == len(TABLE)
    for combination, row in zip(combinations, TABLE, strict=True):
        assert [None if combination.coefficients[i] is None else combination.coefficients[i].value
                for i in cases] == row["coefficients"]


def test_each_check_with_the_train_is_made_for_the_three_placings():
    """The 11 checks with the train, ①, ② and ③ in turn, each on its placing's cases with the same nominal factors;
    the five without the train once: 38 combinations."""
    result = longitudinal()
    assert [c.number for c in result.combinations] == list(range(1, 39))
    by_check = {}
    for c in result.combinations:
        by_check.setdefault(c.check, []).append(c)
    without = {Check.FAILURE_SNOW_MAX, Check.CRACK_PERMANENT, Check.DAMAGE_SNOW_MAX, Check.STABILITY_SNOW_MAX,
               Check.SUPPORT_LONG_TERM}
    for check, made in by_check.items():
        if check in without:
            assert [c.layout for c in made] == [None]
            continue
        assert [c.layout for c in made] == list(Layout) and [c.number for c in made] == [
            made[0].number, made[0].number + 1, made[0].number + 2]
        for c in made:
            assert all(component.source.layout in (None, c.layout) for component in c.components)
            assert [(k.case, k.nominal) for k in c.components] == [(k.case, k.nominal) for k in made[0].components]


def test_8_10_combination_table_digits():
    result = longitudinal()
    cases, combinations = first(result)
    for number, (combination, row) in enumerate(zip(combinations, TABLE, strict=True), 1):
        ours_by_case = [combination.coefficients[i] for i in cases]
        for case, (ours, printed) in enumerate(zip(ours_by_case, row["digits"], strict=True), 1):
            if (number, case) in SERVICE_TRAIN:
                # Example2 prints the serviceability train factor ρ = 1.0 with 1 decimal; the factor comes from the
                # input load factor and is printed like every ρ-derived factor, with 2 decimals (1.00).
                assert (printed, ours.digits) == (1, 2)
            else:
                assert (None if ours is None else ours.digits) == printed


def test_usage_by_requirement():
    service = {5, 6, 7, 14, 15, 16}  # 耐久性・使用性 and 使用性 (支持)
    assert all(c.usage is (Usage.SERVICE if c.check.value in service else Usage.ULTIMATE)
               for c in longitudinal().combinations)


def test_8_11_extraction_cases():
    """Example2's groups of ①; each group also takes ② and ③ of its checks (decision 102)."""
    printed = SECTIONS["extraction_cases"]["rows"]
    result = longitudinal()
    _, combinations = first(result)
    position = {c.number: index for index, c in enumerate(combinations, 1)}
    assert [(e.number, tuple(position[n] for n in e.combinations if n in position)) for e in result.extractions] == [
        (row["no"], tuple(row["combinations"])) for row in printed]
    checks = {c.number: c.check.value for c in result.combinations}
    for extraction, row in zip(result.extractions, printed, strict=True):
        assert extraction.combinations == tuple(c.number for c in result.combinations
                                                if c.check.value in {checks[n] for n in extraction.combinations})


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


@pytest.mark.parametrize("number", range(1, 39))
def test_every_component_is_its_factor_times_the_printed_basic_action(number):
    result = longitudinal()
    combination = result.combinations[number - 1]
    made = [result.basic_cases[i] for i, c in enumerate(combination.coefficients) if c is not None]
    assert [(c.case, c.source.layout) for c in combination.components] == [(b.case, b.layout) for b in made]
    impacts = {Layout.BOTH: result.impact, **{placed.layout: placed.impact for placed in result.one_girder}}
    for component, basic in zip(combination.components, made, strict=True):
        assert component.nominal == combination.coefficients[result.basic_cases.index(basic)]
        if component.basis is Basis.SERVICE_IMPACT:
            placed = impacts[combination.layout]
            impact = placed.service_single if component.case is B.IMPACT_SINGLE else placed.service_double
            basic = [(NodeRole.CAP_TOP, impact.n, impact.m)]
            assert resolved(component) == ([(anchor, q(D(component.factor.value) * value(n), 2), D(0),
                                             q(D(component.factor.value) * value(m), 2)) for anchor, n, m in basic], [])
        else:
            assert component.factor == component.nominal
            assert resolved(component) == scaled(component.factor.value, basic)
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
    for check, case, impact in ((Check.CRACK_PERMANENT_VARIABLE, B.IMPACT_DOUBLE, result.impact.service_double),
                                (Check.CRACK_VARIABLE, B.IMPACT_SINGLE, result.impact.service_single),
                                (Check.SUPPORT_SHORT_TERM_LOW_WATER, B.IMPACT_SINGLE, result.impact.service_single),
                                (Check.SUPPORT_SHORT_TERM_HIGH_WATER, B.IMPACT_SINGLE, result.impact.service_single)):
        component = of_check(result, check).component(case)
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
    long_term = of_check(longitudinal(), Check.SUPPORT_LONG_TERM)  # no horizontal case
    assert long_term.signs == (1,) and long_term.signed(-1) == long_term.components


def test_unknown_component_lookup():
    with pytest.raises(KeyError):
        of_check(longitudinal(), Check.SUPPORT_LONG_TERM).component(B.TRAIN_DOUBLE)
    with pytest.raises(KeyError):
        longitudinal().basic(B.TRAIN_DOUBLE, layout=None)  # a case of each placing has no case for every placing


PEDESTAL = {"下部構造/寸法/側面/B2": 1.025, "下部構造/寸法/側面/B3": 1.0, "下部構造/寸法/正面/W2": 1.0,
            "下部構造/寸法/正面/W3": 7.0, "下部構造/寸法/高さ/H1": 0.3}


@pytest.mark.parametrize("changes", [{}, PEDESTAL], ids=["no_pedestal", "pedestal"])
def test_each_component_keeps_the_action_its_factor_applies_to(changes):
    # The FrameWeb input analyses the factor times this action, so it must be the unscaled action itself:
    # the basic action, or the serviceability impact at the bearing seat (decision 29).
    result = longitudinal(pier(**changes))
    seat = result.frame.bearing_seat.number
    impacts = {Layout.BOTH: result.impact, **{placed.layout: placed.impact for placed in result.one_girder}}
    for combination in result.combinations:
        for component in combination.components:
            basic = result.basic(component.case, combination.layout or Layout.BOTH)
            if component.basis is Basis.BASIC:
                assert component.source == basic
            else:
                placed = impacts[combination.layout]
                impact = placed.service_single if component.case is B.IMPACT_SINGLE else placed.service_double
                (point,) = component.source.points
                # The seat moment: M − N × offset; the pedestal top is +0.175 from the column axis, both bearing
                # lines −0.325 and +0.675 on its edges (0.175 ± 0.500, decision 81).
                offset = D("0.175") if changes else D(0)
                assert (component.source.case, component.source.spring, component.source.line_loads) == (
                    basic.case, basic.spring, ())
                assert (point.node, value(point.n), value(point.h), value(point.m)) == (
                    seat, value(impact.n), D(0), q(value(impact.m) - value(impact.n) * offset, 2))
            assert resolved(component) == scaled(component.factor.value, component.source)
