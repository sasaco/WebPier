"""Real-app acceptance of 0800, 0810 and 0820 of a pile foundation: the section forces of the footing and Capacita's check (decision 96).

``tests/fixtures/inputs/pile_seismic.json`` (the SOIL-JR 5.2 sample E, a 場所打ち杭 of two rows of piles along the track and three
across it, the reinforcement of a pile and of the footing) with every item 0800 uses (0500, 0600, 0610, 0620 and their frame
analyses, 0710, 0720, 0711, 0721) and 0800, 0810, 0820. The acceptance

1. generates them with ``python -m webpier`` and the real runners (SOIL-JR and the analyses of JRSNAP, FEMPython, Aggre-SE, Capacita);
2. reads the section forces again from the files the runners returned, with a reading of its own (the PIK of the frame analysis,
   the pickup of Aggre-SE and the NDU, ``read_pik`` and ``elements_of`` here, not WebPier's), and finds the same numbers in 0800
   (those of 安全性（破壊） times the 応答値係数 γR 1.2 of the linear frame, decision 104)
   for every point and check;
3. checks the forces against statics: at the section of a member end, the bending moment at the face less that at the pile is
   the shear force times the length of the member (``M(j) = M(i) − V·L``, wherever the two ends of the case are the same
   combination), and the largest shear force at the pile position is the largest force at the head of the pile (the axial force
   of the pile's member, the first element of the pile row in the NDU for the earthquake);
4. finds in the reports of 0810 and 0820 the pages of every section Capacita was asked for (bending of 安全性（破壊）, the two deep
   beam shear checks, 耐久性, 復旧性（地震時）, the minimum and the maximum rebar amount), each deep beam page with the shear force
   of 0800.

The record (tests/fixtures/acceptance/pile_footing/record.json) holds the input, the runners' versions, the points of each direction
with their widths and forces, the largest differences of the checks, the pages found and the SHA256 of each WDJ; the files the
sections are read from (the PIK, the pickup, the FrameWeb input and the .sdc) are kept beside it so that tests/acceptance can read
them again and rebuild 0800 with no runner. Capacita's judgement is not recorded (ADR-0008).

    uv run --project "." --locked python -X utf8 scripts/accept_pile_footing.py [--overwrite]
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any

import pymupdf

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.core.integrity import dump_json, file_sha256, load_json  # noqa: E402
from webpier.pipeline import capacita  # noqa: E402
from webpier.pipeline.fempython import RunnerError  # noqa: E402
from webpier.pipeline.generate import GenerationOptions, generate  # noqa: E402

DEFAULT_INPUT = PROJECT / "tests" / "fixtures" / "inputs" / "pile_seismic.json"
DEFAULT_EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "pile_footing"
ITEMS = ("ground_model", "reactions", "longitudinal", "longitudinal_frame_analysis", "transverse", "transverse_frame_analysis",
         "longitudinal_seismic", "longitudinal_nonlinear_analysis", "transverse_seismic", "transverse_nonlinear_analysis",
         "footing")
DIRECTIONS = (("longitudinal", "線路方向", "0810_線路方向フーチング照査"), ("transverse", "線路直角方向", "0820_直角方向フーチング照査"))
CASES = {"安全性（破壊）": "SAFETY", "耐久性 永久＋変動": "SHORT_TERM", "耐久性 永久": "LONG_TERM", "復旧性（地震時）": "SEISMIC"}
PAGES = ("安全性（破壊）曲げモーメントの照査結果", "ディープビーム・下側引張", "ディープビーム・上側引張", "耐久性 曲げひび割れの照査結果",
         "復旧性（損傷）曲げモーメントの照査結果", "最小鉄筋量の照査結果", "最大鉄筋量の照査結果")
TOLERANCE = 0.06  # kN, kN m: the files print two decimals, 0800 one
SEISMIC_PICKUP = 2
GAMMA_R = 1.2  # 応答値係数 of the 安全性 of the linear frame (decision 104; Example橋脚4 III-111)


class AcceptanceError(Exception):
    pass


Lines = dict[tuple[int, str, int, str], tuple[tuple[float, float, float], tuple[float, float, float], int, int]]


def read_pik(content: bytes) -> Lines:
    """(pickup, focus, member, point) → (largest (Md, Vd, Nd), smallest (Md, Vd, Nd), largest case, smallest case)."""
    found: Lines = {}
    for line in content.decode("utf-8-sig", errors="replace").splitlines():
        cells = line.split()
        if len(cells) != 13 or cells[1] not in ("M", "S", "N"):
            continue
        values = [float(cell) for cell in cells[7:]]
        found[(int(cells[0]), cells[1], int(cells[2]), cells[5])] = (tuple(values[:3]), tuple(values[3:]),  # type: ignore[assignment]
                                                                    int(cells[3]), int(cells[4]))
    return found


def sagging(lines: Lines, pickup: int, member: int, point: str, lower: bool) -> tuple[float, int]:
    row = lines[(pickup, "M", member, point)]
    return (row[0][0], row[2]) if lower else (row[1][0], row[3])


def shear(lines: Lines, pickup: int, member: int, point: str) -> tuple[float, float, int]:
    row = lines[(pickup, "S", member, point)]
    best = max(((row[0], row[2]), (row[1], row[3])), key=lambda item: abs(item[0][1]))
    return abs(best[0][1]), best[0][0], best[1]


def expected(lines: Lines, pickup: int, members: dict[str, tuple[int, str]], lower: bool, deep: bool
             ) -> tuple[float, int, float | None, float | None]:
    """The design values of a point from its end on each side: (Md, case, Vd, Md of the case of Vd)."""
    ends = list(members.values())
    candidates = [sagging(lines, pickup, member, point, lower) for member, point in ends]
    moment, case = max(candidates, key=lambda item: item[0]) if lower else min(candidates, key=lambda item: item[0])
    moment = moment if (moment >= 0 if lower else moment <= 0) else 0.0
    if not deep:
        return moment, case, None, None
    shears = [shear(lines, pickup, member, point) for member, point in ends]
    best = max(shears, key=lambda item: item[0])
    return moment, case, best[0], best[1]


def frame_geometry(document: dict[str, Any]) -> tuple[dict[int, tuple[float, float]], dict[int, tuple[int, int]]]:
    nodes = {int(number): (node["x"], node["y"]) for number, node in document["node"].items()}
    members = {int(number): (member["ni"], member["nj"]) for number, member in document["member"].items()}
    return nodes, members


def elements_of(ndu: bytes) -> tuple[dict[int, tuple[float, float]], dict[int, tuple[int, int]], dict[int, int]]:
    """The joints (x, y in m), the elements' joints and the first element of each pile row, from the NDU's records."""
    text = ndu.decode("cp932").split("\r\n")
    joints: dict[int, tuple[float, float]] = {}
    elements: dict[int, tuple[int, int]] = {}
    rows: dict[int, int] = {}
    for line in text:
        if match := re.match(r"JointXY(\d+)=([^,]+),([^,]+)", line):
            joints[int(match[1])] = (float(match[2]), float(match[3]))
        elif match := re.match(r"ElementInfo(\d+)=(?:[^,]*,){4}(\d+),(\d+),", line):
            elements[int(match[1])] = (int(match[2]), int(match[3]))
        elif match := re.match(r"KGInfo(\d+)=(\d+),(\d+),(\d+)", line):
            rows[int(match[1])] = int(match[3])
    return joints, elements, rows


def seismic_end(joints: dict[int, tuple[float, float]], elements: dict[int, tuple[int, int]], base_y: float, item: dict[str, Any]
                ) -> tuple[int, str]:
    """The element of the NDU on the footing base that has the end *item* (its x and its end, ITAN or JTAN) of the frame's member."""
    index = 0 if item["point"] == "ITAN" else 1
    return next((number, item["point"]) for number, ends in elements.items()
                if joints[ends[0]][1] == joints[ends[1]][1] == base_y and abs(joints[ends[index]][0] - item["x"]) < 1e-9)


def check_direction(direction: str, stem: str, post: Path, output: Path, evidence: Path) -> dict[str, Any]:
    result = load_json((output / "0800_フーチング.json").read_bytes())["result"][direction]
    document = json.loads((post / f"{stem}.json").read_bytes().decode("utf-8"))
    nodes, members = frame_geometry(document)
    frame = read_pik((post / f"{stem}.pik").read_bytes())
    seismic = read_pik((post / f"{stem}_Aggre-SE.pik").read_bytes())
    joints, elements, pile_firsts = elements_of((post / f"{stem}.ndu").read_bytes())
    for name in (f"{stem}.pik", f"{stem}.json", f"{stem}_Aggre-SE.pik"):
        shutil.copyfile(post / name, evidence / name)
    base_y = joints[elements[min(pile_firsts.values())][0]][1]  # the heads of the piles: the upper joint of a pile row's first element
    pile_members = {number: ends for number, ends in members.items() if nodes[ends[0]][1] == 0 < nodes[ends[1]][1]}
    failures: list[str] = []
    worst = {"reading": 0.0, "moment_shear": 0.0, "head": 0.0}
    checked = {"reading": 0, "moment_shear": 0, "head": 0}
    points = []
    pickups = {force["case"]: force["pickup"] for force in result["points"][0]["forces"]}
    for point in result["points"]:
        info = point["point"]
        lower, deep = info["tension"] == "下側引張", info["deep_beam"] is not None
        recorded = []
        for force in point["forces"]:
            if CASES[force["case"]] == "SEISMIC":
                found, pickup = seismic, SEISMIC_PICKUP
                ends = {item["side"]: seismic_end(joints, elements, base_y, item) for item in info["ends"]}
            else:
                found, pickup = frame, pickups[force["case"]]
                ends = {item["side"]: (item["member"], item["point"]) for item in info["ends"]}
            values = expected(found, pickup, ends, lower, deep)
            if CASES[force["case"]] == "SAFETY":  # the 応答値係数 γR of the linear frame's 安全性 (decision 104)
                values = tuple(value if value is None or index == 1 else GAMMA_R * value  # 1: the combination
                               for index, value in enumerate(values))
            checked["reading"] += 1
            worst["reading"] = max(worst["reading"], abs(values[0] - force["md"]))
            if abs(values[0] - force["md"]) > TOLERANCE or values[1] != force["md_combination"]:
                failures.append(f"{info['name']} {force['case']}: Md {force['md']}（{force['md_combination']}）が"
                                f"ファイルの値 {values[0]}（{values[1]}）と違います")
            if deep:
                worst["reading"] = max(worst["reading"], abs(values[2] - force["vd"]))
                if abs(values[2] - force["vd"]) > TOLERANCE:
                    failures.append(f"{info['name']} {force['case']}: Vd {force['vd']} がファイルの値 {values[2]} と違います")
            recorded.append({"case": force["case"], "pickup": force["pickup"], "md": force["md"],
                             "md_combination": force["md_combination"], "vd": force["vd"]})
        points.append({"name": info["name"], "key": info["key"], "be": info["width"]["be"], "forces": recorded})
    # statics: the two ends of a member in one combination, and the head of the pile
    face_ends = {item["side"]: item for item in result["points"][0]["point"]["ends"]}
    pile_ends = {item["side"]: item for item in result["points"][2]["point"]["ends"]}
    frame_pickups = sorted({force["pickup"] for force in result["points"][0]["forces"] if force["case"] != "復旧性（地震時）"})
    for side, face in face_ends.items():
        member, pile = face["member"], pile_ends[side]
        length = abs(nodes[members[member][1]][0] - nodes[members[member][0]][0])
        for pickup in frame_pickups:
            row_i, row_j = frame[(pickup, "M", member, "ITAN")], frame[(pickup, "M", member, "JTAN")]
            if row_i[2] != row_j[2]:
                continue  # the largest case of the two ends is not the same one
            for index in (0, 1):
                difference = abs((row_j[index][0] - row_i[index][0]) + row_i[index][1] * length)
                checked["moment_shear"] += 1
                worst["moment_shear"] = max(worst["moment_shear"], difference)
                if difference > 0.2:
                    failures.append(f"{stem} 部材{member} ピックアップ{pickup}: M(j) − M(i) と −V·L が {difference:.2f} 違います")
        head_member = next(number for number, ends in pile_members.items() if abs(nodes[ends[0]][0] - pile["x"]) < 1e-9)
        for pickup in frame_pickups:
            footing = shear(frame, pickup, pile["member"], pile["point"])[0]
            row = frame[(pickup, "N", head_member, "ITAN")]
            head = max(abs(row[0][2]), abs(row[1][2]))
            checked["head"] += 1
            worst["head"] = max(worst["head"], abs(footing - head))
            if abs(footing - head) > TOLERANCE:
                failures.append(f"{stem} ピックアップ{pickup}: 杭位置のせん断力 {footing} が杭頭の軸力 {head} と違います")
        # the earthquake: the pile position's shear force is the force at the head of one of the pile rows (the first element's N)
        element, point_name = seismic_end(joints, elements, base_y, pile)
        footing = shear(seismic, SEISMIC_PICKUP, element, point_name)[0]
        heads = [max(abs(seismic[(SEISMIC_PICKUP, "N", first, "ITAN")][0][2]), abs(seismic[(SEISMIC_PICKUP, "N", first, "ITAN")][1][2]))
                 for first in pile_firsts.values()]
        nearest = min(heads, key=lambda value: abs(value - footing))
        checked["head"] += 1
        worst["head"] = max(worst["head"], abs(footing - nearest))
        if abs(footing - nearest) > TOLERANCE:
            failures.append(f"{stem} 地震時: 杭位置のせん断力 {footing} が杭頭の軸力（{heads}）のどれとも違います")
    return {"points": points, "checked": checked, "worst": {key: round(value, 3) for key, value in worst.items()},
            "failures": failures}


def pages_of(path: Path) -> dict[str, int]:
    found: dict[str, int] = {}
    with pymupdf.open(path) as document:
        texts = [" ".join(page.get_text().split()) for page in document]
    for title in PAGES:
        found[title] = sum(title in text for text in texts)
    return found


def accept(input_path: Path, evidence: Path, overwrite: bool) -> dict[str, Any]:
    record_path = evidence / "record.json"
    if record_path.exists() and not overwrite:
        raise AcceptanceError(f"{record_path} があります（取り直すには --overwrite）")
    failures: list[str] = []
    directions: dict[str, Any] = {}
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="webpier-accept-pile-footing-") as temporary:
        work = Path(temporary)
        data = load_json(input_path.read_bytes())
        data["outputs"] = {key: key in ITEMS for key in data["outputs"]}
        (work / "pre").mkdir()
        source = work / "pre" / "input.json"
        source.write_bytes(dump_json(data))
        generate(GenerationOptions(source, work / "output", work / "post", overwrite=True))
        output, post = work / "output", work / "post"
        shutil.copyfile(post / "杭基礎.sdc", evidence / "ground.sdc")
        for direction, stem, report in DIRECTIONS:
            found = check_direction(direction, stem, post, output, evidence)
            failures += found.pop("failures")
            found["report"] = {"file": f"{report}.pdf", "pages": pages_of(output / f"{report}.pdf")}
            for title, count in found["report"]["pages"].items():
                if count < 1:
                    failures.append(f"{report}: 「{title}」のページがありません")
            wdj_name = f"{stem}フーチング.wdj"
            found["wdj"] = {"file": wdj_name, "sha256": file_sha256(post / wdj_name)}
            directions[direction] = found
    record = {
        "schema_version": 1, "kind": "pile_footing_acceptance",
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": ("本物の SOIL-JR・JRSNAP・FEMPython・Aggre-SE・Capacita の runner で杭基礎の 0800・0810・0820 を生成し、"
                   "フーチングの断面力を runner が返したファイルから別の読み方で読み直して 0800 と照合し、PIK の断面力が"
                   "杭頭の力と静力学でつり合うことと、Capacita のページが各節にそろうことを確かめた。判定は扱わない。"),
        "capacita_judged": False,
        "input": {"path": str(input_path.relative_to(PROJECT)).replace("\\", "/"), "sha256": file_sha256(input_path)},
        "runner": {"capacita": str(capacita.runner_path()), "capacita_sha256": file_sha256(capacita.runner_path())},
        "helpers": {str(Path(__file__).relative_to(PROJECT)).replace("\\", "/"): file_sha256(Path(__file__))},
        "directions": directions, "accepted": not failures, "failures": failures}
    if failures:
        raise AcceptanceError("受入に失敗しました: " + "; ".join(failures))
    record_path.write_bytes(dump_json(record))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--overwrite", action="store_true", help="取り直す")
    arguments = parser.parse_args()
    try:
        record = accept(arguments.input.resolve(), arguments.evidence.resolve(), arguments.overwrite)
    except (AcceptanceError, RunnerError) as exc:
        print(f"受入に失敗しました: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"accepted": record["accepted"],
                      "directions": {name: {"checked": item["checked"], "worst": item["worst"], "pages": item["report"]["pages"]}
                                     for name, item in record["directions"].items()}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
