"""Parse the schema 2 input JSON into PierInput (decisions 5, 6, 16-19).

Nothing is filled in: a missing value is an input error, a value finer than
the printed digits is an input error, and an unknown key is an input error.
Every scalar is read through the field table (fields.py), which the editor
uses too; this module adds the rules between fields.

With a load model (``load_model=True``, decision 70) the items that belong to the load model are not read: the
train (上部構造.列車), the impact coefficient, the curve radius, the train speed and the centrifugal direction of each
side, and the snow loads and train shares of the supports. They may be there with any value, or not be there; their
attributes are None. Every other item, and an unknown key, is read as without one.
"""

from __future__ import annotations

from typing import Any

from ..core.printed import Printed
from ..core.reader import Reader
from . import choices
from .fields import BEAM_SURFACES, LOAD, MAX_PILE_COLUMNS, REPETITION_SLOPES, SNOW_KEYS, read
from .model import (
    Bearing, CantileverCheck, CastInPlacePile, ColumnCheck, EndReaction, FatigueTrains, Jrsnap, JrsnapConditions,
    Materials, PierInput, PileFoundation, PileJoint, PileLayout, Reactions, Reserved, SeismicDesign, Shares, Soil, SoilLayer, Span,
    Spans, Substructure, SteelSoilCementPile, Train,
)
from .outputs import OUTPUT_ITEMS, OUTPUT_KEYS, PILE_OUTPUT_KEYS, foundation_makes
from .rebar import parse_rebar

SCHEMA_VERSION = 2
BEARING_SLOTS = 10


def _required(node: Reader) -> Printed:
    """A field the table lets stay blank, which this row needs."""
    value = read(node)
    if value is None:
        raise node.error("値が必要です")
    return value


def _substructure(root: Reader) -> Substructure:
    sub = root.at("下部構造")
    dims = sub.at("寸法").only("側面", "正面", "高さ")
    sized: dict[str, dict[int, Printed]] = {}
    for group, prefix, count in (("側面", "B", 9), ("正面", "W", 9), ("高さ", "H", 6)):
        node = dims.at(group).only(*(f"{prefix}{index}" for index in range(1, count + 1)))
        sized[prefix] = {index: read(node.at(f"{prefix}{index}")) for index in range(1, count + 1)}
    for prefix, group in (("B", "側面"), ("W", "正面")):
        size = sized[prefix]
        if size[1].value <= size[4].value + size[5].value:
            raise dims.at(group, f"{prefix}1").error(f"{prefix}4+{prefix}5より大きい値が必要です")
    cover = sub.at("土かぶり").only("起点側_df1", "終点側_df2")
    water = sub.at("水位").only("高水位_hw1", "平水位_hw2", "低水位_hw3")
    weights = sub.at("単位体積重量").only("梁・躯体", "フーチング", "上載土")
    return Substructure(
        b=sized["B"], w=sized["W"], h=sized["H"],
        df1=read(cover.at("起点側_df1")), df2=read(cover.at("終点側_df2")),
        hw1=read(water.at("高水位_hw1")), hw2=read(water.at("平水位_hw2")), hw3=read(water.at("低水位_hw3")),
        unit_weight_body=read(weights.at("梁・躯体")), unit_weight_footing=read(weights.at("フーチング")),
        unit_weight_overburden=read(weights.at("上載土")),
        foundation=read(sub.at("基礎形式")),
    )


# decision 59: the rubber bearings and the stoppers of each girder (0900); every value may stay blank
BEARING_DEVICE_KEYS = ("ゴム支承の箇所数", "ストッパーの箇所数", "片持ち梁上のゴム支承", "片持ち梁上のストッパー")


def _span(root: Reader, side: str, load_model: bool) -> Span:
    span = root.at("上部構造", side).only("桁長", "衝撃係数_単線終局", "曲線半径", "列車速度", "遠心作用方向",
                                        "高さ", "重心高_hs", "支承位置_f")
    lengths = span.at("桁長").only("L1", "スパン長", "L2")
    heights = span.at("高さ").only("h1", "h2", "h3", "h4")
    support = root.at("上部構造", "支承データ", side).only("支承名", "摩擦係数_μ", "復旧性制動係数", *BEARING_DEVICE_KEYS)
    brake = support.optional("復旧性制動係数")
    return Span(
        l1=read(lengths.at("L1")), span=read(lengths.at("スパン長")), l2=read(lengths.at("L2")),
        impact=None if load_model else read(span.at("衝撃係数_単線終局")),
        radius=None if load_model else read(span.at("曲線半径")),
        speed=None if load_model else read(span.at("列車速度")),
        heights={index: read(heights.at(f"h{index}")) for index in range(1, 5)},
        hs=read(span.at("重心高_hs")), f=read(span.at("支承位置_f")),
        bearing=read(support.at("支承名")), mu=read(support.at("摩擦係数_μ")),
        recovery_brake_coefficient=None if brake is None else read(brake),
        rubber_count=read(support.at(BEARING_DEVICE_KEYS[0])), stopper_count=read(support.at(BEARING_DEVICE_KEYS[1])),
        rubber_on_cantilever=read(support.at(BEARING_DEVICE_KEYS[2])),
        stopper_on_cantilever=read(support.at(BEARING_DEVICE_KEYS[3])),
    )


def _train(root: Reader) -> Train:
    train = root.at("上部構造", "列車").only("車両名", "1両の長さ", "軸距", "軸重", "編成数", "車両高", "荷重修正係数")
    vehicle = train.at("車両名")
    if not isinstance(vehicle.value, str):
        raise vehicle.error(f"{'・'.join(choices.VEHICLES)}から選んでください（入力: {vehicle.value!r}）")
    name = read(vehicle)
    spacing = train.at("軸距").only("a1_連結部", "a2")
    axle = train.at("軸重").only("地震以外", "地震")
    heights = train.at("車両高").only("受風高", "遠心重心高", "地震重心高")
    factors = train.at("荷重修正係数").only("使用性", "安全性(破壊)", "安全性(疲労)")
    length = read(train.at("1両の長さ"))
    a1, a2 = read(spacing.at("a1_連結部")), read(spacing.at("a2"))
    if length.value <= a1.value + 2 * a2.value:
        raise train.at("1両の長さ").error("a1_連結部+2×a2より大きい値が必要です")
    return Train(
        vehicle=name, braking_rule=choices.VEHICLES[name], car_length=length, a1=a1, a2=a2,
        axle_load=read(axle.at("地震以外")), earthquake_load=read(axle.at("地震")), cars=read(train.at("編成数")),
        height_wind=read(heights.at("受風高")), height_centrifugal=read(heights.at("遠心重心高")),
        height_seismic=read(heights.at("地震重心高")),
        factor_service=read(factors.at("使用性")), factor_ultimate=read(factors.at("安全性(破壊)")),
        factor_fatigue=read(factors.at("安全性(疲労)")),
    )


BEARING_KEYS = ("支承位置", "固定死荷重_D1", "付加死荷重_D2", *SNOW_KEYS, "列車分担")


def _snow(node: Reader) -> Printed:
    """Decision 62: a blank snow load is no snow, 0 kN."""
    value = read(node)
    return LOAD(0) if value is None else value


def _snows(node: Reader, load_model: bool) -> tuple[Printed | None, ...]:
    """The snow loads of a support; with a load model they are not read (decision 70)."""
    return (None,) * len(SNOW_KEYS) if load_model else tuple(_snow(node.at(key)) for key in SNOW_KEYS)


def _bearing(slot: Reader, load_model: bool) -> Bearing | None:
    if slot.is_null:  # 空き支承枠
        return None
    slot.only(*BEARING_KEYS)
    shares = None if load_model else slot.at("列車分担").only("L1", "L2", "L3", "L4")
    if shares is not None:
        for track in ("L3", "L4"):  # decision 23: two tracks only; L3/L4 stay blank
            read(shares.at(track))
    position, d1, d2 = (read(slot.at(key)) for key in ("支承位置", "固定死荷重_D1", "付加死荷重_D2"))
    snow2, snow10, snow30 = _snows(slot, load_model)
    return Bearing(
        position=position, d1=d1, d2=d2, snow2=snow2, snow10=snow10, snow30=snow30,
        shares=None if shares is None else Shares(l1=read(shares.at("L1")), l2=read(shares.at("L2"))),
    )


def _end(node: Reader, load_model: bool) -> EndReaction:
    node.only("固定死荷重_D1", "付加死荷重_D2", *SNOW_KEYS)
    return EndReaction(read(node.at("固定死荷重_D1")), read(node.at("付加死荷重_D2")), *_snows(node, load_model))


def _reactions(root: Reader, load_model: bool) -> Reactions:
    reactions = root.at("上部工反力").only("起点側", "終点側")
    origin = reactions.at("起点側").only("A支点", "B支点")
    end = reactions.at("終点側").only("C支点", "D支点")

    def slots(node: Reader) -> tuple[Bearing | None, ...]:
        return tuple(_bearing(slot, load_model) for slot in node.items(minimum=BEARING_SLOTS, maximum=BEARING_SLOTS))

    return Reactions(a=_end(origin.at("A支点"), load_model), b=slots(origin.at("B支点")),
                     c=slots(end.at("C支点")), d=_end(end.at("D支点"), load_model))


LAYER_KEYS = ("層番", "層厚", "土質区分", "N値", "単位体積重量", "内部摩擦角_φd", "内部摩擦角の上限値",
              "粘着力_c", "変形係数_Ed", "De", "せん断弾性波速度_Vs")


def _layer(node: Reader, index: int) -> SoilLayer:
    node.only(*LAYER_KEYS)
    weights = node.at("単位体積重量").only("湿潤", "水中")
    angle_limit = node.optional("内部摩擦角の上限値")
    velocity = node.optional("せん断弾性波速度_Vs")  # absent is blank: an input made before decision 97 has none
    # decision 64: 表層 may leave its thickness out (blank: the rest of Df); the layers below have the key
    thickness = node.optional("層厚") if index == 0 else node.at("層厚")
    return SoilLayer(
        name=read(node.at("層番")),
        thickness=None if thickness is None else read(thickness),
        soil_type=read(node.at("土質区分")),
        n_value=read(node.at("N値")),
        unit_weight_wet=read(weights.at("湿潤")),
        unit_weight_submerged=read(weights.at("水中")),
        friction_angle=read(node.at("内部摩擦角_φd")),
        friction_angle_limit=None if angle_limit is None else read(angle_limit),
        cohesion=read(node.at("粘着力_c")),
        deformation_modulus=read(node.at("変形係数_Ed")),
        reduction=read(node.at("De")),
        shear_wave_velocity=None if velocity is None else read(velocity),
    )


# SOIL-JR takes up to 20 layers below the bottom of the footing (the layers above it are one); a direct foundation up to 11
PILE_LAYERS = 40
DIRECT_LAYERS = 11


def _soil(root: Reader, foundation: str) -> Soil:
    """The layers from the ground surface. A direct foundation reads them as 表層 … 支持層 (decision 64); a pile foundation
    cuts them at the bottom of the footing and the tip of the pile, which the stage that needs them does (ADR-0013)."""
    rows = root.at("地盤データ").only("層").at("層")
    layers = tuple(_layer(node, index) for index, node in enumerate(rows.items(minimum=1, maximum=PILE_LAYERS if
                                                                              foundation in choices.PILE_FOUNDATIONS
                                                                              else DIRECT_LAYERS)))
    if foundation in choices.PILE_FOUNDATIONS:
        return Soil(layers)
    if layers[0].name != choices.LAYER_SURFACE:
        raise rows.at(0, "層番").error(f"先頭は「{choices.LAYER_SURFACE}」としてください")
    supports = [index for index, layer in enumerate(layers) if layer.name == choices.LAYER_SUPPORT]
    if len(supports) != 1:
        raise rows.error(f"層番「{choices.LAYER_SUPPORT}」の行をちょうど1行指定してください")
    surface, support = rows.at(0), rows.at(supports[0])
    _required(surface.at("単位体積重量", "湿潤"))
    _required(surface.at("単位体積重量", "水中"))
    for index in range(1, supports[0]):  # decision 64: the layers between 表層 and 支持層 fill Df by their thickness
        _required(rows.at(index, "層厚"))
    angle = _required(support.at("内部摩擦角_φd"))
    if not 25 <= angle.value < 90:
        raise support.at("内部摩擦角_φd").error("25度以上90度未満が必要です（支持力係数表の適用範囲）")
    modulus = support.at("変形係数_Ed")
    if _required(modulus).value <= 0:
        raise modulus.error("正の数値が必要です")
    return Soil(layers)


def _materials(root: Reader) -> Materials:
    rebar = root.at("鉄筋")
    return Materials(*(read(rebar.at(part, "concrete_strength_mpa")) for part in ("梁", "柱", "フーチング")))


def _reserved(root: Reader, load_model: bool) -> Reserved:
    sub = root.at("下部構造")
    skew = sub.at("斜角").only("θ", "タイプ")
    skew_type = read(skew.at("タイプ"))
    return Reserved(
        skew_angle=read(skew.at("θ")), skew_type=skew_type,
        centrifugal_direction=None if load_model else tuple(
            read(root.at("上部構造", side, "遠心作用方向")) for side in ("起点側", "終点側")),
    )


def _required_pile(node: Reader) -> Printed | str:
    """A value of the pile foundation the table lets stay blank, which the chosen 基礎形式 needs."""
    value = read(node)
    if value is None:
        raise node.error("値が必要です")
    return value


def _columns(node: Reader) -> tuple[Printed, ...]:
    """The positions of the columns of piles in one direction: one to 99, each larger than the one before."""
    return tuple(read(item) for item in node.items(maximum=MAX_PILE_COLUMNS))


def _layout(node: Reader) -> PileLayout:
    node.only("形式", "線路方向の列の位置", "線路直角方向の列の位置", "抜く杭")
    removed = []
    for row in node.at("抜く杭").items():
        row.only("線路方向の列", "線路直角方向の列")
        removed.append((read(row.at("線路方向の列")), read(row.at("線路直角方向の列"))))
    return PileLayout(pattern=read(node.at("形式")), along=_columns(node.at("線路方向の列の位置")),
                      across=_columns(node.at("線路直角方向の列の位置")), removed=tuple(removed))


def _pile_layout_rules(node: Reader, layout: PileLayout) -> None:
    """The rules of 杭の配置 of a pile foundation (CONTEXT.md 杭の配置, 千鳥配置): the columns are in order, a staggered
    layout has an odd number of columns each way, a pile left out is at a place that has one, and every column keeps one."""
    if layout.pattern is None:
        raise node.at("形式").error("値が必要です")
    for key, positions in (("線路方向の列の位置", layout.along), ("線路直角方向の列の位置", layout.across)):
        if not positions:
            raise node.at(key).error("1列以上の位置が必要です")
        for index in range(1, len(positions)):
            if positions[index].value <= positions[index - 1].value:
                raise node.at(key, index).error(f"前の列（{positions[index - 1].value:g} m）より大きい位置が必要です")
    along, across = len(layout.along), len(layout.across)
    staggered = layout.pattern == choices.STAGGERED
    if staggered and (along % 2 == 0 or across % 2 == 0):
        raise node.at("形式").error(f"千鳥配置は両方向とも奇数列が必要です（線路方向 {along}列、線路直角方向 {across}列）")

    def has_pile(i: int, j: int) -> bool:
        return not staggered or (i + j) % 2 == 0

    seen: set[tuple[int, int]] = set()
    for index, (i, j) in enumerate(layout.removed):
        row = node.at("抜く杭", index)
        if i > along:
            raise row.at("線路方向の列").error(f"線路方向の列は 1～{along} が必要です")
        if j > across:
            raise row.at("線路直角方向の列").error(f"線路直角方向の列は 1～{across} が必要です")
        if not has_pile(i, j):
            raise row.error("千鳥配置の杭のない位置は抜けません")
        if (i, j) in seen:
            raise row.error("同じ位置が重なっています")
        seen.add((i, j))

    def left(i: int, j: int) -> bool:
        return has_pile(i, j) and (i, j) not in seen

    for i in range(1, along + 1):
        if not any(left(i, j) for j in range(1, across + 1)):
            raise node.at("線路方向の列の位置", i - 1).error("この列の杭がすべてなくなります")
    for j in range(1, across + 1):
        if not any(left(i, j) for i in range(1, along + 1)):
            raise node.at("線路直角方向の列の位置", j - 1).error("この列の杭がすべてなくなります")


def _piles(root: Reader, foundation: str) -> PileFoundation:
    """杭基礎 (decision 80): form and digits whatever the 基礎形式; a pile foundation also needs the values of its type."""
    node = root.at("杭基礎").only("杭長", "杭の単位体積重量", "場所打ち杭", "鋼管ソイルセメント杭", "配置")
    cast = node.at("場所打ち杭").only("杭径", "f'ck", "施工条件")
    steel = node.at("鋼管ソイルセメント杭").only("ソイルセメント径", "鋼管外径", "鋼管厚", "腐食代", "鋼管材質", "結合部")
    joint = steel.at("結合部").only("軸方向鉄筋", "中詰めコンクリート_f'ck")
    bars = joint.at("軸方向鉄筋").only("径", "本数", "材質", "重心位置")
    piles = PileFoundation(
        length=read(node.at("杭長")), unit_weight=read(node.at("杭の単位体積重量")),
        cast_in_place=CastInPlacePile(diameter=read(cast.at("杭径")), fck=read(cast.at("f'ck")),
                                      condition=read(cast.at("施工条件"))),
        steel_soil_cement=SteelSoilCementPile(
            soil_cement_diameter=read(steel.at("ソイルセメント径")), steel_diameter=read(steel.at("鋼管外径")),
            thickness=read(steel.at("鋼管厚")), corrosion=read(steel.at("腐食代")),
            grade=read(steel.at("鋼管材質")),
            joint=PileJoint(bar_diameter=read(bars.at("径")), bar_count=read(bars.at("本数")), bar_grade=read(bars.at("材質")),
                            bar_centroid=read(bars.at("重心位置")), fill_fck=read(joint.at("中詰めコンクリート_f'ck")))),
        layout=_layout(node.at("配置")))
    if foundation not in choices.PILE_FOUNDATIONS:
        return piles
    _required_pile(node.at("杭長"))
    _required_pile(node.at("杭の単位体積重量"))
    if foundation == choices.CAST_IN_PLACE_PILE:
        for key in ("杭径", "f'ck", "施工条件"):
            _required_pile(cast.at(key))
    else:
        sizes = {key: _required_pile(steel.at(key)) for key in ("ソイルセメント径", "鋼管外径", "鋼管厚", "腐食代")}
        if sizes["ソイルセメント径"].value <= sizes["鋼管外径"].value:
            raise steel.at("ソイルセメント径").error("鋼管外径より大きい値が必要です")
        if sizes["鋼管厚"].value >= sizes["鋼管外径"].value * 500:
            raise steel.at("鋼管厚").error("鋼管外径の半分より小さい値が必要です")
        if sizes["腐食代"].value > sizes["鋼管厚"].value:
            raise steel.at("腐食代").error("鋼管厚（腐食代を含む）以下が必要です")
    _pile_layout_rules(node.at("配置"), piles.layout)
    return piles


JRSNAP_KEYS = ("shear_factor_vcd", "shear_factor_vsd", "shear_factor_vdd", "analysis_steps",
               "limited_final_step", "target_displacement_m")


def _jrsnap_conditions(root: Reader, key: str) -> JrsnapConditions:
    node = root.at(key).only(*JRSNAP_KEYS)
    vcd, vsd, vdd, steps, limited, target = (read(node.at(name)) for name in JRSNAP_KEYS)
    if steps is not None and limited is not None and limited > steps:
        raise node.at("limited_final_step").error(f"analysis_steps（{steps}）以下が必要です")
    return JrsnapConditions(vcd, vsd, vdd, steps=steps, limited_final_step=limited,
                            target_displacement=target)


def _seismic_design(root: Reader) -> SeismicDesign:
    node = root.at("耐震設計条件").only("地域別", "地盤区分", "液状化指数")
    index = node.optional("液状化指数")  # absent is blank: an input made before decision 95 has none
    return SeismicDesign(region=read(node.at("地域別")), ground_class=read(node.at("地盤区分")),
                         liquefaction_index=None if index is None else read(index))


COLUMN_CHECK_KEYS = ("水掛かりの程度", "外観の照査", "ε'csd", "適用基準の機関", "JR-001", "JR-004")


def _column_check(root: Reader) -> ColumnCheck:
    node = root.at("柱の断面照査").only(*COLUMN_CHECK_KEYS)
    environment, appearance, ecsd, body, jr001, jr004 = (read(node.at(name)) for name in COLUMN_CHECK_KEYS)
    return ColumnCheck(environment=environment, appearance=appearance, ecsd=ecsd, body=body, jr001=jr001,
                       jr004=jr004)


CANTILEVER_CHECK = "片持ち梁の照査"
FATIGUE_KEYS = ("旅客列車本数", "貨物列車本数", "設計耐用年数", "等価繰返し回数")


def _cantilever_check(root: Reader) -> CantileverCheck:
    node = root.at(CANTILEVER_CHECK).only("水掛かりの程度", "外観の照査", "疲労")
    environments = node.at("水掛かりの程度").only(*BEAM_SURFACES)
    fatigue = node.at("疲労").only(*FATIGUE_KEYS)
    repetitions = fatigue.at("等価繰返し回数").only("A列車", "B列車")
    counts = {}
    for train in ("A列車", "B列車"):
        slopes = repetitions.at(train).only(*REPETITION_SLOPES)
        counts |= {(train, slope): read(slopes.at(slope)) for slope in REPETITION_SLOPES}
    return CantileverCheck(
        environments={face: read(environments.at(face)) for face in BEAM_SURFACES},
        appearance=read(node.at("外観の照査")),
        fatigue=FatigueTrains(passenger_trains=read(fatigue.at("旅客列車本数")),
                              freight_trains=read(fatigue.at("貨物列車本数")),
                              service_life=read(fatigue.at("設計耐用年数")), repetitions=counts))


def _outputs(root: Reader, foundation: str) -> tuple[str, ...]:
    """The chosen 出力項目 (decision 72): at least one, each with every item it uses; a pile foundation makes only the
    items it can so far (PILE_OUTPUT_KEYS), and each other chosen item is an input error at its own path."""
    node = root.at("outputs").only(*OUTPUT_KEYS)
    chosen = tuple(key for key in OUTPUT_KEYS if read(node.at(key)))
    for key in chosen:
        if not foundation_makes(foundation, key):
            available = "・".join(PILE_OUTPUT_KEYS) or "なし"
            raise node.at(key).error(f"{foundation}は未対応です（{foundation}で選べる出力項目: {available}）")
    for item in OUTPUT_ITEMS:
        if item.key in chosen and (missing := [key for key in item.requires if key not in chosen]):
            raise node.at(item.key).error(f"{'・'.join(f'outputs.{key}' for key in missing)} も true が必要です")
    if not chosen:
        raise node.error("出力項目が選ばれていません（どれかを true にしてください）")
    return chosen


TOP_KEYS = ("schema_version", "出典", "上部工反力", "上部構造", "下部構造", "杭基礎", "地盤データ", "鉄筋", "耐震設計条件", "柱の断面照査",
            CANTILEVER_CHECK, "jrsnap_longitudinal", "jrsnap_transverse", "outputs")


SPAN_LOAD_MODEL_KEYS = ("衝撃係数_単線終局", "曲線半径", "列車速度", "遠心作用方向")


def load_model_item(pattern: str) -> bool:
    """Whether the field *pattern* (fields.FIELDS) belongs to the load model: not read with one (decision 70)."""
    parts = pattern.split(".")
    if parts[0] == "上部構造":
        return parts[1] == "列車" or parts[-1] in SPAN_LOAD_MODEL_KEYS
    return parts[0] == "上部工反力" and (parts[-1] in SNOW_KEYS or "列車分担" in parts)


def parse_input(data: Any, *, load_model: bool = False) -> PierInput:
    """Validate the whole input once; never mutate *data*. With *load_model* the items of the load model are not read
    (decision 70)."""
    root = Reader(data)
    root.only(*TOP_KEYS)
    root.at("schema_version").integer(SCHEMA_VERSION, SCHEMA_VERSION)
    root.at("上部構造").only("起点側", "終点側", "支承データ", "列車")
    root.at("上部構造", "支承データ").only("起点側", "終点側")
    sub = root.at("下部構造").only("寸法", "土かぶり", "水位", "斜角", "単位体積重量", "基礎形式")
    foundation = read(sub.at("基礎形式"))
    return PierInput(
        substructure=_substructure(root),
        spans=Spans(_span(root, "起点側", load_model), _span(root, "終点側", load_model)),
        train=None if load_model else _train(root),
        reactions=_reactions(root, load_model),
        soil=_soil(root, foundation),
        materials=_materials(root),
        reserved=_reserved(root, load_model),
        piles=_piles(root, foundation),
        rebar=parse_rebar(root),
        seismic_design=_seismic_design(root),
        column_check=_column_check(root),
        cantilever_check=_cantilever_check(root),
        jrsnap=Jrsnap(longitudinal=_jrsnap_conditions(root, "jrsnap_longitudinal"),
                      transverse=_jrsnap_conditions(root, "jrsnap_transverse")),
        outputs=_outputs(root, foundation),
    )
