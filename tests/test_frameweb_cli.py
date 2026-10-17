"""Normal CLI runs publish the reports and native model as one generation."""

import hashlib
import importlib
import json
import os
from pathlib import Path

import pytest

from src import cli, frameweb_artifacts as artifacts


@pytest.fixture
def quick_reports(monkeypatch):
    # Rendering is replaced here; real runtime identity has dedicated tests.
    source = Path(cli.__file__).resolve()
    monkeypatch.setattr(cli, "implementation_hashes", lambda: {source: cli.file_sha256(source)})
    recorded = {}
    def render(result, path):
        recorded[result.get("stage", "0500")] = result
        Path(path).write_bytes(b"test PDF bytes\r\n")
    for module, name in (("report", "render_report"), ("reaction_report", "render_reaction_report"),
                         ("longitudinal_report", "render_longitudinal_report"),
                         ("transverse_report", "render_transverse_report"),
                         ("seismic_longitudinal_report", "render_seismic_longitudinal_report"),
                         ("seismic_transverse_report", "render_seismic_transverse_report")):
        monkeypatch.setattr(importlib.import_module("src." + module), name, render)
    return recorded


def output_files(parent):
    return {path.relative_to(parent): path.read_bytes() for path in parent.rglob("*") if path.is_file()}


def test_resolve_production_custom_and_explicit_post_paths(tmp_path, monkeypatch):
    project = tmp_path / "project"
    monkeypatch.setattr(artifacts, "PROJECT_DIR", project)
    assert artifacts.resolve_post_dir(project / "output") == project / "post"
    assert artifacts.resolve_post_dir(project / "other") == project / "other" / "post"
    assert artifacts.resolve_post_dir(project / "output", tmp_path / "explicit") == tmp_path / "explicit"


def test_provenance_hashes_saved_bytes_including_newlines(tmp_path):
    native, result, pdf = (tmp_path / name for name in (artifacts.NATIVE_FILENAME, "0610.json", "0610.pdf"))
    for path, content in ((native, b'{"dimension":2}\r\n'), (result, b'{"stage":"0610"}\n'), (pdf, b"PDF\r\n")):
        path.write_bytes(content)
    mapping = {"conventions": {"rigid": "finite"}, "basic_cases": [{"id": 1, "source": "$.basic_cases[0]"}]}
    metadata = artifacts.build_provenance(input_sha256="a" * 64, input_file="input.json", native_path=native,
        result_json_path=result, result_pdf_path=pdf, correspondence=mapping)
    assert metadata["schema_version"] == 1
    assert metadata["convention_version"] == artifacts.CONVENTION_VERSION
    assert metadata["provenance"] == {"input_file": "input.json", "input_sha256": "a" * 64}
    assert metadata["correspondence"] == mapping
    for key, path in (("native", native), ("result_json", result), ("result_pdf", pdf)):
        assert metadata["artifacts"][key] == {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.mark.parametrize("stage,count", [("0610", 4), ("0620", 4), ("all", 16)])
def test_normal_stage_publishes_native_and_bound_sidecar(tmp_path, quick_reports, stage, count, capsys):
    output = tmp_path / "output"
    assert cli.main(["--stage", stage, "--output-dir", str(output)]) == 0
    files = output_files(output)
    assert len(files) == count
    frame_stage = "0620" if stage == "0620" else "0610"
    native, sidecar = artifacts.frameweb_paths(output / "post", stage=frame_stage)
    assert native.is_file() and sidecar.is_file()
    document = json.loads(native.read_text(encoding="utf-8"))
    assert len(document["load"]) == (22 if frame_stage == "0620" else 28)
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    result = quick_reports[frame_stage]
    artifacts.validate_frameweb_artifacts(post_dir=output / "post", output_dir=output,
                                         expected_input_sha256=result["provenance"]["input_sha256"], stage=frame_stage)
    assert metadata["correspondence"]["verified_variant_count"] == (37 if frame_stage == "0620" else 28)
    assert metadata["schema_version"] == 2
    printed = capsys.readouterr().out
    assert str(native.resolve()) in printed and str(sidecar.resolve()) in printed


def test_explicit_post_dir_is_used_and_sidecar_published_last(tmp_path, quick_reports, monkeypatch):
    output, post = tmp_path / "reports", tmp_path / "native"
    actual = os.replace
    destinations = []
    def replace(source, destination):
        source, destination = Path(source), Path(destination)
        if not source.name.endswith(".backup"):
            destinations.append(destination)
            assert source.parent.parent == destination.parent
        return actual(source, destination)
    monkeypatch.setattr(os, "replace", replace)
    assert cli.main(["--stage", "0610", "--output-dir", str(output), "--post-dir", str(post)]) == 0
    assert len(output_files(output)) == len(output_files(post)) == 2
    assert destinations[-1] == post / artifacts.PROVENANCE_FILENAME
    assert not (output / "post").exists()


@pytest.mark.parametrize("stage", ["0500", "0600", "0710", "0720"])
def test_other_stages_never_touch_post(tmp_path, quick_reports, stage):
    output, post = tmp_path / "output", tmp_path / "post"
    post.mkdir()
    old = post / artifacts.NATIVE_FILENAME
    old.write_bytes(b"old native")
    assert cli.main(["--stage", stage, "--output-dir", str(output), "--post-dir", str(post)]) == 0
    assert output_files(post) == {Path(artifacts.NATIVE_FILENAME): b"old native"}
    assert len(output_files(output)) == 2


def test_exporter_receives_exact_renderer_result_and_native_is_deterministic(tmp_path, quick_reports, monkeypatch):
    actual = cli.build_frameweb_input
    received = []
    def export(result):
        received.append(result)
        return actual(result)
    monkeypatch.setattr(cli, "build_frameweb_input", export)
    output = tmp_path / "output"
    command = ["--stage", "0610", "--output-dir", str(output)]
    assert cli.main(command) == 0
    assert received[-1] is quick_reports["0610"]
    native, sidecar = artifacts.frameweb_paths(output / "post")
    initial = native.read_bytes()
    correspondence = json.loads(sidecar.read_text(encoding="utf-8"))["correspondence"]
    assert cli.main(command + ["--overwrite"]) == 0
    assert native.read_bytes() == initial
    assert json.loads(sidecar.read_text(encoding="utf-8"))["correspondence"] == correspondence


@pytest.mark.parametrize("target", [artifacts.NATIVE_FILENAME, artifacts.PROVENANCE_FILENAME])
@pytest.mark.parametrize("collision", ["existing", "directory", "input"])
def test_post_destinations_obey_overwrite_file_type_and_input_protection(tmp_path, quick_reports, target, collision):
    output, post = tmp_path / "output", tmp_path / "post"
    post.mkdir()
    path = post / target
    command = ["--stage", "0610", "--output-dir", str(output), "--post-dir", str(post)]
    if collision == "directory":
        path.mkdir()
        (path / "keep").write_bytes(b"keep")
        command += ["--overwrite"]
    elif collision == "input":
        path.write_bytes((cli.PROJECT_DIR / "pre" / "input.json").read_bytes())
        command += ["--input", str(path), "--overwrite"]
    else:
        path.write_bytes(b"old")
    before = output_files(post)
    assert cli.main(command) == 2
    assert output_files(post) == before
    assert not output.exists()


def test_post_symlink_is_rejected_without_changing_target(tmp_path, quick_reports):
    post = tmp_path / "post"
    post.mkdir()
    target = tmp_path / "target"
    target.write_bytes(b"keep")
    link = post / artifacts.NATIVE_FILENAME
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Platform cannot create symlink: {exc}")
    assert cli.main(["--stage", "0610", "--output-dir", str(tmp_path / "output"),
                     "--post-dir", str(post), "--overwrite"]) == 2
    assert link.is_symlink() and target.read_bytes() == b"keep"


@pytest.mark.parametrize("stage", ["0610", "0620", "all"])
@pytest.mark.parametrize("existing", [False, True])
def test_post_publication_failure_rolls_back_every_artifact(tmp_path, quick_reports, monkeypatch, stage, existing):
    output, post = tmp_path / "output", tmp_path / "post"
    command = ["--stage", stage, "--output-dir", str(output), "--post-dir", str(post)]
    if existing:
        assert cli.main(command) == 0
    before = output_files(tmp_path)
    actual = os.replace
    def fail(source, destination):
        source, destination = Path(source), Path(destination)
        sidecar_name = artifacts.frameweb_paths(post, stage="0620" if stage == "0620" else "0610")[1].name
        if source.name == sidecar_name and destination.parent == post:
            raise PermissionError("post sidecar locked")
        return actual(source, destination)
    monkeypatch.setattr(os, "replace", fail)
    assert cli.main(command + ["--overwrite"]) == 2
    assert output_files(tmp_path) == before
    assert not list(tmp_path.rglob(".webpier-*"))


def test_export_failure_does_not_render_or_touch_old_artifacts(tmp_path, monkeypatch, quick_reports):
    output = tmp_path / "output"
    command = ["--stage", "0610", "--output-dir", str(output)]
    assert cli.main(command) == 0
    before = output_files(output)
    quick_reports.clear()
    def fail(result):
        raise cli.InputError("invalid FrameWeb conversion")
    monkeypatch.setattr(cli, "build_frameweb_input", fail)
    assert cli.main(command + ["--overwrite"]) == 2
    assert output_files(output) == before and quick_reports == {}


@pytest.mark.parametrize("modified", ["native", "sidecar", "result_json", "result_pdf", "missing_native"])
def test_generation_validator_rejects_missing_modified_or_old_artifacts(tmp_path, quick_reports, modified):
    output = tmp_path / "output"
    assert cli.main(["--stage", "0610", "--output-dir", str(output)]) == 0
    post = output / "post"
    native, sidecar = artifacts.frameweb_paths(post)
    expected = quick_reports["0610"]["provenance"]["input_sha256"]
    paths = {"native": native, "result_json": output / f"{artifacts.LONGITUDINAL_OUTPUT_STEM}.json",
             "result_pdf": output / f"{artifacts.LONGITUDINAL_OUTPUT_STEM}.pdf"}
    if modified == "sidecar":
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        metadata["provenance"]["input_sha256"] = "0" * 64
        sidecar.write_text(json.dumps(metadata), encoding="utf-8")
    elif modified == "missing_native":
        native.unlink()
    else:
        paths[modified].write_bytes(paths[modified].read_bytes() + b" ")
    with pytest.raises(ValueError):
        artifacts.validate_frameweb_artifacts(post_dir=post, output_dir=output, expected_input_sha256=expected)


def test_all_has_one_publication_id_and_complete_manifest_in_both_sidecars(tmp_path, quick_reports, monkeypatch):
    output, post = tmp_path / "reports", tmp_path / "post"
    actual = os.replace
    published = []
    def replace(source, destination):
        if Path(source).parent.name.startswith(".webpier-") and not Path(source).name.endswith(".backup"):
            published.append(Path(destination))
        return actual(source, destination)
    monkeypatch.setattr(os, "replace", replace)
    assert cli.main(["--stage", "all", "--output-dir", str(output), "--post-dir", str(post)]) == 0
    sidecars = [artifacts.frameweb_paths(post, stage=stage)[1] for stage in ("0610", "0620")]
    first, second = [json.loads(path.read_text("utf-8")) for path in sidecars]
    assert first["publication_id"] == second["publication_id"]
    assert first["artifact_manifest"] == second["artifact_manifest"]
    assert len(first["artifact_manifest"]) == 14
    assert first["selected_stages"] == ["0500", "0600", "0610", "0620", "0710", "0720"]
    assert {entry["role"] for entry in first["artifact_manifest"] if entry["role"].startswith("0710.")} == {
        "0710.result_pdf", "0710.result_json"}
    assert {entry["role"] for entry in first["artifact_manifest"] if entry["role"].startswith("0720.")} == {
        "0720.result_pdf", "0720.result_json"}
    assert first["expected_sidecars"] == second["expected_sidecars"]
    assert len(first["expected_sidecars"]) == 2
    assert published[-2:] == sidecars
    assert not any(".provenance.json" in entry["path"] for entry in first["artifact_manifest"])


@pytest.mark.parametrize("stage,other", [("0610", "0620"), ("0620", "0610")])
def test_direction_only_preserves_other_direction_bytes(tmp_path, quick_reports, stage, other):
    output, post = tmp_path / "reports", tmp_path / "post"
    command = ["--output-dir", str(output), "--post-dir", str(post)]
    assert cli.main(command + ["--stage", "all"]) == 0
    other_paths = artifacts.frameweb_paths(post, stage=other)
    original = {path: path.read_bytes() for path in other_paths}
    native = artifacts.frameweb_paths(post, stage=stage)[0]
    native_bytes = native.read_bytes()
    assert cli.main(command + ["--stage", stage, "--overwrite"]) == 0
    assert {path: path.read_bytes() for path in other_paths} == original
    assert native.read_bytes() == native_bytes
    artifacts.validate_frameweb_artifacts(post_dir=post, output_dir=output,
        expected_input_sha256=quick_reports[stage]["provenance"]["input_sha256"], stage=stage,
        expected_stages=(stage,))
    with pytest.raises(ValueError):
        artifacts.validate_frameweb_artifacts(post_dir=post, output_dir=output,
            expected_input_sha256=quick_reports[stage]["provenance"]["input_sha256"],
            expected_stages=("0500", "0600", "0610", "0620", "0710", "0720"))


@pytest.mark.parametrize("sidecar_stage", ["0610", "0620"])
def test_all_last_sidecars_failure_preserves_dirty_previous_generation(tmp_path, quick_reports, monkeypatch, sidecar_stage):
    output = tmp_path / "output"
    command = ["--output-dir", str(output)]
    assert cli.main(command) == 0
    for path in output.rglob("*.json"):
        path.write_bytes(path.read_bytes() + b" ")
    before = output_files(output)
    target = artifacts.frameweb_paths(output / "post", stage=sidecar_stage)[1]
    actual = os.replace
    def fail(source, destination):
        if Path(destination) == target and Path(source).name == target.name:
            raise PermissionError("sidecar publication failure")
        return actual(source, destination)
    monkeypatch.setattr(os, "replace", fail)
    assert cli.main(command + ["--overwrite"]) == 2
    assert output_files(output) == before


def test_final_bytes_validation_failure_restores_entire_generation(tmp_path, quick_reports, monkeypatch):
    output = tmp_path / "output"
    command = ["--output-dir", str(output)]
    assert cli.main(command) == 0
    before = output_files(output)
    actual = cli.validate_frameweb_artifacts
    seen = []
    def fail_after_publish(**kwargs):
        seen.append(bool(kwargs.get("read_paths")))
        if not kwargs.get("read_paths"):
            raise cli.InputError("final byte check failed")
        actual(**kwargs)
    monkeypatch.setattr(cli, "validate_frameweb_artifacts", fail_after_publish)
    assert cli.main(command + ["--overwrite"]) == 2
    assert seen == [True, False]
    assert output_files(output) == before
