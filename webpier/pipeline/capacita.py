"""The Capacita runner: the 柱の断面照査 of 0611 (decision 48, ADR-0008).

The WDJ a generation builds (export.capacita, without pickup data) and the PIK of the same generation's frame analysis
are given, as they are, to ``WebDanforCS.Headless.exe run-rc --pickup``. The runner imports the PIK with the GUI's
断面力データ取込, calculates, and returns the calculation result (checked, not kept), the report and the completed WDJ
(``model.wdj``). The report's sections and their page ranges (``summary.reportSections``, Capacita's contract) must be
exactly the sections asked for, in order, and cover the PDF; the report of 0611 inserts each range after its heading.
Their content and bytes are Capacita's, so they are neither checked further nor bound to the implementation identity;
the result JSON and the sidecar record the runner's ``engineVersion``. Capacita returns no check values or judgement
(``engineeringStatus`` not_evaluated): the judgement is read on the inserted pages (ADR-0008).

The runner is the absolute path in ``STRUCTURAL_MCP_WEBDAN_RUNNER`` (the legacy name structural-mcp uses): the process
environment first, then the ``.env`` file at the repository root (not tracked). Without a runner, or when it fails,
a generation that needs it stops; nothing is published.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .fempython import ENV_FILE, RunnerError, read_env

RUNNER_KEY = "STRUCTURAL_MCP_WEBDAN_RUNNER"
PROTOCOL_VERSION = 1
ENGINE = "webdan2"
TIMEOUT = 600  # seconds
_FILES = {("result", "result.json"), ("report", "report.pdf"), ("wdj", "model.wdj")}
_CHECK = "で柱の断面照査ができません"


class _Failure(Exception):
    pass


@dataclass(frozen=True)
class ReportSection:
    id: str  # Capacita's section id, e.g. bending_safety_destruction
    first: int  # first page, 1-based
    last: int  # last page, inclusive


@dataclass(frozen=True)
class ColumnCheckPages:
    pdf: bytes  # report.pdf as returned
    sections: tuple[ReportSection, ...]  # in page order, covering the PDF
    wdj: bytes  # the completed WDJ (model.wdj) as returned
    engine_version: str

    def section(self, section_id: str) -> tuple[int, int]:
        """(first, last) page of a section, 1-based and inclusive."""
        found = next(section for section in self.sections if section.id == section_id)
        return found.first, found.last


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
        raise RunnerError(f"柱の断面照査に使う Capacita の runner が設定されていません。リポジトリのルートの .env に "
                          f"{RUNNER_KEY}='<WebDanforCS.Headless.exe の絶対パス>' を書いてください")
    path = Path(value)
    if not path.is_absolute():
        raise RunnerError(f"{where} は絶対パスにしてください: {value}")
    if not path.is_file():
        raise RunnerError(f"{where} の runner がありません: {value}")
    return path


def _envelope(stdout: bytes) -> dict[str, Any]:
    try:
        envelope = json.loads(stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _Failure(f"runner の応答が JSON ではありません（{exc}）") from exc
    if not isinstance(envelope, dict):
        raise _Failure("runner の応答が JSON のオブジェクトではありません")
    if envelope.get("protocolVersion") != PROTOCOL_VERSION or envelope.get("engine") != ENGINE:
        raise _Failure(f"runner のやり取りの版が違います（protocolVersion {envelope.get('protocolVersion')!r}、"
                       f"engine {envelope.get('engine')!r}）")
    return envelope


def _sections(summary: Any, expected: Sequence[str], pages: int) -> tuple[ReportSection, ...]:
    listed = summary.get("reportSections") if isinstance(summary, dict) else None
    if not isinstance(listed, list) or not all(isinstance(item, dict) for item in listed):
        raise _Failure("計算書の節（reportSections）がありません")
    sections = tuple(ReportSection(item.get("id"), item.get("firstPage"), item.get("lastPage")) for item in listed)
    if [section.id for section in sections] != list(expected):
        raise _Failure(f"計算書の節が違います（{[section.id for section in sections]!r}、求めたのは {list(expected)!r}）")
    following = 1
    for section in sections:
        if (type(section.first) is not int or type(section.last) is not int or section.first != following
                or section.last < section.first):
            raise _Failure(f"計算書の節のページが PDF の {pages} ページを順に分けていません（{listed!r}）")
        following = section.last + 1
    if following - 1 != pages:
        raise _Failure(f"計算書の節のページが PDF の {pages} ページを順に分けていません（{listed!r}）")
    return sections


def _run(wdj: bytes, pik_name: str, pik: bytes, runner: Path, expected: Sequence[str],
         timeout: float) -> ColumnCheckPages:
    with tempfile.TemporaryDirectory(prefix="webpier-capacita-") as work:
        source, pickup, output = Path(work) / "model.wdj", Path(work) / pik_name, Path(work) / "output"
        source.write_bytes(wdj)
        pickup.write_bytes(pik)
        try:
            done = subprocess.run([str(runner), "run-rc", "--input", str(source), "--output-dir", str(output),
                                   "--output-format", "pdf", "--pickup", str(pickup)],
                                  capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise _Failure(f"{timeout} 秒で終わりませんでした") from exc
        except OSError as exc:
            raise _Failure(f"runner を起動できません（{exc}）") from exc
        envelope = _envelope(done.stdout)
        if done.returncode or envelope.get("ok") is not True or envelope.get("executionStatus") != "success":
            errors = "; ".join(f"{error.get('code')}: {error.get('message')}" for error in envelope.get("errors") or ()
                               if isinstance(error, dict)) or f"終了コード {done.returncode}"
            raise _Failure(errors)
        version, artifacts = envelope.get("engineVersion"), envelope.get("artifacts")
        if not isinstance(version, str) or not version:
            raise _Failure("runner の版（engineVersion）がありません")
        if (not isinstance(artifacts, list) or len(artifacts) != len(_FILES)
                or not all(isinstance(item, dict) for item in artifacts)
                or {(item.get("kind"), item.get("relativePath")) for item in artifacts} != _FILES):
            raise _Failure(f"runner の成果物が計算結果・計算書・WDJ の3つではありません（{artifacts!r}）")
        files: dict[str, bytes] = {}
        for item in artifacts:
            path = output / item["relativePath"]
            if not path.is_file():
                raise _Failure(f"runner の成果物 {item['relativePath']} がありません")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != item.get("sha256") or len(content) != item.get("bytes"):
                raise _Failure(f"{item['relativePath']} が runner の応答の SHA256・バイト数と一致しません")
            files[item["relativePath"]] = content
        present = sorted(path.name for path in output.iterdir())
        if present != sorted(files):
            raise _Failure(f"runner の出力先のファイルが成果物の一覧と一致しません（{present!r}）")
    pdf = files["report.pdf"]
    try:
        pages = len(PdfReader(BytesIO(pdf), strict=True).pages)
    except (PyPdfError, ValueError, OSError) as exc:
        raise _Failure(f"計算書の PDF を読めません（{exc}）") from exc
    return ColumnCheckPages(pdf, _sections(envelope.get("summary"), expected, pages), files["model.wdj"], version)


def check_column(wdj: bytes, pik_name: str, pik: bytes, runner: Path, sections: Sequence[str], *,
                 timeout: float = TIMEOUT) -> ColumnCheckPages:
    """Capacita's report and completed WDJ for the WDJ *wdj* and the PIK *pik* (given to it as *pik_name*), whose
    report must have exactly *sections* (decision 48)."""
    try:
        return _run(wdj, pik_name, pik, runner, sections, timeout)
    except _Failure as exc:
        raise RunnerError(f"{pik_name} {_CHECK}: {exc}") from exc
