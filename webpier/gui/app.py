"""The editor window: navigation, the pages, open/save, and the status of the input.

Every edit goes straight into the document (binding.py), so navigating never loses or half-applies input. Saving
is refused only while a cell holds text that cannot be entered; blanks a stage needs are saved as null and marked,
and 入力チェック or 計算・印刷 report the first input error with its path.
"""

from __future__ import annotations

import argparse
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from tksheet import Sheet

from ..core.errors import InputError
from ..inputs import parse_input
from ..inputs.fields import path_text
from .binding import Bindings
from .document import EditorDocument, EditorError, fingerprint
from .form import Form
from .lifecycle import destroy_children
from . import pages, reaction_page, settings

PROJECT_DIR = Path(__file__).resolve().parents[2]
INPUT_PAGES: dict[str, Callable[[Form], None]] = {
    "下部構造": pages.substructure, "上部構造": pages.superstructure, "上部工反力": reaction_page.reactions,
    "地盤データ": pages.ground,
}
REBAR = "鉄筋"
CALCULATION = "計算・印刷"
PAGES = (*INPUT_PAGES, REBAR, CALCULATION)
HINTS = {
    "下部構造": "図の記号と同じ欄に寸法を入力します。数値は入力した時点で印字桁に丸めます。",
    "上部構造": "起点側と終点側を並べて入力します。支承と列車の条件は下に続きます。",
    "上部工反力": "支点・支承の並びに沿って、支承位置、死荷重、雪荷重、列車分担を入力します。",
    "地盤データ": "上から順に1層ずつ入力します。行を選ぶと、その層を複製・移動・削除できます。",
    REBAR: "基本配筋を入力し、柱は断面図で配置を確認します。",
    CALCULATION: "入力を保存して全帳票を作り直し、PDFで確認します。",
}


class InputEditor:
    def __init__(self, root: tk.Tk, path: str | Path, *, calculation: Any = None,
                 settings_path: str | Path | None = None) -> None:
        self.root = root
        self.document = EditorDocument.open(path)
        # The editor's own settings (decision 46): per user, not in the input JSON.
        self.settings_path = Path(settings_path) if settings_path is not None else settings.SETTINGS_FILE
        self.settings = settings.load_settings(self.settings_path)
        self.bindings = Bindings(lambda: self.document.data, self.changed)
        self.images: dict[str, tk.PhotoImage] = {}
        self.page = PAGES[0]
        self.soil_selected = 0
        self.reaction_sheets: dict[str, Sheet] = {}
        self.same_buttons: dict[str, ttk.Button] = {}
        self.b7_button: ttk.Button | None = None
        self.soil_sheet: Sheet | None = None
        self.view: Any = None  # the rebar or calculation page object
        self.rebar_state: dict[str, Any] = {}  # member, group, direction and selection of the rebar page
        self.calculation = calculation  # the CalculationController, created by the calculation page when needed
        self.calculation_status = ""
        self.calculation_log = ""
        self.closed = False
        root.title("橋脚 入力データ編集")
        root.geometry("1360x900")
        root.minsize(980, 640)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._build_window()
        root.bind("<Control-s>", lambda event: self.save())
        root.bind("<Control-Shift-S>", lambda event: self.save_as())
        root.bind("<Control-o>", lambda event: self.open_file())
        self.render()

    # window -------------------------------------------------------------------------------------------------

    def _build_window(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self.root.configure(background="#eef2f6")
        style.configure(".", font=("Yu Gothic UI", 10), background="#ffffff", foreground="#23344a")
        style.configure("TButton", padding=(12, 6), background="#f5f7fa")
        style.configure("Heading.TLabel", font=("Yu Gothic UI", 17, "bold"), foreground="#17344f")
        style.configure("Muted.TLabel", foreground="#5d6f82", font=("Yu Gothic UI", 9))
        style.configure("Caption.TLabel", foreground="#61748a", font=("Yu Gothic UI", 9))
        style.configure("Symbol.TLabel", foreground="#31516e", font=("Yu Gothic UI", 10, "bold"))
        style.configure("Error.TLabel", foreground="#ad342f", font=("Yu Gothic UI", 9))
        style.configure("Sheet.TLabelframe.Label", foreground="#244969", font=("Yu Gothic UI", 11, "bold"))
        style.configure("Treeview", rowheight=44, font=("Yu Gothic UI", 11))
        masthead = tk.Frame(self.root, background="#1e3a53", padx=20, pady=11)
        masthead.pack(fill="x")
        tk.Label(masthead, text="橋脚設計  /  入力データ", background="#1e3a53", foreground="white",
                 font=("Yu Gothic UI", 15, "bold")).pack(side="left")
        self.toolbar = ttk.Frame(self.root, padding=(16, 10))
        self.toolbar.pack(fill="x")
        self.toolbar_buttons = {}
        for name, title, command in (("open", "開く…", self.open_file), ("save", "上書き保存", self.save),
                                     ("save_as", "名前を付けて保存…", self.save_as),
                                     ("check", "入力チェック", self.check_input)):
            button = ttk.Button(self.toolbar, text=title, command=command)
            button.pack(side="left", padx=(0, 8))
            self.toolbar_buttons[name] = button
        self.path_text = tk.StringVar(master=self.root)
        ttk.Label(self.root, textvariable=self.path_text, style="Muted.TLabel", padding=(18, 0, 12, 8)).pack(fill="x")
        panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=12)
        left = ttk.Frame(panes, width=185, padding=(0, 8, 8, 0))
        right = ttk.Frame(panes, padding=(10, 0, 0, 0))
        panes.add(left, weight=0)
        panes.add(right, weight=1)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse", height=6)
        self.tree.column("#0", width=180, minwidth=145, stretch=True)
        self.tree.pack(fill="both", expand=True)
        for index, page in enumerate(PAGES, 1):
            self.tree.insert("", "end", iid=page, text=f"{index:02}  {page}")
        self.tree.bind("<<TreeviewSelect>>", self._tree_selected)
        ttk.Label(left, text="空欄：未入力\n赤：入力が必要／入力できない値", style="Muted.TLabel", padding=10).pack(anchor="w")
        self.heading = tk.StringVar(master=self.root)
        ttk.Label(right, textvariable=self.heading, style="Heading.TLabel", padding=(2, 6, 8, 0)).pack(anchor="w")
        self.hint = tk.StringVar(master=self.root)
        ttk.Label(right, textvariable=self.hint, style="Muted.TLabel", padding=(2, 7, 0, 4),
                  wraplength=980).pack(anchor="w")
        self.cell_message = tk.StringVar(master=self.root)
        ttk.Label(right, textvariable=self.cell_message, style="Error.TLabel", padding=(2, 0, 0, 8)).pack(anchor="w")
        body = ttk.Frame(right)
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
        self.canvas.bind("<Configure>", self._resized)
        self.status = tk.StringVar(master=self.root)
        ttk.Label(self.root, textvariable=self.status, relief="sunken", padding=(10, 6)).pack(fill="x", pady=(8, 0))
        self.root.bind_all("<MouseWheel>", self._wheel, add="+")

    def _resized(self, event: tk.Event) -> None:
        fill = self.page in (REBAR, CALCULATION)
        width = event.width if fill else max(event.width, self.form.winfo_reqwidth())
        self.canvas.itemconfigure(self.form_window, width=width, height=event.height if fill else 0)

    def _wheel(self, event: tk.Event) -> None:
        if self.page in (REBAR, CALCULATION) or event.state & 0x5:
            return  # those pages and modified wheels scroll their own widgets
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        if widget is not None and str(widget).startswith(str(self.form)):
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    # pages ------------------------------------------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self.view is not None and getattr(self.view, "busy", False)

    def _tree_selected(self, event: Any = None) -> None:
        selection = self.tree.selection()
        if selection and selection[0] != self.page:
            self.select(selection[0])

    def select(self, page: str) -> bool:
        if page not in PAGES:
            return False
        if self.busy or not self.ready_to_leave():
            self.tree.selection_set(self.page)
            return False
        self.page = page
        self.render()
        return True

    def ready_to_leave(self) -> bool:
        """Commit open cell editors; a page may be left only without text that could not be entered."""
        self.bindings.commit()
        refusal = self.bindings.first_refusal()
        if refusal is not None:
            messagebox.showerror("入力値を確認してください", refusal, parent=self.root)
            self._focus_first_refusal()
            return False
        return self.view is None or self.view.ready_to_leave()

    ready_to_restructure = ready_to_leave

    def _focus_first_refusal(self) -> None:
        for path in self.bindings.refused:
            self.bindings.items[path].cell.focus()
            return

    def rebuild(self) -> None:
        """Render the current page again from the document (after rows were added, moved or removed)."""
        self.render()

    def render(self) -> None:
        if self.view is not None:
            self.view.dispose()
            self.view = None
        destroy_children(self.form)
        self.bindings.clear()
        self.reaction_sheets.clear()
        self.same_buttons.clear()
        self.b7_button = self.soil_sheet = None
        self.tree.selection_set(self.page)
        self.heading.set(self.page)
        self.hint.set(HINTS[self.page])
        self.cell_message.set("")
        if self.page in INPUT_PAGES:
            INPUT_PAGES[self.page](Form(self, self.form))
        elif self.page == REBAR:
            from .rebar_page import RebarPage
            self.view = RebarPage(self, self.form)
        else:
            from .calculation_page import CalculationPage
            self.view = CalculationPage(self, self.form, self.calculation)
        self.root.update_idletasks()
        self.canvas.yview_moveto(0)
        self.canvas.xview_moveto(0)
        self.changed()

    def cell_selected(self, sheet: Sheet) -> None:
        selected = sheet.get_currently_selected()
        message = ""
        if selected:
            for path, bound in self.bindings.items.items():
                cell = bound.cell
                if cell.sheet is sheet and (cell.row, cell.column) == (selected.row, selected.column):
                    found = self.bindings.message(path)
                    message = f"{path_text(path)}: {found}" if found else ""
                    break
        self.cell_message.set(message)

    # state ------------------------------------------------------------------------------------------------------

    @property
    def dirty(self) -> bool:
        return self.document.dirty or bool(self.bindings.refused) or self.bindings.pending

    def changed(self) -> None:
        dirty = self.dirty
        if dirty and self.calculation is not None and self.calculation.state == "success":
            self.calculation.mark_stale()
            self.calculation_status = "入力が変更されました。表示中のPDFは過去の結果です。再計算してください。"
        self.root.title(f"{'* ' if dirty else ''}橋脚 入力データ編集 — {self.document.path.name}")
        self.path_text.set(str(self.document.path))
        marked = len(self.bindings.problems())
        state = "未保存の変更があります" if dirty else "保存済み"
        self.status.set(state + (f"　／　この画面の要確認 {marked} 件（赤の欄）" if marked else ""))
        if self.view is not None:
            self.view.input_changed()

    # files ------------------------------------------------------------------------------------------------------

    def confirm_discard(self) -> bool:
        if self.busy:
            return False
        self.bindings.commit()
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("未保存の変更", "変更を保存しますか？\nはい: 保存 / いいえ: 変更を破棄 / キャンセル: 編集を続ける",
                                           parent=self.root)
        if answer is None:
            return False
        return self.save() if answer else True

    def open_file(self) -> bool:
        if self.busy:
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
        self.soil_selected = 0
        if self.calculation is not None:
            self.calculation.mark_stale()
            self.calculation_status = "入力ファイルを開きました。既存の出力は今回の入力の結果ではありません。"
        self.render()
        self.status.set("入力を読み込みました")
        return True

    def save(self) -> bool:
        return self._save()

    def save_as(self) -> bool:
        if self.busy or not self.ready_to_leave():
            return False
        path = filedialog.asksaveasfilename(parent=self.root, title="入力JSONを別名で保存",
                                            initialdir=self.document.path.parent, initialfile=self.document.path.name,
                                            defaultextension=".json", confirmoverwrite=False,
                                            filetypes=(("JSON", "*.json"),))
        if not path:
            return False
        try:
            expected = fingerprint(Path(path))
        except EditorError as exc:
            messagebox.showerror("保存できません", str(exc), parent=self.root)
            return False
        if expected is not None and Path(path).absolute() != self.document.path:
            if not messagebox.askyesno("上書き確認", f"{path}\nをバックアップ後に上書きしますか？", parent=self.root):
                return False
        return self._save(path, expected=expected)

    def _save(self, path: str | Path | None = None, *, expected: str | None = None) -> bool:
        if self.busy or not self.ready_to_leave():
            return False
        previous = self.document.path
        try:
            result = self.document.save(path, expected=expected)
        except (EditorError, OSError) as exc:
            messagebox.showerror("保存できません", str(exc), parent=self.root)
            return False
        if self.view is not None and result.path != previous:
            self.view.input_moved()
        self.changed()
        self.status.set(f"保存しました: {result.path.name}" + (f"  /  変更前: {result.backup.name}" if result.backup else ""))
        return True

    def check_input(self) -> bool:
        """Parse the whole input as every stage will."""
        if self.busy or not self.ready_to_leave():
            return False
        try:
            parse_input(self.document.data)
        except InputError as exc:
            messagebox.showwarning("入力チェック", f"このままでは計算できません。\n\n{exc}", parent=self.root)
            return False
        messagebox.showinfo("入力チェック", "すべての段階の入力条件を満たしています。", parent=self.root)
        return True

    def close(self) -> bool:
        if self.busy:
            messagebox.showinfo("計算中です", "計算と出力の確認が終わるまで閉じられません。", parent=self.root)
            return False
        if not self.confirm_discard():
            return False
        self.closed = True
        if self.view is not None:
            self.view.dispose()
            self.view = None
        self.root.destroy()
        return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m webpier.gui", description="橋脚の入力JSONを編集し、計算書を作ります。")
    parser.add_argument("--input", type=Path, default=PROJECT_DIR / "pre" / "input.json", help="編集する入力JSON")
    arguments = parser.parse_args(argv)
    root = tk.Tk()
    root.withdraw()
    try:
        InputEditor(root, arguments.input)
    except (EditorError, OSError) as exc:
        messagebox.showerror("入力JSONを開けません", str(exc), parent=root)
        root.destroy()
        return 1
    root.deiconify()
    root.mainloop()
    return 0
