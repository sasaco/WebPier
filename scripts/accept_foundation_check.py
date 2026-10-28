"""Acceptance of the 0612 / 0622 基礎の照査 with the real FEMPython (decision 54, 77, 120).

Two FrameWeb files of the 0610 / 0620 frame are analyzed by the real FrameWebforCS.Headless, as the stage calls it, and
the reaction pickup CSV of each is kept beside the record (tests/fixtures/acceptance/foundation_check/):

- the reference file, the frame with the impact of the girder coefficients as before the impact on the pier body
  (decision 77; ``tests/acceptance/reactions_by_hand.py: reference_frameweb``), which Example2 (no such reduction) can be
  compared with where its combination is still the one WebPier reads:
  - 0612 (08_線路.pdf 8-30): only the long-term column (長期支持), which decision 120 left unchanged. Its combination
    must be WebPier's SUPPORT_LONG_TERM combination (mapped by the check, not by the sample's number; both numbers are
    recorded) and Vd, Hd, Md agree within 0.25 kN (kN m): the sample rounds hidden intermediates (longitudinal_notes.md
    3, 4). The short-term column is now the edge-stress check and the safety columns every safety check, each at low
    and high water (decision 120 (b)(c); Example2 is H16, classification 3): their real reactions must instead be the
    sum of the loads of the combination WebPier picked (``by_hand`` of the reference result, as for the current file
    below). WebPier's combination (number, check, water level, placing) and the sample's are recorded for information;
  - 0622 (09_直角.pdf 9-27): WebPier's 0620 wind differs from the sample's (decisions 12, 35), so only the combinations
    and Vd of every column are compared;
- the file the current generator writes (with the reduction): the frame is statically determinate, so the real
  reaction of the combination a column reads must be the sum of the loads WebPier gives that combination
  (``reactions_by_hand.py: by_hand``): Vd within 0.05 kN (the real run uses the unrounded factors, 22448.2033 against
  22448.22 printed), Fx and Mz within 0.01.

tests/acceptance checks that the record still belongs to the current generator and that the recorded reference
reactions give the independent hand calculation (tests/fixtures/example2/foundation_check.json) where the combination is
still Example2's.

    uv run --project "." --locked python -X utf8 scripts/accept_foundation_check.py [0612|0622]
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "tests"))
sys.path.insert(0, str(PROJECT / "tests" / "acceptance"))

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
from reactions_by_hand import by_hand, reference_frameweb, reference_numbers, reference_result  # noqa: E402

INPUT = "tests/fixtures/inputs/current.json"
RECORDS = PROJECT / "tests" / "fixtures" / "acceptance" / "foundation_check"
HAND = PROJECT / "tests" / "fixtures" / "example2" / "foundation_check.json"
TOLERANCE = 0.25  # kN, kN m: the sample's hidden digits (longitudinal_notes.md 3, 4)
HAND_TOLERANCE = 0.05  # kN, kN m: the real run's unrounded factors against the printed ones (decision 77)
# stage: (the load stage, its FrameWeb name, the direction, the sample page, the actions compared, the columns compared
# with the sample; the others are held to the sum of the loads, decision 120)
STAGES = {"0612": ("0610", "線路方向", fc.LONGITUDINAL, "8-30", ("vd", "hd", "md"), ("long_term",)),
          "0622": ("0620", "線路直角方向", fc.TRANSVERSE, "9-27", ("vd",), tuple(spec.key for spec in fc.COLUMNS))}


def _analyze(name: str, content: bytes, runner) -> tuple[fempython.AnalysisFiles, bytes]:
    analyzed = fempython.analyze_frame(f"{name}.json", content, runner)
    return analyzed, analyzed.files["reaction"]


def _described(result, number: int) -> dict:
    """WebPier's combination *number* of *result*: its check, water level and placing (decision 120)."""
    combination = result.combinations[number - 1]
    return {"webpier_combination": number, "check": combination.check.name,
            "water": combination.water and combination.water.value,
            "placing": combination.layout and combination.layout.value}


def main(stage: str) -> int:
    source, name, direction, page, compared, with_sample = STAGES[stage]
    data = (PROJECT / INPUT).read_bytes()
    pier = parse_input(load_json(data))
    frameweb, reference = export_bytes(pier, source, "frameweb"), reference_frameweb(pier, source)
    runner = fempython.runner_path()
    analyzed, csv = _analyze(name, frameweb, runner)
    analyzed_reference, csv_reference = _analyze(name, reference, runner)
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    frame = (calculate_longitudinal if source == "0610" else calculate_transverse)(pier, foundation, reaction)
    basis = fc.prepare(pier, foundation, frame, direction)
    sample = json.loads(HAND.read_text(encoding="utf-8"))["sample_actions"][page]
    failures = []
    # the reference file: against the sample where its combination is still Example2's, else the sum of the loads
    reference_frame = reference_result(pier, source)
    numbers = reference_numbers(reference_frame) if source == "0610" else None
    reference_reactions = fempython.support_reactions(csv_reference, basis.node)
    reference_check = fc.check(basis, reference_reactions)
    reference_columns = {}
    for spec, column in zip(fc.COLUMNS, reference_check.columns, strict=True):
        ours = {"combination": column.combination, "vd": column.vd.value, "hd": column.hd.value,
                "md": column.md.value}
        if numbers is not None:
            ours |= _described(reference_frame, numbers[column.combination])
        expected = sample[spec.key]
        entry = {"compared_with": "example2" if spec.key in with_sample else "by_hand", "ours": ours,
                 "sample": expected}
        if spec.key in with_sample:
            differences = {key: round(ours[key] - expected[key], 2) for key in ("vd", "hd", "md")}
            entry["differences"] = differences
            if numbers is None:  # 0622: numbered as Example2 (decision 106)
                if ours["combination"] != expected["combination"]:
                    failures.append(f"{spec.key}: 組合せ {ours['combination']}（見本 {expected['combination']}）")
            else:  # by the check: WebPier's combination of the column's group, whatever the sample's number
                wanted = next(extraction.combinations for extraction in reference_frame.extractions
                              if extraction.group is spec.group)
                if ours["webpier_combination"] not in wanted:
                    failures.append(f"{spec.key}: WebPier の組合せ {ours['webpier_combination']} は {spec.group.name}"
                                    f" の組合せ {list(wanted)} でない（見本 {expected['combination']}）")
            failures += [f"{spec.key}: 見本との {key} の差 {differences[key]}" for key in compared
                         if abs(differences[key]) > TOLERANCE]
        else:
            row = fc.pick(reference_reactions, basis.pickups[spec.key], spec.focus)
            hand = by_hand(reference_frame, numbers[row.combination], row.fx, basis.node)
            real = {"vd": round(-row.fy, 4), "fx": round(row.fx, 4), "mz": round(row.mz, 4)}
            differences = {key: round(real[key] - getattr(hand, key), 4) for key in ("vd", "fx", "mz")
                           if getattr(hand, key) is not None}
            entry |= {"real": real, "by_hand": {"vd": hand.vd, "fx": hand.fx, "mz": hand.mz},
                      "differences": differences}
            failures += [f"{spec.key}: 参照の荷重の和との差 {key} {differences[key]}" for key in differences
                         if abs(differences[key]) > HAND_TOLERANCE]
        reference_columns[spec.key] = entry
    # the current file against the sum of the loads
    reactions = fempython.support_reactions(csv, basis.node)
    columns = {}
    for spec in fc.COLUMNS:
        row = fc.pick(reactions, basis.pickups[spec.key], spec.focus)
        hand = by_hand(frame, row.combination, row.fx, basis.node)
        real = {"combination": row.combination, "vd": round(-row.fy, 4), "fx": round(row.fx, 4),
                "mz": round(row.mz, 4)}
        differences = {key: round(real[key] - getattr(hand, key), 4) for key in ("vd", "fx", "mz")
                       if getattr(hand, key) is not None}  # 0620: the vertical sum only
        columns[spec.key] = {"real": real, "by_hand": {"vd": hand.vd, "fx": hand.fx, "mz": hand.mz},
                             "differences": differences}
        failures += [f"{spec.key}: 荷重の和との差 {key} {differences[key]}" for key in differences
                     if abs(differences[key]) > HAND_TOLERANCE]
    RECORDS.mkdir(parents=True, exist_ok=True)
    reaction_file = RECORDS / f"{name}_ピックアップ反力_橋脚く体の衝撃.csv"
    reaction_file.write_bytes(csv)
    reference_file = RECORDS / f"{name}_ピックアップ反力.csv"
    reference_file.write_bytes(csv_reference)
    record = {
        "schema_version": 2, "kind": "foundation_check_acceptance", "stage": stage,
        "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": (f"WebPier が {source} で書く FrameWeb 入力（橋脚く体の衝撃の低減あり、決定77）を本物の FEMPython"
                   f"（FrameWebforCS.Headless）で骨組解析し、反力の CSV の支点（節点 {basis.node}）から {stage} が読む"
                   f"作用を、その組合せの荷重の和と比べた。低減のない参照の FrameWeb 入力も解析し、"
                   + (f"Example2 {page} と比べた。" if len(with_sample) == len(fc.COLUMNS) else
                      f"組合せが Example2 と同じ列（{'・'.join(with_sample)}）は Example2 {page} と、"
                      f"他の列（決定120）はその組合せの荷重の和と比べた。")),
        "input": {"path": INPUT, "sha256": sha256(data)},
        "implementation_sha256": canonical_sha256({str(path): digest for path, digest in dependency_hashes().items()}),
        "fempython": {"runner": str(runner), "engine_version": analyzed.engine_version},
        "frameweb_sha256": sha256(frameweb),
        "reaction": {"file": reaction_file.name, "sha256": sha256(csv)},
        "node": basis.node, "hand_tolerance": HAND_TOLERANCE, "columns": columns,
        "reference": {
            "fempython": {"engine_version": analyzed_reference.engine_version},
            "frameweb_sha256": sha256(reference),
            "reaction": {"file": reference_file.name, "sha256": sha256(csv_reference)},
            "compared": list(compared), "compared_columns": list(with_sample), "tolerance": TOLERANCE,
            "hand_tolerance": HAND_TOLERANCE, "columns": reference_columns,
        },
        "accepted": not failures, "failures": failures,
    }
    (RECORDS / f"record_{stage}.json").write_bytes(dump_json(record))
    print(json.dumps({"stage": stage, "accepted": not failures, "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "0612"))
