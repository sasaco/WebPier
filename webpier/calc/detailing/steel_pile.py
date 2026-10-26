"""杭の構造細目 of a 鋼管ソイルセメント杭 in 0400 (decision 99; the sample Example橋脚4 II-18〜29 "1.2 杭に関する構造細目",
and the 杭体設計の手引き of H26 that the owner has, 鋼管杭編 Ⅱ-15〜26 and Ⅱ-56).

Every size the rules decide is decided here and not entered (owner: 計算で求まる値は入力にしない); the checks compare
it with the rule, as the sample's tables do (its design values are its conditions):

- (1) 鋼管杭: the outer diameter (800〜1200 mm), the thickness as made (≧ 9 mm and 1 % of D) and without the corrosion
  allowance (≧ 6 mm and 1.25 % of D), and the 杭先端部: the ずれ止め of Ⅱ-56 by the diameter (the larger row between two),
  the 貫入長 1.5D, the 余裕長 0.5Dsc and the 根入れ長 Dsc (their least values as the design);
- (2) 杭とフーチングの結合部: the anchor bars (SD345 or SD390, D19〜D38), their cover and clear spacing, pc of 1〜6 %, their
  anchorage in the footing (the sample's ld01 = k1(0.7fsyd／f'cd ＋ 11)φ, less 10φ for the hook, at least 20φ, and 5φ
  above the pipe, rounded up to 50 mm), the length of the filling concrete (the H26 formula of 解説図1.10-4, which gives
  the sample's 1550), the hoops in the footing (解説表1.10-1, 解説図1.10-5) and in the pipe (D10, the range split at
  300 mm or less), and the ずれ止め (SS400, the JIS flat bar of the largest standard thickness within the effective
  thickness and 20 mm, its width the least standard width of 2t', the spacing of 表1.10-1, two steps until the seismic
  check decides them);
- (3) ソイルセメント: the strengths of 解説表1.8-1 as the design, and the nominal diameter (Dsc − Dsp ≧ 200 mm).

The sizes are measured from the top of the pipe (the 杭頭), embedded 50 mm in the footing. Every value is printed and
later formulas use the printed value (ADR-0003).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from ...core.errors import InputError
from ...core.printed import Precision, Printed
from ...inputs import PierInput
from .._exact import d, put
from ..column_rebar import yield_strength
from .common import AREA, GAMMA_C, GAMMA_S, bar_area
from .pile import BOND

_PILE = "杭基礎.鋼管ソイルセメント杭"
_JOINT = f"{_PILE}.結合部"
_MILLI = Decimal(1000)
WHOLE = Precision(0, "mm")
TENTH = Precision(1, "mm")  # 4/3 Dmax, 1.5φ: 33.3, 57.0
RATIO = Precision(4, "")  # t／D: 0.0225
PERCENT2 = Precision(2, "%")  # the tables' t／D and pc: 2.25, 3.63
STRESS = Precision(1, "N/mm2")  # f'cd, fbod: 20.8, 1.9
FACTOR = Precision(2, "")  # k1: 1.15

# (1) 杭体設計の手引き 1.3, 1.5
DIAMETER_RANGE = (Printed(800, 0, "mm"), Printed(1200, 0, "mm"))
MADE_LEAST = Printed(9, 0, "mm")
MADE_RATIO = Printed(0.01, 2, "")
EFFECTIVE_LEAST = Printed(6, 0, "mm")
EFFECTIVE_RATIO = Printed(0.0125, 4, "")
# (1) 4) 杭先端部 (手引き Ⅱ-56, the sample's 表1.2.1): D → (ずれ止め段数 n, 先端間隔 l0, ピッチ l, 取付長 lspi), mm
TIP_RIBS = {800: (4, 300, 250, 1050), 900: (5, 300, 250, 1300), 1000: (5, 300, 250, 1300), 1100: (5, 300, 300, 1500),
            1200: (6, 300, 300, 1800)}
PENETRATION_FACTOR = Printed(1.5, 1, "")  # 鋼管の貫入長 ≧ 1.5D
MARGIN_FACTOR = Printed(0.5, 1, "")  # 余裕長 ≧ 0.5Dsc
# (2) the anchor bars (手引き 1.2, 1.10)
ANCHOR_GRADES = ("SD345", "SD390")
ANCHOR_SIZES = (19, 38)
CLEAR_LEAST = Printed(40, 0, "mm")
AGGREGATE_FACTOR = Decimal(4) / 3
BAR_FACTOR = Printed(1.5, 1, "")
RIB_GAP_LEAST = Printed(15, 0, "mm")  # アンカー鉄筋とずれ止めのあき
PC_RANGE = (Printed(1, 0, "%"), Printed(6, 0, "%"))
# the anchorage in the footing (the sample II-23, 24): ld01 = k1(0.7・fsyd／f'cd ＋ 11)φ, k1 = 1 ＋ 0.5φ／cs (cs ≦ 10φ)
ANCHOR_STEEL = Printed(0.7, 1, "")
ANCHOR_CONSTANT = Printed(11, 0, "")
K1_FACTOR = Printed(0.5, 1, "")
SPACING_LIMIT_BARS = 10  # cs ≦ 10φ
HOOK_BARS = 10  # the standard hook: less 10φ
LEAST_BARS = 20  # at least 20φ
INEFFECTIVE_BARS = 5  # ls = 5φ above the pipe
ROUND_ANCHOR = Decimal(50)
# the filling concrete (H26 解説図1.10-4): lc = max(1.5D, l'' ＋ l'd ＋ lh ＋ 100), l'd with αb 0.6, the lower hook's
# lh = the inner radius of a semicircular hook ＋ φ (the radius by the grade is a guess: decision 99)
FILL_FACTOR = Printed(1.5, 1, "")
FILL_INEFFECTIVE = Printed(100, 0, "mm")  # l''
FILL_ALPHA = Printed(0.6, 1, "")
FILL_BOTTOM = Printed(100, 0, "mm")  # アンカー鉄筋と中詰め下端の間
HOOK_RADIUS = {"SD295": Decimal("2.5"), "SD345": Decimal("2.5"), "SD390": Decimal("3.0")}
ROUND_FILL = Decimal(50)
EMBEDMENT = Printed(50, 0, "mm")  # the pipe into the footing (手引き 1.10(2) "50mm 程度")
# the hoops in the footing (解説表1.10-1, 解説図1.10-5) and in the pipe
FOOTING_HOOPS = ((16, 10), (25, 13), (math.inf, 16))  # anchor bar at most → hoop
FOOTING_HOOP_UPPER = (Printed(1000, 0, "mm"), 22)  # 鋼管外径が1000mm以下の場合はD22以下 (the sample II-25)
FOOTING_PITCHES = {25: (100, 150), 29: (125, 200)}  # anchor bar D25 以下 / D29 以上 → (下側から3本, それ以上)
FOOTING_LOWER_COUNT = 3
PIPE_HOOP = Printed(10, 0, "mm")
PIPE_PITCH_RANGE = (Printed(200, 0, "mm"), Printed(300, 0, "mm"))
PIPE_COUNT_LEAST = 3
ROUND_PIPE = Decimal(50)
# the ずれ止め (表1.10-1, the sample's 表1.2.5): the JIS G 3194 flat bars (a guess from memory: decision 99)
RIB_GRADE = "SS400"
FLAT_THICKNESSES = (Decimal("4.5"), Decimal(6), Decimal(8), Decimal(9), Decimal(12), Decimal(16), Decimal(19),
                    Decimal(22), Decimal(25))
FLAT_WIDTHS = (25, 32, 38, 44, 50, 65, 75, 90, 100)
RIB_THICKNESS_MOST = Decimal(20)
RIB_SPACINGS = ((Decimal(9), Decimal(11), 150), (Decimal(12), Decimal(14), 200), (Decimal(15), Decimal(17), 250),
                (Decimal(18), Decimal(20), 300))  # t' from, to → lz
RIB_WIDTH_FACTOR = 2
RIB_STEPS = 2  # 2 段以上; the seismic check (P10) raises it
# (3) ソイルセメント (解説表1.8-1), kN/m2, and the nominal diameter
STRENGTHS = (("杭一般部（砂質土）", Printed(1000, 0, "kN/m2")), ("杭一般部（粘性土）", Printed(750, 0, "kN/m2")),
             ("杭先端部（砂質土）", Printed(15000, 0, "kN/m2")))
NOMINAL_EXCESS = Printed(200, 0, "mm")


def _mm(value: Decimal) -> Printed:
    """A length in mm as the sample prints it: no decimal when it has none."""
    return Printed(float(value), 0 if value == value.to_integral_value() else 1, "mm")


def _up(value: Decimal, unit: Decimal) -> Decimal:
    return (value / unit).to_integral_value(rounding=ROUND_CEILING) * unit


@dataclass(frozen=True)
class Thickness:
    """The thickness of the pipe against its least value and its ratio to D."""

    value: Printed  # mm
    least: Printed
    ratio: Printed  # t／D
    least_ratio: Printed
    percent: Printed  # t／D × 100, as the table prints it

    @property
    def ok(self) -> bool:
        return d(self.value) >= d(self.least) and d(self.ratio) >= d(self.least_ratio)


@dataclass(frozen=True)
class Tip:
    """(1) 4) 杭先端部: the ずれ止め of the row of the diameter, and the 貫入長, 余裕長 and 根入れ長."""

    row: int | None  # the D of the row of TIP_RIBS; None: beyond it
    steps: int | None
    first: Printed | None  # l0
    pitch: Printed | None  # l
    length: Printed | None  # lspi
    penetration: Printed  # lspo = 1.5D
    margin: Printed  # le = 0.5Dsc
    embedment: Printed  # Df0 = Dsc

    @property
    def ok(self) -> bool:
        return self.row is not None


@dataclass(frozen=True)
class SteelPipe:
    """(1) 鋼管杭."""

    diameter: Printed  # D, mm
    soil_cement: Printed  # Dsc, mm
    corrosion: Printed  # mm
    made: Thickness
    effective: Thickness
    tip: Tip

    @property
    def diameter_ok(self) -> bool:
        return d(DIAMETER_RANGE[0]) <= d(self.diameter) <= d(DIAMETER_RANGE[1])

    @property
    def ok(self) -> bool:
        return self.diameter_ok and self.made.ok and self.effective.ok and self.tip.ok


@dataclass(frozen=True)
class Anchorage:
    """(f) the anchor bars in the footing: ld01 = k1(0.7fsyd／f'cd ＋ 11)φ, ld0 = max(ld01 − 10φ, 20φ), l1 = ld0 ＋ 5φ."""

    fsyd: Printed
    fck: Printed  # of the footing
    fcd: Printed
    spacing: Printed  # cs, the centre spacing of the anchor bars
    spacing_limit: Printed  # 10φ
    k1: Printed
    ld01: Printed
    hook: Printed  # 10φ
    reduced: Printed  # ld01 − 10φ
    least: Printed  # 20φ
    ld0: Printed
    ineffective: Printed  # ls = 5φ
    sum: Printed  # ld0 ＋ ls
    l1: Printed  # rounded up to 50 mm


@dataclass(frozen=True)
class Filling:
    """(g) lc = max(1.5D, l'' ＋ l'd ＋ lh ＋ 100), l'd = αb・fsyd／(4fbod)・φ with αb 0.6, rounded up to 50 mm."""

    fck: Printed  # of the filling concrete
    fbok: Printed
    fbod: Printed
    anchorage: Printed  # l'd
    required: Printed  # l2 = l'' ＋ l'd
    radius_factor: Decimal  # the inner radius of the hook in φ
    hook: Printed  # lh
    least: Printed  # 1.5D
    sum: Printed  # l'' ＋ l'd ＋ lh ＋ 100
    length: Printed  # lc


@dataclass(frozen=True)
class FootingHoops:
    """(h) the hoops in the footing: their diameter by the anchor bar (and at most D22 for D ≦ 1000), their pitches."""

    diameter: Printed
    upper: Printed | None  # D22 for D ≦ 1000
    lower_pitch: Printed  # the three from the footing's lower bars
    upper_pitch: Printed
    positions: tuple[Decimal, ...]  # mm above the top of the pipe


@dataclass(frozen=True)
class PipeHoops:
    """(h) the hoops in the pipe: D10 from l'' down to the lower hook, the range split at 300 mm or less."""

    diameter: Printed
    range: Printed  # mm
    divisions: int
    pitch: Printed  # rounded down to 50 mm
    count: int
    positions: tuple[Decimal, ...]  # mm below the top of the pipe

    @property
    def ok(self) -> bool:
        return self.count >= PIPE_COUNT_LEAST and d(self.pitch) >= d(PIPE_PITCH_RANGE[0])


@dataclass(frozen=True)
class Ribs:
    """(i) the ずれ止め: SS400, the flat bar t'×B, the spacing lz of 表1.10-1, the steps from D／4 below the head."""

    grade: str
    effective: Printed  # t of the pipe
    thickness: Printed | None  # t'; None: no flat bar fits 表1.10-1
    width: Printed | None  # B
    width_least: Printed | None  # 2t'
    spacing: Printed | None  # lz
    quarter: Printed  # D／4: the top step
    bottom_least: Printed | None  # lz0 = max(D／4, lz)
    steps: int
    bottom: Printed | None  # the lowest step above the bottom of the filling

    @property
    def ok(self) -> bool:
        if self.bottom is None or self.bottom_least is None:
            return False  # no flat bar fits 表1.10-1
        return d(self.bottom) >= d(self.bottom_least)


@dataclass(frozen=True)
class Joint:
    """(2) 杭とフーチングの結合部."""

    grade: str
    bar_diameter: Printed
    bar_count: int
    bar_unit: Printed
    bar_area: Printed  # As
    made: Printed  # t of the pipe as made
    centroid: Printed  # mm from the outer edge
    cover: Printed  # c = centroid − t − φ／2
    pitch: Printed  # π(D − 2・centroid)／n
    clear: Printed
    aggregate: Printed  # Dmax of the filling
    aggregate_limit: Printed  # 4/3 Dmax
    bar_limit: Printed  # 1.5φ
    rib_gap: Printed | None  # centroid − t − t' − φ／2
    pc: Printed  # %
    anchorage: Anchorage
    filling: Filling
    footing_hoops: FootingHoops
    pipe_hoops: PipeHoops
    ribs: Ribs

    @property
    def grade_ok(self) -> bool:
        return self.grade in ANCHOR_GRADES

    @property
    def size_ok(self) -> bool:
        return ANCHOR_SIZES[0] <= self.bar_diameter.value <= ANCHOR_SIZES[1]

    @property
    def cover_ok(self) -> bool:
        return d(self.cover) >= d(self.bar_diameter)

    @property
    def clear_ok(self) -> bool:
        return d(self.clear) >= max(d(CLEAR_LEAST), d(self.aggregate_limit), d(self.bar_limit))

    @property
    def rib_gap_ok(self) -> bool:
        return self.rib_gap is not None and d(self.rib_gap) >= d(RIB_GAP_LEAST)

    @property
    def pc_ok(self) -> bool:
        return d(PC_RANGE[0]) <= d(self.pc) <= d(PC_RANGE[1])

    @property
    def ok(self) -> bool:
        return (self.grade_ok and self.size_ok and self.cover_ok and self.clear_ok and self.rib_gap_ok and self.pc_ok
                and self.pipe_hoops.ok and self.ribs.ok)


@dataclass(frozen=True)
class SoilCement:
    """(3) ソイルセメント: the strengths of 解説表1.8-1 as the design, and the nominal diameter."""

    strengths: tuple[tuple[str, Printed], ...]
    soil_cement: Printed  # Dsc, mm
    steel: Printed  # Dsp, mm

    @property
    def ok(self) -> bool:
        return d(self.soil_cement) - d(self.steel) >= d(NOMINAL_EXCESS)


@dataclass(frozen=True)
class SteelPileDetailing:
    pipe: SteelPipe
    joint: Joint
    soil_cement: SoilCement

    @property
    def ok(self) -> bool:
        return self.pipe.ok and self.joint.ok and self.soil_cement.ok


def _need(value, key: str):
    if value is None:
        raise InputError(f"{key}: 杭の構造細目に必要です")
    return value


def _thickness(value: Printed, least: Printed, diameter: Printed, least_ratio: Printed) -> Thickness:
    ratio = put(RATIO, d(value) / d(diameter))
    return Thickness(value, least, ratio, least_ratio, put(PERCENT2, d(ratio) * 100))


def _tip(diameter: Printed, soil_cement: Printed) -> Tip:
    row = next((size for size in TIP_RIBS if size >= d(diameter)), None)
    penetration = put(WHOLE, d(PENETRATION_FACTOR) * d(diameter))
    margin = put(WHOLE, d(MARGIN_FACTOR) * d(soil_cement))
    if row is None:
        return Tip(None, None, None, None, None, penetration, margin, soil_cement)
    steps, first, pitch, length = TIP_RIBS[row]
    return Tip(row, steps, _mm(Decimal(first)), _mm(Decimal(pitch)), _mm(Decimal(length)), penetration, margin,
               soil_cement)


def steel_pipe(pier: PierInput) -> SteelPipe:
    pile = pier.piles.steel_soil_cement
    diameter = _mm(d(_need(pile.steel_diameter, f"{_PILE}.鋼管外径")) * _MILLI)
    soil_cement = _mm(d(_need(pile.soil_cement_diameter, f"{_PILE}.ソイルセメント径")) * _MILLI)
    made = _need(pile.thickness, f"{_PILE}.鋼管厚")
    corrosion = _need(pile.corrosion, f"{_PILE}.腐食代")
    effective = _mm(d(made) - d(corrosion))
    return SteelPipe(diameter, soil_cement, _mm(d(corrosion)),
                     _thickness(_mm(d(made)), MADE_LEAST, diameter, MADE_RATIO),
                     _thickness(effective, EFFECTIVE_LEAST, diameter, EFFECTIVE_RATIO), _tip(diameter, soil_cement))


def _anchorage(pier: PierInput, phi: Printed, fsyd: Printed, pitch: Printed) -> Anchorage:
    fck = Printed(float(d(pier.materials.footing)), 1, "N/mm2")
    fcd = put(STRESS, d(fck) / d(GAMMA_C))
    limit = put(WHOLE, SPACING_LIMIT_BARS * d(phi))
    spacing = min(pitch, limit, key=d)
    k1 = put(FACTOR, 1 + d(K1_FACTOR) * d(phi) / d(spacing))
    ld01 = put(WHOLE, d(k1) * (d(ANCHOR_STEEL) * d(fsyd) / d(fcd) + d(ANCHOR_CONSTANT)) * d(phi))
    hook = put(WHOLE, HOOK_BARS * d(phi))
    reduced = put(WHOLE, d(ld01) - d(hook))
    least = put(WHOLE, LEAST_BARS * d(phi))
    ld0 = max(reduced, least, key=d)
    ineffective = put(WHOLE, INEFFECTIVE_BARS * d(phi))
    total = put(WHOLE, d(ld0) + d(ineffective))
    return Anchorage(fsyd, fck, fcd, spacing, limit, k1, ld01, hook, reduced, least, ld0, ineffective, total,
                     _mm(_up(d(total), ROUND_ANCHOR)))


def _filling(fck_input: Printed, phi: Printed, grade: str, fsyd: Printed, diameter: Printed) -> Filling:
    fck = Printed(float(d(fck_input)), 1, "N/mm2")
    fbok = BOND.get(int(d(fck))) if d(fck) == d(fck).to_integral_value() else None
    if fbok is None:
        strengths = "・".join(str(value) for value in BOND)
        raise InputError(f"{_JOINT}.中詰めコンクリート_f'ck: f'ck {fck.value:g} の付着強度がありません（中詰めコンクリート長"
                         f"の算定。{strengths} N/mm2）")
    fbok_printed = Printed(fbok, 1, "N/mm2")
    fbod = put(STRESS, d(fbok_printed) / d(GAMMA_C))
    anchorage = put(WHOLE, d(FILL_ALPHA) * d(fsyd) / (4 * d(fbod)) * d(phi))
    required = put(WHOLE, d(FILL_INEFFECTIVE) + d(anchorage))
    factor = HOOK_RADIUS[grade]
    hook = put(WHOLE, (factor + 1) * d(phi))
    least = put(WHOLE, d(FILL_FACTOR) * d(diameter))
    total = put(WHOLE, d(required) + d(hook) + d(FILL_BOTTOM))
    return Filling(fck, fbok_printed, fbod, anchorage, required, factor, hook, least, total,
                   _mm(_up(max(d(least), d(total)), ROUND_FILL)))


def _footing_hoops(phi: Printed, diameter: Printed, top: Printed) -> FootingHoops:
    size = next(hoop for most, hoop in FOOTING_HOOPS if phi.value <= most)
    lower, upper = FOOTING_PITCHES[25 if phi.value <= 25 else 29]
    limit, bar = FOOTING_HOOP_UPPER
    positions = []
    height = Decimal(0)  # above the footing's base, which is EMBEDMENT below the top of the pipe
    reach = d(top) + d(EMBEDMENT)
    for _ in range(FOOTING_LOWER_COUNT):
        height += lower
        positions.append(height)
    while height + upper <= reach:
        height += upper
        positions.append(height)
    return FootingHoops(_mm(Decimal(size)), _mm(Decimal(bar)) if d(diameter) <= d(limit) else None,
                        _mm(Decimal(lower)), _mm(Decimal(upper)),
                        tuple(position - d(EMBEDMENT) for position in positions))


def _pipe_hoops(filling: Filling) -> PipeHoops:
    first = d(FILL_INEFFECTIVE)
    span = d(filling.length) - d(FILL_BOTTOM) - d(filling.hook) - first
    divisions = int((span / d(PIPE_PITCH_RANGE[1])).to_integral_value(rounding=ROUND_CEILING))
    pitch = (span / divisions / ROUND_PIPE).to_integral_value(rounding=ROUND_FLOOR) * ROUND_PIPE
    return PipeHoops(PIPE_HOOP, _mm(span), divisions, _mm(pitch), divisions + 1,
                     tuple(first + index * pitch for index in range(divisions + 1)))


def _ribs(effective: Printed, diameter: Printed, filling: Filling) -> Ribs:
    quarter = put(WHOLE, d(diameter) / 4)
    most = min(d(effective), RIB_THICKNESS_MOST)
    thickness = next((size for size in reversed(FLAT_THICKNESSES) if size <= most), None)
    band = None if thickness is None else next(
        (spacing for low, high, spacing in RIB_SPACINGS if low <= thickness <= high), None)
    if thickness is None or band is None:
        return Ribs(RIB_GRADE, effective, None, None, None, None, quarter, None, RIB_STEPS, None)
    least = RIB_WIDTH_FACTOR * thickness
    width = next(size for size in FLAT_WIDTHS if size >= least)
    spacing = _mm(Decimal(band))
    lowest = d(quarter) + (RIB_STEPS - 1) * d(spacing)
    return Ribs(RIB_GRADE, effective, _mm(thickness), _mm(Decimal(width)), _mm(least), spacing, quarter,
                max(quarter, spacing, key=d), RIB_STEPS, _mm(d(filling.length) - lowest))


def joint(pier: PierInput, pipe: SteelPipe) -> Joint:
    found = pier.piles.steel_soil_cement.joint
    bars = f"{_JOINT}.軸方向鉄筋"
    phi = _need(found.bar_diameter, f"{bars}.径")
    count = _need(found.bar_count, f"{bars}.本数")
    grade = _need(found.bar_grade, f"{bars}.材質")
    centroid = _mm(d(_need(found.bar_centroid, f"{bars}.重心位置")))
    fill_fck = _need(found.fill_fck, f"{_JOINT}.中詰めコンクリート_f'ck")
    aggregate = _need(found.fill_aggregate_max, f"{_JOINT}.粗骨材の最大寸法")
    _need(pier.materials.footing, "鉄筋.フーチング.concrete_strength_mpa")
    unit = bar_area(phi, f"{bars}.径")
    area = put(AREA, d(unit) * count)
    if 2 * d(centroid) >= d(pipe.diameter):
        raise InputError(f"{bars}.重心位置: 鋼管外径に対して大きすぎます")
    made = pipe.made.value
    cover = _mm(d(centroid) - d(made) - d(phi) / 2)
    pitch = put(WHOLE, (d(pipe.diameter) - 2 * d(centroid)) * Decimal(repr(math.pi)) / count)
    fsyd = put(Precision(0, "N/mm2"), d(yield_strength(grade)) / d(GAMMA_S))
    anchorage = _anchorage(pier, phi, fsyd, pitch)
    filling = _filling(fill_fck, phi, grade, fsyd, pipe.diameter)
    ribs = _ribs(pipe.effective.value, pipe.diameter, filling)
    rib_gap = None if ribs.thickness is None else _mm(d(centroid) - d(made) - d(ribs.thickness) - d(phi) / 2)
    pc = put(PERCENT2, d(area) / (Decimal(repr(math.pi)) * d(pipe.diameter) ** 2 / 4) * 100)
    return Joint(grade, phi, count, unit, area, made, centroid, cover, pitch, _mm(d(pitch) - d(phi)),
                 _mm(d(aggregate)), put(TENTH, d(aggregate) * AGGREGATE_FACTOR),
                 put(TENTH, d(BAR_FACTOR) * d(phi)), rib_gap, pc, anchorage, filling,
                 _footing_hoops(phi, pipe.diameter, anchorage.l1), _pipe_hoops(filling), ribs)


def steel_pile_detailing(pier: PierInput) -> SteelPileDetailing:
    """The 杭の構造細目 of the 鋼管ソイルセメント杭 of *pier* (decision 99)."""
    pipe = steel_pipe(pier)
    return SteelPileDetailing(pipe, joint(pier, pipe), SoilCement(STRENGTHS, pipe.soil_cement, pipe.diameter))
