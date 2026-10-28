"""0611 / 0621 柱の断面照査 (decision 48, ADR-0008): what Capacita is given to check the column bottom.

Capacita (RcDan) calculates and prints the checks; WebPier decides only the conditions (CONTEXT.md 柱の断面照査). The
two directions differ only by their ``Direction`` (LONGITUDINAL for 0611 along the track, TRANSVERSE for 0621 across
it), not by branches:

- the check point: the column bottom, the J end of the column member of the 0610 / 0620 frame (the member of region
  COLUMN that ends at the footing top), found from the roles of the frame, not from a member number;
- the section: b across the plane of bending and h in it, mm (W6 and B6 along the track, B6 and W6 across it);
- the bars from the 方向別の鉄筋配置表 of the bending direction (calc.column_rebar): the rows of that direction's
  main bars are the main bars of the upper and lower faces, the rows between them the side bars (one size), and that
  direction's hoop row that contains the column base the shear reinforcement (decision 103). The layers of a face are
  of one size at equal spacing, with layer 1's count in every layer but the last, which may have fewer (Capacita
  splits the total by layer 1's count: Example4 along the track, D38 23 + 11). The corner bars of the other
  direction's main rows (their end bars at their own cover from the faces) are in layer 1 of the nearer face: a layer
  is counted as bars of the face's size by area (COUNT), at the centre weighted by area (Example4 III-214 across the
  track: D38-2本 + D19-7本). Side bars are written at their centres when one bar of each face is at each centre and
  the centres are equally spaced; otherwise as half of all of them on each face, equally spaced from the first centre
  to the last (the area kept, not where the bars are: Example4's inner layer across the track). Anything else cannot
  be written to the WDJ and is an input error naming its path. The bars are those in use, with the changes made in
  the 方向別の鉄筋配置表 (decision 68);
- f'ck of the column concrete and its Dmax (鉄筋.柱.aggregate_max_mm);
- the 柱の断面照査 conditions of the input, shared by both directions;
- the extraction case of each check from the extraction groups of 0610 / 0620 (decision 48): Capacita's rows by id;
- the safety factors of each limit state, fsu of each grade, kr and k4: named program constants with their sources.

The result is what the WDJ is written from (export.capacita); the checks themselves, their values, their judgement
and the report with its commentary are Capacita's (ADR-0008, decision 121).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput, choices
from ._exact import d, put
from .column_rebar import (YIELD_STRENGTH, Bar, ColumnLayout, MainRows, TableRow, bar_area, column_layout, main_pitch,
                           main_rows, table, yield_strength)
from .frame import Frame, Member, NodeRole, Region
from .longitudinal.combinations import Extraction, ExtractionGroup

_COLUMN = "鉄筋.柱"
_CHECK = "柱の断面照査"
LENGTH_MM = Precision(1, "mm")
COUNT = Precision(2, "本")  # bars counted by area, or side bars spread evenly (decision 103)


@dataclass(frozen=True)
class Direction:
    """A bending direction of the column: whose rows are its main bars and how its section is turned."""

    face: str  # the direction of the main rows and the hoop row of the check (its 方向別の鉄筋配置表)
    side: str  # the other direction: its main rows are the side bars
    turned: bool  # b = B6 (Y) and h = W6 (X), instead of b = W6 and h = B6

    def section(self, layout: ColumnLayout) -> tuple[Printed, Printed]:
        """(b, h) of the section, mm."""
        return (layout.height, layout.width) if self.turned else (layout.width, layout.height)


LONGITUDINAL = Direction("線路", "直角", False)  # 0611: bending in the plane of the track (faces normal to Y)
TRANSVERSE = Direction("直角", "線路", True)  # 0621: bending across the track (faces normal to X)


class FrameResult(Protocol):
    """What the check reads of the result of 0610 or 0620: its frame and its extraction cases."""

    @property
    def frame(self) -> Frame: ...

    @property
    def extractions(self) -> Sequence[Extraction]: ...


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
    v_rbv: Printed | None  # shear: γb of Vdd (RcDan S_Gamma_bd; Vwcd takes γb of Vcd)
    t_rbt: Printed | None  # torsion: γb (not checked of the column)
    ri: Printed  # γi
    range: int  # the axial bars Capacita counts (RcDan ReBarForCalc): 1 the tension bars, 2 and the compression bars, 3 all with the side bars


def _row(id_: int, title: str, values: str, range_: int) -> SafetyFactors:
    m_rc, m_rs, m_rbs, v_rc, v_rs, v_rbc, v_rbs, v_rbv, t_rbt, ri = (
        None if text == "-" else _factor(text) for text in values.split())
    assert ri is not None
    return SafetyFactors(id_, title, m_rc, m_rs, m_rbs, v_rc, v_rs, v_rbc, v_rbs, v_rbv, t_rbt, ri, range_)


# RC標準（鉄道構造物等設計標準・同解説 コンクリート構造物、R5）の安全係数, as WebDanforJS has them by default for the
# railway bodies (safety-factors-material-strengths.service.ts default_safety_factor; decision 73), by limit state:
#        γc(M) γs(M) γb(M) γc(V) γs(V) γb(Vcd) γb(Vsd) γb(Vdd) γb(T) γi
# (WDJ V_rbv is γb of Vdd and Vod in R5: RcDan OrganizedInput S_Gamma_bd; Vwcd takes γb of Vcd.) 使用性（損傷）の γi
# is 1.2 (曲げ・せん断とも), but 1.0 for JR東日本 (JR_EAST_SAFETY_FACTORS: the default's exception for JREast_H16 and
# JREast_R5). Torsion is not checked of the column (decision 48); γb(T) is the default's. The 安全性（破壊） counts all the axial bars,
# the side bars too (range 3; the default's is 2): the R5 sample Example橋脚4 III-139 and III-214 does (decision 105).
SAFETY_FACTORS = (
    _row(0, "耐久性, 使用性", "1.0 1.0 1.0 1.0 1.0 1.0 1.0 - 1.0 1.0", 1),
    _row(2, "安全性（疲労破壊）", "1.3 1.05 1.0 1.3 1.05 1.3 1.0 - - 1.1", 2),
    _row(5, "安全性（破壊）", "1.3 1.0 1.1 1.3 1.0 1.3 1.1 1.2 1.3 1.2", 3),  # all the axial bars (decision 105)
    _row(6, "使用性（損傷）", "1.3 1.0 1.0 1.3 1.0 1.3 1.1 1.2 1.3 1.2", 3),
    _row(7, "復旧性（損傷）地震時", "1.3 1.0 1.0 1.3 1.0 1.3 1.1 1.2 1.3 1.0", 3),
    _row(8, "最小鉄筋量", "1.3 1.0 1.0 - - - - - - 1.0", 3),
)
JR_EAST_SAFETY_FACTORS = tuple(
    _row(6, factors.title, "1.3 1.0 1.0 1.3 1.0 1.3 1.1 1.2 1.3 1.0", 3) if factors.id == 6 else factors
    for factors in SAFETY_FACTORS)
SAFETY_FACTORS_OF_BODY = {"運輸機構": SAFETY_FACTORS, "JR各社": SAFETY_FACTORS, "JR東日本": JR_EAST_SAFETY_FACTORS}
# kr: 変動作用の頻度の影響を考慮するための係数, 一般に0.5 (RC標準; the sample 8-21)
KR = _factor("0.5")
# k4: 曲げひび割れの変動を考慮する係数 (RC標準; the sample 8-19, 0.85)
K4 = _factor("0.85")
# fsu: the lower limit of the tensile strength of each grade, N/mm2 (JIS G 3112; Capacita's grade presets)
_TENSILE = {"SD295": 440, "SD345": 490, "SD390": 560, "SD490": 620}

# The extraction case of each of Capacita's rows (WDJ basic.pickup_*), by row id; None leaves the row blank
# (decision 48: fatigue and the seismic restorability are not checked; decision 73: the minimum and maximum
# reinforcement of the row 8 from the permanent action).
MOMENT_CASES: tuple[tuple[int, ExtractionGroup | None], ...] = (
    (0, ExtractionGroup.PERMANENT_VARIABLE),  # 耐久性 縁引張応力度検討用
    (1, ExtractionGroup.PERMANENT),  # 耐久性（永久作用）
    (2, None), (3, None), (4, None),  # 安全性（疲労破壊）
    (5, ExtractionGroup.FAILURE),  # 安全性（破壊）
    (6, ExtractionGroup.DAMAGE),  # 使用性（損傷）
    (7, None),  # 復旧性（損傷）地震時
    (8, ExtractionGroup.PERMANENT),  # 最小鉄筋量（最大鉄筋量も。決定73）
)
SHEAR_CASES: tuple[tuple[int, ExtractionGroup | None], ...] = (
    (0, ExtractionGroup.PERMANENT_VARIABLE),  # 耐久性 せん断ひび割れ検討判定用
    (1, ExtractionGroup.PERMANENT),  # 耐久性（永久作用）
    (2, ExtractionGroup.VARIABLE),  # 耐久性（変動作用）
    (3, None), (4, None),  # 安全性（疲労破壊）
    (5, ExtractionGroup.FAILURE),  # 安全性（破壊）
    (6, ExtractionGroup.DAMAGE),  # 使用性（損傷）
    (7, None),  # 復旧性（損傷）地震時
)
TORSION_CASES: tuple[tuple[int, ExtractionGroup | None], ...] = ((0, None), (1, None), (5, None), (6, None),
                                                                 (7, None))
# Capacita's report sections (Capacita README「Headless runner の run-rc」), in report order: the section force list
# and the checks this column asks for. 使用性（外観） is checked only with the appearance check (owner: without it
# 0611 has no 8.8, 0621 no 9.8).
REPORT_SECTIONS = ("section_forces", "bending_safety_destruction", "shear_safety_destruction", "bending_durability",
                   "shear_durability", "bending_serviceability", "bending_restorability", "shear_restorability",
                   "bending_rebar_amount")


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
    per_layer: Printed  # COUNT: layer 1, and every layer but the last
    layers: int
    count: Printed  # COUNT: all layers
    cover: Printed  # centre of the outermost layer from the face, mm
    layer_spacing: Printed | None  # centre to centre of the layers, mm; None for one layer
    spacing: Printed  # along the face, mm


@dataclass(frozen=True)
class SideBars:
    """The side bars of both side faces (WDJ sidebar1), equally spaced: Capacita puts ⌈count⌉ centres with
    2·count／⌈count⌉ bars at each (RcDan MemberGroup)."""

    diameter: Printed  # mm
    count: Printed  # COUNT, on one face
    first: Printed  # centre of the first from the upper face, mm
    spacing: Printed | None  # centre to centre, mm; None for one centre


@dataclass(frozen=True)
class Hoops:
    """The hoop row of the bending direction at the column base (WDJ stirrup)."""

    diameter: Printed  # mm
    legs: int  # 有効本数
    pitch: Printed  # mm


@dataclass(frozen=True)
class ColumnCheckResult:
    direction: Direction
    member: int  # the column member of the 0610 / 0620 frame
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
    environment: str  # 水掛かりの程度
    environment_number: int  # 1 常時乾燥, 2 乾湿繰返し, 3 常時湿潤 (Capacita con)
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
    # The number of the commentary group heading of each section of Capacita's report by its id ("8.7", or None), once
    # Capacita has checked the column in the same generation (pipeline.stages, decision 121): Capacita's, not the
    # calculation's; the sections 0400 refers to and 0612 / 0622 follow. None before that, and then not in the JSON.
    headings: Mapping[str, str | None] | None = field(default=None, compare=False, metadata={"json": "set"})

    @property
    def sections(self) -> tuple[str, ...]:
        """The sections of Capacita's report this check asks for, in report order."""
        return tuple(section for section in REPORT_SECTIONS
                     if section != "bending_serviceability" or self.appearance)


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


def _shown(value) -> str:
    """A bar kind of an input error: its size (the Printed) and its steel."""
    parts = value if isinstance(value, tuple) else (value,)
    return " ".join(f"D{part.value:g}" if isinstance(part, Printed) else str(part) for part in parts)


def _one(values: set, path: str, what: str):
    if len(values) != 1:
        raise InputError(f"{path}: {what}が1種類ではありません（{'・'.join(sorted(map(_shown, values)))}）")
    (value,) = values
    return value


def _spacing(centres: list[Printed], path: str, what: str) -> Printed | None:
    gaps = {put(LENGTH_MM, d(second) - d(first)) for first, second in zip(centres, centres[1:])}
    if len(gaps) > 1:
        raise InputError(f"{path}: {what}の間隔が一定ではないため表せません")
    return next(iter(gaps), None)


def _layer(rows: Sequence[TableRow], diameter: Printed, path: str) -> tuple[Printed, Printed]:
    """(count, centre) of the bars of one layer as bars of *diameter*: by area, at the centre weighted by area."""
    areas = [row.count * d(bar_area(row.diameter, path)) for row in rows]
    total = sum(areas)
    centre = sum(area * d(row.center) for area, row in zip(areas, rows)) / total
    return put(COUNT, total / d(bar_area(diameter, path))), put(LENGTH_MM, centre)


def _face(layers: list[TableRow], corner: tuple[TableRow, ...], depth: Printed | None, pitch: Printed,
          face: str) -> MainBars:
    """One face's layers, outermost first, with the *corner* bars in layer 1; *depth* measures the centres from the
    lower face."""
    path = f"{_COLUMN}.main_bars"
    diameter, _ = _one({(row.diameter, row.material) for row in layers}, path, f"{face}の主鉄筋の段の径・材質")
    counts, centres = zip(*(_layer([row, *(corner if index == 0 else ())], diameter, path)
                            for index, row in enumerate(layers)))
    if any(count != counts[0] for count in counts[1:-1]) or counts[-1].value > counts[0].value:
        raise InputError(f"{path}: {face}の主鉄筋の段の本数は、最後の段のほかは1段目と同じ、最後の段は1段目以下でなければ"
                         "表せません")
    centres = [centre if depth is None else put(LENGTH_MM, d(depth) - d(centre)) for centre in centres]
    return MainBars(diameter=diameter, per_layer=counts[0], layers=len(layers),
                    count=put(COUNT, sum(d(count) for count in counts)), cover=centres[0],
                    layer_spacing=_spacing(centres, path, f"{face}の主鉄筋の段"), spacing=pitch)


def _main(main: MainRows, face: str, depth: Printed,
          corners: tuple[tuple[TableRow, ...], tuple[TableRow, ...]]) -> tuple[MainBars, MainBars, str]:
    upper, lower = corners
    layers = main.layers
    grade = _one({row.material for row in (*main.rows, *upper, *lower)}, f"{_COLUMN}.main_bars", "主鉄筋の材質")
    return (_face(list(main.rows[:layers]), upper, None, main.pitch, face),
            _face(list(reversed(main.rows[-layers:])), lower, depth, main.pitch, face), grade)


def corner_bars(layout: ColumnLayout, direction: Direction) -> tuple[tuple[Bar, ...], tuple[Bar, ...]]:
    """The corner bars of the main rows of the other direction, by the nearer face of *direction* (upper, lower): the
    end bars of a row of the other direction that are at the row's own cover from the faces (Example2: the track rows'
    D32 at 108 from both faces) and not in a main row of *direction*."""
    keys = {row.key for row in layout.rows if row.direction == direction.face}
    upper: list[Bar] = []
    lower: list[Bar] = []
    for row in layout.rows:
        if row.direction != direction.side or len(row.positions) < 2 or row.positions[0] != row.center:
            continue
        for bar in layout.bars:
            place = bar.y if direction.face == "線路" else bar.x  # as calc.column_rebar.table
            if row.key in bar.rows and not keys.intersection(bar.rows):
                if place == row.positions[0]:
                    upper.append(bar)
                elif place == row.positions[-1]:
                    lower.append(bar)
    return tuple(upper), tuple(lower)


def _side(rows: tuple[TableRow, ...], side: str) -> tuple[SideBars, str] | None:
    """The side bars of the table rows between the main bars: at their centres when one bar of each face is at each
    and they are equally spaced; otherwise half of all of them on each face, equally spaced from the first centre to
    the last (decision 103: the area kept)."""
    if not rows:
        return None
    path = f"{_COLUMN}.main_bars"
    diameter, grade = _one({(row.diameter, row.material) for row in rows}, path, "側方鉄筋の径・材質")
    centres = [row.center for row in rows]
    gaps = {put(LENGTH_MM, d(second) - d(first)) for first, second in zip(centres, centres[1:])}
    if all(row.count == 2 for row in rows) and len(gaps) <= 1:
        return SideBars(diameter=diameter, count=COUNT.exact(len(rows)), first=centres[0],
                        spacing=next(iter(gaps), None)), grade
    count = Decimal(sum(row.count for row in rows)) / 2
    places = math.ceil(count)  # Capacita's centres (RcDan MemberGroup)
    if len(rows) == 1 and places > 1:
        raise InputError(f"{path}: {side}の側方鉄筋は1つの芯位置にしかなく、間隔をあけて並べられないため表せません")
    spacing = None if places == 1 else put(LENGTH_MM, (d(centres[-1]) - d(centres[0])) / (places - 1))
    return SideBars(diameter=diameter, count=put(COUNT, count), first=centres[0], spacing=spacing), grade


def _hoops(pier: PierInput, face: str) -> tuple[Hoops, str]:
    column = pier.rebar.column
    path = f"{_COLUMN}.column_hoops.direction_rows"
    rows = [(index, row) for index, row in enumerate(column.hoops.rows)
            if row.direction == face and (row.start is None or row.start.value == 0)]
    if len(rows) != 1:
        raise InputError(f"{path}: {face}の帯鉄筋で柱下端を含む行がちょうど1行必要です（{len(rows)}行）")
    ((index, row),) = rows
    here = f"{path}[{index}]"
    grade = _need(column.materials.transverse, f"{_COLUMN}.materials.transverse")
    return Hoops(diameter=_need(row.diameter, f"{here}.diameter_mm"), legs=_need(row.effective_legs,
                 f"{here}.effective_legs"), pitch=_need(row.pitch, f"{here}.pitch_mm")), grade


def _cases(cases, numbers: Mapping[ExtractionGroup, int]) -> tuple[tuple[int, int | None], ...]:
    return tuple((id_, None if group is None else numbers[group]) for id_, group in cases)


def column_bars(layout: ColumnLayout,
                direction: Direction) -> tuple[MainBars, MainBars, tuple[SideBars, str] | None, str]:
    """(upper, lower, (side bars, their steel) or None, the steel of the main bars) of *direction*. A hand-made table
    (decision 111) gives them as written: its first and last N rows the layers of the two faces, the rest the side bars;
    its rows are all the bars, so no corner bar is added."""
    custom = layout.custom.get(direction.face)
    if custom is not None:
        depth = direction.section(layout)[1]
        grade = _one({row.material for row in custom.rows}, f"{_COLUMN}.main_bars", "主鉄筋の材質")
        pitch = main_pitch(layout, direction.face)
        return (_face(list(custom.upper), (), None, pitch, direction.face),
                _face(list(reversed(custom.lower)), (), depth, pitch, direction.face),
                _side(custom.others, direction.side), grade)
    corners = corner_bars(layout, direction)
    corner = {*corners[0], *corners[1]}
    rows = table((bar for bar in layout.bars if bar not in corner), direction.face)
    main = main_rows(layout, rows, direction.face)
    upper, lower, grade = _main(main, direction.face, direction.section(layout)[1],
                                (table(corners[0], direction.face), table(corners[1], direction.face)))
    # the side bars: the rest of the table, between the layers too (decision 108)
    return upper, lower, _side(tuple(row for row in rows if row not in main.rows), direction.side), grade


def calculate_column_check(pier: PierInput, frame_result: FrameResult, direction: Direction) -> ColumnCheckResult:
    """The check of the column bottom in *direction*: LONGITUDINAL from 0610, TRANSVERSE from 0620."""
    member = _column_member(frame_result.frame)
    layout = column_layout(pier)
    width, depth = direction.section(layout)
    upper, lower, side, main_grade = column_bars(layout, direction)
    hoops, hoop_grade = _hoops(pier, direction.face)
    conditions = pier.column_check
    environment = _need(conditions.environment, f"{_CHECK}.水掛かりの程度")
    appearance = _need(conditions.appearance, f"{_CHECK}.外観の照査")
    ecsd = _need(conditions.ecsd, f"{_CHECK}.ε'csd")
    body = _need(conditions.body, f"{_CHECK}.適用基準の機関")
    jr001 = _need(conditions.jr001, f"{_CHECK}.JR-001")
    jr004 = _need(conditions.jr004, f"{_CHECK}.JR-004")
    numbers = {extraction.group: extraction.number for extraction in frame_result.extractions}
    return ColumnCheckResult(
        direction=direction, member=member.number, length=member.height, width=width, depth=depth,
        upper=upper, lower=lower, side=None if side is None else side[0], hoops=hoops,
        main_steel=_steel(main_grade), side_steel=None if side is None else _steel(side[1]),
        hoop_steel=_steel(hoop_grade), fck=frame_result.frame.materials.column.strength,
        aggregate_max=_need(pier.rebar.column.aggregate_max, f"{_COLUMN}.aggregate_max_mm"),
        environment=environment, environment_number=choices.WATER_EXPOSURES.index(environment) + 1,
        appearance=appearance == choices.APPEARANCE_CHECKED, ecsd=ecsd, body=body,
        jr001=jr001 == choices.ADOPTED, jr004=jr004 == choices.ADOPTED,
        moment_cases=_cases(MOMENT_CASES, numbers), shear_cases=_cases(SHEAR_CASES, numbers),
        torsion_cases=_cases(TORSION_CASES, numbers), safety=SAFETY_FACTORS_OF_BODY[body], kr=KR, k4=K4)
