"""0620 horizontal actions: vehicle lateral, wind on the girders and on the pier (Example2 9-7, 9-8, 9-11, 9-12).

Decision 12: the pier takes the wind over its exposed width per member (beam B1, haunch from B1 to the
lower face B1 − B4 − B5, column B6), and only above the ground surface, footing top + min(df1, df2).
"""

from decimal import Decimal

import pytest

from reaction_support import D, pier, q, value
from transverse_support import (
    DF1, DF2, EXAMPLE2_GROUND, chain, diagram, dims, items, points, transverse,
)
from webpier.calc.frame import Region
from webpier.calc.transverse import BasicCase, Item

B = BasicCase


def test_9_7_vehicle_lateral_load():
    printed = items("vehicle_lateral_load")
    _, reaction, result = chain()
    lateral = result.lateral
    assert (lateral.origin.h, lateral.origin.y) == (reaction.transverse.origin.vehicle_lateral.force,
                                                    reaction.transverse.origin.vehicle_lateral.height)
    assert (lateral.end.h, lateral.end.y) == (reaction.transverse.end.vehicle_lateral.force,
                                              reaction.transverse.end.vehicle_lateral.height)
    assert [lateral.origin.h.value, lateral.origin.y.value, lateral.end.h.value, lateral.end.y.value] == \
        printed["M"]["operands"]  # 52.71 × 3.85 + 58.98 × 3.85
    assert lateral.h.value == printed["H"]["value"] == 111.69
    # M as the printed one-line expression, rounded once: 202.9335 + 227.073 = 430.0065 -> 430.01 (9-7).
    assert value(lateral.m) == q(D(52.71) * D(3.85) + D(58.98) * D(3.85), 2) == Decimal("430.01")
    assert lateral.m.value == printed["M"]["value"]
    assert [lateral.origin.item, lateral.end.item] == [Item.ORIGIN, Item.END]
    assert points(result.basic(B.LATERAL)) == {1: (0.0, 111.69, 430.01)}
    assert diagram(15) == {"H": 111.69, "M": 430.01}
    assert result.basic(B.LATERAL).member_loads == ()


@pytest.mark.parametrize("case,attribute,section", [(B.WIND_WITH_TRAIN, "wind_with_train", "wind_load_with_train"),
                                                    (B.WIND_WITHOUT_TRAIN, "wind_without_train",
                                                     "wind_load_without_train")])
def test_9_7_and_9_8_wind_on_the_girders(case, attribute, section):
    _, reaction, result = chain()
    wind = getattr(result, attribute)
    upstream = {Item.ORIGIN: getattr(reaction.transverse.origin, attribute),
                Item.END: getattr(reaction.transverse.end, attribute)}
    for row in wind.rows:
        assert (row.h, row.y, row.m) == (upstream[row.item].force, upstream[row.item].height, upstream[row.item].moment)
    assert value(wind.h) == sum(value(row.h) for row in wind.rows)
    assert value(wind.m) == sum(value(row.m) for row in wind.rows)  # the M total of 9-7 is the sum of its rows
    printed = items(section)
    # H matches Example2: current.json folds the shelter into h4 (0600 test), 197.00 + 108.88 = 305.88 and
    # 393.99 + 217.76 = 611.75 (Example2 394.00 + 217.75).
    assert wind.h.value == printed["H"]["value"]
    # M differs by design: the shelter is not itemised as vertical couples and its height is folded into h4
    # (the user accepted the wind M). 197.00 × 6.717 + 108.88 × 7.359 = 1323.25 + 801.25 (Example2 1001.33);
    # 393.99 × 6.717 + 217.76 × 7.359 = 2646.43 + 1602.50 (Example2 2002.64).
    assert (wind.m.value, printed["M_total"]["value"]) == {B.WIND_WITH_TRAIN: (2124.5, 1001.33),
                                                           B.WIND_WITHOUT_TRAIN: (4248.93, 2002.64)}[case]
    assert wind.pressure.value == {B.WIND_WITH_TRAIN: 1.5, B.WIND_WITHOUT_TRAIN: 3.0}[case]
    assert points(result.basic(case)) == {1: (0.0, wind.h.value, wind.m.value)}


def segments(wind):
    return [(s.region, s.member, s.top.value, s.bottom.value, s.length.value, s.width_top.value,
             s.width_bottom.value, s.load_top.value, s.load_bottom.value) for s in wind.pier.segments]


def member_loads(action):
    return [(m.member, m.start.value, m.end.value, m.h_start.value, m.h_end.value) for m in action.member_loads]


def test_9_12_pier_wind_with_the_example2_ground():
    # Example2 9-12: Hw1 = 1.5 × 2.70 = 4.05 and 3.0 × 2.70 = 8.10 kN/m over 6.520 m below node 1, stopping
    # 1.080 m above node 4 (Df − H6 = 1.080). With df1 = df2 = 1.080 the ground is 2.700 + 1.080 = 3.780.
    result = transverse(pier(**EXAMPLE2_GROUND))
    for case, attribute, number in ((B.WIND_WITH_TRAIN, "wind_with_train", 16),
                                    (B.WIND_WITHOUT_TRAIN, "wind_without_train", 17)):
        printed, wind = diagram(number), getattr(result, attribute)
        load = printed["Hw1"]
        assert wind.pier.ground.value == 3.78
        assert wind.pier.exposure.value == printed["Hw1_extent"] == 6.52  # 10.300 − 3.780
        assert wind.pier.ground.value - result.frame.nodes[3].y.value == pytest.approx(printed["Hw1_gap_above_node4"])
        assert segments(wind) == [(Region.BEAM, 1, 10.3, 8.3, 2.0, 2.7, 2.7, load, load),
                                  (Region.HAUNCH, 2, 8.3, 7.6, 0.7, 2.7, 2.7, load, load),
                                  (Region.COLUMN, 3, 7.6, 3.78, 3.82, 2.7, 2.7, load, load)]
        # Each member load runs from the member's upper node (start 0) over its loaded length.
        assert member_loads(result.basic(case)) == [(1, 0.0, 2.0, load, load), (2, 0.0, 0.7, load, load),
                                                    (3, 0.0, 3.82, load, load)]
        assert sum(D(s.length.value) for s in wind.pier.segments) == D(printed["Hw1_extent"])
    assert items("wind_load_with_train")["Hw1"]["operands"] == [1.5, 2.7]


def test_current_input_ground_is_2_000_above_the_footing_top():
    # current.json: df1 = df2 = 2.000, so 2.000 of the column is below the ground (Example2: 1.080).
    wind = transverse().wind_without_train
    assert (wind.pier.ground.value, wind.pier.exposure.value) == (4.7, 5.6)
    assert segments(wind)[-1] == (Region.COLUMN, 3, 7.6, 4.7, 2.9, 2.7, 2.7, 8.1, 8.1)


def test_the_lower_soil_surface_sets_the_ground():
    wind = transverse(pier(**{DF1: 2.5, DF2: 1.5})).wind_with_train
    assert wind.pier.ground.value == 4.2  # 2.700 + min(2.500, 1.500)
    assert segments(wind)[-1][2:5] == (7.6, 4.2, 3.4)


# Beam 3.200 wide, haunch from 3.200 down to 3.200 − 0.100 − 0.200 = 2.900, column 2.500.
WIDTHS = dims(B1=3.2, B4=0.1, B5=0.2, B6=2.5)


def hand_load(pressure, width):
    return float(q(D(pressure) * D(width), 2))


def test_exposed_widths_per_member():
    result = transverse(pier(**WIDTHS))
    wind = result.wind_without_train
    assert segments(wind) == [
        (Region.BEAM, 1, 10.3, 8.3, 2.0, 3.2, 3.2, 9.6, 9.6),  # 3.0 × 3.200
        (Region.HAUNCH, 2, 8.3, 7.6, 0.7, 3.2, 2.9, 9.6, 8.7),  # trapezoid 3.0 × 3.200 -> 3.0 × 2.900
        (Region.COLUMN, 3, 7.6, 4.7, 2.9, 2.5, 2.5, 7.5, 7.5)]  # 3.0 × 2.500
    with_train = segments(result.wind_with_train)
    assert [(s[7], s[8]) for s in with_train] == [(4.8, 4.8), (4.8, 4.35), (3.75, 3.75)]  # 1.5 × 2.900 = 4.35
    assert member_loads(result.basic(B.WIND_WITH_TRAIN))[1] == (2, 0.0, 0.7, 4.8, 4.35)


def test_ground_inside_the_haunch_cuts_the_trapezoid():
    # Ground 2.700 + 5.200 = 7.900, 0.300 above the haunch bottom (7.600): the width there is
    # 2.900 + (3.200 − 2.900) × 0.300 / 0.700 = 3.028571 -> 3.029; 3.0 × 3.029 = 9.087 -> 9.09.
    result = transverse(pier(**WIDTHS, **{DF1: 5.2, DF2: 5.2}))
    wind = result.wind_without_train
    width = q(D(2.9) + (D(3.2) - D(2.9)) * (D(7.9) - D(7.6)) / D(0.7), 3)
    assert width == Decimal("3.029")
    assert (wind.pier.ground.value, wind.pier.exposure.value) == (7.9, 2.4)
    assert segments(wind) == [(Region.BEAM, 1, 10.3, 8.3, 2.0, 3.2, 3.2, 9.6, 9.6),
                              (Region.HAUNCH, 2, 8.3, 7.9, 0.4, 3.2, float(width), 9.6, hand_load(3.0, width))]
    assert member_loads(result.basic(B.WIND_WITHOUT_TRAIN)) == [(1, 0.0, 2.0, 9.6, 9.6), (2, 0.0, 0.4, 9.6, 9.09)]


def test_ground_inside_the_beam():
    wind = transverse(pier(**{DF1: 6.5, DF2: 6.5})).wind_with_train  # ground 9.200
    assert segments(wind) == [(Region.BEAM, 1, 10.3, 9.2, 1.1, 2.7, 2.7, 4.05, 4.05)]
    assert wind.pier.exposure.value == 1.1


def test_ground_at_the_column_top_leaves_the_column_unloaded():
    wind = transverse(pier(**{DF1: 4.9, DF2: 4.9})).wind_with_train  # ground 7.600 = haunch bottom
    assert [s[0] for s in segments(wind)] == [Region.BEAM, Region.HAUNCH]


@pytest.mark.parametrize("depth", [7.6, 8.0])
def test_ground_at_or_above_the_pier_top_gives_no_pier_wind(depth):
    result = transverse(pier(**{DF1: depth, DF2: depth}))
    for case, wind in ((B.WIND_WITH_TRAIN, result.wind_with_train), (B.WIND_WITHOUT_TRAIN, result.wind_without_train)):
        assert wind.pier.segments == ()
        assert wind.pier.exposure.value == 0.0
        assert result.basic(case).member_loads == ()
        assert points(result.basic(case)) == {1: (0.0, wind.h.value, wind.m.value)}  # the girder wind remains


def test_zero_haunch_has_no_haunch_segment():
    result = transverse(pier(**dims(H3=0.0)))
    wind = result.wind_with_train
    assert [(s[0], s[1], s[2], s[3]) for s in segments(wind)] == [(Region.BEAM, 1, 9.6, 7.6),
                                                                 (Region.COLUMN, 2, 7.6, 4.7)]


def test_footing_rows_are_not_wind_loaded():
    wind = transverse(pier(**{DF1: 0.0, DF2: 0.0})).wind_with_train  # ground at the footing top
    assert segments(wind)[-1][:5] == (Region.COLUMN, 3, 7.6, 2.7, 4.9)
    assert wind.pier.exposure.value == 7.6


def test_horizontal_actions_print_two_decimals():
    result = transverse()
    for printed in (result.lateral.h, result.lateral.m, result.wind_with_train.h, result.wind_with_train.m):
        assert printed.digits == 2
    for segment in result.wind_with_train.pier.segments:
        assert (segment.width_top.digits, segment.load_top.digits, segment.length.digits) == (3, 2, 3)
        assert segment.load_top.unit == "kN/m"


# Decision 35: the pedestal takes the wind over its width B3 (1.000), above the ground like the rest.
PEDESTAL = dims(B2=1.025, B3=1.0, W2=0.5, W3=7.0, H1=0.3)


def test_pedestal_takes_the_wind_over_b3():
    result = transverse(pier(**PEDESTAL))
    wind = result.wind_with_train
    pedestal = result.frame.members[0]  # numbered from the upper left: the stub is member 1, base 2 → top 1
    assert (pedestal.region, pedestal.number, pedestal.start, pedestal.end) == (Region.PEDESTAL, 1, 2, 1)
    # Pedestal 10.300 -> 10.600: 1.5 × 1.000 = 1.50 kN/m; the exposure runs from its top: 10.600 − 4.700 = 5.900.
    assert segments(wind)[0] == (Region.PEDESTAL, 1, 10.6, 10.3, 0.3, 1.0, 1.0, 1.5, 1.5)
    assert [s[0] for s in segments(wind)] == [Region.PEDESTAL, Region.BEAM, Region.HAUNCH, Region.COLUMN]
    assert wind.pier.exposure.value == 5.9
    # The pedestal member starts at its base (node 2): the load runs 0.000 -> 0.300 from there.
    assert member_loads(result.basic(B.WIND_WITH_TRAIN))[0] == (1, 0.0, 0.3, 1.5, 1.5)
    assert member_loads(result.basic(B.WIND_WITHOUT_TRAIN))[0] == (1, 0.0, 0.3, 3.0, 3.0)


def test_ground_inside_the_pedestal():
    # Ground 2.700 + 7.750 = 10.450: only the top 0.150 of the pedestal; from its base node that is 0.150 -> 0.300.
    result = transverse(pier(**PEDESTAL, **{DF1: 7.75, DF2: 7.75}))
    wind = result.wind_with_train
    assert segments(wind) == [(Region.PEDESTAL, 1, 10.6, 10.45, 0.15, 1.0, 1.0, 1.5, 1.5)]
    assert wind.pier.exposure.value == 0.15
    assert member_loads(result.basic(B.WIND_WITH_TRAIN)) == [(1, 0.15, 0.3, 1.5, 1.5)]


def test_centred_pedestal_starts_at_the_beam_top():
    result = transverse(pier(**dims(B2=0.85, B3=1.2, W2=1.0, W3=7.0, H1=0.4)))  # xC = 0: no arm
    assert member_loads(result.basic(B.WIND_WITHOUT_TRAIN))[0] == (1, 0.0, 0.4, 3.6, 3.6)  # 3.0 × 1.200
