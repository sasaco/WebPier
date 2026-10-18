"""Real-app acceptance of the 0710 / 0720 NDUs in JRSNAP 5.2-L03 (CONTEXT.md NDUの受入記録, decisions 4 and 40).

For each direction the NDU is rebuilt from the input exactly as ``python -m webpier`` writes it
(``export_bytes``). A copy is read and saved twice by the installed JRSNAP_Input.exe (the skill
jrsnap-input-open-save, ``save-ndu.ps1``: JRSNAP's own mdl_Get_NDUDataFile / mdl_Wrt_NDUDataFile, without the
screen), and read once more by ``jrsnap_state_probe.cs``, which reports what JRSNAP holds (counts, combinations).
The saved file and the state are compared with what we wrote (``webpier.export.jrsnap.readback``).

The evidence (the candidate, JRSNAP's saved copy and record.json with the input, candidate, application and
implementation identities) goes to tests/fixtures/acceptance/jrsnap_v52; tests/acceptance checks that it still
belongs to the current generator. No analysis is run: reading and saving an NDU is not a structural analysis.
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

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.core.integrity import canonical_sha256, dump_json, file_sha256, load_json, sha256  # noqa: E402
from webpier.export.jrsnap.readback import (  # noqa: E402
    ReadbackError, compare_readback, compare_state, parse_records, summarize,
)
from webpier.inputs import parse_input  # noqa: E402
from webpier.pipeline.generate import export_bytes  # noqa: E402
from webpier.pipeline.runtime import dependency_hashes  # noqa: E402
from webpier.pipeline.stages import STAGES  # noqa: E402

DEFAULT_INPUT = PROJECT / "tests" / "fixtures" / "inputs" / "current.json"
DEFAULT_EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "jrsnap_v52"
DEFAULT_APP = Path("C:/RTRI_Program/JRSNAP(Ver5.2-L03)/JRSNAP_Input.exe")
HELPER = PROJECT / ".claude" / "skills" / "jrsnap-input-open-save" / "scripts" / "save-ndu.ps1"
PROBE = PROJECT / "scripts" / "jrsnap_state_probe.cs"
COMPILER = Path("C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe")
VERSION = {"file_version": "5.2.3.0", "product_version": "5.2.3.0", "assembly_version": "5.2.3.1"}
DIRECTIONS = {"0710": "longitudinal", "0720": "transverse"}
RUNTIME_CONFIG = ('<?xml version="1.0" encoding="utf-8"?><configuration><runtime><loadFromRemoteSources '
                  'enabled="true"/></runtime><startup><supportedRuntime version="v4.0" '
                  'sku=".NETFramework,Version=v4.7.2"/></startup></configuration>')


class AcceptanceError(RuntimeError):
    """The acceptance did not complete; no evidence is written."""


def _relative(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


def _literal(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _powershell_json(command: str, timeout: int) -> Any:
    prefix = ("$ErrorActionPreference='Stop'; "
              "$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); ")
    encoded = base64.b64encode((prefix + command).encode("utf-16le")).decode("ascii")
    done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                          capture_output=True, timeout=timeout, check=False)
    if done.returncode:
        raise AcceptanceError(f"PowerShell exit {done.returncode}: {done.stderr.decode('utf-8', 'replace').strip()}")
    return json.loads(done.stdout.decode("utf-8-sig"))


def app_identity(executable: Path) -> dict[str, str]:
    """The installed build, checked against 5.2-L03 (not trusted from an NDU header)."""
    command = ("$p=" + _literal(executable) + "; $f=Get-Item -LiteralPath $p; [ordered]@{"
               "file_version=$f.VersionInfo.FileVersion; product_version=$f.VersionInfo.ProductVersion; "
               "assembly_version=[Reflection.AssemblyName]::GetAssemblyName($p).Version.ToString()} "
               "| ConvertTo-Json -Compress")
    identity = _powershell_json(command, 60)
    if any(identity.get(key) != value for key, value in VERSION.items()):
        raise AcceptanceError(f"JRSNAP 5.2-L03 ではありません: {identity}")
    return {"name": "JRSNAP_Input.exe 5.2-L03", **identity, "path": str(executable), "sha256": file_sha256(executable)}


def read_and_save(candidate: Path, timeout: int) -> tuple[bytes, bytes, dict[str, Any]]:
    """JRSNAP's first and second save of a copy of *candidate* (the helper's dry run never touches it)."""
    command = (f"& {_literal(HELPER)} -Path {_literal(candidate)} -Version V52 -TimeoutSeconds {timeout} "
               "| ConvertTo-Json -Compress")
    report = _powershell_json(command, 4 * timeout + 60)
    if report.get("Written") is not False or str(report.get("BeforeHash", "")).lower() != file_sha256(candidate):
        raise AcceptanceError(f"保存の補助が複製を検査していません: {report}")
    stage = Path(report["Stage"])
    first, second = ((stage / f"case1.{name}.ndu").read_bytes() for name in ("saved", "second"))
    shutil.rmtree(stage, ignore_errors=True)
    if first != second:
        raise AcceptanceError(f"{candidate.name}: 2回目の保存が1回目と異なります")
    return first, second, report


def build_probe(directory: Path) -> Path:
    probe = directory / "StateProbe.exe"
    done = subprocess.run([str(COMPILER), "/nologo", "/platform:x86", "/reference:System.Windows.Forms.dll",
                           f"/out:{probe}", str(PROBE)], capture_output=True, check=False)
    if done.returncode:
        raise AcceptanceError(f"状態の読取りを作れません: {done.stdout.decode('cp932', 'replace')}")
    probe.with_name(probe.name + ".config").write_text(RUNTIME_CONFIG, encoding="utf-8")
    return probe


def read_state(probe: Path, app: Path, candidate: Path, timeout: int) -> dict[str, Any]:
    copy = candidate.with_name("probe-" + candidate.name)
    shutil.copyfile(candidate, copy)
    done = subprocess.run([str(probe), str(app), str(copy)], capture_output=True, timeout=timeout, check=False)
    if done.returncode:
        raise AcceptanceError(f"JRSNAP が読めません: {done.stderr.decode('cp932', 'replace')}")
    return json.loads(done.stdout.decode("utf-8-sig"))


def accept(input_path: Path, evidence: Path, app: Path, timeout: int, overwrite: bool) -> dict[str, Any]:
    if evidence.exists() and not overwrite:
        raise AcceptanceError(f"受入記録が既にあります（--overwrite で作り直します）: {evidence}")
    data = input_path.read_bytes()
    pier = parse_input(load_json(data))
    implementation = canonical_sha256({str(path): digest for path, digest in dependency_hashes().items()})
    application = app_identity(app)
    helpers = {_relative(path): file_sha256(path) for path in (HELPER, HELPER.with_name("roundtrip.cs"), PROBE,
                                                                Path(__file__))}
    files: dict[str, bytes] = {}
    directions: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="webpier-jrsnap-acceptance-") as temporary:
        work = Path(temporary)
        probe = build_probe(work)
        for stage, name in DIRECTIONS.items():
            candidate = export_bytes(pier, stage, "jrsnap")
            path = work / f"{name}.candidate.ndu"
            path.write_bytes(candidate)
            first, _, report = read_and_save(path, timeout)
            readback = compare_readback(candidate, first)
            written = parse_records(candidate)
            summary = summarize(parse_records(first))
            if summarize(written) != summary:
                raise AcceptanceError(f"{stage}: 保存した件数・組合せが書いたものと異なります")
            state = read_state(probe, app, path, timeout)
            compare_state(written, state)
            files[f"{name}.candidate.ndu"], files[f"{name}.saved.ndu"] = candidate, first
            export = next(item for item in STAGES.get(stage).exports if item.kind == "jrsnap")
            directions[stage] = {
                "direction": name, "file": export.file_name,
                "candidate": {"path": f"{name}.candidate.ndu", "sha256": sha256(candidate),
                              "records": readback.records},
                "saved": {"path": f"{name}.saved.ndu", "sha256": sha256(first),
                          "header": first.split(b"\r\n", 1)[0].decode("ascii")},
                "read_code": state["read_code"], "write_code": 0, "second_save_identical": True,
                "normalized": [vars(item) for item in readback.normalized],
                "counts": summary["counts"], "combinations": summary["combinations"], "jrsnap_state": state,
                "helper_body_changed_lines": report["BodyChangedLines"],
            }
    if (sha256(input_path.read_bytes()) != sha256(data) or app_identity(app) != application
            or canonical_sha256({str(path): digest for path, digest in dependency_hashes().items()}) != implementation):
        raise AcceptanceError("受入中に入力・JRSNAP・プログラムが変わりました")
    now = datetime.now().astimezone()
    record = {
        "schema_version": 1, "kind": "jrsnap_ndu_acceptance", "date": now.date().isoformat(),
        "verified_at": now.isoformat(timespec="seconds"),
        "method": ("JRSNAP_Input.exe の読込み・保存の処理（mdlDataFile.mdl_Get_NDUDataFile / mdl_Wrt_NDUDataFile）を"
                   "画面なしで呼び、候補の複製を読込み・保存・再保存した（スキル jrsnap-input-open-save の save-ndu.ps1）。"
                   "読込み直後に JRSNAP が保持する件数と組合せを jrsnap_state_probe.cs で取り出した。"),
        "gui_operated": False, "analysis_run": False,
        "not_an_analysis": "NDU の読込み・保存・読戻しの確認であり、耐震解析・部材照査ではない。",
        "application": application, "helpers": helpers,
        "input": {"path": _relative(input_path), "sha256": sha256(data)},
        "implementation_sha256": implementation,
        "directions": directions,
    }
    if evidence.exists():
        shutil.rmtree(evidence)
    evidence.mkdir(parents=True)
    for name, content in files.items():
        (evidence / name).write_bytes(content)
    (evidence / "record.json").write_bytes(dump_json(record))
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="入力JSON（既定: Example2 の設定の current.json）")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE, help="受入記録の出力先")
    parser.add_argument("--app", type=Path, default=DEFAULT_APP, help="JRSNAP_Input.exe（5.2-L03）")
    parser.add_argument("--timeout", type=int, default=60, help="1回の読込み・保存の制限秒（5〜300）")
    parser.add_argument("--overwrite", action="store_true", help="既存の受入記録を作り直す")
    args = parser.parse_args(argv)
    try:
        record = accept(args.input.resolve(), args.evidence.resolve(), args.app.resolve(strict=True), args.timeout,
                        args.overwrite)
    except (AcceptanceError, ReadbackError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"受入未完了: {exc}", file=sys.stderr)
        return 2
    for stage, direction in record["directions"].items():
        print(f"{stage} {direction['file']}: 読込み・保存・再保存 OK、レコード {direction['candidate']['records']}、"
              f"書式だけの違い {len(direction['normalized'])} 欄、組合せ {direction['jrsnap_state']['counts']['G_intConbNum']}")
    print(f"受入記録（解析は実行していません）: {args.evidence.resolve() / 'record.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
