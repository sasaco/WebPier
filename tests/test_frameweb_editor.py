"""FrameWeb publication must verify before the editor presents new reports."""

import json

import pytest

from src import editor_calculation as calculation
from test_editor_calculation import PROJECT, completed, fileset, finish, write_outputs
from test_editor_gui import app, pdf_labels


@pytest.mark.parametrize("custom_output", [False, True])
def test_job_resolves_post_destination_and_passes_it_to_child(tmp_path, custom_output):
    source = tmp_path / "入力.json"
    source.write_text("{}", encoding="utf-8")
    output = tmp_path / "帳票" if custom_output else None
    seen = []

    def fail(command, **kwargs):
        seen.append(command)
        raise OSError("test child is not publishing")

    controller = calculation.CalculationController(output, fail)
    job = controller.start(source, calculation.input_sha256(source))
    assert not finish(controller).success
    expected = output / "post" if custom_output else PROJECT / "post"
    assert job.post_dir == controller.post_dir == expected.resolve()
    assert seen[0][seen[0].index("--post-dir") + 1] == str(expected.resolve())


def test_explicit_post_destination_overrides_default_without_changing_output(tmp_path):
    source = tmp_path / "入力.json"
    source.write_text("{}", encoding="utf-8")
    output, post = tmp_path / "帳票", tmp_path / "別の解析入力"
    seen = []

    def fail(command, **kwargs):
        seen.append(command)
        raise OSError("test child is not publishing")

    controller = calculation.CalculationController(output, fail, post_dir=post)
    job = controller.start(source, calculation.input_sha256(source))
    assert not finish(controller).success
    assert controller.output_dir == output.resolve()
    assert job.post_dir == controller.post_dir == post.resolve()
    assert seen[0][seen[0].index("--post-dir") + 1] == str(post.resolve())


def test_reports_without_frameweb_outputs_are_not_success(fileset):
    source, output, digest = fileset
    for path in (output / "post").iterdir():
        path.unlink()
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and not result.pdf_paths
    assert controller.state == "failed"


@pytest.mark.parametrize("name", ["frameWebForJS.json", "frameWebForJS.provenance.json",
                                  "線路直角方向.json", "線路直角方向.provenance.json"])
@pytest.mark.parametrize("failure", ["missing", "broken", "directory"])
def test_invalid_frameweb_artifact_blocks_success(fileset, name, failure):
    source, output, digest = fileset
    path = output / "post" / name
    if failure in {"missing", "directory"}:
        path.unlink()
        if failure == "directory":
            path.mkdir()
    else:
        path.write_text("broken JSON", encoding="utf-8")
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and not result.pdf_paths
    assert controller.state == "failed"


@pytest.mark.parametrize("artifact", ["native", "result_json", "result_pdf", "input"])
def test_old_generation_sidecar_is_rejected(fileset, artifact):
    source, output, digest = fileset
    sidecar = output / "post" / "frameWebForJS.provenance.json"
    document = json.loads(sidecar.read_text("utf-8"))
    if artifact == "input":
        document["provenance"]["input_sha256"] = "0" * 64
    else:
        document["artifacts"][artifact]["sha256"] = "0" * 64
    sidecar.write_text(json.dumps(document), encoding="utf-8")
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and not result.pdf_paths


def test_invalid_native_schema_with_updated_sha_is_rejected(fileset):
    source, output, digest = fileset
    native = output / "post" / "frameWebForJS.json"
    document = json.loads(native.read_text("utf-8"))
    document["dimension"] = 3
    native.write_text(json.dumps(document), encoding="utf-8")
    for sidecar in (output / "post").glob("*.provenance.json"):
        provenance = json.loads(sidecar.read_text("utf-8"))
        if provenance["stage"] == "0610":
            provenance["artifacts"]["native"]["sha256"] = calculation.input_sha256(native)
        for entry in provenance["artifact_manifest"]:
            if entry["role"] == "0610.native":
                entry["sha256"] = calculation.input_sha256(native)
        sidecar.write_text(json.dumps(provenance), encoding="utf-8")
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and not result.pdf_paths
    assert "native: 2D保存形式のトップレベルが不正" in result.message


def test_valid_native_json_changed_without_updating_sidecar_is_rejected(fileset):
    source, output, digest = fileset
    native = output / "post" / "frameWebForJS.json"
    with native.open("a", encoding="utf-8") as target:
        target.write(" ")
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and not result.pdf_paths


def test_explicit_post_outputs_verify_and_return_only_ordered_reports(fileset, tmp_path):
    source, output, digest = fileset
    post = tmp_path / "別の解析入力"
    write_outputs(output, digest, post_dir=post)
    controller = calculation.CalculationController(output, completed(), post_dir=post)
    controller.start(source, digest)
    result = finish(controller)
    assert result.success, result.message
    assert result.pdf_paths == tuple(output / f"{stem}.pdf" for stem in calculation.OUTPUT_STEMS)
    assert set(controller._verified_outputs) == {
        *(output / f"{stem}.{suffix}" for stem in calculation.OUTPUT_STEMS for suffix in ("pdf", "json")),
        post / "frameWebForJS.json", post / "frameWebForJS.provenance.json",
        post / "線路直角方向.json", post / "線路直角方向.provenance.json",
    }
    assert controller.check_current_outputs() is None


@pytest.mark.parametrize("name", ["frameWebForJS.json", "frameWebForJS.provenance.json",
                                  "線路直角方向.json", "線路直角方向.provenance.json"])
@pytest.mark.parametrize("change", ["replace", "delete", "corrupt", "unreadable"])
def test_frameweb_changes_after_success_invalidate_current_outputs(fileset, monkeypatch, name, change):
    source, output, digest = fileset
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    assert finish(controller).success
    path = output / "post" / name
    if change == "replace":
        replacement = path.with_suffix(".tmp")
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
    elif change == "delete":
        path.unlink()
    elif change == "corrupt":
        path.write_bytes(b"changed")
    else:
        path_type = type(path)
        original_open = path_type.open

        def denied(target, *args, **kwargs):
            if target == path:
                raise PermissionError("frame input read denied")
            return original_open(target, *args, **kwargs)

        monkeypatch.setattr(path_type, "open", denied)
    message = controller.check_current_outputs()
    assert message is not None and "再計算" in message
    assert controller.state == "stale"


def test_frameweb_changes_during_completion_validation_are_rejected(fileset, monkeypatch):
    source, output, digest = fileset
    actual_validate = calculation.validate_frameweb_artifacts
    sidecar = output / "post" / "frameWebForJS.provenance.json"

    def changing_validate(**kwargs):
        actual_validate(**kwargs)
        with sidecar.open("a", encoding="utf-8") as target:
            target.write(" ")

    monkeypatch.setattr(calculation, "validate_frameweb_artifacts", changing_validate)
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and "検証中" in result.message
    assert not result.pdf_paths


@pytest.mark.parametrize("failure", ["native_missing", "native_changed", "sidecar_stale"])
def test_gui_does_not_open_or_label_new_pdfs_when_frameweb_validation_fails(app, failure):
    assert app.save()
    output = app.calculation.output_dir
    write_outputs(output, calculation.input_sha256(app.document.path))
    native = output / "post" / "frameWebForJS.json"
    sidecar = output / "post" / "frameWebForJS.provenance.json"
    if failure == "native_missing":
        native.unlink()
    elif failure == "native_changed":
        with native.open("a", encoding="utf-8") as target:
            target.write(" ")
    else:
        provenance = json.loads(sidecar.read_text("utf-8"))
        provenance["provenance"]["input_sha256"] = "0" * 64
        sidecar.write_text(json.dumps(provenance), encoding="utf-8")
    controller = calculation.CalculationController(output, completed())
    app.calculation = controller
    assert app.start_calculation()
    controller._thread.join(5)
    assert not controller._thread.is_alive()
    if app._calculation_after is not None:
        app.root.after_cancel(app._calculation_after)
    app._poll_calculation()
    assert not app._calculation_busy
    assert controller.state == "failed"
    assert not controller.result.success and not controller.result.pdf_paths
    assert app.pdf_dialog is None
    assert "失敗" in app.calculation_status.get()
    assert all("今回未計算" in label for label in pdf_labels(app))


@pytest.mark.parametrize("defect", ["publication_id", "artifact_manifest", "expected_sidecars", "schema1"])
def test_all_gui_rejects_inconsistent_direction_generation(fileset, defect):
    source, output, digest = fileset
    path = output / "post" / "線路直角方向.provenance.json"
    metadata = json.loads(path.read_text("utf-8"))
    if defect == "publication_id":
        metadata[defect] = "another-publication"
    elif defect == "schema1":
        metadata["schema_version"] = 1
    else:
        metadata[defect].pop()
    path.write_text(json.dumps(metadata), encoding="utf-8")
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    assert not finish(controller).success


def test_gui_rejects_incomplete_publication_journal_even_when_all_bytes_match(fileset):
    source, output, digest = fileset
    journal = output / "post" / ".pier-design-interrupted" / "publication-journal.json"
    journal.parent.mkdir()
    journal.write_text('{"state":"publishing"}', encoding="utf-8")
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    result = finish(controller)
    assert not result.success and "journal" in result.message


def test_new_incomplete_publication_invalidates_previously_verified_outputs(fileset):
    source, output, digest = fileset
    controller = calculation.CalculationController(output, completed())
    controller.start(source, digest)
    assert finish(controller).success
    journal = output / "post" / ".pier-design-incomplete" / "publication-journal.json"
    journal.parent.mkdir()
    journal.write_text('{"state":"publishing"}', encoding="utf-8")
    assert "journal" in controller.check_current_outputs()
    assert controller.state == "stale"
