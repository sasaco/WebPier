"""0600 transverse forces at the bearings on this pier: Example2 07 7-14 to 7-18 and hand calculations."""

from decimal import Decimal

import pytest

from reaction_support import D, example2, pier, q, value
from webpier.calc.moving_load import Girder
from webpier.calc.reaction import calculate_reaction
from webpier.core.errors import InputError

EX = {}
for section in ("07_7-14_vehicle_lateral", "07_7-15_wind_with_train_start", "07_7-16_wind_with_train_end",
                "07_7-17_wind_without_train", "07_7-18_seismic_transverse"):
    EX.update(example2(section))


def transverse(p=None):
    return calculate_reaction(p or pier()).transverse


def triple(force):
    return force.force.value, force.height.value, force.moment.value


def test_example2_vehicle_lateral_7_14():
    result = transverse()
    assert result.lateral_axle_load.value == EX["vehicle_lateral.LF"]
    assert triple(result.origin.vehicle_lateral) == (
        EX["vehicle_lateral.start.HB"], EX["vehicle_lateral.start.y1"], EX["vehicle_lateral.start.M1"])
    assert triple(result.end.vehicle_lateral) == (
        EX["vehicle_lateral.end.HC"], EX["vehicle_lateral.end.y1"], EX["vehicle_lateral.end.M1"])
    # HB = 32.00 x (14.425 + 16.625) / 18.85: two axles per girder.
    assert sorted(a.lever.value for a in result.lateral_loading.axles if a.girder is Girder.ORIGIN) == [14.425, 16.625]


def test_example2_wind_7_15_to_7_17():
    result = transverse()
    # The input folds the shelter into h4 (h4 = 9.433 / 10.767), so H with the train matches Example2's totals
    # (girder + shelter): 1.5 × (2.600 + 1.100 + 9.433) × 20.000 / 2 = 196.995 -> 197.00.
    assert result.origin.wind_with_train.force.value == EX["wind_with_train.start.HB_girder"] + EX[
        "wind_with_train.start.shelter"] == 197.0
    assert result.end.wind_with_train.force.value == EX["wind_with_train.end.HC"] == 108.88  # 108.8775
    # Without the train, 3.0 × 13.133 × 20.000 / 2 = 393.99 (Example2 7-17: 114.00 + 280.00 = 394.00) and
    # 3.0 × 14.517 × 10.000 / 2 = 217.755 -> 217.76 (Example2: 57.75 + 160.00 = 217.75). The 0.01 differences
    # come from h4, back-calculated to 3 decimals in current.json; Example2 itself is not reproducible from our input.
    assert result.origin.wind_without_train.force.value == 393.99
    assert result.end.wind_without_train.force.value == 217.76
    # Heights and moments differ from Example2 by design (shelter included in h; the user accepted the wind M).
    assert result.origin.wind_with_train.height.value == 6.717  # 13.133 / 2 + 0.150
    assert result.origin.wind_with_train.moment.value == 1323.25  # 197.00 × 6.717 = 1323.249


def test_example2_seismic_7_18():
    result = transverse()
    girder, train = result.origin.seismic_girder, result.origin.seismic_train
    assert girder.force.value == EX["seismic_transverse.start.HB"] == 6720.0
    assert girder.height.value == 2.952  # hs, the equivalent height of girder and shelter
    assert girder.moment.value == 19837.44  # 6720.00 × 2.952 (Example2: 15180 + shelter 4658 = 19838)
    # End side: D1 + D2 + S2 = 1860 + 260 + 250 = 2370; Example2 prints 2360 (shelter reaction 640 vs the
    # folded D1 400 + S2 250), the documented +10 kN residual of current.json.
    assert result.end.seismic_girder.force.value == 2370.0
    assert triple(train) == (EX["seismic_train_transverse.start.HB"], EX["seismic_train_transverse.start.y1"],
                             EX["seismic_train_transverse.start.MB"])
    assert triple(result.end.seismic_train) == (EX["seismic_train_transverse.end.HC"],
                                                 EX["seismic_train_transverse.end.y1"],
                                                 EX["seismic_train_transverse.end.MC"])


def test_straight_track_has_no_centrifugal_force():
    result = transverse()
    assert result.origin.centrifugal_coefficient.value == 0.0
    assert result.origin.centrifugal_ultimate.force.value == 0.0


def test_centrifugal_by_hand():
    result = transverse(pier(**{"上部構造/起点側/曲線半径": 600, "上部構造/起点側/列車速度": 130}))
    side = result.origin
    alpha = q(D(130) ** 2 / (127 * D(600)), 3)  # 16900 / 76200 = 0.22178 -> 0.222
    assert value(side.centrifugal_coefficient) == alpha
    height = D("0.15") + D("2.6") + D("1.1") + D("1.5")
    for group, rho in (("ultimate", D("1.231")), ("service", D(1)), ("fatigue", D(1))):
        force = q(q(D("272.47") * rho, 2) * alpha, 2)
        assert (value(getattr(side, "centrifugal_" + group).force), value(getattr(side, "centrifugal_" + group).height),
                value(getattr(side, "centrifugal_" + group).moment)) == (force, height, q(force * height, 2)), group
    assert result.end.centrifugal_coefficient.value == 0.0


def test_wind_height_uses_the_train_when_it_is_taller_than_h4():
    result = transverse(pier(**{"上部構造/終点側/高さ/h4": 2.0}))
    end = result.end
    assert end.wind_height_with_train.value == 7.25  # 2.650 + 1.100 + max(3.500, 2.000)
    assert end.wind_height_without_train.value == 5.75
    assert end.wind_with_train.force.value == float(q(Decimal("1.5") * D(7.25) * D(10) / 2, 2))
    assert end.wind_with_train.height.value == 3.725  # 7.250 / 2 + 0.100


def test_seismic_girder_by_hand():
    result = transverse(pier(**{"上部工反力/起点側/B支点/0/雪荷重_2年確率": 12.34, "上部構造/起点側/重心高_hs": 3.333}))
    force = D(5740) + D(520) + (D(460) - 200 + D("12.34"))
    assert value(result.origin.seismic_girder.force) == force
    assert value(result.origin.seismic_girder.moment) == q(force * D("3.333"), 2)


def test_lateral_load_is_not_factored_by_rho():
    # Example2 7-14: LF = 0.2 × 160.0 (P without ρf). The old code used 0.2 × P × ρu.
    result = transverse(pier(**{"上部構造/列車/荷重修正係数/安全性(破壊)": 1.5}))
    assert result.lateral_axle_load.value == 32.0


def test_a_lateral_load_that_rounds_to_zero_is_an_input_error():
    with pytest.raises(InputError, match="最大"):
        transverse(pier(**{"上部構造/列車/軸重/地震以外": 0.02}))


def test_printed_digits():
    side = transverse().origin
    assert (side.vehicle_lateral.force.digits, side.vehicle_lateral.height.digits, side.vehicle_lateral.moment.digits,
            side.centrifugal_coefficient.digits) == (2, 3, 2, 3)
    assert side.vehicle_lateral.moment.unit == "kN m"
