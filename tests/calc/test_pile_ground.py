"""0500 杭基礎: the values given to SOIL-JR (decision 85, ADR-0013) — the layers cut at the pile head and the pile tip, the
ground above the head weighted over the water, the pile section and the pile rows. Expected values are hand calculations;
the current pile input is the SOIL-JR 5.2 sample (場所打ち杭 3 × 3, the middle one left out), whose own values they are."""

import re

import pytest

from pile_ground_support import layer, layers, pile_pier
from webpier.calc.pile_ground import PileGroundResult, calculate_pile_ground
from webpier.core.errors import InputError


def ground(**changes) -> PileGroundResult:
    return calculate_pile_ground(pile_pier(**changes))


def fails(message, **changes):
    with pytest.raises(InputError, match=re.escape(message)):
        ground(**changes)


def test_the_sample_is_reproduced():
    result = ground()
    assert (result.depth.value, result.length.value, result.water_depth.value) == (2.8, 19.0, 2.8)
    assert (result.head.thickness.value, result.head.unit_weight_wet.value, result.head.unit_weight_submerged.value) == (
        2.8, 18.0, 8.0)
    assert [row.thickness.value for row in result.layers] == [2.6, 5.0, 4.0, 6.4, 1.0]
    assert [row.kind for row in result.layers] == [1, 1, 2, 2, 1]
    assert [(row.n_value.value, row.cohesion.value, row.friction_angle.value) for row in result.layers] == [
        (10, 0, 29), (15, 0, 31), (4, 50, 0), (10, 100, 0), (50, 0, 38)]
    assert [row.deformation_modulus.value for row in result.layers] == [14286, 21429, 2857, 4464, 71429]
    assert sum(row.thickness.value for row in result.layers) == result.length.value
    assert not result.liquefaction and result.head.layers == (0,)


def test_the_pile_of_the_sample():
    section = ground().section
    assert (section.kind, section.method, section.construction) == (1, 1, 1)
    assert (section.diameter.value, section.ec.value, section.area.value, section.second_moment.value) == (
        1.0, 22.4, 0.785398, 0.049087)
    assert section.es is None and section.inner_diameter is None and section.unit_weight.value == 24.5
    assert section.minimum_embedment.value == 1.0  # the layer at the tip is a sand


def test_the_pile_rows_of_the_sample():
    rows = ground().rows
    assert rows.pattern == 1 and rows.piles == 8 and rows.rows_written and rows.removed == ((2, 2),)
    assert [(column.count, column.distance.value) for column in rows.along] == [(3, 0), (2, 3), (3, 6)]
    assert [(column.count, column.distance.value) for column in rows.across] == [(3, 0), (2, 3), (3, 6)]
    assert (rows.spacing_along.value, rows.spacing_across.value) == (3, 3)
    assert [value.value for value in (*rows.lm, *rows.ln)] == [3, 3, 3, 3]


def test_the_construction_condition_is_its_place_in_the_choices():
    assert ground(**{"杭基礎/場所打ち杭/施工条件": "安定液使用"}).section.construction == 2


@pytest.mark.parametrize("fck,ec", [(18.0, 22.0), (24.0, 25.0), (27.0, 26.5), (30.0, 28.0), (80.0, 38.0)])
def test_ec_is_the_table_of_decision_25_in_kn_per_mm2(fck, ec):
    assert ground(**{"杭基礎/場所打ち杭/f'ck": fck}).section.ec.value == ec


def test_a_strength_outside_the_table_is_an_input_error():
    fails("杭基礎.場所打ち杭.f'ck: ヤング係数の表の範囲外です", **{"杭基礎/場所打ち杭/f'ck": 90.0})


def test_a_steel_soil_cement_pile_section():
    # (its 0400 uses 0711 and 0721, decision 123: not chosen here)
    section = ground(**{"下部構造/基礎形式": "鋼管ソイルセメント杭", "outputs/detailing": False}).section
    assert (section.kind, section.method, section.construction) == (5, 7, 0)
    assert (section.diameter.value, section.inner_diameter.value, section.thickness.value, section.corrosion.value) == (
        1.2, 1.0, 18.0, 1.0)
    assert section.es.value == 200.0 and section.ec is None
    assert section.area.value == 1.130973  # π × 1.2² / 4 of the soil cement, π as SOIL-JR writes it
    assert section.second_moment.value == 0.006304  # π ((1.0 − 0.002)⁴ − (1.0 − 0.036)⁴) / 64 of the steel pipe
    assert section.minimum_embedment.value == 1.2


def test_the_least_embedment_is_half_the_diameter_when_the_pile_ends_in_a_clay():
    rows = layers(layer("表層", 2.8), layer("粘", 6.0, "粘性土", n=5, phi=None, c=60, ed=3000),
                  layer("粘2", None, "粘性土", n=6, phi=None, c=70, ed=4000))
    assert ground(**rows).section.minimum_embedment.value == 0.5
    one = layers(layer("表層", 2.8), layer("粘", None, "粘性土", n=5, phi=None, c=60, ed=3000))
    assert ground(**one).section.minimum_embedment.value == 1.0  # a single layer along the pile


def test_a_layer_is_cut_at_the_footing_base_and_at_the_pile_tip():
    data = layers(layer("上", 2.0, wet=17.0, submerged=7.0), layer("中", 2.0, n=12, ed=12000),
                  layer("下", 3.0, n=20, ed=20000), layer("底", None, n=40, ed=40000))
    result = ground(**data)
    assert [row.name for row in result.layers] == ["中", "下", "底"]
    assert [row.thickness.value for row in result.layers] == [1.2, 3.0, 14.8]  # 中 4.0 − 2.8 below the base; 底 to 19 m
    assert result.head.layers == (0, 1)
    tip = ground(**data, **{"杭基礎/杭長": 3.0})
    assert [(row.name, row.thickness.value) for row in tip.layers] == [("中", 1.2), ("下", 1.8)]


def test_the_ground_above_the_head_is_weighted_over_the_water():
    """Df 2.8, the water 1.8 m below the ground (hw2 1.0): 17 over 1.5 m and 19 over 0.3 m above it, 9 below it."""
    data = layers(layer("A", 1.5, wet=17.0, submerged=7.0), layer("B", 1.3, wet=19.0, submerged=9.0),
                  layer("C", None, n=30, ed=30000))
    result = ground(**data, **{"下部構造/水位/平水位_hw2": 1.0})
    assert result.water_depth.value == 1.8
    assert result.head.unit_weight_wet.value == 17.3  # (1.5 × 17 + 0.3 × 19) / 1.8 = 17.33
    assert result.head.unit_weight_submerged.value == 9.0  # 1.0 m of B below the water
    assert result.head.layers == (0, 1)


def test_the_part_without_water_or_with_nothing_but_water_takes_its_neighbours_weight():
    data = layers(layer("A", 1.5, wet=17.0, submerged=7.0), layer("B", 1.3, wet=19.0, submerged=9.0),
                  layer("C", None, n=30, ed=30000))
    dry = ground(**data, **{"下部構造/水位/平水位_hw2": -1.0})  # the water below the base: none of the head is under it
    assert dry.water_depth.value == 3.8
    # (1.5 × 17 + 1.3 × 19) / 2.8 = 17.93 above the water; nothing below it, so the last head layer's 9.0
    assert (dry.head.unit_weight_wet.value, dry.head.unit_weight_submerged.value) == (17.9, 9.0)
    flooded = ground(**data, **{"下部構造/水位/平水位_hw2": 3.5})  # the water above the ground
    assert flooded.water_depth.value == -0.7
    # nothing above the water, so the first layer's wet 17.0; (1.5 × 7 + 1.3 × 9) / 2.8 = 7.93 below it
    assert (flooded.head.unit_weight_wet.value, flooded.head.unit_weight_submerged.value) == (17.0, 7.9)


def test_the_water_must_be_within_what_soil_jr_takes():
    fails("下部構造.水位.平水位_hw2: 地表から平水位までが範囲外です", **{"下部構造/水位/平水位_hw2": 103.0})


def test_a_layer_along_the_pile_may_liquefy_and_a_layer_above_it_does_not_count():
    data = layers(layer("表層", 2.8), layer("液状化する層", 4.0, de=0.5), layer("下", None, n=30, ed=30000))
    assert ground(**data).liquefaction
    assert ground(**data).layers[0].reduction.value == 0.5
    assert not ground(**layers(layer("表層", 2.8, de=0.2), layer("下", None, n=30, ed=30000))).liquefaction
    assert not ground(**layers(layer("表層", 2.8), layer("下", None, de=1.0))).liquefaction


@pytest.mark.parametrize("changes,message", [
    (layers(layer("表層", None), layer("下", None)), "地盤データ.層[0].層厚: 値が必要です"),
    (layers(layer("表層", 0.0), layer("下", None)), "地盤データ.層[0].層厚: 正の数値が必要です"),
    (layers(layer("表層", 2.8), layer("互層", None, "砂質土と粘性土の互層")), "地盤データ.層[1].土質区分: SOIL-JR の地盤種別"),
    (layers(layer("表層", 2.8), layer("下", None, n=None)), "地盤データ.層[1].N値: 値が必要です"),
    (layers(layer("表層", 2.8), layer("下", None, n=0)), "地盤データ.層[1].N値: 0より大きい値が必要です"),
    (layers(layer("表層", 2.8), layer("下", None, phi=None)), "地盤データ.層[1].内部摩擦角_φd: 値が必要です"),
    (layers(layer("表層", 2.8), layer("下", None, "粘性土", phi=None, c=None)), "地盤データ.層[1].粘着力_c: 値が必要です"),
    (layers(layer("表層", 2.8), layer("下", None, ed=None)), "地盤データ.層[1].変形係数_Ed: 値が必要です"),
    (layers(layer("表層", 2.8), layer("下", None, wet=None)), "地盤データ.層[1].単位体積重量.湿潤: 値が必要です"),
    (layers(layer("表層", 2.8), layer("下", None, submerged=0.0)), "地盤データ.層[1].単位体積重量.水中: 0より大きい値が必要です"),
    (layers(layer("表層", 2.8, wet=None), layer("下", None)), "地盤データ.層[0].単位体積重量.湿潤: 値が必要です"),
])
def test_a_value_a_row_needs_is_an_input_error_with_its_path(changes, message):
    fails(message, **changes)


def test_a_sand_may_have_no_cohesion_and_a_clay_no_friction_angle():
    result = ground(**layers(layer("表層", 2.8), layer("砂", 5.0, "砂礫", c=None), layer("粘", None, "粘性土", phi=None, c=40)))
    assert [(row.kind, row.cohesion.value, row.friction_angle.value) for row in result.layers] == [(3, 0, 30), (2, 40, 0)]


def test_at_most_twenty_layers_along_the_pile():
    rows = [layer("表層", 2.8)] + [layer(f"L{i}", 0.5) for i in range(20)] + [layer("底", None)]
    fails("杭の区間の層が21層あります", **layers(*rows))
    rows = [layer("表層", 2.8)] + [layer(f"L{i}", 0.5) for i in range(19)] + [layer("底", None)]
    assert len(ground(**layers(*rows)).layers) == 20


@pytest.mark.parametrize("pattern,along,across,removed,expected", [
    ("格子", [-3.0, 0.0, 3.0], [-3.0, 3.0], [], (6, False)),
    ("格子", [-3.0, 0.0, 3.0], [-3.0, 3.0], [(1, 1)], (5, True)),
    ("格子", [-3.0, 0.0, 4.5], [-3.0, 3.0], [], (6, True)),
    ("千鳥", [-3.0, 0.0, 3.0], [-3.0, 0.0, 3.0], [], (5, False)),
    ("千鳥", [-3.0, 0.0, 3.0], [-3.0, 0.0, 3.0], [(1, 1)], (4, True)),
])
def test_the_rows_are_written_when_holes_or_unequal_intervals_make_them_not_the_grid(pattern, along, across, removed,
                                                                                    expected):
    holes = [{"線路方向の列": i, "線路直角方向の列": j} for i, j in removed]
    layout = {"形式": pattern, "線路方向の列の位置": along, "線路直角方向の列の位置": across, "抜く杭": holes}
    rows = ground(**{"杭基礎/配置": layout}).rows
    assert (rows.piles, rows.rows_written) == expected


def test_the_columns_of_a_staggered_layout_have_the_piles_where_the_numbers_add_to_an_even_number():
    layout = {"形式": "千鳥", "線路方向の列の位置": [0.0, 2.0, 4.0], "線路直角方向の列の位置": [0.0, 3.0, 6.0], "抜く杭": []}
    rows = ground(**{"杭基礎/配置": layout}).rows
    assert rows.pattern == 2
    assert [column.count for column in rows.along] == [2, 1, 2] and [column.count for column in rows.across] == [2, 1, 2]
    assert [column.distance.value for column in rows.along] == [0, 2, 4]


@pytest.mark.parametrize("along,across,lm,ln", [
    # a = 3 (along), b = 3: a / b = 1 < 1.5 → Lm 2a, Ln b; the cross direction the same with the roles swapped
    ([0.0, 3.0, 6.0], [0.0, 3.0, 6.0], (6, 3), (6, 3)),
    # a = 6, b = 3: a / b = 2 ≥ 1.5 → Lm a, Ln 2b; b / a = 0.5 < 1.5 → 2b, a
    ([0.0, 6.0, 12.0], [0.0, 3.0, 6.0], (6, 6), (6, 6)),
    # a = 3, b = 6: a / b = 0.5 → 2a, b; b / a = 2 → b, 2a
    ([0.0, 3.0, 6.0], [0.0, 6.0, 12.0], (6, 6), (6, 6)),
])
def test_the_group_intervals_of_a_staggered_layout(along, across, lm, ln):
    layout = {"形式": "千鳥", "線路方向の列の位置": along, "線路直角方向の列の位置": across, "抜く杭": []}
    rows = ground(**{"杭基礎/配置": layout}).rows
    assert (rows.lm[0].value, rows.lm[1].value) == lm and (rows.ln[0].value, rows.ln[1].value) == ln


def test_a_single_column_has_no_interval():
    layout = {"形式": "格子", "線路方向の列の位置": [0.0], "線路直角方向の列の位置": [-3.0, 3.0], "抜く杭": []}
    rows = ground(**{"杭基礎/配置": layout}).rows
    assert (rows.spacing_along.value, rows.spacing_across.value) == (0, 6)
    assert [column.distance.value for column in rows.across] == [0, 6]
    single = {"形式": "千鳥", "線路方向の列の位置": [0.0], "線路直角方向の列の位置": [0.0], "抜く杭": []}
    one = ground(**{"杭基礎/配置": single}).rows
    assert (one.piles, one.spacing_along.value, one.spacing_across.value) == (1, 0, 0)
    assert [value.value for value in (*one.lm, *one.ln)] == [0, 0, 0, 0]
