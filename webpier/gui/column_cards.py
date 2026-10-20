"""The column's cards on the 鉄筋 page (decision 68; the approved mockup, Main).

A strip with the column's steels, concrete and covers, then one card per direction: layer 1 (size, 片面本数, 芯かぶり
自動 or 指定, the distribution with only the values it uses) and the layers inside it (片面本数 and the clear gap to the
layer outside). Every value is a card input bound to the field table (gui.cards); the centres and spacings shown come
from calc.column_rebar through the page's layout, nothing is computed here.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING

from ..inputs import choices
from . import cards

if TYPE_CHECKING:
    from .rebar_page import RebarPage

COLUMN = ("鉄筋", "柱")
MAIN_SIZES = cards.SIZES[2:]  # D16 … D51
HOOP_SIZES = (13, 16, 19, 22, 25)
FACES = {"線路": "上面・下面", "直角": "左面・右面"}
ENDPOINTS = {"含む": "置く", "含めない": "置かない"}
NO_VALUE = "—"


def _help(parent: tk.Misc, title: str, lines: Callable[[], list[str]]) -> cards.Help:
    """(?) after the inputs of *parent*; *lines* gives the text for the values at the time it opens."""
    def build(body: tk.Misc) -> None:
        for text in lines():
            ttk.Label(body, text=text, wraplength=360, justify="left").pack(anchor="w")
    help_ = cards.Help(parent, title, build)
    help_.button.pack(side="left", padx=(0, 10), pady=(18, 4))
    return help_


def _remove_button(parent: tk.Misc, command: Callable[[], object]) -> tk.Button:
    """×: removes the item of its line."""
    button = tk.Button(parent, text="×", width=2, padx=0, pady=0, relief="groove", borderwidth=1,
                       font=("Yu Gothic UI", 8), fg="#8e1d1d", cursor="hand2", command=command)
    button.pack(side="left", pady=(18, 4))
    return button


def _readout(page: RebarPage, parent: tk.Misc, key: tuple[str, int]) -> None:
    """The centre of the layer *key* from the layout, set by the page's refresh."""
    frame = cards.labelled(parent, "芯かぶり mm")
    variable = page.readouts.setdefault(key, tk.StringVar(master=parent, value=NO_VALUE))
    ttk.Label(frame, textvariable=variable, style="Symbol.TLabel").pack(anchor="w")


def common(page: RebarPage) -> None:
    form = page.form
    card = cards.card(page.inputs, "材料とかぶり")
    line = cards.line(card)
    cards.segment(form, line, (*COLUMN, "materials", "main"), "主鉄筋の材質")
    cards.segment(form, line, (*COLUMN, "materials", "transverse"), "帯鉄筋の材質")
    line = cards.line(card)
    cards.entry(form, line, (*COLUMN, "concrete_strength_mpa"), "コンクリート強度")
    cards.entry(form, line, (*COLUMN, "aggregate_max_mm"), "粗骨材の最大寸法")
    cards.entry(form, line, (*COLUMN, "pure_cover_mm"), "純かぶり")
    _help(line, "純かぶりと芯かぶり", lambda: ["純かぶり：コンクリート面から外側の帯鉄筋の外面まで。",
                                              "芯かぶり（自動）＝ 純かぶり ＋ 外側の帯鉄筋の径 ＋ 主鉄筋の径／2"])
    cards.size(form, line, (*COLUMN, "column_hoops", "enclosing_diameter_mm"), "外側の帯鉄筋の径", sizes=HOOP_SIZES)


def main(page: RebarPage) -> None:
    common(page)
    row = ttk.Frame(page.inputs)
    row.pack(fill="x")
    for direction in choices.REBAR_DIRECTIONS:
        holder = ttk.Frame(row)
        holder.pack(side="left", fill="both", expand=True, padx=(0, 8))
        _direction(page, holder, direction)


LEG_NOTE = "力の向きに沿う脚を数えます。位置は計算に使いません。"


def hoops(page: RebarPage) -> None:
    """The hoops: per direction, the ranges of the column (from its base) with their size, effective legs and pitch."""
    common(page)
    outer = cards.card(page.inputs, "せん断に効く帯鉄筋")
    row = ttk.Frame(outer)
    row.pack(fill="x")
    rows = page.editor.document.data["鉄筋"]["柱"]["column_hoops"]["direction_rows"]
    for direction in choices.REBAR_DIRECTIONS:
        holder = ttk.Frame(row)
        holder.pack(side="left", fill="both", expand=True, padx=(0, 8))
        card = cards.card(holder, f"{direction}方向")
        line = cards.line(card)
        ttk.Label(line, text="効く脚の本数は、力の向きに沿う脚の数です。", style="Muted.TLabel").pack(side="left",
                                                                                     pady=(18, 4))
        _help(line, "効く脚", lambda: [LEG_NOTE])
        for index, hoop in enumerate(rows):
            if hoop["direction"] == direction:
                _hoop(page, card, index)
        ttk.Button(card, text="＋ 範囲を追加", command=lambda direction=direction: page.add_hoop(direction)).pack(
            anchor="w", pady=(6, 0))


def _hoop(page: RebarPage, card: tk.Misc, index: int) -> None:
    form = page.form
    path = (*COLUMN, "column_hoops", "direction_rows", index)
    line = cards.line(card)
    cards.size(form, line, (*path, "diameter_mm"), "径", sizes=HOOP_SIZES)
    cards.entry(form, line, (*path, "effective_legs"), "効く脚の本数", width=6)
    cards.entry(form, line, (*path, "pitch_mm"), "間隔")
    cards.entry(form, line, (*path, "start_mm"), "開始（柱の下端から）")
    cards.entry(form, line, (*path, "end_mm"), "終了")
    _remove_button(line, lambda: page.remove_row((*COLUMN, "column_hoops", "direction_rows"), index))


def _direction(page: RebarPage, parent: tk.Misc, direction: str) -> None:
    form = page.form
    path = (*COLUMN, "main_bars", direction)
    bars = page.editor.document.data["鉄筋"]["柱"]["main_bars"][direction]
    card = cards.card(parent, f"{direction}方向の段（{FACES[direction]}）")
    ttk.Label(card, text="1段目", style="Symbol.TLabel").pack(anchor="w")
    line = cards.line(card)
    cards.size(form, line, (*path, "diameter_mm"), "径", sizes=MAIN_SIZES)
    cards.entry(form, line, (*path, "per_face_count"), "本数（1つの面）", width=6)
    line = cards.line(card)
    cards.segment(form, line, (*path, "cover_mode"), "芯かぶり", selected=page.rebuild_later)
    if bars["cover_mode"] == choices.COVER_SPECIFIED:
        cards.entry(form, line, (*path, "center_mm"), "芯かぶり（指定）")
    else:
        _readout(page, line, (direction, 1))
    _help(line, "芯かぶり（自動）", lambda: cover_lines(page, direction))
    line = cards.line(card)
    cards.segment(form, line, (*path, "distribution", "mode"), "並べ方", selected=page.rebuild_later)
    mode = bars["distribution"]["mode"]
    if mode != choices.CENTRE_PITCH:
        cards.entry(form, line, (*path, "distribution", "edge_center_mm"), "端の芯距離 e")
    if mode != choices.EQUAL:
        cards.entry(form, line, (*path, "distribution", "pitch_mm"), "ピッチ p")
    if mode == choices.EQUAL:
        cards.segment(form, line, (*path, "endpoints"), "e の位置に鉄筋", labels=ENDPOINTS)
    _help(line, "並べ方", lambda: ["等分：e と反対側の e の間を等間隔", "中央ピッチ：p で並べて面の中央にそろえる",
                                   "両端＋中央ピッチ：e に1本ずつ、残りを p で中央に", spacing_line(page, direction)])
    for index in range(len(bars["inner_layers"])):
        _inner(page, card, path, direction, index)
    ttk.Button(card, text=f"＋ {len(bars['inner_layers']) + 2}段目を追加",
               command=lambda: page.add_row((*path, "inner_layers"))).pack(anchor="w", pady=(6, 0))


def _inner(page: RebarPage, card: tk.Misc, path: tuple, direction: str, index: int) -> None:
    form = page.form
    layer = (*path, "inner_layers", index)
    line = cards.line(card)
    ttk.Label(line, text=f"{index + 2}段目", style="Symbol.TLabel").pack(side="left", padx=(0, 10), pady=(18, 4))
    cards.entry(form, line, (*layer, "per_face_count"), "本数（1つの面）", width=6)
    cards.entry(form, line, (*layer, "clear_gap_mm"), f"{index + 1}段目とのあき")
    _readout(page, line, (direction, index + 2))
    _remove_button(line, lambda: page.remove_layers((*path, "inner_layers"), index))


def _row(page: RebarPage, key: tuple[str, int]):
    layout = page.layout
    return None if layout is None else next((row for row in layout.rows if row.key == key), None)


def readout(page: RebarPage, key: tuple[str, int]) -> str:
    """The centre of a layer, and whether the layer is placed symmetrically (an odd rest of layer 1's positions)."""
    row, first = _row(page, key), _row(page, (key[0], 1))
    if row is None:
        return NO_VALUE
    odd = first is not None and key[1] > 1 and (len(first.positions) - len(row.positions)) % 2
    return f"{row.center.value:.1f}" + ("（左右対称になりません）" if odd else "")


def cover_lines(page: RebarPage, direction: str) -> list[str]:
    column = page.editor.document.data["鉄筋"]["柱"]
    diameter = column["main_bars"][direction]["diameter_mm"]
    parts = (("純かぶり", column["pure_cover_mm"]),
             ("＋ 外側の帯鉄筋の径", column["column_hoops"]["enclosing_diameter_mm"]),
             ("＋ 主鉄筋の径／2", None if diameter is None else diameter / 2))
    return [*(f"{name}　{NO_VALUE if value is None else f'{value:g}'}" for name, value in parts),
            f"芯かぶり　{readout(page, (direction, 1))}"]


def spacing_line(page: RebarPage, direction: str) -> str:
    row = _row(page, (direction, 1))
    if row is None or len(row.positions) < 2:
        return ""
    a, b = (position.value for position in row.positions[:2])
    mode = page.editor.document.data["鉄筋"]["柱"]["main_bars"][direction]["distribution"]["mode"]
    if mode == choices.CENTRE_PITCH:
        return f"面の端から最初の鉄筋まで {a:.1f} mm"
    if mode == choices.EDGE_AND_PITCH:
        return f"端の鉄筋と隣の鉄筋の芯間隔 {b - a:.1f} mm"
    return f"芯間隔 {b - a:.1f} mm"
