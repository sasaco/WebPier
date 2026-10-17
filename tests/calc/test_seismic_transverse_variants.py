"""0720 by hand for inputs other than Example2: shares, girder levels, H1, footing, water, zero loads, γ < γ'."""

from decimal import Decimal

import pytest

from reaction_support import D, END_SLOTS, ORIGIN_SLOTS, pier, q, value
from seismic_transverse_support import chain, points, seismic
from transverse_support import dims
from webpier.calc.frame import NodeRole, Region
from webpier.calc.seismic_transverse import SeismicCase
from webpier.calc.transverse import BasicCase, Item, Track
from webpier.core.errors import InputError

C = SeismicCase
WEIGHTS = "下部構造/単位体積重量/"
SURFACE_WET = "地盤データ/層/0/単位体積重量/湿潤"


def hand_train(rows, reaction_b, reaction_c):
    """[(N, M)] and Σ of (side, share, arm) rows: N = R × share, M = N × arm, each rounded to 2 decimals."""
    out = []
    for side, share, arm in rows:
        n = q((reaction_b if side == "B" else reaction_c) * D(share), 2)
        out.append((n, q(n * D(arm), 2)))
    return out, sum(n for n, _ in out), sum(m for _, m in out)


def test_asymmetric_shares_give_two_different_track_tables_and_both_combinations():
    # Up (L2) of B: 0.100, 0.200, 0.300, 0.400 at −3.8, −1.5, 1.5, 3.8; down (L1) unchanged.
    p = pier(**{f"{ORIGIN_SLOTS}/{i}/列車分担/L2": share for i, share in enumerate((0.1, 0.2, 0.3, 0.4))})
    result = seismic(p)
    up_rows = [("B", 0.1, -3.8), ("B", 0.2, -1.5), ("B", 0.3, 1.5), ("B", 0.4, 3.8), ("C", 0.143, -2.95),
               ("C", 0.857, 2.95)]
    rows, n, m = hand_train(up_rows, D(320), D(160))
    up = result.train(Track.UP)
    assert [(value(r.n), value(r.m)) for r in up.rows] == rows
    # 32 + 64 + 96 + 128 + 22.88 + 137.12 = 480.00; −121.60 − 96.00 + 144.00 + 486.40 − 67.50 + 404.50 = 749.80
    assert (value(up.n), value(up.m)) == (n, m) == (Decimal("480.00"), Decimal("749.80"))
    down = result.train(Track.DOWN)
    assert (down.n.value, down.m.value) == (480.0, -1028.62)
    # Both tracks are combined (decision 21); neither is chosen as governing here.
    assert points(result.basic(C.TRAIN_UP)) == {2: (480.0, 0.0, 749.8)}
    assert points(result.basic(C.TRAIN_DOWN)) == {2: (480.0, 0.0, -1028.62)}
    assert [(c.track, C.TRAIN_UP in c.cases, C.TRAIN_DOWN in c.cases) for c in result.combinations] == [
        (Track.UP, True, False), (Track.DOWN, False, True)]


def test_a_track_without_load_on_this_pier_still_has_its_case_and_combination():
    # L1 = 0 everywhere: the down-track table is all zero but stays, with its combination.
    changes = {f"{ORIGIN_SLOTS}/{i}/列車分担/L1": 0.0 for i in range(4)}
    changes |= {f"{END_SLOTS}/{i}/列車分担/L1": 0.0 for i in range(2)}
    result = seismic(pier(**changes))
    assert [row.n.value for row in result.train(Track.DOWN).rows] == [0.0] * 6
    assert points(result.basic(C.TRAIN_DOWN)) == {2: (0.0, 0.0, 0.0)}
    assert len(result.combinations) == 2


def test_earthquake_train_load_zero():
    result = seismic(pier(**{"上部構造/列車/軸重/地震": 0.0}))
    for track in Track.UP, Track.DOWN:
        assert [row.n.value for row in result.train(track).rows] == [0.0] * 6
    assert points(result.basic(C.TRAIN_UP)) == {2: (0.0, 0.0, 0.0)}
    assert points(result.basic(C.TRAIN_INERTIA)) == {2: (0.0, 0.0, 0.0)}
    assert len(result.basic_cases) == 9  # a zero case stays in the table and the combinations
    assert points(result.basic(C.GIRDER_INERTIA)) == {2: (0.0, 9090.0, 27103.86)}


def test_girder_inertia_is_the_0600_force_at_its_height_without_a_second_kh():
    p = pier(**{f"{ORIGIN_SLOTS}/0/雪荷重_2年確率": 212.34, "上部構造/起点側/重心高_hs": 3.333})
    _, reaction, _, result = chain(p)
    # B: 5740 + 520 + 472.34 = 6732.34 at hs 3.333: 6732.34 × 3.333 = 22438.8892 -> 22438.89;
    # C: 2370.00 × 3.066 = 7266.42 (the Example2 input).
    origin = q(D("6732.34") * D("3.333"), 2)
    assert value(result.girder_inertia.rows[0].m) == origin == Decimal("22438.89")
    assert value(result.girder_inertia.rows[0].h) == value(reaction.transverse.origin.seismic_girder.force)
    h, m = D("6732.34") + 2370, origin + D("7266.42")  # 9102.34, 29705.31
    assert points(result.basic(C.GIRDER_INERTIA)) == {2: (0.0, float(h), float(m))}


def test_train_inertia_by_hand_with_other_girder_lengths_and_heights():
    p = pier(**{"上部構造/起点側/桁長/スパン長": 21.35, "上部構造/終点側/高さ/h3": 1.25, "上部構造/列車/車両高/地震重心高": 1.6})
    result = seismic(p)
    rb = q(D(32) * (D(0.575) + D(21.35) + D(0.575)) / 2, 2)  # 32.00 × 22.500 / 2 = 360.00
    hb, hc = q(rb * D("0.30"), 2), q(D(160) * D("0.30"), 2)  # 108.00, 48.00
    yb = D("0.15") + D("2.6") + D("1.1") + D("1.6")  # 5.450
    yc = D("0.1") + D("2.65") + D("1.25") + D("1.6")  # 5.600
    mb, mc = q(hb * yb, 2), q(hc * yc, 2)  # 588.60, 268.80
    train = result.train_inertia
    assert [(value(r.h), value(r.y), value(r.m)) for r in train.rows] == [(hb, yb, mb), (hc, yc, mc)]
    assert points(result.basic(C.TRAIN_INERTIA)) == {2: (0.0, float(hb + hc), float(mb + mc))}
    # The seismic train table of the up track uses RB = 360.00: G4 = 360.00 × 0.471 = 169.56.
    assert result.train(Track.UP).rows[3].n.value == 169.56


def test_girders_at_two_levels_get_a_node_each():
    # Origin h1 + h2 = 0.150 + 2.800 = 2.950, end 0.100 + 2.650 = 2.750: node 1 at the origin girder, node 2 at
    # the end girder, node 3 the beam top; the loads stay at the bearing seat.
    result = seismic(pier(**{"上部構造/起点側/高さ/h2": 2.8}))
    frame = result.frame
    origin, end, top = frame.node(NodeRole.GIRDER_ORIGIN), frame.node(NodeRole.GIRDER_END), frame.node(NodeRole.CAP_TOP)
    assert [(n.number, n.y.value) for n in (origin, end, top)] == [(1, 13.25), (2, 13.05), (3, 10.3)]
    girders = [m for m in frame.members if m.region is Region.GIRDER]
    assert [(m.number, m.start, m.end, m.height.value, m.rigid) for m in girders] == [
        (1, 1, 2, 0.2, True), (2, 2, 3, 2.75, True)]
    assert set(points(result.basic(C.TRAIN_UP))) == {3}
    assert frame.support.node == 9


def test_the_end_girder_may_be_the_higher_one():
    frame = seismic(pier(**{"上部構造/終点側/高さ/h1": 0.3})).frame  # end 0.300 + 2.650 = 2.950
    assert (frame.node(NodeRole.GIRDER_END).number, frame.node(NodeRole.GIRDER_ORIGIN).number) == (1, 2)


def test_a_girder_level_at_the_seat_adds_no_node():
    # h1 + h2 = 0 on the end side: that level is the bearing seat itself (no zero-length member).
    frame = seismic(pier(**{"上部構造/終点側/高さ/h1": 0.0, "上部構造/終点側/高さ/h2": 0.0})).frame
    top = frame.node(NodeRole.CAP_TOP)
    assert frame.node(NodeRole.GIRDER_END) is top and top.number == 2
    assert [m.region for m in frame.members][:2] == [Region.GIRDER, Region.BEAM]
    assert len(frame.nodes) == 8


def test_both_girder_levels_at_the_seat_add_no_member():
    zero = {f"上部構造/{side}/高さ/{h}": 0.0 for side in ("起点側", "終点側") for h in ("h1", "h2")}
    frame = seismic(pier(**zero)).frame
    top = frame.node(NodeRole.CAP_TOP)
    assert top.number == 1 and {NodeRole.GIRDER_ORIGIN, NodeRole.GIRDER_END} <= top.roles
    assert all(m.region is not Region.GIRDER for m in frame.members) and len(frame.nodes) == 7


PEDESTAL = dims(B2=0.5, B3=1.0, W2=0.5, W3=7.0, H1=0.3)


def test_pedestal_inertia_and_bearing_loads_at_the_pedestal_top():
    _, reaction, transverse, result = chain(pier(**PEDESTAL))
    frame = result.frame
    top, base, cap = (frame.node(role) for role in (NodeRole.PEDESTAL_TOP, NodeRole.PEDESTAL_BASE, NodeRole.CAP_TOP))
    x_p = value(reaction.self_weight.pedestal.x_c)  # the pedestal centre across the track (0600)
    assert x_p != 0
    assert (value(base.x), value(top.x), top.y.value) == (x_p, x_p, 10.6)
    # The girder level is h1 + h2 = 2.750 above the seat (the pedestal top), on the pedestal axis.
    girder = frame.node(NodeRole.GIRDER_ORIGIN)
    assert (girder.number, value(girder.x), girder.y.value) == (1, x_p, 13.35)
    assert next(m for m in frame.members if m.region is Region.GIRDER).end == top.number
    # 桁受け: B3 × W3 × γ × Kh = 1.000 × 7.000 × 24.5 × 1.00 = 171.50 kN/m over the pedestal member.
    pedestal = result.self_weight.pedestal
    assert pedestal.value.value == 171.5
    member = next(m for m in frame.members if m.region is Region.PEDESTAL)
    loads = {load.member: (load.start.value, load.end.value) for load in result.basic(C.SELF_INERTIA).member_loads}
    assert loads[member.number] == (171.5, 171.5)
    assert next(m for m in frame.members if m.region is Region.GIRDER).number not in loads
    # Decision 29: N, H and M of the bearings act at the pedestal top; M about the column axis moves to the seat
    # as M − N × x_p, and H × H1 is carried by the frame.
    up = result.train(Track.UP)
    assert up.m.value == 1028.62  # the table keeps the levers from the column axis
    assert points(result.basic(C.TRAIN_UP)) == {top.number: (480.0, 0.0, float(q(D(1028.62) - D(480) * x_p, 2)))}
    assert points(result.basic(C.GIRDER_INERTIA)) == {top.number: (0.0, 9090.0, 27103.86)}
    assert points(result.basic(C.TRAIN_INERTIA)) == {top.number: (0.0, 144.0, 770.4)}
    # D1 as in 0620: the bearing loads at the seat, the pier parts at the beam top.
    ours, theirs = result.basic(C.D1), transverse.basic(BasicCase.D1)
    assert [(p.anchor, p.n, p.m) for p in ours.points] == [(p.anchor, p.n, p.m) for p in theirs.points]
    assert {p.node for p in ours.points} == {top.number, cap.number, frame.node(NodeRole.FOOTING_CENTROID).number}


def test_asymmetric_footing():
    changes = dims(W7=2.5, W9=1.8, H5=0.5, H6=2.2, B8=3.0, W8=5.0) | {"下部構造/土かぶり/終点側_df2": 1.5}
    _, reaction, transverse, result = chain(pier(**changes))
    frame = result.frame
    axis = frame.node(NodeRole.CAP_TOP).x
    assert axis == reaction.self_weight.column.x_c and axis.value == 0.35  # (W7 − W9) / 2
    assert frame.node(NodeRole.GIRDER_ORIGIN).x == axis and frame.node(NodeRole.FOOTING_CENTROID).x.value == 0.0
    footing = reaction.self_weight.footing
    inertia = result.self_weight.footing
    assert inertia.volume == footing.volume
    assert value(inertia.force) == q(value(footing.volume) * (D(24.5) - D(18.0)) * D(1), 2)
    assert points(result.basic(C.SELF_INERTIA)) == {frame.node(NodeRole.FOOTING_CENTROID).number: (
        0.0, inertia.force.value, 0.0)}
    theirs = transverse.basic(BasicCase.D1).points
    assert [(p.n, p.m) for p in result.basic(C.D1).points] == [(p.n, p.m) for p in theirs]


def test_buoyancy_is_the_normal_water_level():
    p = pier(**{"下部構造/水位/高水位_hw1": 4.5, "下部構造/水位/平水位_hw2": 1.2, "下部構造/水位/低水位_hw3": 0.5})
    _, _, transverse, result = chain(p)
    # Normal water 1.200 above the base: 63.000 × 1.200 = 75.600 m3 × −10.0 = −756.00 kN at the footing centroid.
    assert result.buoyancy == transverse.buoyancy[1]
    assert points(result.basic(C.BUOYANCY)) == {7: (-756.0, 0.0, 0.0)}
    dry = seismic(pier(**{"下部構造/水位/平水位_hw2": 0.0}))
    assert points(dry.basic(C.BUOYANCY)) == {7: (0.0, 0.0, 0.0)}


def test_snow_is_the_2_year_snow_with_its_moment():
    p = pier(**{f"{ORIGIN_SLOTS}/0/雪荷重_2年確率": 210.0, f"{END_SLOTS}/1/雪荷重_2年確率": 135.0})
    _, _, transverse, result = chain(p)
    assert result.snow == transverse.snow[0]
    # M = 210 × −3.8 + 30 × −1.5 + 30 × 1.5 + 200 × 3.8 + 125 × −2.95 + 135 × 2.95 = −38.00 + 29.50 = −8.50
    assert points(result.basic(C.SNOW)) == {2: (730.0, 0.0, -8.5)}


def test_self_weight_inertia_with_unround_sizes():
    p = pier(**dims(B1=2.655, W1=8.95, B4=0.105, B5=0.2, W4=2.275, W5=2.125, B6=2.35, W6=4.45)
             | {WEIGHTS + "梁・躯体": 24.7})
    inertia = seismic(p).self_weight
    assert value(inertia.beam_top.value) == q(D(2.655) * D(8.95) * D(24.7), 2)  # 586.927575 -> 586.93
    assert value(inertia.beam_bottom.value) == q(D(2.35) * D(4.55) * D(24.7), 2)  # 264.10475 -> 264.10
    loads = {load.member: (load.start.value, load.end.value) for load in seismic(p).basic(C.SELF_INERTIA).member_loads}
    assert loads[3] == (586.93, 264.1)  # the haunch taper, → (+x)


def test_footing_lighter_than_the_displaced_soil_stops_0720():
    # Decision 32 (as 0710): γ < γ' would give a footing inertia against the earthquake.
    with pytest.raises(InputError, match=r"下部構造\.単位体積重量\.フーチング.*地盤データ\.層\.0\.単位体積重量\.湿潤"):
        seismic(pier(**{WEIGHTS + "フーチング": 17.9}))


def test_footing_as_heavy_as_the_displaced_soil_has_no_inertia():
    result = seismic(pier(**{WEIGHTS + "フーチング": 18.0, SURFACE_WET: 18.0}))
    assert result.self_weight.footing.force.value == 0.0
    assert points(result.basic(C.SELF_INERTIA)) == {7: (0.0, 0.0, 0.0)}


def test_bearing_rows_follow_the_entered_slots():
    result = seismic()
    assert [(row.item, row.slot) for row in result.train(Track.DOWN).rows] == [
        (Item.ORIGIN, 0), (Item.ORIGIN, 1), (Item.ORIGIN, 2), (Item.ORIGIN, 3), (Item.END, 0), (Item.END, 1)]
