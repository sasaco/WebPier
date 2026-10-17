"""Run the existing CLI without blocking Tk, then verify its published results.

Only subprocess execution and bounded log collection run on the worker.  The
controller is polled on the main thread, where PDF checks are serialized with
the preview's PyMuPDF operations.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import stat
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable

import pymupdf

from .artifact_publication import check_incomplete_publications
from .frameweb_artifacts import ALL_STAGES, REPORT_STEMS, publication_paths, resolve_post_dir, validate_frameweb_artifacts
from .jrsnap_artifacts import JRSNAP_STAGES, jrsnap_paths, validate_jrsnap_artifacts

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_STEMS = tuple(REPORT_STEMS[stage] for stage in ALL_STAGES)
MAX_LOG_BYTES = 48 * 1024
LOG_TRUNCATED = "［ログの前半を省略しました］\n"


def default_output_dir() -> Path:
    """The production destination never follows cwd or the selected input."""
    return PROJECT_DIR / "output"


def input_sha256(path: Path) -> str:
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


@dataclass(frozen=True)
class CalculationJob:
    run_id: str
    input_path: Path
    output_dir: Path
    input_sha256: str
    post_dir: Path | None = None
    jrsnap: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "post_dir", resolve_post_dir(self.output_dir, self.post_dir))


@dataclass(frozen=True)
class CalculationResult:
    job: CalculationJob
    success: bool
    message: str
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    pdf_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class _ProcessResult:
    job: CalculationJob
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""


class ArtifactValidationError(ValueError):
    """The CLI's output set cannot be shown as a verified calculation."""


class InputChangedError(ArtifactValidationError):
    """The input no longer matches the calculation's starting snapshot."""


def _main_thread_only() -> None:
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("計算状態とPDFの検証はメインスレッドで処理してください")


def _regular_snapshot(path: Path) -> tuple[int, ...]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ArtifactValidationError(f"出力が通常ファイルではありません: {path.name}")
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _validate_provenance(path: Path, expected_sha256: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    provenance = data.get("provenance") if isinstance(data, dict) else None
    if not isinstance(provenance, dict) or provenance.get("input_sha256") != expected_sha256:
        raise ArtifactValidationError(f"入力SHAが一致しない計算結果です: {path.name}")


def _validate_pdf(path: Path) -> None:
    with pymupdf.open(path) as document:
        if not document.is_pdf or document.needs_pass or document.page_count < 1:
            raise ArtifactValidationError(f"PDFを読み込めません: {path.name}")
        for index in range(document.page_count):
            document.load_page(index)


def validate_outputs(job: CalculationJob, *,
                     snapshots: dict[Path, tuple[int, ...]] | None = None) -> tuple[Path, ...]:
    """Verify all selected artifacts and their provenance on the main thread.

    Both FrameWeb sidecars bind all selected artifacts to one publication
    generation. The snapshots detect observable changes during validation;
    they are not a shared lock. Identical reruns need no timestamp or content
    change to be valid.
    """
    _main_thread_only()
    pdf_paths = tuple(job.output_dir / f"{stem}.pdf" for stem in OUTPUT_STEMS)
    report_paths = tuple(path for pdf in pdf_paths for path in (pdf, pdf.with_suffix(".json")))
    declared, sidecars = publication_paths(job.output_dir, job.post_dir, ALL_STAGES)
    paths = (*declared.values(), *sidecars.values())
    if job.jrsnap:
        paths = (*paths, *(path for stage in JRSNAP_STAGES for path in jrsnap_paths(job.post_dir, stage=stage)))
    try:
        check_incomplete_publications(paths)
        before = {path: _regular_snapshot(path) for path in paths}
        for path in report_paths:
            if path.suffix == ".json":
                _validate_provenance(path, job.input_sha256)
            else:
                _validate_pdf(path)
        if before != {path: _regular_snapshot(path) for path in paths}:
            raise ArtifactValidationError("成果物の検証中に出力ファイルが変更されました。再計算してください。")
        validate_frameweb_artifacts(
            post_dir=job.post_dir, output_dir=job.output_dir,
            expected_input_sha256=job.input_sha256, expected_stages=ALL_STAGES,
        )
        if job.jrsnap:
            for stage in JRSNAP_STAGES:
                validate_jrsnap_artifacts(
                    post_dir=job.post_dir, output_dir=job.output_dir,
                    expected_input_sha256=job.input_sha256, expected_stages=ALL_STAGES, stage=stage,
                )
        after = {path: _regular_snapshot(path) for path in paths}
        if before != after:
            raise ArtifactValidationError("成果物の検証中に出力ファイルが変更されました。再計算してください。")
        if input_sha256(job.input_path) != job.input_sha256:
            raise InputChangedError("入力ファイルが計算開始時から変更されています。現在入力で再計算してください。")
        if snapshots is not None:
            snapshots.update(after)
    except ArtifactValidationError:
        raise
    except Exception as exc:
        raise ArtifactValidationError(f"成果物を確認できません: {exc}") from exc
    return pdf_paths


def _read_log(stream: BinaryIO) -> str:
    stream.flush()
    size = stream.seek(0, os.SEEK_END)
    stream.seek(max(0, size - MAX_LOG_BYTES))
    text = stream.read(MAX_LOG_BYTES).decode("utf-8", errors="replace")
    return (LOG_TRUNCATED if size > MAX_LOG_BYTES else "") + text


def _error_text(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return text[:MAX_LOG_BYTES] + ("［省略］" if len(text) > MAX_LOG_BYTES else "")


def _run_process(job: CalculationJob, runner: Callable) -> _ProcessResult:
    command = [sys.executable, str(PROJECT_DIR / "run_design.py"),
               "--input", str(job.input_path), "--output-dir", str(job.output_dir),
               "--post-dir", str(job.post_dir),
               "--stage", "all", "--overwrite"]
    if job.jrsnap:
        command.append("--jrsnap")
    environment = os.environ.copy()
    environment.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    returncode = None
    stdout = stderr = error = ""
    try:
        # TemporaryFile closes and deletes both logs even when spawn, reading,
        # or collection fails.  Child output never accumulates in RAM or pipes.
        with tempfile.TemporaryFile(mode="w+b") as out, tempfile.TemporaryFile(mode="w+b") as err:
            try:
                completed = runner(
                    command, cwd=str(PROJECT_DIR), env=environment, shell=False,
                    stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                    encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    check=False,
                )
                returncode = completed.returncode
            except Exception as exc:
                error = _error_text(exc)
            finally:
                stdout = _read_log(out)
                stderr = _read_log(err)
    except Exception as exc:
        error = _error_text(exc)
    return _ProcessResult(job, returncode, stdout, stderr, error)


class CalculationController:
    """One calculation at a time, with completion consumed by Tk's after()."""

    def __init__(self, output_dir: Path | None = None, runner: Callable | None = None,
                 *, post_dir: Path | None = None) -> None:
        _main_thread_only()
        self.output_dir = (Path(output_dir) if output_dir is not None else default_output_dir()).resolve()
        self.post_dir = resolve_post_dir(self.output_dir, post_dir)
        self._runner = runner if runner is not None else subprocess.run
        self._completed: queue.Queue[_ProcessResult] = queue.Queue()
        self._thread: threading.Thread | None = None
        self.job: CalculationJob | None = None
        self.result: CalculationResult | None = None
        self._verified_outputs: dict[Path, tuple[int, ...]] = {}
        self.running = False
        self.state = "idle"

    @property
    def busy(self) -> bool:
        return self.running

    def start(self, input_path: Path, expected_sha256: str, *, jrsnap: bool = False) -> CalculationJob:
        _main_thread_only()
        if self.running:
            raise RuntimeError("計算中です。完了までお待ちください。")
        job = CalculationJob(uuid.uuid4().hex, Path(input_path).resolve(),
                             self.output_dir, expected_sha256, self.post_dir, jrsnap)
        self.job = job
        self.result = None
        self._verified_outputs.clear()
        self.running = True
        self.state = "running"
        try:
            self._thread = threading.Thread(target=self._work, args=(job,),
                                            name=f"p7-calculation-{job.run_id}", daemon=True)
            self._thread.start()
        except Exception as exc:
            self._completed.put(_ProcessResult(job, error=_error_text(exc)))
        return job

    def _work(self, job: CalculationJob) -> None:
        try:
            outcome = _run_process(job, self._runner)
        except Exception as exc:
            outcome = _ProcessResult(job, error=_error_text(exc))
        self._completed.put(outcome)

    def poll(self) -> CalculationResult | None:
        _main_thread_only()
        try:
            outcome = self._completed.get_nowait()
        except queue.Empty:
            return None
        success = False
        pdf_paths: tuple[Path, ...] = ()
        state = "failed"
        try:
            if outcome.error:
                message = f"計算を実行できませんでした: {outcome.error}"
            elif outcome.returncode != 0:
                message = f"計算に失敗しました（終了コード {outcome.returncode}）。実行ログを確認してください。"
            else:
                pdf_paths = validate_outputs(outcome.job, snapshots=self._verified_outputs)
                success = True
                state = "success"
                message = f"計算・PDF出力が完了しました（{len(OUTPUT_STEMS)}帳票）。"
                if outcome.job.jrsnap:
                    message += "両方向のJRSNAP入力・付帯JSONも出力しました。"
        except InputChangedError as exc:
            state = "stale"
            message = str(exc)
        except Exception as exc:
            message = f"計算結果の検証に失敗しました: {_error_text(exc)}"
        finally:
            # Validation, including the last input SHA check, finishes before
            # the application is allowed to restore editing or close.
            self.running = False
        self.state = state
        self.result = CalculationResult(outcome.job, success, message,
                                        outcome.stdout, outcome.stderr,
                                        outcome.returncode, pdf_paths)
        return self.result

    def mark_stale(self) -> None:
        _main_thread_only()
        if not self.running and self.state == "success":
            self.state = "stale"

    def check_current_outputs(self) -> str | None:
        """Invalidate a completed set if a later display observes changed output.

        This is a lightweight identity/readability check, not PDF rendering or
        provenance revalidation. Additional PDFs are outside the verified set.
        """
        _main_thread_only()
        if self.state != "success" or self.running:
            return None
        try:
            if not self._verified_outputs:
                raise ArtifactValidationError("検証済み出力の確認情報がありません。")
            check_incomplete_publications(tuple(self._verified_outputs))
            for path, expected in self._verified_outputs.items():
                if _regular_snapshot(path) != expected:
                    raise ArtifactValidationError(f"計算後に出力ファイルが変更されました: {path.name}")
                with path.open("rb") as stream:
                    stream.read(1)
                if _regular_snapshot(path) != expected:
                    raise ArtifactValidationError(f"出力確認中にファイルが変更されました: {path.name}")
        except (OSError, ArtifactValidationError) as exc:
            self.mark_stale()
            return f"出力ファイルが変更・削除されたか、読み込めなくなりました。再計算してください。\n{exc}"
        return None
