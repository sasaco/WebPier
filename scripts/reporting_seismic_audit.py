"""Independent source/manuscript/scene/native-PDF verification for 0710 and 0720."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
import hashlib
import importlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pymupdf
from gridlayoutpdf import Line, Polyline, Rectangle, Text

from reporting_semantic_audit import SemanticMismatch, compare_semantics, verify_manuscript_scene


def _ownership(scene: Any) -> list[str]:
    """Read only ownership, not expected text or expected drawing coordinates."""
    owners = []
    for placement in scene.metadata["placements"]:
        for part in (*placement["prefix"], *placement["parts"]):
            metadata = part["metadata"]
            count = metadata.get("command_count", 0)
            if "semantic_command_owners" in metadata:
                explicit = list(metadata["semantic_command_owners"])
                if len(explicit) != count:
                    raise SemanticMismatch("figure ownership count differs")
                owners.extend(explicit)
            else:
                owners.extend([metadata.get("semantic_id", "unmapped")] * count)
    body_count = len(owners)
    remaining = scene.commands[body_count:]
    if len(remaining) != 1 or not isinstance(remaining[0], Text):
        raise SemanticMismatch("body ownership count differs or footer is absent")
    owners.append("decoration/footer")
    return owners


def _vectors(page: Any, commands: Sequence[Any]) -> int:
    expected = [command for command in commands if isinstance(command, (Line, Polyline, Rectangle))]
    actual = page.get_drawings()
    if len(actual) != len(expected):
        raise SemanticMismatch(f"page {page.number + 1}: vector count differs")
    for command, drawing in zip(expected, actual, strict=True):
        width = command.stroke_width if isinstance(command, Rectangle) else command.width
        color = command.color
        dash = getattr(command, "dash", ())
        dashes = "[ " + " ".join(f"{length:g}" for length in dash) + " ] 0" if dash else "[] 0"
        if (drawing.get("fill") is not None or abs(drawing["width"] - width) > .001
                or drawing["dashes"] != dashes
                or any(abs(a - b) > .001 for a, b in zip(drawing["color"], color, strict=True))):
            raise SemanticMismatch("native vector stroke/color differs")
        if isinstance(command, Rectangle):
            items = drawing["items"]
            if (len(items) != 1 or items[0][0] != "re"
                    or any(abs(a - b) > .001 for a, b in zip(items[0][1],
                          (command.x, command.y, command.x + command.width, command.y + command.height), strict=True))):
                raise SemanticMismatch("native rectangle differs")
            continue
        points = [(command.x1, command.y1), (command.x2, command.y2)] if isinstance(command, Line) else [(p.x, p.y) for p in command.points]
        segments = list(zip(points, points[1:]))
        items = drawing["items"]
        if isinstance(command, Polyline) and command.closed and len(items) == len(segments) + 1:
            segments.append((points[-1], points[0]))
        elif isinstance(command, Polyline) and bool(drawing["closePath"]) != command.closed:
            raise SemanticMismatch("native polyline closure differs")
        if len(items) != len(segments):
            raise SemanticMismatch("native vector segment count differs")
        for item, (start, end) in zip(items, segments, strict=True):
            if item[0] != "l" or any(abs(a - b) > .001 for a, b in zip((*start, *end), (*item[1], *item[2]), strict=True)):
                raise SemanticMismatch("native vector geometry differs")
    return len(expected)


def verify_frame_geometry(result: dict[str, Any], pages: Sequence[Any], stage: str) -> dict[str, Any]:
    """Check member endpoints at one isotropic physical scale, independently of fit_frame."""
    scene = next(page for page in pages if any(p["block_id"] == stage + "/frame" for p in page.metadata["placements"]))
    owned = [(owner, command) for owner, command in zip(_ownership(scene), scene.commands, strict=True)
             if owner.startswith(stage + "/frame.")]
    members = [command for _, command in owned if isinstance(command, Line) and command.width in (.8, 1.6)]
    marks = [command for _, command in owned if isinstance(command, Rectangle)
             and command.width == 2.4 and command.height == 2.4 and command.stroke_width == .48]
    frame = result["frame"]
    nodes = {node["id"]: node for node in frame["nodes"]}
    if len(members) != len(frame["members"]) or len(marks) != len(nodes):
        raise SemanticMismatch("physical graph member/node count differs")
    centers = {node["id"]: (mark.x + 1.2, mark.y + 1.2) for node, mark in zip(frame["nodes"], marks, strict=True)}
    bottom = min(nodes.values(), key=lambda node: node["y"])
    top = max(nodes.values(), key=lambda node: node["y"])
    scale = (centers[bottom["id"]][1] - centers[top["id"]][1]) / (top["y"] - bottom["y"])
    if scale <= 0:
        raise SemanticMismatch("physical graph must preserve top/down order")
    origin_x = centers[bottom["id"]][0] - bottom["x"] * scale
    origin_y = centers[bottom["id"]][1] + bottom["y"] * scale
    for identifier, node in nodes.items():
        expected = (origin_x + node["x"] * scale, origin_y - node["y"] * scale)
        if any(abs(a - b) > .001 for a, b in zip(centers[identifier], expected, strict=True)):
            raise SemanticMismatch("physical node is not at true isotropic scale")
    for source, command in zip(frame["members"], members, strict=True):
        expected = (*centers[source["node_i"]], *centers[source["node_j"]])
        if (command.width != (1.6 if source["behavior"] == "rigid" else .8)
                or any(abs(a - b) > .001 for a, b in zip((command.x1, command.y1, command.x2, command.y2), expected, strict=True))):
            raise SemanticMismatch("physical member endpoints/behavior differ")
    return {"node_count": len(nodes), "member_count": len(members), "scale_pt_per_m": scale}


def audit_seismic_native(reference: dict[str, Any] | None, result: dict[str, Any], document: Any,
                         pages: Sequence[Any], pdf_path: Path) -> dict[str, Any]:
    """Bind independent old-source units to every manuscript leaf and actual PDF glyph/vector.

    A nonbaseline input may pass reference=None; its complete authored manuscript,
    physical graph, and actual PDF are still checked. Baseline acceptance requires
    the frozen source reference and its exact ordered semantic equality.
    """
    stage = result["stage"]
    name = {"0710": "longitudinal", "0720": "transverse"}[stage]
    module = importlib.import_module(f"src.reporting.stages.seismic_{name}")
    actual = module.semantic_records(result)
    if reference is not None:
        if reference["stage"] != stage:
            raise SemanticMismatch("stage differs from source reference")
        compare_semantics(reference, actual)
    units = {unit.identifier: unit for unit in module.content(result)}
    if len(units) != len(actual):
        raise SemanticMismatch("duplicate manuscript unit IDs")
    references = {row["id"]: row for row in reference["records"]} if reference is not None else {}
    records = {identifier: {"id": identifier, "source_ids": references.get(identifier, {}).get("source_ids", []),
                             "semantic_text": next(row["text"] for row in actual if row["id"] == identifier),
                             "native_glyph_ids": [], "scene_commands": []} for identifier in units}
    commands_by_unit: dict[str, list[Any]] = defaultdict(list)
    table_fragments: dict[str, list[list[Any]]] = defaultdict(list)
    glyph_count = vector_count = 0
    with pymupdf.open(pdf_path) as pdf:
        if len(pdf) != len(pages):
            raise SemanticMismatch("native PDF page count differs from fixed scenes")
        for page, scene in zip(pdf, pages, strict=True):
            if page.get_images():
                raise SemanticMismatch("seismic PDF contains a raster body")
            owners = _ownership(scene)
            if len(owners) != len(scene.commands):
                raise SemanticMismatch("scene ownership count differs")
            vector_count += _vectors(page, scene.commands)
            glyphs = [(char, span) for block in page.get_text("rawdict")["blocks"]
                      for line in block.get("lines", []) for span in line["spans"]
                      for char in span["chars"] if not char["c"].isspace()]
            cursor = 0
            page_commands: dict[str, list[Any]] = defaultdict(list)
            for index, (command, owner) in enumerate(zip(scene.commands, owners, strict=True)):
                if owner in units:
                    commands_by_unit[owner].append(command)
                    page_commands[owner].append(command)
                    records[owner]["scene_commands"].append({"page": page.number + 1, "index": index, "type": type(command).__name__})
                elif isinstance(command, Text) and owner != "decoration/footer":
                    raise SemanticMismatch(f"unmapped body text: {owner}")
                if not isinstance(command, Text):
                    continue
                text = document.fonts.normalize_text(command.text)
                dx, dy = ((1, 0), (0, -1), (-1, 0), (0, 1))[command.quarter_turns % 4]
                font = document.fonts.resolve(command.style.font)
                for offset, character in enumerate(text):
                    if character.isspace():
                        continue
                    if cursor >= len(glyphs):
                        raise SemanticMismatch("native PDF is missing glyphs")
                    glyph, span = glyphs[cursor]
                    advance = document.fonts.measure(text[:offset], command.style).width
                    if (glyph["c"] != character or abs(glyph["origin"][0] - command.x - dx * advance) > .03
                            or abs(glyph["origin"][1] - command.y - dy * advance) > .03
                            or abs(span["size"] - command.style.size) > .01 or span["color"] != 0
                            or not font.pdf_name.startswith(span["font"])):
                        raise SemanticMismatch(f"native glyph mismatch: page {page.number + 1}, glyph {cursor}, unit {owner}")
                    if owner in records:
                        records[owner]["native_glyph_ids"].append(f"{page.number + 1}/{cursor}")
                    cursor += 1
                    glyph_count += 1
            if cursor != len(glyphs):
                raise SemanticMismatch("native PDF contains extra glyphs")
            for identifier, commands in page_commands.items():
                if units[identifier].kind == "table" and identifier.endswith(".header"):
                    table_fragments[identifier].append(commands)
    for identifier, unit in units.items():
        groups = table_fragments.get(identifier, [commands_by_unit[identifier]])
        if not groups or not records[identifier]["native_glyph_ids"]:
            raise SemanticMismatch(f"source unit did not reach PDF: {identifier}")
        for commands in groups:
            check = verify_manuscript_scene(unit.value, commands, document.fonts, identifier=identifier,
                                            include_vectors=unit.kind not in ("figure", "table"))
            records[identifier].update(check)
    audit = {"schema_version": 1, "stage": stage, "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
            "page_count": len(pages), "glyph_count": glyph_count, "vector_count": vector_count,
            "physical_graph": verify_frame_geometry(result, pages, stage), "records": list(records.values())}
    audit["appearance"] = verify_seismic_appearance(audit, pdf_path)
    return audit


def verify_seismic_appearance(audit: dict[str, Any], pdf_path: Path) -> dict[str, Any]:
    """Test actual origins/fonts/row bands against independently measured REF roles."""
    from reporting_appearance import TextSample, monochrome_errors, native_rules, painted_rule_bands, role_errors
    from reportlab.pdfbase.ttfonts import TTFontFile

    style_path = Path(__file__).resolve().parents[1] / "tests/fixtures/reporting/appearance/reference-style.json"
    style = json.loads(style_path.read_text(encoding="utf-8"))
    stage = audit["stage"]
    records = {row["id"]: row for row in audit["records"]}
    glyphs = {}
    checked = []
    with pymupdf.open(pdf_path) as pdf:
        embedded_faces = {}
        for page in pdf:
            for xref, _, _, basefont, *_ in page.get_fonts():
                if basefont not in embedded_faces:
                    raw = pdf.extract_font(xref)[3]
                    if raw:
                        embedded_faces[basefont.split("+")[-1]] = TTFontFile(BytesIO(raw)).name.decode("ascii")
        for page in pdf:
            source = [(char, span) for block in page.get_text("rawdict")["blocks"]
                      for line in block.get("lines", []) for span in line["spans"]
                      for char in span["chars"] if not char["c"].isspace()]
            for index, (glyph, span) in enumerate(source):
                faces = [face for alias, face in embedded_faces.items() if alias.startswith(span["font"])]
                if len(faces) != 1:
                    raise SemanticMismatch(f"appearance font is not uniquely embedded: {span['font']}")
                glyphs[f"{page.number + 1}/{index}"] = TextSample(glyph["c"], faces[0], span["size"],
                                                                  glyph["origin"][0], glyph["origin"][1], span["color"], page.number + 1)
            if errors := monochrome_errors(page):
                raise SemanticMismatch(f"appearance monochrome: {errors}")

        def samples(key: str) -> list[TextSample]:
            return [glyphs[key] for key in records[stage + "/" + key]["native_glyph_ids"]]

        def check(sample: TextSample, role: str, anchor: float = 58.92, baseline: float | None = None) -> None:
            errors = role_errors(sample, style["roles"][role], anchor_x=anchor, reference_baseline=baseline)
            if errors:
                raise SemanticMismatch(f"appearance {role}: {errors}")
            checked.append(role)

        for key, role in (("title", "common.chapter"), ("model.heading", "common.section"),
                          ("model.caption", "common.subsection"), ("train.heading", "common.subsection"),
                          ("train.track" if stage == "0710" else "train.up.caption", "common.subsubsection"),
                          ("actions.note", "common.body"), ("frame.nodes", "frame.node"),
                          ("frame.members", "frame.member"), ("frame.vertical_dimensions", "frame.dimension"),
                          ("train.header" if stage == "0710" else "train.up.header", "common.table_header"),
                          ("cases.row.1", "common.table_value")):
            check(samples(key)[0], role)
        formula = samples("inertia.beam")
        equals = [glyph for glyph in formula if glyph.text == "="]
        if len(equals) != 2:
            raise SemanticMismatch("appearance inertia substitution must retain both equals signs")
        check(equals[0], "foundation.substitution_equals", 93.96)
        check(equals[1], "foundation.result_equals", 93.96)
        sub_index = next(index for index, glyph in enumerate(formula) if glyph.size < 7)
        check(formula[sub_index], "common.subscript", baseline=formula[sub_index - 1].baseline)
        row = samples("cases.row.1")[0]
        bands = painted_rule_bands(native_rules(pdf[row.page - 1]), axis="h", crossing=100)
        before = max(band.coordinate for band in bands if band.coordinate < row.baseline)
        after = min(band.coordinate for band in bands if band.coordinate > row.baseline)
        table_role = "longitudinal.combination" if stage == "0710" else "transverse.combination"
        expected = style["tables"][table_role]["nominal_row_height_pt"]
        if abs(after - before - expected) > .5:
            raise SemanticMismatch(f"appearance {table_role}: actual row height {after - before} differs from {expected}")
        return {"reference_style_sha256": hashlib.sha256(style_path.read_bytes()).hexdigest(),
                "roles": checked, "table_role": table_role, "actual_row_height_pt": after - before}


def audited_sections(result: dict[str, Any], pdf_path: Path) -> tuple[list[str], dict[str, Any]]:
    """Expose heading-defined test scopes only after the complete actual-PDF audit.

    Structured scripts and individual equation runs have a different extraction
    order from the former flat strings. This finite manuscript serialization is
    usable for independent decimal-arithmetic assertions because every leaf has
    first been checked against the actual PDF, with no text/value exceptions.
    """
    name = {"0710": "longitudinal", "0720": "transverse"}[result["stage"]]
    module = importlib.import_module(f"src.reporting.stages.seismic_{name}")
    document = module.build_report(result)
    pages = document.layout()
    audit = audit_seismic_native(None, result, document, pages, pdf_path)
    sections: list[list[str]] = [[]]
    for record in audit["records"]:
        if record["id"].endswith(("/actions.heading", "/actions.continuation_heading", "/cases.heading")):
            sections.append([])
        sections[-1].append(record["semantic_text"])
    return ["\n".join(section) for section in sections], audit


def owned_pdf_glyphs(result: dict[str, Any], pdf_path: Path, identifier: str) -> list[dict[str, Any]]:
    """Return actual native glyph boxes for an independently audited semantic unit."""
    _, audit = audited_sections(result, pdf_path)
    record = next(row for row in audit["records"] if row["id"] == identifier)
    selected = set(record["native_glyph_ids"])
    output = []
    with pymupdf.open(pdf_path) as pdf:
        for page in pdf:
            glyphs = [(char, span) for block in page.get_text("rawdict")["blocks"]
                      for line in block.get("lines", []) for span in line["spans"]
                      for char in span["chars"] if not char["c"].isspace()]
            output.extend({"text": glyph["c"], "bbox": glyph["bbox"], "origin": glyph["origin"], "size": span["size"], "font": span["font"]}
                          for index, (glyph, span) in enumerate(glyphs) if f"{page.number + 1}/{index}" in selected)
    return output
