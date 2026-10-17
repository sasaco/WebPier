"""Read check of the 0610 / 0620 FrameWeb files in FrameWebforCS.Headless (FEMPython), decision 38.

For each input the FrameWeb files are rebuilt exactly as ``python -m webpier`` writes them (``export_bytes``) and
given to ``FrameWebforCS.Headless.exe run``, which converts the saved document to FEMPython requests, calculates
every load case and evaluates Define / Combine / Pickup. Its envelope and result.json are compared with what we
wrote (``webpier.export.frameweb.readback``): the counts, the skipped empty cases, the balance of every case's
reactions with our loads, and, for 0610 combination 1, the unrounded combination against the printed total.

The record goes to tests/fixtures/acceptance/frameweb_headless/record.json; tests/acceptance checks that it still
belongs to the current generator. The solver runs only to show the file was read as written; its results are not
a structural analysis or a design check.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.calc.foundation import calculate_foundation  # noqa: E402
from webpier.calc.longitudinal import calculate_longitudinal  # noqa: E402
from webpier.calc.reaction import calculate_reaction  # noqa: E402
from webpier.core.integrity import canonical_sha256, dump_json, file_sha256, load_json, sha256  # noqa: E402
from webpier.export.frameweb.readback import (  # noqa: E402
    ReadbackError, check_equilibrium, combination_vertical, compare_counts,
)
from webpier.inputs import parse_input  # noqa: E402
from webpier.pipeline.generate import export_bytes  # noqa: E402
from webpier.pipeline.runtime import dependency_hashes  # noqa: E402
from webpier.pipeline.stages import STAGES  # noqa: E402

FEMPYTHON = Path("C:/Users/sasai/Documents/structural-mcp/FEMPython")
DEFAULT_HEADLESS = FEMPYTHON / "FrameWebforCS/Headless/bin/Release/net10.0-windows/FrameWebforCS.Headless.exe"
DEFAULT_INPUTS = (PROJECT / "pre" / "input.json", PROJECT / "tests" / "fixtures" / "inputs" / "current.json")
DEFAULT_EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "frameweb_headless"
FRAMEWEB_STAGES = ("0610", "0620")


class CheckError(RuntimeError):
    """The read check did not complete; no record is written."""


def _relative(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


def _git(*arguments: str) -> str:
    done = subprocess.run(["git", "-C", str(FEMPYTHON), *arguments], capture_output=True, check=True)
    return done.stdout.decode("utf-8").strip()


def application(headless: Path) -> dict[str, Any]:
    return {"name": "FrameWebforCS.Headless", "path": str(headless), "sha256": file_sha256(headless),
            "dll_sha256": file_sha256(headless.with_suffix(".dll")),
            "fempython_repository": {"path": str(FEMPYTHON), "head": _git("rev-parse", "HEAD"),
                                     "clean": _git("status", "--porcelain") == ""}}


def run_headless(headless: Path, document: Path, output: Path, timeout: int) -> tuple[dict[str, Any], dict[str, Any]]:
    done = subprocess.run([str(headless), "run", "--input", str(document), "--output-dir", str(output),
                           "--generate-pdf", "false", "--generate-pik", "false"],
                          capture_output=True, timeout=timeout, check=False)
    envelope = json.loads(done.stdout.decode("utf-8-sig"))
    if done.returncode or not envelope.get("ok"):
        raise CheckError(f"{document.name}: FrameWebforCS.Headless exit {done.returncode}: {envelope.get('errors')}")
    (artifact,) = [item for item in envelope["artifacts"] if item["kind"] == "result"]
    path = output / artifact["relativePath"]
    if file_sha256(path) != artifact["sha256"]:
        raise CheckError(f"{document.name}: result.json が封筒の SHA256 と一致しません")
    return envelope, json.loads(path.read_bytes().decode("utf-8-sig"))


def check(inputs: tuple[Path, ...], evidence: Path, headless: Path, timeout: int) -> dict[str, Any]:
    implementation = canonical_sha256({str(path): digest for path, digest in dependency_hashes().items()})
    app = application(headless)
    runs = []
    with tempfile.TemporaryDirectory(prefix="webpier-frameweb-check-") as temporary:
        for number, input_path in enumerate(inputs, 1):
            data = input_path.read_bytes()
            pier = parse_input(load_json(data))
            for stage in FRAMEWEB_STAGES:
                content = export_bytes(pier, stage, "frameweb")
                export = next(item for item in STAGES.get(stage).exports if item.kind == "frameweb")
                document_path = Path(temporary) / f"{number}-{stage}" / export.file_name
                document_path.parent.mkdir()
                document_path.write_bytes(content)
                envelope, result = run_headless(headless, document_path, document_path.parent / "out", timeout)
                document = load_json(content)
                run: dict[str, Any] = {
                    "input": {"path": _relative(input_path), "sha256": sha256(data)}, "stage": stage,
                    "file": export.file_name, "candidate_sha256": sha256(content),
                    "envelope": {key: envelope[key] for key in ("engine", "engineVersion", "ok", "executionStatus",
                                                                "engineeringStatus", "summary", "messages", "errors")},
                    "counts": compare_counts(document, envelope, result),
                    "equilibrium": check_equilibrium(document, result),
                }
                if stage == "0610":
                    longitudinal = calculate_longitudinal(pier, calculate_foundation(pier), calculate_reaction(pier))
                    run["combination"] = combination_vertical(longitudinal.combinations[0], document, result)
                runs.append(run)
    if application(headless) != app or canonical_sha256(
            {str(path): digest for path, digest in dependency_hashes().items()}) != implementation:
        raise CheckError("確認中に FrameWebforCS.Headless・FEMPython・プログラムが変わりました")
    now = datetime.now().astimezone()
    record = {
        "schema_version": 1, "kind": "frameweb_headless_read_check", "date": now.date().isoformat(),
        "verified_at": now.isoformat(timespec="seconds"),
        "method": ("FrameWebforCS.Headless.exe run --generate-pdf false --generate-pik false で、保存形式から FEMPython の"
                   "計算要求への変換・全荷重ケースの計算・Define/Combine/Pickup を行い、件数・飛ばした荷重ケース・荷重ケースごとの"
                   "反力と書いた荷重の釣合い・0610 の組合せ1と計算書の印刷値（決定38）を照合した。"),
        "fempython": "FEMPython は FrameWebforCS.Headless が同じプロセス内で使う計算エンジン（engine: fempython）で、"
                     "FrameWeb の保存形式を直接は読まない。FEMPython 単体での読込み確認はない。",
        "not_an_analysis": "読込みの確認のために計算させたもので、構造解析・部材照査の結果として扱わない。",
        "application": app, "implementation_sha256": implementation, "runs": runs,
    }
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "record.json").write_bytes(dump_json(record))
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, action="append", help="入力JSON（繰り返し可。既定: pre/input.json と current.json）")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE, help="記録の出力先")
    parser.add_argument("--headless", type=Path, default=DEFAULT_HEADLESS, help="FrameWebforCS.Headless.exe")
    parser.add_argument("--timeout", type=int, default=600, help="1回の実行の制限秒")
    args = parser.parse_args(argv)
    inputs = tuple(path.resolve() for path in (args.input or DEFAULT_INPUTS))
    try:
        record = check(inputs, args.evidence.resolve(), args.headless.resolve(strict=True), args.timeout)
    except (CheckError, ReadbackError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"確認未完了: {exc}", file=sys.stderr)
        return 2
    for run in record["runs"]:
        counts = run["counts"]
        print(f"{run['input']['path']} {run['stage']} {run['file']}: "
              f"節点 {counts['nodes']}（生成 {counts['generated_nodes']}）"
              f"・部材 {counts['members']}・計算ケース {counts['calculated_cases']}（飛ばした {counts['skipped_load_cases']}）"
              f"・Define {counts['defines']}・Combine {counts['combines']}・Pickup {counts['pickups']}、"
              f"釣合い {len(run['equilibrium'])} ケース OK")
    print(f"記録（構造解析ではありません）: {args.evidence.resolve() / 'record.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
