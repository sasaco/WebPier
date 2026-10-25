"""The ground springs SOIL-JR calculated for the frame of a pile foundation (decision 88, ADR-0013).

SOIL-JR returns them in its 解析連携データ (.sdc), by *column* of the pile rows (``export.soiljr.parse_sdc`` reads the file
into these values): the horizontal spring and the vertical shear spring of the pile surface of each layer along the pile,
and the springs at the pile tip. They are already bundled by the number of piles of the column in the depth. The frame of
0610 and 0620 takes them as they are (``calc.pile_frame``); WebPier does not calculate or correct them.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.errors import InputError

ODD, EVEN = "奇数列", "偶数列"
ALL = "全列"  # SOIL-JR prints one column when every row has the same springs


@dataclass(frozen=True)
class SpringLayer:
    """A layer along the pile, from the pile head down, with the springs of each column (per m² of the pile surface)."""

    number: int
    thickness: float  # m, the 層厚 of table b) (the whole layer)
    horizontal_long: tuple[float, ...]  # kN/m² per column: 長期
    horizontal_short: tuple[float, ...]  # 短期(線形)
    shear_thickness: float  # m, the 層厚 of the push side of table d): the part that has a shear spring
    shear_long: tuple[float, ...]  # kN/m² per column: 長期, the push side
    shear_short: tuple[float, ...]  # 短期(使用性・安全性), the push side
    pull_thickness: float  # m, the 層厚 of the pull side of table d)
    pull_long: tuple[float, ...]  # kN/m² per column: 長期, the pull side
    pull_short: tuple[float, ...]  # 短期(使用性・安全性), the pull side


@dataclass(frozen=True)
class ListedRow:
    """A pile row listed in a) (K_FLG = 1): its distance from the first row (m) and its piles in the depth."""

    number: int
    distance: float
    piles: int


@dataclass(frozen=True)
class DirectionSprings:
    name: str  # 橋軸方向, 直角方向
    rows: int  # 杭列数
    columns: tuple[str, ...]  # the names of the columns: ("1列目", "2列目", …), ("奇数列", "偶数列") or ("全列",)
    depth_piles: tuple[int, ...]  # 奥行き本数 of each column
    inverse_beta: float  # 1/β (m)
    listed_rows: tuple[ListedRow, ...]  # the rows of a) when the file lists them, else empty
    layers: tuple[SpringLayer, ...]
    tip_long: tuple[float, ...]  # kN/m of each column: the vertical spring at the pile tip, 長期
    tip_short: tuple[float, ...]  # 短期(第1勾配)
    tip_horizontal_long: tuple[float, ...]  # kN/m of each column: the horizontal spring at the pile tip (0 when SOIL-JR leaves it out)
    tip_horizontal_short: tuple[float, ...]
    tip_rotation_long: tuple[float, ...]  # the rotational spring at the pile tip
    tip_rotation_short: tuple[float, ...]

    def column(self, row: int) -> int:
        """The index of the column of the pile row *row* (1 at the first row)."""
        if not 1 <= row <= self.rows:
            raise InputError(f"{self.name}: 杭列 {row} がありません（杭列数 {self.rows}）")
        if self.columns[0] == ODD:
            return 0 if row % 2 == 1 else 1
        if self.columns[0] == ALL:
            return 0
        return row - 1


@dataclass(frozen=True)
class GroundSprings:
    version: str
    title: str
    pile: dict[str, float | str]  # the header of 【杭情報】 by name (杭種, 杭長, 突出長, 根入れ深さ, A, I, …)
    directions: tuple[DirectionSprings, ...]

    def direction(self, name: str) -> DirectionSprings:
        for item in self.directions:
            if item.name == name:
                return item
        raise InputError(f".sdc に {name} がありません")


@dataclass(frozen=True)
class SurfaceSide:
    """The vertical shear spring and the bearing capacity of the pile surface of a layer, on the push or the pull side
    (the L2 / 地震時 tables d) and e) of the .sdc; decision 93)."""

    length: float  # ⊿l (m): the part of the layer that has the spring
    first: tuple[float, ...]  # kN/m2 per column: the first slope
    second: tuple[float, ...]  # the second slope
    yield_load: tuple[float, ...]  # kN/m per column: 降伏点 of the surface bearing capacity
    ultimate: tuple[float, ...]  # 終局点


@dataclass(frozen=True)
class SeismicLayer:
    number: int
    thickness: float  # m
    horizontal: tuple[float, ...]  # kN/m2 per column: the 短期(非線形) horizontal spring
    pressure_upper: tuple[float, ...]  # kN/m per column: the effective resistance earth pressure at the top of the layer
    pressure_lower: tuple[float, ...]  # … at the bottom
    push: SurfaceSide
    pull: SurfaceSide


@dataclass(frozen=True)
class SeismicTip:
    """f) and g): the springs and the bearing capacity at the pile tip, per column."""

    first: tuple[float, ...]  # kN/m: vertical, 短期 first slope
    second: tuple[float, ...]  # vertical, 短期 second slope
    yield_load: tuple[float, ...]  # kN: the vertical bearing capacity, push side, 降伏点
    ultimate: tuple[float, ...]  # 終局点
    horizontal: tuple[float, ...]  # kN/m: the horizontal spring, 短期
    rotation: tuple[float, ...]  # the rotational spring, 短期


@dataclass(frozen=True)
class SeismicDirection:
    """What the JRSNAP model of a pile foundation takes of one direction of the .sdc (decision 93)."""

    name: str
    rows: int
    columns: tuple[str, ...]
    depth_piles: tuple[int, ...]
    inverse_beta: float
    layers: tuple[SeismicLayer, ...]
    tip: SeismicTip


@dataclass(frozen=True)
class SeismicSprings:
    version: str  # "Ver.5.2.3" or "Ver.5.3.1"
    title: str
    pile: dict[str, float | str]
    directions: tuple[SeismicDirection, ...]

    def direction(self, name: str) -> SeismicDirection:
        for item in self.directions:
            if item.name == name:
                return item
        raise InputError(f".sdc に {name} がありません")
