"""tksheet tables: one style, an open cell editor committed before anything reads the table."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass

from tksheet import Sheet

EDITABLE = "#ffffff"
READONLY = "#f1f5f9"
DISABLED = "#e2e8f0"
MISSING = "#fde8e8"  # a needed value is blank or invalid
REFUSED = "#f8b4b4"  # the typed text could not be entered


def pending_edit(sheet: Sheet) -> tuple[int, int, str] | None:
    editor = sheet.MT.text_editor
    if editor.open:
        row, column = editor.coords
        return row, column, sheet.get_text_editor_value()
    return None


def pending_dirty(sheet: Sheet) -> bool:
    edit = pending_edit(sheet)
    return edit is not None and edit[2] != sheet.get_cell_data(edit[0], edit[1])


def commit_editor(sheet: Sheet) -> None:
    """Write an open cell editor into the table, emitting the usual modified event."""
    edit = pending_edit(sheet)
    sheet.close_text_editor(set_data=True)
    if edit is None or not sheet.MT.text_editor.open:
        return
    # tksheet 7.6 leaves the editor open when the window has no OS focus; write the text through the public API
    # (keeping undo and the event) and hide the editor.
    row, column, value = edit
    if value != sheet.get_cell_data(row, column):
        sheet.set_data((row, column), data=value, undo=True, emit_event=True)
    sheet.MT.hide_text_editor_and_dropdown()


@dataclass
class SheetCell:
    sheet: Sheet
    row: int
    column: int

    def get(self) -> str:
        return str(self.sheet.get_cell_data(self.row, self.column))

    def show(self, text: str) -> None:
        """Replace the text without an undo step or a modified event (the editor's own display)."""
        self.sheet.set_cell_data(self.row, self.column, text)

    def type(self, text: str) -> None:
        """Write *text* as the user would, with undo and the modified event."""
        self.sheet.set_data((self.row, self.column), data=text, undo=True, emit_event=True)

    def color(self, background: str) -> None:
        self.sheet.highlight_cells(self.row, self.column, bg=background)

    def focus(self) -> None:
        self.sheet.select_cell(self.row, self.column)
        self.sheet.see(self.row, self.column)
        self.sheet.focus_set()


def make_sheet(parent: tk.Misc, headers: list[str], data: list[list[str]], widths: list[int], *,
               max_height: int = 370, row_labels: list[str] | None = None, index_width: int = 42) -> Sheet:
    """A table with every cell read-only; the editor opens the cells it binds."""
    lines = max((header.count("\n") + 1 for header in headers), default=1)
    header_height = 32 if lines == 1 else 50 if lines == 2 else 66
    preferred_width = min(1000, sum(widths) + index_width + 20)
    sheet = Sheet(
        parent, headers=headers, data=data, total_columns=len(headers), row_index=row_labels,
        width=preferred_width, height=min(max_height, header_height + 30 * max(1, len(data)) + 24),
        default_row_height=30, default_header_height=header_height, default_row_index_width=index_width,
        font=("Yu Gothic UI", 10, "normal"), header_font=("Yu Gothic UI", 9, "bold"),
        index_font=("Yu Gothic UI", 9, "normal"), table_bg=EDITABLE, table_fg="#23344a",
        table_grid_fg="#dbe3ed", header_bg="#eaf0f7", header_fg="#244969", index_bg=READONLY,
        index_fg="#244969", top_left_bg="#eaf0f7", paste_can_expand_x=False, paste_can_expand_y=False,
        cell_auto_resize_enabled=False, auto_resize_row_index=False, edit_cell_tab="right",
        edit_cell_return="down", startup_focus=False, empty_vertical=0, empty_horizontal=0,
        row_index_align="w" if row_labels else "center",
    )
    sheet.preferred_width = preferred_width
    sheet.set_options(redo_bindings=[*sheet.ops.redo_bindings, "<Control-y>", "<Control-Y>"], redo_accelerator="Ctrl+Y")
    sheet.enable_bindings("single_select", "drag_select", "row_select", "column_select", "select_all", "arrowkeys",
                          "copy", "cut", "paste", "delete", "undo", "redo", "edit_cell", "right_click_popup_menu",
                          "column_width_resize", "double_click_column_resize")
    sheet.set_column_widths(widths)
    sheet.readonly_cells(cells=[(r, c) for r, row in enumerate(data) for c in range(len(row))])
    sheet.highlight_cells(row="all", column="all", bg=READONLY)
    return sheet
