"""The content of one NDU, in JRSNAP terms, before it is laid out as records.

Coordinates follow JRSNAP (manual p.38): x to the right, y downward, M clockwise; the origin is the footing top.
Every number is a value of the calc results or of the input, unchanged except for units (m → mm for the
section, the Ec mantissa × 10^7 kN/m2 → kN/mm2) and the sign of y.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...core.printed import Printed
from .profile import Profile

AXIAL = 4  # MLoadInfo load type: uniform along the element axis (D1 column weight)
LOCAL_Y = 1  # trapezoidal, normal to the element (self-weight inertia)


@dataclass(frozen=True)
class Analysis:
    """The displacement-increment analysis of DataInfo, from the input conditions of the direction."""

    steps: int  # divisions of the target displacement
    limited_final_step: int  # last step of the limited incremental load (EQL)
    target: Printed  # target horizontal displacement of the control node, signed as the earthquake


@dataclass(frozen=True)
class Joint:
    number: int
    x: Printed
    y: Printed  # downward from the footing top


@dataclass(frozen=True)
class Element:
    """One frame member as one element (and one native member): i is the upper (or left) end."""

    number: int
    i: int
    j: int
    length: Printed
    nonlinear: bool  # the column-base micro member (M-θ, automatic); the others are rigid regions
    title: str


@dataclass(frozen=True)
class RebarRow:
    center: Printed  # from the upper face of the section, mm
    diameter: Printed
    count: int


@dataclass(frozen=True)
class Shear:
    yield_strength: Printed
    diameter: Printed
    legs: int  # 帯鉄筋の方向別有効本数
    pitch: Printed


@dataclass(frozen=True)
class SectionData:
    width: Printed  # b, normal to the plane, mm
    height: Printed  # h, in the plane, mm
    shear_span: Printed  # La, control node to the footing top, mm
    fck: Printed
    ec: Printed  # kN/mm2
    aggregate_max: Printed
    yield_strength: Printed  # main bars
    main_layers: int  # tension layers counted from each face (DRTU = DRTL)
    main_pitch: Printed  # spacing of the main bars along the face (DELU = DELL)
    rows: tuple[RebarRow, ...]  # 方向別の鉄筋配置表 of the bending direction
    shear: Shear
    safety: tuple[Printed | Decimal | int, ...]  # SectSafe GC .. GBVO


@dataclass(frozen=True)
class Spring:
    node: int
    direction: int  # 1 horizontal, 2 vertical
    stiffness: Printed


@dataclass(frozen=True)
class Footing:
    """FootInfo: the direct foundation whose nonlinear rotational spring JRSNAP derives."""

    node: int
    b: Printed  # in the plane
    l: Printed
    kv: Printed  # vertical subgrade reaction coefficient, short term
    depth: Printed  # Df
    gamma1: Printed  # supporting layer, submerged
    gamma2: Printed  # cover above the base
    phi: Printed


@dataclass(frozen=True)
class MemberLoad:
    element: int
    kind: int  # AXIAL or LOCAL_Y
    start: Printed  # at i
    end: Printed | None  # at j; None for a uniform axial load
    label: str


@dataclass(frozen=True)
class JointLoad:
    node: int
    h: Printed
    n: Printed
    m: Printed
    label: str


@dataclass(frozen=True)
class LoadCase:
    number: int
    title: str
    increment: int  # 0 fixed, 1 incremental, 4 limited incremental
    member_loads: tuple[MemberLoad, ...]
    joint_loads: tuple[JointLoad, ...]


@dataclass(frozen=True)
class Combination:
    rho_m: Printed
    alpha_f: Printed
    coefficients: tuple[int, ...]  # 1 or 0 for each load case


@dataclass(frozen=True)
class NduModel:
    profile: Profile
    analysis: Analysis
    control: int  # joint
    origin: int  # joint at the footing top
    joints: tuple[Joint, ...]
    elements: tuple[Element, ...]
    section: SectionData
    springs: tuple[Spring, Spring]  # horizontal Ks, vertical Kv at the footing base
    footing: Footing
    cases: tuple[LoadCase, ...]
    combinations: tuple[Combination, ...]
