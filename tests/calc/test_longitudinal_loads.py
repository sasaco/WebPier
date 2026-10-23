"""0610 basic actions: Example2 08 pp.8-3 to 8-9 and hand calculations from the printed operands."""

from decimal import Decimal

import pytest

from longitudinal_support import SECTIONS, chain, diagram, items, longitudinal, table
from reaction_support import D, pier_ratios, q, value
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


def test_8_5_single_track_impact_with_the_coefficients_on_the_pier_body():
    # Decision 77: i = i0 × (1 − Ds/(L + Du + Ds)). Example2 8-5 prints the girder coefficients 0.245 / 0.546 (no
    # reduction, classification 3 in longitudinal_notes.md); here 0.245 × 0.751 = 0.18400 -> 0.184 and
    # 0.546 × 0.751 = 0.41005 -> 0.410, the ratio 0.751 by hand in test_reaction_train.
    rows = table("impact_load", "single_track")
    _, reaction, result = chain()
    assert pier_ratios(reaction) == (D("0.751"), D("0.763"))
    impact = result.impact.ultimate_single
    rb, rc = impact.row(Item.ORIGIN), impact.row(Item.END)
    assert [rb.train.value, rb.coefficient.value, rb.arm.value] == [rows["RB"][0], 0.184, rows["RB"][3]]
    assert [rc.train.value, rc.coefficient.value, rc.arm.value] == [rows["RC"][0], 0.41, rows["RC"][3]]
    # 272.47 × 0.184 = 50.13448 -> 50.13; 50.13 × −0.325 = −16.29225 -> −16.29.
    assert (rb.n.value, rb.m.value) == (50.13, -16.29)
    # 294.92 × 0.410 = 120.9172 -> 120.92; 120.92 × 0.675 = 81.621 -> 81.62.
    assert (rc.n.value, rc.m.value) == (120.92, 81.62)
    # Totals 50.13 + 120.92 = 171.05, −16.29 + 81.62 = 65.33.
    assert [impact.n.value, impact.m.value] == [171.05, 65.33]


def test_8_5_double_track_impact_with_the_coefficients_on_the_pier_body():
    rows = table("impact_load", "double_track")
    _, reaction, result = chain()
    impact = result.impact.ultimate_double
    rb, rc = impact.row(Item.ORIGIN), impact.row(Item.END)
    # Train 544.94 (see 8-4 above; 8-5 prints 544.93). Coefficients 0.222 × 0.763 = 0.16939 -> 0.169 and
    # 0.521 × 0.763 = 0.39752 -> 0.398 (the girder values are 8-5's 0.222 / 0.521).
    assert [rb.train.value, rb.coefficient.value, rb.arm.value] == [544.94, 0.169, -0.325]
    assert [rc.train.value, rc.coefficient.value, rc.arm.value] == [rows["RC"][0], 0.398, rows["RC"][3]]
    # 544.94 × 0.169 = 92.09486 -> 92.09; 92.09 × −0.325 = −29.92925 -> −29.93.
    assert (rb.n.value, rb.m.value) == (92.09, -29.93)
    n, m = hand_impact(rc.train.value, 0.398, rc.arm.value)
    assert (value(rc.n), value(rc.m)) == (n, m)
    assert (value(impact.n), value(impact.m)) == (value(rb.n) + n, value(rb.m) + m)


@pytest.mark.parametrize("usage,track", [("ultimate", "single"), ("ultimate", "double"),
                                         ("service", "single"), ("service", "double")])
def test_impact_is_the_train_times_the_0600_coefficient_on_the_pier_body(usage, track):
    # Safety/restorability: 07 7-2 i as entered (single) and i × (1 − L/200) (double); serviceability: 3/4 of them
    # (07 7-2: 0.184 / 0.41, 0.167 / 0.391); each times the ratio of decision 77 (0.751 single, 0.763 double).
    _, reaction, result = chain()
    ratio = dict(zip(("single", "double"), pier_ratios(reaction)))[track]
    impact = getattr(result.impact, f"{usage}_{track}")
    group = getattr(reaction.train, usage)
    trains = getattr(result.train, track)
    total_n = total_m = Decimal(0)
    for item, girder, on_pier in ((Item.ORIGIN, group.origin_impact, group.origin_pier_impact),
                                  (Item.END, group.end_impact, group.end_pier_impact)):
        row, train = impact.row(item), trains.row(item)
        coefficient = q(D(getattr(girder, track).value) * ratio, 3)
        assert value(getattr(on_pier, track)) == coefficient
        assert row.train == train.n and row.coefficient == getattr(on_pier, track) and row.arm == train.arm
        n, m = hand_impact(train.n.value, coefficient, train.arm.value)
        assert (value(row.n), value(row.m)) == (n, m)
        total_n, total_m = total_n + n, total_m + m
    assert (value(impact.n), value(impact.m)) == (total_n, total_m)
    if usage == "service":
        assert [impact.row(Item.ORIGIN).coefficient.value, impact.row(Item.END).coefficient.value] == (
            [0.138, 0.308] if track == "single" else [0.127, 0.298])


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
    assert points(result.basic(B.IMPACT_SINGLE)) == {CAP: (1, 171.05, 0.0, 65.33)}  # see the 8-5 test
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
