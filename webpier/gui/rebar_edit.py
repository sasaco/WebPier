"""Editing helpers of the 鉄筋 section, independent of Tk.

Validation is not done here: the section is read by inputs/rebar.py (through the field table) and the column bars
are placed by calc/column_rebar.py, the same code the stages use. This module only builds JSON: a new list item or
object has every field of the field table under it blank (null), and its lists empty; nothing is filled in. A
hand-made 方向別の鉄筋配置表 (配置表の手直し, decision 111) starts as a copy of the table in use, a new row as a copy of
the row above it, and editing a direction's main bars makes its table from them again (reset_changed).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from ..calc.beam_rebar import BeamLayout, beam_layout, beam_section
from ..calc.column_rebar import ColumnLayout, DirectionTable, count_mismatch, direction_table, section_layout
from ..calc.footing_rebar import FaceLayout, face_layout, stirrup_width
from ..core.errors import InputError
from ..core.printed import Printed
from ..core.reader import Reader
from ..inputs import choices
from ..inputs.fields import FIELDS, path_text, pattern, read
from ..inputs.rebar import parse_rebar
from .document import EditorError

MEMBERS = ("梁", "柱", "フーチング")
PILE = "杭"  # shown only for a cast-in-place pile foundation (decision 87)
COLUMN = "柱"
W6 = ("下部構造", "寸法", "正面", "W6")
B6 = ("下部構造", "寸法", "側面", "B6")
BEAM_SECTION = (("下部構造", "寸法", "側面", "B1"), ("下部構造", "寸法", "高さ", "H2"), ("下部構造", "寸法", "高さ", "H3"))
SIDE_BARS = ("鉄筋", "梁", "side_bars")
TABLES = ("鉄筋", "柱", "custom_tables")
MAIN_BARS = ("鉄筋", "柱", "main_bars")
JsonPath = tuple[str | int, ...]


def members(data: Any) -> tuple[str, ...]:
    """The members of the 鉄筋 page: the pile only when the 基礎形式 is a cast-in-place pile."""
    foundation = data.get("下部構造", {}).get("基礎形式") if isinstance(data, dict) else None
    return (*MEMBERS, PILE) if foundation == choices.CAST_IN_PLACE_PILE else MEMBERS


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


def _table_json(table: DirectionTable) -> dict[str, Any]:
    return {"tension_rows": table.tension,
            "rows": [{"center_mm": row.center.value, "diameter_mm": row.diameter.value, "count": row.count}
                     for row in table.rows]}


def direction_view(layout: ColumnLayout, direction: str) -> DirectionTable:
    """The 方向別の鉄筋配置表 of *direction* in use (calc.column_rebar.direction_table): the hand-made one, else the one
    the main bars make; an EditorError when it cannot be made."""
    try:
        return direction_table(layout, direction)
    except InputError as exc:
        raise _editor_error(exc) from None


def customize(data: Any, layout: ColumnLayout, direction: str) -> dict[str, Any]:
    """The hand-made table of *direction* (配置表の手直し, decision 111), started from the table in use when there is
    none: its JSON."""
    tables = items(data, TABLES)
    if tables[direction] is None:
        tables[direction] = _table_json(direction_view(layout, direction))
    return tables[direction]


def reset_table(data: Any, direction: str) -> bool:
    """入力から作り直す: the table of *direction* is the one the main bars make again; whether it was hand-made."""
    tables = items(data, TABLES)
    custom = tables[direction] is not None
    tables[direction] = None
    return custom


def set_cell(data: Any, layout: ColumnLayout, direction: str, index: int, key: str, value: Any) -> None:
    """The *key* (center_mm, diameter_mm or count) of the row *index* of the table of *direction* becomes *value*."""
    customize(data, layout, direction)["rows"][index][key] = value


def set_tension(data: Any, layout: ColumnLayout, direction: str, value: int | None) -> None:
    """引張鉄筋の段数 of the table of *direction*."""
    customize(data, layout, direction)["tension_rows"] = value


def insert_row(data: Any, layout: ColumnLayout, direction: str, index: int) -> int:
    """A copy of the row *index* below it (a row with every value, for the person to change); its index."""
    rows = customize(data, layout, direction)["rows"]
    rows.insert(index + 1, dict(rows[index]))
    return index + 1


def delete_table_row(data: Any, layout: ColumnLayout, direction: str, index: int) -> bool:
    rows = customize(data, layout, direction)["rows"]
    if not 0 <= index < len(rows) or len(rows) == 1:
        return False
    del rows[index]
    return True


def move_row(data: Any, layout: ColumnLayout, direction: str, index: int, step: int) -> int | None:
    """Move the row *index* up (−1) or down (+1): the order decides the 引張鉄筋. Its new index, or None at an end."""
    rows = customize(data, layout, direction)["rows"]
    target = index + step
    if not (0 <= index < len(rows) and 0 <= target < len(rows)):
        return None
    rows[index], rows[target] = rows[target], rows[index]
    return target


def main_bars(data: Any) -> dict[str, Any]:
    """The main bars of each direction as JSON (a copy): the input the tables are made from."""
    return copy.deepcopy(items(data, MAIN_BARS))


def reset_changed(data: Any, before: dict[str, Any]) -> list[str]:
    """After an edit: the hand-made tables of the directions whose main bars differ from *before* are made from the
    main bars again (decision 111); those directions."""
    now = items(data, MAIN_BARS)
    tables = items(data, TABLES)
    reset = [direction for direction in choices.REBAR_DIRECTIONS
             if now[direction] != before.get(direction) and tables[direction] is not None]
    for direction in reset:
        tables[direction] = None
    return reset


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
    """What the input check names besides the input errors: the column's two tables with other bars (decision 111), the
    beam's overlapping bars and the footing's crossing layers on each face, in that order. None stops the
    calculation. A member whose layout cannot be made
    has no warning here: the calculation reports it as an input error and the 鉄筋 page shows it (the input check parses
    the form only)."""
    found = []
    try:
        mismatch = count_mismatch(column_preview(data))
    except EditorError:
        mismatch = None
    if mismatch is not None:
        found.append(f"柱：線路方向と直角方向の配置表で鉄筋の本数が違います（{mismatch}）。05 鉄筋の柱の配置表を確かめて"
                     "ください（計算は止めません）。")
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
