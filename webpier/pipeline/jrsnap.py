"""The JRSNAP runner: the データ確認図 of 0710 and 0720 (decision 50) and the static nonlinear analysis of 0711 and
0721 (decision 47, ADR-0007).

The NDU a generation writes is given, as it is and under its own name, to ``JRSNAP.Headless.exe``. For the analysis
(``run``) the runner writes the analysis data (.ndt) of every combination as JRSNAP's 解析用データ出力 does, has
JRSNAP's S_ANALYSIS.exe analyze them, and returns every file in its output folder under the names JRSNAP gave them.
They are published together as one folder, as they are returned: their content and bytes are JRSNAP's, so they are
neither checked further nor bound to the implementation identity. The sidecar records the runner's
``engineVersion`` and what the runner reports of JRSNAP (version, display flags, the confirmations it answered, the
messages of the analysis).

For the データ確認図 (``data-check``) the runner writes the .ndt the same way and has JRSNAP's S_DataCheck.exe print
the figures of ``DATA_CHECK_FIGURES`` for combination 1, one PDF each; their pages, in that order, go into the
report as they are. They are not published by themselves, and the NDU's sidecar records which runner drew them.

The runner is the absolute path in ``STRUCTURAL_MCP_JRSNAP_RUNNER``: the process environment first, then the
``.env`` file at the repository root (not tracked). The JRSNAP installation is the runner's own setting. Without a
runner, or when it fails, a generation that needs it stops; nothing is published without its pages or analysis.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError

from .fempython import ENV_FILE, RunnerError, read_env

RUNNER_KEY = "STRUCTURAL_MCP_JRSNAP_RUNNER"
PROTOCOL_VERSION = 1
ENGINE = "jrsnap"
# The runner gives up after this many seconds; WebPier waits a minute longer for its envelope.
ANALYSIS_TIMEOUT = 1800
TIMEOUT = ANALYSIS_TIMEOUT + 60
_KINDS = {"ndt", "analysis-result"}
_ANALYZE = "を JRSNAP で静的非線形解析できません"
# The figures of the データ確認図, in the order of the report (decision 50; Example2 10-3..10-7), and the combination
# they are drawn for: the numbers, sections and node springs do not change with the combination.
DATA_CHECK_FIGURES = ("nonlinear-numbers", "section-numbers", "element-table", "section-detail", "node-springs")
DATA_CHECK_CASE = 1
DATA_CHECK_TIMEOUT = 300
DATA_CHECK_WAIT = DATA_CHECK_TIMEOUT + 60
_DATA_CHECK = "のデータ確認図を JRSNAP で描けません"


@dataclass(frozen=True)
class NonlinearFiles:
    files: Mapping[str, bytes]  # by the name JRSNAP gave each file
    engine_version: str
    summary: Mapping[str, Any]  # what the runner reports of JRSNAP and the analysis
    messages: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class DataCheckPages:
    pdf: bytes  # the pages of every figure, in the order of DATA_CHECK_FIGURES
    engine_version: str
    summary: Mapping[str, Any]  # what the runner reports of JRSNAP, the .ndt and the figures


def runner_path(environ: Mapping[str, str] | None = None, env_file: Path | None = None) -> Path:
    """The runner executable: the environment variable, else the ``.env`` setting (both as they are now)."""
    environ = os.environ if environ is None else environ
    env_file = ENV_FILE if env_file is None else env_file
    value = environ.get(RUNNER_KEY, "")
    where = f"環境変数 {RUNNER_KEY}"
    if not value:
        value = read_env(env_file).get(RUNNER_KEY, "") if Path(env_file).is_file() else ""
        where = f"{env_file} の {RUNNER_KEY}"
    if not value:
        raise RunnerError(f"データ確認図と静的非線形解析に使う JRSNAP の runner が設定されていません。リポジトリのルートの "
                          f".env に {RUNNER_KEY}='<JRSNAP.Headless.exe の絶対パス>' を書いてください")
    path = Path(value)
    if not path.is_absolute():
        raise RunnerError(f"{where} は絶対パスにしてください: {value}")
    if not path.is_file():
        raise RunnerError(f"{where} の runner がありません: {value}")
    return path


def _fail(name: str, message: str, action: str = _ANALYZE) -> RunnerError:
    return RunnerError(f"{name} {action}: {message}")


def _envelope(name: str, stdout: bytes, action: str) -> dict[str, Any]:
    try:
        envelope = json.loads(stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(name, f"runner の応答が JSON ではありません（{exc}）", action) from exc
    if not isinstance(envelope, dict):
        raise _fail(name, "runner の応答が JSON のオブジェクトではありません", action)
    if envelope.get("protocolVersion") != PROTOCOL_VERSION or envelope.get("engine") != ENGINE:
        raise _fail(name, f"runner のやり取りの版が違います（protocolVersion {envelope.get('protocolVersion')!r}、"
                          f"engine {envelope.get('engine')!r}）", action)
    return envelope


def _plain(name: Any) -> bool:
    return isinstance(name, str) and name not in {"", ".", ".."} and not set(name) & set("/\\:")


def _call(name: str, document: bytes, runner: Path, command: str, options: Sequence[str], timeout: float,
          action: str, accepts: Callable[[list[dict[str, Any]]], bool], label: str
          ) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Run *command* of *runner* on the NDU *document*, given to it as *name*: its envelope and every file it returned,
    by name in the order listed, after the checks both commands share. *accepts* checks the listed artifacts, which
    otherwise are not *label*."""
    with tempfile.TemporaryDirectory(prefix="webpier-jrsnap-") as work:
        source, output = Path(work) / name, Path(work) / "output"
        source.write_bytes(document)
        try:
            done = subprocess.run([str(runner), command, "--input", str(source), "--output-dir", str(output),
                                   *options], capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise _fail(name, f"{timeout} 秒で終わりませんでした", action) from exc
        except OSError as exc:
            raise _fail(name, f"runner を起動できません（{exc}）", action) from exc
        envelope = _envelope(name, done.stdout, action)
        if done.returncode or envelope.get("ok") is not True or envelope.get("executionStatus") != "success":
            errors = "; ".join(f"{error.get('code')}: {error.get('message')}" for error in envelope.get("errors") or ()
                               if isinstance(error, dict)) or f"終了コード {done.returncode}"
            raise _fail(name, errors, action)
        version, artifacts = envelope.get("engineVersion"), envelope.get("artifacts")
        summary, messages = envelope.get("summary"), envelope.get("messages")
        if not isinstance(version, str) or not version:
            raise _fail(name, "runner の版（engineVersion）がありません", action)
        if not isinstance(summary, dict) or not isinstance(messages, list) or not all(
                isinstance(message, dict) for message in messages):
            raise _fail(name, "runner の応答に summary・messages がありません", action)
        if (not isinstance(artifacts, list) or not all(isinstance(item, dict) for item in artifacts)
                or not all(_plain(item.get("relativePath")) for item in artifacts) or not accepts(artifacts)
                or len({item["relativePath"].casefold() for item in artifacts}) != len(artifacts)):
            raise _fail(name, f"runner の成果物が{label}ではありません（{artifacts!r}）", action)
        present = sorted(path.name for path in output.iterdir()) if output.is_dir() else []
        if present != sorted(item["relativePath"] for item in artifacts):
            raise _fail(name, f"runner の出力先のファイルが成果物の一覧と一致しません（{present!r}）", action)
        files: dict[str, bytes] = {}
        for item in artifacts:
            content = (output / item["relativePath"]).read_bytes()
            if hashlib.sha256(content).hexdigest() != item.get("sha256") or len(content) != item.get("bytes"):
                raise _fail(name, f"{item['relativePath']} が runner の応答の SHA256・バイト数と一致しません", action)
            files[item["relativePath"]] = content
    return envelope, files


def analyze_nonlinear(name: str, document: bytes, runner: Path, *, timeout: float = TIMEOUT) -> NonlinearFiles:
    """Every file *runner* returns for the NDU *document*, given to it as *name* (decision 47)."""
    envelope, files = _call(
        name, document, runner, "run", ("--analyze", "true", "--timeout-seconds", str(ANALYSIS_TIMEOUT)), timeout,
        _ANALYZE, lambda artifacts: (all(item.get("kind") in _KINDS for item in artifacts)
                                     and any(item["kind"] == "ndt" for item in artifacts)),
        "解析用データと解析結果のファイル")
    return NonlinearFiles(files, envelope["engineVersion"], envelope["summary"], tuple(envelope["messages"]))


def draw_data_check(name: str, document: bytes, runner: Path, *, timeout: float = DATA_CHECK_WAIT
                    ) -> DataCheckPages:
    """The データ確認図 pages *runner* draws for combination 1 of the NDU *document*, given to it as *name*
    (decision 50): the pages of each figure of ``DATA_CHECK_FIGURES``, in that order."""
    names = [f"{figure}.pdf" for figure in DATA_CHECK_FIGURES]
    envelope, files = _call(
        name, document, runner, "data-check",
        ("--figures", ",".join(DATA_CHECK_FIGURES), "--case", str(DATA_CHECK_CASE),
         "--timeout-seconds", str(DATA_CHECK_TIMEOUT)), timeout, _DATA_CHECK,
        lambda artifacts: ([item.get("relativePath") for item in artifacts] == names
                           and all(item.get("kind") == "data-check" for item in artifacts)),
        "データ確認図の図ごとの PDF")
    writer = PdfWriter()
    for file in names:
        try:
            pages = PdfReader(BytesIO(files[file]), strict=True).pages
        except (PyPdfError, ValueError, OSError) as exc:
            raise _fail(name, f"{file} を読めません（{exc}）", _DATA_CHECK) from exc
        if not pages:
            raise _fail(name, f"{file} にページがありません", _DATA_CHECK)
        for page in pages:
            writer.add_page(page)
    stream = BytesIO()
    writer.write(stream)
    return DataCheckPages(stream.getvalue(), envelope["engineVersion"], envelope["summary"])
