"""The validated pier input shared by every stage.

Every number is a Printed value at the digits of the input sheet, so the value
echoed in a report is exactly the value calculated with (ADR-0003).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from ..core.printed import Printed

if TYPE_CHECKING:  # rebar.py reads the choices, which read this module
    from .rebar import RebarInput


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
    # decision 59 (0900): the rubber bearings and the stoppers of the girder on this pier, and those on the cantilever
    # beam; None is blank
    rubber_count: int | None = None  # ゴム支承の箇所数
    stopper_count: int | None = None  # ストッパーの箇所数
    rubber_on_cantilever: int | None = None  # 片持ち梁上のゴム支承
    stopper_on_cantilever: int | None = None  # 片持ち梁上のストッパー


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
class JrsnapConditions:
    """The editable JRSNAP section conditions of one direction (CONTEXT.md JRSNAP入力モデル); None is blank."""

    shear_factor_vcd: Printed | None  # γb of Vcd
    shear_factor_vsd: Printed | None  # γb of Vsd
    shear_factor_vdd: Printed | None  # γb of Vdd
    steps: int | None  # displacement increments to the target (DataInfo 3)
    limited_final_step: int | None  # last step of the limited incremental load (DataInfo 6)
    target_displacement: Printed | None  # magnitude (> 0) at the control node, m; the export signs it (DataInfo 19)


@dataclass(frozen=True)
class Jrsnap:
    longitudinal: JrsnapConditions  # jrsnap_longitudinal (0710)
    transverse: JrsnapConditions  # jrsnap_transverse (0720)


@dataclass(frozen=True)
class SeismicDesign:
    """耐震設計条件 (CONTEXT.md): one for the pier, shared by both directions; None is blank."""

    region: str | None  # 地域別, one of choices.REGIONS
    ground_class: str | None  # 地盤区分, one of choices.GROUND_CLASSES


@dataclass(frozen=True)
class ColumnCheck:
    """柱の断面照査 (CONTEXT.md, decision 48): one set for the column, shared by both directions; None is blank."""

    environment: str | None  # 鋼材の腐食に対する環境条件, one of choices.CORROSION_ENVIRONMENTS
    appearance: str | None  # 外観の照査, one of choices.APPEARANCE_CHECKS
    ecsd: Printed | None  # ε'csd, ×10⁻⁶
    body: str | None  # 適用基準の機関, one of choices.STANDARD_BODIES
    jr001: str | None  # JR-001 ひび割れ幅制限値に用いるかぶりは 100mm を上限とする; one of choices.ADOPTIONS
    jr004: str | None  # JR-004 せん断耐力における βn 算定時の Mud は軸力を考慮しない; one of choices.ADOPTIONS


@dataclass(frozen=True)
class FatigueTrains:
    """片持ち梁の照査.疲労 (decision 59): the trains of the fatigue check; None is blank."""

    passenger_trains: int | None  # 旅客列車本数 (A列車), per track per day
    freight_trains: int | None  # 貨物列車本数 (B列車)
    service_life: int | None  # 設計耐用年数, years
    # 1編成当りの等価繰返し回数 by (train, S-N slope): ("A列車", "k=0.06") …, as fields.REPETITION_SLOPES name them
    repetitions: dict[tuple[str, str], Printed | None]


@dataclass(frozen=True)
class CantileverCheck:
    """片持ち梁の照査 (CONTEXT.md, decision 59): the conditions of the cantilever beam check, shared by both
    overhangs; None is blank."""

    environments: dict[str, str | None]  # 鋼材の腐食に対する環境条件 by face (fields.BEAM_SURFACES: 上面, 下面, 側面)
    appearance: str | None  # 外観の照査, one of choices.APPEARANCE_CHECKS
    fatigue: FatigueTrains


@dataclass(frozen=True)
class PierInput:
    substructure: Substructure
    spans: Spans
    train: Train
    reactions: Reactions
    soil: Soil
    materials: Materials
    reserved: Reserved
    rebar: RebarInput
    seismic_design: SeismicDesign
    column_check: ColumnCheck  # 柱の断面照査 (decision 48)
    cantilever_check: CantileverCheck  # 片持ち梁の照査 (decision 59)
    jrsnap: Jrsnap
