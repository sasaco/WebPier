"""Parse the schema 2 input JSON into PierInput (decisions 5, 6, 16-19).

Nothing is filled in: a missing value is an input error, a value finer than
the printed digits is an input error, and an unknown key is an input error.
"""

from __future__ import annotations

from typing import Any

from ..core.printed import Precision, Printed
from ..core.reader import Reader, Sign
from . import choices
from .model import (
    Bearing, EndReaction, Jrsnap, JrsnapConditions, Materials, PierInput, Pile, Reactions, Reserved, Shares,
    Soil, SoilLayer, Span, Spans, Substructure, Train,
)
from .rebar import parse_rebar

# Digits of the input sheet (.claude/docs/Example橋脚/pre/input-*.pdf).
LENGTH = Precision(3, "m")
LOAD = Precision(2, "kN")
LINE_LOAD = Precision(2, "kN/m")
RATIO = Precision(3, "")
FRICTION = Precision(2, "")
UNIT_WEIGHT = Precision(1, "kN/m3")
RADIUS = Precision(0, "m")
SPEED = Precision(0, "km/h")
ANGLE = Precision(0, "°")
FRICTION_ANGLE = Precision(1, "°")
N_VALUE = Precision(0, "")
STRESS = Precision(0, "kN/m2")
STRENGTH = Precision(1, "N/mm2")
SHEAR_FACTOR = Precision(2, "")  # γb, at most 99.99 (JRSNAP SectSafe)
AGGREGATE = Precision(1, "mm")  # Dmax, 0.1..999999 mm (JRSNAP SectConc)
SHEAR_FACTOR_MAX = 99.99
AGGREGATE_RANGE = (0.1, 999_999)
MAX_STEPS = 100_000

SCHEMA_VERSION = 2
BEARING_SLOTS = 10
SNOW_KEYS = ("雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率")


def _optional(parent: Reader, key: str, precision: Precision, *, sign: Sign = "nonnegative") -> Printed | None:
    child = parent.at(key)
    return None if child.is_null else child.printed(precision, sign=sign)


def _substructure(root: Reader) -> Substructure:
    sub = root.at("下部構造")
    dims = sub.at("寸法").only("側面", "正面", "高さ")
    sized: dict[str, dict[int, Printed]] = {}
    for group, prefix, count, positive in (("側面", "B", 9, {1, 6, 8}), ("正面", "W", 9, {1, 6, 8}),
                                           ("高さ", "H", 6, {4, 6})):
        node = dims.at(group).only(*(f"{prefix}{index}" for index in range(1, count + 1)))
        sized[prefix] = {index: node.at(f"{prefix}{index}").printed(
            LENGTH, sign="positive" if index in positive else "nonnegative") for index in range(1, count + 1)}
    for prefix, group in (("B", "側面"), ("W", "正面")):
        size = sized[prefix]
        if size[1].value <= size[4].value + size[5].value:
            raise dims.at(group, f"{prefix}1").error(f"{prefix}4+{prefix}5より大きい値が必要です")
    cover = sub.at("土かぶり").only("起点側_df1", "終点側_df2")
    water = sub.at("水位").only("高水位_hw1", "平水位_hw2", "低水位_hw3")
    weights = sub.at("単位体積重量").only("梁・躯体", "フーチング", "杭", "上載土")
    return Substructure(
        b=sized["B"], w=sized["W"], h=sized["H"],
        df1=cover.at("起点側_df1").printed(LENGTH), df2=cover.at("終点側_df2").printed(LENGTH),
        hw1=water.at("高水位_hw1").printed(LENGTH, sign="any"),
        hw2=water.at("平水位_hw2").printed(LENGTH, sign="any"),
        hw3=water.at("低水位_hw3").printed(LENGTH, sign="any"),
        unit_weight_body=weights.at("梁・躯体").printed(UNIT_WEIGHT, sign="positive"),
        unit_weight_footing=weights.at("フーチング").printed(UNIT_WEIGHT, sign="positive"),
        unit_weight_overburden=weights.at("上載土").printed(UNIT_WEIGHT),
    )


def _span(root: Reader, side: str) -> Span:
    span = root.at("上部構造", side).only("桁長", "衝撃係数_単線終局", "曲線半径", "列車速度", "遠心作用方向",
                                        "高さ", "重心高_hs", "支承位置_f")
    lengths = span.at("桁長").only("L1", "スパン長", "L2")
    heights = span.at("高さ").only("h1", "h2", "h3", "h4")
    support = root.at("上部構造", "支承データ", side).only("支承名", "摩擦係数_μ", "復旧性制動係数")
    brake = support.optional("復旧性制動係数")
    return Span(
        l1=lengths.at("L1").printed(LENGTH), span=lengths.at("スパン長").printed(LENGTH, sign="positive"),
        l2=lengths.at("L2").printed(LENGTH),
        impact=span.at("衝撃係数_単線終局").printed(RATIO),
        radius=span.at("曲線半径").printed(RADIUS), speed=span.at("列車速度").printed(SPEED),
        heights={index: heights.at(f"h{index}").printed(LENGTH) for index in range(1, 5)},
        hs=span.at("重心高_hs").printed(LENGTH),
        f=span.at("支承位置_f").printed(LENGTH),
        bearing=support.at("支承名").choice(choices.BEARING_TYPES),
        mu=support.at("摩擦係数_μ").printed(FRICTION),
        recovery_brake_coefficient=None if brake is None else brake.printed(RATIO),
    )


def _train(root: Reader) -> Train:
    train = root.at("上部構造", "列車").only("車両名", "1両の長さ", "軸距", "軸重", "編成数", "車両高", "荷重修正係数")
    vehicle = train.at("車両名")
    if not isinstance(vehicle.value, str):
        raise vehicle.error(f"{'・'.join(choices.VEHICLES)}から選んでください（入力: {vehicle.value!r}）")
    name = vehicle.choice(tuple(choices.VEHICLES))
    spacing = train.at("軸距").only("a1_連結部", "a2")
    axle = train.at("軸重").only("地震以外", "地震")
    heights = train.at("車両高").only("受風高", "遠心重心高", "地震重心高")
    factors = train.at("荷重修正係数").only("使用性", "安全性(破壊)", "安全性(疲労)")
    length = train.at("1両の長さ").printed(LENGTH, sign="positive")
    a1 = spacing.at("a1_連結部").printed(LENGTH, sign="positive")
    a2 = spacing.at("a2").printed(LENGTH)
    if length.value <= a1.value + 2 * a2.value:
        raise train.at("1両の長さ").error("a1_連結部+2×a2より大きい値が必要です")
    return Train(
        vehicle=name, braking_rule=choices.VEHICLES[name], car_length=length, a1=a1, a2=a2,
        axle_load=axle.at("地震以外").printed(LOAD, sign="positive"),
        earthquake_load=axle.at("地震").printed(LINE_LOAD),
        cars=train.at("編成数").integer(1, 200),
        height_wind=heights.at("受風高").printed(LENGTH),
        height_centrifugal=heights.at("遠心重心高").printed(LENGTH),
        height_seismic=heights.at("地震重心高").printed(LENGTH),
        factor_service=factors.at("使用性").printed(RATIO, sign="positive"),  # decision 37
        factor_ultimate=factors.at("安全性(破壊)").printed(RATIO, sign="positive"),
        factor_fatigue=factors.at("安全性(疲労)").printed(RATIO, sign="positive"),
    )


BEARING_KEYS = ("支承位置", "固定死荷重_D1", "付加死荷重_D2", *SNOW_KEYS, "列車分担")


def _bearing(slot: Reader) -> Bearing | None:
    if slot.is_null:
        return None
    slot.only(*BEARING_KEYS)
    shares = slot.at("列車分担").only("L1", "L2", "L3", "L4")
    for track in ("L3", "L4"):  # decision 23: two tracks only; L3/L4 stay blank
        if not shares.at(track).is_null:
            raise shares.at(track).error("3線以上は未対応です")
    return Bearing(
        position=slot.at("支承位置").printed(LENGTH, sign="any"),
        d1=slot.at("固定死荷重_D1").printed(LOAD, sign="any"),
        d2=slot.at("付加死荷重_D2").printed(LOAD, sign="any"),
        snow2=slot.at(SNOW_KEYS[0]).printed(LOAD, sign="any"),
        snow10=slot.at(SNOW_KEYS[1]).printed(LOAD, sign="any"),
        snow30=slot.at(SNOW_KEYS[2]).printed(LOAD, sign="any"),
        shares=Shares(
            l1=shares.at("L1").printed(RATIO, sign="any"), l2=shares.at("L2").printed(RATIO, sign="any"),
        ),
    )


def _end(node: Reader) -> EndReaction:
    node.only("固定死荷重_D1", "付加死荷重_D2", *SNOW_KEYS)
    return EndReaction(*(node.at(key).printed(LOAD, sign="any")
                         for key in ("固定死荷重_D1", "付加死荷重_D2", *SNOW_KEYS)))


def _reactions(root: Reader) -> Reactions:
    reactions = root.at("上部工反力").only("起点側", "終点側")
    origin = reactions.at("起点側").only("A支点", "B支点")
    end = reactions.at("終点側").only("C支点", "D支点")

    def slots(node: Reader) -> tuple[Bearing | None, ...]:
        return tuple(_bearing(slot) for slot in node.items(minimum=BEARING_SLOTS, maximum=BEARING_SLOTS))

    return Reactions(a=_end(origin.at("A支点")), b=slots(origin.at("B支点")),
                     c=slots(end.at("C支点")), d=_end(end.at("D支点")))


LAYER_KEYS = ("層番", "層厚", "土質区分", "N値", "単位体積重量", "内部摩擦角_φd", "内部摩擦角の上限値",
              "一軸圧縮強度_qu", "変形係数_Ed")


def _layer(node: Reader, index: int) -> SoilLayer:
    node.only(*(key for key in LAYER_KEYS if index or key != "層厚"))
    weights = node.at("単位体積重量").only("湿潤", "水中")
    angle_limit = node.optional("内部摩擦角の上限値")
    layer = SoilLayer(
        name=node.at("層番").text(),
        thickness=None if index == 0 else _optional(node, "層厚", LENGTH),
        soil_type=node.at("土質区分").choice(choices.SOIL_TYPES),
        n_value=_optional(node, "N値", N_VALUE),
        unit_weight_wet=_optional(weights, "湿潤", UNIT_WEIGHT),
        unit_weight_submerged=_optional(weights, "水中", UNIT_WEIGHT),
        friction_angle=_optional(node, "内部摩擦角_φd", FRICTION_ANGLE),
        friction_angle_limit=None if angle_limit is None else angle_limit.printed(FRICTION_ANGLE),
        compressive_strength=_optional(node, "一軸圧縮強度_qu", STRESS),
        deformation_modulus=_optional(node, "変形係数_Ed", STRESS),
    )
    for key, angle in (("内部摩擦角_φd", layer.friction_angle), ("内部摩擦角の上限値", layer.friction_angle_limit)):
        if angle is not None and angle.value >= 90:
            raise node.at(key).error("90度未満が必要です")
    return layer


def _soil(root: Reader) -> Soil:
    rows = root.at("地盤データ").only("層").at("層")
    layers = tuple(_layer(node, index) for index, node in enumerate(rows.items(minimum=1, maximum=11)))
    if layers[0].name != choices.LAYER_SURFACE:
        raise rows.at(0, "層番").error(f"先頭は「{choices.LAYER_SURFACE}」としてください")
    supports = [index for index, layer in enumerate(layers) if layer.name == choices.LAYER_SUPPORT]
    if len(supports) != 1:
        raise rows.error(f"層番「{choices.LAYER_SUPPORT}」の行をちょうど1行指定してください")
    surface, support = rows.at(0), rows.at(supports[0])
    surface.at("単位体積重量", "湿潤").printed(UNIT_WEIGHT)
    surface.at("単位体積重量", "水中").printed(UNIT_WEIGHT)
    angle = support.at("内部摩擦角_φd").printed(FRICTION_ANGLE)
    if not 25 <= angle.value < 90:
        raise support.at("内部摩擦角_φd").error("25度以上90度未満が必要です（支持力係数表の適用範囲）")
    support.at("変形係数_Ed").printed(STRESS, sign="positive")
    return Soil(layers)


def _materials(root: Reader) -> Materials:
    rebar = root.at("鉄筋")
    return Materials(*(rebar.at(part, "concrete_strength_mpa").printed(STRENGTH, sign="positive")
                       for part in ("梁", "柱", "フーチング")))


def _count(node: Reader, key: str) -> int | None:
    child = node.at(key)
    return None if child.is_null else child.integer(0, 10_000)


def _reserved(root: Reader) -> Reserved:
    sub = root.at("下部構造")
    skew = sub.at("斜角").only("θ", "タイプ")
    pile_weights = sub.at("単位体積重量", "杭").only("鉛直重量", "慣性力")
    condition = sub.at("場所打ち杭の施工条件")
    piles = []
    for row in sub.at("杭の配置").items():
        row.only("線路方向", "線路直角方向")
        along = row.at("線路方向").only("X", "本数")
        across = row.at("線路直角方向").only("Y", "本数")
        piles.append(Pile(x=_optional(along, "X", LENGTH, sign="any"), x_count=_count(along, "本数"),
                          y=_optional(across, "Y", LENGTH, sign="any"), y_count=_count(across, "本数")))
    skew_type = skew.at("タイプ").integer(1, 2)
    return Reserved(
        skew_angle=skew.at("θ").printed(ANGLE, sign="positive"), skew_type=skew_type,
        pile_unit_weight_vertical=_optional(pile_weights, "鉛直重量", UNIT_WEIGHT),
        pile_unit_weight_inertia=_optional(pile_weights, "慣性力", UNIT_WEIGHT),
        cast_in_place_condition=None if condition.is_null else condition.choice(choices.CAST_IN_PLACE_CONDITIONS),
        piles=tuple(piles),
        centrifugal_direction=tuple(root.at("上部構造", side, "遠心作用方向").choice(choices.CENTRIFUGAL_DIRECTIONS)
                                    for side in ("起点側", "終点側")),
    )


def _jrsnap_conditions(root: Reader, key: str) -> JrsnapConditions:
    node = root.at(key).only("shear_factor_vcd", "shear_factor_vsd", "shear_factor_vdd", "aggregate_max_mm",
                             "analysis_steps", "limited_final_step", "target_displacement_m")
    factors = []
    for name in ("shear_factor_vcd", "shear_factor_vsd", "shear_factor_vdd"):
        factor = _optional(node, name, SHEAR_FACTOR, sign="positive")
        if factor is not None and factor.value > SHEAR_FACTOR_MAX:
            raise node.at(name).error(f"{SHEAR_FACTOR_MAX}以下が必要です")
        factors.append(factor)
    aggregate = node.at("aggregate_max_mm")
    size = None if aggregate.is_null else aggregate.printed(AGGREGATE)
    if size is not None and not AGGREGATE_RANGE[0] <= size.value <= AGGREGATE_RANGE[1]:
        raise aggregate.error(f"{AGGREGATE_RANGE[0]}～{AGGREGATE_RANGE[1]} mmが必要です")
    steps, limited = (None if node.at(name).is_null else node.at(name).integer(1, MAX_STEPS)
                      for name in ("analysis_steps", "limited_final_step"))
    if steps is not None and limited is not None and limited > steps:
        raise node.at("limited_final_step").error(f"analysis_steps（{steps}）以下が必要です")
    target = _optional(node, "target_displacement_m", LENGTH, sign="any")
    if target is not None and target.value == 0:
        raise node.at("target_displacement_m").error("0以外が必要です")
    return JrsnapConditions(*factors, aggregate_max=size, steps=steps, limited_final_step=limited,
                            target_displacement=target)


TOP_KEYS = ("schema_version", "出典", "上部工反力", "上部構造", "下部構造", "地盤データ", "鉄筋",
            "jrsnap_longitudinal", "jrsnap_transverse")


def parse_input(data: Any) -> PierInput:
    """Validate the whole input once; never mutate *data*."""
    root = Reader(data)
    root.only(*TOP_KEYS)
    root.at("schema_version").integer(SCHEMA_VERSION, SCHEMA_VERSION)
    root.at("上部構造").only("起点側", "終点側", "支承データ", "列車")
    root.at("上部構造", "支承データ").only("起点側", "終点側")
    sub = root.at("下部構造").only("寸法", "土かぶり", "水位", "斜角", "単位体積重量", "杭種",
                                   "場所打ち杭の施工条件", "杭の配置")
    foundation = sub.at("杭種").choice(choices.FOUNDATION_TYPES)
    if foundation != choices.SUPPORTED_FOUNDATION:
        raise sub.at("杭種").error(f"{foundation}は未対応です（{choices.SUPPORTED_FOUNDATION}のみ計算できます）")
    return PierInput(
        substructure=_substructure(root),
        spans=Spans(_span(root, "起点側"), _span(root, "終点側")),
        train=_train(root),
        reactions=_reactions(root),
        soil=_soil(root),
        materials=_materials(root),
        reserved=_reserved(root),
        rebar=parse_rebar(root),
        jrsnap=Jrsnap(longitudinal=_jrsnap_conditions(root, "jrsnap_longitudinal"),
                      transverse=_jrsnap_conditions(root, "jrsnap_transverse")),
    )
