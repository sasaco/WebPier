"""0620 frame and vertical actions: Example2 09 pp.9-1 to 9-6 and hand calculations from the printed operands."""

from decimal import Decimal

import pytest

from reaction_support import D, pier_ratios, q, value
from transverse_support import (
    SECTIONS, chain, diagram, items, key, product, points, table, transverse,
)
from webpier.calc.frame import Direction, NodeRole, Region
from webpier.calc.longitudinal import SpringTerm
from webpier.calc.transverse import BasicCase, Item, Track

B = BasicCase


def cells(row):
    return [row.n.value, row.arm.value, row.m.value]


def bearing_cells(table_):
    return {key(row): cells(row) for row in table_.rows if row.item in (Item.ORIGIN, Item.END)}


def test_9_1_and_9_2_transverse_frame():
    frame = transverse().frame
    model = items("frame_model")
    assert frame.direction is Direction.TRANSVERSE
    assert [m.height.value for m in frame.members] == [model[f"member{n}_length"]["value"] for n in range(1, 6)]
    assert [m.region for m in frame.members] == [Region.BEAM, Region.HAUNCH, Region.COLUMN, Region.FOOTING_UPPER,
                                                 Region.FOOTING_LOWER]
    spring_table = SECTIONS["frame_model"]["tables"][0]
    spring_rows = {row["key"]: [c["value"] for c in row["cells"]] for row in spring_table["rows"]}
    assert [frame.support.long_term.kr.value, frame.support.short_term.kr.value] == spring_rows["Kr"]  # Kr transverse
    section = items("section_properties")
    assert (frame.column_section.width.value, frame.column_section.depth.value) == (
        section["column_b"]["value"], section["column_h"]["value"])  # b = 2.70 (B6), h = 4.50 (W6) in the plane
    assert frame.column_section.inertia.value == section["column_inertia"]["value"]
    assert frame.materials.column.modulus.value == section["Ec_body_mantissa"]["value"]


def test_9_3_fixed_dead_load():
    printed, rows = items("dead_load"), table("dead_load")
    fixed = transverse().fixed
    assert (fixed.column_q.value, fixed.column_q.digits) == (printed["column_q"]["value"], 2)  # 2.70 × 4.50 × 24.5
    # Every bearing at its own position across the track (9-3: arms ∓3.800 / ∓1.500 and ∓2.950).
    assert bearing_cells(fixed.table) == {k: rows[k] for k in ("RB_G1", "RB_G2", "RB_G3", "RB_G4", "RC_G1", "RC_G2")}
    # Example2 prints the beam as the prism 1190.70 and the haunch wings 104.19 and deducts q × 2.00 (H2).
    # As in 0610 we take the 0600 beam weight (prism + whole haunch, 1503.27, xC = (W5 − W4)/2 = 0.000) and deduct
    # q over H2 + H3 = 2.700, where the column line load overlaps it. N is the same: 9103.27 − 297.68 × 2.700
    # = 8299.534 -> 8299.53 = 8894.89 − 297.68 × 2.00.
    beam = fixed.table.row(Item.BEAM)
    assert cells(beam) == [1503.27, 0.0, 0.0]
    assert [row.item for row in fixed.table.rows][-1] is Item.BEAM  # no pedestal: no pedestal table nor q
    assert fixed.pedestal is None and fixed.pedestal_q is None
    assert fixed.table.n.value == 9103.27
    assert fixed.overlap.value == 2.7
    assert fixed.n.value == printed["top_N"]["value"] == 8299.53
    assert fixed.m.value == printed["top_M"]["value"] == rows["total"][2] == 0.0
    assert cells(fixed.footing) == [printed["footing_W3"]["value"], 0.0, 0.0]


def test_9_3_additional_dead_load_and_soil():
    printed, rows = items("superimposed_dead_load"), table("superimposed_dead_load")
    additional = transverse().additional
    assert bearing_cells(additional.table) == {k: v for k, v in rows.items() if k != "total"}
    assert [additional.table.n.value, additional.table.m.value] == [rows["total"][0], rows["total"][2]]
    assert (additional.soil.item, additional.soil.n.value, additional.soil.m.value) == (
        Item.OVERBURDEN, printed["soil_sumP"]["value"], 0.0)


def test_9_4_buoyancy():
    printed = items("buoyancy")
    water = transverse().buoyancy
    assert [row.n.value for row in water] == [printed[k]["value"] for k in ("omega1_high", "omega2_mean", "omega3_low")]
    assert {row.item for row in water} == {Item.WATER}


@pytest.mark.parametrize("index,name", [(0, "snow_2yr"), (1, "snow_10yr"), (2, "snow_30yr")])
def test_9_4_snow(index, name):
    rows = table("snow_load", name)
    snow = transverse().snow[index]
    assert bearing_cells(snow) == {k: v for k, v in rows.items() if k != "total"}
    assert [snow.n.value, snow.m.value] == [rows["total"][0], rows["total"][2]]


def hand_table(rows, factor_of, base_of):
    """{row key: (base, factor, N, M)} with N = base × factor (2 decimals) and M = N × arm, plus the printed totals."""
    hand = {}
    for row in rows:
        n = product(base_of(row), factor_of(row))
        hand[key(row)] = (D(base_of(row)), D(factor_of(row)), n, product(n, row.arm.value))
    return hand, sum(h[2] for h in hand.values()), sum(h[3] for h in hand.values())


def ours(table_, base, factor):
    return {key(r): (value(getattr(r, base)), value(getattr(r, factor)), value(r.n), value(r.m)) for r in table_.rows}


def printed_rows(section, name):
    rows = table(section, name)
    return {k: (D(v[0]), D(v[1]), D(v[2]), D(v[4])) for k, v in rows.items() if k != "total"}, rows["total"]


def differences(hand, printed):
    return {k: (hand[k], printed[k]) for k in hand if hand[k] != printed[k]}


# Up = L2, down = L1 (Example2 9-5: RB G1 up −0.020 = L2 of slot 1; consistent with 11-8, decision 21).
SHARES = {Track.UP: lambda b: b.shares.l2, Track.DOWN: lambda b: b.shares.l1}


@pytest.mark.parametrize("track,name", [(Track.UP, "single_track_up"), (Track.DOWN, "single_track_down"),
                                        (Track.DOUBLE, "double_track")])
def test_9_5_train_per_bearing(track, name):
    p, reaction, result = chain()
    train = result.train.table(track)
    assert train.track is track
    girders = ((Item.ORIGIN, reaction.dead.origin), (Item.END, reaction.dead.end))
    bearings = {(g.value, b.slot): b for g, girder in girders for b in girder.bearings}
    loading = reaction.train.loading
    for row in train.rows:
        bearing = bearings[(row.item.value, row.slot)]
        expected = bearing.double if track is Track.DOUBLE else SHARES[track](bearing.bearing)
        assert row.share == expected
        assert row.reaction == (loading.rb if row.item is Item.ORIGIN else loading.rc)  # 272.47 / 294.92, no ρf
        assert row.arm == bearing.bearing.position
    hand, n, m = hand_table(train.rows, lambda r: r.share.value, lambda r: r.reaction.value)
    assert ours(train, "reaction", "share") == hand
    assert (value(train.n), value(train.m)) == (n, m)  # totals: sums of the printed rows (ADR-0003)
    printed, total = printed_rows("train_load", name)
    assert set(printed) == set(hand)
    # Example2 9-5 holds hidden digits (notes item 1, 2); from the printed operands:
    expected = {
        Track.UP: {  # 128.33 × 3.8 = 487.654; 42.17 × −2.95 = −124.4015; 252.75 × 2.95 = 745.6125
            "RB_G4": ("487.65", "487.66"), "RC_G1": ("-124.40", "-124.41"), "RC_G2": ("745.61", "745.60")},
        Track.DOWN: {"RB_G1": ("-487.65", "-487.66"), "RC_G1": ("-745.61", "-745.60"), "RC_G2": ("124.40", "124.41")},
        Track.DOUBLE: {  # 272.47 × 0.451 = 122.88397 -> 122.88, × −3.8 = −466.944; 272.47 × 0.549 = 149.58603
            "RB_G1": ("-466.94", "-466.95"), "RB_G4": ("466.94", "466.95")},
    }[track]
    diff = differences(hand, printed)
    if track is Track.DOUBLE:
        assert {k: (h[2], p_[2]) for k, (h, p_) in diff.items() if h[2] != p_[2]} == {
            "RB_G2": (Decimal("149.59"), Decimal("149.58")), "RB_G3": (Decimal("149.59"), Decimal("149.58"))}
        expected |= {"RB_G2": ("-224.39", "-224.38"), "RB_G3": ("224.39", "224.38")}  # 149.59 × 1.5 = 224.385
    assert {k: (h[3], p_[3]) for k, (h, p_) in diff.items()} == {
        k: (Decimal(a), Decimal(b)) for k, (a, b) in expected.items()}
    # Totals: up/down 567.38 (9-5: 567.39), M ±1210.09 (9-5: ±1210.08); double 1134.78 (9-5: 1134.77), M 0.00.
    assert (str(n), str(m)) == {Track.UP: ("567.38", "1210.09"), Track.DOWN: ("567.38", "-1210.09"),
                                Track.DOUBLE: ("1134.78", "0.00")}[track]
    assert (total[2], total[4]) == {Track.UP: (567.39, 1210.08), Track.DOWN: (567.39, -1210.08),
                                    Track.DOUBLE: (1134.77, 0.0)}[track]


@pytest.mark.parametrize("track,name", [(Track.UP, "single_track_up"), (Track.DOWN, "single_track_down"),
                                        (Track.DOUBLE, "double_track")])
def test_9_6_impact_with_the_coefficients_on_the_pier_body(track, name):
    # Decision 77: i = i0 × (1 − Ds/(L + Du + Ds)). Example2 9-6 prints the girder coefficients 0.245 / 0.546, double
    # 0.222 / 0.521 (no reduction, classification 3 in transverse_notes.md); with the ratios 0.751 (single) and
    # 0.763 (double) of test_reaction_train: 0.245 × 0.751 = 0.184, 0.546 × 0.751 = 0.410, 0.222 × 0.763 = 0.169,
    # 0.521 × 0.763 = 0.398.
    _, reaction, result = chain()
    impact = result.impact.ultimate.table(track)
    train = result.train.table(track)
    group = reaction.train.ultimate
    ratio = dict(zip(("single", "double"), pier_ratios(reaction)))["double" if track is Track.DOUBLE else "single"]
    for row, load in zip(impact.rows, train.rows, strict=True):
        girder = group.origin_impact if row.item is Item.ORIGIN else group.end_impact
        i0 = girder.double if track is Track.DOUBLE else girder.single
        assert value(row.coefficient) == q(D(i0.value) * ratio, 3)
        assert (row.item, row.slot, row.train, row.arm) == (load.item, load.slot, load.n, load.arm)
    hand, n, m = hand_table(impact.rows, lambda r: r.coefficient.value, lambda r: r.train.value)
    assert ours(impact, "train", "coefficient") == hand
    assert (value(impact.n), value(impact.m)) == (n, m)
    # The sums of the printed rows, by hand: UP −1.00 + 8.82 + 18.70 + 23.61 + 17.29 + 103.63 = 171.05 and
    # 3.80 − 13.23 + 28.05 + 89.72 − 51.01 + 305.71 = 363.04; DOWN mirrors it; DOUBLE
    # 20.77 + 25.28 + 25.28 + 20.77 + 117.38 + 117.38 = 326.86, the moments cancel.
    expected = {Track.UP: ("171.05", "363.04"), Track.DOWN: ("171.05", "-363.04"), Track.DOUBLE: ("326.86", "0.00")}
    assert (str(n), str(m)) == expected[track]
    # 9-6 prints RC G2 M 407.1 with 1 decimal; ours keeps 2.
    assert all(row.m.digits == 2 for row in impact.rows)


@pytest.mark.parametrize("track", list(Track))
def test_serviceability_impact_uses_the_serviceability_coefficients_on_the_pier_body(track):
    _, reaction, result = chain()
    impact = result.impact.service.table(track)
    group = reaction.train.service  # 07 7-2: 0.75 i = 0.184 / 0.41, double 0.167 / 0.391; times the ratio
    ratio = dict(zip(("single", "double"), pier_ratios(reaction)))["double" if track is Track.DOUBLE else "single"]
    for row, load in zip(impact.rows, result.train.table(track).rows, strict=True):
        girder = group.origin_impact if row.item is Item.ORIGIN else group.end_impact
        i0 = girder.double if track is Track.DOUBLE else girder.single
        assert value(row.coefficient) == q(D(i0.value) * ratio, 3)
        assert row.train == load.n
    hand, n, m = hand_table(impact.rows, lambda r: r.coefficient.value, lambda r: r.train.value)
    assert ours(impact, "train", "coefficient") == hand and (value(impact.n), value(impact.m)) == (n, m)
    expected = {0.127, 0.298} if track is Track.DOUBLE else {0.138, 0.308}  # 0.167 × 0.763, 0.391 × 0.763; 0.184 × 0.751, 0.41 × 0.751
    assert {row.coefficient.value for row in impact.rows} == expected


CAP, FOOTING = 1, 5


def test_9_9_to_9_11_load_diagrams_vertical():
    result = transverse()
    printed = diagram(1)
    assert points(result.basic(B.D1)) == {CAP: (printed["N"], 0.0, printed["M"]), FOOTING: (printed["P"], 0.0, 0.0)}
    (line,) = result.basic(B.D1).line_loads
    assert (line.members, line.n.value, line.h.value) == ((1, 2, 3), printed["q"], 0.0)  # q over 7.600 m
    printed = diagram(2)
    assert points(result.basic(B.D2)) == {CAP: (printed["N"], 0.0, printed["M"]), FOOTING: (printed["P"], 0.0, 0.0)}
    for case in (B.BUOYANCY_HIGH, B.BUOYANCY_NORMAL, B.BUOYANCY_LOW):
        assert points(result.basic(case)) == {FOOTING: (diagram(case.value)["P"], 0.0, 0.0)}
    for case in (B.SNOW2, B.SNOW10, B.SNOW30):
        assert points(result.basic(case)) == {CAP: (diagram(case.value)["N"], 0.0, diagram(case.value)["M"])}
    # Train and impact: our totals of the printed rows (see the 9-5 / 9-6 tests).
    for case, track in ((B.TRAIN_UP, Track.UP), (B.TRAIN_DOWN, Track.DOWN), (B.TRAIN_DOUBLE, Track.DOUBLE)):
        train = result.train.table(track)
        assert points(result.basic(case)) == {CAP: (train.n.value, 0.0, train.m.value)}
        assert result.basic(case).track is track
    for case, track in ((B.IMPACT_UP, Track.UP), (B.IMPACT_DOWN, Track.DOWN), (B.IMPACT_DOUBLE, Track.DOUBLE)):
        impact = result.impact.ultimate.table(track)
        assert points(result.basic(case)) == {CAP: (impact.n.value, 0.0, impact.m.value)}
    assert [points(result.basic(c))[CAP] for c in (B.TRAIN_UP, B.IMPACT_UP)] == [(567.38, 0.0, 1210.09),
                                                                                 (171.05, 0.0, 363.04)]
    for action in result.basic_cases:
        if action.case is not B.D1:
            assert action.line_loads == ()
        if action.case.value < 16:
            assert action.member_loads == ()


def test_9_13_basic_cases_and_springs():
    printed = {row["no"]: row for row in SECTIONS["basic_cases"]["rows"]}
    result = transverse()
    assert [action.case.value for action in result.basic_cases] == list(range(1, 18))
    terms = {1: SpringTerm.LONG, 2: SpringTerm.SHORT}  # バネ 1 / 2 = long / short term (decision 28)
    assert [action.spring for action in result.basic_cases] == [terms[printed[n]["spring"]] for n in range(1, 18)]
    assert [action.horizontal for action in result.basic_cases] == [n >= 15 for n in range(1, 18)]
    assert [action.track for action in result.basic_cases][8:14] == [Track.UP, Track.DOWN, Track.DOUBLE] * 2
    assert {action.track for action in result.basic_cases[:8] + result.basic_cases[14:]} == {None}


def test_anchor_nodes():
    frame = transverse().frame
    assert frame.node(NodeRole.CAP_TOP).number == CAP and frame.node(NodeRole.FOOTING_CENTROID).number == FOOTING
