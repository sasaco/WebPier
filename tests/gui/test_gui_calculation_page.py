"""The 計算・印刷 page with the CLI run in-process on a small registry instead of a child process, and the JRSNAP page
whose conditions it used to hold (decision 72)."""

import json
import subprocess
import time
import tkinter as tk
from pathlib import Path

import pytest

from gui_support import InProcessRunner, registry
from webpier.gui import app as gui
from webpier.gui import calculation_page
from webpier.gui.calculation import CalculationController
from webpier.inputs.outputs import OUTPUT_KEYS
from webpier.pipeline import generate


@pytest.fixture(autouse=True)
def fixed_identity(monkeypatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})


@pytest.fixture
def runner():
    return InProcessRunner(registry())


@pytest.fixture
def editor(tk_root, input_path, quiet, runner, tmp_path):
    controller = CalculationController(tmp_path / "output", runner, registry=runner.registry)
    editor = gui.InputEditor(tk_root, input_path, calculation=controller)
    assert editor.select("計算・印刷")
    return editor


def page(editor) -> calculation_page.CalculationPage:
    return editor.view


def cell(editor, *path):
    return editor.bindings.items[path].cell


def jrsnap_cell(editor, *path):
    """A cell of the JRSNAPの設定 page, which is selected for it."""
    assert editor.page == gui.JRSNAP or editor.select(gui.JRSNAP)
    return cell(editor, *path)


def chosen(editor) -> dict:
    return editor.document.data["outputs"]


def box(editor, key):
    return page(editor).output_boxes[key]


def finish(editor, timeout=30):
    deadline = time.monotonic() + timeout
    while page(editor).busy:
        assert time.monotonic() < deadline, "the calculation did not finish"
        editor.root.update()
        time.sleep(0.01)
    editor.root.update()


def calculate(editor):
    assert page(editor).start()
    finish(editor)
    return page(editor)


def labels(view):
    return [entry.label for entry in view.catalog().entries]


def test_the_jrsnap_conditions_are_inputs_with_program_units_on_their_own_page(editor):
    """Decision 72: the JRSNAP conditions moved from 計算・印刷 to the page 06 JRSNAPの設定."""
    assert ("jrsnap_longitudinal", "analysis_steps") not in editor.bindings.items
    steps = jrsnap_cell(editor, "jrsnap_longitudinal", "analysis_steps")
    assert gui.PAGES.index(gui.JRSNAP) == 5 and gui.PAGES.index(gui.CALCULATION) == 6
    assert steps.get() == "300" and cell(editor, "jrsnap_transverse", "target_displacement_m").get() == "0.350"
    row = steps.row
    assert steps.sheet.get_cell_data(row, 0) == "解析のステップ数"
    target = cell(editor, "jrsnap_longitudinal", "target_displacement_m")
    assert target.sheet.get_cell_data(target.row, 2) == "m"
    assert target.sheet.get_cell_data(target.row, 0) == "目標変位（大きさ）"
    assert ("jrsnap_longitudinal", "aggregate_max_mm") not in editor.bindings.items  # the column's (decision 48)


def test_the_direction_of_the_target_displacement_is_shown_not_entered(editor):
    """Decision 43: the program applies the earthquake direction of each NDU; nobody enters a sign."""
    factor = jrsnap_cell(editor, "jrsnap_longitudinal", "shear_factor_vcd")
    shown = list(texts(editor.form))
    assert "目標変位の向き：−x（←）（地震の向き。自動で決めます）" in shown
    assert "目標変位の向き：+x（→）（地震の向き。自動で決めます）" in shown
    factor.type("1.234")
    assert factor.get() == "1.23" and editor.document.data["jrsnap_longitudinal"]["shear_factor_vcd"] == 1.23


def test_calculation_saves_runs_the_pipeline_checks_and_previews(editor, runner, tmp_path):
    jrsnap_cell(editor, "jrsnap_longitudinal", "shear_factor_vcd").type("2.1")
    assert editor.select(gui.CALCULATION)
    view = calculate(editor)
    assert not editor.dirty
    assert runner.commands[0][1:3] == ["-m", "webpier"] and runner.commands[0][-1] == "--overwrite"
    assert not any(argument.startswith(("--stage", "--frame", "--nonlinear", "--jrsnap"))
                   for argument in runner.commands[0])  # the saved input's 出力項目 choose (decision 72)
    assert (tmp_path / "post" / "線路方向.ndu").exists()
    assert view.status.get() == "計算・PDF出力が完了しました（3帳票）。"
    assert view.dialog is not None and view.dialog.selected_path.name == "0500_直接基礎.pdf"
    assert all(label.endswith("今回の計算結果") for label in labels(view))
    view.dialog.close()
    assert view.dialog is None
    assert view.open_preview() and view.dialog is not None


def texts(widget):
    for child in widget.winfo_children():
        try:
            yield str(child.cget("text"))
        except tk.TclError:
            pass
        yield from texts(child)


def test_there_is_no_jrsnap_checkbox_and_the_settings_are_needed_by_the_seismic_items(editor):
    """Decision 42: the NDUs are always written with 0710 / 0720, so their settings are needed when those are chosen
    (decision 72)."""
    view = page(editor)
    assert not hasattr(view, "jrsnap_box") and not hasattr(view, "jrsnap")
    assert not hasattr(editor, "calculation_jrsnap")
    assert not any("JRSNAP 5.2-L03" in text for text in texts(view.frame))
    editor.select(gui.JRSNAP)
    shown = list(texts(editor.form))
    assert not any("両方向のJRSNAP入力ファイルも出力" in text for text in shown)
    assert ("線路方向の計算（地震時）を選ぶと線路方向の、線路直角方向の計算（地震時）を選ぶと線路直角方向の全項目が必要です。"
            "空欄は補いません。") in shown


def test_the_page_lists_the_output_items_with_their_stages(editor):
    """Decision 72: each item with the stages it makes (none: the caption alone), the analyses indented under the
    item they add to, and nothing about switches or the files under post."""
    view = page(editor)
    shown = list(texts(view.frame))
    for text in ("出力項目", "照査の前提", "地盤のモデル化（0500）", "上部工反力及び橋脚自重",
                 "線路方向の計算（地震時以外）（0610）",
                 "骨組解析も行う（0611）", "線路方向の計算（地震時）（0710）", "静的非線形解析も行う（0711）",
                 "　数分かかり、JRSNAP の画面が出ます", "フーチングの計算", "　両方向の骨組解析と静的非線形解析が必要です",
                 "片持ち梁の計算", "　両方向の静的非線形解析が必要です"):
        assert text in shown
    assert not any("--" in text or "post に出力" in text or "決定" in text for text in shown)
    assert list(view.output_boxes) == list(OUTPUT_KEYS)
    indented = {key for key, row in view.output_boxes.items() if row.master.pack_info()["padx"] != 0}
    assert indented == {"longitudinal_frame_analysis", "transverse_frame_analysis", "longitudinal_nonlinear_analysis",
                        "transverse_nonlinear_analysis"}


def test_the_checkboxes_show_the_input_and_an_item_waits_for_the_items_it_uses(editor):
    """Decision 72: current.json chooses the six items without analyses; an analysis may be checked once its item is,
    the footing only with both directions' analyses, the cantilever with both nonlinear analyses."""
    view = page(editor)
    assert {key for key, variable in view.outputs.items() if variable.get()} == {
        key for key, value in chosen(editor).items() if value}
    enabled = {key for key in OUTPUT_KEYS if box(editor, key).instate(["!disabled"])}
    assert enabled == {"detailing", "ground_model", "reactions", "longitudinal", "longitudinal_frame_analysis", "transverse",
                       "transverse_frame_analysis", "longitudinal_seismic", "longitudinal_nonlinear_analysis",
                       "transverse_seismic", "transverse_nonlinear_analysis"}
    for key in ("longitudinal_nonlinear_analysis", "transverse_nonlinear_analysis"):
        box(editor, key).invoke()
    assert box(editor, "cantilever").instate(["!disabled"]) and box(editor, "footing").instate(["disabled"])
    for key in ("longitudinal_frame_analysis", "transverse_frame_analysis"):
        box(editor, key).invoke()
    assert box(editor, "footing").instate(["!disabled"])


def test_a_checkbox_writes_its_item_into_the_input(editor, runner, tmp_path):
    """Decision 72: the 出力項目 are input, so a click changes the document and the next generation follows it."""
    assert not editor.dirty
    box(editor, "longitudinal_nonlinear_analysis").invoke()
    assert chosen(editor)["longitudinal_nonlinear_analysis"] is True and editor.dirty
    calculate(editor).dialog.close()
    saved = json.loads((Path(editor.document.path)).read_text(encoding="utf-8"))
    assert saved["outputs"]["longitudinal_nonlinear_analysis"] is True
    assert (tmp_path / "post" / "線路方向_JRSNAP").is_dir() and not (tmp_path / "post" / "線路方向.pik").exists()
    box(editor, "longitudinal_frame_analysis").invoke()
    calculate(editor).dialog.close()
    assert (tmp_path / "post" / "線路方向.pik").exists()
    assert page(editor).status.get() == "計算・PDF出力が完了しました（3帳票）。"


def test_unchecking_an_item_unchecks_every_item_that_uses_it(editor):
    for key in ("detailing", "longitudinal_frame_analysis", "longitudinal_nonlinear_analysis",
                "transverse_frame_analysis", "transverse_nonlinear_analysis", "footing", "cantilever"):
        box(editor, key).invoke()
    assert all(chosen(editor).values())
    box(editor, "longitudinal").invoke()
    assert {key for key, value in chosen(editor).items() if not value} == {
        "longitudinal", "longitudinal_frame_analysis", "longitudinal_seismic", "longitudinal_nonlinear_analysis",
        "footing", "cantilever"}
    assert box(editor, "longitudinal_seismic").instate(["disabled"]) and box(editor, "footing").instate(["disabled"])
    assert not page(editor).outputs["footing"].get()


def test_an_input_without_the_items_gets_all_of_them_on_the_first_click(tk_root, input_path, quiet, runner, tmp_path):
    data = json.loads(input_path.read_text(encoding="utf-8"))
    del data["outputs"]
    input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    controller = CalculationController(tmp_path / "output", runner, registry=runner.registry)
    editor = gui.InputEditor(tk_root, input_path, calculation=controller)
    assert editor.select(gui.CALCULATION)
    assert not any(variable.get() for variable in page(editor).outputs.values())
    assert box(editor, "longitudinal").instate(["disabled"])
    assert not page(editor).start()  # an input error names the missing item
    assert "入力項目がありません: outputs" in page(editor).log.get("1.0", "end")
    box(editor, "ground_model").invoke()
    assert chosen(editor) == {key: key == "ground_model" for key in OUTPUT_KEYS}
    assert page(editor).start()
    finish(editor)
    assert page(editor).status.get() == "計算・PDF出力が完了しました（1帳票）。"


def test_an_input_choosing_nothing_is_not_calculated(editor, runner):
    for key in ("ground_model", "reactions"):
        box(editor, key).invoke()
    assert not any(chosen(editor).values())
    assert not page(editor).start() and runner.commands == []
    assert "outputs: 出力項目が選ばれていません（どれかを true にしてください）" in page(editor).log.get("1.0", "end")


def test_a_stray_pdf_of_a_stage_without_a_report_is_listed_as_another_file(editor, tmp_path):
    view = calculate(editor)
    view.dialog.close()
    (tmp_path / "output" / "0611_線路方向照査.pdf").write_bytes(b"%PDF")
    assert [entry.path.name for entry in view.catalog().entries] == [
        "0500_直接基礎.pdf", "0610_線路方向荷重.pdf", "0710_線路方向荷重.pdf", "0611_線路方向照査.pdf"]


def test_an_input_error_stops_before_anything_runs(editor, runner):
    editor.select("下部構造")
    editor.bindings.items[("下部構造", "寸法", "側面", "B1")].cell.type("")
    editor.select("計算・印刷")
    assert not page(editor).start()
    assert runner.commands == []
    assert page(editor).status.get() == "入力エラーのため計算しません。入力を直してください。"
    assert "下部構造.寸法.側面.B1: 値が必要です" in page(editor).log.get("1.0", "end")


def test_text_that_cannot_be_entered_keeps_the_calculation_away(editor, runner, quiet):
    jrsnap_cell(editor, "jrsnap_longitudinal", "analysis_steps").type("many")
    assert not editor.select(gui.CALCULATION) and runner.commands == []


def test_the_editor_is_locked_while_calculating(editor, runner, quiet):
    calls, _ = quiet
    started = []

    def slow(command):
        started.append(True)
        time.sleep(0.3)

    runner.before = slow
    assert page(editor).start()
    assert page(editor).busy and editor.busy
    assert not editor.select("上部構造") and not editor.save() and not editor.close()
    assert calls[-1][0] == "showinfo"
    assert not page(editor).start() and not page(editor).open_preview()
    assert page(editor).calculate_button.instate(["disabled"]) and editor.tree.instate(["disabled"])
    assert all(item.instate(["disabled"]) for item in page(editor).output_boxes.values())
    finish(editor)
    assert started and not editor.busy
    assert box(editor, "ground_model").instate(["!disabled"]) and box(editor, "footing").instate(["disabled"])
    assert editor.select("上部構造")


def failing_cli(command, *, stdout, stderr, **kwargs):
    stderr.write("エラー: 入力が壊れています".encode("utf-8"))
    return subprocess.CompletedProcess(command, 2)


def test_a_failed_generation_is_shown_with_its_log_and_old_pdfs_are_not_current(editor):
    calculate(editor).dialog.close()
    editor.calculation._runner = failing_cli
    view = page(editor)
    assert view.start()
    finish(editor)
    assert view.status.get().startswith("計算に失敗しました（終了コード 2）")
    assert "入力が壊れています" in view.log.get("1.0", "end")
    assert view.dialog is None
    assert all(label.endswith("既存出力／今回未計算") for label in labels(view))


def test_an_edit_after_success_marks_the_pdfs_old(editor):
    view = calculate(editor)
    view.dialog.close()
    box(editor, "longitudinal_frame_analysis").invoke()  # the 出力項目 are input too (decision 72)
    assert editor.calculation.state == "stale"
    assert page(editor).status.get().startswith("入力が変更されました")
    assert all(label.endswith("既存出力／今回未計算") for label in labels(page(editor)))


def test_a_changed_output_marks_the_result_stale_when_previewed(editor, tmp_path):
    view = calculate(editor)
    view.dialog.close()
    (tmp_path / "output" / "0610_線路方向荷重.pdf").write_bytes(b"changed")
    assert view.open_preview()
    assert view.status.get().startswith("出力ファイルが変更・削除されたか")
    assert editor.calculation.state == "stale"


def test_the_preview_without_pdfs_says_so(editor):
    view = page(editor)
    assert view.status.get() == calculation_page.NOT_RUN
    assert view.open_preview()
    assert view.dialog.catalog_message.get().startswith("PDFはまだありません")


def test_a_preview_failure_keeps_the_calculation_result(editor, monkeypatch):
    def broken(self):
        raise RuntimeError("no display")

    monkeypatch.setattr(calculation_page.PdfPreviewDialog, "present", broken)
    view = calculate(editor)
    assert editor.calculation.state == "success" and view.dialog is None
    assert "PDFプレビューを開けません: no display" in view.log.get("1.0", "end")


def test_a_preview_that_cannot_be_built_is_reported(editor, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("cannot build")

    monkeypatch.setattr(calculation_page, "PdfPreviewDialog", broken)
    assert not page(editor).open_preview()
    assert "cannot build" in page(editor).log.get("1.0", "end")


def test_status_survives_navigation_and_opening_another_file(editor, input_path, quiet, monkeypatch):
    calculate(editor).dialog.close()
    editor.select("上部構造")
    editor.select("計算・印刷")
    assert page(editor).status.get() == "計算・PDF出力が完了しました（3帳票）。"
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kwargs: str(input_path))
    assert editor.open_file()
    assert editor.calculation.state == "stale"
    editor.select("計算・印刷")
    assert page(editor).status.get().startswith("入力ファイルを開きました")


def test_a_file_changed_after_saving_is_not_calculated(editor, runner, monkeypatch, quiet):
    calls, _ = quiet
    monkeypatch.setattr(calculation_page, "file_sha256", lambda path: "0" * 64)
    assert not page(editor).start()
    assert calls[-1][:2] == ("showerror", "計算を開始できません") and runner.commands == []


def test_save_as_to_another_file_marks_the_result_stale(editor, tmp_path, monkeypatch):
    calculate(editor).dialog.close()
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: str(tmp_path / "other.json"))
    assert editor.save_as()
    assert editor.calculation.state == "stale"
    assert page(editor).status.get().startswith("保存先を変更しました")


def test_leaving_the_page_cancels_polling(editor, runner):
    runner.before = lambda command: time.sleep(0.2)
    view = page(editor)
    assert view.start()
    view.dispose()
    assert view._after is None
    view.busy = False
    deadline = time.monotonic() + 10
    while editor.calculation.poll() is None:
        assert time.monotonic() < deadline
        time.sleep(0.01)
