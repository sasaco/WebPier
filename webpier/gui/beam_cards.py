"""The beam's cards on the 鉄筋 page (decision 68; the approved mockup, Beam).

A strip with the beam's steels, concrete and pure cover, then a card per face: layer 1 (size, count, the upper face's
shape, 芯かぶり 自動 or 指定) and, on the upper face only, the layers inside it (count and the clear gap to the layer
outside; the lower face's layers inside stay in the data but are not shown, the owner's decision), then the side bars
(or none) and the stirrups. Every value is a card input bound to the field table (gui.cards); the centres shown come
from calc.beam_rebar through the page's layout, nothing is computed here.
"""

from __future__ import annotations

from tkinter import ttk
from typing import TYPE_CHECKING

from ..calc.beam_rebar import SIDE
from ..inputs import choices
from . import cards

if TYPE_CHECKING:
    from .rebar_page import RebarPage

BEAM = ("鉄筋", "梁")
MAIN_SIZES = cards.SIZES[2:]  # D16 … D51
HOOP_SIZES = (13, 16, 19, 22, 25)
NO_VALUE = cards.NO_VALUE
UPPER = choices.BEAM_FACES[0]


def _beam(page: RebarPage) -> dict:
    return page.editor.document.data["鉄筋"]["梁"]


def common(page: RebarPage) -> None:
    form = page.form
    card = cards.card(page.inputs, "材料とかぶり")
    line = cards.line(card)
    cards.segment(form, line, (*BEAM, "materials", "main"), "主鉄筋の材質")
    cards.segment(form, line, (*BEAM, "materials", "transverse"), "スターラップの材質")
    line = cards.line(card)
    cards.entry(form, line, (*BEAM, "concrete_strength_mpa"), "コンクリート強度")
    cards.entry(form, line, (*BEAM, "aggregate_max_mm"), "粗骨材の最大寸法")
    cards.entry(form, line, (*BEAM, "pure_cover_mm"), "純かぶり")
    cards.help_button(line, "純かぶりと芯かぶり", lambda: ["純かぶり：コンクリート面から最も外側の鉄筋の外面まで。",
                                                       "芯かぶり（自動）＝ 純かぶり ＋ スターラップの径 ＋ 主鉄筋の径／2"])


def _beside(row: ttk.Frame) -> ttk.Frame:
    """A place for a card beside the others of *row*."""
    holder = ttk.Frame(row)
    holder.pack(side="left", fill="both", expand=True, padx=(0, 8))
    return holder


def main(page: RebarPage) -> None:
    common(page)
    faces, others = ttk.Frame(page.inputs), ttk.Frame(page.inputs)
    faces.pack(fill="x")
    others.pack(fill="x")
    for face in choices.BEAM_FACES:
        _face(page, _beside(faces), face)
    _side(page, _beside(others))
    _stirrups(page, _beside(others))


def _cover(page: RebarPage, line: ttk.Frame, path: tuple, mode: str | None, key: tuple[str, int]) -> None:
    """芯かぶり 自動 or 指定, and the given centre or the calculated one."""
    cards.segment(page.form, line, (*path, "cover_mode"), "芯かぶり", selected=page.rebuild_later)
    if mode == choices.COVER_SPECIFIED:
        cards.entry(page.form, line, (*path, "center_mm"), "芯かぶり（指定）")
    else:
        cards.readout_label(line, page.readouts, key)


def _face(page: RebarPage, parent: ttk.Frame, face: str) -> None:
    form = page.form
    path = (*BEAM, "faces", face)
    bars = _beam(page)["faces"][face]
    card = cards.card(parent, f"{face}面の主鉄筋")
    ttk.Label(card, text="1段目", style="Symbol.TLabel").pack(anchor="w")
    line = cards.line(card)
    cards.size(form, line, (*path, "diameter_mm"), "径", sizes=MAIN_SIZES)
    cards.entry(form, line, (*path, "count"), "本数", width=6)
    if face == UPPER:
        cards.segment(form, line, (*path, "bar_type"), "形状")
    line = cards.line(card)
    _cover(page, line, path, bars["cover_mode"], (face, 1))
    cards.help_button(line, "芯かぶり（自動）", lambda: cover_lines(page, face))
    if face != UPPER:  # the lower face's layers inside are kept in the data, not shown (the owner's decision)
        return
    for index in range(len(bars["inner_layers"])):
        _inner(page, card, path, face, index)
    ttk.Button(card, text=f"＋ {len(bars['inner_layers']) + 2}段目を追加",
               command=lambda: page.add_row((*path, "inner_layers"))).pack(anchor="w", pady=(6, 0))


def _inner(page: RebarPage, card: ttk.Frame, path: tuple, face: str, index: int) -> None:
    form = page.form
    layer = (*path, "inner_layers", index)
    line = cards.line(card)
    ttk.Label(line, text=f"{index + 2}段目", style="Symbol.TLabel").pack(side="left", padx=(0, 10), pady=(18, 4))
    cards.entry(form, line, (*layer, "count"), "本数", width=6)
    cards.entry(form, line, (*layer, "clear_gap_mm"), f"{index + 1}段目とのあき")
    cards.readout_label(line, page.readouts, (face, index + 2))
    cards.remove_button(line, lambda: page.remove_layers((*path, "inner_layers"), index))


SIDE_NOTE = ("開始位置は上面から1本目の芯まで。2本目からはピッチで下へ並べます。",
             "芯かぶり（自動）＝ 純かぶり ＋（スターラップの内側なら）スターラップの径 ＋ 側面筋の径／2")


def _side(page: RebarPage, parent: ttk.Frame) -> None:
    form = page.form
    path = (*BEAM, "side_bars")
    side = _beam(page)["side_bars"]
    card = cards.card(parent, "側面筋")
    head = cards.line(card)
    ttk.Button(head, text="側面筋なしにする" if side is not None else "側面筋を入れる",
               command=lambda: page.set_side_bars(side is None)).pack(side="left", padx=(0, 10), pady=(18, 4))
    cards.help_button(head, "側面筋", lambda: list(SIDE_NOTE))
    if side is None:
        return
    line = cards.line(card)
    cards.size(form, line, (*path, "diameter_mm"), "径", sizes=MAIN_SIZES)
    cards.entry(form, line, (*path, "per_face_count"), "本数（1つの面）", width=6)
    cards.entry(form, line, (*path, "start_mm"), "開始位置（上面から）")
    cards.entry(form, line, (*path, "pitch_mm"), "ピッチ")
    line = cards.line(card)
    cards.segment(form, line, (*path, "stirrup_position"), "スターラップの")
    _cover(page, line, path, side["cover_mode"], (SIDE, 1))


def _stirrups(page: RebarPage, parent: ttk.Frame) -> None:
    form = page.form
    path = (*BEAM, "stirrups")
    card = cards.card(parent, "スターラップ")
    line = cards.line(card)
    cards.size(form, line, (*path, "diameter_mm"), "径", sizes=HOOP_SIZES)
    cards.entry(form, line, (*path, "effective_legs"), "効く脚の本数", width=6)
    cards.entry(form, line, (*path, "pitch_mm"), "間隔")
    cards.help_button(line, "効く脚", lambda: ["せん断力の向き（鉛直）に沿う脚を数えます。位置は計算に使いません。"])


def readout(page: RebarPage, key: tuple[str, int]) -> str:
    """The centre of a layer from its face, and whether the layer is placed symmetrically (an odd rest of layer 1's
    positions); for the side bars, their centre from the side faces."""
    layout, (group, layer) = page.layout, key
    if layout is None:
        return NO_VALUE
    if group == SIDE:
        return NO_VALUE if layout.side_center is None else f"{layout.side_center.value:.1f}"
    centers = layout.centers[group]
    if layer > len(centers):
        return NO_VALUE
    count = sum(1 for bar in layout.bars if (bar.group, bar.layer) == key)
    odd = layer > 1 and (layout.faces[group].per_layer - count) % 2
    return f"{centers[layer - 1].value:.1f}" + ("（左右対称になりません）" if odd else "")


def cover_lines(page: RebarPage, face: str) -> list[str]:
    beam = _beam(page)
    diameter = beam["faces"][face]["diameter_mm"]
    parts = (("純かぶり", beam["pure_cover_mm"]), ("＋ スターラップの径", beam["stirrups"]["diameter_mm"]),
             ("＋ 主鉄筋の径／2", None if diameter is None else diameter / 2))
    return [*(f"{name}　{NO_VALUE if value is None else f'{value:g}'}" for name, value in parts),
            f"芯かぶり　{readout(page, (face, 1))}"]
