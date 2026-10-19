"""0910 片持ち梁の断面照査 (decision 59, ADR-0008): what Capacita is given to check the beam at the column face.

Capacita (RcDan) calculates and prints the checks; WebPier decides the conditions (CONTEXT.md 片持ち梁の照査):

- the member: the beam, b = B1 and h = H2 + H3 at the column face, mm; one point, 柱前面, checked for bending about
  z, shear in y and torsion, with the shear span a = the farthest bearing on either cantilever from the column face;
- the bars of 鉄筋.梁 (decision 59): the 上 and 下 main rows (one or more layers of one size, the outermost layer's
  centre as the cover, the layer centres equally spaced; the spacing along the face (B1 − 2 c)/(n − 1) with c the
  side bars' centre from the side face, else the cover), one side row (on both side faces, from its start at its
  pitch) and one band row (the stirrups: diameter, effective legs, pitch). What the WDJ cannot hold is an input error
  naming its path;
- f'ck and Dmax of the beam concrete (鉄筋.梁);
- the 片持ち梁の照査 conditions: the corrosion environment of each face, the appearance check, the trains of the
  fatigue check (the equivalent repetitions per train of the input; SA/SC = SB/SC = 1.0 and γ1 = 1.0 for the main
  bars and 0.65 for the bent stirrups are program constants), and ε'csd from 0900's cracking moment;
- the standard body and JR-001 / JR-004 of 柱の断面照査 (one pier), the safety factors of 0611 (with γb of torsion
  1.0), kr and k4;
- the section forces: 0900's governing case of each check (combinations.Selection), Md negative to Capacita.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...core.errors import InputError
from ...core.printed import LENGTH, Precision, Printed
from ...inputs import PierInput, choices
from ...inputs.fields import BEAM_SURFACES
from ...inputs.rebar import BeamBars, BeamMainRow
from .._exact import d, put
from ..column_check import (K4, KR, LENGTH_MM, SAFETY_FACTORS_OF_BODY, Hoops, MainBars, SafetyFactors, SideBars, Steel,
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
            "torsion_restorability", "bending_restorability_eq", "shear_restorability_eq", "torsion_restorability_eq")
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
    environment_numbers: dict[str, int]  # Capacita's con: 1 一般の環境, 2 腐食性環境, 3 特に厳しい腐食性環境
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


def _one(values: set, path: str, what: str):
    if len(values) != 1:
        raise InputError(f"{path}: {what}が1種類ではありません（{'・'.join(sorted(map(str, values)))}）")
    (value,) = values
    return value


def _centre(row: BeamMainRow, index: int, previous: Printed | None, beam: BeamBars, stirrup: Printed) -> Printed:
    path = f"{_BEAM}.main_rows[{index}]"
    mode = _need(row.cover_mode, f"{path}.cover_mode")
    if mode == choices.COVER_SPECIFIED:
        return _need(row.center, f"{path}.center_mm")
    diameter = _need(row.diameter, f"{path}.diameter_mm")
    if previous is None:
        pure = _need(beam.pure_cover, f"{_BEAM}.pure_cover_mm")
        return put(LENGTH_MM, d(pure) + d(stirrup) + d(diameter) / 2)
    gap = _need(row.clear_gap, f"{path}.clear_gap_mm")
    return put(LENGTH_MM, d(previous) + d(gap) + d(diameter))


def _face(beam: BeamBars, face: str, width_mm: Printed, side_cover: Printed | None, stirrup: Printed
          ) -> tuple[MainBars, str]:
    rows = [(index, row) for index, row in enumerate(beam.main_rows) if row.face == face]
    path = f"{_BEAM}.main_rows"
    if not rows:
        raise InputError(f"{path}: 面「{face}」の主鉄筋の行が必要です")
    layers = sorted(_need(row.layer, f"{path}[{index}].layer") for index, row in rows)
    if layers != list(range(1, len(rows) + 1)):
        raise InputError(f"{path}: 面「{face}」の段は 1 から順に1行ずつ必要です（{'・'.join(map(str, layers))}）")
    rows.sort(key=lambda item: item[1].layer)
    diameter = _one({_need(row.diameter, f"{path}[{index}].diameter_mm") for index, row in rows}, path,
                    f"面「{face}」の主鉄筋の径")
    grade = _one({row.material or beam.materials.main for _, row in rows}, path, f"面「{face}」の主鉄筋の材質")
    if grade is None:
        raise InputError(f"{path}: 面「{face}」の主鉄筋の材質が必要です（行と{_BEAM}.materials.main が空欄）")
    counts = [_need(row.count, f"{path}[{index}].count") for index, row in rows]
    centres: list[Printed] = []
    for index, row in rows:
        centres.append(_centre(row, index, centres[-1] if centres else None, beam, stirrup))
    gaps = {put(LENGTH_MM, d(second) - d(first)) for first, second in zip(centres, centres[1:])}
    if len(gaps) > 1:
        raise InputError(f"{path}: 面「{face}」の段の間隔が一定ではないため表せません")
    if counts[0] < 2:
        raise InputError(f"{path}: 面「{face}」の1段目は2本以上が必要です")
    edge = side_cover if side_cover is not None else centres[0]
    spacing = put(LENGTH_MM, (d(width_mm) - 2 * d(edge)) / (counts[0] - 1))
    return MainBars(diameter=diameter, per_layer=counts[0], layers=len(rows), count=sum(counts), cover=centres[0],
                    layer_spacing=next(iter(gaps), None), spacing=spacing), grade


def _side(beam: BeamBars) -> tuple[SideBars, str, Printed | None] | None:
    path = f"{_BEAM}.side_rows"
    if not beam.side_rows:
        return None
    if len(beam.side_rows) != 1:
        raise InputError(f"{path}: 側面筋は1行だけ表せます（{len(beam.side_rows)}行）")
    row, here = beam.side_rows[0], f"{path}[0]"
    grade = row.material or beam.materials.main
    if grade is None:
        raise InputError(f"{here}.material: 値が必要です（行と{_BEAM}.materials.main が空欄）")
    if row.columns not in (None, 1):
        raise InputError(f"{here}.columns: 側面筋は1列だけ表せます（{row.columns}列）")
    count = _need(row.per_face_count, f"{here}.per_face_count")
    centre = row.center if row.cover_mode == choices.COVER_SPECIFIED else None
    return (SideBars(diameter=_need(row.diameter, f"{here}.diameter_mm"), count=count,
                     first=_need(row.start, f"{here}.start_mm"),
                     spacing=_need(row.pitch, f"{here}.pitch_mm") if count > 1 else None), grade, centre)


def _stirrups(beam: BeamBars) -> tuple[Hoops, str]:
    path = f"{_BEAM}.band_rows"
    if len(beam.band_rows) != 1:
        raise InputError(f"{path}: スターラップの行がちょうど1行必要です（{len(beam.band_rows)}行）")
    row, here = beam.band_rows[0], f"{path}[0]"
    grade = row.material or beam.materials.transverse
    if grade is None:
        raise InputError(f"{here}.material: 値が必要です（行と{_BEAM}.materials.transverse が空欄）")
    if row.legs_mode != choices.LEGS_MODES[1]:
        raise InputError(f"{here}.legs_mode: 有効本数は「{choices.LEGS_MODES[1]}」で入力してください")
    return Hoops(diameter=_need(row.diameter, f"{here}.diameter_mm"), legs=_need(row.effective_legs,
                 f"{here}.effective_legs"), pitch=_need(row.pitch, f"{here}.pitch_mm")), grade


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
    width = put(LENGTH_MM, d(s.b[1]) * 1000)
    depth = put(LENGTH_MM, (d(s.h[2]) + d(s.h[3])) * 1000)
    stirrups, stirrup_grade = _stirrups(beam)
    side = _side(beam)
    side_cover = None if side is None else side[2]
    upper, main_grade = _face(beam, "上", width, side_cover, stirrups.diameter)
    lower, lower_grade = _face(beam, "下", width, side_cover, stirrups.diameter)
    grade = _one({main_grade, lower_grade}, f"{_BEAM}.main_rows", "主鉄筋の材質")
    conditions, column = pier.cantilever_check, pier.column_check
    environments = {face: _need(conditions.environments[face], f"{_CHECK}.鋼材の腐食に対する環境条件.{face}")
                    for face in BEAM_SURFACES}
    appearance = _need(conditions.appearance, f"{_CHECK}.外観の照査")
    body = _need(column.body, f"{_COLUMN_CHECK}.適用基準の機関")
    jr001 = _need(column.jr001, f"{_COLUMN_CHECK}.JR-001")
    jr004 = _need(column.jr004, f"{_COLUMN_CHECK}.JR-004")
    span = max((bearing.x for result in cantilever.sides.values() for bearing in result.geometry.bearings),
               key=lambda x: x.value)
    return CantileverSectionResult(
        width=width, depth=depth, shear_span=put(LENGTH, d(span)), upper=upper, lower=lower,
        side=None if side is None else side[0], stirrups=stirrups, main_steel=_steel(grade),
        side_steel=None if side is None else _steel(side[1]), stirrup_steel=_steel(stirrup_grade),
        fck=pier.materials.beam, aggregate_max=_need(beam.aggregate_max, f"{_BEAM}.aggregate_max_mm"),
        environments=environments,
        environment_numbers={face: choices.CORROSION_ENVIRONMENTS.index(name) + 1 for face, name in environments.items()},
        appearance=appearance == choices.APPEARANCE_CHECKED, ecsd=cantilever.cracking.ecsd, body=body,
        jr001=jr001 == choices.ADOPTED, jr004=jr004 == choices.ADOPTED, fatigue=_fatigue(pier),
        safety=SAFETY_FACTORS_OF_BODY[body], kr=KR, k4=K4, selections=cantilever.selections,
        cracking=cantilever.cracking)
