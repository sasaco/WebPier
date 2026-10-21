"""0720 線路直角方向の計算（地震時）: the report of Example2 11 pp.11-1..11-13 on the SeismicTransverseResult.

11.1 the transverse model with the 0.010 m column-base micro member and the
girder level above the bearing seat (11-1 node 1), 11.2 the actions printed
here (the seismic train of each track, the girder and train inertia, the
self-weight inertia; the rest is "§9 と同様"), 11.3 the load diagrams:
JRSNAP's 荷重図 (S_LoadPicture) of each basic case, one page per case in CASE
order, each drawn from the .ndt of the first combination that uses the case
(decision 51: CASE-6, the down track, from combination 2, every other case from
combination 1; Example2 11.3 is an Excel figure of two or three cases a page,
which is not reproduced), and 11.4 the basic cases and one combination per
track (decision 21). The earthquake acts toward W9 (→, decision 30). By the
user's decision (decision 41) WebPier draws no springs (no spring symbol, value
or table) and no enlarged figure of the column bottom. Between 11.1 and 11.2
come JRSNAP's データ確認図 pages (Example2 11-3..11-7), drawn by JRSNAP from
combination 1 of the NDU of the same generation (decision 50). The pushover and
the checks (11-14 onward) are not part of this stage.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document, Row

from ...calc.frame import MICRO_MEMBER, NodeRole, Region
from ...calc.seismic_longitudinal import ActionDirection
from ...calc.seismic_transverse import HorizontalInertia, SeismicCase, SeismicTransverseResult
from ...calc.transverse import Track
from ...inputs import PierInput
from ..equations import terms
from ..figures import pier_outline
from .frame_report import (
    Manuscript, Span, TableSpec, Unit, document, frame_figure, joined, material_lines,
    member_table, node_table, seat_moment, section_lines, self_weight_inertia, semantic_records as records,
    sub, used_concretes, value, with_unit,
)
from .insertion import DATA_CHECK, DIAGRAMS, LOAD_DIAGRAM, Insertion, diagrams_heading, documents, render_with_pages
from .seismic_longitudinal import INCREMENTS
from .transverse import _train_table, action_item, horizontal_table

PREFIX = "0720/"
ACTIONS = "actions.heading"  # the unit the データ確認図 pages come before (decision 50)
# JRSNAP's データ確認図 before 11.2 (decision 50) and its load diagram after 11.3 (decision 51).
INSERTIONS = (Insertion(DATA_CHECK, PREFIX + ACTIONS, before=True), Insertion(LOAD_DIAGRAM, PREFIX + DIAGRAMS))
ARROWS = {ActionDirection.DOWNWARD: "↓", ActionDirection.UPWARD: "↑", ActionDirection.TOWARD_ORIGIN: "←",
          ActionDirection.TOWARD_W9: "→"}
TRACK_NAMES = {Track.UP: "上り", Track.DOWN: "下り"}
_CASES = {
    SeismicCase.D1: (("D", "1"), "固定死荷重"), SeismicCase.D2: (("D", "2"), "付加死荷重"),
    SeismicCase.BUOYANCY: (("W", "p"), "浮力（平水位）"), SeismicCase.SNOW: (("Sw", "2"), "雪荷重（2年確率）"),
    SeismicCase.TRAIN_UP: (("L", ""), "列車荷重（上り）"), SeismicCase.TRAIN_DOWN: (("L", ""), "列車荷重（下り）"),
    SeismicCase.GIRDER_INERTIA: (("EQ", "1"), "地震時桁荷重慣性力"),
    SeismicCase.TRAIN_INERTIA: (("EQL", ""), "地震時列車荷重慣性力"),
    SeismicCase.SELF_INERTIA: (("EQ", "2"), "自重による地震時慣性力"),
}


def case_name(result: SeismicTransverseResult, case: SeismicCase) -> str:
    kh = {SeismicCase.GIRDER_INERTIA: result.girder_inertia.kh, SeismicCase.TRAIN_INERTIA: result.train_inertia.kh,
          SeismicCase.SELF_INERTIA: result.self_weight.kh}.get(case)
    name = _CASES[case][1]
    return name if kh is None else f"{name}（Kh={value(kh)}）"


def case_symbol(case: SeismicCase) -> Any:
    base, suffix = _CASES[case][0]
    return sub(base, suffix) if suffix else base


def _model(m: Manuscript, result: SeismicTransverseResult, pier: PierInput) -> None:
    frame = result.frame
    m.heading("title", "§11. 線路直角方向の計算（地震時）", 0)
    m.heading("model.heading", "11.1 検討モデル", 1)
    m.heading("model.figure.heading", "(1) 骨組図", 2)
    m.figure("model.figure", frame_figure(frame, pier_outline(pier, frame), springs=False,
                                          block_id=PREFIX + "model.figure"))
    m.paragraph("model.figure.note", f"太線は剛域を示す．◎は柱下端の微小部材（長さ {value(MICRO_MEMBER)} m）を示す．"
                                     "最上段の節点は桁の高さ（支承位置から h1 + h2）である．寸法の単位は m．")
    m.heading("model.nodes.heading", "(2) 節点と部材", 2)
    m.table("model.nodes", node_table(frame, springs=False))
    m.table("model.members", member_table(frame))
    m.heading("section.heading", "(3) 部材の断面諸元", 2)
    m.paragraph("section.rigid", "柱下端の微小部材以外の部材はすべて剛域とする．")
    micro = next(member for member in frame.members if member.region is Region.COLUMN_BASE)
    assert micro.section is not None
    m.heading("section.micro.heading", "1) 柱下端の微小部材", 3)
    section_lines(m, "section.micro", micro.section)
    m.equation("section.footing.centroid", "フーチング重心", sub("y", "G"),
               with_unit(frame.node(NodeRole.FOOTING_CENTROID).y))
    m.heading("section.material.heading", "2) 弾性係数", 3)
    for key, label, concrete in used_concretes(frame):
        material_lines(m, "section.material." + key, label, concrete)


def _inertia(m: Manuscript, key: str, heading: str, inertia: HorizontalInertia) -> None:
    m.heading(f"{key}.heading", heading, 2)
    m.equation(f"{key}.h", "水平力", "H", terms(*joined([value(row.h) for row in inertia.rows])), inertia.h)
    m.table(f"{key}.table", horizontal_table(inertia.rows, inertia.h, inertia.m))


def _actions(m: Manuscript, result: SeismicTransverseResult) -> None:
    snow = result.snow is not None  # the items follow those of 9.2 (decision 69)
    m.heading(ACTIONS, "11.2 作用の計算", 1)
    m.paragraph("actions.note", "下記以外の作用については，§9. 線路直角方向の計算（地震時以外）と同様とする．")
    m.heading("train.heading", f"{action_item(snow, 5)} 列車荷重", 2)
    m.paragraph("train.note", "鉛直力は 0600 の地震時列車荷重による反力に支承の分担率を乗じた値とする（上り線 L2，下り線 L1）．")
    for track, case in ((Track.UP, SeismicCase.TRAIN_UP), (Track.DOWN, SeismicCase.TRAIN_DOWN)):
        table = result.train(track)
        m.paragraph(f"train.{track.value}.heading", f"・{TRACK_NAMES[track]}線載荷", keep=True)
        m.table(f"train.{track.value}", _train_table(table))
        seat_moment(m, f"train.{track.value}.seat", result.frame, table.n, table.m, result.basic(case).points[0])
    _inertia(m, "girder", f"{action_item(snow, 6)} 地震時桁荷重慣性力", result.girder_inertia)
    _inertia(m, "train_inertia", f"{action_item(snow, 7)} 地震時列車荷重慣性力", result.train_inertia)
    m.paragraph("inertia.source", f"{action_item(snow, 6)}，{action_item(snow, 7)} は 0600 の支承の水平力"
                                  f"（桁荷重 Kh = {value(result.girder_inertia.kh)}，"
                                  f"列車荷重 Kh = {value(result.train_inertia.kh)}）をそのまま用い，"
                                  "支承位置からの高さ y で M = H × y とする．")
    self_weight_inertia(m, result.self_weight, f"{action_item(snow, 8)} 自重による地震時慣性力", "§6")


def _combinations(m: Manuscript, result: SeismicTransverseResult) -> None:
    m.heading("combination.heading", "11.4 作用の組合せ", 1)
    m.paragraph("basic.caption", "基本Case", keep=True)
    rows: list[tuple[Any, ...]] = [("Case", "記号", "作用方向", "荷重種別", "荷　重　名　称")]
    for action in result.basic_cases:
        rows.append((str(action.number), Span(case_symbol(action.case)), Span(ARROWS[action.direction]),
                     Span(INCREMENTS[action.increment]), case_name(result, action.case)))
    m.table("basic", TableSpec((2, 3, 3, 3, 14), tuple(rows), (1,) * len(rows),
                               numeric=frozenset({0})))
    m.paragraph("combination.caption", "組合せCase", keep=True)
    rows = [("Case", "列車", Row(sub("α", "f"), "／", sub("ρ", "m"), gap=0), "作用方向", "荷重補正係数＋基本Case",
             "地盤抵抗TYPE")]
    for combination in result.combinations:
        rows.append((str(combination.number), Span(TRACK_NAMES[combination.track]),
                     Span(f"{value(combination.alpha_f)}／{value(combination.rho_m)}"), Span(ARROWS[combination.direction]),
                     " + ".join(str(result.basic(case).number) for case in combination.cases),
                     str(combination.ground_resistance_type)))
    m.table("combination", TableSpec((2, 2, 3, 3, 11, 5), tuple(rows), (1,) * len(rows),
                                     numeric=frozenset({0, 5})))
    m.paragraph("combination.note", "上り線・下り線の列車荷重をそれぞれ組み合わせる．")


def content(result: SeismicTransverseResult, pier: PierInput) -> tuple[Unit, ...]:
    """The ordered manuscript, used by both the layout and the semantic tests."""
    m = Manuscript(PREFIX)
    _model(m, result, pier)
    _actions(m, result)
    diagrams_heading(m, "11.3 荷重図")
    _combinations(m, result)
    return tuple(m.units)


def semantic_records(result: SeismicTransverseResult, pier: PierInput) -> list[dict[str, str]]:
    return records(content(result, pier))


def build_seismic_transverse(result: SeismicTransverseResult, pier: PierInput) -> Document:
    """The whole 0720 manuscript as one GridLayoutPdf Document, without JRSNAP's pages."""
    return document(content(result, pier))


def render_seismic_transverse(result: SeismicTransverseResult, pier: PierInput, path: str | Path,
                              pages: Mapping[str, bytes]) -> Path:
    """The report with JRSNAP's データ確認図 (``pages[DATA_CHECK]``) before 11.2 and its load diagram
    (``pages[LOAD_DIAGRAM]``) after 11.3; atomically replaces *path*.

    WebPier's pages are the same bytes for the same input; JRSNAP's are its own (decisions 50, 51).
    """
    return render_with_pages(content(result, pier), INSERTIONS, pages, path)


def grid_documents(result: SeismicTransverseResult, pier: PierInput) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out, without the pages of JRSNAP (its grid Excel workbook)."""
    return documents(content(result, pier), INSERTIONS)
