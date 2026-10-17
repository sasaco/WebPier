"""Ground springs from 0500_直接基礎.xls and tabulated bearing factors.

The order of rounding is material: Av/Bv (3 decimals), kv/ks (integers),
Iv (6 decimals), and then the spring constants (integers).
Gravel uses the sand equation; bearing factors follow 解説表13.2.2.3-2.
"""

from __future__ import annotations

import math
import struct
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .inputs import DesignInput, InputError, validate_support_friction_angle


# AK37/AK38 and I37:I39, with gravel classified as sand.
_SOIL_SPRING_PARAMETERS: dict[str, tuple[float, float]] = {
    "砂質土": (6.9, -0.5),
    "砂礫": (6.9, -0.5),
    "粘性土": (3.8, -1.0),
}


# 解説表13.2.2.3-2「地表面が平坦な場合の支持力係数」: φ, Nγ, Nq.
# The last row applies to all φ >= 42°; intermediate angles use linear interpolation.
_BEARING_FACTOR_TABLE = (
    (25, 3.6, 4.8), (26, 4.0, 5.2), (27, 4.5, 5.6),
    (28, 5.0, 6.1), (29, 6.2, 7.1), (30, 7.7, 8.3),
    (31, 9.7, 9.8), (32, 12, 11), (33, 15, 14),
    (34, 20, 17), (35, 26, 20), (36, 34, 25),
    (37, 45, 31), (38, 60, 39), (39, 80, 50),
    (40, 100, 64), (41, 130, 73), (42, 150, 85),
)


def bearing_factors(friction_angle: float | None) -> tuple[float, float]:
    """Interpolate the supplied flat-ground table without extrapolating below 25°."""
    phi = validate_support_friction_angle(friction_angle)
    if phi >= _BEARING_FACTOR_TABLE[-1][0]:
        return _BEARING_FACTOR_TABLE[-1][1:]
    lower_index = math.floor(phi) - _BEARING_FACTOR_TABLE[0][0]
    lower_phi, lower_gamma, lower_q = _BEARING_FACTOR_TABLE[lower_index]
    upper_phi, upper_gamma, upper_q = _BEARING_FACTOR_TABLE[lower_index + 1]
    fraction = (phi - lower_phi) / (upper_phi - lower_phi)
    return (
        lower_gamma + (upper_gamma - lower_gamma) * fraction,
        lower_q + (upper_q - lower_q) * fraction,
    )


def excel_round(value: float, places: int = 0) -> float | int:
    """ROUND with ties away from zero, unlike Python's built-in round."""
    rounded = Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return int(rounded) if places == 0 else float(rounded)


def vba_single(value: float) -> float:
    """The VBA macro assigns B/L and outgoing spring values to Single."""
    try:
        result = struct.unpack("<f", struct.pack("<f", value))[0]
    except (OverflowError, struct.error) as exc:
        raise InputError("入力または計算結果がVBA Singleの範囲を超えています") from exc
    if not math.isfinite(result):
        raise InputError("入力または計算結果がVBA Singleの範囲を超えています")
    return result


def _single_sum(values: tuple[float, ...]) -> float:
    total = 0.0
    for value in values:
        total = vba_single(total + value)
    return total


def calculate(inputs: DesignInput) -> dict[str, Any]:
    try:
        return _calculate(inputs)
    except InputError:
        raise
    except (ArithmeticError, ValueError) as exc:
        raise InputError("入力が大きすぎるため、ばね値を計算できません") from exc


def _calculate(inputs: DesignInput) -> dict[str, Any]:
    b, length = _single_sum(inputs.b_parts), _single_sum(inputs.l_parts)
    area = excel_round(b * length, 3)  # AC46
    width = excel_round(math.sqrt(area), 3)  # AC45
    if area <= 0 or width <= 0:
        raise InputError("基礎面積または換算幅が丸め後に0になっています")
    inertia_l = excel_round(length * b**3 / 12, 6)  # S110
    inertia_t = excel_round(b * length**3 / 12, 6)  # S121
    support = next(layer for layer in inputs.layers if layer.name == "支持層")
    modulus = support.deformation_modulus
    n_gamma, n_q = bearing_factors(support.friction_angle)
    coefficient, exponent = _SOIL_SPRING_PARAMETERS.get(support.soil_type, (5.1, -0.75))
    warnings = list(inputs.warnings)
    if support.soil_type not in _SOIL_SPRING_PARAMETERS:
        warnings.append(
            f"支持層「{support.soil_type}」は元Excelのその他分岐に従い、"
            "係数5.1・指数-3/4を使用しています"
        )

    def period(rho: float) -> dict[str, int]:
        kv = excel_round(coefficient * rho * modulus * width**exponent)
        ks = excel_round((1 / 3) * kv)
        return {
            "kv": kv,
            "Kv": excel_round(kv * area),
            "ks": ks,
            "Ks": excel_round(ks * area),
            "Kr_longitudinal": excel_round(kv * inertia_l),
            "Kr_transverse": excel_round(kv * inertia_t),
        }

    try:
        long_term, short_term = period(0.5), period(1.0)
    except (ArithmeticError, ValueError) as exc:
        raise InputError("入力が大きすぎるため、ばね値を計算できません") from exc
    # The macro's Kr named range points to U124/U127 (transverse), not U113/U116.
    handoff = {
        term: {"Kv": vba_single(values["Kv"]), "Ks": vba_single(values["Ks"]),
               "Kr": vba_single(values["Kr_transverse"])}
        for term, values in (("long_term", long_term), ("short_term", short_term))
    }
    return {
        "schema_version": 1,
        "foundation": {
            "B": b, "L": length, "area": area, "equivalent_width": width,
            "inertia_longitudinal": inertia_l, "inertia_transverse": inertia_t,
        },
        "layers": [layer.to_dict() for layer in inputs.layers],
        "support_layer": support.to_dict(),
        "model": {
            "coefficient": coefficient, "exponent": exponent,
            "rho_long_term": 0.5, "rho_short_term": 1.0, "shear_ratio": 1 / 3,
            "bearing_n_gamma": n_gamma, "bearing_n_q": n_q,
        },
        "long_term": long_term,
        "short_term": short_term,
        "macro_handoff_single": handoff,
        "units": {"length": "m", "area": "m²", "inertia": "m⁴", "Ed": "kN/m²",
                  "kv": "kN/m³", "ks": "kN/m³", "Kv": "kN/m", "Ks": "kN/m",
                  "Kr_longitudinal": "kN·m/rad", "Kr_transverse": "kN·m/rad"},
        "provenance": {
            "macro": ".claude/docs/Example橋脚/pre/input.xls!直接基礎計算.計算",
            "workbook": ".claude/docs/Example橋脚/0500_直接基礎.xls",
            "sheet": "支持層",
            "bearing_factors": (
                "解説表13.2.2.3-2「地表面が平坦な場合の支持力係数」。"
                "支持層の内部摩擦角_φdから線形補間、42度以上はNγ=150・Nq=85、25度未満は適用外。"
                "地震時を除く・地震時に同じ係数を使用。"
            ),
            "constants": (
                "I37:I39, L48, L51, Q76, Q110, Q121の保存値を移植。"
                "砂礫は砂質土に分類し、係数6.9・指数-1/2を使用。"
            ),
            "surface_thickness": "input.xls 地盤データ!F5 = H6+H5+MIN(df1,df2)",
            "rounding": "Excel ROUND（中間値も同じ桁数で丸める）。B/LはVBA Singleで逐次加算。",
        },
        "warnings": warnings,
    }
