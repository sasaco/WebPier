"""Real-app acceptance of the 杭の構造細目 of a 場所打ち杭 and its cut-off (decision 98).

``tests/fixtures/inputs/pile_cutoff.json`` (pile_seismic.json, the SOIL-JR 5.2 sample E with two rows of piles along the track and
three across it, with a cut-off of the main bars 6.0 m below the head) with 0400, 0500, 0600, 0710, 0711, 0720 and 0721. The
acceptance

1. generates them with ``python -m webpier`` and the real runners (SOIL-JR and the analyses of JRSNAP, Aggre-SE);
2. reads 1/β of each direction from the .sdc SOIL-JR returned and finds it, rounded to two decimals, in the shear span ratio of
   0400, and the pile's figure in 4.1 and in ``post/配筋図.dxf``;
3. reads Pvmax again from the files the runners returned, with a reading of its own (the pickup of 復旧性L2 of Aggre-SE, the first
   element of each pile row in the NDU and the piles of the row in the project's 段落し情報, ``read_pik`` and ``pile_heads`` here,
   not WebPier's), and finds it in 0711 / 0721;
4. checks that the project gives Aggre-SE ⑧ with the 段落し情報 of the input and the 杭頭定着長 of 0400, on the Cases of αf 1.0, and
   that the report of 0711 / 0721 ends with Aggre-SE's 杭の段落とし計算書 after WebPier's page.

The record (tests/fixtures/acceptance/pile_detailing/record.json) holds the input, the 1/β and Pvmax found, the pages and the
SHA256 of each file; the pickup, the NDU, the project and the .sdc are kept beside it so that tests/acceptance can read them again
with WebPier's reading and no runner. Aggre-SE's judgement of ⑧ is not recorded (ADR-0009).

    uv run --project "." --locked python -X utf8 scripts/accept_pile_detailing.py [--overwrite]
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
from webpier.export.soiljr import parse_sdc  # noqa: E402
from webpier.pipeline.fempython import RunnerError  # noqa: E402
from webpier.pipeline.generate import GenerationOptions, generate  # noqa: E402

DEFAULT_INPUT = PROJECT / "tests" / "fixtures" / "inputs" / "pile_cutoff.json"
DEFAULT_EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "pile_detailing"
DIRECTIONS = (("線路方向", "0711_線路方向非線形解析", "橋軸方向"), ("線路直角方向", "0721_線路直角方向非線形解析", "直角方向"))
SEISMIC_PICKUP = 2
MINIMUM = "杭頭反力の最大値から定める最小鉄筋量"


class AcceptanceError(Exception):
    pass


def read_pik(content: bytes) -> dict[tuple[int, str, int, str], tuple[float, float]]:
    """(pickup, focus, member, point) → (largest Nd, smallest Nd)."""
    found = {}
    for line in content.decode("utf-8-sig", errors="replace").splitlines():
        cells = line.split()
        if len(cells) == 13 and cells[1] in ("M", "S", "N"):
            found[(int(cells[0]), cells[1], int(cells[2]), cells[5])] = (float(cells[9]), float(cells[12]))
    return found


def pile_heads(ndu: bytes) -> list[int]:
    """The first element of each pile row (the second field of KGInfo<n>, as accept_pile_footing reads it), in the NDU's order."""
    return [int(match[1]) for line in ndu.decode("cp932").split("\r\n")
            if (match := re.match(r"KGInfo\d+=\d+,(\d+),", line))]


def tag_items(xml: str, tag: str) -> list[str]:
    block = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", xml)
    return re.findall(r"<(?:int|float)>([^<]*)</(?:int|float)>", block[1]) if block else []


def scalar(xml: str, tag: str) -> str:
    return re.search(rf"<{tag}>([^<]*)</{tag}>", xml)[1]


def texts(path: Path) -> list[str]:
    with pymupdf.open(path) as document:
        return [" ".join(page.get_text().split()) for page in document]


def check_direction(words: str, report: str, post: Path, output: Path, evidence: Path, head_anchorage: float,
                    data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    for name in (f"{words}_Aggre-SE.pik", f"{words}.ndu", f"{words}.xml"):
        shutil.copyfile(post / name, evidence / name)
    xml = (post / f"{words}.xml").read_bytes().decode("cp932")
    firsts, piles = tag_items(xml, "dgMemberFirst"), tag_items(xml, "dgMemberNumber")
    heads = pile_heads((post / f"{words}.ndu").read_bytes())
    if [int(first) for first in firsts] != heads:
        failures.append(f"{words}.xml の段落し情報の要素 {firsts} が NDU の杭頭の要素 {heads} と違います")
    pik = read_pik((post / f"{words}_Aggre-SE.pik").read_bytes())
    found = max(-pik[(SEISMIC_PICKUP, "N", head, "ITAN")][1] / float(count) for head, count in zip(heads, piles))
    result = load_json((output / f"{report}.json").read_bytes())["result"]["minimum"]
    if abs(result["pvmax"] - found) > 0.006:
        failures.append(f"{report}: Pvmax {result['pvmax']['value']} がピックアップの値 {found:.3f} と違います")
    cut = data["鉄筋"]["杭"]["cutoff"]
    expected = {"_D1": cut["main_bars"]["diameter_mm"], "_n1": cut["main_bars"]["count"], "_PileHeadLength": head_anchorage,
                "_ParagraphLength": cut["cutoff_length_mm"], "_PileMidLength": cut["cutoff_anchorage_mm"],
                "MudCoefficient": cut["margin_ratio"]["moment"], "VudCoefficient": cut["margin_ratio"]["shear"]}
    for tag, value in expected.items():
        if float(scalar(xml, tag)) != float(value):
            failures.append(f"{words}.xml の {tag} {scalar(xml, tag)} が {value} ではありません")
    eighth = re.findall(r"<int>([^<]*)</int>", re.search(r"<dgCaseList_8>([\s\S]*?)</dgCaseList_8>", xml)[1])
    pages = texts(output / f"{report}.pdf")
    minimum = [index for index, text in enumerate(pages) if MINIMUM in text]
    anchor = [index for index, text in enumerate(pages) if "段落" in text and index > (minimum[-1] if minimum else len(pages))]
    if len(minimum) != 1 or not anchor:
        failures.append(f"{report}: 「{MINIMUM}」の頁（{minimum}）と、その後の杭の段落とし計算書（{anchor}）がそろいません")
    return {"pvmax": result["pvmax"], "pvmax_found": round(found, 3), "rows": firsts, "piles": piles,
            "check_8": [index for index, flag in enumerate(eighth) if flag == "-1"], "pages": len(pages),
            "minimum_page": minimum, "anchor_pages": anchor,
            "files": {name: file_sha256(evidence / name) for name in (f"{words}_Aggre-SE.pik", f"{words}.ndu", f"{words}.xml")}}, \
        failures


def accept(input_path: Path, evidence: Path, overwrite: bool) -> dict[str, Any]:
    record_path = evidence / "record.json"
    if record_path.exists() and not overwrite:
        raise AcceptanceError(f"{record_path} があります（取り直すには --overwrite）")
    failures: list[str] = []
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="webpier-accept-pile-detailing-") as temporary:
        work = Path(temporary)
        (work / "pre").mkdir()
        source = work / "pre" / "input.json"
        shutil.copyfile(input_path, source)
        data = load_json(input_path.read_bytes())
        generate(GenerationOptions(source, work / "output", work / "post", overwrite=True))
        output, post = work / "output", work / "post"
        shutil.copyfile(post / "杭基礎.sdc", evidence / "ground.sdc")
        springs = parse_sdc((post / "杭基礎.sdc").read_bytes())
        detailing = load_json((output / "0400_照査の前提.json").read_bytes())["result"]["pile"]
        betas = {name: springs.direction(sdc).inverse_beta for name, _, sdc in DIRECTIONS}
        printed = {direction: span["inverse_beta"] for span in detailing["hoops"]["spans"]
                   for direction in span["directions"]}
        for name, value in betas.items():
            if abs(printed.get(name, -1) - value) > 0.005:
                failures.append(f"0400: {name}の 1/β {printed.get(name)} が .sdc の {value} と違います")
        report = " ".join(texts(output / "0400_照査の前提.pdf"))
        for word in ("4.5 杭の構造細目", "杭頭定着長", MINIMUM):
            if word not in report:
                failures.append(f"0400: 「{word}」がありません")
        if "杭（杭頭から下の側面と断面）".encode("utf-8") not in (post / "配筋図.dxf").read_bytes():
            failures.append("配筋図.dxf に杭の図がありません")
        head_anchorage = detailing["anchorage"]["length"]
        directions = {}
        for words, report_name, _ in DIRECTIONS:
            found, missed = check_direction(words, report_name, post, output, evidence, head_anchorage, data)
            directions[words] = found
            failures += missed
    record = {
        "schema_version": 1, "kind": "pile_detailing_acceptance",
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": ("本物の SOIL-JR・JRSNAP・Aggre-SE の runner で場所打ち杭（段落しあり）の 0400・0711・0721 を生成し、"
                   "1/β を .sdc から、Pvmax を Aggre-SE のピックアップと NDU から別の読み方で読み直して照合し、"
                   "⑧ の段落し情報と杭の段落とし計算書の頁を確かめた。⑧ の判定は扱わない。"),
        "aggrese_judged": False,
        "input": {"path": str(input_path.relative_to(PROJECT)).replace("\\", "/"), "sha256": file_sha256(input_path)},
        "inverse_beta": betas, "head_anchorage": head_anchorage, "ground_sdc_sha256": file_sha256(evidence / "ground.sdc"),
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
    print(json.dumps({"accepted": record["accepted"], "inverse_beta": record["inverse_beta"],
                      "head_anchorage": record["head_anchorage"],
                      "directions": {name: {key: item[key] for key in ("pvmax", "pvmax_found", "check_8", "minimum_page",
                                                                        "anchor_pages", "pages")}
                                     for name, item in record["directions"].items()}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
