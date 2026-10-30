"""The action tables and the 35 combinations of the cantilever (decisions 59, 125; Example2 13-24 .. 13-37,
Example橋脚4 表1.1.7), and the governing case of each check (the WDJ force table). The N and Mt totals of the sample
are expected where the inputs coincide; the Md values carry the sample's end X 0.645 and are recomputed by hand from
the printed parts instead. Example2's cases 23〜31 are WebPier's 27〜35 (decision 125 adds 23〜26 to 使用性（損傷）),
and its bearing forces are Example2 13's model, which decision 125 replaced (test_cantilever_bearings)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cantilever_support import SAMPLE, D, q, result_of, value
from webpier.calc.cantilever import COLUMNS, DEFINITIONS, LimitState, Quantity, Side
from webpier.calc.cantilever.actions import D1, D2, EQ_TRANSVERSE, REACTION, SELF_WEIGHT, ActionKey, Group
from webpier.calc.cantilever.bearings import label
from webpier.calc.cantilever.combinations import (FORCE_ROWS, CaseResult, Contribution, Selection, adopt, evaluate,
                                                  factor, train_factor)
from webpier.calc.cantilever.loads import Loading, Wind
from webpier.calc.moving_load import Girder
from webpier.calc.reaction.longitudinal import LongitudinalCase, Snow


BEARING_CASES = (9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 24, 25, 26, 28)


def renumbered(number: int) -> int:
    """Example2's case number in WebPier's 35 (decision 125: 23〜26 are new)."""
    return number if number <= 22 else number + 4


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
    assert keys[21:] == [ActionKey.bearing(number) for number in BEARING_CASES]
    assert len(keys) == 35 and len(set(keys)) == 35
    assert ActionKey.train(None).variant == "地震時" and ActionKey.bearing(28).variant == "28"


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
    # B支点最大 (decision 125): RB 532.41, not the sample's 517.77: L 0.471 × 532.41 = 250.77, Mt 250.77 × −0.325;
    # LF 409.95 × 3.800 / 33.3800 = 46.67 (0.2 × 532.41 = 106.48 at 3.850 m)
    origin_max = {"L": {"total_n": 250.77, "total_mt": float(q(D("250.77") * D("-0.325"), 2))},
                  "LF": {"total_n": 46.67, "total_mt": float(q(D("46.67") * D("-0.325"), 2))}}
    assert SAMPLE["actions"]["L"]["B支点最大"]["total_n"] == 243.87
    for loading in Loading:
        expected = SAMPLE["actions"]["L"][loading.value] if loading is not Loading.ORIGIN_MAX else origin_max["L"]
        action = tables[ActionKey.train(loading)]
        assert (action.n.value, action.mt.value) == (expected["total_n"], expected["total_mt"])
        assert action.title == f"列車荷重L {loading.value}の場合"
        lateral = tables[ActionKey.lateral(loading)]
        expected = SAMPLE["actions"]["LF"][loading.value] if loading is not Loading.ORIGIN_MAX else origin_max["LF"]
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
    # B支点最大: 250.77 × 0.245 = 61.44, Mt 61.44 × −0.325 = −19.97 (the sample's 59.75 from RB 517.77, decision 125)
    assert (value(b.n), value(b.mt)) == (D("61.44"), q(D("61.44") * D("-0.325"), 2))
    assert ultimate["B支点最大"]["total_n"] == 59.75
    c = tables[ActionKey.impact(Group.ULTIMATE, Loading.END_MAX)]
    assert [row.n.value for row in c.rows] == [11.85, 217.18]  # 229.03; the sample 229.04 from unrounded parts
    bc = tables[ActionKey.impact(Group.ULTIMATE, Loading.BOTH_MAX)]
    assert (bc.n.value, bc.mt.value) == (ultimate["B+C支点最大"]["total_n"], ultimate["B+C支点最大"]["total_mt"])
    for loading in Loading:
        service = tables[ActionKey.impact(Group.SERVICE, loading)]
        assert service.n.value < tables[ActionKey.impact(Group.ULTIMATE, loading)].n.value
        assert service.title == f"衝撃荷重I 使用性 {loading.value}の場合"
    assert [row.n.value for row in tables[ActionKey.impact(Group.SERVICE, Loading.ORIGIN_MAX)].rows] == [46.14, 0.0]  # 250.77 × 0.184 (decision 125)


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
    """One row per bearing on the cantilever (test_cantilever_bearings has the hand calculations): case 9 149.20 and
    100.00, the seismic case 204.07 (capped) and 946.82, Y = 1.350."""
    _, _, result = current
    tables = _actions(result)
    for number in BEARING_CASES:
        action = tables[ActionKey.bearing(number)]
        case = next(case for case in result.sides[Side.LEFT].bearings if case.number == number)
        assert (action.h, action.mt) == (case.force, case.moment)
        assert (action.n.value, action.md.value) == (0.0, 0.0)
        assert [(row.label, row.sublabel) for row in action.rows] == [("起点側", "Ｇ1桁"), ("終点側", "Ｇ1桁")]
        assert all(row.n is None and row.x is None and row.arm.value == 1.35 for row in action.rows)
    assert [row.h.value for row in tables[ActionKey.bearing(9)].rows] == [149.2, 100.0]
    seismic = tables[ActionKey.bearing(28)]
    assert [row.h.value for row in seismic.rows] == [204.07, 946.82]
    assert (seismic.h.value, seismic.mt.value) == (1150.89, 1553.7)


def test_the_35_cases_their_states_remarks_and_notes():
    assert [definition.number for definition in DEFINITIONS] == list(range(1, 36))
    states = SAMPLE["combinations"]["states"]
    renamed = {"復旧性(地震時以外)": "使用性(損傷)"}  # the R5 name of the sample's H16 state (decision 73)
    for span, state in states.items():
        first, last = (int(part) for part in span.split("-"))
        assert all(DEFINITIONS[renumbered(number) - 1].state.value == renamed.get(state, state)
                   for number in range(first, last + 1))
    for number, remark in SAMPLE["combinations"]["remarks"].items():
        assert DEFINITIONS[renumbered(int(number)) - 1].remark == remark
    for number, note in SAMPLE["combinations"]["notes_column"].items():
        assert DEFINITIONS[renumbered(int(number)) - 1].note == note
    assert DEFINITIONS[6].note == "" and DEFINITIONS[21].note == "" and DEFINITIONS[32].note == "B支点最大"
    assert DEFINITIONS[26].remark == "〃"
    # decision 125 (Example橋脚4 表1.1.7 9-2, 10-1〜10-3): 23 風最大 and 24〜26 with the bearing forces, 使用性（損傷）
    new = DEFINITIONS[22:26]
    assert all(item.state is LimitState.SERVICEABILITY_DAMAGE for item in new)
    assert [item.remark for item in new] == ["風最大", "列車最大", "列車最大", "列車最大"]
    assert [item.note for item in new] == ["", "B支点最大", "C支点最大", "B+C支点最大"]
    wind = new[0]
    assert (wind.d1, wind.d2, wind.snow, wind.train, wind.wind, wind.bearing) == (
        factor("1.0"), factor("1.0"), Snow.S2, None, (Wind.WITHOUT_TRAIN, factor("1.0")), None)
    for item, loading in zip(new[1:], Loading):
        assert (item.d1, item.d2, item.snow, item.bearing, item.lateral, item.wind, item.eq) == (
            factor("1.0"), factor("1.0"), Snow.S10, LongitudinalCase.SAFETY_LR10_B10, None, None, None)
        assert (item.train.loading, item.train.group, item.train.gamma, item.train.impact) == (
            loading, Group.ULTIMATE, factor("1.0"), True)
    assert COLUMNS == ("D1", "D2", "S", "L", "I", "LF", "W", "LR+B", "EQ")


def test_the_factors_of_each_case_as_the_table_prints_them(current):
    _, _, result = current
    cases = result.sides[Side.LEFT].cases
    assert [case.number for case in cases] == list(range(1, 36))
    for number, columns in SAMPLE["combinations"]["factors"].items():
        case = cases[renumbered(int(number)) - 1]
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
    assert value(parts["L"].n) == q(D(250.77) * D("1.35"), 2)  # B支点最大 with RB 532.41 (decision 125)
    assert value(parts["I"].n) == q(D(61.44) * D("1.35"), 2)
    assert value(parts["LF"].n) == q(D(46.67) * D("1.23"), 2)
    assert parts["W"].n == tables[ActionKey.wind(Wind.WITH_TRAIN)].n
    assert value(case.n) == sum(value(part.n) for part in case.contributions)
    assert value(case.md) == sum(value(part.md) for part in case.contributions)
    assert value(case.mt) == sum(value(part.mt) for part in case.contributions)
    # the factors: ρu × γ at 2 decimals (1.231 × 1.1 → 1.35, × 1.0 → 1.23), 使用性 ρ = 1.0
    assert train_factor(pier, DEFINITIONS[0].train).value == 1.35
    assert train_factor(pier, DEFINITIONS[3].train).value == 1.23
    assert train_factor(pier, DEFINITIONS[28].train).value == 1.0
    assert train_factor(pier, DEFINITIONS[26].train).value == 1.0  # the seismic train has no ρ
    assert factor("1.35").digits == 2 and factor("1").digits == 0 and factor("1.0").value == 1.0


def test_the_cases_with_a_bearing_force_or_an_earthquake(current):
    _, _, result = current
    tables = _actions(result)
    cases = result.sides[Side.LEFT].cases
    case_9 = cases[8]
    lrb = case_9.contribution("LR+B")
    assert lrb is not None and lrb.factor == "1.0LR+1.23B"
    assert lrb.mt == tables[ActionKey.bearing(9)].mt and lrb.n.value == 0.0
    assert case_9.contribution("W") is None and case_9.contribution("LF") is None
    case_12 = cases[11]  # 制動最大: the train without impact
    assert case_12.contribution("I") is None and case_12.contribution("L").factor == "1.23"
    assert case_12.contribution("LR+B").factor == "1.0LR+1.35B"
    case_15 = cases[14]  # ロング最大: no snow
    assert case_15.contribution("S") is None and case_15.contribution("LR+B").factor == "1.1LR+1.23B"
    case_27, case_28 = cases[26], cases[27]
    assert case_27.contribution("EQ").n == tables[EQ_TRANSVERSE].n and case_27.contribution("EQ").factor == "1.0"
    assert case_27.contribution("L").n == tables[ActionKey.train(None)].n
    assert case_28.contribution("EQ").mt == tables[ActionKey.bearing(28)].mt
    assert case_28.contribution("EQ").n.value == 0.0 and case_28.contribution("EQ").md.value == 0.0
    # case 28: D1 + D2 + S2 + L(地震時) + the bearings' torsion 275.49 + 1278.21 (decision 125)
    assert value(case_28.mt) == q(D(130.50) + D(35.75) + D(19.38) + D(43.58) + D("1553.70"), 2)
    assert value(case_28.n) == D(SAMPLE["combinations"]["sample_values"]["case_28_n"]) + D(287.84)
    case_32 = cases[31]
    assert case_32.n.value == SAMPLE["combinations"]["sample_values"]["case_28_n"]  # 2809.77 + 290 + 325
    assert case_32.contribution("L") is None
    case_34 = cases[33]
    assert [part.column for part in case_34.contributions] == ["L", "I"]
    assert value(case_34.n) == D(465.24) + value(tables[ActionKey.impact(Group.SERVICE, Loading.END_MAX)].n)
    # case 10's torsion with the bearing forces of C支点最大: 100.00 × 1.350 + 159.04 × 1.350 = 135.00 + 214.70
    case_10 = cases[9]
    assert value(case_10.mt) == q(D(130.50) * D("1.1"), 2) + q(D(35.75) * D("1.2"), 2) + D(31.00) + q(D(265.66) * D("1.35"), 2) \
        + q(value(tables[ActionKey.impact(Group.ULTIMATE, Loading.END_MAX)].mt) * D("1.35"), 2) + D("135.00") + D("214.70")
    # the new 使用性（損傷） cases: 23 = D1 + D2 + S2 + 1.0W (no train), 24 = D1 + D2 + S10 + 1.23(L + I) + 1.0LR+1.23B
    case_23 = cases[22]
    assert {part.column: part.factor for part in case_23.contributions} == {"D1": "1.0", "D2": "1.0", "S": "1.0S2",
                                                                             "W": "1.0"}
    assert case_23.contribution("W").mt == tables[ActionKey.wind(Wind.WITHOUT_TRAIN)].mt
    case_24 = cases[23]
    assert {part.column: part.factor for part in case_24.contributions} == {
        "D1": "1.0", "D2": "1.0", "S": "1.0S10", "L": "1.23", "I": "1.23", "LR+B": "1.0LR+1.23B"}
    assert case_24.contribution("LR+B").mt == tables[ActionKey.bearing(24)].mt


def by_row_8(selections):
    (selected,) = [item for item in selections if item.row == 8]
    return selected


def test_the_sample_rows_of_the_force_table_and_the_governing_cases(current):
    _, _, result = current
    selections = result.selections
    assert [(item.row, item.quantity) for item in selections] == [
        (row.id, quantity) for row in FORCE_ROWS for quantity in row.quantities]
    assert [row.id for row in FORCE_ROWS] == [0, 1, 2, 3, 4, 5, 6, 7, 8]
    assert FORCE_ROWS[8].quantities == (Quantity.BENDING,)  # 最小鉄筋量: the permanent case 32 (decision 73)
    assert by_row_8(selections).case.definition.number == 32
    assert FORCE_ROWS[2].quantities == (Quantity.SHEAR,) and FORCE_ROWS[3].quantities == FORCE_ROWS[4].quantities == (
        Quantity.BENDING, Quantity.SHEAR)
    by = {(item.row, item.quantity): item for item in selections}
    cases = result.sides[Side.LEFT].cases
    # 安全性（破壊）: the largest |Md|, Vd and Mt of cases 1〜18 (the sample: 3, 2 and 10)
    assert by[(5, Quantity.BENDING)].case.number == max(range(1, 19), key=lambda n: abs(cases[n - 1].md.value))
    assert by[(5, Quantity.SHEAR)].case.number == max(range(1, 19), key=lambda n: cases[n - 1].n.value)
    assert by[(5, Quantity.TORSION)].case.number == 10 == max(range(1, 19), key=lambda n: cases[n - 1].mt.value)
    assert by[(5, Quantity.BENDING)].case.number == 3 and by[(5, Quantity.SHEAR)].case.number == 2
    assert by[(1, Quantity.BENDING)].case.number == 32 and by[(3, Quantity.SHEAR)].case.number == 32
    assert {by[(2, Quantity.SHEAR)].case.number} <= {33, 34, 35} and by[(2, Quantity.SHEAR)].case.number == 34
    assert {by[(4, Quantity.BENDING)].case.number} <= {29, 30, 31}
    assert {by[(0, q)].case.number for q in Quantity} <= {29, 30, 31, 32}
    assert by[(7, Quantity.BENDING)].case.number == 27 and by[(7, Quantity.TORSION)].case.number == 28
    assert {by[(6, q)].case.number for q in Quantity} <= set(range(19, 27))
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
    others = [_case(n, DEFINITIONS[n - 1].state, 1, 1, 1) for n in range(19, 36)]
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
    labels = {item.bearing: label(item.bearing, result_of()[1].longitudinal) for item in DEFINITIONS
              if item.bearing is not None}
    found = evaluate(pier, tables, DEFINITIONS[7], labels)  # 8: 1.1D1 + 1.2D2 + S30
    assert [part.column for part in found.contributions] == ["D1", "D2", "S"]
    assert isinstance(found.contributions[0], Contribution)
    assert found == result.sides[Side.LEFT].cases[7]
    assert isinstance(result.selections[0], Selection) and isinstance(Decimal("1"), Decimal)


def test_the_bearing_torsion_takes_the_sign_of_the_rest_of_the_case():
    """Decision 125: Mt of the bearing forces along the track (positive Hi·Y in its table) is added with the sign of
    the rest of the case's Mt; a rest of exactly 0 keeps it positive. Only the bearing action of the case is signed."""
    from webpier.calc.cantilever.actions import Action
    from webpier.core.printed import FORCE, MOMENT

    def action(key: ActionKey, mt: float) -> Action:
        return Action(key, "", (), FORCE(0), MOMENT(0), MOMENT(mt), FORCE(0))

    definition = DEFINITIONS[17]  # 18: 1.1D1 + 1.2D2 + S30 + 1.0LR (no train)
    assert definition.bearing is LongitudinalCase.SAFETY_LR10 and definition.number == 18
    pier = result_of()[0]
    labels = {LongitudinalCase.SAFETY_LR10: "1.0 LR"}
    for d1, d2, expected in ((10.0, -5.0, 100.0), (0.0, 0.0, 100.0), (-10.0, 5.0, -100.0)):
        tables = {D1: action(D1, d1), D2: action(D2, d2), ActionKey.bearing(18): action(ActionKey.bearing(18), 100.0)}
        found = evaluate(pier, tables, definition, labels)
        assert found.contribution("LR+B").mt.value == expected
        rest = float(q(D(d1) * D("1.1"), 2) + q(D(d2) * D("1.2"), 2))
        assert found.mt.value == pytest.approx(rest + expected)
        assert found.contribution("D1").mt.value == float(q(D(d1) * D("1.1"), 2))
