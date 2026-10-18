"""The FEMPython runner that draws the load diagrams of 0610 and 0620 (decision 44, ADR-0005).

The FrameWeb file a generation writes is given, as it is, to ``FrameWebforCS.Headless.exe run`` with the PDF
section ``load_diagram`` alone: the runner draws every load case of the file and calculates nothing. The report
takes the returned pages as they are; their content, page count and bytes are FEMPython's, so they are neither
checked nor bound to the implementation identity, and the sidecars record the runner's ``engineVersion``.

The runner is the absolute path in ``STRUCTURAL_MCP_FEMPYTHON_RUNNER`` (the name structural-mcp uses): the process
environment first, then the ``.env`` file at the repository root (not tracked). Without a runner, or when it fails,
a generation with 0610 or 0620 stops; nothing is published without its load diagram.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

PROJECT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_DIR / ".env"
RUNNER_KEY = "STRUCTURAL_MCP_FEMPYTHON_RUNNER"
PROTOCOL_VERSION = 1
ENGINE = "fempython"
# Decision 44: A4 portrait, no axis page, two cases a page one above the other.
ARGUMENTS = ("--generate-pik", "false", "--pdf-sections", "load_diagram", "--pdf-paper", "A4",
             "--pdf-orientation", "vertical", "--load-diagram-layout", "split_horizontal",
             "--load-diagram-axis", "false")
TIMEOUT = 600  # seconds; the runner itself gives up after ten minutes
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class RunnerError(Exception):
    """The FEMPython runner is not set up, or it did not draw the load diagram."""


@dataclass(frozen=True)
class LoadDiagramPages:
    pdf: bytes
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
        raise RunnerError(f"荷重図を描く FEMPython の runner が設定されていません。リポジトリのルートの .env に "
                          f"{RUNNER_KEY}='<FrameWebforCS.Headless.exe の絶対パス>' を書いてください")
    path = Path(value)
    if not path.is_absolute():
        raise RunnerError(f"{where} は絶対パスにしてください: {value}")
    if not path.is_file():
        raise RunnerError(f"{where} の runner がありません: {value}")
    return path


def _fail(document: Path, message: str) -> RunnerError:
    return RunnerError(f"{document.name} の荷重図を FEMPython で描けません: {message}")


def _envelope(document: Path, stdout: bytes) -> dict[str, Any]:
    try:
        envelope = json.loads(stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(document, f"runner の応答が JSON ではありません（{exc}）") from exc
    if not isinstance(envelope, dict):
        raise _fail(document, "runner の応答が JSON のオブジェクトではありません")
    if envelope.get("protocolVersion") != PROTOCOL_VERSION or envelope.get("engine") != ENGINE:
        raise _fail(document, f"runner のやり取りの版が違います（protocolVersion {envelope.get('protocolVersion')!r}、"
                              f"engine {envelope.get('engine')!r}）")
    return envelope


def draw_load_diagram(document: Path, runner: Path, *, timeout: int = TIMEOUT) -> LoadDiagramPages:
    """The load diagram pages of the FrameWeb file *document*, drawn by *runner*."""
    document = Path(document).resolve()
    with tempfile.TemporaryDirectory(prefix="webpier-fempython-") as work:
        output = Path(work) / "output"
        try:
            done = subprocess.run([str(runner), "run", "--input", str(document), "--output-dir", str(output),
                                   *ARGUMENTS], capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise _fail(document, f"{timeout} 秒で終わりませんでした") from exc
        except OSError as exc:
            raise _fail(document, f"runner を起動できません（{exc}）") from exc
        envelope = _envelope(document, done.stdout)
        if done.returncode or envelope.get("ok") is not True or envelope.get("executionStatus") != "success":
            errors = "; ".join(f"{error.get('code')}: {error.get('message')}" for error in envelope.get("errors") or ()
                               if isinstance(error, dict)) or f"終了コード {done.returncode}"
            raise _fail(document, errors)
        version = envelope.get("engineVersion")
        artifacts = envelope.get("artifacts")
        if not isinstance(version, str) or not version:
            raise _fail(document, "runner の版（engineVersion）がありません")
        if (not isinstance(artifacts, list) or len(artifacts) != 1 or not isinstance(artifacts[0], dict)
                or artifacts[0].get("kind") != "pdf" or artifacts[0].get("relativePath") != "report.pdf"):
            raise _fail(document, f"runner の成果物が荷重図の PDF 1つではありません（{artifacts!r}）")
        path = output / "report.pdf"
        if not path.is_file():
            raise _fail(document, "runner の荷重図の PDF がありません")
        pdf = path.read_bytes()
    if hashlib.sha256(pdf).hexdigest() != artifacts[0].get("sha256") or len(pdf) != artifacts[0].get("bytes"):
        raise _fail(document, "荷重図の PDF が runner の応答の SHA256・バイト数と一致しません")
    try:
        pages = len(PdfReader(BytesIO(pdf), strict=True).pages)
    except (PyPdfError, ValueError, OSError) as exc:
        raise _fail(document, f"荷重図の PDF を読めません（{exc}）") from exc
    if not pages:
        raise _fail(document, "荷重図の PDF にページがありません")
    return LoadDiagramPages(pdf, version)
