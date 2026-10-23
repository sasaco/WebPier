"""The pile body of a steel pipe pile in 0612 / 0622 (decision 89, Example橋脚4 III-3.2.2: 鉄道構造物等設計標準・同解説 基礎構造物
15.3.2, 杭体設計の手引き 2.2).

WebPier chooses the design forces and Capacita's SteelDan calculates (its ``Pipe`` section and ``calculate_pipe_pile``,
Capacita/SteelDan PipePileVerifier): for each pile row, the section forces of the member of the row at the points below the
head (the head is the joint's, which is not checked here) in the pickup of the 安全性（破壊）, the largest bending moment, the
largest shear force and the largest axial compression, each with the other two forces of its case. The forces are those of the
bundled member (the row's piles); SteelDan divides them by the piles of the row. The checks are, of every case, the axial force
with the bending moment (the tension side and the compression side), the shear force, and the three together; each ratio is
judged by its printed value, not above 1.0. Every number is SteelDan's, rounded to the digits the sample prints and used
rounded afterwards (ADR-0003); WebPier only holds them.

The steel pipe is the 鋼管外径 less the corrosion allowance on both sides (D) and the 鋼管厚 less the corrosion allowance (t) of
the input, its grade 鋼管材質 gives the characteristic strengths.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput
from ._exact import d, put

# The characteristic yield strengths in tension and compression (fsyk) and in shear (fsvyk), N/mm2, by the grade of the
# pipe (JIS G 3444; 杭体設計の手引き): the example's SKK490 is 315 and 180.
STEEL_PIPE_STRENGTH = {"SKK400": (235.0, 135.0), "SKK490": (315.0, 180.0)}
GAMMA_I = Printed(1.2, 1, "")  # 構造物係数, 安全性（破壊）
GAMMA_S = Printed(1.05, 2, "")  # 材料係数（鋼材）
GAMMA_B = Printed(1.05, 2, "")  # 部材係数
DIAMETER = Precision(1, "mm")
THICKNESS = Precision(1, "mm")
AREA = Precision(5, "m2")
INERTIA = Precision(8, "m4")
DISTANCE = Precision(1, "mm")
STRENGTH = Precision(0, "N/mm2")
FORCE = Precision(1, "kN")
MOMENT = Precision(1, "kN・m")
RATIO = Precision(2, "")
_MILLI = Decimal(1000)


class Case(Enum):
    """The design force case: the largest bending moment, shear force or axial compression of the row (cases 6, 7 and 8 of
    SteelDan's force rows)."""

    MOMENT = 6
    SHEAR = 7
    AXIAL = 8


class PileResponseError(Exception):
    """The files FEMPython or SteelDan returned have no response the check reads."""


@dataclass(frozen=True)
class SectionForce:
    """The forces of one case at a point (FEMPython's sign: compression negative) and its combination."""

    md: float  # kN m
    vd: float  # kN
    nd: float  # kN
    combination: int


@dataclass(frozen=True)
class PointForces:
    """A line of the PIK: the largest and the smallest case of a focus ("M", "S" or "N") at a point of a member."""

    focus: str
    point: str  # ITAN (the head), JTAN (the tip), or the number of an inner point
    distance: float  # m from the head
    largest: SectionForce
    smallest: SectionForce


@dataclass(frozen=True)
class PileSteel:
    """The steel pipe of one pile as the check takes it."""

    grade: str
    fsyk: Printed  # N/mm2
    fsvyk: Printed
    diameter: Printed  # D, the outer diameter less the corrosion allowance on both sides, mm
    thickness: Printed  # t, the effective wall thickness, mm


@dataclass(frozen=True)
class PileRowForces:
    """One pile row for SteelDan: its piles and the forces of its three cases, as FEMPython returns them for the member."""

    row: int
    member: int
    piles: int
    cases: Mapping[Case, SectionForce]
    distances: Mapping[Case, float]  # where of the pile the force is, m from the head


@dataclass(frozen=True)
class CaseBody:
    """The three checks of one case of one row, with the forces per pile."""

    case: Case
    combination: int
    distance: Printed  # m from the head
    md: Printed  # kN m
    nd: Printed  # N'd, kN, compression positive
    vd: Printed  # kN
    ratio_tension: Printed  # γi (−N'd / Nud + Md / Mutd)
    ratio_compression: Printed  # γi (N'd / N'u0d + Md / Mucd)
    shear: Printed  # γi Vd / Vyd
    combined: Printed  # (γi / 1.1)² ((N'd / N'u0d + Md / Mucd)² + (Vd / Vyd)²)

    @property
    def bending(self) -> Printed:
        """The ratio of the axial force with the bending moment: the larger of the two sides."""
        return max(self.ratio_tension, self.ratio_compression, key=lambda item: item.value)

    @property
    def ratios(self) -> tuple[Printed, ...]:
        return (self.bending, self.shear, self.combined)

    @property
    def ok(self) -> bool:
        return all(item.value <= 1.0 for item in self.ratios)


@dataclass(frozen=True)
class RowBody:
    row: int
    piles: int
    cases: tuple[CaseBody, ...]


@dataclass(frozen=True)
class Resistance:
    """What the pile resists, the same for every case (SteelDan's rounded values)."""

    area: Printed  # A, m2
    inertia: Printed  # I, m4
    distance: Printed  # y, mm
    fsyd: Printed  # the design yield strength in tension and compression, N/mm2
    fsvyd: Printed  # in shear
    tension: Printed  # Nud, kN
    compression: Printed  # N'u0d, kN
    bending_tension: Printed  # Mutd, kN m
    bending_compression: Printed  # Mucd, kN m
    shear: Printed  # Vyd, kN


@dataclass(frozen=True)
class PileBodyResult:
    steel: PileSteel
    gamma_i: Printed
    gamma_s: Printed
    gamma_b: Printed
    resistance: Resistance
    rows: tuple[RowBody, ...]
    engine_version: str
    wsj_sha256: str  # the WSJ SteelDan calculated

    @property
    def ok(self) -> bool:
        return all(case.ok for row in self.rows for case in row.cases)


def steel(pier: PierInput) -> PileSteel:
    """The pipe of the input; a missing grade or size is an input error naming it."""
    pile = pier.piles.steel_soil_cement
    if pile.grade is None:
        raise InputError("杭基礎.鋼管ソイルセメント杭.鋼管材質: 杭体の照査に必要です")
    # the sizes are required by the input of a steel soil cement pile foundation (inputs.parse)
    assert pile.steel_diameter is not None and pile.thickness is not None and pile.corrosion is not None
    fsyk, fsvyk = STEEL_PIPE_STRENGTH[pile.grade]
    diameter = d(pile.steel_diameter) * _MILLI - 2 * d(pile.corrosion)
    return PileSteel(pile.grade, STRENGTH(fsyk), STRENGTH(fsvyk), put(DIAMETER, diameter),
                     put(THICKNESS, d(pile.thickness) - d(pile.corrosion)))


def _largest(focus: str, rows: Sequence[PointForces], key) -> tuple[SectionForce, float] | None:
    """The case of the *focus* lines of the points below the head with the largest *key* of its forces."""
    best: tuple[SectionForce, float] | None = None
    for line in rows:
        if line.focus != focus or line.point == "ITAN":
            continue
        for force in (line.largest, line.smallest):
            if best is None or key(force) > key(best[0]):
                best = (force, line.distance)
    return best


def select(row: int, member: int, piles: int, lines: Sequence[PointForces]) -> PileRowForces:
    """The three design force cases of a pile row from the PIK lines of its member (``PileResponseError`` when the member has
    no point below its head for a case)."""
    chosen = {Case.MOMENT: _largest("M", lines, lambda force: abs(force.md)),
              Case.SHEAR: _largest("S", lines, lambda force: abs(force.vd)),
              Case.AXIAL: _largest("N", lines, lambda force: -force.nd)}  # the largest compression: the smallest Nd
    for case, found in chosen.items():
        if found is None:
            raise PileResponseError(f"杭列 {row}（部材 {member}）の杭頭より下の断面力（{case.name}）がありません")
    return PileRowForces(row, member, piles, {case: found[0] for case, found in chosen.items() if found},
                         {case: found[1] for case, found in chosen.items() if found})


def assemble(section: PileSteel, rows: Sequence[PileRowForces], values: Mapping[tuple[int, int, str], Mapping[str, float]],
             engine_version: str, wsj_sha256: str) -> PileBodyResult:
    """The result from SteelDan's verifications: *values* by (row, case number, kind) → its values (the row is SteelDan's
    point, the kinds are ``bending``, ``shear`` and ``combined``)."""
    bodies = []
    for row in rows:
        cases = []
        for case in Case:
            try:
                bending, shear, combined = (values[(row.row, case.value, kind)] for kind in ("bending", "shear", "combined"))
                force = row.cases[case]
                cases.append(CaseBody(
                    case, force.combination, Printed(round(row.distances[case], 3), 3, "m"), MOMENT(bending["Md"]),
                    FORCE(bending["Nd"]), FORCE(shear["Vd"]), RATIO(bending["ratio_tension"]),
                    RATIO(bending["ratio_compression"]), RATIO(shear["ratio"]), RATIO(combined["ratio"])))
            except KeyError as exc:
                raise PileResponseError(f"SteelDan の結果に杭列 {row.row} のケース {case.value} の {exc.args[0]} がありません") from exc
        bodies.append(RowBody(row.row, row.piles, tuple(cases)))
    first = values[(rows[0].row, Case.MOMENT.value, "bending")]
    shear, combined = values[(rows[0].row, Case.MOMENT.value, "shear")], values[(rows[0].row, Case.MOMENT.value, "combined")]
    resistance = Resistance(
        AREA(first["A"]), INERTIA(first["I"]), DISTANCE(first["y"]), STRENGTH(first["fsyd"]), STRENGTH(shear["fsvyd"]),
        FORCE(first["Nud"]), FORCE(first["Nu0d"]), MOMENT(first["Mutd"]), MOMENT(first["Mucd"]), FORCE(combined["Vyd"]))
    return PileBodyResult(section, GAMMA_I, GAMMA_S, GAMMA_B, resistance, tuple(bodies), engine_version, wsj_sha256)
