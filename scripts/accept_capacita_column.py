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
  0.2 % with the hand calculation (tests/acceptance/column_capacity_by_hand.py). For 0611 it is made at the N'd Capacita
  printed for that check (``Nd (kN)`` on its first result page, given to the hand calculation in N): decision 120 makes
  0610's 安全性（破壊） from WebPier's 48 combinations (low / high water, reduced dead loads 0.9 D1 + 0.8 D2), so the
  governing combination and its N'd are no longer the sample's (classification 3). For 0621 it is the sample's N'd;
- 0611 (08_線路.pdf 8-26): the check ratio and Myd of 使用性（損傷）must be the printed ones. Decision 120 (f) adds the
  normal-water buoyancy (Example2 −1701.00 kN, h_w 2.70) to the damage combinations, but it acts at the footing node,
  below the column bottom, so the checked Md and N'd must still be the sample's (3619.6, 14404.5); were they not, the
  values could only be recorded (decision 120 (f), classification 3), and the acceptance stops instead;
- 0621 (09_直角.pdf 9-19, 9-23): WebPier's 0620 wind differs from the sample's (decisions 12, 35), so Md and the
  ratios differ, and decision 103 puts the corner D32 in the main bars, so Myd differs too and is recorded only;
  Capacita must skip the checks the sample omits (``skipped_by_capacita``) and no other.

Capacita does not print the combination behind a check. It is read from the PIK of the reference file (the row of the
check's extraction case at the column bottom whose Md and N'd are the printed ones) and recorded as ``combinations``
with the WebPier combination of that number (0611, ``reactions_by_hand.reference_numbers``; 0620's reference file is
numbered as Example2, so 0621 records the PIK's number only).

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
from reactions_by_hand import reference_frameweb, reference_numbers, reference_result  # noqa: E402

INPUT = "tests/fixtures/inputs/current.json"
EXAMPLE2 = PROJECT / "tests" / "fixtures" / "example2"
RECORDS = PROJECT / "tests" / "fixtures" / "acceptance" / "capacita"
# (section, label of the ratio, label of the capacity, key of the capacity in the sample, Capacita's row id in WDJ
# basic.pickup_moment) on the first result page
CHECKS = {"bending_safety_destruction": ("γi･Md/Mud", "Mud (kN･m)", "Mud_kNm", 5),
          "bending_restorability": ("γi･Md/Myd", "Myd (kN･m)", "Myd_kNm", 6)}
FORCES = {"md": "Md (kN･m)", "n_d": "Nd (kN)"}  # the section forces of the check, printed on the same page
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
         "0.132）と違う。等価応力ブロックで側方鉄筋を数えない見本の N'd 15089.9 での手計算は 37490.6（いまの Capacita の数えない値"
         " 37426.2 と 0.17%）。",
         "決定120 で 0610 の安全性（破壊）は WebPier の 48 の組合せ（低水位・高水位、死荷重を減らした 0.9D1＋0.8D2）から採るので、"
         "決める組合せと N'd は見本と違う（分類3。参照の FrameWeb 入力では制動最大（死荷重低減）の組合せ）。Mud は Capacita が"
         "その照査に使った N'd での手計算（RC標準の応力ひずみ曲線、側方鉄筋込み）と 0.2% 未満で合う。",
         "使用性（損傷）の組合せは決定120 (f) で平水位の浮力を含むが、浮力はフーチングの節点に作用し柱下端の断面力を変えないので、"
         "Md・N'd（3619.6・14404.5）は見本と同じで、照査値と Myd を見本と比べる。",
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
        for section, (ratio, capacity, _, _) in CHECKS.items():
            first, _ = pages.section(section)
            lines = [line.strip() for line in document[first - 1].get_text().splitlines() if line.strip()]
            values[section] = {"page": first, "ratio": _after(lines, ratio), "capacity": _after(lines, capacity),
                               **{key: _after(lines, label) for key, label in FORCES.items()}}
    return pages, values, page_count


def _pik_case(pik: bytes, group: int, member: int, md: str, n_d: str) -> int:
    """The combination number (of the analysed FrameWeb file) of the PIK row of extraction case *group*, moment, at the
    J end of *member* whose Md and N'd are the printed *md* (kN·m) and *n_d* (kN; the PIK has compression negative)."""
    for line in pik.decode("utf-8-sig").replace("\r\n", "\n").split("\n")[1:]:
        if (line[0:5].strip(), line[5:10].strip(), line[10:15].strip(), line[25:30].strip()) != (
                str(group), "M", str(member), "JTAN"):
            continue
        forces = [float(value) for value in line[30:].split()][1:]  # the distance, then max Md Vd Nd, min Md Vd Nd
        for case, (moment, _, axial) in zip((int(line[15:20]), int(line[20:25])), (forces[0:3], forces[3:6])):
            if f"{moment:.1f}" == md and f"{-axial:.1f}" == n_d:
                return case
        raise AcceptanceError(f"PIK の抽出ケース{group}の部材{member}の JTAN に Md {md}・N'd {n_d} の行がありません")
    raise AcceptanceError(f"PIK に抽出ケース{group}の部材{member}の JTAN の行がありません")


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
    expected = {section: (sample[section]["ratio"], sample[section][key])
                for section, (_, _, key, _) in CHECKS.items()}
    # decisions 103 and 105: Mud is compared with the hand calculation; Myd with the sample along the track only.
    # Decision 120: along the track the hand calculation is made at the N'd Capacita printed (kN -> N)
    safety = values["bending_safety_destruction"]
    n_d = None if stage.transverse else float(safety["n_d"]) * 1e3
    compared = {"bending_safety_destruction": (None, round(mud(stage_id, n_d), 1))}
    basis = {"bending_safety_destruction": "見本の N'd での手計算" if n_d is None else
             f"Capacita の N'd {safety['n_d']} kN での手計算", "bending_restorability": "見本"}
    if not stage.transverse:
        compared["bending_restorability"] = expected["bending_restorability"]
        damage, printed = values["bending_restorability"], sample["bending_restorability"]
        if (damage["md"].lstrip("-"), damage["n_d"]) != (printed["Md_kNm"], printed["Nd_kN"]):
            raise AcceptanceError(
                f"bending_restorability: Md {damage['md']}・N'd {damage['n_d']} が見本（{printed['Md_kNm']}・"
                f"{printed['Nd_kN']}）と違います。平水位の浮力（決定120 (f)）が柱下端に効くなら、照査値と Myd は見本と"
                "比べず記録だけにする（分類3）ので、受入を見直してください")
    for section, (ratio, capacity) in compared.items():
        if ratio is not None and values[section]["ratio"] != ratio:
            raise AcceptanceError(f"{section}: γi・Md/M = {values[section]['ratio']}（見本は {ratio}）")
        if abs(float(values[section]["capacity"]) - float(capacity)) / float(capacity) >= TOLERANCE:
            raise AcceptanceError(
                f"{section}: 耐力 {values[section]['capacity']}（比べる値は {basis[section]}の {capacity}）")
    # the combination behind each check, from the PIK (Capacita does not print it)
    cases = dict(check.moment_cases)
    numbers = None if stage.transverse else reference_numbers(reference_result(pier, stage.source))
    combinations = {}
    for section, (_, _, _, row) in CHECKS.items():
        case = _pik_case(pik, cases[row], check.member, values[section]["md"], values[section]["n_d"])
        combinations[section] = {"extraction_case": cases[row], "reference_case": case,
                                 "webpier_combination": None if numbers is None else numbers[case]}
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
        "combinations": combinations,
        "current": {"frameweb_sha256": sha256(frameweb), "reference_frameweb_sha256": sha256(reference),
                    "pik_sha256": sha256(current_pik), "values": current_values,
                    "skipped": list(current_pages.skipped)},
        "sample": {section: {"ratio": ratio, "capacity": capacity} for section, (ratio, capacity) in expected.items()},
        "compared": {section: {"ratio": ratio, "capacity": capacity, "basis": basis[section]}
                     for section, (ratio, capacity) in compared.items()},
        "mud_n_d_kN": safety["n_d"] if n_d is not None else None,
        "expected_differences": list(stage.differences),
    }
    stage.record.parent.mkdir(parents=True, exist_ok=True)
    stage.record.write_bytes(dump_json(record))
    print(json.dumps({"values": values, "compared": record["compared"], "combinations": combinations,
                      "skipped": list(pages.skipped)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "0611"))
    except (AcceptanceError, capacita.RunnerError) as exc:
        print(f"受入できません: {exc}", file=sys.stderr)
        sys.exit(1)
