"""The SteelDan runner: the pile body of a steel pipe pile in 0612 and 0622 (decision 89).

The WSJ a generation builds (export.steeldan) is given, as it is, to ``WebDanforCS.Headless.exe run-steel`` (the Capacita
runner of ``pipeline.capacita``: the same executable and ``STRUCTURAL_MCP_WEBDAN_RUNNER``). The runner returns the result
(``result.json``) alone: SteelDan makes no report for the pile body, so the report is WebPier's and the numbers are SteelDan's
(``verifications``: for each point and design force case, the three checks with their values rounded to the digits the sample
prints). The result is read by (row, case, kind); a check that is missing, or a row or a case that is not asked for, is an
error. The engine's version is recorded in the result of the stage.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any

from ..calc.pile_body import Case
from .fempython import RunnerError
from .runner_protocol import RunFailure as _Failure, reasons, run

ENGINE = "steeldan"
TIMEOUT = 600  # seconds
KINDS = {"pipePileBending": "bending", "pipePileShear": "shear", "pipePileCombined": "combined"}
_RESULT = ("result", "result.json")
_WHAT = "で鋼管杭の杭体の照査ができません"


def _values(result: Any, rows: set[int]) -> dict[tuple[int, int, str], dict[str, float]]:
    """The values of each check by (row, case number, kind): exactly the three checks of every case of every row."""
    listed = result.get("verifications") if isinstance(result, dict) else None
    if not isinstance(listed, list):
        raise _Failure("計算結果に verifications がありません")
    found: dict[tuple[int, int, str], dict[str, float]] = {}
    for item in listed:
        values = item.get("values") if isinstance(item, dict) else None
        kind = KINDS.get(item.get("kind")) if isinstance(item, dict) else None
        if kind is None or not isinstance(values, dict) or type(item.get("pointIndex")) is not int:
            raise _Failure(f"計算結果の照査が読めません（{item!r}）")
        key = (item["pointIndex"], int(values.get("case", 0)), kind)
        if key in found:
            raise _Failure(f"計算結果の照査が重複しています（杭列 {key[0]}、ケース {key[1]}、{kind}）")
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values.values()):
            raise _Failure(f"計算結果の値が数値ではありません（{item!r}）")
        found[key] = {name: float(value) for name, value in values.items()}
    wanted = {(row, case.value, kind) for row in rows for case in Case for kind in KINDS.values()}
    if set(found) != wanted:
        raise _Failure(f"計算結果の照査が杭列とケースの組に合いません（足りない {sorted(wanted - set(found))!r}、"
                       f"余分 {sorted(set(found) - wanted)!r}）")
    return found


def check_pile(wsj: bytes, rows: set[int], runner: Path, *, timeout: float = TIMEOUT
               ) -> tuple[dict[tuple[int, int, str], dict[str, float]], str]:
    """SteelDan's values for the WSJ *wsj* of the pile *rows*, and the engine's version."""
    try:
        with tempfile.TemporaryDirectory(prefix="webpier-steeldan-") as work:
            source, output = Path(work) / "pile.wsj", Path(work) / "output"
            source.write_bytes(wsj)
            _, version, files = run([str(runner), "run-steel", "--input", str(source), "--output-dir", str(output)],
                                    output, ENGINE, {_RESULT}, "計算結果の1つ", timeout, listing=None,
                                    reasons_of=lambda found, code: reasons(found, code, errors=False, levels=("error",)))
            content = files[_RESULT[1]]
        try:
            result = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _Failure(f"計算結果が JSON ではありません（{exc}）") from exc
        return _values(result, rows), version
    except _Failure as exc:
        raise RunnerError(f"pile.wsj {_WHAT}: {exc}") from exc
