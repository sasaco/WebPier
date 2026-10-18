"""Acceptance of the 0611 柱の断面照査 with the real Capacita (decision 48, ADR-0008).

The WDJ is rebuilt as ``python -m webpier`` writes it for 0611 (calc.column_check, export.capacita) from
tests/fixtures/inputs/current.json (the Example2 input), and the PIK is the real FEMPython's analysis of the same 0610
FrameWeb file (FrameWebforCS.Headless, as 0611 calls it). Both are given to the real WebDanforCS.Headless
``run-rc --pickup``. The values its report prints for 安全性（破壊）の曲げ and 復旧性（地震時以外）の曲げ are compared
with Example2 08_線路.pdf 8-15 and 8-26 (tests/fixtures/example2/column_section_check.json, ``acceptance``): the check
ratios must be the printed ones. The record goes to tests/fixtures/acceptance/capacita/record.json, and
tests/acceptance checks that it still belongs to the current generator. It records that Capacita checked the WDJ as
WebPier writes it; the values and the judgement are Capacita's (ADR-0008).

    uv run --project "." --locked python -X utf8 scripts/accept_capacita_column.py
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

import pymupdf

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.calc.column_check import calculate_column_check  # noqa: E402
from webpier.calc.foundation import calculate_foundation  # noqa: E402
from webpier.calc.longitudinal import calculate_longitudinal  # noqa: E402
from webpier.calc.reaction import calculate_reaction  # noqa: E402
from webpier.core.integrity import canonical_sha256, dump_json, load_json, sha256  # noqa: E402
from webpier.export.capacita import build_wdj, write_wdj  # noqa: E402
from webpier.inputs import parse_input  # noqa: E402
from webpier.pipeline import capacita, fempython  # noqa: E402
from webpier.pipeline.generate import export_bytes  # noqa: E402
from webpier.pipeline.runtime import dependency_hashes  # noqa: E402

INPUT = "tests/fixtures/inputs/current.json"
SAMPLE = PROJECT / "tests" / "fixtures" / "example2" / "column_section_check.json"
RECORD = PROJECT / "tests" / "fixtures" / "acceptance" / "capacita" / "record.json"
# (section, label of the ratio, label of the capacity) on the section's first result page
CHECKS = {"bending_safety_destruction": ("γi･Md/Mud", "Mud (kN･m)"),
          "bending_restorability": ("γi･Md/Myd", "Myd (kN･m)")}


class AcceptanceError(RuntimeError):
    """The acceptance did not hold; no record is written."""


def _after(lines: list[str], label: str) -> str:
    """The value printed on the line after *label* (the first word: "0.132 ≦ 1.0" → "0.132")."""
    try:
        return lines[lines.index(label) + 1].split()[0]
    except (ValueError, IndexError) as exc:
        raise AcceptanceError(f"「{label}」が計算書にありません") from exc


def main() -> int:
    data = (PROJECT / INPUT).read_bytes()
    pier = parse_input(load_json(data))
    reaction = calculate_reaction(pier)
    check = calculate_column_check(pier, calculate_longitudinal(pier, calculate_foundation(pier), reaction))
    wdj = write_wdj(build_wdj(check))
    frameweb = export_bytes(pier, "0610", "frameweb")
    fempython_runner, capacita_runner = fempython.runner_path(), capacita.runner_path()
    analysis = fempython.analyze_frame("線路方向.json", frameweb, fempython_runner)
    pik = analysis.files["pik"]
    pages = capacita.check_column(wdj, "線路方向.pik", pik, capacita_runner, check.sections)
    sample = load_json(SAMPLE.read_bytes())["acceptance"]
    values, with_pdf = {}, pymupdf.open(stream=pages.pdf, filetype="pdf")
    with with_pdf as document:
        page_count = len(document)
        for section, (ratio, capacity) in CHECKS.items():
            first, _ = pages.section(section)
            lines = [line.strip() for line in document[first - 1].get_text().splitlines() if line.strip()]
            values[section] = {"page": first, "ratio": _after(lines, ratio), "capacity": _after(lines, capacity)}
    expected = {"bending_safety_destruction": (sample["bending_safety_destruction"]["ratio"],
                                               sample["bending_safety_destruction"]["Mud_kNm"]),
                "bending_restorability": (sample["bending_restorability"]["ratio"],
                                          sample["bending_restorability"]["Myd_kNm"])}
    for section, (ratio, _) in expected.items():
        if values[section]["ratio"] != ratio:
            raise AcceptanceError(f"{section}: γi・Md/M = {values[section]['ratio']}（見本は {ratio}）")
    runner_dll = capacita_runner.with_suffix(".dll")
    record = {
        "schema_version": 1, "kind": "capacita_column_check_acceptance",
        "date": datetime.now().astimezone().date().isoformat(),
        "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": "WebPier が 0611 で書く WDJ と、同じ 0610 の FrameWeb 入力を本物の FEMPython（FrameWebforCS.Headless）で"
                  "骨組解析した PIK を、本物の WebDanforCS.Headless の run-rc --pickup に渡し、返った計算書の照査値を"
                  "Example2 08_線路.pdf の 8-15・8-26 と比べた。",
        "not_a_judgement": "照査値と判定は Capacita のもの。WebPier は照査を実行したことだけを記録する（ADR-0008）。",
        "input": {"path": INPUT, "sha256": sha256(data)},
        "implementation_sha256": canonical_sha256({str(path): digest for path, digest in dependency_hashes().items()}),
        "capacita": {"runner": str(capacita_runner), "engine_version": pages.engine_version,
                     "runner_dll_sha256": hashlib.sha256(runner_dll.read_bytes()).hexdigest()
                     if runner_dll.is_file() else None},
        "fempython": {"runner": str(fempython_runner), "engine_version": analysis.engine_version},
        "wdj_given_sha256": sha256(wdj), "pik_sha256": sha256(pik), "completed_wdj_sha256": sha256(pages.wdj),
        "report": {"pages": page_count, "sections": [{"id": section.id, "first": section.first,
                                                       "last": section.last} for section in pages.sections]},
        "values": values,
        "sample": {section: {"ratio": ratio, "capacity": capacity} for section, (ratio, capacity) in expected.items()},
        "expected_differences": [
            "照査値（γi・Md/Mud＝0.132、γi・Md/Myd＝0.114）は見本と一致する。耐力（Mud・Myd）は見本の WebDan と"
            "いまの Capacita で 0.2% 未満違う（Mud 37426.2／37449.1、Myd 38200.7／38260.8）（見本自身の WDJ と PIK をいまの Capacita で計算しても同じ値になる）。",
            "復旧性のせん断のページが加わる（見本 8.9(2) は省略。決定48）。",
            "断面力一覧のページが加わる（print_section_force_checked。見本 8.5 に相当）。",
            "表の体裁は Capacita の計算書のもので、見本の WebDan の表とは違う。",
        ],
    }
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_bytes(dump_json(record))
    print(json.dumps(values, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AcceptanceError, capacita.RunnerError) as exc:
        print(f"受入できません: {exc}", file=sys.stderr)
        sys.exit(1)
