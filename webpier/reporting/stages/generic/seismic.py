"""0710 / 0720 with a load model (decision 70): the report of a GenericSeismicResult.

n.1 the model is the train path's (reporting.stages.seismic_longitudinal / seismic_transverse), JRSNAP's データ確認図
before n.2 and its load diagram after n.3 as there (decisions 50, 51). n.2 the actions: those of D1, D2 and the
buoyancy at the normal water level the combinations use, written as 8.2 / 9.2 write them (decision 78), each case of
the load model under its name (without the direction of the stage), and the self-weight inertia EQ2; n.4 the basic
cases with their direction and increment and the combinations.

A case of the load model prints its vertical forces by seat as D2 does, and its horizontal forces by girder (decision
80): along the track as 10-8 summarises the bearing horizontal forces (起点桁・終点桁・合計, toward the earthquake
positive), across the track at the girder levels (水平力, the height above the level and the moment, "-" where they are
none). The load model's sections, its 支承作用 tables and the weights of the control node
are not printed (decision 81).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document, Row

from ....calc.bearing_actions import BearingTable
from ....calc.frame import Direction, NodeRole
from ....calc.generic.seismic import GenericSeismicResult
from ....calc.seismic_longitudinal import toward
from ....inputs import PierInput
from ....loadmodel import D1, D2, WP_NORMAL, Side, bearing_label
from .. import longitudinal as frame_longitudinal, transverse as frame_transverse
from .. import seismic_longitudinal as train_longitudinal, seismic_transverse as train_transverse
from ..frame_report import (
    BODY_LEFT, Manuscript, Span, TableSpec, Unit, document, pedestal_lever_note, seat_heading, self_weight_inertia,
    semantic_records as records, sub, top_table, value, with_unit,
)
from ..insertion import diagrams_heading, documents, render_with_pages
from ..seismic_longitudinal import ARROWS, INCREMENTS, DeadItems, dead_items

_STAGES = {Direction.LONGITUDINAL: (train_longitudinal, "10", frame_longitudinal, "（線路方向）", "§6"),
           Direction.TRANSVERSE: (train_transverse, "11", frame_transverse, "（直角方向）", "§6")}
_GIRDERS = {Side.ORIGIN: ("起点桁 (kN)", "起点側　桁"), Side.END: ("終点桁 (kN)", "終点側　桁")}


def _dead(result: GenericSeismicResult) -> DeadItems:
    """The D1, D2 and buoyancy the combinations use (the cases the result makes)."""
    made = {case.id for case in result.basic_cases}
    dead = result.dead
    return DeadItems(
        frame=result.frame, fixed=dead.fixed if D1 in made else None,
        additional=dead.additional if D2 in made else None,
        buoyancy=dead.buoyancy[1] if WP_NORMAL in made else None)
_ARROWS = {**ARROWS, **train_transverse.ARROWS}


def _vertical(m: Manuscript, key: str, result: GenericSeismicResult, table: BearingTable) -> None:
    """The vertical forces of a case by seat, N × lever (as D2 prints its girder loads)."""
    for seat in table.seats:
        if not any(row.n.value for row in seat.rows):
            continue
        where = key if seat.anchor is NodeRole.CAP_TOP else f"{key}.pedestal"
        seat_heading(m, f"{where}.seat", result.frame, seat.anchor)
        rows = [(bearing_label(row.bearing), row.n, row.arm, row.nm) for row in seat.rows]
        m.table(where, top_table(rows, (seat.n, seat.nm)))
        if seat.anchor is NodeRole.PEDESTAL_TOP:
            pedestal_lever_note(m, f"{where}.note", result.frame, "アーム")


def _along(m: Manuscript, key: str, case: Any, table: BearingTable, earthquake: Decimal) -> None:
    """The horizontal forces of a case along the track by girder and their sum, toward the earthquake positive as 10-8
    1) 支承に働く水平荷重のまとめ prints them."""
    forces = {girder.side: toward(girder.h, earthquake) for girder in table.girders}
    rows: list[tuple[Any, ...]] = [(Span("荷　重　種　別", colspan=2), *(_GIRDERS[side][0] for side in Side), "合計 (kN)")]
    rows.append((Span("地震時", vertical=True), Span(f"1.0 {case.id}", align="left"),
                 *(Span(value(forces[side]) if side in forces else "－", align="right") for side in Side),
                 Span(value(toward(table.h, earthquake)), align="right")))
    m.table(key, TableSpec((2, 12, 4, 4, 4), tuple(rows), (2, 3)))  # 地震時 standing in one row
    for girder in table.girders:
        if girder.m.value:  # H above the seat
            m.equation(f"{key}.{girder.side.value}", _GIRDERS[girder.side][1], "M", with_unit(girder.m))


def _across(m: Manuscript, key: str, table: BearingTable) -> None:
    """The horizontal forces of a case across the track at the girder levels: H, the height above the level and
    H × that height, "-" where they are none (decision 81)."""
    rows: list[tuple[Any, ...]] = [("", "水平力 (kN)", "高さ (m)", "モーメント (kN・m)")]
    for girder in table.girders:
        height = value(girder.height) if girder.height is not None and girder.height.value else "-"
        rows.append((Span(_GIRDERS[girder.side][1], align="left"), value(girder.h), height,
                     value(girder.m) if girder.m.value else "-"))
    rows.append(("合計", value(table.h), "", ""))
    m.table(key, TableSpec((7, 6, 6, 7), tuple(rows), (1,) * len(rows), numeric=frozenset({1, 2, 3}),
                           left=BODY_LEFT, open=True))


def _title(name: str, own: str) -> str:
    """A case's name without the direction of the stage: 上部工の慣性力（線路方向） in 0710 is 上部工の慣性力."""
    return name.removesuffix(own) or name


def _actions(m: Manuscript, result: GenericSeismicResult, reaction: Any, pier: PierInput, chapter: str,
             frame_stage: Any, own: str, self_weight: str) -> None:
    m.heading(train_longitudinal.ACTIONS, f"{chapter}.2 作用の計算", 1)
    number = dead_items(m, _dead(result), reaction, pier, frame_stage)
    along = result.frame.direction is Direction.LONGITUDINAL
    for case in result.basic_cases:
        if case.bearings is None:
            continue
        key = f"case.{case.id}"
        m.heading(f"{key}.heading", f"({number}) {_title(case.name, own)}", 2)
        _vertical(m, f"{key}.vertical", result, case.bearings)
        if case.bearings.girders:
            (_along(m, f"{key}.horizontal", case, case.bearings, result.earthquake) if along
             else _across(m, f"{key}.horizontal", case.bearings))
        number += 1
    self_weight_inertia(m, result.self_weight, f"({number}) 自重による地震時慣性力", self_weight)


def _combinations(m: Manuscript, result: GenericSeismicResult, chapter: str) -> None:
    m.heading("combination.heading", f"{chapter}.4 作用の組合せ", 1)
    m.paragraph("basic.caption", "基本Case", keep=True)
    rows: list[tuple[Any, ...]] = [("Case", "記号", "作用方向", "荷重種別", "荷　重　名　称")]
    for case in result.basic_cases:
        rows.append((str(case.number), case.id, Span(_ARROWS[case.direction]), Span(INCREMENTS[case.increment]),
                     case.name))
    m.table("basic", TableSpec((2, 4, 3, 3, 15), tuple(rows), (1,) * len(rows),
                               numeric=frozenset({0})))
    m.paragraph("combination.caption", "組合せCase", keep=True)
    rows = [("Case", "名称", Row(sub("α", "f"), "／", sub("ρ", "m"), gap=0), "作用方向", "基本Case", "地盤抵抗TYPE")]
    for combination in result.combinations:
        rows.append((str(combination.number), combination.name,
                     Span(f"{value(combination.alpha_f)}／{value(combination.rho_m)}"),
                     Span(_ARROWS[combination.direction]),
                     " + ".join(str(result.basic(case).number) for case in combination.cases),
                     str(combination.ground_resistance_type)))
    m.table("combination", TableSpec((2, 4, 3, 3, 10, 5), tuple(rows), (1,) * len(rows),
                                     numeric=frozenset({0, 5})))


def content(result: GenericSeismicResult, reaction: Any, pier: PierInput) -> tuple[Unit, ...]:
    """The ordered manuscript, used by both the layout and the semantic tests."""
    train, chapter, frame_stage, own, self_weight = _STAGES[result.frame.direction]
    m = Manuscript(train.PREFIX)
    train._model(m, result, pier)  # type: ignore[arg-type]  # the frame only
    _actions(m, result, reaction, pier, chapter, frame_stage, own, self_weight)
    diagrams_heading(m, f"{chapter}.3 荷重図")
    _combinations(m, result, chapter)
    return tuple(m.units)


def semantic_records(result: GenericSeismicResult, reaction: Any, pier: PierInput) -> list[dict[str, str]]:
    return records(content(result, reaction, pier))


def build_generic_seismic(result: GenericSeismicResult, reaction: Any, pier: PierInput) -> Document:
    """The whole manuscript as one GridLayoutPdf Document, without JRSNAP's pages."""
    return document(content(result, reaction, pier))


def render_generic_seismic(result: GenericSeismicResult, reaction: Any, pier: PierInput, path: str | Path,
                           pages: Mapping[str, bytes]) -> Path:
    """The report with JRSNAP's データ確認図 before n.2 and its load diagram after n.3; atomically replaces *path*."""
    train = _STAGES[result.frame.direction][0]
    return render_with_pages(content(result, reaction, pier), train.INSERTIONS, pages, path)


def grid_documents(result: GenericSeismicResult, reaction: Any, pier: PierInput) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out, without the pages of JRSNAP (its grid Excel workbook)."""
    train = _STAGES[result.frame.direction][0]
    return documents(content(result, reaction, pier), train.INSERTIONS)


__all__ = ["build_generic_seismic", "content", "grid_documents", "render_generic_seismic", "semantic_records"]
