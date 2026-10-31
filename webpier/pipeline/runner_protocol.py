"""One call of a Headless runner of structural-mcp by protocol v1, as the runner modules make it.

The runner is started with its arguments (``shell`` false) and must finish within the timeout. Its stdout is one JSON
envelope of the engine asked for; a failed run is reported by the reasons it gives. A successful run declares exactly the
artifacts asked for, each of them a file in the output folder with the SHA-256 and the size declared; the folder holds
nothing else unless the caller does not look (``listing``). What failed is said by the caller (``RunFailure`` holds why).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Literal

PROTOCOL_VERSION = 1


class RunFailure(Exception):
    """The runner did not do what was asked: why, for the caller's message."""


def envelope(stdout: bytes, engine: str) -> dict[str, Any]:
    """The envelope of *engine* on the runner's *stdout*."""
    try:
        found = json.loads(stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunFailure(f"runner の応答が JSON ではありません（{exc}）") from exc
    if not isinstance(found, dict):
        raise RunFailure("runner の応答が JSON のオブジェクトではありません")
    if found.get("protocolVersion") != PROTOCOL_VERSION or found.get("engine") != engine:
        raise RunFailure(f"runner のやり取りの版が違います（protocolVersion {found.get('protocolVersion')!r}、"
                         f"engine {found.get('engine')!r}）")
    return found


def reasons(found: dict[str, Any], returncode: int, *, errors: bool = True, levels: tuple[str, ...] = ()) -> str:
    """Why the runner failed: its ``errors`` (unless *errors* is false), then its ``messages`` at *levels*; the exit code
    when it gives none."""
    listed = [f"{error.get('code')}: {error.get('message')}" for error in found.get("errors") or ()
              if isinstance(error, dict)] if errors else []
    messages = found.get("messages")
    listed += [f"{message.get('code')}: {message.get('text')}" for message in messages if isinstance(message, dict)
               and message.get("level") in levels] if isinstance(messages, list) else []
    return "; ".join(listed) or f"終了コード {returncode}"


def run(arguments: Sequence[str], output: Path, engine: str, expected: set[tuple[str, str]], what: str, timeout: float,
        *, reasons_of: Callable[[dict[str, Any], int], str] = reasons,
        listing: Literal["named", "bare", None] = "named") -> tuple[dict[str, Any], str, dict[str, bytes]]:
    """The envelope, the engine's version and the bytes of each artifact by its relative path of the runner run with
    *arguments* into *output*: the artifacts must be *expected* ((kind, relative path); *what* names them), and the folder
    must hold only them (*listing*: "named" lists what it holds, "bare" does not, None does not look)."""
    try:
        done = subprocess.run(list(arguments), capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RunFailure(f"{timeout} 秒で終わりませんでした") from exc
    except OSError as exc:
        raise RunFailure(f"runner を起動できません（{exc}）") from exc
    found = envelope(done.stdout, engine)
    if done.returncode or found.get("ok") is not True or found.get("executionStatus") != "success":
        raise RunFailure(reasons_of(found, done.returncode))
    version, artifacts = found.get("engineVersion"), found.get("artifacts")
    if not isinstance(version, str) or not version:
        raise RunFailure("runner の版（engineVersion）がありません")
    if (not isinstance(artifacts, list) or len(artifacts) != len(expected)
            or not all(isinstance(item, dict) for item in artifacts)
            or {(item.get("kind"), item.get("relativePath")) for item in artifacts} != expected):
        raise RunFailure(f"runner の成果物が{what}ではありません（{artifacts!r}）")
    files: dict[str, bytes] = {}
    for item in artifacts:
        path = output / item["relativePath"]
        if not path.is_file():
            raise RunFailure(f"runner の成果物 {item['relativePath']} がありません")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != item.get("sha256") or len(content) != item.get("bytes"):
            raise RunFailure(f"{item['relativePath']} が runner の応答の SHA256・バイト数と一致しません")
        files[item["relativePath"]] = content
    if listing is not None:
        present = sorted(path.name for path in output.iterdir())
        if present != sorted(files):
            raise RunFailure("runner の出力先のファイルが成果物の一覧と一致しません"
                             + (f"（{present!r}）" if listing == "named" else ""))
    return found, version, files


__all__ = ["PROTOCOL_VERSION", "RunFailure", "envelope", "reasons", "run"]
