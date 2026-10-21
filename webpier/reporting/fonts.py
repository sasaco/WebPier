"""The report's fonts by name (GridLayoutPdf FR-024), and the files they resolve to for dependency identity."""

from __future__ import annotations

from pathlib import Path

from gridlayoutpdf import FontError, FontRegistry
from gridlayoutpdf.fontfinder import find_font

from .styles import BODY_FONT, CAPTION_FONT, DIMENSION_FONT, HEADING_FONT

FONT_NAMES = {"body": BODY_FONT, "heading": HEADING_FONT, "caption": CAPTION_FONT, "dimension": DIMENSION_FONT}


def font_files() -> dict[str, Path]:
    """The file each report font resolves to; a missing font raises FontError (no fallback face)."""
    return {role: find_font(name).path for role, name in FONT_NAMES.items()}


def load_fonts() -> FontRegistry:
    """A registry that resolves the report fonts by name on first use (missing ones raise FontError)."""
    font_files()
    return FontRegistry()


__all__ = ["FONT_NAMES", "FontError", "font_files", "load_fonts"]
