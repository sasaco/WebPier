"""Moving point loads on the two girders: Example2 07 7-1/7-14 and hand cases for the search rules, the line load
behind the axles, the train running either way and the trains of one vehicle (decision 101)."""

from decimal import Decimal

import pytest

from reaction_support import example2, pier
from webpier.calc.moving_load import AxleTrain, Girder, car_offsets, search_reactions
from webpier.calc.vehicles import vehicle
from webpier.core.errors import InputError
from webpier.core.printed import FORCE, LINE_LOAD

TRAIN = example2("07_7-1_support_reactions_and_service_train")
LATERAL = example2("07_7-14_vehicle_lateral")


def spans(origin, end):
    o, e = origin, end
    return pier(**{"上部構造/起点側/桁長": {"L1": o[0], "スパン長": o[1], "L2": o[2]},
                   "上部構造/終点側/桁長": {"L1": e[0], "スパン長": e[1], "L2": e[2]}}).spans


def cars(load, count, car_length, a1, a2):
    offsets = car_offsets(count, Decimal(str(car_length)), Decimal(str(a1)), Decimal(str(a2)))
    return AxleTrain("cars", (FORCE(load),) * len(offsets), offsets)


def run(p_spans, load, count, car_length, a1, a2):
    return search_reactions(p_spans.origin, p_spans.end, (cars(load, count, car_length, a1, a2),))


def train(loads, gaps, tail=None, tail_gap="0"):
    offsets = [Decimal(0)]
    for gap in gaps:
        offsets.append(offsets[-1] + Decimal(gap))
    return AxleTrain("hand", tuple(FORCE(load) for load in loads), tuple(offsets),
                     None if tail is None else LINE_LOAD(tail), Decimal(tail_gap))


def levers(result, girder):
    return sorted(axle.lever.value for axle in result.axles if axle.girder is girder)


def positions(result, p_spans):
    """Axle positions from the origin end, by hand from the levers: A + a on the origin girder, D − a on the end."""
    o, e = p_spans.origin, p_spans.end
    a = o.l1.value
    d = o.l1.value + o.span.value + o.l2.value + e.l1.value + e.span.value
    return sorted(round(a + axle.lever.value if axle.girder is Girder.ORIGIN else d - axle.lever.value, 3)
                  for axle in result.axles)


def reactions(result):
    return tuple(r.value for r in (result.ra, result.rb, result.rc, result.rd))


def test_example2_train_7_1():
    p = pier()
    result = search_reactions(p.spans.origin, p.spans.end, vehicle(p.train).trains)
    assert result.train == "P-16" and result.tails == () and result.tail_head is None
    # RB = 160.00×(16.625＋14.425＋1.625＋-0.575)/18.850, RC = 160.00×(7.425＋9.625)/9.250
    assert levers(result, Girder.ORIGIN) == [-0.575, 1.625, 14.425, 16.625]
    assert levers(result, Girder.END) == [7.425, 9.625]
    assert reactions(result) == tuple(TRAIN[f"serviceability_train.{s}"] for s in ("RA", "RB", "RC", "RD"))
    assert positions(result, p.spans) == [0.0, 2.2, 15.0, 17.2, 20.0, 22.2]


def test_example2_vehicle_lateral_axles_7_14():
    p = pier()
    result = run(p.spans, 32.0, 1, 10.0, 2.8, 2.2)
    assert levers(result, Girder.ORIGIN) == [14.425, 16.625]
    assert levers(result, Girder.END) == [7.425, 9.625]
    assert (result.rb.value, result.rc.value) == (LATERAL["vehicle_lateral.start.HB"], LATERAL["vehicle_lateral.end.HC"])


def test_adopted_reactions_are_recomputed_from_the_printed_levers():
    result = run(pier().spans, 160.0, 10, 20.0, 2.8, 2.2)
    # 160 × 32.100 / 18.850 = 272.4668 -> 272.47; RA = 160 × 4 - 272.47.
    assert result.rb.value == 272.47 and result.ra.value == 367.53
    assert (result.rb.digits, result.axles[0].lever.digits) == (2, 3)


def test_single_axle_at_the_joint_goes_to_the_larger_side():
    # One axle on the bridge (the second axle is 99 m behind). At the joint x = 11.000:
    # origin RB = P × 10.500/10 = 1.05P, end RC = P × 5.300/5 = 1.06P -> the end girder.
    result = run(spans((0.5, 10.0, 0.5), (0.3, 5.0, 0.3)), 100.0, 1, 100.0, 1.0, 0.0)
    assert [(a.girder, a.lever.value) for a in result.axles] == [(Girder.END, 5.3)]
    assert reactions(result) == (0.0, 0.0, 106.0, -6.0)


def test_joint_prefers_the_origin_girder_when_it_gives_more():
    result = run(spans((0.5, 5.0, 0.5), (0.3, 10.0, 0.3)), 100.0, 1, 100.0, 1.0, 0.0)
    # Origin: 5.500/5 = 1.10P; end: 10.300/10 = 1.03P.
    assert [(a.girder, a.lever.value) for a in result.axles] == [(Girder.ORIGIN, 5.5)]
    assert reactions(result) == (-10.0, 110.0, 0.0, 0.0)


def test_joint_tie_goes_to_the_end_girder():
    result = run(spans((0.5, 10.0, 0.5), (0.5, 10.0, 0.5)), 100.0, 1, 100.0, 1.0, 0.0)
    assert [(a.girder, a.lever.value) for a in result.axles] == [(Girder.END, 10.5)]


def test_equal_totals_keep_the_first_candidate_found():
    # Axles 3 m apart on two 10 m girders without overhangs. (7, 10) and (10, 13) both give RB+RC = 1.7P;
    # the search meets (axle 0 at the joint) first and keeps it.
    result = run(spans((0.0, 10.0, 0.0), (0.0, 10.0, 0.0)), 100.0, 1, 4.0, 1.0, 0.0)
    assert reactions(result) == (30.0, 70.0, 100.0, 0.0)


def test_two_axle_cars_when_a2_is_zero():
    # Cars of 2 axles 3.000 m apart within the car and 1.000 m across the coupling.
    p_spans = spans((0.0, 10.0, 0.0), (0.0, 10.0, 0.0))
    result = run(p_spans, 100.0, 2, 4.0, 1.0, 0.0)
    loaded = positions(result, p_spans)
    gaps = {round(b - a, 3) for a, b in zip(loaded, loaded[1:])}
    assert gaps <= {1.0, 3.0}


def test_axles_beyond_the_bridge_are_not_loaded():
    p_spans = pier().spans
    result = run(p_spans, 160.0, 10, 20.0, 2.8, 2.2)
    assert all(0 <= x <= 30.0 for x in positions(result, p_spans))


def test_a_zero_axle_load_has_no_maximum():
    with pytest.raises(InputError, match="最大"):
        run(pier().spans, 0.0, 1, 10.0, 2.8, 2.2)


def test_the_axle_counts_of_each_girder_are_part_of_the_result():
    """RA = P × (axles on the origin girder) − RB: the report prints the count from the result."""
    result = run(pier().spans, 160.0, 10, 20.0, 2.8, 2.2)
    assert (result.origin_axles.value, result.end_axles.value) == (4, 2)  # Example2 7-1: 160.00×4−272.47, ×2−294.92
    assert (result.origin_axles.digits, result.origin_axles.unit) == (0, "")
    lateral = run(pier().spans, 32.0, 1, 10.0, 2.8, 2.2)
    assert (lateral.origin_axles.value, lateral.end_axles.value) == (2, 2)
    assert result.origin_axles.value == sum(axle.girder is Girder.ORIGIN for axle in result.axles)


def test_example2_figure_dimensions_7_1_and_7_14():
    """The spacings of the bearings A, D and the axles and the girder lengths, read from the figures of 7-1/7-14."""
    train = run(pier().spans, 160.0, 10, 20.0, 2.8, 2.2)
    assert [s.value for s in train.spacings] == [0.575, 1.625, 12.8, 2.2, 2.8, 2.2, 7.425]
    assert [g.value for g in train.girder_lengths] == [20.0, 10.0]
    lateral = run(pier().spans, 32.0, 1, 10.0, 2.8, 2.2)
    assert [s.value for s in lateral.spacings] == [14.425, 2.2, 2.8, 2.2, 7.425]
    assert {s.digits for s in (*train.spacings, *train.girder_lengths)} == {3}


def test_an_axle_on_a_far_bearing_makes_no_zero_spacing():
    # Cars of 2 axles 9 m + 1 m apart on two 10 m girders without overhangs: axles at 0, 1, 10, 11, 20,
    # and the bearings A = 0 and D = 20 are on the end axles.
    p_spans = spans((0.0, 10.0, 0.0), (0.0, 10.0, 0.0))
    result = run(p_spans, 100.0, 3, 10.0, 1.0, 0.0)
    assert positions(result, p_spans) == [0.0, 1.0, 10.0, 11.0, 20.0]
    assert [s.value for s in result.spacings] == [1.0, 9.0, 1.0, 9.0]


def test_the_line_load_behind_the_axles_by_hand():
    """One 100 kN axle and 10 kN/m from 1 m behind it on two 10 m girders without overhangs: RB+RC is largest with the
    axle at the joint (it goes to the end girder on the tie), 100 + 10 × 9 × 4.5 / 10 = 140.5; the line load is cut at
    the bridge end."""
    p_spans = spans((0.0, 10.0, 0.0), (0.0, 10.0, 0.0))
    result = search_reactions(p_spans.origin, p_spans.end, (train([100.0], [], tail=10.0, tail_gap="1.0"),))
    assert [(a.girder, a.lever.value, result.load(a).value) for a in result.axles] == [(Girder.END, 10.0, 100.0)]
    assert [(part.girder, part.length.value, part.lever.value) for part in result.tails] == [(Girder.ORIGIN, 9.0, 4.5)]
    # RB = 10 × 9 × 4.5 / 10, RA = 10 × 9 − RB; RC = 100 × 10 / 10, RD = 100 − RC
    assert reactions(result) == (49.5, 40.5, 100.0, 0.0)
    assert result.tail_head.value == 9.0 and [s.value for s in result.spacings] == [9.0, 1.0, 10.0]
    assert result.tail(Girder.END) is None and result.tail(Girder.ORIGIN) is result.tails[0]


def test_a_line_load_over_both_girders_without_an_axle_on_the_bridge():
    """A 1 kN axle and 50 kN/m from 0.5 m behind it on two 2 m girders: the line load over the whole bridge (its head at
    D, the axle beyond it) gives 50 × 2 × 1 / 2 on each pier support, more than any placing with the axle on."""
    p_spans = spans((0.0, 2.0, 0.0), (0.0, 2.0, 0.0))
    result = search_reactions(p_spans.origin, p_spans.end, (train([1.0], [], tail=50.0, tail_gap="0.5"),))
    assert result.axles == () and (result.origin_axles.value, result.end_axles.value) == (0, 0)
    assert [(part.girder, part.length.value, part.lever.value) for part in result.tails] == [
        (Girder.ORIGIN, 2.0, 1.0), (Girder.END, 2.0, 1.0)]
    assert reactions(result) == (50.0, 50.0, 50.0, 50.0)
    assert result.tail_head.value == 4.0 and [s.value for s in result.spacings] == [4.0]


def test_a_line_load_far_behind_stays_off_the_bridge():
    p_spans = spans((0.0, 10.0, 0.0), (0.0, 10.0, 0.0))
    result = search_reactions(p_spans.origin, p_spans.end, (train([100.0], [], tail=1.0, tail_gap="30.0"),))
    assert (result.tails, result.tail_head) == ((), None) and reactions(result) == (0.0, 0.0, 100.0, 0.0)


def test_the_train_runs_either_way():
    """50 kN then 100 kN, 2 m apart, on girders of 10 m and 4 m: towards D the best is 50 + 100 × 0.8 = 130, towards A
    the 100 kN axle at the joint and the 50 kN 2 m before it give 100 + 50 × 0.8 = 140."""
    p_spans = spans((0.0, 10.0, 0.0), (0.0, 4.0, 0.0))
    result = search_reactions(p_spans.origin, p_spans.end, (train([50.0, 100.0], ["2.0"]),))
    assert [(a.girder, a.lever.value, result.load(a).value) for a in result.axles] == [(Girder.ORIGIN, 8.0, 50.0),
                                                                             (Girder.END, 4.0, 100.0)]
    assert reactions(result) == (10.0, 40.0, 100.0, 0.0)


def test_a17_is_adopted_on_short_girders():
    """EA-17 on two 3 m girders: A-17's middle 190 kN axle at the joint with 130 kN 1.9 m ahead and 190 kN 2.0 m behind
    gives RC = (130 × 1.1 + 190 × 3) / 3 = 237.67 and RB = 190 × 1 / 3 = 63.33 (301.00); E-17 gives at most 170 + 170 ×
    1 / 3."""
    p = pier(**{"上部構造/列車/車両名": "EA-17", "上部構造/列車/編成数": None})
    p_spans = spans((0.0, 3.0, 0.0), (0.0, 3.0, 0.0))
    result = search_reactions(p_spans.origin, p_spans.end, vehicle(p.train).trains)
    assert (result.train, result.axle_load) == ("A-17", None)
    assert [(a.girder, a.lever.value, result.load(a).value) for a in result.axles] == [
        (Girder.END, 1.1, 130.0), (Girder.END, 3.0, 190.0), (Girder.ORIGIN, 1.0, 190.0)]
    assert reactions(result) == (126.67, 63.33, 237.67, 82.33)


def test_a_train_on_the_origin_girder_only_by_hand():
    """列車の配置 ② (decision 102): nothing on the end girder; the axle at the joint goes to the origin girder (RB =
    100 × 10 / 10) and the line load stops at the joint (10 × 9 × 4.5 / 10 = 40.5)."""
    p_spans = spans((0.0, 10.0, 0.0), (0.0, 10.0, 0.0))
    result = search_reactions(p_spans.origin, p_spans.end, (train([100.0], [], tail=10.0, tail_gap="1.0"),),
                              loaded=Girder.ORIGIN)
    assert [(a.girder, a.lever.value) for a in result.axles] == [(Girder.ORIGIN, 10.0)]
    assert [(part.girder, part.length.value, part.lever.value) for part in result.tails] == [(Girder.ORIGIN, 9.0, 4.5)]
    assert reactions(result) == (49.5, 140.5, 0.0, 0.0)


def test_a_train_on_the_end_girder_only_by_hand():
    """③: running towards A, the axle at the joint on the end girder and the line load behind it over the rest of
    it: RC = 100 + 10 × 9 × 4.5 / 10."""
    p_spans = spans((0.0, 10.0, 0.0), (0.0, 10.0, 0.0))
    result = search_reactions(p_spans.origin, p_spans.end, (train([100.0], [], tail=10.0, tail_gap="1.0"),),
                              loaded=Girder.END)
    assert [(a.girder, a.lever.value) for a in result.axles] == [(Girder.END, 10.0)]
    assert [(part.girder, part.length.value, part.lever.value) for part in result.tails] == [(Girder.END, 9.0, 4.5)]
    assert reactions(result) == (0.0, 0.0, 140.5, 49.5)
