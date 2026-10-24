"""The pile body of a cast-in-place pile in 0612 / 0622 (decision 91, 鉄道構造物等設計標準・同解説 コンクリート構造物 (R5), 基礎構造物).

Capacita (RcDan) calculates and prints the check, as for the column (decision 48): a circular reinforced concrete section
with the main bars all round it and the hoops, in its section force input mode, for the 安全性（破壊）: the bending
moment with the axial force, and the shear force. WebPier decides the conditions (CONTEXT.md 杭体の照査):

- the section: the pile diameter D (杭径), f'ck, the main bars (径・本数・材質・純かぶり) and the hoops (径・材質・間隔),
  one set all along the pile (the step of the bars, the length of the head and the hoops of the 2D zone are not
  modelled: decision 87). 主鉄筋の芯かぶり is the 純かぶり + the hoop + half the main bar (CONTEXT.md);
- the 施工条件 of the pile, which Capacita's 杭の施工条件 takes as it reduces f'ck, Ec and Vcd (the pile factors of its
  default table);
- the design forces: for each pile row, from the PIK of the 安全性（破壊）, at the points below the head (the head is the
  joint's, which is not checked here) the case of the largest bending moment, of the largest shear force, of the largest
  axial compression and, when a point of the row is in tension, of the largest axial tension, each with the other two
  forces of its case. RC resists differently under compression and under tension, so the cases of both axial extremes
  are checked. The forces are those of the bundled member (the row's piles): they are given to Capacita as they are with
  the number of the piles as the number of members (``members[].n``), and it divides them. The report prints the forces of
  one pile, rounded to the digits it prints and given back multiplied by the piles (ADR-0003);
- the safety factors, the same as the column's (RC標準 R5, 安全性（破壊）, γi 1.2).

Capacita returns the pages of its report and no values or judgement (ADR-0008): the check is read on the inserted
pages. The result therefore holds the conditions, the design forces and the pages, and its own status is
``not_evaluated``; what WebPier judges of the foundation (the stability) is the stage's status (``calc.pile_check``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput
from ._exact import d, put
from .column_check import SAFETY_FACTORS, SafetyFactors, Steel, tensile_strength
from .column_rebar import yield_strength
from .detailing.common import bar_area
from .pile_body import PileResponseError, PointForces, SectionForce, largest_case

LENGTH = Precision(1, "mm")
FORCE = Precision(1, "kN")
MOMENT = Precision(1, "kN・m")
DISTANCE = Precision(3, "m")
AREA = Precision(1, "mm2")
_MILLI = Decimal(1000)
_PATH = "杭基礎.場所打ち杭"
STATUS = "not_evaluated"  # Capacita returns no judgement (ADR-0008)
# The sections of Capacita's report this check asks for, in report order.
REPORT_SECTIONS = ("bending_safety_destruction", "shear_safety_destruction")
# 安全性（破壊）: the row of the safety factors of RC標準 R5 (calc.column_check.SAFETY_FACTORS)
SAFETY_ID = 5
# A closed hoop crosses the section twice: its two legs are the shear reinforcement (``stirrup_n``, Aw = 2 × the bar's area).
# Capacita's example of a circular section has no hoops, so this is an assumption about RcDan's reading (decision 91).
HOOP_LEGS = 2
# 粗骨材の最大寸法 of the concrete of a cast-in-place pile, mm: not an input (decision 87 leaves it open); 25 is the
# size 場所打ち杭 uses (an assumption, decision 91).
AGGREGATE_MAX = Printed(25.0, 1, "mm")
# 杭の施工条件 of Capacita (the default table of RcDan / WebDanforCS): id, name and the factors that reduce f'ck, the bond
# strength, Ec and Vcd (the one selected applies; Capacita reads the table whole).
PILE_FACTORS = (("pile-000", "使用しない", 1.0, 1.0, 1.0, 1.0), ("pile-001", "泥水中に打込む", 0.8, 0.7, 0.8, 0.9),
                ("pile-002", "自然地盤中に打込む", 0.7, 0.6, 0.8, 0.9), ("pile-003", "ベントナイト泥水", 0.6, 0.5, 0.7, 0.8),
                ("pile-004", "気中施工", 0.9, 0.9, 0.9, 1.0))
# 施工条件 (choices.CAST_IN_PLACE_CONDITIONS) → the id of Capacita's table: the mud that forms by itself is "泥水中に
# 打込む" and the stabilizing fluid "ベントナイト泥水" (decision 91; the correspondence is an assumption: the original
# Excel's four choices had both names).
CONDITION_FACTOR = {"自然泥水": "pile-001", "安定液使用": "pile-003"}


class Kind(Enum):
    """The design force case of a pile row: the largest bending moment, shear force, axial compression or axial tension."""

    MOMENT = "曲げ最大"
    SHEAR = "せん断最大"
    COMPRESSION = "圧縮最大"
    TENSION = "引張最大"


@dataclass(frozen=True)
class CastSection:
    """The section as the check takes it (mm, N/mm2)."""

    diameter: Printed  # D
    fck: Printed  # f'ck of the input (before the reduction of the 施工条件)
    condition: str  # 施工条件
    bar_diameter: Printed
    bar_count: int
    bar_area: Printed  # As of all the bars
    bar_steel: Steel
    cover: Printed  # 純かぶり
    centre: Printed  # 芯かぶり of the main bars
    hoop_diameter: Printed
    hoop_steel: Steel
    hoop_pitch: Printed


@dataclass(frozen=True)
class CaseForces:
    """The forces of one case of one pile row, per pile (compression positive) and where of the pile it is."""

    kind: Kind
    combination: int
    distance: Printed  # m from the head
    md: Printed  # kN m, the absolute value
    nd: Printed  # N'd, kN
    vd: Printed  # kN, the absolute value


@dataclass(frozen=True)
class RowForces:
    row: int
    member: int
    piles: int
    cases: tuple[CaseForces, ...]


@dataclass(frozen=True)
class PileCastResult:
    section: CastSection
    safety: SafetyFactors  # RC標準 R5, 安全性（破壊）
    pile_factor: tuple[str, str, float, float, float, float]  # id, name, the factors of f'ck, the bond, Ec and Vcd
    rows: tuple[RowForces, ...]
    engine_version: str
    wdj_sha256: str  # the WDJ Capacita calculated
    skipped: tuple[str, ...]  # the sections Capacita skipped for zero forces
    engineering_status: str = STATUS
    # Capacita's pages of each section by its id (reporting inserts them): the program's, not the result's
    pages: dict[str, bytes] = field(default_factory=dict, compare=False, repr=False, metadata={"json": False})


def section(pier: PierInput) -> CastSection:
    """The section of the input; a blank item is an input error naming it."""
    pile = pier.piles.cast_in_place
    items = {"軸方向鉄筋.径": pile.bars.diameter, "軸方向鉄筋.本数": pile.bars.count, "軸方向鉄筋.材質": pile.bars.grade,
             "軸方向鉄筋.純かぶり": pile.bars.cover, "帯鉄筋.径": pile.hoops.diameter, "帯鉄筋.材質": pile.hoops.grade,
             "帯鉄筋.間隔": pile.hoops.pitch}
    for name, value in items.items():
        if value is None:
            raise InputError(f"{_PATH}.{name}: 杭体の照査に必要です")
    # the sizes of a cast-in-place pile foundation are required by the input (inputs.parse)
    assert (pile.diameter is not None and pile.fck is not None and pile.condition is not None
            and pile.bars.diameter is not None and pile.bars.count is not None and pile.bars.grade is not None
            and pile.bars.cover is not None and pile.hoops.diameter is not None and pile.hoops.grade is not None
            and pile.hoops.pitch is not None)
    diameter = put(LENGTH, d(pile.diameter) * _MILLI)
    centre = put(LENGTH, d(pile.bars.cover) + d(pile.hoops.diameter) + d(pile.bars.diameter) / 2)
    if 2 * d(centre) >= d(diameter):
        raise InputError(f"{_PATH}.軸方向鉄筋.純かぶり: 杭径に対して大きすぎます（主鉄筋の芯かぶり {centre.value:g} mm が"
                         f"杭の半径 {diameter.value / 2:g} mm 以上になります）")
    area = put(AREA, d(bar_area(pile.bars.diameter, f"{_PATH}.軸方向鉄筋.径")) * pile.bars.count)
    bar_area(pile.hoops.diameter, f"{_PATH}.帯鉄筋.径")  # a size with no nominal area is an input error
    return CastSection(diameter, pile.fck, pile.condition, pile.bars.diameter, pile.bars.count, area,
                       Steel(pile.bars.grade, yield_strength(pile.bars.grade), tensile_strength(pile.bars.grade)),
                       pile.bars.cover, centre, pile.hoops.diameter,
                       Steel(pile.hoops.grade, yield_strength(pile.hoops.grade), tensile_strength(pile.hoops.grade)),
                       pile.hoops.pitch)


def select(row: int, member: int, piles: int, lines: Sequence[PointForces]) -> RowForces:
    """The design force cases of a pile row from the PIK lines of its member (``PileResponseError`` when the member has no
    point below its head for a case). FEMPython's axial force is negative in compression; the forces are per pile."""
    chosen = {Kind.MOMENT: largest_case("M", lines, lambda force: abs(force.md)),
              Kind.SHEAR: largest_case("S", lines, lambda force: abs(force.vd)),
              Kind.COMPRESSION: largest_case("N", lines, lambda force: -force.nd),
              Kind.TENSION: largest_case("N", lines, lambda force: force.nd)}
    for kind in (Kind.MOMENT, Kind.SHEAR, Kind.COMPRESSION):
        if chosen[kind] is None:
            raise PileResponseError(f"杭列 {row}（部材 {member}）の杭頭より下の断面力（{kind.value}）がありません")
    tension = chosen[Kind.TENSION]
    if tension is not None and tension[0].nd <= 0:
        chosen[Kind.TENSION] = None  # no point of the row is in tension: the case is left out
    cases = []
    for kind, found in chosen.items():
        if found is None:
            continue
        force, distance = found
        cases.append(CaseForces(kind, force.combination, Printed(round(distance, 3), 3, "m"),
                                MOMENT(abs(force.md) / piles), FORCE(-force.nd / piles), FORCE(abs(force.vd) / piles)))
    return RowForces(row, member, piles, tuple(cases))


def pile_factor(found: CastSection) -> tuple[str, str, float, float, float, float]:
    """The row of Capacita's 杭の施工条件 the 施工条件 of the pile selects."""
    return next(item for item in PILE_FACTORS if item[0] == CONDITION_FACTOR[found.condition])


def assemble(found: CastSection, rows: Sequence[RowForces], engine_version: str, wdj_sha256: str,
             skipped: Sequence[str], pages: dict[str, bytes]) -> PileCastResult:
    """The result of the check Capacita made of the section *found* for *rows*."""
    safety = next(factors for factors in SAFETY_FACTORS if factors.id == SAFETY_ID)
    return PileCastResult(found, safety, pile_factor(found), tuple(rows), engine_version, wdj_sha256, tuple(skipped),
                          pages=pages)
