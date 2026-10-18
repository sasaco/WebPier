"""The 0610/0620/0710/0720 reports follow the reference look (.claude/docs/Example橋脚/output 0610, 0620):

- no input-sheet cell symbol (B1..B9, H1..H6, W3..W9, df1, df2) is printed; they are not defined in the
  report (W1/W2 are the wind loads of the design standard and stay);
- formulas are written inline: no stacked Fraction in any unit;
- the 鉛直力・アーム・モーメント tables (and the other tables closed by a 合計 row) are open: no frame, no
  vertical rule, no rule under the header, one 0.96 pt rule across the table above 合計 (0610 p4).
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from gridlayoutpdf import Fraction

from frame_report_cases import CASES, TRANSVERSE_CASES, chain, transverse_chain

INPUT_SYMBOL = re.compile(r"(?<![A-Za-z])([BH][1-9]|W[3-9])(?!\d)|df[12]")


def _units(stage: str, case: str) -> tuple[Any, ...]:
    from webpier.reporting.stages import longitudinal, seismic_longitudinal, seismic_transverse, transverse

    if stage in ("0610", "0710"):
        pier, reaction, result, seismic = chain(case)
        return (longitudinal.content(result, reaction, pier) if stage == "0610"
                else seismic_longitudinal.content(seismic, pier))
    pier, reaction, result, seismic = transverse_chain(case)
    return (transverse.content(result, reaction, pier) if stage == "0620"
            else seismic_transverse.content(seismic, pier))


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
    from webpier.reporting.stages.frame_report import FigureSpec, DiagramSpec, semantic_records

    units = _units(stage, case)
    for record in semantic_records(units):
        assert not INPUT_SYMBOL.search(record["text"]), record
    for unit in units:
        if isinstance(unit.value, (FigureSpec, DiagramSpec)):
            continue  # drawings, not formulas
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
        assert rule["width"] == pytest.approx(.96, abs=1e-3)
        rect = rule["rect"]
        assert rect.height == pytest.approx(0, abs=1e-3)
        assert rect.width == pytest.approx(sum(spec.widths), abs=1)  # the whole table width (ends inset .48)
        baselines = {span["text"].strip(): span["origin"][1] for block in page.get_text("dict")["blocks"]
                     for line in block.get("lines", []) for span in line["spans"] if span["text"].strip()}
        last_label = "はり"  # the row above 合計
        assert baselines[last_label] < rect.y0 < baselines["合計"]
