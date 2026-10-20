"""Pieces of the reports of a load model (decision 70): its sections, the 支承作用 tables and the combinations.

The load model writes only the sections about where its values come from (``Section``: paragraphs and tables of
text); they are printed here in the report's format, at the place the stage gives them. Every number is a Printed
value of the generic results (calc.generic); nothing is calculated here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from ....calc.bearing_actions import BearingTable
from ....calc.frame import Frame, PointLoad
from ....calc.longitudinal.combinations import EXTRACTION_NAMES
from ....loadmodel import Paragraph, Section, bearing_label
from ..frame_report import BODY_LEFT, Manuscript, Span, TableSpec, seat_moment, value

NO_COMBINATION = "該当する組合せなし（断面力0）"
GRID = Decimal("0.12")  # the layout grid of a width, pt
_TEXT_WIDTH = 432.0  # the width of a table at the body (as top_table)


def grid_width(width: float) -> float:
    """*width* down to the layout grid."""
    return float((Decimal(repr(width)) / GRID).to_integral_value(rounding=ROUND_FLOOR) * GRID)


@dataclass(frozen=True)
class Points:
    points: tuple[PointLoad, ...]


@dataclass(frozen=True)
class DeadView:
    """What the train path's renderers of D1, D2 and the buoyancy read of a 0610 / 0620 result."""

    frame: Frame
    fixed: Any
    additional: Any
    buoyancy: Any
    points: dict[Any, tuple[PointLoad, ...]]
    snow: None = None

    def basic(self, case: Any) -> Points:
        return Points(self.points[case])


def sections(m: Manuscript, key: str, heading: str, items: Sequence[Section], level: int = 2) -> None:
    """The load model's sections under *heading*: each its title, its paragraphs and its tables of text."""
    m.heading(f"{key}.heading", heading, level)
    for number, section in enumerate(items, 1):
        m.heading(f"{key}.{number}.heading", f"{number}) {section.title}", level + 1)
        for index, block in enumerate(section.blocks, 1):
            where = f"{key}.{number}.{index}"
            if isinstance(block, Paragraph):
                m.paragraph(where, block.text)
            else:
                width = grid_width(_TEXT_WIDTH / len(block.columns))
                rows = (block.columns, *block.rows)
                m.table(where, TableSpec((width,) * len(block.columns), tuple(rows), (14.28,) * len(rows),
                                         left=BODY_LEFT))


def bearing_table(m: Manuscript, key: str, frame: Frame, table: BearingTable, arm: str) -> None:
    """The 支承作用 of a case on the frame: N × lever + H × y by bearing and the sums at the bearing seat."""
    rows: list[tuple[Any, ...]] = [("支承", "鉛直力\n(kN)", f"{arm}\n(m)", "N×アーム\n(kN・m)", "水平力\n(kN)",
                                    "作用高さ\n(m)", "H×y\n(kN・m)", "モーメント\n(kN・m)")]
    for row in table.rows:
        rows.append((Span(bearing_label(row.bearing), align="left"), value(row.n), value(row.arm), value(row.nm),
                     value(row.h), value(row.y), value(row.hm), value(row.m)))
    rows.append(("合計", value(table.n), "", "", value(table.h), "", "", value(table.m)))
    m.table(key, TableSpec((60, 52.08, 52.08, 56.04, 52.08, 52.08, 52.08, 56.04), tuple(rows),
                           (28.56,) + (14.28,) * (len(rows) - 1),
                           numeric=frozenset(range(1, 8)), left=BODY_LEFT, open=True))
    seat_moment(m, key + ".seat", frame, table.n, table.m, table.point)


def extraction_table(m: Manuscript, extractions: Sequence[Any], empty: frozenset[Any]) -> None:
    """The 8 extraction groups with their combinations; a group without one is the zero case (decision 70)."""
    width = max(len(extraction.combinations) for extraction in extractions)
    rows: list[tuple[Any, ...]] = [("No", "名称", *(f"C{index}" for index in range(1, width + 1)), "備考")]
    for extraction in extractions:
        numbers = [str(number) for number in extraction.combinations]
        rows.append((str(extraction.number), EXTRACTION_NAMES[extraction.group], *numbers,
                     *[""] * (width - len(numbers)), NO_COMBINATION if extraction.group in empty else ""))
    m.table("extraction", TableSpec((28.8, 108, *(36.0,) * width, 180.0),
                                    tuple(rows), (14.28,) * len(rows), numeric=frozenset({0, *range(2, 2 + width)})))
