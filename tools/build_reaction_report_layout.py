"""Extract the 0600 worksheet's print layout once, during development.

Run from the repository root with the project's dev environment.  The deployed
renderer reads the generated JSON and does not open either reference artifact.
Page starts include the automatic breaks visible in the reference PDF, as well
as the workbook's manual breaks.  Row/column numbers here are Excel's 1-based
numbers; JSON drawing coordinates are points measured from the page top.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import xlrd
import pymupdf


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Example橋脚" / "0600_上部工反力.xls"
DESTINATION = ROOT / "P7橋脚" / "src" / "assets" / "reaction_report_layout.json"
SCALE = 14.28 / 15.75
LEFT = 58.08
TOP = 71.4
PRINT_PAGES = {
    "死荷重": ([2, 49], 52),
    "橋脚自重": ([14, 60, 108, 134, 182, 231, 280, 303], 335),
    "列車荷重": ([17, 61, 89], 131),
    "線路荷重": ([9, 56, 75, 123, 171, 173, 221, 228, 276, 281, 329,
                  339, 387, 393, 441, 443, 491, 498, 540], 555),
    "直角荷重": ([15, 68, 98, 145, 180], 193),
}
DIAGRAM_REGIONS = {
    3: [[70, 132, 555, 358], [70, 448, 555, 674]],
    4: [[70, 203, 555, 348], [70, 610, 555, 748]],
    5: [[70, 211, 555, 421]],
    6: [[70, 315, 555, 466]],
    7: [[70, 112, 555, 290], [70, 612.7, 555, 773]],
    8: [[70, 70, 555, 104], [70, 398.5, 555, 589]],
    9: [[70, 185.7, 555, 376]],
    11: [[70, 176, 555, 290]],
    34: [[70, 175, 555, 291]],
}
DYNAMIC_TEXT = {"列車荷重": {"J34", "J36", "J38", "J40"},
                "直角荷重": {"K87", "K94"}}
# The reference workbook leaves unused bearing slots blank. They still are
# writable calculation cells: adding a G3--G10 load must make it into the PDF.
DYNAMIC_INPUT = {
    "死荷重": {f"{column}{row}" for first in (21, 29, 39, 47)
               for row in range(first, first + 5)
               for column in ("M", "P", "S", "V", "Y")},
}


def rounded(value: float) -> float:
    return round(value, 4)


def main() -> None:
    book = xlrd.open_workbook(str(SOURCE), formatting_info=True)
    evidence = json.loads((ROOT / "Example橋脚/wiki/evidence/cell-formulas.json").read_text(encoding="utf-8"))
    formulas = evidence["0600_上部工反力"]
    reference = pymupdf.open(ROOT / "Example橋脚/output/0600_上部工反力.pdf")
    constants = {}
    for sheet in book.sheets():
        constants[sheet.name] = {}
        for r in range(sheet.nrows):
            for c in range(sheet.ncols):
                address = f"{xlrd.formula.colname(c)}{r + 1}"
                value = sheet.cell_value(r, c)
                if value != "" and address not in formulas[sheet.name] and address not in DYNAMIC_TEXT.get(sheet.name, set()):
                    constants[sheet.name][address] = value
    fonts = []
    for font in book.font_list:
        colour = book.colour_map.get(font.colour_index) or (0, 0, 0)
        fonts.append({"name": font.name, "size": font.height / 20 * .99,
                      "bold": bool(font.bold), "italic": bool(font.italic),
                      "escapement": font.escapement, "colour": list(colour)})
    styles = []
    for xf in book.xf_list:
        styles.append({"font": xf.font_index,
                       "format": book.format_map[xf.format_key].format_str,
                       "horizontal": xf.alignment.hor_align,
                       "vertical": xf.alignment.vert_align,
                       "wrap": bool(xf.alignment.text_wrapped),
                       "indent": xf.alignment.indent_level,
                       "shrink": bool(xf.alignment.shrink_to_fit),
                       "rotation": xf.alignment.rotation})
    pages = []
    for sheet in book.sheets():
        starts, final_row = PRINT_PAGES[sheet.name]
        y = [0.0]
        for r in range(final_row):
            row = sheet.rowinfo_map.get(r)
            height = row.height if row else sheet.default_row_height
            # Excel's PDF printer rounds each row to its 600 dpi (0.12 pt)
            # device grid. Keeping fractional row heights accumulates >3 pt
            # drift by the last table on page one.
            printed_height = math.floor((height / 20 * SCALE + 1e-7) / .12) * .12
            y.append(y[-1] + (0 if row and row.hidden else printed_height))
        x = [LEFT]
        for c in range(1, 34):
            column = sheet.colinfo_map.get(c)
            x.append(x[-1] + (0 if column and column.hidden else 14.52 * (column.width if column else 672) / 672))
        merged = {}
        hidden = set()
        for r0, r1, c0, c1 in sheet.merged_cells:
            merged[r0, c0] = (r1, c1)
            hidden.update((r, c) for r in range(r0, r1) for c in range(c0, c1) if (r, c) != (r0, c0))
        for index, first in enumerate(starts):
            last = starts[index + 1] - 1 if index + 1 < len(starts) else final_row
            page_number = len(pages) + 1
            page = {"page": page_number, "sheet": sheet.name, "row_start": first,
                    "row_end": last, "x_left": LEFT, "y_top": TOP,
                    "scale": SCALE, "diagram_regions": DIAGRAM_REGIONS.get(page_number, []),
                    "cells": [], "rules": [], "paths": []}
            # Workbook drawing objects (braces and fraction bars) are not cell
            # borders. Keep their print-time vectors, excluding every diagram.
            for drawing in reference[page_number - 1].get_drawings():
                bounds = drawing["rect"]
                # The reference has an empty drawing rectangle over H285's
                # volume. Its narrow outline would cross the recalculated
                # digits; the actual merged-cell value replaces that blank.
                if page_number == 9 and all(abs(actual - expected) < .2 for actual, expected in
                                             zip(bounds, (168.6, 143.038, 197.64, 156.598))):
                    continue
                if any(bounds.x0 <= right + .2 and bounds.x1 >= left - .2 and
                       bounds.y0 <= bottom + .2 and bounds.y1 >= top - .2
                       for left, top, right, bottom in page["diagram_regions"]):
                    continue
                items = []
                for item in drawing["items"]:
                    op = item[0]
                    if op == "re":
                        items.append([op, *map(rounded, item[1])])
                    elif op in ("l", "c"):
                        items.append([op, *[list(map(rounded, point)) for point in item[1:]]])
                    elif op == "qu":
                        items.append([op, *[list(map(rounded, point)) for point in item[1]]])
                page["paths"].append({"items": items, "fill": drawing.get("fill"),
                                      "colour": drawing.get("color"), "width": drawing.get("width"),
                                      "close": drawing.get("closePath", False),
                                      "even_odd": drawing.get("even_odd", True)})
            rules = set()
            for r in range(first - 1, min(last, sheet.nrows)):
                if y[r + 1] == y[r]:
                    continue
                for c in range(1, min(34, sheet.ncols)):
                    cell = sheet.cell(r, c)
                    address = f"{xlrd.formula.colname(c)}{r + 1}"
                    is_dynamic = (address in formulas.get(sheet.name, {})
                                  or address in DYNAMIC_TEXT.get(sheet.name, set())
                                  or address in DYNAMIC_INPUT.get(sheet.name, set()))
                    xf = book.xf_list[cell.xf_index]
                    left, right = x[c - 1], x[c]
                    top, bottom = TOP + y[r] - y[first - 1], TOP + y[r + 1] - y[first - 1]
                    for edge, points in (("left", (left, top, left, bottom)),
                                         ("right", (right, top, right, bottom)),
                                         ("top", (left, top, right, top)),
                                         ("bottom", (left, bottom, right, bottom))):
                        line_style = getattr(xf.border, edge + "_line_style")
                        if line_style:
                            rules.add((*map(rounded, points), line_style))
                    if (r, c) in hidden or not cell.value:
                        # Numeric zero is a real printed value.
                        if (r, c) in hidden or (cell.ctype != xlrd.XL_CELL_NUMBER and not is_dynamic):
                            continue
                    r1, c1 = merged.get((r, c), (r + 1, c + 1))
                    right = x[min(c1, 34) - 1]
                    bottom = TOP + y[min(r1, last)] - y[first - 1]
                    item = {"address": address, "box": list(map(rounded, (left, top, right, bottom))),
                            "style": cell.xf_index}
                    if is_dynamic:
                        item["dynamic"] = True
                        if cell.value == "" and address in DYNAMIC_INPUT.get(sheet.name, set()):
                            item["blank_zero"] = True
                    else:
                        item["value"] = cell.value
                    runs = sheet.rich_text_runlist_map.get((r, c))
                    if runs:
                        item["runs"] = runs
                    page["cells"].append(item)
            page["rules"] = sorted(rules)
            pages.append(page)
    result = {"schema_version": 1, "page_size": [595, 842],
              "source": "Example橋脚/0600_上部工反力.xls",
              "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "description": "Static print layout; formula cached values deliberately omitted.",
              "fonts": fonts, "styles": styles, "formulas": formulas,
              "constants": constants, "pages": pages}
    DESTINATION.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(pages)} pages, {sum(len(p['cells']) for p in pages)} cells: {DESTINATION}")


if __name__ == "__main__":
    main()
