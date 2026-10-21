"""Report settings on GridLayoutPdf's common grid (A4, 16.08 × 15.48 pt cells).

Every position of the report is a whole number of grid columns from the body's left edge and every height a whole
number of grid rows, so that the pages also map onto the grid Excel cell by cell (GridLayoutPdf FR-021, FR-027).
"""

from __future__ import annotations

import math
from numbers import Real

from gridlayoutpdf import A4_PORTRAIT_REFERENCE, PageProfile, ReportStyle, TextStyle

# MS明朝 for the body and MSゴシック for headings, as the references; resolved by name (GridLayoutPdf FR-024).
BODY_FONT, HEADING_FONT = "MS Mincho", "MS Gothic"
CAPTION_FONT, DIMENSION_FONT = "MS PGothic", "Calibri"  # the 0600 figure titles and the outline dimensions
BODY = TextStyle(BODY_FONT, size=10)
HEADING = TextStyle(HEADING_FONT, size=10)
SMALL = TextStyle(BODY_FONT, size=6.5)
REPORT_STYLE = ReportStyle(body=BODY, heading=HEADING)

PROFILE = A4_PORTRAIT_REFERENCE
PITCH_X = PROFILE.grid.pitch_x
PITCH_Y = PROFILE.grid.pitch_y
BODY_COLUMNS = PROFILE.grid.columns


def finite(value: float, name: str, *, positive: bool = False) -> float:
    """Reject ambiguous/nonfinite layout values."""
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")
    return float(value)


def count(value: int, name: str, *, minimum: int = 0) -> int:
    """A whole number of grid columns or rows."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer of at least {minimum}")
    return value


def columns_pt(columns: int) -> float:
    """The width of *columns* grid columns, pt."""
    return count(columns, "columns") * PITCH_X


def rows_pt(rows: int) -> float:
    """The height of *rows* grid rows, pt."""
    return count(rows, "rows") * PITCH_Y


def columns_for(points: float) -> int:
    """The fewest grid columns that hold *points* pt (a figure's frame)."""
    return math.ceil(finite(points, "points") / PITCH_X - 1e-9)


def rows_for(points: float) -> int:
    """The fewest grid rows that hold *points* pt (a figure's frame)."""
    return math.ceil(finite(points, "points") / PITCH_Y - 1e-9)


def column_x(column: int) -> float:
    """The paper x of the left edge of the body column *column*, pt."""
    return PROFILE.grid.origin_x + columns_pt(column)


def report_profile() -> PageProfile:
    """The A4 portrait page of every report: GridLayoutPdf's reference grid, 30 columns × 47 rows."""
    return PROFILE
