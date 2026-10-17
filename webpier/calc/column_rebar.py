"""Column main bar layout: physical positions from the basic input and the direction tables (CONTEXT.md 柱の配筋).

The section is W6 × B6 in mm, origin at the upper-left corner, X across the track and Y along it. A 線路 row
puts 片面本数 bars on each of the two faces normal to Y at y = c and y = B6 − c, spaced along X; a 直角 row
the same on the faces normal to X. c is 主鉄筋の芯かぶり: given (指定), or for layer 1 the 純かぶり + the
enclosing hoop + half the bar, and for layer n the layer n − 1 centre + both half bars + the clear gap.

Along a face the bars follow the distribution of the row:

- 等分: from the edge centre e to span − e in equal steps, with or without bars at those ends;
- 中央ピッチ: n bars at the pitch p, centred on the face;
- 両端＋中央ピッチ: two edge bars at e and span − e, the other n − 2 at p centred between them.

Positions are printed in mm to 0.1 (a person reads 108, 1533.3 in the table). A bar where a bar of the other
direction already is, with the same size and steel, is one corner bar shared by both rows; anything else at one
place, or bars closer than their radii, is an input error. Nothing missing is filled in (decision 5): a blank the
layout needs is an input error naming its path.

The 方向別の鉄筋配置表 groups the bars by their centre from the reference face (y for 線路, x for 直角), size
and steel. Detail positions (position mode 指定) replace the generated bars as entered; whether they still match
the basic input they were generated from is reported, not repaired.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput
from ..inputs import choices
from ..inputs.rebar import LENGTH_MM, ColumnBars, ColumnMainRow, ManualBasis
from ._exact import d, put

YIELD_STRENGTH = Precision(0, "N/mm2")
_PATH = "鉄筋.柱"


@dataclass(frozen=True)
class FaceRow:
    """One active basic-input row, placed: the same positions on both faces."""

    index: int  # in 鉄筋.柱.main_rows
    direction: str  # 線路 / 直角
    diameter: Printed
    material: str
    center: Printed  # 主鉄筋の芯かぶり from each of the two faces
    positions: tuple[Printed, ...]  # along the face
    pitch: Printed | None  # the spacing of the distribution: 等分 step, or the pitch; None for one or two edge bars


@dataclass(frozen=True)
class Bar:
    x: Printed
    y: Printed
    diameter: Printed
    material: str
    rows: tuple[int, ...]  # basic-input rows of the bar (two for a shared corner); () for a detail position


@dataclass(frozen=True)
class TableRow:
    center: Printed  # from the reference face of the direction
    diameter: Printed
    count: int
    material: str


@dataclass(frozen=True)
class ColumnLayout:
    width: Printed  # X = W6, mm
    height: Printed  # Y = B6, mm
    rows: tuple[FaceRow, ...]  # the rows with bars, in input order
    automatic: tuple[Bar, ...]  # generated from the basic input
    manual: tuple[Bar, ...] | None  # the detail positions, when position mode is 指定
    manual_basis_current: bool  # the detail positions were generated from the current basic input

    @property
    def bars(self) -> tuple[Bar, ...]:
        """The bars in use."""
        return self.automatic if self.manual is None else self.manual


def yield_strength(grade: str) -> Printed:
    """fyk of a grade of choices.STEEL_GRADES: its number in N/mm2 (JIS G 3112)."""
    return YIELD_STRENGTH(int(grade[2:]))


def _need(value, path: str):
    if value is None:
        raise InputError(f"{path}: 値が必要です")
    return value


def _mm(length: Printed) -> Printed:
    return put(LENGTH_MM, d(length) * 1000)


class _Placer:
    def __init__(self, column: ColumnBars, width: Printed, height: Printed) -> None:
        self.column, self.width, self.height = column, width, height

    def path(self, index: int, key: str = "") -> str:
        return f"{_PATH}.main_rows[{index}]" + (f".{key}" if key else "")

    def center(self, index: int) -> Printed:
        row = self.column.main_rows[index]
        mode = _need(row.cover_mode, self.path(index, "cover_mode"))
        if mode == choices.COVER_SPECIFIED:
            return _need(row.center, self.path(index, "center_mm"))
        diameter = _need(row.diameter, self.path(index, "diameter_mm"))
        layer = _need(row.layer, self.path(index, "layer"))
        if layer == 1:
            pure = _need(self.column.pure_cover, f"{_PATH}.pure_cover_mm")
            hoop = _need(self.column.hoops.enclosing_diameter, f"{_PATH}.column_hoops.enclosing_diameter_mm")
            return put(LENGTH_MM, d(pure) + d(hoop) + d(diameter) / 2)
        outside = [i for i, other in enumerate(self.column.main_rows)
                   if other.face_direction == row.face_direction and other.layer == layer - 1]
        if len(outside) != 1:
            raise InputError(f"{self.path(index, 'layer')}: 同じ面の{layer - 1}段目の行がちょうど1行必要です")
        gap = _need(row.clear_gap, self.path(index, "clear_gap_mm"))
        (previous,) = outside
        previous_diameter = _need(self.column.main_rows[previous].diameter, self.path(previous, "diameter_mm"))
        return put(LENGTH_MM, d(self.center(previous)) + d(previous_diameter) / 2 + d(gap) + d(diameter) / 2)

    def edge(self, index: int, row: ColumnMainRow, span: Printed, radius: Decimal) -> Printed:
        path = self.path(index, "distribution.edge_center_mm")
        edge = _need(row.distribution.edge_center, path)
        if 2 * d(edge) >= d(span):
            raise InputError(f"{path}: 両端の芯位置が面内寸法の半分以上です")
        if d(edge) < radius:
            raise InputError(f"{path}: 鉄筋の半径より小さく、鉄筋が断面の外に出ます")
        return edge

    def positions(self, index: int, row: ColumnMainRow, count: int, span: Printed, radius: Decimal
                  ) -> tuple[list[Printed], Printed | None]:
        mode = _need(row.distribution.mode, self.path(index, "distribution.mode"))
        if count == 1:
            return [put(LENGTH_MM, d(span) / 2)], None
        if mode == choices.EQUAL:
            edge = self.edge(index, row, span, radius)
            endpoints = _need(row.endpoints, self.path(index, "endpoints"))
            steps, offset = (count - 1, 0) if endpoints == choices.ENDPOINTS_INCLUDED else (count + 1, 1)
            step = (d(span) - 2 * d(edge)) / steps
            return [put(LENGTH_MM, d(edge) + (i + offset) * step) for i in range(count)], put(LENGTH_MM, step)
        if mode == choices.CENTRE_PITCH:
            pitch = _need(row.distribution.pitch, self.path(index, "distribution.pitch_mm"))
            start = (d(span) - (count - 1) * d(pitch)) / 2
            if start < radius:
                raise InputError(f"{self.path(index, 'distribution.pitch_mm')}: "
                                 "中央ピッチの配置幅（(本数−1)×ピッチ）が面内寸法に収まりません")
            return [put(LENGTH_MM, start + i * d(pitch)) for i in range(count)], pitch
        edge = self.edge(index, row, span, radius)  # 両端＋中央ピッチ
        far = put(LENGTH_MM, d(span) - d(edge))
        if count == 2:
            return [edge, far], None
        pitch = _need(row.distribution.pitch, self.path(index, "distribution.pitch_mm"))
        start = (d(span) - (count - 3) * d(pitch)) / 2
        if start < d(edge):
            raise InputError(f"{self.path(index, 'distribution.pitch_mm')}: 内部の鉄筋が両端の鉄筋の間に収まりません")
        return [edge, *(put(LENGTH_MM, start + i * d(pitch)) for i in range(count - 2)), far], pitch

    def row(self, index: int) -> FaceRow | None:
        row = self.column.main_rows[index]
        count = _need(row.per_face_count, self.path(index, "per_face_count"))
        if count == 0:
            return None
        direction = _need(row.face_direction, self.path(index, "face_direction"))
        diameter = _need(row.diameter, self.path(index, "diameter_mm"))
        material = row.material or self.column.materials.main
        if material is None:
            raise InputError(f"{self.path(index, 'material')}: 値が必要です（行と{_PATH}.materials.main が空欄）")
        center = self.center(index)
        rail = direction == "線路"
        depth, span = (self.height, self.width) if rail else (self.width, self.height)
        radius = d(diameter) / 2
        if 2 * d(center) >= d(depth):
            raise InputError(f"{self.path(index)}: 芯かぶり {center.value:g} mm が断面の半分以上です")
        if d(center) < radius:
            raise InputError(f"{self.path(index)}: 芯かぶり {center.value:g} mm が鉄筋の半径より小さく、"
                             "鉄筋が断面の外に出ます")
        positions, pitch = self.positions(index, row, count, span, radius)
        return FaceRow(index=index, direction=direction, diameter=diameter, material=material, center=center,
                       positions=tuple(positions), pitch=pitch)

    def bars(self, rows: Iterable[FaceRow]) -> list[Bar]:
        found: dict[tuple[float, float], tuple[Bar, set[str]]] = {}
        for row in rows:
            rail = row.direction == "線路"
            depth = self.height if rail else self.width
            for fixed in (row.center, put(LENGTH_MM, d(depth) - d(row.center))):
                for along in row.positions:
                    x, y = (along, fixed) if rail else (fixed, along)
                    key = (x.value, y.value)
                    if key not in found:
                        found[key] = (Bar(x, y, row.diameter, row.material, (row.index,)), {row.direction})
                        continue
                    bar, directions = found[key]
                    if (bar.diameter, bar.material) != (row.diameter, row.material):
                        raise InputError(f"{self.path(row.index)}: 同じ位置に径または材質の異なる鉄筋があります")
                    if row.direction in directions:
                        raise InputError(f"{self.path(row.index)}: 同じ方向の鉄筋が同じ位置に重複しています")
                    directions.add(row.direction)
                    found[key] = (Bar(x, y, bar.diameter, bar.material, (*bar.rows, row.index)), directions)
        return _sorted(bar for bar, _ in found.values())


def _sorted(bars: Iterable[Bar]) -> list[Bar]:
    return sorted(bars, key=lambda bar: (bar.y.value, bar.x.value))


def _overlap(bars: list[tuple[Bar, tuple[int, ...]]], family: str) -> None:
    """Bars may touch but not overlap; checked exactly on the printed positions. *family* names the rows."""
    ordered = sorted(bars, key=lambda item: item[0].x.value)
    largest = max((d(bar.diameter) for bar, _ in ordered), default=Decimal(0))
    for i, (bar, rows) in enumerate(ordered):
        for other, other_rows in ordered[i + 1:]:
            if d(other.x) - d(bar.x) >= largest:
                break
            reach = (d(bar.diameter) + d(other.diameter)) / 2
            if (d(other.x) - d(bar.x)) ** 2 + (d(other.y) - d(bar.y)) ** 2 < reach ** 2:
                labels = "・".join(f"[{row}]" for row in sorted({*rows, *other_rows}))
                raise InputError(f"{_PATH}.{family}{labels}: 鉄筋が重なっています")


def _manual(column: ColumnBars, width: Printed, height: Printed) -> list[Bar]:
    bars, seen = [], set()
    for index, row in enumerate(column.manual_positions):
        path = f"{_PATH}.manual_positions[{index}]"
        x, y = _need(row.x, f"{path}.x_mm"), _need(row.y, f"{path}.y_mm")
        diameter = _need(row.diameter, f"{path}.diameter_mm")
        material = _need(row.material, f"{path}.material")
        radius = d(diameter) / 2
        if min(d(x), d(y), d(width) - d(x), d(height) - d(y)) < radius:
            raise InputError(f"{path}: 鉄筋が断面の外に配置されます")
        if (x.value, y.value) in seen:
            raise InputError(f"{path}: 同じ位置の鉄筋が重複しています")
        seen.add((x.value, y.value))
        bars.append(Bar(x, y, diameter, material, ()))
    return bars


def column_layout(pier: PierInput) -> ColumnLayout:
    return section_layout(pier.rebar.column, pier.substructure.w[6], pier.substructure.b[6])


def section_layout(column: ColumnBars, w6: Printed, b6: Printed) -> ColumnLayout:
    """The layout of *column* in a W6 × B6 section (m); the editor previews it before the rest of the input is
    complete."""
    width, height = _mm(w6), _mm(b6)
    placer = _Placer(column, width, height)
    rows = [row for row in (placer.row(index) for index in range(len(column.main_rows))) if row is not None]
    automatic = placer.bars(rows)
    _overlap([(bar, bar.rows) for bar in automatic], "main_rows")
    manual = None
    if column.position_mode == choices.POSITION_MANUAL:
        manual = _manual(column, width, height)
        _overlap([(bar, (index,)) for index, bar in enumerate(manual)], "manual_positions")
        manual = _sorted(manual)
    basis = ManualBasis(width=width, height=height, materials=column.materials, pure_cover=column.pure_cover,
                        main_rows=column.main_rows, hoops=column.hoops)
    return ColumnLayout(width=width, height=height, rows=tuple(rows), automatic=tuple(automatic),
                        manual=None if manual is None else tuple(manual),
                        manual_basis_current=column.manual_basis == basis)


def table(bars: Iterable[Bar], direction: str) -> tuple[TableRow, ...]:
    """方向別の鉄筋配置表: bars by centre from the reference face (y for 線路, x for 直角), size and steel."""
    counts: dict[tuple[Printed, Printed, str], int] = {}
    for bar in bars:
        key = (bar.y if direction == "線路" else bar.x, bar.diameter, bar.material)
        counts[key] = counts.get(key, 0) + 1
    return tuple(TableRow(center, diameter, count, material) for (center, diameter, material), count in
                 sorted(counts.items(), key=lambda item: (item[0][0].value, item[0][1].value, item[0][2])))
