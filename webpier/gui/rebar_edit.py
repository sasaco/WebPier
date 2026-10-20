"""Editing helpers of the 鉄筋 section, independent of Tk.

Validation is not done here: the section is read by inputs/rebar.py (through the field table) and the column bars
are placed by calc/column_rebar.py, the same code the stages use. This module only builds JSON: a new list item or
object has every field of the field table under it blank (null), and its lists empty; nothing is filled in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..calc.beam_rebar import BeamLayout, beam_layout, beam_section
from ..calc.column_rebar import ColumnLayout, LayerKey, section_layout
from ..calc.footing_rebar import FaceLayout, face_layout, stirrup_width
from ..core.errors import InputError
from ..core.printed import Printed
from ..core.reader import Reader
from ..inputs import choices
from ..inputs.fields import FIELDS, path_text, pattern, read
from ..inputs.rebar import parse_rebar
from .document import EditorError

MEMBERS = ("梁", "柱", "フーチング")
COLUMN = "柱"
W6 = ("下部構造", "寸法", "正面", "W6")
B6 = ("下部構造", "寸法", "側面", "B6")
BEAM_SECTION = (("下部構造", "寸法", "側面", "B1"), ("下部構造", "寸法", "高さ", "H2"), ("下部構造", "寸法", "高さ", "H3"))
SIDE_BARS = ("鉄筋", "梁", "side_bars")
OVERRIDES = ("鉄筋", "柱", "table_overrides")
JsonPath = tuple[str | int, ...]


def blank(path: JsonPath) -> dict[str, Any]:
    """A new object at *path* (a list item by any index): every field of the field table under it blank."""
    prefix = pattern(path_text(path)) + "."
    item: dict[str, Any] = {}
    for key in FIELDS:
        if not key.startswith(prefix):
            continue
        node = item
        *parents, leaf = key[len(prefix):].split(".")
        for part in parents:
            if part.endswith("[*]"):
                node.setdefault(part[:-3], [])
                break
            node = node.setdefault(part, {})
        else:
            node[leaf] = None
    return item


def items(data: Any, path: JsonPath) -> Any:
    """The JSON value at *path*."""
    node = data
    for key in path:
        node = node[key]
    return node


def add_row(data: Any, path: JsonPath) -> int:
    """Append a blank item to the list at *path*; its index."""
    rows = items(data, path)
    rows.append(blank((*path, len(rows))))
    return len(rows) - 1


def delete_row(data: Any, path: JsonPath, index: int) -> bool:
    rows = items(data, path)
    if not 0 <= index < len(rows):
        return False
    del rows[index]
    return True


def set_side_bars(data: Any, present: bool) -> None:
    """The beam's side bars: a blank set, or none (null)."""
    items(data, SIDE_BARS[:-1])[SIDE_BARS[-1]] = blank(SIDE_BARS) if present else None


@dataclass(frozen=True)
class TableLine:
    """A row of the 方向別の鉄筋配置表 as the editor shows it: the bars generated at one centre with one size."""

    source: tuple[float, float]  # the generated centre from the reference face and size, mm: the key of a change
    center: float  # in use
    diameter: float  # in use
    count: int
    layers: tuple[LayerKey, ...]
    changed: bool


def table_lines(layout: ColumnLayout, direction: str) -> list[TableLine]:
    """The rows of the 方向別の鉄筋配置表 of *direction* (centres from the upper face for 線路, the left face for 直角),
    by the generated centre and size; a changed row shows the values in use."""
    axis = 1 if direction == "線路" else 0  # the coordinate of the bar's origin and of the bar
    groups: dict[tuple[float, float], list] = {}
    for generated, bar in zip(layout.generated, _in_generated_order(layout)):
        key = (generated.origin[axis].value, generated.diameter.value)
        groups.setdefault(key, []).append(bar)
    lines = []
    for source, bars in groups.items():
        center = (bars[0].y if axis else bars[0].x).value
        diameter = bars[0].diameter.value
        layers = tuple(sorted({key for bar in bars for key in bar.rows}))
        lines.append(TableLine(source, center, diameter, len(bars), layers, (center, diameter) != source))
    return sorted(lines, key=lambda line: (line.center, line.diameter))


def _in_generated_order(layout: ColumnLayout) -> list:
    """The bars in use, in the order of the generated bars they come from (by origin)."""
    by_origin = {bar.origin: bar for bar in layout.bars}
    return [by_origin[bar.origin] for bar in layout.generated]


def change_table(data: Any, direction: str, source: tuple[float, float], key: str, value: float | None) -> None:
    """Change the row of the 方向別の鉄筋配置表 generated at *source* (centre, size): its *key* (center_mm or
    diameter_mm) becomes *value*. The generated value or a blank undoes that part; a change of nothing is removed."""
    rows = items(data, (*OVERRIDES, direction))
    row = next((row for row in rows if (row["source_center_mm"], row["source_diameter_mm"]) == source), None)
    if row is None:
        row = blank((*OVERRIDES, direction, len(rows))) | {"source_center_mm": source[0],
                                                           "source_diameter_mm": source[1]}
        rows.append(row)
    row[key] = None if value == (source[0] if key == "center_mm" else source[1]) else value
    if row["center_mm"] is None and row["diameter_mm"] is None:
        rows.remove(row)


def undo_change(data: Any, direction: str, source: tuple[float, float]) -> bool:
    """戻す: remove the change of the row generated at *source*."""
    rows = items(data, (*OVERRIDES, direction))
    for row in rows:
        if (row["source_center_mm"], row["source_diameter_mm"]) == source:
            rows.remove(row)
            return True
    return False


def remove_unmatched(data: Any, layout: ColumnLayout) -> int:
    """Remove the changes whose generated bars are gone (ColumnLayout.unmatched); their number."""
    for direction, index in sorted(layout.unmatched, reverse=True):
        del items(data, (*OVERRIDES, direction))[index]
    return len(layout.unmatched)


def _editor_error(exc: InputError) -> EditorError:
    return EditorError(str(exc))


def section(data: Any) -> tuple[Printed, Printed]:
    """W6 × B6 of the column (m), read through the field table."""
    root = Reader(data)
    try:
        width, height = read(root.at(*W6)), read(root.at(*B6))
    except InputError as exc:
        raise _editor_error(exc) from None
    return width, height


def column_preview(data: Any) -> ColumnLayout:
    """The column layout of the current input, from the same reader and calculation as the stages."""
    width, height = section(data)
    try:
        return section_layout(parse_rebar(Reader(data)).column, width, height)
    except InputError as exc:
        raise _editor_error(exc) from None


def beam_preview(data: Any) -> BeamLayout:
    """The beam layout of the current input (B1 × (H2 + H3) at the column face), from the same reader and calculation
    as 0910."""
    root = Reader(data)
    try:
        width, depth = beam_section(*(read(root.at(*path)) for path in BEAM_SECTION))
        return beam_layout(parse_rebar(root).beam, width, depth)
    except InputError as exc:
        raise _editor_error(exc) from None


@dataclass(frozen=True)
class FootingPreview:
    faces: dict[str, FaceLayout | None]  # by face (choices.BEAM_FACES); None: the layers cannot be placed
    problems: dict[str, str]  # by face: the input error of a face whose layers cannot be placed
    stirrups: dict[str, tuple[Printed, Printed] | None]  # by direction: stirrup_width; None: it cannot be read


def footing_preview(data: Any) -> FootingPreview:
    """The footing's layers on each face and its stirrups across the width, from the same reader and calculation as
    0800 to 0820 (calc.footing_rebar). A face or a direction that cannot be read has its input error kept or None, so
    the others are still shown."""
    try:
        footing = parse_rebar(Reader(data)).footing
    except InputError as exc:
        raise _editor_error(exc) from None
    faces: dict[str, FaceLayout | None] = {}
    problems: dict[str, str] = {}
    for face in choices.BEAM_FACES:
        try:
            faces[face] = face_layout(footing, face)
        except InputError as exc:
            faces[face], problems[face] = None, str(exc)
    stirrups: dict[str, tuple[Printed, Printed] | None] = {}
    for direction in choices.REBAR_DIRECTIONS:
        try:
            stirrups[direction] = stirrup_width(footing, direction)
        except InputError:
            stirrups[direction] = None
    return FootingPreview(faces=faces, problems=problems, stirrups=stirrups)


def warnings(data: Any) -> list[str]:
    """What the input check names besides the input errors: the column's table changes whose generated bars are gone,
    the beam's overlapping bars and the footing's crossing layers on each face, in that order. None stops the
    calculation. A member whose layout cannot be made
    has no warning here: the calculation reports it as an input error and the 鉄筋 page shows it (the input check parses
    the form only)."""
    found = []
    try:
        unmatched = column_preview(data).unmatched
    except EditorError:
        unmatched = ()
    if unmatched:
        found.append(f"柱：配置表の変更のうち {len(unmatched)} 件は、元の芯位置・径の鉄筋がないため使われていません"
                     "（計算でも使いません）。")
    try:
        overlaps = beam_preview(data).overlaps
    except EditorError:
        overlaps = ()
    if overlaps:
        found.append(f"梁：鉄筋が {len(overlaps)} か所で重なっています。05 鉄筋の梁の配筋略図で赤い鉄筋を確かめてください"
                     "（計算は止めません）。")
    try:
        faces = footing_preview(data).faces
    except EditorError:
        faces = {}
    for face, layout in faces.items():
        if layout is not None and layout.crossings:
            found.append(f"フーチング：{face}面で段が {len(layout.crossings)} か所で交差しています。05 鉄筋のフーチングの"
                         "配筋略図で確かめてください（計算は止めません）。")
    return found
