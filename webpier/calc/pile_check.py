"""0612 / 0622 基礎の照査 of a pile foundation (decision 89, ADR-0013, Example橋脚4 III-3.3): the pile head forces and the
footing top against the design limits of SOIL-JR.

The responses are those the frame of 0610 / 0620 gives (``calc.pile_frame``) once FEMPython has analyzed it:

- Vd, Vud: the largest compression and the largest tension at the head of a pile (the i end of the pile row's member,
  the axial force of its section force pickup) per pile (the row's member is bundled: its force over the piles of the row);
- δd, θd: the largest horizontal displacement and rotation of the footing top (the displacement pickup), each its own
  extreme as the sample's tables 2.5.11 take them.

The limits are SOIL-JR's (its 基礎照査連携用データ, .sdr; ``pipeline.pile_check`` reads them as tables into ``Limits``,
WebPier does not recalculate them): the design vertical bearing capacity Rvd, the design pull-out resistance Rud and
the limits of the horizontal displacement δLd and of the rotation θLd, of 長期支持性能, 短期支持性能 and 安定(地震時以外).
The checks are γi・Vd / Rvd, γi・Vud / Rud (only when a pile head is in tension: the sample omits it otherwise),
γi・δd / δLd and γi・θd / θLd, each not above 1.0. The 構造物係数 γi is 1.2 for the safety and 1.0 for the long and the
short term (the sample, III-3.3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput
from ._exact import d, put
from .foundation_check import FrameResult, LONGITUDINAL, TRANSVERSE, Direction, Requirement
from .pile_body import PileBodyResult, PileResponseError
from .pile_cast import PileCastResult
from .pile_joint import PileJointResult
from .frame import NodeRole
from .longitudinal.combinations import ExtractionGroup

FORCE = Precision(1, "kN")
DISPLACEMENT = Precision(3, "mm")
ROTATION = Precision(5, "rad")
RATIO = Precision(2, "")
_MILLI = Decimal(1000)

# (the requirement, its name in the .sdr, the extraction group whose pickup gives the responses, 構造物係数 γi)
REQUIREMENTS = ((Requirement.LONG_TERM, "長期支持性能", ExtractionGroup.SUPPORT_LONG_TERM, Printed(1.0, 1, "")),
                (Requirement.SHORT_TERM, "短期支持性能", ExtractionGroup.SUPPORT_SHORT_TERM, Printed(1.0, 1, "")),
                (Requirement.SAFETY, "安定(地震時以外)", ExtractionGroup.STABILITY, Printed(1.2, 1, "")))
SDR_DIRECTION = {False: "橋軸方向", True: "直角方向"}


@dataclass(frozen=True)
class Limits:
    """The design limits of one requirement as SOIL-JR's .sdr prints them (one pile; the rotation in 1/1000 rad)."""

    rk: Printed  # 基準支持力 Rk, kN
    pt: Printed  # 先端支持力比 pt
    fr: Printed  # 地盤抵抗係数 fr
    rvd: Printed  # 設計鉛直支持力 Rvd, kN
    rud: Printed  # 設計引き抜き抵抗力, kN
    delta: Printed  # δLd, mm
    indicator: str  # how it is limited: 0.4%L≦40mm
    theta: Printed  # θLd, rad


@dataclass(frozen=True)
class HeadForce:
    """The axial force at the head of a pile row's member in one pickup, as FEMPython returns it (kN, compression
    negative) with the combinations that give the two extremes."""

    largest: float
    largest_combination: int
    smallest: float
    smallest_combination: int


@dataclass(frozen=True)
class Extreme:
    """The largest absolute value of a displacement component of the footing top and its combination."""

    value: float  # m or rad, as the file prints it
    combination: int


# The pile head forces by (pickup, member); the footing top's displacement extremes by (pickup, "dx" or "rz").
HeadForces = Mapping[tuple[int, int], HeadForce]
Displacements = Mapping[tuple[int, str], Extreme]


@dataclass(frozen=True)
class PileMember:
    """A pile row of the frame: its member and the piles it bundles."""

    row: int
    member: int
    piles: int


@dataclass(frozen=True)
class Basis:
    """What the check reads before the frame is analyzed: the pile rows, the footing top and the limits."""

    members: tuple[PileMember, ...]
    node: int  # the footing top of the frame
    pickups: Mapping[str, int]  # the pickup of each requirement, by its value
    body_pickup: int  # the pickup of the 安全性（破壊）, whose section forces the pile body is checked with (decision 89)


@dataclass(frozen=True)
class Judged:
    value: Printed
    ok: bool


@dataclass(frozen=True)
class Column:
    """One requirement: its responses, limits and judgements."""

    requirement: Requirement
    name: str
    pickup: int
    gamma_i: Printed
    vd: Printed  # the largest compression at a pile head, per pile, kN
    vd_row: int
    vd_combination: int
    vud: Printed | None  # the largest tension at a pile head, per pile; None when no pile head is in tension
    vud_row: int | None
    vud_combination: int | None
    delta: Printed  # δd, mm
    delta_combination: int
    theta: Printed  # θd, rad
    theta_combination: int
    limits: Limits
    vertical: Judged
    pull_out: Judged | None
    horizontal: Judged
    rotation: Judged

    @property
    def judgements(self) -> tuple[Judged, ...]:
        return tuple(item for item in (self.vertical, self.pull_out, self.horizontal, self.rotation)
                     if item is not None)


@dataclass(frozen=True)
class PileCheckResult:
    basis: Basis
    columns: tuple[Column, ...]
    engineering_status: str  # "ok" when every check WebPier judges is satisfied (the columns, the steel pile body and joint), else "not_ok"
    body: PileBodyResult | None = None  # the pile body of a steel pipe pile (decision 89), SteelDan's checks
    joint: PileJointResult | None = None  # the joint of the pile with the footing (decision 90), Capacita's Mud
    cast: PileCastResult | None = None  # the pile body of a cast-in-place pile (decision 91), Capacita's pages


def prepare(pier: PierInput, frame_result: FrameResult, direction: Direction) -> Basis:
    """Everything of the check but the limits and the responses; a frame without piles is an input error."""
    frame = frame_result.frame
    if frame.piles is None:
        raise InputError("杭基礎の照査には杭の骨組が必要です（基礎形式が杭基礎ではありません）")
    numbers = {extraction.group: extraction.number for extraction in frame_result.extractions}
    members = tuple(PileMember(nodes.row.number, nodes.member, nodes.row.piles) for nodes in frame.pile_nodes)
    return Basis(members=members, node=frame.node(NodeRole.FOOTING_TOP).number,
                 pickups={requirement.value: numbers[group] for requirement, _, group, _ in REQUIREMENTS},
                 body_pickup=numbers[ExtractionGroup.FAILURE])


def _ratio(numerator: Decimal, denominator: Decimal) -> Judged:
    value = put(RATIO, numerator / denominator)
    return Judged(value, value.value <= 1.0)


def _column(basis: Basis, requirement: Requirement, name: str, gamma_i: Printed, limits: Limits, forces: HeadForces,
            displacements: Displacements) -> Column:
    pickup = basis.pickups[requirement.value]
    compression: list[tuple[Printed, int, int]] = []
    tension: list[tuple[Printed, int, int]] = []
    for member in basis.members:
        try:
            found = forces[(pickup, member.member)]
        except KeyError as exc:
            raise PileResponseError(f"杭頭の軸力のピックアップ {pickup}（部材 {member.member}）がありません") from exc
        piles = Decimal(member.piles)
        compression.append((put(FORCE, -d(found.smallest) / piles), member.row, found.smallest_combination))
        tension.append((put(FORCE, d(found.largest) / piles), member.row, found.largest_combination))
    vd, vd_row, vd_combination = max(compression, key=lambda item: item[0].value)
    vud, vud_row, vud_combination = max(tension, key=lambda item: item[0].value)
    try:
        horizontal, rotation = displacements[(pickup, "dx")], displacements[(pickup, "rz")]
    except KeyError as exc:
        raise PileResponseError(f"フーチング天端の変位のピックアップ {pickup}（節点 {basis.node}）がありません") from exc
    delta = put(DISPLACEMENT, d(horizontal.value) * _MILLI)
    theta = put(ROTATION, d(rotation.value))
    gamma = d(gamma_i)
    pulled = vud.value > 0
    return Column(
        requirement, name, pickup, gamma_i, vd, vd_row, vd_combination, vud if pulled else None,
        vud_row if pulled else None, vud_combination if pulled else None, delta, horizontal.combination, theta,
        rotation.combination, limits, _ratio(gamma * d(vd), d(limits.rvd)),
        _ratio(gamma * d(vud), d(limits.rud)) if pulled else None,
        _ratio(gamma * d(delta), d(limits.delta)), _ratio(gamma * d(theta), d(limits.theta)))


def check(basis: Basis, limits: Mapping[Requirement, Limits], forces: HeadForces,
          displacements: Displacements) -> PileCheckResult:
    """The three columns from the limits, the pile head forces and the footing top's displacements (``PileResponseError`` when a
    pickup is missing)."""
    columns = tuple(_column(basis, requirement, name, gamma_i, limits[requirement], forces, displacements)
                    for requirement, name, _, gamma_i in REQUIREMENTS)
    ok = all(item.ok for column in columns for item in column.judgements)
    return PileCheckResult(basis, columns, "ok" if ok else "not_ok")



def with_body(result: PileCheckResult, body: PileBodyResult) -> PileCheckResult:
    """The check with the pile body of a steel pipe pile: the status is not_ok when a check of the body is not satisfied too."""
    ok = result.engineering_status == "ok" and body.ok
    return replace(result, body=body, engineering_status="ok" if ok else "not_ok")


def with_joint(result: PileCheckResult, joint: PileJointResult) -> PileCheckResult:
    """The check with the joint of the pile with the footing: the status is not_ok when a check of the joint is not satisfied too."""
    ok = result.engineering_status == "ok" and joint.ok
    return replace(result, joint=joint, engineering_status="ok" if ok else "not_ok")


def with_cast(result: PileCheckResult, cast: PileCastResult) -> PileCheckResult:
    """The check with the pile body of a cast-in-place pile. Capacita returns no judgement (ADR-0008): the status stays what
    WebPier's own checks make it, and the body's own status is ``not_evaluated``."""
    return replace(result, cast=cast)


__all__ = ["Basis", "Column", "Displacements", "Extreme", "HeadForce", "HeadForces", "LONGITUDINAL", "Limits",
           "PileCheckResult", "PileMember", "with_body", "with_cast", "with_joint", "REQUIREMENTS", "PileResponseError", "SDR_DIRECTION", "TRANSVERSE", "check",
           "prepare"]
