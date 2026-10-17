"""Moving point loads on the two girders: Example2 07 7-1/7-14 and hand cases for the search rules."""

import pytest

from reaction_support import example2, pier
from webpier.calc.moving_load import Girder, search_reactions
from webpier.core.errors import InputError
from webpier.core.printed import FORCE, LENGTH

TRAIN = example2("07_7-1_support_reactions_and_service_train")
LATERAL = example2("07_7-14_vehicle_lateral")


def spans(origin, end):
    o, e = origin, end
    return pier(**{"上部構造/起点側/桁長": {"L1": o[0], "スパン長": o[1], "L2": o[2]},
                   "上部構造/終点側/桁長": {"L1": e[0], "スパン長": e[1], "L2": e[2]}}).spans


def run(p_spans, load, cars, car_length, a1, a2):
    return search_reactions(p_spans.origin, p_spans.end, axle_load=FORCE(load), cars=cars,
                            car_length=LENGTH(car_length), a1=LENGTH(a1), a2=LENGTH(a2))


def levers(result, girder):
    return sorted(axle.lever.value for axle in result.axles if axle.girder is girder)


def reactions(result):
    return tuple(r.value for r in (result.ra, result.rb, result.rc, result.rd))


def test_example2_train_7_1():
    p = pier()
    t = p.train
    result = search_reactions(p.spans.origin, p.spans.end, axle_load=t.axle_load, cars=t.cars,
                              car_length=t.car_length, a1=t.a1, a2=t.a2)
    # RB = 160.00×(16.625＋14.425＋1.625＋-0.575)/18.850, RC = 160.00×(7.425＋9.625)/9.250
    assert levers(result, Girder.ORIGIN) == [-0.575, 1.625, 14.425, 16.625]
    assert levers(result, Girder.END) == [7.425, 9.625]
    assert reactions(result) == tuple(TRAIN[f"serviceability_train.{s}"] for s in ("RA", "RB", "RC", "RD"))
    assert [axle.position.value for axle in result.axles] == [22.2, 20.0, 17.2, 15.0, 2.2, 0.0]


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
    assert [(a.position.value, a.girder, a.lever.value) for a in result.axles] == [(11.0, Girder.END, 5.3)]
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
    result = run(spans((0.0, 10.0, 0.0), (0.0, 10.0, 0.0)), 100.0, 2, 4.0, 1.0, 0.0)
    positions = sorted(axle.position.value for axle in result.axles)
    gaps = {round(b - a, 3) for a, b in zip(positions, positions[1:])}
    assert gaps <= {1.0, 3.0}


def test_axles_beyond_the_bridge_are_not_loaded():
    result = run(pier().spans, 160.0, 10, 20.0, 2.8, 2.2)
    assert all(0 <= axle.position.value <= 30.0 for axle in result.axles)


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
