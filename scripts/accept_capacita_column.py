"""Acceptance of the 0611 / 0621 柱の断面照査 with the real Capacita (decision 48, ADR-0008).

The WDJ is rebuilt as ``python -m webpier`` writes it for the stage (calc.column_check, export.capacita) from
tests/fixtures/inputs/current.json (the Example2 input), and the PIK is the real FEMPython's analysis of the same
0610 / 0620 FrameWeb file (FrameWebforCS.Headless, as the stage calls it). Both are given to the real
WebDanforCS.Headless ``run-rc --pickup``. Example2 has no impact reduction on the pier body (decision 77), so the values
are compared with it for the PIK of the reference file, the impact with the girder coefficients
(``tests/acceptance/reactions_by_hand.py: reference_frameweb``); the PIK of the file the generator writes now is given
to Capacita too, which must check the same sections and skip the same ones, and its values are recorded
(``current``) as Capacita's, not compared. The values its report prints for 安全性（破壊）の曲げ and
使用性（損傷）の曲げ are compared with Example2 (tests/fixtures/example2/column_section_check.json and
column_section_check_09.json, ``acceptance``):

- Mud of both: decision 105 counts the side bars in 安全性（破壊）（the H16 sample does not), so Mud must agree within
  0.2 % with the hand calculation for the sample's N'd (tests/acceptance/column_capacity_by_hand.py);
- 0611 (08_線路.pdf 8-26): the check ratio and Myd of 使用性（損傷）must be the printed ones;
- 0621 (09_直角.pdf 9-19, 9-23): WebPier's 0620 wind differs from the sample's (decisions 12, 35), so Md and the
  ratios differ, and decision 103 puts the corner D32 in the main bars, so Myd differs too and is recorded only;
  Capacita must skip the checks the sample omits (``skipped_by_capacita``) and no other.

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
sys.path.insert(0, str(PROJECT / "tests"))
sys.path.insert(0, str(PROJECT / "tests" / "acceptance"))

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
from column_capacity_by_hand import mud  # noqa: E402
from reactions_by_hand import reference_frameweb  # noqa: E402

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
        " PIK（と、橋脚く体の衝撃の低減のない参照の FrameWeb 入力の PIK、決定77）を、本物の WebDanforCS.Headless の run-rc --pickup に渡し、返った計算書の照査値を Example2 08_線路.pdf の"
        " 8-15・8-26 と比べた。",
        ("使用性（損傷）の照査値（γi・Md/Myd＝0.114）は見本と一致し、Myd は見本の WebDan といまの Capacita で 0.2% 未満違う"
         "（38200.7／38260.8。見本自身の WDJ と PIK をいまの Capacita で計算しても同じ値になる）。",
         "安全性（破壊）は決定105 で側方鉄筋 D19×9（片面）を数えるので、Mud と照査値は見本（側方鉄筋を数えない H16。Mud 37449.1、"
         "0.132）と違う。Mud は見本の N'd 15089.9 での手計算（RC標準の応力ひずみ曲線、側方鉄筋込み）と 0.2% 未満で合う。等価応力ブロックで側方鉄筋を"
         "数えない同じ手計算は 37490.6（いまの Capacita の数えない値 37426.2 と 0.17%）。",
         "使用性（損傷）のせん断のページが加わる（見本 8.9(2) は省略。決定48）。",
         "断面力一覧のページが加わる（print_section_force_checked。見本 8.5 に相当）。",
         "基準は RC標準 R5（見本は H16。決定73）で、照査値と耐力は H16 のときと同じ。最小鉄筋量及び最大鉄筋量の節"
         "（bending_rebar_amount、行8 に永久作用）のページが加わる。",
         "表の体裁は Capacita の計算書のもので、見本の WebDan の表とは違う。")),
    "0621": Stage(
        RECORDS / "record_0621.json", EXAMPLE2 / "column_section_check_09.json", "0620", "線路直角方向", True,
        "WebPier が 0621 で書く WDJ と、同じ 0620 の FrameWeb 入力を本物の FEMPython（FrameWebforCS.Headless）で骨組解析した"
        " PIK（と、橋脚く体の衝撃の低減のない参照の FrameWeb 入力の PIK、決定77）を、本物の WebDanforCS.Headless の run-rc --pickup に渡し、返った計算書の Mud を"
        "見本の N'd での手計算（tests/acceptance/column_capacity_by_hand.py）と、省略した照査を Example2 09_直角.pdf の 9-19・9-23 と比べた。",
        ("照査値は見本と比べない。WebPier の 0620 の風荷重は見本と違う（決定12・35）ので Md が違う（安全性（破壊）の"
         " Md 10939.1／見本 8256.6）。",
         "耐力も見本と比べない。決定103 で線路の隅の D32 を主鉄筋に入れ（D19×14.54、芯 104.3。見本は D19×9 を 102）、"
         "決定105 で安全性（破壊）に側方鉄筋 D32×27（片面）を数えるので、Mud は見本の 29334.2 よりずっと大きい。Mud は見本の"
         " N'd 13264.1 での手計算（RC標準の応力ひずみ曲線、図面の位置の D19×9＋D32×2 と側方鉄筋）と 0.2% 未満で合う。等価応力ブロックで側方鉄筋を"
         "数えない同じ手計算は見本の鉄筋で 29380.7（見本 29334.2、0.16%）。",
         "Myd は記録だけで比べない（手計算の降伏曲げモーメントは見本の鉄筋でも Capacita と 3% 違い、Capacita の降伏の定義に"
         "合わせていない）。",
         "Capacita は直角方向の永久作用が左右対称なので使用性（WD-1914）と耐久性のせん断（WD-1919）を飛ばす。見本に 9.7・9.8 が"
         "ないのはこのため。WebPier は見出しと解説に省略の理由を付けて印刷する（決定48）。",
         "柱下端の着目点は PIK の 7 番目（柱に風荷重の区間の端の着目点がある）。見本は 6。",
         "側方鉄筋は隅の鉄筋を除いた D32 の 27 本を 300 から 150 間隔に書く（見本は D32×29 を位置なしで、Capacita が等分）。",
         "基準は RC標準 R5（見本は H16。決定73）で、耐力は H16 のときと同じ。最小鉄筋量及び最大鉄筋量の節"
         "（bending_rebar_amount、行8 に永久作用）のページが加わる。",
         "使用性（損傷）のせん断・断面力一覧のページが加わり、表の体裁は Capacita のもの（0611 と同じ）。")),
}


class AcceptanceError(RuntimeError):
    """The acceptance did not hold; no record is written."""


def _after(lines: list[str], label: str) -> str:
    """The value printed on the line after *label* (the first word: "0.132 ≦ 1.0" → "0.132")."""
    try:
        return lines[lines.index(label) + 1].split()[0]
    except (ValueError, IndexError) as exc:
        raise AcceptanceError(f"「{label}」が計算書にありません") from exc


def _check(wdj: bytes, stage: Stage, pik: bytes, check, runner):
    """Capacita's report for *pik*: (the pages, {section: page, ratio, capacity}, the page count)."""
    pages = capacita.check_column(wdj, f"{stage.name}.pik", pik, runner, check.sections)
    values = {}
    with pymupdf.open(stream=pages.pdf, filetype="pdf") as document:
        page_count = len(document)
        for section, (ratio, capacity, _) in CHECKS.items():
            first, _ = pages.section(section)
            lines = [line.strip() for line in document[first - 1].get_text().splitlines() if line.strip()]
            values[section] = {"page": first, "ratio": _after(lines, ratio), "capacity": _after(lines, capacity)}
    return pages, values, page_count


def main(stage_id: str) -> int:
    stage = STAGES[stage_id]
    data = (PROJECT / INPUT).read_bytes()
    pier = parse_input(load_json(data))
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    check = (calculate_column_check(pier, calculate_transverse(pier, foundation, reaction), TRANSVERSE)
             if stage.transverse else
             calculate_column_check(pier, calculate_longitudinal(pier, foundation, reaction), LONGITUDINAL))
    frameweb, reference = export_bytes(pier, stage.source, "frameweb"), reference_frameweb(pier, stage.source)
    fempython_runner, capacita_runner = fempython.runner_path(), capacita.runner_path()
    analysis = fempython.analyze_frame(f"{stage.name}.json", reference, fempython_runner)
    pik = analysis.files["pik"]
    index = point_index(pik, check.member)
    wdj = write_wdj(build_wdj(check, index))
    pages, values, page_count = _check(wdj, stage, pik, check, capacita_runner)
    sample = load_json(stage.sample.read_bytes())["acceptance"]
    expected = {section: (sample[section]["ratio"], sample[section][key]) for section, (_, _, key) in CHECKS.items()}
    # decisions 103 and 105: Mud is compared with the hand calculation; Myd with the sample along the track only
    compared = {"bending_safety_destruction": (None, round(mud(stage_id), 1))}
    if not stage.transverse:
        compared["bending_restorability"] = expected["bending_restorability"]
    for section, (ratio, capacity) in compared.items():
        if ratio is not None and values[section]["ratio"] != ratio:
            raise AcceptanceError(f"{section}: γi・Md/M = {values[section]['ratio']}（見本は {ratio}）")
        if abs(float(values[section]["capacity"]) - float(capacity)) / float(capacity) >= TOLERANCE:
            raise AcceptanceError(f"{section}: 耐力 {values[section]['capacity']}（比べる値は {capacity}）")
    if sorted(pages.skipped) != sorted(sample.get("skipped_by_capacita", [])):
        raise AcceptanceError(f"Capacita が省略した照査 {list(pages.skipped)}（見本は {sample.get('skipped_by_capacita', [])}）")
    current_analysis = fempython.analyze_frame(f"{stage.name}.json", frameweb, fempython_runner)
    current_pik = current_analysis.files["pik"]
    current_index = point_index(current_pik, check.member)
    if current_index != index:
        raise AcceptanceError(f"着目点の番号が参照と違います（{current_index}、参照 {index}）")
    current_pages, current_values, _ = _check(wdj, stage, current_pik, check, capacita_runner)
    if sorted(current_pages.skipped) != sorted(pages.skipped):
        raise AcceptanceError(f"橋脚く体の衝撃の低減ありで Capacita が省略した照査 {list(current_pages.skipped)}"
                              f"（参照 {list(pages.skipped)}）")
    runner_dll = capacita_runner.with_suffix(".dll")
    record = {
        "schema_version": 2, "kind": "capacita_column_check_acceptance", "stage": stage_id,
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
        "current": {"frameweb_sha256": sha256(frameweb), "reference_frameweb_sha256": sha256(reference),
                    "pik_sha256": sha256(current_pik), "values": current_values,
                    "skipped": list(current_pages.skipped)},
        "sample": {section: {"ratio": ratio, "capacity": capacity} for section, (ratio, capacity) in expected.items()},
        "compared": {section: {"ratio": ratio, "capacity": capacity} for section, (ratio, capacity) in compared.items()},
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
