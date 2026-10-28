"""0610 線路方向荷重（地震時以外）: the report of Example2 08 pp.8-1..8-11 on the LongitudinalResult.

8.1 the model (figure, springs, nodes and members, sections, Ec), 8.2 the
actions with their formula lines, 8.3 the load diagrams, drawn by FEMPython
from the FrameWeb file of this generation and put in as its pages (decision 44),
8.4 the basic and Define cases, the combination coefficients as printed (the 48
combinations of Example橋脚4 表2.3.2, decision 120), and the extraction cases.
Member and foundation checks (8-12 onward) are not part of
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
    BasicCase, Check, ImpactTable, Item, Layout, LongitudinalResult, SpringTerm, TopTable, Water,
)
from ...calc.longitudinal.actions import HORIZONTAL_CASES
from ...calc.longitudinal.combinations import MAXIMUM_TRAIN, SERVICE_IMPACT, Basis
from ...calc.reaction import ReactionResult
from ...calc.reaction.longitudinal import LAYOUT_CASES, LongitudinalCase
from ...inputs import PierInput
from ..equations import terms
from ..figures import footing_dimensions, pier_outline
from ..numbers import constant
from ..styles import PROFILE
from .frame_report import (
    BODY_LEFT, FigureSpec, Manuscript, Span, TableParts, TableSpec, Unit, plain, bearing_symbol, document,
    frame_figure, material_lines, member_table, part_weight, node_table, operand, overlap_lines, section_lines, seat_moment,
    coefficient_table, extraction_table, factor_lines, pedestal_lever_note, seat_heading, seat_tables,
    semantic_records as records, pile_section, spring_note, spring_units, sub, top_table, used_concretes, value, with_unit,
)
from .insertion import DIAGRAMS, LOAD_DIAGRAM, Insertion, diagrams_heading, documents, render_with_pages
from .reaction.longitudinal import REDUCED

PREFIX = "0610/"
BEARING_SYMBOLS = {"可動": "M", "固定": "F"}

# Horizontal cases (8-5, 8-9): requirement and the LR part of the name; the B factor comes from 0600.
_HORIZONTAL = {
    LongitudinalCase.SERVICE_LR08: ("使用性", "0.8LR"),
    LongitudinalCase.SERVICE_LR10: ("使用性", "1.0LR"),
    LongitudinalCase.SAFETY_LR10_B10: ("安全性", "1.0LR"),
    LongitudinalCase.SAFETY_LR11_B10: ("安全性", "1.1LR"),
    LongitudinalCase.SAFETY_LR11_B10_REDUCED: ("安全性", "1.1LR"),
    LongitudinalCase.SAFETY_LR10_B11: ("安全性", "1.0LR"),
    LongitudinalCase.SAFETY_LR10_B11_REDUCED: ("安全性", "1.0LR"),
    LongitudinalCase.SAFETY_LR10: ("安全性", "1.0LR"),
    LongitudinalCase.RESTORABILITY_LR10_B10: ("復旧性", "1.0LR"),
    LongitudinalCase.RESTORABILITY_LR10: ("復旧性", "1.0LR"),
}
# The reduced-dead-load cases (decision 120), named with the 0600 REDUCED.
_REDUCED = frozenset({LongitudinalCase.SAFETY_LR11_B10_REDUCED, LongitudinalCase.SAFETY_LR10_B11_REDUCED})
# Their 荷重名称 in the combination table (8-10), whose rows have no 区分 to say （死荷重低減あり）: "低減" as the
# table's "破壊・低減", the long rail shortened as its remark "ﾛﾝｸﾞ最大" and a half-width "･", so that the name fits
# its 5 grid columns (74.4 pt inside the cell: "ﾛﾝｸﾞ+制動･低減" is 70 pt, with a full-width "・" 75 pt).
# Example橋脚4 表2.3.1 says 死荷重低減あり in a 備考 column the table has not.
_REDUCED_NAMES = {"ﾛﾝｸﾞﾚｰﾙ+制動": "ﾛﾝｸﾞ+制動･低減", "ﾛﾝｸﾞﾚｰﾙ縦荷重": "ﾛﾝｸﾞﾚｰﾙ･低減"}
# Basic cases (8-9): name, qualifier and symbol (base, subscript). The single-track train and impact are not basic
# cases (decision 120 (g)).
_BASIC = {
    BasicCase.D1: ("固定死荷重", "", ("D", "1")), BasicCase.D2: ("付加死荷重", "", ("D", "2")),
    BasicCase.BUOYANCY_HIGH: ("浮力", "高水位", ("W", "P1")),
    BasicCase.BUOYANCY_NORMAL: ("浮力", "平水位", ("W", "P2")),
    BasicCase.BUOYANCY_LOW: ("浮力", "低水位", ("W", "P3")),
    BasicCase.SNOW2: ("雪荷重", "2年確率", ("S", "S2")), BasicCase.SNOW10: ("雪荷重", "10年確率", ("S", "S10")),
    BasicCase.SNOW30: ("雪荷重", "30年確率", ("S", "S30")),
    BasicCase.TRAIN_DOUBLE: ("列車荷重", "複線", ("L", "2")),
    BasicCase.IMPACT_DOUBLE: ("衝撃荷重", "安全性・復旧性　複線", ("I", "2")),
}
# The 12 checks of Example橋脚4 表2.3.2 (decision 120): requirement, performance item, remark. The turned remark holds
# two lines of five characters (the table's 38 basic cases leave a band of 4 grid rows on a page), so a reduced check
# names its reduction in its item, "破壊・低減", over the two or more columns it has in each part of the table.
_CHECKS = {
    Check.FAILURE_TRAIN_MAX: ("安全性", "破壊", "列車最大"), Check.FAILURE_BRAKING_MAX: ("安全性", "破壊", "制動最大"),
    Check.FAILURE_BRAKING_MAX_REDUCED: ("安全性", "破壊・低減", "制動最大"),
    Check.FAILURE_RAIL_MAX: ("安全性", "破壊", "ﾛﾝｸﾞ最大"),
    Check.FAILURE_RAIL_MAX_REDUCED: ("安全性", "破壊・低減", "ﾛﾝｸﾞ最大"),
    Check.FAILURE_SNOW_MAX: ("安全性", "破壊", "雪最大"),
    # alone in one column (two grid columns) between 安全性 and 耐久性・使用性: its requirement on two lines
    Check.SUPPORT_LONG_TERM: ("使用\n性", "長期", ""),
    Check.CRACK_PERMANENT_VARIABLE: ("耐久性・\n使用性", "ひび割れ", "縁応力度"),
    Check.CRACK_PERMANENT: ("耐久性・\n使用性", "ひび割れ", "永久荷重"),
    Check.CRACK_VARIABLE: ("耐久性・\n使用性", "ひび割れ", "変動荷重"),
    Check.DAMAGE_TRAIN_MAX: ("使用性", "損傷", "列車最大"), Check.DAMAGE_SNOW_MAX: ("使用性", "損傷", "雪最大"),
}
_WATERS = {Water.LOW: "低水位", Water.HIGH: "高水位"}
# The band of the turned remarks (decision 120): 4 grid rows, two lines of up to five characters ("ﾛﾝｸﾞ最大",
# "高水位・終"); with the four header bands of 2, 1, 4 and 1 rows the 38 basic cases fill a page with a part.
_REMARK_ROWS = 4
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
    """(requirement, ``1.0LR + 1.23B``) of a horizontal case (8-5); a reduced-dead-load case adds the 0600 REDUCED
    (decision 120)."""
    requirement, rail = _HORIZONTAL[case]
    brake = brake_text(reaction, case)[1]
    return requirement, rail + (" + " + brake if brake else "") + (REDUCED if case in _REDUCED else "")


# 列車の配置 (decision 102): the subscript's suffix as the sample's L1-1, L1-2, L1-3 (Example橋脚4 表2.3.1)
PLACINGS = {Layout.BOTH: "1", Layout.ORIGIN: "2", Layout.END: "3"}


def basic_name(result: LongitudinalResult, reaction: ReactionResult, case: BasicCase,
               layout: Layout | None = None) -> tuple[str, str, str, Any]:
    """(name, requirement, qualifier, symbol) of a basic case (8-9); the symbol of a case of each placing names its
    *layout*. The requirement and the qualifier of a reduced-dead-load case end in the 0600 REDUCED (decision 120)."""
    if case in _BASIC:
        name, qualifier, (base, suffix) = _BASIC[case]
        suffix += "" if layout is None else f"-{PLACINGS[layout]}"
        return name, "", qualifier, sub(base, suffix)
    row = next(row for row in result.horizontal if row.case is HORIZONTAL_CASES[case])
    requirement, label = horizontal_name(reaction, row.case)
    short = brake_text(reaction, row.case)[0]
    rail = _HORIZONTAL[row.case][1]
    name = "ﾛﾝｸﾞﾚｰﾙ+制動" if short else "ﾛﾝｸﾞﾚｰﾙ縦荷重"
    parts = [rail.removesuffix("LR"), sub("L", "R"), *((f"+{short}",) if short else ()),
             *(() if layout is None else (f"-{PLACINGS[layout]}",))]  # no empty text: it would be a run of no glyph
    symbol = Row(*parts, gap=0)
    return name, requirement + (REDUCED if row.case in _REDUCED else ""), f"{requirement}　{label}", symbol


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
    spring_units(m, frame)
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
    if frame.piles is not None:
        number += 1
        pile_section(m, frame, number)
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
                     seat_point: Any = None, layout: Layout = Layout.BOTH) -> None:
    point = seat_point or (result.basic(case, layout).points[0] if case is not None else None)
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
    dead = reaction.dead
    # Decision 120 (g): the double track only (no basic case takes the single track), its RB and RC from the 0600
    # reaction of one track.
    for index, (layout, trains) in enumerate(_placings(result)):
        key = _key("train", layout)
        m.heading(f"{key}.double.heading", f"{index + 1}) 複線載荷（{layout.value}）", 3)
        for side, single, double, girder in (("origin", trains.single.row(Item.ORIGIN), trains.double.row(Item.ORIGIN),
                                              dead.origin),
                                             ("end", trains.single.row(Item.END), trains.double.row(Item.END),
                                              dead.end)):
            m.equation(f"{key}.double.{side}", "載荷線数を乗じる" if side == "origin" else "",
                       sub("R", "B" if side == "origin" else "C"),
                       terms(value(single.n), "×", value(girder.track_total)), double.n)
        _table_with_seat(m, f"{key}.double", result, trains.double, BasicCase.TRAIN_DOUBLE, layout=layout)


def _placings(result: LongitudinalResult) -> list[tuple[Layout, Any]]:
    """① and the trains of ② and ③ (decision 102)."""
    return [(Layout.BOTH, result.train), *((placed.layout, placed.train) for placed in result.one_girder)]


def _key(stem: str, layout: Layout) -> str:
    """①'s keys are the stem's; ② and ③ add the placing."""
    return stem if layout is Layout.BOTH else f"{stem}.{layout.name.lower()}"


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
    m.paragraph("impact.note", "鉛直力は列車荷重に橋脚く体の衝撃係数を乗じた値とする．")
    impacts = [(Layout.BOTH, result.impact, result.train),
               *((placed.layout, placed.impact, placed.train) for placed in result.one_girder)]
    number = 0
    for layout, impact, trains in impacts:  # decision 120 (g): the double track only
        for key, label, table, case in (
                ("ultimate_double", "複線載荷（安全性・復旧性", impact.ultimate_double, BasicCase.IMPACT_DOUBLE),
                ("service_double", _SERVICE_LABEL, impact.service_double, None)):
            number += 1
            name = _key(f"impact.{key}", layout)
            m.heading(f"{name}.heading", f"{number}) {label}，{layout.value}）", 3)
            m.table(name, _impact_table(table, trains.double.n))
            point = result.basic(case, layout).points[0] if case is not None else _service_point(result, layout)
            seat_moment(m, f"{name}.seat", result.frame, table.n, table.m, point)
    m.heading("horizontal.heading", f"{_item(result, 7)} 水平荷重", 2)
    m.heading("horizontal.summary.heading", "1) 支承に働く水平荷重のまとめ", 3)
    header = (Span("荷　重　種　別", colspan=2), "起点桁 (kN)", "終点桁 (kN)", "合計 (kN)")
    names = {"使用性": "使用性", "安全性": "安全性（破壊）", "復旧性": "復旧性"}
    placed = [(row, None if row.case not in LAYOUT_CASES else Layout.BOTH) for row in result.horizontal]
    listed = []
    for row, layout in placed:  # each case with the train for ①, ② and ③ in turn (decision 102)
        listed.append((row, layout))
        if layout is not None:
            listed += [(next(r for r in other.horizontal if r.case is row.case), other.layout)
                       for other in result.one_girder]
    groups: dict[str, list[tuple[Any, ...]]] = {}
    for row, layout in listed:
        requirement, label = horizontal_name(reaction, row.case)
        mark = "" if layout is None else f"{_MARKS[layout]} "  # 列車の配置 (decision 102)
        groups.setdefault(requirement, []).append(
            (Span(mark + label, align="left"), *(Span(value(force), align="right") for force in (row.origin, row.end,
                                                                                                  row.total))))
    # Two grid rows a case and for the header, as Example2's taller rows, so that 安全性（破壊） stands written down its
    # cases. A table taller than a page is split between requirement groups (decision 120: 24 cases with ①, ② and ③):
    # the groups in turn go into one part while it fits a page, each part with the header again; a group is never cut.
    parts: list[list[tuple[str, list[tuple[Any, ...]]]]] = [[]]
    for requirement, cases in groups.items():
        height = 2 + 2 * sum(len(own) for _, own in parts[-1]) + 2 * len(cases)
        if parts[-1] and height > PROFILE.grid.rows:
            parts.append([])
        parts[-1].append((requirement, cases))
    specs = tuple(_horizontal_spec(header, part, names) for part in parts)
    if len(specs) == 1:
        m.table("horizontal", specs[0])
        return
    whole = _horizontal_spec(header, [item for part in parts for item in part], names)
    m.figure("horizontal", FigureSpec(TableParts(specs, PREFIX + "horizontal"), (plain(whole),)))


def _horizontal_spec(header: tuple[Any, ...], groups: list[tuple[str, list[tuple[Any, ...]]]],
                     names: Mapping[str, str]) -> TableSpec:
    """The bearing forces of the requirement *groups* under *header*, the requirement written down its cases."""
    rows: list[tuple[Any, ...]] = [header]
    for requirement, cases in groups:
        rows += [(*((Span(names[requirement], rowspan=len(cases), vertical=True),) if index == 0 else ()), *case)
                 for index, case in enumerate(cases)]
    return TableSpec((2, 12, 4, 4, 4), tuple(rows), (2,) * len(rows))


_SERVICE_LABEL = "複線載荷（使用性"


def _service_point(result: LongitudinalResult, layout: Layout) -> Any:
    """The serviceability impact as the serviceability combinations put it on the frame (at the seat)."""
    return next(component.source.points[0] for combination in result.combinations
                for component in combination.components
                if component.case is BasicCase.IMPACT_DOUBLE and component.basis is Basis.SERVICE_IMPACT
                and combination.layout is layout)


def _service_items(result: LongitudinalResult) -> str:
    """The items of 8.2 (6) with the serviceability impact of ①, ② and ③: every second one (2), 4), 6))."""
    return "，".join(f"{2 * (index + 1)})" for index, _ in enumerate(_placings(result)))


def _combinations(m: Manuscript, result: LongitudinalResult, reaction: ReactionResult, pier: PierInput) -> None:
    m.heading("combination.heading", "8.4 設計作用の組合せ", 1)
    m.heading("basic.heading", "(1) 基本ケース", 2)
    # 備考: the placing of a case of each 列車の配置, as Example橋脚4 表2.3.1 (decision 102)
    rows: list[tuple[Any, ...]] = [("No", "荷重名称", "区分", "備考", "バネ")]
    for action in result.basic_cases:
        name, _, qualifier, _ = basic_name(result, reaction, action.case, action.layout)
        remark = "" if action.layout is None else _SHORT_PLACINGS[action.layout]
        rows.append((str(action.number), name, qualifier, remark, "1" if action.spring is SpringTerm.LONG else "2"))
    m.table("basic", TableSpec((2, 6, 14, 3, 2), tuple(rows), (1,) * len(rows), numeric=frozenset({0, 4})))
    m.paragraph("basic.note", spring_note(result.frame))
    m.heading("define.heading", "(2) Defineケース", 2)
    rows = [("No", "C1", "C2", "C3", "記号", "荷重名称", "区分")]
    for define in result.define_cases:
        name, requirement, qualifier, symbol = basic_name(result, reaction, define.case, define.layout)
        second = str(-define.number) if -1 in define.signs else ""
        basic = result.basic(define.case, define.layout or Layout.BOTH)
        rows.append((str(define.number), str(basic.number), second, "", Span(symbol), name,
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
                f" {_service_items(result)} の値に"
                f" ρ = {value(factors.service)} を乗じる．")
    m.line("combination.reduced", Row("破壊・低減は死荷重を低減した組合せ（", sub("D", "1"),
                                      f" × {value(factors.d1_reduced)}，", sub("D", "2"),
                                      f" × {value(factors.d2_reduced)}）を示す．", gap=0))
    m.paragraph("combination.reduced_case", f"荷重名称の低減は水平荷重の{REDUCED}を示す．")
    m.heading("extraction.heading", "(4) 抽出ケース", 2)
    extraction_table(m, result.extractions)


def _combination_table(result: LongitudinalResult, reaction: ReactionResult) -> FigureSpec:
    """Basic cases as rows and the 48 combinations of Example橋脚4 表2.3.2 as columns (decision 120), the coefficients
    as printed (8-10)."""
    rows = []
    for index, action in enumerate(result.basic_cases):
        name, _, _, symbol = basic_name(result, reaction, action.case, action.layout)
        if action.case in HORIZONTAL_CASES and HORIZONTAL_CASES[action.case] in _REDUCED:
            name = _REDUCED_NAMES[name]
        rows.append((str(action.number), symbol, name,
                     [combination.coefficients[index] for combination in result.combinations]))
    return coefficient_table([_check_header(c) for c in result.combinations],
                             [c.number for c in result.combinations], rows, block_id=PREFIX + "combination",
                             case_columns=(1, 5, 5), remark_rows=_REMARK_ROWS)


_SHORT_PLACINGS = {Layout.BOTH: "両側", Layout.ORIGIN: "起点側", Layout.END: "終点側"}
_PLACING_INITIALS = {Layout.BOTH: "両", Layout.ORIGIN: "起", Layout.END: "終"}  # after the water level (表2.3.2)
_MARKS = {Layout.BOTH: "①", Layout.ORIGIN: "②", Layout.END: "③"}


def _check_header(combination: Any) -> tuple[str, str, str]:
    """The requirement, performance item and remark of a combination. On a second line of the remark, a check made at
    two water levels adds its level and a check with the train its placing: "両側" alone (decision 102), "低水位・両"
    with the level, the initial as Example橋脚4 表2.3.2 prints it (decision 120)."""
    requirement, item, remark = _CHECKS[combination.check]
    water, layout = combination.water, combination.layout
    if water is None and layout is None:
        return requirement, item, remark
    if water is None:
        second = _SHORT_PLACINGS[layout]
    else:
        second = _WATERS[water] + ("" if layout is None else "・" + _PLACING_INITIALS[layout])
    return requirement, item, f"{remark}\n{second}".lstrip("\n")


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
