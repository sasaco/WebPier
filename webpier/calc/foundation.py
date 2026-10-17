"""0500 direct foundation: ground springs under the footing.

Equations and printed digits follow .claude/docs/Example橋脚2/04_地盤のモデル化.pdf
(基礎標準 13.2.2.2); bearing factors follow 解説表13.2.2.3-2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.errors import InputError
from ..core.printed import AREA, LENGTH, Precision, Printed
from ..inputs import PierInput

INERTIA_6 = Precision(6, "m4")
REACTION_COEFFICIENT = Precision(0, "kN/m3")
SPRING = Precision(0, "kN/m")
ROTATION_SPRING = Precision(0, "kN m/rad")
BEARING_FACTOR = Precision(2, "")

# kv = c·ρ·Ed·Bv^e by soil type; gravel uses the sand equation.
SOIL_EQUATIONS: dict[str, tuple[float, float, str]] = {
    "砂質土": (6.9, -0.5, "-1/2"),
    "砂礫": (6.9, -0.5, "-1/2"),
    "砂質土と粘性土の互層": (5.1, -0.75, "-3/4"),
    "粘性土": (3.8, -1.0, "-1"),
}
RHO = {"long_term": 0.5, "short_term": 1.0}
SHEAR_RATIO_TEXT = "1/3"

# 解説表13.2.2.3-2 地表面が平坦な場合の支持力係数: φ, Nγ, Nq. φ ≥ 42° uses the last row.
BEARING_FACTOR_TABLE = (
    (25, 3.6, 4.8), (26, 4.0, 5.2), (27, 4.5, 5.6), (28, 5.0, 6.1), (29, 6.2, 7.1), (30, 7.7, 8.3),
    (31, 9.7, 9.8), (32, 12, 11), (33, 15, 14), (34, 20, 17), (35, 26, 20), (36, 34, 25),
    (37, 45, 31), (38, 60, 39), (39, 80, 50), (40, 100, 64), (41, 130, 73), (42, 150, 85),
)


@dataclass(frozen=True)
class SpringSet:
    rho: float
    kv: Printed
    ks: Printed
    Kv: Printed
    Ks: Printed
    Kr_longitudinal: Printed
    Kr_transverse: Printed


@dataclass(frozen=True)
class FoundationResult:
    b: Printed
    l: Printed
    area: Printed
    width: Printed
    inertia_longitudinal: Printed
    inertia_transverse: Printed
    surface_thickness: Printed
    soil_type: str
    deformation_modulus: Printed
    coefficient: float
    exponent: float
    exponent_text: str
    friction_angle: Printed
    n_gamma: Printed
    n_q: Printed
    long_term: SpringSet
    short_term: SpringSet


def bearing_factors(phi: float) -> tuple[Printed, Printed]:
    """Linear interpolation in the table; the input layer guarantees 25 ≤ φ < 90."""
    if phi >= BEARING_FACTOR_TABLE[-1][0]:
        return BEARING_FACTOR(BEARING_FACTOR_TABLE[-1][1]), BEARING_FACTOR(BEARING_FACTOR_TABLE[-1][2])
    index = math.floor(phi) - BEARING_FACTOR_TABLE[0][0]
    (phi0, gamma0, q0), (phi1, gamma1, q1) = BEARING_FACTOR_TABLE[index], BEARING_FACTOR_TABLE[index + 1]
    fraction = (phi - phi0) / (phi1 - phi0)
    return BEARING_FACTOR(gamma0 + (gamma1 - gamma0) * fraction), BEARING_FACTOR(q0 + (q1 - q0) * fraction)


def surface_thickness(pier: PierInput) -> Printed:
    """表層厚 = H6 + H5 + min(df1, df2): the embedment of the footing base."""
    sub = pier.substructure
    return LENGTH(sub.h[6].value + sub.h[5].value + min(sub.df1.value, sub.df2.value))


def _springs(rho: float, coefficient: float, exponent: float, modulus: float,
             area: Printed, width: Printed, inertia_l: Printed, inertia_t: Printed) -> SpringSet:
    kv = REACTION_COEFFICIENT(coefficient * rho * modulus * width.value ** exponent)
    ks = REACTION_COEFFICIENT(kv.value / 3)
    return SpringSet(
        rho=rho, kv=kv, ks=ks,
        Kv=SPRING(kv.value * area.value), Ks=SPRING(ks.value * area.value),
        Kr_longitudinal=ROTATION_SPRING(kv.value * inertia_l.value),
        Kr_transverse=ROTATION_SPRING(kv.value * inertia_t.value),
    )


def calculate_foundation(pier: PierInput) -> FoundationResult:
    sub = pier.substructure
    support = pier.soil.support
    try:
        b = LENGTH.total(sub.b[index] for index in (7, 8, 9))
        l = LENGTH.total(sub.w[index] for index in (7, 8, 9))
        area = AREA(b.value * l.value)
        width = LENGTH(math.sqrt(area.value))
        if area.value <= 0 or width.value <= 0:
            raise InputError("下部構造.寸法: 基礎底面積または換算幅が0になります")
        inertia_l = INERTIA_6(l.value * b.value ** 3 / 12)
        inertia_t = INERTIA_6(b.value * l.value ** 3 / 12)
        coefficient, exponent, exponent_text = SOIL_EQUATIONS[support.soil_type]
        modulus = support.deformation_modulus
        n_gamma, n_q = bearing_factors(support.friction_angle.value)
        terms = {term: _springs(rho, coefficient, exponent, modulus.value, area, width, inertia_l, inertia_t)
                 for term, rho in RHO.items()}
    except (OverflowError, ValueError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError(f"0500: 入力が大きすぎるため地盤ばねを計算できません（{exc}）") from exc
    return FoundationResult(
        b=b, l=l, area=area, width=width, inertia_longitudinal=inertia_l, inertia_transverse=inertia_t,
        surface_thickness=surface_thickness(pier), soil_type=support.soil_type, deformation_modulus=modulus,
        coefficient=coefficient, exponent=exponent, exponent_text=exponent_text,
        friction_angle=support.friction_angle, n_gamma=n_gamma, n_q=n_q,
        long_term=terms["long_term"], short_term=terms["short_term"],
    )
