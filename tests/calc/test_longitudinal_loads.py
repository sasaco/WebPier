"""0610 basic actions: Example2 08 pp.8-3 to 8-9 and hand calculations from the printed operands."""

from decimal import Decimal

import pytest

from longitudinal_support import SECTIONS, chain, diagram, items, longitudinal, table
from reaction_support import D, q, value
from webpier.calc.frame import NodeRole
from webpier.calc.longitudinal import BasicCase, Item, SpringTerm
from webpier.calc.reaction.longitudinal import LongitudinalCase

B = BasicCase


def cells(row):
    return [row.n.value, row.arm.value, row.m.value]


def test_8_3_fixed_dead_load():
    printed, rows = items("dead_load"), table("dead_load")
    fixed = longitudinal().fixed
    assert (fixed.column_q.value, fixed.column_q.digits) == (printed["column_q"]["value"], 2)  # 4.50 × 2.70 × 24.5
    assert cells(fixed.table.row(Item.ORIGIN)) == rows["RB"]
    assert cells(fixed.table.row(Item.END)) == rows["RC"]
    # Example2 prints the beam as the prism 1190.70 and the haunch wings 104.19 and deducts q × 2.00 (H2).
    # We take the 0600 beam weight (prism + whole haunch) and deduct q over H2 + H3 = 2.700, where the column
    # line load overlaps it. Hand: (2.70 × 9.00 × 2.000 + 0.700/6 × (2.7·9 + 2.7·4.5 + 2(24.3 + 12.15))) × 24.5
    # = (48.600 + 12.758) × 24.5 = 1503.271 -> 1503.27.
    beam = fixed.table.row(Item.BEAM)
    assert cells(beam) == [1503.27, 0.0, 0.0]
    assert [row.item for row in fixed.table.rows] == [Item.ORIGIN, Item.END, Item.BEAM]  # no pedestal (H1 = 0)
    assert fixed.table.n.value == 9103.27  # 5740 + 1860 + 1503.27
    assert fixed.overlap.value == 2.7
    # N = 9103.27 − 297.68 × 2.700 = 8299.534 -> 8299.53, the printed N of 8-3 (8894.89 − 297.68 × 2.00).
    assert fixed.n.value == printed["top_N"]["value"] == 8299.53
    assert fixed.m.value == printed["top_M"]["value"] == rows["total"][2]
    assert (fixed.footing.n.value, fixed.footing.arm.value, fixed.footing.m.value) == (
        printed["footing_P"]["value"], 0.0, 0.0)


def test_8_3_additional_dead_load_and_soil():
    printed, rows = items("superimposed_dead_load"), table("superimposed_dead_load")
    additional = longitudinal().additional
    assert cells(additional.table.row(Item.ORIGIN)) == rows["RB"]
    assert cells(additional.table.row(Item.END)) == rows["RC"]
    assert [additional.table.n.value, additional.table.m.value] == [rows["total"][0], rows["total"][2]]
    assert additional.soil.item is Item.OVERBURDEN
    assert additional.soil.n.value == printed["soil_sumP"]["value"]  # 1830.60


def test_8_3_buoyancy():
    printed = items("buoyancy")
    water = longitudinal().buoyancy
    assert [row.n.value for row in water] == [printed[key]["value"] for key in ("omega1_high", "omega2_mean",
                                                                                "omega3_low")]
    assert {row.item for row in water} == {Item.WATER}


@pytest.mark.parametrize("index,key", [(0, "snow_2yr"), (1, "snow_10yr"), (2, "snow_30yr")])
def test_8_4_snow(index, key):
    rows = table("snow_load", key)
    snow = longitudinal().snow[index]
    assert cells(snow.row(Item.ORIGIN)) == rows["RB"]
    assert cells(snow.row(Item.END)) == rows["RC"]
    assert [snow.n.value, snow.m.value] == [rows["total"][0], rows["total"][2]]


def test_8_4_single_track_train():
    rows = table("train_load", "single_track")
    single = longitudinal().train.single
    assert cells(single.row(Item.ORIGIN)) == rows["RB"]  # 272.47 -0.325 -88.55
    assert cells(single.row(Item.END)) == rows["RC"]
    assert [single.n.value, single.m.value] == [rows["total"][0], rows["total"][2]]


def test_8_4_double_track_train_from_the_printed_reaction():
    rows = table("train_load", "double_track")
    double = longitudinal().train.double
    # 8-4 prints RB = 544.93 from the unrounded 272.4668 × 2. From the printed 272.47 × 2.000 = 544.94,
    # M = 544.94 × −0.325 = −177.1055 -> −177.11; totals 544.94 + 589.84 = 1134.78, −177.11 + 398.14 = 221.03.
    assert cells(double.row(Item.ORIGIN)) == [544.94, -0.325, -177.11]
    assert rows["RB"] == [544.93, -0.325, -177.1]
    assert cells(double.row(Item.END)) == rows["RC"]  # 294.92 × 2.000 = 589.84
    assert [double.n.value, double.m.value] == [1134.78, 221.03]
    assert [rows["total"][0], rows["total"][2]] == [1134.77, 221.04]


def hand_impact(train, coefficient, arm):
    n = q(D(train) * D(coefficient), 2)
    return n, q(n * D(arm), 2)


@pytest.mark.parametrize("usage,track", [("ultimate", "single"), ("ultimate", "double"),
                                         ("service", "single"), ("service", "double")])
def test_impact_uses_the_0600_pier_coefficients(usage, track):
    # Decision C05 (longitudinal-example2-parity.md, owner-approved): the pier impact of 0600 (RC標準 解4.4.4,
    # i = i0 (1 − Ds/(L + DU + Ds))) is used, not the girder coefficients of Example2 8-5 (0.245 / 0.546 single,
    # 0.222 / 0.521 double, which give 66.75 / 161.03 and 120.98 / 307.31). The service group carries 0.75 in it.
    _, reaction, result = chain()
    impact = getattr(result.impact, f"{usage}_{track}")
    pier = getattr(getattr(reaction.train, f"pier_{usage}"), track)
    trains = getattr(result.train, track)
    total_n = total_m = Decimal(0)
    for item, support in ((Item.ORIGIN, pier.b), (Item.END, pier.c)):
        row = impact.row(item)
        train = trains.row(item)
        assert row.train == train.n and row.coefficient == support.coefficient and row.arm == train.arm
        n, m = hand_impact(train.n.value, support.coefficient.value, train.arm.value)
        assert (value(row.n), value(row.m)) == (n, m)
        total_n, total_m = total_n + n, total_m + m
    assert (value(impact.n), value(impact.m)) == (total_n, total_m)


def test_impact_ultimate_single_values():
    # 0600 pier coefficients of the current input: 0.185 (B), 0.412 (C).
    impact = longitudinal().impact.ultimate_single
    assert [impact.row(Item.ORIGIN).coefficient.value, impact.row(Item.END).coefficient.value] == [0.185, 0.412]
    # 272.47 × 0.185 = 50.40695 -> 50.41, × −0.325 = −16.38325 -> −16.38; 294.92 × 0.412 = 121.50704 -> 121.51,
    # × 0.675 = 82.019 -> 82.02.
    assert cells(impact.row(Item.ORIGIN))[0::2] == [50.41, -16.38]
    assert cells(impact.row(Item.END))[0::2] == [121.51, 82.02]
    assert [impact.n.value, impact.m.value] == [171.92, 65.64]


def test_8_5_horizontal_bearing_loads():
    rows = table("bearing_horizontal_loads")
    result = longitudinal()
    keys = ("serviceability_0.8LR", "serviceability_1.0LR", "safety_1.0LR+1.23B", "safety_1.1LR+1.23B",
            "safety_1.0LR+1.35B", "safety_1.0LR", "restorability_1.0LR+1.23B", "restorability_1.0LR")
    assert [row.case for row in result.horizontal] == list(LongitudinalCase)
    for row, key in zip(result.horizontal, keys, strict=True):
        assert [row.origin.value, row.end.value] == rows[key]
        assert value(row.total) == D(rows[key][0]) + D(rows[key][1])


CAP, FOOTING = NodeRole.CAP_TOP, NodeRole.FOOTING_CENTROID


def points(action):
    return {point.anchor: (point.node, point.n.value, point.h.value, point.m.value) for point in action.points}


def test_8_6_to_8_8_load_diagrams_vertical():
    result = longitudinal()
    d1 = result.basic(B.D1)
    printed = diagram(1)
    assert points(d1) == {CAP: (1, printed["N"], 0.0, printed["M"]), FOOTING: (5, printed["P"], 0.0, 0.0)}
    (line,) = d1.line_loads
    assert (line.members, line.n.value, line.h.value) == ((1, 2, 3), printed["q"], 0.0)  # q over 7.600 m
    printed = diagram(2)
    assert points(result.basic(B.D2)) == {CAP: (1, printed["N"], 0.0, printed["M"]), FOOTING: (5, printed["P"], 0.0, 0.0)}
    for case, number in ((B.BUOYANCY_HIGH, 3), (B.BUOYANCY_NORMAL, 4), (B.BUOYANCY_LOW, 5)):
        assert points(result.basic(case)) == {FOOTING: (5, diagram(number)["P"], 0.0, 0.0)}
        assert result.basic(case).line_loads == ()
    for case, number in ((B.SNOW2, 6), (B.SNOW10, 7), (B.SNOW30, 8), (B.TRAIN_SINGLE, 9)):
        assert points(result.basic(case)) == {CAP: (1, diagram(number)["N"], 0.0, diagram(number)["M"])}
    assert points(result.basic(B.TRAIN_DOUBLE)) == {CAP: (1, 1134.78, 0.0, 221.03)}  # see the double-track test
    assert points(result.basic(B.IMPACT_SINGLE)) == {CAP: (1, 171.92, 0.0, 65.64)}  # ultimate pier impact (C05)
    assert points(result.basic(B.IMPACT_DOUBLE)) == {
        CAP: (1, result.impact.ultimate_double.n.value, 0.0, result.impact.ultimate_double.m.value)}


def test_8_8_load_diagrams_horizontal():
    result = longitudinal()
    for number in range(13, 21):
        assert points(result.basic(BasicCase(number))) == {CAP: (1, 0.0, diagram(number)["H"], 0.0)}


def test_8_9_basic_cases_and_springs():
    printed = {row["no"]: row for row in SECTIONS["basic_cases"]["rows"]}
    result = longitudinal()
    assert [action.case.value for action in result.basic_cases] == list(range(1, 21))
    # 8-9 prints バネ 1 / 2; 1 is the long-term and 2 the short-term spring set of 8-1.
    terms = {1: SpringTerm.LONG, 2: SpringTerm.SHORT}
    assert [action.spring for action in result.basic_cases] == [terms[printed[n]["spring"]] for n in range(1, 21)]
    assert [action.horizontal for action in result.basic_cases] == [n >= 13 for n in range(1, 21)]
