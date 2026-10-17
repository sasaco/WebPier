"""Publication tests isolate the NDU engine; core has its own numeric oracle."""

import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from src import cli, jrsnap_artifacts
from src.frameweb_artifacts import frameweb_paths
from src.inputs import InputError
from test_seismic_longitudinal_cli import files
from test_seismic_longitudinal_cli import quick_reports as quick_reports  # noqa: PLC0414 - pytest fixture export


@pytest.fixture
def fake_ndu(monkeypatch, tmp_path):
    calls = []

    def build(raw, foundation, seismic, *, input_sha256, direction="longitudinal"):
        calls.append((raw, foundation, seismic, input_sha256))
        return {"metadata": {"profile_id": f"p7-{direction}-v52-v1", "schema_version": 1,
                             "direction": direction,
                             "target_version": "5.2-L03", "input_sha256": input_sha256,
                             "canonical_snapshot_sha256": {
                                 "foundation": jrsnap_artifacts.canonical_sha256(foundation),
                                 "seismic": jrsnap_artifacts.canonical_sha256(seismic)}},
                "title": "線路方向" if direction == "longitudinal" else "線路直角方向"}

    def build_transverse(raw, foundation, seismic, *, input_sha256):
        return build(raw, foundation, seismic, input_sha256=input_sha256, direction="transverse")

    def serialize(model):
        return ("JRSNAP 5.2-L03\r\n" + model["title"] + "\r\n").encode("cp932")

    monkeypatch.setitem(sys.modules, "src.jrsnap_export", SimpleNamespace(
        build_longitudinal_ndu_model=build, build_transverse_ndu_model=build_transverse))
    monkeypatch.setitem(sys.modules, "src.jrsnap_ndu", SimpleNamespace(serialize_ndu=serialize))

    def validate(data):
        assert data in {f"JRSNAP 5.2-L03\r\n{title}\r\n".encode("cp932")
                        for title in ("線路方向", "線路直角方向")}

    monkeypatch.setattr(jrsnap_artifacts, "_validate_native", validate)
    implementation = tmp_path / "implementation.py"
    implementation.write_text("profile = 1\n", encoding="utf-8")

    def hashes():
        return {path: jrsnap_artifacts.file_sha256(path) for path in tmp_path.glob("*.py")}

    monkeypatch.setattr(cli, "implementation_hashes", hashes)
    monkeypatch.setattr(jrsnap_artifacts, "implementation_hashes", hashes)
    return calls, implementation


@pytest.fixture
def generation_options(tmp_path):
    source = tmp_path / "input.json"
    source.write_bytes((cli.PROJECT_DIR / "pre" / "input.json").read_bytes())
    return cli.GenerationOptions(source, tmp_path / "output", jrsnap=True, overwrite=True)


@pytest.mark.parametrize("stage,count", [("0710", 4), ("0720", 4), ("all", 20)])
def test_opt_in_publishes_one_generation_and_reuses_calculations(
    generation_options, fake_ndu, quick_reports, stage, count,
):
    options = cli.GenerationOptions(generation_options.input_path, generation_options.output_dir,
                                    stage=stage, jrsnap=True)
    calls, _ = fake_ndu
    selected = "0720" if stage == "0720" else "0710"
    with cli.prepare_generation(options) as candidate:
        assert len(candidate.artifact_hashes) == count
        assert candidate.input_bytes == options.input_path.read_bytes()
        assert calls[0][1] is candidate.computed["0500"]
        assert calls[0][2] is candidate.computed[selected] is quick_reports[selected]
        assert calls[0][3] == candidate.input_sha256
        with pytest.raises(TypeError):
            candidate.artifact_hashes[candidate.ndu_path] = "bad"
        expected = dict(candidate.artifact_hashes)
        candidate.publish()
        assert candidate.published
        assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in expected} == expected
        with pytest.raises(InputError, match="既に公開"):
            candidate.publish()
        metadata = jrsnap_artifacts.validate_jrsnap_artifacts(
            post_dir=options.output_dir / "post", output_dir=options.output_dir,
            expected_input_sha256=candidate.input_sha256, expected_stages=candidate.stages,
            stage=selected,
        )
        assert len(metadata["artifact_manifest"]) == 3
        assert metadata["app_read_verified"] is False
        if stage == "all":
            fw = json.loads(frameweb_paths(options.output_dir / "post")[1].read_text("utf-8"))
            assert fw["schema_version"] == 2 and len(fw["artifact_manifest"]) == 14
            assert len(fw["expected_sidecars"]) == 2
            assert fw["publication_id"] == candidate.publication_id == metadata["publication_id"]
    assert len(files(options.output_dir)) == count


@pytest.mark.parametrize("stage", ["0500", "0600", "0610", "0620"])
def test_invalid_stage_rejected_without_read_or_output(tmp_path, stage, capsys):
    assert cli.main(["--stage", stage, "--jrsnap", "--input", str(tmp_path / "absent.json"),
                     "--output-dir", str(tmp_path / "output")]) == 2
    assert "0710、0720 または all" in capsys.readouterr().err
    assert not (tmp_path / "output").exists()


def test_duplicate_json_keys_rejected_before_calculation(generation_options, fake_ndu):
    generation_options.input_path.write_text('{"x": 1, "x": 2}', encoding="utf-8")
    with pytest.raises(InputError, match="重複"), cli.prepare_generation(generation_options):
        pytest.fail("duplicate keys accepted")
    assert not generation_options.output_dir.exists()


@pytest.mark.parametrize("change", ["input", "source", "candidate", "missing", "additional", "destination",
                                    "model", "calculation", "source_added"])
def test_held_candidate_rejects_changes_before_publication(
    generation_options, fake_ndu, quick_reports, change,
):
    with cli.prepare_generation(generation_options) as candidate:
        staged, destination = candidate.pairs[0]
        if change == "input":
            generation_options.input_path.write_bytes(candidate.input_bytes + b"\n")
        elif change == "source":
            fake_ndu[1].write_text("profile = 2\n", encoding="utf-8")
        elif change == "source_added":
            fake_ndu[1].with_name("new_source.py").write_text("new code", encoding="utf-8")
        elif change == "candidate":
            staged.write_bytes(staged.read_bytes() + b"changed")
        elif change == "missing":
            staged.unlink()
        elif change == "additional":
            staged.with_name("unexpected.txt").write_text("extra", encoding="utf-8")
        elif change == "model":
            candidate.ndu_model["metadata"]["profile_id"] = "changed"
        elif change == "calculation":
            candidate.computed["0500"]["injected"] = "changed"
        else:
            destination.write_bytes(b"competing writer")
        with pytest.raises((InputError, OSError)):
            candidate.publish()
        assert not candidate.published
        if change == "destination":
            assert destination.read_bytes() == b"competing writer"
        else:
            assert not destination.exists()


@pytest.mark.parametrize("existing", [False, True])
def test_late_competing_writer_is_restored_from_actual_backup(
    generation_options, fake_ndu, quick_reports, monkeypatch, existing,
):
    output = generation_options.output_dir
    output.mkdir()
    destination = output / "0710_線路方向荷重.pdf"
    if existing:
        destination.write_bytes(b"initial baseline")
    actual_publish = cli._publish_outputs

    def competing_publish(*args, **kwargs):
        destination.write_bytes(b"late competing writer")
        return actual_publish(*args, **kwargs)

    monkeypatch.setattr(cli, "_publish_outputs", competing_publish)
    with cli.prepare_generation(generation_options) as candidate, pytest.raises(InputError, match="競合変更"):
        candidate.publish()
    assert destination.read_bytes() == b"late competing writer"
    assert files(output) == {Path(destination.name): b"late competing writer"}
    assert not list(output.rglob(".pier-design-*"))


@pytest.mark.parametrize("stage", ["0710", "all"])
@pytest.mark.parametrize("failure", ["serialize", "write", "staged_validate", "replace", "final_validate"])
def test_failure_restores_entire_generation(
    generation_options, fake_ndu, quick_reports, monkeypatch, stage, failure,
):
    options = cli.GenerationOptions(generation_options.input_path, generation_options.output_dir,
                                    stage=stage, jrsnap=True, overwrite=True)
    with cli.prepare_generation(options) as candidate:
        destinations = tuple(candidate.artifact_hashes)
    for path in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("previous " + path.name).encode("utf-8"))
    before = files(options.output_dir)
    if failure == "serialize":
        def serialize(model):
            raise InputError("serializer failed")
        monkeypatch.setattr(sys.modules["src.jrsnap_ndu"], "serialize_ndu", serialize)
    elif failure == "write":
        actual = Path.write_bytes
        def write(path, data):
            if path.suffix == ".ndu":
                raise OSError("NDU write failed")
            return actual(path, data)
        monkeypatch.setattr(Path, "write_bytes", write)
    elif failure in ("staged_validate", "final_validate"):
        actual = cli.validate_jrsnap_artifacts
        def validate(**kwargs):
            if failure == "staged_validate" or kwargs.get("read_paths") is None:
                raise InputError("NDU validation failed")
            return actual(**kwargs)
        monkeypatch.setattr(cli, "validate_jrsnap_artifacts", validate)
    else:
        actual = os.replace
        def replace(source, destination):
            if Path(source).name == "線路方向.ndu" and Path(destination).name == "線路方向.ndu":
                raise PermissionError("NDU destination locked")
            return actual(source, destination)
        monkeypatch.setattr(os, "replace", replace)
    assert cli.main(["--input", str(options.input_path), "--output-dir", str(options.output_dir),
                     "--stage", stage, "--overwrite", "--jrsnap"]) == 2
    assert files(options.output_dir) == before
    assert not list(options.output_dir.rglob(".pier-design-*"))


def test_closed_candidate_cannot_publish(generation_options, fake_ndu, quick_reports):
    with cli.prepare_generation(generation_options) as candidate:
        pass
    with pytest.raises(InputError, match="保持期間"):
        candidate.publish()


def test_late_competing_deletion_remains_deleted_after_rollback(
    generation_options, fake_ndu, quick_reports, monkeypatch,
):
    output = generation_options.output_dir
    output.mkdir()
    destination = output / "0710_線路方向荷重.pdf"
    destination.write_bytes(b"initial baseline")
    actual_publish = cli._publish_outputs

    def competing_delete(*args, **kwargs):
        destination.unlink()
        return actual_publish(*args, **kwargs)

    monkeypatch.setattr(cli, "_publish_outputs", competing_delete)
    with cli.prepare_generation(generation_options) as candidate, pytest.raises(InputError, match="競合変更"):
        candidate.publish()
    assert not destination.exists()
    assert files(output) == {}


def test_default_0710_does_not_touch_existing_ndu(generation_options, quick_reports):
    post = generation_options.output_dir / "post"
    post.mkdir(parents=True)
    for path in jrsnap_artifacts.jrsnap_paths(post):
        path.write_bytes(b"stale but untouched")
    assert cli.main(["--stage", "0710", "--input", str(generation_options.input_path),
                     "--output-dir", str(generation_options.output_dir)]) == 0
    assert all(path.read_bytes() == b"stale but untouched" for path in jrsnap_artifacts.jrsnap_paths(post))


def test_real_engine_single_and_all_use_identical_ndu_bytes(tmp_path, quick_reports):
    from src.jrsnap_ndu import validate_ndu_bytes
    from test_jrsnap_export import example_input

    source = tmp_path / "input.json"
    raw = example_input()
    raw["jrsnap_transverse"] = dict(raw["jrsnap_longitudinal"])
    source.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    generated = []
    for stage, count in (("0710", 4), ("all", 20)):
        options = cli.GenerationOptions(source, tmp_path / stage, stage=stage, jrsnap=True)
        with cli.prepare_generation(options) as candidate:
            candidate.publish()
            assert len(candidate.artifact_hashes) == count
            data = candidate.ndu_path.read_bytes()
            checked = validate_ndu_bytes(data)
            assert checked["counts"]["nodes"] == 7
            assert checked["counts"]["elements"] == 6
            assert candidate.metadata["canonical_snapshot_sha256"] == {
                "foundation": candidate.canonical_snapshot_sha256["0500"],
                "seismic": candidate.canonical_snapshot_sha256["0710"],
            }
            generated.append(data)
    assert generated[0] == generated[1]
