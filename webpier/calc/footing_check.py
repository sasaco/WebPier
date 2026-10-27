"""0810 / 0820 フーチングの断面照査 (decision 60, CONTEXT.md, ADR-0008): what Capacita is given to check the overhang.

Capacita (RcDan) calculates and prints the checks; WebPier decides only the conditions, from the input and the
response values of 0800 (calc.footing). The two directions differ only by the FootingDirection they are given:

- the point: the overhang at the column face, 1 m of width by H6 (部材 フーチング, 下側引張, N′d 0), named 線路方向 or
  線路直角方向; Capacita keeps one shear span per point, so the WDJ (export.capacita.footing_wdj) writes the 安全性 and
  耐久性 checks at one point with the safety La and the 復旧性（地震時） checks at a second point with the seismic La;
- the bars: the lower main bars and the stirrups of the direction (calc.footing_rebar), the upper face has none
  (the sample 12_フーチング.pdf 255: 圧縮鉄筋 −), no side bars;
- the forces: 安全性（破壊） the safety column (Md最大 or Vd最大) with the larger Md, its Md, Vd and La (the sample
  takes Vd最大: 760.7 / 675.1 / 1127); 耐久性 the short-term Md (縁引張 under 永久＋変動) and the long-term Md (永久作用);
  復旧性（地震時） the 地震時 column's Md, Vd, La. La is Md/Vd in mm, as Capacita reads it;
- the materials: the footing's grades, f'ck and Dmax (鉄筋.フーチング; the footing concrete's Dmax, owner 2026-10-19), fsu of
  each grade (calc.column_check);
- the 柱の断面照査 conditions of the input (環境条件, ε'csd, 機関, JR-001/004; the appearance check is not made), the
  safety factors of the body, kr and k4: the same constants as 0611.

The sections asked of Capacita's report are the five of the sample (12.2〜12.4) and the minimum and maximum
reinforcement of the long-term Md (the row 8, decision 73): 耐久性 shear is not asked for (面部材のため省略, the report
prints the sample's sentence), 使用性（外観） and 使用性（損傷） are not given forces. Only the sections of the parts 0800
made are asked for (decision 110): 安全性, 耐久性 and the rebar amount with the frame analyses, 復旧性（地震時） with the
nonlinear ones.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput, choices
from ._exact import d, put
from .column_check import K4, KR, SAFETY_FACTORS_OF_BODY, SafetyFactors, Steel, tensile_strength
from .column_rebar import yield_strength
from .footing import FootingColumn, FootingDirection
from .footing_rebar import MainBars, Stirrups

_CHECK = "柱の断面照査"
MEMBER = "フーチング"
NAMES = {"線路": "線路方向", "直角": "線路直角方向"}
LENGTH_MM = Precision(0, "mm")
WIDTH = LENGTH_MM(1000)  # the overhang per metre of width
REPORT_SECTIONS = ("bending_safety_destruction", "shear_safety_destruction", "bending_durability",
                   "bending_restorability_eq", "shear_restorability_eq", "bending_rebar_amount")
# the sections of the seismic part (decision 110); the others are those of the frame analyses
SEISMIC_SECTIONS = frozenset(("bending_restorability_eq", "shear_restorability_eq"))


@dataclass(frozen=True)
class Forces:
    """The design forces of one check: the 0800 column they come from, Md, and for a shear check Vd and La."""

    column: str  # the key of the 0800 column
    md: Printed  # kN m
    vd: Printed | None  # kN
    la: Printed | None  # mm


@dataclass(frozen=True)
class FootingCheckResult:
    direction: str  # 線路 / 直角
    name: str  # 線路方向 / 線路直角方向, the point's name
    member: str
    width: Printed  # mm
    depth: Printed  # mm, H6
    bars: MainBars
    stirrups: Stirrups
    main_steel: Steel
    stirrup_steel: Steel
    fck: Printed
    aggregate_max: Printed
    environment: str
    environment_number: int
    ecsd: Printed
    body: str
    jr001: bool
    jr004: bool
    safety: Forces | None  # these three None without the frame analyses (decision 110)
    durability_short: Forces | None
    durability_long: Forces | None
    seismic: Forces | None  # None without the nonlinear analyses
    safety_factors: tuple[SafetyFactors, ...]
    kr: Printed
    k4: Printed

    @property
    def sections(self) -> tuple[str, ...]:
        """The sections of Capacita's report this check asks for, in report order: those of the parts it has."""
        return tuple(section for section in REPORT_SECTIONS
                     if (self.seismic if section in SEISMIC_SECTIONS else self.safety) is not None)


def _need(value, path: str):
    if value is None:
        raise InputError(f"{path}: 値が必要です")
    return value


def _steel(grade: str) -> Steel:
    return Steel(grade, yield_strength(grade), tensile_strength(grade))


def _forces(column: FootingColumn | None, with_shear: bool) -> Forces | None:
    if column is None:
        return None
    forces = column.forces
    if not with_shear:
        return Forces(column.key, forces.md, None, None)
    return Forces(column.key, forces.md, forces.vd, put(LENGTH_MM, d(forces.la) * 1000))


def calculate_footing_check(pier: PierInput, footing: FootingDirection) -> FootingCheckResult:
    """The check of the overhang of the direction of *footing* (0800's result of that direction), of the parts it has."""
    rebar = footing.basis.rebar
    candidates = [column for column in (footing.column("safety_moment"), footing.column("safety_shear")) if column]
    safety = max(candidates, key=lambda column: column.forces.md.value) if candidates else None
    conditions = pier.column_check
    environment = _need(conditions.environment, f"{_CHECK}.水掛かりの程度")
    ecsd = _need(conditions.ecsd, f"{_CHECK}.ε'csd")
    body = _need(conditions.body, f"{_CHECK}.適用基準の機関")
    jr001 = _need(conditions.jr001, f"{_CHECK}.JR-001")
    jr004 = _need(conditions.jr004, f"{_CHECK}.JR-004")
    return FootingCheckResult(
        direction=footing.basis.direction, name=NAMES[footing.basis.direction], member=MEMBER, width=WIDTH,
        depth=put(LENGTH_MM, d(pier.substructure.h[6]) * 1000), bars=rebar.main, stirrups=rebar.stirrups,
        main_steel=_steel(rebar.main.grade), stirrup_steel=_steel(rebar.stirrups.grade), fck=rebar.fck,
        aggregate_max=_need(pier.rebar.footing.aggregate_max, "鉄筋.フーチング.aggregate_max_mm"),
        environment=environment, environment_number=choices.WATER_EXPOSURES.index(environment) + 1, ecsd=ecsd,
        body=body, jr001=jr001 == choices.ADOPTED, jr004=jr004 == choices.ADOPTED,
        safety=_forces(safety, True), durability_short=_forces(footing.column("short_term"), False),
        durability_long=_forces(footing.column("long_term"), False), seismic=_forces(footing.column("seismic"), True),
        safety_factors=SAFETY_FACTORS_OF_BODY[body], kr=KR, k4=K4)
