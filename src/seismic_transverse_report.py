"""Public 0720 entry point; calculated snapshots flow through GridLayoutPdf."""

from pathlib import Path

from .reporting.stages.seismic_transverse import render


def render_seismic_transverse_report(result: dict, output_path: str | Path) -> None:
    """Render every bearing formula and case with content-driven pagination."""
    render(result, output_path)
