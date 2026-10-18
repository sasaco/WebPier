"""The 計算・印刷 page with the CLI run in-process on a small registry instead of a child process."""

import subprocess
import time
import tkinter as tk
from pathlib import Path

import pytest

from gui_support import InProcessRunner, registry
from webpier.gui import app as gui
from webpier.gui import calculation_page
from webpier.gui.calculation import CalculationController
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


def test_the_jrsnap_conditions_are_inputs_with_program_units(editor):
    steps = cell(editor, "jrsnap_longitudinal", "analysis_steps")
    assert steps.get() == "300" and cell(editor, "jrsnap_transverse", "target_displacement_m").get() == "0.350"
    row = steps.row
    assert steps.sheet.get_cell_data(row, 0) == "解析のステップ数"
    target = cell(editor, "jrsnap_longitudinal", "target_displacement_m")
    assert target.sheet.get_cell_data(target.row, 2) == "m"
    assert target.sheet.get_cell_data(target.row, 0) == "目標変位（大きさ）"


def test_the_direction_of_the_target_displacement_is_shown_not_entered(editor):
    """Decision 43: the program applies the earthquake direction of each NDU; nobody enters a sign."""
    shown = list(texts(page(editor).frame))
    assert "目標変位の向き：−x（←）（地震の向き。自動で決めます）" in shown
    assert "目標変位の向き：+x（→）（地震の向き。自動で決めます）" in shown
    factor = cell(editor, "jrsnap_longitudinal", "shear_factor_vcd")
    factor.type("1.234")
    assert factor.get() == "1.23" and editor.document.data["jrsnap_longitudinal"]["shear_factor_vcd"] == 1.23


def test_calculation_saves_runs_the_pipeline_checks_and_previews(editor, runner, tmp_path):
    cell(editor, "jrsnap_longitudinal", "shear_factor_vcd").type("2.1")
    view = calculate(editor)
    assert not editor.dirty
    assert runner.commands[0][1:3] == ["-m", "webpier"] and "--jrsnap" not in runner.commands[0]
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


def test_there_is_no_jrsnap_checkbox_and_the_settings_are_required(editor):
    """Decision 42: the NDUs are always written, so the settings are always needed."""
    view = page(editor)
    shown = list(texts(view.frame))
    assert not any("両方向のJRSNAP入力ファイルも出力" in text for text in shown)
    assert not any("出力するときは" in text for text in shown)
    assert any("両方向の全項目が必要です" in text for text in shown)
    assert not hasattr(view, "jrsnap_box") and not hasattr(view, "jrsnap")
    assert not hasattr(editor, "calculation_jrsnap")


def test_an_input_error_stops_before_anything_runs(editor, runner):
    editor.select("下部構造")
    editor.bindings.items[("下部構造", "寸法", "側面", "B1")].cell.type("")
    editor.select("計算・印刷")
    assert not page(editor).start()
    assert runner.commands == []
    assert page(editor).status.get() == "入力エラーのため計算しません。入力を直してください。"
    assert "下部構造.寸法.側面.B1: 値が必要です" in page(editor).log.get("1.0", "end")


def test_text_that_cannot_be_entered_stops_the_calculation(editor, runner):
    cell(editor, "jrsnap_longitudinal", "analysis_steps").type("many")
    assert not page(editor).start() and runner.commands == []


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
    finish(editor)
    assert started and not editor.busy
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
    cell(editor, "jrsnap_longitudinal", "aggregate_max_mm").type("20")
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
