"""Explicit MS Mincho/Gothic font assets, also used by dependency identity."""

from __future__ import annotations

import os
from pathlib import Path

from gridlayoutpdf import FontError, FontRegistry


FONT_FACES = {
    "body": ("msmincho.ttc", 0),
    "heading": ("msgothic.ttc", 0),
    "symbol": ("msmincho.ttc", 1),
    "caption": ("msgothic.ttc", 2),
    "dimension": ("calibri.ttf", 0),
    "italic": ("timesi.ttf", 0),
}


def font_files(directory: str | Path | None = None) -> dict[str, Path]:
    """Resolve required font files without a CID or alternate-face fallback."""
    if directory is None:
        windows = os.environ.get("WINDIR")
        if not windows:
            raise FontError("WINDIR is absent; an explicit font directory is required")
        directory = Path(windows) / "Fonts"
    root = Path(directory)
    files = {name: root / filename for name, (filename, _) in FONT_FACES.items()}
    for path in files.values():
        if not path.is_file():
            raise FontError(f"Required report font is missing: {path}")
    return files


def load_fonts(directory: str | Path | None = None) -> FontRegistry:
    """Register explicit reference roles, including the measured TTC face indices."""
    registry = FontRegistry()
    for name, path in font_files(directory).items():
        registry.register(name, path, face_index=FONT_FACES[name][1])
    return registry
