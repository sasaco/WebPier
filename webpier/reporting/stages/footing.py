"""0800 フーチングの応答値: 12.1 応答値の算定 (decision 60), (1) 線路方向 and (2) 線路直角方向.

WebPier lays out every page from calc.footing's result, as 12_フーチング.pdf 244〜253: 1) the table of the five design
columns (the actions at the footing base, 0612's bearing capacity, the shape of the base pressure Case 1〜4 with the
figure of the four shapes), 2) the effective width of the lower side with its figure, 3) the base reaction on the
chosen overhang (one row per segment of the pressure profile), 4) the self weight and overburden and 5) the buoyancy
of that overhang (every overhang the columns chose, each named when there are two), 6) the design moment and 7) the
design shear per metre with the shear span. The chapter heading (§12) and 12.1 are not printed (decision 60): the
first heading is (1) 線路方向の計算. Every number is a Printed value of the result (ADR-0003); nothing is calculated
here.

Written differently from the sample (decision 60; as 0612, decision 54): the rows of the second axis (ey, L′) and of
the cohesive soils (c, Nc, frc and their term) are not printed (the sandy equation applies, in the plane of the
frame), Be has a row, q2 of a uniform block is blank, the seismic buoyancy is the normal water in 6) and 7) alike,
and La is printed to 3 decimals. "せん断力ト" of the sample is corrected. The tables of a part the input does not choose
are not printed (decision 110): without the frame analyses only the 地震時 tables, without the nonlinear analyses only
the others.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from itertools import groupby
from pathlib import Path
from typing import Any
import unicodedata

from gridlayoutpdf import Document

from ...calc.footing import EffectiveWidth, FootingColumn, FootingDirection, FootingResult, OverhangSide, WeightRow
from ...calc.foundation_check import Basis
from ...core.printed import Printed
from ..styles import BODY_COLUMNS, columns_for
from ..tables import CELL_PADDING
from .footing_figures import cases_figure, reaction_figure, weight_figure, width_figure
from .frame_report import (
    FigureSpec, Manuscript, Span, TableParts, TableSpec, Unit, document, plain, semantic_records, value,
)

PREFIX = "0800/"
# Widths in grid columns, heights in grid rows. The tables stand from body column 1 (left of the body, as 0612) so that
# the widest, 1) with the label, the symbol and four design columns, ends at the body's right edge (column 30).
TABLE_LEFT = 1
LABEL = (6, 10)  # the label (設計最大地盤反力度) and the symbol (frγ・Iγ・βb・Be・γe1・Nγ) columns of 1)
COLUMN = 3  # one design column of 1), at least: wider when a value needs it (Mmd 109235.91 of P7橋脚)
HALF_WIDTH = 5.0  # pt: a half-width character of the 10 pt body (a full-width one is twice)
REACTION = (3, 4, 4, 4, 3, 4, 3, 4)  # 3): the limit, the column, q1, q2, L1, W, x, M
WEIGHT = (2, 7, 3, 3, 4, 3, 4)  # 4): the part, the formula, V, γ, W, x, M
BUOYANCY = (3, 6, 3, 3, 4, 3, 4)  # 5): the water level, then as 4)
WIDE_LABEL = 15  # the one label column of 6) and 7) (フーチング自重と上載土によるモーメント (kN・m))
NARROW = 3  # one design column of 6) and 7)
LEADING = 1
HEADER = 2  # a two-line header row
BLANK = ""
SEISMIC = "地震時"
DIRECTIONS = (("longitudinal", "(1) 線路方向の計算"), ("transverse", "(2) 線路直角方向の計算"))

Row = tuple[Any, ...]
Cell = Callable[[FootingColumn], str]


def _title(column: FootingColumn) -> str:
    return f"{column.limit}\n{column.detail}" if column.detail else column.limit


def _heights(rows: Sequence[Row]) -> tuple[int, ...]:
    return (HEADER, *(LEADING,) * (len(rows) - 1))


# --- 1) 設計鉛直地盤反力度の算定 --------------------------------------------------------------------------------------


def _number(path: str) -> Cell:
    """The printed attribute at *path* of a column ("capacity.ex")."""
    def cell(column: FootingColumn) -> str:
        item: Any = column
        for name in path.split("."):
            item = getattr(item, name)
        return value(item)
    return cell


def _constant(item: Printed) -> Cell:
    return lambda column: value(item)


def _pressure_groups(basis: Basis) -> list[tuple[str, list[tuple[str, Cell]]]]:
    return [
        ("基礎底面中心に\n作用する断面力", [("Vd (kN)", _number("vd")), ("Hd (kN)", _number("hd")),
                                            ("Md (kN・m)", _number("md"))]),
        ("合力の位置", [("ex = Md / Vd (m)", _number("capacity.ex"))]),
        ("フーチング形状", [("B (m)", _constant(basis.b)), ("L (m)", _constant(basis.l))]),
        ("有効幅", [("B′ = B − 2・ex (m)", _number("capacity.b_effective"))]),
        ("有効面積", [("A′ = B′・L (m2)", _number("capacity.area_effective"))]),
        ("有効根入れ", [("Df (m)", _constant(basis.depth))]),
        ("内部摩擦角", [("φ (度)", _constant(basis.friction_angle))]),
        ("荷重傾斜角", [("δ = tan⁻¹(Hd / Vd) (度)", _number("capacity.delta"))]),
        ("土の有効\n単位体積重量", [("γe1 (kN/m3)", _constant(basis.gamma_e1)),
                                    ("γe2 (kN/m3)", _number("capacity.gamma_e2"))]),
        ("傾斜荷重\n補正係数", [("Iγ = (1 − δ / φ)²", _number("capacity.i_gamma")),
                              ("Iq = (1 − δ / 90)²", _number("capacity.i_q"))]),
        ("形状係数", [("αb = 1.0 + 0.2・B′ / L", _number("alpha_b")), ("βb = 0.5 − 0.2・B′ / L", _number("capacity.beta_b"))]),
        ("載荷幅", [("Be (m)", _number("capacity.b_e"))]),
        ("支持力係数", [("Nγ", _constant(basis.n_gamma)), ("Nq", _constant(basis.n_q))]),
        ("地盤抵抗係数", [("frγ", _number("factors.f_gamma")), ("frq", _number("factors.f_q"))]),
        ("極限支持力度", [("frγ・Iγ・βb・Be・γe1・Nγ", _number("capacity.term_gamma")),
                         ("frq・Iq・γe2・Df・(Nq − 1)", _number("capacity.term_q")), ("qvd (kN/m2)", _number("capacity.qvd"))]),
        ("設計鉛直支持力度", [("qd = qvd + γe2・Df (kN/m2)", _number("capacity.qd_unlimited"))]),
        ("設計最大地盤反力度", [("qd1 (kN/m2)", _number("distribution.apex"))]),
        ("最大抵抗モーメント", [("Mmd (kN・m)", _number("capacity.mmd"))]),
        ("設計地盤反力度", [("qd1 (kN/m2)", _number("distribution.qd1")), ("qd2 (kN/m2)", _number("distribution.qd2"))]),
        ("地盤反力の\n載荷幅", [("X1 (m)", _number("distribution.x1")), ("X2 (m)", _number("distribution.x2"))]),
    ]


def _text_width(text: str) -> float:
    return sum(2 * HALF_WIDTH if unicodedata.east_asian_width(c) in "FWA" else HALF_WIDTH for c in text)


def _column_width(columns: Sequence[FootingColumn], basis: Basis) -> int:
    """The grid columns of a design column of 1): COLUMN, or as many as its widest value needs (the characters are
    never shrunk)."""
    texts = [cell(column) for _, lines in _pressure_groups(basis) for _, cell in lines for column in columns]
    widest = max((_text_width(text) for text in texts), default=0.0)
    return max(COLUMN, columns_for(widest + CELL_PADDING.left + CELL_PADDING.right))


def _pressure(m: Manuscript, key: str, columns: Sequence[FootingColumn], basis: Basis) -> None:
    """The table of 1); when its design columns are too wide for the body's 30 columns, one table a limit state
    (安全性, 使用性) one under another, as the combination tables of 0610 (TableParts)."""
    width = _column_width(columns, basis)
    if TABLE_LEFT + sum(LABEL) + width * len(columns) <= BODY_COLUMNS:
        m.table(key, _pressure_table(columns, basis, width))
        return
    runs = [tuple(run) for _, run in groupby(columns, key=lambda column: column.limit)]
    specs = tuple(_pressure_table(run, basis, width) for run in runs)
    m.figure(key, FigureSpec(TableParts(specs, m.prefix + key), tuple(plain(spec) for spec in specs)))


def _pressure_table(columns: Sequence[FootingColumn], basis: Basis, width: int = COLUMN) -> TableSpec:
    rows: list[Row] = [(Span(BLANK, colspan=2), *(_title(column) for column in columns))]
    groups = _pressure_groups(basis)
    for label, lines in groups[:-2]:
        for index, (symbol, cell) in enumerate(lines):
            name = (Span(label, rowspan=len(lines)),) if index == 0 else ()
            rows.append((*name, Span(symbol, align="left"), *(Span(cell(column), align="right") for column in columns)))
    rows.append((Span("地盤反力形状", colspan=2), *(Span(f"Case {column.distribution.case}") for column in columns)))
    for label, lines in groups[-2:]:
        for index, (symbol, cell) in enumerate(lines):
            name = (Span(label, rowspan=len(lines)),) if index == 0 else ()
            rows.append((*name, Span(symbol, align="left"), *(Span(cell(column), align="right") for column in columns)))
    return TableSpec((*LABEL, *(width,) * len(columns)), tuple(rows), _heights(rows), left=TABLE_LEFT)


# --- 3) 地盤反力による断面力 ------------------------------------------------------------------------------------------


def _reaction_table(found: FootingDirection) -> TableSpec:
    rows: list[Row] = [(Span(BLANK, colspan=2), "q1\n(kN/m2)", "q2\n(kN/m2)", "L1\n(m)", "W\n(kN/m)", "x\n(m)",
                        "M = W・x\n(kN・m/m)")]
    limits = {column.limit: sum(len(column.sides[column.chosen].segments) for column in found.columns
                                if column.limit == limit) for column in found.columns for limit in (column.limit,)}
    named: set[str] = set()
    for column in found.columns:
        segments = column.sides[column.chosen].segments
        for index, segment in enumerate(segments):
            name: tuple = ()
            if column.limit not in named:
                name = (Span(column.limit, rowspan=limits[column.limit]),)
                named.add(column.limit)
            detail = (Span(column.detail, rowspan=len(segments)),) if index == 0 else ()
            cells = (value(segment.q1), BLANK if segment.uniform else value(segment.q2), value(segment.length),
                     value(segment.w), value(segment.x), value(segment.m))
            rows.append((*name, *detail, *(Span(text, align="right") for text in cells)))
    return TableSpec(REACTION, tuple(rows), _heights(rows), left=TABLE_LEFT)


# --- 4) 自重・上載土, 5) 浮力 ------------------------------------------------------------------------------------------


def _product(row: WeightRow) -> str:
    return f"{value(row.height)} × {value(row.length)}"


def _weight_row(row: WeightRow) -> tuple[str, ...]:
    return (_product(row), value(row.volume), value(row.unit_weight), value(row.w), value(row.x), value(row.m))


def _weight_table(side: OverhangSide) -> TableSpec:
    weight = side.weight
    rows: list[Row] = [(BLANK, "計　算　式", "V\n(m3)", "γ\n(kN/m3)", "W\n(kN)", "x\n(m)", "M = W・x\n(kN・m)"),
                       (Span("①"), *_weight_row(weight.overburden)), (Span("②"), *_weight_row(weight.footing)),
                       (Span("合　　計", colspan=2), Span("－"), Span("－"), Span(value(weight.w), align="right"), BLANK,
                        Span(value(weight.m), align="right"))]
    return TableSpec(WEIGHT, tuple(rows), _heights(rows), numeric=frozenset(range(2, 7)), left=TABLE_LEFT)


def _buoyancy_table(side: OverhangSide) -> TableSpec:
    rows: list[Row] = [(BLANK, "計　算　式", "V\n(m3)", "γ\n(kN/m3)", "W\n(kN)", "x\n(m)", "M = W・x\n(kN・m)")]
    for label, row in (("高水位", side.water.high), ("平水位", side.water.normal), ("低水位", side.water.low)):
        rows.append((Span(label), *_weight_row(row)))
    return TableSpec(BUOYANCY, tuple(rows), _heights(rows), numeric=frozenset(range(2, 7)), left=TABLE_LEFT)


# --- 6) 設計曲げモーメント, 7) 発生せん断力 -----------------------------------------------------------------------------


Force = Callable[[FootingColumn], Printed]


def _moment_rows(width: EffectiveWidth) -> list[tuple[str, Force]]:
    return [("地盤反力による曲げモーメント (kN・m/m)", lambda column: column.forces.m_reaction),
            (f"全幅当り B = {value(width.full)} m", lambda column: column.forces.m_full),
            (f"1 m当たりモーメント (kN・m) Be = {value(width.be)} m", lambda column: column.forces.m_per_m),
            ("フーチング自重と上載土によるモーメント (kN・m)", lambda column: column.forces.m_self),
            ("浮力によるモーメント (kN・m)", lambda column: column.forces.m_buoyancy),
            ("設計曲げモーメント Md (kN・m)", lambda column: column.forces.md)]


def _shear_rows(width: EffectiveWidth) -> list[tuple[str, Force]]:
    return [("地盤反力によるせん断力 (kN/m)", lambda column: column.forces.v_reaction),
            (f"全幅当り B = {value(width.full)} m", lambda column: column.forces.v_full),
            (f"1 m当たりせん断力 (kN) Be = {value(width.be)} m", lambda column: column.forces.v_per_m),
            ("フーチング自重と上載土によるせん断力 (kN)", lambda column: column.forces.v_self),
            ("浮力によるせん断力 (kN)", lambda column: column.forces.v_buoyancy),
            ("設計せん断力 Vd (kN)", lambda column: column.forces.vd),
            ("せん断スパン La = Md / Vd (m)", lambda column: column.forces.la)]


def _force_table(columns: Sequence[FootingColumn], lines: list[tuple[str, Force]]) -> TableSpec:
    rows: list[Row] = [(BLANK, *(_title(column) for column in columns))]
    for label, pick in lines:
        rows.append((Span(label, align="left"), *(value(pick(column)) for column in columns)))
    return TableSpec((WIDE_LABEL, *(NARROW,) * len(columns)), tuple(rows), _heights(rows),
                     numeric=frozenset(range(1, len(columns) + 1)), left=TABLE_LEFT)


# --- the manuscript ---------------------------------------------------------------------------------------------------


def _sides(found: FootingDirection) -> tuple[OverhangSide, ...]:
    """The overhangs the columns chose, in the order of the basis."""
    return tuple(found.basis.sides[index] for index in sorted({column.chosen for column in found.columns}))


def _direction(m: Manuscript, key: str, title: str, found: FootingDirection) -> None:
    basis, width = found.basis, found.basis.width
    seismic = tuple(column for column in found.columns if column.limit == SEISMIC)
    others = tuple(column for column in found.columns if column.limit != SEISMIC)
    sides = _sides(found)

    def lead(part: str, side: OverhangSide) -> None:
        if len(sides) > 1:
            m.paragraph(f"{key}.{part}.{side.name}.lead", f"・{side.name}", keep=True)

    m.heading(f"{key}.heading", title, 2)
    m.heading(f"{key}.pressure.heading", "1) 設計鉛直地盤反力度の算定", 3)
    for part, columns in (("", others), (".seismic", seismic)):
        if columns:
            _pressure(m, f"{key}.pressure{part}.table", columns, basis.check)
    m.figure(f"{key}.pressure.cases.figure", cases_figure(m.prefix + f"{key}.pressure.cases.figure"))
    m.heading(f"{key}.width.heading", "2) 有効幅", 3, tag="【ＲＣ標準 13.6.3】")
    m.paragraph(f"{key}.width.side", "下　側", keep=True)
    m.figure(f"{key}.width.figure", width_figure(m.prefix + f"{key}.width.figure", width))
    m.line(f"{key}.width.line", f"be = {value(width.left_effective)} + {value(width.column)} + "
                                f"{value(width.right_effective)} = {value(width.be)} m ≦ {value(width.full)} m")
    m.heading(f"{key}.reaction.heading", "3) 地盤反力による断面力", 3)
    for side in sides:
        lead("reaction", side)
        m.figure(f"{key}.reaction.{side.name}.figure",
                 reaction_figure(m.prefix + f"{key}.reaction.{side.name}.figure", side, width.height))
    m.table(f"{key}.reaction.table", _reaction_table(found))
    m.heading(f"{key}.weight.heading", "4) フーチング自重および上載土による断面力", 3)
    for side in sides:
        lead("weight", side)
        m.figure(f"{key}.weight.{side.name}.figure",
                 weight_figure(m.prefix + f"{key}.weight.{side.name}.figure", side, width.height))
        m.table(f"{key}.weight.{side.name}.table", _weight_table(side))
    m.heading(f"{key}.buoyancy.heading", "5) 浮力による断面力", 3)
    for side in sides:
        lead("buoyancy", side)
        m.table(f"{key}.buoyancy.{side.name}.table", _buoyancy_table(side))
    m.heading(f"{key}.moment.heading", "6) 設計曲げモーメント", 3)
    for part, columns in (("", others), (".seismic", seismic)):
        if columns:
            m.table(f"{key}.moment{part}.table", _force_table(columns, _moment_rows(width)))
    m.paragraph(f"{key}.moment.tension", "よって、下側引張となる。")
    m.heading(f"{key}.shear.heading", "7) 発生せん断力", 3)
    for part, columns in (("", others), (".seismic", seismic)):
        if columns:
            m.table(f"{key}.shear{part}.table", _force_table(columns, _shear_rows(width)))


def content(result: FootingResult) -> tuple[Unit, ...]:
    """The ordered manuscript of both directions, used by both the layout and the semantic tests."""
    m = Manuscript(PREFIX)
    for key, title in DIRECTIONS:
        _direction(m, key, title, getattr(result, key))
    return tuple(m.units)


def records(result: FootingResult) -> list[dict[str, str]]:
    return semantic_records(content(result))


def build_footing(result: FootingResult) -> Document:
    return document(content(result))


def render_footing(result: FootingResult, path: str | Path) -> Path:
    """Lay out completely, then atomically replace *path*; the same result gives the same bytes."""
    return build_footing(result).render(path, invariant=True)


def grid_documents(result: FootingResult) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out (its grid Excel workbook): the whole report."""
    return (build_footing(result),)
