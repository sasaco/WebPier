"""The 計算・印刷 page: the 出力項目, one generation of the reports they choose, and the PDF preview.

計算 saves the input, parses it as every stage will (an input error is shown before anything runs), runs the
pipeline as a child process, checks what it published against the saved input (calculation.py) and then shows
the PDFs. While it runs, the editor refuses navigation, saving, opening and closing. A later edit or a changed
output file marks the shown PDFs as not the current result.

The 出力項目 are part of the input (``outputs``, decision 72, ADR-0011): a checkbox writes its item into the document,
so the input is changed and the shown PDFs are no longer the current result. An item can be checked only when every
item it uses is checked, and unchecking an item unchecks every item that uses it. An input without the items, or
with some missing, gets all of them (the missing ones false) on the first click.
"""

from __future__ import annotations

import gc
import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from ..core.errors import InputError
from ..core.integrity import file_sha256
from ..inputs import parse_input
from ..inputs.outputs import OUTPUT_KEYS, PILE_OUTPUT_KEYS, foundation_makes, requires, users
from . import pdf_catalog
from .calculation import CalculationController, CalculationResult
from .pdf_dialog import PdfPreviewDialog

if TYPE_CHECKING:
    from .app import InputEditor

POLL_MS = 100
NOT_RUN = "未実行 — 表示できるPDFは今回の計算結果ではありません。"
_JRSNAP = "数分かかり、JRSNAP の画面が出ます"
# The 出力項目 as the page lists them (decision 72): (key, caption, note, indented under the item it adds to).
OUTPUT_ROWS = (
    ("detailing", "照査の前提", "", False),
    ("ground_model", "地盤のモデル化", "", False),
    ("reactions", "上部工反力及び橋脚自重", "", False),
    ("longitudinal", "線路方向の計算（地震時以外）", "", False),
    ("longitudinal_frame_analysis", "骨組解析も行う", "", True),
    ("transverse", "線路直角方向の計算（地震時以外）", "", False),
    ("transverse_frame_analysis", "骨組解析も行う", "", True),
    ("longitudinal_seismic", "線路方向の計算（地震時）", "", False),
    ("longitudinal_nonlinear_analysis", "静的非線形解析も行う", _JRSNAP, True),
    ("transverse_seismic", "線路直角方向の計算（地震時）", "", False),
    ("transverse_nonlinear_analysis", "静的非線形解析も行う", _JRSNAP, True),
    ("footing", "フーチングの計算", "両方向の骨組解析と静的非線形解析が必要です", False),
    ("cantilever", "片持ち梁の計算", "両方向の静的非線形解析が必要です", False),
)


class CalculationPage:
    def __init__(self, editor: InputEditor, parent: ttk.Frame, controller: CalculationController | None) -> None:
        self.editor = editor
        if editor.calculation is None:
            editor.calculation = controller if controller is not None else CalculationController()
        self.controller: CalculationController = editor.calculation
        self.busy = False
        self.dialog: PdfPreviewDialog | None = None
        self._after: str | None = None
        self._selected: Any = None
        self.status = tk.StringVar(master=editor.root, value=editor.calculation_status or NOT_RUN)
        page = ttk.Frame(parent)
        page.pack(fill="both", expand=True)
        self.frame = page
        ttk.Label(page, text=f"入力：{editor.document.path}", style="Muted.TLabel").pack(anchor="w")
        ttk.Label(page, text=f"出力先：{self.controller.output_dir}　解析入力：{self.controller.post_dir}",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        box = ttk.LabelFrame(page, text="出力項目", padding=(12, 6), style="Sheet.TLabelframe")
        box.pack(anchor="w", pady=(8, 0))
        registry = self.controller.registry
        self.outputs: dict[str, tk.BooleanVar] = {}
        self.output_boxes: dict[str, ttk.Checkbutton] = {}
        for key, caption, note, child in OUTPUT_ROWS:
            row = ttk.Frame(box)
            row.pack(anchor="w", padx=(28 if child else 0, 0), pady=1)
            stages = "・".join(registry.outputs.get(key, ()))
            self.outputs[key] = tk.BooleanVar(master=editor.root, value=False)
            self.output_boxes[key] = ttk.Checkbutton(row, variable=self.outputs[key],
                                                     command=lambda key=key: self._output_changed(key),
                                                     text=f"{caption}（{stages}）" if stages else caption)
            self.output_boxes[key].pack(side="left")
            if note:
                ttk.Label(row, text=f"　{note}", style="Muted.TLabel").pack(side="left")
        self.foundation_note = tk.StringVar(master=editor.root)
        ttk.Label(box, textvariable=self.foundation_note, style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        self._show_outputs()
        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=(6, 0))
        self.calculate_button = ttk.Button(actions, text="保存して計算・PDF出力", command=self.start)
        self.calculate_button.pack(side="left")
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=150)
        ttk.Label(page, textvariable=self.status, style="Symbol.TLabel", wraplength=900).pack(anchor="w", pady=(8, 6))
        self.log = tk.Text(page, height=4, wrap="word", font=("Yu Gothic UI", 9), background="#fff7f4",
                           relief="solid", borderwidth=1)
        self.log.pack(fill="x")
        self.preview_button = ttk.Button(page, text="PDFプレビュー", command=self.open_preview)
        self.preview_button.pack(anchor="w", pady=(6, 0))
        self._show_log(editor.calculation_log)

    # state --------------------------------------------------------------------------------------------------

    def _set_status(self, text: str, log: str | None = None) -> None:
        self.status.set(text)
        self.editor.calculation_status = text
        if log is not None:
            self._show_log(log)

    def _show_log(self, text: str) -> None:
        self.editor.calculation_log = text
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("1.0", text)
        self.log.configure(state="disabled")

    def _controls(self) -> None:
        state = ["disabled"] if self.busy else ["!disabled"]
        for widget in (self.calculate_button, self.preview_button, self.editor.tree,
                       *self.editor.toolbar_buttons.values()):
            widget.state(state)
        self._show_outputs()
        if self.busy:
            self.progress.pack(side="left", fill="x", expand=True, padx=(16, 0))
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()

    def _stale(self, message: str) -> None:
        self.controller.mark_stale()
        self._set_status(message, "")
        if self.dialog is not None:
            self.dialog.update_labels(self.catalog().entries)

    def _chosen(self) -> dict[str, bool]:
        """Each 出力項目 as the document holds it; a missing or non-true one is not chosen."""
        outputs = self.editor.document.data.get("outputs")
        return {key: isinstance(outputs, dict) and outputs.get(key) is True for key in OUTPUT_KEYS}

    def _show_outputs(self) -> None:
        """The checkboxes as the document holds the items; an item is enabled only with every item it uses."""
        chosen = self._chosen()
        foundation = self.editor.document.data.get("下部構造", {}).get("基礎形式")
        for key, variable in self.outputs.items():
            variable.set(chosen[key])
            # an item the 基礎形式 cannot make yet stays enabled while it is checked, so that it can be unchecked
            enabled = (not self.busy and all(chosen[item] for item in requires(key))
                       and (foundation_makes(foundation, key) or chosen[key]))
            self.output_boxes[key].state(["!disabled"] if enabled else ["disabled"])
        self.foundation_note.set("" if all(foundation_makes(foundation, key) for key in OUTPUT_KEYS) else
                                 f"{foundation}で選べる項目は、対応した段階から広がります（いま選べる項目: "
                                 f"{'・'.join(PILE_OUTPUT_KEYS) or 'なし'}）。")

    def _output_changed(self, key: str) -> None:
        """Write the item into the document (decision 72); unchecking it unchecks every item that uses it."""
        chosen = self._chosen()
        chosen[key] = self.outputs[key].get()
        if not chosen[key]:
            chosen.update((item, False) for item in users(key))
        self.editor.document.data["outputs"] = {item: chosen[item] for item in OUTPUT_KEYS}
        self._show_outputs()
        self.editor.changed()

    # calculation --------------------------------------------------------------------------------------------

    def start(self) -> bool:
        if self.busy or not self.editor.save():
            return False
        try:
            pier = parse_input(self.editor.document.data)
        except InputError as exc:
            self._set_status("入力エラーのため計算しません。入力を直してください。", str(exc))
            return False
        path = self.editor.document.path
        try:
            sha = file_sha256(path)
        except OSError as exc:
            messagebox.showerror("計算を開始できません", str(exc), parent=self.editor.root)
            return False
        if sha != self.editor.document.fingerprint:
            messagebox.showerror("計算を開始できません", "保存後に入力ファイルが変更されました。開き直して確認してください。",
                                 parent=self.editor.root)
            return False
        self._close_preview()
        # Collect garbage here: a Tk image finalized by a collection on the worker thread waits for Tk's main loop.
        gc.collect()
        try:
            self.controller.start(path, sha, self.controller.registry.selected(pier.outputs))
        except RuntimeError as exc:
            self._set_status("計算を開始できませんでした。", str(exc))
            return False
        self.busy = True
        self._set_status("計算・PDF出力中… 完了後に出力ファイルを確認します。", "")
        self._controls()
        self._after = self.editor.root.after(POLL_MS, self._poll)
        return True

    def _poll(self) -> None:
        self._after = None
        result = self.controller.poll()
        if result is None:
            self._after = self.editor.root.after(POLL_MS, self._poll)
            return
        self.finished(result)

    def finished(self, result: CalculationResult) -> None:
        self.busy = False
        self._controls()
        if result.success:
            self._set_status(result.message, "")
            self._selected = None
            self.open_preview()
        else:
            self._set_status(result.message + " 残っているPDFは今回の正常な結果ではありません。",
                             "\n\n".join(part for part in (result.stderr, result.stdout) if part))

    # preview ------------------------------------------------------------------------------------------------

    def catalog(self) -> pdf_catalog.PdfCatalog:
        stems = tuple(stage.stem for stage in self.controller.registry.stages if stage.has_report)
        try:
            paths = pdf_catalog.find_pdfs(self.controller.output_dir, stems)
        except OSError as exc:
            return pdf_catalog.PdfCatalog((), None, f"PDF一覧を読み込めません: {exc}")
        result = self.controller.result
        current = set(result.pdf_paths) if self.controller.state == "success" and result is not None else set()
        return pdf_catalog.catalog(paths, current, selected=self._selected)

    def _check_outputs(self) -> None:
        message = self.controller.check_current_outputs()
        if message is not None:
            self._stale("出力ファイルが変更・削除されたか、読み込めません。再計算してください。")
            self._show_log(message)

    def _selected_pdf(self, path: Any) -> None:
        self._selected = path

    def _preview_closed(self) -> None:
        self.dialog = None

    def open_preview(self) -> bool:
        if self.busy:
            return False
        if self.dialog is None:
            self._check_outputs()
            try:
                self.dialog = PdfPreviewDialog(self.editor.root, self.catalog(), on_refresh=self.catalog,
                                               on_select=self._selected_pdf, on_access=self._check_outputs,
                                               on_close=self._preview_closed, focus_target=self.preview_button)
            except Exception as exc:  # the calculation result stays valid; the preview can be retried
                self._show_log(f"PDFプレビューを開けません: {exc}\n「PDFプレビュー」から再試行できます。")
                return False
        try:
            self.dialog.present()
        except Exception as exc:
            self._close_preview()
            self._show_log(f"PDFプレビューを開けません: {exc}\n「PDFプレビュー」から再試行できます。")
            return False
        return True

    def _close_preview(self) -> None:
        if self.dialog is not None:
            dialog, self.dialog = self.dialog, None
            dialog.close()

    # the editor's page interface ------------------------------------------------------------------------------

    def input_changed(self) -> None:
        """The editor marks a success stale on any edit; show its status here."""
        if self.status.get() != self.editor.calculation_status and self.editor.calculation_status:
            self.status.set(self.editor.calculation_status)
            if self.dialog is not None:
                self.dialog.update_labels(self.catalog().entries)

    def input_moved(self) -> None:
        if self.controller.state == "success":
            self._stale("保存先を変更しました。表示中のPDFは今回の入力の結果ではありません。")

    def ready_to_leave(self) -> bool:
        return not self.busy

    def dispose(self) -> None:
        self._close_preview()
        if self._after is not None:
            self.editor.root.after_cancel(self._after)
            self._after = None
