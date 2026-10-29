"""The content of the NDU of a pile foundation, in JRSNAP terms, before it is laid out as records (decision 93).

The column, the footing and the pile heads are frame members as in the NDU of a direct foundation; the piles are what
JRSNAP's 連携 of a .sdc makes of them (``JRSNAP_Input``, checked against its sample 01_サンプル(V53)：RC橋脚L,
``.claude/docs/plans/pile-ndu-fields.md``): each pile row is one member from its head to its tip, cut into the elements of
``calc.pile_seismic``, whose elements (a range of them, ``PileRange``) carry the ground springs of the row and have the
nonlinear M-φ of a section of the pile; the nodes of the row carry the vertical springs and bearing capacity of the pile
surface. The first element of the member, from the head to the footing base, is a rigid region.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ...core.printed import Precision, Printed
from .model import Analysis, Combination, Joint, LoadCase
from .profile import Profile
from .records import Field, Record

RIGID, COLUMN, PILE = 1, 2, 3  # the kind of an element: a rigid region, a micro member with an M-θ, a pile element
EDSPX = Precision(5, "m")  # the 地盤変位 of a node, as JRSNAP_Input takes it (‐999.99999～9999.99999 m)
M_THETA, M_PHI = 1, 2  # the nonlinear model of a section


@dataclass(frozen=True)
class Member:
    """MemberInfo…MemberKUI: a run of elements between two joints; the lengths of its elements as ``(length, count)``."""

    number: int
    title: str
    i: int
    j: int
    length: Printed
    divisions: tuple[tuple[Printed, int], ...]
    depth_piles: int = 1  # MemberOkuyuki: the piles in the depth, for a pile row
    nonlinear: bool = False  # MemberShogen
    pile: bool = False  # MemberKUI


@dataclass(frozen=True)
class GroundElement:
    """JibanShogenInfo: the horizontal spring of the ground and the effective resistance earth pressure along an element."""

    horizontal: Printed
    pressure_top: Printed
    pressure_bottom: Printed


@dataclass(frozen=True)
class FrameElement:
    number: int
    i: int
    j: int
    kind: int  # RIGID, COLUMN or PILE
    nonlinear: int  # the number of its NonLinInfo, 0 for a rigid region
    ground: GroundElement | None = None


@dataclass(frozen=True)
class NonLinear:
    """NonLinInfo: the nonlinear model of an element: its section (M-θ with the 破壊形態, or M-φ) and its title."""

    section: int
    model: int  # M_THETA or M_PHI
    failure: int  # 1 曲げ, 2 せん断 (the AP card's S)
    ends: tuple[int, int]
    depth_piles: int
    title: str


@dataclass(frozen=True)
class PileRange:
    """KGInfo: a pile row is the member *member*, and its elements from *first* to *last* the piles."""

    member: int
    first: int
    last: int


@dataclass(frozen=True)
class Support:
    """SuppotInfo of a pile node: ``kind`` 2 is the vertical spring of the surface (what JRSNAP calls its Dst)."""

    node: int
    kind: int
    values: tuple[Field, ...]


@dataclass(frozen=True)
class GroundLoad:
    """ELoadInfo and the load increment of DataInfo: the 地盤変位 of the 応答変位法 (decision 97), all on at the step *steps*
    (the 最大応答震度 × the divisions of the incremental load, where the analysis stops), at each node as (joint, EDSPX)."""

    steps: int
    displacements: tuple[tuple[int, Printed], ...]


@dataclass(frozen=True)
class PileNduModel:
    profile: Profile
    analysis: Analysis
    control: int  # joint
    origin: int  # joint at the footing top
    joints: tuple[Joint, ...]
    members: tuple[Member, ...]
    elements: tuple[FrameElement, ...]
    nonlinear: tuple[NonLinear, ...]  # in the order of the elements that have one
    sections: tuple[tuple[Record, ...], ...]  # the records of each section (SectTitle … SectSafe), numbered from 1
    piles: tuple[PileRange, ...]
    supports: tuple[Support, ...]
    cases: tuple[LoadCase, ...]
    combinations: tuple[Combination, ...]
    shear_span: Printed  # La of the column's M-θ member, mm (the project of Aggre-SE takes it, not the NDU)
    ground: GroundLoad | None = None  # the NDU of the 応答変位法: the load increment with the 地盤変位 (decision 97)


@dataclass(frozen=True)
class PileSection:
    """A circular RC section of a pile (SectInfo … SectSafe of shape 2): the bars and the hoops of a part of the pile."""

    title: str
    radius: Printed  # mm
    axial_force: Printed | None  # kN of one pile; None: not given, JRSNAP takes the axial force of the analysis
    fck: Printed  # N/mm2, the nominal strength (the reduction of the construction condition is JRSNAP's)
    construction: int  # the code of the construction condition in the CTS and EC' fields (表2-30: -3 自然泥水)
    aggregate_max: Printed
    yield_strength: Printed  # the main bars
    center: Printed  # 芯かぶり of the main bars from the edge, mm
    diameter: Printed
    count: int
    hoop_yield: Printed
    hoop_diameter: Printed
    hoop_legs: int  # 1 組 is 2
    hoop_pitch: Printed
    safety: tuple[Printed | Decimal | int, ...]  # SectSafe: the factors of the manual's 表2-29, the shear ones are inputs
    inner_radius: Printed | None = None  # mm, the 内周半径 RR2 of the manual's 表2-28 (a solid pile: None, written 0)


@dataclass(frozen=True)
class JointHeadSection:
    """The joint of a 鋼管ソイルセメント杭 with the footing (shape 501, 鋼管杭頭部接合部材, manual 表2-55・2-56; decision 122): the
    virtual RC circle the pipe confines, of the radius of the pipe, with the anchor bars in one ring."""

    title: str
    radius: Printed  # mm
    thickness: Printed  # the effective wall thickness of the pipe, mm
    fck: Printed  # the fill's f'ck, N/mm2
    confined: Printed  # 接合部圧縮強度: f'cck of the fill confined by the pipe, N/mm2 (calc.pile_joint.confined_strength)
    aggregate_max: Printed  # mm
    bar_yield: Printed  # N/mm2
    center: Printed  # 芯かぶり of the anchor bars from the edge, mm
    bar_diameter: Printed
    bar_count: int
    pipe_yield: Printed  # f_syk of the pipe, N/mm2
    safety: tuple[Printed | Decimal | int, ...]


@dataclass(frozen=True)
class PipeSection:
    """The steel pipe of a 鋼管ソイルセメント杭 (shape 8 of the kind 鋼管杭, M-φ only, manual 表2-53・2-54; decision 122): the pipe
    alone, less the corrosion allowance; the soil cement is not counted."""

    title: str
    diameter: Printed  # the outer diameter less the corrosion on both sides, mm
    thickness: Printed  # the effective wall thickness, mm
    yield_strength: Printed  # f_syk, N/mm2
    safety: tuple[Printed | Decimal | int, ...]
