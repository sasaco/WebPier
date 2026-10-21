"""Manuscript pieces shared by the frame-load reports (0610, 0620, 0710 and 0720).

A report is an ordered tuple of ``Unit``: one semantic piece (a heading, an
equation, a table, a figure) with what it prints. The same units drive the
layout and the semantic records of the tests. Every number is a Printed value
of a calc result or of the input, written by reporting.numbers; the formula
lines put printed operands beside the printed result, so a reader can check
them with a calculator (ADR-0003). Nothing is calculated here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from gridlayoutpdf import (
    Block, BreakHint, Cell, CellLines, Document, Equation, KeepWithNext, LayoutContext, Literal, MathNode,
    MeasuredBlock, PreferKeepTogether, Root, Row, Script, Spacer, Stack, TermStop, measure_block,
)

from ...calc.frame import Frame, Member, NodeRole, PointLoad, Region, Section
from ...calc.materials import EC_EXPONENT, Concrete
from ...core.printed import Printed
from ..document import blank, heading, indent_to, math_line, paragraph, report, spacer
from ..equations import Definition, definitions, equation_group, script, terms
from ..figures import FrameFigure
from ..numbers import printed, unit
from ..styles import BODY, BODY_COLUMNS, PITCH_Y
from ..tables import CELL_PADDING, OUTER, VerticalLabel, cell, math_cell, table

# Body columns of the grid: each heading level one column further in (the reference's 14.52 pt steps), then the body.
LEVELS = (0, 1, 2, 3)
BODY_LEFT = 4
TABLE_LEFT = 3
# The formula columns of the action pages (Example2 08 p.8-3: label, symbol, '=', result '='): the label from column 4,
# "=" on the boundary before column 11, the result's "=" before column 22, the result ending at column 26 and the unit
# from column 27 to the body's right edge (column 30).
LABEL_LEFT = 4
FIRST_EQUAL = 11
SECOND_EQUAL = 22
RESULT_RIGHT = 26
UNIT_START = 27
# The "：" of a "ここに、" list: "ここに、" and the widest symbol (Δh) start at the label column.
DEFINITION_COLON = 8


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
    widths: tuple[int, ...]  # grid columns
    rows: tuple[tuple[Any, ...], ...]
    row_heights: tuple[int, ...]  # grid rows
    header_rows: int = 1
    numeric: frozenset[int] = frozenset()  # body columns aligned right
    left: int = TABLE_LEFT
    # An open table (the 鉛直力・アーム・モーメント tables, 0610 p4): no frame, no vertical rules and no rule
    # under the header; one medium rule across the table above its last row (合計).
    open: bool = False


@dataclass(frozen=True)
class FigureSpec:
    block: Any  # a FrameFigure
    texts: tuple[str, ...]
    left: int = 0


@dataclass(frozen=True)
class Definitions:
    """A "ここに、" list under an equation."""

    items: tuple[Definition, ...]
    colon: int = 0  # the "：" column; 0 is DEFINITION_COLON (a wider symbol list takes its own)


@dataclass(frozen=True)
class Unit:
    key: str
    value: Any
    kind: str  # heading, paragraph, line, equation, definitions, table, figure
    left: int = BODY_LEFT
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
    if isinstance(item, (tuple, list)):
        return "".join(plain(part) for part in item)
    raise TypeError(f"Unsupported frame report node: {type(item).__name__}")


class Manuscript:
    """Collects the units of one report under a key prefix."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.units: list[Unit] = []

    def add(self, key: str, item: Any, kind: str, *, left: int = BODY_LEFT, keep: bool = False,
            level: int = 0) -> None:
        self.units.append(Unit(self.prefix + key, item, kind, left, keep, level))

    def heading(self, key: str, text: str, level: int, *, tag: str | None = None) -> None:
        """A heading; *tag* (e.g. "【ＲＣ標準 7.2.2】") is its source on the same line."""
        self.add(key, text if tag is None else (text, tag), "heading", left=LEVELS[level], level=level)

    def paragraph(self, key: str, text: str, *, left: int = BODY_LEFT, keep: bool = False) -> None:
        self.add(key, text, "paragraph", left=left, keep=keep)

    def line(self, key: str, item: Any, *, left: int = BODY_LEFT, keep: bool = False) -> None:
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

    def definitions(self, key: str, *items: Definition, colon: int = 0) -> None:
        self.add(key, Definitions(items, colon), "definitions")

    def table(self, key: str, spec: TableSpec) -> None:
        self.add(key, spec, "table", left=spec.left)

    def figure(self, key: str, spec: FigureSpec) -> None:
        self.add(key, spec, "figure", left=spec.left)


def semantic_records(units: Sequence[Unit]) -> list[dict[str, str]]:
    return [{"id": unit.key, "text": plain(unit.value)} for unit in units]


# --- layout ------------------------------------------------------------------------------------------------


# Where a plain 10 pt line centred in one grid row stands: every one-line body cell takes it (in the middle of its
# span), so that a cell with a subscript (起点側 R_B) stands on the baseline of the numbers of its row, as GridLayoutPdf
# would otherwise centre each cell's own envelope. Header cells stay centred: a superscript (N/mm²) needs the room.
CELL_BASELINE = 11.33


def _cell(item: Any, *, header: bool, numeric: bool, rows: int) -> Cell:
    """A table cell: one grid row per line, or text turned in its column when the span is vertical (*rows* is the
    height of the span in grid rows)."""
    span = item if isinstance(item, Span) else Span(item, align="center" if header else
                                                    "right" if numeric else "left")
    content = span.value
    if span.vertical:
        return cell(VerticalLabel(content, rows), colspan=span.colspan, rowspan=span.rowspan, align="center")
    if not header and not (isinstance(content, str) and "\n" in content):
        lines = CellLines((content,), style=BODY, line_advance=PITCH_Y, inner_padding=CELL_PADDING, align=span.align,
                          first_baseline=CELL_BASELINE + (rows - 1) * PITCH_Y / 2)
        return Cell(lines, colspan=span.colspan, rowspan=span.rowspan, align=span.align, padding=0)
    if isinstance(content, str):
        return cell(content, colspan=span.colspan, rowspan=span.rowspan, align=span.align)
    return math_cell(content, colspan=span.colspan, rowspan=span.rowspan, align=span.align)


def table_block(spec: TableSpec, block_id: str) -> Block:
    rows = []
    for index, row in enumerate(spec.rows):
        rows.append([_cell(item, header=index < spec.header_rows, numeric=column in spec.numeric,
                           rows=sum(spec.row_heights[index:index + (item.rowspan if isinstance(item, Span) else 1)]))
                     for column, item in enumerate(row)])
    rules: dict[str, Any] = {}
    if spec.open:
        # One part (split=False) draws the rule between two rows once, not once per row.
        rules = {"inner": None, "outer": None, "horizontal": {len(rows) - 1: OUTER}, "split": False}
    return indent_to(table(spec.widths, rows, row_heights=spec.row_heights, header_rows=spec.header_rows,
                           block_id=block_id, **rules), spec.left)


_FLOATS = ("table", "figure")


def _columns(equation: Equation) -> tuple[bool, bool]:
    """The anchors an equation uses beyond its "=": the result column and the unit column."""
    return equation.result is not None, equation.unit is not None


def _equations(run: Sequence[Unit]) -> Block:
    """Consecutive equations in one group, their term columns lined up across the lines (0610 p4: the
    浮力 of the high, normal and low water levels); each keeps its word (the Equation's label) on its own first line,
    in a label column GridLayoutPdf shares across a run."""
    result, has_unit = _columns(run[0].value.equation)
    return equation_group(
        *(replace(piece.value.equation, label=piece.value.label, block_id=piece.key) for piece in run),
        left=LABEL_LEFT, first_equal=FIRST_EQUAL,
        second_equal=SECOND_EQUAL if result else None, result_right=RESULT_RIGHT if result else None,
        unit_start=UNIT_START if has_unit else None, block_id=run[0].key,
        keep=tuple(piece.keep for piece in run))


def _title_of(piece: Unit | None, following: Unit | None) -> bool:
    """A kept paragraph directly before a table or figure is its title (as the 0500 table caption)."""
    return (piece is not None and following is not None and piece.kind == "paragraph" and piece.keep
            and following.kind in _FLOATS)


def blocks(units: Sequence[Unit]) -> list[Block]:
    """A heading, table or figure (with its title) has one blank line before and after it, and a
    lead-in line (a kept paragraph, "・橋脚天端に作用する荷重") opens its group with one blank line before it
    (0610 p4); blank lines never stack."""
    found: list[Block] = []
    index = 0
    while index < len(units):
        piece = units[index]
        previous = units[index - 1] if index else None
        index += 1
        if piece.kind == "heading":
            text, tag = piece.value if isinstance(piece.value, tuple) else (piece.value, None)
            blank(found)
            found.append(heading(text, left=piece.left, tag=tag, block_id=piece.key))
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
            block = definitions(*piece.value.items, left=LABEL_LEFT, colon=piece.value.colon or DEFINITION_COLON,
                                block_id=piece.key)
        elif piece.kind == "table":
            block = PreferKeepTogether(table_block(piece.value, piece.key))
        else:  # a figure
            block = indent_to(piece.value.block, piece.left)
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
    girders = {NodeRole.GIRDER_ORIGIN, NodeRole.GIRDER_END}
    for node in frame.nodes:
        names = "・".join(name + ("（ばね）" if springs and role is NodeRole.FOOTING_BOTTOM else "")
                         for role, name in _ROLE_NAMES.items() if role in node.roles)
        if NodeRole.CONTROL in node.roles and not girders <= node.roles:
            # decision 65: girders at different heights; the control node is named (with both girders it is the
            # common girder level, Example2 node 1)
            names = "・".join(filter(None, (names, "制御節点")))
        rows.append((str(node.number), value(node.x), value(node.y), names))
    return TableSpec((4, 5, 5, 13), tuple(rows), (1,) * len(rows), numeric=frozenset({0, 1, 2}))


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
    # 水平距離 (m) and f'ck (N/mm2) take five columns and the longest 部位 (フーチング天端～重心) seven: the body's 30.
    return TableSpec((3, 2, 2, 3, 5, 7, 3, 5), tuple(rows), (1,) * len(rows), numeric=frozenset({0, 1, 2, 3, 4, 7}),
                     left=0)


def spring_table(frame: Frame) -> TableSpec:
    long_term, short_term = frame.support.long_term, frame.support.short_term
    rows = [(Span("", rowspan=2), Span("記号", rowspan=2), Span("安定計算時", colspan=2), Span("単位", rowspan=2)),
            ("長期", "短期")]
    for name, symbol, field_name in (("鉛直ばね", sub("K", "v"), "kv"), ("せん断ばね", sub("K", "s"), "ks"),
                                     ("回転ばね", sub("K", "r"), "kr")):
        a, b = getattr(long_term, field_name), getattr(short_term, field_name)
        rows.append((name, Span(symbol), value(a, thousands=True), value(b, thousands=True), Span(unit(a.unit))))
    return TableSpec((5, 3, 7, 7, 5), tuple(rows), (1,) * len(rows), header_rows=2,
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
    # The note is one line of 28 columns (447 pt): from the item column it ends within the body.
    m.line(key + ".table", Row("（表の f'ck = ", with_unit(low.strength), " で Ec = ", with_unit(low.modulus),
                               "，f'ck = ", with_unit(high.strength), " で Ec = ", with_unit(high.modulus),
                               " から直線補間）", gap=0), left=LEVELS[2])


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
    return TableSpec((7, 6, 6, 7), tuple(body), (1,) * len(body), numeric=frozenset({1, 2, 3}),
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
    # "ここに、Δh" is 65 pt: its "：" one column right of DEFINITION_COLON's.
    m.definitions("fixed.overlap.note", Definition("Δh", "はりの高さ ＋ ハンチの高さ（柱の q と重なる長さ）"),
                  colon=DEFINITION_COLON + 1)


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
    soil = footing.soil
    if len(soil.parts) == 1:
        m.definitions("inertia.footing.note", Definition("V", f"フーチングの体積（{chapter}）"),
                      Definition("γ'", f"排除した土（{soil.parts[0][0].name}）の湿潤単位体積重量"))
        return
    # Decision 64: the layers within the footing height H5 + H6, averaged by their thickness.
    m.definitions("inertia.footing.note", Definition("V", f"フーチングの体積（{chapter}）"),
                  # 36 characters: the note goes on to a line of its own when the line from the "：" holds less
                  Definition("γ'", Row("排除した土の湿潤単位体積重量", BreakHint(),
                                       "（フーチング高さの範囲の層の厚さによる平均）", gap=0)))
    parts: list = []
    for layer, part in soil.parts:
        parts += [*(("+",) if parts else ()), value(part), "×", value(layer.unit_weight_wet)]
    m.equation("inertia.footing.displaced", "", "γ'", terms("(", *parts, ")", "/", value(soil.height)),
               footing.displaced)


# --- combinations (8.4 / 9.4) -----------------------------------------------------------------------------


@dataclass(frozen=True)
class TableParts:
    """The tables *specs* one under another with a blank line between them (``<block_id>.<n>``); the page may break
    between two of them only.

    Each table is a part of its own, measured as a child of a Stack numbered by the empty children before it, so that
    the grid Excel tells the tables apart by the path of their commands; every part lists the children of all
    tables, as the one part of a Stack would (as equations._GridEquations does with its runs).
    """

    specs: tuple[TableSpec, ...]
    block_id: str

    def measure(self, context: LayoutContext, available_width: float) -> MeasuredBlock:
        parts, children, offset = [], [], 0
        for number, spec in enumerate(self.specs):
            block = table_block(spec, f"{self.block_id}.{number}")
            own = (block, *((Spacer(1),) if number < len(self.specs) - 1 else ()))
            stack = Stack(*(Spacer(0),) * offset, *own, block_id=self.block_id)
            (part,) = measure_block(stack, context, available_width).parts
            parts.append(part)
            children += part.metadata["children"][offset:offset + len(own)]
            offset += len(own)
        parts = [replace(part, metadata={**part.metadata, "children": tuple(children)}) for part in parts]
        return MeasuredBlock(available_width, context.profile.grid.pitch_y, tuple(parts),
                             break_after=tuple(range(1, len(parts))), block_id=self.block_id)


# The coefficient table (8-10, 9-14): No, 記号 and 荷重名称 in 1 + 4 + 5 columns from the body's left edge, then two
# columns a combination (a coefficient "1.35" does not fit one). The combinations beyond the body's 30 columns go on in
# a table of its own below, with the cases again (Example2's 23 pt columns are not on the grid).
_CASE_COLUMNS = (1, 4, 5)
_COMBINATION_COLUMNS = 2


def _coefficient_spec(headers: Sequence[tuple[str, str, str]], numbers: Sequence[int],
                      rows: Sequence[tuple[str, Any, str, Sequence[Printed | None]]]) -> TableSpec:
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
    widths = (*_CASE_COLUMNS, *(_COMBINATION_COLUMNS,) * len(headers))
    heights = (2, 1, 3, 1) + (1,) * len(body)
    return TableSpec(widths, (*(tuple(row) for row in header), *body), heights, header_rows=4,
                     numeric=frozenset({0, *range(3, 3 + len(headers))}), left=0)


def _coefficient_runs(headers: Sequence[tuple[str, str, str]], capacity: int) -> list[list[int]]:
    """The combinations of each table: at most *capacity*, cut where the requirement changes unless one
    requirement has more combinations than a table holds."""
    groups, start = [], 0
    for index in range(1, len(headers) + 1):
        if index == len(headers) or headers[index][0] != headers[index - 1][0]:
            groups.append(range(start, index))
            start = index
    runs: list[list[int]] = []
    for group in groups:
        for begin in range(group.start, group.stop, capacity):
            piece = list(range(begin, min(begin + capacity, group.stop)))
            if runs and len(runs[-1]) + len(piece) <= capacity:
                runs[-1] += piece
            else:
                runs.append(piece)
    return runs


def coefficient_table(headers: Sequence[tuple[str, str, str]], numbers: Sequence[int],
                      rows: Sequence[tuple[str, Any, str, Sequence[Printed | None]]], *, block_id: str) -> FigureSpec:
    """Cases as rows, combinations as columns, the coefficients as printed (8-10, 9-14).

    *headers* gives each combination its requirement, performance item and remark; neighbours with the
    same text share a header cell. A missing coefficient prints '－'. The table is printed in parts of as many
    combinations as the body holds (``_COMBINATION_COLUMNS`` each); its record is the whole table's text.
    """
    capacity = (BODY_COLUMNS - sum(_CASE_COLUMNS)) // _COMBINATION_COLUMNS
    specs = tuple(_coefficient_spec([headers[index] for index in run], [numbers[index] for index in run],
                                    [(*row[:3], [row[3][index] for index in run]) for row in rows])
                  for run in _coefficient_runs(headers, capacity))
    return FigureSpec(TableParts(specs, block_id), (plain(_coefficient_spec(headers, numbers, rows)),))


def factor_lines(m: Manuscript, factors: Any, train: Any, maximum: Any, service_impact: Any) -> None:
    """ρ as entered and as printed in the table, 1.1ρ and 0.75ρ (8-10, 9-14)."""
    m.equation("factors.ultimate", "安全性・復旧性", "ρ", value(train.factor_ultimate), factors.ultimate,
               result_relation="≒")
    m.equation("factors.maximum", "列車最大", "1.1ρ", terms(maximum, "×", value(train.factor_ultimate)),
               factors.maximum)
    m.equation("factors.service", "使用性", "ρ", value(train.factor_service), factors.service, result_relation="≒")
    m.equation("factors.service_impact", "使用性の衝撃", "0.75ρ",
               terms(service_impact, "×", value(train.factor_service)), factors.service_impact)


EXTRACTION_NAMES = ("安全性（破壊）", "永久＋変動", "永久作用", "変動作用", "使用性（損傷）", "安全性（安定）",
                    "長期支持性能", "短期支持性能")


def extraction_table(m: Manuscript, extractions: Sequence[Any]) -> None:
    width = max(len(extraction.combinations) for extraction in extractions)
    rows: list[tuple[Any, ...]] = [("No", "名称", *(f"C{index}" for index in range(1, width + 1)))]
    for extraction in extractions:
        numbers = [str(number) for number in extraction.combinations]
        rows.append((str(extraction.number), EXTRACTION_NAMES[extraction.group.value - 1], *numbers,
                     *[""] * (width - len(numbers))))
    m.table("extraction", TableSpec((2, 7, *(2,) * width), tuple(rows), (1,) * len(rows),
                                    numeric=frozenset({0, *range(2, 2 + width)})))


def bearing_symbol(side: str) -> MathNode:
    return Row("起点側　" if side == "origin" else "終点側　", sub("R", "B" if side == "origin" else "C"), gap=0)


def frame_figure(frame: Frame, outline: Any, **options: Any) -> FigureSpec:
    """The model figure across the body's 30 columns (``FrameFigure``'s default size), from column 0."""
    figure = FrameFigure(frame, outline, **options)
    return FigureSpec(figure, figure.texts())


__all__ = [
    "BODY_LEFT", "Definitions", "FigureSpec", "LEVELS", "Labelled", "Manuscript", "Span",
    "TableSpec", "Unit", "bearing_symbol", "document",
    "frame_figure", "material_lines", "member_table", "node_table", "operand", "plain", "section_lines",
    "seat_moment", "semantic_records", "spring_table", "sub", "sup", "top_table", "used_concretes", "value",
    "with_unit",
]
