"""Lay the 0600 manuscript out as native GridLayoutPdf blocks; pages break by content."""

from __future__ import annotations

from collections.abc import Sequence

from gridlayoutpdf import Block, Cell, CellLines, Document, KeepWithNext, PreferKeepTogether

from ...document import heading, indent_to, paragraph, report, spacer
from ...equations import equation_group
from ...styles import BODY
from ...tables import cell, math_cell, table
from .figures import OutlineFigure
from .manuscript import FOOTER, RESULT_EQUAL, RESULT_RIGHT, UNIT_START, WIDE_LABEL, CellSpec, TableSpec, Unit


def _cell(spec: CellSpec) -> Cell:
    if isinstance(spec.content, str):
        return cell(spec.content, colspan=spec.colspan, rowspan=spec.rowspan, align=spec.align)
    return math_cell(spec.content, colspan=spec.colspan, rowspan=spec.rowspan, align=spec.align)


def _table(spec: TableSpec, block_id: str) -> Block:
    heights = [spec.header_height or spec.row_height] * spec.header_rows
    heights += [spec.row_height] * (len(spec.rows) - spec.header_rows)
    rows = [[_cell(item) for item in row] for row in spec.rows]
    return PreferKeepTogether(table(spec.widths, rows, row_heights=heights, header_rows=spec.header_rows,
                                    numeric_columns=spec.numeric_columns, block_id=block_id))


def _block(unit: Unit) -> Block:
    if unit.kind == "heading":
        return heading(unit.value, left=unit.left, block_id=unit.identifier)
    if unit.kind == "paragraph":
        return paragraph(unit.value, left=unit.left, block_id=unit.identifier)
    if unit.kind == "equation":
        result = unit.value.result is not None
        return equation_group(unit.value, left=unit.left, first_equal=unit.first_equal,
                              second_equal=RESULT_EQUAL if result else None,
                              result_right=RESULT_RIGHT if result else None,
                              unit_start=UNIT_START if result and unit.value.unit is not None else None,
                              block_id=unit.identifier, label_width=WIDE_LABEL if unit.value.label else None)
    if unit.kind == "table":
        return indent_to(_table(unit.value, unit.identifier), unit.left)
    if unit.kind == "figure":
        return indent_to(OutlineFigure(unit.value.data, unit.identifier), unit.left)
    return indent_to(CellLines((unit.value,), style=BODY, min_height=14.28, block_id=unit.identifier), unit.left)


def blocks(units: Sequence[Unit]) -> list[Block]:
    """Blocks in manuscript order: a heading and a group's units stay with what follows them."""
    out: list[Block] = []
    spaced = True  # no blank line at the start or twice in a row
    for index, unit in enumerate(units):
        following = units[index + 1] if index + 1 < len(units) else None
        if not spaced and (unit.kind in ("heading", "table", "figure") or unit.gap_before):
            out.append(spacer())
        block = _block(unit)
        keep = following is not None and (unit.kind == "heading" or unit.keep
                                          or bool(unit.group) and following.group == unit.group)
        out.append(KeepWithNext(block) if keep else block)
        spaced = unit.kind in ("table", "figure")
        if spaced:
            out.append(spacer())
    return out


def document(units: Sequence[Unit]) -> Document:
    return report(*blocks(units), footer=FOOTER)
