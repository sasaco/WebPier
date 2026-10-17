"""Independent source/manuscript/scene/native evidence for 0610 and 0620.

The frozen source defines content. Manuscripts define leaf-to-cell order. The
actual supplied scenes, never a second layout, define native glyph positions.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import importlib
import json
from pathlib import Path
import re
from typing import Any, Sequence

from gridlayoutpdf import Line, Polyline, Rectangle, Text, layout_trace

from src.reporting.stages.frame_content import (
    Header, Merged, Unit, VerticalHeader, atoms, plain, semantic_sections,
)
from scripts.reporting_semantic_audit import (
    SemanticMismatch, compare_semantics, normalized_text, validate_source_coverage,
    verify_manuscript_scene,
)


def _near(left: Sequence[float], right: Sequence[float], tolerance: float = .003) -> bool:
    return len(left) == len(right) and all(abs(a - b) <= tolerance for a, b in zip(left, right, strict=True))


def validate_frame_source(reference: dict[str, Any], source: dict[str, Any]) -> None:
    """Only explicitly evidenced document headers/page counters may repeat."""
    validate_source_coverage(reference, source)
    originals = {row["id"]: row for row in source["body"]}
    locations = {row["id"]: row for row in source["locations"]}
    for record in reference["records"]:
        role = record["role"]
        if role == "body":
            continue
        if role == "page_counter" and reference["stage"] == "0620":
            for identifier in record["source_ids"]:
                row = originals[identifier]
                location = locations[identifier]
                if (row["text"] != str(location["source_page"])
                        or abs(location["bbox"][2] - 547) > .01
                        or location["origin"][1] != 815 or location["size"] != 7):
                    raise SemanticMismatch(f"unproven page-counter exception: {identifier}")
        elif role == "repeated_header" and reference["stage"] == "0610":
            if any(originals[key]["text"] != "0610 線路方向荷重" for key in record["source_ids"]):
                raise SemanticMismatch("document-header exemption includes body content")
        else:
            raise SemanticMismatch(f"unapproved semantic exception: {role}")


def _value(value: Any) -> Any:
    if isinstance(value, Merged):
        return _value(value.value)
    if isinstance(value, (Header, VerticalHeader)):
        return tuple(_value(part) for part in value.values)
    if isinstance(value, (tuple, list)):
        return tuple(_value(part) for part in value)
    return value


def _authored_cells(unit: Unit) -> list[tuple[str, int, Any]]:
    """Resolve logical columns independently from native Table placement data."""
    occupied: set[tuple[int, int]] = set()
    cells = []
    for row, values in enumerate(unit.value):
        col = 0
        for value in values:
            while (row, col) in occupied:
                col += 1
            rows, cols = (value.rowspan, value.colspan) if isinstance(value, Merged) else (1, 1)
            cells.append((f"{unit.identifier}.rows[{row}].cells[{col}]", row, value))
            occupied.update((r, c) for r in range(row, row + rows) for c in range(col, col + cols))
            col += cols
    return cells


def _source_links(reference: dict[str, Any], units: Sequence[Unit], source: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    originals = {row["id"]: normalized_text(row["text"]) for row in source["body"]}
    result: dict[str, list[dict[str, Any]]] = {}
    for record in reference["records"]:
        if record["role"] != "body":
            continue
        spans, cursor = [], 0
        for identifier in record["source_ids"]:
            text = originals[identifier]
            spans.append((identifier, cursor, cursor + len(text)))
            cursor += len(text)
        offset = 0
        for unit in units:
            if unit.section != record["id"]:
                continue
            leaves = atoms(unit.value)
            ordered = tuple(leaves[index] for index in unit.source_order) if unit.source_order else unit.value
            stop = offset + len(normalized_text(plain(ordered)))
            result[unit.identifier] = [dict(source_id=key, source_character_start=max(0, offset - start),
                                            source_character_stop=min(end, stop) - start)
                                       for key, start, end in spans if start < stop and end > offset]
            offset = stop
        if offset != cursor:
            raise SemanticMismatch(f"incomplete source-to-unit partition: {record['id']}")
    return result


def _command_owner(page: dict[str, Any], command: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    bounds = command["bounds"]
    center = bounds["y"] + bounds["height"] / 2
    grid = page["profile"]["grid"]
    for placement in page["metadata"]["placements"]:
        top = grid["origin_y"] + placement["row"] * grid["pitch_y"]
        bottom = top + placement["rows"] * grid["pitch_y"]
        if top - .001 <= center <= bottom + .001:
            return placement["block_id"], placement
    return "decoration", None


def _cell_owner(page: dict[str, Any], placement: dict[str, Any], item: dict[str, Any]) -> tuple[str, int]:
    bounds = item["bounds"]
    x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2
    grid = page["profile"]["grid"]
    origin_x = grid["origin_x"] + placement["col"] * grid["pitch_x"]
    origin_y = grid["origin_y"] + placement["row"] * grid["pitch_y"]
    for part in placement["prefix"] + placement["parts"]:
        top = origin_y + part["row"] * grid["pitch_y"]
        for cell in part["metadata"].get("cells", []):
            frame = cell["frame"]
            left, upper = origin_x + frame["x_pt"], top + frame["y_pt"]
            if left - .001 <= x <= left + frame["width"] + .001 and upper - .001 <= y <= upper + frame["height"] + .001:
                return cell["cell_id"], page["page_number"]
    raise SemanticMismatch(f"table text has no authored cell: {placement['block_id']}")


def _check_vectors(scene: Any, page: Any) -> int:
    commands = [command for command in scene.commands if isinstance(command, (Line, Polyline, Rectangle))]
    drawings = page.get_drawings()
    if len(commands) != len(drawings):
        raise SemanticMismatch("native vector count differs from fixed scene")
    for index, (command, drawing) in enumerate(zip(commands, drawings, strict=True)):
        width = command.stroke_width if isinstance(command, Rectangle) else command.width
        if (abs(width - drawing["width"]) > .003 or not _near(command.color, drawing["color"])
                or drawing["stroke_opacity"] != 1 or drawing["fill"] is not None
                or drawing["dashes"] != "[] 0"):
            raise SemanticMismatch(f"native vector style differs: page {page.number + 1}, {index}")
        if isinstance(command, Rectangle):
            if len(drawing["items"]) != 1 or drawing["items"][0][0] != "re" or not _near(
                    (command.x, command.y, command.x + command.width, command.y + command.height), drawing["items"][0][1]):
                raise SemanticMismatch("native rectangle geometry differs")
            continue
        points = [(command.x1, command.y1), (command.x2, command.y2)] if isinstance(command, Line) else [(p.x, p.y) for p in command.points]
        expected = list(zip(points, points[1:]))
        actual = drawing["items"]
        if isinstance(command, Polyline) and command.closed and len(actual) == len(expected) + 1:
            expected.append((points[-1], points[0]))
        if len(actual) != len(expected) or any(item[0] != "l" or not _near((*start, *end), (*item[1], *item[2]))
                for item, (start, end) in zip(actual, expected)):
            raise SemanticMismatch(f"native vector geometry differs: page {page.number + 1}, {index}")
    return len(commands)


def _check_glyphs(scene: Any, page: Any, fonts: Any) -> tuple[dict[int, list[str]], int]:
    glyphs = [(character, span) for span in page.get_texttrace() for character in span["chars"]
              if not chr(character[0]).isspace()]
    cursor = 0
    identifiers: dict[int, list[str]] = defaultdict(list)
    for command_index, command in enumerate(scene.commands):
        if not isinstance(command, Text):
            continue
        text = fonts.normalize_text(command.text)
        dx, dy = ((1, 0), (0, -1), (-1, 0), (0, 1))[command.quarter_turns]
        for offset, char in enumerate(text):
            if char.isspace():
                continue
            if cursor >= len(glyphs):
                raise SemanticMismatch("native PDF glyph is missing")
            glyph, span = glyphs[cursor]
            advance = fonts.measure(text[:offset], command.style).width
            origin = (command.x + dx * advance, command.y + dy * advance)
            face = fonts.resolve(command.style.font).pdf_name
            if (chr(glyph[0]) != char or not _near(glyph[2], origin, .03)
                    or abs(span["size"] - command.style.size) > .01 or not _near(span["dir"], (dx, dy))
                    or span["color"] != (0, 0, 0) or span["opacity"] != 1 or span["type"] != 0
                    or not face.startswith(span["font"])):
                raise SemanticMismatch(f"native glyph mismatch: page {page.number + 1}, glyph {cursor}, {char!r}")
            identifiers[command_index].append(f"{page.number + 1}/{cursor}")
            cursor += 1
    if cursor != len(glyphs):
        raise SemanticMismatch("unexpected native PDF text")
    return identifiers, cursor


def audit_frame_native(reference: dict[str, Any], result: dict[str, Any], document: Any,
                       pages: Sequence[Any], pdf_path: Path) -> dict[str, Any]:
    """Validate the actual held candidate, returning reviewable source links."""
    import pymupdf
    stage = str(reference["stage"])
    module = importlib.import_module("src.reporting.stages." + {"0610": "longitudinal", "0620": "transverse"}[stage])
    units = module.content(result)
    source = json.loads((Path(__file__).resolve().parents[1] / f"tests/fixtures/reporting/baseline/display/{stage}.json").read_text("utf-8"))
    validate_frame_source(reference, source)
    body_reference = {**reference, "records": [record for record in reference["records"] if record["role"] == "body"]}
    compare_semantics(body_reference, semantic_sections(units))
    links = _source_links(reference, units, source)
    evidence = {unit.identifier: {"id": unit.identifier, "section": unit.section,
                                  "source_ranges": links[unit.identifier], "scene_commands": [],
                                  "native_glyph_ids": [], "cells": []} for unit in units}
    by_id = {unit.identifier: unit for unit in units}
    unit_commands: dict[str, list[Any]] = defaultdict(list)
    cell_commands: dict[tuple[str, int], list[Any]] = defaultdict(list)
    seen_cells: dict[str, Counter[str]] = defaultdict(Counter)
    trace = layout_trace(pages, document.fonts)
    glyph_count = vector_count = 0
    with pymupdf.open(pdf_path) as pdf:
        if len(pdf) != len(pages):
            raise SemanticMismatch("native page count differs from fixed scene")
        for native, scene, page in zip(pdf, pages, trace["pages"], strict=True):
            if native.get_images():
                raise SemanticMismatch("raster body in frame report")
            glyphs, count = _check_glyphs(scene, native, document.fonts)
            glyph_count += count
            vector_count += _check_vectors(scene, native)
            decoration = []
            for index, (command, item) in enumerate(zip(scene.commands, page["commands"], strict=True)):
                owner, placement = _command_owner(page, item)
                if owner not in by_id:
                    if isinstance(command, Text):
                        if owner != "decoration":
                            raise SemanticMismatch(f"unmapped body text: {owner}")
                        decoration.append(command)
                    continue
                row = evidence[owner]
                row["scene_commands"].append({"page": native.number + 1, "index": index, "type": item["type"]})
                row["native_glyph_ids"].extend(glyphs.get(index, ()))
                unit_commands[owner].append(command)
                if by_id[owner].kind == "table" and isinstance(command, Text):
                    key = _cell_owner(page, placement, item)
                    cell_commands[key].append(command)
            footer = [command for command in decoration if command.y > 792]
            if len(footer) != 1 or not footer[0].text.endswith(f"8-{native.number + 1}" if stage == "0610" else str(native.number + 1)):
                raise SemanticMismatch("actual footer sequence differs")
            header = [command for command in decoration if command.y < 72]
            if stage == "0610" and (len(header) != 1 or header[0].text != "0610 線路方向荷重" or abs(header[0].x - 48) > .01):
                raise SemanticMismatch("document title must repeat once at its authored location")
    for unit in units:
        row = evidence[unit.identifier]
        if unit.kind != "table":
            row.update(verify_manuscript_scene(_value(unit.value), unit_commands[unit.identifier], document.fonts,
                       identifier=unit.identifier, include_vectors=unit.kind not in ("figure",)))
            continue
        for identifier, row_index, value in _authored_cells(unit):
            occurrences = [(key, commands) for key, commands in cell_commands.items() if key[0] == identifier]
            if not occurrences and normalized_text(plain(value)):
                raise SemanticMismatch(f"authored table cell missing: {identifier}")
            if row_index >= unit.header_rows and len(occurrences) > 1:
                raise SemanticMismatch(f"duplicated body cell: {identifier}")
            for key, commands in occurrences:
                item = verify_manuscript_scene(_value(value), commands, document.fonts, identifier=identifier, include_vectors=False)
                row["cells"].append({"id": identifier, "page": key[1], **item})
                seen_cells[unit.identifier][identifier] += 1
    records = [{"id": record["id"], "source_ids": record["source_ids"], "role": record["role"],
                "unit_ids": [unit.identifier for unit in units if unit.section == record["id"]],
                "exception": record.get("reason")} for record in reference["records"]]
    return {"schema_version": 1, "stage": stage, "source_pdf_sha256": reference["source_pdf_sha256"],
            "pdf_sha256": hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest(), "pages": len(pages),
            "native_glyph_count": glyph_count, "native_vector_count": vector_count,
            "records": records, "units": list(evidence.values())}
