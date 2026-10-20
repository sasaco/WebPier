"""The footing's cards on the 鉄筋 page (decision 68; the approved mockup, Footing).

A strip with the footing's steels, concrete and pure cover, then a card per face (上面, 下面) with a small card per
direction: layer 1 (size, pitch, 芯かぶり 自動 or 指定) and the layers inside it (pitch and the clear gap to the layer
outside). Only the lower face shows which direction lies outside (outer_direction); the upper face's is kept in the
data but not shown. Then the stirrups of each direction (size, pitch along the overhang, and across the width a spacing
or the bars per 1 m). Every value is a card input bound to the field table (gui.cards); the centres, bars per 1 m,
crossings and stirrup widths shown come from calc.footing_rebar through the page's layout (rebar_edit.footing_preview),
nothing is computed here.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..inputs import choices
from . import cards

if TYPE_CHECKING:
    from .rebar_page import RebarPage

FOOTING = ("鉄筋", "フーチング")
MAIN_SIZES = cards.SIZES[1:9]  # D13 … D35
STIRRUP_SIZES = cards.SIZES[1:6]  # D13 … D25
NO_VALUE = cards.NO_VALUE
LOWER = choices.BEAM_FACES[1]
DIRECTIONS = {direction: f"{direction}方向" for direction in choices.REBAR_DIRECTIONS}
WIDTH_LABELS = {choices.WIDTH_DENSITY: "1 m 当たり本数"}
PER_METRE = "per_m"  # the readout keys of the bars per 1 m: (PER_METRE, face, direction, layer)
STIRRUP = "stirrup"  # (STIRRUP, direction)
CROSSING = "・ほかの段と交差"
COVER_NOTE = ["純かぶり：コンクリート面から最も外側の鉄筋の外面まで。",
              "芯かぶり（自動）：外側の方向 ＝ 純かぶり ＋ 径／2、内側の方向 ＝ 純かぶり ＋ 外側の方向の径 ＋ 径／2",
              "2段目以降 ＝ 同じ方向のひとつ前の段 ＋ 径 ＋ あき"]
STIRRUP_NOTE = ["間隔：張出しに沿う間隔です。", "幅方向：幅 1 m 当たりの本数を、間隔か本数で入力します（端数を許します）。"]


def _footing(page: RebarPage) -> dict:
    return page.editor.document.data["鉄筋"]["フーチング"]


def common(page: RebarPage) -> None:
    form = page.form
    card = cards.card(page.inputs, "材料とかぶり")
    line = cards.line(card)
    cards.segment(form, line, (*FOOTING, "materials", "main"), "主鉄筋の材質")
    cards.segment(form, line, (*FOOTING, "materials", "transverse"), "スターラップの材質")
    line = cards.line(card)
    cards.entry(form, line, (*FOOTING, "concrete_strength_mpa"), "コンクリート強度")
    cards.entry(form, line, (*FOOTING, "aggregate_max_mm"), "粗骨材の最大寸法")
    cards.entry(form, line, (*FOOTING, "pure_cover_mm"), "純かぶり")
    cards.help_button(line, "純かぶりと芯かぶり", lambda: list(COVER_NOTE))


def _beside(row: ttk.Frame) -> ttk.Frame:
    """A place for a card beside the others of *row*."""
    holder = ttk.Frame(row)
    holder.pack(side="left", fill="both", expand=True, padx=(0, 8))
    return holder


def main(page: RebarPage) -> None:
    common(page)
    for face in choices.BEAM_FACES:
        _face(page, face)
    _stirrups(page)


def _face(page: RebarPage, face: str) -> None:
    card = cards.card(page.inputs, f"{face}面の主鉄筋")
    if face == LOWER:  # the upper face's is kept in the data, not shown
        line = cards.line(card)
        cards.segment(page.form, line, (*FOOTING, "faces", face, "outer_direction"), f"{face}で外側になる方向",
                      labels=DIRECTIONS, selected=page.rebuild_later)
    row = ttk.Frame(card)
    row.pack(fill="x")
    outer = _footing(page)["faces"][face]["outer_direction"]
    for direction in choices.REBAR_DIRECTIONS:
        _direction(page, _beside(row), face, direction, outer)


def _direction(page: RebarPage, parent: tk.Misc, face: str, direction: str, outer: str | None) -> None:
    form = page.form
    path = (*FOOTING, "faces", face, direction)
    bars = _footing(page)["faces"][face][direction]
    position = "" if outer is None else "　1段目は外側" if outer == direction else "　1段目は内側"
    card = cards.card(parent, f"{direction}方向{position}")
    line = cards.line(card)
    cards.size(form, line, (*path, "diameter_mm"), "径", sizes=MAIN_SIZES)
    cards.entry(form, line, (*path, "pitch_mm"), "ピッチ")
    line = cards.line(card)
    cards.segment(form, line, (*path, "cover_mode"), "芯かぶり", selected=page.rebuild_later)
    if bars["cover_mode"] == choices.COVER_SPECIFIED:
        cards.entry(form, line, (*path, "center_mm"), "芯かぶり（指定）")
    else:
        cards.readout_label(line, page.readouts, (face, direction, 1))
    line = cards.line(card)
    cards.readout_label(line, page.readouts, (PER_METRE, face, direction, 1), "1 m 当たり本数")
    for index in range(len(bars["inner_layers"])):
        _inner(page, card, path, face, direction, index)
    ttk.Button(card, text=f"＋ {len(bars['inner_layers']) + 2}段目を追加",
               command=lambda: page.add_row((*path, "inner_layers"))).pack(anchor="w", pady=(6, 0))


def _inner(page: RebarPage, card: tk.Misc, path: tuple, face: str, direction: str, index: int) -> None:
    form = page.form
    layer = (*path, "inner_layers", index)
    line = cards.line(card)
    ttk.Label(line, text=f"{index + 2}段目", style="Symbol.TLabel").pack(side="left", padx=(0, 10), pady=(18, 4))
    cards.entry(form, line, (*layer, "pitch_mm"), "ピッチ")
    cards.entry(form, line, (*layer, "clear_gap_mm"), f"{index + 1}段目とのあき")
    cards.readout_label(line, page.readouts, (face, direction, index + 2), "")
    cards.remove_button(line, lambda: page.remove_layers((*path, "inner_layers"), index))


def _stirrups(page: RebarPage) -> None:
    form = page.form
    card = cards.card(page.inputs, "スターラップ")
    cards.help_button(cards.line(card), "スターラップ", lambda: list(STIRRUP_NOTE))
    row = ttk.Frame(card)
    row.pack(fill="x")
    for direction in choices.REBAR_DIRECTIONS:
        path = (*FOOTING, "stirrups", direction)
        mode = _footing(page)["stirrups"][direction]["distribution_mode"]
        inner = cards.card(_beside(row), f"{direction}方向")
        line = cards.line(inner)
        cards.size(form, line, (*path, "diameter_mm"), "径", sizes=STIRRUP_SIZES)
        cards.entry(form, line, (*path, "pitch_mm"), "間隔")
        line = cards.line(inner)
        cards.segment(form, line, (*path, "distribution_mode"), "幅方向", labels=WIDTH_LABELS,
                      selected=page.rebuild_later)
        if mode == choices.WIDTH_SPACING:
            cards.entry(form, line, (*path, "width_pitch_mm"), "幅方向の間隔")
        elif mode == choices.WIDTH_DENSITY:
            cards.entry(form, line, (*path, "density_per_m"), "幅方向の 1 m 当たり本数")
        if mode is not None:
            cards.readout_label(line, page.readouts, (STIRRUP, direction), "")


def readout(page: RebarPage, key: tuple) -> str:
    """A layer's centre from its face (1段目) or its centre and bars per 1 m (2段目 and inside), its bars per 1 m, or
    a direction's stirrups across the width; a layer crossing another is named."""
    preview = page.layout
    if preview is None:
        return NO_VALUE
    if key[0] == STIRRUP:
        width = preview.stirrups[key[1]]
        if width is None:
            return NO_VALUE
        legs, spacing = width
        if _footing(page)["stirrups"][key[1]]["distribution_mode"] == choices.WIDTH_SPACING:
            return f"1 m 当たり {legs.value:g} 本"
        return f"間隔 {spacing.value:.1f} mm 相当"
    per_metre = key[0] == PER_METRE
    face, direction, number = key[1:] if per_metre else key
    layout = preview.faces[face]
    if layout is None:
        return NO_VALUE
    index, layer = next(((i, layer) for i, layer in enumerate(layout.layers)
                         if (layer.direction, layer.layer) == (direction, number)), (None, None))
    if layer is None:
        return NO_VALUE
    crossing = CROSSING if any(index in pair for pair in layout.crossings) else ""
    if per_metre:
        return f"{layer.per_metre.value:g}{crossing}"
    if number == 1:
        return f"{layer.center.value:.1f}"
    return f"芯かぶり {layer.center.value:.1f}・1 m 当たり {layer.per_metre.value:g} 本{crossing}"
