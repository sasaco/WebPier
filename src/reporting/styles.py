"""Point-based report settings measured from the four appearance references."""

from __future__ import annotations

import math
from numbers import Real

from gridlayoutpdf import GridSpec, PageProfile, ReportStyle, TextStyle

# The measured 14.52 pt indentation, 14.28/12.84/23.04 pt rows and .12 pt
# rules share this placement quantum. It is not a character-cell size.
PITCH = 0.12
BODY = TextStyle(font="body", size=9.9)
HEADING = TextStyle(font="heading", size=9.9)
SMALL = TextStyle(font="body", size=6.5)
BODY_LEADING = 14.28
INDENT = 14.52
BASELINE = 11.52
REPORT_STYLE = ReportStyle(body=BODY, heading=HEADING, baseline_offset=BASELINE)


def finite(value: float, name: str, *, positive: bool = False) -> float:
    """Reject ambiguous/nonfinite layout values before converting units."""
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")
    return float(value)


def grid_units(points: float, pitch: float = PITCH) -> int:
    """Convert exact authored point distances; never silently snap a value."""
    points = finite(points, "points")
    pitch = finite(pitch, "pitch", positive=True)
    units = round(points / pitch)
    if not math.isclose(units * pitch, points, rel_tol=0, abs_tol=1e-7):
        raise ValueError(f"{points} pt is not representable on the {pitch} pt grid")
    return units


def report_profile(
    *, left: float = 48, right: float = 576, top: float = 72, bottom: float = 792,
    pitch: float = PITCH,
) -> PageProfile:
    """A4 envelope enclosing the measured ink; chapter indents are independent."""
    return PageProfile(
        "p7-reference-appearance", 595, 842,
        GridSpec(left, top, pitch, pitch, grid_units(right - left, pitch),
                 grid_units(bottom - top, pitch)),
    )
