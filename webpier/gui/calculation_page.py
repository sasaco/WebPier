"""The 計算・印刷 page: the JRSNAP conditions, one generation of every report, and the PDF preview.

計算 saves the input, parses it as every stage will (an input error is shown before anything runs), runs the
pipeline as a child process, checks what it published against the saved input (calculation.py) and then shows
the PDFs. While it runs, the editor refuses navigation, saving, opening and closing. A later edit or a changed
output file marks the shown PDFs as not the current result.

The checkbox of the frame analysis adds ``--frame-analysis`` (the opt-in stages, decision 46) to the generation, and
the one of the static nonlinear analysis ``--nonlinear-analysis`` (decision 47; JRSNAP takes minutes and shows its
own windows). Their states are editor settings of the user (settings.py), not inputs, and are kept for the next
start.
"""

from __future__ import annotations

import gc
import tkinter as tk
from dataclasses import replace
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from ..core.errors import InputError
from ..core.integrity import file_sha256
from ..export.jrsnap import LONGITUDINAL, TRANSVERSE
from ..inputs import parse_input
from ..pipeline.stages import FRAME_ANALYSIS, NONLINEAR_ANALYSIS
from . import pdf_catalog
from .calculation import CalculationController, CalculationResult
from .form import Form
from .pdf_dialog import PdfPreviewDialog
from .settings import save_settings

if TYPE_CHECKING:
    from .app import InputEditor

POLL_MS = 100
NOT_RUN = "未実行 — 表示できるPDFは今回の計算結果ではありません。"
JRSNAP_ROWS = (("shear_factor_vcd", "部材係数 γb（Vcd）"), ("shear_factor_vsd", "部材係数 γb（Vsd）"),
               ("shear_factor_vdd", "部材係数 γb（Vdd）"), ("analysis_steps", "解析のステップ数"),
               ("limited_final_step", "限定増分の最終ステップ"), ("target_displacement_m", "目標変位（大きさ）"))


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
        registry = self.controller.registry
        reports = "・".join(stage.id for stage in registry.stages if stage.has_report and not stage.opt_in)
        ttk.Label(page, text=f"{reports} の計算書PDFと計算結果JSONを作り直します。", style="Muted.TLabel").pack(
            anchor="w", pady=(4, 8))
        settings = ttk.Frame(page)
        settings.pack(anchor="w", pady=(0, 8))
        form = Form(editor, settings)
        for profile, direction in ((LONGITUDINAL, "線路方向（0710）"), (TRANSVERSE, "線路直角方向（0720）")):
            namespace = f"jrsnap_{profile.jrsnap}"
            box = ttk.LabelFrame(settings, text=f"JRSNAP 5.2-L03 {direction}")
            box.pack(side="left", anchor="n", padx=(0, 8))
            form.properties(box, [((namespace, key), label) for key, label in JRSNAP_ROWS], widths=[220, 110, 60])
            ttk.Label(box, text=f"目標変位の向き：{profile.earthquake_text}（地震の向き。自動で決めます）",
                      style="Muted.TLabel").pack(anchor="w")
        ttk.Label(page, text="0710・0720 は JRSNAP入力（NDU）も作るため、両方向の全項目が必要です。空欄は補いません。",
                  style="Muted.TLabel").pack(anchor="w")
        self.frame_analysis = tk.BooleanVar(master=editor.root, value=editor.settings.frame_analysis)
        checked = [stage.id for stage in registry.stages if stage.section_check is not None]
        column_check = f"。{'・'.join(checked)} は Capacita で柱の断面照査も行う（決定48）" if checked else ""
        founded = [stage.id for stage in registry.stages if stage.complete is not None]
        column_check += f"。{'・'.join(founded)} は反力で基礎の照査も行う（決定54）" if founded else ""
        self.frame_analysis_box = ttk.Checkbutton(
            page, variable=self.frame_analysis, command=self._analysis_changed,
            text=f"骨組解析も行う（{'・'.join(registry.opt_in(FRAME_ANALYSIS))}。FEMPython：ピックアップ断面力・変位量・反力を "
                 f"post に出力{column_check}）")
        self.frame_analysis_box.pack(anchor="w", pady=(6, 0))
        self.nonlinear_analysis = tk.BooleanVar(master=editor.root, value=editor.settings.nonlinear_analysis)
        self.nonlinear_analysis_box = ttk.Checkbutton(
            page, variable=self.nonlinear_analysis, command=self._analysis_changed,
            text=f"静的非線形解析も行う（{'・'.join(registry.opt_in(NONLINEAR_ANALYSIS))}。JRSNAP：解析用データと解析結果を "
                 "post のフォルダーに出力。数分かかり、JRSNAP の画面が出ます）")
        self.nonlinear_analysis_box.pack(anchor="w", pady=(2, 0))
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
        for widget in (self.calculate_button, self.preview_button, self.frame_analysis_box,
                       self.nonlinear_analysis_box, self.editor.tree, *self.editor.toolbar_buttons.values()):
            widget.state(state)
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

    def _analysis_changed(self) -> None:
        """Keep the choices for the next start of the editor; they are not part of the input (decisions 46, 47)."""
        self.editor.settings = replace(self.editor.settings, frame_analysis=self.frame_analysis.get(),
                                       nonlinear_analysis=self.nonlinear_analysis.get())
        try:
            save_settings(self.editor.settings, self.editor.settings_path)
        except OSError as exc:
            self._show_log(f"設定を保存できません（次回の起動では元に戻ります）: {exc}")

    # calculation --------------------------------------------------------------------------------------------

    def start(self) -> bool:
        if self.busy or not self.editor.save():
            return False
        try:
            parse_input(self.editor.document.data)
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
            self.controller.start(path, sha, frame_analysis=self.frame_analysis.get(),
                                  nonlinear_analysis=self.nonlinear_analysis.get())
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
