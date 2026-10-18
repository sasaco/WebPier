"""The 0600 manuscript: ordered semantic units shared by the layout and the tests.

A unit is what one printed block says (a heading, a sentence, a formula, a
table, a figure) and where it goes. Numbers are Printed values of the
ReactionResult or of the input it echoes, written by reporting.numbers at their
digits; constants of a formula are written as the calculator holds them.
Nothing is calculated here.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any

from gridlayoutpdf import BreakHint, Equation, Literal, MathNode, Operator, Row, Script, TermStop

from ....core.printed import Printed
from ...equations import Definition, over, script, terms
from ...numbers import constant, decimal_constant, printed, unit

PREFIX = "0600/"

# Heading levels and their measured x (reporting-style.md, 0600 p1/p16).
CHAPTER, SECTION, SUBSECTION, ITEM, DETAIL = 58.92, 73.44, 87.96, 102.48, 117.0
BODY = 117.0
INDENTED = 131.52
# Formula columns: short symbols at the body, and the measured multi-step derivation of 0600 p26.
SHORT_LHS, SHORT_EQUAL = 131.52, 160.56
MEDIUM_EQUAL = 204.12  # a labelled symbol such as RB(D1) or iF(複線)
WIDE_LHS, WIDE_EQUAL = 175.08, 276.72
RESULT_EQUAL, RESULT_RIGHT, UNIT_START = 436.44, 516.48, 523.68
DEFINITION_COLON = MEDIUM_EQUAL  # "ここに、" from the indented body, symbols ending before this colon
# A bearing derivation of 6.4.1 (2), measured on 0600 p16: "・case" with its combination from 218.64,
# "※ T1 =" and "※ ∴ H =", and "Rm =" right after its symbol. The movable bearing's candidates use the
# derivation column (WIDE_EQUAL); the fixed bearing's take "=" five indents after their symbols, so that
# "T − 1/2μ・Rm = a − 1/2 × μ × Rm = H" keeps its result on its line (07 7-5; p16 wraps it).
PAIR_SECOND = 218.64
MARK_EQUAL, CONCLUSION_EQUAL, VERTICAL_EQUAL, FIXED_EQUAL = 160.56, 175.08, 189.6, WIDE_LHS + 5 * 14.52
# The rule bracketing "※ T1 … ※ ∴ H" (0600 p16): x, width, and how far it starts below the
# bottom of the "※ T1" row and ends above the top of the "※ ∴ H" row.
RULE_X, RULE_WIDTH, RULE_TOP, RULE_BOTTOM = 136.2, 0.72, 5.76, 1.8
FRAME_RIGHT = 576.0

_OPERATORS = {"+", "−", "×", "/", "=", "-"}
_PARENTHESES = {"(", ")"}


def sub(base: str | MathNode, suffix: str) -> Script:
    return script(base, subscript=suffix)


def sup(base: str | MathNode, exponent: str) -> Script:
    return script(base, superscript=exponent)


def operand(value: Any, *, first: bool = False) -> MathNode | str:
    """One operand as written; a negative printed value after an operator is parenthesized."""
    if isinstance(value, Printed):
        text = printed(value)
        return Row("(", text, ")", gap=0) if value.value < 0 and not first else text
    if isinstance(value, Decimal):
        return decimal_constant(value)
    if isinstance(value, bool):
        raise TypeError("bool は式の項になりません")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return constant(value)
    if isinstance(value, str) and value in _OPERATORS:
        return Operator(value)
    return value


def _aligned(node: Any) -> bool:
    """A Row written by terms(): its items are term columns."""
    return isinstance(node, Row) and any(isinstance(item, TermStop) for item in node.items)


def _parts(node: Row) -> tuple[Any, ...]:
    """The terms and operators of a term-column Row, to be written again inside another expression."""
    return tuple(item for item in node.items if not isinstance(item, (TermStop, BreakHint)))


def _columns(*items: Any) -> Row:
    """terms(), with a leading minus (first, or after another operator) kept on its term: "−(1.0 + z)"."""
    row = terms(*items)
    pairs = list(zip(row.items[::2], row.items[1::2]))
    out: list[Any] = []
    index = 0
    while index < len(pairs):
        stop, node = pairs[index]
        unary = (isinstance(node, Operator) and node.text in ("−", "-") and index + 1 < len(pairs)
                 and not isinstance(pairs[index + 1][1], Operator)
                 and (not out or isinstance(out[-1], Operator)))
        if unary:
            stop, node = TermStop("right"), Row(node.text, pairs[index + 1][1], gap=0)
            index += 1
        out.extend((stop, node))
        index += 1
    return Row(*out, gap=row.gap)


def _opened(items: list[Any]) -> list[Any]:
    """Top-level parentheses kept on their first and last terms, so that a long group wraps inside."""
    out: list[Any] = []
    index = 0
    while index < len(items):
        if items[index] != "(":
            out.append(items[index])
            index += 1
            continue
        depth, end = 0, index
        for end in range(index, len(items)):  # pragma: no branch - terms() rejects an unmatched "("
            depth += (items[end] == "(") - (items[end] == ")")
            if depth == 0:
                break
        inner = list(_parts(terms(*items[index + 1:end])))
        inner[0] = Row("(", inner[0], gap=0)
        inner[-1] = Row(inner[-1], ")", gap=0)
        out.extend(inner)
        index = end + 1
    return out


def expr(*parts: Any, open_groups: bool = False) -> Row:
    """An equation RHS in term columns (terms); printed values are written at their digits.

    A parenthesized group is one term that never wraps inside; with *open_groups* the top-level groups
    keep their parentheses on their first and last terms, so that a group too long for a line wraps.
    """
    items: list[Any] = []
    for index, part in enumerate(parts):
        previous = parts[index - 1] if index else None
        first = index == 0 or (isinstance(previous, str) and previous in ("(", "="))
        node = operand(part, first=first)
        items.extend(_parts(node) if _aligned(node) else (node,))
    return _columns(*(_opened(items) if open_groups else items))


def inline(node: Any) -> Any:
    """A term-column Row written as one run, as an argument of min/max or a side of a ratio."""
    if not _aligned(node):
        return node
    items: list[Any] = []
    for item in _parts(node):
        items.extend((" ", item, " ") if isinstance(item, Operator) else (item,))
    return Row(*items, gap=0)


def call(name: str, *arguments: Any) -> Row:
    """min(a, b) / max(a, b); the comma is followed by a space so two numbers never read as one."""
    items: list[Any] = [name + "("]
    for index, argument in enumerate(arguments):
        if index:
            items.append(", ")
        items.append(inline(argument) if isinstance(argument, Row) else operand(argument, first=True))
    items.append(")")
    return Row(*items, gap=0)


def ratio(numerator: Any, denominator: Any) -> Row:
    """a/b on the line (over); an expression is parenthesized. No stacked fraction."""
    def side(value: Any) -> Any:
        return inline(value) if isinstance(value, Row) else operand(value, first=True)
    return over(side(numerator), side(denominator))


def symbols(*parts: Any) -> Row:
    """A symbolic expression such as A × d in term columns; juxtaposed symbols (b0 w0) form one term."""
    items: list[Any] = []
    run: list[Any] = []

    def close() -> None:
        if run:
            items.append(run[0] if len(run) == 1 else Row(*run))
            run.clear()

    for part in parts:
        if isinstance(part, Operator) or isinstance(part, str) and (part in _OPERATORS or part in _PARENTHESES):
            close()
            items.append(part)
        else:
            run.append(part)
    close()
    return _columns(*items)


def derivation(symbolic: Any, numeric: Row) -> Row:
    """symbols = numbers as one row of term columns; a long row wraps before the numbers' "="."""
    head = symbolic if _aligned(symbolic) else _columns(symbolic)
    return Row(*head.items, BreakHint("preferred"), *numeric.items, gap=numeric.gap)


def unit_of(value: Printed) -> str | MathNode | None:
    return unit(value.unit) if value.unit else None


@dataclass(frozen=True)
class CellSpec:
    """One authored table cell: text or a math node, and its span."""

    content: str | MathNode
    colspan: int = 1
    rowspan: int = 1
    align: str | None = None


@dataclass(frozen=True)
class TableSpec:
    widths: tuple[float, ...]
    rows: tuple[tuple[CellSpec, ...], ...]
    header_rows: int
    row_height: float = 14.88
    header_height: float | None = None
    numeric_columns: tuple[int, ...] = ()


@dataclass(frozen=True)
class FigureSpec:
    """A figure kind and the printed labels it draws (the semantic record of the figure)."""

    kind: str
    labels: tuple[str, ...]
    data: Any = None


@dataclass(frozen=True)
class Pair:
    """Two texts on one line, the second from a column of its own ("・0.8 LR    [D1 + D2 + … の組合せ]")."""

    first: str
    second: str


@dataclass(frozen=True)
class Unit:
    key: str
    kind: str  # heading, paragraph, math, pair, equation, definitions, table, figure
    value: Any
    left: float = BODY
    first_equal: float | None = None  # a pair: the x of its second text
    group: str = ""  # consecutive units of one group are kept on one page
    checked: bool = False  # an equation whose numeric chain recomputes from the printed numbers
    gap_before: bool = False
    keep: bool = False  # kept on the page of the following unit (an introduction to what follows)
    ruled: bool = False  # bracketed by the rule at RULE_X, with the blank lines around it

    @property
    def identifier(self) -> str:
        return PREFIX + self.key


@dataclass
class Manuscript:
    units: list[Unit] = field(default_factory=list)
    _group: str = ""
    _ruled: bool = False
    _keys: set[str] = field(default_factory=set)

    def start(self, name: str) -> None:
        """Following units, up to the next start, are kept together."""
        self._group = name

    def end(self) -> None:
        self._group = ""

    def rule_start(self) -> None:
        """Following units, up to rule_end, are bracketed by the rule (0600 p16)."""
        self._ruled = True

    def rule_end(self) -> None:
        self._ruled = False

    def _add(self, unit: Unit) -> None:
        if unit.key in self._keys:
            raise ValueError(f"0600: 重複した帳票キーです: {unit.key}")
        self._keys.add(unit.key)
        self.units.append(replace(unit, ruled=self._ruled))

    def heading(self, key: str, text: str, left: float) -> None:
        self._add(Unit(key, "heading", text, left))

    def paragraph(self, key: str, text: str, left: float = BODY, *, gap: bool = False, keep: bool = True) -> None:
        """A sentence; it introduces what follows, so it is kept on that unit's page."""
        self._add(Unit(key, "paragraph", text, left, group=self._group, gap_before=gap, keep=keep))

    def math(self, key: str, node: MathNode | str, left: float = BODY, *, gap: bool = False) -> None:
        self._add(Unit(key, "math", node, left, group=self._group, gap_before=gap))

    def pair(self, key: str, first: str, second: str, left: float, second_left: float, *,
             gap: bool = False) -> None:
        """Two texts on one line; it introduces what follows, so it is kept on that unit's page."""
        self._add(Unit(key, "pair", Pair(first, second), left, first_equal=second_left, group=self._group,
                       gap_before=gap, keep=True))

    def equation(self, key: str, lhs: Any, rhs: Any, result: Printed | None = None, *,
                 wide: bool = False, medium: bool = False, left: float | None = None, equal: float | None = None,
                 checked: bool = True, gap: bool = False) -> None:
        """lhs = rhs [= result unit]; a checked equation is a numeric chain the reader recomputes.

        A wide (derivation) equation writes its lhs text left-aligned at the derivation column, as the
        measured 0600 p26 does, so it is the equation's label before an empty lhs. *equal* places the
        "=" at a column of its own instead of the wide, medium or short one.
        """
        if wide and not isinstance(lhs, str):
            raise TypeError("0600: 導出式の左辺は文字列で書きます")
        node = Equation("" if wide else lhs, rhs, label=lhs if wide else "",
                        result=None if result is None else printed(result),
                        unit=None if result is None else unit_of(result), block_id=PREFIX + key)
        first_equal = equal if equal is not None else WIDE_EQUAL if wide else MEDIUM_EQUAL if medium else SHORT_EQUAL
        self._add(Unit(key, "equation", node, left if left is not None else WIDE_LHS if wide else SHORT_LHS,
                       first_equal=first_equal, group=self._group,
                       checked=checked and result is not None, gap_before=gap))

    def formula(self, key: str, lhs: Any, symbolic: MathNode | str | None, numeric: Sequence[Any],
                result: Printed, *, open_groups: bool = False, **options: Any) -> None:
        """lhs = symbols = numbers = result: the numbers are the printed operands of the result.

        The symbols and the numbers are one row of term columns; a long row wraps before the numbers' "=".
        """
        if symbolic is None:
            rhs = expr(*numeric, open_groups=open_groups)
        else:
            rhs = derivation(symbolic, expr("=", *numeric, open_groups=open_groups))
        self.equation(key, lhs, rhs, result, **options)

    def value(self, key: str, lhs: Any, value: Printed, *, symbolic: MathNode | str | None = None,
              **options: Any) -> None:
        """lhs [= symbol] = value: a value taken over as it is (no arithmetic to check)."""
        if symbolic is None:
            rhs: Any = Row(printed(value), " ", unit_of(value) or "", gap=0) if value.unit else printed(value)
            self.equation(key, lhs, rhs, checked=False, **options)
        else:
            self.equation(key, lhs, symbolic, value, checked=False, **options)

    def definitions(self, key: str, *items: Definition) -> None:
        """"ここに、" symbol：meaning, one line each, the symbols right-aligned against one colon column."""
        self._add(Unit(key, "definitions", items, INDENTED, first_equal=DEFINITION_COLON, group=self._group))

    def table(self, key: str, spec: TableSpec, left: float) -> None:
        self._add(Unit(key, "table", spec, left, gap_before=True))

    def figure(self, key: str, spec: FigureSpec, left: float = SUBSECTION) -> None:
        self._add(Unit(key, "figure", spec, left, gap_before=True))


def plain(value: Any) -> str:
    """The text of an authored node, in reading order (the semantic record)."""
    if isinstance(value, str):
        return value
    if isinstance(value, (TermStop, BreakHint)):
        return ""
    if isinstance(value, Literal):
        return value.text
    if isinstance(value, Row):
        return "".join(plain(item) for item in value.items)
    if isinstance(value, Script):
        return (plain(value.base) + (plain(value.subscript) if value.subscript else "")
                + ("^" + plain(value.superscript) if value.superscript else ""))
    if isinstance(value, Equation):
        text = value.label + plain(value.lhs) + value.relation + plain(value.rhs)
        if value.result is not None:
            text += value.result_relation + plain(value.result)
        return text + (plain(value.unit) if value.unit is not None else "")
    if isinstance(value, tuple) and value and all(isinstance(item, Definition) for item in value):
        return "ここに、" + "、".join(plain(item.symbol) + "：" + plain(item.text) for item in value)
    if isinstance(value, Pair):
        return value.first + value.second
    if isinstance(value, CellSpec):
        return plain(value.content)
    if isinstance(value, TableSpec):
        return "|".join("|".join(plain(cell) for cell in row) for row in value.rows)
    if isinstance(value, FigureSpec):
        return "|".join(value.labels)
    raise TypeError(f"0600 の帳票に未対応の要素です: {type(value).__name__}")


def cells(*values: Any, align: str | None = None) -> tuple[CellSpec, ...]:
    """A table row: Printed values are written at their digits, None as a dash."""
    row = []
    for value in values:
        if isinstance(value, CellSpec):
            row.append(value)
        elif isinstance(value, Printed):
            row.append(CellSpec(printed(value), align="right"))
        elif value is None:
            row.append(CellSpec("-", align="center"))
        else:
            row.append(CellSpec(value, align=align))
    return tuple(row)


def join(values: Iterable[Printed], operator: str = "+") -> list[Any]:
    """a + b + c as expression parts."""
    parts: list[Any] = []
    for value in values:
        if parts:
            parts.append(operator)
        parts.append(value)
    return parts
