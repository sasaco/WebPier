"""Lay the 0600 manuscript out as native GridLayoutPdf blocks; pages break by content."""

from __future__ import annotations

from collections.abc import Sequence

from gridlayoutpdf import Block, Cell, Document, KeepWithNext, Leading, MathBlock, PreferKeepTogether, SideRule

from ...document import blank, columns, heading, indent_to, math_line, paragraph, report, spacer
from ...equations import definitions, equation_group
from ...styles import BODY, BODY_LEADING, grid_units, report_profile
from ...tables import REACTION_CELL_PADDING, cell, math_cell, table
from .figures import LoadingFigure, OutlineFigure
from .manuscript import (
    FRAME_RIGHT, RESULT_EQUAL, RESULT_RIGHT, RULE_BOTTOM, RULE_TOP, RULE_WIDTH, RULE_X, UNIT_START, CellSpec,
    Pair, TableSpec, Unit,
)

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


def _pair(pair: Pair, left: float, second: float, block_id: str) -> Block:
    """Two texts on the 14.28 pt row, the second from its own column (0600 p16 "・0.8 LR  [… の組合せ]")."""
    row = Leading(columns(MathBlock(pair.first, style=BODY), MathBlock(pair.second, style=BODY),
                          widths=(second - left, FRAME_RIGHT - second), gap=0, block_id=block_id),
                  grid_units(BODY_LEADING), overhang=0.12)
    return indent_to(row, left)


def _anchors(unit: Unit) -> tuple[float, float | None, bool, bool]:
    """The columns of an equation: its left edge, its "=" and whether it has a result and a unit."""
    result = unit.value.result is not None
    return unit.left, unit.first_equal, result, result and unit.value.unit is not None


def _joins(unit: Unit, following: Unit) -> bool:
    """*following* continues the equations of *unit*: same columns, group and rule, no blank line between."""
    return (unit.kind == following.kind == "equation" and not following.gap_before
            and following.group == unit.group and following.ruled == unit.ruled
            and _anchors(unit) == _anchors(following))


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
    if unit.kind == "pair":
        assert unit.first_equal is not None
        return _pair(unit.value, unit.left, unit.first_equal, unit.identifier)
    if unit.kind == "definitions":
        return definitions(*unit.value, left=unit.left, colon=unit.first_equal, block_id=unit.identifier)
    if unit.kind == "table":
        return indent_to(_table(unit.value, unit.identifier), unit.left)
    if unit.kind == "figure":
        return indent_to(FIGURES[unit.value.kind](unit.value.data, unit.identifier), unit.left)
    return math_line(unit.value, left=unit.left, block_id=unit.identifier)


def _ruled(out: list[Block], ruled: list[bool]) -> list[Block]:
    """Each run of ruled blocks gets the rule at RULE_X, starting RULE_TOP into its first block and
    ending RULE_BOTTOM before the end of its last one (0600 p16)."""
    x = RULE_X - report_profile().grid.origin_x
    result = []
    for index, block in enumerate(out):
        if not ruled[index]:
            result.append(block)
            continue
        first = index == 0 or not ruled[index - 1]
        last = index + 1 == len(out) or not ruled[index + 1]
        result.append(SideRule(block, x, width=RULE_WIDTH, top=RULE_TOP if first else 0.0,
                               bottom=RULE_BOTTOM if last else 0.0))
    return result


def blocks(units: Sequence[Unit]) -> list[Block]:
    """Blocks in manuscript order: a heading and a group's units stay with what follows them.

    A heading, table or figure has one blank line before and after it; blank lines never stack.
    A ruled unit and the blank lines next to it are bracketed by the rule.
    """
    def kept(index: int) -> bool:
        unit, following = units[index], units[index + 1] if index + 1 < len(units) else None
        return following is not None and (unit.kind == "heading" or unit.keep
                                          or bool(unit.group) and following.group == unit.group)

    out: list[Block] = []
    ruled: list[bool] = []
    index = 0
    while index < len(units):
        unit = units[index]
        if unit.kind in ("heading", "table", "figure") or unit.gap_before:
            before = len(out)
            blank(out)
            if len(out) > before and (unit.ruled or index > 0 and units[index - 1].ruled):
                # The rule makes the blank line visible: it continues the chain of a kept group.
                out[-1] = KeepWithNext(out[-1]) if kept(index - 1) else out[-1]
                ruled.append(True)
            else:
                ruled.extend([False] * (len(out) - before))
        end = index + 1
        if unit.kind == "equation":
            while end < len(units) and _joins(units[end - 1], units[end]):
                end += 1
            block = _equations(units[index:end], tuple(kept(position) for position in range(index, end)))
        else:
            block = _block(unit)
        out.append(KeepWithNext(block) if kept(end - 1) else block)
        ruled.append(unit.ruled)
        index = end
        if unit.kind == "heading":
            out.append(KeepWithNext(spacer()))
            ruled.append(False)
        elif unit.kind in ("table", "figure"):
            out.append(spacer())
            ruled.append(False)
    return _ruled(out, ruled)


def document(units: Sequence[Unit]) -> Document:
    return report(*blocks(units))
