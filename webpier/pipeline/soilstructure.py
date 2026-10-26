"""The SoilStructure runner: the 地盤変位 of a pile foundation on G3〜G5 (decision 97, CONTEXT.md 地盤変位).

0710 and 0720 of such a foundation give SoilStructure's Headless runner (``SoilStructure.Headless.exe
run-ground-displacement``) the layers above the base, cut at the depths of the pile nodes (calc.ground_displacement), and
read the natural period Tg of the surface ground and the design horizontal displacement f(z) at each depth from the
result it returns (``result.json``). Its report (a PDF dated when it is made) and its JRSNAP files (JOT) are not asked
for: WebPier prints the values itself and puts the displacement into the NDU (decision 97). The document is the runner's
``schemaVersion`` 1 with the pile items it requires and does not use left at zero.

The runner is the absolute path in ``STRUCTURAL_MCP_SOILSTRUCTURE_RUNNER``: the process environment first, then the ``.env``
file at the repository root (not tracked). Without a runner, or when it fails, a generation that needs it stops; nothing is
published.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from ..calc.ground_displacement import STANDARD_COEFFICIENT, RunnerRow
from .fempython import ENV_FILE, RunnerError, read_env

RUNNER_KEY = "STRUCTURAL_MCP_SOILSTRUCTURE_RUNNER"
PROTOCOL_VERSION = 1
ENGINE = "soilstructure"
TIMEOUT = 600  # seconds
_RESULT = ("result", "result.json")
_FAILED = "地盤変位を算定できません"
# what the runner requires besides the ground displacement, which it does not use for it
_PILE = {"pileType": 6, "constructionMethod": "naturalSlurry",
         "pile": {"diameterM": 0, "lengthM": 0, "embedmentDepthM": 0, "groundwaterDepthM": 0, "unitWeight": 0,
                  "stiffness": 0, "bladeOuterDiameterM": 0, "bladeInnerDiameterM": 0},
         "pileGroup": {"longitudinal": {"lmM": 0, "lnM": 0, "m": 0, "n": 0},
                       "transverse": {"lmM": 0, "lnM": 0, "m": 0, "n": 0}},
         "soilRows": []}
# the JOT the runner is not asked to write still needs these
_JOT = {"jotEquivalentPeriodSeconds": 1, "jotVersion": "Ver.5.1.2", "l2Spectrum": 2}


class _Failure(Exception):
    pass


@dataclass(frozen=True)
class GroundAnswer:
    """What the runner returned: Tg (s) and its points, with the document given and the result as returned."""

    period: float
    points: tuple[Mapping[str, Any], ...]
    document: bytes
    result: bytes
    engine_version: str


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
        raise RunnerError(f"地盤変位の算定に使う SoilStructure の runner が設定されていません。" + (
            f"リポジトリのルートの .env に {RUNNER_KEY}='<SoilStructure.Headless.exe の絶対パス>' を書いてください" if dotenv
            else f"環境変数 {RUNNER_KEY} に SoilStructure.Headless.exe の絶対パスを設定してください"))
    path = Path(value)
    if not path.is_absolute():
        raise RunnerError(f"{where} は絶対パスにしてください: {value}")
    if not path.is_file():
        raise RunnerError(f"{where} の runner がありません: {value}")
    return path


def document(rows: Sequence[RunnerRow], region_coefficient: Any) -> bytes:
    """The runner's input for the ground displacement of *rows* in a region of *region_coefficient*."""
    ground = {"standardDesignSeismicCoefficient": float(STANDARD_COEFFICIENT),
              "regionalCoefficient": float(region_coefficient), **_JOT, "includeL1": True, "includeL2": True,
              "rows": [{"layerNumber": row.layer, "thicknessM": f"{row.thickness:.3f}",
                        "unitWeightKnPerM3": None if row.unit_weight is None else str(row.unit_weight),
                        "shearWaveVelocityMPerSecond": None if row.velocity is None else str(row.velocity)}
                       for row in rows]}
    content = {"schemaVersion": 1, **_PILE, "groundDisplacement": ground}
    return json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")


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


def _answer(result: bytes) -> tuple[float, tuple[Mapping[str, Any], ...]]:
    try:
        content = json.loads(result.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _Failure(f"result.json が JSON ではありません（{exc}）") from exc
    period = content.get("groundNaturalPeriodSeconds") if isinstance(content, dict) else None
    points = content.get("points") if isinstance(content, dict) else None
    keys = ("depthM", "l1DisplacementMm", "l2SpectrumTwoDisplacementMm")
    if (not isinstance(period, (int, float)) or isinstance(period, bool) or not isinstance(points, list)
            or not all(isinstance(point, dict) and all(isinstance(point.get(key), (int, float))
                                                       and not isinstance(point.get(key), bool) for key in keys)
                       for point in points)):
        raise _Failure("result.json に固有周期（groundNaturalPeriodSeconds）と各点の地盤変位（points）がありません")
    return float(period), tuple(points)


def calculate(rows: Sequence[RunnerRow], region_coefficient: Any, runner: Path, *,
              timeout: float = TIMEOUT) -> GroundAnswer:
    """SoilStructure's answer for the ground displacement of *rows*."""
    given = document(rows, region_coefficient)
    try:
        with tempfile.TemporaryDirectory(prefix="webpier-soilstructure-") as work:
            source, output = Path(work) / "ground.json", Path(work) / "output"
            source.write_bytes(given)
            arguments = [str(runner), "run-ground-displacement", "--input", str(source), "--output-dir", str(output),
                         "--generate-pdf", "false", "--generate-jot", "false"]
            try:
                done = subprocess.run(arguments, capture_output=True, timeout=timeout, check=False)
            except subprocess.TimeoutExpired as exc:
                raise _Failure(f"{timeout} 秒で終わりませんでした") from exc
            except OSError as exc:
                raise _Failure(f"runner を起動できません（{exc}）") from exc
            envelope = _envelope(done.stdout)
            if done.returncode or envelope.get("ok") is not True or envelope.get("executionStatus") != "success":
                errors = "; ".join(f"{error.get('code')}: {error.get('message')}"
                                   for error in envelope.get("errors") or () if isinstance(error, dict)
                                   ) or f"終了コード {done.returncode}"
                raise _Failure(errors)
            version, artifacts = envelope.get("engineVersion"), envelope.get("artifacts")
            if not isinstance(version, str) or not version:
                raise _Failure("runner の版（engineVersion）がありません")
            if (not isinstance(artifacts, list) or len(artifacts) != 1 or not isinstance(artifacts[0], dict)
                    or (artifacts[0].get("kind"), artifacts[0].get("relativePath")) != _RESULT):
                raise _Failure(f"runner の成果物が結果（result.json）の1つではありません（{artifacts!r}）")
            path = output / _RESULT[1]
            if not path.is_file():
                raise _Failure("runner の成果物 result.json がありません")
            result = path.read_bytes()
            if hashlib.sha256(result).hexdigest() != artifacts[0].get("sha256") or len(result) != artifacts[0].get("bytes"):
                raise _Failure("result.json が runner の応答の SHA256・バイト数と一致しません")
            if sorted(item.name for item in output.iterdir()) != [_RESULT[1]]:
                raise _Failure("runner の出力先のファイルが成果物の一覧と一致しません")
        period, points = _answer(result)
    except _Failure as exc:
        raise RunnerError(f"SoilStructure で{_FAILED}: {exc}") from exc
    return GroundAnswer(period, points, given, result, version)


__all__ = ["ENGINE", "GroundAnswer", "RUNNER_KEY", "calculate", "document", "runner_path"]
