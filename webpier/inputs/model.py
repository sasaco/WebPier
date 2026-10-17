"""The validated pier input shared by every stage.

Every number is a Printed value at the digits of the input sheet, so the value
echoed in a report is exactly the value calculated with (ADR-0003).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.printed import Printed


class BrakingRule(Enum):
    """How braking and starting forces are derived for the selected vehicle."""

    EA17 = "EA-17の規定式"
    AXLE = "軸重式"


@dataclass(frozen=True)
class Substructure:
    """下部構造. ``b``/``w``/``h`` map the drawing index (1..9, 1..6) to a size."""

    b: dict[int, Printed]
    w: dict[int, Printed]
    h: dict[int, Printed]
    df1: Printed
    df2: Printed
    hw1: Printed
    hw2: Printed
    hw3: Printed
    unit_weight_body: Printed
    unit_weight_footing: Printed
    unit_weight_overburden: Printed


@dataclass(frozen=True)
class Span:
    """上部構造 of one side: the girder resting on this pier."""

    l1: Printed
    span: Printed
    l2: Printed
    impact: Printed
    radius: Printed
    speed: Printed
    heights: dict[int, Printed]
    hs: Printed
    f: Printed
    bearing: str
    mu: Printed
    recovery_brake_coefficient: Printed | None


@dataclass(frozen=True)
class Spans:
    origin: Span
    end: Span


@dataclass(frozen=True)
class Train:
    vehicle: str
    braking_rule: BrakingRule
    car_length: Printed
    a1: Printed
    a2: Printed
    axle_load: Printed
    earthquake_load: Printed
    cars: int
    height_wind: Printed
    height_centrifugal: Printed
    height_seismic: Printed
    factor_service: Printed
    factor_ultimate: Printed
    factor_fatigue: Printed


@dataclass(frozen=True)
class Shares:
    """Train share of the down (L1) and up (L2) track; L3/L4 must be blank (decision 23)."""

    l1: Printed
    l2: Printed


@dataclass(frozen=True)
class Bearing:
    position: Printed
    d1: Printed
    d2: Printed
    snow2: Printed
    snow10: Printed
    snow30: Printed
    shares: Shares


@dataclass(frozen=True)
class EndReaction:
    """A/D: the far end of each girder, entered as totals."""

    d1: Printed
    d2: Printed
    snow2: Printed
    snow10: Printed
    snow30: Printed


@dataclass(frozen=True)
class Reactions:
    """Ten bearing slots per pier-side support; None is an empty slot."""

    a: EndReaction
    b: tuple[Bearing | None, ...]
    c: tuple[Bearing | None, ...]
    d: EndReaction


@dataclass(frozen=True)
class SoilLayer:
    name: str
    thickness: Printed | None
    soil_type: str
    n_value: Printed | None
    unit_weight_wet: Printed | None
    unit_weight_submerged: Printed | None
    friction_angle: Printed | None
    friction_angle_limit: Printed | None
    compressive_strength: Printed | None
    deformation_modulus: Printed | None


@dataclass(frozen=True)
class Soil:
    """The first layer is 表層; its thickness is derived, not entered."""

    layers: tuple[SoilLayer, ...]

    @property
    def surface(self) -> SoilLayer:
        return self.layers[0]

    @property
    def support(self) -> SoilLayer:
        return next(layer for layer in self.layers if layer.name == "支持層")


@dataclass(frozen=True)
class Materials:
    """Concrete design strength of each part, N/mm2."""

    beam: Printed
    column: Printed
    footing: Printed


@dataclass(frozen=True)
class Pile:
    x: Printed | None
    x_count: int | None
    y: Printed | None
    y_count: int | None


@dataclass(frozen=True)
class Reserved:
    """Validated fields kept for features that are not calculated yet (decision 19)."""

    skew_angle: Printed
    skew_type: int
    pile_unit_weight_vertical: Printed | None
    pile_unit_weight_inertia: Printed | None
    cast_in_place_condition: str | None
    piles: tuple[Pile, ...]
    centrifugal_direction: tuple[str, str]


@dataclass(frozen=True)
class PierInput:
    substructure: Substructure
    spans: Spans
    train: Train
    reactions: Reactions
    soil: Soil
    materials: Materials
    reserved: Reserved
