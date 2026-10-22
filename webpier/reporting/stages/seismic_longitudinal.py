"""0710 線路方向の計算（地震時）: the report of Example2 10 pp.10-1..10-12 on the SeismicLongitudinalResult.

10.1 the model with the 0.010 m column-base micro member (figure, nodes and
members, the section of the micro member, Ec), 10.2 the actions printed here
(the seismic train, the bearing horizontal forces and the self-weight inertia;
the rest is "§8 と同様"), 10.3 the load diagrams: JRSNAP's 荷重図
(S_LoadPicture) of each basic case, one page per case in CASE order, each drawn
from the .ndt of the first combination that uses the case (decision 51;
Example2 10.3 is an Excel figure of two or three cases a page, which is not
reproduced), and 10.4 the basic cases and the combination. By the user's
decision (decision 41) WebPier draws no springs (no spring symbol, no Kv/Ks/Kr,
no spring table). Leaving the springs out does not mean a fixed base or any
other support condition. Between 10.1 and 10.2 come JRSNAP's データ確認図
pages (Example2 10-3..10-7: the nonlinear and section numbers, the element
table, the section rebar and the node springs), drawn by JRSNAP from the NDU of
the same generation (decision 50). The pushover and the checks (10-13 onward)
are not part of this stage.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document, Row

from ...calc.frame import MICRO_MEMBER, NodeRole, Region
from ...calc.longitudinal.actions import Item
from ...calc.seismic_longitudinal import (
    ActionDirection, Increment, SeismicCase, SeismicLongitudinalResult,
)
from ...inputs import PierInput
from ..figures import pier_outline
from .frame_report import (
    Manuscript, Span, TableSpec, Unit, bearing_symbol, document,
    frame_figure, material_lines, member_table, node_table, section_lines, seat_moment,
    self_weight_inertia, semantic_records as records, sub, top_table, used_concretes, value, with_unit,
)
from .insertion import DATA_CHECK, DIAGRAMS, LOAD_DIAGRAM, Insertion, diagrams_heading, documents, render_with_pages

PREFIX = "0710/"
ACTIONS = "actions.heading"  # the unit the データ確認図 pages come before (decision 50)
# JRSNAP's データ確認図 before 10.2 (decision 50) and its load diagram after 10.3 (decision 51).
INSERTIONS = (Insertion(DATA_CHECK, PREFIX + ACTIONS, before=True), Insertion(LOAD_DIAGRAM, PREFIX + DIAGRAMS))
ARROWS = {ActionDirection.DOWNWARD: "↓", ActionDirection.UPWARD: "↑", ActionDirection.TOWARD_ORIGIN: "←",
          ActionDirection.TOWARD_END: "→"}
INCREMENTS = {Increment.FIXED: "固定", Increment.INCREMENTAL: "増分", Increment.LIMITED: "限定増分"}
# 10-12: symbol (base, subscript) and name; the inertia names carry their Kh.
_CASES = {
    SeismicCase.D1: (("D", "1"), "固定死荷重"), SeismicCase.D2: (("D", "2"), "付加死荷重"),
    SeismicCase.BUOYANCY: (("W", "p"), "浮力（平水位）"), SeismicCase.SNOW: (("Sw", "2"), "雪荷重（2年確率）"),
    SeismicCase.TRAIN: (("L", ""), "列車荷重"), SeismicCase.GIRDER_INERTIA: (("EQ", "1"), "地震時桁荷重慣性力"),
    SeismicCase.TRAIN_INERTIA: (("EQL", ""), "地震時列車荷重慣性力"),
    SeismicCase.SELF_INERTIA: (("EQ", "2"), "自重による地震時慣性力"),
}


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
    m.figure("model.figure", frame_figure(frame, pier_outline(pier, frame), springs=False,
                                          block_id=PREFIX + "model.figure"))
    m.paragraph("model.figure.note", f"太線は剛域を示す．◎は柱下端の微小部材（長さ {value(MICRO_MEMBER)} m）を示す．"
                                     "寸法の単位は m．")
    m.heading("model.nodes.heading", "(2) 節点と部材", 2)
    m.table("model.nodes", node_table(frame, springs=False))
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


def _actions(m: Manuscript, result: SeismicLongitudinalResult) -> None:
    m.heading(ACTIONS, "10.2 作用の計算", 1)
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
    m.table("horizontal", TableSpec((2, 12, 4, 4, 4), tuple(table), (2, 2, 2)))  # the rows of 0610's table
    m.paragraph("horizontal.note", f"0600 の支承の水平力（桁荷重 Kh = {value(result.girder_inertia.kh)}，"
                                   f"列車荷重 μ = {value(result.train_inertia.kh)}）をそのまま用いる．")
    self_weight_inertia(m, result.self_weight, "(3) 自重による地震時慣性力", "§6")


def _combinations(m: Manuscript, result: SeismicLongitudinalResult) -> None:
    m.heading("combination.heading", "10.4 作用の組合せ", 1)
    m.paragraph("basic.caption", "基本Case", keep=True)
    rows: list[tuple[Any, ...]] = [("Case", "記号", "作用方向", "荷重種別", "荷　重　名　称")]
    for action in result.basic_cases:
        rows.append((str(action.number), Span(case_symbol(action.case)), Span(ARROWS[action.direction]),
                     Span(INCREMENTS[action.increment]), case_name(result, action.case)))
    m.table("basic", TableSpec((2, 3, 3, 3, 14), tuple(rows), (1,) * len(rows),
                               numeric=frozenset({0})))
    m.paragraph("combination.caption", "組合せCase", keep=True)
    rows = [("Case", Row(sub("α", "f"), "／", sub("ρ", "m"), gap=0), "作用方向", "荷重補正係数＋基本Case",
             "地盤抵抗TYPE")]
    for combination in result.combinations:
        rows.append((str(combination.number), Span(f"{value(combination.alpha_f)}／{value(combination.rho_m)}"),
                     Span(ARROWS[combination.direction]),
                     " + ".join(str(result.basic(case).number) for case in combination.cases),
                     str(combination.ground_resistance_type)))
    m.table("combination", TableSpec((2, 3, 3, 13, 5), tuple(rows), (1,) * len(rows),
                                     numeric=frozenset({0, 4})))


def content(result: SeismicLongitudinalResult, pier: PierInput) -> tuple[Unit, ...]:
    """The ordered manuscript, used by both the layout and the semantic tests."""
    m = Manuscript(PREFIX)
    _model(m, result, pier)
    _actions(m, result)
    diagrams_heading(m, "10.3 荷重図")
    _combinations(m, result)
    return tuple(m.units)


def semantic_records(result: SeismicLongitudinalResult, pier: PierInput) -> list[dict[str, str]]:
    return records(content(result, pier))


def build_seismic_longitudinal(result: SeismicLongitudinalResult, pier: PierInput) -> Document:
    """The whole 0710 manuscript as one GridLayoutPdf Document, without JRSNAP's pages."""
    return document(content(result, pier))


def render_seismic_longitudinal(result: SeismicLongitudinalResult, pier: PierInput, path: str | Path,
                                pages: Mapping[str, bytes]) -> Path:
    """The report with JRSNAP's データ確認図 (``pages[DATA_CHECK]``) before 10.2 and its load diagram
    (``pages[LOAD_DIAGRAM]``) after 10.3; atomically replaces *path*.

    WebPier's pages are the same bytes for the same input; JRSNAP's are its own (decisions 50, 51).
    """
    return render_with_pages(content(result, pier), INSERTIONS, pages, path)


def grid_documents(result: SeismicLongitudinalResult, pier: PierInput) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out, without the pages of JRSNAP (its grid Excel workbook)."""
    return documents(content(result, pier), INSERTIONS)
