"""Editing helpers of the 鉄筋 section, independent of Tk.

Validation is not done here: the section is read by inputs/rebar.py (through the field table) and the column bars
are placed by calc/column_rebar.py, the same code the stages use. This module only builds JSON: a new list item or
object has every field of the field table under it blank (null), and its lists empty; nothing is filled in.
"""

from __future__ import annotations

from typing import Any

from ..calc.column_rebar import ColumnLayout, section_layout
from ..core.errors import InputError
from ..core.printed import Printed
from ..core.reader import Reader
from ..inputs.fields import FIELDS, path_text, pattern, read
from ..inputs.rebar import parse_rebar
from .document import EditorError

MEMBERS = ("梁", "柱", "フーチング")
COLUMN = "柱"
W6 = ("下部構造", "寸法", "正面", "W6")
B6 = ("下部構造", "寸法", "側面", "B6")
SIDE_BARS = ("鉄筋", "梁", "side_bars")
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
