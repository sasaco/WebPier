"""The modeless window of the column's section and its 方向別の鉄筋配置表 (decision 68).

It stays open beside the 鉄筋 page and is redrawn after every edit. The section shows the bars in use coloured by
their direction (a corner bar shared by both dark), with a ring on the bars changed in a table and on the picked bar.
A table lists the rows of one direction by their generated centre and size (rebar_edit.table_lines); the centre and
size cells are edited like a sheet (Return moves down). An edit is a change of that row (rebar_edit.change_table),
entered through the field table and refused when the layout would not hold with it, so a change never leaves the
section unplaceable. The changes whose generated bars are gone are named, with a button to remove them.
"""

from __future__ import annotations

import copy
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING

from ..calc.column_rebar import layer_name
from ..inputs.fields import field
from . import rebar_edit
from .document import EditorError
from .entry import EntryError, enter
from .grid import EDITABLE, READONLY, make_sheet
from .rebar_canvas import Circle, SectionView, inset, outline

if TYPE_CHECKING:
    from .app import InputEditor

VIEWS = (("section", "断面図"), ("線路", "配置表：線路方向"), ("直角", "配置表：直角方向"))
COLORS = {"線路": "#1d5fa7", "直角": "#d27a22"}
SHARED, CHANGED, PICKED, CHANGED_ROW = "#1f2937", "#7c3aed", "#f2b705", "#f1e9ff"
HEADS = {"線路": "上面からの芯位置 mm", "直角": "左面からの芯位置 mm"}
KEYS = ("center_mm", "diameter_mm")  # the editable columns 0 and 1


def _field(key: str):
    return field(("鉄筋", "柱", "table_overrides", "線路", 0, key))


class ColumnWindow:
    member = "柱"

    def __init__(self, editor: InputEditor, on_close: Callable[[], None]) -> None:
        self.editor, self.on_close = editor, on_close
        self.view: str = editor.rebar_state.get("window_view", "section")
        self.picked: int | None = None
        self.lines: list[rebar_edit.TableLine] = []
        root = editor.root
        window = self.window = tk.Toplevel(root)
        window.title("断面図・配置表 — 柱")
        window.transient(root)
        window.geometry(f"640x620+{root.winfo_rootx() + max(0, root.winfo_width() - 660)}+{root.winfo_rooty() + 120}")
        window.protocol("WM_DELETE_WINDOW", self.close)
        bar = ttk.Frame(window, padding=(10, 8, 10, 0))
        bar.pack(fill="x")
        self.choice = tk.StringVar(master=window, value=self.view)
        for value, label in VIEWS:
            tk.Radiobutton(bar, text=label, value=value, variable=self.choice, indicatoron=False, padx=10, pady=2,
                           selectcolor="#cfe0f2", command=lambda: self.select(self.choice.get())).pack(side="left")
        body = ttk.Frame(window, padding=10)
        body.pack(fill="both", expand=True)
        self.section = SectionView(body, on_bar=self.pick)
        self.table = ttk.Frame(body)
        self.sheet = make_sheet(self.table, ["芯位置 mm", "径", "本数", "段", "変更"], [], [160, 60, 50, 160, 130],
                                max_height=420)
        self.sheet.pack(fill="both", expand=True)
        self.sheet.bind("<<SheetModified>>", lambda event: self.edited(), add="+")
        ttk.Button(self.table, text="選んだ行を元に戻す", command=self.undo).pack(anchor="w", pady=(6, 0))
        self.message = tk.StringVar(master=window)
        ttk.Label(body, textvariable=self.message, style="Muted.TLabel", wraplength=600).pack(side="bottom", anchor="w")
        self.unmatched = ttk.Frame(body)
        self.unmatched_text = tk.StringVar(master=window)
        ttk.Label(self.unmatched, textvariable=self.unmatched_text, foreground="#b45309", wraplength=440).pack(
            side="left")
        ttk.Button(self.unmatched, text="見つからない変更を消す", command=self.remove_unmatched).pack(side="left", padx=6)
        self.footer = tk.StringVar(master=window)
        ttk.Label(body, textvariable=self.footer).pack(side="bottom", anchor="w", pady=(6, 0))
        self.refresh()

    # views ----------------------------------------------------------------------------------------------------

    def select(self, view: str) -> None:
        self.view = self.editor.rebar_state["window_view"] = view
        self.choice.set(view)
        self.refresh()

    def pick(self, index: int) -> None:
        self.picked = index
        self.refresh()

    def close(self) -> None:
        self.window.destroy()
        self.on_close()

    # edits ----------------------------------------------------------------------------------------------------

    def _shown(self, line: rebar_edit.TableLine, column: int) -> str:
        return f"{line.center:.1f}" if column == 0 else f"D{line.diameter:g}"

    def edited(self) -> None:
        """A centre or size typed into the table: the change of its row, if the layout holds with it."""
        for row, line in enumerate(self.lines):
            for column, key in enumerate(KEYS):
                text = str(self.sheet.get_cell_data(row, column))
                if text == self._shown(line, column):
                    continue
                try:
                    value = enter(_field(key), text.strip().removeprefix("D").removeprefix("d"))
                    trial = copy.deepcopy(self.editor.document.data)
                    rebar_edit.change_table(trial, self.view, line.source, key, value)
                    rebar_edit.column_preview(trial)
                except (EntryError, EditorError) as exc:
                    self.message.set(f"変更できません：{exc}")
                    self.refresh()
                    return
                rebar_edit.change_table(self.editor.document.data, self.view, line.source, key, value)
                self.message.set("")
                self.editor.changed()
                return

    def undo(self) -> bool:
        selected = self.sheet.get_currently_selected()
        if (not selected or self.view == "section" or selected.row >= len(self.lines)
                or not self.lines[selected.row].changed):
            return False
        rebar_edit.undo_change(self.editor.document.data, self.view, self.lines[selected.row].source)
        self.editor.changed()
        return True

    def remove_unmatched(self) -> int:
        layout = rebar_edit.column_preview(self.editor.document.data)
        removed = rebar_edit.remove_unmatched(self.editor.document.data, layout)
        self.editor.changed()
        return removed

    # drawing --------------------------------------------------------------------------------------------------

    def _hoop(self, polygon: list) -> list:
        column = self.editor.document.data["鉄筋"]["柱"]
        pure, diameter = column["pure_cover_mm"], column["column_hoops"]["enclosing_diameter_mm"]
        if not all(isinstance(value, (int, float)) for value in (pure, diameter)):
            return []
        return inset(polygon, pure + diameter / 2)

    def refresh(self) -> None:
        if not self.window.winfo_exists():
            return
        data = self.editor.document.data
        on_section = self.view == "section"
        if on_section:
            self.table.pack_forget()
            self.section.pack(fill="both", expand=True)
        else:
            self.section.pack_forget()
            self.table.pack(fill="both", expand=True)
        self.unmatched.pack_forget()
        self.lines = []
        try:
            polygon = outline("柱", data)
        except EditorError as exc:
            self.section.show([], notice=str(exc))
            self._table()
            self.footer.set("")
            return
        hoop = self._hoop(polygon)
        try:
            layout = rebar_edit.column_preview(data)
        except EditorError as exc:
            self.section.show(polygon, hoop=hoop, notice=str(exc))
            self._table()
            self.footer.set("")
            return
        circles = []
        for index, bar in enumerate(layout.bars):
            directions = {direction for direction, _ in bar.rows}
            ring = PICKED if index == self.picked else CHANGED if (bar.x, bar.y, bar.diameter) != bar.origin else None
            circles.append(Circle(bar.x.value, bar.y.value, bar.diameter.value,
                                  fill=SHARED if len(directions) > 1 else COLORS[bar.rows[0][0]], ring=ring))
        self.section.show(polygon, circles, hoop, caption="X：直角 ／ Y：線路（上面から）",
                          notice="青：線路方向の段　橙：直角方向の段　黒：角（共有）　紫の輪：配置表で変更")
        if not on_section:
            self.lines = rebar_edit.table_lines(layout, self.view)
            self.sheet.headers([HEADS[self.view], "径", "本数", "段", "変更"])
        self._table()
        if layout.unmatched:
            self.unmatched_text.set(f"警告：元の芯位置・径の鉄筋が見つからない配置表の変更が {len(layout.unmatched)} 件"
                                    "あります（計算では使いません）。")
            self.unmatched.pack(side="bottom", fill="x", pady=(6, 0))
        footer = f"物理本数 {len(layout.bars)} 本"
        if self.picked is not None and self.picked < len(layout.bars):
            bar = layout.bars[self.picked]
            shared = "で共有" if len(bar.rows) > 1 else ""
            footer += (f"　X {bar.x.value:.1f}・Y {bar.y.value:.1f}・D{bar.diameter.value:g}・"
                       f"{'と'.join(layer_name(key) for key in bar.rows)}{shared}")
        self.footer.set(footer)

    def _table(self) -> None:
        rows = [[self._shown(line, 0), self._shown(line, 1), str(line.count),
                 "・".join(layer_name(key) for key in line.layers),
                 f"元：{line.source[0]:.1f}・D{line.source[1]:g}" if line.changed else ""] for line in self.lines]
        sheet = self.sheet
        sheet.set_sheet_data(rows, reset_col_positions=False, redraw=False)
        sheet.dehighlight_all()
        sheet.highlight_cells(row="all", column="all", bg=READONLY)
        sheet.readonly_cells(cells=[(r, c) for r in range(len(rows)) for c in range(5)])
        for r, line in enumerate(self.lines):
            for c in (0, 1):
                sheet.readonly_cells(r, c, readonly=False)
                sheet.highlight_cells(r, c, bg=CHANGED_ROW if line.changed else EDITABLE)
        sheet.redraw()
