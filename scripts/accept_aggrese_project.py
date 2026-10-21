"""Real-app acceptance of the 0711 / 0721 Aggre-SE projects (decision 49, CONTEXT.md 耐震照査の入力).

For each direction, ``python -m webpier`` is generated from the input choosing 0711 (0721) and the items it uses
(decision 72) into a temporary folder with the real JRSNAP runner (``STRUCTURAL_MCP_JRSNAP_RUNNER``, as a normal
generation finds it). A copy of the XML and its JRSNAP folder is then

1. read and calculated by the Aggre-SE runner of structural-mcp ``Batch`` (``AggreSE.Headless.exe inspect`` and
   ``run`` with the summary and the report), with the DB1 of each Case mapped as the XML names them; and
2. read and saved again as Aggre-SE itself does (``aggrese_project_roundtrip.cs``: ``Input.SetXmData`` →
   ``applyVersion`` → ``Input.GetXmlData`` → Shift-JIS), which must give the same bytes.

The evidence (the candidate XMLs and record.json with the input, candidate, application and implementation
identities) goes to tests/fixtures/acceptance/aggrese; tests/acceptance checks that it still belongs to the current
generator. Aggre-SE's own results (the report, OK / NG) are not judged here: that is a seismic check, not an
acceptance of the file.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.core.integrity import canonical_sha256, content_sha256, dump_json, file_sha256, load_json  # noqa: E402
from webpier.inputs.outputs import OUTPUT_KEYS, uses  # noqa: E402
from webpier.pipeline.generate import GenerationOptions, generate  # noqa: E402
from webpier.pipeline.runtime import dependency_hashes  # noqa: E402
from webpier.pipeline.stages import STAGES  # noqa: E402

DEFAULT_INPUT = PROJECT / "tests" / "fixtures" / "inputs" / "current.json"
DEFAULT_EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "aggrese"
DEFAULT_BATCH = PROJECT.parent / "Batch" / "Aggre-SE" / "Headless" / "bin" / "Release"
HELPER = PROJECT / "scripts" / "aggrese_project_roundtrip.cs"
COMPILER = Path("C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe")
BATCH_VERSION = "5.3.0.1"
STAGES_ACCEPTED = ("0711", "0721")
RUN = ["--summary-xlsx", "true", "--report-pdf", "true", "--check-tables", "false", "--pik", "false",
       "--pile-anchor-bar-pdf", "false"]


class AcceptanceError(RuntimeError):
    """The acceptance did not complete; no evidence is written."""


def _relative(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


def _literal(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def file_version(path: Path) -> str:
    command = (f"$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "
               f"(Get-Item -LiteralPath {_literal(path)}).VersionInfo.FileVersion")
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                          capture_output=True, timeout=60, check=False)
    if done.returncode:
        raise AcceptanceError(f"版を読めません: {path}")
    return done.stdout.decode("utf-8-sig").strip()


def application(batch: Path) -> dict[str, Any]:
    """Batch.exe (Aggre-SE) and its runner, checked against the version the writer follows."""
    exe, runner = batch / "Batch.exe", batch / "AggreSE.Headless.exe"
    version = file_version(exe)
    if version != BATCH_VERSION:
        raise AcceptanceError(f"Aggre-SE（Batch.exe）が {BATCH_VERSION} ではありません: {version}")
    return {"batch": {"path": str(exe), "file_version": version, "sha256": file_sha256(exe)},
            "runner": {"path": str(runner), "sha256": file_sha256(runner)}}


def databases(project: Path) -> dict[str, str]:
    """{Case index: absolute DB1} as the XML names them (relative to the XML)."""
    root = ET.fromstring(project.read_bytes().decode("cp932").replace('encoding="utf-16"', ""))
    paths = [item.text for item in root.find("SNAP/SnapDBPath")]
    return {str(index): str((project.parent / path).resolve()) for index, path in enumerate(paths) if path}


def run_aggrese(runner: Path, project: Path, snap_map: Path, work: Path, command: str,
                extra: list[str], timeout: int) -> dict[str, Any]:
    output = work / f"out-{command}"
    done = subprocess.run([str(runner), command, "--input", str(project), "--output-dir", str(output),
                           "--snap-map", str(snap_map), *extra], capture_output=True, timeout=timeout, check=False)
    try:
        envelope = json.loads(done.stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"Aggre-SE の runner の応答が JSON ではありません（{command}）: {exc}") from exc
    if done.returncode or envelope.get("ok") is not True or envelope.get("executionStatus") != "success":
        raise AcceptanceError(f"Aggre-SE が {project.name} を{command}できません: {envelope.get('errors')}")
    return envelope


def build_helper(directory: Path) -> Path:
    helper = directory / "AggreSeProjectRoundtrip.exe"
    done = subprocess.run([str(COMPILER), "/nologo", "/platform:x86", f"/out:{helper}", str(HELPER)],
                          capture_output=True, check=False)
    if done.returncode:
        raise AcceptanceError(f"保存し直しの補助を作れません: {done.stdout.decode('cp932', 'replace')}")
    return helper


def roundtrip(helper: Path, batch: Path, project: Path, timeout: int) -> bytes:
    saved = project.with_name("saved-" + project.name)
    done = subprocess.run([str(helper), str(batch), str(project), str(saved)], capture_output=True, timeout=timeout,
                          check=False)
    if done.returncode:
        raise AcceptanceError(f"Aggre-SE が保存し直せません: {done.stderr.decode('cp932', 'replace')}")
    report = json.loads(done.stdout.decode("utf-8-sig"))
    if report.get("version") != BATCH_VERSION:
        raise AcceptanceError(f"保存し直した Version が違います: {report}")
    return saved.read_bytes()


def choosing(input_path: Path, stage: str, work: Path) -> Path:
    """A copy of the input at *input_path* choosing the 出力項目 of *stage* and every item it uses (decision 72)."""
    data = load_json(input_path.read_bytes())
    item = STAGES.item(stage)
    data["outputs"] = {key: key == item or key in uses(item) for key in OUTPUT_KEYS}
    path = work / f"{stage}-input.json"
    path.write_bytes(dump_json(data))
    return path


def accept(input_path: Path, evidence: Path, batch: Path, timeout: int, overwrite: bool) -> dict[str, Any]:
    if evidence.exists() and not overwrite:
        raise AcceptanceError(f"受入記録が既にあります（--overwrite で作り直します）: {evidence}")
    implementation = canonical_sha256({str(path): digest for path, digest in dependency_hashes().items()})
    app = application(batch)
    runner = Path(app["runner"]["path"])
    helpers = {_relative(path): file_sha256(path) for path in (HELPER, Path(__file__))}
    candidates: dict[str, bytes] = {}
    directions: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="webpier-aggrese-acceptance-") as temporary:
        work = Path(temporary)
        helper = build_helper(work)
        for stage in STAGES_ACCEPTED:
            analysis = STAGES.get(stage).nonlinear_analysis
            generated = work / stage
            generate(GenerationOptions(choosing(input_path, stage, work), generated / "output", generated / "post"))
            post = generated / "post"
            project, folder = post / analysis.project.file_name, post / analysis.folder
            sidecar = load_json((post / (analysis.folder + ".provenance.json")).read_bytes())
            copy = work / f"{stage}-copy"
            copy.mkdir()
            shutil.copytree(folder, copy / analysis.folder)
            shutil.copyfile(project, copy / project.name)
            candidate = project.read_bytes()
            snap_map = work / f"{stage}-snap-map.json"
            mapped = databases(copy / project.name)
            snap_map.write_text(json.dumps(mapped, ensure_ascii=False), encoding="utf-8")
            inspected = run_aggrese(runner, copy / project.name, snap_map, work / stage, "inspect", [], timeout)
            calculated = run_aggrese(runner, copy / project.name, snap_map, work / stage, "run", RUN, timeout)
            cases = calculated["summary"]["cases"]
            if len(cases) != len(mapped) or not all(case.get("aggregated") for case in cases):
                raise AcceptanceError(f"{project.name}: 全 Case が集計されていません: {cases}")
            saved = roundtrip(helper, batch, copy / project.name, timeout)
            if saved != candidate:
                raise AcceptanceError(f"{project.name}: Aggre-SE が保存し直すと書式が変わります")
            candidates[project.name] = candidate
            directions[stage] = {
                "candidate": {"path": project.name, "sha256": file_sha256(project)},
                "databases": sorted(Path(path).name for path in mapped.values()),
                "jrsnap": {"folder": analysis.folder, "sha256": content_sha256(folder),
                           "runner_engine_version": sidecar["nonlinear_analysis"]["engine_version"],
                           "product": sidecar["nonlinear_analysis"]["runner_summary"]["jrsnap"]["product"]},
                "inspect": {"engine_version": inspected["engineVersion"], "cases": inspected["summary"]["cases"]},
                "run": {"engine_version": calculated["engineVersion"], "cases": cases,
                        "outputs": calculated["summary"]["outputs"], "warnings": calculated["summary"]["warnings"],
                        "messages": calculated["messages"], "engineering_status": calculated["engineeringStatus"]},
                "roundtrip_identical": True,
            }
    record = {
        "schema_version": 1, "kind": "aggrese_project_acceptance",
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": ("本物の JRSNAP の runner で 0711・0721 を生成し、XML と JRSNAP のフォルダーの複製を Aggre-SE の runner "
                   "（AggreSE.Headless.exe inspect / run、総括表と計算書）で読込み・計算した。さらに Aggre-SE の "
                   "Input.SetXmData → applyVersion → Input.GetXmlData → Shift-JIS の保存し直し"
                   "（scripts/aggrese_project_roundtrip.cs）でバイト列が変わらないことを確かめた。Aggre-SE の照査の"
                   "判定は扱わない。"),
        "seismic_check_judged": False, "gui_operated": False,
        "input": {"path": _relative(input_path), "sha256": file_sha256(input_path)},
        "implementation_sha256": implementation, "application": app, "helpers": helpers, "directions": directions,
    }
    if evidence.exists():
        shutil.rmtree(evidence)
    evidence.mkdir(parents=True)
    for name, content in candidates.items():
        (evidence / name).write_bytes(content)
    (evidence / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                                          newline="\n")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH, help="AggreSE.Headless.exe と Batch.exe のフォルダー")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        record = accept(args.input.resolve(), args.evidence.resolve(), args.batch.resolve(), args.timeout,
                        args.overwrite)
    except AcceptanceError as exc:
        print(f"受入できません: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({stage: {"candidate": value["candidate"], "databases": value["databases"],
                              "outputs": value["run"]["outputs"]} for stage, value in record["directions"].items()},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
