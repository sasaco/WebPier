"""The section drawing of the rebar page: the outline of the member and, for the column, the bars in use.

Drawing only. The column bars come from calc.column_rebar; the beam and the footing are drawn as outlines, because
no stage places their bars yet.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from ..core.errors import InputError
from ..core.reader import Reader
from ..inputs.fields import read
from .document import EditorError

Point = tuple[float, float]


@dataclass(frozen=True)
class Circle:
    x: float  # mm from the left face
    y: float  # mm from the top face
    diameter: float
    selected: bool = False


def _mm(data: Any, group: str, key: str) -> float:
    try:
        value = read(Reader(data).at("下部構造", "寸法", group, key))
    except InputError as exc:
        raise EditorError(str(exc)) from None
    return value.value * 1000


def outline(member: str, data: Any, direction: str = "線路") -> list[Point]:
    """The section polygon in mm (x to the right, y down from the top face)."""
    if member == "柱":
        width, height = _mm(data, "正面", "W6"), _mm(data, "側面", "B6")
        return [(0, 0), (width, 0), (width, height), (0, height)]
    if member == "梁":
        width, left, right = (_mm(data, "側面", key) for key in ("B1", "B4", "B5"))
        h2, h3 = _mm(data, "高さ", "H2"), _mm(data, "高さ", "H3")
        return [(0, 0), (width, 0), (width, h2), (width - right, h2 + h3), (left, h2 + h3), (0, h2)]
    group, prefix = ("側面", "B") if direction == "線路" else ("正面", "W")
    first, top, last = (_mm(data, group, f"{prefix}{index}") for index in (7, 8, 9))
    taper, depth = _mm(data, "高さ", "H5"), _mm(data, "高さ", "H6")
    width = first + top + last
    return [(first, 0), (first + top, 0), (width, taper), (width, taper + depth), (0, taper + depth), (0, taper)]


def inset(polygon: Sequence[Point], distance: float) -> list[Point]:
    """A rectangle *distance* inside the bounding box (the enclosing hoop of the rectangular column)."""
    xs, ys = [x for x, _ in polygon], [y for _, y in polygon]
    left, top, right, bottom = min(xs) + distance, min(ys) + distance, max(xs) - distance, max(ys) - distance
    return [] if right <= left or bottom <= top else [(left, top), (right, top), (right, bottom), (left, bottom)]


class SectionView(ttk.Frame):
    def __init__(self, parent: tk.Misc, *, on_bar: Callable[[int], None] | None = None) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, width=300, height=220, background="#f8fafc", highlightthickness=1,
                                highlightbackground="#dbe3ed")
        self.canvas.pack(fill="both", expand=True, pady=4)
        self.notice = ttk.Label(self, text="", style="Muted.TLabel", wraplength=300, justify="left")
        self.notice.pack(fill="x")
        self._on_bar = on_bar
        self._shown: tuple = ([], [], [], "", "")
        self.canvas.bind("<Configure>", lambda event: self._draw())
        self.canvas.tag_bind("rebar", "<Button-1>", self._clicked)

    def show(self, polygon: Sequence[Point], circles: Sequence[Circle] = (), hoop: Sequence[Point] = (), *,
             caption: str = "", notice: str = "") -> None:
        self._shown = (list(polygon), list(circles), list(hoop), caption, notice)
        self._draw()

    def _draw(self) -> None:
        polygon, circles, hoop, caption, notice = self._shown
        canvas = self.canvas
        canvas.delete("all")
        self.notice.configure(text=notice)
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if not polygon:
            canvas.create_text(max(width, 2) / 2, max(height, 2) / 2, text="断面寸法を入力してください", fill="#64748b",
                               tags=("empty",))
            return
        xs, ys = [x for x, _ in polygon], [y for _, y in polygon]
        span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
        scale = min((max(width, 60) - 40) / span_x, (max(height, 80) - 50) / span_y)
        ox, oy = (width - span_x * scale) / 2 - min(xs) * scale, 22 - min(ys) * scale

        def point(x: float, y: float) -> Point:
            return ox + x * scale, oy + y * scale

        canvas.create_polygon([v for xy in polygon for v in point(*xy)], fill="#eef3f7", outline="#526981",
                              width=1.5, tags=("section-outline",))
        if hoop:
            canvas.create_polygon([v for xy in hoop for v in point(*xy)], fill="", outline="#829bb5", width=1.5,
                                  tags=("hoop",))
        for index, circle in enumerate(circles):
            x, y = point(circle.x, circle.y)
            radius = max(2.5, circle.diameter * scale / 2)
            tags = ("rebar", f"bar:{index}", *(("selected",) if circle.selected else ()))
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius,
                               fill="#1674bf" if circle.selected else "#526981",
                               outline="white" if radius >= 4 else "", tags=tags)
        canvas.create_text(width / 2, 10, text=caption, fill="#64748b", font=("Yu Gothic UI", 8), tags=("caption",))
        canvas.create_text(width / 2, height - 12, text=f"{span_x:g} mm × {span_y:g} mm", fill="#526981",
                           font=("Yu Gothic UI", 9), tags=("size",))

    def _clicked(self, event: tk.Event) -> None:
        current = self.canvas.find_withtag("current")
        if not current or self._on_bar is None:
            return
        for tag in self.canvas.gettags(current[0]):
            if tag.startswith("bar:"):
                self._on_bar(int(tag[4:]))
                return
