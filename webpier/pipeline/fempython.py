"""The FEMPython runner: the load diagrams of 0610 and 0620 (decision 44, ADR-0005) and the frame analyses of 0611,
0612, 0621 and 0622 (decisions 46, 54, ADR-0006).

The FrameWeb file a generation writes is given, as it is, to ``FrameWebforCS.Headless.exe run``. For a load diagram
the PDF section ``load_diagram`` alone is asked for: the runner draws every load case of the file and calculates
nothing, and the report takes the returned pages as they are. For a frame analysis, a separate call asks for no PDF
but the PIK and both node pickup CSVs: the runner calculates the file, and the three files are published as they are
returned (``result.json`` is checked and not kept). Their content and bytes are FEMPython's, so they are neither
checked further nor bound to the implementation identity; the sidecars record the runner's ``engineVersion``. The
基礎の照査 reads the reactions at the support node from the reaction CSV (``support_reactions``, decision 54).

The runner is the absolute path in ``STRUCTURAL_MCP_FEMPYTHON_RUNNER`` (the name structural-mcp uses): the process
environment first, then the ``.env`` file at the repository root (not tracked). Without a runner, or when it fails,
a generation that needs it stops; nothing is published without its load diagram or its analysis.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
from dataclasses import dataclass
import hashlib
from io import BytesIO, StringIO
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from ..calc.foundation_check import ReactionError, Reactions, SupportReaction
from ..calc.pile_body import PointForces, SectionForce
from ..calc.pile_check import Displacements, Extreme, HeadForce, HeadForces, PileResponseError
from ..reporting.stages.insertion import LOAD_DIAGRAM

PROJECT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_DIR / ".env"
RUNNER_KEY = "STRUCTURAL_MCP_FEMPYTHON_RUNNER"
PROTOCOL_VERSION = 1
ENGINE = "fempython"
# Decision 44: A4 portrait, no axis page, two cases a page one above the other.
ARGUMENTS = ("--generate-pik", "false", "--pdf-sections", "load_diagram", "--pdf-paper", "A4",
             "--pdf-orientation", "vertical", "--load-diagram-layout", "split_horizontal",
             "--load-diagram-axis", "false")
# Decision 46: the frame analysis without a PDF, with the PIK and both node pickup CSVs.
ANALYSIS_ARGUMENTS = ("--generate-pdf", "false", "--generate-pik", "true", "--generate-pickup-displacement-csv",
                      "true", "--generate-pickup-reaction-csv", "true")
# The files of an analysis by the kind WebPier publishes them as: (the runner's artifact kind, its file).
ANALYSIS_FILES = {"pik": ("pik", "pickup.pik"),
                  "displacement": ("pickup-displacement", "pickup-displacement.csv"),
                  "reaction": ("pickup-reaction", "pickup-reaction.csv")}
TIMEOUT = 600  # seconds; the runner itself gives up after ten minutes
_DIAGRAM = ("pdf", "report.pdf")
_RESULT = ("result", "result.json")  # always returned with a calculation; checked, not published
_DRAW = "の荷重図を FEMPython で描けません"
_ANALYZE = "を FEMPython で骨組解析できません"
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class RunnerError(Exception):
    """The FEMPython runner is not set up, or it did not draw the load diagram or analyze the frame."""


@dataclass(frozen=True)
class LoadDiagramPages:
    pdf: bytes
    engine_version: str

    @property
    def pages(self) -> dict[str, bytes]:
        """The pages by the name the report takes them (reporting.stages.insertion)."""
        return {LOAD_DIAGRAM: self.pdf}


@dataclass(frozen=True)
class AnalysisFiles:
    files: Mapping[str, bytes]  # by the kinds of ANALYSIS_FILES, the bytes as the runner returned them
    engine_version: str


def read_env(path: Path) -> dict[str, str]:
    """``KEY=VALUE`` lines; blank lines and ``#`` comments are skipped and a value may be quoted with ' or "."""
    settings: dict[str, str] = {}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        key, separator, value = (part.strip() for part in text.partition("="))
        if not separator or not _KEY.fullmatch(key):
            raise RunnerError(f"{path} の {number} 行目は「名前=値」ではありません")
        if key in settings:
            raise RunnerError(f"{path} の {key} が重複しています")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        settings[key] = value
    return settings


def find_runner(key: str, purpose: str, program: str, environ: Mapping[str, str] | None, env_file: Path, *,
                dotenv: bool) -> Path:
    """The runner executable of *key* (*program*, used for *purpose*): the environment variable, else (unless *dotenv* is
    false: the headless runner, decision 61) the setting in *env_file*; both as they are now."""
    environ = os.environ if environ is None else environ
    value = environ.get(key, "")
    where = f"環境変数 {key}"
    if not value and dotenv:
        value = read_env(env_file).get(key, "") if Path(env_file).is_file() else ""
        where = f"{env_file} の {key}"
    if not value:
        raise RunnerError(f"{purpose}の runner が設定されていません。" + (
            f"リポジトリのルートの .env に {key}='<{program} の絶対パス>' を書いてください" if dotenv
            else f"環境変数 {key} に {program} の絶対パスを設定してください"))
    path = Path(value)
    if not path.is_absolute():
        raise RunnerError(f"{where} は絶対パスにしてください: {value}")
    if not path.is_file():
        raise RunnerError(f"{where} の runner がありません: {value}")
    return path


def runner_path(environ: Mapping[str, str] | None = None, env_file: Path | None = None, *, dotenv: bool = True
                ) -> Path:
    """The runner executable: the environment variable, else (unless *dotenv* is false: the headless runner,
    decision 61) the ``.env`` setting; both as they are now."""
    return find_runner(RUNNER_KEY, "荷重図・骨組解析に使う FEMPython ", "FrameWebforCS.Headless.exe", environ, ENV_FILE if env_file is None else env_file,
                       dotenv=dotenv)


def _fail(document: Path, what: str, message: str) -> RunnerError:
    return RunnerError(f"{document.name} {what}: {message}")


def _envelope(document: Path, what: str, stdout: bytes) -> dict[str, Any]:
    try:
        envelope = json.loads(stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(document, what, f"runner の応答が JSON ではありません（{exc}）") from exc
    if not isinstance(envelope, dict):
        raise _fail(document, what, "runner の応答が JSON のオブジェクトではありません")
    if envelope.get("protocolVersion") != PROTOCOL_VERSION or envelope.get("engine") != ENGINE:
        raise _fail(document, what, f"runner のやり取りの版が違います（protocolVersion "
                                    f"{envelope.get('protocolVersion')!r}、engine {envelope.get('engine')!r}）")
    return envelope


def _run(document: Path, runner: Path, arguments: Sequence[str], expected: Sequence[tuple[str, str]], label: str,
         what: str, timeout: float) -> tuple[str, dict[str, bytes]]:
    """Run *runner* on *document*: its engineVersion and exactly the *expected* (kind, file) artifacts by file,
    each checked against the SHA256 and size of the envelope."""
    with tempfile.TemporaryDirectory(prefix="webpier-fempython-") as work:
        output = Path(work) / "output"
        try:
            done = subprocess.run([str(runner), "run", "--input", str(document), "--output-dir", str(output),
                                   *arguments], capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise _fail(document, what, f"{timeout} 秒で終わりませんでした") from exc
        except OSError as exc:
            raise _fail(document, what, f"runner を起動できません（{exc}）") from exc
        envelope = _envelope(document, what, done.stdout)
        if done.returncode or envelope.get("ok") is not True or envelope.get("executionStatus") != "success":
            errors = "; ".join(f"{error.get('code')}: {error.get('message')}" for error in envelope.get("errors") or ()
                               if isinstance(error, dict)) or f"終了コード {done.returncode}"
            raise _fail(document, what, errors)
        version = envelope.get("engineVersion")
        artifacts = envelope.get("artifacts")
        if not isinstance(version, str) or not version:
            raise _fail(document, what, "runner の版（engineVersion）がありません")
        if (not isinstance(artifacts, list) or len(artifacts) != len(expected)
                or not all(isinstance(item, dict) for item in artifacts)
                or {(item.get("kind"), item.get("relativePath")) for item in artifacts} != set(expected)):
            raise _fail(document, what, f"runner の成果物が{label}ではありません（{artifacts!r}）")
        files: dict[str, bytes] = {}
        for item in artifacts:
            path = output / item["relativePath"]
            if not path.is_file():
                raise _fail(document, what, f"runner の成果物 {item['relativePath']} がありません")
            files[item["relativePath"]] = path.read_bytes()
    for item in artifacts:
        content = files[item["relativePath"]]
        if hashlib.sha256(content).hexdigest() != item.get("sha256") or len(content) != item.get("bytes"):
            raise _fail(document, what, f"{item['relativePath']} が runner の応答の SHA256・バイト数と一致しません")
    return version, files


def draw_load_diagram(document: Path, runner: Path, *, timeout: float = TIMEOUT) -> LoadDiagramPages:
    """The load diagram pages of the FrameWeb file *document*, drawn by *runner*."""
    document = Path(document).resolve()
    version, files = _run(document, runner, ARGUMENTS, (_DIAGRAM,), "荷重図の PDF 1つ", _DRAW, timeout)
    pdf = files[_DIAGRAM[1]]
    try:
        pages = len(PdfReader(BytesIO(pdf), strict=True).pages)
    except (PyPdfError, ValueError, OSError) as exc:
        raise _fail(document, _DRAW, f"荷重図の PDF を読めません（{exc}）") from exc
    if not pages:
        raise _fail(document, _DRAW, "荷重図の PDF にページがありません")
    return LoadDiagramPages(pdf, version)


def analyze_frame(name: str, document: bytes, runner: Path, *, timeout: float = TIMEOUT) -> AnalysisFiles:
    """The pickup files *runner* returns for the FrameWeb file *document* (decision 46), given to it as *name*."""
    with tempfile.TemporaryDirectory(prefix="webpier-fempython-") as work:
        path = Path(work) / name
        path.write_bytes(document)
        version, files = _run(path, runner, ANALYSIS_ARGUMENTS, (_RESULT, *ANALYSIS_FILES.values()),
                              "解析結果・PIK・変位量と反力の CSV の4つ", _ANALYZE, timeout)
    return AnalysisFiles({kind: files[file] for kind, (_, file) in ANALYSIS_FILES.items()}, version)


# The columns of the reaction pickup CSV the 基礎の照査 reads, by the name before the unit ("max_fx (kN)").
_REACTION_COLUMNS = ("pickup_id", "focus_component", "node_id", "max_combine_id", "min_combine_id", "max_fx", "max_fy",
                     "max_mz", "min_fx", "min_fy", "min_mz")


def support_reactions(content: bytes, node: int) -> Reactions:
    """The largest and the smallest extreme of every pickup and focus component at *node*, from the reaction pickup
    CSV as FEMPython returns it (decision 54); ``ReactionError`` when it cannot be read."""
    try:
        rows = list(csv.reader(StringIO(content.decode("utf-8-sig"))))
        header = [name.split(" ", 1)[0] for name in rows[0]]
        index = {name: header.index(name) for name in _REACTION_COLUMNS}
        found: dict[tuple[int, str], tuple[SupportReaction, SupportReaction]] = {}
        for number, row in enumerate(rows[1:], 2):
            if int(row[index["node_id"]]) != node:
                continue
            extremes = []
            for side in ("max", "min"):
                forces = tuple(float(row[index[f"{side}_{name}"]]) for name in ("fx", "fy", "mz"))
                if not all(map(math.isfinite, forces)):
                    raise ReactionError(f"{number} 行目に有限でない反力があります")
                extremes.append(SupportReaction(int(row[index[f"{side}_combine_id"]]), *forces))
            key = (int(row[index["pickup_id"]]), row[index["focus_component"]])
            if key in found:
                raise ReactionError(f"{number} 行目: ピックアップ {key[0]}（{key[1]}）の節点 {node} が重複しています")
            found[key] = (extremes[0], extremes[1])
    except (UnicodeDecodeError, IndexError, ValueError) as exc:
        raise ReactionError(f"反力の CSV を読めません（{exc}）") from exc
    return found


def head_forces(content: bytes, members: Sequence[int]) -> HeadForces:
    """The axial force at the head (the ITAN point) of each of *members* in every pickup, from the PIK as FEMPython
    returns it (decision 89): the line whose focus is the axial force (N) gives its largest and smallest values with
    their combinations; ``PileResponseError`` when it cannot be read."""
    found: dict[tuple[int, int], HeadForce] = {}
    try:
        for number, line in enumerate(content.decode("utf-8-sig").splitlines(), 1):
            cells = line.split()
            if len(cells) != 13 or cells[1] != "N" or cells[5] != "ITAN" or int(cells[2]) not in members:
                continue
            key = (int(cells[0]), int(cells[2]))
            forces = (float(cells[9]), float(cells[12]))
            if key in found or not all(map(math.isfinite, forces)):
                raise PileResponseError(f"{number} 行目: ピックアップ {key[0]} の部材 {key[1]} の杭頭が重複しているか有限でありません")
            found[key] = HeadForce(forces[0], int(cells[3]), forces[1], int(cells[4]))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PileResponseError(f"PIK を読めません（{exc}）") from exc
    return found


def footing_displacements(content: bytes, node: int) -> Displacements:
    """The largest absolute horizontal displacement (dx) and rotation (rz) of *node* in every pickup, each from the row
    of its own focus component of the displacement pickup CSV (the sample's 2.5.11 takes each extreme by itself);
    ``PileResponseError`` when it cannot be read."""
    try:
        rows = list(csv.reader(StringIO(content.decode("utf-8-sig"))))
        header = [name.split(" ", 1)[0] for name in rows[0]]
        index = {name: header.index(name) for name in ("pickup_id", "focus_component", "node_id", "max_combine_id",
                                                       "min_combine_id", "max_dx", "min_dx", "max_rz", "min_rz")}
        found: dict[tuple[int, str], Extreme] = {}
        for number, row in enumerate(rows[1:], 2):
            # the rows of the nodes the runner adds inside a member are named "generated:<member>:S<n>"
            if row[index["node_id"]] != str(node) or row[index["focus_component"]] not in ("dx", "rz"):
                continue
            component = row[index["focus_component"]]
            largest, smallest = (float(row[index[f"{side}_{component}"]]) for side in ("max", "min"))
            if not (math.isfinite(largest) and math.isfinite(smallest)):
                raise PileResponseError(f"{number} 行目に有限でない変位があります")
            side = "max" if abs(largest) >= abs(smallest) else "min"
            key = (int(row[index["pickup_id"]]), component)
            if key in found:
                raise PileResponseError(f"{number} 行目: ピックアップ {key[0]}（{component}）の節点 {node} が重複しています")
            found[key] = Extreme(abs(largest if side == "max" else smallest), int(row[index[f"{side}_combine_id"]]))
    except (UnicodeDecodeError, IndexError, ValueError) as exc:
        raise PileResponseError(f"変位の CSV を読めません（{exc}）") from exc
    return found


def member_forces(content: bytes, members: Sequence[int], pickup: int) -> dict[int, tuple[PointForces, ...]]:
    """The section forces of each of *members* in *pickup*, point by point, from the PIK as FEMPython returns it
    (decision 89): a line of the focus M (bending moment), S (shear force) or N (axial force) at a point of a member
    (ITAN: the head, JTAN: the tip, else a number) gives the forces of its largest and its smallest case, each with
    the case; ``PileResponseError`` when it cannot be read."""
    found: dict[int, list[PointForces]] = {member: [] for member in members}
    try:
        for number, line in enumerate(content.decode("utf-8-sig").splitlines(), 1):
            cells = line.split()
            if len(cells) != 13 or cells[1] not in ("M", "S", "N") or int(cells[0]) != pickup or int(cells[2]) not in found:
                continue
            forces = [float(cell) for cell in cells[6:]]
            if not all(map(math.isfinite, forces)):
                raise PileResponseError(f"{number} 行目に有限でない断面力があります")
            found[int(cells[2])].append(PointForces(
                cells[1], cells[5], forces[0], SectionForce(forces[1], forces[2], forces[3], int(cells[3])),
                SectionForce(forces[4], forces[5], forces[6], int(cells[4]))))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PileResponseError(f"PIK を読めません（{exc}）") from exc
    return {member: tuple(rows) for member, rows in found.items()}
