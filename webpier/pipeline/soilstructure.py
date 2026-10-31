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
import json
from pathlib import Path
import tempfile
from typing import Any

from ..calc.ground_displacement import STANDARD_COEFFICIENT, RunnerRow
from .fempython import ENV_FILE, RunnerError, find_runner
from .runner_protocol import RunFailure as _Failure, run

RUNNER_KEY = "STRUCTURAL_MCP_SOILSTRUCTURE_RUNNER"
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
    return find_runner(RUNNER_KEY, "地盤変位の算定に使う SoilStructure ", "SoilStructure.Headless.exe", environ, ENV_FILE if env_file is None else env_file,
                       dotenv=dotenv)


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
            _, version, files = run(arguments, output, ENGINE, {_RESULT}, "結果（result.json）の1つ", timeout,
                                    listing="bare")
            result = files[_RESULT[1]]
        period, points = _answer(result)
    except _Failure as exc:
        raise RunnerError(f"SoilStructure で{_FAILED}: {exc}") from exc
    return GroundAnswer(period, points, given, result, version)


__all__ = ["ENGINE", "GroundAnswer", "RUNNER_KEY", "calculate", "document", "runner_path"]
