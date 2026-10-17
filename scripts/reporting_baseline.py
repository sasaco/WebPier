"""Freeze and inspect the pre-migration reports without publishing a generation.

This is QA tooling, not a runtime fallback. ``capture`` requires an already
frozen source tree and refuses to overwrite an existing fixture directory.
Expected content comes from the old calculation snapshots and old PDFs, never
from the new grid renderer. An external-app acceptance is not performed here.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Any


STAGES = ("0500", "0600", "0610", "0620", "0710", "0720")
PUBLIC_RENDERERS = {
    "0500": "src.report:render_report",
    "0600": "src.reaction_report:render_reaction_report",
    "0610": "src.longitudinal_report:render_longitudinal_report",
    "0620": "src.transverse_report:render_transverse_report",
    "0710": "src.seismic_longitudinal_report:render_seismic_longitudinal_report",
    "0720": "src.seismic_transverse_report:render_seismic_transverse_report",
}
COMPATIBILITY_RENDERERS = {
    "0610": "src.longitudinal_report_reference:render_longitudinal_report",
    "0620": "src.transverse_report_style:render_transverse_report",
}


class BaselineMismatch(ValueError):
    """An independently frozen item is missing, reordered or changed."""


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _pointer_part(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def result_records(stage: str, value: Any) -> list[dict[str, Any]]:
    """Index all leaves and empty containers by RFC 6901 path, including zeros.

    Object key order is immaterial; array order, signs, scalar types, precision,
    missing values and empty container types are significant. No numeric
    tolerance or conversion of None to zero is applied.
    """
    records: list[dict[str, Any]] = []

    def visit(item: Any, pointer: str) -> None:
        if isinstance(item, dict) and item:
            for key in sorted(item):
                visit(item[key], pointer + "/" + _pointer_part(str(key)))
        elif isinstance(item, (list, tuple)) and item:
            for index, child in enumerate(item):
                visit(child, pointer + f"/{index}")
        else:
            kind = ("array" if isinstance(item, (tuple, list)) else
                    "object" if isinstance(item, dict) else
                    "null" if item is None else
                    "boolean" if isinstance(item, bool) else
                    "number" if isinstance(item, (int, float)) else "string")
            records.append({"id": f"{stage}/result{pointer}", "kind": kind,
                            "value": list(item) if isinstance(item, tuple) else item})

    visit(value, "")
    return records


def assert_records_equal(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> None:
    """Compare ordered semantic records; extra and duplicate IDs are errors."""
    for label, rows in (("expected", expected), ("actual", actual)):
        identifiers = [row["id"] for row in rows]
        if len(set(identifiers)) != len(identifiers):
            raise BaselineMismatch(f"{label}: duplicate stable IDs")
    if len(expected) != len(actual):
        raise BaselineMismatch(f"record count: {len(actual)} != {len(expected)}")
    for index, (reference, observed) in enumerate(zip(expected, actual, strict=True)):
        if canonical(reference) != canonical(observed):
            raise BaselineMismatch(f"record {index}: {reference['id']} differs: "
                                   f"{canonical(observed)[:180]}")


def extract_pdf_records(path: Path, stage: str) -> dict[str, Any]:
    """Capture every native text span in content-stream order and its location.

    Stable IDs use the old report's global ordinal, not the future page number.
    Original geometry/colour remains forensic evidence; it is not a required
    coordinate in the new variable-page monochrome report. Builders must map
    these IDs to semantic content explicitly instead of resetting expectations.
    """
    import pymupdf

    body: list[dict[str, Any]] = []
    decorations: list[dict[str, Any]] = []
    locations: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    page_number = re.compile(r"^(?:5|6|8|9|10|11)\s*[-−]\s*\d+$")
    with pymupdf.open(path) as document:
        for page_index, page in enumerate(document):
            pages.append({"page": page_index + 1, "width": page.rect.width,
                          "height": page.rect.height, "rotation": page.rotation,
                          "images": len(page.get_images()),
                          "drawing_count": len(page.get_drawings())})
            for block_index, block in enumerate(page.get_text("dict", sort=False)["blocks"]):
                for line_index, line in enumerate(block.get("lines", [])):
                    for span_index, span in enumerate(line["spans"]):
                        text = span["text"]
                        bbox = span["bbox"]
                        decoration = ((bbox[1] < 60 or bbox[1] > 795)
                                      and bool(page_number.fullmatch(text.strip())))
                        decoration |= bbox[1] > 795 and "入力 SHA256:" in text
                        target = decorations if decoration else body
                        role = "decoration" if decoration else "display"
                        stable_id = f"{stage}/{role}/{len(target) + 1:06d}"
                        target.append({"id": stable_id, "kind": "text", "text": text})
                        locations.append({"id": stable_id, "source_page": page_index + 1,
                                          "block": block_index, "line": line_index,
                                          "span": span_index, "bbox": list(bbox),
                                          "origin": list(span["origin"]),
                                          "direction": list(line["dir"]),
                                          "font": span["font"], "size": span["size"],
                                          "color": span["color"]})
    if not body:
        raise BaselineMismatch(f"{stage}: PDF contains no native body text")
    return {"schema_version": 1, "stage": stage, "source_pdf_sha256": file_sha256(path),
            "pages": pages, "body": body, "decorations": decorations, "locations": locations}


def renderer_inventory(package: Path) -> dict[str, Any]:
    """Find PDF-producing definitions/aliases separately from Tk/PDF preview."""
    definitions: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    canvas_calls: list[dict[str, Any]] = []
    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        module = "src." + path.stem
        canvas_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "reportlab.pdfgen.canvas":
                canvas_names.update(alias.asname or alias.name for alias in node.names if alias.name == "Canvas")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("render_") and node.name.endswith("report"):
                    definitions.append({"entry": module + ":" + node.name, "line": node.lineno,
                                        "parameters": [arg.arg for arg in node.args.args]})
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name.startswith("render_") and alias.name.endswith("report"):
                        aliases.append({"entry": module + ":" + (alias.asname or alias.name),
                                        "source_module": node.module, "line": node.lineno})
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in canvas_names:
                canvas_calls.append({"module": module, "line": node.lineno})
    return {"schema_version": 1, "public": PUBLIC_RENDERERS,
            "compatibility": COMPATIBILITY_RENDERERS,
            "definitions": definitions, "aliases": aliases, "canvas_calls": canvas_calls,
            "readers_only": ["src.pdf_preview", "src.pdf_preview_dialog"],
            "generation_boundary": "src.cli:_render_reports",
            "candidate_boundary": "src.cli:prepare_generation"}


def verify_fixture(root: Path) -> dict[str, Any]:
    """Verify recorded files exactly; the manifest is an externally reviewed root."""
    manifest = read_json(root / "manifest.json")
    expected = {row["path"] for row in manifest["files"]}
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*")
              if path.is_file() and path.name != "manifest.json"}
    if expected != actual:
        raise BaselineMismatch(f"fixture file set changed: missing={expected - actual}, extra={actual - expected}")
    for row in manifest["files"]:
        path = root / row["path"]
        if path.is_symlink() or file_sha256(path) != row["sha256"]:
            raise BaselineMismatch(f"fixture hash changed: {row['path']}")
    return manifest


def source_drift(run: Path, *, roles: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    frozen = read_json(run / "freeze-manifest.json")
    for row in frozen["files"]:
        if roles and row["role"] not in roles:
            continue
        path = Path(row["source"])
        actual = file_sha256(path) if path.is_file() else None
        if actual != row["sha256"]:
            changes.append({"source": str(path), "role": row["role"],
                            "expected": row["sha256"], "actual": actual})
    if not roles or "app-source" in roles:
        known = {Path(row["source"]) for row in frozen["files"] if row["role"] == "app-source"}
        app = Path(frozen["app"])
        for folder in ("src", "scripts"):
            for path in sorted((app / folder).rglob("*")):
                if (path.is_file() and path.suffix in {".py", ".json", ".png", ".md"}
                        and "__pycache__" not in path.parts and path.resolve() not in known):
                    changes.append({"source": str(path), "role": "app-source-added",
                                    "expected": None, "actual": file_sha256(path)})
    return changes


def _reaction_display(result: dict[str, Any]) -> dict[str, Any]:
    from src.reaction_report import _text_overrides
    from src.reaction_report_layout import format_value, load_layout
    from src.reaction_report_values import build_display_values

    values = build_display_values(result)
    captions = _text_overrides(result)
    rendered_values = {sheet: {**cells, **captions.get(sheet, {})} for sheet, cells in values.items()}
    layout = load_layout()
    cells: dict[str, dict[str, Any]] = {}
    for page in layout["pages"]:
        for cell in page["cells"]:
            sheet, address = page["sheet"], cell["address"]
            style = layout["styles"][cell["style"]]
            value = rendered_values.get(sheet, {}).get(address, cell.get("value"))
            identifier = f"0600/cell/{_pointer_part(sheet)}/{address}/{_pointer_part(style['format'])}"
            record = {"id": identifier, "sheet": sheet, "address": address,
                      "value": value, "number_format": style["format"],
                      "formatted": format_value(value, style["format"]),
                      "blank_zero": bool(cell.get("blank_zero")),
                      "dynamic": bool(cell.get("dynamic")),
                      "formula": layout["formulas"].get(sheet, {}).get(address)}
            if identifier in cells and cells[identifier] != record:
                raise BaselineMismatch(f"conflicting repeated source cell {identifier}")
            cells[identifier] = record
    return {"schema_version": 1, "values": values, "caption_overrides": captions,
            "formatted_cells": list(cells.values()), "formulas": layout["formulas"],
            "constants": layout["constants"], "public_values_double": result["public_values"],
            "macro_handoff_single": result["macro_handoff_single"],
            "result_cells_double": result["cells"]}


def _load_frozen_modules(run: Path) -> Any:
    if any(name == "src" or name.startswith("src.") for name in sys.modules):
        raise BaselineMismatch("capture must start in a fresh process without live app modules")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(run / "app"))
    cli = importlib.import_module("src.cli")
    if not Path(cli.__file__).resolve().is_relative_to((run / "app").resolve()):
        raise BaselineMismatch("capture imported live app instead of frozen code")
    return cli


def capture(run: Path, fixture: Path) -> dict[str, Any]:
    """Capture a validated ordinary candidate; never invoke candidate.publish()."""
    run = run.resolve()
    freeze = read_json(run / "freeze-manifest.json")
    for row in freeze["files"]:
        if file_sha256(run / row["copy"]) != row["sha256"]:
            raise BaselineMismatch(f"frozen source changed: {row['copy']}")
    if fixture.exists():
        raise BaselineMismatch(f"refusing to overwrite baseline: {fixture}")
    cli = _load_frozen_modules(run)
    fixture.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(run / "app/pre/input.json", fixture / "input.json")
    write_json(fixture / "source-manifest.json", freeze)
    dependency_manifest = run / "installed-dependencies.json"
    if not dependency_manifest.is_file():
        raise BaselineMismatch("installed dependency manifest must be frozen before generation")
    shutil.copyfile(dependency_manifest, fixture / "installed-dependencies.json")
    write_json(fixture / "renderer-inventory.json", renderer_inventory(run / "app/src"))
    options = cli.GenerationOptions(run / "app/pre/input.json", run / "candidate-output",
                                    run / "candidate-post", stage="all", overwrite=False, jrsnap=False)
    summary: dict[str, Any] = {"published": False, "stage_counts": {}, "generation": "held ordinary candidate"}
    with cli.prepare_generation(options) as candidate:
        candidate.validate_unchanged()
        snapshot_before = canonical(candidate.computed)
        for stage in STAGES:
            result = candidate.computed[stage]
            native_pdf = candidate.read_paths[candidate.declared[f"{stage}.result_pdf"]]
            pdf = fixture / "pdfs" / f"{stage}.pdf"
            pdf.parent.mkdir(exist_ok=True)
            shutil.copyfile(native_pdf, pdf)
            native_json = candidate.read_paths[candidate.declared[f"{stage}.result_json"]]
            target_json = fixture / "results" / f"{stage}.json"
            target_json.parent.mkdir(exist_ok=True)
            shutil.copyfile(native_json, target_json)
            leaves = result_records(stage, result)
            content = extract_pdf_records(pdf, stage)
            write_json(fixture / "result-records" / f"{stage}.json", leaves)
            write_json(fixture / "display" / f"{stage}.json", content)
            summary["stage_counts"][stage] = {"result_records": len(leaves),
                                              "display_records": len(content["body"]),
                                              "decoration_records": len(content["decorations"]),
                                              "pages": len(content["pages"])}
        display = _reaction_display(candidate.computed["0600"])
        write_json(fixture / "reaction-display.json", display)
        summary["reaction_display_value_count"] = sum(len(cells) for cells in display["values"].values())
        summary["reaction_formatted_cell_count"] = len(display["formatted_cells"])
        for role, path in candidate.declared.items():
            if role.endswith(".native"):
                shutil.copyfile(candidate.read_paths[path], fixture / (role.replace(".", "-") + ".json"))
        summary["held_artifact_count"] = len(candidate.artifact_hashes)
        summary["input_sha256"] = candidate.input_sha256
        if canonical(candidate.computed) != snapshot_before:
            raise BaselineMismatch("baseline extraction mutated the computed snapshot")
        candidate.validate_unchanged()
    summary["no_candidate_destinations_published"] = not any(
        path.is_file() for name in ("candidate-output", "candidate-post")
        for path in (run / name).rglob("*"))
    summary["frozen_source_drift_after_capture"] = [row["copy"] for row in freeze["files"]
                                                 if file_sha256(run / row["copy"]) != row["sha256"]]
    summary["protected_original_drift_after_capture"] = source_drift(run, roles=("input", "published", "reference"))
    write_json(fixture / "capture-summary.json", summary)
    files = [{"path": path.relative_to(fixture).as_posix(), "sha256": file_sha256(path),
              "size": path.stat().st_size} for path in sorted(fixture.rglob("*")) if path.is_file()]
    manifest = {"schema_version": 1, "origin": "pre-migration old-code result/PDF capture",
                "freeze_manifest_sha256": file_sha256(run / "freeze-manifest.json"),
                "fixture_source_run": str(run), "files": files}
    write_json(fixture / "manifest.json", manifest)
    verify_fixture(fixture)
    return summary


def probe_jrsnap(run: Path, destination: Path) -> dict[str, Any]:
    """Exercise the frozen real NDU engine with a held 0710 candidate only."""
    run = run.resolve()
    freeze = read_json(run / "freeze-manifest.json")
    for row in freeze["files"]:
        if file_sha256(run / row["copy"]) != row["sha256"]:
            raise BaselineMismatch(f"frozen source changed: {row['copy']}")
    if destination.exists():
        raise BaselineMismatch(f"refusing to overwrite probe: {destination}")
    cli = _load_frozen_modules(run)
    destination.mkdir(parents=True, exist_ok=False)
    options = cli.GenerationOptions(run / "app/pre/input.json", run / "jrsnap-output",
                                    run / "jrsnap-post", stage="0710", overwrite=False, jrsnap=True)
    with cli.prepare_generation(options) as candidate:
        candidate.validate_unchanged()
        for role, path in {**candidate.declared, **candidate.sidecars}.items():
            shutil.copyfile(candidate.read_paths[path], destination / path.name)
        write_json(destination / "native-model.json", candidate.ndu_model)
        for stage in ("0500", "0710"):
            expected = read_json(run / "captured-fixture/results" / f"{stage}.json")
            if canonical(candidate.computed[stage]) != canonical(expected):
                raise BaselineMismatch(f"{stage}: optional export changed calculations")
        summary = {"stage": "0710", "jrsnap": True, "published": False,
                   "app_read_verified": False, "analysis_run": False,
                   "artifact_count": len(candidate.artifact_hashes),
                   "input_sha256": candidate.input_sha256,
                   "calculation_snapshot_sha256": dict(candidate.canonical_snapshot_sha256),
                   "files": [{"name": path.name, "sha256": file_sha256(path)}
                             for path in sorted(destination.iterdir())]}
        candidate.validate_unchanged()
    summary["no_candidate_destinations_published"] = not any(
        path.is_file() for name in ("jrsnap-output", "jrsnap-post")
        for path in (run / name).rglob("*"))
    summary["protected_original_drift"] = source_drift(run, roles=("input", "published", "reference"))
    write_json(destination / "probe-summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture_parser = commands.add_parser("capture")
    capture_parser.add_argument("--run", type=Path, required=True)
    capture_parser.add_argument("--fixture", type=Path, required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--fixture", type=Path, required=True)
    drift_parser = commands.add_parser("source-drift")
    drift_parser.add_argument("--run", type=Path, required=True)
    probe_parser = commands.add_parser("probe-jrsnap")
    probe_parser.add_argument("--run", type=Path, required=True)
    probe_parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "capture":
        result = capture(args.run, args.fixture)
    elif args.command == "verify":
        result = {"ok": True, "file_count": len(verify_fixture(args.fixture)["files"])}
    elif args.command == "probe-jrsnap":
        result = probe_jrsnap(args.run, args.destination)
    else:
        result = {"changes": source_drift(args.run)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
