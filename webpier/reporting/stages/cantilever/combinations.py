"""13.2 設計作用の組合せ of one cantilever (Example2 13-30 to 13-37), and the governing cases of both (decision 59).

The combination tables are turned on the page as the sample prints them (one rotated table per page): the cases
1〜9 and 10〜18 of 安全性（破壊） and the cases 19〜31, for Md, Vd and Mt. Each case cell holds the factor over the
factored value; the last columns are the total, the performance item, the remark and the loading. The summary of the
three (the sample's last tables) lists each case's Md, Vd and Mt without the factors, upright, and comes first (a
rotated table takes a page of its own). The table of the governing cases lists, for each row of Capacita's force
table and each check, the side, the case and its Md, Vd and Mt.
"""

from __future__ import annotations

from collections.abc import Sequence

from ....calc.cantilever import CantileverResult, Side, SideResult
from ....calc.cantilever.combinations import COLUMNS, CaseResult, LimitState, Quantity
from ....core.printed import Printed
from ....inputs import PierInput
from ...numbers import printed
from ..reaction.manuscript import CHAPTER, SECTION, SUBSECTION, CellSpec, Manuscript, TableSpec, cells

STATES = {LimitState.SAFETY: "安全性\n(破壊)", LimitState.RESTORABILITY: "復旧性\n地震時以外",
          LimitState.RESTORABILITY_EQ: "復旧性\n地震時", LimitState.DURABILITY: "耐久性",
          LimitState.FATIGUE: "安全性\n(疲労)"}
QUANTITIES = {Quantity.BENDING: ("曲げモーメント", "Md", "kN・m"), Quantity.SHEAR: ("せん断力", "Vd", "kN"),
              Quantity.TORSION: ("ねじりモーメント", "Mt", "kN・m")}
# The column widths of a rotated table in grid columns of its turned grid (15.48 pt each; 46 of them make its height
# on the page, of the page's 47 rows): the case, the nine action columns, the result, the performance item, the
# remark and the loading. Each case takes two grid rows (16.08 pt each on the page), so that the 13 cases of 19〜31
# and the header take 28 of the page's 30 columns.
CASE_WIDTH, ACTION_WIDTH, RESULT_WIDTH, STATE_WIDTH, REMARK_WIDTH, NOTE_WIDTH = 2, 3, 3, 4, 4, 5
WIDE_ACTIONS = {"LR+B": 4}
SUMMARY_RESULT_WIDTH = 4  # the upright summary (grid columns of the page)
GROUPS = ((1, 9), (10, 18), (19, 31))


def _value_of(case: CaseResult, quantity: Quantity) -> Printed:
    return case.md if quantity is Quantity.BENDING else case.n if quantity is Quantity.SHEAR else case.mt


def _contribution_text(case: CaseResult, column: str, quantity: Quantity) -> str:
    part = case.contribution(column)
    if part is None:
        return ""
    value = part.md if quantity is Quantity.BENDING else part.n if quantity is Quantity.SHEAR else part.mt
    return f"{part.factor}\n{printed(value)}"


def _tail(case: CaseResult) -> tuple[CellSpec, CellSpec, CellSpec]:
    definition = case.definition
    return (CellSpec(STATES[definition.state], align="center"), CellSpec(definition.remark, align="center"),
            CellSpec(definition.note, align="center"))


def _table(cases: Sequence[CaseResult], quantity: Quantity) -> TableSpec:
    """The rotated table of one quantity: the factor over the factored value of each action, the total."""
    _, symbol, unit = QUANTITIES[quantity]
    head = [(CellSpec("Case\nNo.", rowspan=2, align="center"), CellSpec("組合せ", colspan=len(COLUMNS), align="center"),
             CellSpec(f"{symbol}\n({unit})", rowspan=2, align="center"),
             CellSpec("性能項目", rowspan=2, align="center"), CellSpec("備考", rowspan=2, align="center"),
             CellSpec("摘要", rowspan=2, align="center")),
            tuple(CellSpec(column, align="center") for column in COLUMNS)]
    rows = [(CellSpec(str(case.number), align="center"),
             *(CellSpec(_contribution_text(case, column, quantity), align="right") for column in COLUMNS),
             *cells(_value_of(case, quantity)), *_tail(case)) for case in cases]
    widths = (CASE_WIDTH, *(WIDE_ACTIONS.get(column, ACTION_WIDTH) for column in COLUMNS), RESULT_WIDTH, STATE_WIDTH,
              REMARK_WIDTH, NOTE_WIDTH)
    return TableSpec(widths, (*head, *rows), header_rows=2, numeric_columns=tuple(range(1, len(COLUMNS) + 2)))


def _summary(cases: Sequence[CaseResult]) -> TableSpec:
    """Md, Vd and Mt of every case, upright (the factors are in the tables above)."""
    head = [(CellSpec("Case\nNo.", rowspan=2, align="center"), CellSpec("設計作用", colspan=3, align="center"),
             CellSpec("性能項目", rowspan=2, align="center"), CellSpec("備考", rowspan=2, align="center"),
             CellSpec("摘要", rowspan=2, align="center")),
            tuple(CellSpec(f"{QUANTITIES[q][1]}\n({QUANTITIES[q][2]})", align="center") for q in Quantity)]
    rows = [(CellSpec(str(case.number), align="center"), *cells(case.md, case.n, case.mt), *_tail(case))
            for case in cases]
    return TableSpec((CASE_WIDTH, *([SUMMARY_RESULT_WIDTH] * 3), STATE_WIDTH, REMARK_WIDTH, NOTE_WIDTH), (*head, *rows),
                     header_rows=2, numeric_columns=(1, 2, 3))


def section(m: Manuscript, side: Side, side_name: str, result: SideResult, pier: PierInput) -> None:
    key = side.name.lower()
    m.heading(f"{key}.combinations.heading", f"13.2 設計作用の組合せ（{side_name}）", SECTION)
    # The summary first: a rotated table fills a page of its own, which the heading could not share.
    m.paragraph(f"{key}.combinations.summary.title", "設計作用のまとめ", SUBSECTION)
    m.table(f"{key}.combinations.summary", _summary(result.cases), SUBSECTION)
    for quantity in Quantity:
        for first, last in GROUPS:
            cases = [case for case in result.cases if first <= case.number <= last]
            m.rotated_table(f"{key}.combinations.{quantity.name.lower()}.{first}", _table(cases, quantity), CHAPTER)


def adopted(m: Manuscript, result: CantileverResult, names: dict[Side, str]) -> None:
    """The governing case of either cantilever for each row of Capacita's force table and each check."""
    m.heading("adopted.heading", "(3) 照査に用いる設計作用", SUBSECTION)
    rows = [(CellSpec("照査", align="center"), CellSpec("項目", align="center"), CellSpec("側", align="center"),
             CellSpec("Case", align="center"), CellSpec("Md\n(kN・m)", align="center"), CellSpec("Vd\n(kN)", align="center"),
             CellSpec("Mt\n(kN・m)", align="center"))]
    previous = None
    for selection in result.selections:
        title = "" if selection.title == previous else selection.title
        previous = selection.title
        rows.append((CellSpec(title, align="left"), CellSpec(selection.quantity.value, align="center"),
                     CellSpec(names[selection.side], align="center"), CellSpec(str(selection.case.number), align="center"),
                     *cells(selection.md, selection.vd, selection.mt)))
    m.table("adopted.table", TableSpec((10, 3, 2, 2, 4, 3, 4), tuple(rows), header_rows=1, numeric_columns=(4, 5, 6)),
            SUBSECTION)
