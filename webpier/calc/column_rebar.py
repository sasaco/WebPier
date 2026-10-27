"""Column main bar layout: physical positions from the 鉄筋.柱 input (CONTEXT.md 柱の配筋, decision 68).

The section is W6 × B6 in mm, origin at the upper-left corner, X across the track and Y along it. The 線路 bars put
片面本数 bars on each of the two faces normal to Y at y = c and y = B6 − c, spaced along X; the 直角 bars the same on
the faces normal to X. c is 主鉄筋の芯かぶり: for layer 1 given (指定) or the 純かぶり + the enclosing hoop + half the
bar, for a layer inside it the centre of the layer outside + the bar + the clear gap (one size per direction).

Along a face layer 1 follows the distribution of its direction:

- 等分: from the edge centre e to span − e in equal steps, with or without bars at those ends;
- 中央ピッチ: n bars at the pitch p, centred on the face;
- 両端＋中央ピッチ: two edge bars at e and span − e, the other n − 2 at p centred between them.

A layer inside takes the middle n of layer 1's positions (when the rest is odd, the one left over is at the far end);
its spacing is layer 1's pitch when it takes them all, else the one gap of its positions, or none.

Positions are printed in mm to 0.1 (a person reads 108, 1533.3 in the table). A bar where a bar of the other
direction already is, with the same size, is one corner bar shared by both; anything else at one place is an input
error. The changes made in the 方向別の鉄筋配置表 then give the bars generated at a centre with a size another centre
or size; a change that no generated bar has is not applied but returned, for the editor to warn about (decision 68).
Bars outside the section or closer than their radii are an input error. Nothing missing is filled in (decision 5): a
blank the layout needs is an input error naming its path.

The 方向別の鉄筋配置表 groups the bars by their centre from the reference face (y for 線路, x for 直角), size and steel.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from decimal import Decimal

from ..core.errors import InputError
from ..core.printed import Precision, Printed
from ..inputs import PierInput
from ..inputs import choices
from ..inputs.rebar import LENGTH_MM, ColumnBars, ColumnMainBars
from ._exact import d, put

YIELD_STRENGTH = Precision(0, "N/mm2")
# JIS G 3112 公称断面積 (mm2) of the deformed bars, as written there.
_NOMINAL = {6: "31.67", 10: "71.33", 13: "126.7", 16: "198.6", 19: "286.5", 22: "387.1", 25: "506.7", 29: "642.4",
            32: "794.2", 35: "956.6", 38: "1140", 41: "1340", 51: "2027"}
_PATH = "鉄筋.柱"
LayerKey = tuple[str, int]  # (direction, layer)


@dataclass(frozen=True)
class FaceRow:
    """One layer with bars, placed: the same positions on both faces of its direction."""

    direction: str  # 線路 / 直角
    layer: int  # 1, then the layers inside it
    diameter: Printed
    material: str
    center: Printed  # 主鉄筋の芯かぶり from each of the two faces
    positions: tuple[Printed, ...]  # along the face
    pitch: Printed | None  # the spacing of the distribution: 等分 step, or the pitch; None for one or two edge bars

    @property
    def key(self) -> LayerKey:
        return self.direction, self.layer


@dataclass(frozen=True)
class Bar:
    x: Printed
    y: Printed
    diameter: Printed
    material: str
    rows: tuple[LayerKey, ...]  # the layers of the bar (two for a shared corner)
    origin: tuple[Printed, Printed, Printed]  # x, y and size as generated, before the changes of the tables


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
    rows: tuple[FaceRow, ...]  # the layers with bars: 線路 then 直角, outermost first
    generated: tuple[Bar, ...]  # from the main bars
    bars: tuple[Bar, ...]  # in use: the generated bars with the changes of the 方向別の鉄筋配置表
    unmatched: tuple[tuple[str, int], ...]  # (direction, index in table_overrides) of the changes no generated bar has


def yield_strength(grade: str) -> Printed:
    """fyk of a grade of choices.STEEL_GRADES: its number in N/mm2 (JIS G 3112)."""
    return YIELD_STRENGTH(int(grade[2:]))


def bar_area(diameter: Printed, path: str) -> Printed:
    """The nominal area of a deformed bar D*diameter* (JIS G 3112)."""
    text = _NOMINAL.get(int(diameter.value))  # a nominal size has no decimals (inputs.fields.DIAMETER)
    if text is None:
        sizes = "・".join(f"D{size}" for size in _NOMINAL)
        raise InputError(f"{path}: D{diameter.value:g} の公称断面積がありません（JIS G 3112 の {sizes}）")
    value = Decimal(text)
    return Printed(float(value), max(0, -value.as_tuple().exponent), "mm2")


def _need(value, path: str):
    if value is None:
        raise InputError(f"{path}: 値が必要です")
    return value


def _mm(length: Printed) -> Printed:
    return put(LENGTH_MM, d(length) * 1000)


def layer_name(key: LayerKey) -> str:
    return f"{key[0]}{key[1]}段目"


class _Placer:
    def __init__(self, column: ColumnBars, width: Printed, height: Printed) -> None:
        self.column, self.width, self.height = column, width, height

    def path(self, direction: str, key: str = "", inner: int | None = None) -> str:
        base = f"{_PATH}.main_bars.{direction}" + ("" if inner is None else f".inner_layers[{inner}]")
        return base + (f".{key}" if key else "")

    def first_center(self, direction: str, bars: ColumnMainBars, diameter: Printed) -> Printed:
        mode = _need(bars.cover_mode, self.path(direction, "cover_mode"))
        if mode == choices.COVER_SPECIFIED:
            return _need(bars.center, self.path(direction, "center_mm"))
        pure = _need(self.column.pure_cover, f"{_PATH}.pure_cover_mm")
        hoop = _need(self.column.hoops.enclosing_diameter, f"{_PATH}.column_hoops.enclosing_diameter_mm")
        return put(LENGTH_MM, d(pure) + d(hoop) + d(diameter) / 2)

    def edge(self, direction: str, bars: ColumnMainBars, span: Printed, radius: Decimal) -> Printed:
        path = self.path(direction, "distribution.edge_center_mm")
        edge = _need(bars.distribution.edge_center, path)
        if 2 * d(edge) >= d(span):
            raise InputError(f"{path}: 両端の芯位置が面内寸法の半分以上です")
        if d(edge) < radius:
            raise InputError(f"{path}: 鉄筋の半径より小さく、鉄筋が断面の外に出ます")
        return edge

    def positions(self, direction: str, bars: ColumnMainBars, count: int, span: Printed, radius: Decimal
                  ) -> tuple[list[Printed], Printed | None]:
        mode = _need(bars.distribution.mode, self.path(direction, "distribution.mode"))
        if count == 1:
            return [put(LENGTH_MM, d(span) / 2)], None
        if mode == choices.EQUAL:
            edge = self.edge(direction, bars, span, radius)
            endpoints = _need(bars.endpoints, self.path(direction, "endpoints"))
            steps, offset = (count - 1, 0) if endpoints == choices.ENDPOINTS_INCLUDED else (count + 1, 1)
            step = (d(span) - 2 * d(edge)) / steps
            return [put(LENGTH_MM, d(edge) + (i + offset) * step) for i in range(count)], put(LENGTH_MM, step)
        if mode == choices.CENTRE_PITCH:
            pitch = _need(bars.distribution.pitch, self.path(direction, "distribution.pitch_mm"))
            start = (d(span) - (count - 1) * d(pitch)) / 2
            if start < radius:
                raise InputError(f"{self.path(direction, 'distribution.pitch_mm')}: "
                                 "中央ピッチの配置幅（(本数−1)×ピッチ）が面内寸法に収まりません")
            return [put(LENGTH_MM, start + i * d(pitch)) for i in range(count)], pitch
        edge = self.edge(direction, bars, span, radius)  # 両端＋中央ピッチ
        far = put(LENGTH_MM, d(span) - d(edge))
        if count == 2:
            return [edge, far], None
        pitch = _need(bars.distribution.pitch, self.path(direction, "distribution.pitch_mm"))
        start = (d(span) - (count - 3) * d(pitch)) / 2
        if start < d(edge):
            raise InputError(f"{self.path(direction, 'distribution.pitch_mm')}: 内部の鉄筋が両端の鉄筋の間に収まりません")
        return [edge, *(put(LENGTH_MM, start + i * d(pitch)) for i in range(count - 2)), far], pitch

    def checked(self, row: FaceRow, depth: Printed) -> FaceRow:
        here = self.path(row.direction, inner=None if row.layer == 1 else row.layer - 2)
        if 2 * d(row.center) >= d(depth):
            raise InputError(f"{here}: 芯かぶり {row.center.value:g} mm が断面の半分以上です")
        if d(row.center) < d(row.diameter) / 2:
            raise InputError(f"{here}: 芯かぶり {row.center.value:g} mm が鉄筋の半径より小さく、鉄筋が断面の外に出ます")
        return row

    def layers(self, direction: str) -> list[FaceRow]:
        bars = self.column.main_bars[direction]
        count = _need(bars.per_face_count, self.path(direction, "per_face_count"))
        if count == 0:
            if bars.inner_layers:
                raise InputError(f"{self.path(direction, 'inner_layers')}: 1段目に鉄筋がありません")
            return []
        diameter = _need(bars.diameter, self.path(direction, "diameter_mm"))
        material = _need(self.column.materials.main, f"{_PATH}.materials.main")
        depth, span = (self.height, self.width) if direction == "線路" else (self.width, self.height)
        center = self.first_center(direction, bars, diameter)
        positions, pitch = self.positions(direction, bars, count, span, d(diameter) / 2)
        first = self.checked(FaceRow(direction, 1, diameter, material, center, tuple(positions), pitch), depth)
        rows = [first]
        for index, inner in enumerate(bars.inner_layers):
            count = _need(inner.per_face_count, self.path(direction, "per_face_count", index))
            gap = _need(inner.clear_gap, self.path(direction, "clear_gap_mm", index))
            if count > len(first.positions):
                raise InputError(f"{self.path(direction, 'per_face_count', index)}: "
                                 f"1段目の{len(first.positions)}本より多くできません")
            start = (len(first.positions) - count) // 2
            taken = first.positions[start:start + count]
            center = put(LENGTH_MM, d(rows[-1].center) + d(diameter) + d(gap))
            rows.append(self.checked(FaceRow(direction, index + 2, diameter, material, center, taken,
                                             _spacing(first, taken)), depth))
        return rows

    def bars(self, rows: Iterable[FaceRow]) -> list[Bar]:
        """The bars of the rows; a bar where one of the other direction is, of the same size, is one shared corner bar.
        The bars of one direction never meet: their positions along a face differ, and every layer's centre is less
        than half the section from its faces (checked)."""
        found: dict[tuple[float, float], Bar] = {}
        for row in rows:
            rail = row.direction == "線路"
            depth = self.height if rail else self.width
            for fixed in (row.center, put(LENGTH_MM, d(depth) - d(row.center))):
                for along in row.positions:
                    x, y = (along, fixed) if rail else (fixed, along)
                    key = (x.value, y.value)
                    bar = found.get(key)
                    if bar is None:
                        found[key] = Bar(x, y, row.diameter, row.material, (row.key,), (x, y, row.diameter))
                    elif bar.diameter != row.diameter:
                        raise InputError(f"{_PATH}.main_bars.{row.direction}: {layer_name(row.key)}の鉄筋と同じ位置に"
                                         f"{layer_name(bar.rows[0])}の径の異なる鉄筋があります")
                    else:
                        found[key] = replace(bar, rows=(*bar.rows, row.key))
        return _sorted(found.values())


def _sorted(bars: Iterable[Bar]) -> list[Bar]:
    return sorted(bars, key=lambda bar: (bar.y.value, bar.x.value))


def _spacing(first: FaceRow, taken: tuple[Printed, ...]) -> Printed | None:
    """The spacing of a layer inside: layer 1's when it takes all its positions, else its one gap (none for one bar)."""
    if taken == first.positions:
        return first.pitch
    gaps = {d(b) - d(a) for a, b in zip(taken, taken[1:])}
    return put(LENGTH_MM, gaps.pop()) if len(gaps) == 1 else None


def _changed(column: ColumnBars, generated: list[Bar], width: Printed, height: Printed
             ) -> tuple[list[Bar], list[tuple[str, int]]]:
    """The generated bars with the changes of the two 方向別の鉄筋配置表, each matched on the generated centre from the
    reference face and size; the changes no generated bar has are returned, not applied."""
    bars, unmatched = list(generated), []
    for direction in choices.REBAR_DIRECTIONS:
        axis = "y" if direction == "線路" else "x"
        for index, change in enumerate(column.overrides[direction]):
            source = (change.source_center.value, change.source_diameter.value)
            hits = [i for i, bar in enumerate(generated) if (getattr(bar, axis).value, bar.diameter.value) == source]
            if not hits:
                unmatched.append((direction, index))
            for i in hits:
                if change.center is not None:
                    bars[i] = replace(bars[i], **{axis: change.center})
                if change.diameter is not None:
                    bars[i] = replace(bars[i], diameter=change.diameter)
    seen: set[tuple[float, float]] = set()
    for bar in bars:
        where = f"{_PATH}.table_overrides: X {bar.x.value:g}・Y {bar.y.value:g} の鉄筋"
        if (bar.x.value, bar.y.value) in seen:
            raise InputError(f"{where}が配置表の変更でほかの鉄筋と同じ位置になります")
        seen.add((bar.x.value, bar.y.value))
        if min(d(bar.x), d(bar.y), d(width) - d(bar.x), d(height) - d(bar.y)) < d(bar.diameter) / 2:
            raise InputError(f"{where}が断面の外に出ます")
    return bars, unmatched


def _overlap(bars: list[Bar]) -> None:
    """Bars may touch but not overlap; checked exactly on the printed positions."""
    ordered = sorted(bars, key=lambda bar: bar.x.value)
    largest = max((d(bar.diameter) for bar in ordered), default=Decimal(0))
    for i, bar in enumerate(ordered):
        for other in ordered[i + 1:]:
            if d(other.x) - d(bar.x) >= largest:
                break
            reach = (d(bar.diameter) + d(other.diameter)) / 2
            if (d(other.x) - d(bar.x)) ** 2 + (d(other.y) - d(bar.y)) ** 2 < reach ** 2:
                labels = "・".join(layer_name(key) for key in sorted({*bar.rows, *other.rows}))
                raise InputError(f"{_PATH}.main_bars: {labels}の鉄筋が重なっています（X {other.x.value:g}・Y {other.y.value:g}）")


def column_layout(pier: PierInput) -> ColumnLayout:
    return section_layout(pier.rebar.column, pier.substructure.w[6], pier.substructure.b[6])


def section_layout(column: ColumnBars, w6: Printed, b6: Printed) -> ColumnLayout:
    """The layout of *column* in a W6 × B6 section (m); the editor previews it before the rest of the input is
    complete."""
    width, height = _mm(w6), _mm(b6)
    placer = _Placer(column, width, height)
    rows = [row for direction in choices.REBAR_DIRECTIONS for row in placer.layers(direction)]
    generated = placer.bars(rows)
    bars, unmatched = _changed(column, generated, width, height)
    _overlap(bars)
    return ColumnLayout(width=width, height=height, rows=tuple(rows), generated=tuple(generated),
                        bars=tuple(_sorted(bars)), unmatched=tuple(unmatched))


def table(bars: Iterable[Bar], direction: str) -> tuple[TableRow, ...]:
    """方向別の鉄筋配置表: bars by centre from the reference face (y for 線路, x for 直角), size and steel."""
    counts: dict[tuple[Printed, Printed, str], int] = {}
    for bar in bars:
        key = (bar.y if direction == "線路" else bar.x, bar.diameter, bar.material)
        counts[key] = counts.get(key, 0) + 1
    return tuple(TableRow(center, diameter, count, material) for (center, diameter, material), count in
                 sorted(counts.items(), key=lambda item: (item[0][0].value, item[0][1].value, item[0][2])))
