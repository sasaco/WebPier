"""有効根入れ深さ Df と平均有効単位重量 γ2 of the cover above the footing base (CONTEXT.md, README JRSNAP).

Example2 08 p.8-28 procedure: Df = H6 + H5 + min(df1, df2), γ2 = ((Df − hw2) × γwet + hw2 × γsub) / Df, with hw2
measured up from the footing base. Expected values are hand calculations; the current input gives Df = 4.700 and
γ2 = (2.000 × 18.0 + 2.700 × 8.0) / 4.700 = 12.2553… → 12.3 kN/m3. Several layers (decision 64) sum each layer's
part above and below the water.
"""

import re
from decimal import Decimal

import pytest

from reaction_support import document, pier, q
from webpier.calc.embedment import applicable_embedment, calculate_embedment, cover_weight, displaced_soil
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
    assert result.water == Printed(2.7, 3, "m") and result.normal.wet_segment == Printed(2.0, 3, "m")
    assert result.single is not None and result.single.name == "表層"
    assert (result.single.unit_weight_wet.value, result.single.unit_weight_submerged.value) == (18.0, 8.0)
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
    assert result.depth.value == float(df) and result.normal.wet_segment.value == float(df - water)
    assert result.unit_weight.value == float(q(gamma, 1))


def test_the_cover_must_be_level():
    with pytest.raises(InputError, match=re.escape("下部構造.土かぶり: 起点側_df1（2.0 m）と終点側_df2（1.9 m）が異なり")):
        embedment(**{"下部構造/土かぶり/終点側_df2": 1.9})


@pytest.mark.parametrize("hw2", [0.0, 4.7, 5.0, -0.1])
def test_the_normal_water_level_must_lie_inside_the_cover(hw2):
    with pytest.raises(InputError, match=re.escape("下部構造.水位.平水位_hw2: 0 < hw2 < Df（4.7 m）")):
        embedment(**{WATER: hw2})


LOAM = {"層番": "ローム", "層厚": 1.0, "土質区分": "粘性土", "N値": 4, "単位体積重量": {"湿潤": 17.0, "水中": 7.0},
        "内部摩擦角_φd": None, "一軸圧縮強度_qu": None, "変形係数_Ed": None}


def layered(surface, loam=LOAM):
    """表層 (18.0 / 8.0) with *surface* 層厚, ローム, 支持層 (19.0 / 10.0); Df 4.700, hw2 2.700."""
    data = document()
    data["地盤データ"]["層"][0]["層厚"] = surface
    data["地盤データ"]["層"].insert(1, dict(loam))
    p = parse_input(data)
    return p, calculate_embedment(p, calculate_foundation(p))


def test_several_layers_fill_df_from_the_ground_and_the_support_takes_the_rest():
    # 表層 1.050 (3.650–4.700), ローム 1.000 (2.650–3.650), 支持層 4.700 − 2.050 = 2.650 (0–2.650); hw2 = 2.700:
    # (1.050 × 18.0 + 0.950 × 17.0 + 0.050 × 7.0 + 2.650 × 10.0) / 4.700 = 61.90 / 4.700 = 13.170… → 13.2
    _, result = layered(1.05)
    assert [(layer.name, layer.bottom.value, layer.thickness.value) for layer in result.layers] == [
        ("表層", 3.65, 1.05), ("ローム", 2.65, 1.0), ("支持層", 0.0, 2.65)]
    assert [(s.thickness.value, s.unit_weight.value, s.submerged) for s in result.normal.segments] == [
        (1.05, 18.0, False), (0.95, 17.0, False), (0.05, 7.0, True), (2.65, 10.0, True)]
    assert result.unit_weight == Printed(13.2, 1, "kN/m3") and result.single is None
    # all submerged at the ground: (1.050 × 8.0 + 1.000 × 7.0 + 2.650 × 10.0) / 4.700 = 41.90 / 4.700 = 8.914… → 8.9
    assert cover_weight(result, Printed(4.7, 3, "m")).unit_weight == Printed(8.9, 1, "kN/m3")


def test_a_blank_surface_thickness_is_the_rest_above_the_layers_below_it():
    # 表層 4.700 − 1.000 = 3.700 (1.000–4.700), ローム 0–1.000, 支持層 from the footing base (none within Df):
    # (2.000 × 18.0 + 1.700 × 8.0 + 1.000 × 7.0) / 4.700 = 56.60 / 4.700 = 12.042… → 12.0
    _, result = layered(None)
    assert [(layer.name, layer.thickness.value) for layer in result.layers] == [("表層", 3.7), ("ローム", 1.0)]
    assert result.unit_weight == Printed(12.0, 1, "kN/m3")


def test_the_layers_above_the_support_must_fit_in_df():
    with pytest.raises(InputError, match=re.escape(
            "地盤データ.層: 表層から支持層の上までの層厚の合計 5.000 m が Df（H6＋H5＋min(df1,df2) = 4.700 m）を超えます")):
        layered(4.0)
    with pytest.raises(InputError, match=re.escape("地盤データ.層: 表層と支持層の間の層厚の合計 5.000 m が Df")):
        layered(None, LOAM | {"層厚": 5.0})


def test_a_layer_within_df_needs_its_unit_weights():
    with pytest.raises(InputError, match=re.escape("地盤データ.層[1].単位体積重量.湿潤: 値が必要です（Df の範囲の層）")):
        layered(1.05, LOAM | {"単位体積重量": {"湿潤": None, "水中": 7.0}})


def test_the_displaced_soil_averages_the_layers_in_the_footing_height():
    # H5 + H6 = 2.700: 支持層 0–2.650 and ローム 2.650–2.700: (2.650 × 19.0 + 0.050 × 17.0) / 2.700 = 18.962… → 19.0
    p, _ = layered(1.05)
    soil = displaced_soil(p, Printed(2.7, 3, "m"))
    assert [(layer.name, part.value) for layer, part in soil.parts] == [("ローム", 0.05), ("支持層", 2.65)]
    assert soil.unit_weight == Printed(19.0, 1, "kN/m3")
    # Example2: 表層 alone, its wet unit weight
    assert displaced_soil(pier(), Printed(2.7, 3, "m")).unit_weight == Printed(18.0, 1, "kN/m3")


def test_outside_the_procedure_there_is_no_embedment_result():
    # The 0500 report prints γ2 only where the procedure applies; elsewhere it is not defined (not an error there).
    p = pier(**{"下部構造/土かぶり/終点側_df2": 1.9})
    assert applicable_embedment(p, calculate_foundation(p)) is None
    p = pier()
    assert applicable_embedment(p, calculate_foundation(p)) == calculate_embedment(p, calculate_foundation(p))


@pytest.mark.parametrize("water,wet_segment,submerged,gamma", [
    (3.78, 0.92, 3.78, 10.0),  # (0.920 × 18.0 + 3.780 × 8.0) / 4.700 = 9.957…
    (2.7, 2.0, 2.7, 12.3),  # the normal water level: γ2 itself
    (4.7, 0.0, 4.7, 8.0),  # at the ground: all submerged
    (6.0, 0.0, 4.7, 8.0),  # above it: all submerged
    (0.0, 4.7, 0.0, 18.0),  # at the footing base: all wet
    (-1.0, 4.7, 0.0, 18.0),  # below it: all wet
])
def test_the_cover_weight_at_any_water_level(water, wet_segment, submerged, gamma):
    """Decision 54: γ2 at the water level of a check (長期 the normal, 短期 and 安全性 the high one)."""
    level = Printed(water, 3, "m")
    result = cover_weight(embedment(), level)
    assert (result.water, result.wet_segment.value, result.submerged_segment.value) == (level, wet_segment, submerged)
    assert result.unit_weight == Printed(gamma, 1, "kN/m3")
