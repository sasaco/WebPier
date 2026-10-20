"""The column section of the NDU: the micro member's section with the column layout of the bending direction.

JRSNAP derives the M-θ curve of the micro member from a rectangular RC section (SectInfo / SectConc /
SectJiku / SectRein / SectSher / SectSafe). WebPier gives it:

- b × h of the micro member (normal to / in the plane), La from the control node down to the footing top, and
  the 破壊形態 of the M-θ: 曲げ for La/d ≧ 2, せん断 for 1.25 ≦ La/d < 2 (decision 66);
- f'ck and Ec of the column concrete (calc.materials), Dmax of the column concrete (鉄筋.柱.aggregate_max_mm)
  and the three γb of the input conditions;
- the 方向別の鉄筋配置表 of the bending direction (calc.column_rebar), centres from the upper face;
- DRTU = DRTL: the number of main-bar layers of that direction, and DELU = DELL their spacing along the face;
- the one hoop row of that direction: 帯鉄筋の方向別有効本数, size, pitch, steel.

JRSNAP takes the first and last DRTU rows of the table as the tension bars and has no face identity, so the
main bars of the direction must be exactly those rows (a side bar outside them, or between two layers, is not
representable). The bars are those in use, with the changes made in the 方向別の鉄筋配置表 (decision 68).
Anything else is an input error: nothing is guessed.
"""

from __future__ import annotations

from decimal import Decimal

from ...calc._exact import d, put
from ...calc.column_rebar import ColumnLayout, table, yield_strength
from ...calc.frame import Frame, Node, NodeRole
from ...core.errors import InputError
from ...core.printed import Precision, Printed
from ...inputs import PierInput
from ...inputs.rebar import LENGTH_MM
from .model import RebarRow, SectionData, Shear
from .profile import (
    MIN_SHEAR_SPAN_RATIO, SAFETY_BEFORE, SAFETY_GBS, SAFETY_GBVO, SAFETY_K, SHEAR_SPAN_RATIO_BENDING, Profile,
)

EC_KN_MM2 = Precision(1, "kN/mm2")
MAX_ROWS = 100
_COLUMN = "鉄筋.柱"


def need(value, path: str):
    if value is None:
        raise InputError(f"{path}: 値が必要です")
    return value


def _mm(length: Printed) -> Printed:
    return put(LENGTH_MM, d(length) * 1000)


def _main(profile: Profile, layout: ColumnLayout, rows: tuple) -> tuple[int, Printed]:
    face = profile.face
    face_rows = [row for row in layout.rows if row.direction == face]
    if not face_rows:
        raise InputError(f"{_COLUMN}.main_bars: {face}の主鉄筋が必要です")
    keys = {row.key for row in face_rows}
    main = table((bar for bar in layout.bars if keys.intersection(bar.rows)), face)
    layers = len(face_rows)
    if len(main) != 2 * layers or rows[:layers] != main[:layers] or rows[-layers:] != main[-layers:]:
        raise InputError(f"{_COLUMN}.main_bars: {face}方向の表の先頭・末尾{layers}行が{face}の主鉄筋と一致しません"
                         "（主鉄筋より外側や段の間にある鉄筋、同じ段への混在は未対応です）")
    pitches = {row.pitch for row in face_rows}
    if None in pitches or len(pitches) != 1:
        raise InputError(f"{_COLUMN}.main_bars: {face}の主鉄筋の間隔が一つに定まりません"
                         "（1本や両端2本だけの行、行ごとに異なる間隔は未対応です）")
    (pitch,) = pitches
    return layers, pitch


def _shear(profile: Profile, pier: PierInput) -> Shear:
    column = pier.rebar.column
    path = f"{_COLUMN}.column_hoops.direction_rows"
    rows = [(index, row) for index, row in enumerate(column.hoops.rows) if row.direction == profile.face]
    if len(rows) != 1:
        raise InputError(f"{path}: {profile.face}の帯鉄筋はちょうど1行が必要です（{len(rows)}行）")
    ((index, row),) = rows
    here = f"{path}[{index}]"
    if row.start is not None or row.end is not None:
        raise InputError(f"{here}: 区間を指定した帯鉄筋は未対応です（柱全高で一様な1行が必要です）")
    material = need(column.materials.transverse, f"{_COLUMN}.materials.transverse")
    return Shear(yield_strength=yield_strength(material), diameter=need(row.diameter, f"{here}.diameter_mm"),
                 legs=need(row.effective_legs, f"{here}.effective_legs"), pitch=need(row.pitch, f"{here}.pitch_mm"))


def column_section(profile: Profile, pier: PierInput, layout: ColumnLayout, frame: Frame, control: Node
                   ) -> SectionData:
    (micro,) = [member for member in frame.members if not member.rigid]  # 0710 / 0720: the micro member only
    section, concrete = micro.section, micro.material
    assert section is not None and concrete is not None  # an elastic member has both
    width, height = _mm(section.width), _mm(section.depth)
    span = put(LENGTH_MM, (d(control.y) - d(frame.node(NodeRole.FOOTING_TOP).y)) * 1000)
    rows = table(layout.bars, profile.face)
    if len(rows) > MAX_ROWS:
        raise InputError(f"{_COLUMN}: {profile.face}方向の表が{len(rows)}行です（JRSNAP は{MAX_ROWS}行まで）")
    depth = d(height) - d(rows[0].center)
    if d(span) < MIN_SHEAR_SPAN_RATIO * depth:
        raise InputError(f"{_COLUMN}: La/d = {span.value:g}/{float(depth):g} が1.25未満で、"
                         "M-θ 自動算定（低せん断スパン部材は 1.25≦La/d＜2）の対象外です")
    layers, pitch = _main(profile, layout, rows)
    # one steel for the member (decision 68)
    grade = need(pier.rebar.column.materials.main, f"{_COLUMN}.materials.main")
    conditions = getattr(pier.jrsnap, profile.jrsnap)
    key = f"jrsnap_{profile.jrsnap}"
    factors = [need(getattr(conditions, name), f"{key}.{name}")
               for name in ("shear_factor_vcd", "shear_factor_vsd", "shear_factor_vdd")]
    return SectionData(
        width=width, height=height, shear_span=span, shear_failure=d(span) < SHEAR_SPAN_RATIO_BENDING * depth,
        fck=concrete.strength,
        ec=put(EC_KN_MM2, d(concrete.modulus) * Decimal(10)),  # mantissa × 10^7 kN/m2 = × 10 kN/mm2
        aggregate_max=need(pier.rebar.column.aggregate_max, f"{_COLUMN}.aggregate_max_mm"),  # the column concrete's
        yield_strength=yield_strength(grade), main_layers=layers, main_pitch=pitch,
        rows=tuple(RebarRow(row.center, row.diameter, row.count) for row in rows), shear=_shear(profile, pier),
        safety=(*SAFETY_BEFORE, factors[0], factors[1], SAFETY_GBS, SAFETY_K, factors[2], SAFETY_GBVO))
