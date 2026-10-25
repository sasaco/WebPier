"""Real-app acceptance of 0711 and 0721 of a pile foundation: JRSNAP analyzes the NDUs, Aggre-SE checks the piles (decision 94).

``tests/fixtures/inputs/pile_seismic.json`` (the SOIL-JR 5.2 sample E, a 場所打ち杭 of 3 × 3 piles with the middle one left out,
the reinforcement of a pile, f'ck 30 N/mm2) with the items 0500, 0600, 0710, 0711, 0720 and 0721. The acceptance

1. generates them with ``python -m webpier`` and the real runners (JRSNAP for SOIL-JR, the NDUs' analyses and the figures; Aggre-SE
   for the check): every Case of 0711 (4) and of 0721 (8: the four of the NDU of the forward push, then the four of the reversed
   push, each analyzed from its own NDU into the one folder) must be aggregated into Aggre-SE's report;
2. reads the limit values of each direction from the .sdr SOIL-JR returned (``export.soiljr.parse_sdr``, independent of the
   runner) and finds each of them in the 杭基礎の照査 pages of the report of its stage (the runner read the same .sdr itself,
   ``--sdr``): level 1 and the 安定レベル3 (the 地震時 table) must be there, level 2 when the report has it;
3. runs the real Aggre-SE runner on the JRSNAP sample 01_サンプル(V53)：RC橋脚L's own results (its two Cases) twice, with the project
   of the sample as its owner saved it and with the project WebPier writes for the model of that sample (the nonlinear members,
   the reactions at the heads of the pile rows and the displacement at the footing top are the sample's; the check items of
   each Case are the sample's too, which decision 76 does not choose, and the limit values come from the sample's .sdr through
   ``--sdr``): the 杭基礎の照査 of level 1 in the two reports must be the same.

The record (tests/fixtures/acceptance/pile_nonlinear/record.json) holds the input, the projects WebPier wrote (their SHA256 and
the DB1 names, so tests/acceptance can check that the generator still writes them), the runners' versions, the limits found in
each report and the comparison with the sample. Aggre-SE's judgement is not recorded (ADR-0009).

    uv run --project "." --locked python -X utf8 scripts/accept_pile_nonlinear.py [--overwrite]
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import pymupdf

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "tests"))

from pile_ndu_support import sample_model  # noqa: E402

from webpier.core.integrity import content_sha256, dump_json, file_sha256, load_json  # noqa: E402
from webpier.export.aggrese.project import Project, _rows  # noqa: E402
from webpier.export.aggrese.writer import write_project  # noqa: E402
from webpier.export.jrsnap.pile_model import COLUMN  # noqa: E402
from webpier.export.soiljr import parse_sdr  # noqa: E402
from webpier.pipeline import aggrese  # noqa: E402
from webpier.pipeline.fempython import RunnerError  # noqa: E402
from webpier.pipeline.generate import GenerationOptions, generate  # noqa: E402

DEFAULT_INPUT = PROJECT / "tests" / "fixtures" / "inputs" / "pile_seismic.json"
DEFAULT_EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "pile_nonlinear"
SAMPLE = PROJECT.parent / "Batch" / "tests" / "JRSNAP_Ver5.2-L03" / "01_サンプル(V53)：RC橋脚L：RC"
SAMPLE_XML = SAMPLE / "01_サンプル(V53)：RC橋脚L.xml"
# the .sdr the sample's project took its limits from (SOIL-JR 5.3: 5987.0 …); the one in the sample's own folder is the 5.2 one
SAMPLE_SDR = (PROJECT.parent / "Batch" / "tests" / "JRSNAP_Ver5.3-L01体験版2" / "01_サンプル(V53)：RC橋脚L：RC"
              / "RC橋脚（杭基礎）サンプルデータS.sdr")
ITEMS = ("ground_model", "reactions", "longitudinal_seismic", "longitudinal_nonlinear_analysis", "transverse_seismic",
         "transverse_nonlinear_analysis")
STAGES = (("0711", "橋軸方向", aggrese.AXIAL, 4), ("0721", "直角方向", aggrese.TRANSVERSE, 8))
# the check items of the two Cases of the sample as its owner chose them (dgCaseList_1..9 of its project)
SAMPLE_CASES = ((True, True, True, False, False, True, True, False, False),
                (False, False, False, True, False, False, False, False, False))
LEVEL = re.compile(r"([123])\.安定レベル[１２3３]")
CHECK = "杭基礎の照査"


class AcceptanceError(RuntimeError):
    """The acceptance did not complete; no evidence is written."""


def _relative(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


def limits(sdr: bytes, direction: str) -> dict[str, tuple[str, float, str]]:
    """The limit values the runner imports from the .sdr, read as tables: name → (level, value, format)."""
    found = parse_sdr(sdr)

    def named(condition: str, title: str) -> dict[Any, tuple]:
        return {row[0]: row for row in found.table(direction, condition, title).rows}

    vertical, pullout = named("地震時以外", "設計鉛直支持力の算定"), named("地震時以外", "設計引き抜き抵抗力の算定")
    horizontal, rotation = named("地震時以外", "水平変位の照査"), named("地震時以外", "回転角の照査")
    earthquake = {title: found.table(direction, "地震時", title).rows[0]
                  for title in ("設計鉛直支持力の算定", "水平変位の照査", "回転角の照査")}
    one, two = "残留鉛直変位(L1)", "残留鉛直変位(L2)"
    return {"L1 Rvd": ("1", vertical[one][6], ".1f"), "L1 Rud": ("1", pullout[one][4], ".1f"),
            "L1 δL": ("1", horizontal[one][1], ".3f"), "L1 θL": ("1", rotation[one][1], ".3f"),
            "L2 Rvd": ("2", vertical[two][6], ".1f"), "L2 δL": ("2", horizontal[two][1], ".3f"),
            "L2 θL": ("2", rotation[two][1], ".3f"),
            "Azen Rvd": ("3", earthquake["設計鉛直支持力の算定"][6], ".1f"),
            "Azen δL": ("3", earthquake["水平変位の照査"][0], ".3f"), "Azen θL": ("3", earthquake["回転角の照査"][0], ".3f")}


def check_pages(report: bytes) -> dict[str, str]:
    """The text of each 安定レベル of the 杭基礎の照査 pages of an Aggre-SE report (one text per level)."""
    with pymupdf.open(stream=report, filetype="pdf") as document:
        texts = [page.get_text() for page in document]
    levels: dict[str, str] = {}
    for text in texts:
        if text.lstrip().startswith(CHECK):
            parts = LEVEL.split(text)
            levels.update({parts[index]: parts[index + 1] for index in range(1, len(parts), 2)})
        elif levels and LEVEL.match(text.lstrip()):  # a level continued on the next page
            parts = LEVEL.split(text)
            levels.update({parts[index]: parts[index + 1] for index in range(1, len(parts), 2)})
    return levels


def found_in_report(expected: dict[str, tuple[str, float, str]], levels: dict[str, str]) -> dict[str, dict[str, Any]]:
    return {name: {"level": level, "sdr": value, "in_report": f"{value:{fmt}}" in levels.get(level, "")}
            for name, (level, value, fmt) in expected.items()}


def pages(path: Path) -> int:
    with pymupdf.open(path) as document:
        return document.page_count


def run(runner: Path, xml: Path, extra: list[str], work: Path) -> bytes:
    """report.pdf of the real runner for the project *xml* (the DB1 it names beside it), with the *extra* arguments."""
    output = work / (xml.stem + "-output")
    snaps = work / (xml.stem + "-snaps.json")
    snaps.write_text(json.dumps(aggrese.snap_map(xml), ensure_ascii=False), encoding="utf-8")
    done = subprocess.run([str(runner), "run", "--input", str(xml), "--output-dir", str(output), "--snap-map", str(snaps),
                           "--summary-xlsx", "false", "--report-pdf", "true", "--check-tables", "false", "--pik", "false",
                           "--pile-anchor-bar-pdf", "false", *extra], capture_output=True, timeout=600, check=False)
    envelope = json.loads(done.stdout.decode("utf-8-sig"))
    if done.returncode or not envelope.get("ok"):
        raise AcceptanceError(f"{xml.name}: runner が失敗しました: {envelope.get('errors')}")
    return (output / "report.pdf").read_bytes()


def the_sample(runner: Path, work: Path) -> dict[str, Any]:
    """Level 1 of the 杭基礎の照査 of the sample's own project and of the project WebPier writes for its model."""
    folder = work / "sample"
    shutil.copytree(SAMPLE, folder)
    model = sample_model()
    column = next(element for element in model.elements if element.kind == COLUMN)
    names = sorted(path.name for path in folder.glob("*.DB1"))
    if len(names) != 2:
        raise AcceptanceError(f"見本の DB1 が2つではありません: {names}")
    project = Project(region=2, ground_class=3, shear_span=model.shear_span, footing_joint=column.j, cases=SAMPLE_CASES,
                      pile_rows=_rows(model), pile_sections=len(model.sections) - 1)
    ours = folder / "webpier.xml"
    ours.write_bytes(write_project(project, names))
    theirs = folder / "sample.xml"
    shutil.copyfile(SAMPLE_XML, theirs)
    sample_levels = check_pages(run(runner, theirs, [], work))
    our_levels = check_pages(run(runner, ours, ["--sdr", str(SAMPLE_SDR), "--sdr-direction", aggrese.AXIAL], work))
    if "1" not in sample_levels or "1" not in our_levels:
        raise AcceptanceError("見本の計算書に安定レベル1の杭基礎の照査がありません")
    same = " ".join(sample_levels["1"].split()) == " ".join(our_levels["1"].split())
    return {"sample": {"project": SAMPLE_XML.name, "sdr_sha256": file_sha256(SAMPLE_SDR), "db1": names},
            "level1_text_equal": same, "level1_sample_chars": len(sample_levels["1"]),
            "level1_webpier_chars": len(our_levels["1"])}


def accept(input_path: Path, evidence: Path, overwrite: bool) -> dict[str, Any]:
    record_path = evidence / "record.json"
    if record_path.exists() and not overwrite:
        raise AcceptanceError(f"{record_path} があります（取り直すには --overwrite）")
    runner = aggrese.runner_path()
    failures: list[str] = []
    stages: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="webpier-accept-pile-nonlinear-") as temporary:
        work = Path(temporary)
        data = load_json(input_path.read_bytes())
        data["outputs"] = {key: key in ITEMS for key in data["outputs"]}
        (work / "pre").mkdir()
        source = work / "pre" / "input.json"
        source.write_bytes(dump_json(data))
        generate(GenerationOptions(source, work / "output", work / "post", overwrite=True))
        post = work / "post"
        sdr = (post / "杭基礎.sdr").read_bytes()
        for stage, direction, way, count in STAGES:
            stem = {"0711": "線路方向", "0721": "線路直角方向"}[stage]
            report = next((work / "output").glob(f"{stage}_*.pdf"))
            result = load_json(next((work / "output").glob(f"{stage}_*.json")).read_bytes())
            checked = result["seismic_check"]
            if len(checked["cases"]) != count or not all(case["aggregated"] for case in checked["cases"]):
                failures.append(f"{stage}: 集計された Case が {len(checked['cases'])} 個です（{count} 個のはず）")
            names = sorted(path.name for path in (post / f"{stem}_JRSNAP").glob("*.DB1"))
            levels = check_pages(report.read_bytes())
            seen = found_in_report(limits(sdr, direction), levels)
            for name, item in seen.items():
                if item["level"] in ("1", "3") and not item["in_report"]:
                    failures.append(f"{stage}: 制限値 {name}（{item['sdr']}）が計算書の安定レベル{item['level']}にありません")
            if checked["limits"]["direction"] != way:
                failures.append(f"{stage}: 制限値の方向が {checked['limits']['direction']} です")
            stages[stage] = {
                "project": {"file": f"{stem}.xml", "sha256": file_sha256(post / f"{stem}.xml"), "databases": names},
                "jrsnap": {"folder": f"{stem}_JRSNAP", "sha256": content_sha256(post / f"{stem}_JRSNAP")},
                "report": {"file": report.name, "pages": pages(report), "levels": sorted(levels)},
                "cases": [case["name"] for case in checked["cases"]],
                "limits": {"direction": way, "sdr_sha256": checked["limits"]["sha256"], "found": seen},
                "files": sorted(checked["files"])}
        sample = the_sample(runner, work)
        if not sample["level1_text_equal"]:
            failures.append("見本の杭基礎の照査（安定レベル1）と WebPier のプロジェクトの結果が違います")
    record = {
        "schema_version": 1, "kind": "pile_nonlinear_acceptance",
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": ("本物の JRSNAP と Aggre-SE の runner で杭基礎の 0711・0721 を生成し、杭基礎の照査の制限値が .sdr の値"
                   "（SOIL-JR の表から独立に読んだ）と同じであることを計算書で確かめ、見本 RC橋脚L の結果に見本のプロジェクトと"
                   "WebPier のプロジェクトを当てて、安定レベル1の杭基礎の照査が同じになることを確かめた。判定は扱わない。"),
        "seismic_check_judged": False,
        "input": {"path": _relative(input_path), "sha256": file_sha256(input_path)},
        "runner": {"path": str(runner), "sha256": file_sha256(runner)},
        "helpers": {_relative(Path(__file__)): file_sha256(Path(__file__))},
        "stages": stages, "sample": sample, "accepted": not failures, "failures": failures}
    if failures:
        raise AcceptanceError("受入に失敗しました: " + "; ".join(failures))
    evidence.mkdir(parents=True, exist_ok=True)
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
    print(json.dumps({"accepted": record["accepted"], "stages": {stage: {"cases": len(item["cases"]),
                                                                          "limits": {name: found["in_report"] for name, found in
                                                                                     item["limits"]["found"].items()}}
                                                                 for stage, item in record["stages"].items()},
                      "sample": record["sample"]["level1_text_equal"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
