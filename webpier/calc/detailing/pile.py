"""杭の構造細目 of a 場所打ち杭 in 0400 (decision 98; the sample .claude/docs/Example橋脚/output/0440_照査の前提.pdf "2.4 杭の
構造細目", made by the sheet 杭の計算 of 照査の前提.xlsm; 基礎標準 付属資料17).

- (1) 杭頭反力の最大値から定める最小鉄筋量 uses the L2 pile head reaction, a section force: it is checked in 0711 / 0721
  (``minimum_bars``) and 0400 only refers to it (ADR-0012);
- (2) 曲げモーメントから定まる最小鉄筋量: pt = 100·As／(b·d) ≧ 0.20 %, As the quarter of the main bars, b = √2·R,
  d = 2R − ds. The relief to 0.15 % needs the acting moment (a section force) and is not judged;
- (3) 最小帯鉄筋量: the shear span ratio (1/β)／(1.6·D) with 1/β of SOIL-JR's .sdc (0500) decides 0.35 % (2.5 or less) or
  0.30 % for the 2D zone; the zones below it that reach above the cut-off (all of them without one) need 0.20 %;
- (4) 杭頭定着長: the basic anchorage length of the main bars in the footing (RC標準 2.3.7.3, as the sheet 基本定着長D16 of
  照査の前提.xlsm: the bond strength of the footing's concrete, the hoops inside the footing or else those of the 2D zone,
  At = one hoop's area × its 組), rounded up to 100 mm (winPier's 主筋の定着長を 100mm 単位でまるめる).

Every value is printed and later formulas use the printed value (ADR-0003).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from ...core.errors import InputError
from ...core.printed import Precision, Printed
from ...inputs import PierInput
from ...inputs.rebar import PileHoop
from .._exact import d, put
from ..column_rebar import yield_strength
from ..pile_body import PileResponseError, PointForces
from ..response_displacement import ResponseDisplacementResult
from .common import AREA, GAMMA_C, GAMMA_S, LENGTH, PERCENT, bar_area, need

_REBAR = "鉄筋.杭"
_PILE = "杭基礎.場所打ち杭"
_MILLI = Decimal(1000)
INVERSE_BETA = Precision(2, "m")  # 1/β: 3.55 (the sample)
SPAN_RATIO = Precision(2, "")  # L/d: 1.85
FORCE = Precision(2, "kN")  # Pvmax: 7403.05
STRENGTH = Precision(1, "N/mm2")  # fbod: 1.8
RATIO_K = Precision(2, "")  # Kc: 3.67
ALPHA = Precision(3, "")  # αb: 0.404
WHOLE = Precision(0, "mm")  # ld, 20φ: 383, 320
QUARTER = Decimal("0.25")  # (2) the tension bars are the quarter (90°) of the main bars
BENDING_MINIMUM = Printed(0.2, 2, "%")  # (2) 0.20 %
SPAN_LIMIT = Printed(2.5, 1, "")  # (3) the shear span ratio 2.5
HEAD_TOUGH = Printed(0.35, 2, "%")  # (3) the 2D zone at a shear span ratio of 2.5 or less
HEAD_PLAIN = Printed(0.3, 2, "%")  # (3) the 2D zone otherwise
LOWER_MINIMUM = Printed(0.2, 2, "%")  # (3) beyond the 2D zone
SPAN_FACTOR = Printed(1.6, 1, "")
LEGS_PER_SET = 2  # a closed circular hoop crosses the section twice (decision 92)
# (1) As' = 0.0104·Pvmax×10³／(0.85·f'ck ＋ 0.008·fsyd) (基礎標準 付属資料17 1.)
MINIMUM_FACTOR = Printed(0.0104, 4, "")
MINIMUM_CONCRETE = Printed(0.85, 2, "")
MINIMUM_STEEL = Printed(0.008, 3, "")
# (4) RC標準 2.3.7.3: fbok by f'ck (the table of the sheet 基本定着長D16), γc 1.3; αb = 0.75／Kc ＋ 0.2 in [0.5, 1.0]
BOND = {18: 1.9, 21: 2.1, 24: 2.3, 27: 2.5, 30: 2.7, 35: 3.0, 40: 3.3, 50: 3.8}
ALPHA_FACTOR = Printed(0.75, 2, "")
ALPHA_CONSTANT = Printed(0.2, 1, "")
ALPHA_MIN = Printed(0.5, 1, "")
ALPHA_MAX = Printed(1.0, 1, "")
SPLIT_FACTOR = 15
MIN_ANCHORAGE_BARS = 20  # ld ≧ 20φ
ROUND_TO = Decimal(100)  # mm: the 杭頭定着長 is rounded up to it
# the 方向 of the .sdc and the words of the report
DIRECTIONS = (("橋軸方向", "線路方向"), ("直角方向", "線路直角方向"))


def mm(value: Decimal) -> Printed:
    """A length in mm of the input's sizes as the sample prints it: no decimal when it has none (600, 156)."""
    return Printed(float(value), 0 if value == value.to_integral_value() else 1, "mm")


@dataclass(frozen=True)
class Section:
    """The pile and its main bars as (1) and (2) print them."""

    diameter: Printed  # D, mm
    diameter_m: Printed  # D, m (the shear span ratio)
    radius: Printed  # R, mm
    centre: Printed  # ds, 芯かぶり of the main bars, mm
    bar_diameter: Printed
    bar_count: int
    bar_unit: Printed  # one bar, mm2
    bar_area: Printed  # As of all the bars, mm2
    grade: str  # the steel of the main bars
    fsyd: Printed  # N/mm2 (γs 1.0)
    fck: Printed  # f'ck of the pile


@dataclass(frozen=True)
class BendingMinimum:
    """(2) pt = 100·As／(b·d) ≧ 0.20 %."""

    tension_area: Printed  # As, a quarter of the bars
    width: Printed  # b = √2·R
    depth: Printed  # d = 2R − ds
    ratio: Printed  # pt, %
    minimum: Printed
    ok: bool


@dataclass(frozen=True)
class SpanRatio:
    """The shear span ratio of one direction (or of both, when their 1/β is the same)."""

    directions: tuple[str, ...]  # 線路方向, 線路直角方向
    inverse_beta: Printed  # 1/β, m
    ratio: Printed  # L/d
    tough: bool  # 2.5 or less


@dataclass(frozen=True)
class HoopRatio:
    """pw = Aw·legs／(D·s)×100 of a zone, and its minimum."""

    name: str  # 杭頭2D区間, 第1区間, …
    diameter: Printed
    unit_area: Printed  # one bar, mm2
    legs: Printed  # 2 × 組
    width: Printed  # D, mm
    pitch: Printed  # s, mm
    ratio: Printed  # %
    minimum: Printed
    ok: bool


@dataclass(frozen=True)
class HoopMinimum:
    """(3) the 2D zone at 0.35 % or 0.30 % by the shear span ratio, and the zones beyond it at 0.20 %."""

    spans: tuple[SpanRatio, ...]
    tough: bool  # some direction at 2.5 or less: 0.35 %
    head: HoopRatio
    lower: tuple[HoopRatio, ...]
    ok: bool


@dataclass(frozen=True)
class HeadAnchorage:
    """(4) 杭頭定着長: ld = αb·fsyd／(4·fbod)·φ ≧ 20φ (RC標準 2.3.7.3), rounded up to 100 mm."""

    fsyd: Printed
    fck: Printed  # f'ck of the footing
    fbok: Printed
    fbod: Printed  # fbok／γc
    diameter: Printed  # φ
    clear_cover: Printed  # cb1 = ds − φ／2
    pitch: Printed  # the centre spacing of the main bars on their circle
    half_gap: Printed  # cb2 = (pitch − φ)／2
    cb: Printed
    stirrup_zone: str  # フーチング内 or 杭頭2D区間: the hoops At and s are of
    stirrup_diameter: Printed
    stirrup_sets: int
    at: Printed  # At, mm2
    s: Printed  # mm
    kc: Printed
    alpha_raw: Printed  # 0.75／Kc ＋ 0.2
    alpha: Printed  # within [0.5, 1.0]
    basic: Printed  # αb·fsyd／(4·fbod)·φ
    bars: int  # basic in φ, rounded up (the sample's "(24φ)")
    least: Printed  # 20φ
    anchorage: Printed  # max(basic, 20φ)
    length: Printed  # 杭頭定着長: anchorage rounded up to 100 mm


@dataclass(frozen=True)
class PileDetailing:
    section: Section
    bending: BendingMinimum
    hoops: HoopMinimum
    anchorage: HeadAnchorage

    @property
    def ok(self) -> bool:
        return self.bending.ok and self.hoops.ok


def hoop_of(hoop: PileHoop, path: str) -> tuple[Printed, int, Printed]:
    return (need(hoop.diameter, f"{path}.diameter_mm"), need(hoop.sets, f"{path}.sets"),
            need(hoop.pitch, f"{path}.pitch_mm"))


def section(pier: PierInput) -> Section:
    pile, bars = pier.piles.cast_in_place, pier.rebar.pile
    diameter_m = d(need(pile.diameter, f"{_PILE}.杭径"))
    fck = need(pile.fck, f"{_PILE}.f'ck")
    grade = need(bars.materials.main, f"{_REBAR}.materials.main")
    main = need(bars.main_diameter, f"{_REBAR}.main_bars.diameter_mm")
    count = need(bars.main_count, f"{_REBAR}.main_bars.count")
    cover = need(bars.pure_cover, f"{_REBAR}.pure_cover_mm")
    hoop = need(bars.hoops.zone_2d.diameter, f"{_REBAR}.hoops.zone_2d.diameter_mm")
    diameter = diameter_m * _MILLI
    centre = d(cover) + d(hoop) + d(main) / 2  # 芯かぶり (CONTEXT.md)
    if 2 * centre >= diameter:
        raise InputError(f"{_REBAR}.pure_cover_mm: 杭径に対して大きすぎます（主鉄筋の芯かぶり {centre:g} mm が杭の半径 "
                         f"{diameter / 2:g} mm 以上になります）")
    unit = bar_area(main, f"{_REBAR}.main_bars.diameter_mm")
    return Section(diameter=mm(diameter), diameter_m=Printed(float(diameter_m), 2 if diameter_m * 100 % 1 == 0 else 3, "m"),
                   radius=mm(diameter / 2), centre=mm(centre), bar_diameter=main, bar_count=count, bar_unit=unit,
                   bar_area=put(AREA, d(unit) * count), grade=grade, fsyd=put(Precision(0, "N/mm2"),
                                                                              d(yield_strength(grade)) / d(GAMMA_S)),
                   fck=Printed(float(d(fck)), 1, "N/mm2"))


def bending_minimum(found: Section) -> BendingMinimum:
    tension = put(AREA, d(found.bar_area) * QUARTER)
    width = put(LENGTH, Decimal(2).sqrt() * d(found.radius))
    depth = put(LENGTH, 2 * d(found.radius) - d(found.centre))
    ratio = put(PERCENT, 100 * d(tension) / (d(width) * d(depth)))
    return BendingMinimum(tension, width, depth, ratio, BENDING_MINIMUM, d(ratio) >= d(BENDING_MINIMUM))


def _spans(inverse_betas: Sequence[tuple[str, float]], found: Section) -> tuple[SpanRatio, ...]:
    """The shear span ratio of each direction, one line for both when their 1/β prints the same."""
    printed = [(name, put(INVERSE_BETA, Decimal(repr(value)))) for name, value in inverse_betas]
    groups: list[tuple[list[str], Printed]] = []
    for name, value in printed:
        same = next((group for group in groups if group[1] == value), None)
        if same is None:
            groups.append(([name], value))
        else:
            same[0].append(name)
    spans = []
    for names, value in groups:
        ratio = put(SPAN_RATIO, d(value) / (d(SPAN_FACTOR) * d(found.diameter_m)))
        spans.append(SpanRatio(tuple(names), value, ratio, d(ratio) <= d(SPAN_LIMIT)))
    return tuple(spans)


def _ratio(name: str, hoop: tuple[Printed, int, Printed], path: str, found: Section, minimum: Printed) -> HoopRatio:
    diameter, sets, pitch = hoop
    unit = bar_area(diameter, f"{path}.diameter_mm")
    legs = Printed(LEGS_PER_SET * sets, 0, "")
    ratio = put(PERCENT, d(unit) * d(legs) / (d(found.diameter) * d(pitch)) * 100)
    return HoopRatio(name, diameter, unit, legs, found.diameter, pitch, ratio, minimum, d(ratio) >= d(minimum))


def hoop_minimum(pier: PierInput, found: Section, inverse_betas: Sequence[tuple[str, float]]) -> HoopMinimum:
    bars = pier.rebar.pile
    spans = _spans(inverse_betas, found)
    tough = any(span.tough for span in spans)
    path = f"{_REBAR}.hoops.zone_2d"
    head = _ratio("杭頭2D区間", hoop_of(bars.hoops.zone_2d, path), path, found, HEAD_TOUGH if tough else HEAD_PLAIN)
    cutoff = bars.cutoff
    reach = None  # mm from the head down to the cut-off; None: no cut-off (the first main bars run all along)
    if cutoff.main_diameter is not None:
        reach = d(need(cutoff.cutoff_length, f"{_REBAR}.cutoff.cutoff_length_mm"))
    top = 2 * d(found.diameter)  # the 2D zone ends 2D below the head
    lower = []
    for index, zone in enumerate(bars.hoops.lower):
        zone_path = f"{_REBAR}.hoops.lower[{index}]"
        length = d(need(zone.length, f"{zone_path}.length_m")) * _MILLI
        if reach is None or top < reach:
            lower.append(_ratio(f"第{index + 1}区間", hoop_of(zone.hoop, zone_path), zone_path, found, LOWER_MINIMUM))
        top += length
    ok = head.ok and all(item.ok for item in lower)
    return HoopMinimum(spans, tough, head, tuple(lower), ok)


def anchorage_bond(fck: Printed, where: str, purpose: str) -> tuple[Printed, Printed]:
    """fbok of f'ck *fck* (RC標準 2.3.7.3) and fbod = fbok／γc; an f'ck without one is an input error at *where*, naming
    the *purpose*."""
    fbok = BOND.get(int(d(fck))) if d(fck) == d(fck).to_integral_value() else None
    if fbok is None:
        strengths = "・".join(str(value) for value in BOND)
        raise InputError(f"{where}: f'ck {fck.value:g} の付着強度がありません（{purpose}。{strengths} N/mm2）")
    fbok_printed = Printed(fbok, 1, "N/mm2")
    return fbok_printed, put(STRENGTH, d(fbok_printed) / d(GAMMA_C))


def head_anchorage(pier: PierInput, found: Section) -> HeadAnchorage:
    bars = pier.rebar.pile
    fck = pier.materials.footing
    fbok_printed, fbod = anchorage_bond(fck, "鉄筋.フーチング.concrete_strength_mpa", "杭頭定着長の算定")
    phi = found.bar_diameter
    clear = put(LENGTH, d(found.centre) - d(phi) / 2)
    circle = (d(found.diameter) - 2 * d(found.centre)) * Decimal(repr(math.pi))
    pitch = put(LENGTH, circle / found.bar_count)
    half = put(LENGTH, (d(pitch) - d(phi)) / 2)
    cb = min(clear, half, key=d)
    footing = bars.hoops.footing
    if footing.diameter is None and footing.sets is None and footing.pitch is None:
        zone, path, hoop = "杭頭2D区間", f"{_REBAR}.hoops.zone_2d", bars.hoops.zone_2d
    else:
        zone, path, hoop = "フーチング内", f"{_REBAR}.hoops.footing", footing
    diameter, sets, s = hoop_of(hoop, path)
    at = put(AREA, d(bar_area(diameter, f"{path}.diameter_mm")) * sets)
    kc = put(RATIO_K, d(cb) / d(phi) + SPLIT_FACTOR * d(at) / (d(s) * d(phi)))
    raw = put(ALPHA, d(ALPHA_FACTOR) / d(kc) + d(ALPHA_CONSTANT))
    alpha = min(max(raw, ALPHA_MIN, key=d), ALPHA_MAX, key=d)
    basic = put(WHOLE, d(alpha) * d(found.fsyd) / (4 * d(fbod)) * d(phi))
    least = put(WHOLE, MIN_ANCHORAGE_BARS * d(phi))
    anchorage = max(basic, least, key=d)
    length = (d(anchorage) / ROUND_TO).to_integral_value(rounding=ROUND_CEILING) * ROUND_TO
    bars_count = int((d(basic) / d(phi)).to_integral_value(rounding=ROUND_CEILING))
    return HeadAnchorage(found.fsyd, Printed(float(d(fck)), 1, "N/mm2"), fbok_printed, fbod, phi, clear, pitch, half, cb,
                         zone, diameter, sets, at, s, kc, raw, alpha, basic, bars_count, least, anchorage,
                         Printed(float(length), 0, "mm"))


def pile_detailing(pier: PierInput, inverse_betas: Sequence[tuple[str, float]]) -> PileDetailing:
    """The 杭の構造細目 of the 場所打ち杭 of *pier*; *inverse_betas* are 1/β of each direction of SOIL-JR's .sdc as
    (線路方向 or 線路直角方向, m)."""
    found = section(pier)
    return PileDetailing(found, bending_minimum(found), hoop_minimum(pier, found, inverse_betas),
                         head_anchorage(pier, found))


@dataclass(frozen=True)
class MinimumBars:
    """(1) As' = 0.0104·Pvmax×10³／(0.85·f'ck ＋ 0.008·fsyd) ≦ As, in 0711 / 0721 (decision 98)."""

    direction: str  # 線路方向, 線路直角方向
    pvmax: Printed  # kN, one pile
    fck: Printed
    fsyd: Printed
    required: Printed  # As', mm2
    section: Section
    ok: bool


def minimum_bars(pier: PierInput, direction: str, pvmax: Decimal) -> MinimumBars:
    found = section(pier)
    load = put(FORCE, pvmax)
    required = put(AREA, d(MINIMUM_FACTOR) * d(load) * _MILLI
                   / (d(MINIMUM_CONCRETE) * d(found.fck) + d(MINIMUM_STEEL) * d(found.fsyd)))
    return MinimumBars(direction, load, found.fck, found.fsyd, required, found, d(found.bar_area) >= d(required))


def pile_head_reaction(rows: Sequence[tuple[Sequence[PointForces], int]]) -> Decimal:
    """Pvmax (kN, one pile): of each pile row, the lines of the element at its head in the pickup of 復旧性L2 of
    Aggre-SE's check (the forces of the bundle, compression negative) and its piles in the depth; the largest axial
    compression at the head (ITAN) of one pile of any row (decision 98). ``PileResponseError`` when no row has one."""
    found = [Decimal(repr(-line.smallest.nd)) / piles for lines, piles in rows for line in lines
             if line.focus == "N" and line.point == "ITAN" and line.smallest.nd < 0]
    if not found:
        raise PileResponseError("杭頭（ITAN）の軸方向圧縮力がありません")
    return max(found)


@dataclass(frozen=True)
class PileSeismicResult:
    """The result of 0711 / 0721 of a pile foundation: of a 場所打ち杭 (decision 98), (1) 杭頭反力の最大値から定める最小鉄筋量 of
    its direction (None of a 鋼管ソイルセメント杭, decision 122), and the 応答変位法 (calc.response_displacement, decision 97) of
    an input that considers the 地盤変位."""

    minimum: MinimumBars | None
    response: ResponseDisplacementResult | None
