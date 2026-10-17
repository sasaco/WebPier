"""有効根入れ深さ Df と平均有効単位重量 γ2 of the cover above the footing base (CONTEXT.md, README JRSNAP).

Example2 08 p.8-28 procedure: Df = H6 + H5 + min(df1, df2), γ2 = ((Df − hw2) × γwet + hw2 × γsub) / Df, with hw2
measured up from the footing base. Expected values are hand calculations; the current input gives Df = 4.700 and
γ2 = (2.000 × 18.0 + 2.700 × 8.0) / 4.700 = 12.2553… → 12.3 kN/m3.
"""

import re
from decimal import Decimal

import pytest

from reaction_support import document, pier, q
from webpier.calc.embedment import calculate_embedment
from webpier.calc.foundation import calculate_foundation
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import parse_input

WATER = "下部構造/水位/平水位_hw2"
WET, SUBMERGED = "地盤データ/層/0/単位体積重量/湿潤", "地盤データ/層/0/単位体積重量/水中"


def embedment(**changes):
    p = pier(**changes)
    return calculate_embedment(p, calculate_foundation(p))


def test_current_input():
    result = embedment()
    assert result.depth == Printed(4.7, 3, "m")
    assert result.water == Printed(2.7, 3, "m") and result.wet_segment == Printed(2.0, 3, "m")
    assert (result.unit_weight_wet.value, result.unit_weight_submerged.value) == (18.0, 8.0)
    assert result.unit_weight == Printed(12.3, 1, "kN/m3")


@pytest.mark.parametrize("h5,h6,cover,hw2,wet,sub", [
    (0.5, 2.2, 1.5, 0.8, 19.0, 9.0),
    (0.0, 2.7, 2.0, 4.65, 18.0, 8.0),
    (0.3, 1.5, 0.0, 0.05, 17.5, 7.5),
])
def test_hand_calculations(h5, h6, cover, hw2, wet, sub):
    result = embedment(**{"下部構造/寸法/高さ/H5": h5, "下部構造/寸法/高さ/H6": h6, "下部構造/土かぶり/起点側_df1": cover,
                          "下部構造/土かぶり/終点側_df2": cover, WATER: hw2, WET: wet, SUBMERGED: sub})
    df = Decimal(str(h6)) + Decimal(str(h5)) + Decimal(str(cover))
    water = Decimal(str(hw2))
    gamma = ((df - water) * Decimal(str(wet)) + water * Decimal(str(sub))) / df
    assert result.depth.value == float(df) and result.wet_segment.value == float(df - water)
    assert result.unit_weight.value == float(q(gamma, 1))


def test_the_cover_must_be_level():
    with pytest.raises(InputError, match=re.escape("下部構造.土かぶり: 起点側_df1（2.0 m）と終点側_df2（1.9 m）が異なり")):
        embedment(**{"下部構造/土かぶり/終点側_df2": 1.9})


@pytest.mark.parametrize("hw2", [0.0, 4.7, 5.0, -0.1])
def test_the_normal_water_level_must_lie_inside_the_cover(hw2):
    with pytest.raises(InputError, match=re.escape("下部構造.水位.平水位_hw2: 0 < hw2 < Df（4.7 m）")):
        embedment(**{WATER: hw2})


def test_one_surface_layer_on_the_supporting_layer():
    middle = {"層番": "中間層", "層厚": 1.0, "土質区分": "砂質土", "N値": 10, "単位体積重量": {"湿潤": 18.0, "水中": 8.0},
              "内部摩擦角_φd": None, "一軸圧縮強度_qu": None, "変形係数_Ed": None}
    data = document()
    data["地盤データ"]["層"].insert(1, middle)
    p = parse_input(data)
    with pytest.raises(InputError, match=re.escape("地盤データ.層: 表層と支持層の2層だけに対応します（3層）")):
        calculate_embedment(p, calculate_foundation(p))
