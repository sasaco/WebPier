"""Real-app acceptance of the NDU of a pile foundation: JRSNAP writes the NDT of the NDU WebPier writes (decision 93).

``tests/pile_ndu_support.sample_model`` is the model of the JRSNAP sample 01_サンプル(V53)：RC橋脚L (a wall pier on 8
場所打ち杭): the column, the footing and one load are written out there, the piles come from the .sdc of SOIL-JR 5.3 (the one the
sample was linked to) through ``calc.pile_seismic`` and ``export.jrsnap.pile_build``. The acceptance

1. writes its NDU (``write_pile_ndu``) and has the real JRSNAP runner (``STRUCTURAL_MCP_JRSNAP_RUNNER``) export the NDT of it,
   which is JRSNAP reading the NDU and writing what its analysis takes (``run --analyze false``: nothing is analysed);
2. compares that NDT with the NDT of the sample's first case (tests/fixtures/jrsnap/pile_s_case1.ndt, the one JRSNAP wrote for
   the sample): it must be the same but for the names, the count of the load cases and the loads the model of the test does not
   have, the flags of the DA card the sample's program saved, and Kv2 = 2086.25 of two nodes (JRSNAP's Single arithmetic rounds
   it down, the exact decimal up). Everything of the piles, the sections and the supports is the sample's.

The record (tests/fixtures/acceptance/pile_ndu/record.json) holds the SHA256 of the NDU WebPier writes, of the NDT JRSNAP wrote
for it and of the sample's, the runner's versions and the differences by region.

    uv run --project "." --locked python -X utf8 scripts/accept_pile_ndu.py [--overwrite]
"""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "tests"))

from pile_ndu_support import sample_model  # noqa: E402

from webpier.core.integrity import dump_json, sha256  # noqa: E402
from webpier.export.jrsnap.writer import write_pile_ndu  # noqa: E402
from webpier.pipeline import jrsnap  # noqa: E402

SAMPLE_NDT = PROJECT / "tests" / "fixtures" / "jrsnap" / "pile_s_case1.ndt"
SAMPLE_NDU = PROJECT / "tests" / "fixtures" / "jrsnap" / "pile_s.ndu"
EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "pile_ndu"
TIMEOUT = 600
HEADER_LINES = 12  # COUNT, the titles, DIMENSION and the DA card
TIES = ("2086.2", "2086.3")


class AcceptanceError(RuntimeError):
    """The acceptance did not complete; no evidence is written."""


def export_ndt(ndu: bytes, runner: Path) -> tuple[bytes, dict]:
    """The NDT of the first case of *ndu*, as the runner exports it (no analysis), and the runner's summary."""
    with tempfile.TemporaryDirectory(prefix="webpier-accept-pile-ndu-") as work:
        root = Path(work)
        (root / "model.ndu").write_bytes(ndu)
        done = subprocess.run([str(runner), "run", "--input", str(root / "model.ndu"), "--output-dir", str(root / "out"),
                               "--analyze", "false"], capture_output=True, timeout=TIMEOUT, check=False)
        envelope = json.loads(done.stdout.decode("utf-8"))
        if not envelope["ok"]:
            raise AcceptanceError(f"runner が失敗しました: {envelope.get('errors')}")
        names = sorted(path.name for path in (root / "out").glob("*.ndt"))
        if len(names) != 1:
            raise AcceptanceError(f"NDT が1つではありません: {names}")
        return (root / "out" / names[0]).read_bytes(), envelope["summary"]


def regions(ours: list[str], sample: list[str]) -> tuple[list[dict], list[str]]:
    """The differences of two NDTs by region of the sample, and the ones that belong to no region."""
    loads = next(index for index, text in enumerate(sample) if text == "MEMBER LOAD")
    found, unexplained = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, sample, ours, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if i1 < HEADER_LINES:
            region = "header"
        elif i1 >= loads:
            region = "loads"
        elif all(any(tie in text for tie in TIES) for text in sample[i1:i2] + ours[j1:j2]):
            region = "tie"
        else:
            region = ""
        if region:
            found.append({"region": region, "sample_lines": [i1 + 1, i2], "count": max(i2 - i1, j2 - j1)})
        else:
            unexplained.append(f"{i1 + 1}〜{i2}: {sample[i1:i2][:2]} → {ours[j1:j2][:2]}")
    return found, unexplained


def accept(overwrite: bool) -> dict:
    runner = jrsnap.runner_path()
    record_path = EVIDENCE / "record.json"
    if record_path.exists() and not overwrite:
        raise AcceptanceError(f"{record_path} があります（取り直すには --overwrite）")
    ndu = write_pile_ndu(sample_model())
    ndt, summary = export_ndt(ndu, runner)
    sample = SAMPLE_NDT.read_bytes()
    found, unexplained = regions(ndt.decode("cp932").split("\r\n"), sample.decode("cp932").split("\r\n"))
    failures = [f"見本の NDT との説明できない違い: {text}" for text in unexplained]
    if sorted({item["region"] for item in found}) != ["header", "loads", "tie"]:
        failures.append(f"違いの領域が想定と違います: {sorted({item['region'] for item in found})}")
    record = {
        "kind": "pile_ndu_acceptance", "schema_version": 1,
        "model": "tests/pile_ndu_support.py: sample_model()",
        "written": {"ndu_sha256": sha256(ndu), "ndt_sha256": sha256(ndt)},
        "sample": {"ndu_sha256": sha256(SAMPLE_NDU.read_bytes()), "ndt_sha256": sha256(sample)},
        "runner": {"summary": summary}, "differences": found,
        "analyzed": False, "accepted": not failures, "failures": failures}
    if failures:
        raise AcceptanceError("受入に失敗しました: " + "; ".join(failures))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    record_path.write_bytes(dump_json(record))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--overwrite", action="store_true", help="取り直す")
    arguments = parser.parse_args()
    try:
        record = accept(arguments.overwrite)
    except (AcceptanceError, jrsnap.RunnerError, subprocess.TimeoutExpired) as exc:
        print(f"受入に失敗しました: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"accepted": record["accepted"], "differences": record["differences"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
