"""Column-specific controls; the host RebarView owns the save transaction."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import tkinter as tk
from tkinter import messagebox, ttk

from . import rebar_model as model
from .editor_grid import SheetCell, make_sheet, pending_edit
from .editor_model import EditorError, value_text


DISTRIBUTION_MODES = ("等分", "中央ピッチ", "両端＋中央ピッチ")
LEGACY_DISTRIBUTION = "従来の等分"
POSITION_KEYS = ("x_mm", "y_mm", "diameter_mm", "material")


class ColumnRebarEditor:
    """Keep virtual display values separate from the detached member draft."""

    def __init__(self, view):
        self.view = view
        self.dialog = None
        self.comparison = None
        self._dialog_kind = None
        self._display_positions = []
        self.position_sheet = None

    @property
    def blocked(self):
        return self.view.app._calculation_busy or self.dialog is not None

    def build(self):
        v = self.view
        v._updating = True
        v._clear_group()
        v._render_base = deepcopy(v._draft)
        v._leg_raw.clear()
        v._leg_mode.clear()
        v._detail_widgets = {}
        self._display_positions = []
        self.position_sheet = None
        split = ttk.Panedwindow(v.content, orient="horizontal")
        split.pack(fill="both", expand=True)
        inputs = ttk.Frame(split, width=390)
        preview = ttk.Frame(split, width=300, padding=(8, 0, 0, 0))
        split.add(inputs, weight=1)
        split.add(preview, weight=1)
        inputs.rowconfigure(0, weight=1)
        inputs.columnconfigure(0, weight=1)
        v.input_canvas = tk.Canvas(inputs, width=360, height=180,
                                   background="white", highlightthickness=0)
        scroll = ttk.Scrollbar(inputs, orient="vertical", command=v.input_canvas.yview)
        v.input_canvas.configure(yscrollcommand=scroll.set)
        v.input_canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        v.inputs = ttk.Frame(v.input_canvas, padding=(0, 0, 5, 8))
        v.input_window = v.input_canvas.create_window((0, 0), window=v.inputs, anchor="nw")
        v.inputs.bind("<Configure>", lambda event: v.input_canvas.configure(scrollregion=v.input_canvas.bbox("all")))
        v.input_canvas.bind("<Configure>", v._input_resized)
        self._common_inputs()
        if v.group == "main":
            self._main_inputs()
        elif v.group == "bands":
            self._hoop_inputs()
        else:
            self._position_inputs()
        v.details = ttk.LabelFrame(v.inputs, text="選択行の配置条件", style="Sheet.TLabelframe", padding=6)
        v.details.pack(fill="x", pady=(4, 0))
        v._render_details()
        v.notice = tk.Label(inputs, text="", height=3, anchor="nw", justify="left",
                            font=("Yu Gothic UI", 9), foreground="#5d6f82", background="white", wraplength=280)
        v.notice.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        actions = ttk.Frame(inputs)
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.action_buttons = {}
        for name, label, command in (("regenerate", "再配置", self.begin_regeneration),
                                     ("auto", "自動へ戻す", lambda: self.begin_regeneration(to_auto=True)),
                                     ("restore", "詳細へ復帰", self.restore_detail)):
            button = ttk.Button(actions, text=label, command=command, width=10)
            button.pack(side="left", padx=2)
            self.action_buttons[name] = button
        title = ttk.Frame(preview)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1, minsize=148)  # 140 px canvas plus 4 px top/bottom spacing.
        title.grid(row=0, column=0, sticky="ew")
        ttk.Label(title, text="柱の実配筋", style="Symbol.TLabel").pack(side="left")
        v.source_badge = ttk.Label(title, text="使用中：基本配筋", style="Symbol.TLabel")
        v.source_badge.pack(side="left", padx=6)
        v.preview_canvas = tk.Canvas(preview, width=280, height=160, background="#f8fafc",
                                     highlightthickness=1, highlightbackground="#dbe3ed")
        v.preview_canvas.grid(row=1, column=0, sticky="nsew", pady=4)
        v.preview_canvas.bind("<Configure>", lambda event: v._draw_preview())
        v.preview_canvas.tag_bind("rebar", "<Button-1>", self._diagram_selected)
        self.status = ttk.Label(preview, text="", style="Muted.TLabel", wraplength=280)
        self.status.grid(row=2, column=0, sticky="ew")
        review = ttk.Frame(preview)
        review.grid(row=3, column=0, sticky="ew")
        bar = ttk.Frame(review)
        bar.pack(fill="x")
        ttk.Label(bar, text="方向別の配筋表", style="Symbol.TLabel").pack(side="left", padx=(0, 4))
        v.direction_var = tk.StringVar(master=v.frame, value=v.direction)
        selector = ttk.Combobox(bar, textvariable=v.direction_var, values=model.DIRECTIONS, state="readonly", width=7)
        selector.pack(side="left")
        selector.bind("<<ComboboxSelected>>", self._direction_selected)
        v._derived_total = ttk.Label(bar, text="", style="Muted.TLabel")
        v._derived_total.pack(side="left", padx=6)
        v._derived_sheet = make_sheet(review, ["芯位置 mm", "径 mm", "本数", "材質"], [],
                                      [88, 65, 55, 85], max_height=110)
        v._derived_sheet.pack(fill="x")
        v._updating = False
        v.refresh_preview()
        v.app.root.update_idletasks()
        v._input_resized()

    def _direction_selected(self, event=None):
        v = self.view
        if not v.select_direction(v.direction_var.get()):
            v.direction_var.set(v.direction)

    def _common_inputs(self):
        v = self.view
        common = ttk.Frame(v.inputs)
        common.pack(fill="x", pady=(0, 5))
        for index, (path, label) in enumerate(((('materials', 'main'), '主筋材質'),
                                               (('materials', 'transverse'), '横補強筋材質'),
                                               (('concrete_strength_mpa',), '強度 N/mm²'),
                                               (('pure_cover_mm',), '純かぶり mm'))):
            box = ttk.Frame(common)
            box.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 8), pady=3)
            common.columnconfigure(index % 2, weight=1)
            ttk.Label(box, text=label, style="Muted.TLabel").pack(anchor="w")
            variable = v._variable(path)
            widget = (ttk.Combobox(box, textvariable=variable, values=("", "SD295", "SD345", "SD390", "SD490"), width=10)
                      if path[0] == "materials" else ttk.Entry(box, textvariable=variable, width=10))
            widget.pack(fill="x")
        ttk.Label(v.inputs, text="純かぶり：コンクリート面から外帯筋の外面まで。寸法は mm。空欄＝未入力、0＝ゼロ。",
                  style="Muted.TLabel", wraplength=340).pack(anchor="w", pady=(0, 6))

    def _main_inputs(self):
        v = self.view
        v._table("main_rows", [("face_direction", "対向面"), ("diameter_mm", "径 mm"),
                               ("per_face_count", "片面本数"), ("layer", "段")], "主筋の基本条件")
        for i, row in enumerate(v._render_base.get("main_rows", [])):
            mode_default = LEGACY_DISTRIBUTION if "distribution" not in row else None
            for key, default in (("mode", mode_default), ("edge_center_mm", None), ("pitch_mm", None)):
                v._variable(("main_rows", i, "distribution", key), default)
        ttk.Label(v.inputs, text="線路：上下の面 ／ 直角：左右の面。片面本数は一つの面の本数です。",
                  style="Muted.TLabel", wraplength=340).pack(anchor="w")

    def _hoop_inputs(self):
        v = self.view
        if "column_hoops" not in v._render_base:
            ttk.Button(v.inputs, text="方向別の合計有効本数を入力する", command=self.enable_hoops).pack(anchor="w", pady=4)
            ttk.Label(v.inputs, text="旧帯筋入力を使用中。新方式へ切り替えても旧入力は保持します。",
                      style="Muted.TLabel", wraplength=340).pack(anchor="w")
            v._build_group_inputs()
            return
        box = ttk.Frame(v.inputs)
        box.pack(fill="x", pady=5)
        ttk.Label(box, text="現在断面の外帯筋径 mm").pack(side="left")
        ttk.Entry(box, textvariable=v._variable(("column_hoops", "enclosing_diameter_mm")), width=8).pack(side="left", padx=4)
        ttk.Label(v.inputs, text="方向別の合計有効本数を直接入力します（外側・内側の合計）。形状は推定しません。",
                  style="Muted.TLabel", wraplength=340).pack(anchor="w")
        for i, row in enumerate(v._render_base["column_hoops"].get("direction_rows", [])):
            group = ttk.LabelFrame(v.inputs, text=f"方向別帯筋 [{i + 1}]", padding=5)
            group.pack(fill="x", pady=4)
            for key, label in (("direction", "方向"), ("diameter_mm", "径 mm"),
                               ("effective_legs", "合計有効本数"), ("pitch_mm", "間隔 mm"),
                               ("material", "材質"), ("start_mm", "開始 mm（柱下端から）"),
                               ("end_mm", "終了 mm（柱下端から）")):
                self._entry(group, ("column_hoops", "direction_rows", i, key), label,
                            model.DIRECTIONS if key == "direction" else None)
        ttk.Label(v.inputs, text="開始・終了の空欄は未指定です。全高には置き換えません。",
                  style="Muted.TLabel", wraplength=340).pack(anchor="w")
        ttk.Button(v.inputs, text="旧帯筋入力へ戻す", command=self.use_legacy_hoops).pack(anchor="w", pady=4)

    def _position_inputs(self):
        v = self.view
        ttk.Label(v.inputs, text="Xは左面、Yは上面からの芯位置。最初の位置編集で完成した自動配置をコピーし、詳細修正へ切り替えます。",
                  style="Muted.TLabel", wraplength=340).pack(anchor="w", pady=4)
        candidate = v._render_base
        if candidate.get("position_mode", "基本") == "指定":
            positions = candidate.get("manual_positions", [])
        else:
            try:
                layout = model.column_layout(candidate, self.geometry())
                positions = layout["bars"] if layout["complete"] else []
            except EditorError:
                positions = []
        self._display_positions = deepcopy(positions)
        original = v._render_base.get("manual_positions", [])
        v._render_base["manual_positions"] = deepcopy(positions)
        try:
            self.position_sheet = v._table(
                "manual_positions", [(key, label) for key, label in zip(POSITION_KEYS, ("X mm", "Y mm", "径 mm", "材質"))],
                "使用する物理位置 mm", row_actions=False)
        finally:
            v._render_base["manual_positions"] = original
        actions = ttk.Frame(v.inputs)
        actions.pack(fill="x")
        ttk.Button(actions, text="鉄筋を追加", command=self.add_position).pack(side="left", padx=2)
        ttk.Button(actions, text="選択した鉄筋を削除", command=lambda: self.delete_position(v.selected[1])
                   if v.selected[0] == "manual_positions" else None).pack(side="left", padx=2)

    def _entry(self, parent, path, label, values=None):
        v = self.view
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        caption = ttk.Label(row, text=label, width=18)
        caption.pack(side="left")
        caption.bind("<Configure>", lambda event: v._fit_condition_label(caption))
        control = v.cells.get(path)
        if control is None:
            control = v._variable(path)
        if isinstance(control, SheetCell):
            return
        widget = (ttk.Combobox(row, textvariable=control, values=values, state="readonly", width=12)
                  if values is not None else ttk.Entry(row, textvariable=control, width=12))
        widget.pack(side="left", fill="x", expand=True)
        v._detail_widgets[path] = widget

    def render_details(self):
        v = self.view
        if not hasattr(v, "details"):
            return
        for widget in v.details.winfo_children():
            widget.destroy()
        v._detail_widgets = {}
        v.band_schematic = None
        if v.group == "bands" and "column_hoops" in v._render_base:
            ttk.Label(v.details, text="図は現在断面の外帯筋位置の模式図です。合計有効本数から内側の形状は推定しません。",
                      style="Muted.TLabel", wraplength=320).pack(anchor="w")
            return
        family, index = v.selected
        if family != "main_rows" or index >= len(v._render_base.get("main_rows", [])):
            ttk.Label(v.details, text="図と表は同じ物理配筋を表示します。方向別確認表は編集しません。",
                      style="Muted.TLabel", wraplength=320).pack(anchor="w")
            return
        ttk.Label(v.details, text=f"主筋 [{index + 1}]", style="Symbol.TLabel").pack(anchor="w")
        for key in ("material", "cover_mode", "center_mm", "clear_gap_mm", "endpoints"):
            self._entry(v.details, (family, index, key), model.FIELD_LABELS[key] + (" mm" if key.endswith("_mm") else ""),
                        ("", *model.ENUM_FIELDS[key]) if key in model.ENUM_FIELDS else None)
        self._entry(v.details, (family, index, "distribution", "mode"), "面内の配列方法",
                    (LEGACY_DISTRIBUTION, *DISTRIBUTION_MODES) if "distribution" not in v._render_base[family][index] else DISTRIBUTION_MODES)
        self._entry(v.details, (family, index, "distribution", "pitch_mm"), "面内ピッチ mm")
        self._entry(v.details, (family, index, "distribution", "edge_center_mm"), "端部芯距離 mm")
        ttk.Label(v.details, text="端部芯距離は面内の側端面から。芯かぶりとは別の寸法です。",
                  style="Muted.TLabel", wraplength=320).pack(anchor="w", pady=3)
        v.effective_label = ttk.Label(v.details, text="", style="Muted.TLabel", wraplength=320)
        v.effective_label.pack(anchor="w")
        if not v._updating:
            v._refresh_legs(v.draft)
            self.refresh_status()
            v._input_resized()

    def read_candidate(self):
        v = self.view
        candidate = v._read_candidate_fields(skip_families=("manual_positions",))
        for i, row in enumerate(candidate.get("main_rows", [])):
            distribution = row.get("distribution")
            if distribution is not None and distribution.get("mode") == LEGACY_DISTRIBUTION:
                if "distribution" not in v._render_base["main_rows"][i]:
                    row.pop("distribution")
                else:
                    raise EditorError("新しい配列方法を選んでください")
        if v.group == "placement":
            changes = []
            for path, control in v.cells.items():
                if path[0] == "manual_positions" and control.get() != v._initial_text[path]:
                    changes.append((path, v._parse(path, control.get())))
            if changes:
                # Common cover/material may change while a position cell is open.
                # The first accepted edit must copy the current automatic layout.
                positions = self._active_positions(candidate)
                for path, value in changes:
                    if path[1] >= len(positions):
                        raise EditorError("自動配置の本数が変わりました。位置表を確認してから修正してください")
                    positions[path[1]][path[2]] = value
                candidate = model.column_set_detail(candidate, self.geometry(), positions)
        return candidate

    def sync_positions(self, candidate):
        """Refresh virtual rows, then freeze the first actual edit as detail."""
        v, sheet = self.view, self.position_sheet
        if v.group != "placement" or sheet is None:
            return
        detailed = candidate.get("position_mode", "基本") == "指定"
        if detailed:
            positions = candidate.get("manual_positions", [])
            # Accepted sheet data can arrive before tksheet closes its editor.
            # Freeze that validated edit now; defer only the visible refresh.
            for key in ("position_mode", "manual_positions", "manual_basis"):
                if key in candidate:
                    v._render_base[key] = deepcopy(candidate[key])
        else:
            layout = model.column_layout(candidate, self.geometry())
            positions = layout["bars"] if layout["complete"] else []
        if pending_edit(sheet) is not None or positions == self._display_positions:
            return
        v._updating = True
        try:
            self._display_positions = deepcopy(positions)
            data = [[value_text(bar.get(key)) for key in POSITION_KEYS] for bar in positions]
            sheet.set_sheet_data(data, reset_col_positions=False, redraw=True)
            for path in [path for path in v.cells if path[0] == "manual_positions"]:
                del v.cells[path]
                del v._initial_text[path]
            for row, values in enumerate(data):
                for column, key in enumerate(POSITION_KEYS):
                    path = ("manual_positions", row, key)
                    v.cells[path] = SheetCell(sheet, row, column, lambda path=path: v._cell_changed(path))
                    v._initial_text[path] = values[column]
                    sheet.readonly_cells(row, column, readonly=False)
                    sheet.highlight_cells(row, column, bg="#ffffff")
        finally:
            v._updating = False

    def geometry(self):
        return model.section_geometry(self.view.app.document.data, "柱")

    def accept(self):
        if self.view.group == "placement" and self.view._baseline.get("position_mode") == "指定":
            self._display_positions = deepcopy(self.view._baseline.get("manual_positions", []))

    def refresh_status(self):
        v = self.view
        if not hasattr(self, "status") or not self.status.winfo_exists():
            return
        try:
            candidate = v.read_candidate()
            status = model.column_detail_status(candidate, self.geometry())
            text = {"自動": "自動配置：基本条件に連動", "生成元不明": "詳細修正：生成元不明（既存の指定XY）",
                    "一致": "詳細修正：生成時の基本条件と一致", "基本条件変更": "基本条件の変更は未反映 — 詳細位置を保持中"}[status]
            self.status.configure(text=text, wraplength=max(180, v.preview_canvas.winfo_width() - 8))
            self.action_buttons["restore"].state(["!disabled"] if model.column_has_detail(candidate) else ["disabled"])
            self.action_buttons["auto"].state(["!disabled"] if candidate.get("position_mode") == "指定" else ["disabled"])
            if v.selected[0] == "main_rows":
                i = v.selected[1]
                if i < len(candidate.get("main_rows", [])):
                    mode = candidate["main_rows"][i].get("distribution", {}).get("mode", LEGACY_DISTRIBUTION)
                    for key, enabled in (("pitch_mm", mode in DISTRIBUTION_MODES[1:]),
                                         ("edge_center_mm", mode in ("等分", "両端＋中央ピッチ"))):
                        widget = v._detail_widgets.get(("main_rows", i, "distribution", key))
                        if widget is not None:
                            widget.configure(state="normal" if enabled else "disabled")
        except EditorError as exc:
            self.status.configure(text=str(exc))

    def _diagram_selected(self, event):
        v = self.view
        current = v.preview_canvas.find_withtag("current")
        if not current or self.blocked:
            return
        tags = v.preview_canvas.gettags(current[0])
        if v.group == "placement":
            for tag in tags:
                if tag.startswith("physical:"):
                    index = int(tag.split(":")[1])
                    v.select_row("manual_positions", index)
                    control = v.cells.get(("manual_positions", index, "x_mm"))
                    if isinstance(control, SheetCell):
                        control.sheet.select_cell(index, 0)
                        v.reveal_cell(control.sheet, index, 0)
                    return
        for tag in tags:
            parts = tag.split(":")
            if len(parts) == 3 and parts[0] == "rebar":
                v.select_row(parts[1], int(parts[2]))
                return

    @staticmethod
    def draw_axes(canvas, point, geometry):
        x, y = point(0, 0)
        right, bottom = point(geometry["width_mm"], geometry["height_mm"])
        end_x, end_y = x + min(40, (right - x) / 2), y + min(40, (bottom - y) / 2)
        canvas.create_line(x, y - 7, end_x, y - 7, arrow="last", fill="#526981", tags=("axis-x",))
        canvas.create_text(end_x + 7, y - 7, text="X", anchor="w", fill="#526981", font=("Yu Gothic UI", 8))
        canvas.create_line(x - 7, y, x - 7, end_y, arrow="last", fill="#526981", tags=("axis-y",))
        canvas.create_text(x - 7, end_y + 3, text="Y", anchor="n", fill="#526981", font=("Yu Gothic UI", 8))

    @staticmethod
    def draw_hoop(canvas, candidate, geometry, point, width, height):
        diameter = candidate["column_hoops"].get("enclosing_diameter_mm")
        # Only the current enclosing diameter has shape information. Directional
        # effective-leg totals do not define inner shapes or a set count.
        shape = {"type": "外巻き", "diameter_mm": diameter}
        tags = ("transverse", "column-hoop-schematic")
        try:
            outline = model.band_outline("柱", candidate, geometry, shape)
            label = f"現在断面の外帯筋 D{value_text(diameter)}（模式図）" if outline else "外帯筋模式図：純かぶり・外帯筋径を入力"
        except EditorError as exc:
            outline, label = [], str(exc)
        if outline:
            canvas.create_polygon([value for xy in outline for value in point(*xy)], fill="",
                                  outline="#829bb5", width=1.5, tags=tags)
        canvas.create_text(width / 2, height - 30, text=label, fill="#526981",
                           font=("Yu Gothic UI", 8), width=width - 12, tags=tags)

    def _replace_draft(self, candidate):
        v = self.view
        v._draft = candidate
        v._build_group()
        v.app._changed()
        return True

    def enable_hoops(self):
        if self.blocked:
            return False
        v = self.view
        try:
            candidate = v._capture_rows()
            if "column_hoops" in candidate:
                return True
            candidate["column_hoops"] = {"enclosing_diameter_mm": None, "direction_rows": [
                {"direction": direction, "diameter_mm": None, "material": None, "effective_legs": None,
                 "pitch_mm": None, "start_mm": None, "end_mm": None} for direction in model.DIRECTIONS]}
            return self._replace_draft(candidate)
        except EditorError as exc:
            messagebox.showerror("帯筋を切り替えできません", str(exc), parent=v.app.root)
            return False

    def copy_positions(self):
        if self.blocked:
            return False
        v = self.view
        try:
            candidate = v._capture_rows()
            if candidate.get("position_mode", "基本") == "指定":
                return self.begin_regeneration()
            preview = model.column_regeneration_preview(candidate, self.geometry())
            result = model.column_apply_regeneration(candidate, self.geometry(), preview)
            return self._replace_draft(result)
        except EditorError as exc:
            messagebox.showerror("配置をコピーできません", str(exc), parent=v.app.root)
            return False

    def begin_regeneration(self, *, to_auto=False):
        if self.blocked:
            return False
        v = self.view
        try:
            candidate = v._capture_rows()
            geometry = self.geometry()
            preview = model.column_regeneration_preview(candidate, geometry)
        except EditorError as exc:
            messagebox.showerror("再配置できません", str(exc), parent=v.app.root)
            return False
        self.comparison = deepcopy(preview)
        self._to_auto = to_auto
        try:
            self._build_regeneration_dialog(preview, geometry, to_auto)
        except tk.TclError as exc:
            self.cancel_regeneration()
            messagebox.showerror("確認画面を開けません", str(exc), parent=v.app.root)
            return False
        return True

    def _build_regeneration_dialog(self, preview, geometry, to_auto):
        dialog = self._new_dialog("自動配置へ切替 — 新旧の確認" if to_auto else "再配置 — 新旧の確認", "regeneration")
        body = ttk.Frame(dialog, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        ttk.Label(body, text="自動配置へ切り替えます。現在の詳細位置は退避して保持します。" if to_auto else
                  "候補を適用すると詳細位置を置き換えます。使用元は詳細修正のままです。",
                  wraplength=760).grid(row=0, column=0, sticky="w", pady=(0, 6))
        panels = ttk.Panedwindow(body, orient="horizontal")
        panels.grid(row=1, column=0, sticky="nsew")
        old, new = preview["old_bars"], preview["candidate_bars"]
        old_keys, new_keys = self._position_keys(old), self._position_keys(new)
        for label, bars, other in (("現在の使用位置", old, new_keys), ("新しい自動配置候補", new, old_keys)):
            panel = ttk.Frame(panels, padding=5)
            panels.add(panel, weight=1)
            ttk.Label(panel, text=label, style="Symbol.TLabel").pack(anchor="w")
            counts = Counter(bar["diameter_mm"] for bar in bars)
            summary = " / ".join(f"D{diameter:g} × {count}" for diameter, count in sorted(counts.items()))
            ttk.Label(panel, text=f"総本数 {len(bars)} 本　{summary}", wraplength=350).pack(anchor="w")
            figure = tk.Canvas(panel, height=145, width=330, background="#f8fafc", highlightthickness=0)
            figure.pack(fill="x", pady=4)
            figure.bind("<Configure>", lambda event, canvas=figure, bars=bars, other=other:
                        self._draw_comparison(canvas, bars, other, geometry))
            data = [[value_text(bar.get(key)) for key in POSITION_KEYS] for bar in bars]
            sheet = make_sheet(panel, ["X mm", "Y mm", "径 mm", "材質"], data, [78, 78, 65, 78], max_height=230)
            sheet.pack(fill="both", expand=True)
            for index, bar in enumerate(bars):
                if self._position_key(bar) not in other:
                    sheet.highlight_cells(row=index, bg="#fff0d5")
        ttk.Label(body, text=f"同じ位置・径・材質：{len(old_keys & new_keys)} 本　"
                  f"現在のみ：{len(old_keys - new_keys)} 本　候補のみ：{len(new_keys - old_keys)} 本（橙色）",
                  wraplength=760).grid(row=2, column=0, sticky="w", pady=6)
        footer = ttk.Frame(body)
        footer.grid(row=3, column=0, sticky="ew")
        self._dialog_footer(footer, self.apply_regeneration)
        dialog.geometry("820x560")
        self._show_dialog()

    @staticmethod
    def _position_key(bar):
        return tuple(bar.get(key) for key in POSITION_KEYS)

    @classmethod
    def _position_keys(cls, bars):
        return {cls._position_key(bar) for bar in bars}

    def _draw_comparison(self, canvas, bars, other, geometry):
        canvas.delete("all")
        width, height = max(40, canvas.winfo_width()), max(40, canvas.winfo_height())
        scale = min((width - 20) / geometry["width_mm"], (height - 20) / geometry["height_mm"])
        ox, oy = (width - geometry["width_mm"] * scale) / 2, 10
        canvas.create_rectangle(ox, oy, ox + geometry["width_mm"] * scale,
                                oy + geometry["height_mm"] * scale, outline="#526981", fill="#eef3f7")
        for bar in bars:
            x, y = ox + bar["x_mm"] * scale, oy + bar["y_mm"] * scale
            radius = max(2, bar["diameter_mm"] * scale / 2)
            color = "#cc7a00" if self._position_key(bar) not in other else "#1674bf"
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="")

    def _new_dialog(self, title, kind):
        dialog = tk.Toplevel(self.view.app.root)
        # Own the window before any later Tk operation can fail, so cleanup
        # also covers transient setup and a partially acquired modal grab.
        self.dialog = dialog
        self._dialog_kind = kind
        dialog.withdraw()
        dialog.title(title)
        dialog.transient(self.view.app.root)
        dialog.protocol("WM_DELETE_WINDOW", self.cancel_regeneration)
        dialog.bind("<Escape>", lambda event: self.cancel_regeneration())
        self.dialog_error = tk.StringVar(master=dialog, value="")
        return dialog

    def _dialog_footer(self, parent, apply):
        ttk.Label(parent, textvariable=self.dialog_error, foreground="#ad342f", wraplength=750).pack(fill="x", pady=4)
        actions = ttk.Frame(parent)
        actions.pack(fill="x")
        ttk.Button(actions, text="取消", command=self.cancel_regeneration).pack(side="right", padx=4)
        self.apply_button = ttk.Button(actions, text="適用", command=apply)
        self.apply_button.pack(side="right", padx=4)

    def _show_dialog(self):
        self.dialog.deiconify()
        self.dialog.grab_set()
        self.dialog.focus_set()

    def apply_regeneration(self):
        if self.dialog is None or self._dialog_kind != "regeneration" or self.view.app._calculation_busy:
            return False
        try:
            candidate = self.view.read_candidate()
            result = model.column_apply_regeneration(candidate, self.geometry(), self.comparison, to_auto=self._to_auto)
        except EditorError as exc:
            self.dialog_error.set(str(exc))
            self.apply_button.state(["disabled"])
            return False
        self.cancel_regeneration()
        return self._replace_draft(result)

    def _active_positions(self, candidate):
        if candidate.get("position_mode", "基本") == "指定":
            return deepcopy(candidate.get("manual_positions", []))
        layout = model.column_layout(candidate, self.geometry())
        if not layout["complete"]:
            raise EditorError("自動配置が未完成です。不足項目を入力してから詳細を修正してください")
        return deepcopy(layout["bars"])

    def delete_position(self, index):
        if self.blocked:
            return False
        try:
            candidate = self.view._capture_rows()
            positions = self._active_positions(candidate)
            if not 0 <= index < len(positions):
                return False
            del positions[index]
            result = model.column_set_detail(candidate, self.geometry(), positions)
            self.view.selected = ("manual_positions", max(0, index - 1))
            return self._replace_draft(result)
        except EditorError as exc:
            messagebox.showerror("鉄筋を削除できません", str(exc), parent=self.view.app.root)
            return False

    def _with_added_position(self, candidate, values):
        position = {key: self.view._parse(("manual_positions", 0, key), value_text(values.get(key))) for key in POSITION_KEYS}
        if any(position[key] is None for key in POSITION_KEYS[:3]):
            raise EditorError("X・Y・径をすべて入力してください")
        positions = self._active_positions(candidate)
        positions.append(position)
        return model.column_set_detail(candidate, self.geometry(), positions)

    def add_position(self, values=None):
        if self.blocked:
            return False
        try:
            candidate = self.view._capture_rows()
            self._active_positions(candidate)
            if values is not None:
                return self._replace_draft(self._with_added_position(candidate, values))
        except EditorError as exc:
            messagebox.showerror("鉄筋を追加できません", str(exc), parent=self.view.app.root)
            return False
        self._position_context = (deepcopy(candidate), self.geometry())
        try:
            self._build_position_dialog(candidate)
        except tk.TclError as exc:
            self.cancel_regeneration()
            messagebox.showerror("鉄筋追加画面を開けません", str(exc), parent=self.view.app.root)
            return False
        return True

    def _build_position_dialog(self, candidate):
        dialog = self._new_dialog("鉄筋を追加 — 芯位置 mm", "position")
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Xは左面、Yは上面からの芯位置。完成した1本を追加します。", wraplength=380).pack(anchor="w", pady=5)
        self.position_controls = {}
        for key, label in zip(POSITION_KEYS, ("X mm", "Y mm", "径 mm", "材質")):
            line = ttk.Frame(body)
            line.pack(fill="x", pady=4)
            ttk.Label(line, text=label, width=10).pack(side="left")
            default = candidate.get("materials", {}).get("main") if key == "material" else None
            control = tk.StringVar(master=dialog, value=value_text(default))
            self.position_controls[key] = control
            ttk.Entry(line, textvariable=control, width=18).pack(side="left", fill="x", expand=True)
        self._dialog_footer(body, self.apply_position)
        self._show_dialog()

    def apply_position(self):
        if self.dialog is None or self._dialog_kind != "position" or self.view.app._calculation_busy:
            return False
        try:
            candidate = self.view.read_candidate()
            if (candidate, self.geometry()) != self._position_context:
                raise EditorError("入力が変更されています。取消してから鉄筋を追加し直してください")
            result = self._with_added_position(candidate, {key: control.get() for key, control in self.position_controls.items()})
        except EditorError as exc:
            self.dialog_error.set(str(exc))
            return False
        self.cancel_regeneration()
        return self._replace_draft(result)

    def use_legacy_hoops(self):
        if self.blocked:
            return False
        try:
            candidate = self.view._capture_rows()
            if "column_hoops" not in candidate:
                return False
            if not messagebox.askyesno("旧帯筋入力へ戻す", "現在の方向別帯筋入力を削除し、保持している旧帯筋入力を使用します。\n詳細位置はそのまま保持します。", parent=self.view.app.root):
                return False
            candidate.pop("column_hoops")
            return self._replace_draft(candidate)
        except EditorError as exc:
            messagebox.showerror("帯筋を切り替えできません", str(exc), parent=self.view.app.root)
            return False

    def restore_detail(self):
        if self.blocked:
            return False
        v = self.view
        try:
            candidate = v._capture_rows()
            return self._replace_draft(model.column_restore_detail(candidate, self.geometry()))
        except EditorError as exc:
            messagebox.showerror("詳細へ復帰できません", str(exc), parent=v.app.root)
            return False

    def cancel_regeneration(self):
        dialog = self.dialog
        self.dialog = None
        self._dialog_kind = None
        self.comparison = None
        if dialog is None:
            return False
        if dialog.winfo_exists():
            if dialog.grab_current() is dialog:
                dialog.grab_release()
            dialog.destroy()
        return True
