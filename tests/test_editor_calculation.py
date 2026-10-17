"""The calculation worker and its publication checks, without a Tk window."""

import json
from copy import deepcopy
from functools import cache
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import pymupdf
import pytest

from src import editor_calculation as calculation
from test_jrsnap_cli import fake_ndu as fake_ndu  # noqa: PLC0414 - pytest fixture export


PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def jrsnap_fileset(tmp_path, monkeypatch, fake_ndu):
    import importlib

    from src import cli
    from test_seismic_longitudinal_cli import RENDERERS

    with pymupdf.open() as document:
        document.new_page().insert_text((40, 40), "Generated report")
        pdf = document.tobytes()

    def render(result, path):
        path.write_bytes(pdf)

    for module, function in RENDERERS:
        monkeypatch.setattr(importlib.import_module("src." + module), function, render)
    source, output = tmp_path / "input.json", tmp_path / "output"
    source.write_bytes((PROJECT / "pre" / "input.json").read_bytes())
    assert cli.main(["--input", str(source), "--output-dir", str(output), "--stage", "all", "--jrsnap"]) == 0
    return source, output, calculation.input_sha256(source)


def test_jrsnap_job_propagates_flag_and_verifies_twenty_outputs(jrsnap_fileset):
    source, output, digest = jrsnap_fileset
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    controller = calculation.CalculationController(output_dir=output, runner=run)
    job = controller.start(source, digest, jrsnap=True)
    assert job.jrsnap is True
    result = finish(controller)
    assert result.success and len(controller._verified_outputs) == 20
    assert commands[0][-1] == "--jrsnap"
    assert "JRSNAP" in result.message
    native = output / "post" / "線路方向.ndu"
    native.write_bytes(native.read_bytes() + b"changed")
    assert controller.check_current_outputs() is not None
    assert controller.state == "stale"


@pytest.mark.parametrize("stage", ["0710", "0720"])
@pytest.mark.parametrize("change", ["missing_native", "missing_sidecar", "other_generation"])
def test_enabled_job_rejects_incomplete_or_mixed_generation(jrsnap_fileset, change, stage):
    source, output, digest = jrsnap_fileset
    native, sidecar = calculation.jrsnap_paths(output / "post", stage=stage)
    if change == "missing_native":
        native.unlink()
    elif change == "missing_sidecar":
        sidecar.unlink()
    else:
        data = json.loads(sidecar.read_text("utf-8"))
        data["publication_id"] = "other-generation"
        sidecar.write_text(json.dumps(data), encoding="utf-8")
    controller = calculation.CalculationController(output_dir=output, runner=completed())
    controller.start(source, digest, jrsnap=True)
    result = finish(controller)
    assert not result.success and controller.state == "failed"


@cache
def frameweb_template(stage="0610"):
    from src.calculator import calculate
    from src.frameweb_export import build_frameweb_input
    from src.inputs import parse_input
    from src.longitudinal_calculator import calculate_longitudinal
    from src.transverse_calculator import calculate_transverse
    from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
    from src.reaction_calculator import calculate_reactions
    from src.reaction_inputs import parse_reaction_input

    data = json.loads((PROJECT / "tests" / "fixtures" / "frameweb_p7_reference.json").read_text("utf-8"))["input"]
    reaction_inputs = parse_reaction_input(data)
    calculate_direction = calculate_longitudinal if stage == "0610" else calculate_transverse
    result = calculate_direction(
        reaction_inputs, calculate(parse_input(data)), calculate_reactions(reaction_inputs),
        design_conditions=parse_longitudinal_design_conditions(data),
    )
    return result, build_frameweb_input(result)


def write_outputs(output, digest, *, post_dir=None):
    from src.frameweb_artifacts import (ALL_STAGES, FRAMEWEB_STAGES, build_artifact_manifest,
                                               build_provenance, frameweb_paths, publication_paths, resolve_post_dir)

    output.mkdir(parents=True, exist_ok=True)
    templates = {stage: frameweb_template(stage) for stage in FRAMEWEB_STAGES}
    results = {stage: deepcopy(template[0]) for stage, template in templates.items()}
    for result in results.values():
        result["provenance"].update(input_sha256=digest, input_file="test-input.json")
    with pymupdf.open() as document:
        document.new_page().insert_text((40, 40), "First page")
        document.new_page().insert_text((40, 40), "Last page")
        pdf = document.tobytes()
    for stem in calculation.OUTPUT_STEMS:
        (output / f"{stem}.pdf").write_bytes(pdf)
        (output / f"{stem}.json").write_text(
            json.dumps(results.get(stem[:4], {"provenance": {"input_sha256": digest}})), encoding="utf-8"
        )
    post_dir = resolve_post_dir(output, post_dir)
    post_dir.mkdir(parents=True, exist_ok=True)
    for stage, (_, exported) in templates.items():
        native, _ = frameweb_paths(post_dir, stage=stage)
        native.write_text(json.dumps(exported.document, allow_nan=False), encoding="utf-8")
    declared, sidecars = publication_paths(output, post_dir, ALL_STAGES)
    manifest = build_artifact_manifest(declared)
    publication_id = uuid.uuid4().hex
    for stage, (_, exported) in templates.items():
        native, sidecar = frameweb_paths(post_dir, stage=stage)
        provenance = build_provenance(
            input_sha256=digest, input_file="test-input.json", native_path=native,
            result_json_path=declared[f"{stage}.result_json"], result_pdf_path=declared[f"{stage}.result_pdf"],
            correspondence=exported.source_mapping, stage=stage, publication_id=publication_id,
            selected_stages=ALL_STAGES, artifact_manifest=manifest,
            expected_sidecars=[{"role": role, "path": str(path.resolve())} for role, path in sidecars.items()],
        )
        sidecar.write_text(json.dumps(provenance, allow_nan=False), encoding="utf-8")


@pytest.fixture
def fileset(tmp_path):
    source = tmp_path / "日本語 入力.json"
    source.write_text('{"入力": 1}', encoding="utf-8")
    output = tmp_path / "帳票 出力"
    digest = calculation.input_sha256(source)
    write_outputs(output, digest)
    return source, output, digest


def finish(controller, timeout=20):
    if controller._thread is not None and controller._thread.ident is not None:
        controller._thread.join(timeout)
        assert not controller._thread.is_alive(), "calculation worker did not finish"
    result = controller.poll()
    assert result is not None
    assert not controller.running
    return result


def completed(code=0):
    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, code)
    return run


def test_command_preserves_paths_and_runs_only_subprocess_on_worker(fileset, monkeypatch):
    source, output, digest = fileset
    received = {}
    main_ident = threading.get_ident()

    def run(command, **kwargs):
        received.update(command=command, kwargs=kwargs, thread=threading.get_ident())
        kwargs["stdout"].write("正常終了\n".encode("utf-8"))
        return subprocess.CompletedProcess(command, 0)

    actual_validate = calculation.validate_outputs
    controller = calculation.CalculationController(output_dir=output, runner=run)

    def validate(job, **kwargs):
        assert threading.get_ident() == main_ident
        assert controller.running
        assert controller.state == "running"
        return actual_validate(job, **kwargs)

    monkeypatch.setattr(calculation, "validate_outputs", validate)
    job = controller.start(source, digest)
    result = finish(controller)
    assert received["thread"] != main_ident
    assert received["command"] == [
        sys.executable, str(PROJECT / "run_design.py"), "--input", str(source),
        "--output-dir", str(output), "--post-dir", str(output / "post"),
        "--stage", "all", "--overwrite",
    ]
    options = received["kwargs"]
    assert options["shell"] is False
    assert options["cwd"] == str(PROJECT)
    assert options["stdin"] == subprocess.DEVNULL
    assert options["encoding"] == "utf-8"
    assert options["env"]["PYTHONIOENCODING"] == "utf-8"
    assert options["env"]["PYTHONUTF8"] == "1"
    assert options["creationflags"] == (subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert options["stdout"].closed and options["stderr"].closed
    assert result.success and result.returncode == 0
    assert result.job == job and len(job.run_id) == 32
    assert result.stdout == "正常終了\n"
    assert tuple(path.stem for path in result.pdf_paths) == calculation.OUTPUT_STEMS
    assert controller.state == "success"
    assert len(controller._verified_outputs) == 16
    assert controller.check_current_outputs() is None
    assert controller.poll() is None


def test_default_output_does_not_follow_cwd_or_input(fileset, tmp_path, monkeypatch):
    source, _, digest = fileset
    unrelated = tmp_path / "別 cwd"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    seen = []

    def fail(command, **kwargs):
        seen.append(command)
        raise OSError("test only: no output is written")

    assert calculation.default_output_dir() == PROJECT / "output"
    controller = calculation.CalculationController(runner=fail)
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success
    assert controller.output_dir == PROJECT / "output"
    assert seen[0][seen[0].index("--output-dir") + 1] == str(PROJECT / "output")


def test_one_run_guard_lasts_through_unconsumed_completion(fileset):
    source, output, digest = fileset
    started, release = threading.Event(), threading.Event()

    def run(command, **kwargs):
        started.set()
        assert release.wait(5)
        return subprocess.CompletedProcess(command, 0)

    controller = calculation.CalculationController(output, run)
    try:
        first = controller.start(source, digest)
        assert started.wait(5)
        assert controller.busy and controller.poll() is None
        with pytest.raises(RuntimeError, match="計算中"):
            controller.start(source, digest)
        release.set()
        controller._thread.join(5)
        assert controller.running  # Completion alone must not unlock editing.
        with pytest.raises(RuntimeError, match="計算中"):
            controller.start(source, digest)
        assert finish(controller).success
        second = controller.start(source, digest)
        assert first.run_id != second.run_id
        assert finish(controller).success
    finally:
        release.set()


@pytest.mark.parametrize("code", [2, 1, -9])
def test_nonzero_exit_never_relabels_existing_matching_outputs(fileset, code):
    source, output, digest = fileset
    before = {path: path.read_bytes() for path in output.rglob("*") if path.is_file()}
    controller = calculation.CalculationController(output, completed(code))
    assert controller.state == "idle" and controller.result is None
    assert controller.poll() is None
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and not result.pdf_paths
    assert result.returncode == code
    assert str(code) in result.message and controller.state == "failed"
    assert {path: path.read_bytes() for path in output.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("error", [FileNotFoundError("python missing"), RuntimeError("worker failed")])
def test_spawn_and_worker_failures_release_guard_and_allow_retry(fileset, error):
    source, output, digest = fileset

    def fail(*args, **kwargs):
        kwargs["stderr"].write("起動ログ".encode("utf-8"))
        raise error

    controller = calculation.CalculationController(output, fail)
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and result.returncode is None
    assert str(error) in result.message and result.stderr == "起動ログ"
    controller._runner = completed()
    controller.start(source, digest)
    assert finish(controller).success


def test_thread_start_failure_follows_normal_completion_path(fileset, monkeypatch):
    source, output, digest = fileset

    def fail_start(thread):
        raise RuntimeError("thread unavailable")

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    assert controller.running
    result = finish(controller)
    assert not result.success and "thread unavailable" in result.message


def test_large_logs_are_bounded_utf8_tails_and_temporary_handles_close(fileset):
    source, output, digest = fileset
    handles = []

    def run(command, **kwargs):
        for name in ("stdout", "stderr"):
            stream = kwargs[name]
            handles.append(stream)
            stream.write(b"x" * (2 * 1024 * 1024))
            stream.write("\n最後のログ\n".encode("utf-8"))
        return subprocess.CompletedProcess(command, 2)

    controller = calculation.CalculationController(output, run)
    controller.start(source, digest)
    result = finish(controller)
    for text in (result.stdout, result.stderr):
        assert text.startswith(calculation.LOG_TRUNCATED)
        assert text.endswith("最後のログ\n")
        assert len(text) <= calculation.MAX_LOG_BYTES + len(calculation.LOG_TRUNCATED)
    assert all(stream.closed for stream in handles)


def test_log_read_failure_still_closes_files_and_delivers_failure(fileset, monkeypatch):
    source, output, digest = fileset
    handles = []

    def run(command, **kwargs):
        handles.extend((kwargs["stdout"], kwargs["stderr"]))
        return subprocess.CompletedProcess(command, 0)

    def fail_read(stream):
        raise OSError("log read failed")

    monkeypatch.setattr(calculation, "_read_log", fail_read)
    controller = calculation.CalculationController(output, run)
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and "log read failed" in result.message
    assert all(stream.closed for stream in handles)


@pytest.mark.parametrize("stem", calculation.OUTPUT_STEMS)
@pytest.mark.parametrize("suffix", ["pdf", "json"])
def test_missing_each_expected_artifact_fails(fileset, stem, suffix):
    source, output, digest = fileset
    (output / f"{stem}.{suffix}").unlink()
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and not result.pdf_paths


@pytest.mark.parametrize("stem", ["0710_線路方向荷重", "0720_線路直角方向荷重"])
@pytest.mark.parametrize("suffix", ["pdf", "json"])
def test_readable_but_modified_seismic_report_fails_manifest_validation(fileset, stem, suffix):
    source, output, digest = fileset
    path = output / f"{stem}.{suffix}"
    # Whitespace keeps the PDF/JSON readable and the input SHA unchanged.
    path.write_bytes(path.read_bytes() + b" \n")
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and "manifest" in result.message


@pytest.mark.parametrize("suffix", ["pdf", "json"])
def test_artifact_directories_are_rejected(fileset, suffix):
    source, output, digest = fileset
    path = output / f"{calculation.OUTPUT_STEMS[0]}.{suffix}"
    path.unlink()
    path.mkdir()
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and "通常ファイル" in result.message


@pytest.mark.parametrize("payload", ["broken", "[]", "{}", '{"provenance": []}',
                                     '{"provenance": {"input_sha256": "different"}}'])
def test_corrupt_or_mismatching_json_is_not_success(fileset, payload):
    source, output, digest = fileset
    path = output / f"{calculation.OUTPUT_STEMS[1]}.json"
    path.write_text(payload, encoding="utf-8")
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    assert not finish(controller).success


@pytest.mark.parametrize("payload", [b"", b"not a PDF", b"%PDF-1.7\nbroken"])
def test_corrupt_pdf_is_not_success(fileset, payload):
    source, output, digest = fileset
    (output / f"{calculation.OUTPUT_STEMS[2]}.pdf").write_bytes(payload)
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    assert not finish(controller).success


def test_unreadable_output_is_reported(fileset, monkeypatch):
    source, output, digest = fileset
    inaccessible = output / f"{calculation.OUTPUT_STEMS[1]}.json"
    actual_read = Path.read_text

    def read(path, *args, **kwargs):
        if path == inaccessible:
            raise PermissionError("read denied")
        return actual_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and "read denied" in result.message


def test_stat_change_during_validation_is_rejected(fileset, monkeypatch):
    source, output, digest = fileset
    actual_open = pymupdf.open
    changed = output / f"{calculation.OUTPUT_STEMS[0]}.json"

    def open_document(path):
        document = actual_open(path)
        if Path(path).stem == calculation.OUTPUT_STEMS[-1]:
            with changed.open("a", encoding="utf-8") as target:
                target.write(" ")  # Still valid JSON with the same input SHA.
        return document

    monkeypatch.setattr(pymupdf, "open", open_document)
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and "検証中" in result.message


def test_final_input_sha_check_detects_edit_after_cli_read(fileset):
    source, output, digest = fileset
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    source.write_text('{"入力": 2}', encoding="utf-8")
    result = finish(controller)
    assert not result.success and controller.state == "stale"
    assert "入力ファイル" in result.message


def test_pdf_checks_cannot_run_on_background_thread(fileset):
    source, output, digest = fileset
    job = calculation.CalculationJob("test", source, output, digest)
    errors = []

    def validate():
        try:
            calculation.validate_outputs(job)
        except RuntimeError as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=validate)
    thread.start()
    thread.join(5)
    assert len(errors) == 1 and "メインスレッド" in errors[0]


def test_verified_outputs_need_no_timestamp_change_and_can_be_marked_stale(fileset):
    source, output, digest = fileset
    before = {path: path.stat().st_mtime_ns for path in output.iterdir()}
    controller = calculation.CalculationController(output, completed())
    controller.mark_stale()
    assert controller.state == "idle"
    controller.start(source, digest)
    assert finish(controller).success
    controller.mark_stale()
    assert controller.state == "stale"
    controller.start(source, digest)
    assert finish(controller).success
    assert {path: path.stat().st_mtime_ns for path in output.iterdir()} == before


def test_real_cli_all_reports_and_same_input_rerun_use_isolated_output(tmp_path):
    source = tmp_path / "別の場所 入力.json"
    source.write_bytes((PROJECT / "pre" / "input.json").read_bytes())
    output = tmp_path / "帳票 出力"
    digest = calculation.input_sha256(source)
    from src import cli
    single = tmp_path / "single-direction"
    assert cli.main(["--stage", "0620", "--input", str(source), "--output-dir", str(single)]) == 0
    expected_native = (single / "post" / "線路直角方向.json").read_bytes()
    controller = calculation.CalculationController(output)
    run_ids = []
    for _ in range(2):
        run_ids.append(controller.start(source, digest).run_id)
        result = finish(controller, timeout=120)
        assert result.success, result.message + "\n" + result.stderr
        assert controller.check_current_outputs() is None
        assert len(result.pdf_paths) == 6
        assert result.pdf_paths[-1].name == "0720_線路直角方向荷重.pdf"
        assert (output / "post" / "線路直角方向.json").read_bytes() == expected_native
        for pdf in result.pdf_paths:
            with pymupdf.open(pdf) as document:
                assert document.page_count > 0
                if pdf.name.startswith("0720_"):
                    # Variable pages: the report always ends with its combinations.
                    assert "11.3 作用の組合せ" in "".join(page.get_text() for page in document)
                assert document[0].get_pixmap(matrix=pymupdf.Matrix(.1, .1)).width > 0
                assert document[-1].get_pixmap(matrix=pymupdf.Matrix(.1, .1)).height > 0
        assert all(json.loads(path.read_text("utf-8"))["provenance"]["input_sha256"] == digest
                   for path in output.glob("*.json"))
    assert run_ids[0] != run_ids[1]
    assert len(list(output.glob("*.pdf"))) == 6
    assert len(list(output.glob("*.json"))) == 6
    assert not list(output.glob(".pier-design-*"))
    assert calculation.input_sha256(source) == digest


@pytest.mark.parametrize("suffix", ["pdf", "json"])
@pytest.mark.parametrize("change", ["replace", "delete", "corrupt", "unreadable"])
@pytest.mark.parametrize("stem", ["0710_線路方向荷重", "0720_線路直角方向荷重"])
def test_verified_output_identity_is_rechecked_after_success(fileset, monkeypatch, suffix, change, stem):
    source, output, digest = fileset
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    assert finish(controller).success
    assert len(controller._verified_outputs) == 16
    assert controller.check_current_outputs() is None
    path = output / f"{stem}.{suffix}"
    if change == "replace":
        replacement = output / "replacement.tmp"
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)  # Even equal bytes belong to a new file identity.
    elif change == "delete":
        path.unlink()
    elif change == "corrupt":
        path.write_bytes(b"broken artifact")
    else:
        original_open = Path.open
        def denied(target, *args, **kwargs):
            if target == path:
                raise PermissionError("output read denied")
            return original_open(target, *args, **kwargs)
        monkeypatch.setattr(Path, "open", denied)
    message = controller.check_current_outputs()
    assert message is not None and "再計算" in message
    assert controller.state == "stale"
    assert controller.result.success  # Historical calculation success is retained.


def test_extra_pdf_changes_do_not_invalidate_verified_outputs(fileset):
    source, output, digest = fileset
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    assert finish(controller).success
    extra = output / "extra.pdf"
    for content in (b"arbitrary first output", b"different external output"):
        extra.write_bytes(content)
        assert controller.check_current_outputs() is None
        assert controller.state == "success"
    extra.unlink()
    assert controller.check_current_outputs() is None
