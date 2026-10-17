"""Public 0600 entry point; the reaction result flows through GridLayoutPdf."""

from pathlib import Path

from .reporting.stages.reaction import render


def render_reaction_report(result: dict, output_path: str | Path) -> None:
    """Render the current semantic manuscript through native GridLayoutPdf."""
    render(result, output_path)
