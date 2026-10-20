"""The modeless window of the footing's 配筋略図 (decision 68; the approved mockup, Footing).

It stays open beside the 鉄筋 page and is redrawn after every edit. The section along the chosen direction shows the
outline with the column on it, the layers of both faces in their order from each face (7 px apart: the covers and the
spacings are enlarged) and the stirrups of that direction: a layer of the direction seen is a line, one of the other
direction a row of dots at its pitch, centred; crossing layers are red. Below it, the left end of the chosen face at
true scale (0.4 px/mm, 640 × 400 mm) with the list of its layers. The layers come from calc.footing_rebar through
rebar_edit.footing_preview; the dots, the stirrups and the zoom are a picture only, used by no calculation.
"""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from ..calc.footing_rebar import FaceLayout
from ..inputs import choices
from . import rebar_edit
from .document import EditorError
from .rebar_canvas import dimension_mm, outline

if TYPE_CHECKING:
    from .app import InputEditor

UPPER, LOWER = choices.BEAM_FACES
VIEWS = tuple((direction, f"{direction}方向の断面") for direction in choices.REBAR_DIRECTIONS)
ZOOMS = ((UPPER, "上面"), (LOWER, "下面"))
COLORS = {"線路": "#1d5fa7", "直角": "#d27a22"}
CROSSING, STIRRUP = "#c62828", "#8a99a8"
COLUMN_WIDTH = {"線路": ("側面", "B6"), "直角": ("正面", "W6")}
LEGEND = "青：線路方向の主鉄筋　橙：直角方向の主鉄筋　灰：スターラップ　赤：交差"
ENLARGED = "略図：かぶりと段の間隔は拡大して描いています"
SECTION_HEIGHT, COLUMN_PX, MARGIN = 260, 30, 20
DOTS, STIRRUPS, STIRRUP_EDGE = 150, 120, 200  # the most dots and stirrups drawn; the stirrups keep 200 mm off the ends
ZOOM_SCALE, ZOOM_WIDTH, ZOOM_DEPTH, ZOOM_X, ZOOM_Y = 0.4, 640, 400, 44, 4  # px/mm, mm, mm, px, px


def centred(length: float, pitch: float, span: float, cap: int) -> list[float]:
    """The positions at *pitch* that fit in *span*, centred on *length* (x = L/2 + (j − (n − 1)/2)·p), at most *cap*."""
    count = min(cap, math.floor(span / pitch) + 1) if pitch > 0 and span >= 0 else 0
    return [length / 2 + (j - (count - 1) / 2) * pitch for j in range(count)]


def _number(value: Any) -> float | None:
    return value if isinstance(value, (int, float)) else None


class FootingWindow:
    member = "フーチング"

    def __init__(self, editor: InputEditor, on_close: Callable[[], None]) -> None:
        self.editor, self.on_close = editor, on_close
        self.view: str = editor.rebar_state.get("footing_view", choices.REBAR_DIRECTIONS[0])
        self.zoom: str = editor.rebar_state.get("footing_zoom", LOWER)
        self.scale = 0.0  # px/mm of the section, set when drawn
        self.rows: list[str] = []  # the list of the zoomed face's layers
        root = editor.root
        window = self.window = tk.Toplevel(root)
        window.title("配筋略図 — フーチング")
        window.transient(root)
        window.geometry(f"700x660+{root.winfo_rootx() + max(0, root.winfo_width() - 720)}+{root.winfo_rooty() + 120}")
        window.protocol("WM_DELETE_WINDOW", self.close)
        body = ttk.Frame(window, padding=10)
        body.pack(fill="both", expand=True)
        bar = ttk.Frame(body)
        bar.pack(fill="x")
        self.view_choice = tk.StringVar(master=window, value=self.view)
        for value, label in VIEWS:
            tk.Radiobutton(bar, text=label, value=value, variable=self.view_choice, indicatoron=False, padx=10, pady=2,
                           selectcolor="#cfe0f2", command=lambda: self.select(self.view_choice.get())).pack(side="left")
        self.section = tk.Canvas(body, height=SECTION_HEIGHT, background="#f8fafc", highlightthickness=1,
                                 highlightbackground="#dbe3ed")
        self.section.pack(fill="x", pady=(6, 4))
        self.section.bind("<Configure>", lambda event: self.refresh())
        ttk.Label(body, text=f"{LEGEND}　{ENLARGED}", style="Muted.TLabel").pack(anchor="w")
        head = ttk.Frame(body)
        head.pack(fill="x", pady=(10, 4))
        ttk.Label(head, text="左端の拡大（実際の縮尺）", style="Symbol.TLabel").pack(side="left", padx=(0, 10))
        self.zoom_choice = tk.StringVar(master=window, value=self.zoom)
        for value, label in ZOOMS:
            tk.Radiobutton(head, text=label, value=value, variable=self.zoom_choice, indicatoron=False, padx=10,
                           pady=2, selectcolor="#cfe0f2",
                           command=lambda: self.select_zoom(self.zoom_choice.get())).pack(side="left")
        zoom = ttk.Frame(body)
        zoom.pack(fill="x")
        self.zoom_canvas = tk.Canvas(zoom, width=ZOOM_X + ZOOM_WIDTH * ZOOM_SCALE + 8,
                                     height=ZOOM_Y * 2 + ZOOM_DEPTH * ZOOM_SCALE, background="#ffffff",
                                     highlightthickness=1, highlightbackground="#dbe3ed")
        self.zoom_canvas.pack(side="left")
        self.row_frame = ttk.Frame(zoom, padding=(12, 0, 0, 0))
        self.row_frame.pack(side="left", fill="both", expand=True)
        self.notice = tk.StringVar(master=window)
        ttk.Label(body, textvariable=self.notice, foreground="#8e1d1d", wraplength=660, justify="left").pack(
            anchor="w", pady=(8, 0))
        self.refresh()

    def select(self, view: str) -> None:
        self.view = self.editor.rebar_state["footing_view"] = view
        self.view_choice.set(view)
        self.refresh()

    def select_zoom(self, face: str) -> None:
        self.zoom = self.editor.rebar_state["footing_zoom"] = face
        self.zoom_choice.set(face)
        self.refresh()

    def close(self) -> None:
        self.window.destroy()
        self.on_close()

    # drawing --------------------------------------------------------------------------------------------------

    def _clear(self, notice: str) -> None:
        self.section.delete("all")
        self.zoom_canvas.delete("all")
        self._list([])
        self.notice.set(notice)

    def refresh(self) -> None:
        if not self.window.winfo_exists():
            return
        data = self.editor.document.data
        group, key = COLUMN_WIDTH[self.view]
        try:
            preview = rebar_edit.footing_preview(data)
            polygon = outline("フーチング", data, self.view)
            column = dimension_mm(data, group, key)
        except EditorError as exc:
            self._clear(str(exc))
            return
        footing = data["鉄筋"]["フーチング"]
        pure = _number(footing["pure_cover_mm"]) or 0
        pitch = _number(footing["stirrups"][self.view]["pitch_mm"])
        self._section(polygon, column, preview.faces, pure, pitch)
        self._zoom(preview.faces[self.zoom], pure)
        self.notice.set("\n".join(f"{face}面：{problem}" for face, problem in preview.problems.items()))

    def _color(self, layout: FaceLayout, index: int) -> str:
        crossing = any(index in pair for pair in layout.crossings)
        return CROSSING if crossing else COLORS[layout.layers[index].direction]

    def _section(self, polygon: list, column: float, faces: dict[str, FaceLayout | None], pure: float,
                 pitch: float | None) -> None:
        canvas = self.section
        canvas.delete("all")
        width = max(canvas.winfo_width(), 600)
        xs, ys = [x for x, _ in polygon], [y for _, y in polygon]
        length, depth = max(xs), max(ys)
        scale = self.scale = min((width - 2 * MARGIN) / length,
                                 (SECTION_HEIGHT - COLUMN_PX - 2 * MARGIN - 24) / depth)
        ox, oy = (width - length * scale) / 2, MARGIN + COLUMN_PX
        top, bottom = oy, oy + depth * scale

        def at(x: float) -> float:
            return ox + x * scale

        canvas.create_polygon([v for x, y in polygon for v in (at(x), oy + y * scale)], fill="#eef3f7",
                              outline="#526981", width=1.5, tags=("outline",))
        flat = polygon[0][0], polygon[1][0]  # the top face between the tapers
        middle = (flat[0] + flat[1]) / 2
        canvas.create_rectangle(at(middle - column / 2), top - COLUMN_PX, at(middle + column / 2), top,
                                fill="#dfe6ee", outline="#526981", tags=("column",))
        if pitch is not None:
            for x in centred(length, pitch, length - 2 * STIRRUP_EDGE, STIRRUPS):
                canvas.create_line(at(x), top + 20, at(x), bottom - 20, fill=STIRRUP, tags=("stirrup",))
        for face, layout in faces.items():
            if layout is None:
                continue
            for index, layer in enumerate(layout.layers):
                offset = 9 + 7 * index
                y = top + offset if face == UPPER else bottom - offset
                color = self._color(layout, index)
                if layer.direction == self.view:
                    canvas.create_line(at(pure), y, at(length - pure), y, fill=color, width=3, tags=("band",))
                    continue
                for x in centred(length, layer.pitch.value, length - 2 * pure, DOTS):
                    canvas.create_oval(at(x) - 2.5, y - 2.5, at(x) + 2.5, y + 2.5, fill=color, outline="",
                                       tags=("dot",))
        canvas.create_text(ox - 4, top + 9, text="上面", anchor="e", fill="#4a5a69", font=("Yu Gothic UI", 8),
                           tags=("face",))
        canvas.create_text(ox - 4, bottom - 9, text="下面", anchor="e", fill="#4a5a69", font=("Yu Gothic UI", 8),
                           tags=("face",))
        edges = (0, flat[0], flat[1], length)
        for start, end in zip(edges, edges[1:]):
            canvas.create_line(at(start), bottom + 10, at(start), bottom + 18, fill="#5b6b7a", tags=("tick",))
            canvas.create_text(at((start + end) / 2), bottom + 14, text=f"{end - start:g}", fill="#3d4c5a",
                               font=("Yu Gothic UI", 8), tags=("dimension",))
        canvas.create_line(at(length), bottom + 10, at(length), bottom + 18, fill="#5b6b7a", tags=("tick",))

    def _zoom(self, layout: FaceLayout | None, pure: float) -> None:
        canvas = self.zoom_canvas
        canvas.delete("all")
        lower = self.zoom == LOWER
        face_y = ZOOM_Y + (ZOOM_DEPTH * ZOOM_SCALE if lower else 0)

        def y_of(cover: float) -> float:
            return face_y - cover * ZOOM_SCALE if lower else face_y + cover * ZOOM_SCALE

        def x_of(x: float) -> float:
            return ZOOM_X + x * ZOOM_SCALE

        canvas.create_rectangle(x_of(0), ZOOM_Y, x_of(ZOOM_WIDTH), ZOOM_Y + ZOOM_DEPTH * ZOOM_SCALE, fill="#f6f8fa",
                                outline="", tags=("concrete",))
        canvas.create_line(x_of(0), face_y, x_of(ZOOM_WIDTH), face_y, fill="#334155", width=2, tags=("face",))
        canvas.create_line(x_of(0), ZOOM_Y, x_of(0), ZOOM_Y + ZOOM_DEPTH * ZOOM_SCALE, fill="#334155", width=2,
                           tags=("face",))
        canvas.create_line(ZOOM_X - 10, face_y, ZOOM_X - 10, y_of(pure), fill="#5b6b7a", tags=("pure",))
        canvas.create_text(ZOOM_X - 14, (face_y + y_of(pure)) / 2, text=f"{pure:g}", anchor="e", fill="#3d4c5a",
                           font=("Yu Gothic UI", 8), tags=("pure",))
        if layout is None:
            self._list([])
            return
        rows = []
        for index, layer in enumerate(layout.layers):
            color = self._color(layout, index)
            size, center = layer.diameter.value, layer.center.value
            y, half = y_of(center), size * ZOOM_SCALE / 2
            if layer.direction == self.view:
                canvas.create_rectangle(x_of(pure), y - half, x_of(ZOOM_WIDTH), y + half, fill=color, outline="",
                                        tags=("zoom-band",))
            else:
                x = 150.0
                while x + size / 2 <= ZOOM_WIDTH:
                    canvas.create_oval(x_of(x) - half, y - half, x_of(x) + half, y + half, fill=color, outline="",
                                       tags=("zoom-dot",))
                    x += layer.pitch.value
            crossing = "（交差）" if color == CROSSING else ""
            rows.append((f"{layer.direction}方向 {layer.layer}段目　D{size:g} @{layer.pitch.value:g}　"
                         f"芯かぶり {center:.1f}{crossing}", color))
        self._list(rows)

    def _list(self, rows: list[tuple[str, str]]) -> None:
        for child in self.row_frame.winfo_children():
            child.destroy()
        self.rows = [text for text, _ in rows]
        for text, color in rows:
            ttk.Label(self.row_frame, text=text, foreground=color).pack(anchor="w")
