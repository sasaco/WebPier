"""The column dialogs: compare the bars in use with the automatic layout before replacing them, and add one bar.

A dialog belongs to the rebar page, which refuses its own actions while one is open. The grab only adds modality:
Tk keeps one grab per display for every interpreter of the process, so taking it can fail because of another
window; that never leaves a half-built window behind or the page unguarded, and closing never asks Tk whose grab
is current (which can name a window of another interpreter).
"""

from __future__ import annotations

import tkinter as tk
from collections import Counter
from collections.abc import Callable, Sequence
from tkinter import ttk
from typing import Any

from ..inputs import choices
from ..inputs.fields import field
from .document import EditorError
from .entry import EntryError, display, enter
from .grid import make_sheet
from .lifecycle import destroy
from .rebar_edit import ROW_KEYS, Comparison

POSITION_KEYS = ROW_KEYS[("bar", "manual_positions")]
POSITION_LABELS = ("X mm", "Y mm", "径 mm", "材質")
CHANGED = "#fff0d5"


class Modal:
    def __init__(self, root: tk.Misc, title: str, on_close: Callable[[], None]) -> None:
        self._root = root
        self._on_close = on_close
        self.closed = False
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title(title)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())
        self.error = tk.StringVar(master=self.window, value="")

    def footer(self, parent: tk.Misc, apply: Callable[[], Any]) -> None:
        ttk.Label(parent, textvariable=self.error, style="Error.TLabel", wraplength=750).pack(fill="x", pady=4)
        actions = ttk.Frame(parent)
        actions.pack(fill="x")
        ttk.Button(actions, text="取消", command=self.close).pack(side="right", padx=4)
        self.apply_button = ttk.Button(actions, text="適用", command=apply)
        self.apply_button.pack(side="right", padx=4)

    def present(self) -> None:
        self.window.transient(self._root)
        self.window.deiconify()
        try:
            self.window.grab_set()
        except tk.TclError:
            pass  # another window holds the grab; the page still blocks its actions while this dialog is open
        self.window.focus_set()

    def close(self) -> bool:
        if self.closed:
            return False
        self.closed = True
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        destroy(self.window)
        self._on_close()
        return True


def _key(bar: dict[str, Any]) -> tuple:
    return tuple(bar.get(key) for key in POSITION_KEYS)


def summary(bars: Sequence[dict[str, Any]]) -> str:
    counts = Counter(bar["diameter_mm"] for bar in bars)
    return f"総本数 {len(bars)} 本　" + " / ".join(f"D{size:g} × {count}" for size, count in sorted(counts.items()))


class RegenerationDialog(Modal):
    """The bars in use beside the automatic layout; 適用 replaces them (or, to the automatic layout, switches)."""

    def __init__(self, root: tk.Misc, shown: Comparison, size: tuple[float, float], *, to_auto: bool,
                 apply: Callable[[Comparison], str | None], on_close: Callable[[], None]) -> None:
        super().__init__(root, "自動配置へ切替 — 新旧の確認" if to_auto else "再配置 — 新旧の確認", on_close)
        self.shown = shown
        self._apply = apply
        body = ttk.Frame(self.window, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="自動配置を使います。詳細位置は保存したまま残します。" if to_auto else
                  "適用すると詳細位置を新しい自動配置で置き換え、詳細位置を使います。", wraplength=760).pack(anchor="w")
        panels = ttk.Frame(body)
        panels.pack(fill="both", expand=True)
        current, candidate = {_key(bar) for bar in shown.current}, {_key(bar) for bar in shown.candidate}
        self.sheets = []
        for column, (label, bars, other) in enumerate((("現在の使用位置", shown.current, candidate),
                                                       ("新しい自動配置", shown.candidate, current))):
            panel = ttk.Frame(panels, padding=5)
            panel.grid(row=0, column=column, sticky="nsew")
            ttk.Label(panel, text=label, style="Symbol.TLabel").pack(anchor="w")
            ttk.Label(panel, text=summary(bars)).pack(anchor="w")
            figure = tk.Canvas(panel, width=330, height=150, background="#f8fafc", highlightthickness=0)
            figure.pack(fill="x", pady=4)
            figure.bind("<Configure>", lambda event, canvas=figure, bars=bars, other=other:
                        self._draw(canvas, bars, other, size))
            rows = [[display(field(("鉄筋", "柱", "manual_positions", 0, key)), bar[key]) for key in POSITION_KEYS]
                    for bar in bars]
            sheet = make_sheet(panel, list(POSITION_LABELS), rows, [78, 78, 60, 78], max_height=230)
            sheet.pack(fill="both", expand=True)
            for index, bar in enumerate(bars):
                if _key(bar) not in other:
                    sheet.highlight_cells(row=index, bg=CHANGED)
            self.sheets.append(sheet)
        ttk.Label(body, text=f"同じ位置・径・材質：{len(current & candidate)} 本　現在のみ：{len(current - candidate)} 本　"
                  f"新しい配置のみ：{len(candidate - current)} 本（橙色）").pack(anchor="w", pady=6)
        self.footer(body, self.apply)
        self.window.geometry("820x560")

    @staticmethod
    def _draw(canvas: tk.Canvas, bars: Sequence[dict[str, Any]], other: set, size: tuple[float, float]) -> None:
        canvas.delete("all")
        width, height = max(40, canvas.winfo_width()), max(40, canvas.winfo_height())
        scale = min((width - 20) / size[0], (height - 20) / size[1])
        ox = (width - size[0] * scale) / 2
        canvas.create_rectangle(ox, 10, ox + size[0] * scale, 10 + size[1] * scale, outline="#526981", fill="#eef3f7")
        for bar in bars:
            x, y = ox + bar["x_mm"] * scale, 10 + bar["y_mm"] * scale
            radius = max(2, bar["diameter_mm"] * scale / 2)
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius, outline="",
                               fill="#1674bf" if _key(bar) in other else "#cc7a00")

    def apply(self) -> bool:
        problem = self._apply(self.shown)
        if problem is not None:
            self.error.set(problem)
            self.apply_button.state(["disabled"])
            return False
        return self.close()


class AddBarDialog(Modal):
    """One bar of the detail positions, entered through the field table like any cell."""

    def __init__(self, root: tk.Misc, material: str | None, *, apply: Callable[[dict[str, Any]], str | None],
                 on_close: Callable[[], None]) -> None:
        super().__init__(root, "鉄筋を追加 — 芯位置 mm", on_close)
        self._apply = apply
        body = ttk.Frame(self.window, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="X は左面、Y は上面からの芯位置（mm）。入力した時点の桁に丸めます。").pack(anchor="w", pady=5)
        self.values: dict[str, tk.StringVar] = {}
        for key, label in zip(POSITION_KEYS, POSITION_LABELS):
            line = ttk.Frame(body)
            line.pack(fill="x", pady=4)
            ttk.Label(line, text=label, width=10).pack(side="left")
            variable = tk.StringVar(master=self.window, value=(material or "") if key == "material" else "")
            self.values[key] = variable
            if key == "material":
                ttk.Combobox(line, textvariable=variable, values=("", *choices.STEEL_GRADES), state="readonly",
                             width=16).pack(side="left", fill="x", expand=True)
            else:
                ttk.Entry(line, textvariable=variable, width=18).pack(side="left", fill="x", expand=True)
        self.footer(body, self.apply)

    def apply(self) -> bool:
        bar = {}
        for key, variable in self.values.items():
            try:
                bar[key] = enter(field(("鉄筋", "柱", "manual_positions", 0, key)), variable.get())
            except EntryError as exc:
                self.error.set(f"{POSITION_LABELS[POSITION_KEYS.index(key)]}: {exc}")
                return False
        problem = self._apply(bar)
        if problem is not None:
            self.error.set(problem)
            return False
        return self.close()


def guarded(action: Callable[[], Any]) -> str | None:
    """Run an edit of the document; the message of an EditorError, or None."""
    try:
        action()
    except EditorError as exc:
        return str(exc)
    return None
