"""The column section of the NDU: the micro member's section with the column layout of the bending direction.

JRSNAP derives the M-θ curve of the micro member from a rectangular RC section (SectInfo / SectConc /
SectJiku / SectRein / SectSher / SectSafe). WebPier gives it:

- b × h of the micro member (normal to / in the plane), La from the control node down to the footing top, and
  the M-θ always of the 破壊形態 曲げ, a column below La/d 1.25 (a low-shear-span member) refused (decision 114);
- f'ck and Ec of the column concrete (calc.materials), Dmax of the column concrete (鉄筋.柱.aggregate_max_mm)
  and the three γb of the input conditions;
- the 方向別の鉄筋配置表 of the bending direction in use (calc.column_rebar.direction_table), its rows in their order,
  centres from the upper face;
- DRTU = DRTL: the table's 引張鉄筋の段数, and DELU = DELL the spacing of the direction's main bars along the face
  (from its main bars, also for a hand-made table: decision 111);
- the one hoop row of that direction: 帯鉄筋の方向別有効本数, size, pitch, steel.

JRSNAP takes the first and the last DRTU rows as written as the tension bars, without ordering them by their centre
(decision 111, seen in JRSNAP 5.2-L03's echo of the M-θ calculation), so the table is written in its own order: the
table the main bars make has their layers first and last, a side bar between two layers after them.
Anything else is an input error: nothing is guessed.
"""

from __future__ import annotations

from decimal import Decimal

from ...calc._exact import d, put
from ...calc.column_rebar import ColumnLayout, direction_table, main_pitch, yield_strength
from ...calc.frame import Frame, Node, NodeRole
from ...core.errors import InputError
from ...core.printed import Precision, Printed
from ...inputs import PierInput
from ...inputs.rebar import LENGTH_MM
from .model import RebarRow, SectionData, Shear
from .profile import (
    MIN_SHEAR_SPAN_RATIO, SAFETY_BEFORE, SAFETY_GBS, SAFETY_GBVO, SAFETY_K, Profile,
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
    (micro,) = [member for member in frame.members if not member.rigid and not member.pile]  # the micro member only
    section, concrete = micro.section, micro.material
    assert section is not None and concrete is not None  # an elastic member has both
    width, height = _mm(section.width), _mm(section.depth)
    span = put(LENGTH_MM, (d(control.y) - d(frame.node(NodeRole.FOOTING_TOP).y)) * 1000)
    found = direction_table(layout, profile.face)
    rows = found.rows
    if len(rows) > MAX_ROWS:
        raise InputError(f"{_COLUMN}: {profile.face}方向の表が{len(rows)}行です（JRSNAP は{MAX_ROWS}行まで）")
    depth = d(height) - d(rows[0].center)
    if d(span) < MIN_SHEAR_SPAN_RATIO * depth:
        raise InputError(f"{_COLUMN}: La/d = {span.value:g}/{float(depth):g} が1.25未満の低せん断スパン部材で、"
                         "M-θ 自動算定の対象外です")
    layers, pitch = found.tension, main_pitch(layout, profile.face)
    # one steel for the member (decision 68)
    grade = need(pier.rebar.column.materials.main, f"{_COLUMN}.materials.main")
    conditions = getattr(pier.jrsnap, profile.jrsnap)
    key = f"jrsnap_{profile.jrsnap}"
    factors = [need(getattr(conditions, name), f"{key}.{name}")
               for name in ("shear_factor_vcd", "shear_factor_vsd", "shear_factor_vdd")]
    return SectionData(
        width=width, height=height, shear_span=span, fck=concrete.strength,
        ec=put(EC_KN_MM2, d(concrete.modulus) * Decimal(10)),  # mantissa × 10^7 kN/m2 = × 10 kN/mm2
        aggregate_max=need(pier.rebar.column.aggregate_max, f"{_COLUMN}.aggregate_max_mm"),  # the column concrete's
        yield_strength=yield_strength(grade), main_layers=layers, main_pitch=pitch,
        rows=tuple(RebarRow(row.center, row.diameter, row.count) for row in rows), shear=_shear(profile, pier),
        safety=(*SAFETY_BEFORE, factors[0], factors[1], SAFETY_GBS, SAFETY_K, factors[2], SAFETY_GBVO))
