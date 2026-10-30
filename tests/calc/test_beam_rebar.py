"""Beam bar layout (calc.beam_rebar, decisions 59, 68): the bars of 鉄筋.梁 placed in the section at the column face.

Expected values are hand calculations from the current input (Example2 13_片持ち梁照査/WebDan.wdj): b = h = 2700 mm,
上側 D32 × 17 at 108 and × 8 at 172, 下側 D19 × 18 at 121, side bars D22 at 184 from 350 at 125.
"""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from reaction_support import D, document, q, value
from webpier.calc.beam_rebar import SIDE, beam_layout, beam_section
from webpier.core.errors import InputError
from webpier.core.printed import Printed
from webpier.inputs import parse_input

BEAM = "鉄筋/梁"
SIZE = Printed(2700.0, 1, "mm")


def layout(**changes):
    return beam_layout(parse_input(document(**changes)).rebar.beam, SIZE, SIZE)


def fails(message, **changes):
    with pytest.raises(InputError, match=re.escape(message)):
        layout(**changes)


def of(result, group, layer):
    return [bar for bar in result.bars if (bar.group, bar.layer) == (group, layer)]


def xs(bars):
    return [bar.x.value for bar in bars]


def test_the_centres_and_the_number_of_bars():
    result = layout()
    assert result.centers == {"上": (Printed(108.0, 1, "mm"), Printed(172.0, 1, "mm")), "下": (Printed(121.0, 1, "mm"),)}
    assert result.side_center.value == 184.0 and (result.width, result.depth) == (SIZE, SIZE)
    assert len(result.bars) == 17 + 8 + 18 + 34 == 77
    assert result.overlaps == ()


def test_the_inner_layer_takes_the_middle_of_layer_1s_positions():
    result = layout()
    first = of(result, "上", 1)
    assert {bar.y.value for bar in first} == {108.0} and len(first) == 17
    # s = (2700 − 2 × 184) / 16 = 145.75 from the side bars' centre
    assert xs(first)[:2] == [184.0, 329.8] and xs(first)[-1] == 2516.0
    second = of(result, "上", 2)
    assert {bar.y.value for bar in second} == {172.0} and len(second) == 8
    # 17 − 8 = 9 left over: from the 5th of layer 1, 184 + 4 × 145.75 = 767.0, to 184 + 11 × 145.75 = 1787.25
    assert (xs(second)[0], xs(second)[-1]) == (767.0, 1787.3)
    assert set(xs(second)) <= set(xs(first))
    assert result.faces["上"].layer_spacing.value == 64.0  # 32 + 32


def test_an_even_rest_is_symmetric():
    result = layout(**{f"{BEAM}/faces/上/inner_layers/0/count": 7})
    second = of(result, "上", 2)
    # 17 − 7 = 10 left over: from 184 + 5 × 145.75 = 912.75 to 1787.25 (912.75 + 1787.25 = 2700)
    assert len(second) == 7 and (xs(second)[0], xs(second)[-1]) == (912.8, 1787.3)


def test_the_lower_layer_is_measured_from_the_lower_face():
    result = layout()
    lower = of(result, "下", 1)
    assert {bar.y.value for bar in lower} == {2579.0} and len(lower) == 18  # 2700 − 121
    assert (xs(lower)[0], xs(lower)[-1]) == (184.0, 2516.0)
    assert value(result.faces["下"].spacing) == q(D(2332) / 17, 1)
    assert result.faces["下"].layer_spacing is None


def test_the_side_bars_lie_on_both_side_faces_from_their_start():
    result = layout()
    side = [bar for bar in result.bars if bar.group == SIDE]
    assert xs(side[:2]) == [184.0, 2516.0] and [bar.layer for bar in side[:4]] == [1, 1, 2, 2]
    assert [bar.y.value for bar in side[::2]] == [350.0 + 125 * j for j in range(17)]
    assert side[-1].y.value == 2350.0 and result.side.count.value == 17


def test_one_side_bar_needs_no_pitch():
    result = layout(**{f"{BEAM}/side_bars/per_face_count": 1, f"{BEAM}/side_bars/pitch_mm": None})
    side = [bar for bar in result.bars if bar.group == SIDE]
    assert [(bar.x.value, bar.y.value) for bar in side] == [(184.0, 350.0), (2516.0, 350.0)]
    assert result.side.spacing is None


def test_without_side_bars_layer_1_runs_from_its_cover():
    result = layout(**{f"{BEAM}/side_bars": None})
    assert result.side is None and result.side_center is None
    assert not [bar for bar in result.bars if bar.group == SIDE]
    assert (xs(of(result, "上", 1))[0], xs(of(result, "下", 1))[0]) == (108.0, 121.0)


def test_bars_closer_than_their_sizes_overlap():
    result = layout(**{f"{BEAM}/side_bars/start_mm": 108})
    # the first side bars sit on the end bars of layer 1 of the upper face, left and right
    assert len(result.overlaps) == 2
    for i, j in result.overlaps:
        a, b = result.bars[i], result.bars[j]
        assert (a.group, a.layer, b.group, b.layer) == ("上", 1, SIDE, 1) and (a.x, a.y) == (b.x, b.y)
    assert layout(**{f"{BEAM}/side_bars/start_mm": 135}).overlaps == ()  # 27 = (32 + 22) / 2 apart: touching
    assert len(layout(**{f"{BEAM}/side_bars/start_mm": 134}).overlaps) == 2


def test_an_automatic_cover_needs_the_stirrup_only_then():
    automatic = {f"{BEAM}/pure_cover_mm": 70, f"{BEAM}/faces/上/cover_mode": "自動", f"{BEAM}/faces/上/center_mm": None}
    assert layout(**automatic).centers["上"][0].value == 108.0  # 70 + 22 + 32 / 2
    fails("鉄筋.梁.stirrups.diameter_mm: 値が必要です", **automatic, **{f"{BEAM}/stirrups/diameter_mm": None})
    assert len(layout(**{f"{BEAM}/stirrups/diameter_mm": None}).bars) == 77  # every cover given


# 内側: c_s = 70 + 22 + 22/2 = 103 and the main bars' end at c_s; 外側: c_s = 70 + 22/2 = 81 and the main bars inside
# the side bars and the stirrup, 81 + 22/2 + 22 + 32/2 = 130 (upper) and 81 + 11 + 22 + 19/2 = 123.5 (lower, D19)
@pytest.mark.parametrize("position,centre,upper,lower", [("内側", 103.0, 103.0, 103.0), ("外側", 81.0, 130.0, 123.5)])
def test_an_automatic_side_centre(position, centre, upper, lower):
    result = layout(**{f"{BEAM}/pure_cover_mm": 70, f"{BEAM}/side_bars/cover_mode": "自動",
                       f"{BEAM}/side_bars/center_mm": None, f"{BEAM}/side_bars/stirrup_position": position})
    assert result.side_center.value == centre
    assert (xs(of(result, "上", 1))[0], xs(of(result, "下", 1))[0]) == (upper, lower)
    assert value(result.faces["上"].spacing) == q((D(2700) - 2 * D(str(upper))) / 16, 1)


def test_a_given_side_centre_outside_the_stirrups_moves_the_main_bars_in():
    result = layout(**{f"{BEAM}/side_bars/stirrup_position": "外側"})  # c_s 184 given
    assert result.side_center.value == 184.0
    assert xs(of(result, "上", 1))[0] == 233.0  # 184 + 22/2 + 22 + 32/2
    assert xs(of(result, "下", 1))[0] == 226.5  # 184 + 11 + 22 + 19/2


def test_an_outside_side_bar_needs_the_stirrup_for_the_main_bars():
    """The side bars' centre outside the stirrups does not use the stirrup, but the main bars' end inside it does."""
    fails("鉄筋.梁.stirrups.diameter_mm: 値が必要です",
          **{f"{BEAM}/pure_cover_mm": 70, f"{BEAM}/side_bars/cover_mode": "自動", f"{BEAM}/side_bars/center_mm": None,
             f"{BEAM}/side_bars/stirrup_position": "外側", f"{BEAM}/stirrups/diameter_mm": None})


@pytest.mark.parametrize("changes,message", [
    ({f"{BEAM}/faces/上/count": 1}, "鉄筋.梁.faces.上.count: 2本以上が必要です"),
    ({f"{BEAM}/faces/上/center_mm": None}, "鉄筋.梁.faces.上.center_mm: 値が必要です"),
    ({f"{BEAM}/faces/上/inner_layers": [{"count": 17, "clear_gap_mm": 32}, {"count": 8, "clear_gap_mm": 40}]},
     "鉄筋.梁.faces.上.inner_layers: 段のあきが一定ではないため表せません"),
    ({f"{BEAM}/faces/上/inner_layers": [{"count": 18, "clear_gap_mm": 32}]}, "鉄筋.梁.faces.上.inner_layers: 段の本数は"),
    ({f"{BEAM}/side_bars/pitch_mm": None}, "鉄筋.梁.side_bars.pitch_mm: 値が必要です"),
])
def test_what_cannot_be_placed_names_its_path(changes, message):
    fails(message, **changes)


def test_three_layers_lie_one_bar_and_gap_apart():
    result = layout(**{f"{BEAM}/faces/上/inner_layers": [{"count": 17, "clear_gap_mm": 32},
                                                         {"count": 8, "clear_gap_mm": 32}]})
    assert [centre.value for centre in result.centers["上"]] == [108.0, 172.0, 236.0]
    assert Decimal(repr(result.faces["上"].spacing.value)) == Decimal("145.8")


def test_the_section_is_b1_by_h2_and_h3_in_mm():
    b, h = beam_section(Printed(2.7, 3, "m"), Printed(2.0, 3, "m"), Printed(0.7, 3, "m"))
    assert (b, h) == (SIZE, SIZE)  # 2.700 m; 2.000 + 0.700 m


def test_example4_the_main_bars_lie_inside_the_side_bars_and_the_stirrup():
    """Example橋脚4 第V編 図1.2.1・1.2.2: b = 2500, pure cover 45, side bars D19 outside the stirrups (自動), stirrup
    D19. c_s = 45 + 19/2 = 54.5; the upper face (D32) ends at 54.5 + 19/2 + 19 + 32/2 = 99 (the figure's 99 =
    45 + 19 + 19 + 32/2), the lower face (D16) at 54.5 + 9.5 + 19 + 16/2 = 91."""
    path = Path(__file__).parents[2] / ".claude" / "docs" / "Example橋脚4" / "pre" / "input.json"
    pier = parse_input(json.loads(path.read_text(encoding="utf-8")))
    s = pier.substructure
    result = beam_layout(pier.rebar.beam, *beam_section(s.b[1], s.h[2], s.h[3]))
    assert result.width.value == 2500.0 and result.side_center.value == 54.5
    upper, lower = xs(of(result, "上", 1)), xs(of(result, "下", 1))
    assert (len(upper), upper[0], upper[-1]) == (14, 99.0, 2401.0)
    assert value(result.faces["上"].spacing) == q((D(2500) - 2 * D(99)) / 13, 1) == D("177.1")
    assert (len(lower), lower[0], lower[-1]) == (10, 91.0, 2409.0)
    assert value(result.faces["下"].spacing) == q((D(2500) - 2 * D(91)) / 9, 1) == D("257.6")
