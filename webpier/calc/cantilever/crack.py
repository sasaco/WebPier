"""The flexural cracking moment of the beam and ε'csd (0910 13.5 (1), decision 59; Example2 13-54, 13-55).

Mcrd = σcrd·I/y + N'd·I/(A·y) (RC標準 5.3.4), with the gross section b × h at the column face (I = b·h³/12, y = h/2,
A = b·h), σcrd = kob·k1b·ftk, ftk = 0.23 f'ck^(2/3), kob = 1 + 1/(0.85 + 4.5 h/lch), lch = 1000·GF·Ec/ftk²,
GF = 1/100·dmax^(1/3)·f'ck^(1/3), k1b = 1.0 and N'd = 0 (the beam carries no axial force). Ec is the modulus of
0600's materials (calc.materials, kN/mm²). The printed digits follow the reference: I and Mcrd·y/σcrd as three
significant figures in scientific notation (kept as the rounded values), the others as 13-54 prints them.

ε'csd is the value of the RC標準 table for the age at which the beam first cracks: 450 when the self weight alone
cracks it (30日), 350 when the permanent actions do (100日), 300 when only the permanent and variable actions do or
nothing does (200日以上). The moments compared are the self weight of the cantilever, the permanent actions (case
32) and the largest 安全性（破壊） moment (13-55).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...core.printed import MOMENT, Precision, Printed
from .._exact import d, put
from ..materials import Concrete

MM = Precision(0, "mm")
MM2 = Precision(0, "mm2")
STRESS = Precision(2, "N/mm2")
ENERGY = Precision(4, "N/mm")  # GF
MODULUS = Precision(1, "kN/mm2")  # Ec
LENGTH_MM = Precision(0, "mm")  # lch
COEFFICIENT = Precision(2, "")  # kob, k1b
SHRINKAGE = Precision(0, "×10⁻⁶")
K1B = COEFFICIENT.exact(1.0)
AXIAL = Precision(2, "kN")
_THIRD = Decimal(1) / Decimal(3)
# ε'csd by the age at first cracking (RC標準; Example2 13-55): the action that cracks the beam, ε'csd, the note
AGES = (("部材自重", 450, "30日"), ("永久作用", 350, "100日"), ("永久作用および変動作用", 300, "200日以上"))
UNCRACKED = 300


def significant(value: Decimal, figures: int) -> Printed:
    """*value* rounded to *figures* significant figures, kept as a number without decimals (printed as a.bcE+nn)."""
    exponent = value.adjusted() - figures + 1
    return Precision(max(-exponent, 0), "")(float(value.quantize(Decimal(1).scaleb(exponent))))


@dataclass(frozen=True)
class CrackingMoment:
    width: Printed  # b, mm
    depth: Printed  # h, mm
    inertia: Printed  # I = b h³/12, mm⁴ (3 significant figures)
    neutral_axis: Printed  # y = h/2, mm
    area: Printed  # A = b h, mm²
    strength: Printed  # f'ck, N/mm²
    aggregate_max: Printed  # dmax, mm
    tensile_strength: Printed  # ftk = 0.23 f'ck^(2/3), N/mm²
    fracture_energy: Printed  # GF, N/mm
    modulus: Printed  # Ec, kN/mm²
    characteristic_length: Printed  # lch, mm
    kob: Printed
    k1b: Printed
    crack_stress: Printed  # σcrd, N/mm²
    axial: Printed  # N'd, kN (0)
    moment: Printed  # Mcrd, kN m


@dataclass(frozen=True)
class Cracking:
    """Which actions crack the beam and the ε'csd that follows (13-55)."""

    cracking_moment: CrackingMoment
    self_weight: Printed  # Md of the self weight, kN m
    permanent: Printed  # Md of the permanent actions (case 32)
    permanent_variable: Printed  # the largest 安全性（破壊） Md
    ecsd: Printed  # ×10⁻⁶
    age: str  # the note of the row chosen (30日 …), or 200日以上 when nothing cracks


def cracking_moment(width_mm: Printed, depth_mm: Printed, concrete: Concrete, aggregate_max: Printed) -> CrackingMoment:
    b, h = d(width_mm), d(depth_mm)
    inertia = significant(b * h ** 3 / 12, 3)
    y, area = put(MM, h / 2), put(MM2, b * h)
    fck = d(concrete.strength)
    ftk = put(STRESS, Decimal("0.23") * (fck ** (Decimal(2) / Decimal(3))))
    gf = put(ENERGY, (d(aggregate_max) ** _THIRD) * (fck ** _THIRD) / 100)
    ec = put(MODULUS, d(concrete.modulus) * 10)  # ×10^7 kN/m² → kN/mm²
    lch = put(LENGTH_MM, 1000 * d(gf) * d(ec) / d(ftk) ** 2)
    kob = put(COEFFICIENT, 1 + 1 / (Decimal("0.85") + Decimal("4.5") * h / d(lch)))
    sigma = put(STRESS, d(kob) * d(K1B) * d(ftk))
    axial = AXIAL(0)
    moment = put(MOMENT, (d(sigma) * d(inertia) / d(y) + d(axial) * 1000 * d(inertia) / (d(area) * d(y))) / 10 ** 6)
    return CrackingMoment(width_mm, depth_mm, inertia, y, area, concrete.strength, aggregate_max, ftk, gf, ec, lch,
                          kob, K1B, sigma, axial, moment)


def cracking(moment: CrackingMoment, self_weight: Printed, permanent: Printed, permanent_variable: Printed) -> Cracking:
    compared = (self_weight, permanent, permanent_variable)
    for (_, ecsd, age), md in zip(AGES, compared):
        if abs(md.value) >= moment.moment.value:
            return Cracking(moment, *compared, SHRINKAGE(ecsd), age)
    return Cracking(moment, *compared, SHRINKAGE(UNCRACKED), AGES[-1][2])
