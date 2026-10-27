"""0800 フーチングの応答値 of a pile foundation: 12.1 (decision 96, Example橋脚4 第V編 2.3 (1)・(2)): the effective widths of
the sections of the footing and the design section forces of each, for each direction.

WebPier lays out every page from ``calc.pile_footing``'s result: for the direction, 1) the effective width of each point
(the rule, the quantities it takes, and the result with the footing width it is limited to), and 2) the design section
forces of each point by check (安全性（破壊）, 耐久性の 永久＋変動 and 永久, 復旧性（地震時）): where on the footing they are read
(the side of the column, the member and its end), the combination, the bending moment (a lower tension positive, an upper
tension negative) and, at the points of the deep beam shear, the shear force; those of 安全性（破壊） are the frame's times
the 応答値係数 γR, which the section says (decision 104). Every number is a ``Printed`` value (ADR-0003); nothing is
calculated here. The chapter heading (§12) and 12.1 are not printed, as the direct footing's.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document

from ...calc.pile_body import GAMMA_R
from ...calc.pile_footing import CASES, Case, End, FootingDirection, FootingResult, Force, SectionForces
from ..document import report
from .frame_report import Manuscript, Span, TableSpec, Unit, blocks, value

PREFIX = "0800/"
TABLE_LEFT = 1
WIDTH_COLUMNS = (10, 9, 6, 4)  # the point, the rule, the quantities, be
FORCE_COLUMNS = (5, 4, 5, 5, 5, 5)  # the label, the symbol and the four checks
DASH = "－"
DIRECTIONS = (("longitudinal", "(1) 線路方向の計算"), ("transverse", "(2) 線路直角方向の計算"))
CASE_TITLES = {Case.SAFETY: "安全性\n（破壊）", Case.SHORT_TERM: "耐久性\n永久＋変動", Case.LONG_TERM: "耐久性\n永久",
               Case.SEISMIC: "復旧性\n（地震時）"}

Row = tuple[Any, ...]


def _where(end: End) -> str:
    return f"{end.side}（部材{end.member}）"


def _width_table(direction: FootingDirection) -> TableSpec:
    rows: list[Row] = [tuple(Span(text, align="center") for text in ("照査位置", "算定式", "各量 (mm)", "be (mm)"))]
    heights = [1]
    for item in direction.points:
        width = item.point.width
        terms = "\n".join(f"{name} = {value(amount)}" for name, amount in width.terms)
        heights.append(len(width.terms))
        rows.append((Span(item.point.name if item.point.bending else f"{item.point.position}（せん断）", align="left"),
                     Span(f"{width.rule} ≦ B", align="left"), Span(terms, align="left"),
                     Span(value(width.be), align="right")))
    return TableSpec(WIDTH_COLUMNS, tuple(rows), tuple(heights), header_rows=1, left=TABLE_LEFT)


def _forces_table(forces: SectionForces) -> TableSpec:
    point = forces.point
    found = {force.case: force for force in forces.forces}
    cases = [case for case, _ in CASES]
    lines: list[tuple[str, str, Callable[[Force], str]]] = [
        ("着目端", "", lambda force: _where(force.end)),
        ("組合せ", "No", lambda force: str(force.md_combination)),
        ("設計断面力", "Md (kN・m)", lambda force: value(force.md))]
    rows: list[Row] = [(Span(point.name, colspan=2), *(Span(CASE_TITLES[case], align="center") for case in cases))]
    for label, symbol, cell in lines:
        if not point.bending:
            continue
        rows.append((Span(label, align="left"), Span(symbol, align="left"),
                     *(Span(cell(found[case]), align="right") for case in cases)))
    if point.deep_beam is not None:
        safety = found[Case.SAFETY]
        rows.append((Span("設計せん断力", align="left"), Span("Vd (kN)", align="left"),
                     *(Span(value(safety.vd) if case is Case.SAFETY else DASH, align="right") for case in cases)))
        rows.append((Span("組合せ", align="left"), Span("No", align="left"),
                     *(Span(str(safety.vd_combination) if case is Case.SAFETY else DASH, align="right")
                       for case in cases)))
        rows.append((Span("着目端", align="left"), Span("", align="left"),
                     *(Span(_where(safety.vd_end) if case is Case.SAFETY else DASH, align="right") for case in cases)))
    return TableSpec(FORCE_COLUMNS, tuple(rows), (2,) + (1,) * (len(rows) - 1), header_rows=1, left=TABLE_LEFT)


def _direction(m: Manuscript, key: str, title: str, direction: FootingDirection) -> None:
    m.heading(f"{key}.heading", title, 1)
    m.paragraph(f"{key}.width.title", "1) 有効幅", left=TABLE_LEFT, keep=True)
    m.table(f"{key}.width", _width_table(direction))
    m.paragraph(f"{key}.forces.title", "2) 設計断面力", left=TABLE_LEFT, keep=True)
    m.paragraph(f"{key}.forces.response", f"安全性（破壊）の設計断面力は，骨組解析の応答値に応答値係数γR（={value(GAMMA_R)}）を"
                "乗じたものとする．", left=TABLE_LEFT)
    for index, forces in enumerate(direction.points, 1):
        m.table(f"{key}.forces{index}", _forces_table(forces))


def content(result: FootingResult) -> tuple[Unit, ...]:
    """The ordered manuscript."""
    m = Manuscript(PREFIX)
    for attribute, title in DIRECTIONS:
        _direction(m, attribute, title, getattr(result, attribute))
    return tuple(m.units)


def _blocks(units: Sequence[Unit]) -> list:
    return blocks(list(units))


def build_pile_footing(result: FootingResult) -> Document:
    return report(*_blocks(content(result)))


def render_pile_footing(result: FootingResult, path: str | Path) -> Path:
    """Lay out completely, then atomically replace *path*; the same result gives the same bytes."""
    return build_pile_footing(result).render(path, invariant=True)


def grid_documents(result: FootingResult) -> tuple[Document, ...]:
    return (build_pile_footing(result),)
