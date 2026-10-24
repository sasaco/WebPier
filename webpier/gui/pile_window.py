"""The modeless window of the cast-in-place pile's 配筋略図 (decisions 87 and 92).

It stays open beside the 鉄筋 page and is redrawn after every edit. Left, the side view from the pile head down: the part
inside the footing, the 2D zone, the zones below it and the cut-off of the main bars. Right, the section (the head's, or
the one after the cut-off when it is entered): the main bars at their core cover, evenly round the pile, inside the
closed circular hoop, with the core cover and the core spacing. Drawing only: nothing here is used by a calculation, and
the length of the part inside the footing is not an input, so it is drawn at a fixed height.
"""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .app import InputEditor

VIEWS = (("head", "杭頭の断面"), ("cutoff", "段落し後の断面"))
SIDE_WIDTH, SIDE_HEIGHT, SECTION_SIZE, MARGIN = 220, 560, 300, 20
FOOTING_PX = 40
ZONE = ("#e3edf7", "#d3e3f2", "#c4d9ee", "#b6cfe9", "#a8c5e4")
BAR, HOOP, OUTLINE = "#1674bf", "#8a99a8", "#526981"
LEGEND = "青：主鉄筋　灰：帯鉄筋（閉じた円形、1組＝1本）"
CUTOFF_NOTE = "段落し位置は、段落し長を杭頭から下へ測って描いています"


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def bar_ring(diameter: float, cover: float, hoop: float, bar: float) -> tuple[float, float, float]:
    """(芯かぶり, ring radius of the main bars, radius of the hoop's centre line) in mm: the core cover is
    pure cover + hoop + bar/2."""
    core = cover + hoop + bar / 2
    return core, diameter / 2 - core, diameter / 2 - cover - hoop / 2


def spacing(radius: float, count: int) -> float:
    """The clear distance between neighbouring bars' centres: the chord 2·r·sin(π/n)."""
    return 2 * radius * math.sin(math.pi / count) if count > 0 else 0.0


class PileWindow:
    member = "杭"

    def __init__(self, editor: InputEditor, on_close: Callable[[], None]) -> None:
        self.editor, self.on_close = editor, on_close
        self.view: str = editor.rebar_state.get("pile_view", VIEWS[0][0])
        self.rows: list[str] = []
        root = editor.root
        window = self.window = tk.Toplevel(root)
        window.title("配筋略図 — 杭")
        window.transient(root)
        window.geometry(f"660x680+{root.winfo_rootx() + max(0, root.winfo_width() - 680)}+{root.winfo_rooty() + 80}")
        window.protocol("WM_DELETE_WINDOW", self.close)
        body = ttk.Frame(window, padding=10)
        body.pack(fill="both", expand=True)
        row = ttk.Frame(body)
        row.pack(fill="both", expand=True)
        self.side = tk.Canvas(row, width=SIDE_WIDTH, height=SIDE_HEIGHT, background="#f8fafc", highlightthickness=1,
                              highlightbackground="#dbe3ed")
        self.side.pack(side="left", anchor="n")
        right = ttk.Frame(row, padding=(12, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True, anchor="n")
        bar = ttk.Frame(right)
        bar.pack(fill="x")
        self.view_choice = tk.StringVar(master=window, value=self.view)
        for value, label in VIEWS:
            tk.Radiobutton(bar, text=label, value=value, variable=self.view_choice, indicatoron=False, padx=10, pady=2,
                           selectcolor="#cfe0f2", command=lambda: self.select(self.view_choice.get())).pack(side="left")
        self.section = tk.Canvas(right, width=SECTION_SIZE, height=SECTION_SIZE, background="#ffffff",
                                 highlightthickness=1, highlightbackground="#dbe3ed")
        self.section.pack(pady=(6, 4), anchor="w")
        ttk.Label(right, text=LEGEND, style="Muted.TLabel", wraplength=SECTION_SIZE).pack(anchor="w")
        self.row_frame = ttk.Frame(right, padding=(0, 8, 0, 0))
        self.row_frame.pack(anchor="w", fill="x")
        self.notice = tk.StringVar(master=window)
        ttk.Label(body, textvariable=self.notice, foreground="#8e1d1d", wraplength=620, justify="left").pack(
            anchor="w", pady=(8, 0))
        self.refresh()

    def select(self, view: str) -> None:
        self.view = self.editor.rebar_state["pile_view"] = view
        self.view_choice.set(view)
        self.refresh()

    def close(self) -> None:
        self.window.destroy()
        self.on_close()

    # drawing --------------------------------------------------------------------------------------------------

    def refresh(self) -> None:
        if not self.window.winfo_exists():
            return
        data = self.editor.document.data
        pile = data["鉄筋"]["杭"]
        diameter = _number(data["杭基礎"]["場所打ち杭"]["杭径"])
        diameter = None if diameter is None else diameter * 1000
        self.side.delete("all")
        self.section.delete("all")
        self._list([])
        notes: list[str] = []
        if diameter is None or diameter <= 0:
            self.notice.set("杭基礎ページで杭径を入力してください")
            return
        self._side(pile, diameter, notes)
        self._section(pile, diameter, notes)
        self.notice.set("\n".join(notes))

    def _side(self, pile: dict, diameter: float, notes: list[str]) -> None:
        canvas = self.side
        zones: list[tuple[str, float | None, dict]] = [("フーチング内", None, pile["hoops"]["footing"]),
                                                       ("2D 区間", 2 * diameter, pile["hoops"]["zone_2d"])]
        for index, lower in enumerate(pile["hoops"]["lower"], 1):
            length = _number(lower["length_m"])
            zones.append((f"第{index}区間", None if length is None else length * 1000, lower))
        lengths = [length for _, length, _ in zones[1:] if length is not None]
        total = max(sum(lengths), _number(pile["cutoff"]["cutoff_length_mm"]) or 0, 1.0) * 1.15
        scale = (SIDE_HEIGHT - 2 * MARGIN - FOOTING_PX) / total
        left, right = 60, SIDE_WIDTH - 60
        top = MARGIN
        canvas.create_rectangle(left - 30, top, right + 30, top + FOOTING_PX, fill="#dfe6ee", outline=OUTLINE,
                                tags=("footing",))
        canvas.create_text((left + right) / 2, top + FOOTING_PX / 2, text="フーチング", fill="#4a5a69",
                           font=("Yu Gothic UI", 8))
        head = top + FOOTING_PX  # the pile head
        y = head
        for index, (title, length, hoop) in enumerate(zones):
            if title == "フーチング内":
                end = head
                label = self._hoop_text(hoop)
                canvas.create_text(right + 4, head - FOOTING_PX / 2, text=label, anchor="w", fill="#3d4c5a",
                                   font=("Yu Gothic UI", 8), tags=("zone",))
                canvas.create_line(left + 8, head - FOOTING_PX + 6, left + 8, head, fill=HOOP, width=2, tags=("hoops",))
                continue
            if length is None:
                break
            end = y + length * scale
            canvas.create_rectangle(left, y, right, end, fill=ZONE[index % len(ZONE)], outline=OUTLINE, tags=("zone",))
            canvas.create_text(left + 6, (y + end) / 2, text=title, anchor="w", fill="#3d4c5a", font=("Yu Gothic UI", 8))
            canvas.create_text(right + 4, (y + end) / 2, text=f"{length:g}\n{self._hoop_text(hoop)}", anchor="w",
                               fill="#3d4c5a", font=("Yu Gothic UI", 8), tags=("zone",))
            y = end
        canvas.create_line(left, head, right, head, fill="#334155", width=2, tags=("head",))
        for x in (left + 14, right - 14):
            canvas.create_line(x, head, x, y if y > head else head + 20, fill=BAR, width=3, tags=("bars",))
        cut = pile["cutoff"]
        length = _number(cut["cutoff_length_mm"])
        if cut["main_bars"]["diameter_mm"] is not None and cut["main_bars"]["count"] is not None and length:
            at = head + length * scale
            canvas.create_line(left - 20, at, right + 20, at, fill="#c62828", dash=(5, 3), width=2, tags=("cutoff",))
            canvas.create_text(left - 22, at, text=f"段落し {length:g}", anchor="e", fill="#c62828",
                               font=("Yu Gothic UI", 8), tags=("cutoff",))
            notes.append(CUTOFF_NOTE)

    @staticmethod
    def _hoop_text(hoop: dict) -> str:
        size, sets, pitch = (_number(hoop[key]) for key in ("diameter_mm", "sets", "pitch_mm"))
        if size is None or pitch is None:
            return "未入力"
        return f"D{size:g}@{pitch:g}" + ("" if sets in (None, 1) else f"×{sets:g}組")

    def _section(self, pile: dict, diameter: float, notes: list[str]) -> None:
        canvas = self.section
        cut = self.view == "cutoff"
        bars = pile["cutoff"]["main_bars"] if cut else pile["main_bars"]
        hoop = pile["cutoff"]["hoops"] if cut else pile["hoops"]["zone_2d"]
        cover = _number(pile["pure_cover_mm"])
        size, count = _number(bars["diameter_mm"]), _number(bars["count"])
        hoop_size = _number(hoop["diameter_mm"])
        scale = (SECTION_SIZE - 2 * MARGIN) / diameter
        cx = cy = SECTION_SIZE / 2
        radius = diameter / 2 * scale
        canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill="#eef3f7", outline=OUTLINE, width=1.5,
                           tags=("outline",))
        canvas.create_text(cx, SECTION_SIZE - 8, text=f"φ{diameter:g} mm", fill=OUTLINE, font=("Yu Gothic UI", 9),
                           tags=("size",))
        missing = [name for name, value in (("純かぶり", cover), ("主鉄筋の径", size), ("主鉄筋の本数", count),
                                            ("帯鉄筋の径", hoop_size)) if value is None]
        if missing:
            where = "段落し後" if cut else "杭頭"
            notes.append(f"{where}の断面に必要な値が空欄です：{'、'.join(missing)}")
            return
        count = int(count)
        core, ring, hoop_radius = bar_ring(diameter, cover, hoop_size, size)
        if ring <= 0 or count <= 0:
            notes.append("かぶりが杭径に対して大きすぎます")
            return
        canvas.create_oval(cx - hoop_radius * scale, cy - hoop_radius * scale, cx + hoop_radius * scale,
                           cy + hoop_radius * scale, fill="", outline=HOOP, width=max(1.5, hoop_size * scale),
                           tags=("hoop",))
        half = max(2.5, size * scale / 2)
        for index in range(count):
            angle = 2 * math.pi * index / count - math.pi / 2
            x, y = cx + ring * scale * math.cos(angle), cy + ring * scale * math.sin(angle)
            canvas.create_oval(x - half, y - half, x + half, y + half, fill=BAR, outline="white", tags=("rebar",))
        gap = spacing(ring, count)
        rows = [f"主鉄筋 {count}-D{size:g}　帯鉄筋 D{hoop_size:g}", f"芯かぶり {core:.1f} mm", f"芯間隔 {gap:.1f} mm"]
        if gap - size < 0:
            notes.append("主鉄筋が重なっています")
        self._list(rows)

    def _list(self, rows: list[str]) -> None:
        for child in self.row_frame.winfo_children():
            child.destroy()
        self.rows = rows
        for text in rows:
            ttk.Label(self.row_frame, text=text).pack(anchor="w")
