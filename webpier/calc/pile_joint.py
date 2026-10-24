"""The joint of a steel pipe pile with the footing in 0612 / 0622 (decision 90, Example橋脚4 III-3.2.2 (b): 杭体設計の手引き 2.4).

The joint is checked at the head of each pile row, in the case of the largest bending moment there, with the forces of one pile
(the sample's table 2.5.2): γi・Md / Mud ≦ 1.0. The row of the largest axial force of those cases is the push side and the row of
the smallest the pull side (the sample's two rows). WebPier chooses the design forces from the
pickup and Capacita calculates the design bending resistance Mud (its HsCalc: 異種部材接合部, 鉄筋差込み方式, the section
the sample's own program calculated; the strength and the strain of the concrete the pipe confines are its). Shear is not
checked (the sample omits it). Mud is Capacita's value, rounded to the digits the sample prints and used rounded afterwards
(ADR-0003); WebPier only holds it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput
from ._exact import d, put
from .detailing.common import bar_area
from .pile_body import PileResponseError, PileSteel, PointForces, SectionForce

GAMMA_I = Printed(1.2, 1, "")  # 構造物係数, 安全性（破壊）
GAMMA_C = Printed(1.3, 1, "")  # コンクリートの材料係数
GAMMA_S = Printed(1.05, 2, "")  # 鋼材の材料係数
GAMMA_B = Printed(1.3, 1, "")  # 部材係数
BAR_STRENGTH = {"SD295": 295.0, "SD345": 345.0, "SD390": 390.0}  # fsyk (JIS G 3112: the name is the strength)
AREA = Precision(1, "mm2")
DISTANCE = Precision(1, "mm")
STRENGTH = Precision(1, "N/mm2")
FORCE = Precision(1, "kN")
MOMENT = Precision(1, "kN・m")
RATIO = Precision(2, "")


class Side(Enum):
    """The push side and the pull side: the pile row whose design axial compression is the largest and the one whose is the smallest."""

    PUSH = "押込み側"
    PULL = "引抜き側"


@dataclass(frozen=True)
class JointForces:
    """The design forces of one side of one row, of one pile (compression positive)."""

    md: float  # kN m, the absolute value of the bending moment
    nd: float  # kN
    combination: int


@dataclass(frozen=True)
class JointRowForces:
    """One pile row: its piles and the design forces of one pile."""

    row: int
    member: int
    piles: int
    forces: JointForces


@dataclass(frozen=True)
class JointSection:
    """What the sample's table 3.2.11 prints of the section."""

    diameter: Printed  # D, mm
    thickness: Printed  # t, mm
    corrosion: Printed  # mm
    bar_diameter: Printed  # mm
    bar_count: int
    bar_area: Printed  # As, mm2
    bar_grade: str
    bar_strength: Printed  # fsyk of the bars, N/mm2
    pipe_strength: Printed  # f'syk of the pipe, N/mm2
    centroid: Printed  # dsc, mm from the outer edge of the pipe
    fck: Printed  # f'ck of the concrete the pipe fills, N/mm2


@dataclass(frozen=True)
class RowCheck:
    side: Side | None  # None for a row between the push side and the pull side (and for a single row)
    combination: int
    md: Printed  # kN m
    nd: Printed  # N'd, kN, compression positive
    mud: Printed  # kN m
    ratio: Printed  # γi Md / Mud

    @property
    def ok(self) -> bool:
        return self.ratio.value <= 1.0


@dataclass(frozen=True)
class RowJoint:
    row: int
    piles: int
    check: RowCheck


@dataclass(frozen=True)
class PileJointResult:
    section: JointSection
    gamma_i: Printed
    gamma_c: Printed
    gamma_s: Printed
    gamma_b: Printed
    rows: tuple[RowJoint, ...]
    engine_version: str
    input_sha256: str  # the JSON given to Capacita

    @property
    def ok(self) -> bool:
        return all(row.check.ok for row in self.rows)


def section(pier: PierInput, pipe: PileSteel) -> JointSection:
    """The section of the input; a blank item is an input error naming it."""
    joint = pier.piles.steel_soil_cement.joint
    prefix = "杭基礎.鋼管ソイルセメント杭.結合部"
    items = {"径": joint.bar_diameter, "本数": joint.bar_count, "材質": joint.bar_grade, "重心位置": joint.bar_centroid}
    for name, value in items.items():
        if value is None:
            raise InputError(f"{prefix}.軸方向鉄筋.{name}: 結合部の照査に必要です")
    if joint.fill_fck is None:
        raise InputError(f"{prefix}.中詰めコンクリート_f'ck: 結合部の照査に必要です")
    assert joint.bar_diameter is not None and joint.bar_count is not None and joint.bar_grade is not None
    assert joint.bar_centroid is not None
    steel = pier.piles.steel_soil_cement
    assert steel.corrosion is not None
    area = put(AREA, d(bar_area(joint.bar_diameter, f"{prefix}.軸方向鉄筋.径")) * joint.bar_count)
    return JointSection(pipe.diameter, pipe.thickness, steel.corrosion, joint.bar_diameter, joint.bar_count, area,
                        joint.bar_grade, STRENGTH(BAR_STRENGTH[joint.bar_grade]), pipe.fsyk, joint.bar_centroid,
                        joint.fill_fck)


def select(row: int, member: int, piles: int, lines: Sequence[PointForces]) -> JointRowForces:
    """The design forces of a pile row from the PIK lines of its member: at the head (ITAN), in the lines of the focus M, the
    case of the largest bending moment (the larger in absolute value of the largest and the smallest), with the axial force of
    the case, for one pile. FEMPython's axial force is negative in compression (``PileResponseError`` when the member has no
    such line)."""
    heads = [line for line in lines if line.focus == "M" and line.point == "ITAN"]
    if len(heads) != 1:
        raise PileResponseError(f"杭列 {row}（部材 {member}）の杭頭の曲げモーメントの行が {len(heads)} 行あります（1行が必要です）")
    force = max((heads[0].largest, heads[0].smallest), key=lambda found: abs(found.md))
    return JointRowForces(row, member, piles, JointForces(abs(force.md) / piles, -force.nd / piles, force.combination))


def assemble(joint: JointSection, rows: Sequence[JointRowForces], moments: Mapping[int, float],
             engine_version: str, input_sha256: str) -> PileJointResult:
    """The result from Capacita's design bending resistances *moments* by row. The row of the largest design axial force is the
    push side and the row of the smallest the pull side (the first of equal ones; no side when the two are one row)."""
    forces = [FORCE(row.forces.nd) for row in rows]
    largest = max(range(len(rows)), key=lambda index: (forces[index].value, -index), default=None)
    smallest = min(range(len(rows)), key=lambda index: (forces[index].value, index), default=None)
    bodies = []
    for index, row in enumerate(rows):
        try:
            resistance = MOMENT(moments[row.row])
        except KeyError as exc:
            raise PileResponseError(f"Capacita の結果に杭列 {row.row} の Mud がありません") from exc
        md = MOMENT(row.forces.md)
        ratio = put(RATIO, d(GAMMA_I) * d(md) / d(resistance))
        side = None if largest == smallest else Side.PUSH if index == largest else Side.PULL if index == smallest else None
        bodies.append(RowJoint(row.row, row.piles, RowCheck(side, row.forces.combination, md, forces[index], resistance, ratio)))
    return PileJointResult(joint, GAMMA_I, GAMMA_C, GAMMA_S, GAMMA_B, tuple(bodies),
                           engine_version, input_sha256)
