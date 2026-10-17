"""0600 migration source audit: logical identity precedes new page layout."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

import pytest

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts"))
from reporting_semantic_audit import SemanticMismatch, trace_source_links

BASELINE = PROJECT / "tests/fixtures/reporting/baseline"
SEMANTIC = PROJECT / "tests/fixtures/reporting/semantic"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_old_trace_links_every_native_span_in_exact_order() -> None:
    trace = read_json(SEMANTIC / "0600-source-events.json")
    source = read_json(BASELINE / "display/0600.json")
    assert trace["source_pdf_sha256"] == source["source_pdf_sha256"]
    links = trace_source_links(trace, source)
    assert len(links) == 3228
    assert len({item["source_id"] for item in links}) == len(links)
    events = {event["event"]: event for event in trace["events"]}
    assert len(events) == 3308
    assert all(events[event_id]["context"] for item in links for event_id in item["event_ids"])
    first = events[links[0]["event_ids"][0]]
    assert any(context.get("cell") == {"address": "B3"} and context.get("page") == {"sheet": "死荷重"}
               for context in first["context"])


def test_old_trace_rejects_character_reordering_inside_a_value() -> None:
    trace = read_json(SEMANTIC / "0600-source-events.json")
    changed = deepcopy(trace)
    event = next(item for item in changed["events"] if len(set(item["text"])) > 2 and item["text"].replace(".", "").isdigit())
    event["text"] = event["text"][::-1]
    with pytest.raises(SemanticMismatch, match="character order"):
        trace_source_links(changed, read_json(BASELINE / "display/0600.json"))


def test_display_evaluation_uses_pure_content_without_legacy_geometry(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import reaction_report_values

    def forbidden_layout() -> None:
        pytest.fail("new display evaluation still loads the old page coordinates")

    monkeypatch.setattr(reaction_report_values, "load_layout", forbidden_layout, raising=False)
    assert hasattr(reaction_report_values, "load_content"), "pure reaction content loader is missing"
    content = reaction_report_values.load_content()
    forbidden = {"box", "bands", "diagram_regions", "paths", "x_left", "y_top", "row_start", "row_end", "page_size"}

    def keys(value: Any) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    assert not keys(content) & forbidden
    expected = read_json(BASELINE / "reaction-display.json")
    result = read_json(BASELINE / "results/0600.json")
    before = deepcopy(result)
    assert reaction_report_values.build_display_values(result) == expected["values"]
    assert sum(len(cells) for cells in expected["values"].values()) == 4601
    assert content["formulas"] == expected["formulas"]
    assert content["constants"] == expected["constants"]
    assert result == before


def test_native_reaction_manuscript_has_all_calculation_sections() -> None:
    from src.reporting.stages.reaction import content, semantic_records
    from reporting_semantic_audit import compare_semantics, validate_source_coverage

    reference = read_json(SEMANTIC / "0600.json")
    source = read_json(BASELINE / "display/0600.json")
    result = read_json(BASELINE / "results/0600.json")
    before = deepcopy(result)
    validate_source_coverage(reference, source)
    compare_semantics(reference, semantic_records(result))
    assert len(reference["records"]) == 205
    assert sum(len(record["source_ids"]) for record in reference["records"]) == 3198
    assert {unit.key.split(".")[0] for unit in content(result)} >= {
        "dead", "weights", "train", "impact", "longitudinal", "centrifugal", "lateral", "wind", "transverse"}
    assert result == before


@pytest.mark.parametrize("change", ["sign", "factor", "unit", "order", "subscript_base", "fraction"])
def test_source_audit_rejects_semantic_loss(change: str) -> None:
    from src.reporting.stages.reaction import semantic_records
    from reporting_semantic_audit import compare_semantics

    records = semantic_records(read_json(BASELINE / "results/0600.json"))
    if change == "order":
        records[2], records[3] = records[3], records[2]
    else:
        key, old, new = {
            "sign": ("longitudinal.case.1", "−", "+"),
            "factor": ("longitudinal.case.1", "1/2", "1/3"),
            "unit": ("weights.beam.92", "kN", "N"),
            "subscript_base": ("dead.support", "ＲA", "A"),
            "fraction": ("impact.pier.formula", "/", ""),
        }[change]
        record = next(record for record in records if record["id"] == "0600/" + key)
        assert old in record["text"]
        record["text"] = record["text"].replace(old, new, 1)
    with pytest.raises(SemanticMismatch):
        compare_semantics(read_json(SEMANTIC / "0600.json"), records)


@pytest.fixture(scope="module")
def native_reaction(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, ...]:
    from gridlayoutpdf import render_pdf
    from src.reporting.stages.reaction import build_report

    result = read_json(BASELINE / "results/0600.json")
    document = build_report(result)
    pages = document.layout()
    destination = tmp_path_factory.mktemp("reaction-native") / "0600.pdf"
    render_pdf(pages, destination, document.fonts)
    return result, document, pages, destination


def test_native_pdf_matches_every_authored_leaf_and_old_source(native_reaction: tuple[Any, ...]) -> None:
    from reporting_semantic_audit import audit_reaction_native

    audit = audit_reaction_native(read_json(SEMANTIC / "0600.json"), *native_reaction)
    assert len(audit["records"]) == 205
    assert audit["native_glyph_count"] > 13000
    assert all(record["native_glyph_ids"] and record["manuscript_scene"] for record in audit["records"])


@pytest.mark.parametrize("loss", ["factor", "unit", "subscript_base", "fraction"])
def test_same_scene_pdf_loss_cannot_bless_missing_content(native_reaction: tuple[Any, ...], tmp_path: Path, loss: str) -> None:
    from dataclasses import replace
    from gridlayoutpdf import Line, Text, layout_trace, render_pdf
    from reporting_semantic_audit import audit_reaction_native

    result, document, pages, _ = native_reaction
    changed = list(pages)
    trace = layout_trace(pages, document.fonts)
    for page_index, page in enumerate(changed):
        evidence = trace["pages"][page_index]
        grid = evidence["profile"]["grid"]
        formula_ranges = [(grid["origin_y"] + item["row"] * grid["pitch_y"],
                           grid["origin_y"] + (item["row"] + item["rows"]) * grid["pitch_y"])
                          for item in evidence["metadata"]["placements"]
                          if item["block_id"] == "0600/impact.pier.formula"]
        for index, command in enumerate(page.commands):
            matches = (isinstance(command, Line) and loss == "fraction"
                       and any(start <= command.y1 <= end for start, end in formula_ranges)
                       or isinstance(command, Text) and command.text == {"factor": "24.5", "unit": "kN", "subscript_base": "Ｒ"}.get(loss))
            if matches:
                changed[page_index] = replace(page, commands=page.commands[:index] + page.commands[index + 1:])
                break
        else:
            continue
        break
    else:
        pytest.fail("negative mutation target was not found")
    path = tmp_path / (loss + ".pdf")
    render_pdf(changed, path, document.fonts)
    with pytest.raises(SemanticMismatch, match="manuscript/scene"):
        audit_reaction_native(read_json(SEMANTIC / "0600.json"), result, document, changed, path)


def test_public_renderer_uses_native_stage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src import reaction_report
    from src.reporting.stages import reaction

    assert reaction_report.render is reaction.render
    sentinel = {"native": True}
    seen = []
    monkeypatch.setattr(reaction_report, "render", lambda result, path: seen.append((result, path)))
    path = tmp_path / "0600.pdf"
    reaction_report.render_reaction_report(sentinel, path)
    assert seen == [(sentinel, path)]


def test_unbreakable_large_value_preserves_existing_target(tmp_path: Path) -> None:
    from gridlayoutpdf import LayoutError
    from src.reporting.stages.reaction import render

    result = read_json(BASELINE / "results/0600.json")
    result["snow_loads"]["points"]["A"]["雪荷重_2年確率"] = 1e30
    path = tmp_path / "0600.pdf"
    path.write_bytes(b"previous publication")
    with pytest.raises(LayoutError):
        render(result, path)
    assert path.read_bytes() == b"previous publication"
