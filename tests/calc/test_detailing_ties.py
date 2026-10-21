"""中間帯鉄筋 (CONTEXT.md, decision 73): the legs of the hoops of each direction at the column base.

The expected positions are hand calculations from the column of tests/fixtures/inputs/current.json (Example2: W6
4500, B6 2700; 線路 D32 29 per face, 両端＋中央ピッチ with the end bars at 108 and the others at 150 centred, cover
70 + 22 + 32/2 = 108; 直角 D19 9 per face at 102, 中央ピッチ 250; hoops 線路 10 legs, 直角 6 legs), not from the code.

線路 (face W6 = 4500, legs at x): the layer-1 bars are at 108, 300, 450, … , 4200 (300 + 26 × 150) and 4392; the
outermost bars along x are the 直角 bars at 102 and 4398. The eight points k × 4500 / 9 are 500, 1000, … , 4000 and the
nearest bars 450, 1050, 1500, 1950, 2550, 3000, 3450, 4050; the gaps are 348, 600, 450, 450, 600, 450, 450, 600, 348.

直角 (face B6 = 2700, legs at y): the layer-1 bars are at 350, 600, … , 2350 ((2700 − 8 × 250) / 2 = 350); the outermost
bars along y are the 線路 bars at 108 and 2592. The points k × 2700 / 5 are 540, 1080, 1620, 2160 and the nearest bars
600, 1100, 1600, 2100; the gaps are 492, 500, 500, 500, 492.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from webpier.calc.column_rebar import column_layout
from webpier.calc.detailing.ties import base_hoops, column_ties, tie_layout
from webpier.core.errors import InputError
from webpier.inputs import parse_input

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
ROWS = "鉄筋.柱.column_hoops.direction_rows"


def pier(**hoops):
    """current.json with hoop row fields changed: {'0.effective_legs': 4, ...}."""
    data = deepcopy(CURRENT)
    rows = data["鉄筋"]["柱"]["column_hoops"]["direction_rows"]
    for key, value in hoops.items():
        index, name = key.split(".")
        rows[int(index)][name] = value
    return parse_input(data)


def values(numbers):
    return [number.value for number in numbers]


def test_longitudinal_legs_hook_the_bars_nearest_the_ninths():
    ties = column_ties(pier(), "線路")
    assert ties.effective_legs == 10 and ties.span.value == 4500
    assert values(ties.targets) == [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000]
    assert values(ties.outer) == [102, 4398]
    assert values(ties.intermediate) == [450, 1050, 1500, 1950, 2550, 3000, 3450, 4050]
    assert values(ties.legs) == [102, 450, 1050, 1500, 1950, 2550, 3000, 3450, 4050, 4398]
    assert (ties.sets.value, ties.sets.digits) == (5.0, 1)
    assert ties.intermediate_sets.value == 4.0
    assert (ties.max_spacing.value, ties.max_spacing.unit) == (600, "mm")


def test_transverse_legs_hook_the_bars_nearest_the_fifths():
    ties = column_ties(pier(), "直角")
    assert values(ties.targets) == [540, 1080, 1620, 2160]
    assert values(ties.outer) == [108, 2592]
    assert values(ties.intermediate) == [600, 1100, 1600, 2100]
    assert ties.sets.value == 3.0 and ties.intermediate_sets.value == 2.0
    assert ties.max_spacing.value == 500


def test_two_legs_are_the_outer_hoop_only():
    ties = column_ties(pier(**{"1.effective_legs": 2}), "直角")
    assert ties.targets == () and ties.intermediate == ()
    assert ties.intermediate_sets.value == 0 and ties.sets.value == 1.0
    assert ties.max_spacing.value == 2592 - 108


def test_an_odd_count_has_half_a_set():
    # 3 legs: one point at 2700 / 2 = 1350, between 1350 ± 0 → the bar at 1350 (350 + 4 × 250)
    ties = column_ties(pier(**{"1.effective_legs": 3}), "直角")
    assert values(ties.intermediate) == [1350]
    assert ties.sets.value == 1.5 and ties.intermediate_sets.value == 0.5
    assert ties.max_spacing.value == 2592 - 1350


def test_of_two_equally_near_bars_the_one_nearer_the_origin():
    # 4 legs across 2700: points 900 and 1800; bars at 350 + 250 j → 850 (50 from 900) and 1850 (50 from 1800)
    ties = column_ties(pier(**{"1.effective_legs": 4}), "直角")
    assert values(ties.intermediate) == [850, 1850]
    # 直角 bars at a pitch of 300 from (2700 − 8 × 300) / 2 = 150: 900 lies midway between 750 and 1050, 1800 between
    # 1650 and 1950 → the bars nearer the origin
    data = deepcopy(CURRENT)
    data["鉄筋"]["柱"]["main_bars"]["直角"]["distribution"]["pitch_mm"] = 300
    data["鉄筋"]["柱"]["column_hoops"]["direction_rows"][1]["effective_legs"] = 4
    ties = column_ties(parse_input(data), "直角")
    assert values(ties.intermediate) == [750, 1650]


def test_the_base_row_is_the_one_from_the_column_base():
    data = deepcopy(CURRENT)
    rows = data["鉄筋"]["柱"]["column_hoops"]["direction_rows"]
    rows[0].update(start_mm=0, end_mm=5400)
    rows.append({**rows[0], "effective_legs": 4, "pitch_mm": 300, "start_mm": 5400, "end_mm": None})
    hoops = base_hoops(parse_input(data), "線路")
    assert (hoops.legs, hoops.pitch.value, hoops.diameter.value, hoops.grade) == (10, 150, 22, "SD390")
    assert hoops.path == f"{ROWS}[0]"


@pytest.mark.parametrize(("change", "message"), [
    ({"1.effective_legs": 1}, f"{ROWS}[1].effective_legs: 外巻き帯鉄筋の2本を含めて2本以上が必要です（1本）"),
    ({"1.effective_legs": 20}, f"{ROWS}[1].effective_legs: 中間帯鉄筋を掛ける直角の1段目の主鉄筋が足りません"),
    ({"1.start_mm": 100}, f"{ROWS}: 直角の帯鉄筋で柱下端を含む行がちょうど1行必要です（0行）"),
    ({"1.pitch_mm": None}, f"{ROWS}[1].pitch_mm: 値が必要です"),
])
def test_ties_that_cannot_be_placed_name_the_row(change, message):
    with pytest.raises(InputError) as caught:
        column_ties(pier(**change), "直角")
    assert str(caught.value).startswith(message)


def test_an_intermediate_tie_needs_layer_one_bars():
    data = deepcopy(CURRENT)
    data["鉄筋"]["柱"]["main_bars"]["直角"]["per_face_count"] = 0
    pier_ = parse_input(data)
    with pytest.raises(InputError, match=r"direction_rows\[1\].effective_legs: 中間帯鉄筋を掛ける直角の1段目の主鉄筋がありません"):
        tie_layout(column_layout(pier_), "直角", 6, f"{ROWS}[1]")
    # the outer hoop alone needs none
    assert tie_layout(column_layout(pier_), "直角", 2, f"{ROWS}[1]").max_spacing.value == 2592 - 108
