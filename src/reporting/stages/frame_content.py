"""Explicit manuscripts shared by the two non-seismic frame reports.

Units describe engineering content, never legacy paper coordinates.  Their
identifiers survive native layout so QA can follow every leaf into the PDF.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from collections.abc import Sequence
import re
from typing import Any

from gridlayoutpdf import (
    Block, Cell, CellLines, Document, Equation, Fraction, Insets, LayoutContext,
    LayoutPart, Literal, MathNode, MeasuredBlock, Root, Row, Script, Text, TextStyle,
    command_bounds, wrap_text,
)

from ..document import IndentTo, heading, paragraph, report, spacer
from ..equations import equation_group, script
from ..figures import physical_frame
from ..styles import BODY, HEADING
from ..tables import math_cell, table


def plain(value: Any) -> str:
    """Read authored leaves, independently of measurement or output commands."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Merged):
        return plain(value.value)
    if isinstance(value, (Header, VerticalHeader)):
        return plain(value.values)
    if isinstance(value, Literal):
        return value.text
    if isinstance(value, Row):
        return plain(value.items)
    if isinstance(value, Script):
        return plain((value.base, value.superscript, value.subscript))
    if isinstance(value, Fraction):
        return plain(value.numerator) + "/" + plain(value.denominator)
    if isinstance(value, Root):
        return "√" + plain(value.body)
    if isinstance(value, Equation):
        return plain((value.lhs, value.relation, value.rhs,
                      value.result_relation if value.result is not None else None,
                      value.result, value.unit))
    if isinstance(value, (tuple, list)):
        return "".join(plain(item) for item in value)
    raise TypeError(f"Unsupported frame manuscript leaf: {type(value).__name__}")


@dataclass(frozen=True)
class Merged:
    value: Any
    colspan: int = 1
    rowspan: int = 1


@dataclass(frozen=True)
class Header:
    values: tuple[Any, ...]

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        lines = []
        for value in self.values:
            if isinstance(value, str):
                lines.extend(line.text for line in wrap_text(value, context.fonts, BODY, available_width - 2.16,
                                                            max_tracking_em=0))
            else:
                lines.append(value)
        return CellLines(tuple(lines), style=BODY, line_advance=14.28, align="center",
                         inner_padding=Insets(1.08, 1.08, 1.08, 1.08)).measure(context, available_width)


@dataclass(frozen=True)
class VerticalHeader:
    values: tuple[str, str]

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        from dataclasses import replace
        first = Text(0, 0, self.values[0], BODY, quarter_turns=1)
        bounds = command_bounds(first, context.fonts)
        first = replace(first, x=1.08 - bounds.x, y=1.08 - bounds.y)
        number = context.fonts.measure(self.values[1], BODY)
        width = max(bounds.width, number.width) + 2.16
        second = Text((width - number.width) / 2, bounds.height + 1.08 + 12, self.values[1], BODY)
        height = command_bounds(second, context.fonts).bottom + 1.08
        if width > available_width:
            raise ValueError("matrix header cannot fit at the authored font size")
        return MeasuredBlock(width, context.profile.grid.pitch_y,
                             (LayoutPart(context.rows_for(height), (first, second)),), keep_together=True)


def atoms(value: Any) -> tuple[Any, ...]:
    """Authored semantic atoms, before native measurement and wrapping."""
    if isinstance(value, Merged):
        return atoms(value.value)
    if isinstance(value, (Header, VerticalHeader)):
        return atoms(value.values)
    if isinstance(value, (tuple, list)):
        return tuple(atom for item in value for atom in atoms(item))
    return (value,)


@dataclass(frozen=True)
class Unit:
    identifier: str
    section: str
    value: Any
    kind: str = "body"
    left: float = 117
    weights: tuple[float, ...] = ()
    header_rows: int = 0
    row_height: float = 14.28
    figure: tuple[Any, Any, str] | None = None
    source_order: tuple[int, ...] = ()
    keep_with_next: bool = False


def engineering_text(value: Any) -> Any:
    """Known unit powers and engineering subscripts, with unchanged plain text."""
    if not isinstance(value, str):
        return value
    pattern = re.compile(r"(?<![A-Za-z0-9_])(?:(mm|cm|m)([234])|(ω|H)([1-6]))(?![0-9])")
    pieces: list[Any] = []
    cursor = 0
    for match in pattern.finditer(value):
        if match.start() > cursor:
            pieces.append(value[cursor:match.start()])
        if match[1]:
            pieces.append(script(match[1], superscript=match[2]))
        else:
            pieces.append(script(match[3], subscript=match[4]))
        cursor = match.end()
    if not pieces:
        return value
    if cursor < len(value):
        pieces.append(value[cursor:])
    return Row(*pieces)


_BINARY = re.compile(r" [×÷+＋−\-/] ")


class Manuscript:
    """Ordered, result-only content with stable semantic sections and units."""

    def __init__(self, stage: str) -> None:
        self.stage, self.current = stage, ""
        self.units: list[Unit] = []

    def section(self, name: str) -> None:
        self.current = f"{self.stage}/{name}"

    def keep_since(self, start: int) -> None:
        """Keep a short engineering condition and its supporting evidence together."""
        for index in range(start, len(self.units) - 1):
            self.units[index] = replace(self.units[index], keep_with_next=True)

    def add(self, value: Any, kind: str = "body", *, left: float = 117,
            **options: Any) -> None:
        self.units.append(Unit(f"{self.current}/{sum(unit.section == self.current for unit in self.units):03d}",
                               self.current, value, kind, left, **options))

    def title(self, value: str, *, left: float = 58.92) -> None:
        self.add(value, "heading", left=left)

    def text(self, value: str, *, left: float = 117) -> None:
        self.add(value, left=left)

    def formula(self, value: str, *, left: float = 117) -> None:
        parts = value.split(" = ", 2)
        # A second "=" is a result only after an arithmetic substitution;
        # "P = … kN、M = … kN m" lists two values and stays one right side.
        if len(parts) == 3 and _BINARY.search(parts[1]) is None:
            parts = [parts[0], f"{parts[1]} = {parts[2]}"]
        if len(parts) == 1:
            self.text(value, left=left)
        else:
            self.add(Equation(engineering_text(parts[0]), engineering_text(parts[1]),
                              result=engineering_text(parts[2]) if len(parts) == 3 else None),
                     "equation", left=left)

    def rows(self, values: Sequence[Sequence[Any]], weights: Sequence[float], *,
             header_rows: int = 0, row_height: float = 14.28,
             source_order: Sequence[int] = ()) -> None:
        self.add(tuple(tuple(str(value) if isinstance(value, (int, float)) else engineering_text(value) for value in row)
                       for row in values), "table", left=48, weights=tuple(weights),
                 header_rows=header_rows, row_height=row_height, source_order=tuple(source_order))

    def table(self, headers: Sequence[Any], rows: Sequence[Sequence[Any]], weights: Sequence[float],
              *, row_height: float = 14.28) -> None:
        self.rows((headers, *rows), weights, header_rows=1, row_height=row_height)


def semantic_sections(units: Sequence[Unit]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for unit in units:
        if not records or records[-1]["id"] != unit.section:
            records.append({"id": unit.section, "text": ""})
        value = unit.value
        if unit.source_order:
            leaves = atoms(value)
            if sorted(unit.source_order) != list(range(len(leaves))):
                raise ValueError(f"{unit.identifier}: source cell order must be a complete permutation")
            value = tuple(leaves[index] for index in unit.source_order)
        records[-1]["text"] += plain(value)
    return records


@dataclass(frozen=True)
class WrappedCell:
    text: str
    align: str = "left"
    style: TextStyle = BODY
    minimum: float = 14.28

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        lines = wrap_text(self.text, context.fonts, self.style, available_width - 2.16,
                          align=self.align, max_tracking_em=0)
        return CellLines(tuple(line.text for line in lines), style=self.style, line_advance=14.28,
                         min_height=self.minimum, inner_padding=Insets(1.08, 1.08, 1.08, 1.08),
                         align=self.align).measure(context, available_width)


def column_widths(weights: Sequence[float], width: float = 528) -> tuple[float, ...]:
    """Distribute an authored frame width on the explicit .12 pt page grid."""
    total = round(width / .12)
    boundaries = [round(total * sum(weights[:index]) / sum(weights)) for index in range(len(weights) + 1)]
    return tuple((right - left) * .12 for left, right in zip(boundaries, boundaries[1:]))


@dataclass(frozen=True)
class MinimumLeading:
    block: Block

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        measured = self.block.measure(context, available_width)
        minimum = context.rows_for(14.28)
        return replace(measured, parts=tuple(replace(part, rows=max(part.rows, minimum)) for part in measured.parts))


@dataclass(frozen=True)
class FlowKeep:
    block: Block
    prefer: bool = False
    following: bool = False

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        measured = self.block.measure(context, available_width)
        return replace(measured, prefer_keep=self.prefer or measured.prefer_keep,
                       keep_with_next=self.following or measured.keep_with_next)


_NUMBER = re.compile(r"[-+−]?\d[\d,.]*")
_BLANK = {"", "－", "—", "―", "-"}


def _grid_columns(rows: Sequence[Sequence[Any]]) -> list[list[int]]:
    """First grid column of each authored cell, skipping rowspan-occupied slots."""
    occupied: dict[tuple[int, int], bool] = {}
    placed = []
    for row_index, row in enumerate(rows):
        column, starts = 0, []
        for value in row:
            while occupied.get((row_index, column)):
                column += 1
            starts.append(column)
            colspan = value.colspan if isinstance(value, Merged) else 1
            rowspan = value.rowspan if isinstance(value, Merged) else 1
            for down in range(rowspan):
                for across in range(colspan):
                    occupied[(row_index + down, column + across)] = True
            column += colspan
        placed.append(starts)
    return placed


def _numeric_columns(unit: Unit) -> set[int]:
    """Columns whose every body value is a number or an empty placeholder.

    Alignment is a property of the column, so "－" or a short ID list never
    flips a single cell to the opposite edge of its neighbours.
    """
    seen: dict[int, bool] = {}
    for row, columns in list(zip(unit.value, _grid_columns(unit.value)))[unit.header_rows:]:
        for value, column in zip(row, columns):
            if isinstance(value, Merged):
                if value.colspan != 1:
                    continue
                value = value.value
            if not isinstance(value, str):
                seen[column] = False
            elif value not in _BLANK:
                seen[column] = seen.get(column, True) and _NUMBER.fullmatch(value) is not None
    return {column for column, numeric in seen.items() if numeric}


def blocks_for(units: Sequence[Unit]) -> tuple[Block, ...]:
    blocks: list[Block] = []
    for index, unit in enumerate(units):
        if unit.kind == "heading":
            if blocks:
                blocks.append(spacer())
            blocks.append(heading(plain(unit.value), left=unit.left, block_id=unit.identifier))
        elif unit.kind == "figure":
            assert unit.figure is not None
            geometry, frame, direction = unit.figure
            blocks.append(physical_frame(geometry, frame, direction, block_id=unit.identifier))
        elif unit.kind == "table":
            numeric = _numeric_columns(unit)
            rows = []
            for row_index, (row, columns) in enumerate(zip(unit.value, _grid_columns(unit.value), strict=True)):
                cells = []
                for value, column in zip(row, columns, strict=True):
                    colspan, rowspan = 1, 1
                    if isinstance(value, Merged):
                        colspan, rowspan, value = value.colspan, value.rowspan, value.value
                    if isinstance(value, str):
                        align = "left"
                        if row_index >= unit.header_rows and colspan == 1 and column in numeric:
                            # A right-aligned "－" would touch the next number
                            # and read as a minus sign; centre placeholders.
                            align = "center" if value in _BLANK else "right"
                        cells.append(Cell(WrappedCell(value, align, minimum=unit.row_height), padding=0,
                                          align=align, colspan=colspan, rowspan=rowspan))
                    elif isinstance(value, (Header, VerticalHeader)):
                        cells.append(Cell(value, colspan=colspan, rowspan=rowspan, padding=0))
                    else:
                        cells.append(math_cell(value, colspan=colspan, rowspan=rowspan))
                rows.append(cells)
            blocks.append(table(column_widths(unit.weights), rows, row_heights=None,
                                header_rows=unit.header_rows, block_id=unit.identifier))
        elif unit.kind == "equation":
            blocks.append(MinimumLeading(equation_group(unit.value, left=unit.left, first_equal=276.72,
                                         second_equal=436.44 if unit.value.result is not None else None,
                                         result_right=565.08 if unit.value.result is not None else None,
                                         block_id=unit.identifier)))
        elif unit.kind == "math":
            blocks.append(IndentTo(CellLines((unit.value,), style=BODY, min_height=14.28,
                                             block_id=unit.identifier), unit.left))
        else:
            blocks.append(paragraph(plain(unit.value), left=unit.left, block_id=unit.identifier))
        next_is_table = index + 1 < len(units) and units[index + 1].kind == "table"
        following = unit.keep_with_next or (next_is_table and (unit.kind != "table" or len(unit.value) == 1))
        if unit.kind == "table" or following:
            blocks[-1] = FlowKeep(blocks[-1], prefer=unit.kind == "table", following=following)
    return tuple(blocks)


def build_document(units: Sequence[Unit], *, header: str | None = None,
                   footer: str = "{page}") -> Document:
    return report(*blocks_for(units), header=header, footer=footer)
