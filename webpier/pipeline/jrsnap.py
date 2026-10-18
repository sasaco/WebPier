"""The JRSNAP runner: the static nonlinear analysis of 0711 and 0721 (decision 47, ADR-0007).

The NDU a generation writes is given, as it is and under its own name, to ``JRSNAP.Headless.exe run``. The runner
writes the analysis data (.ndt) of every combination as JRSNAP's 解析用データ出力 does, has JRSNAP's S_ANALYSIS.exe
analyze them, and returns every file in its output folder under the names JRSNAP gave them. They are published
together as one folder, as they are returned: their content and bytes are JRSNAP's, so they are neither checked
further nor bound to the implementation identity. The sidecar records the runner's ``engineVersion`` and what the
runner reports of JRSNAP (version, display flags, the confirmations it answered, the messages of the analysis).

The runner is the absolute path in ``STRUCTURAL_MCP_JRSNAP_RUNNER``: the process environment first, then the
``.env`` file at the repository root (not tracked). The JRSNAP installation is the runner's own setting. Without a
runner, or when it fails, a generation that needs it stops; nothing is published without its analysis.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from .fempython import ENV_FILE, RunnerError, read_env

RUNNER_KEY = "STRUCTURAL_MCP_JRSNAP_RUNNER"
PROTOCOL_VERSION = 1
ENGINE = "jrsnap"
# The runner gives up after this many seconds; WebPier waits a minute longer for its envelope.
ANALYSIS_TIMEOUT = 1800
TIMEOUT = ANALYSIS_TIMEOUT + 60
_KINDS = {"ndt", "analysis-result"}
_ANALYZE = "を JRSNAP で静的非線形解析できません"


@dataclass(frozen=True)
class NonlinearFiles:
    files: Mapping[str, bytes]  # by the name JRSNAP gave each file
    engine_version: str
    summary: Mapping[str, Any]  # what the runner reports of JRSNAP and the analysis
    messages: tuple[Mapping[str, Any], ...]


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
        raise RunnerError(f"静的非線形解析に使う JRSNAP の runner が設定されていません。リポジトリのルートの .env に "
                          f"{RUNNER_KEY}='<JRSNAP.Headless.exe の絶対パス>' を書いてください")
    path = Path(value)
    if not path.is_absolute():
        raise RunnerError(f"{where} は絶対パスにしてください: {value}")
    if not path.is_file():
        raise RunnerError(f"{where} の runner がありません: {value}")
    return path


def _fail(name: str, message: str) -> RunnerError:
    return RunnerError(f"{name} {_ANALYZE}: {message}")


def _envelope(name: str, stdout: bytes) -> dict[str, Any]:
    try:
        envelope = json.loads(stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(name, f"runner の応答が JSON ではありません（{exc}）") from exc
    if not isinstance(envelope, dict):
        raise _fail(name, "runner の応答が JSON のオブジェクトではありません")
    if envelope.get("protocolVersion") != PROTOCOL_VERSION or envelope.get("engine") != ENGINE:
        raise _fail(name, f"runner のやり取りの版が違います（protocolVersion {envelope.get('protocolVersion')!r}、"
                          f"engine {envelope.get('engine')!r}）")
    return envelope


def _plain(name: Any) -> bool:
    return isinstance(name, str) and name not in {"", ".", ".."} and not set(name) & set("/\\:")


def analyze_nonlinear(name: str, document: bytes, runner: Path, *, timeout: float = TIMEOUT) -> NonlinearFiles:
    """Every file *runner* returns for the NDU *document*, given to it as *name* (decision 47)."""
    with tempfile.TemporaryDirectory(prefix="webpier-jrsnap-") as work:
        source, output = Path(work) / name, Path(work) / "output"
        source.write_bytes(document)
        try:
            done = subprocess.run([str(runner), "run", "--input", str(source), "--output-dir", str(output),
                                   "--analyze", "true", "--timeout-seconds", str(ANALYSIS_TIMEOUT)],
                                  capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise _fail(name, f"{timeout} 秒で終わりませんでした") from exc
        except OSError as exc:
            raise _fail(name, f"runner を起動できません（{exc}）") from exc
        envelope = _envelope(name, done.stdout)
        if done.returncode or envelope.get("ok") is not True or envelope.get("executionStatus") != "success":
            errors = "; ".join(f"{error.get('code')}: {error.get('message')}" for error in envelope.get("errors") or ()
                               if isinstance(error, dict)) or f"終了コード {done.returncode}"
            raise _fail(name, errors)
        version, artifacts = envelope.get("engineVersion"), envelope.get("artifacts")
        summary, messages = envelope.get("summary"), envelope.get("messages")
        if not isinstance(version, str) or not version:
            raise _fail(name, "runner の版（engineVersion）がありません")
        if not isinstance(summary, dict) or not isinstance(messages, list) or not all(
                isinstance(message, dict) for message in messages):
            raise _fail(name, "runner の応答に summary・messages がありません")
        if (not isinstance(artifacts, list) or not all(isinstance(item, dict) for item in artifacts)
                or not all(item.get("kind") in _KINDS and _plain(item.get("relativePath")) for item in artifacts)
                or not any(item["kind"] == "ndt" for item in artifacts)
                or len({item["relativePath"].casefold() for item in artifacts}) != len(artifacts)):
            raise _fail(name, f"runner の成果物が解析用データと解析結果のファイルではありません（{artifacts!r}）")
        present = sorted(path.name for path in output.iterdir()) if output.is_dir() else []
        if present != sorted(item["relativePath"] for item in artifacts):
            raise _fail(name, f"runner の出力先のファイルが成果物の一覧と一致しません（{present!r}）")
        files: dict[str, bytes] = {}
        for item in artifacts:
            content = (output / item["relativePath"]).read_bytes()
            if hashlib.sha256(content).hexdigest() != item.get("sha256") or len(content) != item.get("bytes"):
                raise _fail(name, f"{item['relativePath']} が runner の応答の SHA256・バイト数と一致しません")
            files[item["relativePath"]] = content
    return NonlinearFiles(files, version, summary, tuple(messages))
