"""The contract between WebPier and a 荷重モデル (CONTEXT.md, ADR-0010, decision 70), version ``CONTRACT_VERSION``.

A load model gives what comes to the pier through its bearings other than the dead loads: the 支承作用 of each basic
case (the vertical force, the horizontal forces along and across the track and the height each acts at above the
bearing seat, per bearing), how each basic case behaves (its ground springs and, in the static nonlinear analysis, its
increment and direction), and the combinations of the frames, of the seismic analyses and of the cantilever beam,
assigned to the extraction groups and to the rows of Capacita's force table the application fixes.

WebPier keeps the dead loads D1 and D2, the buoyancy, the wind on the pier body and the 橋脚自重の慣性力; a
combination refers to them by their ids (``APP_*``). Everything else here is the load model's: the application turns
the 支承作用 into the frame and cantilever loads, writes FrameWeb, the NDU and the reports in its own format, and
prints the sections the load model writes about where its values come from.

The values are Decimal at their printed digits (ADR-0003): forces 2 decimals (kN), heights 3 (m), the wind pressures
1 (kN/m2) and the factors as written. A load model imports this package only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from ..core.errors import InputError

CONTRACT_VERSION = 1

# The basic cases of the application, by the id a combination refers to them with.
D1 = "D1"  # 固定死荷重: the dead load reactions D1 of the bearings and the pier body
D2 = "D2"  # 付加死荷重: the D2 reactions of the bearings and the overburden soil
WP_HIGH = "WP_HIGH"  # 浮力（高水位）
WP_NORMAL = "WP_NORMAL"  # 浮力（平水位）
WP_LOW = "WP_LOW"  # 浮力（低水位）
EQ2 = "EQ2"  # 橋脚自重の慣性力 (the seismic analyses)
PIER_WIND = "PIER_WIND_"  # + n: the wind on the pier body with the n-th pressure of pier_wind_pressures (0620)


def pier_wind(number: int) -> str:
    """The id of the wind on the pier body with the *number*-th (1, 2, …) pressure of ``pier_wind_pressures``."""
    return f"{PIER_WIND}{number}"


class Side(Enum):
    ORIGIN = "origin"  # 起点側: the bearings B of the origin girder on this pier
    END = "end"  # 終点側: the bearings C of the end girder


class SpringTerm(Enum):
    """The ground springs a basic case is analysed with (decision 36)."""

    LONG = "long_term"  # バネ 1 of 8-9
    SHORT = "short_term"  # バネ 2


class ExtractionGroup(Enum):
    """The 8 extraction groups of 8-11 the frame combinations are assigned to."""

    FAILURE = 1
    PERMANENT_VARIABLE = 2
    PERMANENT = 3
    VARIABLE = 4
    DAMAGE = 5
    STABILITY = 6
    SUPPORT_LONG_TERM = 7
    SUPPORT_SHORT_TERM = 8


class CantileverRow(Enum):
    """The rows of Capacita's force table of the cantilever beam (0910), by their id."""

    DURABILITY_STRESS = 0  # 耐久性 縁応力度検討用
    DURABILITY_PERMANENT = 1  # 耐久性（永久荷重）
    DURABILITY_VARIABLE = 2  # 耐久性（変動荷重）
    FATIGUE_PERMANENT = 3  # 安全性（疲労破壊）永久作用
    FATIGUE_VARIABLE = 4  # 安全性（疲労破壊）永久＋変動
    SAFETY = 5  # 安全性（破壊）
    SERVICEABILITY_DAMAGE = 6  # 使用性（損傷）
    RESTORABILITY_EQ = 7  # 復旧性（損傷）地震時


class Increment(Enum):
    """How the static nonlinear analysis treats a seismic basic case (10-12 荷重種別)."""

    FIXED = "fixed"  # 固定
    INCREMENTAL = "incremental"  # 増分
    LIMITED = "limited_incremental"  # 限定増分


class SeismicDirection(Enum):
    """How a seismic basic case acts (10-12 作用方向)."""

    DOWNWARD = "downward"  # ↓: the vertical forces
    EARTHQUAKE = "earthquake"  # the direction of the earthquake: the horizontal forces are magnitudes toward it


class FrameDirection(Enum):
    LONGITUDINAL = "longitudinal"  # 線路方向 (0711)
    TRANSVERSE = "transverse"  # 線路直角方向 (0721)


@dataclass(frozen=True)
class BearingRef:
    side: Side
    slot: int  # 1..10: the bearing slot of the side in the input (上部工反力の支承データ)


@dataclass(frozen=True)
class BearingAction:
    """The 支承作用 of a basic case on one bearing: forces in kN (vertical downward positive, the horizontal ones in
    +x of each frame: toward the end side along the track, toward W9 across it), heights in m above the bearing seat."""

    bearing: BearingRef
    vertical: Decimal = Decimal("0.00")
    longitudinal: Decimal = Decimal("0.00")
    longitudinal_height: Decimal = Decimal("0.000")
    transverse: Decimal = Decimal("0.00")
    transverse_height: Decimal = Decimal("0.000")


@dataclass(frozen=True)
class Seismic:
    increment: Increment
    direction: SeismicDirection


@dataclass(frozen=True)
class BasicCase:
    """A basic case of the load model; ``seismic`` is set for a case of the seismic analyses."""

    id: str
    name: str  # printed in the reports and written to FrameWeb and the NDU
    spring: SpringTerm
    actions: tuple[BearingAction, ...]
    seismic: Seismic | None = None


@dataclass(frozen=True)
class Candidate:
    case: str  # the id of a basic case of the load model or of the application
    sign: int = 1  # −1 reverses the whole case: only for a case without vertical forces (FrameWeb Define −n)


@dataclass(frozen=True)
class Term:
    """A factor on one basic case, or on whichever of the candidates governs (two or more: FrameWeb's Define)."""

    factor: Decimal
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True)
class Combination:
    """A combination of a frame (0610, 0620) and the extraction groups it is extracted for."""

    name: str
    terms: tuple[Term, ...]
    groups: frozenset[ExtractionGroup]


@dataclass(frozen=True)
class SeismicCombination:
    """A combination of a static nonlinear analysis: the basic cases it loads, each with the factor 1. The application
    analyses it for each 照査パターン (ρm, αf); ``reverse`` pushes the incremental cases away from the earthquake
    (逆向, decision 76), as for a load on the other side of the axis."""

    name: str
    cases: tuple[str, ...]
    reverse: bool = False


@dataclass(frozen=True)
class MaxResponse:
    """The 最大応答震度 of the seismic check in *direction*, which the application reads from Aggre-SE."""

    direction: FrameDirection


@dataclass(frozen=True)
class CantileverTerm:
    case: str
    factor: Decimal | MaxResponse


@dataclass(frozen=True)
class CantileverCombination:
    name: str
    terms: tuple[CantileverTerm, ...]
    rows: frozenset[CantileverRow]


@dataclass(frozen=True)
class Paragraph:
    text: str


@dataclass(frozen=True)
class Table:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Section:
    """A section about where the load model's values come from, which the application prints in its format."""

    title: str
    blocks: tuple[Paragraph | Table, ...]


# The stages whose reports print the load model's sections.
SECTION_STAGES = ("0610", "0620", "0710", "0720", "0900")


@dataclass(frozen=True)
class LoadModelResult:
    cases: tuple[BasicCase, ...]
    longitudinal: tuple[Combination, ...]  # 0610
    transverse: tuple[Combination, ...]  # 0620
    seismic_longitudinal: tuple[SeismicCombination, ...]  # 0710
    seismic_transverse: tuple[SeismicCombination, ...]  # 0720
    cantilever: tuple[CantileverCombination, ...]  # 0900
    pier_wind_pressures: tuple[Decimal, ...] = ()  # kN/m2: one wind case on the pier body each (0620)
    sections: Mapping[str, tuple[Section, ...]] = field(default_factory=dict)  # by stage, one of SECTION_STAGES
    provenance: Mapping[str, Any] = field(default_factory=dict)  # copied as it is into the provenance (JSON values)


@dataclass(frozen=True)
class BearingSlot:
    ref: BearingRef
    position: Decimal  # 支承位置 across the track, m (the input)


@dataclass(frozen=True)
class Context:
    input_path: Path  # the input.json being calculated; the load model's own input is its business
    bearings: tuple[BearingSlot, ...]  # the bearings of the input: the slots that are not empty


class LoadModel(Protocol):
    def calculate(self, context: Context) -> LoadModelResult: ...


class LoadModelInputError(InputError):
    """The load model's own input cannot be interpreted: *path* names the place in it."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message
