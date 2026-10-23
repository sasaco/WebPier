"""The piles of the frame of a pile foundation (0610 and 0620, decision 88, ADR-0013).

The frame stands on the piles instead of on the springs of 0500: the footing is rigid, with a rigid horizontal member
along its base through the heads of the pile rows, and each pile row is one member of the length of the pile, fixed to
the base at its head (Example橋脚4 図 1.2.3). A row of piles is bundled into one member: its area and second moment are
the one pile's times the number of piles of the row in the depth, and the springs SOIL-JR calculated are already those of
the row (the 解析連携データ, ``calc.pile_springs``).

* **The pile section** is the one of the pile head for the whole length (no 段落し, decision 88): the steel pipe of a
  鋼管ソイルセメント杭, with its thickness less the corrosion allowance, or the circle of a 場所打ち杭. The soil cement
  and the reinforcement are not counted.
* **The surface springs** of a row are the horizontal and the vertical shear springs of each layer along the pile,
  per metre of the pile, as one interval of the member each: the layer, or the part of it that has a shear spring
  (the part within the least embedment into the bearing layer has none, push side, decision 88).
* **The tip** of a row has the vertical spring (and the horizontal and the rotational one, which SOIL-JR leaves out
  for a long pile) of the long term and of the short term (the first slope).

Nothing is calculated of the ground: every spring is read from the .sdc as it is printed there (kN/m² or kN/m).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import LENGTH, Precision, Printed
from ..inputs import PierInput, choices
from ._exact import d, put
from .pile_ground import PI, STEEL_MODULUS, PileGroundResult
from .pile_springs import DirectionSprings, GroundSprings

FRAME_AREA = Precision(5, "m2")  # A of one pile as the frame prints it (Example橋脚4 図 1.2.2: 0.04171)
FRAME_INERTIA = Precision(5, "m4")  # I of one pile (0.00318)
MODULUS = Precision(0, "kN/m2")  # E of the frame's pile
SPRING = Precision(0, "kN/m2")  # a surface spring, per metre of the pile
TIP_SPRING = Precision(0, "kN/m")  # a spring at the tip
_MM = Decimal(1000)
_GIGA = Decimal(10) ** 6  # kN/mm² → kN/m²
LONGITUDINAL, TRANSVERSE = "橋軸方向", "直角方向"


@dataclass(frozen=True)
class PileFoundation:
    """What the frame of a pile foundation takes of 0500: the values WebPier gave SOIL-JR and the springs it returned."""

    ground: PileGroundResult
    springs: GroundSprings


@dataclass(frozen=True)
class PileSection:
    """One pile as the frame models it (the same for every row and the whole length)."""

    kind: str  # 鋼管 or 円形断面
    modulus: Printed  # E, kN/m2
    area: Printed  # A of one pile
    inertia: Printed  # I of one pile
    diameter: Printed  # the outer diameter drawn, m


@dataclass(frozen=True)
class SpringInterval:
    """A stretch of a pile row from its head, with the springs of the row per metre of the pile."""

    length: Printed  # m
    horizontal: Printed  # kN/m²
    shear: Printed  # kN/m², the vertical shear spring of the pile surface


@dataclass(frozen=True)
class TipSpring:
    vertical: Printed  # kN/m
    horizontal: Printed  # kN/m
    rotation: Printed  # kN/m


@dataclass(frozen=True)
class PileRow:
    number: int  # 1 at the first row
    x: Printed  # from the footing centre, m
    piles: int  # the piles of the row in the depth
    column: str  # the column of SOIL-JR's table the springs are of (1列目, 奇数列)
    area: Printed  # A of the row: piles × the area of one pile
    inertia: Printed  # I of the row
    long_term: tuple[SpringInterval, ...]
    short_term: tuple[SpringInterval, ...]
    long_tip: TipSpring
    short_tip: TipSpring


@dataclass(frozen=True)
class PileGroup:
    direction: str  # 橋軸方向 or 直角方向
    length: Printed  # the pile length below the footing base, m
    section: PileSection
    inverse_beta: Printed  # 1/β, m
    rows: tuple[PileRow, ...]


def _mm(value: float) -> int:
    return int((Decimal(repr(value)) * _MM).to_integral_value())


def _length(millimetres: int) -> Printed:
    return LENGTH(float(Decimal(millimetres) / _MM))


def section(pier: PierInput, ground: PileGroundResult) -> PileSection:
    """The section of one pile (decision 88): the steel pipe less the corrosion allowance, or the circle."""
    piles = pier.piles
    if pier.substructure.foundation == choices.CAST_IN_PLACE_PILE:
        cast = piles.cast_in_place
        diameter = d(cast.diameter)
        return PileSection(
            kind="円形断面", modulus=MODULUS(float(d(ground.section.ec) * _GIGA)), area=put(FRAME_AREA, PI * diameter * diameter / 4),
            inertia=put(FRAME_INERTIA, PI * diameter ** 4 / 64), diameter=cast.diameter)
    steel = piles.steel_soil_cement
    outer = d(steel.steel_diameter) - 2 * d(steel.corrosion) / _MM
    inner = d(steel.steel_diameter) - 2 * d(steel.thickness) / _MM
    return PileSection(
        kind="鋼管", modulus=MODULUS(float(d(STEEL_MODULUS) * _GIGA)),
        area=put(FRAME_AREA, PI * (outer * outer - inner * inner) / 4),
        inertia=put(FRAME_INERTIA, PI * (outer ** 4 - inner ** 4) / 64), diameter=steel.steel_diameter)


def _intervals(direction: DirectionSprings, column: int, long_term: bool) -> tuple[SpringInterval, ...]:
    """The intervals of a row: each layer, split where its shear spring ends (the part at the bottom within the least
    embedment has none)."""
    rows = []
    for layer in direction.layers:
        thickness, shear = _mm(layer.thickness), _mm(layer.shear_thickness)
        if shear > thickness:
            raise InputError(f".sdc の{direction.name}の層 {layer.number}: せん断ばねの層厚が層厚より大きい値です")
        horizontal = (layer.horizontal_long if long_term else layer.horizontal_short)[column]
        vertical = (layer.shear_long if long_term else layer.shear_short)[column]
        if shear:
            rows.append(SpringInterval(_length(shear), SPRING(horizontal), SPRING(vertical)))
        rest = thickness - shear
        if rest:
            # the part without a push-side shear spring has none, except at the bottom of the pile: within the least
            # embedment into the bearing layer the pull side's spring is taken (owner, P5: the example's table III-21)
            bottom = layer is direction.layers[-1] and _mm(layer.pull_thickness) >= rest
            pulled = (layer.pull_long if long_term else layer.pull_short)[column] if bottom else 0
            rows.append(SpringInterval(_length(rest), SPRING(horizontal), SPRING(pulled)))
    return tuple(rows)


def pile_group(pier: PierInput, foundation: PileFoundation, direction: str) -> PileGroup:
    """The pile rows of *direction* (``LONGITUDINAL`` or ``TRANSVERSE``): where they stand, what they are made of and
    the springs of SOIL-JR."""
    ground, found = foundation.ground, foundation.springs.direction(direction)
    along = direction == LONGITUDINAL
    layout = pier.piles.layout
    positions = layout.along if along else layout.across
    columns = ground.rows.along if along else ground.rows.across
    if found.rows != len(positions):
        raise InputError(f".sdc の{direction}の杭列数（{found.rows}）が入力の杭の列（{len(positions)}列）と違います")
    if foundation.springs.pile.get("突出長"):
        raise InputError(f".sdc の突出長（{foundation.springs.pile['突出長']} m）の杭は骨組にできません")
    pile = section(pier, ground)
    total = sum(_mm(layer.thickness) for layer in found.layers)
    if total != _mm(ground.length.value):
        raise InputError(f".sdc の{direction}の層厚の合計（{total / 1000} m）が杭長（{ground.length.value} m）と違います")
    rows = []
    for number, (position, column) in enumerate(zip(positions, columns), 1):
        index = found.column(number)
        piles = found.depth_piles[number - 1 if found.listed_rows else index]
        if piles != column.count:
            raise InputError(f".sdc の{direction}の杭列 {number} の奥行き本数（{piles}）が入力から求めた本数"
                             f"（{column.count}）と違います")
        rows.append(PileRow(
            number=number, x=position, piles=piles, column=found.columns[index],
            area=put(FRAME_AREA, d(pile.area) * piles), inertia=put(FRAME_INERTIA, d(pile.inertia) * piles),
            long_term=_intervals(found, index, True),
            short_term=_intervals(found, index, False),
            long_tip=TipSpring(TIP_SPRING(found.tip_long[index]), TIP_SPRING(found.tip_horizontal_long[index]),
                               TIP_SPRING(found.tip_rotation_long[index])),
            short_tip=TipSpring(TIP_SPRING(found.tip_short[index]), TIP_SPRING(found.tip_horizontal_short[index]),
                                TIP_SPRING(found.tip_rotation_short[index]))))
    return PileGroup(direction=direction, length=ground.length, section=pile, inverse_beta=LENGTH(found.inverse_beta),
                     rows=tuple(rows))


__all__ = ["LONGITUDINAL", "TRANSVERSE", "PileFoundation", "PileGroup", "PileRow", "PileSection", "SpringInterval",
           "TipSpring", "pile_group", "section"]
