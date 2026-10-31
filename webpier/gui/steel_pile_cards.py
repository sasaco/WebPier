"""The 鋼管ソイルセメント杭's cards on the 鉄筋 page (decisions 87 and 126).

Two groups: 鋼管・ソイルセメント (the grade and the wall of the pipe, bound to the same items as the 杭基礎 page, so one value
whichever page enters it; its diameters and corrosion allowance are shown only, the effective wall t − c calculated) and
段落し (the pipe below the cut-off and the lengths Aggre-SE's ⑧ takes; blank 段落し後の鋼管厚 is no cut-off). The ソイルセメント
strength is no input (decision 99) and the 結合部 stays on the 杭基礎 page (decision 90). There is no 配筋略図: the joint and
the tip are drawn in 0400's 配筋図.
"""

from __future__ import annotations

from tkinter import ttk
from typing import TYPE_CHECKING, Any

from . import cards

if TYPE_CHECKING:
    from .rebar_page import RebarPage

STEEL = ("杭基礎", "鋼管ソイルセメント杭")
CUT = (*STEEL, "段落し")
EFFECTIVE = (*STEEL, "有効肉厚")  # the readouts of the effective walls (no input)
CUT_EFFECTIVE = (*CUT, "有効肉厚")
GROUPS = (("pipe", "鋼管・ソイルセメント"), ("cutoff", "段落し"))
CUTOFF_NOTE = ("段落し後の鋼管厚が空欄なら段落しなし。下杭は上杭より薄いか弱い材質にし、肉厚の変化は 7 mm 以下です。"
               "杭頭埋込長 50 mm と継手低減係数 0.9 はプログラムが持ちます（杭体設計の手引き）。"
               "上杭長が空欄なら、耐震性能照査（Aggre-SE）が段落し位置を決めます。")


def _steel(page: RebarPage) -> dict[str, Any]:
    return page.editor.document.data["杭基礎"]["鋼管ソイルセメント杭"]


def _wall(thickness: Any, corrosion: Any) -> str:
    """t − c as the 鋼管厚 is printed (0.1 mm), or no value while either is blank."""
    if not isinstance(thickness, (int, float)) or not isinstance(corrosion, (int, float)):
        return cards.NO_VALUE
    return f"{thickness - corrosion:.1f}"


def readouts(page: RebarPage) -> dict[tuple, str]:
    """The effective walls of the pipe and of the pipe below the cut-off."""
    steel = _steel(page)
    cutoff = steel.get("段落し") or {}
    return {EFFECTIVE: _wall(steel.get("鋼管厚"), steel.get("腐食代")),
            CUT_EFFECTIVE: _wall(cutoff.get("段落し後の鋼管厚"), steel.get("腐食代"))}


def pipe(page: RebarPage) -> None:
    form, steel = page.form, _steel(page)
    card = cards.card(page.inputs, "鋼管（「杭基礎」ページと共通の値）")
    line = cards.line(card)
    cards.segment(form, line, (*STEEL, "鋼管材質"), "鋼管の材質")
    cards.entry(form, line, (*STEEL, "鋼管厚"), "鋼管厚（腐食代を含む）")
    cards.readout_label(line, page.readouts, EFFECTIVE, "有効肉厚 t－c mm")
    line = cards.line(card)
    cards.shown(line, "鋼管外径 m", steel.get("鋼管外径"))
    cards.shown(line, "腐食代 mm", steel.get("腐食代"))
    cards.shown(line, "ソイルセメント径 m", steel.get("ソイルセメント径"))
    ttk.Label(card, text="外径・腐食代・ソイルセメント径と結合部は「杭基礎」ページで入力します。ソイルセメントの強度は"
                         "規則の値を使い、入力しません。", style="Muted.TLabel", wraplength=640).pack(anchor="w")


def cutoff(page: RebarPage) -> None:
    form = page.form
    card = cards.card(page.inputs, "段落し後の鋼管（空欄なら段落しなし）")
    line = cards.line(card)
    cards.entry(form, line, (*CUT, "段落し後の鋼管厚"), "段落し後の鋼管厚（腐食代を含む）")
    cards.segment(form, line, (*CUT, "段落し後の鋼管材質"), "段落し後の鋼管の材質")
    cards.readout_label(line, page.readouts, CUT_EFFECTIVE, "有効肉厚 mm")
    card = cards.card(page.inputs, "上杭長・施工余裕長")
    line = cards.line(card)
    cards.entry(form, line, (*CUT, "上杭長"), "上杭長")
    cards.entry(form, line, (*CUT, "施工余裕長", "低止まり"), "施工余裕長 低止まり")
    cards.entry(form, line, (*CUT, "施工余裕長", "高止まり"), "施工余裕長 高止まり")
    card = cards.card(page.inputs, "継手を設けない範囲")
    line = cards.line(card)
    cards.entry(form, line, (*CUT, "継手を設けない範囲_杭頭から"), "杭頭から")
    ttk.Label(page.inputs, text=CUTOFF_NOTE, style="Muted.TLabel", wraplength=640).pack(anchor="w")
