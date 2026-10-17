"""Editing helpers of the 鉄筋 section, independent of Tk.

Validation is not done here: the section is read by inputs/rebar.py (through the field table) and the column bars
are placed by calc/column_rebar.py, the same code the stages use. This module only builds JSON: blank rows, the
detail positions copied from the automatic layout with the basic input they came from (manual_basis), and the
position mode. Nothing is filled in: a new row has every value blank.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ..calc.column_rebar import Bar, ColumnLayout, section_layout
from ..core.errors import InputError
from ..core.printed import Printed
from ..core.reader import Reader
from ..inputs import choices
from ..inputs.fields import BASIS_VERSION, read
from ..inputs.rebar import parse_rebar
from .document import EditorError

MEMBERS = ("梁", "柱", "フーチング")
COLUMN = "柱"
W6 = ("下部構造", "寸法", "正面", "W6")
B6 = ("下部構造", "寸法", "側面", "B6")

_MAIN = ("diameter_mm", "material", "cover_mode", "center_mm", "clear_gap_mm")
ROW_KEYS: dict[tuple[str, str], tuple[str, ...]] = {
    ("柱", "main_rows"): (*_MAIN, "face_direction", "layer", "per_face_count", "endpoints"),
    ("梁", "main_rows"): (*_MAIN, "face", "bar_type", "layer", "count"),
    ("フーチング", "main_rows"): (*_MAIN, "direction", "face", "pitch_mm", "layers", "stack_order"),
    ("side", "side_rows"): ("diameter_mm", "material", "per_face_count", "columns", "column_pitch_mm", "start_mm",
                            "pitch_mm", "stirrup_position", "cover_mode", "center_mm"),
    ("band", "band_rows"): ("type", "direction", "diameter_mm", "material", "sets", "pitch_mm", "start_mm", "end_mm",
                            "legs_mode", "effective_legs"),
    ("hoop", "direction_rows"): ("direction", "diameter_mm", "material", "effective_legs", "pitch_mm", "start_mm",
                                 "end_mm"),
    ("bar", "manual_positions"): ("x_mm", "y_mm", "diameter_mm", "material"),
}
FOOTING_BAND_KEYS = ("distribution_mode", "width_pitch_mm", "density_per_m")


def blank_row(member: str, family: str) -> dict[str, Any]:
    """A new row of *family* with every value blank."""
    if family == "main_rows":
        row: dict[str, Any] = dict.fromkeys(ROW_KEYS[(member, family)])
        if member == COLUMN:
            row["distribution"] = {"mode": None, "edge_center_mm": None, "pitch_mm": None}
        return row
    kind = {"side_rows": "side", "band_rows": "band", "direction_rows": "hoop", "manual_positions": "bar"}[family]
    row = dict.fromkeys(ROW_KEYS[(kind, family)])
    if family == "band_rows" and member == "フーチング":
        row.update(dict.fromkeys(FOOTING_BAND_KEYS))
    return row


def rows_of(data: Any, member: str, family: str) -> list:
    member_data = data["鉄筋"][member]
    return member_data["column_hoops"]["direction_rows"] if family == "direction_rows" else member_data[family]


def add_row(data: Any, member: str, family: str) -> int:
    rows = rows_of(data, member, family)
    rows.append(blank_row(member, family))
    return len(rows) - 1


def delete_row(data: Any, member: str, family: str, index: int) -> bool:
    rows = rows_of(data, member, family)
    if not 0 <= index < len(rows):
        return False
    del rows[index]
    return True


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


def bar_json(bar: Bar) -> dict[str, Any]:
    return {"x_mm": bar.x.value, "y_mm": bar.y.value, "diameter_mm": int(bar.diameter.value), "material": bar.material}


def _basis(column: dict, layout: ColumnLayout) -> dict[str, Any]:
    return {"generator_version": BASIS_VERSION,
            "geometry": {"width_mm": layout.width.value, "height_mm": layout.height.value},
            "inputs": {"main_rows": deepcopy(column["main_rows"]), "materials": deepcopy(column["materials"]),
                       "pure_cover_mm": column["pure_cover_mm"], "column_hoops": deepcopy(column["column_hoops"])}}


@dataclass(frozen=True)
class Comparison:
    """The bars in use and the automatic layout that would replace them."""

    current: tuple[dict[str, Any], ...]
    candidate: tuple[dict[str, Any], ...]
    detailed: bool  # the bars in use are detail positions


def comparison(data: Any) -> Comparison:
    layout = column_preview(data)
    detailed = layout.manual is not None
    return Comparison(tuple(bar_json(bar) for bar in layout.bars), tuple(bar_json(bar) for bar in layout.automatic),
                      detailed)


def copy_automatic(data: Any, shown: Comparison | None = None) -> None:
    """Replace the detail positions with the automatic layout and its basis, and use them (position mode 指定).

    *shown* is the comparison the user confirmed; if the input has changed since, nothing is replaced.
    """
    if shown is not None and comparison(data) != shown:
        raise EditorError("入力が変更されています。比較し直してください")
    layout = column_preview(data)
    column = data["鉄筋"][COLUMN]
    column["manual_positions"] = [bar_json(bar) for bar in layout.automatic]
    column["manual_basis"] = _basis(column, layout)
    column["position_mode"] = choices.POSITION_MANUAL


def use_mode(data: Any, mode: str) -> None:
    """Switch between the automatic layout (基本) and the kept detail positions (指定); both stay saved."""
    column = data["鉄筋"][COLUMN]
    if mode == choices.POSITION_MANUAL and not column["manual_positions"]:
        raise EditorError("詳細位置がありません。先に自動配置をコピーしてください")
    column["position_mode"] = mode


def _detailed(data: Any) -> list:
    """The detail positions to edit; the first edit of an automatic layout copies it."""
    column = data["鉄筋"][COLUMN]
    if column["position_mode"] != choices.POSITION_MANUAL:
        copy_automatic(data)
    return column["manual_positions"]


def add_bar(data: Any, bar: dict[str, Any]) -> int:
    if any(bar.get(key) is None for key in ("x_mm", "y_mm", "diameter_mm")):
        raise EditorError("X・Y・径をすべて入力してください")
    before = deepcopy(data["鉄筋"][COLUMN])
    positions = _detailed(data)
    positions.append({key: bar.get(key) for key in ROW_KEYS[("bar", "manual_positions")]})
    try:
        column_preview(data)
    except EditorError:
        data["鉄筋"][COLUMN] = before
        raise
    return len(positions) - 1


def delete_bar(data: Any, index: int) -> bool:
    column = data["鉄筋"][COLUMN]
    detailed = column["position_mode"] == choices.POSITION_MANUAL
    count = len(column["manual_positions"]) if detailed else len(column_preview(data).automatic)
    if not 0 <= index < count:
        return False
    del _detailed(data)[index]
    return True
