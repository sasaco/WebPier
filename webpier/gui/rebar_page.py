"""The 鉄筋 page: the basic reinforcement of each member, and for the column its layout and detail positions.

Cells are bound through the field table like every input page. The column drawing, the 方向別の鉄筋配置表 and
every layout error come from calc.column_rebar via rebar_edit; nothing here checks the reinforcement itself.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from ..calc.column_rebar import ColumnLayout, table
from ..inputs import choices
from . import rebar_edit
from .column_dialogs import AddBarDialog, Modal, RegenerationDialog, guarded
from .document import EditorError
from .form import Form
from .grid import make_sheet
from .rebar_canvas import Circle, SectionView, inset, outline

if TYPE_CHECKING:
    from .app import InputEditor

LABELS = {
    "diameter_mm": "径\nmm", "material": "材質", "cover_mode": "芯かぶりの\n決め方", "center_mm": "芯かぶり\nmm",
    "clear_gap_mm": "段間のあき\nmm", "face_direction": "対向面", "layer": "段", "per_face_count": "片面本数",
    "endpoints": "端部の鉄筋", "distribution.mode": "面内の配列", "distribution.edge_center_mm": "端部芯距離\nmm",
    "distribution.pitch_mm": "面内ピッチ\nmm", "face": "面", "bar_type": "形状", "count": "本数", "direction": "方向",
    "pitch_mm": "間隔\nmm", "layers": "段数", "stack_order": "重ね順", "columns": "列数", "column_pitch_mm": "列の芯間隔\nmm",
    "start_mm": "開始\nmm", "stirrup_position": "スターラップ\nとの内外", "type": "種類", "sets": "組数",
    "end_mm": "終了\nmm", "legs_mode": "有効脚数の\n決め方", "effective_legs": "有効本数", "distribution_mode": "幅方向の\n指定",
    "width_pitch_mm": "幅方向の\n間隔 mm", "density_per_m": "幅方向の\n密度 本/m", "x_mm": "X mm", "y_mm": "Y mm",
}
GROUPS = {"柱": (("main", "基本配筋"), ("hoops", "帯鉄筋"), ("placement", "詳細修正")),
          "梁": (("main", "基本配筋"), ("bands", "横補強筋"), ("placement", "指定位置")),
          "フーチング": (("main", "基本配筋"), ("bands", "横補強筋"))}
COMMON = ((("materials", "main"), "主鉄筋の材質"), (("materials", "transverse"), "横補強筋の材質"),
          (("concrete_strength_mpa",), "コンクリート強度"), (("pure_cover_mm",), "純かぶり"))
OUTLINE_ONLY = "配筋位置を計算する段階がまだないため、断面の外形だけを表示します。"


def _columns(member: str, family: str) -> tuple[str, ...]:
    if family == "main_rows":
        keys = rebar_edit.ROW_KEYS[(member, family)]
        return (*keys, "distribution.mode", "distribution.edge_center_mm", "distribution.pitch_mm") \
            if member == "柱" else keys
    kind = {"side_rows": "side", "band_rows": "band", "direction_rows": "hoop", "manual_positions": "bar"}[family]
    keys = rebar_edit.ROW_KEYS[(kind, family)]
    return (*keys, *rebar_edit.FOOTING_BAND_KEYS) if family == "band_rows" and member == "フーチング" else keys


class RebarPage:
    busy = False

    def __init__(self, editor: InputEditor, parent: ttk.Frame) -> None:
        self.editor = editor
        state = editor.rebar_state
        self.member: str = state.setdefault("member", "柱")
        self.group: str = state.setdefault("group", "main")
        self.direction: str = state.setdefault("direction", "線路")
        self.selected: tuple[str, int] | None = state.get("selected")
        self.dialog: Modal | None = None
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
        self.tables: dict[str, Any] = {}
        self._build_inputs()
        title = ttk.Frame(right)
        title.pack(fill="x")
        ttk.Label(title, text="断面図", style="Symbol.TLabel").pack(side="left")
        self.source = ttk.Label(title, text="", style="Symbol.TLabel")
        self.source.pack(side="left", padx=8)
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

    def _rows_table(self, family: str, title: str, *, actions: bool = True) -> None:
        group = ttk.LabelFrame(self.inputs, text=title, style="Sheet.TLabelframe", padding=4)
        group.pack(fill="x", pady=(0, 6))
        keys = _columns(self.member, family)
        rows = rebar_edit.rows_of(self.editor.document.data, self.member, family)
        prefix = self._path("column_hoops", "direction_rows") if family == "direction_rows" else self._path(family)
        cells = [[(*prefix, index, *key.split(".")) for key in keys] for index in range(len(rows))]
        sheet = self.form.table(group, [LABELS[key] for key in keys], cells, [78] * len(keys), pack=False,
                                max_height=230, index_width=34)
        sheet.pack(fill="x", expand=True)
        sheet.bind("<<SheetSelect>>", lambda event: self._row_selected(family, sheet), add="+")
        self.tables[family] = sheet
        if actions:
            line = ttk.Frame(group)
            line.pack(fill="x")
            ttk.Button(line, text="行を追加", command=lambda: self.add_row(family)).pack(side="left", padx=2)
            ttk.Button(line, text="選択行を削除", command=lambda: self.delete_row(family)).pack(side="left", padx=2)

    def _build_inputs(self) -> None:
        self.form.properties(self.inputs, [(self._path(*tail), label) for tail, label in COMMON])
        ttk.Label(self.inputs, text="純かぶり：コンクリート面から外側の帯鉄筋の外面まで。空欄は未入力です。",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        if self.group == "main":
            self._rows_table("main_rows", "主鉄筋")
            if self.member != "柱":
                self._rows_table("side_rows", "側面筋")
            else:
                ttk.Label(self.inputs, text="線路：上下の面 ／ 直角：左右の面。片面本数は一つの面の本数です。",
                          style="Muted.TLabel").pack(anchor="w")
        elif self.group == "hoops":
            self.form.properties(self.inputs, [(self._path("column_hoops", "enclosing_diameter_mm"), "外側の帯鉄筋の径")])
            self._rows_table("direction_rows", "帯鉄筋の方向別有効本数")
            ttk.Label(self.inputs, text="方向別の合計有効本数を入力します。本数から帯鉄筋の形状は決めません。",
                      style="Muted.TLabel").pack(anchor="w")
        elif self.group == "bands":
            self._rows_table("band_rows", "スターラップ・帯鉄筋")
        elif self.member == "柱":
            self._placement()
        else:
            self.form.properties(self.inputs, [(self._path("position_mode"), "配置方法")])
            self._rows_table("manual_positions", "指定位置 mm")

    def _placement(self) -> None:
        column = self.editor.document.data["鉄筋"]["柱"]
        detailed = column["position_mode"] == choices.POSITION_MANUAL
        ttk.Label(self.inputs, text="X は左面、Y は上面からの芯位置（mm）。自動配置をコピーすると、生成元の基本条件も"
                  "一緒に保存し、基本条件が変わったかを表示します。", style="Muted.TLabel", wraplength=520).pack(anchor="w")
        actions = ttk.Frame(self.inputs)
        actions.pack(fill="x", pady=4)
        self.placement_buttons = {}
        for name, label, command in (("regenerate", "自動配置をコピー（再配置）", self.begin_regeneration),
                                     ("auto", "自動へ戻す", lambda: self.begin_regeneration(to_auto=True)),
                                     ("detail", "詳細へ戻る", self.use_detail),
                                     ("add", "鉄筋を追加", self.begin_add_bar),
                                     ("delete", "選択した鉄筋を削除", self.delete_bar)):
            button = ttk.Button(actions, text=label, command=command)
            button.pack(side="left", padx=2)
            self.placement_buttons[name] = button
        self.placement_buttons["auto"].state(["!disabled" if detailed else "disabled"])
        kept = not detailed and bool(column["manual_positions"])
        self.placement_buttons["detail"].state(["!disabled" if kept else "disabled"])
        if detailed:
            self._rows_table("manual_positions", "使用中の詳細位置 mm", actions=False)
        else:
            ttk.Label(self.inputs, text="使用中：自動配置（位置を直すときは「自動配置をコピー」か「鉄筋を追加」）",
                      style="Symbol.TLabel").pack(anchor="w", pady=4)

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

    def _row_selected(self, family: str, sheet: Any) -> None:
        current = sheet.get_currently_selected()
        if current:
            self.selected = (family, current.row)
            self.editor.rebar_state["selected"] = self.selected
            self.refresh()

    def _restructure(self, change: Any, title: str) -> bool:
        if self.dialog is not None or not self.editor.ready_to_restructure():
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

    def add_row(self, family: str) -> bool:
        def add() -> None:
            self.selected = (family, rebar_edit.add_row(self.editor.document.data, self.member, family))
        return self._restructure(add, "行を追加できません")

    def delete_row(self, family: str) -> bool:
        if self.selected is None or self.selected[0] != family:
            return False
        index = self.selected[1]
        self.selected = None
        return self._restructure(lambda: rebar_edit.delete_row(self.editor.document.data, self.member, family, index),
                                 "行を削除できません")

    def use_detail(self) -> bool:
        return self._restructure(lambda: rebar_edit.use_mode(self.editor.document.data, choices.POSITION_MANUAL),
                                 "詳細位置へ戻せません")

    def delete_bar(self) -> bool:
        if self.selected is None or self.selected[0] != "manual_positions":
            return False
        index = self.selected[1]
        self.selected = None
        return self._restructure(lambda: rebar_edit.delete_bar(self.editor.document.data, index), "鉄筋を削除できません")

    def _dialog_closed(self) -> None:
        self.dialog = None

    def _open(self, build: Any, title: str) -> bool:
        if self.dialog is not None or not self.editor.ready_to_restructure():
            return False
        try:
            self.dialog = build()
            self.dialog.present()
        except (EditorError, tk.TclError) as exc:
            if self.dialog is not None:
                self.dialog.close()
            messagebox.showerror(title, str(exc), parent=self.editor.root)
            return False
        return True

    def begin_regeneration(self, *, to_auto: bool = False) -> bool:
        data = self.editor.document.data

        def apply(shown: rebar_edit.Comparison) -> str | None:
            def change() -> None:
                if not to_auto:
                    rebar_edit.copy_automatic(data, shown)
                elif rebar_edit.comparison(data) != shown:
                    raise EditorError("入力が変更されています。比較し直してください")
                else:
                    rebar_edit.use_mode(data, choices.POSITION_BASIC)
            problem = guarded(change)
            if problem is None:
                self.editor.root.after_idle(self._rebuild)
            return problem

        def build() -> RegenerationDialog:
            shown = rebar_edit.comparison(data)
            width, height = (value.value * 1000 for value in rebar_edit.section(data))
            return RegenerationDialog(self.editor.root, shown, (width, height), to_auto=to_auto, apply=apply,
                                      on_close=self._dialog_closed)

        return self._open(build, "再配置できません")

    def begin_add_bar(self) -> bool:
        data = self.editor.document.data

        def apply(bar: dict[str, Any]) -> str | None:
            problem = guarded(lambda: rebar_edit.add_bar(data, bar))
            if problem is None:
                self.editor.root.after_idle(self._rebuild)
            return problem

        def build() -> AddBarDialog:
            rebar_edit.column_preview(data)  # the automatic layout must be complete before it is copied
            return AddBarDialog(self.editor.root, data["鉄筋"]["柱"]["materials"]["main"], apply=apply,
                                on_close=self._dialog_closed)

        return self._open(build, "鉄筋を追加できません")

    def bar_clicked(self, index: int) -> None:
        if self.layout is None or self.member != "柱":
            return
        bar = self.layout.bars[index]
        if self.layout.manual is not None:
            positions = self.editor.document.data["鉄筋"]["柱"]["manual_positions"]
            match = next(i for i, row in enumerate(positions)
                         if (row["x_mm"], row["y_mm"]) == (bar.x.value, bar.y.value))
            self.selected = ("manual_positions", match)
        elif bar.rows:
            self.selected = ("main_rows", bar.rows[0])
        self.editor.rebar_state["selected"] = self.selected
        self.refresh()

    # preview ------------------------------------------------------------------------------------------------

    def _selected_bar(self, bar: Any) -> bool:
        if self.selected is None:
            return False
        family, index = self.selected
        if family == "main_rows":
            return index in bar.rows
        if family == "manual_positions" and self.layout is not None and self.layout.manual is not None:
            positions = self.editor.document.data["鉄筋"]["柱"]["manual_positions"]
            row = positions[index] if index < len(positions) else {}
            return (row.get("x_mm"), row.get("y_mm")) == (bar.x.value, bar.y.value)
        return False

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
            self.source.configure(text="")
            self.section.show(polygon, caption=f"{self.member}（{self.direction}方向）", notice=OUTLINE_ONLY)
            self._table(rows)
            return
        hoop = self._hoop(polygon)
        try:
            self.layout = rebar_edit.column_preview(data)
        except EditorError as exc:
            self.source.configure(text="")
            self.section.show(polygon, hoop=hoop, caption="X：直角 ／ Y：線路（上面から）", notice=str(exc))
            self._table(rows)
            return
        layout = self.layout
        circles = [Circle(bar.x.value, bar.y.value, bar.diameter.value, self._selected_bar(bar)) for bar in layout.bars]
        if layout.manual is None:
            source, notice = "使用中：自動配置", "X：左面、Y：上面からの芯位置（mm）。"
        elif layout.manual_basis_current:
            source, notice = "使用中：詳細位置", "詳細位置は生成時の基本条件と一致しています。"
        else:
            source, notice = "使用中：詳細位置", "基本条件の変更は詳細位置に反映されていません（「再配置」で置き換えます）。"
        self.source.configure(text=source)
        self.section.show(polygon, circles, hoop, caption="X：直角 ／ Y：線路（上面から）",
                          notice=f"{notice}　物理本数 {len(layout.bars)} 本")
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
        return self.dialog is None

    def dispose(self) -> None:
        self._save_state()
        if self.dialog is not None:
            self.dialog.close()
