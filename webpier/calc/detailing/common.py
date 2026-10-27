"""What the detailing checks of the column, the beam and the footing share (decision 73): the bar areas, the clear
spacing of the main bars, the shear reinforcement ratio and the bounds of its spacing, the upper limit of the
ductility and the shear capacity ratio.

Every value is printed and later formulas use the printed value (ADR-0003). The constants are those of the sample
0400 (.claude/docs/Example橋脚/output/0400_照査の前提.pdf) and of Example2 06_照査の前提 6.3〜6.8, with their sources.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from ...core.errors import InputError
from ...core.printed import Precision, Printed
from .._exact import d, put
from ..column_rebar import bar_area, yield_strength

AREA = Precision(1, "mm2")  # bar areas: 61560.0, 5297.3 (the sample 0400)
SECTION = Precision(0, "mm2")  # b·h: 6698000
LENGTH = Precision(1, "mm")  # spacings, depths: 1558.4
BOUND = Precision(0, "mm")  # the bounds of the stirrup spacing: 390, 304 (the sample 0400 7))
LIMIT = Precision(1, "mm")  # the limits of the clear spacing: 57.0, 33.3 (the sample 0400 5))
PERCENT = Precision(3, "%")  # Pc, Ps, pw: 0.919, 2.264, 0.655
COUNT = Precision(0, "本")
FRACTION = Precision(5, "")  # pw as a fraction in 9): 0.00655
RATIO = Precision(3, "")  # 8) 0.029, 9) 0.138
STRENGTH = Precision(0, "N/mm2")  # fwyd: 390

# 1) (a): the axial bars at least 0.15 % of the whole section (RC標準第Ⅲ編 2.3.3.1(1); the sample 0400)
MIN_RATIO = Printed(0.15, 2, "%")
# 3): the axial bars at most 6 % (RC標準第Ⅲ編 2.3.3.2; the sample 0400)
MAX_RATIO = Printed(6.0, 1, "%")
# 6): the shear reinforcement at least 0.15 % (RC標準第Ⅲ編 2.3.3.1(4); the sample 0400)
MIN_SHEAR_RATIO = Printed(0.15, 2, "%")
# 5) 鉄筋のあき (RC標準第Ⅲ編 2.3.4; the sample 0400): a column 40 mm, 1.5φ and 4/3 Dmax; a beam or a footing 20 mm,
# φ and 4/3 Dmax (the sample's footing page uses the column's: not reproduced, ADR-0001)
COLUMN_CLEAR = (Printed(40, 0, "mm"), Printed(1.5, 1, ""))
MEMBER_CLEAR = (Printed(20, 0, "mm"), Printed(1.0, 1, ""))
AGGREGATE_FACTOR = Fraction(4, 3)
# 8) 帯鉄筋の靭性率における上限値 (RC標準[R5] 第Ⅲ編 5.2.3.3; the sample 0400): 0.021・kwo・pw + 0.013 ≦ 0.04,
# pw in %, kwo by the grade of the hoops (owner 2026-10-21); SD490's is not checked in a source (decision 100)
DUCTILITY_FACTOR = Printed(0.021, 3, "")
DUCTILITY_CONSTANT = Printed(0.013, 3, "")
DUCTILITY_LIMIT = Printed(0.04, 3, "")
KWO = {"SD295": Printed(0.85, 2, ""), "SD345": Printed(1.0, 2, ""), "SD390": Printed(1.15, 2, "")}
# 9) 帯鉄筋の設計せん断耐力の上限値 (RC標準[R5] 第Ⅲ編 7.2.2; the sample 0400): pw・fwyd / f'cd and 0.1, printed
# without a judgement (owner 2026-10-21); γc 1.3, γs 1.0
CAPACITY_LIMIT = Printed(0.1, 2, "")
GAMMA_C = Printed(1.3, 1, "")
GAMMA_S = Printed(1.0, 1, "")


@dataclass(frozen=True)
class BarGroup:
    """Bars of one size: a count (per 1 m of width for a footing) and their area."""

    diameter: Printed  # mm
    count: Printed  # 本, or 本 per 1 m
    unit_area: Printed  # mm2, one bar
    area: Printed  # mm2, all of them

    @staticmethod
    def of(diameter: Printed, count: Printed, path: str) -> BarGroup:
        unit = bar_area(diameter, path)
        return BarGroup(diameter, count, unit, put(AREA, d(count) * d(unit)))


@dataclass(frozen=True)
class SteelRatio:
    """1) (a) Pc = As／(b·h) ≧ 0.15 % and 3) Pc ＜ 6 %."""

    groups: tuple[BarGroup, ...]
    grade: str  # the steel of the main bars
    area: Printed  # As, the sum of the groups
    width: Printed  # b, mm
    depth: Printed  # h, mm
    section: Printed  # b·h
    ratio: Printed  # Pc, %
    minimum: Printed
    maximum: Printed | None  # None: 3) is not checked (the beam)
    minimum_ok: bool
    maximum_ok: bool | None


@dataclass(frozen=True)
class ClearSpacing:
    """5) 鉄筋のあき of a group of main bars: the clear gaps along the face and between the layers, and the limits."""

    pitch: Printed | None  # the least centre spacing along the face; None: one bar a line
    layer: Printed | None  # the least centre spacing of two layers; None: one layer
    diameter: Printed  # φ, the largest bar of the group
    pitch_clear: Printed | None  # pitch − φ
    layer_clear: Printed | None  # layer − φ
    clear: Printed | None  # the least of them
    minimum: Printed  # 40 or 20 mm
    bar_factor: Printed  # 1.5 or 1.0
    bar_limit: Printed  # factor·φ
    aggregate_max: Printed  # Dmax
    aggregate_limit: Printed  # 4/3·Dmax
    ok: bool


@dataclass(frozen=True)
class ShearRatio:
    """6) Ps = Σ legs·Aw／(b·s) ≧ 0.15 %; also pw of 8) and 9)."""

    diameter: Printed
    unit_area: Printed  # Aw of one leg
    legs: Printed  # the legs (per 1 m of width for a footing)
    area: Printed  # legs·Aw
    width: Printed  # b (1000 for a footing)
    pitch: Printed  # s
    ratio: Printed  # %
    minimum: Printed
    ok: bool


@dataclass(frozen=True)
class Bound:
    """A bound on the spacing of the shear reinforcement: numerator／denominator·base, or a fixed length (no base)."""

    name: str  # what it is (reporting gives the words): see general_spacing and confinement_spacing
    base: Printed | None  # d, φ or the short side, mm; None for a fixed length (its numerator, in mm)
    numerator: int
    denominator: int
    value: Printed  # mm


@dataclass(frozen=True)
class StirrupSpacing:
    """7) the spacing of the shear reinforcement against the least of its bounds."""

    bounds: tuple[Bound, ...]
    limit: Printed  # the least bound
    pitch: Printed  # s
    ok: bool


@dataclass(frozen=True)
class DuctilityLimit:
    """8) 0.021・kwo・pw + 0.013 ≦ 0.04 (pw in %)."""

    grade: str
    factor: Printed  # 0.021
    kwo: Printed
    pw: Printed  # %
    constant: Printed  # 0.013
    value: Printed
    limit: Printed
    ok: bool


@dataclass(frozen=True)
class CapacityRatio:
    """9) pw・fwyd／f'cd and 0.1, f'cd = f'ck／γc: printed with its sign only (no judgement)."""

    pw: Printed  # fraction
    fwyd: Printed  # N/mm2
    fck: Printed  # N/mm2
    gamma_c: Printed
    value: Printed
    limit: Printed
    above: bool  # value > 0.1


def need(value, path: str):
    if value is None:
        raise InputError(f"{path}: 値が必要です")
    return value


def steel_ratio(groups: Sequence[BarGroup], grade: str, width: Printed, depth: Printed, *,
                maximum: bool = True) -> SteelRatio:
    area = put(AREA, sum((d(group.area) for group in groups), Decimal(0)))
    section = put(SECTION, d(width) * d(depth))
    ratio = put(PERCENT, d(area) / d(section) * 100)
    return SteelRatio(groups=tuple(groups), grade=grade, area=area, width=width, depth=depth, section=section, ratio=ratio,
                      minimum=MIN_RATIO, maximum=MAX_RATIO if maximum else None,
                      minimum_ok=d(ratio) >= d(MIN_RATIO), maximum_ok=d(ratio) < d(MAX_RATIO) if maximum else None)


def least_gap(lines: Iterable[Sequence[Printed]]) -> Printed | None:
    """The least difference of neighbouring positions in any of *lines* (each in any order)."""
    gaps = [d(b) - d(a) for line in lines for a, b in zip(sorted(line, key=d), sorted(line, key=d)[1:])]
    return put(LENGTH, min(gaps)) if gaps else None


def clear_spacing(pitch: Printed | None, layer: Printed | None, diameter: Printed, aggregate_max: Printed, *,
                  column: bool) -> ClearSpacing:
    minimum, factor = COLUMN_CLEAR if column else MEMBER_CLEAR
    pitch_clear = None if pitch is None else put(LENGTH, d(pitch) - d(diameter))
    layer_clear = None if layer is None else put(LENGTH, d(layer) - d(diameter))
    clears = [value for value in (pitch_clear, layer_clear) if value is not None]
    clear = min(clears, key=d) if clears else None
    bar_limit = put(LIMIT, d(factor) * d(diameter))
    aggregate_limit = put(LIMIT, d(aggregate_max) * 4 / 3)
    ok = clear is None or d(clear) >= max(d(minimum), d(bar_limit), d(aggregate_limit))
    return ClearSpacing(pitch=pitch, layer=layer, diameter=diameter, pitch_clear=pitch_clear, layer_clear=layer_clear,
                        clear=clear, minimum=minimum, bar_factor=factor, bar_limit=bar_limit,
                        aggregate_max=aggregate_max, aggregate_limit=aggregate_limit, ok=ok)


def shear_ratio(diameter: Printed, legs: Printed, width: Printed, pitch: Printed, path: str) -> ShearRatio:
    unit = bar_area(diameter, path)
    area = put(AREA, d(legs) * d(unit))
    ratio = put(PERCENT, d(area) / (d(width) * d(pitch)) * 100)
    return ShearRatio(diameter=diameter, unit_area=unit, legs=legs, area=area, width=width, pitch=pitch, ratio=ratio,
                      minimum=MIN_SHEAR_RATIO, ok=d(ratio) >= d(MIN_SHEAR_RATIO))


def bound(name: str, base: Printed | None, factor: Fraction | int) -> Bound:
    factor = Fraction(factor)
    exact = Decimal(factor.numerator) / Decimal(factor.denominator)
    return Bound(name, base, factor.numerator, factor.denominator,
                 put(BOUND, exact if base is None else d(base) * exact))


def stirrup_spacing(bounds: Sequence[Bound], pitch: Printed) -> StirrupSpacing:
    limit = min((item.value for item in bounds), key=d)
    return StirrupSpacing(bounds=tuple(bounds), limit=limit, pitch=pitch, ok=d(pitch) <= d(limit))


def general_spacing(depth: Printed, compression: Printed, stirrup: Printed, pitch: Printed) -> StirrupSpacing:
    """7) ① 一般部 (Example2 06 6.7, コンクリート標準 11.7.3): 3/4·d and 400 mm (the minimum reinforcement), d/2 and
    300 mm (reinforcement the calculation needs), 15φ of the compression bars and 48φ of the stirrups."""
    return stirrup_spacing((bound("three_quarters_d", depth, Fraction(3, 4)), bound("fixed_400", None, 400),
                            bound("half_d", depth, Fraction(1, 2)), bound("fixed_300", None, 300),
                            bound("compression_15", compression, 15), bound("stirrup_48", stirrup, 48)), pitch)


def confinement_spacing(depth: Printed, main: Printed, stirrup: Printed, short_side: Printed,
                        pitch: Printed) -> StirrupSpacing:
    """7) ② 塑性ヒンジ部 (the sample 0400 7) ①, Example2 06 6.8 コンクリート標準 11.7.4): d/4, 8φ of the main bars,
    24φ of the stirrups and 300 mm in the plastic hinge; 12φ of the main bars and half the short side of the
    section for the lateral confinement."""
    return stirrup_spacing((bound("quarter_d", depth, Fraction(1, 4)), bound("main_8", main, 8),
                            bound("stirrup_24", stirrup, 24), bound("fixed_300", None, 300),
                            bound("main_12", main, 12), bound("half_short_side", short_side, Fraction(1, 2))), pitch)


def ductility_limit(grade: str, pw: Printed, path: str) -> DuctilityLimit:
    kwo = KWO.get(grade)
    if kwo is None:
        raise InputError(f"{path}: {grade} の kwo（帯鉄筋の靭性率の上限、RC標準[R5] 第Ⅲ編 5.2.3.3）が未確認です"
                         f"（{'・'.join(KWO)} のいずれかを選んでください）")
    value = put(RATIO, d(DUCTILITY_FACTOR) * d(kwo) * d(pw) + d(DUCTILITY_CONSTANT))
    return DuctilityLimit(grade=grade, factor=DUCTILITY_FACTOR, kwo=kwo, pw=pw, constant=DUCTILITY_CONSTANT,
                          value=value, limit=DUCTILITY_LIMIT,
                          ok=d(value) <= d(DUCTILITY_LIMIT))


def capacity_ratio(pw: Printed, grade: str, fck: Printed) -> CapacityRatio:
    fraction = put(FRACTION, d(pw) / 100)
    fwyd = put(STRENGTH, d(yield_strength(grade)) / d(GAMMA_S))
    value = put(RATIO, d(fraction) * d(fwyd) * d(GAMMA_C) / d(fck))
    return CapacityRatio(pw=fraction, fwyd=fwyd, fck=fck, gamma_c=GAMMA_C, value=value, limit=CAPACITY_LIMIT,
                         above=d(value) > d(CAPACITY_LIMIT))


def count(number: int) -> Printed:
    return COUNT(number)
