"""Read the existing Japanese input.json without depending on Excel."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .input_formulas import B9_PATH, FORMULAS_BY_PATH, SURFACE_THICKNESS_PATH, FormulaError


class InputError(ValueError):
    """An input cannot be interpreted by the direct-foundation calculation."""


def _get(value: Any, *keys: str) -> Any:
    traversed: list[str] = []
    for key in keys:
        traversed.append(key)
        if not isinstance(value, dict) or key not in value:
            raise InputError(f"入力項目がありません: {'.'.join(traversed)}")
        value = value[key]
    return value


def _number(value: Any, label: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{label}: 有限の数値が必要です（入力: {value!r}）")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise InputError(f"{label}: 数値が大きすぎます") from exc
    if not math.isfinite(result) or result < 0:
        raise InputError(f"{label}: 0以上の有限の数値が必要です")
    return result


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{label}: 空でない文字列が必要です")
    return value


def validate_support_friction_angle(value: Any) -> float:
    """Require an angle covered by the supplied flat-ground bearing table."""
    angle = _number(value, "支持層の内部摩擦角_φd")
    if angle < 25 or angle >= 90:
        raise InputError("支持層の内部摩擦角_φdは25度以上90度未満が必要です（支持力係数表の適用範囲）")
    return angle


@dataclass(frozen=True)
class Layer:
    name: str
    thickness: float | None
    soil_type: str
    n_value: float | None
    unit_weight_wet: float | None
    unit_weight_submerged: float | None
    friction_angle: float | None
    friction_angle_limit: float | None
    compressive_strength: float | None
    deformation_modulus: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DesignInput:
    b_parts: tuple[float, float, float]
    l_parts: tuple[float, float, float]
    layers: tuple[Layer, ...]
    warnings: tuple[str, ...] = ()


def parse_input(data: Any) -> DesignInput:
    """Validate only the fields used by the original 0500 calculation.

    The first ground row's thickness is an Excel formula (H6+H5+min(df1,df2)),
    so recompute it rather than reusing the PDF transcription's cached value.
    The other bridge/load sections belong to the later 0600/0610/0620 stages.
    """
    version = _get(data, "schema_version")
    if type(version) is not int or version != 1:
        raise InputError("schema_version は整数の1に対応しています")
    sub = _get(data, "下部構造")
    foundation_type = _get(sub, "杭種", "選択値")
    if foundation_type != "直接基礎":
        raise InputError(f"対応する基礎形式は直接基礎です（入力: {foundation_type!r}）")

    dims = _get(sub, "寸法")
    b7 = _number(_get(dims, "側面", "B7"), "B7")
    b8 = _number(_get(dims, "側面", "B8"), "B8")
    # Explicit B9 permits asymmetric footings; missing/null uses the workbook default.
    raw_b9 = _get(dims, "側面").get("B9")
    b9 = (FORMULAS_BY_PATH[B9_PATH].evaluate(lambda path: b7) if raw_b9 is None
          else _number(raw_b9, "下部構造.寸法.側面.B9"))
    b_parts = (b7, b8, b9)
    l_parts = tuple(_number(_get(dims, "正面", f"W{i}"), f"W{i}") for i in (7, 8, 9))
    if sum(b_parts) <= 0 or sum(l_parts) <= 0:
        raise InputError("基礎幅 B7+B8+B9 と W7+W8+W9 は正の値が必要です")
    h5 = _number(_get(dims, "高さ", "H5"), "H5")
    h6 = _number(_get(dims, "高さ", "H6"), "H6")
    df1 = _number(_get(sub, "土かぶり", "起点側_df1"), "起点側_df1")
    df2 = _number(_get(sub, "土かぶり", "終点側_df2"), "終点側_df2")
    surface_formula = FORMULAS_BY_PATH[SURFACE_THICKNESS_PATH]
    source_values = dict(zip(surface_formula.dependencies, (h6, h5, df1, df2)))
    try:
        surface_thickness = surface_formula.evaluate(source_values.__getitem__)
    except FormulaError as exc:
        raise InputError(str(exc)) from exc

    raw_layers = _get(data, "地盤データ", "層")
    if not isinstance(raw_layers, list) or not 1 <= len(raw_layers) <= 11:
        raise InputError("地盤データ.層 は1～11層の配列が必要です")
    layers: list[Layer] = []
    for index, raw in enumerate(raw_layers):
        label = f"地盤データ.層[{index}]"

        def optional(key: str) -> float | None:
            return _number(_get(raw, key), f"{label}.{key}", optional=True)

        weights = _get(raw, "単位体積重量")
        layer = Layer(
            name=_text(_get(raw, "層番"), f"{label}.層番"),
            thickness=surface_thickness if index == 0 else optional("層厚"),
            soil_type=_text(_get(raw, "土質区分"), f"{label}.土質区分"),
            n_value=optional("N値"),
            unit_weight_wet=_number(_get(weights, "湿潤"), f"{label}.湿潤", optional=True),
            unit_weight_submerged=_number(_get(weights, "水中"), f"{label}.水中", optional=True),
            friction_angle=optional("内部摩擦角_φd"),
            friction_angle_limit=_number(raw.get("内部摩擦角の上限値"), f"{label}.内部摩擦角の上限値", optional=True),
            compressive_strength=optional("一軸圧縮強度_qu"),
            deformation_modulus=optional("変形係数_Ed"),
        )
        for angle in (layer.friction_angle, layer.friction_angle_limit):
            if angle is not None and angle >= 90:
                raise InputError(f"{label}: 内部摩擦角は90度未満が必要です")
        layers.append(layer)

    supports = [layer for layer in layers if layer.name == "支持層"]
    if len(supports) != 1:
        raise InputError("層番が「支持層」の行をちょうど1行指定してください")
    if supports[0].deformation_modulus is None or supports[0].deformation_modulus <= 0:
        raise InputError("支持層の変形係数_Edは正の数値が必要です")
    validate_support_friction_angle(supports[0].friction_angle)
    if layers[0].name != "表層":
        raise InputError("先頭の層番は「表層」としてください（元ブックF5の層厚計算対象）")

    warnings: list[str] = []
    cached_thickness = raw_layers[0].get("層厚")
    if cached_thickness != surface_thickness:
        try:
            cached_label = float(cached_thickness) if type(cached_thickness) in (int, float) else "旧値"
        except (OverflowError, ValueError):
            cached_label = "旧値"
        warnings.append(
            f"表層厚はH6+H5+min(df1,df2)で再計算しました: "
            f"入力{cached_label!r} → {surface_thickness} m"
        )
    return DesignInput(b_parts, l_parts, tuple(layers), tuple(warnings))


def load_input(path: str | Path) -> DesignInput:
    try:
        with Path(path).open(encoding="utf-8-sig") as stream:
            data = json.load(stream)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"JSONを読み込めません: {exc}") from exc
    return parse_input(data)
