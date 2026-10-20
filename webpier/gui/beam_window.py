"""The modeless window of the beam's 配筋略図 at the column face (decision 68; the approved mockup, Beam).

It stays open beside the 鉄筋 page and is redrawn after every edit. The section b × h shows the bars of
calc.beam_rebar coloured by their group (上面, 下面, 側面筋), the overlapping ones red, with a ring on the picked bar;
the stirrup is drawn touching the outermost bars of each face, its effective legs inside it dashed and equally spaced.
The stirrup is a picture only: its position is not used by any calculation.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from ..calc.beam_rebar import SIDE, BeamBar, BeamLayout
from ..inputs import choices
from . import rebar_edit
from .cards import NO_VALUE
from .document import EditorError
from .rebar_canvas import Circle, Point, SectionView

if TYPE_CHECKING:
    from .app import InputEditor

UPPER, LOWER = choices.BEAM_FACES
COLORS = {UPPER: "#1d5fa7", LOWER: "#d27a22", SIDE: "#2e7d4f"}
OVERLAP, PICKED = "#c62828", "#f2b705"


def stirrup(layout: BeamLayout, beam: Any) -> tuple[list[Point], list[tuple[Point, Point]]]:
    """The stirrup's centre line (a rectangle touching the upper and lower faces' layer 1 and the side bars inside it,
    else the upper face's outermost bars) and its effective legs inside it (more than two: equally spaced between its
    sides), mm. Nothing when its size is blank or it would not lie inside the section. *beam*: the JSON of 鉄筋.梁."""
    size, legs = beam["stirrups"]["diameter_mm"], beam["stirrups"]["effective_legs"]
    if not isinstance(size, (int, float)):
        return [], []
    half = size / 2
    upper, lower = layout.faces[UPPER].diameter.value, layout.faces[LOWER].diameter.value
    top = layout.centers[UPPER][0].value - upper / 2 - half
    bottom = layout.centers[LOWER][0].value - lower / 2 - half
    side = beam["side_bars"]
    if layout.side is not None and side["stirrup_position"] == choices.STIRRUP_POSITIONS[0]:
        edge = layout.side_center.value - layout.side.diameter.value / 2 - half
    else:
        edge = layout.bars[0].x.value - upper / 2 - half
    if min(top, bottom, edge) <= 0:
        return [], []
    width, depth = layout.width.value, layout.depth.value
    rectangle = [(edge, top), (width - edge, top), (width - edge, depth - bottom), (edge, depth - bottom)]
    count = legs if isinstance(legs, int) and legs > 2 else 2
    xs = [edge + (width - 2 * edge) * j / (count - 1) for j in range(1, count - 1)]
    return rectangle, [((x, top), (x, depth - bottom)) for x in xs]


def bar_name(bar: BeamBar) -> str:
    return "側面筋" if bar.group == SIDE else f"{bar.group}面{bar.layer}段目"


class BeamWindow:
    member = "梁"

    def __init__(self, editor: InputEditor, on_close: Callable[[], None]) -> None:
        self.editor, self.on_close = editor, on_close
        self.picked: int | None = None
        root = editor.root
        window = self.window = tk.Toplevel(root)
        window.title("配筋略図 — 梁（柱前面）")
        window.transient(root)
        window.geometry(f"640x620+{root.winfo_rootx() + max(0, root.winfo_width() - 660)}+{root.winfo_rooty() + 120}")
        window.protocol("WM_DELETE_WINDOW", self.close)
        body = ttk.Frame(window, padding=10)
        body.pack(fill="both", expand=True)
        self.footer = tk.StringVar(master=window)
        ttk.Label(body, textvariable=self.footer).pack(side="bottom", anchor="w", pady=(6, 0))
        self.section = SectionView(body, on_bar=self.pick)
        self.section.pack(fill="both", expand=True)
        self.refresh()

    def pick(self, index: int) -> None:
        self.picked = index
        self.refresh()

    def close(self) -> None:
        self.window.destroy()
        self.on_close()

    def refresh(self) -> None:
        if not self.window.winfo_exists():
            return
        data = self.editor.document.data
        try:
            layout = rebar_edit.beam_preview(data)
        except EditorError as exc:
            self.section.show([], notice=str(exc))
            self.footer.set("")
            return
        beam = data["鉄筋"]["梁"]
        overlapping = {index for pair in layout.overlaps for index in pair}
        circles = [Circle(bar.x.value, bar.y.value, bar.diameter.value,
                          fill=OVERLAP if index in overlapping else COLORS[bar.group],
                          ring=PICKED if index == self.picked else None) for index, bar in enumerate(layout.bars)]
        width, depth = layout.width.value, layout.depth.value
        hoop, legs = stirrup(layout, beam)
        count = beam["stirrups"]["effective_legs"]
        self.section.show([(0, 0), (width, 0), (width, depth), (0, depth)], circles, hoop, lines=legs,
                          notice="青：上面の主鉄筋　橙：下面の主鉄筋　緑：側面筋　"
                                 f"灰：スターラップ（効く脚 {NO_VALUE if count is None else count} 本）　赤：重なり")
        footer = f"物理本数 {len(layout.bars)} 本"
        if layout.overlaps:
            footer += f"・重なり {len(layout.overlaps)} か所"
        if self.picked is not None and self.picked < len(layout.bars):
            bar = layout.bars[self.picked]
            footer += (f"　{bar_name(bar)} D{bar.diameter.value:g}・上面から {bar.y.value:.1f}・"
                       f"左面から {bar.x.value:.1f}")
        self.footer.set(footer)
