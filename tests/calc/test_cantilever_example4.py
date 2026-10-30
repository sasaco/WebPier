"""0900 for the Example橋脚4 input against the sample's 第V編 1.1 (V-1〜V-39, tests/fixtures/example4/
cantilever_responses.json; the comparison is tests/fixtures/example4/cantilever_acceptance_notes.md).

The 最大応答震度 is the sample's (線路方向 0.495, 線路直角方向 0.786), so that what differs here is not the analysis.
Values that agree are compared with the transcription at its printed digits; values that differ are fixed by hand
calculations from the input (never by WebPier's output), with the reason in the docstring. The horizontal forces at
the bearings are test_cantilever_bearings.py's (test_example4_*). No runner is used."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from cantilever_support import D, q, result_of, value
from webpier.calc.cantilever import Quantity, Side
from webpier.calc.cantilever.actions import D1, D2, ActionKey
from webpier.calc.cantilever.loads import Loading, Wind
from webpier.calc.moving_load import Girder, Objective, search_reactions
from webpier.calc.vehicles import vehicle
from webpier.inputs import parse_input

ROOT = Path(__file__).parents[2]
EXAMPLE4 = json.loads((ROOT / ".claude" / "docs" / "Example橋脚4" / "pre" / "input.json").read_text(encoding="utf-8"))
SAMPLE = json.loads((ROOT / "tests" / "fixtures" / "example4" / "cantilever_responses.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def example4():
    return result_of(parse_input(EXAMPLE4), longitudinal=0.495, transverse=0.786)


def _action(result, key: ActionKey, side: Side = Side.LEFT):
    return next(item for item in result.sides[side].actions if item.key == key)


def _case(result, number: int, side: Side = Side.LEFT):
    return next(item for item in result.sides[side].cases if item.number == number)


def _loading(result, loading: Loading):
    return next(item for item in result.basis.loadings if item.loading is loading)


def _printed(text: str) -> Decimal:
    return Decimal(text)


def _rows(table: list) -> dict:
    return {(row[0], row[1]): row for row in table}


def test_dead_loads_arms_and_torsion_of_the_dead_loads_agree(example4):
    """表1.1.3・1.1.5：R_D11 855.0（X 0.450、e −0.700）、R_D12 1062.5（1.225、0.200）、R_D21 235.0、R_D22 262.5、
    ΣD1 の Md 1911.4・Mt −386.0、ΣD2 の Mt −112.0（左右とも同じ）."""
    _, _, result = example4
    table3 = _rows(SAMPLE["load_tables"]["表1.1.3"]["各性能共通・死荷重"])
    table5 = _rows(SAMPLE["load_tables"]["表1.1.5"]["各性能共通・死荷重"])
    for side in Side:
        d1, d2 = _action(result, D1, side), _action(result, D2, side)
        origin, end = d1.rows[1], d1.rows[2]
        assert value(origin.n) == _printed(table3[("固定（D1）上部工", "R_D11")][2])
        assert value(end.n) == _printed(table3[("固定（D1）上部工", "R_D12")][2])
        assert (value(origin.x), value(end.x)) == (_printed("0.450"), _printed("1.225"))
        assert (value(origin.arm), value(end.arm)) == (_printed("-0.700"), _printed("0.200"))
        assert value(d2.rows[0].n) == _printed(table3[("付加（D2）上部工", "R_D21")][2])
        assert value(d2.rows[1].n) == _printed(table3[("付加（D2）上部工", "R_D22")][2])
        assert q(value(d1.md), 1) == _printed(table3[("ΣD1", None)][4])  # 1911.41 → 1911.4
        assert q(value(d1.mt), 1) == _printed(table5[("ΣD1", None)][4])  # −386.0
        assert q(value(d2.mt), 1) == _printed(table5[("ΣD2", None)][4])  # −112.0


def test_self_weight_agrees_with_v26(example4):
    """V-26：W＝(91.9＋122.5)/2×2.10＝225.1（表 1.1.3 の 225.0 は見本の食い違い 8）、x1 1.000."""
    _, _, result = example4
    weight = result.sides[Side.LEFT].geometry.self_weight
    assert q(value(weight.force), 1) == _printed(SAMPLE["self_weight"]["W"]["value_kN"])
    assert value(weight.moment) == value(weight.force)  # x1 = 1.000


def test_the_second_moments_and_shares_agree_except_the_end_single_share(example4):
    """V-2・V-9：ΣXi² 9.68・21.2125、起点側 単線 0.932・複線 1.000、終点側 複線 0.500. 終点側 単線は
    1/4＋1.90×2.975/21.2125＝0.51647 → 0.516、見本は 21.21 で割って 0.517（食い違い 10）."""
    _, _, result = example4
    girders = result.basis.girders
    assert value(girders[Girder.ORIGIN].sum_squares) == _printed(SAMPLE["shoe_share"]["起点方"]["I_m2"])
    assert value(girders[Girder.END].sum_squares) == _printed(SAMPLE["transverse"]["section_modulus"]["終点側"]["I_m2"])
    both = _loading(result, Loading.BOTH_MAX)
    origin = both.girders[Girder.ORIGIN].bearings[0]
    end = both.girders[Girder.END].bearings[0]
    assert value(origin.single.share) == _printed(SAMPLE["shoe_share"]["起点方"]["R2_single"])
    assert value(origin.double.share) == _printed(SAMPLE["shoe_share"]["起点方"]["R2_double"])
    assert value(end.double.share) == _printed(SAMPLE["shoe_share"]["終点方"]["R2_double"])
    hand = q(Decimal("0.25") + Decimal("1.90") * Decimal("2.975") / Decimal("21.2125"), 3)
    assert value(end.single.share) == hand == Decimal("0.516") != _printed(SAMPLE["shoe_share"]["終点方"]["R2_single"])
    assert q(Decimal("0.25") + Decimal("1.90") * Decimal("2.975") / Decimal("21.21"), 3) == Decimal("0.517")


def test_impact_coefficients(example4):
    """表1.1.2：起点側 単線 0.542・0.407、終点側 0.591・0.520・0.443・0.390 は一致. 起点側の複線は入力が単線の
    0.542 だけなので 0.542×(1−7.2/200)＝0.522、使用性 0.75×0.522＝0.392（見本は桁の計算書の 0.512・0.384。(2)）."""
    _, reaction, _ = example4
    ultimate, service = reaction.train.ultimate, reaction.train.service
    table = SAMPLE["impact"]["表1.1.2"]
    assert value(ultimate.origin_impact.single) == _printed(table["起点側桁"]["group1"]["単線"])
    assert value(service.origin_impact.single) == _printed(table["起点側桁"]["group2"]["単線"])
    for impact, group in ((ultimate.end_impact, "group1"), (service.end_impact, "group2")):
        assert value(impact.single) == _printed(table["終点側桁"][group]["単線"])
        assert value(impact.double) == _printed(table["終点側桁"][group]["複線"])
    double = q(Decimal("0.542") * (1 - Decimal("7.2") / 200), 3)
    assert value(ultimate.origin_impact.double) == double == Decimal("0.522")
    assert value(service.origin_impact.double) == q(Decimal("0.75") * double, 3) == Decimal("0.392")
    assert (table["起点側桁"]["group1"]["複線"], table["起点側桁"]["group2"]["複線"]) == ("0.512", "0.384")


def test_train_of_the_loading_both_spans(example4):
    """両スパン（B+C支点最大＝0600 の載荷）：R_C 697.71 は見本 697.7 と一致. R_B は 379.44（EA-17 の後続の線荷重
    50 kN/m×1.2 m、てこ 0.2 を含む：(170×(7.6＋5.6＋2.8)＋50×1.2×0.2)/7.2＝379.44。見本 368.3 は 0600 の食い違い 1
    で 3 本目の軸を落とし、線荷重を載せない）. 終点側の片持ち梁上のシューは単線 0.516×697.71＝360.02 が複線
    0.500×697.71＝348.86 より大きいので 360.02（見本の表 1.1.3 は R_C 697.7 そのもの、食い違い 11）."""
    _, _, result = example4
    both = _loading(result, Loading.BOTH_MAX)
    sample = SAMPLE["train_loads"]["両スパン"]["複線"]
    assert q(value(both.result.rc), 1) == _printed(sample["R_C"]["value"])
    rb = (170 * (Decimal("7.6") + Decimal("5.6") + Decimal("2.8")) + 50 * Decimal("1.2") * Decimal("0.2")) / Decimal("7.2")
    assert value(both.result.rb) == q(rb, 2) == Decimal("379.44")
    end = both.girders[Girder.END].bearings[0]
    assert value(end.adopted.load) == q(Decimal("697.71") * Decimal("0.516"), 2) == Decimal("360.02")
    assert not end.adopted_double


def test_seismic_train_on_the_bearings(example4):
    """V-4：起点側 0.932×35.0×8.00/2＝130.48 → 130.5（一致）. 終点側は 0.516×437.50＝225.75（見本 0.517 で 226.2）."""
    _, _, result = example4
    seismic = _action(result, ActionKey.train(None))
    assert q(value(seismic.rows[0].n), 1) == _printed(SAMPLE["train_loads"]["地震時列車荷重"]["R_B"]["value"])
    assert value(seismic.rows[1].n) == q(Decimal("437.50") * Decimal("0.516"), 2) == Decimal("225.75")


def test_wind_torques(example4):
    """V-10・V-11：終点側桁 M 402.00、R_T 56.38 → 56.4（列車あり）、43.07 → 43.1（列車なし）は一致. 起点側桁は
    WebPier に「足」の風荷重（1.5×1.1×0.9＝1.5 kN を 0.70 m、列車なしは 3.0 kN）がなく、M＝31.8×3.90＝124.02
    （見本 125.1）、R_T＝124.02×2.2/9.68＝28.19（見本 28.4）. (2)."""
    _, _, result = example4
    wind = result.basis.wind
    with_train, without = SAMPLE["transverse"]["風荷重_列車あり"], SAMPLE["transverse"]["風荷重_列車なし"]
    assert value(wind[Wind.WITH_TRAIN][Girder.END].moment) == _printed(with_train["終点側桁"]["M1"]["value_kNm"])
    end = result.basis.girders[Girder.END].bearings[0].number
    assert q(value(wind[Wind.WITH_TRAIN][Girder.END].vertical(end)), 1) == _printed(with_train["終点側桁"]["RT"]["value_kN"])
    assert q(value(wind[Wind.WITHOUT_TRAIN][Girder.END].vertical(end)), 1) == _printed(without["終点側桁"]["RT"]["value_kN"])
    origin = wind[Wind.WITH_TRAIN][Girder.ORIGIN]
    assert value(origin.moment) == Decimal("31.8") * Decimal("3.90") == Decimal("124.020")
    assert value(origin.vertical(1)) == q(Decimal("124.02") * Decimal("2.2") / Decimal("9.68"), 2) == Decimal("28.19")


def test_seismic_torques_across_the_track(example4):
    """V-12（Kh 0.786）：WebPier の桁の慣性力はこの橋脚の反力 2180.00（IV-101 の荷重図の 7480 と同じ取り方）に Kh、
    H＝1713.48、M＝3855.33、R_T＝876.21. 見本は桁の ΣR（3420＋940）で 3427.0、R_T 1752.5（2 倍）. 列車慣性力は
    起点側 0.300×8.0×35.0/2＝42.00、M 186.90、R_T 42.48（見本は桁長を入れ替えて 131.3・132.8、食い違い 3）."""
    _, _, result = example4
    girder = result.seismic_girder[Girder.ORIGIN]
    h = q(Decimal("0.786") * 2180, 2)
    m = q(h * Decimal("2.25"), 2)
    assert (value(girder.force), value(girder.moment)) == (h, m) == (Decimal("1713.48"), Decimal("3855.33"))
    assert value(girder.vertical(1)) == q(m * Decimal("2.2") / Decimal("9.68"), 2) == Decimal("876.21")
    assert SAMPLE["transverse"]["地震時上部工慣性力"]["起点側桁"]["H_expr"] == "0.786 × (3420 + 940)"
    train = result.basis.seismic_train_torque[Girder.ORIGIN]
    assert value(train.force) == Decimal("0.300") * Decimal("8.0") * Decimal("35.0") / 2 == Decimal("42.00")
    assert value(train.vertical(1)) == q(Decimal("186.90") * Decimal("2.2") / Decimal("9.68"), 2) == Decimal("42.48")


def test_permanent_case_and_seismic_case_vertical_totals(example4):
    """表1.1.7 の Case 7（D1＋D2）は WebPier の 32：N＝2142.60＋497.50＝2640.10（見本 2640.0：自重 225.1 と 225.0、
    食い違い 8）、Md＝1911.41＋427.31＝2338.72（見本 2338.8：見本は行ごとに 1 桁に丸めて和、427.4）. Case 12 は
    WebPier の 28：N＝2640.10＋356.23＝2996.33（見本 2996.7：0.517 と 225.0）."""
    _, _, result = example4
    permanent = _case(result, 32)
    assert value(permanent.n) == D("2142.60") + D("497.50") == Decimal("2640.10")
    assert value(permanent.md) == D("1911.41") + D("427.31") == Decimal("2338.72")
    assert q(value(permanent.n), 0) == q(_printed(SAMPLE["summary"]["表1.1.8"]["rows"][12][5]), 0)
    seismic = _case(result, 28)
    assert value(seismic.n) == Decimal("2640.10") + D("130.48") + D("225.75")


def test_torsion_arm_is_y_not_the_samples_0881(example4):
    """Y＝(H2＋H3)/2＝(1.50＋0.50)/2＝1.000 m（見本 y＝0.881、出所の記載なし、決定125）."""
    _, _, result = example4
    assert value(result.sides[Side.LEFT].geometry.torsion_arm) == (Decimal("1.50") + Decimal("0.50")) / 2
    assert SAMPLE["load_tables"]["表1.1.6"]["安全性（破壊）・線路方向水平力"][0][3] == "0.881"


def test_the_torsion_check_takes_the_largest_magnitude(example4):
    """Example4 の Mt は負（起点側の死荷重のねじり 855×(−0.700) が大きい）. ねじりは |Mt| が最大のケースを採る
    （曲げの |Md| と同じ）. 符号付きの最大では |Mt| が最小のケース（安全性 Case 16 の −256.06）を採っていた."""
    _, _, result = example4
    for row, numbers in ((5, range(1, 19)), (6, range(19, 27)), (7, range(27, 29))):
        cases = [_case(result, number) for number in numbers]
        largest = max(cases, key=lambda case: abs(case.mt.value))
        assert result.selection(row, Quantity.TORSION).case.number == largest.number
        assert all(case.mt.value <= 0 for case in cases)


def _rest(*parts: tuple[str, str]) -> Decimal:
    """Σ factor × Mt of the vertical actions, each product printed to 2 decimals (ADR-0003)."""
    return sum((q(Decimal(by) * Decimal(mt), 2) for by, mt in parts), Decimal(0))


# Mt = Σ N·e of the bearings on the left cantilever (起点側 Ｇ1 e −0.700, 終点側 Ｇ1 e 0.200), each row printed:
D1_MT = q(Decimal("855.0") * Decimal("-0.700"), 2) + q(Decimal("1062.5") * Decimal("0.200"), 2)  # −598.50 + 212.50
D2_MT = q(Decimal("235.0") * Decimal("-0.700"), 2) + q(Decimal("262.5") * Decimal("0.200"), 2)  # −164.50 + 52.50
L_ORIGIN_MT = q(Decimal("415.14") * Decimal("-0.700"), 2)  # B支点最大: A-17 on the origin girder only (R_B 415.14)
I_ORIGIN_MT = q(q(Decimal("415.14") * Decimal("0.522"), 2) * Decimal("-0.700"), 2)  # 216.70 × −0.700 (複線 0.522)
SEISMIC_TRAIN_MT = q(Decimal("130.48") * Decimal("-0.700"), 2) + q(Decimal("225.75") * Decimal("0.200"), 2)


def test_the_bearing_torsion_is_added_on_the_side_of_the_rest_of_the_case(example4):
    """線路方向の水平荷重（制動・ロングレール・地震時）はどちら向きにも働くので、片持ち梁のねじり ΣHi·Y は
    そのケースの他のねじりと同じ向き（|Mt| が大きくなる向き）に足す（見本 4-2：−424.6−134.4−269.1−137.7−330.4、
    12：…−1397.8. 表の H·y は正のまま）. 腕 Y＝1.000.

    Case 9（安全性、B支点最大、1.0LR＋1.00B）：起点側 Ts＝(1.00×127.50＋1.0×160.00)/2＝143.75（μ·Ni に届かない）、
    終点側 500.00/4＝125.00 → ΣHi·Y＝268.75. 他のねじり 1.1×(−386.00)＋1.2×(−112.00)＋1.10×(−290.60)＋1.10×(−151.69)
    ＝−1045.52 → Mt＝−1045.52−268.75＝−1314.27（見本 4-2 −1296.2）.
    Case 24（使用性（損傷）、同じ T）：−386.00−112.00−290.60−151.69−268.75＝−1209.04（見本 10-2 −1198.2）.
    Case 28（復旧性、Kh 0.495）：起点側（可動）Ts＝2214.20/2＝1107.10 は μ·Ni＝0.1×(855.0＋235.0＋130.48)＝122.05 で
    上限、終点側（固定）5422.00/4＝1355.50 → ΣHi·Y＝1477.55. 他のねじり −386.00−112.00＋(−91.34＋45.15)＝−544.19
    → −2021.74（見本 12 −1942.0：上限 231.1、y 0.881）."""
    _, _, result = example4
    assert (D1_MT, D2_MT, L_ORIGIN_MT, I_ORIGIN_MT, SEISMIC_TRAIN_MT) == (
        Decimal("-386.00"), Decimal("-112.00"), Decimal("-290.60"), Decimal("-151.69"), Decimal("-46.19"))
    expected = {
        9: (_rest(("1.1", D1_MT), ("1.2", D2_MT), ("1.10", L_ORIGIN_MT), ("1.10", I_ORIGIN_MT)),
            (Decimal("143.75") + Decimal("125.00")) * 1, "LR+B"),
        24: (_rest(("1.0", D1_MT), ("1.0", D2_MT), ("1.00", L_ORIGIN_MT), ("1.00", I_ORIGIN_MT)),
             (Decimal("143.75") + Decimal("125.00")) * 1, "LR+B"),
        28: (_rest(("1.0", D1_MT), ("1.0", D2_MT), ("1.00", SEISMIC_TRAIN_MT)),
             q(Decimal("0.1") * (Decimal("855.0") + Decimal("235.0") + Decimal("130.48")), 2) + Decimal("5422.00") / 4,
             "EQ"),
    }
    assert expected[9][0] == Decimal("-1045.52") and expected[28][1] == Decimal("1477.55")
    for number, (rest, torque, column) in expected.items():
        for side in Side:
            case = _case(result, number, side)
            assert value(_action(result, ActionKey.bearing(number), side).mt) == torque  # the table: H·Y, positive
            assert value(case.contribution(column).mt) == -torque  # the combination: on the side of the rest
            assert value(case.mt) == rest - torque
    assert {number: value(_case(result, number).mt) for number in expected} == {
        9: Decimal("-1314.27"), 24: Decimal("-1209.04"), 28: Decimal("-2021.74")}
    for row, number in ((5, 9), (6, 24), (7, 28)):
        assert result.selection(row, Quantity.TORSION).case.number == number


def test_the_end_maximum_counts_the_axle_at_the_joint_on_the_end_girder():
    """C支点最大（R_C の最大、0900）は継ぎ目（終点側の桁の起点側の端、D から 0.5＋24.0＝24.5 m）の軸を終点側の桁に
    数える配置も評価する. E-17（vehicles.E17：170 kN×12 軸、軸間 2.8・2.0・2.8・2.0・2.8・4.0・2.8・2.0・2.8・2.0・
    2.8 m）の 2〜11 軸目を D から 1.3・3.3・6.1・8.1・10.9・14.9・17.7・19.7・22.5・24.5 m（軸間 2.0・2.8・2.0・2.8・
    4.0・2.8・2.0・2.8・2.0）に置くと R_C＝170×129.0/24.0＝913.75（0600 の ③ 終点側だけの載荷と同じ）. 継ぎ目の軸を
    てこ比の大きい起点側（7.6/7.2＞24.5/24.0）に数えていたので 878.33 を採っていた."""
    pier = parse_input(EXAMPLE4)
    trains = vehicle(pier.train).trains
    free = search_reactions(pier.spans.origin, pier.spans.end, trains, objective=Objective.END)
    end_only = search_reactions(pier.spans.origin, pier.spans.end, trains, objective=Objective.END, loaded=Girder.END)
    levers = [Decimal(text) for text in ("1.3", "3.3", "6.1", "8.1", "10.9", "14.9", "17.7", "19.7", "22.5", "24.5")]
    assert sum(levers) == Decimal("129.0")
    hand = q(170 * sum(levers) / Decimal("24.0"), 2)
    assert end_only.rc.value == float(hand) == 913.75
    assert free.rc.value == float(hand)
    assert [value(axle.lever) for axle in free.on(Girder.END)] == levers
