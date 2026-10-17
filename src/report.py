"""Public 0500 entry point; the foundation result flows through GridLayoutPdf."""

from pathlib import Path

from .reporting.stages.foundation import render


def render_report(result: dict, output_path: str | Path) -> None:
    """Render all current foundation content with native flowing grid blocks."""
    render(result, output_path)
