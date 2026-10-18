"""Lay the 0600 manuscript out as native GridLayoutPdf blocks; pages break by content."""

from __future__ import annotations

from collections.abc import Sequence

from gridlayoutpdf import Block, Cell, Document, KeepWithNext, PreferKeepTogether

from ...document import blank, heading, indent_to, math_line, paragraph, report, spacer
from ...equations import definitions, equation_group
from ...tables import REACTION_CELL_PADDING, cell, math_cell, table
from .figures import LoadingFigure, OutlineFigure
from .manuscript import RESULT_EQUAL, RESULT_RIGHT, UNIT_START, CellSpec, TableSpec, Unit

FIGURES = {"outline": OutlineFigure, "loading": LoadingFigure}


def _cell(spec: CellSpec) -> Cell:
    """0600 tables use the clearance measured in the reference 0600 tables."""
    if isinstance(spec.content, str):
        return cell(spec.content, colspan=spec.colspan, rowspan=spec.rowspan, align=spec.align,
                    padding=REACTION_CELL_PADDING)
    return math_cell(spec.content, colspan=spec.colspan, rowspan=spec.rowspan, align=spec.align,
                     padding=REACTION_CELL_PADDING)


def _table(spec: TableSpec, block_id: str) -> Block:
    heights = [spec.header_height or spec.row_height] * spec.header_rows
    heights += [spec.row_height] * (len(spec.rows) - spec.header_rows)
    rows = [[_cell(item) for item in row] for row in spec.rows]
    return PreferKeepTogether(table(spec.widths, rows, row_heights=heights, header_rows=spec.header_rows,
                                    numeric_columns=spec.numeric_columns, block_id=block_id))


def _anchors(unit: Unit) -> tuple[float, float | None, bool, bool]:
    """The columns of an equation: its left edge, its "=" and whether it has a result and a unit."""
    result = unit.value.result is not None
    return unit.left, unit.first_equal, result, result and unit.value.unit is not None


def _joins(unit: Unit, following: Unit) -> bool:
    """*following* continues the equations of *unit*: same columns and group, no blank line between."""
    return (unit.kind == following.kind == "equation" and not following.gap_before
            and following.group == unit.group and _anchors(unit) == _anchors(following))


def _equations(run: Sequence[Unit], keep: tuple[bool, ...]) -> Block:
    """Consecutive equations in one group, so that their term columns line up across the lines (0600 p16)."""
    left, first_equal, result, has_unit = _anchors(run[0])
    return equation_group(*(unit.value for unit in run), left=left, first_equal=first_equal,
                          second_equal=RESULT_EQUAL if result else None,
                          result_right=RESULT_RIGHT if result else None,
                          unit_start=UNIT_START if has_unit else None,
                          block_id=run[0].identifier, keep=keep)


def _block(unit: Unit) -> Block:
    if unit.kind == "heading":
        return heading(unit.value, left=unit.left, block_id=unit.identifier)
    if unit.kind == "paragraph":
        return paragraph(unit.value, left=unit.left, block_id=unit.identifier)
    if unit.kind == "definitions":
        return definitions(*unit.value, left=unit.left, colon=unit.first_equal, block_id=unit.identifier)
    if unit.kind == "table":
        return indent_to(_table(unit.value, unit.identifier), unit.left)
    if unit.kind == "figure":
        return indent_to(FIGURES[unit.value.kind](unit.value.data, unit.identifier), unit.left)
    return math_line(unit.value, left=unit.left, block_id=unit.identifier)


def blocks(units: Sequence[Unit]) -> list[Block]:
    """Blocks in manuscript order: a heading and a group's units stay with what follows them.

    A heading, table or figure has one blank line before and after it; blank lines never stack.
    """
    def kept(index: int) -> bool:
        unit, following = units[index], units[index + 1] if index + 1 < len(units) else None
        return following is not None and (unit.kind == "heading" or unit.keep
                                          or bool(unit.group) and following.group == unit.group)

    out: list[Block] = []
    index = 0
    while index < len(units):
        unit = units[index]
        if unit.kind in ("heading", "table", "figure") or unit.gap_before:
            blank(out)
        end = index + 1
        if unit.kind == "equation":
            while end < len(units) and _joins(units[end - 1], units[end]):
                end += 1
            block = _equations(units[index:end], tuple(kept(position) for position in range(index, end)))
        else:
            block = _block(unit)
        out.append(KeepWithNext(block) if kept(end - 1) else block)
        index = end
        if unit.kind == "heading":
            out.append(KeepWithNext(spacer()))
        elif unit.kind in ("table", "figure"):
            out.append(spacer())
    return out


def document(units: Sequence[Unit]) -> Document:
    return report(*blocks(units))
