"""0810 / 0820 フーチングの断面照査 of a pile foundation (decision 96, ADR-0008): what Capacita is given to check the footing.

Capacita (RcDan) calculates and prints the checks; WebPier decides only the conditions, from the input and the section
forces of 0800 (``calc.pile_footing``). The footing is checked at six points of the WDJ (``export.capacita.pile_footing_wdj``),
each a member of its own because the effective width, the section's width, differs:

- the face (く体前面) and the pile position (杭位置), each for the lower and for the upper tension: the bending checks of
  安全性（破壊）, 耐久性, 復旧性（地震時） and the minimum and maximum rebar amount, with the bars of the face that is in
  tension, per the width of the member (the bars of ``鉄筋.フーチング`` are per 1 m of width);
- the shear: the deep beam checks of 安全性（破壊） and of 復旧性（地震時） (decision 124; the sample V-130, V-131 and
  V-139, V-140), the design shear compression failure capacity Vfdd at the face for the lower tension and the design
  pull-out shear capacity Vsd at the pile position for the upper tension. The widths of the shear (at the face the
  shares of the piles of the nearest row, at the pile position the footing's whole width B, calc.pile_footing) differ
  from the bending's, so each is a point and member of its own with the shear check alone (its bars those of its width).
  No shear of 耐久性 is asked: it is omitted as in the direct footing (面部材).

Only the sections of the parts 0800 made are asked for (decision 110): 復旧性（地震時） with the nonlinear analyses, the
others with the frame analysis.

The materials, the conditions of 柱の断面照査 and the safety factors are those of the direct footing (``calc.footing_check``,
``calc.column_check``).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from ..core.printed import Printed
from ..inputs import PierInput, choices
from ._exact import d, put
from .column_check import K4, KR, SAFETY_FACTORS_OF_BODY, SafetyFactors, Steel
from .footing_check import MEMBER, NAMES, _steel, conditions_of
from .footing_rebar import COUNT, MainBars, Stirrups
from .pile_footing import Case, FootingDirection, Point, SectionForces

REPORT_SECTIONS = ("bending_safety_destruction", "shear_deep_beam_safety_destruction", "bending_durability",
                   "bending_restorability_eq", "shear_deep_beam_restorability_eq", "bending_rebar_amount")
# the sections of the nonlinear analyses (decision 110), the deep beam shear of 復旧性（地震時） with them (decision 124)
SEISMIC_SECTIONS = frozenset(("bending_restorability_eq", "shear_deep_beam_restorability_eq"))
DEEP_BEAM_SECTIONS = frozenset(("shear_deep_beam_safety_destruction", "shear_deep_beam_restorability_eq"))


@dataclass(frozen=True)
class CheckPoint:
    """A point of the WDJ: the section, the bars per its width and the forces of its checks."""

    index: int  # from 1: the point and its member
    point: Point
    lower: MainBars  # the bars of the width of the point (the input's are per 1 m)
    upper: MainBars
    forces: SectionForces


@dataclass(frozen=True)
class PileFootingCheckResult:
    direction: str  # 線路 / 直角
    name: str  # 線路方向 / 線路直角方向
    member: str
    points: tuple[CheckPoint, ...]
    stirrups: Stirrups
    stirrup_spacing: Printed  # b1, mm
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
    safety_factors: tuple[SafetyFactors, ...]
    kr: Printed
    k4: Printed

    @property
    def sections(self) -> tuple[str, ...]:
        """The sections of Capacita's report this check asks for, in report order: those of the parts it has; a section of
        the deep beam shear (shared by the points of Vfdd and Vsd) when a point has a Vd of its case (decision 124: a case
        without a shear of the point's sense gives Capacita none, and Capacita checks nothing of it)."""
        cases = {force.case for item in self.points for force in item.forces.forces}
        sheared = {force.case for item in self.points for force in item.forces.forces if force.vd is not None}
        return tuple(section for section in REPORT_SECTIONS
                     if (Case.SEISMIC if section in SEISMIC_SECTIONS else Case.SAFETY)
                     in (sheared if section in DEEP_BEAM_SECTIONS else cases))

    def sheared(self, case: Case, deep_beam: str) -> bool:
        """Whether a point of the deep beam shear *deep_beam* ("lower_tension" Vfdd / "upper_tension" Vsd) has a Vd of
        *case* (decision 124: without one Capacita checks nothing of it, and the report says it is omitted)."""
        return any(force.vd is not None for item in self.points if item.point.deep_beam == deep_beam
                   for force in item.forces.forces if force.case is case)


def scaled(bars: MainBars, width: Printed) -> MainBars:
    """*bars* (per 1 m of width) for a member of *width* mm: the count of each layer scaled, everything else as it is."""
    factor = d(width) / Decimal(1000)
    return replace(bars, counts=tuple(put(COUNT, d(count) * factor) for count in bars.counts))


def calculate_pile_footing_check(pier: PierInput, footing: FootingDirection) -> PileFootingCheckResult:
    """The check of the footing in the direction of *footing* (0800's result of that direction)."""
    basis = footing.basis
    found = conditions_of(pier)  # also the precheck of 0810 / 0820 (footing_check.check_footing_check_inputs)
    environment, ecsd, body, jr001, jr004 = found.environment, found.ecsd, found.body, found.jr001, found.jr004
    lower, upper = basis.bars
    points = tuple(CheckPoint(index, found.point, scaled(lower, found.point.width.be), scaled(upper, found.point.width.be),
                              found)
                   for index, found in enumerate(footing.points, 1))
    return PileFootingCheckResult(
        direction=basis.direction, name=NAMES[basis.direction], member=MEMBER, points=points, stirrups=basis.stirrups,
        stirrup_spacing=basis.stirrup_spacing, main_steel=_steel(lower.grade), stirrup_steel=_steel(basis.stirrups.grade),
        fck=basis.fck, aggregate_max=found.aggregate_max,
        environment=environment, environment_number=choices.WATER_EXPOSURES.index(environment) + 1, ecsd=ecsd, body=body,
        jr001=jr001 == choices.ADOPTED, jr004=jr004 == choices.ADOPTED, safety_factors=SAFETY_FACTORS_OF_BODY[body],
        kr=KR, k4=K4)
