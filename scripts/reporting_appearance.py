"""Independent PDF appearance measurements; never a report authoring dependency.

The reference corpus supplies appearance only. Values in these measurements are
not engineering or calculation expectations. Coordinates use PDF points from
the page's top-left and line coordinates describe the centre of visible ink.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import pymupdf


@dataclass(frozen=True)
class TextSample:
    """A semantically selected native span, independently extracted from PDF."""

    text: str
    font: str
    size: float
    x: float
    baseline: float
    color: int
    page: int = 1


@dataclass(frozen=True)
class Rule:
    """A visible horizontal or vertical rule, including filled thin rectangles."""

    axis: str
    coordinate: float
    start: float
    end: float
    width: float


@dataclass(frozen=True)
class InkBand:
    """Centre and actual painted width along one independent cross-section."""

    coordinate: float
    width: float


def canonical_font(name: str) -> str:
    """Strip a PDF subset prefix, but never conflate proportional/mono faces."""

    return re.sub(r"^[A-Z]{6}\+", "", name)


def text_samples(page: pymupdf.Page) -> list[TextSample]:
    return [
        TextSample(
            span["text"], canonical_font(span["font"]), float(span["size"]),
            float(span["origin"][0]), float(span["origin"][1]),
            int(span["color"]), page.number + 1,
        )
        for block in page.get_text("dict")["blocks"] if "lines" in block
        for line in block["lines"] for span in line["spans"]
    ]


def native_rules(page: pymupdf.Page) -> list[Rule]:
    """Extract actual rule widths, not get_drawings' zero-width fill metadata."""

    rules: list[Rule] = []
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "re":
                rect = item[1]
                if drawing["type"] == "f":
                    if 0 < rect.height <= 2 and rect.width >= 4:
                        rules.append(Rule("h", (rect.y0 + rect.y1) / 2,
                                          rect.x0, rect.x1, rect.height))
                    elif 0 < rect.width <= 2 and rect.height >= 4:
                        rules.append(Rule("v", (rect.x0 + rect.x1) / 2,
                                          rect.y0, rect.y1, rect.width))
                elif drawing.get("color") is not None:
                    width = float(drawing.get("width") or 0)
                    rules.extend((Rule("h", rect.y0, rect.x0, rect.x1, width),
                                  Rule("h", rect.y1, rect.x0, rect.x1, width),
                                  Rule("v", rect.x0, rect.y0, rect.y1, width),
                                  Rule("v", rect.x1, rect.y0, rect.y1, width)))
            elif item[0] == "l" and drawing.get("color") is not None:
                p1, p2 = item[1:3]
                width = float(drawing.get("width") or 0)
                if abs(p1.y - p2.y) < 0.002 and abs(p1.x - p2.x) >= 4:
                    rules.append(Rule("h", (p1.y + p2.y) / 2,
                                      min(p1.x, p2.x), max(p1.x, p2.x), width))
                elif abs(p1.x - p2.x) < 0.002 and abs(p1.y - p2.y) >= 4:
                    rules.append(Rule("v", (p1.x + p2.x) / 2,
                                      min(p1.y, p2.y), max(p1.y, p2.y), width))
    return sorted(set(rules), key=lambda r: (r.axis, r.coordinate, r.start, r.end))


def row_boundaries(rules: Iterable[Rule], x: float, top: float, bottom: float) -> list[float]:
    """Find horizontal ink centres crossing an independently specified column."""

    positions = sorted(r.coordinate for r in rules if r.axis == "h"
                       and r.start - 0.01 <= x <= r.end + 0.01
                       and top - 0.01 <= r.coordinate <= bottom + 0.01)
    unique: list[float] = []
    for value in positions:
        if not unique or value - unique[-1] > 0.02:
            unique.append(value)
    return unique


def painted_rule_bands(rules: Iterable[Rule], *, axis: str, crossing: float) -> list[InkBand]:
    """Union touching/overlapping ink at a fixed table-column cross-section.

    This measures the visible band, not a nominal border or a row snap. Two
    touching 0.12pt strokes remain a 0.24pt band; a real gap remains two bands.
    The 0.0002pt contact epsilon accommodates PDF float coordinate extraction,
    and is unrelated to the 0.5pt role-anchor acceptance tolerance.
    """
    if axis not in {"h", "v"} or not math.isfinite(crossing):
        raise ValueError("A finite cross-section and h/v axis are required")
    intervals = []
    for rule in rules:
        if rule.axis == axis and rule.start <= crossing <= rule.end:
            if not all(math.isfinite(value) for value in (rule.coordinate, rule.width)) or rule.width <= 0:
                raise ValueError("Painted rule widths must be finite and positive")
            intervals.append((rule.coordinate - rule.width / 2, rule.coordinate + rule.width / 2))
    merged: list[tuple[float, float]] = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1] + .0002:
            merged[-1] = (merged[-1][0], max(high, merged[-1][1]))
        else:
            merged.append((low, high))
    return [InkBand((low + high) / 2, high - low) for low, high in merged]


def role_errors(sample: TextSample, contract: Mapping[str, Any], *,
                anchor_x: float = 0.0, reference_baseline: float | None = None) -> list[str]:
    """Compare a selected span to an independently measured role contract.

    Callers choose a semantic item (heading, body, equation equals, etc.). No
    generated layout trace is used as the expected geometry. Absolute page Y is
    deliberately not checked: all six reports have variable pagination.
    """

    errors: list[str] = []
    for label, actual in (("x", sample.x), ("baseline", sample.baseline), ("size", sample.size)):
        if not math.isfinite(actual):
            errors.append(f"{label}: non-finite measurement")
    if canonical_font(sample.font) != contract["font"]:
        errors.append(f"font: {sample.font!r} != {contract['font']!r}")
    if abs(sample.size - contract["size_pt"]) > contract.get("size_tolerance_pt", 0.1):
        errors.append(f"size: {sample.size} != {contract['size_pt']}")
    if "relative_x_pt" in contract:
        actual_x = sample.x - anchor_x
        if abs(actual_x - contract["relative_x_pt"]) > contract.get("anchor_tolerance_pt", 0.5):
            errors.append(f"indent/equals: {actual_x} != {contract['relative_x_pt']}")
    if "baseline_delta_pt" in contract:
        if reference_baseline is None:
            errors.append("baseline: missing semantic reference")
        elif abs(sample.baseline - reference_baseline - contract["baseline_delta_pt"]) > contract.get("anchor_tolerance_pt", 0.5):
            errors.append("baseline: relative leading differs")
    if contract.get("monochrome", True) and sample.color != 0:
        errors.append(f"color: {sample.color:#08x} != black")
    return errors


def table_errors(boundaries: Sequence[float], expected_heights: Sequence[float],
                 *, tolerance: float = 0.5) -> list[str]:
    """Check row count and individual heights; uniform or cumulative drift fails."""

    if len(boundaries) != len(expected_heights) + 1:
        return [f"table boundaries: {len(boundaries)} != {len(expected_heights) + 1}"]
    errors = []
    for index, (start, end, expected) in enumerate(zip(boundaries, boundaries[1:], expected_heights)):
        actual = end - start
        if not math.isfinite(actual) or actual <= 0 or abs(actual - expected) > tolerance:
            errors.append(f"table row {index}: {actual} != {expected}")
    return errors


def monochrome_errors(page: pymupdf.Page) -> list[str]:
    """Require native text black and painted vectors black/white (no grey)."""

    errors = [f"page {page.number + 1} colored text: {sample.text!r}"
              for sample in text_samples(page) if sample.color != 0]
    for index, drawing in enumerate(page.get_drawings()):
        for kind in ("color", "fill"):
            color = drawing.get(kind)
            if color is None:
                continue
            if not (all(abs(c) <= 1e-6 for c in color)
                    or all(abs(c - 1) <= 1e-6 for c in color)):
                errors.append(f"page {page.number + 1} drawing {index} {kind}: {color}")
    return errors


def _histogram(values: Iterable[float]) -> list[dict[str, float | int]]:
    return [{"value": value, "count": count}
            for value, count in Counter(round(value, 3) for value in values).most_common()]


def measure_page(page: pymupdf.Page) -> dict[str, Any]:
    spans = text_samples(page)
    rules = native_rules(page)
    raw = page.get_text("rawdict")
    equals = [float(char["origin"][0]) for block in raw["blocks"] if "lines" in block
              for line in block["lines"] for span in line["spans"]
              for char in span["chars"] if char["c"] in ("=", "＝")]
    fonts = Counter((s.font, round(s.size, 3)) for s in spans for c in s.text if not c.isspace())
    baselines = sorted({round(s.baseline, 3) for s in spans if abs(s.size - 9.9) < 0.1})
    headings = [asdict(s) for s in spans if "Gothic" in s.font
                and (s.text.startswith(("§", "(", "（")) or re.match(r"\d[).]", s.text))
                and len(s.text) >= 4]
    visible = page.get_pixmap(matrix=pymupdf.Matrix(0.5, 0.5), colorspace=pymupdf.csGRAY, alpha=False)
    blank = min(visible.samples, default=255) == 255
    return {
        "page": page.number + 1, "size_pt": [page.rect.width, page.rect.height],
        "rotation": page.rotation, "characters": sum(len(s.text) for s in spans),
        "native_images": len(page.get_images()), "rendered_blank": blank,
        "fonts": [{"font": font, "size_pt": size, "characters": count}
                  for (font, size), count in fonts.most_common()],
        "headings": headings, "equals_x_pt": _histogram(equals),
        "main_baseline_deltas_pt": _histogram(b - a for a, b in zip(baselines, baselines[1:]) if b - a >= 5),
        "rule_widths_pt": _histogram(r.width for r in rules),
        "rules": [asdict(rule) for rule in rules],
        "structure": ("blank" if blank else "table-and-text" if len(rules) >= 20
                      else "equations-and-text" if len(equals) >= 10 else "figure-or-text"),
    }


# The samples measured for the appearance record; the folder also holds samples added later (0400, 0440, 最大鉄筋量)
# that the record never measured.
MEASURED_STAGES = ("0500", "0600", "0610", "0620")


def _measured(reference_directory: Path) -> list[Path]:
    return sorted(path for path in reference_directory.glob("*.pdf") if path.name[:4] in MEASURED_STAGES)


def census(reference_directory: Path) -> dict[str, Any]:
    paths = _measured(reference_directory)
    if len(paths) != 4:
        raise ValueError(f"Expected 4 reference PDFs, found {len(paths)}")
    documents = []
    for path in paths:
        with pymupdf.open(path) as doc:
            documents.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                              "pages": [measure_page(page) for page in doc]})
    return {"schema_version": 1, "purpose": "appearance only; never calculation expectations",
            "extractor": f"PyMuPDF {pymupdf.VersionBind}",
            "coordinate_system": "points, top-left; visible rule ink centres",
            "documents": documents}


def build_style_contract(reference_directory: Path) -> dict[str, Any]:
    """Freeze named, manually selected source roles, independent of new builders."""

    selectors = {
        "foundation.chapter": ("0500", 1, "§5. 地盤のモデル化", 93.96),
        "foundation.section": ("0500", 1, "5.1 地盤の諸数値の設計用値のまとめ", 93.96),
        "foundation.body": ("0500", 1, "本橋脚の設計に用いる地盤の諸数値の設計用値を表 2.4.8 に示す.", 93.96),
        "foundation.subsection": ("0500", 1, "(1) フーチング底面の鉛直地盤ばね定数", 93.96),
        "foundation.subsubsection": ("0500", 1, "1) フーチング底面の鉛直地盤反力係数", 93.96),
        "foundation.table_header": ("0500", 1, "層番", None),
        "foundation.table_header_compressive": ("0500", 1, "一軸圧縮強度", None),
        "foundation.table_value": ("0500", 1, "4.000", None),
        "common.chapter": ("0600", 1, "§6. 上部工反力 及び 橋脚自重", 58.92),
        "common.section": ("0600", 1, "6.1 死荷重", 58.92),
        "common.subsection": ("0600", 1, "(1) 支点反力", 58.92),
        "common.subsubsection": ("0600", 1, "1) 起点側桁", 58.92),
        "common.body": ("0600", 13, "橋脚く体の下端に対して次式で求める.", 58.92),
        "common.detail_heading": ("0600", 16, "(a) 使用性の照査におけるひび割れの検討", 58.92),
        "common.table_header": ("0610", 10, "荷重名称", None),
        "common.table_value": ("0610", 10, "21", None),
        "horizontal.formula_lhs": ("0600", 26, "T / n", 58.92),
        "figure.caption": ("0600", 3, "側面図", None),
        "figure.dimension": ("0600", 3, "4500", None),
        "frame.node": ("0610", 1, "1", None),
        "frame.member": ("0610", 1, "4", None),
        "frame.dimension": ("0610", 1, "16.000", None),
    }
    files = {path.name[:4]: path for path in _measured(reference_directory)}
    documents = {stage: pymupdf.open(path) for stage, path in files.items()}
    roles: dict[str, Any] = {}
    try:
        for name, (stage, page_no, text, origin) in selectors.items():
            matches = [sample for sample in text_samples(documents[stage][page_no - 1])
                       if sample.text == text]
            if not matches:
                raise ValueError(f"Missing source role {name}: {text!r}")
            sample = matches[0]
            role: dict[str, Any] = {
                "font": sample.font, "size_pt": round(sample.size, 3),
                "size_tolerance_pt": 0.1, "anchor_tolerance_pt": 0.5,
                "monochrome": True,
                "source": {"file": files[stage].name, "page": page_no,
                           "selector_exact_text": text, "occurrence": 0,
                           "sample": asdict(sample)},
            }
            if origin is not None:
                role["relative_x_pt"] = round(sample.x - origin, 3)
                role["source"]["anchor_x_pt"] = origin
            roles[name] = role
        # Exact semantic anchor families, not a universal equals column.
        for name, stage, page_no, x, origin in (
            ("foundation.symbolic_equals", "0500", 1, 169.92, 93.96),
            ("foundation.substitution_equals", "0500", 2, 184.44, 93.96),
            ("foundation.result_equals", "0500", 1, 460.32, 93.96),
            ("horizontal.first_equals", "0600", 26, 276.72, 58.92),
            ("horizontal.result_equals", "0600", 26, 436.44, 58.92),
        ):
            samples = [s for s in text_samples(documents[stage][page_no - 1])
                       if s.text in ("=", "＝") and s.font == "MS-Mincho" and abs(s.x - x) < .02]
            sample = samples[0]
            roles[name] = {
                "font": sample.font, "size_pt": round(sample.size, 3),
                "relative_x_pt": round(sample.x - origin, 3),
                "size_tolerance_pt": 0.1, "anchor_tolerance_pt": 0.5, "monochrome": True,
                "source": {"file": files[stage].name, "page": page_no,
                           "selector_exact_text": sample.text, "selector_x_pt": x,
                           "selector_font": "MS-Mincho", "occurrence": 0,
                           "anchor_x_pt": origin, "sample": asdict(sample)},
            }
        sub = next(s for s in text_samples(documents["0500"][0])
                   if s.text == "v" and abs(s.size - 6.5) < .01)
        roles["common.subscript"] = {
            "font": "MS-Mincho", "size_pt": 6.5, "size_tolerance_pt": 0.1,
            "anchor_tolerance_pt": 0.5, "monochrome": True,
            "baseline_delta_pt": 1.92,
            "source": {"file": files["0500"].name, "page": 1,
                       "selector_exact_text": "v", "occurrence": 0,
                       "reference_baseline_pt": 565.558, "sample": asdict(sub)},
        }
        superscript = next(s for s in text_samples(documents["0500"][0])
                           if s.text == "-1/2" and abs(s.size - 6.5) < .01)
        roles["common.superscript"] = {
            "font": "MS-Mincho", "size_pt": 6.5, "size_tolerance_pt": 0.1,
            "anchor_tolerance_pt": 0.5, "monochrome": True,
            "baseline_delta_pt": -4.92,
            "source": {"file": files["0500"].name, "page": 1,
                       "selector_exact_text": "-1/2", "occurrence": 0,
                       "reference_baseline_pt": 565.558, "sample": asdict(superscript)},
        }
        tables = {}
        for name, stage, page_no, crossing, top, bottom, nominal, merged in (
            ("foundation.soil", "0500", 1, 310, 185.6, 371.3, 14.28,
             "Two header rows; unit-weight heading spans two columns; other headings span two rows."),
            ("reaction.girder", "0600", 1, 250, 314.7, 419.0, 14.88,
             "Support heading spans five values; train ratio label spans three rows."),
            ("reaction.impact", "0600", 13, 350, 286.1, 480.0, 14.88,
             "Safety/repair and serviceability labels span six rows; groups of three loads have selected thick rules."),
            ("reaction.horizontal_summary", "0600", 37, 350, 142.8, 327.2, 23.04,
             "Header height 28.56; body load-type labels span selected rows."),
            ("longitudinal.combination", "0610", 10, 230, 200.0, 500.0, 14.28,
             "Four header bands; grouped safety/service columns; basic case labels span the header."),
            ("transverse.combination", "0620", 17, 230, 187.0, 495.3, 12.84,
             "Four header bands; repeated load labels; vertical column labels use 64.2 pt bottom band."),
        ):
            page = documents[stage][page_no - 1]
            bounds = row_boundaries(native_rules(page), crossing, top, bottom)
            tables[name] = {
                "nominal_row_height_pt": nominal, "tolerance_pt": 0.5,
                "thin_rule_pt": 0.12, "thick_rule_pt": 0.96,
                "merged_structure": merged,
                "source": {"file": files[stage].name, "page": page_no,
                           "crossing_x_pt": crossing, "top_pt": top, "bottom_pt": bottom,
                           "boundaries_pt": bounds,
                           "heights_pt": [round(b - a, 4) for a, b in zip(bounds, bounds[1:])]},
            }
        return {
            "schema_version": 1, "purpose": "appearance only; no calculation or page-count expectations",
            "sources": [{"file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                        for p in files.values()],
            "user_transform": "All native text and values black; table fills white; rules black.",
            "roles": roles, "tables": tables,
            "common_measures": {"hierarchy_indent_pt": 14.52, "body_leading_pt": 14.28,
                                "section_gap_pt": 28.56, "script_size_pt": 6.5,
                                "measured_increment_pt": 0.12},
            "layout_proposal": {"page_size_pt": [595, 842], "frame_pt": [48, 72, 576, 792],
                                "first_baseline_offset_pt": 11.52,
                                "status": "implementation choice supported by source envelopes, not exact source frame"},
            "blank_source_pages": {"0610": [8], "0620": [14, 15]},
        }
    finally:
        for document in documents.values():
            document.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--style", action="store_true", help="Write selected role contracts instead of the census")
    args = parser.parse_args()
    result = build_style_contract(args.reference_directory) if args.style else census(args.reference_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "kind": "style" if args.style else "census"}))


if __name__ == "__main__":
    main()
