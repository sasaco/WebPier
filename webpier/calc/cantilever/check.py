"""0910 片持ち梁の断面照査 (decision 59, ADR-0008): what Capacita is given to check the beam at the column face.

Capacita (RcDan) calculates and prints the checks; WebPier decides the conditions (CONTEXT.md 片持ち梁の照査):

- the member: the beam, b = B1 and h = H2 + H3 at the column face, mm; one point, 柱前面, checked for bending about
  z, shear in y and torsion, with the shear span a = the farthest bearing on either cantilever from the column face;
- the bars of 鉄筋.梁 (decisions 59, 68) as calc.beam_rebar places them: each face's main bars (its layers, their
  cover, layer spacing and spacing along the face) and the side bars; the stirrups' diameter, effective legs and
  pitch. The main and side bars are of the member's main steel, the stirrups of its transverse steel. What the WDJ
  cannot hold is an input error naming its path;
- f'ck and Dmax of the beam concrete (鉄筋.梁);
- the 片持ち梁の照査 conditions: the 水掛かりの程度 of each face, the appearance check, the trains of the
  fatigue check (the equivalent repetitions per train of the input; SA/SC = SB/SC = 1.0 and γ1 = 1.0 for the main
  bars and 0.65 for the bent stirrups are program constants), and ε'csd from 0900's cracking moment;
- the standard body and JR-001 / JR-004 of 柱の断面照査 (one pier), the safety factors of 0611 (with γb of torsion
  1.3, R5), kr and k4;
- the section forces: 0900's governing case of each check (combinations.Selection), Md negative to Capacita.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.errors import InputError
from ...core.printed import LENGTH, Precision, Printed
from ...inputs import PierInput, choices
from ...inputs.fields import BEAM_SURFACES
from ...inputs.rebar import BeamBars
from .._exact import d, put
from ..beam_rebar import beam_layout, beam_section
from ..column_check import (K4, KR, SAFETY_FACTORS_OF_BODY, Hoops, MainBars, SafetyFactors, SideBars, Steel,
                            tensile_strength)
from ..column_rebar import yield_strength
from . import CantileverResult
from .combinations import Quantity, Selection
from .crack import Cracking

_BEAM = "鉄筋.梁"
_CHECK = "片持ち梁の照査"
_COLUMN_CHECK = "柱の断面照査"
MEMBER, MEMBER_NAME, POINT_NAME = 1, "片持ち梁", "柱前面"
RATIO = Precision(2, "")
# Capacita's report sections of the beam check (RcDan VerificationResultPrinter.SectionIds), in report order; the
# appearance check only when asked for. Every row of the force table is written, so every check is asked for.
SECTIONS = ("bending_safety_destruction", "shear_safety_destruction", "torsion_safety_destruction",
            "bending_safety_fatigue", "shear_safety_fatigue", "bending_durability", "shear_durability",
            "torsion_durability", "bending_serviceability", "bending_restorability", "shear_restorability",
            "torsion_restorability", "bending_restorability_eq", "shear_restorability_eq", "torsion_restorability_eq",
            "bending_rebar_amount")
SA_RATIO = RATIO.exact(1.0)  # SA/SC: the A train is the standard train
SB_RATIO = RATIO.exact(1.0)
GAMMA1_MAIN = RATIO.exact(1.0)  # γ1 of the main bars: no joint, no bend
GAMMA1_STIRRUP = RATIO.exact(0.65)  # γ1 of the bent stirrups (RC標準: 曲げ加工 0.65)


@dataclass(frozen=True)
class Fatigue:
    passenger_trains: int  # A列車, per track per day
    freight_trains: int  # B列車
    service_life: int  # years
    na06: Printed  # equivalent repetitions per A train, k = 0.06
    na12: Printed
    nb06: Printed
    nb12: Printed
    sa_ratio: Printed  # SA/SC
    sb_ratio: Printed
    gamma1_main: Printed
    gamma1_stirrup: Printed


@dataclass(frozen=True)
class CantileverSectionResult:
    width: Printed  # b = B1, mm
    depth: Printed  # h = H2 + H3, mm
    shear_span: Printed  # a, m
    upper: MainBars
    lower: MainBars
    side: SideBars | None
    stirrups: Hoops
    main_steel: Steel
    side_steel: Steel | None
    stirrup_steel: Steel
    fck: Printed
    aggregate_max: Printed
    environments: dict[str, str]  # by face: 上面, 下面, 側面
    environment_numbers: dict[str, int]  # Capacita's con: 1 常時乾燥, 2 乾湿繰返し, 3 常時湿潤
    appearance: bool
    ecsd: Printed  # ×10⁻⁶, from 0900's cracking moment
    body: str
    jr001: bool
    jr004: bool
    fatigue: Fatigue
    safety: tuple[SafetyFactors, ...]
    kr: Printed
    k4: Printed
    selections: tuple[Selection, ...]  # the governing case of each check (0900)
    cracking: Cracking  # the cracking moment and ε'csd of 0900 (13.5 (1))

    @property
    def sections(self) -> tuple[str, ...]:
        return tuple(section for section in SECTIONS if section != "bending_serviceability" or self.appearance)

    def selection(self, row: int, quantity: Quantity) -> Selection | None:
        return next((item for item in self.selections if item.row == row and item.quantity == quantity), None)


def _need(value, path: str):
    if value is None:
        raise InputError(f"{path}: 値が必要です")
    return value


def _stirrups(beam: BeamBars) -> Hoops:
    stirrups, path = beam.stirrups, f"{_BEAM}.stirrups"
    return Hoops(diameter=_need(stirrups.diameter, f"{path}.diameter_mm"),
                 legs=_need(stirrups.effective_legs, f"{path}.effective_legs"),
                 pitch=_need(stirrups.pitch, f"{path}.pitch_mm"))


def _steel(grade: str) -> Steel:
    return Steel(grade, yield_strength(grade), tensile_strength(grade))


def _fatigue(pier: PierInput) -> Fatigue:
    trains = pier.cantilever_check.fatigue
    path = f"{_CHECK}.疲労"
    repetitions = {key: _need(value, f"{path}.等価繰返し回数.{key[0]}.{key[1]}") for key, value in trains.repetitions.items()}
    return Fatigue(passenger_trains=_need(trains.passenger_trains, f"{path}.旅客列車本数"),
                   freight_trains=_need(trains.freight_trains, f"{path}.貨物列車本数"),
                   service_life=_need(trains.service_life, f"{path}.設計耐用年数"),
                   na06=repetitions[("A列車", "k=0.06")], na12=repetitions[("A列車", "k=0.12")],
                   nb06=repetitions[("B列車", "k=0.06")], nb12=repetitions[("B列車", "k=0.12")],
                   sa_ratio=SA_RATIO, sb_ratio=SB_RATIO, gamma1_main=GAMMA1_MAIN, gamma1_stirrup=GAMMA1_STIRRUP)


def calculate_cantilever_section(pier: PierInput, cantilever: CantileverResult) -> CantileverSectionResult:
    """The beam check Capacita is given, from the input and 0900's result."""
    s, beam = pier.substructure, pier.rebar.beam
    width, depth = beam_section(s.b[1], s.h[2], s.h[3])
    stirrups = _stirrups(beam)
    main_grade = _need(beam.materials.main, f"{_BEAM}.materials.main")
    stirrup_grade = _need(beam.materials.transverse, f"{_BEAM}.materials.transverse")
    layout = beam_layout(beam, width, depth)
    upper, lower, side = layout.faces["上"], layout.faces["下"], layout.side
    conditions, column = pier.cantilever_check, pier.column_check
    environments = {face: _need(conditions.environments[face], f"{_CHECK}.水掛かりの程度.{face}")
                    for face in BEAM_SURFACES}
    appearance = _need(conditions.appearance, f"{_CHECK}.外観の照査")
    body = _need(column.body, f"{_COLUMN_CHECK}.適用基準の機関")
    jr001 = _need(column.jr001, f"{_COLUMN_CHECK}.JR-001")
    jr004 = _need(column.jr004, f"{_COLUMN_CHECK}.JR-004")
    span = max((bearing.x for result in cantilever.sides.values() for bearing in result.geometry.bearings),
               key=lambda x: x.value)
    return CantileverSectionResult(
        width=width, depth=depth, shear_span=put(LENGTH, d(span)), upper=upper, lower=lower,
        side=side, stirrups=stirrups, main_steel=_steel(main_grade),
        side_steel=None if side is None else _steel(main_grade), stirrup_steel=_steel(stirrup_grade),
        fck=pier.materials.beam, aggregate_max=_need(beam.aggregate_max, f"{_BEAM}.aggregate_max_mm"),
        environments=environments,
        environment_numbers={face: choices.WATER_EXPOSURES.index(name) + 1 for face, name in environments.items()},
        appearance=appearance == choices.APPEARANCE_CHECKED, ecsd=cantilever.cracking.ecsd, body=body,
        jr001=jr001 == choices.ADOPTED, jr004=jr004 == choices.ADOPTED, fatigue=_fatigue(pier),
        safety=SAFETY_FACTORS_OF_BODY[body], kr=KR, k4=K4, selections=cantilever.selections,
        cracking=cantilever.cracking)
