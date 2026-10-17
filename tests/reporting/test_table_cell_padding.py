"""The table cell clearance of the shared table style, measured in the reference PDFs.

The appearance fixture records rule widths and row heights but no cell clearance, so it is
measured here from the reference sample itself (never from our output): the gap between a
right-aligned number's advance box and the ink of the thin rule after it. Our 0600 tables
are then measured the same way and must show the same gap.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf
import pytest

ROOT = Path(__file__).parents[2]
REFERENCE = ROOT / ".claude" / "docs" / "Example橋脚" / "output"
_spec = importlib.util.spec_from_file_location("reporting_appearance_measure_padding",
                                               ROOT / "scripts" / "reporting_appearance.py")
assert _spec is not None and _spec.loader is not None
measure = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = measure
_spec.loader.exec_module(measure)

NUMBER = re.compile(r"-?[\d ]*\d(?:\.\d+)?")
THIN = 0.2  # a 0.12 pt rule (the thick rules are 0.96 pt)


def number_clearances(page: pymupdf.Page) -> Counter[float]:
    """Gaps (pt, 2 decimals) from right-aligned 9.9 pt numbers to the next thin vertical rule's ink."""
    rules = [rule for rule in measure.native_rules(page) if rule.axis == "v" and rule.width < THIN]
    found: Counter[float] = Counter()
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                chars = [char for char in span["chars"] if not char["c"].isspace()]
                text = "".join(char["c"] for char in chars)
                if span["size"] < 9 or not chars or not NUMBER.fullmatch(text):
                    continue
                right, baseline = chars[-1]["bbox"][2], chars[-1]["origin"][1]
                gaps = [rule.coordinate - rule.width / 2 - right for rule in rules
                        if rule.start <= baseline - 3 <= rule.end and 0 <= rule.coordinate - right < 15]
                if gaps:
                    found[round(min(gaps), 2)] += 1
    return found


def reference_clearance(name: str, *pages: int) -> float:
    with pymupdf.open(REFERENCE / name) as pdf:
        counts = sum((number_clearances(pdf[page - 1]) for page in pages), Counter())
    return counts.most_common(1)[0][0]


def test_the_reaction_tables_use_the_clearance_of_the_reference_0600_tables():
    from webpier.reporting.tables import REACTION_CELL_PADDING

    clearance = reference_clearance("0600_上部工反力.pdf", 12, 32, 37)
    assert clearance == pytest.approx(6.93, abs=.005)
    # The padding is measured from the rule centre: half the thin rule further.
    assert REACTION_CELL_PADDING.right == pytest.approx(clearance + .06, abs=.01)
    assert REACTION_CELL_PADDING.left == REACTION_CELL_PADDING.right


def test_the_soil_table_of_0500_uses_the_same_clearance_as_0600(tmp_path: Path):
    from foundation_report_cases import case as foundation_case
    from webpier.reporting.stages.foundation import render_foundation

    reference = reference_clearance("0500_直接基礎.pdf", 1)
    assert reference == reference_clearance("0600_上部工反力.pdf", 12, 32, 37)
    path = render_foundation(*foundation_case("current"), tmp_path / "0500.pdf")
    with pymupdf.open(path) as pdf:
        assert number_clearances(pdf[0]).most_common(1)[0][0] == pytest.approx(reference, abs=.1)


def test_the_default_cell_uses_the_clearance_of_the_reference_combination_tables():
    from webpier.reporting.tables import CELL_PADDING

    for name, page in (("0610_線路方向荷重.pdf", 10), ("0620_直角方向荷重.pdf", 17)):
        clearance = reference_clearance(name, page)
        assert clearance == pytest.approx(4.05, abs=.005), name
        assert CELL_PADDING.right == pytest.approx(clearance + .06, abs=.01)
    assert CELL_PADDING.left == CELL_PADDING.right


def test_our_0600_tables_show_the_reference_clearance(tmp_path: Path):
    sys.path.insert(0, str(Path(__file__).parent))
    from reaction_report_cases import case
    from webpier.reporting.stages.reaction import render_reaction

    path = render_reaction(*case("current"), tmp_path / "0600.pdf")
    with pymupdf.open(path) as pdf:
        counts = sum((number_clearances(page) for page in pdf), Counter())
    reference = reference_clearance("0600_上部工反力.pdf", 12, 32, 37)
    assert counts.most_common(1)[0][0] == pytest.approx(reference, abs=.1)
