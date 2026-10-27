"""The modeless window of the column's section and its 方向別の鉄筋配置表 (decisions 68, 111).

It stays open beside the 鉄筋 page and is redrawn after every edit. The section shows the bars the main bars make,
coloured by their direction (a corner bar shared by both dark), with a ring on the picked bar. A table view shows the
方向別の鉄筋配置表 of one direction in use (rebar_edit.direction_view) and, above it, its rows drawn across the section
with their counts, the 引張鉄筋 rows in the colour of the direction. Editing the table is the 配置表の手直し
(rebar_edit.customize): a centre, size or count typed into a cell (Return moves down), a row added (a copy of the
selected one), deleted, or moved up or down (the order decides the 引張鉄筋), and the 引張鉄筋の段数. Each is entered
through the field table and refused when the table would not hold with it, so an edit never leaves the column
unplaceable. 入力から作り直す makes the table from the main bars again.
"""

from __future__ import annotations

import copy
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from ..calc.column_rebar import ColumnLayout, DirectionTable, count_mismatch, layer_name
from ..inputs.fields import field
from . import rebar_edit
from .document import EditorError
from .entry import EntryError, enter
from .grid import EDITABLE, READONLY, make_sheet
from .rebar_canvas import Band, Circle, SectionView, inset, outline

if TYPE_CHECKING:
    from .app import InputEditor

VIEWS = (("section", "断面図"), ("線路", "配置表：線路方向"), ("直角", "配置表：直角方向"))
COLORS = {"線路": "#1d5fa7", "直角": "#d27a22"}
SHARED, PICKED, TENSION_ROW, OTHER = "#1f2937", "#f2b705", "#e6effa", "#94a3b8"
HEADS = {"線路": "上面からの芯位置 mm", "直角": "左面からの芯位置 mm"}
SIDES = {"線路": ("引張（上）", "引張（下）"), "直角": ("引張（左）", "引張（右）")}
KEYS = ("center_mm", "diameter_mm", "count")  # the editable columns 0, 1 and 2
TABLE = ("鉄筋", "柱", "custom_tables", "線路")


def _field(key: str):
    return field((*TABLE, "rows", 0, key))


TENSION = field((*TABLE, "tension_rows"))


def shown(row, column: int) -> str:
    """A cell of a table row as the window shows it."""
    return (f"{row.center.value:g}", f"D{row.diameter.value:g}", str(row.count))[column]


def bands(table: DirectionTable, width: float, height: float) -> list[Band]:
    """The rows of *table* across the section, labelled with their count (the 引張鉄筋 with their size too); a row of
    the same count as the one before it is not labelled again, so the labels of a long run do not cover each other."""
    found, previous = [], None
    for index, row in enumerate(table.rows):
        tension = index < table.tension or index >= len(table.rows) - table.tension
        centre = row.center.value
        start, end = ((0.0, centre), (width, centre)) if table.direction == "線路" else ((centre, 0.0), (centre, height))
        label = (f"D{row.diameter.value:g}×{row.count}" if tension else
                 "" if row.count == previous else str(row.count))
        found.append(Band(start, end, label, COLORS[table.direction] if tension else OTHER))
        previous = None if tension else row.count
    return found


class ColumnWindow:
    member = "柱"

    def __init__(self, editor: InputEditor, on_close: Callable[[], None]) -> None:
        self.editor, self.on_close = editor, on_close
        self.view: str = editor.rebar_state.get("window_view", "section")
        self.picked: int | None = None
        self.layout: ColumnLayout | None = None
        self.shown: DirectionTable | None = None
        self.selected: int | None = None  # the table row to select again after a redraw
        root = editor.root
        window = self.window = tk.Toplevel(root)
        window.title("断面図・配置表 — 柱")
        window.transient(root)
        window.geometry(f"660x760+{root.winfo_rootx() + max(0, root.winfo_width() - 680)}+{root.winfo_rooty() + 80}")
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
        self.strip = SectionView(self.table)
        self.strip.canvas.configure(height=180)
        self.strip.pack(fill="x")
        line = ttk.Frame(self.table)
        line.pack(fill="x", pady=(4, 4))
        self.state = tk.StringVar(master=window)
        ttk.Label(line, textvariable=self.state, style="Muted.TLabel").pack(side="left")
        self.tension = tk.StringVar(master=window)
        self.tension_entry = ttk.Entry(line, textvariable=self.tension, width=5)
        self.tension_entry.pack(side="right")
        self.tension_entry.bind("<Return>", lambda event: self.set_tension())
        self.tension_entry.bind("<FocusOut>", lambda event: self.set_tension())
        ttk.Label(line, text="引張鉄筋の段数 N（上から・下から）").pack(side="right", padx=(0, 4))
        buttons = ttk.Frame(self.table)
        buttons.pack(fill="x", pady=(0, 4))
        for text, command in (("行を追加（選んだ行の下）", self.add), ("行を削除", self.delete), ("↑", lambda: self.move(-1)),
                              ("↓", lambda: self.move(1))):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=(0, 4))
        ttk.Button(buttons, text="入力から作り直す", command=self.reset).pack(side="right")
        self.sheet = make_sheet(self.table, ["芯位置 mm", "径", "本数", "区分"], [], [170, 70, 60, 110], max_height=330)
        self.sheet.pack(fill="both", expand=True)
        self.sheet.bind("<<SheetModified>>", lambda event: self.edited(), add="+")
        self.message = tk.StringVar(master=window)
        ttk.Label(body, textvariable=self.message, style="Muted.TLabel", wraplength=620).pack(side="bottom", anchor="w")
        self.footer = tk.StringVar(master=window)
        ttk.Label(body, textvariable=self.footer, wraplength=620).pack(side="bottom", anchor="w", pady=(6, 0))
        self.refresh()

    # views ----------------------------------------------------------------------------------------------------

    def select(self, view: str) -> None:
        self.view = self.editor.rebar_state["window_view"] = view
        self.choice.set(view)
        self.selected = None
        self.refresh()

    def pick(self, index: int) -> None:
        self.picked = index
        self.refresh()

    def close(self) -> None:
        self.window.destroy()
        self.on_close()

    # edits ----------------------------------------------------------------------------------------------------

    def _apply(self, change: Callable[[Any, ColumnLayout], Any]) -> Any:
        """*change* of the document (data, layout): tried on a copy first and refused, with the reason, when the column
        cannot be laid out with it."""
        if self.layout is None or self.view == "section":
            return None
        try:
            trial = copy.deepcopy(self.editor.document.data)
            change(trial, self.layout)
            rebar_edit.direction_view(rebar_edit.column_preview(trial), self.view)
        except (EntryError, EditorError) as exc:
            self.message.set(f"変更できません：{exc}")
            self.refresh()
            return None
        result = change(self.editor.document.data, self.layout)
        self.message.set("")
        self.editor.changed()
        self.refresh()  # also when the 鉄筋 page does not hold this window
        return result

    def _row(self) -> int | None:
        selected = self.sheet.get_currently_selected()
        if not selected or self.shown is None or selected.row >= len(self.shown.rows):
            return None
        return selected.row

    def edited(self) -> None:
        """A centre, size or count typed into the table."""
        if self.shown is None:
            return
        for row, line in enumerate(self.shown.rows):
            for column, key in enumerate(KEYS):
                text = str(self.sheet.get_cell_data(row, column))
                if text == shown(line, column):
                    continue
                try:
                    value = enter(_field(key), text.strip().removeprefix("D").removeprefix("d"))
                except EntryError as exc:
                    self.message.set(f"変更できません：{exc}")
                    self.refresh()
                    return
                self.selected = row
                self._apply(lambda data, layout: rebar_edit.set_cell(data, layout, self.view, row, key, value))
                return

    def set_tension(self) -> None:
        if self.shown is None or self.tension.get().strip() == str(self.shown.tension):
            return
        try:
            value = enter(TENSION, self.tension.get())
        except EntryError as exc:
            self.message.set(f"変更できません：{exc}")
            self.refresh()
            return
        self._apply(lambda data, layout: rebar_edit.set_tension(data, layout, self.view, value))

    def add(self) -> int | None:
        index = self._row()
        if index is None:
            self.message.set("行を選んでから追加してください（選んだ行の写しが下に入ります）。")
            return None
        self.selected = index + 1
        return self._apply(lambda data, layout: rebar_edit.insert_row(data, layout, self.view, index))

    def delete(self) -> bool:
        index = self._row()
        if index is None:
            return False
        self.selected = max(0, index - 1)
        return bool(self._apply(lambda data, layout: rebar_edit.delete_table_row(data, layout, self.view, index)))

    def move(self, step: int) -> int | None:
        index = self._row()
        if index is None or not 0 <= index + step < len(self.shown.rows if self.shown else ()):
            return None
        self.selected = index + step
        return self._apply(lambda data, layout: rebar_edit.move_row(data, layout, self.view, index, step))

    def reset(self) -> bool:
        """入力から作り直す: the table of the view is the one the main bars make again."""
        if self.view == "section" or not rebar_edit.reset_table(self.editor.document.data, self.view):
            return False
        self.selected = None
        self.message.set("")
        self.editor.changed()
        self.refresh()
        return True

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
        self.layout, self.shown = None, None
        try:
            polygon = outline("柱", data)
        except EditorError as exc:
            self.section.show([], notice=str(exc))
            self.strip.show([], notice=str(exc))
            self._table()
            self.footer.set("")
            return
        hoop = self._hoop(polygon)
        try:
            layout = self.layout = rebar_edit.column_preview(data)
        except EditorError as exc:
            self.section.show(polygon, hoop=hoop, notice=str(exc))
            self.strip.show(polygon, notice=str(exc))
            self._table()
            self.footer.set("")
            return
        circles = []
        for index, bar in enumerate(layout.bars):
            directions = {direction for direction, _ in bar.rows}
            circles.append(Circle(bar.x.value, bar.y.value, bar.diameter.value,
                                  fill=SHARED if len(directions) > 1 else COLORS[bar.rows[0][0]],
                                  ring=PICKED if index == self.picked else None))
        notice = "青：線路方向の段　橙：直角方向の段　黒：角（共有）"
        if layout.customized:
            notice += "\n手直しした配置表があります。計算はその表を使います（この断面図は主鉄筋の入力の並びです）。"
        self.section.show(polygon, circles, hoop, caption="X：直角 ／ Y：線路（上面から）", notice=notice)
        footer = f"物理本数 {len(layout.bars)} 本"
        if self.picked is not None and self.picked < len(layout.bars):
            bar = layout.bars[self.picked]
            shared = "で共有" if len(bar.rows) > 1 else ""
            footer += (f"　X {bar.x.value:.1f}・Y {bar.y.value:.1f}・D{bar.diameter.value:g}・"
                       f"{'と'.join(layer_name(key) for key in bar.rows)}{shared}")
        if (mismatch := count_mismatch(layout)) is not None:
            footer += f"\n警告：2つの配置表で鉄筋の本数が違います（{mismatch}）。計算は止めません。"
        if not on_section:
            try:
                self.shown = rebar_edit.direction_view(layout, self.view)
            except EditorError as exc:
                self.strip.show(polygon, notice=str(exc))
            else:
                width, height = polygon[2]
                self.strip.show(polygon, bands=bands(self.shown, width, height),
                                caption=f"{self.view}方向の配置表（色：引張鉄筋）")
            self.sheet.headers([HEADS[self.view], "径", "本数", "区分"])
        self._table()
        self.footer.set(footer)

    def _table(self) -> None:
        table, sheet = self.shown, self.sheet
        if table is None:
            self.state.set("")
            self.tension.set("")
            sheet.set_sheet_data([], reset_col_positions=False, redraw=True)
            return
        self.state.set("手直しした表（計算はこの表を使います）" if table.custom else "主鉄筋の入力から作った表")
        self.tension.set(str(table.tension))
        upper, lower = SIDES[table.direction]
        count = len(table.rows)
        kinds = [upper if index < table.tension else lower if index >= count - table.tension else ""
                 for index in range(count)]
        rows = [[shown(row, 0), shown(row, 1), shown(row, 2), kind] for row, kind in zip(table.rows, kinds)]
        sheet.set_sheet_data(rows, reset_col_positions=False, redraw=False)
        sheet.dehighlight_all()
        sheet.highlight_cells(row="all", column="all", bg=READONLY)
        sheet.readonly_cells(cells=[(r, c) for r in range(count) for c in range(4)])
        for r, kind in enumerate(kinds):
            for c in range(3):
                sheet.readonly_cells(r, c, readonly=False)
                sheet.highlight_cells(r, c, bg=TENSION_ROW if kind else EDITABLE)
        if self.selected is not None and self.selected < count:
            sheet.select_row(self.selected, redraw=False)
            sheet.see(self.selected, 0)
        sheet.redraw()
