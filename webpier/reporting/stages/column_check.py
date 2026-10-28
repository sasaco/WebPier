"""0611 線路方向の照査 (8.5〜) and 0621 直角方向の照査 (9.5〜): 柱の断面照査 (decisions 48, 121; ADR-0008).

The report is Capacita's: the pages of its sections, cut by the page ranges Capacita returns (``stages.insertion``
names them by section id), joined in report order. WebPier lays out nothing of it, and it has no grid Excel workbook
(decision 121; owner 2026-10-28). The WDJ asks Capacita for its commentary (``calc.print_commentary_checked``):
before the result of each section Capacita prints the heading of its group and its explanation (the check formulas,
the symbols, the flowchart of the flexural crack check), within the section's pages. Capacita numbers the group
headings from n.5 (``Chapter.commentary``: ``run-rc --commentary-chapter n --commentary-first-section 5``), n the
chapter of the stage (8 for 0611, 9 for 0621; the two directions differ by nothing else), continuing the load chapter
(8.1〜8.4, 9.1〜9.4); the chapter heading (§8, §9) is not printed. Only the groups Capacita prints take a number, in
order and without a gap: n.5 the section force list, n.6 安全性（破壊）, n.7 耐久性, n.8 使用性 (the appearance
check), n.9 使用性（損傷）, n.10 最小鉄筋量及び最大鉄筋量 when every group is printed. A check Capacita skipped for zero
section forces (pipeline.capacita.SKIPPED; the result JSON's ``skipped_sections``) has nothing in the report, and a
group with nothing printed takes no number (Example2 across the track: 使用性 is 9.8 no more, 9.8 is 使用性（損傷）).

0400 refers to the sections of 最小鉄筋量及び最大鉄筋量 and 耐久性 by the numbers Capacita gave them
(``ColumnCheckResult.headings``, set once Capacita has checked the column; ``reference``), and the foundation check of
the same direction follows the last of them (``following_section``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ...calc.column_check import ColumnCheckResult
from ..assembly import join

FIRST_SECTION = 5  # n.5 断面力の総括, after the load chapter's n.1〜n.4
# The section the foundation check takes when the column check of its direction is not numbered (not checked in the
# same generation): after n.10, the last when every group is printed (decision 73).
FOLLOWING_ALL = 11
# The sections 0400 refers to (reporting.stages.detailing, ADR-0012): each carries the heading of its group.
REBAR_AMOUNT, DURABILITY = "bending_rebar_amount", "bending_durability"


@dataclass(frozen=True)
class Chapter:
    """Where a stage's column check stands in the report: the chapter of its section numbers."""

    number: int  # n of n.5 …, continuing the stage's load chapter

    @property
    def commentary(self) -> tuple[int, int]:
        """The numbers of Capacita's commentary headings (chapter, first section): ``run-rc --commentary-chapter
        --commentary-first-section`` (pipeline.capacita.check_column)."""
        return self.number, FIRST_SECTION


LONGITUDINAL = Chapter(8)  # after 0610 (8.1 〜 8.4)
TRANSVERSE = Chapter(9)  # after 0620 (9.1 〜 9.4)


def reference(result: ColumnCheckResult | None, section: str) -> str | None:
    """The number of the heading of the group of *section* in Capacita's report of *result* ("8.10"), or None: the
    column check not made in the same generation (``headings`` unset), the section not printed, or printed without a
    heading of its own."""
    if result is None or result.headings is None:
        return None
    return result.headings.get(section)


def following_section(result: ColumnCheckResult | None) -> int:
    """The section number after the last group Capacita numbered in the report of *result* (8.11 after 8.10), or
    FOLLOWING_ALL when it is not numbered."""
    numbers = [int(heading.split(".")[1]) for heading in (result.headings or {}).values() if heading] \
        if result is not None else []
    return max(numbers) + 1 if numbers else FOLLOWING_ALL


def render_column_check(result: ColumnCheckResult, path: str | Path, pages: Mapping[str, bytes]) -> Path:
    """The report: Capacita's pages of each section of *result* in report order (``pages``: the pages of each section
    by its id, cut by ``assembly.page_range``; a section Capacita skipped for zero forces has none); atomically
    replaces *path*. The pages are Capacita's own bytes (decision 48)."""
    if unknown := sorted(set(pages) - set(result.sections)):
        raise ValueError(f"柱の断面照査にない節のページです: {', '.join(unknown)}")
    if result.sections[0] not in pages:  # the section force list: Capacita never skips it
        raise ValueError(f"差し込むページ {result.sections[0]} がありません")
    return join([pages[section] for section in result.sections if section in pages], path)
