"""Real-app acceptance of 0500 for a pile foundation: SOIL-JR calculates the .sdt WebPier writes (decision 85, ADR-0013).

``tests/fixtures/inputs/pile.json`` is the SOIL-JR 5.2 sample RC橋脚（杭基礎）サンプルデータE.sdt (a 場所打ち杭 of 3 × 3 piles
with the middle one left out) as a WebPier input. The acceptance

1. generates 0500 from it with ``python -m webpier``'s generation and the real JRSNAP runner
   (``STRUCTURAL_MCP_JRSNAP_RUNNER``, as a normal generation finds it), which has the real SOIL-JR calculate the .sdt;
2. has the same runner calculate the sample's own .sdt (from the installation next to the runner) and compares the two
   results: the .sdr and the .sdc must be the sample's byte for byte but for the title (WebPier's is ``WebPier 杭基礎``),
   and the report must have as many pages.

The record (tests/fixtures/acceptance/pile_ground/record.json) holds the input, the .sdt WebPier writes (its SHA256, so
tests/acceptance can check that the generator still writes it), the SHA256 of each file of both calculations, the runner's
versions and the comparison. SOIL-JR returns no judgement.

    uv run --project "." --locked python -X utf8 scripts/accept_pile_ground.py [--overwrite]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

import pymupdf

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.core.integrity import dump_json, file_sha256, load_json, sha256  # noqa: E402
from webpier.pipeline import jrsnap  # noqa: E402
from webpier.pipeline.generate import GenerationOptions, generate  # noqa: E402

DEFAULT_INPUT = PROJECT / "tests" / "fixtures" / "inputs" / "pile.json"
DEFAULT_EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "pile_ground"
SAMPLE = Path("サンプルデータ") / "SOILデータ(SDT)" / "RC橋脚（杭基礎）サンプルデータE.sdt"
CONFIGURATION = "jrsnap-headless.json"


class AcceptanceError(RuntimeError):
    """The acceptance did not complete; no evidence is written."""


def installation(runner: Path) -> Path:
    """The JRSNAP installation the runner uses (its own setting next to it)."""
    configured = runner.with_name(CONFIGURATION)
    if not configured.is_file():
        raise AcceptanceError(f"{configured} がありません")
    return Path(json.loads(configured.read_text(encoding="utf-8-sig"))["installDir"])


def untitled(data: bytes, *titles: str) -> bytes:
    """The bytes of a .sdr or .sdc with each title replaced, so that two calculations of the same model compare."""
    for title in titles:
        data = data.replace(title.encode("cp932"), b"T")
    return data


def pages(pdf: bytes) -> int:
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        return document.page_count


def accept(input_path: Path, evidence: Path, overwrite: bool) -> dict:
    runner = jrsnap.runner_path()
    sample_path = installation(runner) / SAMPLE
    if not sample_path.is_file():
        raise AcceptanceError(f"SOIL-JR の見本 {sample_path} がありません")
    record_path = evidence / "record.json"
    if record_path.exists() and not overwrite:
        raise AcceptanceError(f"{record_path} があります（取り直すには --overwrite）")
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="webpier-accept-pile-") as work:
        root = Path(work)
        (root / "pre").mkdir()
        source = root / "pre" / "input.json"
        source.write_bytes(input_path.read_bytes())
        generation = generate(GenerationOptions(source, root / "output", root / "post"))
        if generation.stages != ("0400", "0500", "0600"):
            raise AcceptanceError(f"段階が想定と違います: {generation.stages}")
        written = {kind: (root / "post" / f"杭基礎.{kind}").read_bytes() for kind in ("sdt", "sdr", "sdc")}
        report = (root / "output" / "0500_杭基礎.pdf").read_bytes()
        result = load_json((root / "output" / "0500_杭基礎.json").read_bytes())
        sample = jrsnap.calculate_ground("sample.sdt", sample_path.read_bytes(), runner, liquefaction=False)
    title = "WebPier 杭基礎"
    sample_title = sample.files["sdr"].decode("cp932").split("\r\n")[1]
    same = {kind: untitled(written[kind], title) == untitled(sample.files[kind], sample_title) for kind in ("sdr", "sdc")}
    for kind, equal in same.items():
        if not equal:
            failures.append(f".{kind} が見本の .sdt の結果と（表題を除いて）違います")
    if pages(report) != pages(sample.report):
        failures.append(f"帳票のページ数が見本と違います（{pages(report)} と {pages(sample.report)}）")
    if result["soil_jr"]["engineering_status"] != "not_evaluated":
        failures.append("判定を返さない計算として記録されていません")
    record = {
        "kind": "pile_ground_acceptance", "schema_version": 1,
        "input": {"path": input_path.relative_to(PROJECT).as_posix(), "sha256": file_sha256(input_path)},
        "runner": {"engine_version": result["soil_jr"]["engine_version"], "summary": result["soil_jr"]["runner_summary"]},
        "sample": {"file": SAMPLE.as_posix(), "sha256": sha256(sample_path.read_bytes()),
                   "runner_summary": sample.summary},
        "written": {"sdt_sha256": sha256(written["sdt"]),
                    **{f"{kind}_sha256": sha256(written[kind]) for kind in ("sdr", "sdc")},
                    "report_pages": pages(report)},
        "sample_result": {f"{kind}_sha256": sha256(sample.files[kind]) for kind in ("sdr", "sdc")} | {
            "report_pages": pages(sample.report)},
        "same_as_sample_but_for_the_title": same,
        "soil_jr_judged": False, "accepted": not failures, "failures": failures}
    if failures:
        raise AcceptanceError("受入に失敗しました: " + "; ".join(failures))
    evidence.mkdir(parents=True, exist_ok=True)
    record_path.write_bytes(dump_json(record))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--overwrite", action="store_true")
    arguments = parser.parse_args()
    try:
        record = accept(arguments.input.resolve(), arguments.evidence.resolve(), arguments.overwrite)
    except (AcceptanceError, jrsnap.RunnerError) as exc:
        print(f"受入を記録していません: {exc}", file=sys.stderr)
        return 1
    print(re.sub(r"\s+", " ", json.dumps(record["same_as_sample_but_for_the_title"], ensure_ascii=False)))
    print(f"受入を記録しました: {arguments.evidence / 'record.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
