"""The geometry of one cantilever of the beam (0900, decision 59; Example2 13-23, 13-24).

The beam overhangs the column on both sides across the track: the left side (bearings at a negative 支承位置,
overhang W4) and the right side (positive, W5). The bearings on a cantilever are the slots of either girder whose
position lies beyond the column face (|支承位置| > W6/2); a bearing beyond the beam end is an input error. Their
loads act at X = |支承位置| − W6/2 from the design section, the column face, and at e = ∓f along the track (the
girder's bearing position f, towards the origin girder negative), which twists the beam. A horizontal force at the
bearing seat twists it with the arm Y = (H2 + H3)/2, half the beam depth at the column face.

The self weight of the cantilever is the rectangular part B1 × H2 × W (arm W/2) and the haunch B1 × H3 × W × 1/2
(arm W/3, the haunch being deepest at the column face), with the unit weight of the beam (下部構造.単位体積重量.梁・躯体).
Example2 types the end girder's X as 0.645 (its own 2.95 − 2.25 = 0.700); the position is used (decision 59).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ...core.errors import InputError
from ...core.printed import FORCE, LENGTH, MOMENT, Precision, Printed
from ...inputs import PierInput
from .._exact import d, put, total
from ..moving_load import Girder
from ..reaction.dead import BearingLoads, DeadResult

SQUARE = Precision(4, "m2")  # Σ xi² of the bearing positions (Example2 13-9: 33.3800)
HALF, THIRD = Decimal("0.5"), Decimal(1) / Decimal(3)
GIRDER_SIDES = {Girder.ORIGIN: "起点側", Girder.END: "終点側"}


class Side(Enum):
    """A cantilever of the beam, by the sign of the bearing positions it carries."""

    LEFT = "左側"  # 支承位置 < 0, overhang W4
    RIGHT = "右側"  # 支承位置 > 0, overhang W5

    @property
    def sign(self) -> int:
        return -1 if self is Side.LEFT else 1


@dataclass(frozen=True)
class NumberedBearing:
    """One occupied bearing slot of a girder, numbered G1.. by position (Example2 表 13.1)."""

    number: int  # 1-based, in ascending position
    loads: BearingLoads

    @property
    def label(self) -> str:
        return f"Ｇ{self.number}桁"

    @property
    def position(self) -> Printed:
        return self.loads.bearing.position


@dataclass(frozen=True)
class GirderBearings:
    """Every bearing of one girder on this pier, and the torsional constant of their positions."""

    girder: Girder
    bearings: tuple[NumberedBearing, ...]
    sum_squares: Printed  # Σ xi², m²: a torque M about the pier axis loads bearing i with M·|xi| / Σ xi²

    @property
    def side(self) -> str:
        return GIRDER_SIDES[self.girder]


@dataclass(frozen=True)
class CantileverBearing:
    """A bearing on this cantilever: its arms about the design section."""

    girder: Girder
    bearing: NumberedBearing
    x: Printed  # from the column face, m
    e: Printed  # along the track from the beam axis, m (origin girder negative): the arm of its torsion

    @property
    def label(self) -> str:
        return f"{GIRDER_SIDES[self.girder]} {self.bearing.label}"


@dataclass(frozen=True)
class SelfWeightPart:
    width: Printed  # B1, m
    depth: Printed  # H2 (rectangle) or H3 (haunch), m
    length: Printed  # the overhang W, m
    force: Printed  # kN
    arm: Printed  # from the column face, m
    moment: Printed  # kN m


@dataclass(frozen=True)
class SelfWeight:
    unit_weight: Printed  # kN/m3
    rectangle: SelfWeightPart  # ① γ × B1 × H2 × W, arm W/2
    haunch: SelfWeightPart  # ② γ × B1 × H3 × W × 1/2, arm W/3
    force: Printed  # Σ
    moment: Printed  # Σ


@dataclass(frozen=True)
class Geometry:
    side: Side
    overhang: Printed  # W4 or W5, m
    half_column: Printed  # W6/2: the column face from the pier axis, m
    torsion_arm: Printed  # Y = (H2 + H3)/2, m
    girders: dict[Girder, GirderBearings]
    bearings: tuple[CantileverBearing, ...]  # on this cantilever, origin girder first
    self_weight: SelfWeight


def numbered(dead: DeadResult) -> dict[Girder, GirderBearings]:
    """The bearings of both girders, numbered by position, with Σ xi² of each girder."""
    found = {}
    for girder, loads in ((Girder.ORIGIN, dead.origin), (Girder.END, dead.end)):
        ordered = sorted(loads.bearings, key=lambda item: item.bearing.position.value)
        bearings = tuple(NumberedBearing(number, item) for number, item in enumerate(ordered, 1))
        found[girder] = GirderBearings(girder, bearings,
                                       put(SQUARE, total(d(item.position) ** 2 for item in bearings)))
    return found


def _self_weight(pier: PierInput, overhang: Printed) -> SelfWeight:
    s = pier.substructure
    gamma, b1 = s.unit_weight_body, s.b[1]

    def part(depth: Printed, share: Decimal, arm_ratio: Decimal) -> SelfWeightPart:
        force = put(FORCE, d(gamma) * d(b1) * d(depth) * d(overhang) * share)
        arm = put(LENGTH, d(overhang) * arm_ratio)
        return SelfWeightPart(b1, depth, overhang, force, arm, put(MOMENT, d(force) * d(arm)))

    rectangle, haunch = part(s.h[2], Decimal(1), HALF), part(s.h[3], HALF, THIRD)
    return SelfWeight(gamma, rectangle, haunch, put(FORCE, total((rectangle.force, haunch.force))),
                      put(MOMENT, total((rectangle.moment, haunch.moment))))


def geometry(pier: PierInput, dead: DeadResult, side: Side) -> Geometry:
    """The cantilever of *side*; its bearings may be none (the caller decides what that means)."""
    s = pier.substructure
    overhang = s.w[4] if side is Side.LEFT else s.w[5]
    half = put(LENGTH, d(s.w[6]) * HALF)
    arm = put(LENGTH, (d(s.h[2]) + d(s.h[3])) * HALF)
    girders = numbered(dead)
    bearings = []
    for girder, span, slots in ((Girder.ORIGIN, pier.spans.origin, "B支点"), (Girder.END, pier.spans.end, "C支点")):
        for item in girders[girder].bearings:
            position = d(item.position)
            if position * side.sign <= d(half):
                continue
            if abs(position) > d(half) + d(overhang):
                raise InputError(f"上部工反力.{GIRDER_SIDES[girder]}.{slots}[{item.loads.slot}].支承位置: はりの張出し"
                                 f"（W6/2 + {'W4' if side is Side.LEFT else 'W5'} = {half.value + overhang.value:g} m）"
                                 f"の外にあります（{item.position.value:g} m）")
            e = put(LENGTH, -d(span.f) if girder is Girder.ORIGIN else d(span.f))
            bearings.append(CantileverBearing(girder, item, put(LENGTH, abs(position) - d(half)), e))
    return Geometry(side, overhang, half, arm, girders, tuple(bearings), _self_weight(pier, overhang))
