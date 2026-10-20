"""The 上部工反力 sheet: the girder-end totals (A, D) and the ten bearing slots of each pier support (B, C).

A slot left entirely blank is an empty slot (CONTEXT.md 空き支承枠); a slot with some values entered marks its
blank cells as missing. L3/L4 are shown disabled: only two tracks are calculated (decision 23). "B/Cと同じ"
writes the sums of the bearings into A or D as explicit values (decision 5).
"""

from __future__ import annotations

from tkinter import messagebox

from ..inputs.fields import LOAD_KEYS
from . import bearings
from .document import EditorError
from .form import Form, unit_of

SLOTS = 10
ROW_LABELS = {("支承位置",): "支承位置", ("固定死荷重_D1",): "固定死荷重 D1", ("付加死荷重_D2",): "付加死荷重 D2",
              ("雪荷重_2年確率",): "雪荷重 2年確率", ("雪荷重_10年確率",): "雪荷重 10年確率",
              ("雪荷重_30年確率",): "雪荷重 30年確率", **{("列車分担", f"L{i}"): f"列車分担 L{i}" for i in range(1, 5)}}


def _label(side: str, support: str, tail: tuple) -> str:
    unit = unit_of(("上部工反力", side, support, 0, *tail))
    return ROW_LABELS[tail] + (f" ({unit})" if unit else "") + ("（未対応）" if tail[-1] in ("L3", "L4") else "")


def _writer(form: Form, side: str, index: int, tail: tuple):
    return lambda value: bearings.set_value(form.data, side, index, tail, value)


def reactions(form: Form) -> None:
    form.figure(form.section("支点と支承の位置", note="支承位置は柱の中心線から測った線路直角方向の距離です。"
                             "全項目が空欄の枠は支承なし（空き支承枠）、一部だけ入力した枠の空欄は入力エラーです。"
                             "ただし雪荷重の空欄は雪荷重なし（0）です。"),
                "reactions", "A・B・C・D支点と支承位置 / 原図・記号確認用")
    for side in bearings.SUPPORTS:
        end, support = bearings.SUPPORTS[side]
        body = form.section(side, note=f"{end}は桁端の合計を入力します。「B/Cと同じ」で{support}の合計を{end}に書き込みます。")
        slots = [(f"{support} {index + 1}", index) for index in range(SLOTS)]
        columns = [(f"{end} 合計", None), *slots] if side == "起点側" else [*slots, (f"{end} 合計", None)]
        rows, writers = [], {}
        for tail in bearings.SLOT_LEAVES:
            row = []
            for _, index in columns:
                if index is None:
                    row.append(("上部工反力", side, end, *tail) if tail[0] in LOAD_KEYS else "—")
                else:
                    path = ("上部工反力", side, support, index, *tail)
                    writers[path] = _writer(form, side, index, tail)
                    row.append(path)
            rows.append(row)
        sheet = form.table(body, [title for title, _ in columns], rows, [100] * len(columns), writers=writers,
                           row_labels=[_label(side, support, tail) for tail in bearings.SLOT_LEAVES], index_width=190)
        form.editor.reaction_sheets[side] = sheet
        form.editor.same_buttons[side] = form.button(body, f"B/Cと同じ（{end}＝{support}の合計）",
                                                     lambda side=side: same_as_bearings(form, side))


def same_as_bearings(form: Form, side: str) -> bool:
    if not form.editor.ready_to_restructure():
        return False
    try:
        bearings.same_as_bearings(form.data, side)
    except EditorError as exc:
        messagebox.showerror("合計を書き込めません", str(exc), parent=form.editor.root)
        return False
    form.editor.bindings.refresh()
    form.editor.changed()
    return True
