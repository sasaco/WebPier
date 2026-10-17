"""What each report leaves out, as the user decided (decision 41 of refactoring-decisions.md).

- 0610 has no load-diagram pages; its spring table and the spring column of
  the basic cases stay (Example2 08 p.8-1, p.8-9).
- 0710 and 0720 show no springs at all (no spring symbol in the frame figure,
  no Kv/Ks/Kr, no spring table or values), no load diagrams and no enlarged
  figure of the column bottom. Example2 10-7 / 11-7 print the JRSNAP node
  springs; the user's decision wins over the sample.

The expectations come from the input and the decision, never from the report code.
"""

from __future__ import annotations

import re

import pytest
from gridlayoutpdf import LayoutContext, Polyline, Text, measure_block

from frame_report_cases import CASES, TRANSVERSE_CASES, chain, transverse_chain

SPRING = re.compile(r"ばね|バネ|K[vsr]")


def records(module, *arguments) -> dict[str, str]:
    return {r["id"]: re.sub(r"\s+", "", r["text"]) for r in module.semantic_records(*arguments)}


def sections(found: dict[str, str]) -> list[str]:
    """The numbered sections (8.1, 10.2, ...) in order."""
    return [text for text in found.values() if re.fullmatch(r"\d+\.\d[^\d.].*", text)]


def figure_commands(units, key: str):
    from webpier.reporting.fonts import load_fonts
    from webpier.reporting.styles import REPORT_STYLE, report_profile

    figure = next(unit for unit in units if unit.key == key).value.block
    measured = measure_block(figure, LayoutContext(load_fonts(), report_profile(), REPORT_STYLE), 528)
    return [command for part in measured.parts for command in part.commands]


@pytest.mark.parametrize("case", list(CASES))
def test_0610_has_no_load_diagrams_and_keeps_its_springs(case: str):
    from webpier.reporting.stages import longitudinal

    pier, reaction, result, _ = chain(case)
    found = records(longitudinal, result, reaction, pier)
    assert not any("荷重図" in text for text in found.values())
    assert not any(unit.kind == "diagram" for unit in longitudinal.content(result, reaction, pier))
    assert sections(found) == ["8.1検討モデル", "8.2作用の計算", "8.3設計作用の組合せ"]
    assert "0610/model.springs" in found and found["0610/basic"].startswith("No荷重名称区分バネ")


@pytest.mark.parametrize("case", list(CASES))
def test_0710_shows_no_springs_and_no_load_diagrams(case: str):
    from webpier.reporting.stages import seismic_longitudinal

    pier, _, _, result = chain(case)
    found = records(seismic_longitudinal, result, pier)
    assert {key: text for key, text in found.items() if SPRING.search(text) or "荷重図" in text} == {}
    assert sections(found) == ["10.1検討モデル", "10.2作用の計算", "10.3作用の組合せ"]
    units = seismic_longitudinal.content(result, pier)
    assert not any(unit.kind == "diagram" for unit in units)
    drawn = figure_commands(units, "0710/model.figure")
    assert [c.text for c in drawn if isinstance(c, Text) and c.text in ("K", "v", "s", "r")] == []
    assert [c for c in drawn if isinstance(c, Polyline) and len(c.points) > 3] == []  # no zigzag, no coil


@pytest.mark.parametrize("case", list(TRANSVERSE_CASES))
def test_0720_shows_no_springs_no_load_diagrams_and_no_enlarged_column_bottom(case: str):
    from webpier.reporting.stages import seismic_transverse

    pier, _, _, result = transverse_chain(case)
    found = records(seismic_transverse, result, pier)
    assert {key: text for key, text in found.items() if SPRING.search(text) or "荷重図" in text} == {}
    assert sections(found) == ["11.1検討モデル", "11.2作用の計算", "11.3作用の組合せ"]
    units = seismic_transverse.content(result, pier)
    assert not any(unit.kind == "diagram" for unit in units)
    assert [unit.key for unit in units if unit.kind == "figure"] == ["0720/model.figure"]  # the frame only
    drawn = figure_commands(units, "0720/model.figure")
    assert [c.text for c in drawn if isinstance(c, Text) and c.text in ("K", "v", "s", "r")] == []
    assert [c for c in drawn if isinstance(c, Polyline) and len(c.points) > 3] == []
