"""Independent source-to-semantic coverage checks for the PDF migration.

Reference text comes exclusively from the frozen old PDFs.  A generated report
must never be used to refresh these fixtures.  Layout coordinates are evidence
for the one-time reading-order mapping, not an input to the new renderer.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import inspect
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any, Sequence


class SemanticMismatch(ValueError):
    """A source item was omitted, duplicated, reordered, or changed."""


def normalized_text(text: str) -> str:
    """Ignore only separating whitespace, retaining signs, factors and units."""
    return re.sub(r"\s+", "", text)


def reference_text(record: dict[str, Any]) -> str:
    """Add reviewed nontext mathematical marks to the native source text."""
    text = record["source_text"]
    for atom in sorted(record.get("vector_atoms", []), key=lambda item: item["offset"], reverse=True):
        text = text[:atom["offset"]] + atom["text"] + text[atom["offset"]:]
    return text


def validate_source_coverage(reference: dict[str, Any], source: dict[str, Any]) -> None:
    """Require explicit, exactly-once coverage and unchanged source chunks."""
    originals = {record["id"]: record["text"] for record in source["body"]}
    claimed = [source_id for record in reference["records"] for source_id in record["source_ids"]]
    counts = Counter(claimed)
    if set(counts) != set(originals) or any(count != 1 for count in counts.values()):
        missing = sorted(set(originals) - set(counts))
        extra = sorted(set(counts) - set(originals))
        duplicates = sorted(key for key, count in counts.items() if count != 1)
        raise SemanticMismatch(f"source coverage: missing={missing}, extra={extra}, duplicate={duplicates}")
    semantic_ids = [record["id"] for record in reference["records"]]
    if len(set(semantic_ids)) != len(semantic_ids):
        raise SemanticMismatch("duplicate semantic ID")
    for record in reference["records"]:
        expected = "".join(originals[key] for key in record["source_ids"])
        if record["source_text"] != expected:
            raise SemanticMismatch(f"{record['id']}: source chunks changed")


def compare_semantics(reference: dict[str, Any], actual: Sequence[dict[str, Any]]) -> None:
    """Compare ordered semantic units; a numeric multiset is never sufficient."""
    expected = reference["records"]
    if len(expected) != len(actual):
        raise SemanticMismatch(f"semantic count: {len(actual)} != {len(expected)}")
    for left, right in zip(expected, actual, strict=True):
        if left["id"] != right["id"]:
            raise SemanticMismatch(f"semantic order/ID: {right['id']} != {left['id']}")
        if normalized_text(reference_text(left)) != normalized_text(right["text"]):
            raise SemanticMismatch(f"{left['id']}: content changed: {right['text']!r}")


def _group(name: str, first: int, last: int | None = None,
           *, order: Sequence[int] | None = None) -> tuple[str, tuple[int, ...]]:
    return name, tuple(order if order is not None else range(first, (last or first) + 1))


def foundation_groups() -> tuple[tuple[str, tuple[int, ...]], ...]:
    """Reviewed logical groups from frozen report.py and its native PDF.

    The old kv substitution draws all numbers before its multiplication signs.
    Its explicit source ordering below restores the visible expression order.
    Every original whitespace span is still assigned exactly once.
    """
    groups = [
        _group("title", 1), _group("soil.heading", 2), _group("soil.introduction", 3),
        _group("soil.caption", 4),
        _group("soil.header", 5, 22, order=(5, 8, 9, 6, 7, 10, 11, 12, 13, 16,
                                                14, 17, 18, 19, 15, 20, 21, 22)),
        _group("soil.row.0", 23, 28), _group("soil.row.1", 29, 36),
        _group("bearing.heading", 37), _group("bearing.normal", 38, 48),
        _group("bearing.seismic", 49, 59), _group("spring.heading", 60),
        _group("vertical.heading", 61), _group("kv.heading", 62, 63),
        _group("kv.sand", 64, 77), _group("kv.alternating", 78, 91),
        _group("kv.clay", 92, 105), _group("kv.definition.kv", 106, 111),
        _group("kv.definition.rho", 112, 115), _group("kv.definition.Ed", 116, 124),
        _group("kv.definition.Bv", 125, 128), _group("kv.width", 129, 139),
        _group("kv.area", 140, 153), _group("kv.long_term.label", 154, 159),
        _group("kv.long_term", 160, 175,
               order=(160, 161, 162, 163, 164, 169, 165, 170, 166, 171, 167, 172, 173, 168, 174, 175)),
        _group("kv.short_term.label", 176, 181),
        _group("kv.short_term", 182, 197,
               order=(182, 183, 184, 185, 186, 191, 187, 192, 188, 193, 189, 194, 195, 190, 196, 197)),
        _group("Kv.heading", 198, 199), _group("Kv.formula", 200, 208),
        _group("Kv.definition.Kv", 209, 212), _group("Kv.definition.kv", 213, 218),
        _group("Kv.definition.Av", 219, 224), _group("Kv.long_term.label", 225),
        _group("Kv.long_term", 226, 235), _group("Kv.short_term.label", 236),
        _group("Kv.short_term", 237, 246), _group("shear.heading", 247),
        _group("ks.heading", 248, 249), _group("ks.formula", 250, 256),
        _group("ks.definition.ks", 257, 262), _group("ks.definition.lambda", 263, 268),
        _group("ks.long_term.label", 269), _group("ks.long_term", 270, 280),
        _group("ks.short_term.label", 281), _group("ks.short_term", 282, 292),
        _group("Ks.heading", 293, 294), _group("Ks.formula", 295, 303),
        _group("Ks.definition.Ks", 304, 307), _group("Ks.definition.ks", 308, 313),
        _group("Ks.definition.Av", 314, 319), _group("Ks.long_term.label", 320),
        _group("Ks.long_term", 321, 330), _group("Ks.short_term.label", 331),
        _group("Ks.short_term", 332, 341), _group("rotation.heading", 342, 343),
        _group("Kr.formula", 344, 352), _group("Kr.definition.Kr", 353, 356),
        _group("Kr.definition.kv", 357, 362), _group("Kr.definition.Iv", 363, 368),
        _group("Kr.longitudinal.heading", 369), _group("Kr.longitudinal.inertia", 370, 382),
        _group("Kr.longitudinal.long_term.label", 383), _group("Kr.longitudinal.long_term", 384, 393),
        _group("Kr.longitudinal.short_term.label", 394), _group("Kr.longitudinal.short_term", 395, 404),
        _group("Kr.transverse.heading", 405), _group("Kr.transverse.inertia", 406, 418),
        _group("Kr.transverse.long_term.label", 419), _group("Kr.transverse.long_term", 420, 429),
        _group("Kr.transverse.short_term.label", 430), _group("Kr.transverse.short_term", 431, 440),
    ]
    return tuple(groups)


def capture_foundation_reference(source_path: Path, destination: Path) -> dict[str, Any]:
    """Write once from the frozen old output, with no production-builder import."""
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    originals = {record["id"]: record["text"] for record in source["body"]}
    records = []
    for name, numbers in foundation_groups():
        ids = [f"0500/display/{number:06d}" for number in numbers]
        records.append({"id": "0500/" + name, "source_ids": ids,
                        "source_text": "".join(originals[key] for key in ids)})
    width = next(record for record in records if record["id"] == "0500/kv.width")
    radicand = originals["0500/display/000135"]
    width["vector_atoms"] = [{"offset": width["source_text"].index(radicand), "text": "√",
                              "source_page": 1, "source_drawing_indices": [25, 26, 27],
                              "meaning": "numeric radicand root; three native line strokes in frozen PDF"}]
    reference = {
        "schema_version": 1, "stage": "0500",
        "source_display_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_pdf_sha256": source["source_pdf_sha256"],
        "mapping_basis": "Frozen old PDF native spans and reviewed old report.py meaning/visible order",
        "normalization": "Whitespace only; preserve every non-whitespace sign, factor, unit and symbol",
        "records": records,
    }
    validate_source_coverage(reference, source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(reference, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return reference


def _legacy_context() -> list[dict[str, Any]]:
    """Capture old logical identities; coordinates never become new layout data."""
    context = []
    frame = inspect.currentframe()
    try:
        while frame is not None:
            module = frame.f_globals.get("__name__", "")
            if module.startswith("src."):
                values = frame.f_locals
                item: dict[str, Any] = {"module": module, "function": frame.f_code.co_name,
                                        "line": frame.f_lineno}
                for key in ("side", "key", "prefix", "kind", "page_number", "column", "index", "start", "address"):
                    value = values.get(key)
                    if isinstance(value, (str, int)):
                        item[key] = value
                for key in ("cell", "template", "page", "row"):
                    value = values.get(key)
                    if isinstance(value, dict):
                        selected = {name: value[name] for name in ("sheet", "address", "case", "label")
                                    if name in value}
                        if selected:
                            item[key] = selected
                context.append(item)
            frame = frame.f_back
    finally:
        del frame
    return context


def capture_reaction_trace(run: Path, baseline: Path, destination: Path) -> dict[str, Any]:
    """Observe the frozen renderer only, and require its exact baseline PDF.

    Text output is intercepted in memory. No publication or product source
    mutation occurs, and no generated data is accepted as a new text oracle.
    """
    import importlib
    from reportlab.pdfgen.textobject import PDFTextObject
    from reporting_baseline import _load_frozen_modules

    _load_frozen_modules(run)
    module = importlib.import_module("src.reaction_report")
    old_canvas = module.Canvas
    original_out, original_line = PDFTextObject.textOut, PDFTextObject.textLine
    buffer = BytesIO()
    events: list[dict[str, Any]] = []

    def observe(text_object: Any, text: str) -> None:
        if not text:
            return
        canvas = text_object._canvas
        a, b, c, d, e, f = canvas._currentMatrix
        x, y = text_object._x, text_object._y
        events.append({"event": len(events) + 1, "page": canvas._pageNumber,
                       "text": str(text), "font": text_object._fontname,
                       "size": text_object._fontsize,
                       "origin": [a * x + c * y + e, 842 - (b * x + d * y + f)],
                       "context": _legacy_context()})

    def text_out(text_object: Any, text: str) -> Any:
        observe(text_object, text)
        return original_out(text_object, text)

    def text_line(text_object: Any, text: str = "") -> Any:
        observe(text_object, text)
        return original_line(text_object, text)

    def canvas_to_memory(*args: Any, **kwargs: Any) -> Any:
        return old_canvas(buffer, **kwargs)

    module.Canvas = canvas_to_memory
    PDFTextObject.textOut, PDFTextObject.textLine = text_out, text_line
    try:
        result = json.loads((baseline / "results/0600.json").read_text(encoding="utf-8"))
        module.render_reaction_report(result, run / "semantic-trace/no-published-file.pdf")
    finally:
        module.Canvas = old_canvas
        PDFTextObject.textOut, PDFTextObject.textLine = original_out, original_line
    expected_pdf = (baseline / "pdfs/0600.pdf").read_bytes()
    if buffer.getvalue() != expected_pdf:
        raise SemanticMismatch("instrumented frozen renderer differs from the frozen PDF")
    trace = {"schema_version": 1, "stage": "0600", "kind": "old-source-observation-only",
             "source_pdf_sha256": hashlib.sha256(expected_pdf).hexdigest(), "events": events}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(trace, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return trace


def trace_source_links(trace: dict[str, Any], source: dict[str, Any]) -> list[dict[str, Any]]:
    """Link each frozen native span to old draw calls by exact character order.

    PDF extraction occasionally inserts whitespace or joins adjacent text
    objects. Both are handled explicitly; no fuzzy text matching is permitted.
    Empty native spacing spans attach to the preceding draw call on that page.
    """
    originals = {record["id"]: record for record in source["body"] + source["decorations"]}
    links = []
    for page in source["pages"]:
        number = page["page"]
        events = [event for event in trace["events"] if event["page"] == number]
        locations = [item for item in source["locations"] if item["source_page"] == number]
        source_text = "".join(normalized_text(originals[item["id"]]["text"]) for item in locations)
        event_text = "".join(normalized_text(event["text"]) for event in events)
        if source_text != event_text:
            raise SemanticMismatch(f"page {number}: old trace/native source character order differs")
        character_events = [event["event"] for event in events for _ in normalized_text(event["text"])]
        cursor = 0
        for location in locations:
            record = originals[location["id"]]
            length = len(normalized_text(record["text"]))
            ids = list(dict.fromkeys(character_events[cursor:cursor + length]))
            if not ids:
                ids = [character_events[max(0, cursor - 1)]]
            links.append({"source_id": record["id"], "event_ids": ids,
                          "text": record["text"], "source_page": number})
            cursor += length
    if {item["source_id"] for item in links} != set(originals):
        raise SemanticMismatch("source trace does not cover every native span")
    return links


def capture_reaction_reference(baseline: Path, trace_path: Path, destination: Path) -> dict[str, Any]:
    """One-time logical mapping from frozen old calls/spans, without new imports.

    Row/address groups below are a reviewed reading of the old report, including
    its inserted snow rows and hand-authored horizontal calculations. Neither
    the new builder nor its PDF supplies a single expected character.
    """
    source_bytes = (baseline / "display/0600.json").read_bytes()
    source = json.loads(source_bytes)
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    events = {event["event"]: event for event in trace["events"]}
    links = trace_source_links(trace, source)
    cell_events: dict[str, list[int]] = {}
    for event in trace["events"]:
        for context in event["context"]:
            if context["function"] == "draw_layout_page":
                cell_events.setdefault(context["page"]["sheet"] + "!" + context["cell"]["address"], []).append(event["event"])
    order: list[str] = []
    assigned: dict[int, str] = {}
    cell_rank: dict[int, int] = {}

    def add(key: str, sheet: str | None = None, rows: Sequence[int] = (), addresses: Sequence[str] | None = None) -> None:
        order.append(key)
        if sheet is None:
            return
        names = list(addresses) if addresses is not None else [name.split("!")[1] for name in cell_events
                 if name.startswith(sheet + "!") and int(re.sub("[A-Z]", "", name.split("!")[1])) in rows]
        def address_order(address: str) -> tuple[int, int]:
            column = 0
            for char in re.match("[A-Z]+", address)[0]:
                column = 26 * column + ord(char) - 64
            return int(re.sub("[A-Z]", "", address)), column
        if addresses is None:
            names.sort(key=address_order)
        for rank, address in enumerate(names):
            for event_id in cell_events.get(sheet + "!" + address, ()):
                if event_id in assigned:
                    raise SemanticMismatch(f"duplicate old event assignment: {event_id}")
                assigned[event_id], cell_rank[event_id] = key, rank

    s = "死荷重"
    for key, address in (("title", "B3"), ("dead.heading", "C5"), ("dead.support.heading", "D7"), ("dead.unit", "AF8")):
        add(key, s, addresses=(address,))
    add("dead.support", s, (9, 10, 11, 12))
    add("dead.support.snow")
    add("dead.girders.heading", s, (15,))
    for side, heading_row, start in (("B", 17, 19), ("C", 35, 37)):
        add(f"dead.{side}.heading", s, (heading_row,))
        add(f"dead.{side}.0.unit", s, (start - 1,))
        add(f"dead.{side}.0.caption", s, (start,))
        add(f"dead.{side}.0.table", s, tuple(range(start + 1, start + 7)))
        add(f"dead.{side}.0.snow")
    s = "橋脚自重"
    add("weights.heading", s, (15,))
    add("weights.overall.figure")
    for key, head, areas, first, totals in (("beam", 81, (83, 84), 86, range(92, 96)),
                                           ("column", 109, range(111, 117), None, ()),
                                           ("footing", 135, (137, 138), 140, range(146, 150))):
        add(f"weights.{key}.heading", s, (head,))
        for row in areas:
            add(f"weights.{key}.{row}", s, (row,))
        if first:
            add(f"weights.{key}.table", s, tuple(range(first, first + 5)))
        for row in totals:
            add(f"weights.{key}.{row}", s, (row,))
        add(f"weights.{key}.figure")
    def volume(key: str, start: int, moment: int, totals: int) -> None:
        add(f"weights.{key}.volume.caption", s, (start,))
        add(f"weights.{key}.volume", s, tuple(range(start + 1, moment - 1)))
        add(f"weights.{key}.moments", s, tuple(range(moment, totals)))
        for row in range(totals, totals + 3):
            add(f"weights.{key}.{row}", s, (row,))
        add(f"weights.{key}.figure")
    add("weights.soil.heading", s, (163,))
    volume("soil", 165, 173, 181)
    add("weights.water.heading", s, (199,))
    for key, start in (("high", 201), ("normal", 235), ("low", 269)):
        add(f"weights.water.{key}.heading", s, (start,))
        volume("water." + key, start + 2, start + 9, start + 16)
    for key, start, end in (("column_base", 304, 311), ("footing_center", 319, 328)):
        add(f"weights.{key}.heading", s, (start,))
        add(f"weights.{key}.table", s, tuple(range(start + 2, end + 1)))
        for row in range(end + 2, end + 6):
            add(f"weights.{key}.{row}", s, (row,))
    s = "列車荷重"
    for row in (18, 20, 22):
        add(f"train.heading.{row}", s, (row,))
    add("train.moving.figure")
    for row in (34, 36, 38, 40):
        add(f"train.reaction.{row}", s, (row,))
    for row in (43, 47, 51):
        add(f"train.factor.heading.{row}", s, (row,))
        add(f"train.factor.{row + 2}", s, (row + 2,))
    add("train.earthquake.heading", s, (55,))
    for row in (57, 58):
        add(f"train.earthquake.{row}", s, (row,))
    for row in (62, 64):
        add(f"impact.heading.{row}", s, (row,))
    add("impact.girder.unit", s, (65,))
    add("impact.girder.table", s, tuple(range(66, 88)))
    add("impact.pier.heading", s, (90,))
    add("impact.pier.introduction", s, (92,))
    add("impact.pier.formula", s, addresses=("G94", "H94", "I94", "J94", "K94", "L94", "M94", "O94", "N95", "S94", "U95"))
    for row in range(97, 102):
        add(f"impact.pier.definition.{row}", s, (row,))
    add("impact.pier.unit", s, (103,))
    add("impact.pier.table", s, tuple(range(104, 117)))
    add("impact.foundation.heading", s, (119,))
    for row in range(121, 126):
        add(f"impact.foundation.note.{row}", s, (row,))
    add("longitudinal.introduction")
    for number in range(1, 13):
        add(f"longitudinal.case.{number}")
    for key in ("heading", "unit", "table"):
        add("longitudinal.summary." + key)
    s = "直角荷重"
    add("centrifugal.heading", s, (16,))
    add("centrifugal.subheading", s, (18,))
    for side, start in (("B", 20), ("C", 45)):
        key = "centrifugal." + side
        for suffix, row in (("heading", start), ("zero", start + 2), ("coefficient.note", start + 3)):
            add(key + "." + suffix, s, (row,))
        first, second = start + 5, start + 6
        add(key + ".coefficient", s, addresses=tuple(f"{column}{row}" for column, row in (
            ("G", first), ("I", first), ("J", first), ("J", second), ("N", first),
            ("Q", first), ("S", first), ("P", second), ("R", second), ("S", second), ("V", first), ("W", first))))
        add(key + ".height.caption", s, (start + 8,))
        add(key + ".height", s, (start + 10,))
        for number, row in enumerate((start + 12, start + 16, start + 20)):
            add(key + f".force.{number}.heading", s, (row,))
            add(key + f".force.{number}", s, (row + 2,))
    for key, row in (("heading", 69), ("note", 71), ("load", 73)):
        add("lateral." + key, s, (row,))
    add("lateral.moving.figure")
    for side, start in (("B", 85), ("C", 92)):
        for key, row in (("heading", start), ("force", start + 2), ("height", start + 4)):
            add(f"lateral.{side}.{key}", s, (row,))
    add("wind.heading", s, (99,))
    for key, start, supports in (("loaded", 101, (106, 115)), ("empty", 124, (128, 137))):
        add(f"wind.{key}.heading", s, (start,))
        add(f"wind.{key}.pressure", s, (start + 2,))
        if key == "loaded":
            add("wind.loaded.width", s, (104,))
        for side, first in zip(("B", "C"), supports):
            add(f"wind.{key}.{side}.heading", s, (first,))
            for name, row in zip(("height", "force", "position"), (first + 2, first + 4, first + 6)):
                add(f"wind.{key}.{side}.{name}", s, (row,))
    add("transverse.earthquake")
    for key in ("heading", "unit", "table"):
        add("transverse.summary." + key)

    def classify(event: dict[str, Any]) -> str:
        if event["event"] in assigned:
            return assigned[event["event"]]
        contexts = {item["function"]: item for item in event["context"]}
        if "_draw_cell" in contexts:
            context = contexts["draw_snow_page"]
            return f"dead.{context['side']}.{context['start'] // 5}.snow" if context["side"] else "dead.support.snow"
        for function, kind in (("_overall", "overall"), ("_beam", "beam"), ("_pedestal", "pedestal"), ("_foundation", "foundation")):
            if function in contexts:
                if kind == "foundation":
                    kind = contexts[function]["kind"]
                    if kind == "water":
                        kind += "." + {7: "high", 8: "normal", 9: "low"}[contexts["draw_diagrams"]["page_number"]]
                return "weights." + kind + ".figure"
        if "_moving" in contexts:
            return "train.moving.figure" if contexts["draw_diagrams"]["page_number"] == 11 else "lateral.moving.figure"
        if "_summary" in contexts:
            line = contexts["_summary"]["line"]
            return "longitudinal.summary." + ("heading" if line == 330 else "unit" if line == 331 else "table")
        if "_case_page" in contexts or "_earthquake_cases" in contexts:
            if "_earthquake_cases" in contexts:
                number = contexts["_earthquake_cases"]["row"]["case"]
            else:
                label = contexts["_case_page"]["row"]["label"]
                number = contexts["_case_page"]["row"].get("case", 11 if label.startswith("安全性") else 12)
            return f"longitudinal.case.{number}"
        if "_introduction" in contexts:
            return "longitudinal.introduction"
        if "draw_transverse_earthquake_report" in contexts:
            line = contexts["draw_transverse_earthquake_report"]["line"]
            return ("transverse.earthquake" if line <= 400 else "transverse.summary."
                    + ("heading" if line == 403 else "unit" if line == 404 else "table"))
        raise SemanticMismatch(f"unmapped old event {event['event']}: {event['text']!r}, {contexts}")

    originals = {record["id"]: record["text"] for record in source["body"]}
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in order}
    for link in links:
        if link["source_id"] not in originals:
            continue
        owners = {classify(events[event_id]) for event_id in link["event_ids"]}
        if len(owners) != 1:
            raise SemanticMismatch(f"native span crosses logical units: {link}, {owners}")
        owner = owners.pop()
        if owner not in grouped:
            raise SemanticMismatch(f"unlisted old semantic group: {owner}")
        grouped[owner].append(link)
    records = []
    for key in order:
        items = grouped[key]
        def rank(link: dict[str, Any]) -> tuple[int, int, int]:
            event = events[link["event_ids"][0]]
            contexts = {context["function"]: context for context in event["context"]}
            if key == "longitudinal.summary.table" and "row" in contexts.get("_summary", {}):
                context = contexts["_summary"]
                column = contexts.get("_draw_numeric_cell", {}).get("column", 1)
                return context["index"], column, event["event"]
            return 0, cell_rank.get(event["event"], 0), event["event"]
        items.sort(key=rank)
        ids = [item["source_id"] for item in items]
        records.append({"id": "0600/" + key, "source_ids": ids,
                        "source_event_ids": [event_id for item in items for event_id in item["event_ids"]],
                        "source_text": "".join(originals[source_id] for source_id in ids)})
    by_id = {record["id"]: record for record in records}
    impact = by_id["0600/impact.pier.formula"]
    impact["vector_atoms"] = [{"offset": impact["source_text"].index("Ｌ"), "text": "/",
                                "source_page": 12, "source_drawing_indices": [30],
                                "meaning": "drawn fraction rule between Ds and L+DU+Ds"}]
    for side, drawing in (("B", (2, 0)), ("C", (3, 1))):
        record = by_id[f"0600/centrifugal.{side}.coefficient"]
        text = record["source_text"]
        first = text.index("127")
        second = text.index("127", first + 3)
        record["vector_atoms"] = [{"offset": offset, "text": "/", "source_page": 26,
                                    "source_drawing_indices": [index],
                                    "meaning": "drawn symbolic/substitution centrifugal fraction rule"}
                                   for offset, index in zip((first, second), drawing)]
    reference = {"schema_version": 1, "stage": "0600", "source_display_sha256": hashlib.sha256(source_bytes).hexdigest(),
                 "source_pdf_sha256": source["source_pdf_sha256"],
                 "mapping_basis": "Frozen old call sites/cell addresses and native spans; explicit logical table/formula order; no new builder import",
                 "normalization": "Whitespace only, with reviewed drawn fraction bars represented by slash vector atoms", "records": records}
    validate_source_coverage(reference, source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(reference, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return reference


def _foundation_owner(page: dict[str, Any], command: dict[str, Any]) -> str:
    bounds = command["bounds"]
    center = bounds["y"] + bounds["height"] / 2
    grid = page["profile"]["grid"]
    for placement in page["metadata"]["placements"]:
        top = grid["origin_y"] + placement["row"] * grid["pitch_y"]
        bottom = top + placement["rows"] * grid["pitch_y"]
        if not top - .001 <= center <= bottom + .001:
            continue
        identifier = placement["block_id"]
        if identifier == "0500/soil.table":
            for part in placement["prefix"] + placement["parts"]:
                start = top + part["row"] * grid["pitch_y"]
                end = start + part["rows"] * grid["pitch_y"]
                if start - .001 <= center <= end + .001:
                    source_rows = part["metadata"]["source_rows"]
                    return "0500/soil.header" if source_rows[0] < 2 else f"0500/soil.row.{source_rows[0] - 2}"
        return identifier
    return "decoration/footer"


def manuscript_payload(value: Any) -> list[tuple[str, str]]:
    """Read authored math leaves without measuring or rendering the manuscript.

    The finite rules preserve native draw order: base/upper/lower scripts,
    numerator/denominator/fraction rule, and radical stroke/body. Separators
    represented by vectors are explicit tokens, never silently stripped text.
    This can be used by every stage's source -> manuscript -> scene audit.
    """
    from gridlayoutpdf import BreakHint, Equation, Fraction, Literal, Root, Row, Script

    if value is None:
        return []
    if isinstance(value, BreakHint):
        return []
    if isinstance(value, str):
        return [("text", value)]
    if isinstance(value, Literal):
        return manuscript_payload(value.text)
    if isinstance(value, Row):
        return manuscript_payload(value.items)
    if isinstance(value, Script):
        return manuscript_payload((value.base, value.superscript, value.subscript))
    if isinstance(value, Fraction):
        return manuscript_payload((value.numerator, value.denominator)) + [("vector", "Line")]
    if isinstance(value, Root):
        return [("vector", "Polyline")] + manuscript_payload(value.body)
    if isinstance(value, Equation):
        pieces = [value.lhs, value.relation, value.rhs]
        if value.result is not None:
            pieces.extend((value.result_relation, value.result))
        pieces.append(value.unit)
        return manuscript_payload(pieces)
    if isinstance(value, (list, tuple)):
        return [token for part in value for token in manuscript_payload(part)]
    raise SemanticMismatch(f"unaudited manuscript node: {type(value).__name__}")


def verify_manuscript_scene(value: Any, commands: Sequence[Any], fonts: Any,
                            *, identifier: str, include_vectors: bool = True) -> dict[str, Any]:
    """Reject a complete-looking scene that dropped an authored factor or unit.

    Expected leaves come from the manuscript already checked against the old
    source. They are never derived from measured blocks or the new PDF.
    """
    from gridlayoutpdf import Line, Polyline, Text

    def characters(tokens: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
        result = []
        for kind, text in tokens:
            if kind == "text":
                result.extend((kind, char) for char in fonts.normalize_text(text) if not char.isspace())
            elif include_vectors:
                result.append((kind, text))
        return result

    expected = characters(manuscript_payload(value))
    observed = characters([("text", command.text) if isinstance(command, Text)
                           else ("vector", type(command).__name__)
                           for command in commands if isinstance(command, (Text, Line, Polyline))])
    if expected != observed:
        mismatch = next((index for index, (left, right) in enumerate(zip(expected, observed)) if left != right),
                        min(len(expected), len(observed)))
        raise SemanticMismatch(f"manuscript/scene mismatch: {identifier}, token {mismatch}: "
                               f"{expected[mismatch:mismatch + 5]} != {observed[mismatch:mismatch + 5]}")
    return {"manuscript_scene_token_count": len(expected),
            "manuscript_scene_sha256": hashlib.sha256(json.dumps(expected, ensure_ascii=False).encode()).hexdigest()}


def audit_foundation_native(reference: dict[str, Any], result: dict[str, Any],
                            document: Any, pages: Sequence[Any], pdf_path: Path) -> dict[str, Any]:
    """Prove old semantic units reach the actual native PDF, including positions.

    Every new Text character is compared in draw order with native PDF glyphs,
    including its origin, size, embedded face and black color. This is separate
    from old-to-new semantic equality; the output cannot bless its own content.
    """
    import pymupdf
    from gridlayoutpdf import Line, Polyline, Text, layout_trace
    from src.reporting.stages.foundation import content, semantic_records

    actual = semantic_records(result)
    compare_semantics(reference, actual)
    records = {row["id"]: {"id": row["id"], "source_ids": row["source_ids"],
                           "source_vector_atoms": row.get("vector_atoms", []),
                           "semantic_text": actual[index]["text"], "native_glyph_ids": [],
                           "scene_commands": []} for index, row in enumerate(reference["records"])}
    trace = layout_trace(pages, document.fonts)
    commands_by_unit: dict[str, list[Any]] = {key: [] for key in records}
    glyph_count = 0
    with pymupdf.open(pdf_path) as pdf:
        if len(pdf) != len(pages):
            raise SemanticMismatch("native PDF page count differs from the fixed scenes")
        for page, scene, evidence in zip(pdf, pages, trace["pages"], strict=True):
            if page.get_images():
                raise SemanticMismatch("0500 contains a raster body")
            glyphs = [(character, span) for block in page.get_text("rawdict")["blocks"]
                      for line in block.get("lines", []) for span in line["spans"]
                      for character in span["chars"] if not character["c"].isspace()]
            vectors = [command for command in scene.commands if isinstance(command, (Line, Polyline))]
            native_vectors = page.get_drawings()
            if len(vectors) != len(native_vectors):
                raise SemanticMismatch("native vector count differs (root/fraction/table rule)")
            for command, drawing in zip(vectors, native_vectors, strict=True):
                points = [(command.x1, command.y1), (command.x2, command.y2)] if isinstance(command, Line) else [(point.x, point.y) for point in command.points]
                expected_segments = list(zip(points, points[1:]))
                if len(drawing["items"]) != len(expected_segments) or abs(drawing["width"] - command.width) > .001:
                    raise SemanticMismatch("native vector structure differs")
                for segment, (start, end) in zip(drawing["items"], expected_segments, strict=True):
                    if segment[0] != "l" or any(abs(a - b) > .001 for a, b in zip((*start, *end), (*segment[1], *segment[2]), strict=True)):
                        raise SemanticMismatch("native vector geometry differs")
            cursor = 0
            for command_index, command in enumerate(scene.commands):
                item = evidence["commands"][command_index]
                owner = _foundation_owner(evidence, item)
                if owner in records:
                    commands_by_unit[owner].append(command)
                    records[owner]["scene_commands"].append({"page": page.number + 1, "index": command_index,
                                                             "type": item["type"], "bounds": item["bounds"]})
                elif isinstance(command, Text) and owner != "decoration/footer":
                    raise SemanticMismatch(f"unmapped native body command: {owner}")
                if not isinstance(command, Text):
                    continue
                text = document.fonts.normalize_text(command.text)
                for offset, char in enumerate(text):
                    if char.isspace():
                        continue
                    if cursor >= len(glyphs):
                        raise SemanticMismatch("native PDF text is missing")
                    glyph, span = glyphs[cursor]
                    expected_x = command.x + document.fonts.measure(text[:offset], command.style).width
                    font = document.fonts.resolve(command.style.font)
                    if (glyph["c"] != char or abs(glyph["origin"][0] - expected_x) > .03
                            or abs(glyph["origin"][1] - command.y) > .03
                            or abs(span["size"] - command.style.size) > .01 or span["color"] != 0
                            or not font.pdf_name.startswith(span["font"])):
                        raise SemanticMismatch(f"native glyph mismatch: page {page.number + 1}, glyph {cursor}, unit {owner}")
                    if owner in records:
                        records[owner]["native_glyph_ids"].append(f"{page.number + 1}/{cursor}")
                    cursor += 1
                    glyph_count += 1
            if cursor != len(glyphs):
                raise SemanticMismatch("unexpected native PDF text")
    if any(not row["native_glyph_ids"] for row in records.values()):
        raise SemanticMismatch("semantic unit has no native PDF text")
    for unit in content(result):
        value = unit.value
        if unit.kind == "soil_header":
            # Merged native cells are emitted in row-major order: the wet/dry
            # subheaders follow the seven two-row cells, not their parent.
            value = (*value[:4], value[4][0], *value[5:], *value[4][1:])
        records[unit.identifier].update(verify_manuscript_scene(
            value, commands_by_unit[unit.identifier], document.fonts, identifier=unit.identifier,
            include_vectors=unit.kind not in ("soil_header", "soil_row")))
    roots = [command for command in records["0500/kv.width"]["scene_commands"] if command["type"] == "Polyline"]
    if len(roots) != 2:
        raise SemanticMismatch("symbolic/numeric root vector was lost")
    for identifier in ("0500/ks.definition.lambda", "0500/ks.long_term", "0500/ks.short_term",
                       "0500/Kr.longitudinal.inertia", "0500/Kr.transverse.inertia"):
        if not any(command["type"] == "Line" for command in records[identifier]["scene_commands"]):
            raise SemanticMismatch(f"fraction rule missing: {identifier}")
    return {"schema_version": 1, "stage": "0500", "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
            "source_pdf_sha256": reference["source_pdf_sha256"], "pages": len(pages),
            "native_glyph_count": glyph_count, "records": list(records.values())}


def write_foundation_proof(baseline: Path, destination: Path) -> dict[str, Any]:
    """Emit reviewable QA only; never update source fixtures or formal outputs."""
    from copy import deepcopy
    from dataclasses import asdict
    import pymupdf
    from src.reporting.document import write_proof
    from src.reporting.stages.foundation import build_report
    from scripts.reporting_appearance import native_rules, painted_rule_bands

    result = json.loads((baseline / "results/0500.json").read_text(encoding="utf-8"))
    reference = json.loads((baseline.parent / "semantic/0500.json").read_text(encoding="utf-8"))
    summary: dict[str, Any] = {}
    for stem in ("0500", "0500-long90", "0500-longnames"):
        current = deepcopy(result)
        if stem == "0500-long90":
            current["layers"] = [{**current["layers"][0], "name": f"層{index:03d}"} for index in range(90)]
            current["layers"][40]["soil_type"] = "砂質土と粘性土の互層を含む区分"
        elif stem == "0500-longnames":
            current["layers"][0].update(name="長い地層名称と砂礫を含む地層", soil_type="砂質土と粘性土の互層を含む区分")
        document = build_report(current)
        pages = document.layout()
        artifacts = write_proof(pages, document.fonts, destination, stem=stem)
        summary[stem] = {"pages": len(pages), "pdf_sha256": hashlib.sha256(artifacts.normal.read_bytes()).hexdigest()}
        if stem == "0500":
            audit = audit_foundation_native(reference, current, document, pages, artifacts.normal)
            (destination / "0500-source-native-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
            with pymupdf.open(artifacts.normal) as pdf:
                rules = native_rules(pdf[0])
                vertical = [rule for rule in rules if rule.axis == "v" and abs(rule.coordinate - 76.92) <= .5]
                bands = [band for band in painted_rule_bands(rules, axis="h", crossing=310)
                         if min(rule.start for rule in vertical) - .5 <= band.coordinate <= max(rule.end for rule in vertical) + .5]
                ink = {"per_stroke_pt": {"thin": .12, "outer": .96}, "bands": [asdict(band) for band in bands],
                       "measured_row_heights_pt": [b.coordinate - a.coordinate for a, b in zip(bands, bands[1:])],
                       "reference_nominal_row_height_pt": 14.28,
                       "shared_boundary_difference": "two .12pt strokes produce .24pt painted union; original has one .12pt stroke"}
                (destination / "0500-table-ink.json").write_text(json.dumps(ink, indent=2), encoding="utf-8")
            summary[stem].update(semantic_units=len(audit["records"]), native_glyph_count=audit["native_glyph_count"])
    (destination / "proof-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def audit_reaction_native(reference: dict[str, Any], result: dict[str, Any],
                          document: Any, pages: Sequence[Any], pdf_path: Path) -> dict[str, Any]:
    """Old source -> authored leaves -> actual staged scene -> native PDF."""
    import pymupdf
    from gridlayoutpdf import Line, Polyline, Text, layout_trace
    from src.reporting.stages.reaction import content, figure_labels, semantic_key, semantic_records

    compare_semantics(reference, semantic_records(result))
    units = {unit.identifier: unit for unit in content(result)}
    records = {row["id"]: {"id": row["id"], "source_ids": row["source_ids"],
                          "vector_atoms": row.get("vector_atoms", []), "native_glyph_ids": [],
                          "unit_ids": [], "manuscript_scene": []} for row in reference["records"]}
    trace = layout_trace(pages, document.fonts)
    by_unit: dict[str, list[Any]] = {key: [] for key in units}
    table_parts: dict[tuple[int, str, int], dict[str, Any]] = {}
    glyph_count = 0
    with pymupdf.open(pdf_path) as pdf:
        if len(pdf) != len(pages):
            raise SemanticMismatch("native page count differs")
        for page, scene, evidence in zip(pdf, pages, trace["pages"], strict=True):
            if page.get_images():
                raise SemanticMismatch("0600 contains a raster body")
            glyphs = [(character, span) for block in page.get_text("rawdict")["blocks"]
                      for line in block.get("lines", []) for span in line["spans"]
                      for character in span["chars"] if not character["c"].isspace()]
            vectors = [command for command in scene.commands if isinstance(command, (Line, Polyline))]
            drawings = page.get_drawings()
            if len(vectors) != len(drawings):
                raise SemanticMismatch("native vector count differs")
            for command, drawing in zip(vectors, drawings, strict=True):
                points = [(command.x1, command.y1), (command.x2, command.y2)] if isinstance(command, Line) else [(point.x, point.y) for point in command.points]
                segments = list(zip(points, points[1:]))
                native_segments = []
                for item in drawing["items"]:
                    if item[0] == "l":
                        native_segments.append((tuple(item[1]), tuple(item[2])))
                    elif item[0] == "qu":
                        quad = item[1]
                        corners = [tuple(quad.ul), tuple(quad.ll), tuple(quad.lr), tuple(quad.ur), tuple(quad.ul)]
                        native_segments.extend(zip(corners, corners[1:]))
                    elif item[0] == "re":
                        rectangle = item[1]
                        corners = [(rectangle.x0, rectangle.y0), (rectangle.x1, rectangle.y0),
                                   (rectangle.x1, rectangle.y1), (rectangle.x0, rectangle.y1), (rectangle.x0, rectangle.y0)]
                        native_segments.extend(zip(corners, corners[1:]))
                    else:
                        raise SemanticMismatch("unexpected native vector primitive")
                if len(native_segments) != len(segments) or abs(drawing["width"] - command.width) > .001:
                    raise SemanticMismatch("native vector structure differs")
                # MuPDF may coalesce a four-line native closed polygon into a
                # rectangle/quad. Compare its same four undirected edges.
                def edges(items: Sequence[Any]) -> list[tuple[Any, Any]]:
                    return sorted(tuple(sorted((tuple(a), tuple(b)))) for a, b in items)
                for expected, observed in zip(edges(segments), edges(native_segments), strict=True):
                    if any(abs(a - b) > .001 for a, b in zip((*expected[0], *expected[1]), (*observed[0], *observed[1]), strict=True)):
                        raise SemanticMismatch("native vector geometry differs")
            cursor = 0
            grid = evidence["profile"]["grid"]
            for command_index, command in enumerate(scene.commands):
                item = evidence["commands"][command_index]
                bounds = item["bounds"]
                center = bounds["y"] + bounds["height"] / 2
                owner = "decoration/footer"
                placement = None
                for candidate in evidence["metadata"]["placements"]:
                    top = grid["origin_y"] + candidate["row"] * grid["pitch_y"]
                    if top - .001 <= center <= top + candidate["rows"] * grid["pitch_y"] + .001:
                        owner, placement = candidate["block_id"], candidate
                        break
                if owner in units:
                    by_unit[owner].append(command)
                    unit = units[owner]
                    semantic_id = "0600/" + semantic_key(unit.key)
                    record = records[semantic_id]
                    if owner not in record["unit_ids"]:
                        record["unit_ids"].append(owner)
                    if unit.kind == "table" and isinstance(command, Text):
                        assert placement is not None
                        for part_index, part in enumerate(placement["prefix"] + placement["parts"]):
                            start = grid["origin_y"] + (placement["row"] + part["row"]) * grid["pitch_y"]
                            end = start + part["rows"] * grid["pitch_y"]
                            if start - .001 <= center <= end + .001:
                                key = (page.number, owner, part_index)
                                item = table_parts.setdefault(key, {"source_rows": part["metadata"]["source_rows"], "commands": []})
                                item["commands"].append(command)
                                break
                        else:
                            raise SemanticMismatch("native table glyph has no logical row")
                elif isinstance(command, Text) and owner != "decoration/footer":
                    raise SemanticMismatch(f"unmapped native body text: {owner}")
                if not isinstance(command, Text):
                    continue
                text = document.fonts.normalize_text(command.text)
                for offset, char in enumerate(text):
                    if char.isspace():
                        continue
                    if cursor >= len(glyphs):
                        raise SemanticMismatch("native PDF text is missing")
                    glyph, span = glyphs[cursor]
                    expected_x = command.x + document.fonts.measure(text[:offset], command.style).width
                    face = document.fonts.resolve(command.style.font)
                    if (glyph["c"] != char or abs(glyph["origin"][0] - expected_x) > .03
                            or abs(glyph["origin"][1] - command.y) > .03
                            or abs(span["size"] - command.style.size) > .01 or span["color"] != 0
                            or not face.pdf_name.startswith(span["font"])):
                        raise SemanticMismatch(f"native glyph mismatch: page {page.number + 1}, glyph {cursor}, unit {owner}")
                    if owner in units:
                        records["0600/" + semantic_key(units[owner].key)]["native_glyph_ids"].append(f"{page.number + 1}/{cursor}")
                    cursor += 1
                    glyph_count += 1
            if cursor != len(glyphs):
                raise SemanticMismatch("unexpected native PDF text")
    for identifier, unit in units.items():
        record = records["0600/" + semantic_key(unit.key)]
        if unit.kind == "table":
            for (page, owner, index), part in table_parts.items():
                if owner == identifier:
                    value = tuple(unit.value[row] for row in part["source_rows"])
                    checked = verify_manuscript_scene(value, part["commands"], document.fonts,
                                                      identifier=identifier, include_vectors=False)
                    record["manuscript_scene"].append({"unit": identifier, "page": page + 1,
                                                       "table_part": index, "source_rows": part["source_rows"], **checked})
        else:
            value = figure_labels(unit.value[0], result) if unit.kind == "figure" else unit.value
            checked = verify_manuscript_scene(value, by_unit[identifier], document.fonts,
                                              identifier=identifier, include_vectors=unit.kind != "figure")
            record["manuscript_scene"].append({"unit": identifier, **checked})
    if any(not row["native_glyph_ids"] for row in records.values()):
        raise SemanticMismatch("semantic unit has no native PDF text")
    return {"schema_version": 1, "stage": "0600", "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
            "source_pdf_sha256": reference["source_pdf_sha256"], "pages": len(pages),
            "native_glyph_count": glyph_count, "records": list(records.values())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foundation-source", type=Path)
    parser.add_argument("--foundation-proof", action="store_true")
    parser.add_argument("--reaction-run", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.foundation_proof:
        if not args.baseline:
            parser.error("--foundation-proof requires --baseline")
        print(json.dumps(write_foundation_proof(args.baseline, args.destination)))
    elif args.reaction_run:
        if not args.baseline:
            parser.error("--reaction-run requires --baseline")
        result = capture_reaction_trace(args.reaction_run.resolve(), args.baseline.resolve(), args.destination)
        print(json.dumps({"events": len(result["events"]), "source_pdf_sha256": result["source_pdf_sha256"]}))
    elif args.foundation_source:
        result = capture_foundation_reference(args.foundation_source, args.destination)
        print(json.dumps({"records": len(result["records"]),
                          "source_ids": sum(len(record["source_ids"]) for record in result["records"])},
                         ensure_ascii=False))
    else:
        parser.error("select --foundation-source or --reaction-run")


if __name__ == "__main__":
    main()
