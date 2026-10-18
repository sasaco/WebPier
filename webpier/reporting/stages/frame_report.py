"""Manuscript pieces shared by the frame-load reports (0610, 0620, 0710 and 0720).

A report is an ordered tuple of ``Unit``: one semantic piece (a heading, an
equation, a table, a figure) with what it prints. The same units drive the
layout and the semantic records of the tests. Every number is a Printed value
of a calc result or of the input, written by reporting.numbers; the formula
lines put printed operands beside the printed result, so a reader can check
them with a calculator (ADR-0003). Nothing is calculated here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from gridlayoutpdf import (
    Block, BreakHint, Cell, CellLines, Columns, Document, Equation, KeepWithNext, LayoutContext,
    LayoutOverflowError, Literal, MathNode, MeasuredBlock, PreferKeepTogether, Root, Row, Script, TermStop, Text,
    as_math, measure_block,
)

from ...calc.frame import Frame, LineLoad, Member, NodeRole, PointLoad, Region, Section
from ...calc.materials import EC_EXPONENT, Concrete
from ...core.printed import Printed
from ..document import blank, heading, indent_to, math_line, paragraph, report, spacer
from ..equations import Definition, definitions, equation_group, script, terms
from ..figures import AxialGlyph, DistributedGlyph, FrameFigure, Glyph, LoadDiagram, PointGlyph
from ..numbers import printed, unit
from ..styles import BASELINE, BODY, BODY_LEADING, grid_units
from ..tables import VerticalLabel, cell, table

# Heading levels (reporting-style.md: chapter 58.92, then 14.52 steps) and the body.
LEVELS = (58.92, 73.44, 87.96, 102.48)
BODY_LEFT = 117.0
TABLE_LEFT = 102.48
# The formula columns of the action pages (Example2 08 p.8-3: label, symbol, '=' ~205, result '=' ~437).
LABEL_LEFT = 117.0
FIRST_EQUAL = 219.72
SECOND_EQUAL = 436.44  # the 0600 multi-step result column (reporting-style.md)
RESULT_RIGHT = 496.2
UNIT_START = 500.64
# The "：" of a "ここに、" list: "ここに、" and the widest symbol (Δh) start at the label column.
DEFINITION_COLON = 178.08


def sub(base: str | MathNode, suffix: str) -> Script:
    return script(base, subscript=suffix)


def sup(base: str | MathNode, exponent: str) -> Script:
    return script(base, superscript=exponent)


def value(number: Printed, *, thousands: bool = False) -> str:
    return printed(number, thousands=thousands)


def operand(number: Printed) -> str:
    """A printed operand inside a formula: a negative value is put in parentheses."""
    text = printed(number)
    return f"({text})" if number.value < 0 else text


def with_unit(number: Printed, *, thousands: bool = False) -> Row:
    return Row(printed(number, thousands=thousands), " ", unit(number.unit), gap=0)


@dataclass(frozen=True)
class Labelled:
    """An equation with a word on the left of its symbol (はり, 断面積), as the action pages print them."""

    label: str
    equation: Equation


@dataclass(frozen=True)
class Span:
    """A table cell that spans rows/columns, or is written vertically."""

    value: Any
    colspan: int = 1
    rowspan: int = 1
    vertical: bool = False
    align: str = "center"


@dataclass(frozen=True)
class TableSpec:
    widths: tuple[float, ...]
    rows: tuple[tuple[Any, ...], ...]
    row_heights: tuple[float, ...]
    header_rows: int = 1
    numeric: frozenset[int] = frozenset()  # body columns aligned right
    left: float = TABLE_LEFT
    # An open table (the 鉛直力・アーム・モーメント tables, 0610 p4): no frame, no vertical rules and no rule
    # under the header; one 0.96 pt rule across the table above its last row (合計).
    open: bool = False


@dataclass(frozen=True)
class FigureSpec:
    block: Any  # a FrameFigure or a LoadDiagram
    texts: tuple[str, ...]
    left: float = 48.0


@dataclass(frozen=True)
class DiagramSpec:
    """A load diagram with the values of its cases beside it."""

    figure: LoadDiagram
    lines: tuple[Any, ...]


@dataclass(frozen=True)
class Definitions:
    """A "ここに、" list under an equation."""

    items: tuple[Definition, ...]


@dataclass(frozen=True)
class Unit:
    key: str
    value: Any
    kind: str  # heading, paragraph, line, equation, definitions, table, figure, diagram
    left: float = BODY_LEFT
    keep: bool = False  # keep with the next unit (a lead-in line)
    level: int = 0


def plain(item: Any) -> str:
    """The text a unit prints, in reading order (the semantic record)."""
    if item is None or isinstance(item, (TermStop, BreakHint)):
        return ""
    if isinstance(item, str):
        return item
    if isinstance(item, Literal):
        return item.text
    if isinstance(item, Row):
        return "".join(plain(part) for part in item.items)
    if isinstance(item, Script):
        return plain(item.base) + plain(item.subscript) + plain(item.superscript)
    if isinstance(item, Root):
        return "√" + plain(item.body)
    if isinstance(item, Equation):
        result = "" if item.result is None else item.result_relation + plain(item.result) + plain(item.unit)
        return plain(item.lhs) + item.relation + plain(item.rhs) + result
    if isinstance(item, Labelled):
        return item.label + plain(item.equation)
    if isinstance(item, Definitions):
        return "ここに、" + "".join(plain(d.symbol) + "：" + plain(d.text) for d in item.items)
    if isinstance(item, Span):
        return plain(item.value)
    if isinstance(item, TableSpec):
        return "".join(plain(cell_value) for row in item.rows for cell_value in row)
    if isinstance(item, FigureSpec):
        return "".join(item.texts)
    if isinstance(item, DiagramSpec):
        return "".join(item.figure.texts()) + "".join(plain(line) for line in item.lines)
    if isinstance(item, (tuple, list)):
        return "".join(plain(part) for part in item)
    raise TypeError(f"Unsupported frame report node: {type(item).__name__}")


class Manuscript:
    """Collects the units of one report under a key prefix."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.units: list[Unit] = []

    def add(self, key: str, item: Any, kind: str, *, left: float = BODY_LEFT, keep: bool = False,
            level: int = 0) -> None:
        self.units.append(Unit(self.prefix + key, item, kind, left, keep, level))

    def heading(self, key: str, text: str, level: int) -> None:
        self.add(key, text, "heading", left=LEVELS[level], level=level)

    def paragraph(self, key: str, text: str, *, left: float = BODY_LEFT, keep: bool = False) -> None:
        self.add(key, text, "paragraph", left=left, keep=keep)

    def line(self, key: str, item: Any, *, left: float = BODY_LEFT, keep: bool = False) -> None:
        self.add(key, item, "line", left=left, keep=keep)

    def equation(self, key: str, label: str, lhs: Any, rhs: Any, result: Printed | None = None, *,
                 thousands: bool = False, relation: str = "=", result_relation: str = "=",
                 result_text: Any = None, keep: bool = False) -> None:
        """``label  lhs = rhs = result unit``; without a result, ``label  lhs = rhs``."""
        if result is not None:
            item = Equation(lhs, rhs, result=result_text or printed(result, thousands=thousands),
                            unit=unit(result.unit) if result.unit else None, relation=relation,
                            result_relation=result_relation)
        elif result_text is not None:
            item = Equation(lhs, rhs, result=result_text, relation=relation, result_relation=result_relation)
        else:
            item = Equation(lhs, rhs, relation=relation)
        self.add(key, Labelled(label, item), "equation", keep=keep)

    def definitions(self, key: str, *items: Definition) -> None:
        self.add(key, Definitions(items), "definitions")

    def table(self, key: str, spec: TableSpec) -> None:
        self.add(key, spec, "table", left=spec.left)

    def figure(self, key: str, spec: FigureSpec) -> None:
        self.add(key, spec, "figure", left=spec.left)

    def diagram(self, key: str, spec: DiagramSpec) -> None:
        self.add(key, spec, "diagram")


def semantic_records(units: Sequence[Unit]) -> list[dict[str, str]]:
    return [{"id": unit.key, "text": plain(unit.value)} for unit in units]


# --- layout ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _LabelledBlock:
    """Draw each equation's label at *left* on the first line of that equation; never over its symbol.

    *labels* has one word per equation of the equation_group *block* ("" for none). The label is not
    an EquationGroup label column: a column shared by the group would push every symbol right of the
    widest word (断面二次モーメント), while the reference prints each word only before its own symbol.
    """

    labels: tuple[str, ...]
    block: Block
    left: float

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        measured = measure_block(self.block, context, available_width)
        x = self.left - context.profile.grid.origin_x
        parts = list(measured.parts)
        labelled: set[int] = set()
        for position, part in enumerate(parts):
            index = part.metadata["equation_index"]
            if index in labelled or not self.labels[index]:
                continue
            labelled.add(index)
            label, block_id = self.labels[index], part.metadata["equation_block_id"]
            texts = [command for command in part.commands if isinstance(command, Text)]
            width = context.fonts.measure(label, BODY).width
            if x + width + 2 > min(command.x for command in texts):
                raise LayoutOverflowError(f"{block_id}: 式の見出し「{label}」が記号に重なります",
                                          block_id=block_id, needed=width + 2, available=texts[0].x - x)
            relation = next((c for c in texts if c.text in ("=", "＝")), texts[0])
            parts[position] = replace(part, commands=(Text(x, relation.y, label, BODY), *part.commands))
        return replace(measured, parts=tuple(parts))


@dataclass(frozen=True)
class _RowLine:
    """One line in a one-row cell, on one baseline shared by every cell of the row.

    A line with a subscript (R_B, D_1) would otherwise be centred by its own
    taller envelope and sit off the baseline of the plain cells of its row.
    The row baseline centres the envelope of all the row's lines together.
    """

    content: Any
    align: str
    height: float
    row: tuple[Any, ...]  # the one-line contents of the row
    # An open table puts a one-row line on the body baseline (its text reads as body lines) when the row
    # fits there; a row with a subscript stays centred, a little higher, as in the reference (0610 p4).
    on_body_row: bool = False

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        boxes = [as_math(item).measure(context.fonts, BODY) for item in self.row]
        ascent, descent = max(box.ascent for box in boxes), max(box.descent for box in boxes)
        baseline = (self.height + ascent - descent) / 2
        if (self.on_body_row and self.height == BODY_LEADING and BASELINE - ascent >= 1.08
                and BASELINE + descent <= self.height - 1.08):
            baseline = BASELINE
        lines = CellLines((self.content,), style=BODY, line_advance=12.84, inner_padding=1.08, align=self.align,
                          min_height=self.height, first_baseline=baseline)
        return measure_block(lines, context, available_width)


def _one_line(span: Span) -> bool:
    return not span.vertical and span.rowspan == 1 and not (isinstance(span.value, str) and "\n" in span.value)


def _cell(item: Any, *, header: bool, numeric: bool, height: float, row: tuple[Any, ...],
          open_table: bool = False) -> Cell:
    span = item if isinstance(item, Span) else Span(item, align="center" if header else
                                                    "right" if numeric else "left")
    content = span.value
    if span.vertical:
        return cell(VerticalLabel(content, style=BODY), colspan=span.colspan, rowspan=span.rowspan, align="center")
    if _one_line(span):
        return Cell(_RowLine(content, span.align, height, row, open_table), colspan=span.colspan, align=span.align,
                    padding=0)
    if isinstance(content, str) and open_table and span.rowspan == 1:
        # a two-line header of an open table, on the body rows
        lines = CellLines(tuple(content.split("\n")), style=BODY, line_advance=BODY_LEADING, inner_padding=1.08,
                          align=span.align, min_height=height, first_baseline=BASELINE)
        return Cell(lines, colspan=span.colspan, align=span.align, padding=0)
    if isinstance(content, str):
        return cell(content, colspan=span.colspan, rowspan=span.rowspan, align=span.align)
    lines = CellLines((content,), style=BODY, inner_padding=1.08, align=span.align)
    return Cell(lines, colspan=span.colspan, rowspan=span.rowspan, align=span.align, padding=0)


def table_block(spec: TableSpec, block_id: str) -> Block:
    rows = []
    for index, row in enumerate(spec.rows):
        spans = [item if isinstance(item, Span) else Span(item) for item in row]
        lines = tuple(span.value for span in spans if _one_line(span))
        rows.append([_cell(item, header=index < spec.header_rows, numeric=column in spec.numeric,
                           height=spec.row_heights[index], row=lines, open_table=spec.open)
                     for column, item in enumerate(row)])
    rules: dict[str, Any] = {}
    if spec.open:
        # One part (split=False) draws the rule between two rows once, not once per row.
        rules = {"horizontal_rules": tuple(.96 if index == len(rows) - 1 else 0 for index in range(len(rows) + 1)),
                 "vertical_rules": (0,) * (len(spec.widths) + 1), "split": False}
    return indent_to(table(spec.widths, rows, row_heights=spec.row_heights, header_rows=spec.header_rows,
                           block_id=block_id, **rules), spec.left)


def _diagram_block(spec: DiagramSpec, block_id: str) -> Block:
    lines = CellLines(spec.lines, style=BODY, line_advance=BODY_LEADING)
    width = 528 - (BODY_LEFT - 48) - spec.figure.width - 14.52
    return indent_to(Columns(spec.figure, lines, col_spans=(grid_units(spec.figure.width), grid_units(width)),
                             gap_cols=grid_units(14.52), block_id=block_id), BODY_LEFT)


_FLOATS = ("table", "figure", "diagram")


def _columns(equation: Equation) -> tuple[bool, bool]:
    """The anchors an equation uses beyond its "=": the result column and the unit column."""
    return equation.result is not None, equation.unit is not None


def _equations(run: Sequence[Unit]) -> Block:
    """Consecutive equations in one group, their term columns lined up across the lines (0610 p4: the
    浮力 of the high, normal and low water levels); each keeps its word on its own first line."""
    result, has_unit = _columns(run[0].value.equation)
    return _LabelledBlock(tuple(piece.value.label for piece in run), equation_group(
        *(replace(piece.value.equation, block_id=piece.key) for piece in run),
        left=LABEL_LEFT, first_equal=FIRST_EQUAL,
        second_equal=SECOND_EQUAL if result else None, result_right=RESULT_RIGHT if result else None,
        unit_start=UNIT_START if has_unit else None, block_id=run[0].key,
        keep=tuple(piece.keep for piece in run)), LABEL_LEFT)


def _title_of(piece: Unit | None, following: Unit | None) -> bool:
    """A kept paragraph directly before a table, figure or diagram is its title (as the 0500 table caption)."""
    return (piece is not None and following is not None and piece.kind == "paragraph" and piece.keep
            and following.kind in _FLOATS)


def blocks(units: Sequence[Unit]) -> list[Block]:
    """A heading, table, figure or diagram (with its title) has one blank line before and after it, and a
    lead-in line (a kept paragraph, "・橋脚天端に作用する荷重") opens its group with one blank line before it
    (0610 p4); blank lines never stack."""
    found: list[Block] = []
    index = 0
    while index < len(units):
        piece = units[index]
        previous = units[index - 1] if index else None
        index += 1
        if piece.kind == "heading":
            blank(found)
            found.append(heading(piece.value, left=piece.left, block_id=piece.key))
            found.append(KeepWithNext(spacer()))
            continue
        if piece.kind == "paragraph":
            block: Block = paragraph(piece.value, left=piece.left, block_id=piece.key)
        elif piece.kind == "line":
            block = math_line(piece.value, left=piece.left, block_id=piece.key)
        elif piece.kind == "equation":
            run = [piece]
            while index < len(units) and units[index].kind == "equation" and (
                    _columns(units[index].value.equation) == _columns(piece.value.equation)):
                run.append(units[index])
                index += 1
            block = _equations(run)
            piece = run[-1]
        elif piece.kind == "definitions":
            block = definitions(*piece.value.items, left=LABEL_LEFT, colon=DEFINITION_COLON, block_id=piece.key)
        elif piece.kind == "table":
            block = PreferKeepTogether(table_block(piece.value, piece.key))
        elif piece.kind == "figure":
            block = indent_to(piece.value.block, piece.left)
        else:
            block = _diagram_block(piece.value, piece.key)
        lead_in = piece.kind == "paragraph" and piece.keep
        if lead_in or piece.kind in _FLOATS and not _title_of(previous, piece):
            blank(found)
        found.append(KeepWithNext(block) if piece.keep else block)
        if piece.kind in _FLOATS:
            found.append(spacer())
    return found


def document(units: Sequence[Unit]) -> Document:
    if len({unit.key for unit in units}) != len(units):
        raise ValueError("帳票の単位に重複したキーがあります")
    return report(*blocks(units))


# --- the frame model (8.1 / 10.1) ---------------------------------------------------------------------------

_ROLE_NAMES = {
    NodeRole.CAP_TOP: "はり天端", NodeRole.BEAM_BOTTOM: "はり下端", NodeRole.COLUMN_TOP: "柱上端",
    NodeRole.MICRO_TOP: "微小部材上端", NodeRole.FOOTING_TOP: "フーチング天端",
    NodeRole.FOOTING_CENTROID: "フーチング重心", NodeRole.FOOTING_BOTTOM: "フーチング底面",
    NodeRole.PEDESTAL_BASE: "桁受け下端", NodeRole.PEDESTAL_TOP: "桁受け天端",
    NodeRole.GIRDER_ORIGIN: "起点側の桁", NodeRole.GIRDER_END: "終点側の桁",
}
REGION_NAMES = {
    Region.BEAM: "はり", Region.HAUNCH: "ハンチ", Region.COLUMN: "柱", Region.COLUMN_BASE: "柱下端の微小部材",
    Region.FOOTING_UPPER: "フーチング天端～重心", Region.FOOTING_LOWER: "フーチング重心～底面",
    Region.PEDESTAL_ARM: "桁受けまでの剛域", Region.PEDESTAL: "桁受け", Region.GIRDER: "支承から桁までの剛域",
}


def node_table(frame: Frame, *, springs: bool = True) -> TableSpec:
    """Nodes and their roles; with *springs* the footing bottom is named as the spring node (0610, 0620)."""
    rows = [("節点番号", "X座標 (m)", "Y座標 (m)", "位置")]
    for node in frame.nodes:
        names = "・".join(name + ("（ばね）" if springs and role is NodeRole.FOOTING_BOTTOM else "")
                         for role, name in _ROLE_NAMES.items() if role in node.roles)
        rows.append((str(node.number), value(node.x), value(node.y), names))
    return TableSpec((60, 84, 84, 204), tuple(rows), (BODY_LEADING,) * len(rows), numeric=frozenset({0, 1, 2}))


def _section_name(frame: Frame, member: Member) -> str:
    if member.section is None:
        return "剛域"
    return "桁受け" if member.section == frame.pedestal_section and member.region is Region.PEDESTAL else "柱"


def member_table(frame: Frame) -> TableSpec:
    rows = [("部材番号", "i端", "j端", "高さ (m)", "水平距離 (m)", "部位", "断面", Row("f'ck (N/mm", sup("", "2"), ")",
                                                                              gap=0))]
    for member in frame.members:
        rows.append((str(member.number), str(member.start), str(member.end), value(member.height),
                     value(member.offset), REGION_NAMES[member.region], _section_name(frame, member),
                     value(member.material.strength) if member.material is not None else "－"))
    return TableSpec((48, 32.4, 32.4, 56.4, 63.6, 120, 43.2, 72), tuple(rows), (BODY_LEADING,) * len(rows),
                     numeric=frozenset({0, 1, 2, 3, 4, 7}))


def spring_table(frame: Frame) -> TableSpec:
    long_term, short_term = frame.support.long_term, frame.support.short_term
    rows = [(Span("", rowspan=2), Span("記号", rowspan=2), Span("安定計算時", colspan=2), Span("単位", rowspan=2)),
            ("長期", "短期")]
    for name, symbol, field_name in (("鉛直ばね", sub("K", "v"), "kv"), ("せん断ばね", sub("K", "s"), "ks"),
                                     ("回転ばね", sub("K", "r"), "kr")):
        a, b = getattr(long_term, field_name), getattr(short_term, field_name)
        rows.append((name, Span(symbol), value(a, thousands=True), value(b, thousands=True), Span(unit(a.unit))))
    return TableSpec((84, 48, 108, 108, 84), tuple(rows), (BODY_LEADING,) * len(rows), header_rows=2,
                     numeric=frozenset({2, 3}))


def section_lines(m: Manuscript, key: str, section: Section) -> None:
    """b, h, A = b × h and I = 1/12 × b × h³ (8-2)."""
    m.line(key + ".size", Row("b = ", with_unit(section.width), "　　h = ", with_unit(section.depth), gap=0))
    m.equation(key + ".area", "断面積", "A", terms(value(section.width), "×", value(section.depth)),
               section.area)
    m.equation(key + ".inertia", "断面二次モーメント", "I",
               terms("1/12", "×", value(section.width), "×", sup(value(section.depth), "3")),
               section.inertia)


def material_lines(m: Manuscript, key: str, label: str, concrete: Concrete) -> None:
    """f'ck, the two table points and Ec (decision 25)."""
    m.equation(key + ".strength", label, "f'ck", with_unit(concrete.strength))
    m.equation(key + ".modulus", "", "Ec", terms(value(concrete.modulus), "×",
                                                 Row(sup("10", str(EC_EXPONENT)), " ", unit("kN/m2"), gap=0)))
    low, high = concrete.lower, concrete.upper
    m.line(key + ".table", Row("（表の f'ck = ", with_unit(low.strength), " で Ec = ", with_unit(low.modulus),
                               "，f'ck = ", with_unit(high.strength), " で Ec = ", with_unit(high.modulus),
                               " から直線補間）", gap=0), left=LABEL_LEFT + 14.52)


def used_concretes(frame: Frame) -> list[tuple[str, str, Concrete]]:
    """The concretes of the members with a section: く体 if beam and column are the same."""
    regions = {member.region for member in frame.members if not member.rigid}
    beam = bool(regions & {Region.BEAM, Region.HAUNCH, Region.PEDESTAL})
    column = bool(regions & {Region.COLUMN, Region.COLUMN_BASE})
    materials = frame.materials
    if beam and column and materials.beam == materials.column:
        return [("body", "く体", materials.column)]
    found = []
    if beam:
        found.append(("beam", "はり", materials.beam))
    if column:
        found.append(("column", "柱", materials.column))
    return found


# --- load tables and seat transfer ----------------------------------------------------------------------------

def top_table(rows: Sequence[tuple[Any, Printed, Printed, Printed]], total: tuple[Printed, Printed]) -> TableSpec:
    """鉛直力・アーム・モーメント by source and their sums (8-3, 8-4)."""
    body = [("", "鉛直力 (kN)", "アーム (m)", "モーメント (kN・m)")]
    body += [(Span(label, align="left"), value(n), value(arm), value(moment)) for label, n, arm, moment in rows]
    body.append(("合計", value(total[0]), "", value(total[1])))
    return TableSpec((120, 96, 96, 120), tuple(body), (BODY_LEADING,) * len(body), numeric=frozenset({1, 2, 3}),
                     left=BODY_LEFT, open=True)


def seat_moment(m: Manuscript, key: str, frame: Frame, n: Printed, moment: Printed, point: PointLoad) -> None:
    """With an offset pedestal the bearing moment moves to the seat: M' = M − N × e (decision 29)."""
    offset = frame.bearing_offset
    if not offset.value:
        return
    m.equation(key, "桁受け天端", "M", terms(value(moment), "−", value(n), "×", operand(offset)), point.m)


def overlap_lines(m: Manuscript, substructure: Any, fixed: Any) -> None:
    """The length where the column q runs through the beam and haunch already weighed in the table (8-3, 9-3)."""
    m.equation("fixed.overlap", "重複区間", "Δh", terms(value(substructure.h[2]), "+", value(substructure.h[3])),
               fixed.overlap)
    m.definitions("fixed.overlap.note", Definition("Δh", "はりの高さ ＋ ハンチの高さ（柱の q と重なる長さ）"))


def joined(parts: list[Any]) -> list[Any]:
    """Operands joined by +, for terms()."""
    found: list[Any] = []
    for part in parts:
        if found:
            found.append("+")
        found.append(part)
    return found


def seat_split(m: Manuscript, fixed: Any, points: Sequence[PointLoad], frame: Frame,
               bearing: Callable[[Any], bool]) -> None:
    """With the bearings on an offset pedestal, D1 splits into the seat and the beam top (decision 29).

    *fixed* is the D1 of the stage (its table, q and the overlap), *points* the D1 point loads and
    *bearing* tells the bearing rows of the table from the pier parts.
    """
    seat = next(p for p in points if p.anchor is NodeRole.PEDESTAL_TOP)
    cap = next(p for p in points if p.anchor is NodeRole.CAP_TOP)
    bearings = [row for row in fixed.table.rows if bearing(row)]
    body = [row for row in fixed.table.rows if not bearing(row)]
    m.paragraph("fixed.seat.heading", "・桁受け天端とはり天端への載荷", keep=True)
    m.equation("fixed.seat.n", "桁受け天端", "N", terms(*joined([value(r.n) for r in bearings])), seat.n)
    moments = joined([operand(r.m) if i else value(r.m) for i, r in enumerate(bearings)])
    m.equation("fixed.seat.m", "", "M", terms(*moments, "−", value(seat.n), "×", operand(frame.bearing_offset)),
               seat.m)
    m.equation("fixed.cap.n", "はり天端", "N'", terms(*joined([value(r.n) for r in body]), "−",
                                                  value(fixed.column_q), "×", value(fixed.overlap)), cap.n)
    m.equation("fixed.cap.m", "", "M'", terms(*joined([operand(r.m) if i else value(r.m)
                                                        for i, r in enumerate(body)])), cap.m)


def self_weight_inertia(m: Manuscript, inertia: Any, heading: str, chapter: str) -> None:
    """Kh, Hw = b × w × γ × Kh of the beam, haunch bottom, column (pedestal) and H at the footing (10-8, 11-8)."""
    m.heading("inertia.heading", heading, 2)
    m.equation("inertia.kh", "設計水平震度", sub("K", "h"), value(inertia.kh))
    m.paragraph("inertia.body", "・橋脚く体に作用する水平力", keep=True)
    parts = (("beam_top", "はり", "w1", inertia.beam_top), ("beam_bottom", "ハンチ下端", "w2", inertia.beam_bottom),
             ("column", "柱", "w3", inertia.column), ("pedestal", "桁受け", "w4", inertia.pedestal))
    for key, label, name, intensity in parts:
        if intensity is not None:
            m.equation(f"inertia.{key}", label, sub("H", name),
                       terms(value(intensity.along), "×", value(intensity.across), "×",
                             value(intensity.unit_weight), "×", value(intensity.kh)), intensity.value)
    m.paragraph("inertia.footing.heading", "・フーチング重心に作用する水平力", keep=True)
    footing = inertia.footing
    m.equation("inertia.footing.formula", "", "H", terms("V", "×", "(", "γ", "−", "γ'", ")", "×", sub("K", "h")))
    m.equation("inertia.footing", "", "H",
               terms(value(footing.volume), "×", "(", value(footing.unit_weight), "−", value(footing.displaced), ")",
                     "×", value(footing.kh)), footing.force)
    m.definitions("inertia.footing.note", Definition("V", f"フーチングの体積（{chapter}）"),
                  Definition("γ'", "排除した土（表層）の湿潤単位体積重量"))


# --- combinations (8.4 / 9.4) -----------------------------------------------------------------------------


def coefficient_table(headers: Sequence[tuple[str, str, str]], numbers: Sequence[int],
                      rows: Sequence[tuple[str, Any, str, Sequence[Printed | None]]]) -> TableSpec:
    """Cases as rows, combinations as columns, the coefficients as printed (8-10, 9-14).

    *headers* gives each combination its requirement, performance item and remark; neighbours with the
    same text share a header cell. A missing coefficient prints '－'.
    """
    header: list[list[Any]] = [[Span("No", rowspan=4), Span("記号", rowspan=4), Span("荷重名称", rowspan=4)], [], [], []]
    for level in (0, 1):
        index = 0
        while index < len(headers):
            text, span = headers[index][level], 1
            while (index + span < len(headers) and headers[index + span][level] == text
                   and headers[index + span][0] == headers[index][0]):
                span += 1
            header[level].append(Span(text, colspan=span))
            index += span
    header[2] = [Span(remark, vertical=True) if remark else "" for *_, remark in headers]
    header[3] = [str(number) for number in numbers]
    body = [(number, Span(symbol), name, *(value(c) if c is not None else Span("－") for c in coefficients))
            for number, symbol, name, coefficients in rows]
    width = 23.04 if len(headers) <= 16 else 22.08
    widths = (19.92, 64.32, 528 - 19.92 - 64.32 - width * len(headers), *(width,) * len(headers))
    heights = (28.56, 14.28, 47.76, 14.28) + (14.28,) * len(body)
    return TableSpec(widths, (*(tuple(row) for row in header), *body), heights, header_rows=4,
                     numeric=frozenset({0, *range(3, 3 + len(headers))}), left=48.0)


def factor_lines(m: Manuscript, factors: Any, train: Any, maximum: Any, service_impact: Any) -> None:
    """ρ as entered and as printed in the table, 1.1ρ and 0.75ρ (8-10, 9-14)."""
    m.equation("factors.ultimate", "安全性・復旧性", "ρ", value(train.factor_ultimate), factors.ultimate,
               result_relation="≒")
    m.equation("factors.maximum", "列車最大", "1.1ρ", terms(maximum, "×", value(train.factor_ultimate)),
               factors.maximum)
    m.equation("factors.service", "使用性", "ρ", value(train.factor_service), factors.service, result_relation="≒")
    m.equation("factors.service_impact", "使用性の衝撃", "0.75ρ",
               terms(service_impact, "×", value(train.factor_service)), factors.service_impact)


EXTRACTION_NAMES = ("安全性（破壊）", "永久＋変動", "永久作用", "変動作用", "復旧性（損傷）", "安全性（安定）",
                    "長期支持性能", "短期支持性能")


def extraction_table(m: Manuscript, extractions: Sequence[Any]) -> None:
    width = max(len(extraction.combinations) for extraction in extractions)
    rows: list[tuple[Any, ...]] = [("No", "名称", *(f"C{index}" for index in range(1, width + 1)))]
    for extraction in extractions:
        numbers = [str(number) for number in extraction.combinations]
        rows.append((str(extraction.number), EXTRACTION_NAMES[extraction.group.value - 1], *numbers,
                     *[""] * (width - len(numbers))))
    m.table("extraction", TableSpec((28.8, 120, *(39.6,) * width), tuple(rows), (14.28,) * len(rows),
                                    numeric=frozenset({0, *range(2, 2 + width)})))


def bearing_symbol(side: str) -> MathNode:
    return Row("起点側　" if side == "origin" else "終点側　", sub("R", "B" if side == "origin" else "C"), gap=0)


# --- load diagrams (0620 9.3; 0610, 0710 and 0720 print none, decision 41) --------------------------------------


@dataclass(frozen=True)
class CaseLoads:
    """One basic case on the frame, with its title and how the all-zero loads are listed."""

    number: int
    title: str
    points: tuple[PointLoad, ...]
    line_loads: tuple[LineLoad, ...] = ()
    # member, start, end (signed, kN/m), and optionally the loaded part (t0, t1) of the member length
    member_loads: tuple[tuple[Any, ...], ...] = ()
    member_names: dict[Region, tuple[str, str]] = field(default_factory=dict)  # region → names of start, end
    horizontal: bool = False  # an all-zero load is listed as H, otherwise as N


_TOP = (NodeRole.PEDESTAL_TOP, NodeRole.CAP_TOP)


def _point_names(case: CaseLoads) -> list[tuple[PointLoad, dict[str, str]]]:
    """Symbols of each point load: N/M/H at the top, P/MP/H at the footing; N'/M'/H' at the beam top if a seat exists."""
    anchors = {point.anchor for point in case.points}
    named = []
    top_horizontal = any(p.h.value for p in case.points if p.anchor in _TOP)
    for point in case.points:
        if point.anchor in _TOP:
            prime = "'" if point.anchor is NodeRole.CAP_TOP and NodeRole.PEDESTAL_TOP in anchors else ""
            names = {"n": "N" + prime, "m": "M" + prime, "h": "H" + prime}
        else:
            names = {"n": "P", "m": "M_P", "h": "H_P" if top_horizontal else "H"}
        named.append((point, names))
    return named


def _listed(point: PointLoad, horizontal: bool) -> list[str]:
    # Example2 9-11: N, then H, then M
    found = [component for component in ("n", "h", "m") if getattr(point, component).value]
    return found or (["h"] if horizontal else ["n"])


def _symbol(name: str) -> MathNode | str:
    base, _, suffix = name.partition("_")
    return sub(base, suffix) if suffix else name


def _point_signs(case: CaseLoads) -> list[tuple[int, str, str, int]]:
    """(node, kind, label, sign) of each listed point component; a zero component has sign 0."""
    kinds = {"n": "N", "m": "M", "h": "H"}
    found = []
    for point, names in _point_names(case):
        for component in _listed(point, case.horizontal):
            number = getattr(point, component).value
            kind = "P" if component == "n" and point.anchor not in _TOP else kinds[component]
            found.append((point.node, kind, names[component], (number > 0) - (number < 0)))
    return found


def case_glyphs(frame: Frame, case: CaseLoads, signs: Sequence[int] | None = None) -> list[Glyph]:
    """The glyphs of *case*; *signs* (of a group) replace the case's own, a zero drawn positive."""
    glyphs: list[Glyph] = []
    points = _point_signs(case)
    for index, (node, kind, label, sign) in enumerate(points):
        chosen = signs[index] if signs is not None else sign
        glyphs.append(PointGlyph(node, kind, -1 if chosen < 0 else 1, label))
    for line in case.line_loads:
        if line.n.value:
            glyphs.append(AxialGlyph(line.members, "q"))
        if line.h.value:
            glyphs.append(DistributedGlyph(tuple((number, line.h.value, line.h.value) for number in line.members),
                                           ((line.members[0], .5, "qh"),)))
    if case.member_loads:
        regions = {member.number: member.region for member in frame.members}
        labels, seen = [], set()
        for number, start, end, *_ in case.member_loads:
            for where, name in zip((0.0, 1.0), case.member_names[regions[number]], strict=True):
                if name not in seen:
                    seen.add(name)
                    labels.append((number, .5 if start == end else where, name))
        glyphs.append(DistributedGlyph(tuple((n, s.value, e.value, *part) for n, s, e, *part in case.member_loads),
                                       tuple(labels)))
    return glyphs


def directed(number: Printed) -> Row:
    """A horizontal force as Example2 9-11 prints it: its magnitude and its direction (+x is →).

    The sign stays in the calc result; only the way it is written changes.
    """
    magnitude = Printed(abs(number.value), number.digits, number.unit)
    return Row(with_unit(magnitude), "（←）" if number.value < 0 else "（→）", gap=0)


def case_lines(frame: Frame, case: CaseLoads) -> list[Any]:
    """The values of one case: ``N = 8299.53 kN`` and so on, in the order of the glyphs.

    Horizontal forces are written as magnitude and direction (Example2 9-11).
    """
    lines: list[Any] = []
    for point, names in _point_names(case):
        for component in _listed(point, case.horizontal):
            number = getattr(point, component)
            lines.append(Row(_symbol(names[component]), " = ", directed(number) if component == "h" else
                             with_unit(number), gap=0))
    for line in case.line_loads:
        if line.n.value:
            lines.append(Row("q = ", with_unit(line.n), gap=0))
        if line.h.value:
            lines.append(Row(sub("q", "h"), " = ", directed(line.h), gap=0))
    if case.member_loads:
        regions = {member.number: member.region for member in frame.members}
        seen: set[str] = set()
        for number, start, end, *_ in case.member_loads:
            for intensity, name in zip((start, end), case.member_names[regions[number]], strict=True):
                if name not in seen:
                    seen.add(name)
                    lines.append(Row(name, " = ", directed(intensity), gap=0))
    return lines


def _shape(frame: Frame, case: CaseLoads) -> tuple[Any, ...]:
    """What a diagram draws for *case*, apart from the point directions."""
    others = tuple(type(glyph) for glyph in case_glyphs(frame, case) if not isinstance(glyph, PointGlyph))
    return tuple((node, kind, label) for node, kind, label, _ in _point_signs(case)) + others


def _compatible(frame: Frame, cases: Sequence[CaseLoads]) -> list[tuple[list[CaseLoads], list[int]]]:
    """Split *cases* into runs drawn by one diagram: the same glyphs, pointing the same way.

    A zero load fits either direction; a run takes the direction of its first nonzero load.
    """
    runs: list[tuple[list[CaseLoads], list[int]]] = []
    for case in cases:
        signs = [sign for *_, sign in _point_signs(case)]
        if runs and _shape(frame, runs[-1][0][0]) == _shape(frame, case) and \
                all(a == b or not a or not b for a, b in zip(runs[-1][1], signs, strict=True)):
            runs[-1][0].append(case)
            runs[-1][1][:] = [a or b for a, b in zip(runs[-1][1], signs, strict=True)]
        else:
            runs.append(([case], signs))
    return runs


def diagram_groups(m: Manuscript, frame: Frame, groups: Iterable[tuple[str, str, Sequence[CaseLoads]]],
                   title: Callable[[str, Sequence[CaseLoads]], str]) -> None:
    """One diagram per group of cases with the same glyphs; each group heads its values with the case titles."""
    for key, name, cases in groups:
        runs = _compatible(frame, cases)
        for index, (run, signs) in enumerate(runs):
            suffix = "" if len(runs) == 1 else f".{index + 1}"
            alone = f"　{run[0].title}" if len(run) == 1 and len(cases) > 1 else ""  # a case split from its group
            m.paragraph(f"diagrams.{key}{suffix}.title", title(name, run) + alone, keep=True, left=LEVELS[3])
            lines: list[Any] = []
            for case in run:
                if len(run) > 1:
                    lines.append(f"Case {case.number}　{case.title}")
                lines += case_lines(frame, case)
            diagram = LoadDiagram(frame, tuple(case_glyphs(frame, run[0], signs)),
                                  block_id=f"{m.prefix}diagrams.{key}{suffix}")
            m.diagram(f"diagrams.{key}{suffix}", DiagramSpec(diagram, tuple(lines)))


def frame_figure(frame: Frame, outline: Any, **options: Any) -> FigureSpec:
    figure = FrameFigure(frame, outline, **options)
    return FigureSpec(figure, figure.texts())


__all__ = [
    "BODY_LEFT", "CaseLoads", "Definitions", "DiagramSpec", "FigureSpec", "LEVELS", "Labelled", "Manuscript", "Span",
    "TableSpec", "Unit", "bearing_symbol", "case_glyphs", "case_lines", "diagram_groups", "document",
    "frame_figure", "material_lines", "member_table", "node_table", "operand", "plain", "section_lines",
    "seat_moment", "semantic_records", "spring_table", "sub", "sup", "top_table", "used_concretes", "value",
    "with_unit",
]
