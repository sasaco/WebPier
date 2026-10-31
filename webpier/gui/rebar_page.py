"""The 鉄筋 page: each member's reinforcement on cards (column_cards, beam_cards, footing_cards; decision 68), the
column's section and 方向別の鉄筋配置表 in a modeless window (column_window) and the beam's and the footing's 配筋略図
in others (beam_window, footing_window), the 柱の断面照査 conditions (decision 48) and the 片持ち梁の照査 conditions
(decision 59).

The layouts, every layout error and the warnings (the column's two tables with other bars, the beam's overlapping
bars, the footing's crossing layers: the calculation goes on) come from calc.column_rebar, calc.beam_rebar and
calc.footing_rebar via rebar_edit; nothing here checks the reinforcement itself. Editing a direction of the column's
main bars makes its hand-made 方向別の鉄筋配置表 from them again (decision 111, rebar_edit.reset_changed).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from tksheet import Sheet

from ..calc.beam_rebar import BeamLayout
from ..calc.column_rebar import ColumnLayout, count_mismatch
from ..inputs import choices
from ..inputs.fields import FORCE_RATIOS
from . import beam_cards, column_cards, footing_cards, pile_cards, rebar_edit, steel_pile_cards
from .beam_window import BeamWindow
from .column_window import ColumnWindow
from .document import EditorError
from .footing_window import FootingWindow
from .pile_window import PileWindow
from .form import Form
from .rebar_edit import FootingPreview

if TYPE_CHECKING:
    from .app import InputEditor

GROUPS = {"柱": (("main", "主鉄筋"), ("hoops", "帯鉄筋"), ("check", "断面照査の条件")),
          "梁": (("main", "配筋"), ("check", "断面照査の条件")),
          "フーチング": (("main", "配筋"),),
          "杭": (("main", "主鉄筋"), ("hoops", "帯鉄筋"), ("cutoff", "段落し"))}
WINDOWS = {"柱": ColumnWindow, "梁": BeamWindow, "フーチング": FootingWindow, "杭": PileWindow}  # the member's window (toggle_window)
CHECK = "柱の断面照査"  # one set for the column, shared by both directions (decision 48)
CHECK_LABELS = (("水掛かりの程度", "水掛かりの程度"), ("外観の照査", "外観の照査"),
                ("ε'csd", "ε'csd（収縮・クリープによるひび割れ幅の増加）"), ("適用基準の機関", "適用基準の機関"),
                ("JR-001", "JR-001 ひび割れ幅制限値に用いるかぶりは100mmを上限"),
                ("JR-004", "JR-004 βn算定時のMudは軸力を考慮しない"))
CANTILEVER_CHECK = "片持ち梁の照査"  # one set for both overhangs of the beam (decision 59)
CANTILEVER_LABELS = (
    (("水掛かりの程度", "上面"), "水掛かりの程度：上面"),
    (("水掛かりの程度", "下面"), "水掛かりの程度：下面"),
    (("水掛かりの程度", "側面"), "水掛かりの程度：側面"),
    (("外観の照査",), "外観の照査"),
    (("疲労", "旅客列車本数"), "旅客列車本数（本/日）"), (("疲労", "貨物列車本数"), "貨物列車本数（本/日）"),
    (("疲労", "設計耐用年数"), "設計耐用年数（年）"),
    (("疲労", "等価繰返し回数", "A列車", "k=0.06"), "等価繰返し回数 A列車 k=0.06"),
    (("疲労", "等価繰返し回数", "A列車", "k=0.12"), "等価繰返し回数 A列車 k=0.12"),
    (("疲労", "等価繰返し回数", "B列車", "k=0.06"), "等価繰返し回数 B列車 k=0.06"),
    (("疲労", "等価繰返し回数", "B列車", "k=0.12"), "等価繰返し回数 B列車 k=0.12"),
    (("疲労", FORCE_RATIOS, "A列車"), "最大変動断面力比 SA/SC（A列車）"),
    (("疲労", FORCE_RATIOS, "B列車"), "最大変動断面力比 SB/SC（B列車）"),
)
CANTILEVER_NOTE = ("片持ち梁の照査（0900・0910）の条件です。左右の張出しで共通です。"
                   "等価繰返し回数は外部プログラム（N-EQUIVALENT）の値を、最大変動断面力比は A列車・B列車と標準列車荷重の"
                   "最大変動断面力の比を入力します。")


class RebarPage:
    busy = False

    def __init__(self, editor: InputEditor, parent: ttk.Frame) -> None:
        self.editor = editor
        state = editor.rebar_state
        self.member: str = state.setdefault("member", "柱")
        if self.member not in self.members():  # the pile of a foundation that is no longer a pile foundation
            self.member = state["member"] = "柱"
        self.group: str = state.setdefault("group", "main")
        self.steel = self.member == rebar_edit.PILE and (
            rebar_edit.foundation(editor.document.data) == choices.STEEL_SOIL_CEMENT_PILE)  # decision 126
        self.layout: ColumnLayout | BeamLayout | FootingPreview | None = None
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="both", expand=True)
        bar = ttk.Frame(self.frame)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text=self.member, style="Symbol.TLabel").pack(side="left", padx=(0, 18))  # chosen in the tree
        self.group_buttons = {}
        for name, title in self.groups():
            button = ttk.Button(bar, text=title, command=lambda name=name: self.select_group(name))
            button.pack(side="left", padx=3)
            self.group_buttons[name] = button
        if self.group not in self.group_buttons:
            self.group = state["group"] = self.groups()[0][0]
        column = self.member == "柱"
        if not self.steel:  # a 鋼管ソイルセメント杭 has no 配筋略図 (its joint and tip are drawn in 0400)
            ttk.Button(bar, text="断面図・配置表" if column else "配筋略図", command=self.toggle_window).pack(side="right")
        left = ttk.Frame(self.frame)
        left.pack(fill="both", expand=True)
        self.inputs_canvas = tk.Canvas(left, highlightthickness=0, background="white", height=480)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.inputs_canvas.yview)
        self.inputs_canvas.configure(yscrollcommand=scroll.set)
        self.inputs_canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.inputs = ttk.Frame(self.inputs_canvas, padding=(0, 0, 5, 8))
        self.inputs_canvas.create_window((0, 0), window=self.inputs, anchor="nw")
        self.inputs.bind("<Configure>", lambda event: self.inputs_canvas.configure(
            scrollregion=self.inputs_canvas.bbox("all")))
        self.status = tk.StringVar(master=self.frame)  # the member's layout errors and warnings
        line = ttk.Frame(self.inputs)
        line.pack(fill="x", pady=(0, 6))
        ttk.Label(line, textvariable=self.status, foreground="#8e1d1d", wraplength=900, justify="left").pack(
            side="left")
        if column:
            self.fix_corner = ttk.Button(line, command=self.match_corner_sizes)  # packed when the sizes differ
        self.form = Form(editor, self.inputs)
        self.readouts: dict[tuple, tk.StringVar] = {}
        self.main_bars = rebar_edit.main_bars(editor.document.data)  # the column's, to reset its hand-made tables
        self.reset_note = ""
        self._build_inputs()
        self.refresh()

    # inputs -------------------------------------------------------------------------------------------------

    def _build_inputs(self) -> None:
        if self.group == "check" and self.member == "梁":
            self.form.properties(self.inputs,
                                 [((CANTILEVER_CHECK, *tail), label) for tail, label in CANTILEVER_LABELS])
            ttk.Label(self.inputs, text=CANTILEVER_NOTE, style="Muted.TLabel", wraplength=520).pack(anchor="w")
        elif self.group == "check":
            self.form.properties(self.inputs, [((CHECK, key), label) for key, label in CHECK_LABELS])
            ttk.Label(self.inputs, text="柱の断面照査（0611・0621）の条件です。線路方向・線路直角方向で共通です。",
                      style="Muted.TLabel").pack(anchor="w")
        elif self.steel:
            {"pipe": steel_pile_cards.pipe, "cutoff": steel_pile_cards.cutoff}[self.group](self)
        elif self.member == rebar_edit.PILE:
            {"main": pile_cards.main, "hoops": pile_cards.hoops, "cutoff": pile_cards.cutoff}[self.group](self)
        elif self.group == "hoops":
            column_cards.hoops(self)
        elif self.member == "柱":
            column_cards.main(self)
        elif self.member == "梁":
            beam_cards.main(self)
        else:
            footing_cards.main(self)

    # actions ------------------------------------------------------------------------------------------------

    def members(self) -> tuple[str, ...]:
        return rebar_edit.members(self.editor.document.data)

    def groups(self) -> tuple[tuple[str, str], ...]:
        """The groups of the member: a 鋼管ソイルセメント杭's pile has its own (decision 126)."""
        return steel_pile_cards.GROUPS if self.steel else GROUPS[self.member]

    def _save_state(self) -> None:
        self.editor.rebar_state.update(member=self.member, group=self.group)

    def _rebuild(self) -> None:
        self._save_state()
        self.editor.rebuild()

    def select_member(self, member: str) -> bool:
        if member not in self.members() or not self.ready_to_leave() or not self.editor.ready_to_restructure():
            return False
        self.member, self.group = member, "main"  # a group the member lacks opens at its first
        self._rebuild()
        return True

    def select_group(self, group: str) -> bool:
        if not self.ready_to_leave() or not self.editor.ready_to_restructure():
            return False
        self.group = group
        self._rebuild()
        return True

    def _restructure(self, change: Any, title: str) -> bool:
        if not self.editor.ready_to_restructure():
            return False
        try:
            result = change()
        except EditorError as exc:
            messagebox.showerror(title, str(exc), parent=self.editor.root)
            return False
        if result is False:
            return False
        self._rebuild()
        return True

    def add_row(self, path: tuple) -> bool:
        """A blank item at the end of the list at *path* (a card's ＋)."""
        return self._restructure(lambda: rebar_edit.add_row(self.editor.document.data, path), "行を追加できません")

    def add_hoop(self, direction: str) -> bool:
        """A new range of the hoops of *direction* (its other values blank)."""
        path = ("鉄筋", "柱", "column_hoops", "direction_rows")

        def add() -> None:
            data = self.editor.document.data
            rebar_edit.items(data, path)[rebar_edit.add_row(data, path)]["direction"] = direction
        return self._restructure(add, "範囲を追加できません")

    def remove_row(self, path: tuple, index: int) -> bool:
        """Remove the item *index* of the list at *path* (a card's ×)."""
        return self._restructure(lambda: rebar_edit.delete_row(self.editor.document.data, path, index),
                                 "行を削除できません")

    def rebuild_later(self) -> None:
        """A choice that shows other inputs (芯かぶり, 並べ方): the page is built again once the choice is entered."""
        self.editor.root.after_idle(self._rebuild)

    def remove_layers(self, path: tuple, index: int) -> bool:
        """Remove the layer at *index* of the list at *path* and the layers inside it."""
        def remove() -> None:
            del rebar_edit.items(self.editor.document.data, path)[index:]
        return self._restructure(remove, "段を削除できません")

    def match_corner_sizes(self) -> None:
        """直角1段目を線路1段目と同じ径にする: the corner bars are shared only when their sizes are the same."""
        bars = self.editor.document.data["鉄筋"]["柱"]["main_bars"]
        bars["直角"]["diameter_mm"] = bars["線路"]["diameter_mm"]
        self.editor.bindings.refresh()
        self.editor.changed()

    def set_side_bars(self, present: bool) -> bool:
        return self._restructure(lambda: rebar_edit.set_side_bars(self.editor.document.data, present),
                                 "側面筋を変更できません")

    # the member's window ------------------------------------------------------------------------------------

    def window(self) -> ColumnWindow | BeamWindow | FootingWindow | PileWindow | None:
        """The open window of the member (the column's section and tables, the beam's or the footing's 配筋略図), kept
        by the editor while the page is rebuilt."""
        window = self.editor.rebar_state.get("window")
        return window if window is not None and window.window.winfo_exists() else None

    def toggle_window(self) -> bool:
        """Open the member's window, or close the open one; whether it is open."""
        window = self.window()
        if window is not None:
            window.close()
            return False
        if self.steel:  # no 配筋略図 of a 鋼管ソイルセメント杭 (decision 126)
            return False
        kind = WINDOWS[self.member]
        self.editor.rebar_state["window"] = kind(self.editor, self._window_closed)
        return True

    def _window_closed(self) -> None:
        self.editor.rebar_state["window"] = None

    def _close_window_if_left(self) -> None:
        """After the page is disposed: close the window unless the 鉄筋 page of its member comes back. Decided from
        where the editor goes (its page, the member kept in rebar_state), not from editor.view: a new page may still be
        being built when this runs (tksheet updates the idle tasks while it builds a table)."""
        window = self.window()
        if window is None:
            return
        staying = self.editor.page == "鉄筋" and self.editor.rebar_state.get("member") == window.member
        if not staying:
            window.close()

    # preview ------------------------------------------------------------------------------------------------

    def refresh(self) -> None:
        data = self.editor.document.data
        if self.member == rebar_edit.PILE:  # nothing to lay out: the cards show only what is entered
            self.layout = None
            self.status.set("")
            if self.steel:  # the effective walls (decision 126)
                for key, text in steel_pile_cards.readouts(self).items():
                    if key in self.readouts:
                        self.readouts[key].set(text)
                return
            if (window := self.window()) is not None:
                window.refresh()
            return
        if self.member == "柱":
            self.layout = None
            try:
                self.layout = rebar_edit.column_preview(data)
                problem = ""
            except EditorError as exc:
                problem = str(exc)
            if self.layout is not None and (mismatch := count_mismatch(self.layout)) is not None:
                problem = (f"警告：線路方向と直角方向の配置表で鉄筋の本数が違います（{mismatch}）。断面図・配置表で"
                           "確かめてください（計算は止めません）。")
            self.status.set("\n".join(text for text in (self.reset_note, problem) if text))
            for key, variable in self.readouts.items():
                variable.set(column_cards.readout(self, key))
            bars = data["鉄筋"]["柱"]["main_bars"]
            sizes = (bars["線路"]["diameter_mm"], bars["直角"]["diameter_mm"])
            if "径の異なる鉄筋" in problem and None not in sizes and sizes[0] != sizes[1]:
                self.fix_corner.configure(text=f"直角1段目を D{sizes[0]:g} にする")
                self.fix_corner.pack(side="left", padx=8)
            else:
                self.fix_corner.pack_forget()
            if (window := self.window()) is not None:
                window.refresh()
            return
        if self.member == "梁":
            self.layout = None
            try:
                self.layout = rebar_edit.beam_preview(data)
                problem = ""
            except EditorError as exc:
                problem = str(exc)
            if self.layout is not None and self.layout.overlaps:
                problem = (f"警告：鉄筋が {len(self.layout.overlaps)} か所で重なっています。配筋略図の赤い鉄筋を確かめて"
                           "ください（計算は止めません）。")
            self.status.set(problem)
            for key, variable in self.readouts.items():
                variable.set(beam_cards.readout(self, key))
            if (window := self.window()) is not None:
                window.refresh()
            return
        self.layout = None
        problems = []
        try:
            self.layout = rebar_edit.footing_preview(data)
        except EditorError as exc:
            problems.append(str(exc))
        if self.layout is not None:
            lower = footing_cards.LOWER  # the upper face is not read by the calculation: only its readouts say —
            if lower in self.layout.problems:
                problems.append(f"{lower}面：{self.layout.problems[lower]}")
            for face, layout in self.layout.faces.items():
                if layout is not None and layout.crossings:
                    problems.append(f"警告：{face}面で段が {len(layout.crossings)} か所で交差しています。配筋略図で"
                                    "確かめてください（計算は止めません）。")
        self.status.set("\n".join(problems))
        for key, variable in self.readouts.items():
            variable.set(footing_cards.readout(self, key))
        if (window := self.window()) is not None:
            window.refresh()

    # the editor's page interface ------------------------------------------------------------------------------

    def wheel(self, event: Any) -> bool:
        """The mouse wheel over the inputs scrolls them, but not over a table (a tksheet Sheet scrolls itself); whether
        it did."""
        widget = self.editor.root.winfo_containing(event.x_root, event.y_root)
        name = "" if widget is None else str(widget)
        if not (name == str(self.inputs_canvas) or name.startswith(f"{self.inputs_canvas}.")):
            return False
        while widget is not None:
            if isinstance(widget, Sheet):
                return False
            widget = widget.master
        self.inputs_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return True

    def input_changed(self) -> None:
        reset = rebar_edit.reset_changed(self.editor.document.data, self.main_bars)
        self.main_bars = rebar_edit.main_bars(self.editor.document.data)
        if reset:
            self.reset_note = (f"{'・'.join(reset)}方向の主鉄筋を変えたので、手直しした配置表を主鉄筋の入力から作り直し"
                               "ました。")
        self.refresh()

    def input_moved(self) -> None:
        pass

    def ready_to_leave(self) -> bool:
        return True

    def dispose(self) -> None:
        self._save_state()
        self.editor.root.after_idle(self._close_window_if_left)
