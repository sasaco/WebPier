"""0612 線路方向の基礎の照査 (8.11) and 0622 直角方向の基礎の照査 (9.11) of a pile foundation (decision 89, Example橋脚4
III-3.3).

The section continues the column check of the same direction (n.5 to n.10) as n.11. It prints the checks of the
foundation's stability against the design limits SOIL-JR returned (the table of limits is its .sdr, as it printed them) and
the responses of the frame of 0610 / 0620: the pile head force Vd and the pull-out force Vud per pile, the horizontal
displacement and the rotation of the footing top. The pull-out check is a row of dashes when no pile head is in tension
(the sample omits it). Every number is a Printed value of the calc result (ADR-0003); nothing is calculated here.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document

from ...calc.foundation_check import Requirement
from ...calc.pile_check import Column, Judged, PileCheckResult
from ...core.printed import Printed
from ..document import blank, report
from ..equations import Definition
from .foundation_check import COLON, Chapter, LONGITUDINAL, TRANSVERSE
from .frame_report import Manuscript, Span, TableSpec, Unit, blocks, semantic_records, value

TABLE_LEFT = 1
WIDTHS = (6, 11, 4, 4, 4)  # the label, the symbol, and 長期支持, 短期支持, 安全性
BLANK = ""
NAMES = {Requirement.LONG_TERM: "長期支持", Requirement.SHORT_TERM: "短期支持", Requirement.SAFETY: "安全性"}
DASH = "－"


def _text(item: Printed | None) -> str:
    return DASH if item is None else value(item)


def _ratio(item: Judged | None) -> str:
    return DASH if item is None else value(item.value)


def _judgement(column: Column) -> str:
    return "ＯＫ" if all(item.ok for item in column.judgements) else "ＮＧ"


def _number(item: int | None) -> str:
    return DASH if item is None else str(item)


Row = tuple[Any, ...]


def _table(result: PileCheckResult) -> TableSpec:
    columns = result.columns
    groups: list[tuple[str, list[tuple[str, Callable[[Column], str]]]]] = [
        ("組合せ", [("Vd の No", lambda column: _number(column.vd_combination)),
                   ("Vud の No", lambda column: _number(column.vud_combination)),
                   ("δd の No", lambda column: _number(column.delta_combination)),
                   ("θd の No", lambda column: _number(column.theta_combination))]),
        ("設計応答値", [("Vd (kN)", lambda column: value(column.vd)), ("Vud (kN)", lambda column: _text(column.vud)),
                       ("δd (mm)", lambda column: value(column.delta)), ("θd (rad)", lambda column: value(column.theta))]),
        ("基準支持力", [("Rk (kN)", lambda column: value(column.limits.rk)), ("pt", lambda column: value(column.limits.pt)),
                       ("fr", lambda column: value(column.limits.fr))]),
        ("設計限界値", [("Rvd (kN)", lambda column: value(column.limits.rvd)),
                       ("Rud (kN)", lambda column: value(column.limits.rud)),
                       ("δLd (mm)", lambda column: value(column.limits.delta)),
                       ("θLd (rad)", lambda column: value(column.limits.theta))]),
        ("構造物係数", [("γi", lambda column: value(column.gamma_i))]),
        ("安全率", [("γi・Vd / Rvd", lambda column: _ratio(column.vertical)),
                   ("γi・Vud / Rud", lambda column: _ratio(column.pull_out)),
                   ("γi・δd / δLd", lambda column: _ratio(column.horizontal)),
                   ("γi・θd / θLd", lambda column: _ratio(column.rotation))]),
    ]
    rows: list[Row] = [(Span(BLANK, colspan=2), *(Span(NAMES[column.requirement], align="center")
                                                  for column in columns))]
    for label, lines in groups:
        for index, (symbol, cell) in enumerate(lines):
            name = (Span(label, rowspan=len(lines)),) if index == 0 else ()
            rows.append((*name, Span(symbol, align="left"), *(Span(cell(column), align="right") for column in columns)))
    rows.append((Span("判　　定", colspan=2), *(Span(_judgement(column)) for column in columns)))
    return TableSpec(WIDTHS, tuple(rows), (1,) * len(rows), header_rows=1, left=TABLE_LEFT)


def content(result: PileCheckResult, chapter: Chapter) -> tuple[Unit, ...]:
    """The ordered manuscript, used by both the layout and the semantic tests."""
    m = Manuscript(chapter.prefix)
    m.heading("heading", f"{chapter.number}.11 基礎の照査", 1)
    m.heading("stability.heading", "(1) 杭基礎の安定に対する検討", 2)
    m.paragraph("stability.text", "杭基礎の安定に対する検討においては，次式を満足することを確かめる．")
    m.line("vertical", "γi・Vd / Rvd ≦ 1.0")
    m.line("pull_out", "γi・Vud / Rud ≦ 1.0")
    m.line("horizontal", "γi・δd / δLd ≦ 1.0")
    m.line("rotation", "γi・θd / θLd ≦ 1.0")
    m.definitions("symbols",
                  Definition("γi", "構造物係数"),
                  Definition("Vd", "押込み側杭頭部の設計鉛直力(kN)"),
                  Definition("Rvd", "設計鉛直支持力(kN)"),
                  Definition("Vud", "引抜き側杭頭部の設計引抜き力(kN)"),
                  Definition("Rud", "設計引抜き抵抗力(kN)"),
                  Definition("δd", "フーチング天端の最大応答水平変位(mm)"),
                  Definition("δLd", "水平変位の設計限界値(mm)"),
                  Definition("θd", "フーチング天端の最大応答回転角(rad)"),
                  Definition("θLd", "回転角の設計限界値(rad)"), colon=COLON)
    m.paragraph("table.title", "杭基礎の安定に対する検討表（杭1本当り）", left=TABLE_LEFT, keep=True)
    m.table("table", _table(result))
    return tuple(m.units)


def records(result: PileCheckResult, chapter: Chapter) -> list[dict[str, str]]:
    return semantic_records(content(result, chapter))


def build_pile_check(result: PileCheckResult, chapter: Chapter) -> Document:
    units = content(result, chapter)
    found: list = []
    run: list[Unit] = []
    for unit in units:
        previous = run[-1].kind if run else None
        if run and not run[-1].keep and (unit.kind == "definitions" or unit.kind in ("line", "equation")
                                         and previous not in ("line", "equation")):
            found += blocks(run)
            blank(found)
            run = []
        run.append(unit)
    return report(*found, *blocks(run))


def render_pile_check(result: PileCheckResult, path: str | Path, chapter: Chapter) -> Path:
    """Lay out completely, then atomically replace *path*; the same result gives the same bytes."""
    return build_pile_check(result, chapter).render(path, invariant=True)


def grid_documents(result: PileCheckResult, chapter: Chapter) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out (its grid Excel workbook): the whole report."""
    return (build_pile_check(result, chapter),)


__all__ = ["LONGITUDINAL", "TRANSVERSE", "Chapter", "build_pile_check", "content", "grid_documents", "records",
           "render_pile_check"]
