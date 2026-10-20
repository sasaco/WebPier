"""The 鉄筋 page: each member's reinforcement through the field table, the column drawn from calc.column_rebar, the
柱の断面照査 conditions (decision 48) and the 片持ち梁の照査 conditions (decision 59).

A provisional page for the 鉄筋 input of decision 68: the values of a member are listed by their paths, and the layers
inside layer 1 and the hoop rows are small tables with rows to add and delete. The column drawing, the 方向別の鉄筋配置表,
every layout error and the table changes whose generated bars are gone (a warning: the generation leaves them out)
come from calc.column_rebar via rebar_edit; nothing here checks the reinforcement itself.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from ..calc.column_rebar import ColumnLayout, table
from ..inputs import choices
from . import rebar_edit
from .document import EditorError
from .form import Form
from .grid import make_sheet
from .rebar_canvas import Circle, SectionView, inset, outline

if TYPE_CHECKING:
    from .app import InputEditor

GROUPS = {"柱": (("main", "主鉄筋"), ("hoops", "帯鉄筋"), ("check", "断面照査の条件")),
          "梁": (("main", "配筋"), ("check", "断面照査の条件")),
          "フーチング": (("main", "配筋"),)}
COMMON = ((("materials", "main"), "主鉄筋の材質"), (("materials", "transverse"), "帯鉄筋・スターラップの材質"),
          (("concrete_strength_mpa",), "コンクリート強度"), (("aggregate_max_mm",), "粗骨材の最大寸法 Dmax"),
          (("pure_cover_mm",), "純かぶり"))
COLUMN_FIRST = ((("diameter_mm",), "1段目の径"), (("per_face_count",), "1段目の本数（1つの面）"),
                (("cover_mode",), "芯かぶりの決め方"), (("center_mm",), "芯かぶり（指定）"),
                (("distribution", "mode"), "並べ方"), (("distribution", "edge_center_mm",), "端の芯距離 e"),
                (("distribution", "pitch_mm"), "ピッチ p"), (("endpoints",), "e の位置に鉄筋（等分）"))
BEAM_FIRST = ((("diameter_mm",), "径"), (("count",), "1段目の本数"), (("cover_mode",), "芯かぶりの決め方"),
              (("center_mm",), "芯かぶり（指定）"))
SIDE_BARS = ((("diameter_mm",), "径"), (("per_face_count",), "本数（1つの面）"), (("start_mm",), "開始位置（上面から）"),
             (("pitch_mm",), "ピッチ"), (("stirrup_position",), "スターラップの内側・外側"),
             (("cover_mode",), "芯かぶりの決め方"), (("center_mm",), "芯かぶり（指定）"))
STIRRUPS = ((("diameter_mm",), "径"), (("effective_legs",), "効く脚の本数"), (("pitch_mm",), "間隔"))
FOOTING_FIRST = ((("diameter_mm",), "径"), (("pitch_mm",), "ピッチ"), (("cover_mode",), "芯かぶりの決め方"),
                 (("center_mm",), "芯かぶり（指定）"))
FOOTING_STIRRUPS = ((("diameter_mm",), "径"), (("pitch_mm",), "間隔"), (("distribution_mode",), "幅方向の指定"),
                    (("width_pitch_mm",), "幅方向の間隔"), (("density_per_m",), "幅方向の 1 m 当たり本数"))
LAYER_LABELS = {"per_face_count": "本数（1つの面）", "count": "本数", "pitch_mm": "ピッチ\nmm",
                "clear_gap_mm": "前の段との\nあき mm"}
HOOP_KEYS = ("direction", "diameter_mm", "effective_legs", "pitch_mm", "start_mm", "end_mm")
HOOP_LABELS = ("方向", "径\nmm", "効く脚の\n本数", "間隔\nmm", "開始\nmm", "終了\nmm")
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
        self.layout: ColumnLayout | None = None
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
        self.form = Form(editor, self.inputs)
        self.tables: dict[tuple, Any] = {}
        self._build_inputs()
        title = ttk.Frame(right)
        title.pack(fill="x")
        ttk.Label(title, text="断面図", style="Symbol.TLabel").pack(side="left")
        self.direction_choice = ttk.Combobox(title, values=choices.REBAR_DIRECTIONS, state="readonly", width=7)
        self.direction_choice.set(self.direction)
        self.direction_choice.pack(side="right")
        self.direction_choice.bind("<<ComboboxSelected>>",
                                   lambda event: self.select_direction(self.direction_choice.get()))
        self.section = SectionView(right, on_bar=self.bar_clicked)
        self.section.pack(fill="both", expand=True)
        ttk.Label(right, text="方向別の鉄筋配置表（基準面からの芯位置）", style="Symbol.TLabel").pack(anchor="w", pady=(6, 0))
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
            self.form.properties(self.inputs,
                                 [(self._path("column_hoops", "enclosing_diameter_mm"), "外側の帯鉄筋の径")])
            group = self._group("帯鉄筋の方向別有効本数")
            self._rows_table(group, self._path("column_hoops", "direction_rows"), HOOP_KEYS, HOOP_LABELS)
            ttk.Label(self.inputs, text="方向別の合計有効本数を入力します。本数から帯鉄筋の形状は決めません。",
                      style="Muted.TLabel").pack(anchor="w")
        elif self.member == "柱":
            for direction in choices.REBAR_DIRECTIONS:
                faces = "上面・下面" if direction == "線路" else "左面・右面"
                group = self._group(f"{direction}方向の段（{faces}）")
                prefix = self._path("main_bars", direction)
                self._values(group, prefix, COLUMN_FIRST)
                self._layers(group, prefix, ("per_face_count", "clear_gap_mm"))
        elif self.member == "梁":
            for face in choices.BEAM_FACES:
                group = self._group(f"{face}面の主鉄筋")
                prefix = self._path("faces", face)
                shape = (((("bar_type",), "形状"),) if face == choices.BEAM_FACES[0] else ())
                self._values(group, prefix, (*BEAM_FIRST, *shape))
                self._layers(group, prefix, ("count", "clear_gap_mm"))
            group = self._group("側面筋")
            present = self.editor.document.data["鉄筋"]["梁"]["side_bars"] is not None
            if present:
                self._values(group, self._path("side_bars"), SIDE_BARS)
            ttk.Button(group, text="側面筋なしにする" if present else "側面筋を入れる",
                       command=lambda: self.set_side_bars(not present)).pack(anchor="w", pady=(4, 0))
            self._values(self._group("スターラップ"), self._path("stirrups"), STIRRUPS)
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

    def set_side_bars(self, present: bool) -> bool:
        return self._restructure(lambda: rebar_edit.set_side_bars(self.editor.document.data, present),
                                 "側面筋を変更できません")

    def bar_clicked(self, index: int) -> None:
        if self.layout is None:
            return
        self.selected = ("layer", self.layout.bars[index].rows)
        self.editor.rebar_state["selected"] = self.selected
        self.refresh()

    # preview ------------------------------------------------------------------------------------------------

    def _selected_bar(self, bar: Any) -> bool:
        return self.selected is not None and self.selected[0] == "layer" and bool(set(bar.rows) & set(self.selected[1]))

    def refresh(self) -> None:
        data = self.editor.document.data
        self.layout = None
        rows: list[list[str]] = []
        try:
            polygon = outline(self.member, data, self.direction)
        except EditorError as exc:
            self.section.show([], notice=str(exc))
            self._table(rows)
            return
        if self.member != "柱":
            self.section.show(polygon, caption=f"{self.member}（{self.direction}方向）", notice=OUTLINE_ONLY)
            self._table(rows)
            return
        hoop = self._hoop(polygon)
        try:
            self.layout = rebar_edit.column_preview(data)
        except EditorError as exc:
            self.section.show(polygon, hoop=hoop, caption="X：直角 ／ Y：線路（上面から）", notice=str(exc))
            self._table(rows)
            return
        layout = self.layout
        circles = [Circle(bar.x.value, bar.y.value, bar.diameter.value, self._selected_bar(bar)) for bar in layout.bars]
        notice = f"X：左面、Y：上面からの芯位置（mm）。物理本数 {len(layout.bars)} 本"
        if layout.unmatched:
            notice += (f"\n警告：配置表の変更のうち {len(layout.unmatched)} 件は、元の芯位置・径の鉄筋がないため"
                       "使われていません（計算でも使いません）。")
        self.section.show(polygon, circles, hoop, caption="X：直角 ／ Y：線路（上面から）", notice=notice)
        rows = [[f"{row.center.value:.1f}", f"{row.diameter.value:g}", str(row.count), row.material]
                for row in table(layout.bars, self.direction)]
        self._table(rows)

    def _hoop(self, polygon: list) -> list:
        column = self.editor.document.data["鉄筋"]["柱"]
        pure, diameter = column["pure_cover_mm"], column["column_hoops"]["enclosing_diameter_mm"]
        if not all(isinstance(value, (int, float)) for value in (pure, diameter)):
            return []
        return inset(polygon, pure + diameter / 2)

    def _table(self, rows: list[list[str]]) -> None:
        self.direction_sheet.set_sheet_data(rows, reset_col_positions=False, redraw=True)
        self.direction_sheet.readonly_cells(cells=[(r, c) for r in range(len(rows)) for c in range(4)])

    # the editor's page interface ------------------------------------------------------------------------------

    def input_changed(self) -> None:
        self.refresh()

    def input_moved(self) -> None:
        pass

    def ready_to_leave(self) -> bool:
        return True

    def dispose(self) -> None:
        self._save_state()
