"""The cast-in-place pile's cards on the 鉄筋 page (decisions 87 and 92; the approved mockup, 杭).

Three groups: 主鉄筋 (the main bars all along the pile), 帯鉄筋 (the hoops of the part inside the footing, of the 2D zone and
of up to three zones below it) and 段落し (the section after the cut-off of the bars, the lengths and the rules). Each starts
with the strip of the steels, concrete and cover: the f'ck is the 杭基礎's (one value, entered here or on that page), the
diameter of the pile is shown only. Every value is a card input bound to the field table (gui.cards); nothing is computed
here. The 配筋略図 and the pile body check's conditions are not here yet (decision 92).
"""

from __future__ import annotations

from tkinter import ttk
from typing import TYPE_CHECKING

from ..inputs.rebar import PILE_LOWER_HOOPS
from . import cards

if TYPE_CHECKING:
    from .rebar_page import RebarPage

PILE = ("鉄筋", "杭")
CAST = ("杭基礎", "場所打ち杭")
MAIN_SIZES = cards.SIZES[2:]  # D16 … D51
HOOP_SIZES = (13, 16, 19, 22, 25, 29, 32)
COVER_NOTE = ["純かぶり：コンクリート面から帯鉄筋の外面まで。",
              "芯かぶり（自動）＝ 純かぶり ＋ 帯鉄筋の径 ＋ 主鉄筋の径／2"]
SETS_NOTE = ["組：閉じた円形の帯鉄筋1本が1組です。1組は断面を2回横切るので、せん断補強鉄筋は組の2倍の脚で数えます。"]


def _pile(page: RebarPage) -> dict:
    return page.editor.document.data["鉄筋"]["杭"]


def common(page: RebarPage) -> None:
    form = page.form
    card = cards.card(page.inputs, "材料とかぶり")
    line = cards.line(card)
    cards.segment(form, line, (*PILE, "materials", "main"), "主鉄筋の材質")
    cards.segment(form, line, (*PILE, "materials", "transverse"), "帯鉄筋の材質")
    line = cards.line(card)
    cards.entry(form, line, (*CAST, "f'ck"), "コンクリート強度")
    cards.entry(form, line, (*PILE, "aggregate_max_mm"), "粗骨材の最大寸法")
    cards.entry(form, line, (*PILE, "pure_cover_mm"), "純かぶり")
    cards.help_button(line, "純かぶりと芯かぶり", lambda: list(COVER_NOTE))
    cards.shown(line, "杭径 m（杭基礎ページ）", page.editor.document.data["杭基礎"]["場所打ち杭"]["杭径"])


def main(page: RebarPage) -> None:
    common(page)
    form = page.form
    card = cards.card(page.inputs, "主鉄筋（全長で1組）")
    line = cards.line(card)
    cards.size(form, line, (*PILE, "main_bars", "diameter_mm"), "径", sizes=MAIN_SIZES)
    cards.entry(form, line, (*PILE, "main_bars", "count"), "本数", width=6)
    ttk.Label(card, text="段落し後の主鉄筋は「段落し」で入力します（空欄なら段落しなし）。",
              style="Muted.TLabel").pack(anchor="w")


def _title(line: ttk.Frame, text: str) -> None:
    ttk.Label(line, text=text, style="Symbol.TLabel", width=12).pack(side="left", padx=(0, 10), pady=(18, 4))


def _hoop(page: RebarPage, line: ttk.Frame, path: tuple) -> None:
    form = page.form
    cards.size(form, line, (*path, "diameter_mm"), "径", sizes=HOOP_SIZES)
    cards.entry(form, line, (*path, "sets"), "組", width=6)
    cards.entry(form, line, (*path, "pitch_mm"), "間隔")


def hoops(page: RebarPage) -> None:
    common(page)
    card = cards.card(page.inputs, "帯鉄筋（杭頭から下へ）")
    for title, zone in (("フーチング内", "footing"), ("2D 区間", "zone_2d")):
        line = cards.line(card)
        _title(line, title)
        _hoop(page, line, (*PILE, "hoops", zone))
        if zone == "zone_2d":
            cards.help_button(line, "2D 区間", lambda: ["2D 区間：杭頭から杭径の2倍の長さ。杭体の照査はこの区間の帯鉄筋を使います。",
                                                      *SETS_NOTE])
    zones = _pile(page)["hoops"]["lower"]
    for index in range(len(zones)):
        path = (*PILE, "hoops", "lower", index)
        line = cards.line(card)
        _title(line, f"第{index + 1}区間")
        cards.entry(page.form, line, (*path, "length_m"), "区間長")
        _hoop(page, line, path)
        cards.remove_button(line, lambda index=index: page.remove_row((*PILE, "hoops", "lower"), index))
    if len(zones) < PILE_LOWER_HOOPS:
        ttk.Button(card, text=f"＋ 第{len(zones) + 1}区間を追加",
                   command=lambda: page.add_row((*PILE, "hoops", "lower"))).pack(anchor="w", pady=(6, 0))


def cutoff(page: RebarPage) -> None:
    form = page.form
    path = (*PILE, "cutoff")
    card = cards.card(page.inputs, "段落し後の断面（主鉄筋が空欄なら段落しなし）")
    line = cards.line(card)
    _title(line, "主鉄筋")
    cards.size(form, line, (*path, "main_bars", "diameter_mm"), "径", sizes=MAIN_SIZES)
    cards.entry(form, line, (*path, "main_bars", "count"), "本数", width=6)
    line = cards.line(card)
    _title(line, "帯鉄筋")
    _hoop(page, line, (*path, "hoops"))
    card = cards.card(page.inputs, "定着長・余裕長")
    line = cards.line(card)
    cards.entry(form, line, (*path, "cutoff_length_mm"), "段落し長")
    cards.entry(form, line, (*path, "cutoff_anchorage_mm"), "段落し定着長")
    cards.entry(form, line, (*path, "joint_reduction"), "継手低減係数")
    cards.entry(form, line, (*path, "margin_mm"), "設計余裕長")
    card = cards.card(page.inputs, "継ぎ手を設けない範囲")
    line = cards.line(card)
    cards.entry(form, line, (*path, "no_joint", "from_head_mm"), "杭頭から")
    cards.entry(form, line, (*path, "no_joint", "above_mm"), "カットオフ点から 上方")
    cards.entry(form, line, (*path, "no_joint", "below_mm"), "カットオフ点から 下方")
    card = cards.card(page.inputs, "段落しのルール")
    line = cards.line(card)
    cards.entry(form, line, (*path, "margin_ratio", "moment"), "曲げモーメントの余裕率")
    cards.entry(form, line, (*path, "margin_ratio", "shear"), "せん断力の余裕率")
    ttk.Label(card, text="コンクリート強度は「主鉄筋」画面の値と共通です。", style="Muted.TLabel").pack(anchor="w")
