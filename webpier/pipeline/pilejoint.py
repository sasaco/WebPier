"""The Capacita runner of the joint of a steel pipe pile with the footing in 0612 and 0622 (decision 90).

The JSON a generation builds (``export.capacita.pile_joint``) is given, as it is, to ``WebDanforCS.Headless.exe
run-pile-joint`` (the runner of ``pipeline.capacita``, ``STRUCTURAL_MCP_WEBDAN_RUNNER``). The runner returns ``result.json`` alone:
HsCalc's design bending resistance (``rows[].mu``, kN m) of every row asked for, by the id of the row. A row that is missing,
duplicated or not asked for is an error. The engine's version is recorded in the result of the stage.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from .fempython import RunnerError

PROTOCOL_VERSION = 1
ENGINE = "webdan2"
TIMEOUT = 600  # seconds
_RESULT = ("result", "result.json")
_WHAT = "で鋼管杭の結合部の照査ができません"


class _Failure(Exception):
    pass


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


def _moments(result: Any, ids: set[str]) -> dict[str, float]:
    listed = result.get("rows") if isinstance(result, dict) else None
    if not isinstance(listed, list):
        raise _Failure("計算結果に rows がありません")
    found: dict[str, float] = {}
    for item in listed:
        mu = item.get("mu") if isinstance(item, dict) else None
        name = item.get("id") if isinstance(item, dict) else None
        if not isinstance(name, str) or isinstance(mu, bool) or not isinstance(mu, (int, float)):
            raise _Failure(f"計算結果の行が読めません（{item!r}）")
        if name in found:
            raise _Failure(f"計算結果の行が重複しています（{name}）")
        found[name] = float(mu)
    if set(found) != ids:
        raise _Failure(f"計算結果の行が依頼に合いません（足りない {sorted(ids - set(found))!r}、余分 {sorted(set(found) - ids)!r}）")
    return found


def check_joint(content: bytes, ids: set[str], runner: Path, *, timeout: float = TIMEOUT) -> tuple[dict[str, float], str]:
    """HsCalc's Mu for the input *content* by row id, and the engine's version."""
    try:
        with tempfile.TemporaryDirectory(prefix="webpier-pilejoint-") as work:
            source, output = Path(work) / "pile-joint.json", Path(work) / "output"
            source.write_bytes(content)
            try:
                done = subprocess.run([str(runner), "run-pile-joint", "--input", str(source), "--output-dir", str(output)],
                                      capture_output=True, timeout=timeout, check=False)
            except subprocess.TimeoutExpired as exc:
                raise _Failure(f"{timeout} 秒で終わりませんでした") from exc
            except OSError as exc:
                raise _Failure(f"runner を起動できません（{exc}）") from exc
            envelope = _envelope(done.stdout)
            if done.returncode or envelope.get("ok") is not True or envelope.get("executionStatus") != "success":
                errors = "; ".join(f"{message.get('code')}: {message.get('text')}" for message in envelope.get("messages") or ()
                                   if isinstance(message, dict) and message.get("level") == "error") \
                    or f"終了コード {done.returncode}"
                raise _Failure(errors)
            version, artifacts = envelope.get("engineVersion"), envelope.get("artifacts")
            if not isinstance(version, str) or not version:
                raise _Failure("runner の版（engineVersion）がありません")
            if (not isinstance(artifacts, list) or len(artifacts) != 1 or not isinstance(artifacts[0], dict)
                    or (artifacts[0].get("kind"), artifacts[0].get("relativePath")) != _RESULT):
                raise _Failure(f"runner の成果物が計算結果の1つではありません（{artifacts!r}）")
            path = output / _RESULT[1]
            if not path.is_file():
                raise _Failure("runner の成果物 result.json がありません")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != artifacts[0].get("sha256") or len(data) != artifacts[0].get("bytes"):
                raise _Failure("result.json が runner の応答の SHA256・バイト数と一致しません")
        try:
            result = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _Failure(f"計算結果が JSON ではありません（{exc}）") from exc
        return _moments(result, ids), version
    except _Failure as exc:
        raise RunnerError(f"pile-joint.json {_WHAT}: {exc}") from exc
