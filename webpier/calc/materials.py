"""Concrete elastic modulus Ec from the design strength f'ck (decision 25).

Ec is interpolated linearly in the RcDan table (EcCivilList: f'ck 18..80 N/mm2,
Ec in kN/mm2; RcDan/General/InformationGetter.cs GetEc, Calculation/
GeneralCalculation.cs GetLinear). Outside the table it is an input error: no
extrapolation and no cap. The report prints f'ck, the two table points used and
Ec (Example2 08 p.8-2 / 09 p.9-2: f'ck 27.0, Ec = 2.65 × 10^7 kN/m2).

Ec is printed as a mantissa with 2 decimals times 10^7 kN/m2, i.e. rounded to
0.1 kN/mm2. ``Printed`` holds decimal places only, so the mantissa is the
printed value and ``Concrete.ec`` gives the same number in kN/m2 exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput
from ._exact import d, put

TABLE_STRENGTH = Precision(0, "N/mm2")
TABLE_MODULUS = Precision(0, "kN/mm2")
EC_EXPONENT = 7
EC_MANTISSA = Precision(2, f"x10^{EC_EXPONENT} kN/m2")
_MANTISSA_PER_KN_MM2 = Decimal(10) ** (EC_EXPONENT - 6)  # 1 kN/mm2 = 10^6 kN/m2


@dataclass(frozen=True)
class TablePoint:
    strength: Printed  # f'ck, N/mm2
    modulus: Printed  # Ec, kN/mm2


EC_TABLE = tuple(TablePoint(TABLE_STRENGTH.exact(f), TABLE_MODULUS.exact(e)) for f, e in (
    (18, 22), (24, 25), (30, 28), (40, 31), (50, 33), (60, 35), (70, 37), (80, 38)))


@dataclass(frozen=True)
class Concrete:
    strength: Printed  # f'ck as entered, N/mm2
    lower: TablePoint  # table point at or below f'ck
    upper: TablePoint  # table point at or above f'ck
    modulus: Printed  # Ec / 10^7 kN/m2, 2 decimals

    @property
    def ec(self) -> float:
        """Ec in kN/m2: the printed mantissa times 10^7."""
        return float(d(self.modulus) * Decimal(10) ** EC_EXPONENT)


@dataclass(frozen=True)
class MaterialsResult:
    beam: Concrete  # 鉄筋.梁
    column: Concrete  # 鉄筋.柱
    footing: Concrete  # 鉄筋.フーチング


def concrete(strength: Printed, path: str) -> Concrete:
    """Ec for *strength*; *path* names the input in the error message."""
    f = d(strength)
    first, last = EC_TABLE[0].strength, EC_TABLE[-1].strength
    if not d(first) <= f <= d(last):
        raise InputError(f"{path}: ヤング係数の表の範囲外です（f'ck {first.value:g}～{last.value:g} N/mm2、"
                         f"入力 {strength.value} N/mm2）")
    lower, upper = next((a, b) for a, b in zip(EC_TABLE, EC_TABLE[1:]) if f <= d(b.strength))
    f0, e0, f1, e1 = (d(value) for value in (lower.strength, lower.modulus, upper.strength, upper.modulus))
    ec = e0 + (e1 - e0) * (f - f0) / (f1 - f0)  # kN/mm2
    return Concrete(strength=strength, lower=lower, upper=upper,
                    modulus=put(EC_MANTISSA, ec / _MANTISSA_PER_KN_MM2))


def calculate_materials(pier: PierInput) -> MaterialsResult:
    m = pier.materials
    return MaterialsResult(
        beam=concrete(m.beam, "鉄筋.梁.concrete_strength_mpa"),
        column=concrete(m.column, "鉄筋.柱.concrete_strength_mpa"),
        footing=concrete(m.footing, "鉄筋.フーチング.concrete_strength_mpa"),
    )
