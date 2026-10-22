"""Real-runner acceptance of the データ確認図 and the 荷重図 of 0710 / 0720 in JRSNAP 5.2-L03 (decisions 50, 51).

For each direction the NDU is rebuilt from the input exactly as ``python -m webpier`` writes it (``export_bytes``),
and the (basic case, combination) of each load diagram page as a generation asks for them (``figure_cases``). The
real runner (``STRUCTURAL_MCP_JRSNAP_RUNNER`` of the environment or ``.env``: JRSNAPHeadless ``figures``) draws the
データ確認図 and the 荷重図 of that NDU, and the pages WebPier receives (``draw_figures``) are measured with pymupdf:
the size of every page, and for each load diagram page its CASE title, any page number, the coloured pixels and
whether it prints 480. Nothing is recorded unless the pages are what the report takes: at least 5 データ確認図 pages,
one load diagram page per case in case order, A4 portrait, black and white, without page numbers, and the 480 of the
transverse CASE-5 and CASE-6.

The record goes to tests/fixtures/acceptance/jrsnap_figures/record.json; tests/acceptance/
test_jrsnap_figures_acceptance.py checks that it still belongs to the current generator. No analysis is run.

    uv run --project "." --locked python -X utf8 scripts/accept_jrsnap_figures.py [--overwrite]
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
import sys
from typing import Any

import pymupdf

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.core.errors import InputError  # noqa: E402
from webpier.core.integrity import canonical_sha256, dump_json, load_json, sha256  # noqa: E402
from webpier.inputs import parse_input  # noqa: E402
from webpier.pipeline import jrsnap  # noqa: E402
from webpier.pipeline.fempython import RunnerError  # noqa: E402
from webpier.pipeline.generate import export_bytes, figure_cases  # noqa: E402
from webpier.pipeline.runtime import dependency_hashes  # noqa: E402
from webpier.pipeline.stages import STAGES  # noqa: E402

DEFAULT_INPUT = PROJECT / "tests" / "fixtures" / "inputs" / "current.json"
DEFAULT_EVIDENCE = PROJECT / "tests" / "fixtures" / "acceptance" / "jrsnap_figures"
DIRECTIONS = ("0710", "0720")
PRODUCT = "5.2-L03"
A4 = (595.3, 841.9)  # portrait, pt
A4_TOLERANCE = 0.5
MINIMUM_DATA_CHECK_PAGES = 5  # one page at least for each figure of DATA_CHECK_FIGURES
WITH_480 = {"0720": (5, 6)}  # the cases whose load diagram must print 480 (the up and the down track of 0720)
DPI = 100
COLOUR = 30  # max - min of R, G, B above which a pixel is coloured
PAGE_NUMBER = re.compile(r"\b\d+\s*/\s*\d+\b")
DATE = re.compile(r"\d{4}/\d{2}/\d{2}")


class AcceptanceError(RuntimeError):
    """The acceptance did not hold; no record is written."""


def _relative(path: Path) -> str:
    return Path(path).resolve().relative_to(PROJECT).as_posix()


def _implementation() -> str:
    return canonical_sha256({str(path): digest for path, digest in dependency_hashes().items()})


def _size(page: Any) -> list[float]:
    return [round(page.rect.width, 1), round(page.rect.height, 1)]


def _is_a4_portrait(page: Any) -> bool:
    return abs(page.rect.width - A4[0]) <= A4_TOLERANCE and abs(page.rect.height - A4[1]) <= A4_TOLERANCE


def _title(text: str) -> str:
    """The first line beginning with ``CASE-``, its blanks collapsed to one space ("" when there is none)."""
    for line in text.splitlines():
        if line.strip().startswith("CASE-"):
            return " ".join(line.split())
    return ""


def _page_numbers(text: str) -> list[str]:
    """What looks like a page number ("1/8", "2 / 9"), but not a part of a date (2026/10/18)."""
    dates = [match.span() for match in DATE.finditer(text)]
    return [match.group() for match in PAGE_NUMBER.finditer(text)
            if not any(start < match.end() and match.start() < end for start, end in dates)]


def _coloured_pixels(page: Any) -> int:
    pixmap = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csRGB, alpha=False)
    samples = pixmap.samples
    if pixmap.n != 3 or len(samples) != pixmap.width * pixmap.height * 3:
        raise AcceptanceError(f"画素を RGB で読めません（n={pixmap.n}）")
    return sum(1 for red, green, blue in zip(samples[0::3], samples[1::3], samples[2::3])
               if max(red, green, blue) - min(red, green, blue) > COLOUR)


def measure_data_check(content: bytes) -> dict[str, Any]:
    with pymupdf.open(stream=content, filetype="pdf") as document:
        pages = list(document)
        sizes = [_size(page) for page in pages]
        portrait = [_is_a4_portrait(page) for page in pages]
    return {"pages": len(sizes), "sizes": sizes, "a4_portrait": portrait}


def measure_load_diagram(content: bytes, load_cases: tuple[tuple[int, int], ...]) -> list[dict[str, Any]]:
    measured = []
    with pymupdf.open(stream=content, filetype="pdf") as document:
        if len(document) != len(load_cases):
            raise AcceptanceError(f"荷重図が {len(document)} ページです（ケースは {len(load_cases)}）")
        for number, (page, (case, combination)) in enumerate(zip(document, load_cases), start=1):
            text = page.get_text()
            measured.append({
                "page": number, "case": case, "combination": combination, "title": _title(text),
                "size": _size(page), "a4_portrait": _is_a4_portrait(page), "colored_pixels": _coloured_pixels(page),
                "page_numbers": _page_numbers(text), "has_480": "480" in text,
            })
    return measured


def check(stage: str, data_check: dict[str, Any], load_diagram: list[dict[str, Any]],
          load_cases: tuple[tuple[int, int], ...]) -> None:
    """Stop (AcceptanceError) unless the pages are what the report of *stage* takes."""
    if data_check["pages"] < MINIMUM_DATA_CHECK_PAGES:
        raise AcceptanceError(f"{stage}: データ確認図が {data_check['pages']} ページです（{MINIMUM_DATA_CHECK_PAGES} 以上）")
    if not all(data_check["a4_portrait"]):
        raise AcceptanceError(f"{stage}: データ確認図に A4縦でないページがあります {data_check['sizes']}")
    if len(load_diagram) != len(load_cases):
        raise AcceptanceError(f"{stage}: 荷重図が {len(load_diagram)} ページです（ケースは {len(load_cases)}）")
    for page in load_diagram:
        where = f"{stage}: 荷重図 {page['page']} ページ（CASE-{page['case']}）"
        if not page["title"].startswith(f"CASE-{page['case']} "):
            raise AcceptanceError(f"{where} の表題が違います: {page['title']!r}")
        if not page["a4_portrait"]:
            raise AcceptanceError(f"{where} が A4縦ではありません: {page['size']}")
        if page["colored_pixels"]:
            raise AcceptanceError(f"{where} に色の付いた画素が {page['colored_pixels']} あります")
        if page["page_numbers"]:
            raise AcceptanceError(f"{where} にページ番号があります: {page['page_numbers']}")
    for case in WITH_480.get(stage, ()):
        if not any(page["case"] == case and page["has_480"] for page in load_diagram):
            raise AcceptanceError(f"{stage}: 荷重図の CASE-{case} に 480 がありません")


def accept(input_path: Path, evidence: Path, overwrite: bool) -> dict[str, Any]:
    record_path = evidence / "record.json"
    if record_path.exists() and not overwrite:
        raise AcceptanceError(f"受入記録が既にあります（--overwrite で作り直します）: {record_path}")
    runner = jrsnap.runner_path()
    data = input_path.read_bytes()
    pier = parse_input(load_json(data))
    implementation = _implementation()
    runner_identity: dict[str, Any] | None = None
    stages: dict[str, Any] = {}
    for stage in DIRECTIONS:
        export = next(item for item in STAGES.get(stage).exports if item.kind == "jrsnap")
        ndu = export_bytes(pier, stage, "jrsnap")
        cases = figure_cases(pier, stage)
        figures = jrsnap.draw_figures(export.file_name, ndu, runner, cases)
        product = (figures.summary.get("jrsnap") or {}).get("product")
        if figures.engine_version.startswith("fake") or product != PRODUCT:
            raise AcceptanceError(f"{stage}: 本物の JRSNAP {PRODUCT} の runner ではありません"
                                  f"（engineVersion {figures.engine_version!r}、product {product!r}）")
        identity = {"engine_version": figures.engine_version, "product": product,
                    "assemblyVersion": figures.summary["jrsnap"].get("assemblyVersion")}
        if runner_identity is not None and identity != runner_identity:
            raise AcceptanceError(f"{stage}: runner の版が段階で違います {identity} {runner_identity}")
        runner_identity = identity
        data_check = measure_data_check(figures.data_check)
        load_diagram = measure_load_diagram(figures.load_diagram, figures.load_cases)
        check(stage, data_check, load_diagram, cases)
        stages[stage] = {
            "ndu": {"file": export.file_name, "sha256": sha256(ndu)},
            "load_cases": [[case, combination] for case, combination in figures.load_cases],
            "data_check": {"figures": list(jrsnap.DATA_CHECK_FIGURES),
                           "combination": jrsnap.DATA_CHECK_COMBINATION,
                           "pages": data_check["pages"], "sizes": data_check["sizes"]},
            "load_diagram": [{key: page[key] for key in ("page", "case", "combination", "title", "size",
                                                         "colored_pixels", "page_numbers", "has_480")}
                             for page in load_diagram],
            "runner_summary": figures.summary,
        }
    if sha256(input_path.read_bytes()) != sha256(data) or _implementation() != implementation:
        raise AcceptanceError("受入中に入力・プログラムが変わりました")
    now = datetime.now().astimezone()
    record = {
        "schema_version": 1, "kind": "jrsnap_figures_acceptance", "date": now.date().isoformat(),
        "verified_at": now.isoformat(timespec="seconds"),
        "method": ("WebPier が 0710・0720 で書く NDU を本物の JRSNAP 5.2-L03 の runner（JRSNAPHeadless の figures）に渡して"
                   "データ確認図と荷重図を描かせ、WebPier が受け取るページ（draw_figures）を pymupdf で測った。"),
        "analysis_run": False,
        "runner": runner_identity,
        "input": {"path": _relative(input_path), "sha256": sha256(data)},
        "implementation_sha256": implementation,
        "stages": stages,
    }
    evidence.mkdir(parents=True, exist_ok=True)
    record_path.write_bytes(dump_json(record))
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="入力JSON（既定: Example2 の設定の current.json）")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE, help="受入記録（record.json）の出力先")
    parser.add_argument("--overwrite", action="store_true", help="既存の record.json を置き換える")
    args = parser.parse_args(argv)
    try:
        record = accept(args.input.resolve(), args.evidence.resolve(), args.overwrite)
    except (AcceptanceError, RunnerError, InputError, OSError, ValueError) as exc:
        print(f"受入未完了: {exc}", file=sys.stderr)
        return 2
    print(f"runner: {record['runner']['engine_version']}（JRSNAP {record['runner']['product']}、"
          f"{record['runner']['assemblyVersion']}）")
    for stage, measured in record["stages"].items():
        print(f"{stage} {measured['ndu']['file']}: データ確認図 {measured['data_check']['pages']} ページ、"
              f"荷重図 {len(measured['load_diagram'])} ページ")
        for page in measured["load_diagram"]:
            print(f"  {page['page']}: 組合せ {page['combination']}  {page['title']}")
    print(f"受入記録（解析は実行していません）: {args.evidence.resolve() / 'record.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
