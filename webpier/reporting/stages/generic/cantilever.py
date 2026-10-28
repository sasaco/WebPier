"""0900 with a load model (decision 70): the report of a GenericCantileverResult.

§13. 片持ち梁の照査 (decision 117, as the train path's), then 13.1 応答値の算定: the load model's sections, the 最大応答震度 of 0711 and 0721, and for each cantilever its self weight
and the table of each action (the train path's tables, reporting.stages.cantilever.summary); 13.2 設計作用の組合せ:
for each cantilever the factored actions of each combination of the load model and their sums, then the governing
case of either side for each row of Capacita's force table and each check, a row without a combination printed
該当する組合せなし（断面力0）. Every number is a Printed value of the result; nothing is calculated here.
"""

from __future__ import annotations

from pathlib import Path

from gridlayoutpdf import Document

from ....calc.cantilever.geometry import Side
from ....calc.generic.cantilever import NO_COMBINATION, GenericCantileverResult, GenericSide
from ....inputs import PierInput
from ....loadmodel import D1, D2, Paragraph, Section
from ...numbers import printed
from ..cantilever import CHAPTER_TITLE, SIDES
from ..cantilever.summary import _action_table, _self_weight_table
from ..reaction.layout import document
from ..reaction.manuscript import (
    CHAPTER, ITEM, SECTION, SUBSECTION, CellSpec, Manuscript, TableSpec, Unit, cells, plain,
)
from ..reaction.tables import header

PREFIX = "0900/"
ZERO = "－"  # the side and the case of a row without a combination, in the table of the governing cases
LOADMODEL_COLUMNS = 26  # the grid columns a table of the load model's sections spreads its columns over


def _sections(m: Manuscript, items: tuple[Section, ...]) -> None:
    if not items:
        return
    m.heading("loadmodel.heading", "(1) 荷重モデルの作用の根拠", SUBSECTION)
    for number, section in enumerate(items, 1):
        m.heading(f"loadmodel.{number}.heading", f"{number}) {section.title}", ITEM)
        for index, block in enumerate(section.blocks, 1):
            where = f"loadmodel.{number}.{index}"
            if isinstance(block, Paragraph):
                m.paragraph(where, block.text, gap=True)
            else:
                width = LOADMODEL_COLUMNS // len(block.columns)
                rows = (header(*block.columns), *(tuple(CellSpec(text, align="left") for text in row)
                                                   for row in block.rows))
                m.table(where, TableSpec((width,) * len(block.columns), tuple(rows), header_rows=1), SUBSECTION)


def _responses(m: Manuscript, result: GenericCantileverResult, number: int) -> None:
    m.heading("response.heading", f"({number}) 最大応答震度", SUBSECTION)
    for key, label, response in (("longitudinal", "線路方向（0711）", result.longitudinal),
                                 ("transverse", "線路直角方向（0721）", result.transverse)):
        m.paragraph(f"response.{key}", f"{label}　Khmax = {printed(response.kh)}（{response.adopted.name}，"
                                       f"{response.adopted.block}）", gap=True)


def _actions(m: Manuscript, side: Side, result: GenericSide, number: int) -> None:
    key, name = side.name.lower(), SIDES[side]
    m.heading(f"{key}.weight.heading", f"({number}) 片持梁の自重（{name}）", SUBSECTION)
    m.paragraph(f"{key}.weight.section", "設計断面：柱前面", gap=True)
    m.table(f"{key}.weight.table", _self_weight_table(result), SUBSECTION)  # type: ignore[arg-type]
    m.heading(f"{key}.actions.heading", f"({number + 1}) 荷重設計の集計（{name}）", SUBSECTION)
    for index, action in enumerate(result.actions, 1):
        title = action.title if action.key.kind in (D1, D2) else f"{action.title}（{action.key.kind}）"
        m.heading(f"{key}.actions.{action.key.kind}.heading", f"{index}) {title}", ITEM)
        m.table(f"{key}.actions.{action.key.kind}.table", _action_table(action), SUBSECTION)


def _combinations(m: Manuscript, side: Side, result: GenericSide) -> None:
    key, name = side.name.lower(), SIDES[side]
    m.heading(f"{key}.combinations.heading", f"13.2 設計作用の組合せ（{name}）", SECTION)
    rows = [header("Case", "組合せ", "基本ケース", "係数", "Md\n(kN・m)", "Vd\n(kN)", "Mt\n(kN・m)")]
    for case in result.cases:
        for index, part in enumerate(case.contributions):
            lead = (CellSpec(str(case.number), align="center"), CellSpec(case.name, align="left")) if not index else (
                CellSpec("", align="center"), CellSpec("", align="left"))
            rows.append((*lead, CellSpec(part.column, align="left"), CellSpec(part.factor, align="right"),
                         *cells(part.md, part.n, part.mt)))
        rows.append((CellSpec("", align="center"), CellSpec("", align="left"), CellSpec("合計", align="left"),
                     CellSpec("", align="right"), *cells(case.md, case.n, case.mt)))
    m.table(f"{key}.combinations.table", TableSpec((2, 7, 5, 3, 3, 3, 3), tuple(rows), header_rows=1,
                                                   numeric_columns=(3, 4, 5, 6)), SUBSECTION)


def _adopted(m: Manuscript, result: GenericCantileverResult) -> None:
    m.heading("adopted.heading", "(3) 照査に用いる設計作用", SUBSECTION)
    rows = [header("照査", "項目", "側", "Case", "Md\n(kN・m)", "Vd\n(kN)", "Mt\n(kN・m)")]
    previous = None
    for selection in result.selections:
        title = "" if selection.title == previous else selection.title
        previous = selection.title
        zero = selection.case.name == NO_COMBINATION
        rows.append((CellSpec(title, align="left"), CellSpec(selection.quantity.value, align="center"),
                     CellSpec(ZERO if zero else SIDES[selection.side], align="center"),
                     CellSpec(ZERO if zero else str(selection.case.number), align="center"),
                     *cells(selection.md, selection.vd, selection.mt)))
    m.table("adopted.table", TableSpec((10, 3, 2, 2, 4, 3, 4), tuple(rows), header_rows=1, numeric_columns=(4, 5, 6)),
            SUBSECTION)
    if any(selection.case.name == NO_COMBINATION for selection in result.selections):
        m.paragraph("adopted.zero", f"{ZERO}：{NO_COMBINATION}．Capacita はその照査を省略する．", gap=True)


def content(result: GenericCantileverResult, pier: PierInput) -> tuple[Unit, ...]:
    """One ordered manuscript, used by both the layout and the semantic tests."""
    m = Manuscript(prefix=PREFIX)
    m.heading("title", CHAPTER_TITLE, CHAPTER)
    m.heading("section.heading", "13.1 応答値の算定", SECTION)
    sections = result.basis.sections
    _sections(m, sections)
    number = 2 if sections else 1
    _responses(m, result, number)
    for side, side_result in result.sides.items():
        _actions(m, side, side_result, number + 1)
    for side, side_result in result.sides.items():
        _combinations(m, side, side_result)
    _adopted(m, result)
    return tuple(m.units)


def semantic_records(result: GenericCantileverResult, pier: PierInput) -> list[dict[str, str]]:
    return [{"id": unit.identifier, "text": plain(unit.value)} for unit in content(result, pier)]


def build_generic_cantilever(result: GenericCantileverResult, pier: PierInput) -> Document:
    return document(content(result, pier))


def render_generic_cantilever(result: GenericCantileverResult, pier: PierInput, path: str | Path) -> Path:
    """Lay out completely, then atomically replace *path*; the same input gives the same bytes."""
    return build_generic_cantilever(result, pier).render(path, invariant=True)


def grid_documents(result: GenericCantileverResult, pier: PierInput) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out (its grid Excel workbook): the whole report."""
    return (build_generic_cantilever(result, pier),)
