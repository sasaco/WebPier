"""Small tksheet bindings; sheet data is the only editable cell state."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
import tkinter as tk

from tksheet import Sheet


def pending_edit(sheet: Sheet) -> tuple[int, int, str] | None:
    editor = sheet.MT.text_editor
    if editor.open:
        row, column = editor.coords
        return row, column, sheet.get_text_editor_value()
    return None


def pending_dirty(sheet: Sheet) -> bool:
    edit = pending_edit(sheet)
    if edit is None:
        return False
    row, column, value = edit
    return value != sheet.get_cell_data(row, column)


def commit_editor(sheet: Sheet) -> None:
    edit = pending_edit(sheet)
    sheet.close_text_editor(set_data=True)
    if edit is None or not sheet.MT.text_editor.open:
        return
    # tksheet 7.6 leaves the editor open when OS focus is absent. Its public
    # destroy_text_editor also passes an unsupported `reason` argument.
    # Keep this version-specific fallback here, preserving undo and events.
    row, column, value = edit
    if value != sheet.get_cell_data(row, column):
        sheet.set_data((row, column), data=value, undo=True, emit_event=True)
    sheet.MT.hide_text_editor_and_dropdown()


@dataclass
class SheetCell:
    sheet: Sheet
    row: int
    column: int
    changed: Callable

    def get(self) -> str:
        return str(self.sheet.get_cell_data(self.row, self.column))

    def set(self, value: str) -> None:
        self.sheet.set_cell_data(self.row, self.column, str(value))
        self.changed()

    def focus_set(self) -> None:
        self.sheet.select_cell(self.row, self.column)
        self.sheet.see(self.row, self.column)
        self.sheet.focus_set()

    def bounds(self) -> tuple[float, float, float, float]:
        """Return the actual visible cell rectangle in screen coordinates."""
        table = self.sheet.MT
        columns = self.sheet.get_column_widths(canvas_positions=True)
        rows = self.sheet.get_row_heights(canvas_positions=True)
        left = table.winfo_rootx() - table.canvasx(0)
        top = table.winfo_rooty() - table.canvasy(0)
        return (left + columns[self.column], top + rows[self.row],
                left + columns[self.column + 1], top + rows[self.row + 1])


def make_sheet(parent: tk.Misc, headers: list[str], data: list[list[str]],
               widths: list[int], *, max_height: int = 370,
               row_labels: list[str] | None = None, index_width: int = 42) -> Sheet:
    lines = max((header.count("\n") + 1 for header in headers), default=1)
    header_height = 32 if lines == 1 else 50 if lines == 2 else 66
    preferred_width = min(1000, sum(widths) + index_width + 20)
    sheet = Sheet(
        parent, headers=headers, data=data, total_columns=len(headers), row_index=row_labels,
        width=preferred_width, height=min(max_height, header_height + 30 * max(1, len(data)) + 24),
        default_row_height=30, default_header_height=header_height,
        default_row_index_width=index_width, font=("Yu Gothic UI", 10, "normal"),
        header_font=("Yu Gothic UI", 9, "bold"), index_font=("Yu Gothic UI", 9, "normal"),
        table_bg="#ffffff", table_fg="#23344a", table_grid_fg="#dbe3ed",
        header_bg="#eaf0f7", header_fg="#244969", index_bg="#f1f5f9",
        index_fg="#244969", top_left_bg="#eaf0f7",
        paste_can_expand_x=False, paste_can_expand_y=False,
        cell_auto_resize_enabled=False, auto_resize_row_index=False,
        edit_cell_tab="right", edit_cell_return="down",
        startup_focus=False, empty_vertical=0, empty_horizontal=0,
        row_index_align="w" if row_labels else "center",
    )
    sheet.input_preferred_width = preferred_width
    sheet.input_fixed_labels = row_labels is not None
    _enable_sheet_bindings(sheet)
    sheet.set_column_widths(widths)
    sheet.readonly_cells(cells=[(r, c) for r, row in enumerate(data) for c in range(len(row))])
    sheet.highlight_cells(row="all", column="all", bg="#f1f5f9")
    return sheet


def _enable_sheet_bindings(sheet: Sheet) -> None:
    sheet.set_options(redo_bindings=[*sheet.ops.redo_bindings, "<Control-y>", "<Control-Y>"],
                      redo_accelerator="Ctrl+Y")
    sheet.enable_bindings(
        "single_select", "drag_select", "row_select", "column_select", "select_all",
        "arrowkeys", "copy", "cut", "paste", "delete", "undo", "redo", "edit_cell",
        "right_click_popup_menu", "column_width_resize", "double_click_column_resize",
    )
