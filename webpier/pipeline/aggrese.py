"""The Aggre-SE runner: the 耐震性能照査 of 0711 and 0721 (decision 56, ADR-0009).

The project XML a generation stages (export.aggrese, decision 49) and the JRSNAP folder staged beside it are given,
where they are, to ``AggreSE.Headless.exe run`` (structural-mcp ``Batch``), with the DB1 of each Case mapped as the
XML names them (``--snap-map``: the index of each ``SnapDBPath`` → its DB1, resolved from the XML's folder). The
runner reads them, writes nothing beside the DB1, and returns its result (checked, not kept) and its report
(``report.pdf``), which is the stage's report as it is; no summary workbook, check tables, PIK or pile anchor report
is asked for. Every Case must be aggregated. The report's content and bytes are Aggre-SE's, so it is neither checked
further than being a PDF nor bound to the implementation identity; the result JSON and the project's sidecar record
the runner's ``engineVersion``. Aggre-SE returns no check values or judgement (``engineeringStatus``
not_evaluated): the judgement is read in the report (ADR-0009).

The runner is the absolute path in ``STRUCTURAL_MCP_AGGRESE_RUNNER`` (the name structural-mcp uses): the process
environment first, then the ``.env`` file at the repository root (not tracked). Without a runner, or when it fails,
a generation that needs it stops; nothing is published.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import xml.etree.ElementTree as ET

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from ..reporting.stages.seismic_check import SEISMIC_CHECK
from .fempython import ENV_FILE, RunnerError, read_env

RUNNER_KEY = "STRUCTURAL_MCP_AGGRESE_RUNNER"
PROTOCOL_VERSION = 1
ENGINE = "aggrese"
TIMEOUT = 600  # seconds
# The report only (decision 56): the summary is in it, and nothing else is published.
ARGUMENTS = ("--summary-xlsx", "false", "--report-pdf", "true", "--check-tables", "false", "--pik", "false",
             "--pile-anchor-bar-pdf", "false")
_FILES = {("result-json", "result.json"), ("report-pdf", "report.pdf")}
_CHECK = "で耐震性能照査ができません"


class _Failure(Exception):
    pass


@dataclass(frozen=True)
class SeismicCheckPages:
    pdf: bytes  # report.pdf as returned
    cases: tuple[Mapping[str, Any], ...]  # the runner's summary.cases, in order
    engine_version: str

    @property
    def pages(self) -> dict[str, bytes]:
        """The report by the name the stage's report takes it (reporting.stages.seismic_check)."""
        return {SEISMIC_CHECK: self.pdf}


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
        raise RunnerError(f"耐震性能照査に使う Aggre-SE の runner が設定されていません。リポジトリのルートの .env に "
                          f"{RUNNER_KEY}='<AggreSE.Headless.exe の絶対パス>' を書いてください")
    path = Path(value)
    if not path.is_absolute():
        raise RunnerError(f"{where} は絶対パスにしてください: {value}")
    if not path.is_file():
        raise RunnerError(f"{where} の runner がありません: {value}")
    return path


def snap_map(project: Path) -> dict[str, str]:
    """{Case index: absolute DB1} as the project XML names them, relative to its folder.

    The XML declares utf-16 but is Shift-JIS, as Aggre-SE writes and reads it (export.aggrese).
    """
    try:
        root = ET.fromstring(Path(project).read_bytes().decode("cp932").replace('encoding="utf-16"', "", 1))
    except (UnicodeDecodeError, ET.ParseError) as exc:
        raise _Failure(f"プロジェクトを読めません（{exc}）") from exc
    listed = root.find("SNAP/SnapDBPath")
    paths = [] if listed is None else [item.text for item in listed]
    found = {str(index): str((Path(project).parent / path).resolve()) for index, path in enumerate(paths) if path}
    if not found:
        raise _Failure("プロジェクトに解析ケースの DB1（SNAP/SnapDBPath）がありません")
    return found


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


def _cases(summary: Any, mapped: Mapping[str, str]) -> tuple[Mapping[str, Any], ...]:
    cases = summary.get("cases") if isinstance(summary, dict) else None
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise _Failure("runner の応答に解析ケース（summary.cases）がありません")
    if len(cases) != len(mapped) or not all(case.get("selected") is True and case.get("aggregated") is True
                                            for case in cases):
        raise _Failure(f"全 {len(mapped)} ケースが集計されていません（{cases!r}）")
    return tuple(cases)


def _run(project: Path, runner: Path, timeout: float) -> SeismicCheckPages:
    mapped = snap_map(project)
    with tempfile.TemporaryDirectory(prefix="webpier-aggrese-") as work:
        snaps, output = Path(work) / "snap-map.json", Path(work) / "output"
        snaps.write_text(json.dumps(mapped, ensure_ascii=False), encoding="utf-8")
        try:
            done = subprocess.run([str(runner), "run", "--input", str(project), "--output-dir", str(output),
                                   "--snap-map", str(snaps), *ARGUMENTS],
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
            raise _Failure(f"runner の成果物が結果と計算書の2つではありません（{artifacts!r}）")
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
    cases = _cases(envelope.get("summary"), mapped)
    pdf = files["report.pdf"]
    try:
        pages = len(PdfReader(BytesIO(pdf), strict=True).pages)
    except (PyPdfError, ValueError, OSError) as exc:
        raise _Failure(f"計算書の PDF を読めません（{exc}）") from exc
    if not pages:
        raise _Failure("計算書の PDF にページがありません")
    return SeismicCheckPages(pdf, cases, version)


def check_seismic(project: Path, runner: Path, *, timeout: float = TIMEOUT) -> SeismicCheckPages:
    """Aggre-SE's report for the project XML at *project* and the DB1 it names (decision 56)."""
    try:
        return _run(Path(project), runner, timeout)
    except _Failure as exc:
        raise RunnerError(f"{Path(project).name} {_CHECK}: {exc}") from exc
