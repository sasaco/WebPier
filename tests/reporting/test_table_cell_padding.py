"""The table cell clearance on the common grid: Excel's cell padding plus half a medium rule.

The reference's clearances (6.93 pt in 0600, 4.05 pt in the combination tables) are not kept: a cell of the grid
Excel holds its text Excel's padding (gridlayoutpdf.equations.EXCEL_CELL_PADDING_PT) from each edge, and a number
must not touch the medium frame either. The 0600 and 0500 tables are measured from our own PDFs: the gap between a
right-aligned number's advance box and the centre of the vertical rule after it.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

import pymupdf
import pytest

NUMBER = re.compile(r"-?[\d,]*\d(?:\.\d+)?")


def number_clearances(page: pymupdf.Page) -> Counter[float]:
    """Gaps (pt, 2 decimals) from right-aligned 10 pt numbers to the centre of the next vertical rule beside them."""
    rules = [((drawing["rect"].x0 + drawing["rect"].x1) / 2, drawing["rect"].y0, drawing["rect"].y1)
             for drawing in page.get_drawings() if drawing["rect"].height > 10 and drawing["rect"].width < 2]
    found: Counter[float] = Counter()
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                chars = [char for char in span["chars"] if not char["c"].isspace()]
                text = "".join(char["c"] for char in chars)
                if abs(span["size"] - 10) > .05 or not chars or not NUMBER.fullmatch(text):
                    continue
                right = chars[-1]["origin"][0] + (chars[-1]["bbox"][2] - chars[-1]["bbox"][0])
                baseline = chars[-1]["origin"][1]
                gaps = [x - right for x, top, bottom in rules if 0 <= x - right < 8 and top <= baseline - 3 <= bottom]
                if gaps:
                    found[round(min(gaps), 2)] += 1
    return found


def test_the_cell_padding_is_excel_s_with_room_for_a_medium_rule():
    from gridlayoutpdf import BorderStyle
    from gridlayoutpdf.equations import EXCEL_CELL_PADDING_PT
    from webpier.reporting.tables import CELL_PADDING, INNER, OUTER

    assert (OUTER, INNER) == (BorderStyle.MEDIUM, BorderStyle.HAIR)
    assert CELL_PADDING.left == CELL_PADDING.right == 3.0
    assert CELL_PADDING.right >= EXCEL_CELL_PADDING_PT + BorderStyle.MEDIUM.thickness / 2


@pytest.mark.parametrize("stage", ["0500", "0600"])
def test_our_tables_keep_the_cell_padding_before_a_rule(stage: str, tmp_path: Path):
    from gridlayoutpdf import BorderStyle
    from webpier.reporting.tables import CELL_PADDING

    if stage == "0500":
        from foundation_report_cases import case as foundation_case
        from webpier.reporting.stages.foundation import render_foundation

        path = render_foundation(*foundation_case("current"), tmp_path / "0500.pdf")
    else:
        from reaction_report_cases import case
        from webpier.reporting.stages.reaction import render_reaction

        path = render_reaction(*case("current"), tmp_path / "0600.pdf")
    with pymupdf.open(path) as pdf:
        counts = sum((number_clearances(page) for page in pdf), Counter())
    assert counts, stage
    # 3 pt from a hair rule's centre (on the column boundary); the medium frame lies inside the table, its centre
    # half its thickness in from the boundary, so a number before it is 2.5 pt from that centre.
    assert counts.most_common(1)[0][0] == pytest.approx(CELL_PADDING.right, abs=.02)
    assert set(counts) <= {CELL_PADDING.right, CELL_PADDING.right - BorderStyle.MEDIUM.thickness / 2}
