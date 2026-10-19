"""The action tables and the 31 combinations of the cantilever (decision 59; Example2 13-24 .. 13-37), and the
governing case of each check (the WDJ force table). The N and Mt totals of the sample are expected where the inputs
coincide; the Md values carry the sample's end X 0.645 and are recomputed by hand from the printed parts instead."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cantilever_support import SAMPLE, D, q, result_of, value
from webpier.calc.cantilever import COLUMNS, DEFINITIONS, LimitState, Quantity, Side
from webpier.calc.cantilever.actions import (D1, D2, EQ_TRANSVERSE, REACTION, RUBBER, SELF_WEIGHT, STOPPER,
                                             ActionKey, Group)
from webpier.calc.cantilever.combinations import (FORCE_ROWS, CaseResult, Contribution, Selection, adopt, evaluate,
                                                  factor, train_factor)
from webpier.calc.cantilever.loads import Loading, Wind
from webpier.calc.moving_load import Girder
from webpier.calc.reaction.longitudinal import LongitudinalCase, Snow


@pytest.fixture(scope="module")
def current():
    return result_of()


def _actions(result, side=Side.LEFT):
    return {action.key: action for action in result.sides[side].actions}


def test_the_actions_come_in_report_order(current):
    _, _, result = current
    keys = [action.key for action in result.sides[Side.LEFT].actions]
    assert keys[:5] == [D1, D2, ActionKey.snow(Snow.S2), ActionKey.snow(Snow.S10), ActionKey.snow(Snow.S30)]
    assert keys[5:9] == [ActionKey.train(Loading.ORIGIN_MAX), ActionKey.train(Loading.END_MAX),
                         ActionKey.train(Loading.BOTH_MAX), ActionKey.train(None)]
    assert keys[9:15] == [ActionKey.impact(group, loading) for group in Group for loading in Loading]
    assert keys[15:18] == [ActionKey.lateral(loading) for loading in Loading]
    assert keys[18:20] == [ActionKey.wind(Wind.WITH_TRAIN), ActionKey.wind(Wind.WITHOUT_TRAIN)]
    assert keys[20] == EQ_TRANSVERSE
    assert keys[21:] == [ActionKey.bearing(case) for case in (LongitudinalCase.SAFETY_LR10_B10,
                                                              LongitudinalCase.SAFETY_LR11_B10,
                                                              LongitudinalCase.SAFETY_LR10_B11,
                                                              LongitudinalCase.SAFETY_LR10, None)]
    assert len(keys) == 26 and len(set(keys)) == 26
    assert ActionKey.train(None).variant == "地震時" and ActionKey.bearing(None).variant == "地震時"


def test_the_dead_load_action_with_the_self_weight(current):
    _, _, result = current
    action = _actions(result)[D1]
    expected = SAMPLE["actions"]["D1"]
    assert action.title == "固定死荷重D1"
    weight, origin, end = action.rows
    assert (weight.label, weight.n.value, weight.md.value, weight.x, weight.arm, weight.mt.value) == (
        SELF_WEIGHT, expected["self_weight"]["n"], expected["self_weight"]["md"], None, None, 0.0)
    assert (origin.label, origin.sublabel, origin.n.value, origin.x.value, origin.arm.value, origin.mt.value) == (
        REACTION, "起点側 Ｇ1桁", expected["origin"]["n"], 1.55, -0.325, expected["origin"]["mt"])
    assert (end.sublabel, end.n.value, end.x.value, end.arm.value, end.mt.value) == (
        "終点側 Ｇ1桁", expected["end"]["n"], 0.7, 0.675, expected["end"]["mt"])
    assert value(origin.md) == q(D(1530) * D(1.55), 2) and value(end.md) == q(D(930) * D(0.7), 2)
    assert (action.n.value, action.mt.value, action.h.value) == (expected["total_n"], expected["total_mt"], 0.0)
    assert value(action.md) == q(D(373.96) + D(2371.5) + D(651), 2)  # with X 0.700, not the sample's 3345.31


@pytest.mark.parametrize("key,name", [(D2, "D2"), (ActionKey.snow(Snow.S2), "S2"), (ActionKey.snow(Snow.S10), "S10"),
                                      (ActionKey.snow(Snow.S30), "S30")])
def test_the_other_dead_and_snow_actions(current, key, name):
    _, _, result = current
    action = _actions(result)[key]
    expected = SAMPLE["actions"][name]
    assert (action.n.value, action.mt.value) == (expected["total_n"], expected["total_mt"])
    assert len(action.rows) == 2 and all(row.n is not None for row in action.rows)
    for row in action.rows:
        assert value(row.md) == q(value(row.n) * value(row.x), 2) and value(row.mt) == q(value(row.n) * value(row.arm), 2)
    assert value(action.n) == sum(value(row.n) for row in action.rows)
    assert value(action.md) == sum(value(row.md) for row in action.rows)


def test_the_train_lateral_and_seismic_actions(current):
    _, _, result = current
    tables = _actions(result)
    for loading in Loading:
        expected = SAMPLE["actions"]["L"][loading.value]
        action = tables[ActionKey.train(loading)]
        assert (action.n.value, action.mt.value) == (expected["total_n"], expected["total_mt"])
        assert action.title == f"列車荷重L {loading.value}の場合"
        lateral = tables[ActionKey.lateral(loading)]
        expected = SAMPLE["actions"]["LF"][loading.value]
        assert (lateral.n.value, lateral.mt.value) == (expected["total_n"], expected["total_mt"])
    seismic = tables[ActionKey.train(None)]
    assert seismic.n.value == SAMPLE["actions"]["L"]["地震時"]["total_n"]
    assert value(seismic.mt) == q(D(150.72) * D(-0.325), 2) + q(D(137.12) * D(0.675), 2)  # 43.58; the sample 43.57
    assert [row.n.value for row in seismic.rows] == [150.72, 137.12]


def test_the_impact_actions_of_both_groups(current):
    _, _, result = current
    tables = _actions(result)
    ultimate = SAMPLE["actions"]["I_ultimate"]
    b = tables[ActionKey.impact(Group.ULTIMATE, Loading.ORIGIN_MAX)]
    assert (b.n.value, b.mt.value) == (ultimate["B支点最大"]["total_n"], ultimate["B支点最大"]["total_mt"])
    c = tables[ActionKey.impact(Group.ULTIMATE, Loading.END_MAX)]
    assert [row.n.value for row in c.rows] == [11.85, 217.18]  # 229.03; the sample 229.04 from unrounded parts
    bc = tables[ActionKey.impact(Group.ULTIMATE, Loading.BOTH_MAX)]
    assert (bc.n.value, bc.mt.value) == (ultimate["B+C支点最大"]["total_n"], ultimate["B+C支点最大"]["total_mt"])
    for loading in Loading:
        service = tables[ActionKey.impact(Group.SERVICE, loading)]
        assert service.n.value < tables[ActionKey.impact(Group.ULTIMATE, loading)].n.value
        assert service.title == f"衝撃荷重I 使用性 {loading.value}の場合"
    assert [row.n.value for row in tables[ActionKey.impact(Group.SERVICE, Loading.ORIGIN_MAX)].rows] == [44.87, 0.0]


def test_the_wind_and_seismic_transverse_actions_follow_the_torques(current):
    _, _, result = current
    tables = _actions(result)
    basis = result.basis
    for kind in Wind:
        action = tables[ActionKey.wind(kind)]
        assert [row.n for row in action.rows] == [basis.wind[kind][Girder.ORIGIN].vertical(1),
                                                  basis.wind[kind][Girder.END].vertical(1)]
    eq = tables[EQ_TRANSVERSE]
    assert eq.title == "地震時直角方向EQ"
    assert [(row.label, row.sublabel) for row in eq.rows] == [
        ("上部工慣性力", "起点側 Ｇ1桁"), ("上部工慣性力", "終点側 Ｇ1桁"), ("列車慣性力", "起点側 Ｇ1桁"),
        ("列車慣性力", "終点側 Ｇ1桁")]
    assert [row.n for row in eq.rows] == [result.seismic_girder[Girder.ORIGIN].vertical(1),
                                          result.seismic_girder[Girder.END].vertical(1),
                                          basis.seismic_train_torque[Girder.ORIGIN].vertical(1),
                                          basis.seismic_train_torque[Girder.END].vertical(1)]
    assert [row.n.value for row in eq.rows[2:]] == [58.47, 43.53]
    assert value(eq.n) == sum(value(row.n) for row in eq.rows)


def test_the_bearing_force_actions(current):
    _, _, result = current
    tables = _actions(result)
    expected = SAMPLE["actions"]["LRB"]
    for case, name in ((LongitudinalCase.SAFETY_LR10_B10, "1.0 LR + 1.23B"), (LongitudinalCase.SAFETY_LR11_B10, "1.1 LR + 1.23B"),
                       (LongitudinalCase.SAFETY_LR10_B11, "1.0 LR + 1.35B"), (LongitudinalCase.SAFETY_LR10, "1.0 LR"),
                       (None, "地震時")):
        action = tables[ActionKey.bearing(case)]
        assert (action.h.value, action.mt.value) == (expected[name]["total_h"], expected[name]["total_mt"])
        assert (action.n.value, action.md.value) == (0.0, 0.0)
        assert [(row.label, row.sublabel) for row in action.rows] == [("起点側", RUBBER), ("起点側", STOPPER),
                                                                     ("終点側", RUBBER), ("終点側", STOPPER)]
        assert all(row.n is None and row.x is None and row.arm.value == 1.35 for row in action.rows)
        assert action.title == (f"{name}の支承に働く水平荷重" if case is not None else "地震時線路方向")
    first = tables[ActionKey.bearing(LongitudinalCase.SAFETY_LR10_B10)]
    assert [row.h.value for row in first.rows] == [214.43, 0.0, 0.0, 0.0]
    seismic = tables[ActionKey.bearing(None)]
    assert [row.h.value for row in seismic.rows] == [0.0, 894.98, 0.0, 0.0]


def test_the_31_cases_their_states_remarks_and_notes():
    assert [definition.number for definition in DEFINITIONS] == list(range(1, 32))
    states = SAMPLE["combinations"]["states"]
    for span, state in states.items():
        first, last = (int(part) for part in span.split("-"))
        assert all(DEFINITIONS[number - 1].state.value == state for number in range(first, last + 1))
    for number, remark in SAMPLE["combinations"]["remarks"].items():
        assert DEFINITIONS[int(number) - 1].remark == remark
    for number, note in SAMPLE["combinations"]["notes_column"].items():
        assert DEFINITIONS[int(number) - 1].note == note
    assert DEFINITIONS[6].note == "" and DEFINITIONS[21].note == "" and DEFINITIONS[28].note == "B支点最大"
    assert DEFINITIONS[22].remark == "〃"
    assert COLUMNS == ("D1", "D2", "S", "L", "I", "LF", "W", "LR+B", "EQ")


def test_the_factors_of_each_case_as_the_table_prints_them(current):
    _, _, result = current
    cases = result.sides[Side.LEFT].cases
    assert [case.number for case in cases] == list(range(1, 32))
    for number, columns in SAMPLE["combinations"]["factors"].items():
        case = cases[int(number) - 1]
        found = {part.column: part.factor for part in case.contributions}
        assert found == columns, number
        assert [part.column for part in case.contributions] == [column for column in COLUMNS if column in columns]


def test_a_case_sums_the_printed_products_of_its_factors(current):
    pier, _, result = current
    tables = _actions(result)
    cases = result.sides[Side.LEFT].cases
    case = cases[0]  # 1: 1.1D1 + 1.2D2 + S10 + 1.35(L + I) + 1.23LF + 1.0W, B支点最大
    parts = {part.column: part for part in case.contributions}
    assert value(parts["D1"].n) == q(value(tables[D1].n) * D("1.1"), 2)
    assert value(parts["D1"].md) == q(value(tables[D1].md) * D("1.1"), 2)
    assert value(parts["D2"].mt) == q(value(tables[D2].mt) * D("1.2"), 2)
    assert parts["S"].n == tables[ActionKey.snow(Snow.S10)].n
    assert value(parts["L"].n) == q(D(243.87) * D("1.35"), 2)
    assert value(parts["I"].n) == q(D(59.75) * D("1.35"), 2)
    assert value(parts["LF"].n) == q(D(45.38) * D("1.23"), 2)
    assert parts["W"].n == tables[ActionKey.wind(Wind.WITH_TRAIN)].n
    assert value(case.n) == sum(value(part.n) for part in case.contributions)
    assert value(case.md) == sum(value(part.md) for part in case.contributions)
    assert value(case.mt) == sum(value(part.mt) for part in case.contributions)
    # the factors: ρu × γ at 2 decimals (1.231 × 1.1 → 1.35, × 1.0 → 1.23), 使用性 ρ = 1.0
    assert train_factor(pier, DEFINITIONS[0].train).value == 1.35
    assert train_factor(pier, DEFINITIONS[3].train).value == 1.23
    assert train_factor(pier, DEFINITIONS[24].train).value == 1.0
    assert train_factor(pier, DEFINITIONS[22].train).value == 1.0  # the seismic train has no ρ
    assert factor("1.35").digits == 2 and factor("1").digits == 0 and factor("1.0").value == 1.0


def test_the_cases_with_a_bearing_force_or_an_earthquake(current):
    _, _, result = current
    tables = _actions(result)
    cases = result.sides[Side.LEFT].cases
    case_9 = cases[8]
    lrb = case_9.contribution("LR+B")
    assert lrb is not None and lrb.factor == "1.0LR+1.23B"
    assert lrb.mt == tables[ActionKey.bearing(LongitudinalCase.SAFETY_LR10_B10)].mt and lrb.n.value == 0.0
    assert case_9.contribution("W") is None and case_9.contribution("LF") is None
    case_12 = cases[11]  # 制動最大: the train without impact
    assert case_12.contribution("I") is None and case_12.contribution("L").factor == "1.23"
    assert case_12.contribution("LR+B").factor == "1.0LR+1.35B"
    case_15 = cases[14]  # ロング最大: no snow
    assert case_15.contribution("S") is None and case_15.contribution("LR+B").factor == "1.1LR+1.23B"
    case_23, case_24 = cases[22], cases[23]
    assert case_23.contribution("EQ").n == tables[EQ_TRANSVERSE].n and case_23.contribution("EQ").factor == "1.0"
    assert case_23.contribution("L").n == tables[ActionKey.train(None)].n
    assert case_24.contribution("EQ").mt == tables[ActionKey.bearing(None)].mt
    assert case_24.contribution("EQ").n.value == 0.0 and case_24.contribution("EQ").md.value == 0.0
    # case 24: D1 + D2 + S2 + L(地震時) + the stopper's torsion (the sample 1437.42 from unrounded parts)
    assert value(case_24.mt) == q(D(130.50) + D(35.75) + D(19.38) + D(43.58) + D(1208.22), 2)
    assert value(case_24.n) == D(SAMPLE["combinations"]["sample_values"]["case_28_n"]) + D(287.84)
    case_28 = cases[27]
    assert case_28.n.value == SAMPLE["combinations"]["sample_values"]["case_28_n"]  # 2809.77 + 290 + 325
    assert case_28.contribution("L") is None
    case_30 = cases[29]
    assert [part.column for part in case_30.contributions] == ["L", "I"]
    assert value(case_30.n) == D(465.24) + value(tables[ActionKey.impact(Group.SERVICE, Loading.END_MAX)].n)
    # case 10's torsion: the sample's 1058.29 from unrounded parts
    case_10 = cases[9]
    assert value(case_10.mt) == q(D(130.50) * D("1.1"), 2) + q(D(35.75) * D("1.2"), 2) + D(31.00) + q(D(265.66) * D("1.35"), 2) \
        + q(value(tables[ActionKey.impact(Group.ULTIMATE, Loading.END_MAX)].mt) * D("1.35"), 2) + D(289.48)


def test_the_sample_rows_of_the_force_table_and_the_governing_cases(current):
    _, _, result = current
    selections = result.selections
    assert [(item.row, item.quantity) for item in selections] == [
        (row.id, quantity) for row in FORCE_ROWS for quantity in row.quantities]
    assert [row.id for row in FORCE_ROWS] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert FORCE_ROWS[2].quantities == (Quantity.SHEAR,) and FORCE_ROWS[3].quantities == FORCE_ROWS[4].quantities == (
        Quantity.BENDING, Quantity.SHEAR)
    by = {(item.row, item.quantity): item for item in selections}
    cases = result.sides[Side.LEFT].cases
    # 安全性（破壊）: the largest |Md|, Vd and Mt of cases 1〜18 (the sample: 3, 2 and 10)
    assert by[(5, Quantity.BENDING)].case.number == max(range(1, 19), key=lambda n: abs(cases[n - 1].md.value))
    assert by[(5, Quantity.SHEAR)].case.number == max(range(1, 19), key=lambda n: cases[n - 1].n.value)
    assert by[(5, Quantity.TORSION)].case.number == 10 == max(range(1, 19), key=lambda n: cases[n - 1].mt.value)
    assert by[(5, Quantity.BENDING)].case.number == 3 and by[(5, Quantity.SHEAR)].case.number == 2
    assert by[(1, Quantity.BENDING)].case.number == 28 and by[(3, Quantity.SHEAR)].case.number == 28
    assert {by[(2, Quantity.SHEAR)].case.number} <= {29, 30, 31} and by[(2, Quantity.SHEAR)].case.number == 30
    assert {by[(4, Quantity.BENDING)].case.number} <= {25, 26, 27}
    assert {by[(0, q)].case.number for q in Quantity} <= {25, 26, 27, 28}
    assert by[(7, Quantity.BENDING)].case.number == 23 and by[(7, Quantity.TORSION)].case.number == 24
    assert {by[(6, q)].case.number for q in Quantity} <= {19, 20, 21, 22}
    for item in selections:
        assert item.side is Side.LEFT  # the symmetric input: equal values keep the left side
        assert (item.md, item.vd, item.mt) == (item.case.md, item.case.n, item.case.mt)
        assert item.title == next(row.title for row in FORCE_ROWS if row.id == item.row)
    assert result.selection(5, Quantity.TORSION) is by[(5, Quantity.TORSION)]
    assert result.selection(2, Quantity.BENDING) is None


def test_both_sides_are_evaluated_and_pooled(current):
    _, _, result = current
    assert list(result.sides) == [Side.LEFT, Side.RIGHT]
    left, right = result.sides[Side.LEFT].cases, result.sides[Side.RIGHT].cases
    assert [(case.n, case.md, case.mt) for case in left] == [(case.n, case.md, case.mt) for case in right]


def _case(number: int, state: LimitState, md: float, n: float, mt: float) -> CaseResult:
    definition = DEFINITIONS[number - 1]
    assert definition.state is state
    moment, force = type(DEFINITIONS[0].d1), None
    from webpier.core.printed import FORCE, MOMENT
    return CaseResult(definition, (), FORCE(n), MOMENT(md), MOMENT(mt))


def test_adopt_pools_both_sides_and_keeps_the_left_side_and_the_earlier_case_on_ties():
    left = [_case(n, LimitState.SAFETY, 100 + n, 50, 10) for n in range(1, 19)]
    right = [_case(n, LimitState.SAFETY, 100 + n, 60 if n == 2 else 50, 10) for n in range(1, 19)]
    others = [_case(n, DEFINITIONS[n - 1].state, 1, 1, 1) for n in range(19, 32)]
    found = {(item.row, item.quantity): item for item in adopt({Side.LEFT: left + others, Side.RIGHT: right + others})}
    bending = found[(5, Quantity.BENDING)]
    assert (bending.side, bending.case.number) == (Side.LEFT, 18)  # equal |Md| on both sides: the left wins
    shear = found[(5, Quantity.SHEAR)]
    assert (shear.side, shear.case.number, shear.vd.value) == (Side.RIGHT, 2, 60.0)
    torsion = found[(5, Quantity.TORSION)]
    assert (torsion.side, torsion.case.number) == (Side.LEFT, 1)  # equal Mt everywhere: the earliest case
    # the bending measure is |Md|: a negative moment of larger magnitude governs
    negative = [_case(n, LimitState.SAFETY, -200 if n == 7 else 100, 50, 10) for n in range(1, 19)]
    assert {item.case.number for item in adopt({Side.LEFT: negative + others}) if item.row == 5
            and item.quantity is Quantity.BENDING} == {7}
    # one side alone
    only = adopt({Side.RIGHT: right + others})
    assert all(item.side is Side.RIGHT for item in only)


def test_evaluate_reads_only_the_actions_a_case_names(current):
    pier, _, result = current
    tables = _actions(result)
    labels = {case.case: case.label for case in result.bearing_cases if case.case is not None}
    found = evaluate(pier, tables, DEFINITIONS[7], labels)  # 8: 1.1D1 + 1.2D2 + S30
    assert [part.column for part in found.contributions] == ["D1", "D2", "S"]
    assert isinstance(found.contributions[0], Contribution)
    assert found == result.sides[Side.LEFT].cases[7]
    assert isinstance(result.selections[0], Selection) and isinstance(Decimal("1"), Decimal)
