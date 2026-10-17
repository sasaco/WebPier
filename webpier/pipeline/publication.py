"""Publish a related file set with backups beside each destination.

Individual replacements are atomic; the set is not an OS transaction. On an
ordinary failure every old file is restored, and failed restorations retain
their backups for manual recovery.
"""

from __future__ import annotations

import os
import json
import shutil
import stat
import tempfile
import warnings
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path


class RecoveryError(OSError):
    """Publication and recovery failed; temporary backups must be retained."""


JOURNAL_FILENAME = "publication-journal.json"
PENDING_FILENAME = "publication-pending"


def _incomplete_journal(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (not isinstance(data, dict) or not isinstance(data.get("state"), str)
                or data["state"] not in {"committed", "rolled_back"})
    except (OSError, ValueError):
        return True


def _incomplete_staging(directory: Path) -> bool:
    journal = directory / JOURNAL_FILENAME
    return ((directory / PENDING_FILENAME).exists()
            or (journal.exists() and _incomplete_journal(journal)))


def check_incomplete_publications(destinations: Sequence[Path], *,
                                  exclude: Sequence[Path] = ()) -> None:
    """Fail closed; recovery is manual so another writer is never overwritten."""
    excluded = {path.resolve() for path in exclude}
    for parent in dict.fromkeys(path.parent.resolve() for path in destinations):
        for directory in parent.glob(".webpier-*"):
            if directory.resolve() not in excluded and _incomplete_staging(directory):
                raise RecoveryError(
                    f"未完了の公開journalがあります。自動復旧は行いません。"
                    f"退避先・復旧対象を確認してください: {directory}"
                )


def _write_journals(directories: Mapping[Path, Path], record: dict) -> None:
    for directory in dict.fromkeys(directories.values()):
        with (directory / JOURNAL_FILENAME).open("w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())


def _create_pending(directories: Mapping[Path, Path], transaction_id: str) -> None:
    # This marker is immutable until all publication or restoration work has
    # finished. A failed journal rewrite cannot remove its recovery protection.
    for directory in dict.fromkeys(directories.values()):
        with (directory / PENDING_FILENAME).open("x", encoding="ascii") as stream:
            stream.write(transaction_id + "\n")
            stream.flush()
            os.fsync(stream.fileno())


def _clear_pending(directories: Mapping[Path, Path], *, completed: str) -> None:
    for directory in dict.fromkeys(directories.values()):
        try:
            (directory / PENDING_FILENAME).unlink(missing_ok=True)
        except OSError as exc:
            raise RecoveryError(
                f"成果物の{completed}は完了しましたが未完了マーカーを削除できません。"
                f"保持場所: {tuple(directories.values())}; {exc}"
            ) from exc


def _remove_staging(directory: Path) -> None:
    try:
        shutil.rmtree(directory)
    except OSError as exc:
        # Cleanup is after publication/rollback has finished. It must neither
        # report a committed generation as failed nor mask its original error.
        warnings.warn(f"一時ファイルを削除できません。保持場所: {directory}; {exc}",
                      RuntimeWarning, stacklevel=2)


def backup_path(staging: Mapping[Path, Path], destination: Path) -> Path:
    """Where publish_outputs keeps the old *destination* until the generation is committed."""
    return staging[destination.parent.resolve()] / (destination.name + ".backup")


def validate_destinations(destinations: Sequence[Path], *, overwrite: bool,
                          input_path: Path | None = None) -> None:
    check_incomplete_publications(destinations)
    seen: set[Path] = set()
    resolved_input = input_path.resolve() if input_path is not None else None
    for destination in destinations:
        resolved = destination.resolve()
        if resolved in seen:
            raise OSError(f"出力先が重複しています: {destination}")
        seen.add(resolved)
        if resolved == resolved_input:
            raise OSError("入力ファイルと出力ファイルを同じパスにはできません")
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise OSError(f"通常ファイル以外は上書きできません: {destination}")
        if destination.exists() and not overwrite:
            raise FileExistsError(f"出力が既にあります: {destination}（更新する場合は --overwrite）")
        if destination.exists() and not destination.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            # Windows permits renaming a read-only file to its backup, then
            # refuses to delete that backup. Reject before replacing anything.
            raise PermissionError(f"読取専用の出力は上書きできません: {destination}")


class ArtifactStaging:
    """Create staging on each destination filesystem and clean only our files."""

    def __init__(self, destinations: Sequence[Path]) -> None:
        self.parents = tuple(dict.fromkeys(path.parent.resolve() for path in destinations))
        self.directories: dict[Path, Path] = {}
        self.created_parents: list[Path] = []

    def __enter__(self) -> ArtifactStaging:
        try:
            for parent in self.parents:
                missing = []
                current = parent
                while not current.exists():
                    missing.append(current)
                    current = current.parent
                parent.mkdir(parents=True, exist_ok=True)
                self.created_parents.extend(reversed(missing))
                self.directories[parent] = Path(tempfile.mkdtemp(prefix=".webpier-", dir=parent)).resolve()
        except OSError:
            self._cleanup()
            raise
        return self

    def path_for(self, destination: Path) -> Path:
        return self.directories[destination.parent.resolve()] / destination.name

    def _cleanup(self) -> None:
        for parent, directory in reversed(tuple(self.directories.items())):
            # Never recursively remove a destination directory or a guessed path.
            assert directory.parent == parent and directory.name.startswith(".webpier-")
            _remove_staging(directory)
        for parent in reversed(self.created_parents):
            try:
                parent.rmdir()  # Only directories we created, and only if empty.
            except OSError:
                pass

    def __exit__(self, kind, value, traceback) -> None:
        incomplete = any(_incomplete_staging(directory) for directory in self.directories.values())
        if not incomplete and (kind is None or not issubclass(kind, RecoveryError)):
            self._cleanup()


def publish_outputs(pairs: list[tuple[Path, Path]],
                    staging: Mapping[Path, Path], overwrite: bool, *,
                    final_validator: Callable[[], None] | None = None) -> None:
    """Back up every old file, publish every new file, and restore all on failure.

    *staging* maps each destination parent to its ArtifactStaging directory.
    """
    destinations = [destination for _, destination in pairs]
    validate_destinations(destinations, overwrite=overwrite)
    sources = [source.resolve() for source, _ in pairs]
    if len(set(sources)) != len(sources) or set(sources) & {path.resolve() for path in destinations}:
        raise OSError("一時ファイルと出力先が重複しています")
    for source, _ in pairs:
        if source.is_symlink() or not source.is_file():
            raise OSError(f"一時ファイルが通常ファイルではありません: {source}")

    directories = {parent.resolve(): directory.resolve() for parent, directory in staging.items()}
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    journal: dict | None = None
    try:
        for destination in destinations:
            parent = destination.parent.resolve()
            if parent not in directories or directories[parent].parent != parent:
                raise OSError(f"退避先は出力先と同じ親に必要です: {destination}")
        journal = {
            "schema_version": 1, "transaction_id": uuid.uuid4().hex, "state": "publishing",
            "artifacts": [{"source": str(source.resolve()), "destination": str(destination.resolve()),
                           "backup": str(backup_path(directories, destination)),
                           "had_original": destination.exists()}
                          for source, destination in pairs],
        }
        _create_pending(directories, journal["transaction_id"])
        _write_journals(directories, journal)
        check_incomplete_publications(destinations, exclude=tuple(directories.values()))
        # Back up every old artifact before publishing any new artifact.
        for destination in destinations:
            if destination.exists():
                backup = backup_path(directories, destination)
                os.replace(destination, backup)
                backups[destination] = backup
        for source, destination in pairs:
            os.replace(source, destination)
            published.append(destination)
        if final_validator is not None:
            final_validator()
        journal["state"] = "committed"
        _write_journals(directories, journal)
    except Exception as exc:
        journal_errors = []
        if journal is not None:
            # A commit write/fsync can fail after "committed" is readable.
            # Mark every parent incomplete before restoring any artifact, so
            # interrupted/failed recovery cannot look like a successful run.
            journal["state"] = "rolling_back"
            for parent, directory in directories.items():
                try:
                    _write_journals({parent: directory}, journal)
                except OSError as error:
                    journal_errors.append(f"{directory}: {error}")
        restore_errors = []
        for destination in reversed(published):
            if destination not in backups:
                try:
                    destination.unlink()
                except OSError as error:
                    restore_errors.append(f"{destination}: {error}")
        # Continue restoring other files after a locked file, so one failure
        # does not needlessly strand every remaining original in its backup.
        for destination, backup in reversed(tuple(backups.items())):
            try:
                os.replace(backup, destination)
            except OSError as error:
                restore_errors.append(f"{backup} -> {destination}: {error}")
        if restore_errors:
            locations = ", ".join(str(path) for path in dict.fromkeys(directories.values()))
            raise RecoveryError(
                f"出力更新と復元に失敗しました。旧成果物の退避先を保持しました: {locations}; "
                f"更新エラー: {exc}; 復元エラー: {'; '.join(restore_errors)}"
                + (f"; journal記録エラー: {'; '.join(journal_errors)}" if journal_errors else "")
            ) from exc
        if journal is not None:
            journal["state"] = "rolled_back"
            try:
                _write_journals(directories, journal)
            except OSError as error:
                raise RecoveryError(f"成果物は復元しましたがjournalを完了できません。退避先: "
                                    f"{tuple(directories.values())}; {error}") from exc
        _clear_pending(directories, completed="復元")
        raise
    else:
        # Every new artifact and every commit record is complete. Once marker
        # removal starts, never roll back: another parent can already be open
        # to the next writer. Removal errors retain backups for manual cleanup.
        _clear_pending(directories, completed="公開")
