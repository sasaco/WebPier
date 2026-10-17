"""Public 0610 entry point; the schema-2 result flows through GridLayoutPdf."""

from pathlib import Path

from .reporting.stages.longitudinal import render


def render_longitudinal_report(result: dict, output_path: str | Path) -> None:
    """Render every condition, action and case with content-driven pagination."""
    render(result, output_path)
