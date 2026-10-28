"""0900 片持ち梁: §13. 片持ち梁の照査, 13.1 応答値の算定 and 13.2 設計作用の組合せ (decision 59; Example2 13-1 to 13-37).

The report is authored with the 0600 manuscript (reporting.stages.reaction.manuscript, prefix 0900/) and laid out by
its layout: formula lines whose numbers a reader recomputes, the 0600 tables, the loading figure of 0600, and the
combination tables turned on the page as the sample prints them (QuarterTurn). The report begins with the chapter
heading 「§13. 片持ち梁の照査」 (decision 117; the sample's is 「§13 片持ち梁」). 13.1 (1) and (2) hold for both cantilevers and are printed once; (3) 片持梁の自重, (4) 荷重設計
の集計 and 13.2 are printed for the left cantilever, then for the right one, and 13.2 ends with the table of the
governing cases of either side for each check (decision 59). Every number is a Printed value of the CantileverResult,
of the 0600 result it was calculated from, or of the input; nothing is calculated here.
"""

from __future__ import annotations

from pathlib import Path

from gridlayoutpdf import Document

from ....calc.cantilever import CantileverResult, Side
from ....calc.reaction import ReactionResult
from ....inputs import PierInput
from ..reaction.layout import document
from ..reaction.manuscript import CHAPTER, SECTION, Manuscript, Unit, plain
from . import combinations, horizontal, summary, vertical

PREFIX = "0900/"
SIDES = {Side.LEFT: "左側", Side.RIGHT: "右側"}
# The derivations' "=" a column further left than 0600's: their widest label (最大応答震度) is shorter than 0600's
# T − 1/2μ・Rm, and "G1桁 = M × x / ΣXi²" then keeps its result on its line (13-11).
WIDE_EQUAL = 11
CHAPTER_TITLE = "§13. 片持ち梁の照査"  # decision 117, as 0800's §12; 0910 continues the chapter from 13.3


def content(result: CantileverResult, reaction: ReactionResult, pier: PierInput) -> tuple[Unit, ...]:
    """One ordered manuscript, used by both the layout and the semantic tests."""
    m = Manuscript(prefix=PREFIX, wide_equal=WIDE_EQUAL)
    m.heading("title", CHAPTER_TITLE, CHAPTER)
    m.heading("section.heading", "13.1 応答値の算定", SECTION)
    vertical.section(m, result, reaction, pier)
    horizontal.section(m, result, reaction, pier)
    for side, side_result in result.sides.items():
        summary.section(m, side, SIDES[side], side_result, result, reaction)
    for side, side_result in result.sides.items():
        combinations.section(m, side, SIDES[side], side_result, pier)
    combinations.adopted(m, result, SIDES)
    return tuple(m.units)


def semantic_records(result: CantileverResult, reaction: ReactionResult, pier: PierInput) -> list[dict[str, str]]:
    return [{"id": unit.identifier, "text": plain(unit.value)} for unit in content(result, reaction, pier)]


def build_cantilever(result: CantileverResult, reaction: ReactionResult, pier: PierInput) -> Document:
    return document(content(result, reaction, pier))


def render_cantilever(result: CantileverResult, reaction: ReactionResult, pier: PierInput, path: str | Path) -> Path:
    """Lay out completely, then atomically replace *path*; the same input gives the same bytes."""
    return build_cantilever(result, reaction, pier).render(path, invariant=True)


def grid_documents(result: CantileverResult, reaction: ReactionResult, pier: PierInput) -> tuple[Document, ...]:
    """The documents of the report WebPier lays out (its grid Excel workbook): the whole report."""
    return (build_cantilever(result, reaction, pier),)


__all__ = ["PREFIX", "SIDES", "build_cantilever", "content", "grid_documents", "render_cantilever",
           "semantic_records"]
