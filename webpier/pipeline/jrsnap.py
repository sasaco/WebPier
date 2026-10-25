"""The JRSNAP runner: the データ確認図 and the 荷重図 of 0710 and 0720 (decisions 50, 51) and the static nonlinear
analysis of 0711 and 0721 (decision 47, ADR-0007).

The NDU a generation writes is given, as it is and under its own name, to ``JRSNAP.Headless.exe``. For the analysis
(``run``) the runner writes the analysis data (.ndt) of every combination as JRSNAP's 解析用データ出力 does, has
JRSNAP's S_ANALYSIS.exe analyze them, and returns every file in its output folder under the names JRSNAP gave them.
They are published together as one folder, as they are returned: their content and bytes are JRSNAP's, so they are
neither checked further nor bound to the implementation identity. The sidecar records the runner's
``engineVersion`` and what the runner reports of JRSNAP (version, display flags, the confirmations it answered, the
messages of the analysis).

For the figures (``figures``) the runner writes the .ndt the same way, in one call: JRSNAP's S_DataCheck.exe prints
the データ確認図 figures of ``DATA_CHECK_FIGURES`` from the .ndt of combination 1, one PDF each, and its
S_LoadPicture.exe draws the 荷重図 of each combination the stage's ``load_cases`` name from that combination's .ndt,
one PDF per combination with one page per basic case. The pages of the データ確認図 go into the report in that order;
the load diagram pages are taken one each, in case order, each from the combination named for its case (JRSNAP writes
the loads of a case a combination does not use as 0; decision 51). The pages go in as they are and are not published
by themselves; the NDU's sidecar records which runner drew them, the combination of each case and what the runner
reports (decisions 50, 51).

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

from ..reporting.stages.insertion import DATA_CHECK, LOAD_DIAGRAM
from .fempython import ENV_FILE, RunnerError, read_env

RUNNER_KEY = "STRUCTURAL_MCP_JRSNAP_RUNNER"
PROTOCOL_VERSION = 1
ENGINE = "jrsnap"
# The runner gives up after this many seconds; WebPier waits a minute longer for its envelope.
ANALYSIS_TIMEOUT = 1800
TIMEOUT = ANALYSIS_TIMEOUT + 60
_KINDS = {"ndt", "analysis-result"}
_ANALYZE = "を JRSNAP で静的非線形解析できません"
# The figures of the データ確認図, in the order of the report (decision 50; Example2 10-3..10-7).
DATA_CHECK_FIGURES = ("nonlinear-numbers", "section-numbers", "element-table", "section-detail", "node-springs")
DATA_CHECK_COMBINATION = 1  # 番号図・断面・節点ばねは組合せで変わらない（決定50）
FIGURES_TIMEOUT = 300  # the runner's time for the データ確認図 …
LOAD_DIAGRAM_TIMEOUT = 120  # … and for the 荷重図 of each combination; WebPier waits a minute longer
_FIGURES = "のデータ確認図と荷重図を JRSNAP で描けません"


@dataclass(frozen=True)
class NonlinearFiles:
    files: Mapping[str, bytes]  # by the name JRSNAP gave each file
    engine_version: str
    summary: Mapping[str, Any]  # what the runner reports of JRSNAP and the analysis
    messages: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class FigurePages:
    data_check: bytes  # the pages of every figure, in the order of DATA_CHECK_FIGURES
    load_diagram: bytes  # one page per basic case, in case order, each from its combination's .ndt
    load_cases: tuple[tuple[int, int], ...]  # (basic case, combination) of each load diagram page
    engine_version: str
    summary: Mapping[str, Any]  # what the runner reports of JRSNAP, the .ndt and the pages
    # the pages of a basic case drawn from another NDU of the stage (decision 93: the NDU of a reversed push), as that NDU's
    # export kind and the pages it drew; ``load_cases`` then lists all, each combination being the one of its own NDU
    also: tuple[tuple[str, FigurePages], ...] = ()
    drawn_from: tuple[str, ...] = ()  # the export kind each load diagram page was drawn from (empty: all from the one NDU)

    @property
    def pages(self) -> dict[str, bytes]:
        """The pages by the name the report takes them (reporting.stages.insertion)."""
        return {DATA_CHECK: self.data_check, LOAD_DIAGRAM: self.load_diagram}


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
        raise RunnerError(f"データ確認図と静的非線形解析に使う JRSNAP の runner が設定されていません。" + (
            f"リポジトリのルートの .env に {RUNNER_KEY}='<JRSNAP.Headless.exe の絶対パス>' を書いてください" if dotenv
            else f"環境変数 {RUNNER_KEY} に JRSNAP.Headless.exe の絶対パスを設定してください"))
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


def _pages(name: str, file: str, content: bytes, action: str = _FIGURES) -> list[Any]:
    """The pages of the returned PDF *file*, which must have some."""
    try:
        pages = list(PdfReader(BytesIO(content), strict=True).pages)
    except (PyPdfError, ValueError, OSError) as exc:
        raise _fail(name, f"{file} を読めません（{exc}）", action) from exc
    if not pages:
        raise _fail(name, f"{file} にページがありません", action)
    return pages


def add_load_diagrams(pages: FigurePages, export: str, more: FigurePages) -> FigurePages:
    """*pages* with the load diagrams of the basic cases it has none of taken from *more*, drawn from the NDU of *export*
    (decision 93): the pages stay in the order of the basic cases, each from the first NDU that has it."""
    found: dict[int, tuple[int, str, Any]] = {}
    own = pages.drawn_from or ("",) * len(pages.load_cases)
    for source, kinds in ((pages, own), (more, (export,) * len(more.load_cases))):
        for (case, combination), page, kind in zip(source.load_cases, PdfReader(BytesIO(source.load_diagram)).pages, kinds):
            found.setdefault(case, (combination, kind, page))
    order = sorted(found)
    return FigurePages(pages.data_check, _pdf([found[case][2] for case in order]),
                       tuple((case, found[case][0]) for case in order), pages.engine_version, pages.summary,
                       (*pages.also, (export, more)), tuple(found[case][1] for case in order))


def _pdf(pages: Sequence[Any]) -> bytes:
    writer = PdfWriter()
    for page in pages:
        writer.add_page(page)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def _diagrams(name: str, summary: Mapping[str, Any], files: Mapping[str, bytes],
              combinations: Sequence[int]) -> dict[int, dict[int, Any]]:
    """The load diagram page of each basic case by its number, for each combination: the runner's
    ``summary.loadDiagram`` must list, in the order asked, one page per page of each combination's PDF."""
    listed = summary.get("loadDiagram")
    if (not isinstance(listed, list) or len(listed) != len(combinations)
            or not all(isinstance(item, dict) for item in listed)):
        raise _fail(name, f"runner の応答に組合せ {'・'.join(map(str, combinations))} の荷重図のページ"
                          f"（summary.loadDiagram）がありません（{listed!r}）", _FIGURES)
    found: dict[int, dict[int, Any]] = {}
    for combination, item in zip(combinations, listed):
        file = f"load-diagram-{combination}.pdf"
        pages, numbers = _pages(name, file, files[file]), item.get("pages")
        if (item.get("combination") != combination or item.get("file") != file or not isinstance(numbers, list)
                or not all(isinstance(page, dict) for page in numbers)
                or [page.get("page") for page in numbers] != list(range(1, len(pages) + 1))
                or not all(type(page.get("case")) is int for page in numbers)
                or len({page["case"] for page in numbers}) != len(numbers)):
            raise _fail(name, f"{file} のページが runner の応答（summary.loadDiagram）と一致しません（{item!r}）",
                        _FIGURES)
        found[combination] = {page["case"]: pages[page["page"] - 1] for page in numbers}
    return found


def draw_figures(name: str, document: bytes, runner: Path, load_cases: Sequence[tuple[int, int]], *,
                 timeout: float | None = None) -> FigurePages:
    """The データ確認図 and the 荷重図 pages *runner* draws for the NDU *document*, given to it as *name*, in one call
    (decisions 50, 51): the pages of each figure of ``DATA_CHECK_FIGURES`` for combination 1, in that order, and the
    load diagram page of each (basic case, combination) of *load_cases*, in that order, from that combination's .ndt.

    *timeout* (seconds) is how long WebPier waits: by default a minute longer than the runner's own time.
    ``ValueError`` when *load_cases* is empty, repeats a case or names a combination below 1.
    """
    cases = [case for case, _ in load_cases]
    combinations = sorted({combination for _, combination in load_cases})
    if not load_cases or len(set(cases)) != len(cases) or combinations[0] < 1:
        raise ValueError(f"荷重図のケースと組合せが不正です: {list(load_cases)!r}")
    seconds = FIGURES_TIMEOUT + LOAD_DIAGRAM_TIMEOUT * len(combinations)
    figures = [f"{figure}.pdf" for figure in DATA_CHECK_FIGURES]
    diagrams = [f"load-diagram-{combination}.pdf" for combination in combinations]
    kinds = ["data-check"] * len(figures) + ["load-diagram"] * len(diagrams)
    envelope, files = _call(
        name, document, runner, "figures",
        ("--data-check", ",".join(DATA_CHECK_FIGURES), "--data-check-combination", str(DATA_CHECK_COMBINATION),
         "--load-diagram", ",".join(map(str, combinations)), "--timeout-seconds", str(seconds)),
        seconds + 60 if timeout is None else timeout, _FIGURES,
        lambda artifacts: ([item.get("relativePath") for item in artifacts] == figures + diagrams
                           and [item.get("kind") for item in artifacts] == kinds),
        "データ確認図の図ごとの PDF と組合せごとの荷重図の PDF")
    data_check = _pdf([page for file in figures for page in _pages(name, file, files[file])])
    drawn = _diagrams(name, envelope["summary"], files, combinations)
    pages = []
    for case, combination in load_cases:
        if case not in drawn[combination]:
            raise _fail(name, f"組合せ {combination} の荷重図に CASE-{case} のページがありません", _FIGURES)
        pages.append(drawn[combination][case])
    return FigurePages(data_check, _pdf(pages), tuple((case, combination) for case, combination in load_cases),
                       envelope["engineVersion"], envelope["summary"])


# SOIL-JR's calculation of the ground of a pile foundation (decision 85, ADR-0013): one call of the runner's ``soil``.
SOIL_TIMEOUT = 600  # the runner's time; WebPier waits a minute longer
SOIL_REPORT = "soil-jr-report"  # the name the stage's report takes SOIL-JR's report (reporting.stages.insertion's kind)
_SOIL = "を SOIL-JR で計算できません"


@dataclass(frozen=True)
class SoilFiles:
    files: Mapping[str, bytes]  # the files by kind: "sdr", "sdc", and "liquefiedsdr", "liquefiedsdc" with a liquefaction
    report: bytes  # SOIL-JR's report as the runner printed it (a PDF of every output item)
    engine_version: str
    summary: Mapping[str, Any]  # what the runner reports of JRSNAP and of the input
    messages: tuple[Mapping[str, Any], ...]  # SOIL-JR's warnings during the calculation

    @property
    def pages(self) -> dict[str, bytes]:
        """The report by the name the stage's report takes it: SOIL-JR's own, with no page of WebPier's."""
        return {SOIL_REPORT: self.report}


def calculate_ground(name: str, document: bytes, runner: Path, *, liquefaction: bool,
                     timeout: float | None = None) -> SoilFiles:
    """SOIL-JR's files and report for the .sdt *document*, given to the runner as *name* (``<stem>.sdt``): the
    基礎照査連携用データ (``<stem>.sdr``) and 解析連携データ (``<stem>.sdc``), the same two for the liquefaction
    (``<stem>(液状化時用).sdr``, ``.sdc``) when *liquefaction* (the runner returns them only for an input that considers
    it), and the report ``<stem>.pdf``. The runner's account of the input (its name and SHA256) and of the liquefaction
    must be this document's."""
    stem = name.removesuffix(".sdt")
    expected = [(f"{stem}.sdr", "soil-sdr", "sdr"), (f"{stem}.sdc", "soil-sdc", "sdc")]
    if liquefaction:
        expected += [(f"{stem}(液状化時用).sdr", "soil-sdr-liquefaction", "liquefiedsdr"),
                     (f"{stem}(液状化時用).sdc", "soil-sdc-liquefaction", "liquefiedsdc")]
    expected.append((f"{stem}.pdf", "soil-report", "report"))
    envelope, files = _call(
        name, document, runner, "soil", ("--timeout-seconds", str(SOIL_TIMEOUT)),
        SOIL_TIMEOUT + 60 if timeout is None else timeout, _SOIL,
        lambda artifacts: ([item.get("relativePath") for item in artifacts] == [file for file, _, _ in expected]
                           and [item.get("kind") for item in artifacts] == [kind for _, kind, _ in expected]),
        "SOIL-JR の連携ファイルと帳票")
    summary = envelope["summary"]
    reported = summary.get("input")
    if (not isinstance(reported, dict) or reported.get("name") != name
            or reported.get("sha256") != hashlib.sha256(document).hexdigest()
            or summary.get("liquefaction") is not liquefaction):
        raise _fail(name, f"runner が計算した入力か液状化の有無が渡した .sdt と違います（{reported!r}、"
                          f"liquefaction {summary.get('liquefaction')!r}）", _SOIL)
    report = files[f"{stem}.pdf"]
    _pages(name, f"{stem}.pdf", report, _SOIL)
    return SoilFiles({key: files[file] for file, _, key in expected if key != "report"}, report,
                     envelope["engineVersion"], summary, tuple(envelope["messages"]))
