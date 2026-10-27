"""0612 / 0622 基礎の照査 (decision 54, CONTEXT.md): the direct foundation against the support reactions.

The design response values are the reactions at the spring support of the 0610 / 0620 frame (the centre of the
footing base, NodeRole.FOOTING_BOTTOM), as FEMPython's reaction pickup returns them (ADR-0006): Vd = −fy (the y axis
of the file is downward), Hd = |fx| and Md = |mz|, rounded to their printed digits when they are read. Four columns,
as Example2 08 p.8-30 / 09 p.9-27, by the extraction groups of 0610 / 0620:

- 長期支持 (7) and 短期支持 (8): the combination of the largest Vd and its Hd, Md;
- 安全性 鉛直力最大 (6): the same; 安全性 曲げ最大 (6): the combination of the largest |Md| and its Vd, Hd.

The two directions differ only by their ``Direction``: B is the width of the footing in the plane of the frame
(0500 B along the track, 0500 L across it) and L the other one. The calculation runs in two steps: ``prepare`` from
the input before the frame is analyzed (an input error stops the generation before any runner), then ``check`` with
the reactions.

The equations follow Example2 08 pp.8-27 to 8-32 (鉄道構造物等設計標準・同解説 基礎構造物, 直接基礎) for a sandy
supporting layer, the only one the sample and its workbook (安定計算.xls) have the equations of. Not reproduced from
them (ADR-0001, ADR-0003): ex is used as printed everywhere (8-30 and 8-32 differ in the third decimal), Be is the
smaller of B′ and L (9-27 takes B′ even when it is larger), the long term qd uses the printed γe2, the bearing check
uses the largest pd1 and says so, and Rhb is rounded once. Df is the 0500 表層厚 and γe2 that of the water level of the
column (CONTEXT.md 有効根入れ深さと平均有効単位重量): 長期 the normal water level, 短期 and 安全性 the high one.

``bearing_capacity`` (ex, the effective base, δ, the inclination and shape factors, qvd, the unlimited qd and Mmd of
one set of actions) and ``pick`` (the extreme of a reaction pickup) are shared with the footing's response values
(calc.footing, decision 60).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Protocol

from ..core.errors import InputError
from ..core.printed import AREA, FORCE, LENGTH, MOMENT, Precision, Printed
from ..inputs import PierInput
from ._exact import d, put
from .embedment import CoverWeight, EmbedmentResult, calculate_embedment, cover_weight
from .foundation import FoundationResult
from .frame import Frame, NodeRole
from .longitudinal.combinations import EXTRACTION_NAMES, Extraction, ExtractionGroup

ECCENTRICITY = Precision(3, "m")
ANGLE = Precision(3, "度")
FACTOR = Precision(3, "")
PRESSURE = Precision(2, "kN/m2")
RATIO = Precision(3, "")
_SUPPORT = "地盤データ.層[支持層]"


@dataclass(frozen=True)
class Direction:
    """The plane of the frame: B is the footing width in it, L the width across it."""

    turned: bool  # B = 0500 L (across the track) instead of 0500 B

    def widths(self, foundation: FoundationResult) -> tuple[Printed, Printed]:
        """(B, L), m."""
        return (foundation.l, foundation.b) if self.turned else (foundation.b, foundation.l)


LONGITUDINAL = Direction(False)  # 0612: B = 7.000, L = 9.000 for Example2
TRANSVERSE = Direction(True)  # 0622: B = 9.000, L = 7.000


class Requirement(Enum):
    LONG_TERM = "long_term"  # 長期支持
    SHORT_TERM = "short_term"  # 短期支持
    SAFETY = "safety"  # 安全性


class Focus(Enum):
    VERTICAL = "fy"  # the combination of the largest Vd
    MOMENT = "mz"  # the combination of the largest |Md|


@dataclass(frozen=True)
class ColumnSpec:
    key: str
    name: str
    requirement: Requirement
    group: ExtractionGroup
    focus: Focus


COLUMNS = (ColumnSpec("long_term", "長期支持", Requirement.LONG_TERM, ExtractionGroup.SUPPORT_LONG_TERM,
                      Focus.VERTICAL),
           ColumnSpec("short_term", "短期支持", Requirement.SHORT_TERM, ExtractionGroup.SUPPORT_SHORT_TERM,
                      Focus.VERTICAL),
           ColumnSpec("safety_vertical", "安全性（鉛直力最大）", Requirement.SAFETY, ExtractionGroup.STABILITY,
                      Focus.VERTICAL),
           ColumnSpec("safety_moment", "安全性（曲げ最大）", Requirement.SAFETY, ExtractionGroup.STABILITY, Focus.MOMENT))


@dataclass(frozen=True)
class Factors:
    """The factors of one requirement (Example2 08 pp.8-27, 8-30, 8-32 and 安定計算.xls)."""

    gamma_i: Printed  # 構造物係数 of the vertical checks
    gamma_a: Printed  # 構造解析係数 of the vertical checks
    f_gamma: Printed  # frγ
    f_q: Printed  # frq
    f_s: Printed  # frs, horizontal
    gamma_i_horizontal: Printed  # γi of the horizontal check (1.0 in every column of 8-32: owner 2026-10-18)


def _f(text: str) -> Printed:
    """A constant with the digits it is written with ("0.33" → 2 decimals)."""
    exponent = Decimal(text).as_tuple().exponent
    assert isinstance(exponent, int)
    return Printed(float(text), -exponent, "")


# 地盤抵抗係数 frγ = frq of 長期 0.33, 短期 0.5, 安全性 0.67 and frs 0.33; γi・γa 1.0 for the bearing and 1.2 for
# the safety checks (基礎標準 直接基礎; the sample's values, 8-30 and 8-32).
FACTORS = {
    Requirement.LONG_TERM: Factors(_f("1.0"), _f("1.0"), _f("0.33"), _f("0.33"), _f("0.33"), _f("1.0")),
    Requirement.SHORT_TERM: Factors(_f("1.0"), _f("1.0"), _f("0.50"), _f("0.50"), _f("0.33"), _f("1.0")),
    Requirement.SAFETY: Factors(_f("1.2"), _f("1.2"), _f("0.67"), _f("0.67"), _f("0.33"), _f("1.0")),
}
# The limit of ex for the rotation of the bearing checks: B/6 for 長期, B/4 for 短期 (8-30).
ROTATION_DIVISOR = {Requirement.LONG_TERM: 6, Requirement.SHORT_TERM: 4}


@dataclass(frozen=True)
class GroundKind:
    """The ground of the long-term limit of the bearing pressure (8-28), by the soil type of the supporting layer."""

    name: str
    base: Printed  # kN/m2
    with_cover: bool  # + γe2 Df


GROUND_KINDS = (GroundKind("洪積砂礫地盤", Printed(500, 0, "kN/m2"), True),
                GroundKind("洪積砂地盤・沖積砂礫地盤", Printed(300, 0, "kN/m2"), True),
                GroundKind("洪積粘性土地盤", Printed(200, 0, "kN/m2"), False))
# owner 2026-10-18: 砂礫 is 洪積砂礫地盤, 砂質土 洪積砂地盤・沖積砂礫地盤, 粘性土 and 互層 洪積粘性土地盤. Only the sandy
# soils have the bearing equation of the sample, so the clayey ones are input errors before this is read.
GROUND_OF_SOIL = {"砂礫": GROUND_KINDS[0], "砂質土": GROUND_KINDS[1]}


class FrameResult(Protocol):
    """What the check reads of the result of 0610 or 0620: its frame and its extraction cases."""

    @property
    def frame(self) -> Frame: ...

    @property
    def extractions(self) -> Sequence[Extraction]: ...


@dataclass(frozen=True)
class Basis:
    """What the check reads before the frame is analyzed: the footing, the ground and where to read the reactions."""

    b: Printed  # B, in the plane of the frame
    l: Printed  # L
    depth: Printed  # Df
    friction_angle: Printed  # φ of the supporting layer
    gamma_e1: Printed  # γe1, 支持層の水中
    embedment: EmbedmentResult
    normal: CoverWeight  # γe2 at the normal water level (長期)
    high: CoverWeight  # γe2 at the high water level (短期, 安全性)
    n_gamma: Printed
    n_q: Printed
    soil_type: str
    ground: GroundKind
    long_term_limit: Printed  # the upper limit of qd for 長期
    node: int | None  # the support node of the frame; None without one (the seismic footing alone, decision 110)
    pickups: Mapping[str, int]  # the pickup (extraction) number of each column, by its key; none without a frame


@dataclass(frozen=True)
class SupportReaction:
    """One extreme of a reaction pickup at the support node, as FEMPython returns it (y downward, kN and kN m)."""

    combination: int
    fx: float
    fy: float
    mz: float


class ReactionError(Exception):
    """The reactions FEMPython returned have no extreme the check reads."""


# Each extreme (largest, smallest) of a pickup at the support node, by (pickup number, focus component).
Reactions = Mapping[tuple[int, str], tuple[SupportReaction, SupportReaction]]


@dataclass(frozen=True)
class Judged:
    value: Printed | None  # None: no value (Mmd ≦ 0)
    ok: bool


@dataclass(frozen=True)
class Column:
    """One column of the vertical (8-30) and horizontal (8-32) tables."""

    key: str
    requirement: Requirement
    pickup: int
    combination: int
    vd: Printed
    hd: Printed
    md: Printed
    ex: Printed  # Md/Vd
    b_effective: Printed  # B′ = B − 2ex
    area_effective: Printed  # A′ = B′L
    delta: Printed  # δ = tan⁻¹(Hd/Vd), 度
    triangular: bool  # ex > B/6: the pressure is a triangle
    width_loaded: Printed  # x: B, or 3(B/2 − ex)
    pd1: Printed
    pd2: Printed
    gamma_e2: Printed
    i_gamma: Printed  # (1 − δ/φ)², not below 0
    i_q: Printed  # (1 − δ/90)²
    beta_b: Printed  # 0.5 − 0.2(B′/L), B′/L as L/B′ when B′ > L
    b_e: Printed  # min(B′, L)
    factors: Factors
    term_gamma: Printed  # frγ Iγ βb Be γe1 Nγ
    term_q: Printed  # frq Iq γe2 Df (Nq − 1)
    qvd: Printed
    qd_unlimited: Printed  # qvd + γe2 Df
    qd: Printed  # 長期: not above its limit
    rvd: Printed | None  # A′qvd + γe2 Df A′, 安全性 only
    bearing: Judged | None  # γi γa pd1/qd ≦ 1.0, 長期・短期
    vertical: Judged | None  # γi γa Vd/Rvd ≦ 1.0, 安全性
    rotation_limit: Printed | None  # B/6 or B/4, 長期・短期
    rotation_ex: Judged | None  # γi γa ex/limit ≦ 1.0, 長期・短期
    mmd: Printed | None  # Vd B/2 (1 − Vd/(qd B L)), 安全性
    rotation_moment: Judged | None  # γi γa Md/Mmd ≦ 1.0, 安全性
    rhb: Printed  # frs Vd tanφ
    horizontal: Judged  # γi Hd/Rhd ≦ 1.0

    @property
    def judgements(self) -> tuple[Judged, ...]:
        return tuple(item for item in (self.bearing, self.vertical, self.rotation_ex, self.rotation_moment,
                                       self.horizontal) if item is not None)


@dataclass(frozen=True)
class FoundationCheckResult:
    basis: Basis
    columns: tuple[Column, ...]
    engineering_status: str  # "ok" when every check of every column is satisfied, else "not_ok" (decision 54)


def prepare(pier: PierInput, foundation: FoundationResult, frame_result: FrameResult | None,
            direction: Direction) -> Basis:
    """Everything of the check but the reactions; an input outside it is an input error, before any analysis. Without
    *frame_result* (the seismic footing alone, decision 110) there is no support node and no pickup."""
    support = pier.soil.support
    ground = GROUND_OF_SOIL.get(support.soil_type)
    if ground is None:
        raise InputError(f"{_SUPPORT}.土質区分: 基礎の照査は砂質土・砂礫だけに対応します（入力 {support.soil_type}）")
    if support.unit_weight_submerged is None:
        raise InputError(f"{_SUPPORT}.単位体積重量.水中: 基礎の照査の γe1 に必要です")
    embedment = calculate_embedment(pier, foundation)
    b, l = direction.widths(foundation)
    normal, high = (cover_weight(embedment, water) for water in (pier.substructure.hw2, pier.substructure.hw1))
    limit = (put(PRESSURE, d(ground.base) + d(normal.unit_weight) * d(embedment.depth)) if ground.with_cover
             else PRESSURE(ground.base.value))
    numbers = {} if frame_result is None else {extraction.group: extraction.number
                                               for extraction in frame_result.extractions}
    return Basis(b=b, l=l, depth=embedment.depth, friction_angle=foundation.friction_angle,
                 gamma_e1=support.unit_weight_submerged, embedment=embedment, normal=normal, high=high,
                 n_gamma=foundation.n_gamma, n_q=foundation.n_q, soil_type=support.soil_type, ground=ground,
                 long_term_limit=limit,
                 node=None if frame_result is None else frame_result.frame.node(NodeRole.FOOTING_BOTTOM).number,
                 pickups={} if frame_result is None else {spec.key: numbers[spec.group] for spec in COLUMNS})


def pick(reactions: Reactions, pickup: int, focus: Focus) -> SupportReaction:
    """The extreme of *pickup* at the support node the column reads: the largest Vd (the smallest fy) or the largest
    |Md|. The largest Vd is looked for on every row of the pickup (its fy, mz and fx extremes: FEMPython's fy rows
    carry one of the two variants of a combination, the horizontal force in either direction; 12.1 使用性), and rows
    with the same fy give the one with the larger |Md|, then the larger |Hd| (decision 60, owner 2026-10-19)."""
    try:
        largest, smallest = reactions[(pickup, focus.value)]
    except KeyError as exc:
        raise ReactionError(f"支点の反力のピックアップ {pickup}（{focus.value}）がありません") from exc
    if focus is Focus.VERTICAL:  # the largest Vd = −fy is the smallest fy
        rows = [row for component in ("fy", "mz", "fx") if (pickup, component) in reactions
                for row in reactions[(pickup, component)]]
        return min(rows, key=lambda row: (row.fy, -abs(row.mz), -abs(row.fx)))
    return smallest if abs(smallest.mz) > abs(largest.mz) else largest


def _judged(value: Decimal, precision: Precision = RATIO) -> Judged:
    printed = put(precision, value)
    return Judged(printed, printed.value <= 1.0)


@dataclass(frozen=True)
class Capacity:
    """The bearing capacity of one set of actions at the footing base (8-30), before the checks of a column."""

    ex: Printed  # Md/Vd
    b_effective: Printed  # B′ = B − 2ex
    area_effective: Printed  # A′ = B′L
    delta: Printed  # δ = tan⁻¹(Hd/Vd), 度
    gamma_e2: Printed
    i_gamma: Printed  # (1 − δ/φ)², not below 0
    i_q: Printed  # (1 − δ/90)²
    beta_b: Printed  # 0.5 − 0.2(B′/L), B′/L as L/B′ when B′ > L
    b_e: Printed  # min(B′, L)
    term_gamma: Printed  # frγ Iγ βb Be γe1 Nγ
    term_q: Printed  # frq Iq γe2 Df (Nq − 1)
    qvd: Printed
    qd_unlimited: Printed  # qvd + γe2 Df
    mmd: Printed  # Vd B/2 (1 − Vd/(qd B L)) with the unlimited qd


def bearing_capacity(basis: Basis, factors: Factors, cover: CoverWeight, vd: Printed, hd: Printed, md: Printed,
                     name: str = "基礎の照査", extraction: ExtractionGroup | None = None) -> Capacity:
    """The capacity of the actions *vd*, *hd*, *md* with the 地盤抵抗係数 of *factors* and the cover soil *cover*
    (8-30 and 安定計算.xls); the footing's columns use it too (decision 60). Actions outside the equations (Vd upward,
    ex outside the footing) are input errors naming *name*; Vd = 0 of the actions of *extraction* names it: a load model
    may leave an extraction group without a combination, the zero case (decision 70)."""
    if vd.value == 0 and extraction is not None:
        raise InputError(f"{name}: 抽出ケース「{EXTRACTION_NAMES[extraction]}」の鉛直力 Vd が0です（該当する組合せがなく、"
                         "断面力0のケースです）")
    if vd.value <= 0:
        raise InputError(f"{name}: フーチング底面の鉛直力 Vd が上向きです（{vd.value} kN）")
    b, l = d(basis.b), d(basis.l)
    ex = put(ECCENTRICITY, d(md) / d(vd))
    if d(ex) * 2 >= b:
        raise InputError(f"{name}: 合力の作用位置 ex＝{ex.value} m がフーチングの外にあり、照査できません")
    b_eff = put(LENGTH, b - 2 * d(ex))
    area = put(AREA, d(b_eff) * l)
    delta = ANGLE(math.degrees(math.atan2(hd.value, vd.value)))
    gamma_e2, depth = cover.unit_weight, basis.depth
    i_gamma = put(FACTOR, max(1 - d(delta) / d(basis.friction_angle), Decimal(0)) ** 2)
    i_q = put(FACTOR, (1 - d(delta) / 90) ** 2)
    ratio = d(b_eff) / l if b_eff.value <= basis.l.value else l / d(b_eff)
    beta_b = put(FACTOR, Decimal("0.5") - Decimal("0.2") * ratio)
    b_e = b_eff if b_eff.value <= basis.l.value else basis.l
    term_gamma = put(PRESSURE, d(factors.f_gamma) * d(i_gamma) * d(beta_b) * d(b_e) * d(basis.gamma_e1)
                     * d(basis.n_gamma))
    term_q = put(PRESSURE, d(factors.f_q) * d(i_q) * d(gamma_e2) * d(depth) * (d(basis.n_q) - 1))
    qvd = put(PRESSURE, d(term_gamma) + d(term_q))
    qd_unlimited = put(PRESSURE, d(qvd) + d(gamma_e2) * d(depth))
    mmd = put(MOMENT, d(vd) * b / 2 * (1 - d(vd) / (d(qd_unlimited) * b * l)))
    return Capacity(ex, b_eff, area, delta, gamma_e2, i_gamma, i_q, beta_b, b_e, term_gamma, term_q, qvd,
                    qd_unlimited, mmd)


def _column(basis: Basis, spec: ColumnSpec, reaction: SupportReaction) -> Column:
    factors = FACTORS[spec.requirement]
    vd, hd, md = FORCE(-reaction.fy), FORCE(abs(reaction.fx)), MOMENT(abs(reaction.mz))
    cover = basis.normal if spec.requirement is Requirement.LONG_TERM else basis.high
    capacity = bearing_capacity(basis, factors, cover, vd, hd, md, f"基礎の照査（{spec.name}）", spec.group)
    b, l = d(basis.b), d(basis.l)
    ex, b_eff, area, delta = capacity.ex, capacity.b_effective, capacity.area_effective, capacity.delta
    triangular = d(ex) * 6 > b
    if triangular:
        width = put(LENGTH, 3 * (b / 2 - d(ex)))
        pd1, pd2 = put(PRESSURE, 2 * d(vd) / (3 * l * (b / 2 - d(ex)))), PRESSURE(0)
    else:
        width = basis.b
        pd1, pd2 = (put(PRESSURE, d(vd) / (b * l) * (1 + sign * 6 * d(ex) / b)) for sign in (1, -1))
    gamma_e2, depth = capacity.gamma_e2, basis.depth
    i_gamma, i_q, beta_b, b_e = capacity.i_gamma, capacity.i_q, capacity.beta_b, capacity.b_e
    term_gamma, term_q, qvd, qd_unlimited = capacity.term_gamma, capacity.term_q, capacity.qvd, capacity.qd_unlimited
    long_term = spec.requirement is Requirement.LONG_TERM
    qd = (basis.long_term_limit if long_term and basis.long_term_limit.value < qd_unlimited.value
          else qd_unlimited)
    gamma = d(factors.gamma_i) * d(factors.gamma_a)
    rhb = put(FORCE, d(factors.f_s) * d(vd) * Decimal(repr(math.tan(math.radians(basis.friction_angle.value)))))
    horizontal = _judged(d(factors.gamma_i_horizontal) * d(hd) / d(rhb))
    if spec.requirement is Requirement.SAFETY:
        rvd = put(FORCE, d(area) * d(qvd) + d(gamma_e2) * d(depth) * d(area))
        mmd = capacity.mmd  # qd is the unlimited one for 安全性
        moment = _judged(gamma * d(md) / d(mmd)) if mmd.value > 0 else Judged(None, False)
        return Column(spec.key, spec.requirement, basis.pickups[spec.key], reaction.combination, vd, hd, md, ex,
                      b_eff, area, delta, triangular, width, pd1, pd2, gamma_e2, i_gamma, i_q, beta_b, b_e, factors,
                      term_gamma, term_q, qvd, qd_unlimited, qd, rvd, None, _judged(gamma * d(vd) / d(rvd)), None,
                      None, mmd, moment, rhb, horizontal)
    limit = put(LENGTH, b / ROTATION_DIVISOR[spec.requirement])
    return Column(spec.key, spec.requirement, basis.pickups[spec.key], reaction.combination, vd, hd, md, ex, b_eff,
                  area, delta, triangular, width, pd1, pd2, gamma_e2, i_gamma, i_q, beta_b, b_e, factors, term_gamma,
                  term_q, qvd, qd_unlimited, qd, None, _judged(gamma * d(pd1) / d(qd)), None, limit,
                  _judged(gamma * d(ex) / d(limit)), None, None, rhb, horizontal)


def check(basis: Basis, reactions: Reactions) -> FoundationCheckResult:
    """The four columns from the reactions at the support node (``ReactionError`` when a pickup is missing)."""
    columns = tuple(_column(basis, spec, pick(reactions, basis.pickups[spec.key], spec.focus)) for spec in COLUMNS)
    ok = all(judged.ok for column in columns for judged in column.judgements)
    return FoundationCheckResult(basis, columns, "ok" if ok else "not_ok")
