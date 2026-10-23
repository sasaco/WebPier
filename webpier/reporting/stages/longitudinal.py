"""0610 線路方向荷重（地震時以外）: the report of Example2 08 pp.8-1..8-11 on the LongitudinalResult.

8.1 the model (figure, springs, nodes and members, sections, Ec), 8.2 the
actions with their formula lines, 8.3 the load diagrams, drawn by FEMPython
from the FrameWeb file of this generation and put in as its pages (decision 44),
8.4 the basic and Define cases, the combination coefficients as printed, and the
extraction cases. Member and foundation checks (8-12 onward) are not part of
this stage. Every number is a Printed value of the
LongitudinalResult, of the 0600 ReactionResult it was calculated from, or of
the input.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document, Row

from ...calc.frame import NodeRole
from ...calc.longitudinal import (
    BasicCase, Check, ImpactTable, Item, LongitudinalResult, SpringTerm, TopTable,
)
from ...calc.longitudinal.combinations import MAXIMUM_TRAIN, SERVICE_IMPACT, Basis
from ...calc.reaction import ReactionResult
from ...calc.reaction.longitudinal import LongitudinalCase
from ...inputs import PierInput
from ..equations import terms
from ..figures import footing_dimensions, pier_outline
from ..numbers import constant
from .frame_report import (
    BODY_LEFT, FigureSpec, Manuscript, Span, TableSpec, Unit, bearing_symbol, document,
    frame_figure, material_lines, member_table, part_weight, node_table, operand, overlap_lines, section_lines, seat_moment,
    coefficient_table, extraction_table, factor_lines, pedestal_lever_note, seat_heading, seat_tables,
    semantic_records as records, spring_table, sub, top_table, used_concretes, value, with_unit,
)
from .insertion import DIAGRAMS, LOAD_DIAGRAM, Insertion, diagrams_heading, documents, render_with_pages

PREFIX = "0610/"
BEARING_SYMBOLS = {"可動": "M", "固定": "F"}

# Horizontal cases (8-5, 8-9): requirement and the LR part of the name; the B factor comes from 0600.
_HORIZONTAL = {
    LongitudinalCase.SERVICE_LR08: ("使用性", "0.8LR"),
    LongitudinalCase.SERVICE_LR10: ("使用性", "1.0LR"),
    LongitudinalCase.SAFETY_LR10_B10: ("安全性", "1.0LR"),
    LongitudinalCase.SAFETY_LR11_B10: ("安全性", "1.1LR"),
    LongitudinalCase.SAFETY_LR10_B11: ("安全性", "1.0LR"),
    LongitudinalCase.SAFETY_LR10: ("安全性", "1.0LR"),
    LongitudinalCase.RESTORABILITY_LR10_B10: ("復旧性", "1.0LR"),
    LongitudinalCase.RESTORABILITY_LR10: ("復旧性", "1.0LR"),
}
# Basic cases (8-9): name, qualifier and symbol (base, subscript).
_BASIC = {
    BasicCase.D1: ("固定死荷重", "", ("D", "1")), BasicCase.D2: ("付加死荷重", "", ("D", "2")),
    BasicCase.BUOYANCY_HIGH: ("浮力", "高水位", ("W", "P1")),
    BasicCase.BUOYANCY_NORMAL: ("浮力", "平水位", ("W", "P2")),
    BasicCase.BUOYANCY_LOW: ("浮力", "低水位", ("W", "P3")),
    BasicCase.SNOW2: ("雪荷重", "2年確率", ("S", "S2")), BasicCase.SNOW10: ("雪荷重", "10年確率", ("S", "S10")),
    BasicCase.SNOW30: ("雪荷重", "30年確率", ("S", "S30")),
    BasicCase.TRAIN_SINGLE: ("列車荷重", "単線", ("L", "1")), BasicCase.TRAIN_DOUBLE: ("列車荷重", "複線", ("L", "2")),
    BasicCase.IMPACT_SINGLE: ("衝撃荷重", "安全性・復旧性　単線", ("I", "1")),
    BasicCase.IMPACT_DOUBLE: ("衝撃荷重", "安全性・復旧性　複線", ("I", "2")),
}
# The 16 combinations of 8-10: requirement, performance item, remark.
_CHECKS = {
    Check.FAILURE_TRAIN_MAX: ("安全性", "破壊", "列車最大"), Check.FAILURE_BRAKING_MAX: ("安全性", "破壊", "制動最大"),
    Check.FAILURE_RAIL_MAX: ("安全性", "破壊", "ﾛﾝｸﾞ最大"), Check.FAILURE_SNOW_MAX: ("安全性", "破壊", "雪最大"),
    Check.CRACK_PERMANENT_VARIABLE: ("耐久性・\n使用性", "ひび割れ", "縁応力度"),
    Check.CRACK_PERMANENT: ("耐久性・\n使用性", "ひび割れ", "永久荷重"),
    Check.CRACK_VARIABLE: ("耐久性・\n使用性", "ひび割れ", "変動荷重"),
    Check.DAMAGE_TRAIN_MAX: ("使用性", "損傷", "列車最大"), Check.DAMAGE_SNOW_MAX: ("使用性", "損傷", "雪最大"),
    Check.STABILITY_TRAIN_MAX: ("安全性", "地盤の安定", "列車最大"),
    Check.STABILITY_BRAKING_MAX: ("安全性", "地盤の安定", "制動最大"),
    Check.STABILITY_RAIL_MAX: ("安全性", "地盤の安定", "ﾛﾝｸﾞ最大"),
    Check.STABILITY_SNOW_MAX: ("安全性", "地盤の安定", "雪最大"),
    Check.SUPPORT_LONG_TERM: ("使用性", "長期", ""), Check.SUPPORT_SHORT_TERM_LOW_WATER: ("使用性", "短期", ""),
    Check.SUPPORT_SHORT_TERM_HIGH_WATER: ("使用性", "短期", ""),
}
_WATER = (("high", "高水位", "1"), ("normal", "平水位", "2"), ("low", "低水位", "3"))
_ROW_NAMES = {Item.BEAM: "はり"}


def brake_text(reaction: ReactionResult, case: LongitudinalCase) -> tuple[str, str]:
    """The B part of a horizontal case name, short and in full: ``1.23B`` with the ρf × γ of 0600 (07 7-7).

    When the two bearings have different factors (an entered restorability factor), the short form is
    ``B`` and the full form names both.
    """
    forces = reaction.longitudinal.case(case)
    factors = [force.brake_factor for force in (forces.origin, forces.end) if force.brake_factor is not None]
    if not factors:
        return "", ""
    if len({factor.value for factor in factors}) == 1:
        return f"{value(factors[0])}B", f"{value(factors[0])}B"
    return "B", f"B（起点 {value(factors[0])}，終点 {value(factors[1])}）"


def horizontal_name(reaction: ReactionResult, case: LongitudinalCase) -> tuple[str, str]:
    """(requirement, ``1.0LR + 1.23B``) of a horizontal case (8-5)."""
    requirement, rail = _HORIZONTAL[case]
    brake = brake_text(reaction, case)[1]
    return requirement, rail + (" + " + brake if brake else "")


def basic_name(result: LongitudinalResult, reaction: ReactionResult, case: BasicCase) -> tuple[str, str, str, Any]:
    """(name, requirement, qualifier, symbol) of a basic case (8-9)."""
    if case in _BASIC:
        name, qualifier, (base, suffix) = _BASIC[case]
        return name, "", qualifier, sub(base, suffix)
    row = result.horizontal[case.value - BasicCase.SERVICE_LR08.value]
    requirement, label = horizontal_name(reaction, row.case)
    short = brake_text(reaction, row.case)[0]
    rail = _HORIZONTAL[row.case][1]
    name = "ﾛﾝｸﾞﾚｰﾙ+制動" if short else "ﾛﾝｸﾞﾚｰﾙ縦荷重"
    symbol = Row(rail.removesuffix("LR"), sub("L", "R"), ("+" + short) if short else "", gap=0)
    return name, requirement, f"{requirement}　{label}", symbol


def _model(m: Manuscript, result: LongitudinalResult, reaction: ReactionResult, pier: PierInput) -> None:
    frame = result.frame
    m.heading("title", "§8. 線路方向の計算（地震時以外）", 0)
    m.heading("model.heading", "8.1 検討モデル", 1)
    m.heading("model.figure.heading", "(1) 骨組図", 2)
    bearings = (BEARING_SYMBOLS[pier.spans.origin.bearing], BEARING_SYMBOLS[pier.spans.end.bearing])
    m.figure("model.figure", frame_figure(frame, pier_outline(pier, frame), bearings=bearings,
                                          horizontal=footing_dimensions(pier, frame, reaction.self_weight.footing_length),
                                          block_id=PREFIX + "model.figure"))
    m.paragraph("model.figure.note", "太線は剛域を示す．Ⓜは可動支承，Ⓕは固定支承．寸法の単位は m．")
    m.paragraph("model.springs.caption", "フーチング底面のばね", keep=True)
    m.table("model.springs", spring_table(frame))
    m.heading("model.nodes.heading", "(2) 節点と部材", 2)
    m.table("model.nodes", node_table(frame))
    m.table("model.members", member_table(frame))
    m.heading("section.heading", "(3) 部材の断面諸元", 2)
    number = 1
    m.heading("section.column.heading", f"{number}) 柱（はり・ハンチを含む）", 3)
    section_lines(m, "section.column", frame.column_section)
    if frame.pedestal_section is not None:
        number += 1
        m.heading("section.pedestal.heading", f"{number}) 桁受け", 3)
        section_lines(m, "section.pedestal", frame.pedestal_section)
    number += 1
    m.heading("section.footing.heading", f"{number}) フーチング", 3)
    m.paragraph("section.footing.rigid", "フーチングはすべて剛域とする．")
    m.equation("section.footing.centroid", "断面の重心位置", sub("y", "G"),
               with_unit(frame.node(NodeRole.FOOTING_CENTROID).y))
    number += 1
    m.heading("section.material.heading", f"{number}) 弾性係数", 3)
    for key, label, concrete in used_concretes(frame):
        material_lines(m, "section.material." + key, label, concrete)


def _top_rows(table: TopTable) -> list[tuple[Any, Any, Any, Any]]:
    found = []
    for row in table.rows:
        label = bearing_symbol("origin" if row.item is Item.ORIGIN else "end") if row.item in (Item.ORIGIN, Item.END) \
            else _ROW_NAMES[row.item]
        found.append((label, row.n, row.arm, row.m))
    return found


def top_with_seat(m: Manuscript, key: str, frame: Any, table: TopTable, point: Any) -> None:
    """A table of the loads at B and C with, on an offset pedestal, its moment at the seat (*point*)."""
    m.table(key, top_table(_top_rows(table), (table.n, table.m)))
    seat_moment(m, key + ".seat", frame, table.n, table.m, point)


def _table_with_seat(m: Manuscript, key: str, result: LongitudinalResult, table: TopTable, case: BasicCase | None,
                     seat_point: Any = None) -> None:
    point = seat_point or (result.basic(case).points[0] if case is not None else None)
    if point is None:
        m.table(key, top_table(_top_rows(table), (table.n, table.m)))
    else:
        top_with_seat(m, key, result.frame, table, point)


def _footing_moment(m: Manuscript, key: str, symbol: Any, n: Any, arm: Any, moment: Any) -> None:
    if arm.value:
        m.equation(key, "", symbol, terms(value(n), "×", operand(arm)), moment)


def fixed_dead(m: Manuscript, heading: str, pier: PierInput, weights: Any, frame: Any, fixed: Any) -> None:
    """8.2 (1) 固定死荷重, and of 10.2 (decision 78): with a pedestal, its q and the tables of the beam top and of the
    pedestal top, its levers from the pedestal centre (decision 81)."""
    s = pier.substructure
    m.heading("fixed.heading", heading, 2)
    if fixed.pedestal_q is not None:
        m.equation("fixed.pedestal", "桁受け", "q", terms(value(s.w[3]), "×", value(s.b[3]), "×",
                                                       value(s.unit_weight_body)), fixed.pedestal_q)
    m.equation("fixed.column", "柱", "q", terms(value(s.w[6]), "×", value(s.b[6]), "×",
                                               value(s.unit_weight_body)), fixed.column_q)
    m.equation("fixed.footing", "フーチング", "P", part_weight(weights.footing), fixed.footing.n)
    _footing_moment(m, "fixed.footing.moment", sub("M", "P"), fixed.footing.n, fixed.footing.arm, fixed.footing.m)
    m.paragraph("fixed.top.heading", "・橋脚天端に作用する荷重", keep=True)
    m.equation("fixed.top.beam", "はり・ハンチ", "N", part_weight(weights.beam), fixed.table.row(Item.BEAM).n)
    seat_heading(m, "fixed.top.seat", frame, NodeRole.CAP_TOP)
    m.table("fixed.top", top_table(_top_rows(fixed.table), (fixed.table.n, fixed.table.m)))
    overlap_lines(m, s, fixed)
    m.equation("fixed.n", "鉛直力", "N", terms(value(fixed.table.n), "−", value(fixed.column_q), "×",
                                              value(fixed.overlap)), fixed.n)
    m.equation("fixed.m", "モーメント", "M", with_unit(fixed.m))
    if fixed.pedestal is not None:
        seat_heading(m, "fixed.pedestal.seat", frame, NodeRole.PEDESTAL_TOP)
        m.table("fixed.pedestal.top", top_table(_top_rows(fixed.pedestal), (fixed.pedestal.n, fixed.pedestal.m)))
        pedestal_lever_note(m, "fixed.pedestal.note", frame, "アーム")


def additional_dead(m: Manuscript, heading: str, weights: Any, frame: Any, additional: Any) -> None:
    """8.2 (2) 付加死荷重, and of 10.2: the girder loads by seat (decision 81)."""
    m.heading("additional.heading", heading, 2)
    soil = additional.soil
    m.equation("additional.soil", "載荷土", "P", part_weight(weights.overburden), soil.n)
    _footing_moment(m, "additional.soil.moment", sub("M", "P"), soil.n, soil.arm, soil.m)
    seat_tables(m, "additional.top", frame, ((NodeRole.CAP_TOP, additional.table),
                                             (NodeRole.PEDESTAL_TOP, additional.pedestal)), _top_rows)


def buoyancy_line(m: Manuscript, key: str, label: str, symbol: Any, row: Any, water: Any) -> None:
    """The buoyancy of one water level (8.2 (3), 10.2 (3)) and its moment about the footing centroid."""
    m.equation(key, label, symbol, terms(value(water.body.unit_weight), "×", value(water.body.volume)), row.n)
    _footing_moment(m, f"{key}.moment", sub("M", "P"), row.n, row.arm, row.m)


def _dead(m: Manuscript, result: LongitudinalResult, reaction: ReactionResult, pier: PierInput) -> None:
    weights = reaction.self_weight
    m.heading("actions.heading", "8.2 作用の計算", 1)
    fixed_dead(m, "(1) 固定死荷重", pier, weights, result.frame, result.fixed)
    additional_dead(m, "(2) 付加死荷重", weights, result.frame, result.additional)
    m.heading("buoyancy.heading", "(3) 浮力", 2)
    for (key, label, suffix), row, water in zip(_WATER, result.buoyancy, (weights.buoyancy_high,
                                                                         weights.buoyancy_normal,
                                                                         weights.buoyancy_low), strict=True):
        buoyancy_line(m, f"buoyancy.{key}", label, sub("ω", suffix), row, water)


def _item(result: LongitudinalResult, number: int) -> str:
    """8.2 (number) as numbered with snow: without snow, (4) 雪荷重 is not printed and the items after it move up
    (decision 69)."""
    return f"({number if result.snow is not None or number < 4 else number - 1})"


def _snow_train(m: Manuscript, result: LongitudinalResult, reaction: ReactionResult) -> None:
    if result.snow is not None:
        m.heading("snow.heading", "(4) 雪荷重", 2)
        for index, (key, label, case) in enumerate((("2", "1) 2年確率", BasicCase.SNOW2),
                                                    ("10", "2) 10年確率", BasicCase.SNOW10),
                                                    ("30", "3) 30年確率", BasicCase.SNOW30))):
            m.heading(f"snow.{key}.heading", label, 3)
            _table_with_seat(m, f"snow.{key}", result, result.snow[index], case)
    m.heading("train.heading", f"{_item(result, 5)} 列車荷重", 2)
    m.heading("train.single.heading", "1) 単線載荷", 3)
    _table_with_seat(m, "train.single", result, result.train.single, BasicCase.TRAIN_SINGLE)
    m.heading("train.double.heading", "2) 複線載荷", 3)
    dead = reaction.dead
    for side, single, double, girder in (("origin", result.train.single.row(Item.ORIGIN),
                                          result.train.double.row(Item.ORIGIN), dead.origin),
                                         ("end", result.train.single.row(Item.END),
                                          result.train.double.row(Item.END), dead.end)):
        m.equation(f"train.double.{side}", "載荷線数を乗じる" if side == "origin" else "",
                   sub("R", "B" if side == "origin" else "C"),
                   terms(value(single.n), "×", value(girder.track_total)), double.n)
    _table_with_seat(m, "train.double", result, result.train.double, BasicCase.TRAIN_DOUBLE)


def _impact_table(table: ImpactTable, train_total: Any) -> TableSpec:
    rows = [("", "列車荷重\n(kN)", "衝撃係数", "鉛直力\n(kN)", "アーム\n(m)", "モーメント\n(kN・m)")]
    for row in table.rows:
        rows.append((Span(bearing_symbol("origin" if row.item is Item.ORIGIN else "end"), align="left"),
                     value(row.train), value(row.coefficient), value(row.n), value(row.arm), value(row.m)))
    rows.append(("合計", value(train_total), "", value(table.n), "", value(table.m)))
    return TableSpec((5, 4, 4, 4, 4, 5), tuple(rows), (2,) + (1,) * (len(rows) - 1),
                     numeric=frozenset(range(1, 6)), left=BODY_LEFT, open=True)


def _impact_horizontal(m: Manuscript, result: LongitudinalResult, reaction: ReactionResult) -> None:
    m.heading("impact.heading", f"{_item(result, 6)} 衝撃荷重", 2)
    m.paragraph("impact.note", "鉛直力は列車荷重に桁の衝撃係数を乗じた値とする．")
    impact = result.impact
    for key, label, table, train, case in (
            ("ultimate_single", "1) 単線載荷（安全性・復旧性）", impact.ultimate_single, result.train.single,
             BasicCase.IMPACT_SINGLE),
            ("ultimate_double", "2) 複線載荷（安全性・復旧性）", impact.ultimate_double, result.train.double,
             BasicCase.IMPACT_DOUBLE),
            ("service_single", "3) 単線載荷（使用性）", impact.service_single, result.train.single, None),
            ("service_double", "4) 複線載荷（使用性）", impact.service_double, result.train.double, None)):
        m.heading(f"impact.{key}.heading", label, 3)
        m.table(f"impact.{key}", _impact_table(table, train.n))
        point = result.basic(case).points[0] if case is not None else _service_point(result, key)
        seat_moment(m, f"impact.{key}.seat", result.frame, table.n, table.m, point)
    m.heading("horizontal.heading", f"{_item(result, 7)} 水平荷重", 2)
    m.heading("horizontal.summary.heading", "1) 支承に働く水平荷重のまとめ", 3)
    rows: list[tuple[Any, ...]] = [(Span("荷　重　種　別", colspan=2), "起点桁 (kN)", "終点桁 (kN)", "合計 (kN)")]
    groups = {"使用性": 2, "安全性": 4, "復旧性": 2}
    names = {"使用性": "使用性", "安全性": "安全性（破壊）", "復旧性": "復旧性"}
    previous = ""
    for row in result.horizontal:
        requirement, label = horizontal_name(reaction, row.case)
        lead: tuple[Any, ...] = ()
        if requirement != previous:
            lead = (Span(names[requirement], rowspan=groups[requirement], vertical=True),)
            previous = requirement
        rows.append((*lead, Span(label, align="left"),
                     *(Span(value(force), align="right") for force in (row.origin, row.end, row.total))))
    # Two grid rows a case, as Example2's taller rows, so that 安全性（破壊） stands written down its four cases.
    m.table("horizontal", TableSpec((2, 12, 4, 4, 4), tuple(rows), (2,) * len(rows)))


def _service_point(result: LongitudinalResult, key: str) -> Any:
    """The serviceability impact as the serviceability combinations put it on the frame (at the seat)."""
    case = BasicCase.IMPACT_SINGLE if key == "service_single" else BasicCase.IMPACT_DOUBLE
    return next(component.source.points[0] for combination in result.combinations
                for component in combination.components
                if component.case is case and component.basis is Basis.SERVICE_IMPACT)


def _combinations(m: Manuscript, result: LongitudinalResult, reaction: ReactionResult, pier: PierInput) -> None:
    m.heading("combination.heading", "8.4 設計作用の組合せ", 1)
    m.heading("basic.heading", "(1) 基本ケース", 2)
    rows: list[tuple[Any, ...]] = [("No", "荷重名称", "区分", "バネ")]
    for action in result.basic_cases:
        name, _, qualifier, _ = basic_name(result, reaction, action.case)
        rows.append((str(action.number), name, qualifier, "1" if action.spring is SpringTerm.LONG else "2"))
    m.table("basic", TableSpec((2, 7, 16, 2), tuple(rows), (1,) * len(rows), numeric=frozenset({0, 3})))
    m.paragraph("basic.note", "バネ 1 は長期，2 は短期のフーチング底面のばねを用いる．")
    m.heading("define.heading", "(2) Defineケース", 2)
    rows = [("No", "C1", "C2", "C3", "記号", "荷重名称", "区分")]
    for define in result.define_cases:
        name, requirement, qualifier, symbol = basic_name(result, reaction, define.case)
        second = str(-define.number) if -1 in define.signs else ""
        rows.append((str(define.number), str(result.basic(define.case).number), second, "", Span(symbol), name,
                     requirement or qualifier))
    m.table("define", TableSpec((2, 2, 2, 2, 5, 6, 8), tuple(rows), (1,) * len(rows),
                                numeric=frozenset({0, 1, 2})))
    m.paragraph("define.note", "C2 は水平荷重を逆向きにも作用させることを示す．")
    m.heading("factors.heading", "(3) 組合せケースと荷重係数", 2)
    factors = result.factors
    factor_lines(m, factors, pier.train, constant(float(MAXIMUM_TRAIN)), constant(float(SERVICE_IMPACT)))
    m.figure("combination", _combination_table(result, reaction))
    services = [str(c.number) for c in result.combinations
                if any(component.basis is Basis.SERVICE_IMPACT for component in c.components)]
    m.paragraph("combination.note",
                f"組合せ {'，'.join(services)} の衝撃荷重には，使用性の衝撃係数（3/4 を含む）による 8.2 {_item(result, 6)}"
                " 3)，4) の値に"
                f" ρ = {value(factors.service)} を乗じる．")
    m.heading("extraction.heading", "(4) 抽出ケース", 2)
    extraction_table(m, result.extractions)


def _combination_table(result: LongitudinalResult, reaction: ReactionResult) -> FigureSpec:
    """Basic cases as rows and the 16 combinations as columns, the coefficients as printed (8-10)."""
    rows = []
    for index, action in enumerate(result.basic_cases):
        name, _, _, symbol = basic_name(result, reaction, action.case)
        rows.append((str(action.number), symbol, name,
                     [combination.coefficients[index] for combination in result.combinations]))
    return coefficient_table([_CHECKS[c.check] for c in result.combinations],
                             [c.number for c in result.combinations], rows, block_id=PREFIX + "combination")


def content(result: LongitudinalResult, reaction: ReactionResult, pier: PierInput) -> tuple[Unit, ...]:
    """The ordered manuscript, used by both the layout and the semantic tests."""
    m = Manuscript(PREFIX)
    _model(m, result, reaction, pier)
    _dead(m, result, reaction, pier)
    _snow_train(m, result, reaction)
    _impact_horizontal(m, result, reaction)
    diagrams_heading(m, "8.3 荷重図")
    _combinations(m, result, reaction, pier)
    return tuple(m.units)


def semantic_records(result: LongitudinalResult, reaction: ReactionResult, pier: PierInput) -> list[dict[str, str]]:
    return records(content(result, reaction, pier))


def build_longitudinal(result: LongitudinalResult, reaction: ReactionResult, pier: PierInput) -> Document:
    """The whole 0610 manuscript as one GridLayoutPdf Document, without the load diagram pages."""
    return document(content(result, reaction, pier))


def render_longitudinal(result: LongitudinalResult, reaction: ReactionResult, pier: PierInput,
                        path: str | Path, pages: Mapping[str, bytes]) -> Path:
    """The report with the FEMPython load diagram pages (``pages[LOAD_DIAGRAM]``) after 8.3; atomically replaces
    *path*.

    The pages WebPier lays out are the same for the same input; the load diagram pages are FEMPython's.
    """
    return render_with_pages(content(result, reaction, pier), (Insertion(LOAD_DIAGRAM, PREFIX + DIAGRAMS),), pages,
                             path)


def grid_documents(result: LongitudinalResult, reaction: ReactionResult, pier: PierInput) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out, without the pages of FEMPython (its grid Excel workbook)."""
    return documents(content(result, reaction, pier), (Insertion(LOAD_DIAGRAM, PREFIX + DIAGRAMS),))
