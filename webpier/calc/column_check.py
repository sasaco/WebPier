"""0611 柱の断面照査 (decision 48, ADR-0008): what Capacita is given to check the column bottom along the track.

Capacita (RcDan) calculates and prints the checks; WebPier decides only the conditions (CONTEXT.md 柱の断面照査):

- the check point: the column bottom, the J end of the column member of the 0610 frame (the member of region COLUMN
  that ends at the footing top), found from the roles of the frame, not from a member number;
- the section: b = W6 across the plane of bending and h = B6 in it, mm;
- the bars from the 方向別の鉄筋配置表 of the bending direction 線路 (calc.column_rebar): the rows of the 線路 main
  bars are the main bars of the upper and lower faces (one or more equal layers), the rows between them the side
  bars (one size, one bar on each face at each centre), and the 線路 hoop row that contains the column base the
  shear reinforcement. Anything else cannot be written to the WDJ and is an input error naming its path; detail
  positions are accepted only as the generated bars of the current basic input (the same rule as the JRSNAP export);
- f'ck of the column concrete and its Dmax (鉄筋.柱.aggregate_max_mm);
- the 柱の断面照査 conditions of the input, shared by both directions;
- the extraction case of each check from the 0610 extraction groups (decision 48): Capacita's rows by id;
- the safety factors of each limit state, fsu of each grade, kr and k4: named program constants with their sources.

The result is what the report prints of the conditions and what the WDJ is written from (export.capacita); the
checks themselves, their values and their judgement are Capacita's (ADR-0008).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput, choices
from ._exact import d, put
from .column_rebar import (YIELD_STRENGTH, ColumnLayout, TableRow, check_detail_positions, column_layout, table,
                           yield_strength)
from .frame import Frame, Member, NodeRole, Region
from .longitudinal import LongitudinalResult
from .longitudinal.combinations import ExtractionGroup

_COLUMN = "鉄筋.柱"
_CHECK = "柱の断面照査"
_FACE = "線路"  # 0611: bending in the plane of the track, so the faces normal to Y carry the main bars
_SIDE = "直角"
LENGTH_MM = Precision(1, "mm")


def _factor(text: str) -> Printed:
    """A factor with the digits it is written with ("1.05" → 2 decimals)."""
    value = Decimal(text)
    return Printed(float(value), max(0, -value.as_tuple().exponent), "")


@dataclass(frozen=True)
class SafetyFactors:
    """One row of Capacita's safety factor table (WDJ safety.safety_factor), by its limit state id."""

    id: int
    title: str
    m_rc: Printed | None  # bending: γc
    m_rs: Printed | None  # bending: γs
    m_rbs: Printed | None  # bending: γb
    v_rc: Printed | None  # shear: γc
    v_rs: Printed | None  # shear: γs
    v_rbc: Printed | None  # shear: γb of Vcd
    v_rbs: Printed | None  # shear: γb of Vsd
    v_rbv: Printed | None  # shear: γb of Vwcd
    t_rbt: Printed | None  # torsion: γb (torsion is not checked)
    ri: Printed  # γi
    range: int  # Capacita's range of the material factors (1 serviceability, 2 safety, 3 restorability)


def _row(id_: int, title: str, values: str, range_: int) -> SafetyFactors:
    m_rc, m_rs, m_rbs, v_rc, v_rs, v_rbc, v_rbs, v_rbv, t_rbt, ri = (
        None if text == "-" else _factor(text) for text in values.split())
    assert ri is not None
    return SafetyFactors(id_, title, m_rc, m_rs, m_rbs, v_rc, v_rs, v_rbc, v_rbs, v_rbv, t_rbt, ri, range_)


# RC標準（鉄道構造物等設計標準・同解説 コンクリート構造物、平成16年）の安全係数, as Capacita's railway rows (WebDan
# RcBusinessEditor) and the sample 08_線路/WebDan.wdj have them, by limit state:
#        γc(M) γs(M) γb(M) γc(V) γs(V) γb(Vcd) γb(Vsd) γb(Vwcd) γb(T) γi
# 復旧性（地震時以外）の γi は 1.2 (曲げ・せん断とも; owner 2026-10-18: the 1.0 of the sample's 8-25 is an error,
# ADR-0001), but 1.0 for JR東日本 (JR_EAST_SAFETY_FACTORS: Capacita's default exception, WebDanforJS
# safety-factors-material-strengths.service.ts). γb(T) is the sample's; torsion is not checked (decision 48).
SAFETY_FACTORS = (
    _row(0, "耐久性, 使用性", "1.0 1.0 1.0 1.0 1.0 1.0 1.0 - 1.0 1.0", 1),
    _row(2, "安全性（疲労破壊）", "1.3 1.05 1.0 1.3 1.05 1.3 1.0 - 1.0 1.1", 2),
    _row(5, "安全性（破壊）", "1.3 1.0 1.1 1.3 1.0 1.3 1.1 1.2 1.0 1.2", 2),
    _row(6, "復旧性（損傷）地震時以外", "1.3 1.0 1.0 1.3 1.0 1.3 1.1 1.2 1.0 1.2", 3),
    _row(7, "復旧性（損傷）地震時", "1.3 1.0 1.0 1.3 1.0 1.3 1.0 1.2 1.0 1.0", 3),
    _row(8, "最小鉄筋量", "1.3 1.0 1.0 - - - - - - 1.0", 3),
)
JR_EAST_SAFETY_FACTORS = tuple(
    _row(6, factors.title, "1.3 1.0 1.0 1.3 1.0 1.3 1.1 1.2 1.0 1.0", 3) if factors.id == 6 else factors
    for factors in SAFETY_FACTORS)
SAFETY_FACTORS_OF_BODY = {"運輸機構": SAFETY_FACTORS, "JR各社": SAFETY_FACTORS, "JR東日本": JR_EAST_SAFETY_FACTORS}
# kr: 変動作用の頻度の影響を考慮するための係数, 一般に0.5 (RC標準; the sample 8-21)
KR = _factor("0.5")
# k4: 曲げひび割れの変動を考慮する係数 (RC標準; the sample 8-19, 0.85)
K4 = _factor("0.85")
# fsu: the lower limit of the tensile strength of each grade, N/mm2 (JIS G 3112; Capacita's grade presets)
_TENSILE = {"SD295": 440, "SD345": 490, "SD390": 560}

# The extraction case of each of Capacita's rows (WDJ basic.pickup_*), by row id; None leaves the row blank
# (decision 48: fatigue, the seismic restorability and the minimum reinforcement are not checked).
MOMENT_CASES: tuple[tuple[int, ExtractionGroup | None], ...] = (
    (0, ExtractionGroup.PERMANENT_VARIABLE),  # 耐久性 縁引張応力度検討用
    (1, ExtractionGroup.PERMANENT),  # 耐久性（永久作用）
    (2, None), (3, None), (4, None),  # 安全性（疲労破壊）
    (5, ExtractionGroup.FAILURE),  # 安全性（破壊）
    (6, ExtractionGroup.DAMAGE),  # 復旧性（損傷）地震時以外
    (7, None),  # 復旧性（損傷）地震時
    (8, None),  # 最小鉄筋量
)
SHEAR_CASES: tuple[tuple[int, ExtractionGroup | None], ...] = (
    (0, ExtractionGroup.PERMANENT_VARIABLE),  # 耐久性 せん断ひび割れ検討判定用
    (1, ExtractionGroup.PERMANENT),  # 耐久性（永久作用）
    (2, ExtractionGroup.VARIABLE),  # 耐久性（変動作用）
    (3, None), (4, None),  # 安全性（疲労破壊）
    (5, ExtractionGroup.FAILURE),  # 安全性（破壊）
    (6, ExtractionGroup.DAMAGE),  # 復旧性（損傷）地震時以外
    (7, None),  # 復旧性（損傷）地震時
)
TORSION_CASES: tuple[tuple[int, ExtractionGroup | None], ...] = ((0, None), (1, None), (5, None), (6, None),
                                                                 (7, None))


def tensile_strength(grade: str) -> Printed:
    """fsu of a grade of choices.STEEL_GRADES (JIS G 3112)."""
    return YIELD_STRENGTH.exact(_TENSILE[grade])


@dataclass(frozen=True)
class Steel:
    grade: str
    fsy: Printed  # N/mm2
    fsu: Printed  # N/mm2


@dataclass(frozen=True)
class MainBars:
    """The main bars of one face (WDJ rebar1 upper / rebar2 lower), outermost layer first."""

    diameter: Printed  # mm
    per_layer: int
    layers: int
    count: int  # all layers
    cover: Printed  # centre of the outermost layer from the face, mm
    layer_spacing: Printed | None  # centre to centre of the layers, mm; None for one layer
    spacing: Printed  # along the face, mm


@dataclass(frozen=True)
class SideBars:
    """The side bars of both side faces (WDJ sidebar1): one bar on each face at each centre."""

    diameter: Printed  # mm
    count: int  # on one face
    first: Printed  # centre of the first from the upper face, mm
    spacing: Printed | None  # centre to centre, mm; None for one


@dataclass(frozen=True)
class Hoops:
    """The hoop row of the bending direction at the column base (WDJ stirrup)."""

    diameter: Printed  # mm
    legs: int  # 有効本数
    pitch: Printed  # mm


@dataclass(frozen=True)
class ColumnCheckResult:
    member: int  # the column member of the 0610 frame
    length: Printed  # its length, m: the check point is its J end (the column bottom)
    width: Printed  # b, mm
    depth: Printed  # h, mm
    upper: MainBars
    lower: MainBars
    side: SideBars | None
    hoops: Hoops
    main_steel: Steel
    side_steel: Steel | None
    hoop_steel: Steel
    fck: Printed  # N/mm2
    aggregate_max: Printed  # Dmax, mm
    environment: str  # 鋼材の腐食に対する環境条件
    environment_number: int  # 1 一般の環境, 2 腐食性環境, 3 特に厳しい腐食性環境 (Capacita con)
    appearance: bool  # 外観の照査
    ecsd: Printed  # ε'csd, ×10⁻⁶
    body: str  # 適用基準の機関
    jr001: bool
    jr004: bool
    moment_cases: tuple[tuple[int, int | None], ...]  # (Capacita row id, extraction case number)
    shear_cases: tuple[tuple[int, int | None], ...]
    torsion_cases: tuple[tuple[int, int | None], ...]
    safety: tuple[SafetyFactors, ...]
    kr: Printed
    k4: Printed


def _need(value, path: str):
    if value is None:
        raise InputError(f"{path}: 値が必要です")
    return value


def _column_member(frame: Frame) -> Member:
    footing_top = frame.node(NodeRole.FOOTING_TOP).number
    (member,) = [member for member in frame.members if member.region is Region.COLUMN and member.end == footing_top]
    assert not member.offset.value, f"member {member.number}: the column is vertical in every frame"
    return member


def _steel(grade: str) -> Steel:
    return Steel(grade, yield_strength(grade), tensile_strength(grade))


def _one(values: set, path: str, what: str):
    if len(values) != 1:
        raise InputError(f"{path}: {what}が1種類ではありません（{'・'.join(sorted(map(str, values)))}）")
    (value,) = values
    return value


def _spacing(centres: list[Printed], path: str, what: str) -> Printed | None:
    gaps = {put(LENGTH_MM, d(second) - d(first)) for first, second in zip(centres, centres[1:])}
    if len(gaps) > 1:
        raise InputError(f"{path}: {what}の間隔が一定ではないため表せません")
    return next(iter(gaps), None)


def _face(layers: list[TableRow], depth: Printed | None, pitch: Printed) -> MainBars:
    """One face's layers, outermost first; *depth* measures the centres from the lower face."""
    path = f"{_COLUMN}.main_rows"
    kind = _one({(row.diameter, row.count, row.material) for row in layers}, path,
                f"{_FACE}の主鉄筋の段の径・本数・材質")
    centres = [row.center if depth is None else put(LENGTH_MM, d(depth) - d(row.center)) for row in layers]
    diameter, count, _ = kind
    return MainBars(diameter=diameter, per_layer=count, layers=len(layers), count=count * len(layers),
                    cover=centres[0], layer_spacing=_spacing(centres, path, f"{_FACE}の主鉄筋の段"), spacing=pitch)


def _main(layout: ColumnLayout, rows: tuple[TableRow, ...]) -> tuple[MainBars, MainBars, str]:
    path = f"{_COLUMN}.main_rows"
    face_rows = [row for row in layout.rows if row.direction == _FACE]
    if not face_rows:
        raise InputError(f"{path}: {_FACE}の主鉄筋の行が必要です")
    indices = {row.index for row in face_rows}
    main = table((bar for bar in layout.automatic if indices.intersection(bar.rows)), _FACE)
    layers = len(face_rows)
    if len(main) != 2 * layers or rows[:layers] != main[:layers] or rows[-layers:] != main[-layers:]:
        raise InputError(f"{path}: {_FACE}方向の表の先頭・末尾{layers}行が{_FACE}の主鉄筋と一致しません"
                         "（主鉄筋より外側や段の間にある鉄筋、同じ段への混在は表せません）")
    pitches = {row.pitch for row in face_rows}
    if None in pitches or len(pitches) != 1:
        raise InputError(f"{path}: {_FACE}の主鉄筋の間隔が一つに定まりません"
                         "（1本や両端2本だけの行、行ごとに異なる間隔は表せません）")
    (pitch,) = pitches
    grade = _one({row.material for row in main}, path, "主鉄筋の材質")
    return (_face(list(main[:layers]), None, pitch), _face(list(reversed(main[-layers:])), layout.height, pitch),
            grade)


def _side(rows: tuple[TableRow, ...]) -> tuple[SideBars, str] | None:
    if not rows:
        return None
    path = f"{_COLUMN}.main_rows"
    diameter, grade = _one({(row.diameter, row.material) for row in rows}, path, "側方鉄筋の径・材質")
    if any(row.count != 2 for row in rows):
        raise InputError(f"{path}: 側方鉄筋は各芯位置に左右の面で1本ずつだけ表せます（{_SIDE}の多段は表せません）")
    centres = [row.center for row in rows]
    return SideBars(diameter=diameter, count=len(rows), first=centres[0],
                    spacing=_spacing(centres, path, "側方鉄筋")), grade


def _hoops(pier: PierInput) -> tuple[Hoops, str]:
    column = pier.rebar.column
    path = f"{_COLUMN}.column_hoops.direction_rows"
    rows = [(index, row) for index, row in enumerate(column.hoops.rows)
            if row.direction == _FACE and (row.start is None or row.start.value == 0)]
    if len(rows) != 1:
        raise InputError(f"{path}: {_FACE}の帯鉄筋で柱下端を含む行がちょうど1行必要です（{len(rows)}行）")
    ((index, row),) = rows
    here = f"{path}[{index}]"
    grade = row.material or column.materials.transverse
    if grade is None:
        raise InputError(f"{here}.material: 値が必要です（行と{_COLUMN}.materials.transverse が空欄）")
    return Hoops(diameter=_need(row.diameter, f"{here}.diameter_mm"), legs=_need(row.effective_legs,
                 f"{here}.effective_legs"), pitch=_need(row.pitch, f"{here}.pitch_mm")), grade


def _cases(cases, numbers: Mapping[ExtractionGroup, int]) -> tuple[tuple[int, int | None], ...]:
    return tuple((id_, None if group is None else numbers[group]) for id_, group in cases)


def calculate_column_check(pier: PierInput, longitudinal: LongitudinalResult) -> ColumnCheckResult:
    member = _column_member(longitudinal.frame)
    layout = column_layout(pier)
    check_detail_positions(layout)
    rows = table(layout.bars, _FACE)
    upper, lower, main_grade = _main(layout, rows)
    side = _side(rows[upper.layers:len(rows) - lower.layers])
    hoops, hoop_grade = _hoops(pier)
    conditions = pier.column_check
    environment = _need(conditions.environment, f"{_CHECK}.鋼材の腐食に対する環境条件")
    appearance = _need(conditions.appearance, f"{_CHECK}.外観の照査")
    ecsd = _need(conditions.ecsd, f"{_CHECK}.ε'csd")
    body = _need(conditions.body, f"{_CHECK}.適用基準の機関")
    jr001 = _need(conditions.jr001, f"{_CHECK}.JR-001")
    jr004 = _need(conditions.jr004, f"{_CHECK}.JR-004")
    numbers = {extraction.group: extraction.number for extraction in longitudinal.extractions}
    return ColumnCheckResult(
        member=member.number, length=member.height, width=layout.width, depth=layout.height,
        upper=upper, lower=lower, side=None if side is None else side[0], hoops=hoops,
        main_steel=_steel(main_grade), side_steel=None if side is None else _steel(side[1]),
        hoop_steel=_steel(hoop_grade), fck=longitudinal.frame.materials.column.strength,
        aggregate_max=_need(pier.rebar.column.aggregate_max, f"{_COLUMN}.aggregate_max_mm"),
        environment=environment, environment_number=choices.CORROSION_ENVIRONMENTS.index(environment) + 1,
        appearance=appearance == choices.APPEARANCE_CHECKED, ecsd=ecsd, body=body,
        jr001=jr001 == choices.ADOPTED, jr004=jr004 == choices.ADOPTED,
        moment_cases=_cases(MOMENT_CASES, numbers), shear_cases=_cases(SHEAR_CASES, numbers),
        torsion_cases=_cases(TORSION_CASES, numbers), safety=SAFETY_FACTORS_OF_BODY[body], kr=KR, k4=K4)
