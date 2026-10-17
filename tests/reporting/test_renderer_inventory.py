"""Keep all public and legacy entrypoints visible while their renderer changes."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
from pathlib import Path

import pytest

from scripts.reporting_baseline import (
    COMPATIBILITY_RENDERERS, PUBLIC_RENDERERS, STAGES, read_json, renderer_inventory,
)


APP = Path(__file__).resolve().parents[2]
BASELINE = APP / "tests/fixtures/reporting/baseline"


@pytest.mark.parametrize("stage", STAGES)
def test_public_renderer_result_output_signature_is_preserved(stage: str) -> None:
    module, name = PUBLIC_RENDERERS[stage].split(":")
    renderer = getattr(importlib.import_module(module), name)
    assert callable(renderer)
    parameters = list(inspect.signature(renderer).parameters.values())
    assert [parameter.name for parameter in parameters[:2]] == ["result", "output_path"]
    assert all(parameter.default is not inspect.Parameter.empty
               or parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
               for parameter in parameters[2:])


def test_inventory_records_legacy_paths_and_distinguishes_preview_readers() -> None:
    inventory = read_json(BASELINE / "renderer-inventory.json")
    assert inventory["public"] == PUBLIC_RENDERERS
    assert inventory["compatibility"] == COMPATIBILITY_RENDERERS
    definitions = {row["entry"] for row in inventory["definitions"]}
    assert set(COMPATIBILITY_RENDERERS.values()) <= definitions
    assert len(inventory["canvas_calls"]) == 8
    assert not any("pdf_preview" in row["module"] for row in inventory["canvas_calls"])
    assert len(inventory["readers_only"]) == 2


RETIRED_RENDERERS = (
    "longitudinal_example2_report", "longitudinal_report_reference", "transverse_report_example2",
    "transverse_report_example2_cases", "transverse_report_example2_loads", "transverse_report_style",
    "frame_model_report", "reaction_report_diagrams", "reaction_report_horizontal",
    "reaction_report_pagination", "reaction_report_snow",
)


def test_live_package_has_no_legacy_canvas_renderer() -> None:
    """The frozen inventory records 8 Canvas paths; none may remain reachable."""
    live = renderer_inventory(APP / "src")
    assert live["canvas_calls"] == []
    assert len(live["readers_only"]) == 2
    # Font metrics may still come from ReportLab; PDF drawing may not.
    drawing = [path.relative_to(APP).as_posix() for path in (APP / "src").rglob("*.py")
               if "reportlab.pdfgen" in path.read_text(encoding="utf-8-sig")]
    assert drawing == []
    for name in RETIRED_RENDERERS:
        assert importlib.util.find_spec(f"src.{name}") is None, name
    for stage, entry in PUBLIC_RENDERERS.items():
        module, function = entry.split(":")
        source = inspect.getsource(importlib.import_module(module))
        assert "reportlab" not in source and "Canvas" not in source, stage
        assert "reporting.stages." in source, stage


def test_static_inventory_does_not_misclassify_tk_canvas(tmp_path: Path) -> None:
    package = tmp_path / "src"
    package.mkdir()
    (package / "readers.py").write_text("import tkinter as tk\nwidget = tk.Canvas(None)\n", encoding="utf-8")
    (package / "report.py").write_text(
        "from reportlab.pdfgen.canvas import Canvas as PdfCanvas\n"
        "def render_report(result, output_path):\n    PdfCanvas(output_path)\n", encoding="utf-8")
    result = renderer_inventory(package)
    assert result["canvas_calls"] == [{"module": "src.report", "line": 3}]


def test_cli_dispatch_still_contains_all_six_public_functions() -> None:
    from src import cli

    tree = ast.parse(inspect.getsource(cli._render_reports))
    choices = next(node.value for node in tree.body[0].body
                   if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict))
    assert isinstance(choices, ast.Dict)
    assert {key.value for key in choices.keys if isinstance(key, ast.Constant)} == set(STAGES)
    assert {value.id for value in choices.values if isinstance(value, ast.Name)} == {
        entry.partition(":")[2] for entry in PUBLIC_RENDERERS.values()
    }
