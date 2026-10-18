"""Acceptance of the 0612 / 0622 基礎の照査 with the real FEMPython (decision 54).

The 0610 / 0620 FrameWeb file is rebuilt as ``python -m webpier`` writes it from tests/fixtures/inputs/current.json
(the Example2 input) and analyzed by the real FrameWebforCS.Headless, as the stage calls it. Its reaction pickup CSV is
kept beside the record (tests/fixtures/acceptance/foundation_check/), and the actions WebPier reads from it at the
support node (Vd, Hd, Md and the combination of each column) are compared with Example2:

- 0612 (08_線路.pdf 8-30): every column; the combinations must be the sample's and Vd, Hd, Md agree within 0.25 kN
  (kN m): the sample rounds hidden intermediates (longitudinal_notes.md 3, 4; the short term column differs most);
- 0622 (09_直角.pdf 9-27): WebPier's 0620 wind differs from the sample's (decisions 12, 35), so only the combinations
  and Vd are compared.

tests/acceptance checks that the record still belongs to the current generator and that the recorded reactions give
the independent hand calculation (tests/fixtures/example2/foundation_check.json).

    uv run --project "." --locked python -X utf8 scripts/accept_foundation_check.py [0612|0622]
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.calc import foundation_check as fc  # noqa: E402
from webpier.calc.foundation import calculate_foundation  # noqa: E402
from webpier.calc.longitudinal import calculate_longitudinal  # noqa: E402
from webpier.calc.reaction import calculate_reaction  # noqa: E402
from webpier.calc.transverse import calculate_transverse  # noqa: E402
from webpier.core.integrity import canonical_sha256, dump_json, load_json, sha256  # noqa: E402
from webpier.inputs import parse_input  # noqa: E402
from webpier.pipeline import fempython  # noqa: E402
from webpier.pipeline.generate import export_bytes  # noqa: E402
from webpier.pipeline.runtime import dependency_hashes  # noqa: E402

INPUT = "tests/fixtures/inputs/current.json"
RECORDS = PROJECT / "tests" / "fixtures" / "acceptance" / "foundation_check"
HAND = PROJECT / "tests" / "fixtures" / "example2" / "foundation_check.json"
TOLERANCE = 0.25  # kN, kN m: the sample's hidden digits (longitudinal_notes.md 3, 4)
# stage: (the load stage, its FrameWeb name, the direction, the sample page, the actions compared)
STAGES = {"0612": ("0610", "線路方向", fc.LONGITUDINAL, "8-30", ("vd", "hd", "md")),
          "0622": ("0620", "線路直角方向", fc.TRANSVERSE, "9-27", ("vd",))}


def main(stage: str) -> int:
    source, name, direction, page, compared = STAGES[stage]
    data = (PROJECT / INPUT).read_bytes()
    pier = parse_input(load_json(data))
    frameweb = export_bytes(pier, source, "frameweb")
    runner = fempython.runner_path()
    analyzed = fempython.analyze_frame(f"{name}.json", frameweb, runner)
    csv = analyzed.files["reaction"]
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    frame = (calculate_longitudinal if source == "0610" else calculate_transverse)(pier, foundation, reaction)
    basis = fc.prepare(pier, foundation, frame, direction)
    reactions = fempython.support_reactions(csv, basis.node)
    sample = json.loads(HAND.read_text(encoding="utf-8"))["sample_actions"][page]
    columns, failures = {}, []
    for spec in fc.COLUMNS:
        column = fc.check(basis, reactions).columns[fc.COLUMNS.index(spec)]
        ours = {"combination": column.combination, "vd": column.vd.value, "hd": column.hd.value,
                "md": column.md.value}
        expected = sample[spec.key]
        differences = {key: round(ours[key] - expected[key], 2) for key in ("vd", "hd", "md")}
        columns[spec.key] = {"ours": ours, "sample": expected, "differences": differences}
        if ours["combination"] != expected["combination"]:
            failures.append(f"{spec.key}: 組合せ {ours['combination']}（見本 {expected['combination']}）")
        failures += [f"{spec.key}: {key} の差 {differences[key]}" for key in compared
                     if abs(differences[key]) > TOLERANCE]
    RECORDS.mkdir(parents=True, exist_ok=True)
    reaction_file = RECORDS / f"{name}_ピックアップ反力.csv"
    reaction_file.write_bytes(csv)
    record = {
        "schema_version": 1, "kind": "foundation_check_acceptance", "stage": stage,
        "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": (f"WebPier が {source} で書く FrameWeb 入力を本物の FEMPython（FrameWebforCS.Headless）で骨組解析し、"
                   f"反力の CSV の支点（節点 {basis.node}）から {stage} が読む作用を Example2 {page} と比べた。"),
        "input": {"path": INPUT, "sha256": sha256(data)},
        "implementation_sha256": canonical_sha256({str(path): digest for path, digest in dependency_hashes().items()}),
        "fempython": {"runner": str(runner), "engine_version": analyzed.engine_version},
        "frameweb_sha256": sha256(frameweb),
        "reaction": {"file": reaction_file.name, "sha256": sha256(csv)},
        "node": basis.node, "compared": list(compared), "tolerance": TOLERANCE, "columns": columns,
        "accepted": not failures, "failures": failures,
    }
    (RECORDS / f"record_{stage}.json").write_bytes(dump_json(record))
    print(json.dumps({"stage": stage, "accepted": not failures, "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "0612"))
