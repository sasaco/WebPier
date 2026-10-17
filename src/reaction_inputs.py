"""Validated, immutable input for the Excel-independent 0600 calculation.

B/C cached totals are ignored. A/D end reactions use explicit dead-load inputs,
falling back to the B/C bearing totals for missing or blank inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, cast

from .inputs import InputError
from .input_formulas import DISPLACED_SOIL_PATH, FORMULAS_BY_PATH, InputPath, FormulaError, support_position_value


SNOW_LOAD_CASES: tuple[tuple[str, str], ...] = (
    ("雪荷重_2年確率", "雪荷重 2年確率"),
    ("雪荷重_10年確率", "雪荷重 10年確率"),
    ("雪荷重_30年確率", "雪荷重 30年確率"),
)
SnowValues = tuple[float, float, float]
SnowEndValues = tuple[float | None, float | None, float | None]


@dataclass(frozen=True)
class ReactionGeometry:
    b1: float
    b2: float
    b3: float
    b4: float
    b5: float
    b6: float
    b7: float
    b8: float
    b9: float
    w1: float
    w2: float
    w3: float
    w4: float
    w5: float
    w6: float
    w7: float
    w8: float
    w9: float
    h1: float
    h2: float
    h3: float
    h4: float
    h5: float
    h6: float
    df1: float
    df2: float
    hw1: float
    hw2: float
    hw3: float
    unit_weight_body: float
    unit_weight_footing: float
    unit_weight_soil: float
    unit_weight_displaced_soil: float


@dataclass(frozen=True)
class SpanInput:
    l1: float
    span: float
    l2: float
    impact: float
    radius: float
    speed: float
    h1: float
    h2: float
    h3: float
    h4: float
    hs: float
    f: float
    bearing: str
    mu: float
    recovery_brake_coefficient: float | None = None


@dataclass(frozen=True)
class ReactionSpans:
    b: SpanInput
    c: SpanInput


@dataclass(frozen=True)
class TrainInput:
    length: float
    a1: float
    a2: float
    axle_load: float
    earthquake_load: float
    n: int
    height_wind: float
    height_centrifugal: float
    height_seismic: float
    factors_service: float
    factors_ultimate: float
    factors_fatigue: float
    name: str = "EA-17"


@dataclass(frozen=True)
class BearingReaction:
    position: float | None
    d1: float
    d2: float
    # L1, L2, L3, L4, in that order. Only the first two enter 0600.
    factors: tuple[float, float, float, float]


@dataclass(frozen=True)
class EndReaction:
    d1: float
    d2: float


@dataclass(frozen=True)
class DeadReactions:
    b: tuple[BearingReaction, ...]
    c: tuple[BearingReaction, ...]
    a: EndReaction
    d: EndReaction


@dataclass(frozen=True)
class SnowReactions:
    """Separate snow inputs, with values ordered exactly as SNOW_LOAD_CASES.

    An unset A/D value remains None until the matching B/C total is known.
    The defaults keep existing ReactionInput constructor calls compatible.
    """

    b: tuple[SnowValues, ...] = ((0.0, 0.0, 0.0),) * 10
    c: tuple[SnowValues, ...] = ((0.0, 0.0, 0.0),) * 10
    a: SnowEndValues = (None, None, None)
    d: SnowEndValues = (None, None, None)


@dataclass(frozen=True)
class ReactionInput:
    geometry: ReactionGeometry
    spans: ReactionSpans
    train: TrainInput
    dead: DeadReactions
    warnings: tuple[str, ...] = ()
    snow: SnowReactions = SnowReactions()


class _Reader:
    """Keep a full Japanese path on every validation failure."""

    def __init__(self, value: Any, path: str = "") -> None:
        self.value = value
        self.path = path

    def at(self, *keys: str) -> _Reader:
        current = self
        for key in keys:
            path = f"{current.path}.{key}" if current.path else key
            if not isinstance(current.value, dict) or key not in current.value:
                raise InputError(f"入力項目がありません: {path}")
            current = _Reader(current.value[key], path)
        return current

    def number(self, *, positive: bool = False, signed: bool = False,
               null_zero: bool = False) -> float:
        value = self.value
        if value is None and null_zero:
            return 0.0
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InputError(f"{self.path}: 有限の数値が必要です（入力: {value!r}）")
        try:
            result = float(value)
        except (OverflowError, ValueError) as exc:
            raise InputError(f"{self.path}: 数値が大きすぎます") from exc
        if not math.isfinite(result):
            raise InputError(f"{self.path}: 有限の数値が必要です")
        if positive and result <= 0:
            raise InputError(f"{self.path}: 正の数値が必要です")
        if not signed and result < 0:
            raise InputError(f"{self.path}: 0以上の数値が必要です")
        return result

    def formula(self, path: InputPath, *, signed_sources: bool = False) -> float:
        def source(source_path: InputPath) -> float:
            current = self
            for key in source_path:
                if isinstance(key, int):
                    if not isinstance(current.value, list) or not 0 <= key < len(current.value):
                        raise InputError(f"入力項目がありません: {current.path}[{key}]")
                    current = _Reader(current.value[key], f"{current.path}[{key}]")
                else:
                    current = current.at(key)
            return current.number(signed=signed_sources, null_zero=True)

        try:
            return FORMULAS_BY_PATH[path].evaluate(source)
        except FormulaError as exc:
            raise InputError(str(exc)) from exc


def _geometry(root: _Reader) -> ReactionGeometry:
    sub = root.at("下部構造")
    dims = sub.at("寸法")
    numbers: dict[str, float] = {}
    for group, prefix, count, positive in (
        ("側面", "B", 9, {1, 6, 8}),
        ("正面", "W", 9, {1, 6, 8}),
        ("高さ", "H", 6, {4, 6}),
    ):
        for i in range(1, count + 1):
            # Keep explicit asymmetric B9, including zero; default only missing/null.
            if prefix == "B" and i == 9 and dims.at(group).value.get("B9") is None:
                numbers["b9"] = root.formula(("下部構造", "寸法", "側面", "B9"))
                continue
            numbers[f"{prefix.lower()}{i}"] = dims.at(group, f"{prefix}{i}").number(positive=i in positive)
    for prefix, group in (("b", "側面"), ("w", "正面")):
        if numbers[f"{prefix}1"] <= numbers[f"{prefix}4"] + numbers[f"{prefix}5"]:
            p = prefix.upper()
            raise InputError(f"下部構造.寸法.{group}.{p}1: {p}4+{p}5より大きい値が必要です")
    weights = sub.at("単位体積重量")
    return ReactionGeometry(
        **numbers,
        df1=sub.at("土かぶり", "起点側_df1").number(),
        df2=sub.at("土かぶり", "終点側_df2").number(),
        hw1=sub.at("水位", "高水位_hw1").number(signed=True),
        hw2=sub.at("水位", "平水位_hw2").number(signed=True),
        hw3=sub.at("水位", "低水位_hw3").number(signed=True),
        unit_weight_body=weights.at("梁・躯体").number(),
        unit_weight_footing=weights.at("フーチング").number(),
        unit_weight_soil=weights.at("土", "上載土").number(),
        unit_weight_displaced_soil=root.formula(DISPLACED_SOIL_PATH),
    )


def _span(root: _Reader, side: str) -> SpanInput:
    structure = root.at("上部構造")
    span = structure.at(side)
    support = structure.at("支承データ", side)
    bearing = support.at("支承名")
    if bearing.value not in ("固定", "可動"):
        raise InputError(f"{bearing.path}: 固定または可動を指定してください")
    recovery_brake = support.value.get("復旧性制動係数")
    return SpanInput(
        l1=span.at("桁長", "L1").number(),
        span=span.at("桁長", "スパン長").number(positive=True),
        l2=span.at("桁長", "L2").number(),
        impact=span.at("衝撃係数", "単線終局").number(),
        radius=span.at("遠心", "曲線半径").number(),
        speed=span.at("遠心", "列車速度").number(),
        h1=span.at("高さ", "h1").number(),
        h2=span.at("高さ", "h2").number(),
        h3=span.at("高さ", "h3").number(),
        h4=span.at("高さ", "h4").number(),
        hs=span.at("重心高_hs").number(),
        f=_support_position(root, side),
        bearing=bearing.value,
        mu=support.at("摩擦係数_μ").number(),
        recovery_brake_coefficient=(None if recovery_brake is None
                                    else support.at("復旧性制動係数").number()),
    )


def _support_position(root: _Reader, side: str) -> float:
    def optional(path: InputPath) -> Any:
        current = root.value
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        return current

    try:
        return support_position_value(optional, side)
    except FormulaError as exc:
        raise InputError(str(exc)) from exc


def _train(root: _Reader) -> TrainInput:
    train = root.at("上部構造", "列車")
    n = train.at("編成数")
    name = train.value.get("車両名")
    if name is None:
        name = ""
    elif not isinstance(name, str):
        raise InputError("上部構造.列車.車両名: 文字列が必要です")
    if type(n.value) is not int or not 1 <= n.value <= 200:
        raise InputError(f"{n.path}: 1～200の整数が必要です")
    length = train.at("1両の長さ", "値").number(positive=True)
    a1 = train.at("軸距", "a1_連結部").number(positive=True)
    a2 = train.at("軸距", "a2").number()
    if length <= a1 + 2 * a2:
        raise InputError("上部構造.列車.1両の長さ: a1_連結部+2*a2より大きい値が必要です")
    return TrainInput(
        length=length, a1=a1, a2=a2,
        axle_load=train.at("軸重", "地震以外", "値").number(positive=True),
        earthquake_load=train.at("軸重", "地震", "値").number(),
        n=n.value,
        height_wind=train.at("車両高", "受風高").number(),
        height_centrifugal=train.at("車両高", "遠心重心高").number(),
        height_seismic=train.at("車両高", "地震重心高").number(),
        factors_service=train.at("荷重修正係数", "使用性").number(),
        factors_ultimate=train.at("荷重修正係数", "安全性(破壊)").number(),
        factors_fatigue=train.at("荷重修正係数", "安全性(疲労)").number(),
        name=name,
    )


def _bearings(root: _Reader, side: str, point: str) -> tuple[BearingReaction, ...]:
    rows = root.at("上部工反力", side, point, "支承")
    if not isinstance(rows.value, list) or len(rows.value) != 10:
        raise InputError(f"{rows.path}: 10支承の配列が必要です（空支承はnullを指定）")
    result = []
    for index, value in enumerate(rows.value):
        row = _Reader(value, f"{rows.path}[{index}]")
        position = row.at("支承位置")
        position_value = None if position.value is None else position.number(signed=True)
        result.append(BearingReaction(
            position=position_value,
            d1=row.at("固定死荷重_D1").number(null_zero=True),
            d2=row.at("付加死荷重_D2").number(null_zero=True),
            factors=tuple(row.at("列車分担", f"L{i}").number(signed=True, null_zero=True) for i in range(1, 5)),
        ))
    return tuple(result)


def _end(root: _Reader, side: str, point: str,
         rows: tuple[BearingReaction, ...]) -> EndReaction:
    parent = root.at("上部工反力", side)
    end = _Reader(parent.value.get(point, {}), f"{parent.path}.{point}")
    if not isinstance(end.value, dict):
        raise InputError(f"{end.path}: オブジェクトが必要です")
    total = _Reader(end.value.get("合計", {}), f"{end.path}.合計")
    if not isinstance(total.value, dict):
        raise InputError(f"{total.path}: オブジェクトが必要です")
    values = []
    for key, fallback in (("固定死荷重_D1", sum(row.d1 for row in rows)),
                          ("付加死荷重_D2", sum(row.d2 for row in rows))):
        value = total.value.get(key)
        values.append(fallback if value is None else total.at(key).number(signed=True))
    return EndReaction(*values)


def _snow_bearings(root: _Reader, side: str, point: str) -> tuple[SnowValues, ...]:
    # The existing bearing parser validates the required parents and 10 rows.
    rows = root.at("上部工反力", side, point, "支承")
    return tuple(
        cast(SnowValues, tuple(
            _Reader(value.get(key), f"{rows.path}[{index}].{key}").number(null_zero=True)
            for key, _ in SNOW_LOAD_CASES
        ))
        for index, value in enumerate(rows.value)
    )


def _snow_end(root: _Reader, side: str, point: str) -> SnowEndValues:
    # _end validates the optional end point and total object before this call.
    parent = root.at("上部工反力", side)
    total = parent.value.get(point, {}).get("合計", {})
    path = f"{parent.path}.{point}.合計"
    return cast(SnowEndValues, tuple(
        None if total.get(key) is None else _Reader(total[key], f"{path}.{key}").number(signed=True)
        for key, _ in SNOW_LOAD_CASES
    ))


def parse_reaction_input(data: Any) -> ReactionInput:
    """Read only the schema fields consumed by 0600; never mutate *data*."""
    root = _Reader(data)
    version = root.at("schema_version")
    if type(version.value) is not int or version.value != 1:
        raise InputError("schema_version: 整数の1に対応しています")
    foundation = root.at("下部構造", "杭種", "選択値")
    if foundation.value != "直接基礎":
        raise InputError(f"{foundation.path}: 対応する基礎形式は直接基礎です")
    geometry = _geometry(root)
    spans = ReactionSpans(_span(root, "起点側"), _span(root, "終点側"))
    train = _train(root)
    b = _bearings(root, "起点側", "B支点")
    c = _bearings(root, "終点側", "C支点")
    dead = DeadReactions(b=b, c=c, a=_end(root, "起点側", "A支点", b),
                         d=_end(root, "終点側", "D支点", c))
    snow = SnowReactions(
        b=_snow_bearings(root, "起点側", "B支点"),
        c=_snow_bearings(root, "終点側", "C支点"),
        a=_snow_end(root, "起点側", "A支点"),
        d=_snow_end(root, "終点側", "D支点"),
    )
    warnings = ["B・C支点の合計は支承明細から再計算します。A・D支点の死荷重は入力値を使用し、未入力の項目は A＝B、D＝C とします。"]
    if any(any(row.factors[2:]) for row in (*dead.b, *dead.c)):
        warnings.append("列車分担L3・L4は保持しますが0600では使用しません。複線の分担はL1・L2のみです。")
    return ReactionInput(geometry, spans, train, dead, tuple(warnings), snow)


def load_reaction_input(path: str | Path) -> ReactionInput:
    try:
        with Path(path).open(encoding="utf-8-sig") as stream:
            data = json.load(stream)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"JSONを読み込めません: {path}: {exc}") from exc
    return parse_reaction_input(data)
