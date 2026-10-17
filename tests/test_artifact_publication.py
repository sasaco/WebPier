"""Multi-directory publication must restore every original byte on failure."""

import os
import json
import stat
import shutil
from pathlib import Path

import pytest

from src import cli
from src.artifact_publication import ArtifactStaging, RecoveryError, publish_outputs


def test_cross_directory_failure_restores_same_named_files(tmp_path, monkeypatch):
    pairs = []
    originals = {}
    for name in ("output", "post"):
        parent = tmp_path / name
        parent.mkdir()
        staging = parent / ".pier-design-test"
        staging.mkdir()
        destination = parent / "model.json"
        originals[destination] = name.encode()
        destination.write_bytes(originals[destination])
        staged = staging / destination.name
        staged.write_bytes(b"new")
        pairs.append((staged, destination))
    original_replace = os.replace
    def locked_second(source, destination):
        if Path(source) == pairs[1][0]:
            raise PermissionError("second directory locked")
        return original_replace(source, destination)
    monkeypatch.setattr(os, "replace", locked_second)
    with pytest.raises(OSError):
        cli._publish_outputs(pairs, pairs[0][0].parent, True)
    assert {path: path.read_bytes() for path in originals} == originals


def test_duplicate_destinations_are_rejected_before_backup(tmp_path):
    staging = tmp_path / ".pier-design-test"
    staging.mkdir()
    first, second = staging / "one", staging / "two"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    destination = tmp_path / "result"
    destination.write_bytes(b"old")
    with pytest.raises(OSError, match="重複"):
        cli._publish_outputs([(first, destination), (second, destination)], staging, True)
    assert destination.read_bytes() == b"old"


@pytest.mark.parametrize("old_indices", [(), (0,), (0, 1)])
def test_second_directory_failure_removes_new_and_restores_old(tmp_path, monkeypatch, old_indices):
    destinations = [tmp_path / "reports" / "report.pdf", tmp_path / "post" / "native.json"]
    old = {}
    for index in old_indices:
        destination = destinations[index]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(f"old {index}".encode())
        old[destination] = destination.read_bytes()
    actual = os.replace
    def fail_second(source, destination):
        if Path(source).name == destinations[1].name:
            raise PermissionError("post locked")
        return actual(source, destination)
    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(PermissionError, match="post locked"):
        with ArtifactStaging(destinations) as staging:
            pairs = []
            for destination in destinations:
                source = staging.path_for(destination)
                source.write_bytes(b"new")
                pairs.append((source, destination))
            publish_outputs(pairs, staging.directories, True)
    assert {path: path.read_bytes() for path in destinations if path.exists()} == old
    assert not list(tmp_path.rglob(".pier-design-*"))


def test_restore_failure_preserves_backup_and_still_restores_other_files(tmp_path, monkeypatch):
    destinations = [tmp_path / name / "result.json" for name in ("reports", "post", "other")]
    for index, path in enumerate(destinations):
        path.parent.mkdir()
        path.write_bytes(str(index).encode())
    actual = os.replace
    def fail(source, destination):
        source, destination = Path(source), Path(destination)
        if source.name == "result.json" and destination == destinations[-1]:
            raise PermissionError("publication locked")
        if source.name.endswith(".backup") and destination == destinations[1]:
            raise PermissionError("restoration locked")
        return actual(source, destination)
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(RecoveryError, match="退避先") as raised:
        with ArtifactStaging(destinations) as staging:
            pairs = []
            for destination in destinations:
                source = staging.path_for(destination)
                source.write_bytes(b"new")
                pairs.append((source, destination))
            publish_outputs(pairs, staging.directories, True)
    assert destinations[0].read_bytes() == b"0"
    assert destinations[2].read_bytes() == b"2"
    backup, = list(destinations[1].parent.rglob("*.backup"))
    assert backup.read_bytes() == b"1"
    assert str(backup.parent) in str(raised.value)


def test_staging_failure_cleans_first_parent_without_changing_outputs(tmp_path, monkeypatch):
    destinations = [tmp_path / "reports" / "report.pdf", tmp_path / "post" / "native.json"]
    destinations[0].parent.mkdir()
    destinations[0].write_bytes(b"old PDF")
    actual = Path.mkdir
    def readonly(path, *args, **kwargs):
        if path == destinations[1].parent:
            raise PermissionError("post is read-only")
        return actual(path, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", readonly)
    with pytest.raises(PermissionError, match="read-only"):
        with ArtifactStaging(destinations):
            pytest.fail("staging should fail before rendering")
    assert destinations[0].read_bytes() == b"old PDF"
    assert not list(tmp_path.rglob(".pier-design-*"))


def test_readonly_old_artifact_is_rejected_before_any_replacement(tmp_path):
    destination = tmp_path / "native.json"
    destination.write_bytes(b"old native")
    destination.chmod(stat.S_IREAD)
    try:
        with pytest.raises(PermissionError):
            with ArtifactStaging([destination]) as staging:
                source = staging.path_for(destination)
                source.write_bytes(b"new native")
                publish_outputs([(source, destination)], staging.directories, True)
        assert destination.read_bytes() == b"old native"
        assert not list(tmp_path.glob(".pier-design-*"))
    finally:
        for path in tmp_path.rglob("*"):
            if path.is_file():
                path.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_cleanup_lock_keeps_successful_generation_and_reports_retained_directory(tmp_path, monkeypatch):
    destination = tmp_path / "native.json"
    destination.write_bytes(b"old native")
    def locked_cleanup(path):
        raise PermissionError("backup is being inspected")
    monkeypatch.setattr(shutil, "rmtree", locked_cleanup)
    with pytest.warns(RuntimeWarning, match="一時ファイル") as warning:
        with ArtifactStaging([destination]) as staging:
            source = staging.path_for(destination)
            source.write_bytes(b"new native")
            publish_outputs([(source, destination)], staging.directories, True)
    assert destination.read_bytes() == b"new native"
    directory, = staging.directories.values()
    assert str(directory) in str(warning[0].message)
    assert (directory / "native.json.backup").read_bytes() == b"old native"


@pytest.mark.parametrize("existing", [False, True])
def test_final_validation_runs_before_backups_are_discarded_and_rolls_back(tmp_path, existing):
    destination = tmp_path / "native.json"
    if existing:
        destination.write_bytes(b"old")
    with pytest.raises(ValueError, match="final bytes"):
        with ArtifactStaging([destination]) as staging:
            source = staging.path_for(destination)
            source.write_bytes(b"new")
            def verify():
                assert destination.read_bytes() == b"new"
                if existing:
                    assert (source.parent / "native.json.backup").read_bytes() == b"old"
                raise ValueError("final bytes invalid")
            publish_outputs([(source, destination)], staging.directories, True,
                            final_validator=verify)
    assert destination.read_bytes() == b"old" if existing else not destination.exists()
    assert not list(tmp_path.glob(".pier-design-*"))


def test_interrupted_publication_retains_journal_and_blocks_next_writer(tmp_path, monkeypatch):
    destination = tmp_path / "native.json"
    destination.write_bytes(b"old")
    actual = os.replace
    def terminate(source, target):
        if Path(source).name == "native.json" and Path(source).parent != tmp_path:
            raise KeyboardInterrupt("simulated process termination")
        return actual(source, target)
    monkeypatch.setattr(os, "replace", terminate)
    with pytest.raises(KeyboardInterrupt):
        with ArtifactStaging([destination]) as staging:
            source = staging.path_for(destination)
            source.write_bytes(b"new")
            publish_outputs([(source, destination)], staging.directories, True)
    backup, = list(tmp_path.rglob("*.backup"))
    assert backup.read_bytes() == b"old"
    with pytest.raises(RecoveryError, match="journal") as raised:
        from src.artifact_publication import validate_destinations
        validate_destinations([destination], overwrite=True)
    assert str(backup.parent) in str(raised.value)
    assert not destination.exists()


def test_successful_cleanup_failure_does_not_block_identical_rerun(tmp_path, monkeypatch):
    destination = tmp_path / "native.json"
    actual = shutil.rmtree
    def fail_cleanup(path):
        raise PermissionError("cleanup locked")
    monkeypatch.setattr(shutil, "rmtree", fail_cleanup)
    with pytest.warns(RuntimeWarning):
        with ArtifactStaging([destination]) as staging:
            source = staging.path_for(destination)
            source.write_bytes(b"new")
            publish_outputs([(source, destination)], staging.directories, True)
    monkeypatch.setattr(shutil, "rmtree", actual)
    with ArtifactStaging([destination]) as staging:
        source = staging.path_for(destination)
        source.write_bytes(b"new")
        publish_outputs([(source, destination)], staging.directories, True)
    assert destination.read_bytes() == b"new"


@pytest.mark.parametrize("payload", ["broken JSON", json.dumps({"state": {}}), json.dumps({"state": []})])
def test_corrupt_journal_is_a_recovery_error_and_preserves_outputs(tmp_path, payload):
    from src.artifact_publication import validate_destinations
    destination = tmp_path / "native.json"
    destination.write_bytes(b"current")
    journal = tmp_path / ".pier-design-incomplete" / "publication-journal.json"
    journal.parent.mkdir()
    journal.write_text(payload, encoding="utf-8")
    with pytest.raises(RecoveryError, match="journal"):
        validate_destinations([destination], overwrite=True)
    assert destination.read_bytes() == b"current"


@pytest.mark.parametrize("parent_count", [1, 2])
@pytest.mark.parametrize("block_rollback_journal", [False, True])
def test_commit_journal_failure_and_locked_restore_block_the_next_writer(
    tmp_path, monkeypatch, parent_count, block_rollback_journal,
):
    from src import artifact_publication as publication
    import json

    destinations = [tmp_path / str(index) / "native.json" for index in range(parent_count)]
    for path in destinations:
        path.parent.mkdir()
        path.write_bytes(b"old")
    actual_write, actual_replace = publication._write_journals, os.replace

    def fail_commit(directories, record):
        if block_rollback_journal and record["state"] == "rolling_back":
            raise PermissionError("rollback journal locked")
        actual_write(directories, record)
        if record["state"] == "committed":
            # A write or fsync may fail after the new JSON is already readable.
            raise OSError("commit fsync failed")

    def locked_restore(source, destination):
        if str(source).endswith(".backup") and Path(destination) == destinations[0]:
            raise PermissionError("restore locked")
        return actual_replace(source, destination)

    monkeypatch.setattr(publication, "_write_journals", fail_commit)
    monkeypatch.setattr(os, "replace", locked_restore)
    with pytest.raises(RecoveryError, match="復元"):
        with ArtifactStaging(destinations) as staging:
            pairs = []
            for destination in destinations:
                source = staging.path_for(destination)
                source.write_bytes(b"new")
                pairs.append((source, destination))
            publish_outputs(pairs, staging.directories, True)
    assert destinations[0].read_bytes() == b"new"
    assert list(destinations[0].parent.rglob("*.backup"))[0].read_bytes() == b"old"
    for destination in destinations:
        # Even a later single-stage run in just one parent must stop.
        with pytest.raises(RecoveryError, match="journal"):
            publication.validate_destinations([destination], overwrite=True)
    journals = list(tmp_path.rglob(publication.JOURNAL_FILENAME))
    assert len(journals) == parent_count
    assert {json.loads(path.read_text(encoding="utf-8"))["state"] for path in journals} == {
        "committed" if block_rollback_journal else "rolling_back"}


def test_failure_clearing_second_pending_marker_never_rolls_back_committed_files(tmp_path, monkeypatch):
    destinations = [tmp_path / str(index) / "native.json" for index in range(2)]
    for path in destinations:
        path.parent.mkdir()
        path.write_bytes(b"old")
    actual_unlink = Path.unlink
    def locked_second_marker(path, *args, **kwargs):
        if path.name == "publication-pending" and path.parent.parent == destinations[1].parent:
            raise PermissionError("pending marker locked")
        return actual_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", locked_second_marker)
    with pytest.raises(RecoveryError, match="公開は完了"):
        with ArtifactStaging(destinations) as staging:
            pairs = []
            for destination in destinations:
                source = staging.path_for(destination)
                source.write_bytes(b"new")
                pairs.append((source, destination))
            publish_outputs(pairs, staging.directories, True)
    assert [path.read_bytes() for path in destinations] == [b"new", b"new"]
    assert [staging.path_for(path).with_name("native.json.backup").read_bytes() for path in destinations] == [b"old", b"old"]
    first, second = (staging.path_for(path).parent / "publication-pending" for path in destinations)
    assert not first.exists() and second.exists()


def test_pending_marker_blocks_writer_when_interruption_prevents_first_journal(tmp_path, monkeypatch):
    from src import artifact_publication as publication
    destination = tmp_path / "native.json"
    destination.write_bytes(b"old")
    def interrupted_before_journal(*args):
        raise KeyboardInterrupt("journal not written")
    monkeypatch.setattr(publication, "_write_journals", interrupted_before_journal)
    with pytest.raises(KeyboardInterrupt):
        with ArtifactStaging([destination]) as staging:
            source = staging.path_for(destination)
            source.write_bytes(b"new")
            publish_outputs([(source, destination)], staging.directories, True)
    directory = staging.path_for(destination).parent
    assert (directory / publication.PENDING_FILENAME).is_file()
    assert not (directory / publication.JOURNAL_FILENAME).exists()
    assert destination.read_bytes() == b"old"
    with pytest.raises(RecoveryError, match="journal"):
        publication.validate_destinations([destination], overwrite=True)
