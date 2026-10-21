"""Structured formula helpers with equal/result anchors in grid columns and grid term columns (GridLayoutPdf FR-025)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from gridlayoutpdf import (
    Block, Equation, EquationAnchors, EquationGroup, LayoutContext, LayoutOverflowError, Leading, MathNode,
    MeasuredBlock, Operator, Row, Script, Spacer, Stack, TermStop, measure_block,
)

from .document import indent_to
from .styles import BODY, count

# The gap of a terms() Row: one half-width space of the 10 pt body. Laid out in grid term columns each
# term takes whole grid columns of its own, so it changes nothing there; a row too long for its columns
# falls back to ordinary wrapping, and then it separates the terms and operators as in "(1 + 0.222)".
TERM_SPACE = 5.0
_OPERATORS = frozenset(("+", "−", "-", "×", "/", "="))


def script(base: str | MathNode, *, superscript: str | MathNode | None = None,
           subscript: str | MathNode | None = None) -> Script:
    return Script(base, superscript=superscript, subscript=subscript, scale=6.5 / BODY.size,
                  superscript_rise=4.92 if superscript is not None else None,
                  subscript_drop=1.92 if subscript is not None else None)


def _operator(part: object) -> Operator | None:
    if isinstance(part, Operator):
        return part
    if isinstance(part, str) and part in _OPERATORS:
        return Operator(part)
    return None


def terms(*parts: str | MathNode) -> Row:
    """An equation RHS in term columns: numbers right-aligned, operators centered.

    "(" ... ")" (nested allowed) form one term printed as "(1 + 0.222)"; it is
    never broken inside. Each term takes whole grid columns (term_columns="grid"); the
    Row gap (TERM_SPACE) only spaces a row that falls back to ordinary wrapping.
    """
    items: list[MathNode] = []
    groups: list[list[MathNode | str]] = []
    for part in parts:
        if isinstance(part, str) and part == "(":
            groups.append([])
            continue
        if isinstance(part, str) and part == ")":
            if not groups:
                raise ValueError("terms: unmatched ')'")
            node: MathNode | str = Row("(", *groups.pop(), ")", gap=0)
        else:
            node = part
        operator = _operator(node)
        if groups:
            groups[-1].extend((" ", operator, " ") if operator is not None else (node,))
        elif operator is not None:
            items.extend((TermStop("center"), operator))
        else:
            items.extend((TermStop("right"), node))
    if groups:
        raise ValueError("terms: unmatched '('")
    return Row(*items, gap=TERM_SPACE)


def over(numerator: str | MathNode, denominator: str | MathNode) -> Row:
    """An inline fraction a/b; a multi-item Row operand is parenthesized. No stacked Fraction."""
    def operand(node: str | MathNode) -> str | MathNode:
        if isinstance(node, Row) and len(node.items) > 1:
            return Row("(", node, ")", gap=0)
        return node
    return Row(operand(numerator), "/", operand(denominator), gap=0)


def _term_shape(rhs: object) -> tuple[str, ...] | None:
    """The aligns of an RHS's term columns in order (GridLayoutPdf opens a leading "left"
    column unless the Row starts with a TermStop); None for an RHS without TermStop."""
    if not isinstance(rhs, Row) or not any(isinstance(item, TermStop) for item in rhs.items):
        return None
    leading = rhs.items[0].align if isinstance(rhs.items[0], TermStop) else "left"
    return (leading, *(item.align for item in rhs.items[1:] if isinstance(item, TermStop)))


@dataclass(frozen=True)
class _GridEquations:
    """Equations whose anchors are grid columns from the block's left edge (relation centres on column
    boundaries, as EquationAnchors), one grid row per display line."""

    equations: tuple[Equation, ...]
    anchors: EquationAnchors
    block_id: str
    gap: float = 4.0
    label_columns: int | None = None
    # Per equation: kept on the page of the next one. None: the block moves to a new page whole when it fits one.
    keep: tuple[bool, ...] | None = None

    def _group(self, indices: list[int]) -> EquationGroup:
        return EquationGroup(*(self.equations[index] for index in indices), anchors=self.anchors, style=BODY,
                             gap=self.gap, term_columns="grid", label_columns=self.label_columns,
                             block_id=f"{self.block_id}-run{indices[0]}")

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        def lines(measured: MeasuredBlock, count: int) -> list[int]:
            found = [0] * count
            for part in measured.parts:
                found[part.metadata["equation_index"]] += 1
            return found

        # Consecutive equations with the same relations, style and term-column shape
        # share one EquationGroup (and so its term columns), labeled or not: a label
        # stands at the block's left edge in a column GridLayoutPdf shares across the
        # group, and each lhs stays right-aligned against its relation. Rows of
        # another shape (column count or align order) never share columns: a short
        # "200.00 / 2" must not be spread over the columns of a longer row. An
        # equation joins the group only when its terms still fit their grid columns and
        # no equation of it takes more lines than alone: a wide term of another row (a
        # symbolic min/max) must not spread a short row nor push its result to a line of
        # its own.
        runs: list[tuple[tuple, list[int], MeasuredBlock]] = []
        alone: dict[int, int] = {}
        for index, equation in enumerate(self.equations):
            key = (equation.style or BODY, equation.relation, equation.result_relation, _term_shape(equation.rhs))
            measured = measure_block(self._group([index]), context, available_width)
            alone[index] = len(measured.parts)
            if runs and runs[-1][0] == key:
                trial = [*runs[-1][1], index]
                joined = measure_block(self._group(trial), context, available_width)
                fits = not any(part.metadata.get("term_fallback") for part in joined.parts)
                if fits and all(count <= alone[member] for member, count in zip(trial, lines(joined, len(trial)))):
                    runs[-1] = (key, trial, joined)
                    continue
            runs.append((key, [index], measured))
        for _, _, measured in runs:
            if any(part.metadata.get("term_fallback") for part in measured.parts):
                raise LayoutOverflowError(f"{self.block_id}: the terms of an equation do not fit its grid columns "
                                          "(term_fallback); move the anchors or split the equation",
                                          block_id=self.block_id)
        # Each run is a child of its own Stack, numbered by the empty children before it: the grid Excel tells the
        # lines of two groups apart by the path of their commands (the Stack child), not by the group's id. Each run
        # is a part of its own, so that a page breaks only between two runs, after one whose last equation is not
        # kept with the next; every part lists the children of all runs, as the one part of a Stack would, since the
        # grid Excel follows a Stack child through the first part of the placement that has children.
        parts = []
        for number, (_, indices, _) in enumerate(runs):
            stack = Stack(*(Spacer(0),) * number, Leading(self._group(indices), 1), block_id=self.block_id)
            parts += measure_block(stack, context, available_width).parts
        children = tuple(part.metadata["children"][number] for number, part in enumerate(parts))
        parts = [replace(part, metadata={**part.metadata, "children": children}) for part in parts]
        if self.keep is None:
            return MeasuredBlock(available_width, context.profile.grid.pitch_y, tuple(parts), prefer_keep=True,
                                 block_id=self.block_id)
        cuts = tuple(position + 1 for position, (_, indices, _) in enumerate(runs[:-1]) if not self.keep[indices[-1]])
        return MeasuredBlock(available_width, context.profile.grid.pitch_y, tuple(parts), break_after=cuts,
                             prefer_keep=not cuts, block_id=self.block_id)


def _anchors(left: int, first_equal: int, second_equal: int | None, result_right: int | None,
             unit_start: int | None) -> EquationAnchors:
    """EquationAnchors from body columns: the relations' centres on the boundaries before the columns
    *first_equal* and *second_equal*, the result ending at *result_right* and the unit from *unit_start*."""
    def relative(value: int | None, name: str) -> int | None:
        return None if value is None else count(value, name) - count(left, "left")
    return EquationAnchors(relative(first_equal, "first_equal"), relative(second_equal, "second_equal"),
                           relative(result_right, "result_right"), relative(unit_start, "unit_start"))


def equation_group(*equations: Equation, left: int = 4, first_equal: int = 7,
                   second_equal: int | None = None, result_right: int | None = None,
                   unit_start: int | None = None, label_columns: int | None = None, block_id: str = "",
                   keep: Sequence[bool] | None = None) -> Block:
    """Equations from the body column *left*, their anchors body columns (see ``_anchors``).

    Consecutive equations of one call share their grid term columns across lines when
    they have the same shape. Every display line takes exactly one grid row (a taller
    line raises LayoutOverflowError), and an equation whose terms do not fit their grid
    columns raises LayoutOverflowError instead of falling back to packed terms. An
    equation's ``label`` stands in *label_columns* columns at the block's left edge
    (None: its measured width). With *keep* (one flag per equation: kept with the next)
    the page may break between two runs of equations after one not kept with the next.
    """
    if keep is not None and len(keep) != len(equations):
        raise ValueError("equation_group: keep needs one flag per equation")
    return indent_to(_GridEquations(equations, _anchors(left, first_equal, second_equal, result_right, unit_start),
                                    block_id, label_columns=label_columns,
                                    keep=None if keep is None else tuple(keep)), left)


@dataclass(frozen=True)
class Definition:
    """One symbol of a "ここに、" list; a value prints as "(= value unit)"."""

    symbol: str | MathNode
    text: str | MathNode
    value: str | MathNode | None = None
    unit: str | MathNode | None = None


def definitions(*items: Definition, left: int, colon: int, value_equal: int | None = None,
                value_right: int | None = None, unit_start: int | None = None,
                label: str = "ここに、", block_id: str = "") -> Block:
    """A "ここに、" list: symbols right-aligned against one "：" column, then the text.

    Reference 0500 p1/p2: "ここに、" opens the first line only; each symbol ends
    one half-width space before the "：" centred on the boundary before the body
    column *colon* (like the relations of equation_group) and the text follows the
    colon directly. A value takes "(=" at *value_equal*, ends at *value_right* and is
    closed by its unit and ")" from *unit_start* (body columns).

    The label leads the first symbol directly ("ここに、k" is one run in the
    reference) instead of taking an EquationGroup label column: such a column
    would be reserved on every line, yet the reference's wider "ρgk" starts
    left of where "ここに、" ends. All lines share one EquationGroup; *left*
    is only the block's left edge, and a label and symbol reaching past it
    raise LayoutOverflowError.
    """
    if not items or any(not isinstance(item, Definition) for item in items):
        raise ValueError("definitions requires Definition items")
    equations = []
    for index, item in enumerate(items):
        if item.value is None and item.unit is not None:
            raise ValueError("a definition unit requires a value")
        unit = None if item.value is None else (
            ")" if item.unit is None else Row(item.unit, ")", gap=0))
        lead = (label,) if index == 0 and label else ()
        equations.append(Equation(Row(*lead, item.symbol, " ", gap=0), item.text, relation="：",
                                  result=item.value, result_relation="(=", unit=unit))
    return indent_to(_GridEquations(tuple(equations), _anchors(left, colon, value_equal, value_right,
                                                                unit_start), block_id, gap=0), left)
