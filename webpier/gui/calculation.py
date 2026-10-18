"""Run one generation (``python -m webpier --stage all --overwrite``, and ``--frame-analysis`` when the frame
analysis is chosen, decision 46) without blocking Tk, then check it.

Only the child process and its bounded logs run on the worker thread. The result is consumed on the main thread,
where it is checked against the files the pipeline plans for the same options: every result JSON and every
provenance sidecar must name the SHA256 of the input that was saved before the run, every sidecar must list the
files of that one generation with their SHA256, the PDFs must open, nothing may change during the check, and the
input must still be the saved one.
"""

from __future__ import annotations

import os
import queue
import stat
import subprocess
import sys
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import pymupdf

from ..core.errors import InputError
from ..core.integrity import file_sha256, load_json
from ..pipeline.cli import post_dir as default_post_dir
from ..pipeline.generate import Artifact, GenerationOptions, planned
from ..pipeline.publication import check_incomplete_publications
from ..pipeline.stages import ALL, STAGES, Registry

PROJECT_DIR = Path(__file__).resolve().parents[2]
MAX_LOG_BYTES = 48 * 1024
LOG_TRUNCATED = "［ログの前半を省略しました］\n"


class ArtifactValidationError(ValueError):
    """The published files cannot be shown as the result of this calculation."""


class InputChangedError(ArtifactValidationError):
    """The input is no longer the one the calculation started from."""


def _main_thread_only() -> None:
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("計算状態とPDFの検証はメインスレッドで処理してください")


@dataclass(frozen=True)
class CalculationJob:
    run_id: str
    input_path: Path
    output_dir: Path
    post_dir: Path
    input_sha256: str
    frame_analysis: bool = False  # add the opt-in frame analysis stages (decision 46)

    @property
    def options(self) -> GenerationOptions:
        return GenerationOptions(self.input_path, self.output_dir, self.post_dir, stage=ALL, overwrite=True,
                                 frame_analysis=self.frame_analysis)

    @property
    def command(self) -> list[str]:
        return [sys.executable, "-m", "webpier", "--input", str(self.input_path), "--output-dir",
                str(self.output_dir), "--post-dir", str(self.post_dir), "--stage", ALL, "--overwrite",
                *(["--frame-analysis"] if self.frame_analysis else [])]


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


def _snapshot(path: Path) -> tuple[int, ...]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ArtifactValidationError(f"出力が通常ファイルではありません: {path.name}")
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _json(path: Path) -> Any:
    document = load_json(path.read_bytes())
    if not isinstance(document, dict):
        raise ArtifactValidationError(f"JSONの形式が違います: {path.name}")
    return document


def _input_sha(document: dict, path: Path, expected: str) -> None:
    source = document.get("input")
    if not isinstance(source, dict) or source.get("sha256") != expected:
        raise ArtifactValidationError(f"入力SHAが一致しない成果物です: {path.name}")


def _check_pdf(path: Path) -> None:
    with pymupdf.open(path) as document:
        if not document.is_pdf or document.needs_pass or document.page_count < 1:
            raise ArtifactValidationError(f"PDFを読み込めません: {path.name}")
        for index in range(document.page_count):
            document.load_page(index)


def _check_sidecar(sidecar: Artifact, native: Artifact, generation: list[Artifact], job: CalculationJob) -> None:
    document = _json(sidecar.path)
    _input_sha(document, sidecar.path, job.input_sha256)
    if document.get("sha256") != file_sha256(native.path):
        raise ArtifactValidationError(f"付帯JSONと出力が一致しません: {native.path.name}")
    listed = document.get("artifacts")
    roles = None
    if isinstance(listed, list):
        roles = sorted(item.get("role", "") for item in listed if isinstance(item, dict))
    if roles != sorted(artifact.role for artifact in generation):
        raise ArtifactValidationError(f"付帯JSONの成果物一覧が今回の生成と一致しません: {sidecar.path.name}")
    by_role = {artifact.role: artifact for artifact in generation}
    for item in listed:
        if file_sha256(by_role[item["role"]].path) != item.get("sha256"):
            raise ArtifactValidationError(f"別の生成の成果物があります: {by_role[item['role']].path.name}")


def validate_outputs(job: CalculationJob, *, registry: Registry = STAGES,
                     snapshots: dict[Path, tuple[int, ...]] | None = None) -> tuple[Path, ...]:
    """Check the published generation on the main thread; return its PDFs in stage order."""
    _main_thread_only()
    try:
        artifacts = list(planned(job.options, registry=registry))
        paths = [artifact.path for artifact in artifacts]
        check_incomplete_publications(paths)
        before = {path: _snapshot(path) for path in paths}
        generation = [artifact for artifact in artifacts if not artifact.role.endswith(".provenance")]
        for artifact in artifacts:
            if artifact.role.endswith(".pdf"):
                _check_pdf(artifact.path)
            elif artifact.directory == "output":
                _input_sha(_json(artifact.path), artifact.path, job.input_sha256)
            elif artifact.role.endswith(".provenance"):
                native = next(item for item in artifacts if item.role == artifact.role.removesuffix(".provenance"))
                _check_sidecar(artifact, native, generation, job)
        after = {path: _snapshot(path) for path in paths}
        if before != after:
            raise ArtifactValidationError("成果物の検証中に出力ファイルが変更されました。再計算してください。")
        if file_sha256(job.input_path) != job.input_sha256:
            raise InputChangedError("入力ファイルが計算開始時から変更されています。現在の入力で再計算してください。")
    except ArtifactValidationError:
        raise
    except (OSError, InputError, KeyError, StopIteration, RuntimeError, ValueError) as exc:
        raise ArtifactValidationError(f"成果物を確認できません: {exc}") from exc
    if snapshots is not None:
        snapshots.update(after)
    return tuple(artifact.path for artifact in artifacts if artifact.role.endswith(".pdf"))


def _read_log(stream: BinaryIO) -> str:
    stream.flush()
    size = stream.seek(0, os.SEEK_END)
    stream.seek(max(0, size - MAX_LOG_BYTES))
    text = stream.read(MAX_LOG_BYTES).decode("utf-8", errors="replace")
    return (LOG_TRUNCATED if size > MAX_LOG_BYTES else "") + text


def _error_text(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return text[:MAX_LOG_BYTES] + ("［省略］" if len(text) > MAX_LOG_BYTES else "")


def run_process(job: CalculationJob, runner: Callable[..., Any]) -> _ProcessResult:
    environment = os.environ.copy()
    environment.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    returncode, stdout, stderr, error = None, "", "", ""
    # The logs go to temporary files, removed even when spawning or reading fails; nothing accumulates in pipes.
    with tempfile.TemporaryFile(mode="w+b") as out, tempfile.TemporaryFile(mode="w+b") as err:
        try:
            completed = runner(job.command, cwd=str(PROJECT_DIR), env=environment, shell=False,
                               stdin=subprocess.DEVNULL, stdout=out, stderr=err, check=False,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            returncode = completed.returncode
        except Exception as exc:  # the worker reports any failure to start the child to the main thread
            error = _error_text(exc)
        stdout, stderr = _read_log(out), _read_log(err)
    return _ProcessResult(job, returncode, stdout, stderr, error)


class CalculationController:
    """One calculation at a time; the editor polls ``poll`` with Tk's after()."""

    def __init__(self, output_dir: Path | None = None, runner: Callable[..., Any] | None = None, *,
                 post_dir: Path | None = None, registry: Registry = STAGES) -> None:
        _main_thread_only()
        self.registry = registry
        self.output_dir = (Path(output_dir) if output_dir is not None else PROJECT_DIR / "output").resolve()
        self.post_dir = default_post_dir(self.output_dir, post_dir).resolve()
        self._runner = runner if runner is not None else subprocess.run
        self._completed: queue.Queue[_ProcessResult] = queue.Queue()
        self.job: CalculationJob | None = None
        self.result: CalculationResult | None = None
        self._verified: dict[Path, tuple[int, ...]] = {}
        self.running = False
        self.state = "idle"  # idle, running, success, failed, stale

    def start(self, input_path: Path, input_sha256: str, *, frame_analysis: bool = False) -> CalculationJob:
        _main_thread_only()
        if self.running:
            raise RuntimeError("計算中です。完了までお待ちください。")
        job = CalculationJob(uuid.uuid4().hex, Path(input_path).resolve(), self.output_dir, self.post_dir,
                             input_sha256, frame_analysis)
        self.job, self.result = job, None
        self._verified.clear()
        self.running, self.state = True, "running"
        threading.Thread(target=self._work, args=(job,), name=f"webpier-calculation-{job.run_id}", daemon=True).start()
        return job

    def _work(self, job: CalculationJob) -> None:
        self._completed.put(run_process(job, self._runner))

    def poll(self) -> CalculationResult | None:
        _main_thread_only()
        try:
            outcome = self._completed.get_nowait()
        except queue.Empty:
            return None
        success, pdf_paths, state = False, (), "failed"
        try:
            if outcome.error:
                message = f"計算を実行できませんでした: {outcome.error}"
            elif outcome.returncode != 0:
                message = f"計算に失敗しました（終了コード {outcome.returncode}）。実行ログを確認してください。"
            else:
                pdf_paths = validate_outputs(outcome.job, registry=self.registry, snapshots=self._verified)
                success, state = True, "success"
                message = f"計算・PDF出力が完了しました（{len(pdf_paths)}帳票）。"
        except InputChangedError as exc:
            state, message = "stale", str(exc)
        except ArtifactValidationError as exc:
            message = f"計算結果の検証に失敗しました: {exc}"
        finally:
            self.running = False
        self.state = state
        self.result = CalculationResult(outcome.job, success, message, outcome.stdout, outcome.stderr,
                                        outcome.returncode, pdf_paths)
        return self.result

    def mark_stale(self) -> None:
        if not self.running and self.state == "success":
            self.state = "stale"

    def check_current_outputs(self) -> str | None:
        """After a success: the verified files are unchanged and readable, or the message why they are not."""
        _main_thread_only()
        if self.state != "success":
            return None
        try:
            check_incomplete_publications(tuple(self._verified))
            for path, expected in self._verified.items():
                if _snapshot(path) != expected:
                    raise ArtifactValidationError(f"計算後に出力ファイルが変更されました: {path.name}")
                with path.open("rb") as stream:
                    stream.read(1)
        except (OSError, ArtifactValidationError) as exc:
            self.mark_stale()
            return f"出力ファイルが変更・削除されたか、読み込めなくなりました。再計算してください。\n{exc}"
        return None
