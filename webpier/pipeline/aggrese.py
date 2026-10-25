"""The Aggre-SE runner: the 耐震性能照査 of 0711 and 0721 (decisions 56〜58, ADR-0009).

The project XML a generation stages (export.aggrese, decision 49) and the JRSNAP folder staged beside it are given,
where they are, to ``AggreSE.Headless.exe run`` (structural-mcp ``Batch``), with the DB1 of each Case mapped as the
XML names them (``--snap-map``: the index of each ``SnapDBPath`` → its DB1, resolved from the XML's folder). The
runner reads them, writes nothing beside the DB1, and returns its result (checked, not kept), its report
(``report.pdf``), which is the stage's report as it is, and the files of ``PUBLISHED``, each published under post/
as it is by its kind: the section force pickup (``pickup.pik``, decision 57) and the summary workbook
(``summary.xlsx``, decision 58) and the step table of the direct foundation (``foundation-steps.csv``, decision 60:
every output step of each direct-foundation node, which 0800 reads for the Rvd到達ステップ); no check tables or pile
anchor report is asked for. Every Case must be aggregated.
A pile foundation (decision 94) gives the runner the limit values of its stability as SOIL-JR's .sdr (``Limits``: its bytes and
the direction, ``--sdr`` and ``--sdr-direction``, and for the Cases for the liquefaction the .sdr for it, ``--sdr-liquefied``),
which the runner reads as the foundation setting screen does; it has no
step table of the direct foundation, so the runner is not asked for one and returns four files.
The content and bytes of these files are Aggre-SE's (the report and the workbook differ between runs), so they are
checked no further than being a PDF and a workbook (a zip) and are not bound to the implementation identity; the
result JSON and the sidecars record the runner's ``engineVersion``. Aggre-SE returns no check values or judgement
(``engineeringStatus`` not_evaluated): the judgement is read in the report (ADR-0009).

The runner is the absolute path in ``STRUCTURAL_MCP_AGGRESE_RUNNER`` (the name structural-mcp uses): the process
environment first, then the ``.env`` file at the repository root (not tracked). Without a runner, or when it fails,
a generation that needs it stops; nothing is published.
"""

from __future__ import annotations

from collections.abc import Mapping
import csv
from dataclasses import dataclass
import hashlib
from io import BytesIO, StringIO
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from ..calc.footing import FoundationStep, StepsError
from ..reporting.stages.seismic_check import SEISMIC_CHECK
from .fempython import ENV_FILE, RunnerError, read_env

RUNNER_KEY = "STRUCTURAL_MCP_AGGRESE_RUNNER"
PROTOCOL_VERSION = 1
ENGINE = "aggrese"
TIMEOUT = 600  # seconds
# The report (decision 56), the pickup (decision 57), the summary workbook (decision 58) and the step table of the
# direct foundation (decision 60).
ARGUMENTS = ("--summary-xlsx", "true", "--report-pdf", "true", "--check-tables", "false", "--pik", "true",
             "--pile-anchor-bar-pdf", "false", "--foundation-steps", "true")
# The files published under post/, by the kind a stage publishes them as: (the runner's kind, its file name).
PUBLISHED = {"pik": ("pickup-pik", "pickup.pik"), "xlsx": ("summary-xlsx", "summary.xlsx"),
             "steps": ("foundation-steps-csv", "foundation-steps.csv")}
# The columns of the step table (Batch/Aggre-SE/Headless/README.md): V, H, M as Aggre-SE sums the support springs
# (H signed, M absolute), qvd〜plasticity as JRSNAP wrote them, step the number of JRSNAP's output list (from 1).
FOUNDATION_STEPS_COLUMNS = ("case_index", "case_name", "node", "step", "V", "H", "M", "qvd", "qd", "Rvd", "Mmd",
                            "plasticity")
PILE_PUBLISHED = {kind: item for kind, item in PUBLISHED.items() if kind != "steps"}  # no step table of a pile foundation
_FILES = {("result-json", "result.json"), ("report-pdf", "report.pdf"), *PUBLISHED.values()}
_PILE_FILES = {("result-json", "result.json"), ("report-pdf", "report.pdf"), *PILE_PUBLISHED.values()}
SDR_NAME = "foundation.sdr"  # the name the runner is given the .sdr as: the file's own name is not a fact of the check
LIQUEFIED_SDR_NAME = "foundation(液状化時用).sdr"  # and the one for the liquefaction (Aggre-SE reads "液状化" in the name)
AXIAL, TRANSVERSE = "axial", "transverse"  # --sdr-direction: 橋軸方向 (線路方向), 直角方向 (線路直角方向)
# The pickups of the PIK, by number: Batch's default (Option_PickUpFileCase = 0, reports/ExcelReportPickUpFile.vb),
# each the envelope of every Case up to its response step (decision 57).
PICKUPS = {1: "L1地震動", 2: "復旧性L2地震動", 3: "安全性L2地震動"}
_CHECK = "で耐震性能照査ができません"


class _Failure(Exception):
    pass


@dataclass(frozen=True)
class Limits:
    """The limit values of the stability of a pile foundation: SOIL-JR's .sdr (0500) and the direction the project checks; and,
    for a project with a Case for the liquefaction (decision 95), the .sdr for the liquefaction."""

    sdr: bytes
    direction: str  # AXIAL or TRANSVERSE
    liquefied: bytes | None = None


@dataclass(frozen=True)
class SeismicCheckPages:
    pdf: bytes  # report.pdf as returned
    files: Mapping[str, bytes]  # each file of PUBLISHED as returned, by its kind
    cases: tuple[Mapping[str, Any], ...]  # the runner's summary.cases, in order
    engine_version: str

    @property
    def pages(self) -> dict[str, bytes]:
        """The report by the name the stage's report takes it (reporting.stages.seismic_check)."""
        return {SEISMIC_CHECK: self.pdf}


def runner_path(environ: Mapping[str, str] | None = None, env_file: Path | None = None, *, dotenv: bool = True
                ) -> Path:
    """The runner executable: the environment variable, else (unless *dotenv* is false: the headless runner,
    decision 61) the ``.env`` setting; both as they are now."""
    environ = os.environ if environ is None else environ
    env_file = ENV_FILE if env_file is None else env_file
    value = environ.get(RUNNER_KEY, "")
    where = f"環境変数 {RUNNER_KEY}"
    if not value and dotenv:
        value = read_env(env_file).get(RUNNER_KEY, "") if Path(env_file).is_file() else ""
        where = f"{env_file} の {RUNNER_KEY}"
    if not value:
        raise RunnerError(f"耐震性能照査に使う Aggre-SE の runner が設定されていません。" + (
            f"リポジトリのルートの .env に {RUNNER_KEY}='<AggreSE.Headless.exe の絶対パス>' を書いてください" if dotenv
            else f"環境変数 {RUNNER_KEY} に AggreSE.Headless.exe の絶対パスを設定してください"))
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


def _run(project: Path, runner: Path, timeout: float, limits: Limits | None) -> SeismicCheckPages:
    mapped = snap_map(project)
    published, expected = (PUBLISHED, _FILES) if limits is None else (PILE_PUBLISHED, _PILE_FILES)
    arguments = ARGUMENTS if limits is None else ARGUMENTS[:-2]  # a pile foundation has no step table
    with tempfile.TemporaryDirectory(prefix="webpier-aggrese-") as work:
        snaps, output = Path(work) / "snap-map.json", Path(work) / "output"
        snaps.write_text(json.dumps(mapped, ensure_ascii=False), encoding="utf-8")
        sdr = []
        if limits is not None:
            (Path(work) / SDR_NAME).write_bytes(limits.sdr)
            sdr = ["--sdr", str(Path(work) / SDR_NAME), "--sdr-direction", limits.direction]
            if limits.liquefied is not None:
                (Path(work) / LIQUEFIED_SDR_NAME).write_bytes(limits.liquefied)
                sdr += ["--sdr-liquefied", str(Path(work) / LIQUEFIED_SDR_NAME)]
        try:
            done = subprocess.run([str(runner), "run", "--input", str(project), "--output-dir", str(output),
                                   "--snap-map", str(snaps), *arguments, *sdr],
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
        if (not isinstance(artifacts, list) or len(artifacts) != len(expected)
                or not all(isinstance(item, dict) for item in artifacts)
                or {(item.get("kind"), item.get("relativePath")) for item in artifacts} != expected):
            raise _Failure("runner の成果物が結果・計算書・ピックアップ・総括表" + (
                "・直接基礎のステップ表の5つ" if limits is None else "の4つ") + f"ではありません（{artifacts!r}）")
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
    if not zipfile.is_zipfile(BytesIO(files["summary.xlsx"])):
        raise _Failure("総括表が xlsx（zip）ではありません")
    if limits is None:
        try:
            steps = files["foundation-steps.csv"].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _Failure(f"直接基礎のステップ表を UTF-8 で読めません（{exc}）") from exc
        if steps.split("\r\n", 1)[0] != ",".join(FOUNDATION_STEPS_COLUMNS):
            raise _Failure("直接基礎のステップ表の列が違います")
    return SeismicCheckPages(pdf, {kind: files[name] for kind, (_, name) in published.items()}, cases, version)


def check_seismic(project: Path, runner: Path, *, timeout: float = TIMEOUT, limits: Limits | None = None
                  ) -> SeismicCheckPages:
    """Aggre-SE's report and published files for the project XML at *project* and the DB1 it names
    (decisions 56〜58, 60); of a pile foundation, with the *limits* of its stability (decision 94)."""
    try:
        return _run(Path(project), runner, timeout, limits)
    except _Failure as exc:
        raise RunnerError(f"{Path(project).name} {_CHECK}: {exc}") from exc


def foundation_steps(content: bytes) -> tuple[FoundationStep, ...]:
    """The rows of the step table of the direct foundation as the runner returned it (decision 60): UTF-8 (a BOM and
    LF endings tolerated), the columns of FOUNDATION_STEPS_COLUMNS; ``StepsError`` when it cannot be read."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StepsError(f"直接基礎のステップ表を読めません（{exc}）") from exc
    rows = list(csv.reader(StringIO(text)))
    if not rows or tuple(rows[0]) != FOUNDATION_STEPS_COLUMNS:
        raise StepsError("直接基礎のステップ表の列が違います")
    if len(rows) < 2:
        raise StepsError("直接基礎のステップ表に行がありません")
    found = []
    for number, row in enumerate(rows[1:], 2):
        try:
            if len(row) != len(FOUNDATION_STEPS_COLUMNS):
                raise ValueError(f"{len(row)} 列")
            case_index, name, node, step = int(row[0]), row[1], int(row[2]), int(row[3])
            values = tuple(float(value) for value in row[4:])
        except ValueError as exc:
            raise StepsError(f"直接基礎のステップ表を読めません（{number} 行目: {exc}）") from exc
        if not all(map(math.isfinite, values)):
            raise StepsError(f"直接基礎のステップ表の {number} 行目に有限でない値があります")
        found.append(FoundationStep(case_index, name, node, step, *values))
    return tuple(found)
