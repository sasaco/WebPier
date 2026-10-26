"""場所打ち杭の配筋図 (decision 98, CONTEXT.md 配筋図): the side of the pile from its head and its sections.

The input is pile_seismic.json (杭径 1.0 m, D32 − 20 本, 純かぶり 100, 2D 区間 D16 1 組 ctc200, 第1区間 4.0 m D16 1 組
ctc300); the expected positions, counts and texts are hand calculation from it (芯かぶり 100 + 16 + 32／2 = 132). The 杭頭定着長
is the calculation's (calc.detailing.pile, tested there), which the figure draws.
"""

import io
import json
import re
from copy import deepcopy
from pathlib import Path

import ezdxf
import pytest

from webpier.calc.detailing.pile import pile_detailing
from webpier.core.errors import InputError
from webpier.export.drawing import FIGURES, drawing_dxf, drawing_figures, pile
from webpier.export.drawing.sheet import Sheet, Vec2
from webpier.inputs import parse_input

ROOT = Path(__file__).parents[2]
PILE = json.loads((ROOT / "tests" / "fixtures" / "inputs" / "pile_seismic.json").read_text(encoding="utf-8"))
BETAS = (("線路方向", 3.0), ("線路直角方向", 3.0))
CUTOFF = {"main_bars": {"diameter_mm": 25, "count": 16}, "hoops": {"diameter_mm": 13, "sets": 1, "pitch_mm": 300.0},
          "cutoff_length_mm": 3500.0}


def pier(**cutoff):
    data = deepcopy(PILE)
    data["鉄筋"]["杭"]["cutoff"].update(deepcopy(cutoff))
    return parse_input(data)


def figure(found):
    return pile.pile_figure(found, pile_detailing(found, BETAS))


def drawn(found):
    sheet = Sheet(50)
    pile.draw_pile(sheet, figure(found), Vec2(0, 0))
    return sheet.msp


def texts(msp) -> list[str]:
    return [entity.dxf.text for entity in msp.query("TEXT")]


def lines(msp, layer: str) -> set[tuple[float, float, float, float]]:
    return {(round(line.dxf.start.x, 1), round(line.dxf.start.y, 1), round(line.dxf.end.x, 1), round(line.dxf.end.y, 1))
            for line in msp.query(f'LINE[layer=="{layer}"]')}


def test_the_figure_has_the_zones_the_head_anchorage_and_the_section_at_the_head():
    found = figure(pier())
    assert (found.diameter, found.centre, found.length, found.cutoff) == (1000, 132, 6000, None)
    assert [(zone.name, zone.top, zone.bottom) for zone in found.zones] == [("2D区間", 0, 2000), ("第1区間", 2000, 6000)]
    assert [section.title for section in found.sections] == ["杭頭"]
    assert found.anchorage == pile_detailing(pier(), BETAS).anchorage.length.value


def test_the_side_has_the_outline_the_main_bars_from_the_anchorage_and_the_hoops_at_their_pitch():
    found = pier()
    anchorage = figure(found).anchorage
    msp = drawn(found)
    body = lines(msp, "躯体")
    assert {(-500.0, 0.0, -500.0, -6000.0), (500.0, 0.0, 500.0, -6000.0), (-500.0, -6000.0, 500.0, -6000.0)} <= body
    bars = lines(msp, "鉄筋")
    assert {(-368.0, float(anchorage), -368.0, -6000.0), (368.0, float(anchorage), 368.0, -6000.0)} <= bars
    hoops = sorted(abs(y) for x0, y, x1, _ in bars if (x0, x1) == (-368.0, 368.0))
    # the 2D zone 0, 200, …, 2000 (11) and the zone below it 2000, 2300, …, 5900 (14), 2000 drawn once
    assert hoops == sorted({float(200 * k) for k in range(11)} | {float(2000 + 300 * k) for k in range(14)})
    assert {"フーチング下面", "2D区間", "D16-1組 ctc200", "第1区間", "D16-1組 ctc300", "杭頭定着長", "杭頭", "D32-20本",
            "帯鉄筋 D16-1組 ctc200", "芯かぶり 132"} <= set(texts(msp))
    assert "段落し位置" not in texts(msp)


def test_a_cut_off_is_drawn_with_the_section_after_it():
    found = pier(**CUTOFF)
    assert figure(found).cutoff == 3500
    msp = drawn(found)
    assert {"段落し位置", "段落し後", "D25-16本", "帯鉄筋 D13-1組 ctc300"} <= set(texts(msp))
    # the line across the pile at the cut-off, 5 paper mm beyond each side at 1:50
    assert (-750.0, -3500.0, 750.0, -3500.0) in lines(msp, "引出線")


@pytest.mark.parametrize("path, value, message", [
    ("main_bars", {"diameter_mm": 25, "count": None}, "鉄筋.杭.cutoff.main_bars.count: 配筋図に必要です"),
    ("hoops", {"diameter_mm": None, "sets": 1, "pitch_mm": 300.0}, "鉄筋.杭.cutoff.hoops.diameter_mm: 配筋図に必要です"),
    ("cutoff_length_mm", None, "鉄筋.杭.cutoff.cutoff_length_mm: 値が必要です")])
def test_a_blank_item_of_the_cut_off_is_an_input_error(path, value, message):
    with pytest.raises(InputError, match=re.escape(message)):
        figure(pier(**{**CUTOFF, path: value}))


def test_the_files_have_the_pile_only_with_its_detailing():
    found = pier(**CUTOFF)
    detailing = pile_detailing(found, BETAS)
    assert FIGURES[-1] == "杭" and "杭" not in drawing_figures(found) and "杭" in drawing_figures(found, detailing)
    data = drawing_dxf(found, detailing)
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    titles = [text for text in texts(doc.modelspace()) if text.startswith("杭（杭頭から下の側面と断面）　1:")]
    assert len(titles) == 1 and not doc.audit().has_errors
    assert data == drawing_dxf(found, detailing) and data != drawing_dxf(found)
