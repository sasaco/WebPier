"""0610 / 0620 with a load model (decision 70): the report of a GenericFrameResult.

n.1 the model and n.2 (1)〜(3) D1, D2 and the buoyancy are those of the train path's report (reporting.stages.
longitudinal / transverse); then, across the track, the wind on the pier body of each pressure the load model lists;
the load model's sections about its values; the 支承作用 of each of its cases with their sum at the bearing seat
(橋脚天端の等価作用); n.3 the load diagrams FEMPython draws from the FrameWeb file of this generation; n.4 the basic
cases, the Defines, the combinations with their extraction groups and coefficients by Define, and the extraction
groups, one without a combination printed 該当する組合せなし（断面力0）. Nothing of the input's train is printed.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document, Row

from ....calc.frame import Direction, NodeRole
from ....calc.generic.frame import ZERO, GenericFrameResult
from ....calc.longitudinal.combinations import EXTRACTION_NAMES
from ....calc.reaction import DeadReactionResult
from ....inputs import PierInput
from ....loadmodel import SpringTerm, pier_wind
from ...equations import terms
from .. import longitudinal as train_longitudinal, transverse as train_transverse
from ..frame_report import Manuscript, Span, TableSpec, Unit, document, semantic_records as records, value
from ..insertion import DIAGRAMS, LOAD_DIAGRAM, Insertion, diagrams_heading, render_with_pages
from .common import DeadView, bearing_table, extraction_table, sections

_STAGES = {Direction.LONGITUDINAL: ("0610/", "8", train_longitudinal, "アーム"),
           Direction.TRANSVERSE: ("0620/", "9", train_transverse, "支承位置")}


def _winds(m: Manuscript, result: GenericFrameResult, pier: PierInput, number: int) -> int:
    """The wind on the pier body of each pressure (0620), as the train path prints it; the next item number."""
    if not result.winds:
        return number
    s, frame = pier.substructure, result.frame
    m.heading("wind.heading", f"({number}) 躯体の風荷重", 2)
    m.paragraph("wind.ground.heading", "・く体の受風範囲（地表面はフーチング天端から起点側・終点側の土かぶりの小さい方だけ上）",
                keep=True)
    m.equation("wind.ground", "地表面の高さ", "z", terms(value(frame.node(NodeRole.FOOTING_TOP).y), "+",
                                                       Row("min(", value(s.df1), ", ", value(s.df2), ")", gap=0)),
               result.winds[0].ground)
    for index, wind in enumerate(result.winds, 1):
        m.heading(f"wind.{index}.heading", f"{index}) 風圧 {value(wind.pressure)} kN/m2（{pier_wind(index)}）", 3)
        train_transverse._pier_wind(m, f"wind.{index}", wind)
    return number + 1


def _bearings(m: Manuscript, result: GenericFrameResult, number: int, arm: str) -> None:
    m.heading("bearings.heading", f"({number}) 荷重モデルの支承作用", 2)
    m.paragraph("bearings.note", "支承ごとの支承作用を支承位置に集めて橋脚天端の等価作用とする"
                                 "（M = N × アーム ＋ H × y，y は支承からの作用高さ）．")
    for index, case in enumerate((case for case in result.basic_cases if case.bearings is not None), 1):
        m.heading(f"bearings.{case.id}.heading", f"{index}) {case.name}（{case.id}）", 3)
        bearing_table(m, f"bearings.{case.id}", result.frame, case.bearings, arm)  # type: ignore[arg-type]


def _candidates(result: GenericFrameResult, define: Any, field: str) -> str:
    return "／".join(dict.fromkeys(getattr(result.basic(case), field) for case, _ in define.candidates))


def _combinations(m: Manuscript, result: GenericFrameResult, chapter: str) -> None:
    m.heading("combination.heading", f"{chapter}.4 設計作用の組合せ", 1)
    m.heading("basic.heading", "(1) 基本ケース", 2)
    rows: list[tuple[Any, ...]] = [("No", "記号", "荷重名称", "バネ")]
    for case in result.basic_cases:
        rows.append((str(case.number), case.id, case.name, "1" if case.spring is SpringTerm.LONG else "2"))
    m.table("basic", TableSpec((28.8, 96, 250.8, 39.6), tuple(rows), (14.28,) * len(rows), numeric=frozenset({0, 3})))
    m.paragraph("basic.note", "バネ 1 は長期，2 は短期のフーチング底面のばねを用いる．")
    if result.empty:
        m.paragraph("basic.zero", f"{ZERO} は，組合せのない抽出ケースのための荷重0のケースである．")
    m.heading("define.heading", "(2) Defineケース", 2)
    width = max(len(define.candidates) for define in result.define_cases)
    number = {case.id: case.number for case in result.basic_cases}
    rows = [("No", *(f"C{index}" for index in range(1, width + 1)), "荷重名称")]
    for define in result.define_cases:
        cells = [str(sign * number[case]) for case, sign in define.candidates]
        rows.append((str(define.number), *cells, *[""] * (width - len(cells)), _candidates(result, define, "name")))
    m.table("define", TableSpec((28.8, *(36.0,) * width, 396 - 36.0 * width), tuple(rows), (14.28,) * len(rows),
                                numeric=frozenset(range(0, width + 1))))
    m.paragraph("define.note", "負の番号は荷重を逆向きに作用させることを示す．番号が複数あるものは，いずれか不利な一つをとる．")
    m.heading("factors.heading", "(3) 組合せケースと荷重係数", 2)
    rows = [("No", "組合せ名称", "抽出ケース")]
    for combination in result.combinations:
        groups = "，".join(EXTRACTION_NAMES[group] for group in sorted(combination.groups, key=lambda g: g.value))
        rows.append((str(combination.number), combination.name, groups))
    m.table("combinations", TableSpec((28.8, 192, 194.4), tuple(rows), (14.28,) * len(rows), numeric=frozenset({0})))
    numbers = [c.number for c in result.combinations]
    column = 30.0 if len(numbers) <= 12 else 22.08  # 1.35 fits 30 pt; more combinations take the narrow grid of 9-14
    m.paragraph("coefficients.caption", "Define ごとの荷重係数（列は組合せの番号）", keep=True)
    rows = [("No", "Define", *(str(n) for n in numbers))]
    for define in result.define_cases:
        factors = [next((t.factor for t in c.terms if t.define == define.number), None) for c in result.combinations]
        rows.append((str(define.number), _candidates(result, define, "id"),
                     *(value(f) if f is not None else Span("－") for f in factors)))
    m.table("coefficients", TableSpec((28.8, 480 - 28.8 - column * len(numbers), *(column,) * len(numbers)),
                                      tuple(rows), (14.28,) * len(rows),
                                      numeric=frozenset({0, *range(2, 2 + len(numbers))}), left=48.0))
    m.heading("extraction.heading", "(4) 抽出ケース", 2)
    extraction_table(m, result.extractions, result.empty)


def content(result: GenericFrameResult, reaction: DeadReactionResult, pier: PierInput) -> tuple[Unit, ...]:
    """The ordered manuscript, used by both the layout and the semantic tests."""
    prefix, chapter, train, arm = _STAGES[result.frame.direction]
    m = Manuscript(prefix)
    dead = result.dead
    view = DeadView(result.frame, dead.fixed, dead.additional, dead.buoyancy, dead.points)
    train._model(m, view, reaction, pier)  # type: ignore[arg-type]  # the frame and the self weight
    train._dead(m, view, reaction, pier)  # type: ignore[arg-type]
    number = _winds(m, result, pier, 4)
    if result.sections:
        sections(m, "loadmodel", f"({number}) 荷重モデルの作用の根拠", result.sections)
        number += 1
    _bearings(m, result, number, arm)
    diagrams_heading(m, f"{chapter}.3 荷重図")
    _combinations(m, result, chapter)
    return tuple(m.units)


def semantic_records(result: GenericFrameResult, reaction: DeadReactionResult, pier: PierInput) -> list[dict[str, str]]:
    return records(content(result, reaction, pier))


def build_generic_frame(result: GenericFrameResult, reaction: DeadReactionResult, pier: PierInput) -> Document:
    """The whole manuscript as one GridLayoutPdf Document, without the load diagram pages."""
    return document(content(result, reaction, pier))


def render_generic_frame(result: GenericFrameResult, reaction: DeadReactionResult, pier: PierInput,
                         path: str | Path, pages: Mapping[str, bytes]) -> Path:
    """The report with FEMPython's load diagram pages (``pages[LOAD_DIAGRAM]``) after n.3; atomically replaces
    *path*."""
    prefix = _STAGES[result.frame.direction][0]
    return render_with_pages(content(result, reaction, pier), (Insertion(LOAD_DIAGRAM, prefix + DIAGRAMS),), pages,
                             path)
