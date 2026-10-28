"""0610 Define cases, the combination table and the resolved actions: Example橋脚4 表2.3.2 / 表2.3.3, Example2 08
pp.8-9 to 8-11, hand calculations.

Decision 120: the combinations follow Example橋脚4 表2.3.2 (III-70〜III-73): every safety check is made at low and at
high water, the braking and long-rail maxima also with the reduced dead loads 0.9 D1 + 0.8 D2, the edge-stress and
permanent checks at low and high water, the variable check with the double-track train, and no single-track train or
impact on the longitudinal frame. Example2's 8-10 / 8-11 have 16 combinations without these (classification 3): its
table is no longer compared; the Example2 expectations here are the new structure and hand calculations.

WebPier makes the train, its impact and the bearing forces with the train or braking for each 列車の配置 ①②③ and
every check with the train for each placing (decision 102).
"""

from functools import cache
import json

import pytest

from example4_support import EXAMPLE4_INPUT
from longitudinal_support import diagram, longitudinal
from reaction_support import D, FIXTURES, pier, q, value
from webpier.calc.frame import NodeRole
from webpier.calc.longitudinal import Basis, BasicCase, Check, ExtractionGroup, Layout, Usage, Water
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.longitudinal.actions import HORIZONTAL_CASES, LAYOUT_DEPENDENT
from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.core.integrity import load_json
from webpier.export.soiljr import parse_sdc
from webpier.inputs import parse_input

B = BasicCase
C = Check
LOW, HIGH = Water.LOW, Water.HIGH
BOTH, ORIGIN, END = Layout.BOTH, Layout.ORIGIN, Layout.END
NOT_MADE = (B.TRAIN_SINGLE, B.IMPACT_SINGLE)  # decision 120 (g): no single-track train or impact on this frame
PICKUP = json.loads((FIXTURES / "example4" / "longitudinal_pickup.json").read_text(encoding="utf-8"))


@cache
def example4():
    """0610 of Example橋脚4 (no snow; ρ of safety and of serviceability 1.0) on the pile foundation of its frame
    springs (tests/calc/test_pile_frame.py)."""
    p = parse_input(load_json(EXAMPLE4_INPUT.read_bytes()))
    foundation = PileFoundation(calculate_pile_ground(p),
                                parse_sdc((FIXTURES / "soiljr" / "pile_steel_grid.sdc").read_bytes()))
    return calculate_longitudinal(p, foundation, calculate_reaction(p))


@cache
def example2():
    return longitudinal()


def of_check(result, check, layout=BOTH, water=LOW):
    return next(c for c in result.combinations
                if c.check is check and c.layout in (layout, None) and c.water in (water, None))


# --- Example橋脚4 表2.3.2 ---------------------------------------------------------------------------------------
# The sample's symbols as WebPier's basic cases. The water level of a buoyancy is read from the table's own remarks
# (備考): case 1 低水位 takes Wp2-1, case 4 高水位 Wp2-2, case 31 平水位 Wp1-1. (The load diagrams III-58〜59 head
# Wp2-1 浮力（高水位） and Wp2-2 浮力（低水位）, the other way round: a contradiction of the sample; the table is the
# combination's record.) L1 is the double-track train, I1 the safety impact (basic), I2 the serviceability impact.
SYMBOL = {"D1": B.D1, "D2": B.D2, "Wp1-1": B.BUOYANCY_NORMAL, "Wp2-1": B.BUOYANCY_LOW, "Wp2-2": B.BUOYANCY_HIGH,
          "L1": B.TRAIN_DOUBLE, "I1": B.IMPACT_DOUBLE, "I2": B.IMPACT_DOUBLE,
          "(B+LR)1": B.SAFETY_LR10_B, "(1.1B+LR)2": B.SAFETY_LR10_BMAX, "(1.1B+LR)3": B.SAFETY_LR10_BMAX_REDUCED,
          "(B+1.1LR)4": B.SAFETY_LR11_B, "(B+1.1LR)5": B.SAFETY_LR11_B_REDUCED, "(LR)6": B.SERVICE_LR08,
          "(LR)7": B.SERVICE_LR10, "(B+LR)8": B.RESTORABILITY_LR10_B}
PLACED = {"L1", "I1", "I2", "(B+LR)1", "(1.1B+LR)2", "(1.1B+LR)3", "(B+1.1LR)4", "(B+1.1LR)5", "(LR)7", "(B+LR)8"}
WATER = {"低水位": LOW, "高水位": HIGH, "平水位": None, None: None}


def sample_rows(checks):
    """表2.3.2 as (check, water, placing, {symbol: coefficient}): each row × ①②③ when it has the train."""
    rows = []
    for check, water, terms in checks:
        placed = any(symbol in PLACED for symbol, _ in terms)
        for layout in ((BOTH, ORIGIN, END) if placed else (None,)):
            rows.append((check, WATER[water], layout, dict(terms)))
    return rows


TRAIN_MAX = [("D1", 1.10), ("D2", 1.20), ("L1", 1.10), ("I1", 1.10), ("(B+LR)1", 1.00)]
BRAKING_MAX = [("D1", 1.10), ("D2", 1.20), ("L1", 1.00), ("(1.1B+LR)2", 1.00)]
# Case 15 prints the horizontal coefficient 23.00 (its case number 23 in the coefficient row): read as 1.00.
BRAKING_MAX_REDUCED = [("D1", 0.90), ("D2", 0.80), ("L1", 1.00), ("(1.1B+LR)3", 1.00)]
RAIL_MAX = [("D1", 1.10), ("D2", 1.20), ("L1", 1.00), ("I1", 1.00), ("(B+1.1LR)4", 1.00)]
# Cases 25〜30 print L 1.10 next to I 1.00: a misprint (the long-rail maximum takes 1.0 ρ L, as cases 19〜24 and
# 0600's 1.1 LR + 1.0 B with the train 1.0). WebPier: ρ = 1.00 (decision 120 (a)).
RAIL_MAX_REDUCED = [("D1", 0.90), ("D2", 0.80), ("L1", 1.00), ("I1", 1.00), ("(B+1.1LR)5", 1.00)]
EDGE = [("D1", 1.00), ("D2", 1.00), ("L1", 1.00), ("I2", 1.00), ("(LR)7", 1.00)]
PERMANENT = [("D1", 1.00), ("D2", 1.00), ("(LR)6", 1.00)]


def water(terms, symbol):
    return [*terms[:2], (symbol, 1.00), *terms[2:]]


SAMPLE = sample_rows([
    *[(check, level, water(terms, wp)) for check, terms in (
        (C.FAILURE_TRAIN_MAX, TRAIN_MAX), (C.FAILURE_BRAKING_MAX, BRAKING_MAX),
        (C.FAILURE_BRAKING_MAX_REDUCED, BRAKING_MAX_REDUCED), (C.FAILURE_RAIL_MAX, RAIL_MAX),
        (C.FAILURE_RAIL_MAX_REDUCED, RAIL_MAX_REDUCED)) for level, wp in (("低水位", "Wp2-1"), ("高水位", "Wp2-2"))],
    (C.SUPPORT_LONG_TERM, "平水位", [("D1", 1.00), ("D2", 1.00), ("Wp1-1", 1.00)]),  # 31
    (C.CRACK_PERMANENT_VARIABLE, "低水位", water(EDGE, "Wp2-1")),
    (C.CRACK_PERMANENT_VARIABLE, "高水位", water(EDGE, "Wp2-2")),
    (C.CRACK_PERMANENT, "低水位", water(PERMANENT, "Wp2-1")), (C.CRACK_PERMANENT, "高水位", water(PERMANENT, "Wp2-2")),
])


def made(combination):
    """{(case, placing): (applied factor, basis)} of a combination, the impact's basis naming I1 or I2."""
    return {(c.case, c.source.layout): (c.factor.value, c.basis) for c in combination.components}


def expected(layout, terms):
    found = {}
    for symbol, coefficient in terms.items():
        basis = Basis.SERVICE_IMPACT if symbol == "I2" else Basis.BASIC
        found[(SYMBOL[symbol], layout if symbol in PLACED else None)] = (coefficient, basis)
    return found


def test_example4_combinations_1_to_39_are_table_2_3_2():
    """The order (check, water level, placing) and every applied factor of 表2.3.2 cases 1〜39.

    Cases 1〜30 are WebPier's 1〜30. The sample has no snow maximum (no snow); WebPier makes the failure snow maximum
    at low and at high water even without snow, 31 and 32 (decision 69: the combinations, their numbers and the name
    雪最大 do not change without snow), so the sample's 31〜39 are WebPier's 33〜41 (classification: decision 69).
    The serviceability impact I2 prints 1.00 in the sample and its nominal 0.75 here (0.75 ρs, Example2 8-10's
    notation); the applied factor on the serviceability impact is ρs = 1.00 in both (decision 77)."""
    result = example4()
    assert len(SAMPLE) == 39
    combinations = (*result.combinations[:30], *result.combinations[32:41])
    assert [(c.number, c.check, c.water, c.layout) for c in combinations] == [
        (n if n <= 30 else n + 2, check, level, layout) for n, (check, level, layout, _) in enumerate(SAMPLE, 1)]
    for combination, (_, _, layout, terms) in zip(combinations, SAMPLE, strict=True):
        assert made(combination) == expected(layout, terms), combination.number


def test_example4_failure_snow_maxima_without_snow_have_no_snow_term():
    """Decision 69: 31 and 32 are the failure snow maximum at low and at high water, 1.1 D1 + 1.2 D2 + 1.0 Wp of the
    level + 1.0 (LR)10 without a snow term (the snow basic case is not made); not in the sample (no snow)."""
    result = example4()
    snow_max = result.combinations[30:32]
    assert [(c.number, c.check, c.water, c.layout) for c in snow_max] == [
        (31, C.FAILURE_SNOW_MAX, LOW, None), (32, C.FAILURE_SNOW_MAX, HIGH, None)]
    for c, buoyancy in zip(snow_max, (B.BUOYANCY_LOW, B.BUOYANCY_HIGH), strict=True):
        assert made(c) == {(B.D1, None): (1.1, Basis.BASIC), (B.D2, None): (1.2, Basis.BASIC),
                           (buoyancy, None): (1.0, Basis.BASIC), (B.SAFETY_LR10, None): (1.0, Basis.BASIC)}


def test_example4_combinations_after_39_differ_from_the_sample_by_decision_120():
    """表2.3.2 cases 40〜45 make the variable check (L1 + I2) at low and at high water, though it has no buoyancy:
    WebPier makes it once for each placing, 42〜44 (decision 120 (e); classification 3; +2 by decision 69). The damage
    check 46〜48 is therefore 45〜47; the sample's I2 and (B+LR)8 = case 27〜29 there are not copied (decision 120
    (f)): WebPier keeps ρ on the safety impact and the restorability 1.0 LR + 1.0 B, with the normal-water buoyancy.
    The damage snow maximum 48 is made without snow, with no snow term (decision 69; 48 combinations)."""
    result = example4()
    rest = result.combinations[41:]
    assert [(c.number, c.check, c.water, c.layout) for c in rest] == [
        (42, C.CRACK_VARIABLE, None, BOTH), (43, C.CRACK_VARIABLE, None, ORIGIN), (44, C.CRACK_VARIABLE, None, END),
        (45, C.DAMAGE_TRAIN_MAX, None, BOTH), (46, C.DAMAGE_TRAIN_MAX, None, ORIGIN),
        (47, C.DAMAGE_TRAIN_MAX, None, END), (48, C.DAMAGE_SNOW_MAX, None, None)]
    for c in rest[:3]:
        assert made(c) == {(B.TRAIN_DOUBLE, c.layout): (1.0, Basis.BASIC),
                           (B.IMPACT_DOUBLE, c.layout): (1.0, Basis.SERVICE_IMPACT)}
    for c in rest[3:6]:
        assert made(c) == {(B.D1, None): (1.0, Basis.BASIC), (B.D2, None): (1.0, Basis.BASIC),
                           (B.BUOYANCY_NORMAL, None): (1.0, Basis.BASIC),
                           (B.TRAIN_DOUBLE, c.layout): (1.0, Basis.BASIC),
                           (B.IMPACT_DOUBLE, c.layout): (1.0, Basis.BASIC),
                           (B.RESTORABILITY_LR10_B, c.layout): (1.0, Basis.BASIC)}
    assert made(rest[6]) == {(B.D1, None): (1.0, Basis.BASIC), (B.D2, None): (1.0, Basis.BASIC),
                             (B.BUOYANCY_NORMAL, None): (1.0, Basis.BASIC),
                             (B.RESTORABILITY_LR10, None): (1.0, Basis.BASIC)}


def test_example4_extractions_are_table_2_3_3():
    """PICK UP 1 and 6 are 1〜32 (sample 1〜30: WebPier keeps the snow maximum 31, 32 without snow, decision 69). The
    later groups are the sample's moved by 2 (decision 69): PICK UP 7 is 33 (sample 31), 2 and 8 34〜39 (sample
    32〜37), 3 40〜41 (sample 38〜39). PICK UP 4 is 42〜44 (sample 40〜45, the variable check at two water levels:
    decision 120 (e), classification 3) and 5 / 9 (damage) 45〜48 (sample 46〜48, plus the snow maximum 48: decision
    69). The sample's 9 PICK UP are WebPier's 8 groups (its 5 and 9 are both the damage group, decision 70)."""
    pickup = {row["pickup"]: tuple(row["combine"]) for row in PICKUP["rows"]}
    found = {e.group: e.combinations for e in example4().extractions}
    assert [e.group for e in example4().extractions] == list(ExtractionGroup)
    assert (found[ExtractionGroup.FAILURE], pickup[1]) == (tuple(range(1, 33)), tuple(range(1, 31)))
    assert (found[ExtractionGroup.STABILITY], pickup[6]) == (tuple(range(1, 33)), tuple(range(1, 31)))
    assert (found[ExtractionGroup.SUPPORT_LONG_TERM], pickup[7]) == ((33,), (31,))
    assert (found[ExtractionGroup.PERMANENT_VARIABLE], pickup[2]) == (tuple(range(34, 40)), tuple(range(32, 38)))
    assert (found[ExtractionGroup.SUPPORT_SHORT_TERM], pickup[8]) == (tuple(range(34, 40)), tuple(range(32, 38)))
    assert (found[ExtractionGroup.PERMANENT], pickup[3]) == ((40, 41), (38, 39))
    assert (found[ExtractionGroup.VARIABLE], pickup[4]) == ((42, 43, 44), tuple(range(40, 46)))
    assert (found[ExtractionGroup.DAMAGE], pickup[5], pickup[9]) == ((45, 46, 47, 48), (46, 47, 48), (46, 47, 48))


# --- Example2 (snow): the new structure --------------------------------------------------------------------------
ORDER = [  # (check, waters, placed) in the order made
    (C.FAILURE_TRAIN_MAX, (LOW, HIGH), True), (C.FAILURE_BRAKING_MAX, (LOW, HIGH), True),
    (C.FAILURE_BRAKING_MAX_REDUCED, (LOW, HIGH), True), (C.FAILURE_RAIL_MAX, (LOW, HIGH), True),
    (C.FAILURE_RAIL_MAX_REDUCED, (LOW, HIGH), True), (C.FAILURE_SNOW_MAX, (LOW, HIGH), False),
    (C.SUPPORT_LONG_TERM, (None,), False), (C.CRACK_PERMANENT_VARIABLE, (LOW, HIGH), True),
    (C.CRACK_PERMANENT, (LOW, HIGH), False), (C.CRACK_VARIABLE, (None,), True), (C.DAMAGE_TRAIN_MAX, (None,), True),
    (C.DAMAGE_SNOW_MAX, (None,), False)]


def order():
    return [(check, level, layout) for check, waters, placed in ORDER for level in waters for layout in ((BOTH, ORIGIN, END) if placed else (None,))]


def test_the_checks_are_numbered_in_the_order_made():
    assert [check for check, _, _ in ORDER] == list(Check) and [c.value for c in Check] == list(range(1, 13))


def test_example2_makes_48_combinations_check_water_then_placing():
    result = example2()
    assert [(c.number, c.check, c.water, c.layout) for c in result.combinations] == [
        (n, *made_as) for n, made_as in enumerate(order(), 1)]
    counts = {}
    for c in result.combinations:
        counts[c.check] = counts.get(c.check, 0) + 1
    assert counts == {C.FAILURE_TRAIN_MAX: 6, C.FAILURE_BRAKING_MAX: 6, C.FAILURE_BRAKING_MAX_REDUCED: 6,
                      C.FAILURE_RAIL_MAX: 6, C.FAILURE_RAIL_MAX_REDUCED: 6, C.FAILURE_SNOW_MAX: 2,
                      C.SUPPORT_LONG_TERM: 1, C.CRACK_PERMANENT_VARIABLE: 6, C.CRACK_PERMANENT: 2,
                      C.CRACK_VARIABLE: 3, C.DAMAGE_TRAIN_MAX: 3, C.DAMAGE_SNOW_MAX: 1}
    assert len(result.combinations) == 48


def test_example2_extractions():
    found = {e.group: e.combinations for e in example2().extractions}
    assert [e.number for e in example2().extractions] == list(range(1, 9))
    assert found == {
        ExtractionGroup.FAILURE: tuple(range(1, 33)), ExtractionGroup.STABILITY: tuple(range(1, 33)),
        ExtractionGroup.SUPPORT_LONG_TERM: (33,), ExtractionGroup.PERMANENT_VARIABLE: tuple(range(34, 40)),
        ExtractionGroup.SUPPORT_SHORT_TERM: tuple(range(34, 40)), ExtractionGroup.PERMANENT: (40, 41),
        ExtractionGroup.VARIABLE: (42, 43, 44), ExtractionGroup.DAMAGE: (45, 46, 47, 48)}


WATER_CASE = {LOW: B.BUOYANCY_LOW, HIGH: B.BUOYANCY_HIGH}


def test_example2_nominal_coefficients_by_check():
    """Each combination's nominal coefficients by case (ρ 1.23 of safety, 1.1 ρ = 1.35, ρs 1.00, 0.75 ρs = 0.75)."""
    rows = {
        C.FAILURE_TRAIN_MAX: {B.D1: 1.1, B.D2: 1.2, B.SNOW10: 1.0, B.TRAIN_DOUBLE: 1.35, B.IMPACT_DOUBLE: 1.35,
                              B.SAFETY_LR10_B: 1.0},
        C.FAILURE_BRAKING_MAX: {B.D1: 1.1, B.D2: 1.2, B.SNOW10: 1.0, B.TRAIN_DOUBLE: 1.23, B.SAFETY_LR10_BMAX: 1.0},
        C.FAILURE_BRAKING_MAX_REDUCED: {B.D1: 0.9, B.D2: 0.8, B.SNOW10: 1.0, B.TRAIN_DOUBLE: 1.23,
                                        B.SAFETY_LR10_BMAX_REDUCED: 1.0},
        C.FAILURE_RAIL_MAX: {B.D1: 1.1, B.D2: 1.2, B.SNOW10: 1.0, B.TRAIN_DOUBLE: 1.23, B.IMPACT_DOUBLE: 1.23,
                             B.SAFETY_LR11_B: 1.0},
        C.FAILURE_RAIL_MAX_REDUCED: {B.D1: 0.9, B.D2: 0.8, B.SNOW10: 1.0, B.TRAIN_DOUBLE: 1.23,
                                     B.IMPACT_DOUBLE: 1.23, B.SAFETY_LR11_B_REDUCED: 1.0},
        C.FAILURE_SNOW_MAX: {B.D1: 1.1, B.D2: 1.2, B.SNOW30: 1.0, B.SAFETY_LR10: 1.0},
        C.SUPPORT_LONG_TERM: {B.D1: 1.0, B.D2: 1.0, B.BUOYANCY_NORMAL: 1.0, B.SNOW2: 1.0},
        C.CRACK_PERMANENT_VARIABLE: {B.D1: 1.0, B.D2: 1.0, B.SNOW2: 1.0, B.TRAIN_DOUBLE: 1.0, B.IMPACT_DOUBLE: 0.75,
                                     B.SERVICE_LR10: 1.0},
        C.CRACK_PERMANENT: {B.D1: 1.0, B.D2: 1.0, B.SNOW2: 1.0, B.SERVICE_LR08: 1.0},
        C.CRACK_VARIABLE: {B.TRAIN_DOUBLE: 1.0, B.IMPACT_DOUBLE: 0.75},
        C.DAMAGE_TRAIN_MAX: {B.D1: 1.0, B.D2: 1.0, B.BUOYANCY_NORMAL: 1.0, B.SNOW10: 1.0, B.TRAIN_DOUBLE: 1.23,
                             B.IMPACT_DOUBLE: 1.23, B.RESTORABILITY_LR10_B: 1.0},
        C.DAMAGE_SNOW_MAX: {B.D1: 1.0, B.D2: 1.0, B.BUOYANCY_NORMAL: 1.0, B.SNOW30: 1.0, B.RESTORABILITY_LR10: 1.0},
    }
    result = example2()
    for c in result.combinations:
        want = dict(rows[c.check])
        if c.water is not None:
            want[WATER_CASE[c.water]] = 1.0
        assert {k.case: k.nominal.value for k in c.components} == want, c.number
        assert all(k.source.layout in (None, c.layout) for k in c.components)


def test_no_single_track_train_or_impact_on_the_longitudinal_frame():
    result = example2()
    assert not any(basic.case in NOT_MADE for basic in result.basic_cases)
    with pytest.raises(KeyError):
        result.basic(B.TRAIN_SINGLE)


def test_the_basic_cases_made():
    """Decision 120: no single-track train or impact; the reduced 1.1 LR + 1.0 B and 1.0 LR + 1.1 B of 0600 follow
    their unreduced twins, each for ①②③. Define n is basic case n, the horizontal ones in both directions."""
    result = example2()
    expected_cases = [(case, layout) for case in B if case not in NOT_MADE
                      for layout in ((BOTH, ORIGIN, END) if case in LAYOUT_DEPENDENT else (None,))]
    assert [(basic.case, basic.layout) for basic in result.basic_cases] == expected_cases
    assert [case for case in B if case not in NOT_MADE] == [
        B.D1, B.D2, B.BUOYANCY_HIGH, B.BUOYANCY_NORMAL, B.BUOYANCY_LOW, B.SNOW2, B.SNOW10, B.SNOW30, B.TRAIN_DOUBLE,
        B.IMPACT_DOUBLE, B.SERVICE_LR08, B.SERVICE_LR10, B.SAFETY_LR10_B, B.SAFETY_LR11_B, B.SAFETY_LR11_B_REDUCED,
        B.SAFETY_LR10_BMAX, B.SAFETY_LR10_BMAX_REDUCED, B.SAFETY_LR10, B.RESTORABILITY_LR10_B, B.RESTORABILITY_LR10]
    assert {case.name for case in LAYOUT_DEPENDENT} == {
        "TRAIN_DOUBLE", "IMPACT_DOUBLE", "SERVICE_LR10", "SAFETY_LR10_B", "SAFETY_LR11_B", "SAFETY_LR11_B_REDUCED",
        "SAFETY_LR10_BMAX", "SAFETY_LR10_BMAX_REDUCED", "RESTORABILITY_LR10_B"}
    assert [define.number for define in result.define_cases] == list(range(1, len(expected_cases) + 1))
    assert [(define.case, define.layout, define.signs) for define in result.define_cases] == [
        (case, layout, (1, -1) if case in HORIZONTAL_CASES else (1,)) for case, layout in expected_cases]


def test_without_snow_the_snow_maxima_are_made_without_snow():
    """Decision 69: Example橋脚4 (no snow) makes the same 48 combinations as with snow (30 + 2 + 1 + 6 + 2 + 3 + 3 + 1),
    the snow maxima included; no combination has a snow component."""
    result = example4()
    assert result.snow is None
    assert [(c.check, c.water, c.layout) for c in result.combinations] == order()
    assert len(result.combinations) == 48
    assert not any(k.case in (B.SNOW2, B.SNOW10, B.SNOW30) for c in result.combinations for k in c.components)


def test_example2_low_water_braking_maximum_by_hand():
    """Combination 7: 1.1 D1 + 1.2 D2 + 1.0 Wp(low) + 1.0 S10 + 1.23 L + 1.0 (1.0 LR + 1.35 B), ①."""
    c = example2().combinations[6]
    assert (c.check, c.water, c.layout) == (C.FAILURE_BRAKING_MAX, LOW, BOTH)
    cap, footing = c.component(B.D1).points
    assert (cap.n.value, cap.m.value, footing.n.value) == (9129.48, -671.0, 4584.2)  # see combination 1
    assert [(p.n.value, p.m.value) for p in c.component(B.D2).points] == [(936.0, 7.8), (2196.72, 0.0)]
    assert c.component(B.BUOYANCY_LOW).points[0].n.value == diagram(5)["P"] == 0.0  # low water 0.00 (8-6)
    assert (c.component(B.SNOW10).factor.value, c.component(B.SNOW10).points[0].n.value) == (1.0, diagram(7)["N"])
    train = c.component(B.TRAIN_DOUBLE).points[0]
    assert (train.n.value, train.m.value) == (1395.78, 271.87)  # 1.23 × 1134.78 = 1395.7794; 1.23 × 221.03 = 271.8669
    # decision 119: 308.00 + 188.62 = 496.62
    assert c.component(B.SAFETY_LR10_BMAX).points[0].h.value == 496.62
    with pytest.raises(KeyError):
        c.component(B.IMPACT_DOUBLE)  # the braking maximum has no impact (decision 119)


def test_example2_reduced_dead_loads_by_hand():
    """Combination 13 (reduced braking maximum, low water, ①) and 25 (reduced long-rail maximum, low water, ①):
    0.9 D1 + 0.8 D2, the 0600 reduced cases' bearing forces (520.42 and 537.69 of the 0600 hand checks)."""
    result = example2()
    braking, rail = result.combinations[12], result.combinations[24]
    assert (braking.check, braking.water, braking.layout) == (C.FAILURE_BRAKING_MAX_REDUCED, LOW, BOTH)
    assert (rail.check, rail.water, rail.layout) == (C.FAILURE_RAIL_MAX_REDUCED, LOW, BOTH)
    for c in (braking, rail):
        d1 = c.component(B.D1)
        cap, footing = d1.points
        # 0.9 × 8299.53 = 7469.577; 0.9 × −610.00 = −549.00; 0.9 × 4167.45 = 3750.705; 0.9 × 297.68 = 267.912
        assert (d1.factor.value, d1.factor.digits) == (0.9, 1)
        assert (cap.n.value, cap.m.value, footing.n.value, d1.line_loads[0].n.value) == (7469.58, -549.0, 3750.71,
                                                                                          267.91)
        d2 = c.component(B.D2)
        # 0.8 × 780.00 = 624.00; 0.8 × 6.50 = 5.20; 0.8 × 1830.60 = 1464.48
        assert (d2.factor.value, [(p.n.value, p.m.value) for p in d2.points]) == (0.8, [(624.0, 5.2), (1464.48, 0.0)])
        assert c.component(B.TRAIN_DOUBLE).factor.value == 1.23
    assert braking.component(B.SAFETY_LR10_BMAX_REDUCED).points[0].h.value == 520.42
    assert rail.component(B.SAFETY_LR11_B_REDUCED).points[0].h.value == 537.69
    assert rail.component(B.IMPACT_DOUBLE).factor.value == 1.23
    with pytest.raises(KeyError):
        braking.component(B.IMPACT_DOUBLE)


def test_high_water_takes_the_high_water_buoyancy():
    result = example2()
    high = of_check(result, C.FAILURE_TRAIN_MAX, water=HIGH)
    assert high.number == 4
    assert high.component(B.BUOYANCY_HIGH).points[0].n.value == diagram(3)["P"] == -2381.4
    with pytest.raises(KeyError):
        high.component(B.BUOYANCY_LOW)
    low = of_check(result, C.FAILURE_TRAIN_MAX)
    assert [k for k in low.components if k.case is not B.BUOYANCY_LOW] == [
        k for k in high.components if k.case is not B.BUOYANCY_HIGH]


def test_each_check_with_the_train_is_made_for_the_three_placings():
    result = example2()
    by_made = {}
    for c in result.combinations:
        by_made.setdefault((c.check, c.water), []).append(c)
    for (check, _), made_ in by_made.items():
        placed = any(k.case in LAYOUT_DEPENDENT for k in made_[0].components)
        if not placed:
            assert [c.layout for c in made_] == [None]
            continue
        assert [c.layout for c in made_] == list(Layout) and [c.number for c in made_] == [
            made_[0].number, made_[0].number + 1, made_[0].number + 2]
        for c in made_:
            assert all(component.source.layout in (None, c.layout) for component in c.components)
            assert [(k.case, k.nominal) for k in c.components] == [(k.case, k.nominal) for k in made_[0].components]


def test_usage_by_requirement():
    service = {C.CRACK_PERMANENT_VARIABLE, C.CRACK_PERMANENT, C.CRACK_VARIABLE, C.SUPPORT_LONG_TERM}
    assert all(c.usage is (Usage.SERVICE if c.check in service else Usage.ULTIMATE) for c in example2().combinations)


def test_factors_follow_the_input_load_factors():
    factors = longitudinal(pier(**{"上部構造/列車/荷重修正係数/安全性(破壊)": 1.25,
                                   "上部構造/列車/荷重修正係数/使用性": 0.9})).factors
    # 1.25 -> 1.25; 1.1 × 1.25 = 1.375 -> 1.38; 0.900 -> 0.90; 0.75 × 0.900 = 0.675 -> 0.68 (half up)
    assert [factors.ultimate.value, factors.maximum.value, factors.service.value, factors.service_impact.value] == [
        1.25, 1.38, 0.9, 0.68]
    assert [factors.d1_safety.value, factors.d2_safety.value, factors.one.value] == [1.1, 1.2, 1.0]
    assert [(f.value, f.digits) for f in (factors.d1_reduced, factors.d2_reduced)] == [(0.9, 1), (0.8, 1)]


def scaled(factor, basic):
    """Each printed N, H, M (and q) of the basic action times the factor, rounded once to its digits."""
    return ([(p.anchor, q(D(factor) * value(p.n), 2), q(D(factor) * value(p.h), 2), q(D(factor) * value(p.m), 2))
             for p in basic.points],
            [(line.members, q(D(factor) * value(line.n), 2)) for line in basic.line_loads])


def resolved(component):
    return ([(p.anchor, value(p.n), value(p.h), value(p.m)) for p in component.points],
            [(line.members, value(line.n)) for line in component.line_loads])


@pytest.mark.parametrize("number", range(1, 49))
def test_every_component_is_its_factor_times_the_printed_basic_action(number):
    result = example2()
    combination = result.combinations[number - 1]
    made_ = [result.basic_cases[i] for i, c in enumerate(combination.coefficients) if c is not None]
    assert [(c.case, c.source.layout) for c in combination.components] == [(b.case, b.layout) for b in made_]
    impacts = {Layout.BOTH: result.impact, **{placed.layout: placed.impact for placed in result.one_girder}}
    for component, basic in zip(combination.components, made_, strict=True):
        assert component.nominal == combination.coefficients[result.basic_cases.index(basic)]
        if component.basis is Basis.SERVICE_IMPACT:
            impact = impacts[combination.layout].service_double
            basic = [(NodeRole.CAP_TOP, impact.n, impact.m)]
            assert resolved(component) == ([(anchor, q(D(component.factor.value) * value(n), 2), D(0),
                                             q(D(component.factor.value) * value(m), 2)) for anchor, n, m in basic], [])
        else:
            assert component.factor == component.nominal
            assert resolved(component) == scaled(component.factor.value, basic)
        assert component.reversible is (component.case in HORIZONTAL_CASES)


def test_combination_1_by_hand():
    combination = example2().combinations[0]
    assert (combination.check, combination.water, combination.layout) == (C.FAILURE_TRAIN_MAX, LOW, BOTH)
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
    assert combination.component(B.BUOYANCY_LOW).factor.value == 1.0  # decision 120 (b)


def test_serviceability_impact_comes_from_the_serviceability_girder_coefficient():
    result = example2()
    for check in (C.CRACK_PERMANENT_VARIABLE, C.CRACK_VARIABLE):
        component = of_check(result, check).component(B.IMPACT_DOUBLE)
        # The printed 0.75 = ρ × 0.75 is already in the 0600 serviceability girder coefficient
        # (07 7-2: 0.245 × 0.75 = 0.184); only ρ (1.00) remains.
        assert (component.nominal.value, component.factor.value, component.basis) == (0.75, 1.0, Basis.SERVICE_IMPACT)
        impact = result.impact.service_double
        assert (component.points[0].n, component.points[0].m) == (impact.n, impact.m)


def test_signed_variants_reverse_only_the_horizontal_action():
    combination = example2().combinations[0]
    assert combination.signs == (1, -1)
    forward, backward = combination.signed(1), combination.signed(-1)
    assert forward == combination.components
    for a, b in zip(forward, backward, strict=True):
        if a.reversible:
            assert [(p.n, p.h.value, p.m.value) for p in b.points] == [(p.n, -p.h.value, -p.m.value + 0.0)
                                                                       for p in a.points]
        else:
            assert a == b
    long_term = of_check(example2(), C.SUPPORT_LONG_TERM)  # no horizontal case
    assert long_term.signs == (1,) and long_term.signed(-1) == long_term.components


def test_unknown_component_lookup():
    with pytest.raises(KeyError):
        of_check(example2(), C.SUPPORT_LONG_TERM).component(B.TRAIN_DOUBLE)
    with pytest.raises(KeyError):
        example2().basic(B.TRAIN_DOUBLE, layout=None)  # a case of each placing has no case for every placing


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
                impact = impacts[combination.layout].service_double
                (point,) = component.source.points
                # The seat moment: M − N × offset; the pedestal top is +0.175 from the column axis, both bearing
                # lines −0.325 and +0.675 on its edges (0.175 ± 0.500, decision 81).
                offset = D("0.175") if changes else D(0)
                assert (component.source.case, component.source.spring, component.source.line_loads) == (
                    basic.case, basic.spring, ())
                assert (point.node, value(point.n), value(point.h), value(point.m)) == (
                    seat, value(impact.n), D(0), q(value(impact.m) - value(impact.n) * offset, 2))
            assert resolved(component) == scaled(component.factor.value, component.source)
