"""A stand-in for ``SoilStructure.Headless.exe run-ground-displacement``: the 地盤変位 of 0710 and 0720 (decision 97).

It follows the runner's protocol as WebPier uses it (structural-mcp SoilStructure/README.md, SoilStructure.Headless): the
arguments of ``webpier.pipeline.soilstructure.calculate`` (``run-ground-displacement --input <json> --output-dir <dir>
--generate-pdf false --generate-jot false``; anything else is INVALID_ARGUMENT), an output directory that must be absent
or empty, and one UTF-8 JSON envelope (protocolVersion 1, engine soilstructure, engineeringStatus not_evaluated) on stdout.
Instead of the transfer matrix of SoilDisp it writes ``result.json`` with numbers anyone can recalculate:

- Tg = 4 Σ H/Vs of the rows (a row with blank γ and Vs takes the row above's), the quarter wave of the layers;
- at the surface (``表層``, depth 0) and at the bottom of each row: f(z) = a cos(πz / 2H), H the depth of the base, with
  a = 0.064 Tg^2.1 × 1000 HK for L1, 0.320 Tg × 1000 HK^0.9 and 0.413 Tg × 1000 HK^0.9 for L2 (mm, HK the 標準設計震度
  × the 地域別係数), the real runner's surface displacements;
- ``input`` with the rows as given.

When the real runner's protocol changes, change this too. ``FAKE_SOILSTRUCTURE`` makes it misbehave, for the error tests:
fail, exit, text, protocol, version (no engineVersion), artifacts (two artifacts), missing (result.json not written), sha
(its SHA256 wrong), extra (a file not listed), result (result.json without points), notjson (result.json is not JSON).
"""

import hashlib
import json
import math
import os
from pathlib import Path
import sys

EXPECTED = ["--generate-pdf", "false", "--generate-jot", "false"]


def envelope(ok, artifacts=(), errors=(), **changes):
    value = {"protocolVersion": 1, "engine": "soilstructure", "engineVersion": "1.3.0", "readiness": "production",
             "ok": ok, "executionStatus": "success" if ok else "failed",
             "engineeringStatus": "not_evaluated" if ok else "not_applicable",
             "summary": {"operation": "ground-displacement"} if ok else None, "messages": [],
             "artifacts": list(artifacts), "errors": list(errors)}
    return {**value, **changes}


def failure(code, message, exit_code):
    print(json.dumps(envelope(False, errors=[{"category": "input", "code": code, "message": message}]),
                     ensure_ascii=False))
    return exit_code


def answer(ground):
    rows, gamma, velocity, depth, period = [], None, None, 0.0, 0.0
    for row in ground["rows"]:
        gamma = row["unitWeightKnPerM3"] or gamma
        velocity = row["shearWaveVelocityMPerSecond"] or velocity
        thickness = float(row["thicknessM"])
        period += 4 * thickness / float(velocity)
        depth += thickness
        rows.append((row, depth))
    hk = ground["standardDesignSeismicCoefficient"] * ground["regionalCoefficient"]
    surface = (0.064 * period ** 2.1 * 1000 * hk, 0.320 * period * 1000 * hk ** 0.9, 0.413 * period * 1000 * hk ** 0.9)

    def point(name, row, at):
        shape = math.cos(math.pi * at / (2 * depth))
        return {"layerNumber": name, "thicknessM": None if row is None else float(row["thicknessM"]), "depthM": at,
                "unitWeightKnPerM3": None, "shearWaveVelocityMPerSecond": None,
                "l1DisplacementMm": surface[0] * shape, "l2SpectrumOneDisplacementMm": surface[1] * shape,
                "l2SpectrumTwoDisplacementMm": surface[2] * shape}

    points = [point("表層", None, 0)] + [point(row["layerNumber"], row, at) for row, at in rows]
    return {"input": {"rows": ground["rows"]}, "groundNaturalPeriodSeconds": period, "points": points}


def main(argv):
    mode = os.environ.get("FAKE_SOILSTRUCTURE", "")
    if (len(argv) != 9 or argv[0] != "run-ground-displacement" or argv[1] != "--input" or argv[3] != "--output-dir"
            or argv[5:] != EXPECTED):
        return failure("INVALID_ARGUMENT", f"unexpected arguments: {argv}", 2)
    output = Path(argv[4])
    if output.exists() and any(output.iterdir()):
        return failure("OUTPUT_NOT_EMPTY", "output folder is not empty", 5)
    if mode == "fail":
        return failure("invalid_document", "FAKE refused the document", 3)
    if mode == "text":
        print("not json")
        return 0
    document = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    result = json.dumps(answer(document["groundDisplacement"]), ensure_ascii=False, indent=2).encode("utf-8")
    if mode == "result":
        result = json.dumps({"groundNaturalPeriodSeconds": 0.5}).encode("utf-8")
    elif mode == "notjson":
        result = b"not json"
    if mode != "missing":
        (output / "result.json").write_bytes(result)
    if mode == "extra":
        (output / "report.pdf").write_bytes(b"%PDF")
    digest = hashlib.sha256(result).hexdigest()
    artifacts = [{"kind": "result", "mediaType": "application/json; charset=utf-8", "relativePath": "result.json",
                  "bytes": len(result), "sha256": "0" * 64 if mode == "sha" else digest}]
    if mode == "artifacts":
        artifacts.append(dict(artifacts[0], kind="report", relativePath="report.pdf"))
    changes = {}
    if mode == "protocol":
        changes["protocolVersion"] = 2
    elif mode == "version":
        changes["engineVersion"] = ""
    print(json.dumps(envelope(True, artifacts, **changes), ensure_ascii=False))
    return 4 if mode == "exit" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
