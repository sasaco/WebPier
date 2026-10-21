"""4.4 フーチングの構造細目: the detailing of the footing in each direction (decision 73; the sample 0400 2.3).

Per 1 m of width (b = 1000 mm) and the footing height h = H6; the bars of a direction are its layers on the upper and
the lower face (calc.footing_rebar.face_layout: each layer 1000／pitch bars to 0.01, as the sample's D32 − 6.67 本).

- 1) (a) and 3): Pc = (upper + lower)／(b·h) of the direction.
- 5) 鉄筋のあき of each face: the least pitch of the direction's layers, and the least centre spacing of two
  neighbouring layers of the direction, less the bar; the limits are those of a member that is not a column (20 mm,
  φ, 4/3 Dmax with the footing's Dmax). The sample prints the column's limits (40 mm, 1.5φ): not reproduced
  (ADR-0001).
- 6), 8), 9): the stirrups of the direction, per 1 m of width (calc.footing_rebar.stirrup_width), at their pitch
  along the overhang; f'ck and the steel are the footing's.
- 7) ① 一般部, with d = h − the centroid of the direction's lower bars (the tensile bars of the overhang, as 0800〜0820),
  the compression bars the upper bars of the direction.
- 10) 配力鉄筋及び圧縮鉄筋: on each face, the other direction's bars of the face (配力鉄筋) and the direction's bars of
  the other face (圧縮鉄筋) at least As／6 of the direction's bars of the face.

The axial force of the column is not used (the sample's N'd of the column in the footing's checks is not reproduced,
ADR-0001); the checks that use section forces are Capacita's (0810, 0820; ADR-0012).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...core.printed import Printed
from ...inputs import PierInput, choices
from .._exact import d, put
from ..footing_rebar import COUNT, PlacedLayer, face_layout, stirrup_width
from .common import (AREA, LENGTH, BarGroup, CapacityRatio, ClearSpacing, DuctilityLimit, ShearRatio, SteelRatio,
                     StirrupSpacing, capacity_ratio, clear_spacing, ductility_limit, general_spacing, least_gap,
                     need, shear_ratio, steel_ratio)

_FOOTING = "鉄筋.フーチング"
UPPER, LOWER = choices.BEAM_FACES
WIDTH = Printed(1000, 0, "mm")  # per 1 m of width (the sample 0400 2.3: b = 1000.0)
DISTRIBUTION_DIVISOR = 6  # 10): As／6 (RC標準 13.6.4; the sample 0400 10))


@dataclass(frozen=True)
class FaceBars:
    """10) of one face of the direction."""

    face: str  # choices.BEAM_FACES
    bars: BarGroup  # the direction's bars of the face (all layers)
    required: Printed  # As／6
    distribution: Printed  # the other direction's bars of the face
    compression: Printed  # the direction's bars of the other face
    distribution_ok: bool
    compression_ok: bool


@dataclass(frozen=True)
class FootingDirection:
    direction: str  # choices.REBAR_DIRECTIONS
    effective_depth: Printed  # d, mm
    amount: SteelRatio  # 1) (a), 3): the upper, then the lower bars
    spacings: tuple[ClearSpacing, ClearSpacing]  # 5): the upper and the lower face
    shear: ShearRatio  # 6)
    general: StirrupSpacing  # 7)
    ductility: DuctilityLimit  # 8)
    capacity: CapacityRatio  # 9)
    faces: tuple[FaceBars, FaceBars]  # 10): the upper and the lower face

    @property
    def ok(self) -> bool:
        return all((self.amount.minimum_ok, self.amount.maximum_ok, *(item.ok for item in self.spacings),
                    self.shear.ok, self.general.ok, self.ductility.ok,
                    *(item.distribution_ok and item.compression_ok for item in self.faces)))


@dataclass(frozen=True)
class FootingDetailing:
    depth: Printed  # h, mm
    fck: Printed
    aggregate_max: Printed
    directions: tuple[FootingDirection, ...]  # 線路, 直角

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.directions)


def _layers(pier: PierInput, face: str, direction: str) -> list[PlacedLayer]:
    return [layer for layer in face_layout(pier.rebar.footing, face).layers if layer.direction == direction]


def _group(layers: list[PlacedLayer], face: str, direction: str) -> BarGroup:
    number = put(COUNT, sum((d(layer.per_metre) for layer in layers), Decimal(0)))
    return BarGroup.of(layers[0].diameter, number, f"{_FOOTING}.faces.{face}.{direction}.diameter_mm")


def _spacing(layers: list[PlacedLayer], aggregate_max: Printed) -> ClearSpacing:
    pitch = min((layer.pitch for layer in layers), key=d)
    return clear_spacing(put(LENGTH, d(pitch)), least_gap([[layer.center for layer in layers]]), layers[0].diameter,
                         aggregate_max, column=False)


def _direction(pier: PierInput, direction: str, depth: Printed, aggregate_max: Printed) -> FootingDirection:
    other = next(item for item in choices.REBAR_DIRECTIONS if item != direction)
    layers = {face: _layers(pier, face, direction) for face in (UPPER, LOWER)}
    groups = {face: _group(layers[face], face, direction) for face in (UPPER, LOWER)}
    crossing = {face: _group(_layers(pier, face, other), face, other) for face in (UPPER, LOWER)}
    lower = layers[LOWER]
    total = sum((d(layer.per_metre) for layer in lower), Decimal(0))
    centroid = sum((d(layer.per_metre) * d(layer.center) for layer in lower), Decimal(0)) / total
    effective = put(LENGTH, d(depth) - centroid)
    footing = pier.rebar.footing
    here = f"{_FOOTING}.stirrups.{direction}"
    diameter = need(footing.stirrups[direction].diameter, f"{here}.diameter_mm")
    pitch = need(footing.stirrups[direction].pitch, f"{here}.pitch_mm")
    grade = need(footing.materials.transverse, f"{_FOOTING}.materials.transverse")
    shear = shear_ratio(diameter, stirrup_width(footing, direction)[0], WIDTH, pitch, f"{here}.diameter_mm")
    faces = []
    for face, opposite in ((UPPER, LOWER), (LOWER, UPPER)):
        required = put(AREA, d(groups[face].area) / DISTRIBUTION_DIVISOR)
        faces.append(FaceBars(face=face, bars=groups[face], required=required, distribution=crossing[face].area,
                              compression=groups[opposite].area,
                              distribution_ok=d(crossing[face].area) >= d(required),
                              compression_ok=d(groups[opposite].area) >= d(required)))
    return FootingDirection(
        direction=direction, effective_depth=effective,
        amount=steel_ratio((groups[UPPER], groups[LOWER]), need(footing.materials.main, f"{_FOOTING}.materials.main"),
                           WIDTH, depth),
        spacings=(_spacing(layers[UPPER], aggregate_max), _spacing(lower, aggregate_max)), shear=shear,
        general=general_spacing(effective, groups[UPPER].diameter, diameter, pitch),
        ductility=ductility_limit(grade, shear.ratio), capacity=capacity_ratio(shear.ratio, grade, pier.materials.footing),
        faces=(faces[0], faces[1]))


def footing_detailing(pier: PierInput) -> FootingDetailing:
    depth = put(LENGTH, d(pier.substructure.h[6]) * 1000)
    aggregate_max = need(pier.rebar.footing.aggregate_max, f"{_FOOTING}.aggregate_max_mm")
    return FootingDetailing(depth=depth, fck=pier.materials.footing, aggregate_max=aggregate_max,
                            directions=tuple(_direction(pier, direction, depth, aggregate_max)
                                             for direction in choices.REBAR_DIRECTIONS))
