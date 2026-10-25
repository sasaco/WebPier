"""Real-app acceptance of 0710 and 0720 of a pile foundation: JRSNAP analyzes the NDUs WebPier writes (decision 93).

``tests/fixtures/inputs/pile_seismic.json`` is the SOIL-JR 5.2 sample E (a 場所打ち杭 of 3 × 3 piles with the middle one left out;
tests/fixtures/inputs/pile.json) with the reinforcement of a pile (20-D32 SD345, D16 hoops at 200 in the 2D zone and at 300 below,
f'ck 30 N/mm2 so that its value after the construction condition is inside what JRSNAP takes) and the items 0500, 0600, 0710 and
0720. The acceptance

1. generates them with ``python -m webpier`` and the real runners (``STRUCTURAL_MCP_JRSNAP_RUNNER``: SOIL-JR for
   0500, and JRSNAP's figures of the NDUs for the reports);
2. has the real JRSNAP analyze each of the three NDUs written (0710, 0720, and 0720 of the reversed push): every combination must
   finish (the engine says 解析に問題はありませんでした, the LOG has its end marker). The runner raises ANALYSIS_FAILED otherwise.

The record (tests/fixtures/acceptance/pile_seismic/record.json) holds the input, the SHA256 of each NDU (so that tests/acceptance
can check the generator still writes them), the runner's versions and, for each analysis, the SHA256 of each combination's DB1
(JRSNAP writes it the same every run), the warnings and the engine's messages by kind. The analyses are the same program's, not a
check against a reference: the sample RC橋脚L's own results are compared in scripts/accept_pile_ndu.py through its NDT.

    uv run --project "." --locked python -X utf8 scripts/accept_pile_seismic.py [--overwrite]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.core.integrity import dump_json, file_sha256, sha256  # noqa: E402
from webpier.pipeline import jrsnap  # noqa: E402
from webpier.pipeline.fempython import RunnerError  # noqa: E402

DEFAULT_INPUT = PROJECT / "tests" / "fixtures" / "inputs" / "pile_seismic.json"
DEFAULT_EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "pile_seismic"
NDUS = ("線路方向.ndu", "線路直角方向.ndu", "線路直角方向_逆向.ndu")
OK_MESSAGE = "情報：解析に問題はありませんでした"
_NUMBER = re.compile(r"[0-9]+")


class AcceptanceError(RuntimeError):
    """The acceptance did not complete; no evidence is written."""


def pages(pdf: bytes) -> int:
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        return document.page_count


def analysis_record(name: str, document: bytes, runner: Path, failures: list[str]) -> dict:
    """What the real analysis of *document* did: the combinations, their DB1 and what JRSNAP and its engine said."""
    result = jrsnap.analyze_nonlinear(name, document, runner)
    cases = [item["name"] for item in result.summary["cases"]]
    db1 = {case: sha256(result.files[Path(case).with_suffix(".DB1").name]) for case in cases}
    texts = [message["text"] for message in result.messages]
    fine = sum(OK_MESSAGE in text for text in texts)
    if fine != len(cases):
        failures.append(f"{name}: 解析に問題がなかった組合せが {fine}/{len(cases)} です")
    warnings = collections.Counter(_NUMBER.sub("#", message["text"]) for message in result.messages
                                   if message["level"] == "warning")
    others = collections.Counter(_NUMBER.sub("#", text)[:30] for text in texts if OK_MESSAGE not in text)
    return {"cases": cases, "db1_sha256": db1, "analysis_ok_messages": fine, "warnings": dict(sorted(warnings.items())),
            "engine_messages": dict(sorted(others.items()))}


def accept(input_path: Path, evidence: Path, overwrite: bool) -> dict:
    runner = jrsnap.runner_path()
    record_path = evidence / "record.json"
    if record_path.exists() and not overwrite:
        raise AcceptanceError(f"{record_path} があります（取り直すには --overwrite）")
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="webpier-accept-pile-seismic-") as work:
        root = Path(work)
        (root / "pre").mkdir()
        source = root / "pre" / "input.json"
        source.write_bytes(input_path.read_bytes())
        done = subprocess.run([sys.executable, "-X", "utf8", "-m", "webpier", "--input", str(source), "--output-dir",
                               str(root / "output"), "--post-dir", str(root / "post")], cwd=PROJECT, capture_output=True,
                              check=False)
        if done.returncode:
            raise AcceptanceError("生成に失敗しました: " + done.stdout.decode("utf-8", "replace")[-600:]
                                  + done.stderr.decode("utf-8", "replace")[-600:])
        written = {name: (root / "post" / name).read_bytes() for name in NDUS}
        reports = {stage: pages(next((root / "output").glob(f"{stage}*.pdf")).read_bytes()) for stage in ("0710", "0720")}
        analyses = {name: analysis_record(name, written[name], runner, failures) for name in NDUS}
    record = {
        "kind": "pile_seismic_acceptance", "schema_version": 1,
        "input": {"path": input_path.relative_to(PROJECT).as_posix(), "sha256": file_sha256(input_path)},
        "ndus": {name: {"sha256": sha256(written[name]), **analyses[name]} for name in NDUS},
        "report_pages": reports, "accepted": not failures, "failures": failures}
    if failures:
        raise AcceptanceError("受入に失敗しました: " + "; ".join(failures))
    evidence.mkdir(parents=True, exist_ok=True)
    record_path.write_bytes(dump_json(record))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--overwrite", action="store_true", help="取り直す")
    arguments = parser.parse_args()
    try:
        record = accept(arguments.input.resolve(), DEFAULT_EVIDENCE, arguments.overwrite)
    except (AcceptanceError, RunnerError) as exc:
        print(f"受入に失敗しました: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"accepted": record["accepted"], "report_pages": record["report_pages"],
                      "ndus": {name: item["analysis_ok_messages"] for name, item in record["ndus"].items()}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
