"""Real-app acceptance of 0711 and 0721 of a pile foundation whose ground liquefies (decision 95).

The input is ``tests/fixtures/inputs/pile_seismic.json`` (the SOIL-JR 5.2 sample E with the reinforcement of a pile) with the
third layer liquefying (De 0.5), the 液状化指数 ``20<PL`` (the owner's sample R-7 has it) and the items 0500, 0600, 0710, 0711,
0720 and 0721. The acceptance

1. generates them with ``python -m webpier`` and the real runners: SOIL-JR returns the .sdr and .sdc for the liquefaction too,
   JRSNAP analyzes the NDUs for the liquefaction with the others into one folder, Aggre-SE checks every Case. Every Case must
   be aggregated (0711: 4 and one for the liquefaction; 0721: 4, 4 and one for each push for the liquefaction), the engine of
   each analysis must say 解析に問題はありませんでした, and the report must treat each Case for the liquefaction as one
   (「液状化区分 液状化指数PL(20＜PL)」 on its page of the response values);
2. checks that the runner imports the limit values of the .sdr for the liquefaction (``--sdr-liquefied``, rows 10〜16 of the
   limit values): the project of 0711 is run again with only its Case for the liquefaction checked for the stability of the
   piles (① 復旧性L2 and ⑦ on), and the 安定レベル2 of the report must hold the Rvd of 残留鉛直変位(L2) of the .sdr for the
   liquefaction, read from its tables independent of the runner, not that of the ordinary .sdr;
3. compares the project with the owner's sample ``03_参考(V51)：液状化/後処理C1.xml`` (a viaduct: 12 Cases, the 液状化指数 ``20<PL``):
   which Cases are flagged for the liquefaction (``dgEkijoCase2``), the 液状化指数, and the check items of such a Case, which
   are the sample's but for ⑧ 杭の段落し (WebPier makes no check of it).

The record (tests/fixtures/acceptance/pile_liquefaction/record.json) holds the input (kept beside it, with the .sdc and the
.sdc for the liquefaction SOIL-JR returned, so that tests/acceptance can rebuild the projects), the projects (their SHA256 and
the DB1 names), the runners' versions and what was found. Aggre-SE's judgement is not recorded (ADR-0009).

    uv run --project "." --locked python -X utf8 scripts/accept_pile_liquefaction.py [--overwrite]
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

import accept_pile_nonlinear as nonlinear  # noqa: E402

from webpier.core.integrity import content_sha256, dump_json, file_sha256, load_json, sha256  # noqa: E402
from webpier.export.soiljr import parse_sdr  # noqa: E402
from webpier.pipeline import aggrese  # noqa: E402
from webpier.pipeline.fempython import RunnerError  # noqa: E402
from webpier.pipeline.generate import GenerationOptions, generate  # noqa: E402

DEFAULT_INPUT = PROJECT / "tests" / "fixtures" / "inputs" / "pile_seismic.json"
DEFAULT_EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "pile_liquefaction"
SAMPLE_XML = PROJECT.parent / "Batch" / "tests" / "JRSNAP_Ver5.2-L03" / "03_参考(V51)：液状化" / "後処理C1.xml"
LAYER, DE, INDEX = 2, 0.5, "20<PL"
ITEMS = nonlinear.ITEMS
STAGES = (("0711", "線路方向", aggrese.AXIAL, 5, 1), ("0721", "線路直角方向", aggrese.TRANSVERSE, 10, 2))  # Cases, for the liquefaction
OK_MESSAGE = "解析に問題はありませんでした"
RESPONSE_PL = "液状化区分 液状化指数PL(20＜PL)"  # (the lines of the page are read joined by blanks)
AcceptanceError = nonlinear.AcceptanceError


def liquefying(input_path: Path) -> bytes:
    data = load_json(input_path.read_bytes())
    data["outputs"] = {key: key in ITEMS for key in data["outputs"]}
    data["地盤データ"]["層"][LAYER]["De"] = DE
    data["耐震設計条件"]["液状化指数"] = INDEX
    return dump_json(data)


def items_of(xml: str, tag: str) -> list[str]:
    block = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", xml)
    return re.findall(r"<(?:int|boolean)>([^<]*)</(?:int|boolean)>", block[1]) if block else []


def case_items(xml: str, index: int) -> list[int]:
    return [int(items_of(xml, f"dgCaseList_{number}")[index]) for number in range(1, 10)]


def only_liquefied_checked(xml: str, index: int) -> str:
    """The project with ① (復旧性L2) on for the Case *index* and ⑦ (基礎の安定) for it alone, to see its limit values."""
    def rewrite(item: int, keep: list[int]) -> str:
        def fix(match: re.Match) -> str:
            count = len(re.findall(r"<int>", match[0]))
            values = iter(f"<int>{-1 if position in keep else 0}</int>" for position in range(count))
            return re.sub(r"<int>-?\d+</int>", lambda _: next(values), match[0])
        return re.sub(rf"<dgCaseList_{item}>[\s\S]*?</dgCaseList_{item}>", fix, xml)
    others = [(item, [position for position, flag in enumerate(items_of(xml, f"dgCaseList_{item}")) if flag == "-1"])
              for item in range(1, 10)]
    for item, kept in others:
        xml = rewrite(item, kept + [index] if item == 1 else ([index] if item == 7 else kept))
    return xml


def importing(runner: Path, post: Path, work: Path, liquefied_sdr: bytes) -> dict[str, Any]:
    """Run the project of 0711 with only the Case for the liquefaction checked for the stability of the piles: its level 2 limit."""
    folder = work / "limits"
    shutil.copytree(post, folder)
    xml = (folder / "線路方向.xml").read_bytes().decode("cp932")
    index = next(position for position, flag in enumerate(items_of(xml, "dgEkijoCase2")) if flag == "-1")
    (folder / "limits.xml").write_bytes(only_liquefied_checked(xml, index).encode("cp932"))
    report = nonlinear.run(runner, folder / "limits.xml",
                           ["--sdr", str(folder / "杭基礎.sdr"), "--sdr-direction", aggrese.AXIAL,
                            "--sdr-liquefied", str(folder / "杭基礎(液状化時用).sdr")], work)
    with pymupdf.open(stream=report, filetype="pdf") as document:
        text = "".join(page.get_text() for page in document if page.get_text().lstrip().startswith("杭基礎の照査"))
    wet, plain = parse_sdr(liquefied_sdr), parse_sdr((post / "杭基礎.sdr").read_bytes())

    def level2(found) -> float:
        rows = {row[0]: row for row in found.table("橋軸方向", "地震時以外", "設計鉛直支持力の算定").rows}
        return rows["残留鉛直変位(L2)"][6]

    expected, ordinary = f"{level2(wet):.1f}", f"{level2(plain):.1f}"
    return {"case_index": index, "level2_rvd_liquefied": expected, "level2_rvd_ordinary": ordinary,
            "found": expected in text, "ordinary_absent": ordinary not in text}


def the_sample(xml: str) -> dict[str, Any]:
    """The sample's Cases for the liquefaction against WebPier's project of 0711."""
    sample = SAMPLE_XML.read_bytes().decode("cp932")
    flagged = [position for position, flag in enumerate(items_of(sample, "dgEkijoCase2")) if flag == "-1"]
    ours = [position for position, flag in enumerate(items_of(xml, "dgEkijoCase2")) if flag == "-1"]
    sample_items = case_items(sample, flagged[0])
    our_items = case_items(xml, ours[0])
    masked = sample_items[:7] + [0] + sample_items[8:]  # ⑧ 杭の段落し: no check of it
    return {"sample": SAMPLE_XML.name, "sample_flagged_cases": flagged, "sample_index": items_of(sample, "_rbEkijo"),
            "index": items_of(xml, "_rbEkijo"), "sample_items": sample_items, "items": our_items,
            "items_equal_but_for_8": our_items == masked}


def accept(input_path: Path, evidence: Path, overwrite: bool) -> dict[str, Any]:
    record_path = evidence / "record.json"
    if record_path.exists() and not overwrite:
        raise AcceptanceError(f"{record_path} があります（取り直すには --overwrite）")
    runner = aggrese.runner_path()
    failures: list[str] = []
    stages: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="webpier-accept-pile-liquefaction-") as temporary:
        work = Path(temporary)
        (work / "pre").mkdir()
        source = work / "pre" / "input.json"
        source.write_bytes(liquefying(input_path))
        generate(GenerationOptions(source, work / "output", work / "post", overwrite=True))
        post = work / "post"
        for stage, stem, way, count, wet in STAGES:
            report = next((work / "output").glob(f"{stage}_*.pdf"))
            result = load_json(next((work / "output").glob(f"{stage}_*.json")).read_bytes())
            checked = result["seismic_check"]
            folder = load_json((post / f"{stem}_JRSNAP.provenance.json").read_bytes())["nonlinear_analysis"]
            fine = sum(OK_MESSAGE in message["text"] for message in folder["messages"])
            with pymupdf.open(report) as document:
                texts = [page.get_text() for page in document]
            pages = sum(RESPONSE_PL in " ".join(text.split()) for text in texts)
            if len(checked["cases"]) != count or not all(case["aggregated"] for case in checked["cases"]):
                failures.append(f"{stage}: 集計された Case が {len(checked['cases'])} 個です（{count} 個のはず）")
            if fine != count:
                failures.append(f"{stage}: 解析に問題がなかった Case が {fine}/{count} です")
            if pages != wet:
                failures.append(f"{stage}: 液状化の Case の応答値のページが {pages} です（{wet} のはず）")
            xml = (post / f"{stem}.xml").read_bytes().decode("cp932")
            stages[stage] = {
                "project": {"file": f"{stem}.xml", "sha256": file_sha256(post / f"{stem}.xml"),
                            "databases": sorted(path.name for path in (post / f"{stem}_JRSNAP").glob("*.DB1"))},
                "jrsnap": {"folder": f"{stem}_JRSNAP", "sha256": content_sha256(post / f"{stem}_JRSNAP")},
                "report": {"file": report.name, "pages": nonlinear.pages(report)},
                "cases": [case["name"] for case in checked["cases"]], "analysis_ok_messages": fine,
                "liquefaction_cases": [position for position, flag in enumerate(items_of(xml, "dgEkijoCase2"))
                                       if flag == "-1"],
                "liquefaction_response_pages": pages,
                "limits": {key: checked["limits"].get(key) for key in ("direction", "sha256", "liquefied_sha256")}}
        liquefied_sdr = (post / "杭基礎(液状化時用).sdr").read_bytes()
        limits = importing(runner, post, work, liquefied_sdr)
        if not (limits["found"] and limits["ordinary_absent"]):
            failures.append(f"液状化時用の .sdr の制限値が計算書にありません: {limits}")
        sample = the_sample((post / "線路方向.xml").read_bytes().decode("cp932"))
        if not sample["items_equal_but_for_8"] or sample["sample_index"] != sample["index"]:
            failures.append(f"見本の液状化の Case と違います: {sample}")
        kept = {"input.json": source.read_bytes(), "ground.sdc": (post / "杭基礎.sdc").read_bytes(),
                "ground_liquefied.sdc": (post / "杭基礎(液状化時用).sdc").read_bytes()}
    record = {
        "schema_version": 1, "kind": "pile_liquefaction_acceptance",
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": ("液状化する地層（De 0.5）と液状化指数 20<PL の杭基礎の 0711・0721 を本物の JRSNAP・Aggre-SE で生成し、"
                   "全 Case の集計と解析の完了、液状化の Case の扱い、液状化時用の .sdr の制限値の取り込み（液状化の Case だけを"
                   "杭基礎の照査にして、安定レベル2の Rvd が .sdr の表の値と同じこと）、見本 後処理C1.xml の液状化の Case との"
                   "比較（⑧を除いて同じ）を確かめた。判定は扱わない。"),
        "seismic_check_judged": False,
        "input": {"path": _relative(input_path), "sha256": file_sha256(input_path), "kept": "input.json",
                  "kept_sha256": sha256(kept["input.json"])},
        "runner": {"path": str(runner), "sha256": file_sha256(runner)},
        "helpers": {_relative(Path(__file__)): file_sha256(Path(__file__))},
        "stages": stages, "limits_import": limits, "sample": sample, "accepted": not failures, "failures": failures}
    if failures:
        raise AcceptanceError("受入に失敗しました: " + "; ".join(failures))
    evidence.mkdir(parents=True, exist_ok=True)
    for name, content in kept.items():
        (evidence / name).write_bytes(content)
    record_path.write_bytes(dump_json(record))
    return record


def _relative(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


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
                                                                          "ok": item["analysis_ok_messages"],
                                                                          "pages": item["liquefaction_response_pages"]}
                                                                 for stage, item in record["stages"].items()},
                      "limits_import": record["limits_import"], "sample": record["sample"]["items_equal_but_for_8"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
