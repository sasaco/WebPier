"""0710 線路方向の計算（地震時）: the report of Example2 10 pp.10-1..10-12 on the SeismicLongitudinalResult.

10.1 the model with the 0.010 m column-base micro member (figure, nodes and
members, the section of the micro member, Ec, springs), 10.2 the actions
printed here (the seismic train, the bearing horizontal forces and the
self-weight inertia; the rest is "§8 と同様"), 10.3 the load diagrams of the
8 basic cases and 10.4 the basic cases and the combination. The pushover and
the checks (10-13 onward) and the section rebar of 10-6 (JRSNAP output) are
not part of this stage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gridlayoutpdf import Document, Row

from ...calc.frame import MICRO_MEMBER, NodeRole, Region
from ...calc.longitudinal.actions import Item
from ...calc.seismic_longitudinal import (
    ActionDirection, Increment, Intensity, SeismicCase, SeismicLongitudinalResult,
)
from ...inputs import PierInput
from ..figures import pier_outline
from .frame_report import (
    CaseLoads, Manuscript, Span, TableSpec, Unit, bearing_symbol, diagram_groups, document, expression,
    frame_figure, material_lines, member_table, node_table, section_lines, seat_moment,
    semantic_records as records, spring_table, sub, top_table, used_concretes, value, with_unit,
)

PREFIX = "0710/"
FOOTER = "10 - {page}"
ARROWS = {ActionDirection.DOWNWARD: "↓", ActionDirection.UPWARD: "↑", ActionDirection.TOWARD_ORIGIN: "←"}
INCREMENTS = {Increment.FIXED: "固定", Increment.INCREMENTAL: "増分", Increment.LIMITED: "限定増分"}
# 10-12: symbol (base, subscript) and name; the inertia names carry their Kh.
_CASES = {
    SeismicCase.D1: (("D", "1"), "固定死荷重"), SeismicCase.D2: (("D", "2"), "付加死荷重"),
    SeismicCase.BUOYANCY: (("W", "p"), "浮力（平水位）"), SeismicCase.SNOW: (("Sw", "2"), "雪荷重（2年確率）"),
    SeismicCase.TRAIN: (("L", ""), "列車荷重"), SeismicCase.GIRDER_INERTIA: (("EQ", "1"), "地震時桁荷重慣性力"),
    SeismicCase.TRAIN_INERTIA: (("EQL", ""), "地震時列車荷重慣性力"),
    SeismicCase.SELF_INERTIA: (("EQ", "2"), "自重による地震時慣性力"),
}
# Names of the self-weight inertia per metre at the start and end of each member (10-8, 10-11).
INERTIA_NAMES = {Region.BEAM: ("Hw1", "Hw1"), Region.HAUNCH: ("Hw1", "Hw2"), Region.COLUMN: ("Hw3", "Hw3"),
                 Region.COLUMN_BASE: ("Hw3", "Hw3"), Region.PEDESTAL: ("Hw4", "Hw4")}


def case_name(result: SeismicLongitudinalResult, case: SeismicCase) -> str:
    kh = {SeismicCase.GIRDER_INERTIA: result.girder_inertia.kh, SeismicCase.TRAIN_INERTIA: result.train_inertia.kh,
          SeismicCase.SELF_INERTIA: result.self_weight.kh}.get(case)
    name = _CASES[case][1]
    return name if kh is None else f"{name}（Kh={value(kh)}）"


def case_symbol(case: SeismicCase) -> Any:
    base, suffix = _CASES[case][0]
    return sub(base, suffix) if suffix else base


def _model(m: Manuscript, result: SeismicLongitudinalResult, pier: PierInput) -> None:
    frame = result.frame
    m.heading("title", "§10. 線路方向の計算（地震時）", 0)
    m.heading("model.heading", "10.1 検討モデル", 1)
    m.heading("model.figure.heading", "(1) 骨組図", 2)
    m.figure("model.figure", frame_figure(frame, pier_outline(pier, frame), block_id=PREFIX + "model.figure"))
    m.paragraph("model.figure.note", f"太線は剛域を示す．◎は柱下端の微小部材（長さ {value(MICRO_MEMBER)} m）を示す．"
                                     "寸法の単位は m．")
    m.heading("model.nodes.heading", "(2) 節点と部材", 2)
    m.table("model.nodes", node_table(frame))
    m.table("model.members", member_table(frame))
    m.heading("section.heading", "(3) 部材の断面諸元", 2)
    m.paragraph("section.rigid", "柱下端の微小部材以外の部材はすべて剛域とする．")
    micro = next(member for member in frame.members if member.region is Region.COLUMN_BASE)
    m.heading("section.micro.heading", "1) 柱下端の微小部材", 3)
    assert micro.section is not None
    section_lines(m, "section.micro", micro.section)
    m.equation("section.footing.centroid", "フーチング重心", sub("y", "G"),
               with_unit(frame.node(NodeRole.FOOTING_CENTROID).y))
    m.heading("section.material.heading", "2) 弾性係数", 3)
    for key, label, concrete in used_concretes(frame):
        material_lines(m, "section.material." + key, label, concrete)
    m.heading("springs.heading", "(4) フーチング底面のばね", 2)
    m.table("springs", spring_table(frame))


def _intensity(m: Manuscript, key: str, label: str, name: str, intensity: Intensity) -> None:
    m.equation(key, label, sub("H", name), expression(value(intensity.along), "×", value(intensity.across), "×",
                                                      value(intensity.unit_weight), "×", value(intensity.kh)),
               intensity.value)


def _actions(m: Manuscript, result: SeismicLongitudinalResult) -> None:
    m.heading("actions.heading", "10.2 作用の計算", 1)
    m.paragraph("actions.note", "下記以外の作用については，§8. 線路方向の計算（地震時以外）と同様とする．")
    m.heading("train.heading", "(1) 列車荷重", 2)
    m.paragraph("train.single", "・単線載荷", keep=True)
    rows = [(bearing_symbol("origin" if row.item is Item.ORIGIN else "end"), row.n, row.arm, row.m)
            for row in result.train.rows]
    m.table("train", top_table(rows, (result.train.n, result.train.m)))
    seat_moment(m, "train.seat", result.frame, result.train.n, result.train.m,
                result.basic(SeismicCase.TRAIN).points[0])
    m.heading("horizontal.heading", "(2) 水平荷重", 2)
    m.heading("horizontal.summary.heading", "1) 支承に働く水平荷重のまとめ", 3)
    table: list[tuple[Any, ...]] = [(Span("荷　重　種　別", colspan=2), "起点桁 (kN)", "終点桁 (kN)", "合計 (kN)")]
    for index, (name, inertia) in enumerate((("桁荷重", result.girder_inertia), ("列車荷重", result.train_inertia))):
        forces = inertia.forces
        lead = (Span("地震時", rowspan=2, vertical=True),) if not index else ()
        table.append((*lead, Span(Row("1.0 ", sub("E", "Q"), f"（{name}）", gap=0), align="left"),
                      *(Span(value(force), align="right") for force in (forces.origin.force, forces.end.force,
                                                                        forces.total))))
    m.table("horizontal", TableSpec((28.8, 199.2, 66, 66, 66), tuple(table), (28.56, 23.04, 23.04)))
    m.paragraph("horizontal.note", f"0600 の支承の水平力（桁荷重 Kh = {value(result.girder_inertia.kh)}，"
                                   f"列車荷重 μ = {value(result.train_inertia.kh)}）をそのまま用いる．")
    inertia = result.self_weight
    m.heading("inertia.heading", "(3) 自重による地震時慣性力", 2)
    m.equation("inertia.kh", "設計水平震度", sub("K", "h"), value(inertia.kh))
    m.paragraph("inertia.body", "・橋脚く体に作用する水平力", keep=True)
    _intensity(m, "inertia.beam_top", "はり", "w1", inertia.beam_top)
    _intensity(m, "inertia.beam_bottom", "ハンチ下端", "w2", inertia.beam_bottom)
    _intensity(m, "inertia.column", "柱", "w3", inertia.column)
    if inertia.pedestal is not None:
        _intensity(m, "inertia.pedestal", "桁受け", "w4", inertia.pedestal)
    m.paragraph("inertia.footing.heading", "・フーチング重心に作用する水平力", keep=True)
    footing = inertia.footing
    m.equation("inertia.footing.formula", "", "H", expression("V", "×", Row("(", expression("γ", "−", "γ'"), ")", gap=0),
                                                         "×", sub("K", "h")))
    m.equation("inertia.footing", "", "H",
               expression(value(footing.volume), "×",
                          Row("(", expression(value(footing.unit_weight), "−", value(footing.displaced)), ")", gap=0),
                          "×", value(footing.kh)), footing.force)
    m.paragraph("inertia.footing.note", "V はフーチングの体積（§6），γ' は排除した土（表層）の湿潤単位体積重量．")


def _diagrams(m: Manuscript, result: SeismicLongitudinalResult) -> None:
    m.heading("diagrams.heading", "10.3 荷重図", 1)
    m.paragraph("diagrams.note", "鉛直力 N・P は下向き，モーメント M は時計回りを正とする．水平力は大きさと向き（←，→）で示し，"
                                 "地震は起点側（←）に作用させる．")
    groups = []
    for action in result.basic_cases:
        loads = tuple((load.member, load.start, load.end) for load in action.member_loads)
        case = CaseLoads(action.case.value, case_name(result, action.case), action.points, action.line_loads,
                         loads, INERTIA_NAMES, horizontal=action.direction is ActionDirection.TOWARD_ORIGIN,
                         magnitudes=True)
        groups.append((str(action.case.value), case.title, [case]))
    diagram_groups(m, result.frame, groups, lambda name, cases: f"Case {cases[0].number}　{name}")


def _combinations(m: Manuscript, result: SeismicLongitudinalResult) -> None:
    m.heading("combination.heading", "10.4 作用の組合せ", 1)
    m.paragraph("basic.caption", "基本Case", keep=True)
    rows: list[tuple[Any, ...]] = [("Case", "記号", "作用方向", "荷重種別", "荷　重　名　称")]
    for action in result.basic_cases:
        rows.append((str(action.case.value), Span(case_symbol(action.case)), Span(ARROWS[action.direction]),
                     Span(INCREMENTS[action.increment]), case_name(result, action.case)))
    m.table("basic", TableSpec((39.6, 48, 55.2, 63.6, 225.6), tuple(rows), (14.28,) * len(rows),
                               numeric=frozenset({0})))
    m.paragraph("combination.caption", "組合せCase", keep=True)
    rows = [("Case", Row(sub("α", "f"), "／", sub("ρ", "m"), gap=0), "作用方向", "荷重補正係数＋基本Case",
             "地盤抵抗TYPE")]
    for combination in result.combinations:
        rows.append((str(combination.number), Span(f"{value(combination.alpha_f)}／{value(combination.rho_m)}"),
                     Span(ARROWS[combination.direction]), " + ".join(str(case.value) for case in combination.cases),
                     str(combination.ground_resistance_type)))
    m.table("combination", TableSpec((39.6, 55.2, 55.2, 211.2, 70.8), tuple(rows), (14.28,) * len(rows),
                                     numeric=frozenset({0, 4})))


def content(result: SeismicLongitudinalResult, pier: PierInput) -> tuple[Unit, ...]:
    """The ordered manuscript, used by both the layout and the semantic tests."""
    m = Manuscript(PREFIX)
    _model(m, result, pier)
    _actions(m, result)
    _diagrams(m, result)
    _combinations(m, result)
    return tuple(m.units)


def semantic_records(result: SeismicLongitudinalResult, pier: PierInput) -> list[dict[str, str]]:
    return records(content(result, pier))


def build_seismic_longitudinal(result: SeismicLongitudinalResult, pier: PierInput) -> Document:
    """The 0710 report as a GridLayoutPdf Document (lay out or render it)."""
    return document(content(result, pier), FOOTER)


def render_seismic_longitudinal(result: SeismicLongitudinalResult, pier: PierInput, path: str | Path) -> Path:
    """Lay out completely, then atomically replace *path*; the same input gives the same bytes."""
    return build_seismic_longitudinal(result, pier).render(path, invariant=True)
