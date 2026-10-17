"""Building blocks of the input pages: titled sections, bound tables, property lists and reference figures.

Captions and notes are the editor's; digits, units, signs and choices come from the field table.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from tksheet import Sheet

from ..inputs.fields import field
from .document import JsonPath
from .grid import make_sheet

if TYPE_CHECKING:
    from .app import InputEditor

ASSETS = Path(__file__).with_name("assets")
Cell = str | JsonPath  # a caption, or the path of a bound value


def unit_text(unit: str) -> str:
    return unit.replace("m3", "m³").replace("m2", "m²")


def unit_of(path: JsonPath) -> str:
    return unit_text(field(path).unit)


class Form:
    """One page of the editor; tables it builds are bound and watched by the editor's bindings."""

    def __init__(self, editor: InputEditor, parent: ttk.Frame) -> None:
        self.editor = editor
        self.parent = parent

    @property
    def data(self) -> Any:
        return self.editor.document.data

    def section(self, title: str, *, note: str = "", parent: tk.Misc | None = None) -> ttk.Frame:
        frame = ttk.LabelFrame(parent or self.parent, text=title, padding=12, style="Sheet.TLabelframe")
        frame.pack(fill="x", pady=(0, 14))
        if note:
            ttk.Label(frame, text=note, style="Muted.TLabel", wraplength=980).pack(anchor="w", pady=(0, 9))
        body = ttk.Frame(frame)
        body.pack(fill="x")
        return body

    def table(self, parent: tk.Misc, headers: list[str], rows: Sequence[Sequence[Cell]], widths: list[int], *,
              writers: dict[JsonPath, Callable[[Any], None]] | None = None, row_labels: list[str] | None = None,
              index_width: int = 42, max_height: int = 370, pack: bool = True) -> Sheet:
        """A table whose path cells are bound to the document; captions stay read-only."""
        data = [[cell if isinstance(cell, str) else "" for cell in row] for row in rows]
        sheet = make_sheet(parent, headers, data, widths, max_height=max_height, row_labels=row_labels,
                           index_width=index_width)
        bindings = self.editor.bindings
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                if not isinstance(cell, str):
                    bindings.bind(sheet, r, c, cell, write=(writers or {}).get(cell))
        bindings.watch(sheet)
        sheet.bind("<<SheetSelect>>", lambda event: self.editor.cell_selected(sheet), add="+")
        if pack:
            sheet.pack(anchor="w")
        return sheet

    def properties(self, parent: tk.Misc, specs: Sequence[tuple[JsonPath, str]], *,
                   widths: list[int] | None = None) -> Sheet:
        return self.table(parent, ["項目・記号", "値", "単位"], [[label, path, unit_of(path)] for path, label in specs],
                          widths or [260, 150, 100])

    def button(self, parent: tk.Misc, text: str, command: Callable[[], Any]) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command)
        button.pack(anchor="w", pady=(6, 0))
        return button

    def figure(self, parent: tk.Misc, name: str, caption: str) -> None:
        frame = ttk.Frame(parent, padding=(10, 0, 0, 0))
        frame.pack(fill="x")
        try:
            photo = self.editor.images.get(name)
            if photo is None:
                photo = tk.PhotoImage(master=self.editor.root, file=str(ASSETS / f"{name}.png"))
                self.editor.images[name] = photo
        except tk.TclError:
            ttk.Label(frame, text="参照図を読み込めませんでした。", style="Muted.TLabel").pack()
            return
        label = ttk.Label(frame, image=photo, cursor="hand2", background="white")
        label.pack(anchor="center")
        label.bind("<Button-1>", lambda event: self.enlarge(name, caption))
        ttk.Label(frame, text=caption + "  ·  クリックで拡大", style="Caption.TLabel").pack(anchor="center", pady=(6, 0))

    def enlarge(self, name: str, caption: str) -> tk.Toplevel:
        window = tk.Toplevel(self.editor.root)
        window.title(caption + " — 原図・記号確認用")
        window.geometry("1100x760")
        ttk.Label(window, text="原図・記号確認用（入力値には連動しません）", padding=10).pack(anchor="w")
        canvas = tk.Canvas(window, background="white", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        try:
            photo = tk.PhotoImage(master=window, file=str(ASSETS / f"{name}_large.png"))
        except tk.TclError:
            photo = self.editor.images[name]
        window.reference_image = photo  # keep the Tcl image alive with its window
        canvas.create_image(12, 12, image=photo, anchor="nw")
        canvas.configure(scrollregion=canvas.bbox("all"))
        window.bind("<Escape>", lambda event: window.destroy())
        return window
