"""Acceptance of the 0611 / 0621 柱の断面照査 with the real Capacita (decision 48, ADR-0008).

The WDJ is rebuilt as ``python -m webpier`` writes it for the stage (calc.column_check, export.capacita) from
tests/fixtures/inputs/current.json (the Example2 input), and the PIK is the real FEMPython's analysis of the same
0610 / 0620 FrameWeb file (FrameWebforCS.Headless, as the stage calls it). Both are given to the real
WebDanforCS.Headless ``run-rc --pickup``. The values its report prints for 安全性（破壊）の曲げ and
復旧性（地震時以外）の曲げ are compared with Example2 (tests/fixtures/example2/column_section_check.json and
column_section_check_09.json, ``acceptance``):

- 0611 (08_線路.pdf 8-15, 8-26): the check ratios must be the printed ones;
- 0621 (09_直角.pdf 9-19, 9-23): WebPier's 0620 wind differs from the sample's (decisions 12, 35), so Md and the
  ratios differ; N'd is the same, so the capacities Mud and Myd must agree within 0.2 %, and Capacita must skip the
  checks the sample omits (``skipped_by_capacita``) and no other.

The record goes to tests/fixtures/acceptance/capacita/record.json (0611) or record_0621.json, and tests/acceptance
checks that it still belongs to the current generator. It records that Capacita checked the WDJ as WebPier writes
it; the values and the judgement are Capacita's (ADR-0008).

    uv run --project "." --locked python -X utf8 scripts/accept_capacita_column.py [0611|0621]
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

import pymupdf

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.calc.column_check import LONGITUDINAL, TRANSVERSE, calculate_column_check  # noqa: E402
from webpier.calc.foundation import calculate_foundation  # noqa: E402
from webpier.calc.longitudinal import calculate_longitudinal  # noqa: E402
from webpier.calc.reaction import calculate_reaction  # noqa: E402
from webpier.calc.transverse import calculate_transverse  # noqa: E402
from webpier.core.integrity import canonical_sha256, dump_json, load_json, sha256  # noqa: E402
from webpier.export.capacita import build_wdj, point_index, write_wdj  # noqa: E402
from webpier.inputs import parse_input  # noqa: E402
from webpier.pipeline import capacita, fempython  # noqa: E402
from webpier.pipeline.generate import export_bytes  # noqa: E402
from webpier.pipeline.runtime import dependency_hashes  # noqa: E402

INPUT = "tests/fixtures/inputs/current.json"
EXAMPLE2 = PROJECT / "tests" / "fixtures" / "example2"
RECORDS = PROJECT / "tests" / "fixtures" / "acceptance" / "capacita"
# (section, label of the ratio, label of the capacity, key of the capacity in the sample) on the first result page
CHECKS = {"bending_safety_destruction": ("γi･Md/Mud", "Mud (kN･m)", "Mud_kNm"),
          "bending_restorability": ("γi･Md/Myd", "Myd (kN･m)", "Myd_kNm")}
TOLERANCE = 0.002  # the sample's WebDan and the current Capacita (the sample's own WDJ shows the same difference)


@dataclass(frozen=True)
class Stage:
    record: Path
    sample: Path
    source: str  # the FrameWeb export analyzed
    name: str  # the stem of the post/ files
    transverse: bool
    method: str
    differences: tuple[str, ...]


STAGES = {
    "0611": Stage(
        RECORDS / "record.json", EXAMPLE2 / "column_section_check.json", "0610", "線路方向", False,
        "WebPier が 0611 で書く WDJ と、同じ 0610 の FrameWeb 入力を本物の FEMPython（FrameWebforCS.Headless）で骨組解析した"
        " PIK を、本物の WebDanforCS.Headless の run-rc --pickup に渡し、返った計算書の照査値を Example2 08_線路.pdf の"
        " 8-15・8-26 と比べた。",
        ("照査値（γi・Md/Mud＝0.132、γi・Md/Myd＝0.114）は見本と一致する。耐力（Mud・Myd）は見本の WebDan といまの Capacita で"
         " 0.2% 未満違う（Mud 37426.2／37449.1、Myd 38200.7／38260.8）（見本自身の WDJ と PIK をいまの Capacita で計算しても"
         "同じ値になる）。",
         "復旧性のせん断のページが加わる（見本 8.9(2) は省略。決定48）。",
         "断面力一覧のページが加わる（print_section_force_checked。見本 8.5 に相当）。",
         "表の体裁は Capacita の計算書のもので、見本の WebDan の表とは違う。")),
    "0621": Stage(
        RECORDS / "record_0621.json", EXAMPLE2 / "column_section_check_09.json", "0620", "線路直角方向", True,
        "WebPier が 0621 で書く WDJ と、同じ 0620 の FrameWeb 入力を本物の FEMPython（FrameWebforCS.Headless）で骨組解析した"
        " PIK を、本物の WebDanforCS.Headless の run-rc --pickup に渡し、返った計算書の耐力と省略した照査を Example2"
        " 09_直角.pdf の 9-19・9-23 と比べた。",
        ("照査値は見本と比べない。WebPier の 0620 の風荷重は見本と違う（決定12・35）ので Md が違う（安全性（破壊）の"
         " Md 10939.1／見本 8256.6）。軸力 N'd は見本と同じなので、耐力（Mud・Myd）を比べる。",
         "耐力は見本の WebDan といまの Capacita で 0.2% 未満違う（見本自身の WDJ をいまの Capacita で計算すると Mud 29326.7、"
         "Myd 48634.5）。",
         "Capacita は直角方向の永久作用が左右対称なので使用性（WD-1901）と耐久性のせん断（WD-1906）を飛ばす。見本に 9.7・9.8 が"
         "ないのはこのため。WebPier は見出しと解説に省略の理由を付けて印刷する（決定48）。",
         "柱下端の着目点は PIK の 7 番目（柱に風荷重の区間の端の着目点がある）。見本は 6。",
         "側方鉄筋 D32×29 は見本どおり位置を書かず、Capacita が等分に配置する。",
         "復旧性のせん断・断面力一覧のページが加わり、表の体裁は Capacita のもの（0611 と同じ）。")),
}


class AcceptanceError(RuntimeError):
    """The acceptance did not hold; no record is written."""


def _after(lines: list[str], label: str) -> str:
    """The value printed on the line after *label* (the first word: "0.132 ≦ 1.0" → "0.132")."""
    try:
        return lines[lines.index(label) + 1].split()[0]
    except (ValueError, IndexError) as exc:
        raise AcceptanceError(f"「{label}」が計算書にありません") from exc


def main(stage_id: str) -> int:
    stage = STAGES[stage_id]
    data = (PROJECT / INPUT).read_bytes()
    pier = parse_input(load_json(data))
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    check = (calculate_column_check(pier, calculate_transverse(pier, foundation, reaction), TRANSVERSE)
             if stage.transverse else
             calculate_column_check(pier, calculate_longitudinal(pier, foundation, reaction), LONGITUDINAL))
    frameweb = export_bytes(pier, stage.source, "frameweb")
    fempython_runner, capacita_runner = fempython.runner_path(), capacita.runner_path()
    analysis = fempython.analyze_frame(f"{stage.name}.json", frameweb, fempython_runner)
    pik = analysis.files["pik"]
    index = point_index(pik, check.member)
    wdj = write_wdj(build_wdj(check, index))
    pages = capacita.check_column(wdj, f"{stage.name}.pik", pik, capacita_runner, check.sections)
    sample = load_json(stage.sample.read_bytes())["acceptance"]
    values, with_pdf = {}, pymupdf.open(stream=pages.pdf, filetype="pdf")
    with with_pdf as document:
        page_count = len(document)
        for section, (ratio, capacity, _) in CHECKS.items():
            first, _ = pages.section(section)
            lines = [line.strip() for line in document[first - 1].get_text().splitlines() if line.strip()]
            values[section] = {"page": first, "ratio": _after(lines, ratio), "capacity": _after(lines, capacity)}
    expected = {section: (sample[section]["ratio"], sample[section][key]) for section, (_, _, key) in CHECKS.items()}
    for section, (ratio, capacity) in expected.items():
        if not stage.transverse and values[section]["ratio"] != ratio:
            raise AcceptanceError(f"{section}: γi・Md/M = {values[section]['ratio']}（見本は {ratio}）")
        if abs(float(values[section]["capacity"]) - float(capacity)) / float(capacity) >= TOLERANCE:
            raise AcceptanceError(f"{section}: 耐力 {values[section]['capacity']}（見本は {capacity}）")
    if sorted(pages.skipped) != sorted(sample.get("skipped_by_capacita", [])):
        raise AcceptanceError(f"Capacita が省略した照査 {list(pages.skipped)}（見本は {sample.get('skipped_by_capacita', [])}）")
    runner_dll = capacita_runner.with_suffix(".dll")
    record = {
        "schema_version": 1, "kind": "capacita_column_check_acceptance", "stage": stage_id,
        "date": datetime.now().astimezone().date().isoformat(),
        "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": stage.method,
        "not_a_judgement": "照査値と判定は Capacita のもの。WebPier は照査を実行したことだけを記録する（ADR-0008）。",
        "input": {"path": INPUT, "sha256": sha256(data)},
        "implementation_sha256": canonical_sha256({str(path): digest for path, digest in dependency_hashes().items()}),
        "capacita": {"runner": str(capacita_runner), "engine_version": pages.engine_version,
                     "runner_dll_sha256": hashlib.sha256(runner_dll.read_bytes()).hexdigest()
                     if runner_dll.is_file() else None},
        "fempython": {"runner": str(fempython_runner), "engine_version": analysis.engine_version},
        "point_index": index,
        "wdj_given_sha256": sha256(wdj), "pik_sha256": sha256(pik), "completed_wdj_sha256": sha256(pages.wdj),
        "report": {"pages": page_count, "sections": [{"id": section.id, "first": section.first,
                                                       "last": section.last} for section in pages.sections],
                   "skipped": list(pages.skipped)},
        "values": values,
        "sample": {section: {"ratio": ratio, "capacity": capacity} for section, (ratio, capacity) in expected.items()},
        "expected_differences": list(stage.differences),
    }
    stage.record.parent.mkdir(parents=True, exist_ok=True)
    stage.record.write_bytes(dump_json(record))
    print(json.dumps({"values": values, "skipped": list(pages.skipped)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "0611"))
    except (AcceptanceError, capacita.RunnerError) as exc:
        print(f"受入できません: {exc}", file=sys.stderr)
        sys.exit(1)
