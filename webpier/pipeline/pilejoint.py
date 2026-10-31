"""The Capacita runner of the joint of a steel pipe pile with the footing in 0612 and 0622 (decision 90).

The JSON a generation builds (``export.capacita.pile_joint``) is given, as it is, to ``WebDanforCS.Headless.exe
run-pile-joint`` (the runner of ``pipeline.capacita``, ``STRUCTURAL_MCP_WEBDAN_RUNNER``). The runner returns ``result.json`` alone:
HsCalc's design bending resistance (``rows[].mu``, kN m) of every row asked for, by the id of the row. A row that is missing,
duplicated or not asked for is an error. The engine's version is recorded in the result of the stage.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any

from .fempython import RunnerError
from .runner_protocol import RunFailure as _Failure, reasons, run

ENGINE = "webdan2"
TIMEOUT = 600  # seconds
_RESULT = ("result", "result.json")
_WHAT = "で鋼管杭の結合部の照査ができません"


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
            _, version, files = run([str(runner), "run-pile-joint", "--input", str(source), "--output-dir", str(output)],
                                    output, ENGINE, {_RESULT}, "計算結果の1つ", timeout, listing=None,
                                    reasons_of=lambda found, code: reasons(found, code, errors=False, levels=("error",)))
            data = files[_RESULT[1]]
        try:
            result = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _Failure(f"計算結果が JSON ではありません（{exc}）") from exc
        return _moments(result, ids), version
    except _Failure as exc:
        raise RunnerError(f"pile-joint.json {_WHAT}: {exc}") from exc
