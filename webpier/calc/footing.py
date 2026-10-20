"""0800 フーチングの応答値 (decision 60, CONTEXT.md): 12.1 応答値の算定, the pieces of one direction.

Five columns of design response values at the centre of the footing base: 安全性 Md最大 and Vd最大 (the extraction
group 安全性（破壊） of the frame analysis: the combination of the largest |mz| and of the largest fy), 使用性 短期 and
長期 (耐久性 永久＋変動 and 永久作用, the largest fy), read as 0612 reads its support reactions (foundation_check.pick),
and 地震時 (JRSNAP's Rvd到達ステップ: the first output step at which V reaches Rvd in the step table Aggre-SE's runner
returns, of the Case with the largest |M|; ``seismic_action``). Each column has 0612's bearing capacity
(foundation_check.bearing_capacity, with the column's 地盤抵抗係数 and water level: 地震時 1.00 and the normal water;
the long-term qd is the unlimited one, the limit being the bearing check's), the shape factor αb of the sample's
table, the distribution of the base pressure (``distribution``: Case 1〜4 of the workbook 0700_線路フーチング.xls,
地盤反力 (1) rows 43〜49), and, for an overhang of length L1, the base pressure under it per metre of width
(``ground_reaction``: the segments of the profile within the overhang, q1 at the edge and q2 at the segment's end,
W = (q1 + q2)/2 ℓ, x the centroid from the column face, M = W x), the footing's self weight and the overburden
(``self_weight``), the buoyancy at a water level (``buoyancy``), and the design forces per metre
(``section_forces``: the full-width reaction over the effective width be, minus the self weight, plus the uplift;
La = Md/Vd). The effective width (``effective_width``) is the column width plus the overhangs across, each not more
than d = H6 − the centre of the lower bars (RC標準 13.6.3).

Not reproduced from the sample (ADR-0001, ADR-0003; tests/fixtures/example2/footing_notes.md): q2 of a sloping
segment is the pressure at the end of the segment on the q1 side, q1 − (q1 − q2)ℓ/X (the workbook takes it from the
other edge); the seismic buoyancy of 7) is the normal water as in 6); La is printed to 3 decimals. The check itself
is Capacita's (0810 / 0820, ADR-0008).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import FORCE, LENGTH, LINE_LOAD, MOMENT, Precision, Printed
from ..inputs import PierInput
from ..inputs.model import Substructure
from ._exact import d, put
from .footing_rebar import FootingReinforcement, footing_reinforcement
from .foundation import FoundationResult
from .foundation_check import (FACTORS as CHECK_FACTORS, FACTOR, PRESSURE, Basis as CheckBasis, Capacity,
                               Direction as CheckDirection, Factors, Focus, FrameResult, Reactions, Requirement,
                               bearing_capacity, pick, prepare as prepare_check)
from .longitudinal.combinations import ExtractionGroup

VOLUME = Precision(2, "m3")
MOMENT_PER_M = Precision(2, "kN m/m")
# 5) 浮力: the uplift on the base per metre of width (sample 247, −10.0 kN/m3).
WATER_UNIT_WEIGHT = Printed(-10.0, 1, "kN/m3")
# 地震時: 地盤抵抗係数 1.00 (sample 245: frc = fry = frd = 1.00); γi, γa as the safety checks are not used here.
SEISMIC_FACTORS = Factors(Printed(1.0, 1, ""), Printed(1.0, 1, ""), Printed(1.0, 2, ""), Printed(1.0, 2, ""),
                          Printed(1.0, 2, ""), Printed(1.0, 1, ""))


@dataclass(frozen=True)
class ColumnSpec:
    key: str
    limit: str  # 安全性 / 使用性 / 地震時
    detail: str  # Ｍd最大 / Ｖd最大 / 短期 / 長期 / ""
    factors: Factors
    water: str  # γe2: the cover weight of the Basis, "high" or "normal"
    uplift: str  # 5) 浮力: the water level of the buoyancy, "high" (安全性) or "normal" (使用性, 地震時)
    group: ExtractionGroup | None  # the extraction group of the frame analysis; None for 地震時
    focus: Focus | None


COLUMNS = (
    ColumnSpec("safety_moment", "安全性", "Ｍd最大", CHECK_FACTORS[Requirement.SAFETY], "high", "high",
               ExtractionGroup.FAILURE, Focus.MOMENT),
    ColumnSpec("safety_shear", "安全性", "Ｖd最大", CHECK_FACTORS[Requirement.SAFETY], "high", "high",
               ExtractionGroup.FAILURE, Focus.VERTICAL),
    ColumnSpec("short_term", "使用性", "短期", CHECK_FACTORS[Requirement.SHORT_TERM], "high", "normal",
               ExtractionGroup.PERMANENT_VARIABLE, Focus.VERTICAL),
    ColumnSpec("long_term", "使用性", "長期", CHECK_FACTORS[Requirement.LONG_TERM], "normal", "normal",
               ExtractionGroup.PERMANENT, Focus.VERTICAL),
    ColumnSpec("seismic", "地震時", "", SEISMIC_FACTORS, "normal", "normal", None, None),
)
FACTORS = {spec.key: spec.factors for spec in COLUMNS}
WATER = {spec.key: spec.water for spec in COLUMNS}
UPLIFT = {spec.key: spec.uplift for spec in COLUMNS}


def shape_alpha(b_effective: Printed, l: Printed) -> Printed:
    """αb = 1.0 + 0.2 B′/L′ (B′/L as L/B′ when B′ > L), printed with the cohesion term (sample 244)."""
    ratio = d(b_effective) / d(l) if b_effective.value <= l.value else d(l) / d(b_effective)
    return put(FACTOR, 1 + Decimal("0.2") * ratio)


@dataclass(frozen=True)
class Distribution:
    """地盤反力形状: the pressure profile from the q1 edge (workbook 地盤反力 (1) rows 43〜49)."""

    case: int  # 1 trapezoid over B, 2 triangle over X1, 3 block X1 then triangle X2, 4 block X1
    apex: Printed  # 設計最大地盤反力度 qd1 of the triangle: 2Vd/(3L(B/2 − ex))
    qd1: Printed  # 設計地盤反力度 at the edge
    qd2: Printed  # at the far edge (Case 1), else 0
    x1: Printed  # 載荷幅
    x2: Printed


def distribution(vd: Printed, md: Printed, ex: Printed, b: Printed, l: Printed, qd: Printed,
                 mmd: Printed) -> Distribution:
    """Case 4 when Md > Mmd, 3 when the triangle's apex exceeds qd, 2 when ex > B/6, else 1."""
    bb, ll = d(b), d(l)
    apex = put(PRESSURE, 2 * d(vd) / (3 * ll * (bb / 2 - d(ex))))
    zero = PRESSURE(0)
    if md.value > mmd.value:
        x1 = put(LENGTH, d(vd) / (d(qd) * ll))
        return Distribution(4, apex, qd, zero, x1, LENGTH(0))
    if apex.value > qd.value:
        under = (12 * bb * d(vd) / (d(qd) * ll) - 12 * d(vd) ** 2 / (d(qd) * ll) ** 2
                 - 24 * d(md) / (d(qd) * ll))
        x2 = put(LENGTH, max(under, Decimal(0)).sqrt())
        x1 = put(LENGTH, d(vd) / (d(qd) * ll) - d(x2) / 2)
        return Distribution(3, apex, qd, zero, x1, x2)
    if d(ex) * 6 > bb:
        x1 = put(LENGTH, 2 * d(vd) / (d(apex) * ll))
        return Distribution(2, apex, apex, zero, x1, LENGTH(0))
    qd1, qd2 = (put(PRESSURE, d(vd) / (bb * ll) * (1 + sign * 6 * d(ex) / bb)) for sign in (1, -1))
    return Distribution(1, apex, qd1, qd2, b, LENGTH(0))


@dataclass(frozen=True)
class EffectiveWidth:
    """2) 有効幅: be = min(left, d) + column + min(right, d) ≦ the full width, d = H6 − cover."""

    column: Printed  # the column width across the plane of bending, m
    left: Printed  # the overhangs across, m
    right: Printed
    height: Printed  # H6
    cover: Printed  # the centre of the lower bars from the lower face, m
    d: Printed
    left_effective: Printed
    right_effective: Printed
    be: Printed
    full: Printed


def effective_width(column: Printed, left: Printed, right: Printed, h6: Printed, cover_mm: Printed) -> EffectiveWidth:
    cover = put(LENGTH, d(cover_mm) / 1000)
    depth = put(LENGTH, d(h6) - d(cover))
    left_effective = left if left.value <= depth.value else depth
    right_effective = right if right.value <= depth.value else depth
    be = put(LENGTH, d(left_effective) + d(column) + d(right_effective))
    full = put(LENGTH, d(left) + d(column) + d(right))
    return EffectiveWidth(column, left, right, h6, cover, depth, left_effective, right_effective, be, full)


@dataclass(frozen=True)
class WeightRow:
    """One row of 4) 自重・上載土 or 5) 浮力 per metre of width: V = height × length, W = V γ, x = length/2, M = W x."""

    height: Printed  # m
    length: Printed  # L1, m
    volume: Printed  # m3 per metre
    unit_weight: Printed  # kN/m3
    w: Printed  # kN
    x: Printed  # m, from the column face
    m: Printed  # kN m


def _weight_row(height: Printed, length: Printed, unit_weight: Printed) -> WeightRow:
    volume = put(VOLUME, d(height) * d(length))
    w = put(FORCE, d(volume) * d(unit_weight))
    x = put(LENGTH, d(length) / 2)
    return WeightRow(height, length, volume, unit_weight, w, x, put(MOMENT, d(w) * d(x)))


@dataclass(frozen=True)
class SelfWeight:
    overburden: WeightRow  # ① the cover soil df × L1
    footing: WeightRow  # ② the footing H6 × L1
    w: Printed
    m: Printed


def self_weight(cover_depth: Printed, h6: Printed, l1: Printed, gamma_overburden: Printed,
                gamma_footing: Printed) -> SelfWeight:
    overburden = _weight_row(cover_depth, l1, gamma_overburden)
    footing = _weight_row(h6, l1, gamma_footing)
    return SelfWeight(overburden, footing, FORCE.total((overburden.w, footing.w)),
                      MOMENT.total((overburden.m, footing.m)))


def buoyancy(water: Printed, l1: Printed) -> WeightRow:
    """The uplift of the water *water* above the footing base on the overhang."""
    return _weight_row(water, l1, WATER_UNIT_WEIGHT)


@dataclass(frozen=True)
class ReactionSegment:
    """3) 地盤反力による断面力: one segment of the pressure profile within the overhang."""

    q1: Printed  # at the segment's start (the edge for the first segment)
    q2: Printed  # at its end
    uniform: bool  # a block: q2 = q1
    length: Printed  # ℓ, m
    w: Printed  # kN/m
    x: Printed  # m, the centroid from the column face
    m: Printed  # kN m/m


def _profile(dist: Distribution) -> tuple[tuple[Printed, Printed, Printed], ...]:
    """(length, q at the start, q at the end) of each piece of the profile from the q1 edge."""
    if dist.case == 1:
        return ((dist.x1, dist.qd1, dist.qd2),)
    if dist.case == 2:
        return ((dist.x1, dist.qd1, PRESSURE(0)),)
    if dist.case == 3:
        return ((dist.x1, dist.qd1, dist.qd1), (dist.x2, dist.qd1, PRESSURE(0)))
    return ((dist.x1, dist.qd1, dist.qd1),)


def ground_reaction(dist: Distribution, l1: Printed) -> tuple[ReactionSegment, ...]:
    """The segments of the profile within the overhang of length *l1*, from the edge."""
    segments = []
    position = Decimal(0)
    for length, q_start, q_end in _profile(dist):
        if position >= d(l1) or length.value <= 0:
            break
        end = min(position + d(length), d(l1))
        portion = end - position
        q2 = put(PRESSURE, d(q_start) + (d(q_end) - d(q_start)) * portion / d(length))
        uniform = q_start == q_end
        w = put(LINE_LOAD, (d(q_start) + d(q2)) / 2 * portion)
        if d(q_start) + d(q2) > 0:
            x = put(LENGTH, (d(l1) - end) + portion * (2 * d(q_start) + d(q2)) / (3 * (d(q_start) + d(q2))))
        else:
            x = put(LENGTH, d(l1) - end + portion / 2)
        segments.append(ReactionSegment(q_start, q2, uniform, put(LENGTH, portion), w, x,
                                        put(MOMENT_PER_M, d(w) * d(x))))
        position = end
    return tuple(segments)


@dataclass(frozen=True)
class SectionForces:
    """6) 設計曲げモーメント and 7) 発生せん断力 per metre of width at the column face."""

    m_reaction: Printed  # kN m/m under the overhang
    m_full: Printed  # × the full width
    m_per_m: Printed  # ÷ be
    m_self: Printed  # −(self weight and overburden)
    m_buoyancy: Printed  # −(uplift), positive
    md: Printed
    v_reaction: Printed  # kN/m
    v_full: Printed
    v_per_m: Printed
    v_self: Printed
    v_buoyancy: Printed
    vd: Printed
    la: Printed  # Md/Vd, m


def section_forces(m_reaction: Printed, w_reaction: Printed, full: Printed, be: Printed, weight: SelfWeight,
                   water: WeightRow) -> SectionForces:
    m_full = put(MOMENT, d(m_reaction) * d(full))
    m_per_m = put(MOMENT, d(m_full) / d(be))
    m_self, m_buoyancy = put(MOMENT, -d(weight.m)), put(MOMENT, -d(water.m))
    md = MOMENT.total((m_per_m, m_self, m_buoyancy))
    v_full = put(FORCE, d(w_reaction) * d(full))
    v_per_m = put(FORCE, d(v_full) / d(be))
    v_self, v_buoyancy = put(FORCE, -d(weight.w)), put(FORCE, -d(water.w))
    vd = FORCE.total((v_per_m, v_self, v_buoyancy))
    if vd.value <= 0:
        raise InputError(f"フーチングの応答値: 設計せん断力 Vd が 0 以下で、せん断スパンを求められません（{vd.value} kN）")
    return SectionForces(m_reaction, m_full, m_per_m, m_self, m_buoyancy, md, w_reaction, v_full, v_per_m, v_self,
                         v_buoyancy, vd, put(LENGTH, d(md) / d(vd)))


@dataclass(frozen=True)
class FoundationStep:
    """One row of the step table of the direct foundation (pipeline.aggrese.FOUNDATION_STEPS_COLUMNS)."""

    case_index: int
    case_name: str
    node: int
    step: int  # JRSNAP's output step number, from 1
    v: float
    h: float
    m: float
    qvd: float
    qd: float
    rvd: float
    mmd: float
    plasticity: float


class StepsError(Exception):
    """The step table has no Rvd到達ステップ the footing can use (an error of the result, not of the input)."""


@dataclass(frozen=True)
class SeismicAction:
    """The 地震時 column: V, |H|, |M| of the Rvd到達ステップ of the Case with the largest |M|."""

    case_index: int
    case_name: str
    step: int
    vd: Printed
    hd: Printed
    md: Printed
    rvd: Printed  # JRSNAP's Rvd at that step, kN


def seismic_action(rows: Sequence[FoundationStep]) -> SeismicAction:
    cases: dict[int, list[FoundationStep]] = {}
    for row in rows:
        cases.setdefault(row.case_index, []).append(row)
    candidates = []
    for case_index in sorted(cases):
        reached = next((row for row in sorted(cases[case_index], key=lambda row: row.step) if row.v >= row.rvd),
                       None)
        if reached is None:
            continue
        if reached.v <= 0:
            raise StepsError(f"{reached.case_name} のステップ {reached.step} の鉛直力 V が 0 以下です（{reached.v} kN）")
        candidates.append(SeismicAction(case_index, reached.case_name, reached.step, FORCE(reached.v),
                                        FORCE(abs(reached.h)), MOMENT(abs(reached.m)), FORCE(reached.rvd)))
    if not candidates:
        raise StepsError("どの Case も Rvd到達ステップがありません（V が Rvd に達しません）")
    return max(candidates, key=lambda action: action.md.value)


def _check_direction(name: str) -> CheckDirection:
    from .foundation_check import LONGITUDINAL as along, TRANSVERSE as across
    return along if name == "線路" else across


@dataclass(frozen=True)
class Direction:
    """The plane of bending: the bars of ``name`` (calc.footing_rebar), 0612's basis (B in the plane), the column
    width and the overhangs across the plane (the effective width), and the two overhangs in it."""

    name: str  # 線路 / 直角

    @property
    def check(self) -> CheckDirection:
        return _check_direction(self.name)

    def across(self, sub: Substructure) -> tuple[Printed, Printed, Printed]:
        """(column width, overhang, overhang) across the plane of bending, m."""
        return (sub.w[6], sub.w[7], sub.w[9]) if self.name == "線路" else (sub.b[6], sub.b[7], sub.b[9])

    def along(self, sub: Substructure) -> tuple[tuple[str, Printed, Printed], ...]:
        """(name, L1, cover depth) of the 起点側 and the 終点側 overhang in the plane of bending."""
        lengths = (sub.b[7], sub.b[9]) if self.name == "線路" else (sub.w[7], sub.w[9])
        return (("起点側", lengths[0], sub.df1), ("終点側", lengths[1], sub.df2))


LONGITUDINAL = Direction("線路")
TRANSVERSE = Direction("直角")


@dataclass(frozen=True)
class Buoyancy:
    """5) 浮力 at the three water levels of the input."""

    high: WeightRow  # hw1
    normal: WeightRow  # hw2
    low: WeightRow  # hw3


@dataclass(frozen=True)
class OverhangSide:
    """One overhang in the plane of bending: its length, cover depth, self weight and buoyancy per metre."""

    name: str  # 起点側 / 終点側
    length: Printed  # L1
    cover_depth: Printed  # df
    weight: SelfWeight
    water: Buoyancy


@dataclass(frozen=True)
class FootingBasis:
    """What 0800 reads of one direction before the analyses: 0612's basis, where to read the reactions, the bars,
    the effective width and the overhangs (an input outside it is an input error before any runner)."""

    direction: str  # 線路 / 直角
    check: CheckBasis
    node: int  # the support node of the frame
    pickups: Mapping[str, int]  # the extraction number of each non-seismic column, by its key
    rebar: FootingReinforcement
    width: EffectiveWidth
    sides: tuple[OverhangSide, OverhangSide]


def prepare(pier: PierInput, foundation: FoundationResult, frame_result: FrameResult,
            direction: Direction) -> FootingBasis:
    check = prepare_check(pier, foundation, frame_result, direction.check)
    rebar = footing_reinforcement(pier, direction.name)
    sub = pier.substructure
    column, left, right = direction.across(sub)
    # the effective depth to the centroid of the tensile bars (owner, decision 68); one layer: its centre
    width = effective_width(column, left, right, sub.h[6], rebar.main.centroid)
    sides = tuple(
        OverhangSide(name, length, cover_depth,
                     self_weight(cover_depth, sub.h[6], length, sub.unit_weight_overburden, sub.unit_weight_footing),
                     Buoyancy(*(buoyancy(water, length) for water in (sub.hw1, sub.hw2, sub.hw3))))
        for name, length, cover_depth in direction.along(sub))
    numbers = {extraction.group: extraction.number for extraction in frame_result.extractions}
    pickups = {spec.key: numbers[spec.group] for spec in COLUMNS if spec.group is not None}
    return FootingBasis(direction.name, check, check.node, pickups, rebar, width, sides)


@dataclass(frozen=True)
class OverhangForces:
    """3) 6) 7) of one column on one overhang."""

    side: str
    segments: tuple[ReactionSegment, ...]
    w: Printed  # kN/m, the sum of the segments
    m: Printed  # kN m/m
    forces: SectionForces


@dataclass(frozen=True)
class ColumnSource:
    """Where a column's actions come from: a reaction pickup and its combination, or a Case and its step."""

    pickup: int | None
    combination: int | None
    case_index: int | None
    case_name: str | None
    step: int | None
    rvd: Printed | None


@dataclass(frozen=True)
class FootingColumn:
    key: str
    limit: str
    detail: str
    source: ColumnSource
    vd: Printed
    hd: Printed
    md: Printed
    factors: Factors
    water: str
    uplift: str
    capacity: Capacity
    alpha_b: Printed
    distribution: Distribution
    sides: tuple[OverhangForces, OverhangForces]
    chosen: int  # the side taken: the larger Md, the 起点側 when equal

    @property
    def forces(self) -> SectionForces:
        return self.sides[self.chosen].forces


@dataclass(frozen=True)
class FootingDirection:
    basis: FootingBasis
    columns: tuple[FootingColumn, ...]  # in the order of COLUMNS

    def column(self, key: str) -> FootingColumn:
        return next(column for column in self.columns if column.key == key)


def complete(basis: FootingBasis, reactions: Reactions, steps: Sequence[FoundationStep]) -> FootingDirection:
    """The five columns from the support reactions (``ReactionError`` when a pickup is missing) and the step table
    (``StepsError`` when no Case reaches Rvd)."""
    seismic = seismic_action(steps)
    columns = []
    for spec in COLUMNS:
        if spec.group is None:
            source = ColumnSource(None, None, seismic.case_index, seismic.case_name, seismic.step, seismic.rvd)
            vd, hd, md = seismic.vd, seismic.hd, seismic.md
        else:
            reaction = pick(reactions, basis.pickups[spec.key], spec.focus)
            source = ColumnSource(basis.pickups[spec.key], reaction.combination, None, None, None, None)
            vd, hd, md = FORCE(-reaction.fy), FORCE(abs(reaction.fx)), MOMENT(abs(reaction.mz))
        label = spec.limit + (f" {spec.detail}" if spec.detail else "")
        capacity = bearing_capacity(basis.check, spec.factors, getattr(basis.check, spec.water), vd, hd, md,
                                    f"フーチングの応答値（{label}）")
        alpha_b = shape_alpha(capacity.b_effective, basis.check.l)
        dist = distribution(vd, md, capacity.ex, basis.check.b, basis.check.l, capacity.qd_unlimited, capacity.mmd)
        sides = []
        for side in basis.sides:
            segments = ground_reaction(dist, side.length)
            w = LINE_LOAD.total(segment.w for segment in segments)
            m = MOMENT_PER_M.total(segment.m for segment in segments)
            forces = section_forces(m, w, basis.width.full, basis.width.be, side.weight,
                                    getattr(side.water, spec.uplift))
            sides.append(OverhangForces(side.name, segments, w, m, forces))
        chosen = 0 if sides[0].forces.md.value >= sides[1].forces.md.value else 1
        columns.append(FootingColumn(spec.key, spec.limit, spec.detail, source, vd, hd, md, spec.factors, spec.water,
                                     spec.uplift, capacity, alpha_b, dist, (sides[0], sides[1]), chosen))
    return FootingDirection(basis, tuple(columns))


@dataclass(frozen=True)
class FootingResult:
    """0800: both directions."""

    longitudinal: FootingDirection
    transverse: FootingDirection


@dataclass(frozen=True)
class FootingBases:
    """0800 before the analyses: both directions prepared (an input outside the equations stops here)."""

    longitudinal: FootingBasis
    transverse: FootingBasis


Analyses = tuple[Reactions, Sequence[FoundationStep]]  # (the support reactions, the step table) of one direction


def calculate_footing(pier: PierInput, foundation: FoundationResult, longitudinal_frame: FrameResult,
                      transverse_frame: FrameResult) -> FootingBases:
    """Both directions from the input, 0500 and the frames of 0610 and 0620, before any runner."""
    return FootingBases(prepare(pier, foundation, longitudinal_frame, LONGITUDINAL),
                        prepare(pier, foundation, transverse_frame, TRANSVERSE))


def complete_footing(bases: FootingBases, longitudinal: Analyses, transverse: Analyses) -> FootingResult:
    """Both directions finished with the reactions of their frame analyses and the step tables of their nonlinear
    analyses (``ReactionError`` / ``StepsError`` as ``complete``)."""
    return FootingResult(complete(bases.longitudinal, *longitudinal), complete(bases.transverse, *transverse))
