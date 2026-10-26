"""Real-app acceptance of the 地盤変位 of a pile foundation on G3〜G5 (decision 97, P6d): SoilStructure, JRSNAP and Aggre-SE.

``tests/fixtures/inputs/pile_seismic.json`` (the SOIL-JR 5.2 sample E with the reinforcement of a pile) on G4 with a Vs for each
layer above the base, with the items 0500, 0600, 0710, 0711, 0720 and 0721. The acceptance

1. generates them with the real runners (SOIL-JR and JRSNAP with the JRSNAP runner, SoilStructure for the 地盤変位, Aggre-SE for
   the checks): every Case of 0711 and 0721, the inertia ones and those of the 応答変位法 after them, must be aggregated;
2. reads the DB1 of each Case of the 応答変位法 with SNAPDBLib (independent of WebPier): the analysis is the load increment
   (KaisekiFlg ≠ 1), it stopped at the step of the 最大応答震度 of its level (Kh × 1000), its 着目点 is the NDU's control joint,
   and the 地盤変位 JRSNAP put on the pile head (DeltaG) is the EDSPX the NDU gives it (the reversed Case turns it round);
3. reads Aggre-SE's summary workbook: the response of each Case of the 応答変位法 is at the 最大応答震度 of its level (KhL1 for
   L1, Khmax for L2), and the correction factors of the result are those of the formulas by hand from the summary's Teq, Kheq
   and the Tg of 0710 / 0720;
4. checks that the report has WebPier's pages of the 応答変位法 first, then Aggre-SE's.

The record (tests/fixtures/acceptance/pile_ground_displacement/record.json) keeps the input, the .sdc SOIL-JR returned and the
answer SoilStructure returned beside it, the response values read and the SHA256 of each NDU of the 応答変位法, so that
tests/acceptance can check that the generator still writes those NDUs from them. Aggre-SE's judgement is not recorded (ADR-0009).

    uv run --project "." --locked python -X utf8 scripts/accept_pile_ground_displacement.py [--overwrite]
"""

from __future__ import annotations

import argparse
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

import pymupdf
from openpyxl import load_workbook

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.core.integrity import dump_json, file_sha256, load_json, sha256  # noqa: E402
from webpier.pipeline import aggrese, soilstructure  # noqa: E402
from webpier.pipeline.fempython import RunnerError  # noqa: E402
from webpier.pipeline.generate import GenerationOptions, generate  # noqa: E402

DEFAULT_INPUT = PROJECT / "tests" / "fixtures" / "inputs" / "pile_seismic.json"
DEFAULT_EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "pile_ground_displacement"
VELOCITIES = (170, 120, 140, 180, 330)  # m/s of the layers above the base (made up: the sample E has no Vs)
ITEMS = ("ground_model", "reactions", "longitudinal_seismic", "longitudinal_nonlinear_analysis", "transverse_seismic",
         "transverse_nonlinear_analysis")
STAGES = (("0711", "0710", "線路方向", 4), ("0721", "0720", "線路直角方向", 8))
SNAPDBLIB = PROJECT.parent / "Batch" / "Aggre-SE" / "Headless" / "bin" / "Release" / "SNAPDBLib.dll"
POWERSHELL = Path(r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe")  # SNAPDBLib is 32-bit
READ_DB1 = r"""param([string]$dll, [string]$db1, [int]$node, [int]$control)
[void][Reflection.Assembly]::UnsafeLoadFrom($dll)
$db = New-Object SNAPDBLib.CSNAPDB
$rc = $db.DataRead($db1)
$k = $db.InputInfo.KihonInfo
$steps = $db.OutputInfo.StepCtrl
$last = $steps[$steps.Length - 1]
"$rc|$($k.KaisekiFlg)|$($k.JNo)|$($k.LastStep)|$($last.LoStepNo)|$($last.JointItem[$node].DeltaG)|$($steps[0].JointItem[$control].DeltaX)|$($last.JointItem[$control].DeltaX)"
"""
OK_MESSAGE = "解析に問題はありませんでした"
HEADING = "応答変位法による設計応答値の算定"


class AcceptanceError(RuntimeError):
    """The acceptance did not complete; no evidence is written."""


def _relative(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


def displacing(input_path: Path) -> bytes:
    data = load_json(input_path.read_bytes())
    data["outputs"] = {key: key in ITEMS for key in data["outputs"]}
    data["耐震設計条件"]["地盤区分"] = "G4地盤"
    for layer, velocity in zip(data["地盤データ"]["層"], VELOCITIES):
        layer["せん断弾性波速度_Vs"] = velocity
    return dump_json(data)


def read_db1(db1: Path, node: int, control: int, work: Path) -> dict[str, Any]:
    script = work / "read_db1.ps1"
    script.write_text(READ_DB1, encoding="utf-8-sig")
    done = subprocess.run([str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                           str(SNAPDBLIB), str(db1), str(node), str(control)], capture_output=True, timeout=300,
                          check=False)
    line = done.stdout.decode("cp932", errors="replace").strip().splitlines()[-1] if done.stdout else ""
    fields = line.split("|")
    if done.returncode or len(fields) != 8 or fields[0] != "0":
        raise AcceptanceError(f"{db1.name} を SNAPDBLib で読めません: {done.stderr.decode('cp932', errors='replace')}")
    return {"kaiseki_flg": int(fields[1]), "jno": int(fields[2]), "last_step": int(fields[3]),
            "last_load_step": int(fields[4]), "head_delta_g": float(fields[5]),
            "control_displacement_mm": round(abs(float(fields[7]) - float(fields[6])) * 1000, 1)}


def ndu_fields(ndu: bytes) -> dict[str, str]:
    return dict(line.split("=", 1) for line in ndu.decode("cp932").split("\r\n") if "=" in line)


def summary_values(xlsx: Path) -> dict[int, dict[str, str]]:
    """The 応答値一覧表 by Case number: the rows read here (column A's block and column B's heading)."""
    book = load_workbook(xlsx, read_only=True, data_only=True)
    rows = list(book["応答値一覧表"].iter_rows(values_only=True))
    book.close()
    numbers: tuple = ()
    found: dict[int, dict[str, str]] = {}
    block = ""
    for row in rows:  # the sheet folds the Cases into blocks of columns, each with its own No row
        if row[1] == "No":
            numbers = row
        block = str(row[0]) if row[0] else block
        key = f"{block}/{row[1]}"
        for index, number in enumerate(numbers):
            if index >= 3 and number and index < len(row):
                # the first row of a heading in a block: the sheet goes on below with other tables
                found.setdefault(int(number), {}).setdefault(key, "" if row[index] is None else str(row[index]))
    return found


def _round(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def by_hand(teq: str, tg: float, kh: str, kheq: str, level: str) -> dict[str, str]:
    """α and ν of the formulas (橋りょう編 解7.10.6・7.10.7, 耐震標準 解10.2.9), written out here without WebPier."""
    alpha = _round(Decimal(teq) / (Decimal(repr(tg)) / Decimal({"L1": "0.7", "L2": "0.5"}[level])), "0.001")
    if alpha <= Decimal("0.75"):
        upper, lower = Decimal("1.0"), Decimal("0.0")
    elif alpha < Decimal("1.10"):
        upper, lower = -2 * alpha + Decimal("2.5"), -2 * alpha + Decimal("1.5")
    else:
        upper, lower = Decimal("0.3"), Decimal("-0.7")
    adopted = Decimal("1.0") if Decimal(kh) > Decimal(kheq) else upper
    return {"alpha": str(alpha), "upper": str(_round(upper, "0.01")), "lower": str(_round(lower, "0.01")),
            "adopted": str(_round(adopted, "0.01"))}


def check_stage(stage: str, source: str, stem: str, inertia_count: int, work: Path, failures: list[str]) -> dict[str, Any]:
    output, post = work / "output", work / "post"
    result = load_json(next(output.glob(f"{stage}_*.json")).read_bytes())
    response = result["result"]
    ground = load_json(next(output.glob(f"{source}_*.json")).read_bytes())["result"]["ground_displacement"]
    cases = result["seismic_check"]["cases"]
    count = inertia_count + len(response["cases"])
    if len(cases) != count or not all(case["aggregated"] for case in cases):
        failures.append(f"{stage}: 集計された Case が {len(cases)} 個です（{count} 個のはず）")
    if response["first_case"] != inertia_count + 1:
        failures.append(f"{stage}: 応答変位法の最初の Case が {response['first_case']} です")
    folder = post / f"{stem}_JRSNAP"
    control = int(ndu_fields((post / f"{stem}.ndu").read_bytes())["DataInfo"].split(",")[3])  # the inertia NDU's
    sidecar = load_json((post / f"{stem}_JRSNAP.provenance.json").read_bytes())["nonlinear_analysis"]
    fine = sum(OK_MESSAGE in message["text"] for message in sidecar["messages"])
    summary = summary_values(post / f"{stem}_Aggre-SE.xlsx")
    inertia = response["inertia"]
    first = summary[inertia["case"]]
    for key, value in (("降伏点/全体系折曲点震度", inertia["kheq"]), ("降伏点/等価固有周期", inertia["teq"]),
                       ("復旧性/L1地震動", inertia["kh_l1"])):
        if Decimal(first[key]) != Decimal(repr(value)):
            failures.append(f"{stage}: 慣性力の Case の {key} が総括表（{first[key]}）と違います（{value}）")
    corrections = []
    for correction in response["corrections"]:
        hand = by_hand(first["降伏点/等価固有周期"], ground["period"], str(correction["kh"]), first["降伏点/全体系折曲点震度"],
                       correction["level"])
        ours = {key: str(_round(Decimal(repr(correction[key])), "0.001" if key == "alpha" else "0.01"))
                for key in ("alpha", "upper", "lower")}
        ours["adopted"] = str(_round(Decimal("1.0") if correction["yielded"] else Decimal(repr(correction["upper"])), "0.01"))
        if ours != hand:
            failures.append(f"{stage} {correction['level']}: 補正係数 {ours} が手計算 {hand} と違います")
        corrections.append({"level": correction["level"], "ours": ours, "hand": hand})
    ndus = []
    for index, case in enumerate(response["cases"]):
        name = f"{stem}_応答変位法_{case['level']}-{case['number']}"
        ndu = (folder / f"{name}.ndu").read_bytes()
        fields = ndu_fields(ndu)
        head, edspx = fields["ELoadInfo1"].split(",")[1:3]
        reverse = fields["SNAPConb1"].split(",")[2] == "1"
        db1 = next(folder.glob(f"{name}(Case1_*).DB1"))
        read = read_db1(db1, int(head), control, work)
        steps = int(Decimal(repr(case["kh"])) * 1000)
        applied = -float(edspx) if reverse else float(edspx)
        if read["kaiseki_flg"] == 1 or read["last_step"] != steps or read["jno"] != 0:
            failures.append(f"{name}: DB1 が荷重増分・最終ステップ {steps}・着目点なしではありません（{read}）")
        if abs(read["head_delta_g"] - applied) > 1e-5:
            failures.append(f"{name}: 杭頭の地盤変位 {read['head_delta_g']} が NDU の {applied} と違います")
        row = summary[response["first_case"] + index]
        key = "復旧性/L1地震動" if case["level"] == "L1" else "復旧性/最大応答震度"
        if Decimal(row[key]) != Decimal(repr(case["kh"])):
            failures.append(f"{name}: 総括表の {key} {row[key]} が最大応答震度 {case['kh']} と違います")
        # the 着目点 of the project is the control joint (decision 97): Aggre-SE's displacement is the one of that joint
        if case["level"] == "L2" and abs(float(row["復旧性/最大応答変位"]) - read["control_displacement_mm"]) > 0.11:
            failures.append(f"{name}: 総括表の最大応答変位 {row['復旧性/最大応答変位']} が制御節点 {control} の変位 "
                            f"{read['control_displacement_mm']} と違います")
        ndus.append({"name": f"{name}.ndu", "sha256": sha256(ndu), "reverse": reverse, "head": int(head),
                     "edspx": edspx, "db1": read, "summary": {key: row[key]}})
    with pymupdf.open(next(output.glob(f"{stage}_*.pdf"))) as document:
        texts = [page.get_text() for page in document]
    webpier = sum(1 for text in texts if HEADING in text or "荷重の組合せ" in text)
    if HEADING not in texts[0] or fine != count:
        failures.append(f"{stage}: 計算書の頭に応答変位法の頁がないか、解析に問題がなかった Case が {fine}/{count} です")
    return {"cases": [case["name"] for case in cases], "analysis_ok_messages": fine, "inertia": inertia,
            "first_case": response["first_case"], "corrections": corrections, "ndus": ndus,
            "report": {"pages": len(texts), "webpier_pages_at_least": webpier},
            "project": {"file": f"{stem}.xml", "sha256": file_sha256(post / f"{stem}.xml")}}


def accept(input_path: Path, evidence: Path, overwrite: bool, kept_work: Path | None = None) -> dict[str, Any]:
    record_path = evidence / "record.json"
    if record_path.exists() and not overwrite:
        raise AcceptanceError(f"{record_path} があります（取り直すには --overwrite）")
    runners = {"soilstructure": soilstructure.runner_path(), "aggrese": aggrese.runner_path()}
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="webpier-accept-pile-ground-displacement-",
                                     ignore_cleanup_errors=True) as temporary:
        work = kept_work or Path(temporary)
        source = work / "pre" / "input.json"
        # with --work, a generation of the same input left there is checked again instead of made again
        if not (kept_work and source.is_file() and source.read_bytes() == displacing(input_path)
                and (work / "output").is_dir()):
            (work / "pre").mkdir(parents=True, exist_ok=True)
            source.write_bytes(displacing(input_path))
            generate(GenerationOptions(source, work / "output", work / "post", overwrite=True))
        grounds = {}
        for stage in ("0710", "0720"):
            document = load_json(next((work / "output").glob(f"{stage}_*.json")).read_bytes())
            grounds[stage] = {"result": document["result"]["ground_displacement"], "runner": document["ground_displacement"]}
        if grounds["0710"]["result"] != grounds["0720"]["result"]:
            failures.append("0710 と 0720 の地盤変位が違います")
        stages = {stage: check_stage(stage, source_stage, stem, count, work, failures)
                  for stage, source_stage, stem, count in STAGES}
        kept = {"input.json": source.read_bytes(), "ground.sdc": (work / "post" / "杭基礎.sdc").read_bytes()}
    record = {
        "schema_version": 1, "kind": "pile_ground_displacement_acceptance",
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": ("地盤区分 G4 と各層の Vs を入れた杭基礎の 0711・0721 を本物の SOIL-JR（JRSNAP の runner）・SoilStructure・JRSNAP・"
                   "Aggre-SE で生成し、全 Case の集計、応答変位法の各 Case の DB1（荷重増分・最大応答震度のステップ・着目点・杭頭の"
                   "地盤変位）を SNAPDBLib で、総括表の震度と、補正係数を総括表の Teq・Kheq と Tg からの手計算で確かめた。判定は扱わない。"),
        "seismic_check_judged": False,
        "input": {"path": _relative(input_path), "sha256": file_sha256(input_path), "kept": "input.json",
                  "kept_sha256": sha256(kept["input.json"]), "velocities": list(VELOCITIES)},
        "runners": {name: {"path": str(path), "sha256": file_sha256(path)} for name, path in runners.items()},
        "helpers": {_relative(Path(__file__)): file_sha256(Path(__file__))},
        "ground": grounds, "stages": stages, "accepted": not failures, "failures": failures}
    if failures:
        raise AcceptanceError("受入に失敗しました: " + "; ".join(failures))
    evidence.mkdir(parents=True, exist_ok=True)
    for name, content in kept.items():
        (evidence / name).write_bytes(content)
    record_path.write_bytes(dump_json(record))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--overwrite", action="store_true", help="取り直す")
    parser.add_argument("--work", type=Path, help="生成するフォルダー（同じ入力の生成が残っていれば作り直さずに確かめる）")
    arguments = parser.parse_args()
    try:
        record = accept(arguments.input.resolve(), arguments.evidence.resolve(), arguments.overwrite,
                        arguments.work.resolve() if arguments.work else None)
    except (AcceptanceError, RunnerError) as exc:
        print(f"受入に失敗しました: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"accepted": record["accepted"],
                      "stages": {stage: {"cases": len(item["cases"]), "ok": item["analysis_ok_messages"],
                                         "corrections": item["corrections"]}
                                 for stage, item in record["stages"].items()}},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
