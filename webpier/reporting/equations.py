"""Structured formula helpers with paper-coordinate equal/result anchors."""

from __future__ import annotations

from dataclasses import dataclass, replace

from gridlayoutpdf import (
    Block, Equation, EquationAnchors, EquationGroup, LayoutContext, Leading, MathNode,
    MeasuredBlock, Operator, Row, Script, TermStop, measure_block,
)

from .document import indent_to
from .styles import BODY, BODY_LEADING, finite, grid_units

# Between a number and an operator the reference keeps 9.2-9.4 pt on 0500 p1 ("5.1 × 0.5 × 68600")
# and 5.8-8.7 pt in the narrow derivation columns of 0600 p16. One gap serves every report:
# 7.44 pt keeps "T = 1.0 × LR = 1.0 × 200.00" on its result's line between 0600's first equal
# (276.72) and result equal (436.44).
TERM_GAP = 7.44
# The gap of a terms() Row: one half-width space of the 9.9 pt body. Laid out in term columns each
# column holds one term, so it changes nothing there; a row too long for its columns falls back to
# ordinary wrapping, and then it separates the terms and operators as in "(1 + 0.222)".
TERM_SPACE = 4.95
_OPERATORS = frozenset(("+", "−", "-", "×", "/", "="))


def script(base: str | MathNode, *, superscript: str | MathNode | None = None,
           subscript: str | MathNode | None = None) -> Script:
    return Script(base, superscript=superscript, subscript=subscript, scale=6.5 / 9.9,
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
    never broken inside. Column spacing belongs to TermStop and TERM_GAP; the
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
class _PaperEquations:
    equations: tuple[Equation, ...]
    left: float
    first_equal: float
    second_equal: float | None
    result_right: float | None
    unit_start: float | None
    block_id: str
    gap: float = 4.08
    # Per equation: kept on the page of the next one (no page break after it). None: the block
    # breaks between any two display lines, as one prefer-keep equation block.
    keep: tuple[bool, ...] | None = None

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        pitch = context.profile.grid.pitch_x

        def relative(value: float | None) -> int | None:
            return None if value is None else grid_units(value - self.left, pitch)

        def anchors(equation: Equation) -> EquationAnchors:
            style = equation.style or BODY

            def relation_center(value: float | None, relation: str) -> int | None:
                if value is None:
                    return None
                # EquationAnchors uses relation centers; the application API
                # accepts native PDF text origins (left edges) from the reference.
                center = finite(value - self.left, "relation offset") + context.fonts.measure(relation, style).width / 2
                # Nearest fine-grid center introduces at most half a pitch.
                return round(center / pitch)

            first = relation_center(self.first_equal, equation.relation)
            assert first is not None
            return EquationAnchors(first, relation_center(self.second_equal, equation.result_relation),
                                   relative(self.result_right), relative(self.unit_start))

        def group(key: tuple, indices: list[int]) -> MeasuredBlock:
            return measure_block(EquationGroup(*(self.equations[index] for index in indices),
                                               anchors=key[0], style=BODY, gap=self.gap, term_gap=TERM_GAP,
                                               block_id=self.block_id), context, available_width)

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
        # equation joins the group only when no equation of it takes more lines than
        # alone: a wide term of another row (a symbolic min/max) must not spread a
        # short row nor push its result to a line of its own.
        runs: list[tuple[tuple, list[int], MeasuredBlock]] = []
        alone: dict[int, int] = {}
        for index, equation in enumerate(self.equations):
            key = (anchors(equation), equation.style or BODY, equation.relation, equation.result_relation,
                   _term_shape(equation.rhs))
            measured = group(key, [index])
            alone[index] = len(measured.parts)
            if runs and runs[-1][0] == key:
                trial = [*runs[-1][1], index]
                joined = group(key, trial)
                if all(count <= alone[member] for member, count in zip(trial, lines(joined, len(trial)))):
                    runs[-1] = (key, trial, joined)
                    continue
            runs.append((key, [index], measured))
        parts = []
        for _, indices, measured in runs:
            for part in measured.parts:
                index = indices[part.metadata["equation_index"]]
                parts.append(replace(part, metadata={
                    **part.metadata, "equation_index": index,
                    "equation_block_id": self.equations[index].block_id or self.block_id}))
        if self.keep is None or len(self.equations) == 1:
            return MeasuredBlock(available_width, context.profile.grid.pitch_y, tuple(parts),
                                 prefer_keep=True, block_id=self.block_id)
        # A page breaks only between two equations, never inside one (each was one prefer-keep
        # block) nor after an equation kept with the next.
        cuts = tuple(position for position in range(1, len(parts))
                     if parts[position].metadata["equation_index"] != parts[position - 1].metadata["equation_index"]
                     and not self.keep[parts[position - 1].metadata["equation_index"]])
        return MeasuredBlock(available_width, context.profile.grid.pitch_y, tuple(parts), break_after=cuts,
                             prefer_keep=not cuts, block_id=self.block_id)


def equation_group(*equations: Equation, left: float = 117, first_equal: float = 169.92,
                   second_equal: float | None = None, result_right: float | None = None,
                   unit_start: float | None = None, block_id: str = "",
                   keep: tuple[bool, ...] | None = None) -> Block:
    """Use paper text-origin x values for relations, and right edges for results.

    Consecutive equations of one call share their term columns across lines. With
    *keep* (one flag per equation: kept with the next) the page breaks only between
    two equations not kept together; each equation's parts carry its block_id as
    "equation_block_id".

    Relation centers are rounded to the nearest 0.12 pt grid column at measure
    time, so their native text origins differ by at most 0.06 pt from the target.
    Each equation resolves its own relation font/width; no text is resized.
    Every display line advances exactly the body's 14.28 pt row (a taller line raises
    LayoutOverflowError); a 6.5 pt subscript's 0.07 pt reach below it stays within the
    0.12 pt overhang.
    """
    if keep is not None and len(keep) != len(equations):
        raise ValueError("equation_group: keep needs one flag per equation")
    return indent_to(Leading(_PaperEquations(equations, left, first_equal, second_equal,
                                             result_right, unit_start, block_id,
                                             keep=None if keep is None else tuple(keep)),
                             grid_units(BODY_LEADING), minimum=False, overhang=0.12), left)


@dataclass(frozen=True)
class Definition:
    """One symbol of a "ここに、" list; a value prints as "(= value unit)"."""

    symbol: str | MathNode
    text: str | MathNode
    value: str | MathNode | None = None
    unit: str | MathNode | None = None


def definitions(*items: Definition, left: float, colon: float, value_equal: float | None = None,
                value_right: float | None = None, unit_start: float | None = None,
                label: str = "ここに、", block_id: str = "") -> Block:
    """A "ここに、" list: symbols right-aligned against one "：" column, then the text.

    Reference 0500 p1/p2: "ここに、" opens the first line only; each symbol ends
    one half-width space before the "：" at *colon* (a text origin, like the
    relations of equation_group) and the text follows the colon directly. A
    value takes "(=" at *value_equal*, ends at *value_right* and is closed by
    its unit and ")" from *unit_start*.

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
    return indent_to(Leading(_PaperEquations(tuple(equations), left, colon, value_equal, value_right,
                                             unit_start, block_id, gap=0),
                             grid_units(BODY_LEADING), minimum=False, overhang=0.12), left)
