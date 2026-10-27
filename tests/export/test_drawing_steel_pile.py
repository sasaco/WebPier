"""鋼管ソイルセメント杭の配筋図 (decision 99, CONTEXT.md 配筋図): the head joint from the side and at the head, and the
杭先端部.

The input is the sample Example橋脚4's pile (D 800, t 18, Dsc 1000, D38 − 16 本 at 75 mm) on pile.json; the sizes are
0400's (calc.detailing.steel_pile, tested there) and the expected positions are hand calculation from them: the pipe's
faces at 400 and 400 − 18 = 382, the soil cement at 500, the anchor bars at 400 − 75 = 325, the footing's base 50 below
the top of the pipe, the hook's centre line radius 152 − 38／2 = 133.
"""

import io
import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import ezdxf

from webpier.calc.detailing.steel_pile import steel_pile_detailing
from webpier.export.drawing import drawing_dxf, drawing_figures, steel_pile
from webpier.export.drawing.sheet import Sheet, Vec2
from webpier.inputs import parse_input
from example4_support import EXAMPLE4_INPUT

FIXTURES = Path(__file__).parents[1] / "fixtures" / "inputs"
PILE = json.loads((FIXTURES / "pile.json").read_text(encoding="utf-8"))
EXAMPLE4 = json.loads(EXAMPLE4_INPUT.read_text(encoding="utf-8"))


def pier(**steel):
    data = deepcopy(PILE)
    data["下部構造"]["基礎形式"] = "鋼管ソイルセメント杭"
    data["杭基礎"]["鋼管ソイルセメント杭"] = deepcopy(EXAMPLE4["杭基礎"]["鋼管ソイルセメント杭"])
    data["杭基礎"]["鋼管ソイルセメント杭"]["結合部"]["粗骨材の最大寸法"] = 25.0
    data["杭基礎"]["鋼管ソイルセメント杭"].update(steel)
    data["鉄筋"]["フーチング"]["concrete_strength_mpa"] = 27.0
    return parse_input(data)


def figure(found):
    return steel_pile.steel_pile_figure(steel_pile_detailing(found))


def drawn(found):
    sheet = Sheet(25)
    steel_pile.draw_steel_pile(sheet, figure(found), Vec2(0, 0))
    return sheet.msp


def texts(msp) -> list[str]:
    return [entity.dxf.text for entity in msp.query("TEXT")]


def lines(msp, layer: str) -> set[tuple[float, float, float, float]]:
    return {(round(line.dxf.start.x, 1), round(line.dxf.start.y, 1), round(line.dxf.end.x, 1), round(line.dxf.end.y, 1))
            for line in msp.query(f'LINE[layer=="{layer}"]')}


def test_the_figure_has_the_sizes_of_0400():
    found = figure(pier())
    assert (found.diameter, found.thickness, found.soil_cement, found.centroid, found.hook) == (800, 18, 1000, 75, 152)
    assert (found.l1, found.filling, found.length, found.rib_size) == (950, 1550, 2800, (16, 32))
    assert found.ribs == (Decimal(200), Decimal(450))
    assert found.tip_steps == (Decimal(300), Decimal(550), Decimal(800), Decimal(1050))
    assert (found.margin, found.penetration, found.embedment) == (500, 1200, 1000)


def test_the_head_has_the_pipe_the_anchor_bars_the_hoops_and_the_ribs():
    msp = drawn(pier())
    body = lines(msp, "躯体")
    assert {(-400.0, 0.0, -400.0, -1850.0), (382.0, 0.0, 382.0, -1850.0), (500.0, -50.0, 500.0, -1850.0),
            (-382.0, -1550.0, 382.0, -1550.0)} <= body
    bars = lines(msp, "鉄筋")
    assert {(-325.0, 817.0, -325.0, -1317.0), (325.0, 817.0, 325.0, -1317.0)} <= bars  # 950 − 133, −(1450 − 133)
    across = sorted(y for x0, y, x1, _ in bars if (x0, x1) == (-325.0, 325.0))
    assert across == [-1100.0, -850.0, -600.0, -350.0, -100.0, 75.0, 200.0, 325.0, 525.0, 725.0, 925.0]
    assert len(msp.query('ARC[layer=="鉄筋"]')) == 4
    assert len(msp.query('LWPOLYLINE[layer=="鉄筋"]')) == 4  # two steps of ずれ止め on each side
    assert {"フーチング下面", "アンカー鉄筋", "D38-16本 SD390", "帯鉄筋", "D16 ctc125・200", "D10", "鋼管", "t=18",
            "ずれ止め", "t16×32 SS400", "lc=1550", "l1=950", "杭頭", "Dsp=800", "Dsc=1000", "D38-16本", "杭先端部",
            "支持層", "ずれ止め 4段"} <= set(texts(msp))


def test_a_pipe_without_ribs_or_tip_steps_draws_neither():
    found = figure(pier(鋼管厚=9.0, 鋼管外径=1.3, ソイルセメント径=1.4))
    assert (found.ribs, found.rib_size, found.tip_steps) == ((), None, ())
    msp = drawn(pier(鋼管厚=9.0, 鋼管外径=1.3, ソイルセメント径=1.4))
    assert "ずれ止め" not in texts(msp) and "ずれ止め 0段" in texts(msp)
    assert not msp.query('LWPOLYLINE[layer=="鉄筋"]')


def test_the_files_have_the_steel_pile_with_its_detailing():
    found = pier()
    detailing = steel_pile_detailing(found)
    assert "杭" in drawing_figures(found, detailing)
    data = drawing_dxf(found, detailing)
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    titles = [text for text in texts(doc.modelspace()) if text.startswith("杭（杭頭の結合部・断面と杭先端部）　1:")]
    assert titles == ["杭（杭頭の結合部・断面と杭先端部）　1:25"] and not doc.audit().has_errors
    assert data == drawing_dxf(found, detailing)
