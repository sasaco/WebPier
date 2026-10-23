"""0620 線路直角方向荷重（地震時以外）: the report of Example2 09 pp.9-1..9-15 on the TransverseResult.

9.1 the model across the track (W sizes), 9.2 the actions per bearing (each
bearing a row with its position as the lever), the train and impact of the up,
down and double tracks, the vehicle lateral load, the wind with and without the
train on the girders and on the pier body above the ground (decision 12), the
centrifugal load on a curve (decision 33), 9.3 the load diagrams, drawn by
FEMPython from the FrameWeb file of this generation and put in as its pages
(decision 44), 9.4 the basic and Define cases, the coefficients of the 16 combinations by Define case and the
extraction cases. Member and foundation checks (9-16 onward) are not part of
this stage. Horizontal forces print as magnitude and direction, as in 0710.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document, Row

from ...calc.frame import NodeRole, Region
from ...calc.longitudinal.combinations import MAXIMUM_TRAIN, SERVICE_IMPACT, Basis
from ...calc.longitudinal.actions import SpringTerm
from ...calc.reaction import ReactionResult
from ...calc.transverse import (
    BasicCase, Check, Define, HorizontalRow, ImpactTable, Item, PierWind, TopTable, Track, TrainTable,
    TransverseResult, Wind,
)
from ...calc.transverse.actions import CentrifugalTable
from ...inputs import PierInput
from ..equations import terms
from ..figures import footing_dimensions, pier_outline
from ..numbers import constant
from .frame_report import (
    BODY_LEFT, Manuscript, Span, TableSpec, Unit, coefficient_table, document,
    extraction_table, factor_lines, frame_figure, joined, material_lines, member_table, node_table,
    operand, overlap_lines, seat_moment, seat_split, section_lines, semantic_records as records, spring_table, sub,
    top_table, used_concretes, value, with_unit,
)
from .insertion import DIAGRAMS, LOAD_DIAGRAM, Insertion, diagrams_heading, documents, render_with_pages

PREFIX = "0620/"
TRACKS = {Track.UP: "上り線載荷", Track.DOWN: "下り線載荷", Track.DOUBLE: "複線載荷"}
# Names of the wind per metre at the start and end of each loaded member (9-7, 9-12).
WIND_NAMES = {Region.BEAM: ("Hw1", "Hw1"), Region.HAUNCH: ("Hw1", "Hw2"), Region.COLUMN: ("Hw3", "Hw3"),
              Region.PEDESTAL: ("Hw4", "Hw4")}
_PARTS = {Region.BEAM: "はり", Region.HAUNCH: "ハンチ", Region.COLUMN: "柱", Region.PEDESTAL: "桁受け"}
# 9-13: name, qualifier and symbol (base, subscript) of each basic case.
_BASIC = {
    BasicCase.D1: ("固定死荷重", "", ("D", "1")), BasicCase.D2: ("付加死荷重", "", ("D", "2")),
    BasicCase.BUOYANCY_HIGH: ("浮力", "高水位", ("W", "P1")), BasicCase.BUOYANCY_NORMAL: ("浮力", "平水位", ("W", "P2")),
    BasicCase.BUOYANCY_LOW: ("浮力", "低水位", ("W", "P3")),
    BasicCase.SNOW2: ("雪荷重", "2年確率", ("S", "S2")), BasicCase.SNOW10: ("雪荷重", "10年確率", ("S", "S10")),
    BasicCase.SNOW30: ("雪荷重", "30年確率", ("S", "S30")),
    BasicCase.TRAIN_UP: ("列車荷重", "単線　上り", ("L", "1")), BasicCase.TRAIN_DOWN: ("列車荷重", "単線　下り", ("L", "1")),
    BasicCase.TRAIN_DOUBLE: ("列車荷重", "複線", ("L", "2")),
    BasicCase.IMPACT_UP: ("衝撃荷重", "安全性・復旧性　単線　上り", ("I", "1")),
    BasicCase.IMPACT_DOWN: ("衝撃荷重", "安全性・復旧性　単線　下り", ("I", "1")),
    BasicCase.IMPACT_DOUBLE: ("衝撃荷重", "安全性・復旧性　複線", ("I", "2")),
    BasicCase.LATERAL: ("車両横荷重", "", ("L", "F")),
    BasicCase.WIND_WITH_TRAIN: ("風荷重", "列車荷重がある場合", ("W", "1")),
    BasicCase.WIND_WITHOUT_TRAIN: ("風荷重", "列車荷重がない場合", ("W", "2")),
    BasicCase.CENTRIFUGAL_UP: ("遠心荷重", "単線　上り", ("C", "F1")),
    BasicCase.CENTRIFUGAL_DOWN: ("遠心荷重", "単線　下り", ("C", "F1")),
    BasicCase.CENTRIFUGAL_DOUBLE: ("遠心荷重", "複線", ("C", "F2")),
}
_DEFINE_QUALIFIERS = {Define.TRAIN_SINGLE: "単線", Define.IMPACT_SINGLE: "安全性・復旧性　単線",
                      Define.CENTRIFUGAL_SINGLE: "単線"}
# The 16 combinations of 9-14: requirement, performance item, remark.
_CHECKS = {
    Check.FAILURE_TRAIN_MAX: ("安全性", "破壊", "列車最大"), Check.FAILURE_LATERAL_MAX: ("安全性", "破壊", "車横最大"),
    Check.FAILURE_WIND_MAX: ("安全性", "破壊", "風最大"), Check.FAILURE_SNOW_MAX: ("安全性", "破壊", "雪最大"),
    Check.CRACK_PERMANENT_VARIABLE: ("耐久性・\n使用性", "ひび割れ", "縁応力度"),
    Check.CRACK_PERMANENT: ("耐久性・\n使用性", "ひび割れ", "永久荷重"),
    Check.CRACK_VARIABLE: ("耐久性・\n使用性", "ひび割れ", "変動荷重"),
    Check.DAMAGE_TRAIN_MAX: ("使用性", "損傷", "列車最大"), Check.DAMAGE_SNOW_MAX: ("使用性", "損傷", "雪最大"),
    Check.STABILITY_TRAIN_MAX: ("安全性", "地盤の安定", "列車最大"),
    Check.STABILITY_LATERAL_MAX: ("安全性", "地盤の安定", "車横最大"),
    Check.STABILITY_WIND_MAX: ("安全性", "地盤の安定", "風最大"),
    Check.STABILITY_SNOW_MAX: ("安全性", "地盤の安定", "雪最大"),
    Check.SUPPORT_LONG_TERM: ("使用性", "長期", ""), Check.SUPPORT_SHORT_TERM_LOW_WATER: ("使用性", "短期", ""),
    Check.SUPPORT_SHORT_TERM_HIGH_WATER: ("使用性", "短期", ""),
}
_WATER = (("high", "高水位", "1"), ("normal", "平水位", "2"), ("low", "低水位", "3"))


def symbol(case: BasicCase) -> Any:
    base, suffix = _BASIC[case][2]
    return sub(base, suffix)


def bearing_label(item: Item, slot: int | None) -> Any:
    """起点側 R_B G1: the girder bearing of the input slot (9-3)."""
    origin = item is Item.ORIGIN
    return Row("起点側　" if origin else "終点側　", sub("R", "B" if origin else "C"), f" G{slot + 1}", gap=0)


def _top_rows(table: TopTable) -> list[tuple[Any, Any, Any, Any]]:
    names = {Item.PEDESTAL: "桁受け", Item.BEAM: "はり"}
    return [(bearing_label(row.item, row.slot) if row.slot is not None else names[row.item], row.n, row.arm, row.m)
            for row in table.rows]


def top_with_seat(m: Manuscript, key: str, frame: Any, table: TopTable, point: Any) -> None:
    """A table of the loads at each bearing with, on an offset pedestal, its moment at the seat (*point*)."""
    m.table(key, top_table(_top_rows(table), (table.n, table.m)))
    seat_moment(m, key + ".seat", frame, table.n, table.m, point)


def _bearing_table(m: Manuscript, key: str, result: TransverseResult, table: TopTable, case: BasicCase | None) -> None:
    if case is None:
        m.table(key, top_table(_top_rows(table), (table.n, table.m)))
    else:
        top_with_seat(m, key, result.frame, table, result.basic(case).points[0])


def _footing_moment(m: Manuscript, key: str, row: Any) -> None:
    if row.arm.value:
        m.equation(key, "", sub("M", "P"), terms(value(row.n), "×", operand(row.arm)), row.m)


# The bearing tables with a product (9-5, 9-6, 9-8): the bearing (起点側　R_B G1), five numbers; 26 columns from the body.
PRODUCT_COLUMNS = (5, 4, 4, 4, 4, 5)


def _product_table(header: tuple[str, str], rows: list[tuple[Any, ...]], total: tuple[Any, Any]) -> TableSpec:
    """Load × factor = 鉛直力 by bearing, with the lever and the moment (9-5, 9-6)."""
    body: list[tuple[Any, ...]] = [("", header[0], header[1], "鉛直力\n(kN)", "アーム\n(m)", "モーメント\n(kN・m)")]
    body += [(Span(label, align="left"), *(value(number) for number in numbers)) for label, *numbers in rows]
    body.append(("合計", "", "", value(total[0]), "", value(total[1])))
    return TableSpec(PRODUCT_COLUMNS, tuple(body), (2,) + (1,) * (len(body) - 1),
                     numeric=frozenset(range(1, 6)), left=BODY_LEFT, open=True)


def _train_table(table: TrainTable) -> TableSpec:
    return _product_table(("反力\n(kN)", "分担率"), [(bearing_label(r.item, r.slot), r.reaction, r.share, r.n, r.arm, r.m)
                                                 for r in table.rows], (table.n, table.m))


def _impact_table(table: ImpactTable) -> TableSpec:
    return _product_table(("列車荷重\n(kN)", "衝撃係数"), [(bearing_label(r.item, r.slot), r.train, r.coefficient, r.n,
                                                       r.arm, r.m) for r in table.rows], (table.n, table.m))


def horizontal_table(rows: tuple[HorizontalRow, ...], h: Any, moment: Any) -> TableSpec:
    """H at the height y above the bearing seat and M = H × y, by girder (9-7, 11-8)."""
    body: list[tuple[Any, ...]] = [("", "水平力 (kN)", "高さ (m)", "モーメント (kN・m)")]
    body += [("起点側　桁" if row.item is Item.ORIGIN else "終点側　桁", value(row.h), value(row.y), value(row.m))
             for row in rows]
    body.append(("合計", value(h), "", value(moment)))
    return TableSpec((7, 6, 6, 7), tuple(body), (1,) * len(body), numeric=frozenset({1, 2, 3}),
                     left=BODY_LEFT, open=True)


def _model(m: Manuscript, result: TransverseResult, reaction: ReactionResult, pier: PierInput) -> None:
    frame = result.frame
    m.heading("title", "§9. 線路直角方向の計算（地震時以外）", 0)
    m.heading("model.heading", "9.1 検討モデル", 1)
    m.heading("model.figure.heading", "(1) 骨組図", 2)
    m.figure("model.figure", frame_figure(frame, pier_outline(pier, frame), block_id=PREFIX + "model.figure",
                                          horizontal=footing_dimensions(pier, frame, reaction.self_weight.footing_width)))
    m.paragraph("model.figure.note", "太線は剛域を示す．寸法の単位は m．")
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
    m.heading("section.footing.heading", f"{number + 1}) フーチング", 3)
    m.paragraph("section.footing.rigid", "フーチングはすべて剛域とする．")
    m.equation("section.footing.centroid", "断面の重心位置", sub("y", "G"),
               with_unit(frame.node(NodeRole.FOOTING_CENTROID).y))
    m.heading("section.material.heading", f"{number + 2}) 弾性係数", 3)
    for key, label, concrete in used_concretes(frame):
        material_lines(m, "section.material." + key, label, concrete)


def fixed_dead(m: Manuscript, heading: str, pier: PierInput, weights: Any, frame: Any, fixed: Any,
               points: Sequence[Any]) -> None:
    """9.2 (1) 固定死荷重, and of 11.2 (decision 78): *points* are the D1 point loads on *frame*."""
    s = pier.substructure
    m.heading("fixed.heading", heading, 2)
    m.equation("fixed.column", "柱", "q", terms(value(s.w[6]), "×", value(s.b[6]), "×",
                                               value(s.unit_weight_body)), fixed.column_q)
    m.equation("fixed.footing", "フーチング", "P",
               terms(value(weights.footing.unit_weight), "×", value(weights.footing.volume)), fixed.footing.n)
    _footing_moment(m, "fixed.footing.moment", fixed.footing)
    m.paragraph("fixed.top.heading", "・橋脚天端に作用する荷重", keep=True)
    if s.h[1].value > 0:
        m.equation("fixed.top.pedestal", "桁受け", "N", terms(value(weights.pedestal.unit_weight), "×",
                                                             value(weights.pedestal.volume)),
                   fixed.table.row(Item.PEDESTAL).n)
    m.equation("fixed.top.beam", "はり・ハンチ", "N",
               terms(value(weights.beam.unit_weight), "×", value(weights.beam.volume)), fixed.table.row(Item.BEAM).n)
    m.table("fixed.top", top_table(_top_rows(fixed.table), (fixed.table.n, fixed.table.m)))
    overlap_lines(m, s, fixed)
    m.equation("fixed.n", "鉛直力", "N", terms(value(fixed.table.n), "−", value(fixed.column_q), "×",
                                              value(fixed.overlap)), fixed.n)
    m.equation("fixed.m", "モーメント", "M", with_unit(fixed.m))
    if frame.bearing_offset.value:
        seat_split(m, fixed, points, frame, lambda row: row.slot is not None)


def additional_dead(m: Manuscript, heading: str, weights: Any, frame: Any, additional: Any, point: Any) -> None:
    """9.2 (2) 付加死荷重, and of 11.2: *point* is the D2 load at the seat."""
    m.heading("additional.heading", heading, 2)
    soil = additional.soil
    m.equation("additional.soil", "載荷土", "P",
               terms(value(weights.overburden.unit_weight), "×", value(weights.overburden.volume)), soil.n)
    _footing_moment(m, "additional.soil.moment", soil)
    m.paragraph("additional.top.heading", "・橋脚天端に作用する荷重", keep=True)
    top_with_seat(m, "additional.top", frame, additional.table, point)


def buoyancy_line(m: Manuscript, key: str, label: str, symbol: Any, row: Any, water: Any) -> None:
    """The buoyancy of one water level (9.2 (3), 11.2 (3)) and its moment about the footing centroid."""
    m.equation(key, label, symbol, terms(value(water.body.unit_weight), "×", value(water.body.volume)), row.n)
    _footing_moment(m, f"{key}.moment", row)


def _dead(m: Manuscript, result: TransverseResult, reaction: ReactionResult, pier: PierInput) -> None:
    weights = reaction.self_weight
    m.heading("actions.heading", "9.2 作用の計算", 1)
    fixed_dead(m, "(1) 固定死荷重", pier, weights, result.frame, result.fixed, result.basic(BasicCase.D1).points)
    additional_dead(m, "(2) 付加死荷重", weights, result.frame, result.additional,
                    result.basic(BasicCase.D2).points[0])
    m.heading("buoyancy.heading", "(3) 浮力", 2)
    for (key, label, suffix), row, water in zip(_WATER, result.buoyancy, (weights.buoyancy_high,
                                                                         weights.buoyancy_normal,
                                                                         weights.buoyancy_low), strict=True):
        buoyancy_line(m, f"buoyancy.{key}", label, sub("ω", suffix), row, water)
    if result.snow is not None:
        m.heading("snow.heading", "(4) 雪荷重", 2)
        for index, (key, label, case) in enumerate((("2", "1) 2年確率", BasicCase.SNOW2),
                                                    ("10", "2) 10年確率", BasicCase.SNOW10),
                                                    ("30", "3) 30年確率", BasicCase.SNOW30))):
            m.heading(f"snow.{key}.heading", label, 3)
            _bearing_table(m, f"snow.{key}", result, result.snow[index], case)


def action_item(snow: bool, number: int) -> str:
    """9.2 (number) as numbered with snow: without snow, (4) 雪荷重 is not printed and the items after it move up
    (decision 69). 0720 numbers its items after those of 9.2 the same way."""
    return f"({number if snow or number < 4 else number - 1})"


def _train_impact(m: Manuscript, result: TransverseResult) -> None:
    snow = result.snow is not None
    m.heading("train.heading", f"{action_item(snow, 5)} 列車荷重", 2)
    m.paragraph("train.note", "鉛直力は 0600 の 1 線分の反力に支承の分担率を乗じた値とする（上り線 L2，下り線 L1）．")
    cases = {Track.UP: BasicCase.TRAIN_UP, Track.DOWN: BasicCase.TRAIN_DOWN, Track.DOUBLE: BasicCase.TRAIN_DOUBLE}
    for track, case in cases.items():
        table = result.train.table(track)
        m.paragraph(f"train.{track.value}.heading", "・" + TRACKS[track], keep=True)
        m.table(f"train.{track.value}", _train_table(table))
        seat_moment(m, f"train.{track.value}.seat", result.frame, table.n, table.m, result.basic(case).points[0])
    m.heading("impact.heading", f"{action_item(snow, 6)} 衝撃荷重", 2)
    m.paragraph("impact.note", "鉛直力は列車荷重に桁の衝撃係数を乗じた値とする．")
    impacts = {Track.UP: BasicCase.IMPACT_UP, Track.DOWN: BasicCase.IMPACT_DOWN, Track.DOUBLE: BasicCase.IMPACT_DOUBLE}
    for usage, label, impact_set in (("ultimate", "安全性・復旧性", result.impact.ultimate),
                                     ("service", "使用性", result.impact.service)):
        for track, case in impacts.items():
            table = impact_set.table(track)
            key = f"impact.{usage}.{track.value}"
            m.paragraph(key + ".heading", f"・{TRACKS[track]}（{label}）", keep=True)
            m.table(key, _impact_table(table))
            point = result.basic(case).points[0] if usage == "ultimate" else _service_point(result, case)
            seat_moment(m, key + ".seat", result.frame, table.n, table.m, point)


def _service_point(result: TransverseResult, case: BasicCase) -> Any:
    """The serviceability impact as the serviceability combinations put it on the frame (at the seat)."""
    return next(alternative.source.points[0] for combination in result.combinations
                for component in combination.components for alternative in component.alternatives
                if alternative.case is case and alternative.basis is Basis.SERVICE_IMPACT)


def _horizontal_lines(m: Manuscript, key: str, rows: tuple[HorizontalRow, ...], h: Any, moment: Any | None) -> None:
    m.equation(key + ".h", "水平力", "H", terms(*joined([value(row.h) for row in rows])), h)
    if moment is not None:
        products = []
        for row in rows:
            products += [value(row.h), "×", value(row.y)] if not products else ["+", value(row.h), "×", value(row.y)]
        m.equation(key + ".m", "モーメント", "M", terms(*products), moment)


def _wind(m: Manuscript, key: str, label: str, wind: Wind) -> None:
    m.heading(f"{key}.heading", label, 3)
    m.equation(f"{key}.pressure", "風圧", sub("ω", "1"), with_unit(wind.pressure))
    m.paragraph(f"{key}.girder", "・桁に作用する風荷重（支承位置）", keep=True)
    _horizontal_lines(m, key, wind.rows, wind.h, None)
    m.table(f"{key}.table", horizontal_table(wind.rows, wind.h, wind.m))
    _pier_wind(m, key, wind.pier)


def _pier_wind(m: Manuscript, key: str, wind: PierWind) -> None:
    m.paragraph(f"{key}.pier", "・く体に作用する風荷重（地表面より上）", keep=True)
    rows: list[tuple[Any, ...]] = [("部位", "上端 (m)", "下端 (m)", "長さ (m)", "幅（上端） (m)", "幅（下端） (m)")]
    for segment in wind.segments:
        rows.append((_PARTS[segment.region], value(segment.top), value(segment.bottom), value(segment.length),
                     value(segment.width_top), value(segment.width_bottom)))
    if wind.segments:
        m.table(f"{key}.segments", TableSpec((4, 4, 4, 4, 5, 5), tuple(rows), (1,) * len(rows),
                                             numeric=frozenset(range(1, 6)), left=BODY_LEFT))
    seen: set[str] = set()
    for segment in wind.segments:
        names = WIND_NAMES[segment.region]
        for name, width, load in ((names[0], segment.width_top, segment.load_top),
                                  (names[1], segment.width_bottom, segment.load_bottom)):
            if name not in seen:
                seen.add(name)
                m.equation(f"{key}.{name}", _PARTS[segment.region], sub("H", name[1:]),
                           terms(value(wind.pressure), "×", value(width)), load)


def _wind_ground(m: Manuscript, result: TransverseResult, pier: PierInput) -> None:
    s, wind, frame = pier.substructure, result.wind_with_train.pier, result.frame
    m.paragraph("wind.ground.heading", "・く体の受風範囲（地表面はフーチング天端から起点側・終点側の土かぶりの小さい方だけ上）",
                keep=True)
    m.equation("wind.ground", "地表面の高さ", "z", terms(value(frame.node(NodeRole.FOOTING_TOP).y), "+",
                                                       Row("min(", value(s.df1), ", ", value(s.df2), ")", gap=0)),
               wind.ground)
    seat = frame.bearing_seat.y
    if wind.exposure.value:
        m.equation("wind.exposure", "受風高さ", "h", terms(value(seat), "−", value(wind.ground)), wind.exposure)
    else:
        m.equation("wind.exposure", "受風高さ", "h", with_unit(wind.exposure))


def _horizontal(m: Manuscript, result: TransverseResult, pier: PierInput) -> None:
    snow = result.snow is not None
    m.heading("lateral.heading", f"{action_item(snow, 7)} 車両横荷重", 2)
    lateral = result.lateral
    _horizontal_lines(m, "lateral", (lateral.origin, lateral.end), lateral.h, lateral.m)
    m.heading("wind.heading", f"{action_item(snow, 8)} 風荷重", 2)
    _wind_ground(m, result, pier)
    _wind(m, "wind.with_train", "1) 列車荷重がある場合", result.wind_with_train)
    _wind(m, "wind.without_train", "2) 列車荷重がない場合", result.wind_without_train)
    if result.centrifugal is not None:
        m.heading("centrifugal.heading", f"{action_item(snow, 9)} 遠心荷重", 2)
        m.paragraph("centrifugal.note", f"水平力は列車荷重（9.2 {action_item(snow, 5)}）に 0600 の遠心荷重係数 α を乗じ，"
                                        "支承位置から遠心荷重の作用高さ y に作用させる．")
        for track in Track:
            table: CentrifugalTable = result.centrifugal.table(track)
            m.paragraph(f"centrifugal.{track.value}.heading", "・" + TRACKS[track], keep=True)
            rows: list[tuple[Any, ...]] = [("", "列車荷重\n(kN)", "α", "水平力\n(kN)", "高さ\n(m)", "モーメント\n(kN・m)")]
            for row in table.rows:
                rows.append(("起点側" if row.item is Item.ORIGIN else "終点側", value(row.train), value(row.coefficient),
                             value(row.h), value(row.y), value(row.m)))
            rows.append(("合計", "", "", value(table.h), "", value(table.m)))
            m.table(f"centrifugal.{track.value}", TableSpec(PRODUCT_COLUMNS, tuple(rows),
                                                            (2,) + (1,) * (len(rows) - 1),
                                                            numeric=frozenset(range(1, 6)), left=BODY_LEFT, open=True))


def _combinations(m: Manuscript, result: TransverseResult, pier: PierInput) -> None:
    m.heading("combination.heading", "9.4 設計作用の組合せ", 1)
    m.heading("basic.heading", "(1) 基本ケース", 2)
    rows: list[tuple[Any, ...]] = [("No", "荷重名称", "区分", "バネ")]
    for action in result.basic_cases:
        name, qualifier, _ = _BASIC[action.case]
        rows.append((str(action.number), name, qualifier, "1" if action.spring is SpringTerm.LONG else "2"))
    m.table("basic", TableSpec((2, 7, 16, 2), tuple(rows), (1,) * len(rows), numeric=frozenset({0, 3})))
    m.paragraph("basic.note", "バネ 1 は長期，2 は短期のフーチング底面のばねを用いる．")
    m.heading("define.heading", "(2) Defineケース", 2)
    width = max(len(define.cases) * len(define.signs) for define in result.define_cases)
    rows = [("No", *(f"C{index}" for index in range(1, width + 1)), "記号", "荷重名称", "区分")]
    labels = []
    for define in result.define_cases:
        entries = [str(sign * result.basic(case).number) for sign in define.signs for case in define.cases]
        name, qualifier, _ = _BASIC[define.cases[0]]
        qualifier = _DEFINE_QUALIFIERS.get(define.define, qualifier)
        labels.append((symbol(define.cases[0]), name, qualifier))
        rows.append((str(define.number), *entries, *[""] * (width - len(entries)), Span(symbol(define.cases[0])), name,
                     qualifier))
    m.table("define", TableSpec((2, *(2,) * width, 4, 6, 15 - 2 * width), tuple(rows), (1,) * len(rows),
                                numeric=frozenset(range(0, 1 + width))))
    m.paragraph("define.note", "C1・C2 は同じ Define で選ぶ基本ケース（単線は上り・下りのいずれか），負の番号は"
                               "逆向きに作用させることを示す．")
    m.heading("factors.heading", "(3) 組合せケースと荷重係数", 2)
    factor_lines(m, result.factors, pier.train, constant(float(MAXIMUM_TRAIN)), constant(float(SERVICE_IMPACT)))
    table_rows = [(str(define.number), labels[index][0], labels[index][1],
                   [combination.coefficients[index] for combination in result.combinations])
                  for index, define in enumerate(result.define_cases)]
    m.figure("combination", coefficient_table([_CHECKS[c.check] for c in result.combinations],
                                              [c.number for c in result.combinations], table_rows,
                                              block_id=PREFIX + "combination"))
    services = [str(c.number) for c in result.combinations
                if any(a.basis is Basis.SERVICE_IMPACT for component in c.components for a in component.alternatives)]
    m.paragraph("combination.note",
                "列は Define ケースである．単線の列車荷重・衝撃荷重（遠心荷重）は一つの組合せで同じ線とし，"
                "車両横荷重・風荷重は正負それぞれを組み合わせる．"
                f"組合せ {'，'.join(services)} の衝撃荷重には，使用性の衝撃係数（3/4 を含む）による値に"
                f" ρ = {value(result.factors.service)} を乗じる．")
    m.heading("extraction.heading", "(4) 抽出ケース", 2)
    extraction_table(m, result.extractions)


def content(result: TransverseResult, reaction: ReactionResult, pier: PierInput) -> tuple[Unit, ...]:
    """The ordered manuscript, used by both the layout and the semantic tests."""
    m = Manuscript(PREFIX)
    _model(m, result, reaction, pier)
    _dead(m, result, reaction, pier)
    _train_impact(m, result)
    _horizontal(m, result, pier)
    diagrams_heading(m, "9.3 荷重図")
    _combinations(m, result, pier)
    return tuple(m.units)


def semantic_records(result: TransverseResult, reaction: ReactionResult, pier: PierInput) -> list[dict[str, str]]:
    return records(content(result, reaction, pier))


def build_transverse(result: TransverseResult, reaction: ReactionResult, pier: PierInput) -> Document:
    """The whole 0620 manuscript as one GridLayoutPdf Document, without the load diagram pages."""
    return document(content(result, reaction, pier))


def render_transverse(result: TransverseResult, reaction: ReactionResult, pier: PierInput, path: str | Path,
                      pages: Mapping[str, bytes]) -> Path:
    """The report with the FEMPython load diagram pages (``pages[LOAD_DIAGRAM]``) after 9.3; atomically replaces
    *path*.

    The pages WebPier lays out are the same for the same input; the load diagram pages are FEMPython's.
    """
    return render_with_pages(content(result, reaction, pier), (Insertion(LOAD_DIAGRAM, PREFIX + DIAGRAMS),), pages,
                             path)


def grid_documents(result: TransverseResult, reaction: ReactionResult, pier: PierInput) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out, without the pages of FEMPython (its grid Excel workbook)."""
    return documents(content(result, reaction, pier), (Insertion(LOAD_DIAGRAM, PREFIX + DIAGRAMS),))
