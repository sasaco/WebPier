"""Detached reinforcement forms, using the editor's shared save transaction."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import math
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter import font as tkfont
from typing import Any

from . import rebar_model as model
from .editor_grid import SheetCell, make_sheet, pending_dirty
from .editor_model import EditorError, value_text


MAIN_COLUMNS = {
    "柱": [("face_direction", "対向面"), ("diameter_mm", "径 mm"), ("per_face_count", "片面本数")],
    "梁": [("face", "面"), ("bar_type", "形状"), ("diameter_mm", "径 mm"), ("count", "本数")],
    "フーチング": [("direction", "鉄筋方向"), ("face", "面"), ("diameter_mm", "径 mm"),
                 ("pitch_mm", "間隔 mm")],
}
SIDE_COLUMNS = [("diameter_mm", "径 mm"), ("per_face_count", "片面本数"),
                ("columns", "列数")]
BAND_COLUMNS = [("type", "種類"), ("direction", "方向"), ("diameter_mm", "径 mm"),
                ("sets", "組数"), ("pitch_mm", "縦間隔 mm")]
MANUAL_COLUMNS = [("x_mm", "X mm"), ("y_mm", "Y mm"), ("diameter_mm", "径 mm"), ("material", "材質")]


class RebarView:
    def __init__(self, app, parent):
        self.app, self.parent = app, parent
        self.member = "柱"
        self.group = "main"
        self.direction = "線路"
        self.selected = ("main_rows", 0)
        self.cells = {}
        self._initial_text = {}
        self._grids = []
        self._updating = False
        self._disposed = False
        self.column_editor = None
        self._leg_raw = {}
        self._leg_mode = {}
        self.preview_geometry = None
        self.preview_bars = []
        self.preview_lines = []
        self.preview_error = ""
        self._preview_candidate = deepcopy({})
        self.effective_centers = []
        self._baseline = model.load_member(app.document.data, self.member)
        self._draft = deepcopy(self._baseline)
        self._render_base = deepcopy(self._draft)
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="both", expand=True)
        bar = ttk.Frame(self.frame)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="部材", style="Symbol.TLabel").pack(side="left")
        self.member_var = tk.StringVar(master=parent, value=self.member)
        choice = ttk.Combobox(bar, textvariable=self.member_var, values=model.MEMBERS,
                              state="readonly", width=12)
        choice.pack(side="left", padx=(8, 18))
        choice.bind("<<ComboboxSelected>>", self._member_selected)
        self.group_buttons = {}
        for name, title in (("main", "基本配筋"), ("bands", "横補強筋"), ("placement", "配置確認・調整")):
            button = ttk.Button(bar, text=title, command=lambda name=name: self.select_group(name))
            button.pack(side="left", padx=3)
            self.group_buttons[name] = button
        self.content = ttk.Frame(self.frame)
        self.content.pack(fill="both", expand=True)
        self._build_group()

    @property
    def draft(self):
        try:
            return self.read_candidate()
        except EditorError:
            return deepcopy(self._draft)

    @property
    def dirty(self):
        if self._disposed:
            return False
        if any(pending_dirty(sheet) for sheet in self._grids):
            return True
        try:
            return self.read_candidate() != self._baseline
        except EditorError:
            return True

    def _member_selected(self, event=None):
        if not self.select_member(self.member_var.get()):
            self.member_var.set(self.member)

    @property
    def modal_open(self):
        return self.member == "柱" and self.column_editor is not None and self.column_editor.dialog is not None

    def select_member(self, name):
        if name not in model.MEMBERS or self.app._calculation_busy or self.modal_open:
            return False
        try:
            model.load_member(self.app.document.data, name)
        except EditorError as exc:
            self.member_var.set(self.member)
            messagebox.showerror("部材を表示できません", str(exc), parent=self.app.root)
            return False
        if not self.app.flush_fields():
            return False
        self.member = name
        self.member_var.set(name)
        self._baseline = model.load_member(self.app.document.data, name)
        self._draft = deepcopy(self._baseline)
        self.selected = ("main_rows", 0)
        self._build_group()
        return True

    def select_group(self, name):
        if name not in ("main", "bands", "placement") or self.app._calculation_busy or self.modal_open:
            return False
        if not self.app.flush_fields():
            return False
        self.group = name
        self.selected = (("band_rows", 0) if name == "bands" else
                         ("manual_positions", 0) if name == "placement" else ("main_rows", 0))
        self._build_group()
        return True

    def select_direction(self, name):
        if name not in model.DIRECTIONS or self.app._calculation_busy or self.modal_open:
            return False
        self.app._commit_grid_editors()
        try:
            model.validate_member(self.member, self.read_candidate())
        except EditorError:
            return False
        self.direction = name
        if hasattr(self, "direction_var"):
            self.direction_var.set(name)
        self.refresh_preview()
        return True

    def _clear_group(self):
        for sheet in self._grids:
            if sheet in self.app.grids:
                self.app.grids.remove(sheet)
        self._grids.clear()
        for widget in self.content.winfo_children():
            widget.destroy()
        self.cells.clear()
        self._initial_text.clear()

    def _value(self, path, default=None):
        owner = self._render_base
        try:
            for key in path:
                owner = owner[key]
            return owner
        except (KeyError, IndexError, TypeError):
            return default

    def _variable(self, path, default=None):
        value = self._value(path, default)
        control = tk.StringVar(master=self.frame, value=value_text(value))
        self.cells[path] = control
        self._initial_text[path] = control.get()
        control.trace_add("write", lambda *args, path=path: self._cell_changed(path))
        return control

    def _common(self):
        frame = ttk.Frame(self.content)
        frame.pack(fill="x", pady=(0, 6))
        for index, (path, title, width) in enumerate((
            (("materials", "main"), "主筋材質", 10),
            (("materials", "transverse"), "横補強筋材質", 10),
            (("concrete_strength_mpa",), "強度 N/mm²", 7),
            (("pure_cover_mm",), "純かぶり mm", 7),
        )):
            box = ttk.Frame(frame)
            box.pack(side="left", padx=(0, 12))
            ttk.Label(box, text=title, style="Muted.TLabel").pack(anchor="w")
            variable = self._variable(path)
            if path[0] == "materials":
                ttk.Combobox(box, textvariable=variable, values=("", "SD295", "SD345", "SD390", "SD490"), width=width).pack()
            else:
                ttk.Entry(box, textvariable=variable, width=width).pack()
        ttk.Label(self.content, text="純かぶり：コンクリート面から外帯筋の外面まで。寸法は mm。空欄＝未入力、0＝ゼロ。",
                  style="Muted.TLabel", wraplength=680).pack(anchor="w", pady=(0, 6))

    def _row_controls(self, family):
        defaults = model.blank_row(self.member, family)
        for index, row in enumerate(self._render_base.get(family, [])):
            for key, default in defaults.items():
                self._variable((family, index, key), default)
            if family == "band_rows":
                self._leg_raw[index] = value_text(row.get("effective_legs"))
                self._leg_mode[index] = row.get("legs_mode", "自動")

    def _table(self, family, columns, title, *, row_actions=True):
        self._row_controls(family)
        group = ttk.LabelFrame(self.inputs, text=title, style="Sheet.TLabelframe", padding=4)
        group.pack(fill="x", pady=(0, 6))
        paths = [[(family, index, key) for key, _ in columns]
                 for index in range(len(self._render_base.get(family, [])))]
        data = [[self.cells[path].get() for path in row] for row in paths]
        column_widths = {"face": 50, "bar_type": 75, "diameter_mm": 62, "count": 66,
                         "per_face_count": 78, "face_direction": 74, "direction": 68,
                         "pitch_mm": 78, "sets": 58, "type": 68, "columns": 58,
                         "x_mm": 72, "y_mm": 72, "material": 86}
        widths = [column_widths.get(key, 70) for key, _ in columns]
        sheet = make_sheet(group, [title for _, title in columns], data, widths,
                           max_height=210 if family != "side_rows" else 120, index_width=34)
        sheet.pack(fill="x", expand=True)
        self._grids.append(sheet)
        self.app.grids.append(sheet)
        for r, row in enumerate(paths):
            for c, path in enumerate(row):
                key = path[-1]
                control = SheetCell(sheet, r, c, lambda path=path: self._cell_changed(path))
                self.cells[path] = control
                sheet.readonly_cells(r, c, readonly=False)
                sheet.highlight_cells(r, c, bg="#ffffff")
                if key in model.ENUM_FIELDS:
                    sheet.dropdown((r, c), values=["", *model.ENUM_FIELDS[key]],
                                   edit_data=False, state="normal", validate_input=False)
        sheet.bind("<<SheetModified>>", lambda event: self._cell_changed(None), add="+")
        sheet.bind("<<SheetSelect>>", lambda event: self._sheet_selected(sheet, family), add="+")
        if row_actions and not (self.member == "フーチング" and family == "main_rows"):
            actions = ttk.Frame(group)
            actions.pack(fill="x")
            ttk.Button(actions, text="行を追加", command=lambda: self.add_row(family)).pack(side="left", padx=2)
            ttk.Button(actions, text="選択行を削除", command=lambda: self.delete_row(family, self.selected[1]) if self.selected[0] == family else None).pack(side="left", padx=2)
        return sheet

    def _build_group(self) -> None:
        self.group_buttons["bands"].configure(text="帯鉄筋" if self.member == "柱" else "横補強筋")
        self.group_buttons["placement"].configure(text="詳細修正" if self.member == "柱" else "配置確認・調整")
        if self.member == "柱":
            if self.column_editor is None:
                from .column_rebar_ui import ColumnRebarEditor
                self.column_editor = ColumnRebarEditor(self)
            self.column_editor.build()
            return
        self._updating = True
        self._clear_group()
        self._render_base = deepcopy(self._draft)
        self._leg_raw.clear()
        self._leg_mode.clear()
        self._common()
        split = ttk.Panedwindow(self.content, orient="horizontal")
        split.pack(fill="both", expand=True)
        input_pane = ttk.Frame(split, width=400)
        preview = ttk.Frame(split, width=285, padding=(8, 0, 0, 0))
        split.add(input_pane, weight=1)
        split.add(preview, weight=1)
        input_pane.rowconfigure(0, weight=1)
        input_pane.columnconfigure(0, weight=1)
        self.input_canvas = tk.Canvas(input_pane, width=390, height=180,
                                      highlightthickness=0, background="white")
        scroll = ttk.Scrollbar(input_pane, orient="vertical", command=self.input_canvas.yview)
        self.input_canvas.configure(yscrollcommand=scroll.set)
        self.input_canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.inputs = ttk.Frame(self.input_canvas, padding=(0, 0, 5, 8))
        self.input_window = self.input_canvas.create_window((0, 0), window=self.inputs, anchor="nw")
        self.inputs.bind("<Configure>", lambda event: self.input_canvas.configure(scrollregion=self.input_canvas.bbox("all")))
        self.input_canvas.bind("<Configure>", self._input_resized)
        self._build_group_inputs()
        self.details = ttk.LabelFrame(self.inputs, text="選択行の配置条件", style="Sheet.TLabelframe", padding=6)
        self.details.pack(fill="x", pady=(6, 0))
        title = ttk.Frame(preview)
        title.pack(fill="x")
        ttk.Label(title, text="断面方向" if self.member == "フーチング" else "実配筋の断面図", style="Symbol.TLabel").pack(side="left")
        self.source_badge = ttk.Label(title, text="使用中：基本配筋", style="Symbol.TLabel")
        self.source_badge.pack(side="left", padx=(8, 0))
        if self.member == "フーチング":
            self.direction_var = tk.StringVar(master=self.frame, value=self.direction)
            selector = ttk.Combobox(title, textvariable=self.direction_var, values=model.DIRECTIONS, state="readonly", width=7)
            selector.pack(side="right")
            selector.bind("<<ComboboxSelected>>", lambda event: self.select_direction(self.direction_var.get()))
        self.preview_canvas = tk.Canvas(preview, width=280, height=180, background="#f8fafc", highlightthickness=1, highlightbackground="#dbe3ed")
        self.preview_canvas.pack(fill="both", expand=True, pady=4)
        self.preview_canvas.bind("<Configure>", lambda event: self._draw_preview())
        self.notice = tk.Label(preview, text="", height=3, anchor="nw", justify="left",
                               font=("Yu Gothic UI", 9), foreground="#5d6f82", background="white", wraplength=280)
        self.notice.pack(fill="x")
        self._render_details()
        self._updating = False
        self.refresh_preview()
        self.app.root.update_idletasks()
        self._input_resized()

    def _build_group_inputs(self) -> None:
        if self.group == "main":
            self._table("main_rows", MAIN_COLUMNS[self.member], "主筋 — 行を選ぶと配置条件を調整できます")
            if self.member == "梁":
                ttk.Label(self.inputs, text="同じ段の全本数を等間隔に配置（形状は交互、残りは順に配置）", style="Muted.TLabel", wraplength=360).pack(anchor="w")
                self._table("side_rows", SIDE_COLUMNS, "側面筋 — 本数は片側の合計")
        elif self.group == "bands":
            self._table("band_rows", BAND_COLUMNS, "スターラップ・帯鉄筋")
            ttk.Label(self.inputs, text="1組＝2脚相当。有効脚数は自動／指定を明示します。組数から鉄筋の形状は推定しません。",
                      style="Muted.TLabel", wraplength=360).pack(anchor="w")
            if self.member == "フーチング":
                ttk.Label(self.inputs, text="幅方向：配置間隔または密度 ／ 縦方向：スターラップ間隔（別の寸法）",
                          style="Muted.TLabel", wraplength=360).pack(anchor="w")
        else:
            modebar = ttk.Frame(self.inputs)
            modebar.pack(fill="x", pady=4)
            ttk.Label(modebar, text="配置方法").pack(side="left")
            variable = self._variable(("position_mode",), "基本")
            state = "disabled" if self.member == "フーチング" else "readonly"
            ttk.Combobox(modebar, textvariable=variable, values=("基本", "指定"), state=state, width=10).pack(side="left", padx=8)
            button = ttk.Button(modebar, text="基本配置をコピー", command=self.copy_basic_positions)
            button.pack(side="left")
            if self.member == "フーチング":
                button.state(["disabled"])
                ttk.Label(self.inputs, text="フーチングは方向別の芯かぶり・重ね順・段間のあきで調整します。2方向を一つのXY配列にはまとめません。",
                          style="Muted.TLabel", wraplength=360).pack(anchor="w")
            else:
                ttk.Label(self.inputs, text="コピー後も「基本」のままです。「指定」を選ぶと入力したXYを使用します。Xは左面、Yは上面からの芯位置。基本配筋と指定位置は両方保存します。",
                          style="Muted.TLabel", wraplength=360).pack(anchor="w")
                self._table("manual_positions", MANUAL_COLUMNS, "指定する物理位置 mm")

    def _input_resized(self, event=None):
        if self._disposed or not hasattr(self, "input_canvas") or not self.input_canvas.winfo_exists():
            return
        width = max(150, self.input_canvas.winfo_width())
        self.input_canvas.itemconfigure(self.input_window, width=width)
        for sheet in self._grids:
            sheet.configure(width=max(150, width - 16))
        def wrap(widget):
            if isinstance(widget, ttk.Label):
                fixed = widget.cget("width")
                if fixed and int(fixed) > 0:
                    self._fit_condition_label(widget)
                else:
                    widget.configure(wraplength=max(110, width - 26))
            for child in widget.winfo_children():
                if not str(child).startswith(tuple(str(sheet) for sheet in self._grids)):
                    wrap(child)
        wrap(self.inputs)

    def _fit_condition_label(self, label):
        """Use this label's own box; height changes do not resize its width."""
        if self._disposed or not label.winfo_exists():
            return
        width = label.winfo_width()
        if width <= 1:
            width = label.winfo_reqwidth()
        if width <= 1:
            specification = label.cget("font") or ttk.Style(self.app.root).lookup(label.winfo_class(), "font") or "TkDefaultFont"
            font = tkfont.Font(root=self.app.root, font=specification)
            width = font.measure("0" * max(1, int(label.cget("width") or 1)))
        target = max(1, width - 2)
        if float(label.cget("wraplength") or 0) != target:
            label.configure(wraplength=target)

    def reveal_cell(self, sheet, row, column):
        if self._disposed or not sheet.winfo_exists():
            return
        sheet.see(row, column)
        self.app.root.update_idletasks()
        bounds = SheetCell(sheet, row, column, lambda: None).bounds()
        viewport = self.input_canvas
        top, bottom = viewport.winfo_rooty(), viewport.winfo_rooty() + viewport.winfo_height()
        if bounds[1] < top or bounds[3] > bottom:
            offset = bounds[1] - self.inputs.winfo_rooty() - 10 if bounds[1] < top else bounds[3] - self.inputs.winfo_rooty() - viewport.winfo_height() + 10
            viewport.yview_moveto(max(0, offset) / max(1, self.inputs.winfo_height()))

    def wheel(self, event):
        if self._disposed or event.state & (0x0001 | 0x0004):
            return
        widget = self.app.root.winfo_containing(event.x_root, event.y_root)
        if widget is None or not str(widget).startswith(str(self.input_canvas)):
            return
        for sheet in self._grids:
            if str(widget).startswith(str(sheet)):
                if widget not in (sheet.MT, sheet.CH, sheet.RI, sheet.TL):
                    return
                first, last = sheet.MT.yview()
                if last - first < .999:
                    return
        units = -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        self.input_canvas.yview_scroll(units, "units")

    def _sheet_selected(self, sheet, family):
        selected = sheet.get_currently_selected()
        if selected and not self._updating:
            self.select_row(family, selected.row)
            self.reveal_cell(sheet, selected.row, selected.column)

    def select_row(self, family, index):
        if self._disposed or self.app._calculation_busy:
            return
        self.selected = (family, index)
        self._render_details()
        self._draw_preview()

    def _render_details(self):
        if (self.member == "柱" and self.column_editor is not None
                and (self.group != "bands" or "column_hoops" in self._render_base)):
            self.column_editor.render_details()
            return
        if not hasattr(self, "details"):
            return
        for widget in self.details.winfo_children():
            widget.destroy()
        family, index = self.selected
        rows = self._render_base.get(family, [])
        self._detail_widgets = {}
        # The dedicated column review lives outside this legacy detail panel.
        if self.member != "柱":
            self._derived_sheet = None
        if index < 0 or index >= len(rows):
            ttk.Label(self.details, text="表の行を選択してください。", style="Muted.TLabel").pack(anchor="w")
            if self.member == "柱" and self.group == "placement":
                self._directional_review()
            return
        ttk.Label(self.details, text=f"{model.ROW_LABELS[family]} [{index + 1}]", style="Symbol.TLabel").pack(anchor="w", pady=(0, 5))
        fields = {
            "main_rows": (["layers", "stack_order"] if self.member == "フーチング" else ["layer"]) + ["material", "cover_mode", "center_mm", "clear_gap_mm"] + (["endpoints"] if self.member == "柱" else []),
            "side_rows": ["start_mm", "pitch_mm", "stirrup_position", "column_pitch_mm", "cover_mode", "center_mm", "material"],
            "band_rows": ["legs_mode", "effective_legs", "material"] + (["distribution_mode", "width_pitch_mm", "density_per_m"] if self.member == "フーチング" else ["start_mm", "end_mm"]),
            "manual_positions": [],
        }[family]
        for key in fields:
            path = (family, index, key)
            if path not in self.cells:
                continue
            row = ttk.Frame(self.details)
            row.pack(fill="x", pady=2)
            label = model.FIELD_LABELS.get(key, key)
            if key == "density_per_m":
                label += " 組/m"
            elif key.endswith("_mm"):
                label += " mm"
            caption = ttk.Label(row, text=label, width=18)
            caption.pack(side="left")
            caption.bind("<Configure>", lambda event, caption=caption: self._fit_condition_label(caption))
            control = self.cells[path]
            if isinstance(control, SheetCell):
                continue
            if key in model.ENUM_FIELDS:
                widget = ttk.Combobox(row, textvariable=control, values=("", *model.ENUM_FIELDS[key]), state="readonly", width=10)
            else:
                widget = ttk.Entry(row, textvariable=control, width=12)
            widget.pack(side="left", fill="x", expand=True)
            self._detail_widgets[path] = widget
        self.effective_label = ttk.Label(self.details, text="", style="Muted.TLabel", wraplength=300)
        self.effective_label.pack(anchor="w", pady=6)
        if self.member == "柱" and self.group == "placement":
            self._directional_review()
        self.band_schematic = None
        if family == "band_rows" and self.member in ("柱", "フーチング"):
            self.band_schematic = tk.Canvas(self.details, height=120, width=280, background="white", highlightthickness=0)
            self.band_schematic.pack(fill="x")
        if not self._updating:
            self._refresh_legs(self.draft)
            self._input_resized()

    def _directional_review(self):
        ttk.Label(self.details, text="計算に使う段配置を確認", style="Symbol.TLabel").pack(anchor="w", pady=(5, 3))
        bar = ttk.Frame(self.details)
        bar.pack(fill="x")
        self.direction_var = tk.StringVar(master=self.frame, value=self.direction)
        selector = ttk.Combobox(bar, textvariable=self.direction_var, values=model.DIRECTIONS, state="readonly", width=8)
        selector.pack(side="left")
        selector.bind("<<ComboboxSelected>>", lambda event: self.select_direction(self.direction_var.get()))
        self._derived_total = ttk.Label(bar, text="", style="Muted.TLabel")
        self._derived_total.pack(side="left", padx=8)
        self._derived_sheet = make_sheet(self.details, ["芯位置 mm", "径 mm", "本数", "材質"], [], [88, 65, 55, 85], max_height=170)
        self._derived_sheet.pack(fill="x", pady=3)

    def _cell_changed(self, path):
        if self._updating or self._disposed:
            return
        if path and path[0] == "band_rows" and path[-1] == "legs_mode":
            index = path[1]
            previous = self._leg_mode.get(index, "自動")
            current = self.cells[path].get()
            field = self.cells.get(("band_rows", index, "effective_legs"))
            if field is not None:
                if previous == "指定":
                    self._leg_raw[index] = field.get()
                if current == "指定":
                    self._updating = True
                    field.set(self._leg_raw.get(index, ""))
                    self._updating = False
            self._leg_mode[index] = current
        self.refresh_preview()
        self.app._changed()

    @staticmethod
    def _set_local(candidate, path, value):
        owner = candidate
        for key in path[:-1]:
            if isinstance(key, int):
                owner = owner[key]
            else:
                owner = owner.setdefault(key, {})
        owner[path[-1]] = value

    def _parse(self, path, text):
        numeric = path[-1] in model.NUMERIC_FIELDS or path[-1] in ("edge_center_mm", "enclosing_diameter_mm")
        text = text.strip() if numeric else text
        if text == "":
            return None
        if not numeric:
            return text
        try:
            value = float(text)
        except (ValueError, OverflowError) as exc:
            raise EditorError(f"{self.member} / {model.FIELD_LABELS.get(path[-1], path[-1])}: 数値または空欄を入力してください") from exc
        return int(value) if math.isfinite(value) and value.is_integer() else value

    def read_candidate(self):
        if self.member == "柱" and self.column_editor is not None:
            return self.column_editor.read_candidate()
        return self._read_candidate_fields()

    def _read_candidate_fields(self, skip_families=()):
        candidate = deepcopy(self._render_base)
        for path, control in self.cells.items():
            if path[0] in skip_families:
                continue
            if path[0] == "band_rows" and path[-1] == "effective_legs":
                continue
            text = control.get()
            if text != self._initial_text[path]:
                self._set_local(candidate, path, self._parse(path, text))
        for index, row in enumerate(candidate.get("band_rows", [])):
            path = ("band_rows", index, "effective_legs")
            if path not in self.cells:
                continue
            text = self.cells[path].get() if row.get("legs_mode", "自動") == "指定" else self._leg_raw.get(index, "")
            original = value_text(self._render_base.get("band_rows", [])[index].get("effective_legs"))
            if text != original:
                row["effective_legs"] = self._parse(path, text)
        return candidate

    def prepare(self, document):
        if self.member == "柱" and self.column_editor is not None and self.column_editor.dialog is not None:
            raise EditorError("再配置の確認を適用または取消してから保存してください")
        candidate = self.read_candidate()
        model.validate_member(self.member, candidate)
        for direction in model.DIRECTIONS if self.member == "フーチング" else (self.direction,):
            try:
                geometry = model.section_geometry(document, self.member, direction)
            except model.GeometryIncomplete:
                continue
            model.member_preview(self.member, candidate, geometry, direction)
        return candidate

    def accept(self):
        self._baseline = model.load_member(self.app.document.data, self.member)
        self._draft = deepcopy(self._baseline)
        self._render_base = deepcopy(self._baseline)
        for path, control in self.cells.items():
            if path[0] == "band_rows" and path[-1] == "effective_legs":
                continue
            self._initial_text[path] = control.get()
        for index, row in enumerate(self._baseline.get("band_rows", [])):
            self._leg_raw[index] = value_text(row.get("effective_legs"))
        if self.member == "柱" and self.column_editor is not None:
            self.column_editor.accept()
        self.refresh_preview()

    def refresh_preview(self):
        if self._disposed or not hasattr(self, "preview_canvas"):
            return
        self.preview_bars, self.preview_lines, self.preview_error = [], [], ""
        self._preview_candidate = {}
        self.effective_centers = []
        try:
            self.preview_geometry = model.section_geometry(self.app.document.data, self.member, self.direction)
        except EditorError as exc:
            self.preview_geometry = None
            self.preview_error = str(exc)
        try:
            candidate = self.read_candidate()
            model.validate_member(self.member, candidate)
            self._preview_candidate = deepcopy(candidate)
            self._draft = deepcopy(candidate)
            if self.preview_geometry is not None:
                bars, lines, centers, warnings = model.member_preview(self.member, candidate, self.preview_geometry, self.direction)
                self.preview_bars, self.preview_lines, self.effective_centers = bars, lines, centers
                self.preview_error = "\n".join(dict.fromkeys(warnings))
            self._refresh_legs(candidate)
            if self.member == "柱" and self.column_editor is not None:
                self.column_editor.sync_positions(candidate)
        except EditorError as exc:
            self.preview_error = str(exc)
        self._draw_preview()

    def _draw_band_schematic(self):
        diagram = getattr(self, "band_schematic", None)
        if diagram is None or not diagram.winfo_exists() or self.selected[0] != "band_rows":
            return
        diagram.delete("all")
        index = self.selected[1]
        rows = self._preview_candidate.get("band_rows", [])
        if index >= len(rows):
            return
        row = rows[index]
        tags = ("transverse", "selected", f"rebar:band_rows:{index}")
        if row.get("sets") == 0:
            diagram.create_text(12, 28, anchor="w", text="0組：この横補強筋は無効（入力は保持）", font=("Yu Gothic UI", 9), fill="#1674bf", tags=tags)
            return
        if self.member == "柱":
            height = (self.preview_geometry or {}).get("member_height_mm")
            start, end = row.get("start_mm"), row.get("end_mm")
            diagram.create_line(35, 10, 35, 100, fill="#94a3b8", width=7)
            if height and start is not None and end is not None:
                a, b = 100 - 90 * start / height, 100 - 90 * end / height
                diagram.create_line(35, a, 35, b, fill="#1674bf", width=9, tags=tags)
                diagram.create_text(55, 30, anchor="w", text=f"柱高さ {height:g} mm（下端から）", font=("Yu Gothic UI", 8))
            diagram.create_text(55, 55, anchor="w", text=f"開始 {value_text(start) or '未入力'} ～ 終了 {value_text(end) or '未入力'} mm", font=("Yu Gothic UI", 8), fill="#1674bf", tags=tags)
            diagram.create_text(55, 80, anchor="w", text=f"縦方向間隔 {value_text(row.get('pitch_mm')) or '未入力'} mm", font=("Yu Gothic UI", 8))
        else:
            width = (self.preview_geometry or {}).get("width_mm")
            density = row.get("density_per_m")
            pitch = row.get("width_pitch_mm") if row.get("distribution_mode", "間隔") == "間隔" else 1000 / density if density else None
            count = min(16, int(width / pitch) + 1) if width and pitch and width / pitch < 100000 else 5
            for position in range(max(1, count)):
                x = 20 + 170 * position / max(1, count - 1)
                diagram.create_line(x, 20, x, 55, fill="#1674bf", width=2, tags=tags)
            description = (f"幅間隔 {value_text(row.get('width_pitch_mm')) or '未入力'} mm" if row.get("distribution_mode", "間隔") == "間隔"
                           else f"幅密度 {value_text(density) or '未入力'} 組/m")
            diagram.create_line(20, 65, 190, 65, arrow="both", fill="#1674bf", tags=tags)
            diagram.create_text(105, 79, text=description, font=("Yu Gothic UI", 8), fill="#1674bf", tags=tags)
            diagram.create_line(215, 20, 215, 55, arrow="both", fill="#1674bf", tags=tags)
            diagram.create_text(244, 38, text=f"縦間隔\n{value_text(row.get('pitch_mm')) or '未入力'} mm", font=("Yu Gothic UI", 8), tags=tags)
            diagram.create_text(20, 105, anchor="w", text="配置方向の模式図（曲げ形状は未指定）", font=("Yu Gothic UI", 8), fill="#64748b")

    def _refresh_legs(self, candidate):
        self._updating = True
        try:
            for index, row in enumerate(candidate.get("band_rows", [])):
                path = ("band_rows", index, "effective_legs")
                control = self.cells.get(path)
                if control is None:
                    continue
                automatic = row.get("legs_mode", "自動") == "自動"
                if automatic:
                    control.set(value_text(model.effective_legs(row)))
                if isinstance(control, SheetCell):
                    control.sheet.readonly_cells(control.row, control.column, readonly=automatic)
                    control.sheet.highlight_cells(control.row, control.column, bg="#f1f5f9" if automatic else "#ffffff")
                else:
                    widget = getattr(self, "_detail_widgets", {}).get(path)
                    if widget is not None:
                        widget.configure(state="readonly" if automatic else "normal")
            for path, widget in getattr(self, "_detail_widgets", {}).items():
                if path[-1] == "center_mm":
                    row = candidate[path[0]][path[1]]
                    widget.configure(state="readonly" if row.get("cover_mode", "自動") == "自動" else "normal")
        finally:
            self._updating = False

    def _draw_preview(self) -> None:
        if self._disposed or not hasattr(self, "preview_canvas") or not self.preview_canvas.winfo_exists():
            return
        canvas = self.preview_canvas
        canvas.delete("all")
        mode_control = self.cells.get(("position_mode",))
        mode = self._preview_candidate.get("position_mode", mode_control.get() if mode_control is not None else self._render_base.get("position_mode", "基本"))
        if self.member == "柱":
            self.source_badge.configure(text="使用中：詳細修正" if mode == "指定" else "使用中：自動配置")
        else:
            self.source_badge.configure(text="使用中：指定位置" if mode == "指定" else "使用中：基本配筋")
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        self.notice.configure(wraplength=max(160, cw - 8))
        normal_notice = ("X：左面、Y：上面からの芯位置。単位 mm。" if self.member == "柱" else
                         "入力に応じた実配筋を表示。構造の安全性を判定する図ではありません。")
        self.notice.configure(text=self.preview_error or normal_notice)
        geometry = self.preview_geometry
        if geometry is None:
            canvas.create_text(max(1, cw) / 2, max(1, ch) / 2, text="断面寸法を入力してください", fill="#64748b", font=("Yu Gothic UI", 10), width=max(100, cw - 20))
            return
        if cw < 40 or ch < 60:
            return
        bottom_padding = 44 if (self.selected[0] == "band_rows" or
                                self.member == "柱" and "column_hoops" in self._preview_candidate) else 26
        scale = min((cw - 44) / geometry["width_mm"], max(1, ch - 25 - bottom_padding) / geometry["height_mm"])
        ox = (cw - geometry["width_mm"] * scale) / 2
        oy = 25 + (ch - 25 - bottom_padding - geometry["height_mm"] * scale) / 2
        point = lambda x, y: (ox + x * scale, oy + y * scale)
        outline = [value for xy in model.section_outline(self.member, geometry) for value in point(*xy)]
        canvas.create_polygon(outline, fill="#eef3f7", outline="#526981", width=1.5, tags=("section-outline",))
        self._draw_transverse(canvas, geometry, point, cw, ch)
        for physical_index, bar in enumerate(self.preview_bars):
            sources = bar.get("sources", [(bar.get("family", "main_rows"), index) for index in bar["row_indices"]])
            selected = self.selected in sources
            if self.member == "柱" and self.group == "placement":
                selected = self.selected == ("manual_positions", physical_index)
            x, y = point(bar["x_mm"], bar["y_mm"])
            radius = max(2.5, bar["diameter_mm"] * scale / 2)
            tags = ["rebar", *(f"rebar:{family}:{index}" for family, index in sources)]
            if self.member == "柱":
                tags.append(f"physical:{physical_index}")
            if selected:
                tags.append("selected")
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius,
                               fill="#1674bf" if selected else "#7a8797", outline="white", tags=tuple(tags))
        for line in self.preview_lines:
            sources = line.get("sources", [("main_rows", index) for index in line["row_indices"]])
            selected = self.selected in sources
            tags = ["rebar", "rebar-line", *(f"rebar:{family}:{index}" for family, index in sources)]
            if selected:
                tags.append("selected")
            canvas.create_line(*point(line["x1_mm"], line["y1_mm"]), *point(line["x2_mm"], line["y2_mm"]),
                               fill="#1674bf" if selected else "#7a8797", width=max(2, line["diameter_mm"] * scale), tags=tuple(tags))
        canvas.create_text(cw / 2, ch - 12, text=f"{geometry['width_mm']:g} mm  ×  {geometry['height_mm']:g} mm", fill="#526981", font=("Yu Gothic UI", 9))
        if self.member == "柱":
            canvas.create_text(cw / 2, 10, text="X：直角  ／  Y：線路（上面から）", fill="#64748b", font=("Yu Gothic UI", 8), width=cw - 12)
            self.column_editor.draw_axes(canvas, point, geometry)
        elif self.member == "フーチング":
            canvas.create_text(cw / 2, 10, text=f"{self.direction}方向断面：交差筋 ● ／ 面内筋 ━", fill="#64748b", font=("Yu Gothic UI", 8), width=cw - 12)
        self._refresh_effective_label()
        self._draw_band_schematic()
        self._refresh_directional_review()
        if self.member == "柱" and self.column_editor is not None:
            self.column_editor.refresh_status()

    def _draw_transverse(
        self, canvas: tk.Canvas, geometry: dict[str, Any],
        point: Callable[[float, float], tuple[float, float]], cw: int, ch: int,
    ) -> None:
        if self.member == "柱" and "column_hoops" in self._preview_candidate:
            self.column_editor.draw_hoop(canvas, self._preview_candidate, geometry, point, cw, ch)
            return
        bands = self._preview_candidate.get("band_rows", [])
        order = sorted(range(len(bands)), key=lambda index: self.selected == ("band_rows", index))
        for index in order:
            row = bands[index]
            selected = self.selected == ("band_rows", index)
            tags = ["transverse", f"rebar:band_rows:{index}"] + (["selected"] if selected else [])
            color = "#1674bf" if selected else "#a7b6c7"
            if row.get("sets") == 0:
                if selected:
                    canvas.create_text(cw / 2, ch - 30, text="0組：無効（入力は保持）", fill=color, font=("Yu Gothic UI", 8), tags=tuple(tags))
                continue
            try:
                polygon = model.band_outline(self.member, self._preview_candidate, geometry, row)
            except EditorError:
                polygon = []
            if polygon:
                coordinates = [v for xy in polygon for v in point(*xy)]
                canvas.create_polygon(coordinates, fill="", outline=color, width=2.5 if selected else 1, tags=tuple(tags))
            elif selected:
                legs = model.effective_legs(row)
                label = f"{row.get('type') or '種類未入力'} {row.get('direction') or ''}／{legs if legs is not None else '未確定'}脚相当"
                if row.get("type") == "内側":
                    if row.get("direction") == "線路":
                        canvas.create_line(*point(geometry["width_mm"] / 2, geometry["height_mm"] * .15),
                                           *point(geometry["width_mm"] / 2, geometry["height_mm"] * .85), arrow="both", fill=color, width=2, tags=tuple(tags))
                    else:
                        canvas.create_line(*point(geometry["width_mm"] * .15, geometry["height_mm"] / 2),
                                           *point(geometry["width_mm"] * .85, geometry["height_mm"] / 2), arrow="both", fill=color, width=2, tags=tuple(tags))
                    label += "（形状未指定）"
                else:
                    label += "：純かぶり・径を入力"
                canvas.create_text(cw / 2, ch - 30, text=label, fill=color, font=("Yu Gothic UI", 8), width=cw - 12, tags=tuple(tags))

    def _refresh_effective_label(self) -> None:
        if hasattr(self, "effective_label") and self.effective_label.winfo_exists():
            family, index = self.selected
            if family == "main_rows" and index < len(self.effective_centers):
                value = self.effective_centers[index]
                self.effective_label.configure(text="有効芯かぶり：" + (f"{value:g} mm" if value is not None else "未確定"))
            elif family == "side_rows":
                rows = self._preview_candidate.get("side_rows", [])
                try:
                    offsets = model.side_offsets(self._preview_candidate, rows[index]) if index < len(rows) else None
                except EditorError:
                    offsets = None
                if offsets is None:
                    text = "有効横芯位置：未確定"
                elif not offsets:
                    text = "有効横芯位置：配置なし（0本）"
                else:
                    text = "有効横芯位置：" + " / ".join(f"{value:g}" for value in offsets) + " mm（各側のコンクリート面から、1列目順）"
                self.effective_label.configure(text=text)
            else:
                self.effective_label.configure(text="図の青色が選択した行の鉄筋です。")

    def _refresh_directional_review(self) -> None:
        derived = getattr(self, "_derived_sheet", None)
        if derived is not None and derived.winfo_exists():
            rows = model.directional_rows(self.preview_bars, self.direction)
            data = [[value_text(row[key]) for key in ("center_mm", "diameter_mm", "count", "material")] for row in rows]
            if derived.get_sheet_data() != data:
                derived.set_sheet_data(data, reset_col_positions=False, redraw=True)
            derived.readonly_cells(cells=[(r, c) for r in range(len(rows)) for c in range(4)])
            self._derived_total.configure(text=f"物理本数 {len(self.preview_bars)} 本")

    def _capture_rows(self):
        self.app._commit_grid_editors()
        candidate = self.read_candidate()
        model.validate_member(self.member, candidate)
        return candidate

    def add_row(self, family):
        if self.app._calculation_busy or self.member == "フーチング" and family == "main_rows":
            return False
        try:
            candidate = self._capture_rows()
            candidate.setdefault(family, []).append(model.blank_row(self.member, family))
            self._draft = candidate
            self.selected = (family, len(candidate[family]) - 1)
            self._build_group()
            self.app._changed()
            return True
        except EditorError as exc:
            messagebox.showerror("入力値を確認してください", str(exc), parent=self.app.root)
            return False

    def delete_row(self, family, index):
        if self.app._calculation_busy or self.member == "フーチング" and family == "main_rows":
            return False
        try:
            candidate = self._capture_rows()
            if index < 0 or index >= len(candidate.get(family, [])):
                return False
            del candidate[family][index]
            self._draft = candidate
            self.selected = (family, max(0, index - 1))
            self._build_group()
            self.app._changed()
            return True
        except EditorError as exc:
            messagebox.showerror("入力値を確認してください", str(exc), parent=self.app.root)
            return False

    def copy_basic_positions(self):
        if self.member == "フーチング" or self.app._calculation_busy:
            return False
        if self.member == "柱" and self.column_editor is not None:
            return self.column_editor.copy_positions()
        try:
            candidate = self._capture_rows()
            basic = deepcopy(candidate)
            basic["position_mode"] = "基本"
            geometry = model.section_geometry(self.app.document.data, self.member, self.direction)
            bars, _, _, _ = model.member_preview(self.member, basic, geometry, self.direction)
            candidate["manual_positions"] = deepcopy(bars)
            self._draft = candidate
            self._build_group()
            self.app._changed()
            return True
        except EditorError as exc:
            messagebox.showerror("配置をコピーできません", str(exc), parent=self.app.root)
            return False

    def dispose(self):
        if self.column_editor is not None:
            self.column_editor.cancel_regeneration()
        self._disposed = True
        for sheet in self._grids:
            if sheet in self.app.grids:
                self.app.grids.remove(sheet)
        self._grids.clear()
