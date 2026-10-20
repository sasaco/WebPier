"""The 鉄筋 page: each member's reinforcement through the field table, the column's section and 方向別の鉄筋配置表 in
a modeless window (column_window) and the beam's 配筋略図 in another (beam_window), the 柱の断面照査 conditions
(decision 48) and the 片持ち梁の照査 conditions (decision 59).

The column and the beam are entered on cards (column_cards, beam_cards; decision 68); the footing is still a
provisional page where its values are listed by their paths, its layers inside layer 1 in small tables. The column's
and the beam's layouts, every layout error, the beam's overlapping bars and the column's table changes whose generated
bars are gone (warnings: the calculation goes on) come from calc.column_rebar and calc.beam_rebar via rebar_edit;
nothing here checks the reinforcement itself.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from ..calc.beam_rebar import BeamLayout
from ..calc.column_rebar import ColumnLayout
from ..inputs import choices
from . import beam_cards, column_cards, rebar_edit
from .beam_window import BeamWindow
from .column_window import ColumnWindow
from .document import EditorError
from .form import Form
from .grid import make_sheet
from .rebar_canvas import SectionView, outline

if TYPE_CHECKING:
    from .app import InputEditor

GROUPS = {"柱": (("main", "主鉄筋"), ("hoops", "帯鉄筋"), ("check", "断面照査の条件")),
          "梁": (("main", "配筋"), ("check", "断面照査の条件")),
          "フーチング": (("main", "配筋"),)}
COMMON = ((("materials", "main"), "主鉄筋の材質"), (("materials", "transverse"), "帯鉄筋・スターラップの材質"),
          (("concrete_strength_mpa",), "コンクリート強度"), (("aggregate_max_mm",), "粗骨材の最大寸法 Dmax"),
          (("pure_cover_mm",), "純かぶり"))
FOOTING_FIRST = ((("diameter_mm",), "径"), (("pitch_mm",), "ピッチ"), (("cover_mode",), "芯かぶりの決め方"),
                 (("center_mm",), "芯かぶり（指定）"))
FOOTING_STIRRUPS = ((("diameter_mm",), "径"), (("pitch_mm",), "間隔"), (("distribution_mode",), "幅方向の指定"),
                    (("width_pitch_mm",), "幅方向の間隔"), (("density_per_m",), "幅方向の 1 m 当たり本数"))
LAYER_LABELS = {"per_face_count": "本数（1つの面）", "pitch_mm": "ピッチ\nmm", "clear_gap_mm": "前の段との\nあき mm"}
CHECK = "柱の断面照査"  # one set for the column, shared by both directions (decision 48)
CHECK_LABELS = (("鋼材の腐食に対する環境条件", "鋼材の腐食に対する環境条件"), ("外観の照査", "外観の照査"),
                ("ε'csd", "ε'csd（収縮・クリープによるひび割れ幅の増加）"), ("適用基準の機関", "適用基準の機関"),
                ("JR-001", "JR-001 ひび割れ幅制限値に用いるかぶりは100mmを上限"),
                ("JR-004", "JR-004 βn算定時のMudは軸力を考慮しない"))
CANTILEVER_CHECK = "片持ち梁の照査"  # one set for both overhangs of the beam (decision 59)
CANTILEVER_LABELS = (
    (("鋼材の腐食に対する環境条件", "上面"), "鋼材の腐食に対する環境条件：上面"),
    (("鋼材の腐食に対する環境条件", "下面"), "鋼材の腐食に対する環境条件：下面"),
    (("鋼材の腐食に対する環境条件", "側面"), "鋼材の腐食に対する環境条件：側面"),
    (("外観の照査",), "外観の照査"),
    (("疲労", "旅客列車本数"), "旅客列車本数（本/日）"), (("疲労", "貨物列車本数"), "貨物列車本数（本/日）"),
    (("疲労", "設計耐用年数"), "設計耐用年数（年）"),
    (("疲労", "等価繰返し回数", "A列車", "k=0.06"), "等価繰返し回数 A列車 k=0.06"),
    (("疲労", "等価繰返し回数", "A列車", "k=0.12"), "等価繰返し回数 A列車 k=0.12"),
    (("疲労", "等価繰返し回数", "B列車", "k=0.06"), "等価繰返し回数 B列車 k=0.06"),
    (("疲労", "等価繰返し回数", "B列車", "k=0.12"), "等価繰返し回数 B列車 k=0.12"),
)
CANTILEVER_NOTE = ("片持ち梁の照査（0900・0910）の条件です。左右の張出しで共通です。"
                   "等価繰返し回数は外部プログラム（N-EQUIVALENT）の値を入力します。")
OUTLINE_ONLY = "配筋位置を計算する段階がまだないため、断面の外形だけを表示します。"


class RebarPage:
    busy = False

    def __init__(self, editor: InputEditor, parent: ttk.Frame) -> None:
        self.editor = editor
        state = editor.rebar_state
        self.member: str = state.setdefault("member", "柱")
        self.group: str = state.setdefault("group", "main")
        self.direction: str = state.setdefault("direction", "線路")
        self.selected: tuple | None = state.get("selected")  # (list path, row) of a table, or ("layer", key)
        self.layout: ColumnLayout | BeamLayout | None = None
        self.section: SectionView | None = None  # the outline of the footing
        self.direction_sheet: Any = None
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="both", expand=True)
        bar = ttk.Frame(self.frame)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="部材", style="Symbol.TLabel").pack(side="left")
        self.member_choice = ttk.Combobox(bar, values=rebar_edit.MEMBERS, state="readonly", width=12)
        self.member_choice.set(self.member)
        self.member_choice.pack(side="left", padx=(8, 18))
        self.member_choice.bind("<<ComboboxSelected>>", lambda event: self.select_member(self.member_choice.get()))
        self.group_buttons = {}
        for name, title in GROUPS[self.member]:
            button = ttk.Button(bar, text=title, command=lambda name=name: self.select_group(name))
            button.pack(side="left", padx=3)
            self.group_buttons[name] = button
        if self.group not in self.group_buttons:
            self.group = state["group"] = "main"
        column, footing = self.member == "柱", self.member == "フーチング"
        if column:
            ttk.Button(bar, text="断面図・配置表", command=self.toggle_window).pack(side="right")
        elif not footing:
            ttk.Button(bar, text="配筋略図", command=self.toggle_window).pack(side="right")
        if not footing:
            left = ttk.Frame(self.frame)
            left.pack(fill="both", expand=True)
        else:
            split = ttk.Panedwindow(self.frame, orient="horizontal")
            split.pack(fill="both", expand=True)
            left = ttk.Frame(split)
            right = ttk.Frame(split, padding=(8, 0, 0, 0))
            split.add(left, weight=3)
            split.add(right, weight=2)
        self.inputs_canvas = tk.Canvas(left, highlightthickness=0, background="white", height=480)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.inputs_canvas.yview)
        self.inputs_canvas.configure(yscrollcommand=scroll.set)
        self.inputs_canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.inputs = ttk.Frame(self.inputs_canvas, padding=(0, 0, 5, 8))
        self.inputs_canvas.create_window((0, 0), window=self.inputs, anchor="nw")
        self.inputs.bind("<Configure>", lambda event: self.inputs_canvas.configure(
            scrollregion=self.inputs_canvas.bbox("all")))
        self.status = tk.StringVar(master=self.frame)  # the column's or the beam's layout error or warning
        if not footing:
            line = ttk.Frame(self.inputs)
            line.pack(fill="x", pady=(0, 6))
            ttk.Label(line, textvariable=self.status, foreground="#8e1d1d", wraplength=900).pack(side="left")
        if column:
            self.fix_corner = ttk.Button(line, command=self.match_corner_sizes)  # packed when the sizes differ
        self.form = Form(editor, self.inputs)
        self.tables: dict[tuple, Any] = {}
        self.readouts: dict[tuple[str, int], tk.StringVar] = {}
        self._build_inputs()
        if footing:
            title = ttk.Frame(right)
            title.pack(fill="x")
            ttk.Label(title, text="断面図", style="Symbol.TLabel").pack(side="left")
            self.direction_choice = ttk.Combobox(title, values=choices.REBAR_DIRECTIONS, state="readonly", width=7)
            self.direction_choice.set(self.direction)
            self.direction_choice.pack(side="right")
            self.direction_choice.bind("<<ComboboxSelected>>",
                                       lambda event: self.select_direction(self.direction_choice.get()))
            self.section = SectionView(right)
            self.section.pack(fill="both", expand=True)
            ttk.Label(right, text="方向別の鉄筋配置表（基準面からの芯位置）", style="Symbol.TLabel").pack(anchor="w",
                                                                                         pady=(6, 0))
            self.direction_sheet = make_sheet(right, ["芯位置 mm", "径 mm", "本数", "材質"], [], [90, 60, 55, 80],
                                              max_height=150)
            self.direction_sheet.pack(fill="x")
        self.refresh()

    # inputs -------------------------------------------------------------------------------------------------

    def _path(self, *keys: Any) -> tuple:
        return ("鉄筋", self.member, *keys)

    def _values(self, parent: tk.Misc, prefix: tuple, specs) -> None:
        self.form.properties(parent, [((*prefix, *tail), label) for tail, label in specs])

    def _group(self, title: str) -> ttk.LabelFrame:
        group = ttk.LabelFrame(self.inputs, text=title, style="Sheet.TLabelframe", padding=4)
        group.pack(fill="x", pady=(0, 6))
        return group

    def _rows_table(self, parent: tk.Misc, path: tuple, keys: tuple[str, ...], labels: tuple[str, ...]) -> None:
        rows = rebar_edit.items(self.editor.document.data, path)
        cells = [[(*path, index, key) for key in keys] for index in range(len(rows))]
        sheet = self.form.table(parent, list(labels), cells, [78] * len(keys), pack=False, max_height=200,
                                index_width=34)
        sheet.pack(fill="x", expand=True)
        sheet.bind("<<SheetSelect>>", lambda event: self._row_selected(path, sheet), add="+")
        self.tables[path] = sheet
        line = ttk.Frame(parent)
        line.pack(fill="x")
        ttk.Button(line, text="行を追加", command=lambda: self.add_row(path)).pack(side="left", padx=2)
        ttk.Button(line, text="選択行を削除", command=lambda: self.delete_row(path)).pack(side="left", padx=2)

    def _layers(self, parent: tk.Misc, prefix: tuple, keys: tuple[str, ...]) -> None:
        ttk.Label(parent, text="2段目以降（径と並べ方は1段目と同じ）", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        self._rows_table(parent, (*prefix, "inner_layers"), keys, tuple(LAYER_LABELS[key] for key in keys))

    def _build_inputs(self) -> None:
        if self.member == "フーチング":  # the column's and the beam's are on their cards (column_cards, beam_cards)
            self._values(self.inputs, self._path(), COMMON)
            ttk.Label(self.inputs, text="純かぶり：コンクリート面から最も外側の鉄筋の外面まで。空欄は未入力です。",
                      style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        if self.group == "check" and self.member == "梁":
            self.form.properties(self.inputs,
                                 [((CANTILEVER_CHECK, *tail), label) for tail, label in CANTILEVER_LABELS])
            ttk.Label(self.inputs, text=CANTILEVER_NOTE, style="Muted.TLabel", wraplength=520).pack(anchor="w")
        elif self.group == "check":
            self.form.properties(self.inputs, [((CHECK, key), label) for key, label in CHECK_LABELS])
            ttk.Label(self.inputs, text="柱の断面照査（0611・0621）の条件です。線路方向・線路直角方向で共通です。",
                      style="Muted.TLabel").pack(anchor="w")
        elif self.group == "hoops":
            column_cards.hoops(self)
        elif self.member == "柱":
            column_cards.main(self)
        elif self.member == "梁":
            beam_cards.main(self)
        else:
            for face in choices.BEAM_FACES:
                group = self._group(f"{face}面の主鉄筋")
                self.form.properties(group, [(self._path("faces", face, "outer_direction"), f"{face}で外側になる方向")])
                for direction in choices.REBAR_DIRECTIONS:
                    ttk.Label(group, text=f"{direction}方向", style="Symbol.TLabel").pack(anchor="w", pady=(6, 0))
                    prefix = self._path("faces", face, direction)
                    self._values(group, prefix, FOOTING_FIRST)
                    self._layers(group, prefix, ("pitch_mm", "clear_gap_mm"))
            for direction in choices.REBAR_DIRECTIONS:
                self._values(self._group(f"{direction}方向のスターラップ"), self._path("stirrups", direction),
                             FOOTING_STIRRUPS)

    # actions ------------------------------------------------------------------------------------------------

    def _save_state(self) -> None:
        self.editor.rebar_state.update(member=self.member, group=self.group, direction=self.direction,
                                       selected=self.selected)

    def _rebuild(self) -> None:
        self._save_state()
        self.editor.rebuild()

    def select_member(self, member: str) -> bool:
        if member not in rebar_edit.MEMBERS or not self.ready_to_leave() or not self.editor.ready_to_restructure():
            self.member_choice.set(self.member)
            return False
        self.member, self.group, self.selected = member, "main", None
        self._rebuild()
        return True

    def select_group(self, group: str) -> bool:
        if not self.ready_to_leave() or not self.editor.ready_to_restructure():
            return False
        self.group, self.selected = group, None
        self._rebuild()
        return True

    def select_direction(self, direction: str) -> None:
        self.direction = self.editor.rebar_state["direction"] = direction
        self.refresh()

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

    def _row_selected(self, path: tuple, sheet: Any) -> None:
        current = sheet.get_currently_selected()
        if current:
            self.selected = (path, current.row)
            self.editor.rebar_state["selected"] = self.selected

    def add_row(self, path: tuple) -> bool:
        def add() -> None:
            self.selected = (path, rebar_edit.add_row(self.editor.document.data, path))
        return self._restructure(add, "行を追加できません")

    def delete_row(self, path: tuple) -> bool:
        if self.selected is None or self.selected[0] != path:
            return False
        index = self.selected[1]
        self.selected = None
        return self._restructure(lambda: rebar_edit.delete_row(self.editor.document.data, path, index),
                                 "行を削除できません")

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

    def window(self) -> ColumnWindow | BeamWindow | None:
        """The open window of the member (the column's section and tables, the beam's 配筋略図), kept by the editor
        while the page is rebuilt."""
        window = self.editor.rebar_state.get("window")
        return window if window is not None and window.window.winfo_exists() else None

    def toggle_window(self) -> bool:
        """Open the member's window, or close the open one; whether it is open."""
        window = self.window()
        if window is not None:
            window.close()
            return False
        kind = ColumnWindow if self.member == "柱" else BeamWindow
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
        if self.member == "柱":
            self.layout = None
            try:
                self.layout = rebar_edit.column_preview(data)
                problem = ""
            except EditorError as exc:
                problem = str(exc)
            if self.layout is not None and self.layout.unmatched:
                problem = (f"警告：配置表の変更のうち {len(self.layout.unmatched)} 件は、元の芯位置・径の鉄筋がないため"
                           "使われていません（計算でも使いません）。")
            self.status.set(problem)
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
        try:
            polygon = outline(self.member, data, self.direction)
        except EditorError as exc:
            self.section.show([], notice=str(exc))
            self._table([])
            return
        self.section.show(polygon, caption=f"{self.member}（{self.direction}方向）", notice=OUTLINE_ONLY)
        self._table([])

    def _table(self, rows: list[list[str]]) -> None:
        self.direction_sheet.set_sheet_data(rows, reset_col_positions=False, redraw=True)
        self.direction_sheet.readonly_cells(cells=[(r, c) for r in range(len(rows)) for c in range(4)])

    # the editor's page interface ------------------------------------------------------------------------------

    def wheel(self, event: Any) -> bool:
        """The mouse wheel over the inputs scrolls them, but not over a table (it scrolls itself); whether it did."""
        widget = self.editor.root.winfo_containing(event.x_root, event.y_root)
        name = "" if widget is None else str(widget)

        def within(parent: Any) -> bool:
            return name == str(parent) or name.startswith(f"{parent}.")
        if not within(self.inputs_canvas) or any(within(sheet) for sheet in self.tables.values()):
            return False
        self.inputs_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return True

    def input_changed(self) -> None:
        self.refresh()

    def input_moved(self) -> None:
        pass

    def ready_to_leave(self) -> bool:
        return True

    def dispose(self) -> None:
        self._save_state()
        self.editor.root.after_idle(self._close_window_if_left)
