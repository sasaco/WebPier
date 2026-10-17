"""Japanese input sheets and calculation preview backed by a lossless document."""

from __future__ import annotations

import argparse
from copy import deepcopy
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .editor_model import (
    EditorDocument, EditorError, JsonPath, MANUAL_REACTION_TOTAL_PATHS, fingerprint, get_at,
    formula_source_number, numeric_field, optional_jrsnap_path, optional_reaction_path, parse_field, set_at,
    update_formula_snapshots, value_kind, value_text,
)
from .input_formulas import FORMULAS_BY_PATH, SUPPORT_POSITION_PATHS, SUPPORT_LENGTH_PATHS, opposite_support_position
from .inputs import InputError, parse_input
from .editor_forms import InputSheets, SECTIONS, SHEET_HINTS
from .editor_grid import SheetCell, commit_editor, make_sheet, pending_dirty
from .editor_calculation import CalculationController, OUTPUT_STEMS, input_sha256
from .pdf_preview_dialog import PdfCatalog, PdfEntry, PdfPreviewDialog
from . import rebar_model
from .rebar_ui import RebarView
from tksheet import Sheet


class EditorPage(Enum):
    CALCULATION = "calculation"
    REBAR = "reinforcement"


CALCULATION_PAGE = EditorPage.CALCULATION
REBAR_PAGE = EditorPage.REBAR
NavigationPath = JsonPath | EditorPage


@dataclass
class Field:
    path: JsonPath
    text: SheetCell
    kind: str
    initial_text: str
    widget: SheetCell
    empty_is_null: bool = False

    @property
    def dirty(self) -> bool:
        return self.text.get() != self.initial_text

    def parse(self) -> Any:
        text = self.text.get()
        kind = self.kind
        if numeric_field(self.path):
            kind = "適用外 (-)" if self.path[0] == "上部工反力" and text.strip() == "-" else "数値"
        if self.empty_is_null and kind == "文字列" and text == "":
            return None
        return parse_field(text, kind, self.path)


class InputEditor(InputSheets):
    def __init__(self, root: tk.Tk, path: str | Path, *,
                 output_dir: str | Path | None = None,
                 calculation_controller: CalculationController | None = None) -> None:
        self.root = root
        self.document = EditorDocument.open(path)
        self.calculation = (calculation_controller if calculation_controller is not None
                            else CalculationController(output_dir=output_dir))
        self._calculation_busy = False
        self._calculation_after: str | None = None
        self._closed = False
        self.calculation_status = tk.StringVar(master=root, value="未実行 — 既存出力は今回の計算結果ではありません。")
        self.jrsnap_enabled = tk.BooleanVar(master=root, value=False)
        self._calculation_details = ""
        self.pdf_dialog: PdfPreviewDialog | None = None
        self._pdf_paths: list[Path] = []
        self._selected_pdf: Path | None = None
        self._toolbar_buttons: list[ttk.Button] = []
        self.fields: list[Field] = []
        self.grids: list[Sheet] = []
        self.grid_cells: dict[JsonPath, SheetCell] = {}
        self._support_text: dict[JsonPath, str] = {}
        self._support_sync_error: str | None = None
        self._support_pending: JsonPath | None = None
        self._restoring_grid = False
        self._reaction_refreshers: list[Callable[[], None]] = []
        self.rebar_view: RebarView | None = None
        self.paths: dict[str, NavigationPath] = {}
        self.current_path: NavigationPath = ()
        self._building = False
        self._revealing_grid = False
        self._images: dict[str, tk.PhotoImage] = {}
        self.soil_selected = tk.IntVar(master=root, value=0)
        root.title("橋脚 入力データ編集")
        root.geometry("1360x900")
        root.minsize(980, 640)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._build_window()
        initial = ("下部構造",) if "下部構造" in self.document.data else ()
        self.refresh_tree(initial)
        root.bind("<Control-s>", lambda event: self.save())
        root.bind("<Control-Shift-S>", lambda event: self.save_as())
        root.bind("<Control-o>", lambda event: self.open_file())
        root.bind_all("<MouseWheel>", self._wheel, add="+")
        root.bind("<Destroy>", self._root_destroyed, add="+")
        self.status.set("入力を読み込みました。数値欄は空欄＝未入力、0＝ゼロとして保存します。")

    def _build_window(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self.root.configure(background="#eef2f6")
        style.configure(".", font=("Yu Gothic UI", 10), background="#ffffff", foreground="#23344a")
        style.configure("TFrame", background="#ffffff")
        style.configure("TLabel", background="#ffffff")
        style.configure("TButton", padding=(12, 6), background="#f5f7fa")
        style.map("TButton", background=[("active", "#e4edf6")])
        style.configure("Heading.TLabel", font=("Yu Gothic UI", 17, "bold"), foreground="#17344f")
        style.configure("Muted.TLabel", foreground="#5d6f82", font=("Yu Gothic UI", 9))
        style.configure("Caption.TLabel", foreground="#61748a", font=("Yu Gothic UI", 9))
        style.configure("Symbol.TLabel", foreground="#31516e", font=("Yu Gothic UI", 10, "bold"))
        style.configure("Sheet.TLabelframe", background="#ffffff", bordercolor="#dbe3ed", relief="solid")
        style.configure("Sheet.TLabelframe.Label", background="#ffffff", foreground="#244969", font=("Yu Gothic UI", 11, "bold"))
        style.configure("Treeview", rowheight=48, fieldbackground="#f5f7fa", background="#f5f7fa", borderwidth=0, font=("Yu Gothic UI", 11))
        style.map("Treeview", background=[("selected", "#dceaf7")], foreground=[("selected", "#173f64")])
        masthead = tk.Frame(self.root, background="#1e3a53", padx=20, pady=11)
        masthead.pack(fill="x")
        tk.Label(masthead, text="橋脚設計  /  入力データ", background="#1e3a53", foreground="white", font=("Yu Gothic UI", 15, "bold")).pack(side="left")
        tk.Label(masthead, text="原資料の表と図を見ながら入力", background="#1e3a53", foreground="#d3dfeb", font=("Yu Gothic UI", 10)).pack(side="left", padx=22)
        toolbar = self.toolbar = ttk.Frame(self.root, padding=(16, 10))
        toolbar.pack(fill="x")
        for title, command in (("開く…", self.open_file), ("上書き保存", self.save),
                               ("名前を付けて保存…", self.save_as), ("0500 入力チェック", self.check_calculation)):
            button = ttk.Button(toolbar, text=title, command=command)
            button.pack(side="left", padx=(0, 8))
            self._toolbar_buttons.append(button)
        self.path_text = tk.StringVar()
        self.global_path_label = ttk.Label(self.root, textvariable=self.path_text, style="Muted.TLabel", padding=(18, 0, 12, 10))
        self.global_path_label.pack(fill="x")
        panes = self.panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=12)
        left = ttk.Frame(panes, width=185, padding=(0, 8, 8, 0))
        right = ttk.Frame(panes, padding=(10, 0, 0, 0))
        panes.add(left, weight=0)
        panes.add(right, weight=1)
        ttk.Label(left, text="入力・計算", style="Symbol.TLabel", padding=(10, 0, 0, 10)).pack(anchor="w")
        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse", height=5)
        self.tree.column("#0", width=180, minwidth=145, stretch=True)
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        ttk.Label(left, text="空欄：未入力\n0：ゼロ\n-：適用外（反力のみ）", style="Muted.TLabel", padding=10).pack(anchor="w")
        self.heading = tk.StringVar()
        heading_row = ttk.Frame(right, padding=(2, 6, 8, 0))
        heading_row.pack(fill="x")
        ttk.Label(heading_row, textvariable=self.heading, style="Heading.TLabel").pack(side="left")
        self.hint = tk.StringVar()
        self.hint_label = ttk.Label(right, textvariable=self.hint, style="Muted.TLabel", padding=(2, 7, 0, 12), wraplength=980)
        self.hint_label.pack(anchor="w")
        body = self.body = ttk.Frame(right)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, highlightthickness=0, background="#ffffff")
        vertical = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        horizontal = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.form = ttk.Frame(self.canvas, padding=(2, 6, 14, 10))
        self.form_window = self.canvas.create_window((0, 0), window=self.form, anchor="nw")
        self.form.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._resize_form)
        self.status = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status, relief="sunken", padding=(10, 6)).pack(fill="x", pady=(8, 0))

    def _resize_form(self, event: tk.Event) -> None:
        if self.current_path in (CALCULATION_PAGE, REBAR_PAGE):
            self.canvas.itemconfigure(self.form_window, width=event.width, height=event.height)
            return
        self._resize_grids(event.width)
        self.canvas.itemconfigure(self.form_window, width=max(event.width, self.form.winfo_reqwidth()), height=0)

    def _resize_grids(self, width: int) -> None:
        if self.current_path is REBAR_PAGE:
            return  # Its bounded split owns table widths and input scrolling.
        for sheet in self.grids:
            sheet.configure(width=min(sheet.input_preferred_width, max(200, width - 44)))

    def _reveal_field(self, cell: SheetCell) -> None:
        """Keep the selected cell visible in both the sheet and outer canvas."""
        self._reveal_grid_cell(cell.sheet, cell.row, cell.column)

    def _grid_selected(self, sheet: Sheet) -> None:
        selected = sheet.get_currently_selected()
        if selected and not self._building:
            self._reveal_grid_cell(sheet, selected.row, selected.column)

    def _reveal_grid_cell(self, sheet: Sheet, row: int, column: int) -> None:
        if self.current_path is REBAR_PAGE and self.rebar_view is not None:
            self.rebar_view.reveal_cell(sheet, row, column)
            return
        if self._revealing_grid or not sheet.winfo_exists():
            return
        self._revealing_grid = True
        try:
            sheet.see(row, column)
            self.root.update_idletasks()
            left, top, right, bottom = SheetCell(sheet, row, column, self._changed).bounds()
            if sheet.input_fixed_labels:
                left = min(left, sheet.RI.winfo_rootx())
            x = self.form.winfo_rootx()
            y = self.form.winfo_rooty()
            self._reveal_rectangle(left - x, top - y, right - x, bottom - y)
        finally:
            self._revealing_grid = False

    def _reveal_rectangle(self, x: float, y: float, right: float, bottom: float) -> None:
        view_x, view_y = self.canvas.canvasx(0), self.canvas.canvasy(0)
        if y < view_y or bottom > view_y + self.canvas.winfo_height():
            target_y = max(0, y - 18) if y < view_y else max(0, bottom - self.canvas.winfo_height() + 18)
            self.canvas.yview_moveto(target_y / max(1, self.form.winfo_height()))
        if x < view_x or right > view_x + self.canvas.winfo_width():
            target_x = max(0, x - 18) if x < view_x else max(0, right - self.canvas.winfo_width() + 18)
            self.canvas.xview_moveto(target_x / max(1, self.form.winfo_width()))

    def _wheel(self, event: tk.Event) -> None:
        if self.current_path is CALCULATION_PAGE:
            return  # The preview and its selector own their scrolling.
        if self.current_path is REBAR_PAGE:
            if self.rebar_view is not None:
                self.rebar_view.wheel(event)
            return
        if event.state & (0x0001 | 0x0004):
            return
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        if widget is None:
            return
        widget_path = str(widget)
        for sheet in self.grids:
            if widget != sheet and not widget_path.startswith(str(sheet) + "."):
                continue
            # Only the table surfaces may pass a wheel through. Text editors
            # and dropdown lists keep their own scrolling behavior.
            if widget not in (sheet.MT, sheet.CH, sheet.RI, sheet.TL):
                return
            first, last = sheet.MT.yview()
            if last - first < 0.999:
                return
            break
        if widget_path.startswith(str(self.form)) or widget == self.canvas:
            self.canvas.yview_scroll(-int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1), "units")

    @property
    def dirty(self) -> bool:
        return (self.document.dirty or any(field.dirty for field in self.fields)
                or any(pending_dirty(sheet) for sheet in self.grids)
                or self.rebar_view is not None and self.rebar_view.dirty)

    def _changed(self, *args: Any) -> None:
        if self._building:
            return
        self._sync_support_positions(args[0] if args else None)
        self._refresh_formula_previews()
        for refresh in self._reaction_refreshers:
            refresh()
        dirty = self.dirty
        if dirty and self.calculation.state == "success":
            self._invalidate_calculation("入力が変更されました。表示中のPDFは過去の結果です。再計算してください。")
        self.root.title(f"{'* ' if dirty else ''}橋脚 入力データ編集 — {self.document.path.name}")
        self.path_text.set(str(self.document.path))
        self.status.set("未保存の変更があります" if dirty else "保存済み")

    def _sync_support_positions(self, event: Any = None) -> None:
        paths = SUPPORT_POSITION_PATHS
        if any(path not in self.grid_cells for path in paths):
            return
        cells = {path: self.grid_cells[path] for path in paths}
        changed = [path for path in paths if path in self._support_text
                   and cells[path].get() != self._support_text[path]]
        if not self._restoring_grid and (changed or self._support_pending is not None):
            # A range changing both f inputs uses the origin side.
            source = changed[0] if changed else self._support_pending
            target = paths[1] if source == paths[0] else paths[0]
            self._support_pending = None
            self._support_sync_error = None
            try:
                value = parse_field(cells[source].get(), "数値", source)
                if value is not None:
                    edited = {field.path: field for field in self.fields if field.dirty}
                    lengths = [formula_source_number(edited[path].parse() if path in edited
                               else get_at(self.document.data, path), path) for path in SUPPORT_LENGTH_PATHS]
                    if any(length is None for length in lengths):
                        raise EditorError("反対側の支承位置 f を更新するには、起点側 L2 と終点側 L1 を入力してください")
                    result = opposite_support_position(lengths[0], lengths[1], value)
                    # Keep full float precision: f is now a saved input value.
                    display = value_text(result)
                    cell = cells[target]
                    if cell.get() != display:
                        if isinstance(event, dict) and event.get("sheetname") == cell.sheet.name:
                            event["cells"]["table"].setdefault((cell.row, cell.column), cell.get())
                        cell.sheet.set_cell_data(cell.row, cell.column, display)
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                self._support_pending = source
                self._support_sync_error = str(exc)
        elif self._restoring_grid:
            self._support_pending = None
            self._support_sync_error = None
        self._support_text.update({path: cells[path].get() for path in paths})

    def _formula_preview(self, path: JsonPath) -> str:
        edited = {field.path: field for field in self.fields if field.dirty}

        def source(source_path: JsonPath) -> float | None:
            value = (edited[source_path].parse() if source_path in edited
                     else get_at(self.document.data, source_path))
            return formula_source_number(value, source_path)

        try:
            return format(FORMULAS_BY_PATH[path].evaluate(source), ".15g")
        except (KeyError, IndexError, TypeError, ValueError):
            return "入力エラー"

    def _refresh_formula_previews(self) -> None:
        for path, cell in self.grid_cells.items():
            if path not in FORMULAS_BY_PATH:
                continue
            display = self._formula_preview(path)
            if cell.get() != display:
                cell.sheet.set_cell_data(cell.row, cell.column, display)

    def flush_fields(self, *, preflight: bool = False) -> bool:
        if self._calculation_busy:
            return False
        self._commit_grid_editors()
        changes = []
        for field in self.fields:
            if not field.dirty:
                continue
            try:
                value = field.parse()
            except EditorError as exc:
                messagebox.showerror("入力値を確認してください", str(exc), parent=self.root)
                field.widget.focus_set()
                self._reveal_field(field.widget)
                return False
            changes.append((field, value))
        if self._support_sync_error:
            messagebox.showerror("入力値を確認してください", self._support_sync_error, parent=self.root)
            return False
        candidate_document = deepcopy(self.document.data)
        for field, value in changes:
            set_at(candidate_document, field.path, value)
        update_formula_snapshots(candidate_document)
        rebar_changed = False
        if self.rebar_view is not None:
            try:
                candidate = self.rebar_view.prepare(candidate_document)
                rebar_changed = candidate != self.rebar_view._baseline
                if rebar_changed:
                    candidate_document = rebar_model.patch_member(candidate_document, self.rebar_view.member, candidate)
            except EditorError as exc:
                self.rebar_view.refresh_preview()
                messagebox.showerror("入力値を確認してください", str(exc), parent=self.root)
                return False
        if preflight:
            try:
                rebar_model.validate_document_rebar(candidate_document)
            except EditorError as exc:
                messagebox.showerror("入力値を確認してください", str(exc), parent=self.root)
                return False
        for field, value in changes:
            set_at(self.document.data, field.path, value)
            field.initial_text = field.text.get()
        update_formula_snapshots(self.document.data)
        if rebar_changed:
            self.document.data["鉄筋"] = candidate_document["鉄筋"]
        if self.rebar_view is not None:
            self.rebar_view.accept()
        self._changed()
        return True

    def _commit_grid_editors(self) -> None:
        for sheet in self.grids:
            commit_editor(sheet)

    def refresh_tree(self, selected: NavigationPath | None = None) -> None:
        if self._calculation_busy:
            return
        self._building = True
        self.tree.delete(*self.tree.get_children())
        self.paths.clear()
        chosen = ""
        for index, section in enumerate(SECTIONS, 1):
            if not isinstance(self.document.data.get(section), dict):
                continue
            node = self.tree.insert("", "end", text=f"{index:02}  {section}")
            self.paths[node] = (section,)
            if selected == (section,):
                chosen = node
        node = self.tree.insert("", "end", text="05  計算・印刷")
        self.paths[node] = CALCULATION_PAGE
        if selected is CALCULATION_PAGE:
            chosen = node
        node = self.tree.insert("", "end", text="06  鉄筋")
        self.paths[node] = REBAR_PAGE
        if selected is REBAR_PAGE:
            chosen = node
        chosen = chosen or next(iter(self.paths), "")
        self.current_path = self.paths.get(chosen, ())
        if chosen:
            self.tree.selection_set(chosen)
        self._building = False
        self.render_fields()

    def _selected(self, event: tk.Event | None = None) -> None:
        if self._building or not self.tree.selection():
            return
        path = self.paths[self.tree.selection()[0]]
        if path == self.current_path:
            return
        self.select_path(path)

    def select_path(self, path: NavigationPath) -> None:
        node = next((node for node, candidate in self.paths.items() if candidate == path), None)
        if node is None:
            return
        if self._calculation_busy or not self.flush_fields():
            for previous, candidate in self.paths.items():
                if candidate == self.current_path:
                    self.tree.selection_set(previous)
                    break
            return
        self.tree.selection_set(node)
        self.tree.see(node)
        self.current_path = path
        self.render_fields()

    def render_fields(self) -> None:
        if self._calculation_busy:
            return
        update_formula_snapshots(self.document.data)
        self._building = True
        self._close_pdf_preview()
        if self.rebar_view is not None:
            self.rebar_view.dispose()
            self.rebar_view = None
        for widget in self.form.winfo_children():
            widget.destroy()
        self.fields.clear()
        self.grids.clear()
        self.grid_cells.clear()
        self._support_text.clear()
        self._support_sync_error = None
        self._support_pending = None
        self._reaction_refreshers.clear()
        if self.current_path is CALCULATION_PAGE:
            self.toolbar.pack_forget()
            self.global_path_label.pack_forget()
            self.hint_label.pack_forget()
        else:
            self.toolbar.pack(fill="x", before=self.panes)
            self.global_path_label.pack(fill="x", before=self.panes)
            self.hint_label.pack(anchor="w", before=self.body)
        section = self.current_path[0] if isinstance(self.current_path, tuple) and self.current_path else ""
        self.heading.set(section or "入力シート")
        if self.current_path is CALCULATION_PAGE:
            self.heading.set("計算・印刷")
            self.hint.set(f"入力を保存して{len(OUTPUT_STEMS)}帳票を一括更新し、PDFプレビューで確認します。")
            self._build_calculation_page()
        elif self.current_path is REBAR_PAGE:
            self.heading.set("鉄筋")
            self.hint.set("基本配筋を入力し、断面図で確認します。必要な行だけ配置条件を調整できます。")
            try:
                self.rebar_view = RebarView(self, self.form)
            except EditorError as exc:
                ttk.Label(self.form, text=f"鉄筋データを表示できません。\n{exc}", wraplength=650).pack(anchor="w")
        elif section:
            self.hint.set(SHEET_HINTS[section])
            builders = {"下部構造": self._sheet_substructure, "上部構造": self._sheet_superstructure, "上部工反力": self._sheet_reactions, "地盤データ": self._sheet_ground}
            builders[section]()
        else:
            self.hint.set("このファイルには表示できる入力シートがありません。")
        self._building = False
        self._resize_grids(self.canvas.winfo_width())
        self.root.update_idletasks()
        if self.current_path in (CALCULATION_PAGE, REBAR_PAGE):
            self.canvas.itemconfigure(self.form_window, width=self.canvas.winfo_width(), height=self.canvas.winfo_height())
        else:
            self.canvas.itemconfigure(self.form_window, width=max(self.canvas.winfo_width(), self.form.winfo_reqwidth()), height=0)
        self.root.update_idletasks()
        self.canvas.yview_moveto(0)
        self.canvas.xview_moveto(0)
        self._changed()

    def _build_calculation_page(self) -> None:
        page = ttk.Frame(self.form)
        page.pack(fill="both", expand=True)
        page.columnconfigure(1, weight=1)
        ttk.Label(page, text="入力", style="Symbol.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.calculation_input = ttk.Label(page, text=str(self.document.path), style="Muted.TLabel")
        self.calculation_input.grid(row=0, column=1, columnspan=2, sticky="ew")
        ttk.Label(page, text="出力先", style="Symbol.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(3, 0))
        ttk.Label(page, text=str(self.calculation.output_dir), style="Muted.TLabel").grid(row=1, column=1, columnspan=2, sticky="ew")
        stages = "・".join(stem[:4] for stem in OUTPUT_STEMS)
        ttk.Label(page, text=f"{stages}の同名PDFと結果JSONを更新します。", style="Muted.TLabel").grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 6))
        settings_panel = ttk.Frame(page)
        settings_panel.grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.jrsnap_grids = {}
        for namespace, direction in (("jrsnap_longitudinal", "線路方向"), ("jrsnap_transverse", "線路直角方向")):
            settings = ttk.LabelFrame(settings_panel, text=f"JRSNAP 5.2-L03 {direction}入力")
            settings.pack(side="left", anchor="n", padx=(0, 8))
            rows = [
                ["部材係数 γb（Vcd）", (namespace, "shear_factor_vcd"), ""],
                ["部材係数 γb（Vsd）", (namespace, "shear_factor_vsd"), ""],
                ["部材係数 γb（Vdd）", (namespace, "shear_factor_vdd"), ""],
                ["粗骨材最大寸法 Dmax", (namespace, "aggregate_max_mm"), "mm"],
            ]
            self.jrsnap_grids[namespace] = self._grid(settings, ["項目", "値", "単位"], rows, [270, 130, 65])
            ttk.Label(settings, text="JRSNAP出力時は4項目を入力してください。空欄は自動補完しません。",
                      style="Muted.TLabel").pack(anchor="w", padx=4, pady=(0, 4))
        self.jrsnap_grid = self.jrsnap_grids["jrsnap_longitudinal"]
        actions = ttk.Frame(page)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew")
        self.calculate_button = ttk.Button(actions, text="保存して計算・PDF出力", command=self.start_calculation)
        self.calculate_button.pack(side="left")
        self.jrsnap_checkbox = ttk.Checkbutton(
            actions, text="両方向のJRSNAP入力ファイルも出力", variable=self.jrsnap_enabled,
        )
        self.jrsnap_checkbox.pack(side="left", padx=(12, 0))
        self.calculation_progress = ttk.Progressbar(actions, mode="indeterminate", length=150)
        self.calculation_progress.pack(side="left", fill="x", expand=True, padx=(16, 0))
        self._build_calculation_feedback(page)
        self._build_pdf_preview(page)
        self._refresh_pdf_list()
        self._update_calculation_widgets()

    def _build_calculation_feedback(self, page: ttk.Frame) -> None:
        calculation_status_label = ttk.Label(page, textvariable=self.calculation_status, style="Symbol.TLabel")
        calculation_status_label.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 6))
        calculation_status_label.bind("<Configure>", lambda event: calculation_status_label.configure(wraplength=max(100, event.width)))
        self.calculation_log_frame = ttk.Frame(page)
        self.calculation_log_frame.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        self.calculation_log = tk.Text(self.calculation_log_frame, height=3, wrap="word", font=("Yu Gothic UI", 9), background="#fff7f4", relief="solid", borderwidth=1)
        log_scroll = ttk.Scrollbar(self.calculation_log_frame, orient="vertical", command=self.calculation_log.yview)
        self.calculation_log.configure(yscrollcommand=log_scroll.set)
        self.calculation_log.pack(side="left", fill="x", expand=True)
        log_scroll.pack(side="right", fill="y")

    def _build_pdf_preview(self, page: ttk.Frame) -> None:
        self.preview_button = ttk.Button(page, text="PDFプレビュー", command=self.open_pdf_preview)
        self.preview_button.grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 6))

    def _update_calculation_widgets(self) -> None:
        busy = self._calculation_busy
        state = ["disabled"] if busy else ["!disabled"]
        for widget in (*self._toolbar_buttons, self.tree):
            widget.state(state)
        if self.current_path is not CALCULATION_PAGE:
            return
        for button in (self.calculate_button, self.preview_button, self.jrsnap_checkbox):
            button.state(state)
        editing = ("edit_cell", "paste", "cut", "delete", "undo", "redo")
        for grid in self.jrsnap_grids.values():
            if busy:
                grid.disable_bindings(*editing)
            else:
                grid.enable_bindings(*editing)
        self.calculation_input.configure(text=str(self.document.path))
        if busy:
            self.calculation_progress.pack(side="left", fill="x", expand=True, padx=(16, 0))
            self.calculation_progress.start(12)
        else:
            self.calculation_progress.stop()
            self.calculation_progress.pack_forget()
        self._update_calculation_log()

    def _update_calculation_log(self) -> None:
        self.calculation_log.configure(state="normal")
        self.calculation_log.delete("1.0", "end")
        self.calculation_log.insert("1.0", self._calculation_details)
        self.calculation_log.configure(state="disabled")
        if self._calculation_details:
            self.calculation_log_frame.grid()
        else:
            self.calculation_log_frame.grid_remove()

    def _refresh_pdf_list(self, *, after_success: bool = False) -> PdfCatalog:
        if self._calculation_busy:
            return self._pdf_catalog()
        self._check_calculation_outputs()
        previous = self._selected_pdf
        try:
            self._pdf_paths = self._find_pdf_paths()
        except OSError as exc:
            self._pdf_paths = []
            self._selected_pdf = None
            return self._pdf_catalog(message=f"PDF一覧を読み込めません: {exc}")
        current = self._current_pdf_paths()
        if not self._pdf_paths:
            self._selected_pdf = None
            return self._pdf_catalog(message="PDFはまだありません。「保存して計算・PDF出力」で作成します。")
        if previous not in self._pdf_paths or (after_success and previous not in current):
            previous = next((path for path in self._pdf_paths if path in current), self._pdf_paths[0])
        self._selected_pdf = previous
        return self._pdf_catalog()

    def _find_pdf_paths(self) -> list[Path]:
        return sorted(
            (path for path in self.calculation.output_dir.glob("*.pdf")
             if path.is_file() and not path.is_symlink()),
            key=lambda path: (OUTPUT_STEMS.index(path.stem), "") if path.stem in OUTPUT_STEMS
            else (len(OUTPUT_STEMS), path.name.casefold()),
        )

    def _current_pdf_paths(self) -> set[Path]:
        return set(self.calculation.result.pdf_paths) if self.calculation.state == "success" and self.calculation.result else set()

    def _pdf_catalog(self, *, message: str = "") -> PdfCatalog:
        current = self._current_pdf_paths()
        entries = tuple(
            PdfEntry(path, f"{path.name}  —  {'今回の計算結果' if path in current else '既存出力／今回未計算'}")
            for path in self._pdf_paths
        )
        return PdfCatalog(entries, self._selected_pdf, message)

    def _update_pdf_labels(self) -> None:
        if self.pdf_dialog is not None:
            self.pdf_dialog.update_labels(self._pdf_catalog().entries)

    def open_pdf_preview(self) -> bool:
        if self._calculation_busy or self._closed:
            return False
        if self.pdf_dialog is not None:
            return self._present_pdf_preview()
        return self._present_pdf_preview(self._refresh_pdf_list())

    def _present_pdf_preview(self, catalog: PdfCatalog | None = None) -> bool:
        try:
            if self.pdf_dialog is None:
                self.pdf_dialog = PdfPreviewDialog(
                    self.root, catalog if catalog is not None else self._pdf_catalog(),
                    on_refresh=self._refresh_pdf_list, on_select=self._pdf_selected,
                    on_access=self._check_calculation_outputs, on_close=self._pdf_preview_closed,
                    focus_target=getattr(self, "preview_button", None),
                )
                # Initial PDF reads can invalidate results before assignment.
                self._update_pdf_labels()
            self.pdf_dialog.present()
            return True
        except Exception as exc:
            self._close_pdf_preview()
            message = f"PDFプレビューを開けません: {exc}\n「PDFプレビュー」から再試行できます。"
            self._calculation_details = "\n\n".join(part for part in (self._calculation_details, message) if part)
            self._update_calculation_widgets()
            return False

    def _pdf_preview_closed(self) -> None:
        self.pdf_dialog = None

    def _close_pdf_preview(self) -> None:
        if self.pdf_dialog is not None:
            dialog, self.pdf_dialog = self.pdf_dialog, None
            dialog.close()

    def _check_calculation_outputs(self) -> None:
        message = self.calculation.check_current_outputs()
        if message is None:
            return
        self.calculation_status.set("出力ファイルが変更・削除されたか、読み込めません。再計算してください。")
        self._calculation_details = message
        # May be called inside a PDF read/render: update labels only and
        # never refresh the list or reenter the preview from this callback.
        self._update_calculation_widgets()
        self._update_pdf_labels()

    def _pdf_selected(self, path: Path) -> None:
        if not self._calculation_busy and path in self._pdf_paths:
            self._selected_pdf = path

    def _invalidate_calculation(self, message: str) -> None:
        self.calculation.mark_stale()
        self.calculation_status.set(message)
        self._calculation_details = ""
        self._update_calculation_widgets()
        self._update_pdf_labels()

    def start_calculation(self) -> bool:
        if self._calculation_busy:
            return False
        saved_sha = self._save_calculation_input()
        if saved_sha is None:
            return False
        self._close_pdf_preview()
        self.select_path(CALCULATION_PAGE)
        # Protect every GUI entry point before the worker can start.
        self._calculation_busy = True
        self.calculation_status.set("計算・PDF出力中… 完了後に出力ファイルを確認します。")
        self._calculation_details = ""
        self._update_calculation_widgets()
        return self._dispatch_calculation(saved_sha)

    def _save_calculation_input(self) -> str | None:
        # save() also flushes an open tksheet editor and detects clean-file conflicts.
        if not self.save():
            self._invalidate_calculation("計算を開始できませんでした。既存出力は今回未計算です。")
            return None
        try:
            saved_sha = input_sha256(self.document.path)
            if saved_sha != self.document._fingerprint:
                raise EditorError("保存後に入力ファイルが変更されました。開き直して変更を確認してください。")
        except (EditorError, OSError) as exc:
            self._invalidate_calculation("計算を開始できませんでした。入力ファイルを確認してください。")
            messagebox.showerror("計算を開始できません", str(exc), parent=self.root)
            return None
        return saved_sha

    def _dispatch_calculation(self, saved_sha: str) -> bool:
        try:
            if self.jrsnap_enabled.get():
                self.calculation.start(self.document.path, saved_sha, jrsnap=True)
            else:
                self.calculation.start(self.document.path, saved_sha)
        except Exception as exc:
            if self.calculation.running:
                self._calculation_after = self.root.after(100, self._poll_calculation)
            else:
                self._calculation_busy = False
                self._invalidate_calculation("計算を開始できませんでした。既存出力は今回未計算です。")
                self._calculation_details = str(exc)
                self._update_calculation_widgets()
                self._refresh_pdf_list()
            return False
        self._calculation_after = self.root.after(100, self._poll_calculation)
        return True

    def _poll_calculation(self) -> None:
        self._calculation_after = None
        if self._closed:
            return
        result = self.calculation.poll()
        if result is None:
            self._calculation_after = self.root.after(100, self._poll_calculation)
            return
        self._calculation_busy = False
        if result.success:
            self.calculation_status.set(f"計算・PDF出力が完了しました。{len(OUTPUT_STEMS)}帳票を確認できます。")
            if result.job.jrsnap:
                self.calculation_status.set(self.calculation_status.get() + " 両方向のJRSNAP入力も出力しました。")
            self._calculation_details = ""
        else:
            self.calculation_status.set("計算・出力の確認に失敗しました。残存PDFは今回の正常な結果ではありません。")
            self._calculation_details = "\n\n".join(part for part in (result.message, result.stderr, result.stdout) if part)
        self._update_calculation_widgets()
        catalog = self._refresh_pdf_list(after_success=result.success)
        if result.success:
            self._present_pdf_preview(catalog)

    def _cleanup_calculation(self) -> None:
        self._closed = True
        if self.rebar_view is not None:
            self.rebar_view.dispose()
        if self._calculation_after is not None:
            self.root.after_cancel(self._calculation_after)
            self._calculation_after = None
        self._close_pdf_preview()

    def _root_destroyed(self, event: tk.Event) -> None:
        if event.widget is self.root:
            self._cleanup_calculation()

    def _grid(self, parent: tk.Misc, headers: list[str], rows: list[list[str | JsonPath]],
              widths: list[int], *, choices: dict[JsonPath, tuple] | None = None,
              totals: tuple[int, ...] = (), max_height: int = 370,
              row_labels: list[str] | None = None, index_width: int = 42) -> Sheet:
        """Bind existing leaves and known optional reaction inputs; keep labels readonly."""
        data, bindings = self._grid_data(rows)
        sheet = make_sheet(parent, headers, data, widths, max_height=max_height,
                           row_labels=row_labels, index_width=index_width)
        self.grids.append(sheet)
        for path, row, column, value in bindings:
            cell = SheetCell(sheet, row, column, self._changed)
            self._bind_grid_field(path, cell, value, choices)
        for column in totals:
            sheet.highlight_cells(row="all", column=column, bg="#fff8e7")
        if any(path in SUPPORT_POSITION_PATHS for path, *_ in bindings):
            # In tksheet 7.6 these bindings run for both undo and redo.
            sheet.extra_bindings("begin_undo", lambda event: setattr(self, "_restoring_grid", True))
            sheet.extra_bindings("end_undo", lambda event: setattr(self, "_restoring_grid", False))
        sheet.bind("<<SheetModified>>", self._changed)
        sheet.bind("<<SheetSelect>>", lambda event: self._grid_selected(sheet))
        sheet.pack(anchor="w")
        return sheet

    def _grid_data(self, rows: list[list[str | JsonPath]]) -> tuple[
        list[list[str]], list[tuple[JsonPath, int, int, Any]]
    ]:
        data: list[list[str]] = []
        bindings: list[tuple[JsonPath, int, int, Any]] = []
        for row, values in enumerate(rows):
            cells = []
            for column, item in enumerate(values):
                if isinstance(item, str):
                    cells.append(item)
                    continue
                if item in FORMULAS_BY_PATH:
                    cells.append(self._formula_preview(item))
                    bindings.append((item, row, column, None))
                    continue
                try:
                    value = get_at(self.document.data, item)
                except KeyError:
                    if optional_reaction_path(item) or optional_jrsnap_path(item):
                        value = None
                    else:
                        cells.append("未設定")
                        continue
                except (IndexError, TypeError):
                    cells.append("未設定")
                    continue
                if isinstance(value, (dict, list)):
                    cells.append("入力対象外")
                    continue
                cells.append(value_text(value))
                bindings.append((item, row, column, value))
            data.append(cells)
        return data, bindings

    def _bind_grid_field(self, path: JsonPath, cell: SheetCell, value: Any,
                         choices: dict[JsonPath, tuple] | None) -> None:
        self.grid_cells[path] = cell
        if path in FORMULAS_BY_PATH:
            cell.sheet.align_cells(cell.row, cell.column, align="e")
            return
        candidates = (choices or {}).get(path, ())
        owner = self._value(path[:-1], {})
        if path[-1] == "選択値" and isinstance(owner, dict):
            declared = owner.get("選択肢", [])
            if isinstance(declared, list) and all(isinstance(choice, str) for choice in declared):
                candidates = tuple(declared)
        numeric = numeric_field(path)
        if numeric:
            kind = "数値"
        elif value is None or isinstance(value, str):
            kind = "文字列"
        else:
            kind = value_kind(value)
        self.fields.append(Field(path, cell, kind, cell.get(), cell, bool(candidates)))
        sheet, row, column = cell.sheet, cell.row, cell.column
        sheet.readonly_cells(row, column, readonly=False)
        sheet.highlight_cells(row, column, bg="#ffffff")
        sheet.align_cells(row, column, align="e" if numeric else "w")
        if candidates:
            sheet.dropdown((row, column), values=["", *candidates], edit_data=False,
                           state="normal", validate_input=False)

    def confirm_discard(self) -> bool:
        if self._calculation_busy or self.rebar_view is not None and self.rebar_view.modal_open:
            return False
        self._commit_grid_editors()
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("未保存の変更", "変更を保存しますか？\nはい: 保存 / いいえ: 変更を破棄 / キャンセル: 編集を続ける", parent=self.root)
        if answer is None:
            return False
        return self.save() if answer else True

    def open_file(self) -> bool:
        if self._calculation_busy or self.rebar_view is not None and self.rebar_view.modal_open:
            return False
        path = filedialog.askopenfilename(parent=self.root, title="入力JSONを開く", initialdir=self.document.path.parent,
                                          filetypes=(("JSON", "*.json"), ("すべて", "*.*")))
        if not path or not self.confirm_discard():
            return False
        try:
            document = EditorDocument.open(path)
        except (EditorError, OSError) as exc:
            messagebox.showerror("開けません", str(exc), parent=self.root)
            return False
        self.document = document
        self._invalidate_calculation("入力ファイルを開きました。既存出力は今回未計算です。")
        self.refresh_tree(("下部構造",) if "下部構造" in document.data else ())
        self.status.set("入力を読み込みました")
        return True

    def save(self) -> bool:
        return self._save()

    def save_as(self) -> bool:
        if self._calculation_busy:
            return False
        if not self.flush_fields(preflight=True):
            return False
        path = filedialog.asksaveasfilename(parent=self.root, title="入力JSONを別名で保存", initialdir=self.document.path.parent,
                                          initialfile=self.document.path.name, defaultextension=".json", confirmoverwrite=False,
                                          filetypes=(("JSON", "*.json"),))
        if not path:
            return False
        try:
            expected = fingerprint(Path(path))
        except (EditorError, OSError) as exc:
            messagebox.showerror("保存できません", str(exc), parent=self.root)
            return False
        if expected is not None and Path(path).absolute() != self.document.path:
            if not messagebox.askyesno("上書き確認", f"{path}\nをバックアップ後に上書きしますか？", parent=self.root):
                return False
        return self._save(path, expected=expected)

    def _save(self, path: str | Path | None = None, *, expected: str | None = None) -> bool:
        if self._calculation_busy:
            return False
        if not self.flush_fields(preflight=True):
            return False
        try:
            previous_path = self.document.path
            result = self.document.save(path, expected=expected)
        except (EditorError, OSError) as exc:
            messagebox.showerror("保存できません", str(exc), parent=self.root)
            return False
        if self.document.path != previous_path:
            self._close_pdf_preview()
            self._invalidate_calculation("保存先を変更しました。既存出力は今回未計算です。")
        self._changed()
        self.status.set(f"保存しました: {result.path.name}" + (f"  /  変更前: {result.backup.name}" if result.backup else ""))
        return True

    def check_calculation(self) -> bool:
        if self._calculation_busy:
            return False
        if not self.flush_fields():
            return False
        try:
            result = parse_input(self.document.data)
        except InputError as exc:
            messagebox.showwarning("0500 入力チェック", f"現在の入力では0500計算を実行できません。\n\n{exc}\n\n編集途中や他の基礎形式でもJSONは保存できます。", parent=self.root)
            return False
        details = "\n".join(result.warnings) or "0500直接基礎計算に必要な入力条件を満たしています。"
        messagebox.showinfo("0500 入力チェック", details + "\n\n上部構造・上部工反力の設計照査はこのチェックに含みません。", parent=self.root)
        return True

    def close(self) -> bool:
        if self._calculation_busy:
            messagebox.showinfo("計算中です", "計算と出力の確認が終わるまで、この画面を閉じられません。完了後に閉じてください。", parent=self.root)
            return False
        if not self.confirm_discard():
            return False
        self._cleanup_calculation()
        self.root.destroy()
        return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="橋脚 input.json のTkinter編集アプリ")
    parser.add_argument("--input", type=Path, default=Path(__file__).resolve().parents[1] / "pre" / "input.json", help="編集するJSON（既定: P7橋脚/pre/input.json）")
    args = parser.parse_args(argv)
    root = tk.Tk()
    root.withdraw()
    try:
        InputEditor(root, args.input)
    except (EditorError, OSError) as exc:
        messagebox.showerror("入力JSONを開けません", str(exc), parent=root)
        root.destroy()
        return 1
    root.deiconify()
    root.mainloop()
    return 0
