"""The calculation: the new pipeline as a child process, then a check of what it published."""

import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

from gui_support import InProcessRunner, registry, wait
from webpier.core.errors import InputError
from webpier.core.integrity import file_sha256
from webpier.gui import calculation
from webpier.gui.calculation import CalculationController, CalculationJob, validate_outputs
from webpier.pipeline import generate
from webpier.pipeline.generate import GenerationOptions, planned, selection
from webpier.pipeline.stages import STAGES

# current.json's 出力項目 (decision 72), and those with the analyses of both directions
CURRENT_ITEMS = ("ground_model", "reactions", "longitudinal", "transverse", "longitudinal_seismic", "transverse_seismic")
FRAMES = ("longitudinal_frame_analysis", "transverse_frame_analysis")
NONLINEAR = ("longitudinal_nonlinear_analysis", "transverse_nonlinear_analysis")


@pytest.fixture(autouse=True)
def fixed_identity(monkeypatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})


@pytest.fixture
def stages():
    return registry()


def controller(tmp_path, runner, stages):
    return CalculationController(tmp_path / "output", runner, registry=stages)


def chosen(input_path, stages):
    """The stages the input's 出力項目 choose, as the page passes them; none for an input the CLI will refuse."""
    try:
        return selection(GenerationOptions(input_path, Path("output"), Path("post")), registry=stages)
    except InputError:
        return ()


def choose(input_path, *items):
    """Choose the 出力項目 *items* as well in the input at *input_path*."""
    data = json.loads(input_path.read_text(encoding="utf-8"))
    data["outputs"].update((item, True) for item in items)
    input_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def start(control, input_path, stages):
    return control.start(input_path, file_sha256(input_path), chosen(input_path, stages))


def run(tmp_path, input_path, stages, *, before=None, after=None, items=()):
    """One calculation of the input with the 出力項目 *items* chosen as well."""
    if items:
        choose(input_path, *items)
    runner = InProcessRunner(stages, before=before, after=after)
    control = controller(tmp_path, runner, stages)
    start(control, input_path, stages)
    return control, runner, wait(control)


def job(tmp_path, *items):
    return CalculationJob("id", tmp_path / "in.json", tmp_path / "output", tmp_path / "post", "0" * 64,
                          STAGES.selected(items))


def test_the_command_runs_the_new_pipeline(tmp_path):
    """Decision 72: the saved input's 出力項目 choose the reports; the command chooses nothing."""
    assert job(tmp_path, *CURRENT_ITEMS).command == [
        sys.executable, "-m", "webpier", "--input", str(tmp_path / "in.json"), "--output-dir", str(tmp_path / "output"),
        "--post-dir", str(tmp_path / "post"), "--overwrite"]


def test_the_check_covers_the_files_of_the_chosen_frame_analysis(tmp_path):
    """Decision 46: with the frame analyses chosen, the check covers their pickup files."""
    chosen_job = job(tmp_path, *CURRENT_ITEMS, *FRAMES)
    assert chosen_job.stages == ("0500", "0600", "0610", "0611", "0612", "0620", "0621", "0622", "0710", "0720")
    names = {artifact.path.name for artifact in planned(chosen_job.options, chosen_job.stages)}
    assert {"線路方向.pik", "線路直角方向_ピックアップ反力.csv", "線路方向_ピックアップ変位量.csv.provenance.json"} <= names
    plain = job(tmp_path, *CURRENT_ITEMS)
    assert not any(artifact.path.suffix == ".pik" for artifact in planned(plain.options, plain.stages))


def test_the_check_covers_the_folders_of_the_chosen_nonlinear_analysis(tmp_path):
    """Decision 47: with the static nonlinear analyses chosen, the check covers their JRSNAP folders."""
    chosen_job = job(tmp_path, *CURRENT_ITEMS, *NONLINEAR)
    folders = [artifact for artifact in planned(chosen_job.options, chosen_job.stages) if artifact.folder]
    assert [artifact.path.name for artifact in folders] == ["線路方向_JRSNAP", "線路直角方向_JRSNAP"]


def test_there_is_no_jrsnap_or_switch_choice():
    """Decisions 42, 72: the NDUs are always written with their stage, and no switch adds stages to a generation."""
    with pytest.raises(TypeError):
        CalculationJob("id", Path("i"), Path("o"), Path("p"), "0", (), jrsnap=True)
    with pytest.raises(TypeError):
        CalculationJob("id", Path("i"), Path("o"), Path("p"), "0", (), frame_analysis=True)
    parameters = inspect.signature(CalculationController.start).parameters
    assert not {"jrsnap", "frame_analysis", "nonlinear_analysis"} & set(parameters)


def test_the_check_covers_the_ndus_of_the_real_registry(tmp_path):
    chosen_job = job(tmp_path, *CURRENT_ITEMS)
    names = {artifact.path.name for artifact in planned(chosen_job.options, chosen_job.stages)}
    assert {"線路方向.ndu", "線路直角方向.ndu", "線路方向.ndu.provenance.json",
            "線路直角方向.ndu.provenance.json"} <= names


def test_a_successful_generation_is_verified(tmp_path, input_path, stages):
    control, runner, result = run(tmp_path, input_path, stages)
    assert result.success and control.state == "success"
    assert result.message == "計算・PDF出力が完了しました（3帳票）。"
    assert [path.name for path in result.pdf_paths] == ["0500_直接基礎.pdf", "0610_線路方向荷重.pdf", "0710_線路方向荷重.pdf"]
    assert "0500 計算書" in result.stdout
    assert runner.commands[0][-1] == "--overwrite"
    assert control.post_dir == (tmp_path / "post").resolve()
    assert (tmp_path / "post" / "線路方向.ndu").read_bytes() == b"NDU\r\n"
    assert (tmp_path / "post" / "線路方向.ndu.provenance.json").exists()
    assert control.check_current_outputs() is None


def test_a_generation_with_the_frame_analysis_is_verified(tmp_path, input_path, stages):
    control, runner, result = run(tmp_path, input_path, stages, items=("longitudinal_frame_analysis",))
    assert result.success, result.message
    assert control.job.stages == ("0500", "0610", "0611", "0710")
    assert [path.name for path in result.pdf_paths] == ["0500_直接基礎.pdf", "0610_線路方向荷重.pdf", "0710_線路方向荷重.pdf"]
    assert (tmp_path / "post" / "線路方向.pik").read_bytes().startswith("FAKE PIK 線路方向.json ".encode())
    (tmp_path / "post" / "線路方向.pik").write_bytes(b"replaced")
    with pytest.raises(calculation.ArtifactValidationError, match="別の生成の成果物があります: 線路方向.pik"):
        validate_outputs(control.job, registry=stages)


def test_a_generation_without_the_frame_analysis_removes_old_pickup_files(tmp_path, input_path, stages):
    original = input_path.read_bytes()
    run(tmp_path, input_path, stages, items=("longitudinal_frame_analysis",))
    input_path.write_bytes(original)
    control, _, result = run(tmp_path, input_path, stages)
    assert result.success and "0611" not in control.job.stages
    assert not (tmp_path / "post" / "線路方向.pik").exists()  # removed (decision 74)


def test_a_generation_with_the_nonlinear_analysis_checks_the_folder_as_a_whole(tmp_path, input_path, stages):
    control, runner, result = run(tmp_path, input_path, stages, items=("longitudinal_nonlinear_analysis",))
    assert result.success, result.message
    assert control.job.stages == ("0500", "0610", "0710", "0711")
    folder = tmp_path / "post" / "線路方向_JRSNAP"
    assert sorted(path.suffix for path in folder.iterdir()) == [".DB1", ".LOG", ".OUT", ".ndt"]
    assert control.check_current_outputs() is None
    (folder / "線路方向(Case1_ρm10_αf1_正向).OUT").write_bytes(b"replaced")
    assert "計算後に出力ファイルが変更されました: 線路方向_JRSNAP" in control.check_current_outputs()
    assert control.state == "stale"
    with pytest.raises(calculation.ArtifactValidationError, match="別の生成の成果物があります: 線路方向_JRSNAP"):
        validate_outputs(control.job, registry=stages)


def test_a_folder_that_is_not_one_any_more_breaks_the_generation(tmp_path, input_path, stages):
    control, _, _ = run(tmp_path, input_path, stages, items=("longitudinal_nonlinear_analysis",))
    folder = tmp_path / "post" / "線路方向_JRSNAP"
    for path in folder.iterdir():
        path.unlink()
    folder.rmdir()
    folder.write_bytes(b"a file")
    with pytest.raises(calculation.ArtifactValidationError, match="出力がフォルダーではありません: 線路方向_JRSNAP"):
        validate_outputs(control.job, registry=stages)


def test_a_replaced_ndu_breaks_the_generation(tmp_path, input_path, stages):
    control, _, _ = run(tmp_path, input_path, stages)
    (tmp_path / "post" / "線路方向.ndu").write_bytes(b"NDU 2\r\n")
    with pytest.raises(calculation.ArtifactValidationError, match="線路方向.ndu"):
        validate_outputs(control.job, registry=stages)


def test_a_failing_cli_is_reported_with_its_log(tmp_path, input_path, stages):
    input_path.write_text(input_path.read_text(encoding="utf-8").replace('"schema_version": 2', '"schema_version": 1'),
                          encoding="utf-8")
    control, _, result = run(tmp_path, input_path, stages)
    assert not result.success and control.state == "failed" and result.returncode == 2
    assert result.message == "計算に失敗しました（終了コード 2）。実行ログを確認してください。"
    assert "schema_version" in result.stderr


def test_a_runner_that_cannot_start_is_reported(tmp_path, input_path, stages):
    def broken(command, **kwargs):
        raise FileNotFoundError("python")

    control = controller(tmp_path, broken, stages)
    start(control, input_path, stages)
    result = wait(control)
    assert not result.success and result.message == "計算を実行できませんでした: FileNotFoundError: python"


def test_only_one_calculation_runs_at_a_time(tmp_path, input_path, stages):
    control = controller(tmp_path, InProcessRunner(stages), stages)
    start(control, input_path, stages)
    with pytest.raises(RuntimeError, match="計算中です"):
        start(control, input_path, stages)
    assert wait(control).success


def edit(path):
    return lambda command: path.write_bytes(path.read_bytes() + b"\n")


def test_an_input_changed_after_the_run_makes_the_result_stale(tmp_path, input_path, stages):
    control, _, result = run(tmp_path, input_path, stages, after=edit(input_path))
    assert not result.success and control.state == "stale"
    assert result.message == "入力ファイルが計算開始時から変更されています。現在の入力で再計算してください。"


def test_an_input_changed_before_the_run_is_another_generation(tmp_path, input_path, stages):
    control, _, result = run(tmp_path, input_path, stages, before=edit(input_path))
    assert not result.success and control.state == "failed"
    assert result.message == "計算結果の検証に失敗しました: 入力SHAが一致しない成果物です: 0500_直接基礎.json"


def test_files_of_another_generation_are_rejected(tmp_path, input_path, stages):
    control, _, result = run(tmp_path, input_path, stages)
    job = control.job
    report = tmp_path / "output" / "0500_直接基礎.json"
    document = json.loads(report.read_text(encoding="utf-8"))
    document["input"]["sha256"] = "f" * 64
    report.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(calculation.ArtifactValidationError, match="入力SHAが一致しない成果物です: 0500_直接基礎.json"):
        validate_outputs(job, registry=stages)


def test_a_replaced_export_breaks_the_generation(tmp_path, input_path, stages):
    control, _, _ = run(tmp_path, input_path, stages)
    (tmp_path / "post" / "線路方向.json").write_bytes(b'{"frame": 2}\n')
    with pytest.raises(calculation.ArtifactValidationError, match="付帯JSONと出力が一致しません"):
        validate_outputs(control.job, registry=stages)


def test_a_report_of_another_generation_breaks_the_set(tmp_path, input_path, stages):
    control, _, _ = run(tmp_path, input_path, stages)
    pdf = tmp_path / "output" / "0610_線路方向荷重.pdf"
    from gui_support import write_pdf
    write_pdf(pdf, 1)
    with pytest.raises(calculation.ArtifactValidationError, match="別の生成の成果物があります: 0610_線路方向荷重.pdf"):
        validate_outputs(control.job, registry=stages)


def test_a_sidecar_listing_other_files_is_rejected(tmp_path, input_path, stages):
    control, _, _ = run(tmp_path, input_path, stages)
    sidecar = tmp_path / "post" / "線路方向.json.provenance.json"
    document = json.loads(sidecar.read_text(encoding="utf-8"))
    document["artifacts"] = document["artifacts"][1:]
    sidecar.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(calculation.ArtifactValidationError, match="成果物一覧が今回の生成と一致しません"):
        validate_outputs(control.job, registry=stages)


@pytest.mark.parametrize("damage,message", [
    (lambda out: (out / "0500_直接基礎.pdf").unlink(), "成果物を確認できません"),
    (lambda out: (out / "0500_直接基礎.pdf").write_bytes(b"not a pdf"), "成果物を確認できません"),
    (lambda out: (out / "0500_直接基礎.json").write_text("[1]", encoding="utf-8"), "JSONの形式が違います"),
])
def test_missing_or_broken_files_are_rejected(tmp_path, input_path, stages, damage, message):
    control, _, _ = run(tmp_path, input_path, stages)
    damage(tmp_path / "output")
    with pytest.raises(calculation.ArtifactValidationError, match=message):
        validate_outputs(control.job, registry=stages)


def test_a_failed_check_is_reported(tmp_path, input_path, stages, monkeypatch):
    def damaged(job, **kwargs):
        raise calculation.ArtifactValidationError("壊れています")

    monkeypatch.setattr(calculation, "validate_outputs", damaged)
    control, _, result = run(tmp_path, input_path, stages)
    assert not result.success and result.message == "計算結果の検証に失敗しました: 壊れています"


def test_a_change_after_success_marks_the_result_stale(tmp_path, input_path, stages):
    control, _, _ = run(tmp_path, input_path, stages)
    (tmp_path / "output" / "0710_線路方向荷重.pdf").write_bytes(b"changed")
    assert "再計算してください" in control.check_current_outputs()
    assert control.state == "stale" and control.check_current_outputs() is None


def test_long_logs_keep_their_end(tmp_path, input_path, stages):
    def chatty(command, *, stdout, stderr, **kwargs):
        stdout.write(b"x" * (calculation.MAX_LOG_BYTES + 10) + "最後".encode("utf-8"))
        return subprocess.CompletedProcess(command, 1)

    control = controller(tmp_path, chatty, stages)
    start(control, input_path, stages)
    result = wait(control)
    assert result.stdout.startswith(calculation.LOG_TRUNCATED) and result.stdout.endswith("最後")


def test_mark_stale_only_changes_a_success(tmp_path, stages):
    control = controller(tmp_path, None, stages)
    control.mark_stale()
    assert control.state == "idle"
    assert control.output_dir == (tmp_path / "output").resolve()
    assert CalculationController(None).output_dir == calculation.PROJECT_DIR / "output"


def test_the_controller_and_checks_belong_to_the_main_thread(tmp_path, stages):
    import threading
    errors = []

    def other():
        try:
            CalculationController(tmp_path, registry=stages)
        except RuntimeError as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=other)
    thread.start()
    thread.join()
    assert errors == ["計算状態とPDFの検証はメインスレッドで処理してください"]
