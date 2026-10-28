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

    EA17 = "EA-17の規定"
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
    foundation: str  # 基礎形式, one of choices.FOUNDATION_TYPES


@dataclass(frozen=True)
class Span:
    """上部構造 of one side: the girder resting on this pier."""

    l1: Printed
    span: Printed
    l2: Printed
    impact: Printed | None  # None with a load model (decision 70), like radius and speed
    radius: Printed | None
    speed: Printed | None
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
    """上部構造.列車: the vehicle's loads are the program's (calc.vehicles, decision 101)."""

    vehicle: str
    braking_rule: BrakingRule
    cars: int | None  # 編成数 of a vehicle of repeated cars (P-16); blank for EA-17, whose train the standard fixes
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
    snow2: Printed | None  # None with a load model (decision 70), like the snow loads after it and the shares
    snow10: Printed | None
    snow30: Printed | None
    shares: Shares | None


@dataclass(frozen=True)
class EndReaction:
    """A/D: the far end of each girder, entered as totals."""

    d1: Printed
    d2: Printed
    snow2: Printed | None  # None with a load model (decision 70)
    snow10: Printed | None
    snow30: Printed | None


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
    cohesion: Printed | None  # 粘着力 c (decision 80; it replaced the 一軸圧縮強度 qu)
    deformation_modulus: Printed | None
    reduction: Printed | None  # De of the layer in liquefaction; None is blank, 1 (the layer does not liquefy)
    # Vs, m/s (decision 97): the 地盤変位 of a pile foundation on G3〜G5 needs it above the base; None is blank
    shear_wave_velocity: Printed | None = None


@dataclass(frozen=True)
class Soil:
    """The first layer is 表層; its thickness may be blank, the rest of Df (decision 64, calc.embedment)."""

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
class CastInPlacePile:
    """場所打ち杭: its diameter, concrete strength and construction condition (its reinforcement is 鉄筋.杭, decision 92);
    None is blank."""

    diameter: Printed | None  # 杭径 D, m
    fck: Printed | None  # f'ck, N/mm2
    condition: str | None  # 施工条件, one of choices.CAST_IN_PLACE_CONDITIONS


@dataclass(frozen=True)
class PileJoint:
    """杭とフーチングの結合部 (CONTEXT.md, decision 90) of a steel soil cement pile: the anchor bars inside the pipe and the
    strength of the concrete filling it; None is blank."""

    bar_diameter: Printed | None  # 軸方向鉄筋の径 (D38 → 38), mm
    bar_count: int | None  # 軸方向鉄筋の本数
    bar_grade: str | None  # 軸方向鉄筋の材質, one of choices.STEEL_GRADES
    bar_centroid: Printed | None  # 鉄筋重心位置, mm from the outer edge of the pipe (the outer diameter less the corrosion)
    fill_fck: Printed | None  # 中詰めコンクリートの f'ck, N/mm2
    fill_aggregate_max: Printed | None  # 中詰めコンクリートの粗骨材の最大寸法, mm (decision 99)


@dataclass(frozen=True)
class SteelSoilCementPile:
    """鋼管ソイルセメント杭; None is blank."""

    soil_cement_diameter: Printed | None  # ソイルセメント径 Dsc, m
    steel_diameter: Printed | None  # 鋼管外径 Dsp, m
    thickness: Printed | None  # 鋼管厚 t, mm (it includes the corrosion allowance)
    corrosion: Printed | None  # 腐食代 c, mm
    grade: str | None  # 鋼管材質, one of choices.STEEL_PIPE_GRADES (the pile body check, decision 89)
    joint: PileJoint  # 結合部 (the joint check, decision 90)


@dataclass(frozen=True)
class PileLayout:
    """杭の配置 (CONTEXT.md): the positions of the columns of piles in each direction (m from the centre of the footing,
    in the direction of the frame's x and of its y), grid or staggered, and the piles left out. A column is numbered
    from 1 in the order of the positions; ``removed`` holds (column along the line, column across it)."""

    pattern: str | None  # 形式, one of choices.PILE_ARRANGEMENTS
    along: tuple[Printed, ...]  # 線路方向の列の位置
    across: tuple[Printed, ...]  # 線路直角方向の列の位置
    removed: tuple[tuple[int, int], ...]  # 抜く杭


@dataclass(frozen=True)
class PileFoundation:
    """杭基礎 (decision 80): read for every 基礎形式 as to form and digits; a pile foundation uses the items of its type."""

    length: Printed | None  # 杭長 L, m
    unit_weight: Printed | None  # 杭の単位体積重量, kN/m3
    cast_in_place: CastInPlacePile
    steel_soil_cement: SteelSoilCementPile
    layout: PileLayout


@dataclass(frozen=True)
class Reserved:
    """Validated fields kept for features that are not calculated yet (decision 19)."""

    skew_angle: Printed
    skew_type: int
    centrifugal_direction: tuple[str, str] | None  # None with a load model (decision 70)


@dataclass(frozen=True)
class JrsnapConditions:
    """The editable JRSNAP section conditions of one direction (CONTEXT.md JRSNAP入力モデル); None is blank."""

    shear_factor_vcd: Printed | None  # γb of Vcd
    shear_factor_vsd: Printed | None  # γb of Vsd
    shear_factor_vdd: Printed | None  # γb of Vdd
    steps: int | None  # displacement increments to the target (DataInfo 3)
    limited_final_step: int | None  # last step of the limited incremental load (DataInfo 6)
    target_displacement: Printed | None  # magnitude (> 0) at the control node, m; the export signs it (DataInfo 19)
    max_seismic: Printed  # 最大震度 of the incremental load, 1.00 when blank (decision 112; ExOptLoad 2, DataInfo 5)


@dataclass(frozen=True)
class Jrsnap:
    longitudinal: JrsnapConditions  # jrsnap_longitudinal (0710)
    transverse: JrsnapConditions  # jrsnap_transverse (0720)


@dataclass(frozen=True)
class SeismicDesign:
    """耐震設計条件 (CONTEXT.md): one for the pier, shared by both directions; None is blank."""

    region: str | None  # 地域別, one of choices.REGIONS
    ground_class: str | None  # 地盤区分, one of choices.GROUND_CLASSES
    liquefaction_index: str | None = None  # 液状化指数, one of choices.LIQUEFACTION_INDEXES (decision 95)


@dataclass(frozen=True)
class ColumnCheck:
    """柱の断面照査 (CONTEXT.md, decision 48): one set for the column, shared by both directions; None is blank."""

    environment: str | None  # 水掛かりの程度, one of choices.WATER_EXPOSURES
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

    environments: dict[str, str | None]  # 水掛かりの程度 by face (fields.BEAM_SURFACES: 上面, 下面, 側面)
    appearance: str | None  # 外観の照査, one of choices.APPEARANCE_CHECKS
    fatigue: FatigueTrains


@dataclass(frozen=True)
class CalculationSection:
    """計算上断面 of the column (CONTEXT.md, decision 118): the rectangle it is an RC section with, which an add-in
    gives in place of its 実断面 B6 × W6."""

    b: Printed  # along the track, in place of B6
    w: Printed  # across the track, in place of W6


@dataclass(frozen=True)
class PierInput:
    substructure: Substructure
    spans: Spans
    train: Train | None  # None with a load model (decision 70)
    reactions: Reactions
    soil: Soil
    materials: Materials
    reserved: Reserved
    piles: PileFoundation  # 杭基礎 (decision 80); used when substructure.foundation is a pile foundation
    rebar: RebarInput
    seismic_design: SeismicDesign
    column_check: ColumnCheck  # 柱の断面照査 (decision 48)
    cantilever_check: CantileverCheck  # 片持ち梁の照査 (decision 59)
    jrsnap: Jrsnap
    outputs: tuple[str, ...]  # the chosen 出力項目 (decision 72), in the order of inputs.outputs.OUTPUT_KEYS
    calculation_section: CalculationSection | None = None  # an add-in's (decision 118); None: the 実断面

    @property
    def column_section(self) -> tuple[Printed, Printed]:
        """B and W of the column as an RC section (decision 118): its 計算上断面, or the 実断面 B6 × W6 without one.
        Its shape (weight, inertia, buoyancy, wind, faces) is always the 実断面."""
        if self.calculation_section is None:
            return self.substructure.b[6], self.substructure.w[6]
        return self.calculation_section.b, self.calculation_section.w
