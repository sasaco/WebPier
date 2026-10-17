"""Public 0710 entry point; calculated snapshots flow through GridLayoutPdf."""

from pathlib import Path

from .reporting.stages.seismic_longitudinal import render


def render_seismic_longitudinal_report(result: dict, output_path: str | Path) -> None:
    """Render every action and case with content-driven pagination."""
    render(result, output_path)
