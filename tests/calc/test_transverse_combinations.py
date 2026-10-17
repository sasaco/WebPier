"""0620 Define cases, combinations and the resolved actions: Example2 09 pp.9-13 to 9-15, hand calculations."""

import pytest

from reaction_support import D, pier, q, value
from transverse_support import SECTIONS, transverse
from webpier.calc.longitudinal import Basis, Usage
from webpier.calc.transverse import BasicCase, Define, Track

B = BasicCase
TABLE = SECTIONS["combinations"]["combination_table"]["rows"]
# (combination, Define) of the serviceability train L: Example2 prints ρs = 1.0 with 1 decimal.
SERVICE_TRAIN = {(5, 10), (7, 9), (15, 9), (16, 9)}


def test_9_13_define_cases():
    printed = SECTIONS["define_cases"]["rows"]
    result = transverse()
    assert [define.number for define in result.define_cases] == [row["no"] for row in printed]
    signed = [tuple(sign * case.value for case in define.cases for sign in define.signs)
              for define in result.define_cases]
    assert signed == [tuple(row["C"]) for row in printed]  # 9: {9, 10}, 11: {12, 13}, 13-15: ±
    assert [define.define for define in result.define_cases] == list(Define)[:15]  # no centrifugal on a straight


def test_9_14_combination_table_values_and_digits():
    result = transverse()
    assert [c.number for c in result.combinations] == [row["no"] for row in TABLE]
    for combination, row in zip(result.combinations, TABLE, strict=True):
        assert [None if c is None else c.value for c in combination.coefficients] == row["coefficients"]
        for define, (ours, printed) in enumerate(zip(combination.coefficients, row["digits"], strict=True), 1):
            if (combination.number, define) in SERVICE_TRAIN:
                # ρs comes from the input load factor and prints like every ρ-derived factor (1.00), as in 0610.
                assert (printed, ours.digits) == (1, 2)
            else:
                assert (None if ours is None else ours.digits) == printed


def test_usage_by_requirement():
    service = {5, 6, 7, 14, 15, 16}
    assert [c.usage for c in transverse().combinations] == [
        Usage.SERVICE if n in service else Usage.ULTIMATE for n in range(1, 17)]


def test_9_15_extraction_cases():
    printed = SECTIONS["extraction_cases"]["rows"]
    assert [(e.number, e.combinations) for e in transverse().extractions] == [
        (row["no"], tuple(row["combinations"])) for row in printed]


def test_factors_follow_the_input_load_factors():
    result = transverse(pier(**{"上部構造/列車/荷重修正係数/安全性(破壊)": 1.25, "上部構造/列車/荷重修正係数/使用性": 0.9}))
    first, second, fifth = result.combinations[0], result.combinations[1], result.combinations[4]
    # 1.1 × 1.25 = 1.375 -> 1.38 (train maximum); LF 1.25 (ρ) in 1 and 1.38 in 2 (車横最大).
    assert [first.coefficients[n - 1].value for n in (10, 12, 13)] == [1.38, 1.38, 1.25]
    assert [second.coefficients[n - 1].value for n in (10, 12, 13)] == [1.25, 1.25, 1.38]
    assert [fifth.coefficients[n - 1].value for n in (10, 12)] == [0.9, 0.68]  # 0.75 × 0.900 = 0.675 -> 0.68
    assert result.combinations[2].coefficients[14].value == 1.2  # W2 in 風最大, a fixed factor


def scaled(factor, action):
    f = D(factor)
    return ([(p.node, q(f * value(p.n), 2), q(f * value(p.h), 2), q(f * value(p.m), 2)) for p in action.points],
            [(line.members, q(f * value(line.n), 2), q(f * value(line.h), 2)) for line in action.line_loads],
            [(m.member, value(m.start), value(m.end), q(f * value(m.h_start), 2), q(f * value(m.h_end), 2))
             for m in action.member_loads])


def resolved(component, sign=1):
    s = D(sign)
    return ([(p.node, value(p.n), s * value(p.h), s * value(p.m)) for p in component.points],
            [(line.members, value(line.n), value(line.h)) for line in component.line_loads],
            [(m.member, value(m.start), value(m.end), s * value(m.h_start), s * value(m.h_end))
             for m in component.member_loads])


@pytest.mark.parametrize("number", range(1, 17))
def test_every_alternative_is_its_factor_times_the_printed_basic_action(number):
    result = transverse()
    combination = result.combinations[number - 1]
    assert [c.define.value for c in combination.components] == [
        n for n, c in enumerate(combination.coefficients, 1) if c is not None]
    for component in combination.components:
        assert component.nominal == combination.coefficients[component.define.value - 1]
        define = result.define_cases[component.define.value - 1]
        assert [(a.case, a.sign) for a in component.alternatives] == [
            (case, sign) for case in define.cases for sign in define.signs]
        for alternative in component.alternatives:
            assert alternative.nominal == component.nominal
            if alternative.basis is Basis.SERVICE_IMPACT:
                impact = result.impact.service.table(alternative.track)
                assert alternative.factor == result.factors.service
                f = D(alternative.factor.value)
                assert resolved(alternative) == ([(1, q(f * value(impact.n), 2), D(0), q(f * value(impact.m), 2))],
                                                 [], [])
                # The source is the serviceability impact at the seat, unscaled.
                assert [(p.node, p.n, p.m) for p in alternative.source.points] == [(1, impact.n, impact.m)]
                assert alternative.source.case is alternative.case
            else:
                assert alternative.factor == alternative.nominal
                assert alternative.source == result.basic(alternative.case)  # unscaled, positive direction
                assert resolved(alternative, alternative.sign) == scaled(alternative.factor.value,
                                                                         alternative.source)


def test_serviceability_impact_comes_from_the_serviceability_girder_coefficients():
    result = transverse()
    for number, define in ((5, Define.IMPACT_DOUBLE), (7, Define.IMPACT_SINGLE), (15, Define.IMPACT_SINGLE),
                           (16, Define.IMPACT_SINGLE)):
        component = result.combinations[number - 1].component(define)
        for alternative in component.alternatives:
            # The printed 0.75 = ρs × 0.75 is already in the 0600 serviceability coefficient; only ρs (1.00) remains.
            assert (alternative.nominal.value, alternative.factor.value, alternative.basis) == (
                0.75, 1.0, Basis.SERVICE_IMPACT)
            table = result.impact.service.table(alternative.track)
            assert (alternative.points[0].n, alternative.points[0].m) == (table.n, table.m)
    # In the ultimate combinations the basic impact (girder coefficients) takes the nominal factor.
    assert result.combinations[0].component(Define.IMPACT_DOUBLE).alternatives[0].basis is Basis.BASIC


def test_combination_1_by_hand():
    combination = transverse().combinations[0]
    d1 = combination.component(Define.D1).alternatives[0]
    assert [(p.n.value, p.m.value) for p in d1.points] == [(9129.48, 0.0), (4584.2, 0.0)]  # 1.1 × 8299.53 = 9129.483
    assert d1.line_loads[0].n.value == 327.45  # 1.1 × 297.68 = 327.448
    train = combination.component(Define.TRAIN_DOUBLE).alternatives[0].points[0]
    assert (train.n.value, train.m.value) == (1531.95, 0.0)  # 1.35 × 1134.78 = 1531.953
    lateral = combination.component(Define.LATERAL).alternatives
    # 1.23 × 111.69 = 137.3787 -> 137.38; 1.23 × 430.01 = 528.9123 -> 528.91; the other sign reverses H and M.
    assert [(a.sign, a.points[0].h.value, a.points[0].m.value) for a in lateral] == [
        (1, 137.38, 528.91), (-1, -137.38, -528.91)]
    wind = combination.component(Define.WIND_WITH_TRAIN).alternatives
    assert [m.h_start.value for a in wind for m in a.member_loads] == [4.05] * 3 + [-4.05] * 3


def test_wind_maximum_by_hand():
    combination = transverse().combinations[2]  # 風最大: W2 × 1.2
    plus, minus = combination.component(Define.WIND_WITHOUT_TRAIN).alternatives
    # 1.2 × 611.75 = 734.10; 1.2 × 4248.93 = 5098.716 -> 5098.72; 1.2 × 8.10 = 9.72 kN/m.
    assert (plus.points[0].h.value, plus.points[0].m.value) == (734.1, 5098.72)
    assert [m.h_start.value for m in plus.member_loads] == [9.72] * 3
    assert [m.h_start.value for m in minus.member_loads] == [-9.72] * 3


def test_variants_keep_one_track_and_every_sign():
    combinations = transverse().combinations
    count = {c.number: len(c.variants()) for c in combinations}
    # 1, 2, 8, 10, 11: LF ± × W1 ±; 3, 9, 12: one wind ±; 7, 15, 16: up or down; the rest: one.
    assert count == {1: 4, 2: 4, 3: 2, 4: 1, 5: 1, 6: 1, 7: 2, 8: 4, 9: 2, 10: 4, 11: 4, 12: 2, 13: 1, 14: 1,
                     15: 2, 16: 2}
    for combination in combinations:
        for variant in combination.variants():
            assert len(variant) == len(combination.components)
            single = {a.track for a in variant if a.track in (Track.UP, Track.DOWN)}
            assert len(single) <= 1  # an up train never goes with a down impact
    seventh = combinations[6].variants()
    assert [[a.case for a in v] for v in seventh] == [[B.TRAIN_UP, B.IMPACT_UP], [B.TRAIN_DOWN, B.IMPACT_DOWN]]
    signs = {tuple(a.sign for a in v if a.case in (B.LATERAL, B.WIND_WITH_TRAIN)) for v in combinations[0].variants()}
    assert signs == {(1, 1), (1, -1), (-1, 1), (-1, -1)}


def test_unknown_component_lookup():
    with pytest.raises(KeyError):
        transverse().combinations[13].component(Define.TRAIN_DOUBLE)
