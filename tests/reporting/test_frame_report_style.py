"""The 0610/0620/0710/0720 reports follow the reference look (.claude/docs/Example橋脚/output 0610, 0620):

- no input-sheet cell symbol (B1..B9, H1..H6, W3..W9, df1, df2) is printed; they are not defined in the
  report (W1/W2 are the wind loads of the design standard and stay);
- formulas are written inline: no stacked Fraction in any unit;
- the 鉛直力・アーム・モーメント tables (and the other tables closed by a 合計 row) are open: no frame, no
  vertical rule, no rule under the header, one medium rule across the table above 合計 (0610 p4; the reference's
  0.96 pt rule is GridLayoutPdf's medium border);
- a coefficient table printed in parts (8-10, 9-14) holds in its parts every cell of the whole table, the cases
  again in each part, and no part is wider than the body.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from gridlayoutpdf import BorderStyle, Fraction

from frame_report_cases import CASES, TRANSVERSE_CASES, chain, transverse_chain

INPUT_SYMBOL = re.compile(r"(?<![A-Za-z])([BH][1-9]|W[3-9])(?!\d)|df[12]")


def _units(stage: str, case: str) -> tuple[Any, ...]:
    from webpier.reporting.stages import longitudinal, seismic_longitudinal, seismic_transverse, transverse

    if stage in ("0610", "0710"):
        pier, reaction, result, seismic = chain(case)
        return (longitudinal.content(result, reaction, pier) if stage == "0610"
                else seismic_longitudinal.content(seismic, reaction, pier))
    pier, reaction, result, seismic = transverse_chain(case)
    return (transverse.content(result, reaction, pier) if stage == "0620"
            else seismic_transverse.content(seismic, reaction, pier))


PARAMETERS = ([(stage, case) for stage in ("0610", "0710") for case in CASES]
              + [(stage, case) for stage in ("0620", "0720") for case in TRANSVERSE_CASES])


def _nodes(item: Any) -> Iterator[Any]:
    """Every node of a unit value: tuples, rows, scripts, equations, table cells and dataclass fields."""
    yield item
    if isinstance(item, (tuple, list)):
        for part in item:
            yield from _nodes(part)
    elif dataclasses.is_dataclass(item) and not isinstance(item, type):
        for found in dataclasses.fields(item):
            yield from _nodes(getattr(item, found.name))


@pytest.mark.parametrize(("stage", "case"), PARAMETERS)
def test_no_input_sheet_symbol_and_no_stacked_fraction(stage: str, case: str):
    from webpier.reporting.stages.frame_report import FigureSpec, semantic_records

    units = _units(stage, case)
    for record in semantic_records(units):
        assert not INPUT_SYMBOL.search(record["text"]), record
    for unit in units:
        if isinstance(unit.value, FigureSpec):
            continue  # a drawing, not a formula
        assert not any(isinstance(node, Fraction) for node in _nodes(unit.value)), unit.key


@pytest.mark.parametrize(("stage", "case"), PARAMETERS)
def test_every_table_closed_by_a_total_row_is_open(stage: str, case: str):
    from webpier.reporting.stages.frame_report import TableSpec

    tables = [unit for unit in _units(stage, case) if isinstance(unit.value, TableSpec)]
    totals = [unit for unit in tables if unit.value.rows[-1][0] == "合計"]
    assert totals
    for unit in tables:
        assert unit.value.open == (unit in totals), unit.key


def test_an_open_table_draws_one_rule_above_its_total(tmp_path: Path):
    from webpier.reporting import document
    from webpier.reporting.stages.frame_report import table_block
    from webpier.reporting.styles import columns_pt
    from webpier.reporting.stages.longitudinal import content

    pier, reaction, result, _ = chain("current")
    spec = next(unit.value for unit in content(result, reaction, pier) if unit.key == "0610/fixed.top")
    path = document.report(table_block(spec, "t"), document.paragraph("本文")).render(tmp_path / "t.pdf",
                                                                                    invariant=True)
    with pymupdf.open(path) as pdf:
        page = pdf[0]
        drawings = page.get_drawings()
        assert len(drawings) == 1 and [item[0] for item in drawings[0]["items"]] == ["l"]
        (rule,) = drawings
        assert rule["width"] == pytest.approx(BorderStyle.MEDIUM.stroke_width, abs=1e-3)
        rect = rule["rect"]
        assert rect.height == pytest.approx(0, abs=1e-3)
        assert rect.width == pytest.approx(columns_pt(sum(spec.widths)), abs=1)  # the whole table width
        baselines = {span["text"].strip(): span["origin"][1] for block in page.get_text("dict")["blocks"]
                     for line in block.get("lines", []) for span in line["spans"] if span["text"].strip()}
        last_label = "はり"  # the row above 合計
        assert baselines[last_label] < rect.y0 < baselines["合計"]


# 0610: 38 combinations (decision 102), the ten of 安全性 halved so that no part is too narrow for its heading; 0620:
# 25 (decision 106)
@pytest.mark.parametrize(("stage", "case", "parts"), [("0610", "current", 6), ("0620", "curve", 4), ("0620", "no_snow", 4)])
def test_a_coefficient_table_in_parts_holds_every_cell_of_the_whole_table(stage: str, case: str, parts: int):
    from webpier.reporting.stages.frame_report import FigureSpec, TableParts, plain
    from webpier.reporting.styles import BODY_COLUMNS

    (unit,) = [unit for unit in _units(stage, case) if unit.key.endswith("/combination")]
    assert isinstance(unit.value, FigureSpec) and isinstance(unit.value.block, TableParts)
    specs = unit.value.block.specs
    assert len(specs) == parts and all(spec.left + sum(spec.widths) <= BODY_COLUMNS for spec in specs)
    cases = [row[:3] for row in specs[0].rows[4:]]
    assert all([row[:3] for row in spec.rows[4:]] == cases for spec in specs)  # the cases again in each part
    numbers = [cell for spec in specs for cell in spec.rows[3]]
    assert numbers == [str(number) for number in range(1, len(numbers) + 1)]  # every combination once, in order
    # the rows of the whole table (its record ends with them): each case with its coefficients of every part
    rows = "".join(plain(case) + "".join(plain(spec.rows[4 + index][3:]) for spec in specs)
                   for index, case in enumerate(cases))
    assert plain(unit.value).endswith(rows)
