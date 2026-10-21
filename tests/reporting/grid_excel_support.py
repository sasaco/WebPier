"""The Excel comparison of the reports' grid Excel workbooks (``webpier.reporting.workbook``, published in export/).

``compare_with_excel`` runs GridLayoutPdf's ``scripts/compare_xlsx_pdf.py`` (loaded from a GridLayoutPdf checkout,
``glp_checkout``, so GridLayoutPdf is not changed) and ``accepted_failures`` judges its result: every check must pass, and the
only text pieces allowed outside their tolerance are the limitation the user accepted for GridLayoutPdf's grid Excel
(Gate 3, 2026-10-20): the last character of a body line that Excel's 2.4 pt cell padding clips — a line that fills
the body's width, or one whose cells the writer recorded as ``text_clipped`` (its cells cannot grow enough).
"""

from __future__ import annotations

from collections.abc import Sequence
import importlib.util
import os
from pathlib import Path
import re
import sys
import tomllib

from gridlayoutpdf import ScenePage

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path("scripts") / "compare_xlsx_pdf.py"
CHECKS = ("opens_without_repair", "readback", "strict", "no_hashes", "page_count", "page_size", "positions",
          "no_extra_text")


def glp_checkout() -> Path:
    """The GridLayoutPdf checkout: the pyproject's path dependency if it has one, else ``GRIDLAYOUTPDF_CHECKOUT``
    (default ``C:/Users/sasai/Documents/GridLayoutPdf``), because the release wheel of the url dependency has no
    scripts."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    source = data["tool"]["uv"]["sources"]["gridlayoutpdf"]
    if "path" in source:
        return Path(source["path"])
    return Path(os.environ.get("GRIDLAYOUTPDF_CHECKOUT", "C:/Users/sasai/Documents/GridLayoutPdf"))


def comparison():
    """GridLayoutPdf's comparison script as a module, or None when the checkout has none."""
    script = glp_checkout() / SCRIPT
    if not script.is_file():
        return None
    name = "compare_xlsx_pdf"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, script)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def compare_with_excel(module, name: str, sheet: str, pages: Sequence[ScenePage], out: Path) -> tuple[int, dict]:
    """Write the pages as a strict workbook (``out/workbook.xlsx``, as ``render_xlsx`` writes it for the sheet *sheet*)
    and a library PDF, print the workbook with Excel and compare."""
    target = module.Target(name, sheet, lambda: (tuple(pages), None))
    return module.run(target, out, strict=True)


def _clipped_texts(report: dict) -> dict[int, list[str]]:
    """Per page, the texts the grid Excel writer recorded as text_clipped (their cells cannot hold them in
    Excel's print, so their end may be cut: the accepted limitation), without whitespace."""
    found: dict[int, list[str]] = {}
    for record in report.get("xlsx", {}).get("texts_clipped", ()):
        text = re.match(r"^(['\"])(.*)\1 at [A-Z]+\d+: ", record["detail"])
        if text is not None:
            found.setdefault(record["page"], []).append(re.sub(r"\s+", "", text.group(2)))
    return found


def _accepted(item: dict, body_right: float, pitch_x: float, clipped: Sequence[str]) -> bool:
    """A piece outside its tolerance only because Excel clipped its last character, on a body line that fills
    the body's width or whose cells the writer recorded as text_clipped."""
    return (item["failures"] == ["clipped"] and item["clipped_glyphs"] == [item["text"][-1]]
            and (item["library_box"][2] >= body_right - pitch_x / 2
                 or any(text.endswith(item["text"]) for text in clipped)))


def accepted_failures(report: dict, pages: Sequence[ScenePage]) -> list[str]:
    """What fails in the comparison *report* beyond the accepted limitation (empty: the report passes)."""
    checks = report.get("checks", {})
    failures = [f"check {name}: {checks.get(name)}" for name in CHECKS if name != "positions" and not checks.get(name)]
    if not report.get("checks_complete"):
        failures.append("checks incomplete")
    clipped = _clipped_texts(report)
    summary = report.get("summary", {})
    if not summary or summary.get("pieces", 0) + summary.get("fr021_vertical_merge", {}).get("pieces", 0) == 0:
        failures.append("no text piece")
    for page in report.get("pages", ()):
        grid = pages[page["page"] - 1].profile.grid
        body_right = grid.origin_x + grid.columns * grid.pitch_x
        where = f"page {page['page']}"
        if page["missing"]:
            failures.append(f"{where}: missing {[item['text'] for item in page['missing']]}")
        if page["clipped_out_count"]:
            failures.append(f"{where}: clipped out {[item['char'] for item in page['clipped_out']]}")
        if page["pieces"] + page["fr021_vertical_merge"]["pieces"] == 0 and page["text_commands"]:
            failures.append(f"{where}: text without pieces")
        for item in page["outside"]:
            if not _accepted(item, body_right, grid.pitch_x, clipped.get(page["page"], ())):
                failures.append(f"{where}: {item['text']!r} {item['failures']} dx {item['dx_pt']} dy {item['dy_pt']}")
    return failures
