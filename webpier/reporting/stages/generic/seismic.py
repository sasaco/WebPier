"""0710 / 0720 with a load model (decision 70): the report of a GenericSeismicResult.

n.1 the model is the train path's (reporting.stages.seismic_longitudinal / seismic_transverse), JRSNAP's データ確認図
before n.2 and its load diagram after n.3 as there (decisions 50, 51). n.2 the actions: D1, D2 and the buoyancy as in
§8 / §9, the load model's sections, the 支承作用 of each of its cases on this frame (a horizontal force toward the
earthquake signed toward it), across the track the weights of the control node (decision 65), and the self-weight
inertia EQ2; n.4 the basic cases with their direction and increment and the combinations.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from gridlayoutpdf import Document, Row

from ....calc.frame import Direction
from ....calc.generic.seismic import GenericSeismicResult
from ....inputs import PierInput
from .. import seismic_longitudinal as train_longitudinal, seismic_transverse as train_transverse
from ..frame_report import (
    Manuscript, Span, TableSpec, Unit, document, self_weight_inertia, semantic_records as records, sub, value,
    with_unit,
)
from ..insertion import diagrams_heading, render_with_pages
from ..seismic_longitudinal import ARROWS, INCREMENTS
from .common import bearing_table, sections

_STAGES = {Direction.LONGITUDINAL: (train_longitudinal, "10", "8", "アーム", "§6"),
           Direction.TRANSVERSE: (train_transverse, "11", "9", "支承位置", "§6")}
_ARROWS = {**ARROWS, **train_transverse.ARROWS}


def _actions(m: Manuscript, result: GenericSeismicResult, chapter: str, frame_chapter: str, arm: str,
             self_weight: str) -> None:
    m.heading(train_longitudinal.ACTIONS, f"{chapter}.2 作用の計算", 1)
    m.paragraph("actions.note", f"固定死荷重・付加死荷重・浮力（平水位）は §{frame_chapter}. と同様とする．")
    number = 1
    if result.sections:
        sections(m, "loadmodel", f"({number}) 荷重モデルの作用の根拠", result.sections)
        number += 1
    cases = [case for case in result.basic_cases if case.bearings is not None]
    if cases:
        m.heading("bearings.heading", f"({number}) 荷重モデルの支承作用", 2)
        m.paragraph("bearings.note", "地震の向きに作用する水平力は，その向きを正負に含めて示す．"
                                     "M = N × アーム ＋ H × y（y は支承からの作用高さ）．")
        for index, case in enumerate(cases, 1):
            m.heading(f"bearings.{case.id}.heading", f"{index}) {case.name}（{case.id}，{INCREMENTS[case.increment]}）",
                      3)
            bearing_table(m, f"bearings.{case.id}", result.frame, case.bearings, arm)  # type: ignore[arg-type]
        number += 1
    if result.girder_weights is not None:
        origin, end = result.girder_weights
        m.heading("control.heading", f"({number}) 制御節点の重み", 2)
        m.paragraph("control.note", "制御節点の高さは，荷重モデルの増分の地震時ケースの直角方向の支承作用を起点側・終点側ごとに"
                                    "合計した値で，両側の桁の高さを重み付けて求める（決定65）．")
        m.equation("control.origin", "起点側", sub("H", "B"), with_unit(origin))
        m.equation("control.end", "終点側", sub("H", "C"), with_unit(end))
        number += 1
    self_weight_inertia(m, result.self_weight, f"({number}) 自重による地震時慣性力", self_weight)


def _combinations(m: Manuscript, result: GenericSeismicResult, chapter: str) -> None:
    m.heading("combination.heading", f"{chapter}.4 作用の組合せ", 1)
    m.paragraph("basic.caption", "基本Case", keep=True)
    rows: list[tuple[Any, ...]] = [("Case", "記号", "作用方向", "荷重種別", "荷　重　名　称")]
    for case in result.basic_cases:
        rows.append((str(case.number), case.id, Span(_ARROWS[case.direction]), Span(INCREMENTS[case.increment]),
                     case.name))
    m.table("basic", TableSpec((39.6, 64.8, 55.2, 63.6, 208.8), tuple(rows), (14.28,) * len(rows),
                               numeric=frozenset({0})))
    m.paragraph("combination.caption", "組合せCase", keep=True)
    rows = [("Case", "名称", Row(sub("α", "f"), "／", sub("ρ", "m"), gap=0), "作用方向", "基本Case", "地盤抵抗TYPE")]
    for combination in result.combinations:
        rows.append((str(combination.number), combination.name,
                     Span(f"{value(combination.alpha_f)}／{value(combination.rho_m)}"),
                     Span(_ARROWS[combination.direction]),
                     " + ".join(str(result.basic(case).number) for case in combination.cases),
                     str(combination.ground_resistance_type)))
    m.table("combination", TableSpec((39.6, 96, 55.2, 55.2, 130.8, 70.8), tuple(rows), (14.28,) * len(rows),
                                     numeric=frozenset({0, 5})))


def content(result: GenericSeismicResult, pier: PierInput) -> tuple[Unit, ...]:
    """The ordered manuscript, used by both the layout and the semantic tests."""
    train, chapter, frame_chapter, arm, self_weight = _STAGES[result.frame.direction]
    m = Manuscript(train.PREFIX)
    train._model(m, result, pier)  # type: ignore[arg-type]  # the frame only
    _actions(m, result, chapter, frame_chapter, arm, self_weight)
    diagrams_heading(m, f"{chapter}.3 荷重図")
    _combinations(m, result, chapter)
    return tuple(m.units)


def semantic_records(result: GenericSeismicResult, pier: PierInput) -> list[dict[str, str]]:
    return records(content(result, pier))


def build_generic_seismic(result: GenericSeismicResult, pier: PierInput) -> Document:
    """The whole manuscript as one GridLayoutPdf Document, without JRSNAP's pages."""
    return document(content(result, pier))


def render_generic_seismic(result: GenericSeismicResult, pier: PierInput, path: str | Path,
                           pages: Mapping[str, bytes]) -> Path:
    """The report with JRSNAP's データ確認図 before n.2 and its load diagram after n.3; atomically replaces *path*."""
    train = _STAGES[result.frame.direction][0]
    return render_with_pages(content(result, pier), train.INSERTIONS, pages, path)


__all__ = ["build_generic_seismic", "content", "render_generic_seismic", "semantic_records"]
