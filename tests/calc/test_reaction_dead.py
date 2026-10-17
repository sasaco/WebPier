"""0600 dead and snow loads per support: Example2 05/07 7-1, 7-3 and 08 8-3/8-4, and hand sums."""

from reaction_support import END_SLOTS, ORIGIN_SLOTS, SELF_WEIGHT_08, example2, pier
from webpier.calc.reaction.dead import calculate_dead

TABLE = example2("07_7-1_support_reactions_and_service_train")
GIRDERS = example2("07_7-3_main_girder_reactions")


def loads(support):
    return (support.d1.value, support.d2.value, support.snow2.value, support.snow10.value, support.snow30.value)


def test_example2_support_reactions_7_1():
    dead = calculate_dead(pier())
    for name, support in (("RA", dead.origin.far), ("RB", dead.origin.pier),
                          ("RC", dead.end.pier), ("RD", dead.end.far)):
        expected = tuple(TABLE[f"support_reaction.{key}.{name}"] for key in ("D1", "D2", "snow_S2", "snow_S10", "snow_S30"))
        assert loads(support) == expected, name


def test_example2_double_track_shares_and_totals_7_3():
    dead = calculate_dead(pier())
    origin = [bearing.double.value for bearing in dead.origin.bearings]
    end = [bearing.double.value for bearing in dead.end.bearings]
    assert origin == [GIRDERS[f"start_girder.train_share.double.B.G{index}"] for index in range(1, 5)]
    assert end == [GIRDERS[f"end_girder.train_share.double.C.G{index}"] for index in range(1, 3)]
    assert dead.origin.track_total.value == GIRDERS["start_girder.train_share.double.B.total"] == 2.0
    assert dead.end.track_total.value == GIRDERS["end_girder.train_share.double.C.total"] == 2.0
    assert dead.origin.track_total.digits == 3


def test_example2_08_snow_and_dead_on_the_pier():
    dead = calculate_dead(pier())
    snow = SELF_WEIGHT_08["8-4"]["snow"]
    for key, field in (("S2", "snow2"), ("S10", "snow10"), ("S30", "snow30")):
        assert getattr(dead.origin.pier, field).value == snow[key]["RB"]
        assert getattr(dead.end.pier, field).value == snow[key]["RC"]
    top = SELF_WEIGHT_08["8-3"]
    assert dead.origin.pier.d1.value == top["fixed_dead_top"]["RB"]["N"]
    assert dead.end.pier.d2.value == top["additional_dead_top"]["RC"]["N"]


def test_no_superstructure_dead_for_a_pier_impact():
    # Decision 27: DU served only the pier impact reduction, which is removed.
    assert not hasattr(calculate_dead(pier()), "superstructure")


def test_printed_digits_and_units():
    dead = calculate_dead(pier())
    assert (dead.origin.pier.d1.digits, dead.origin.pier.d1.unit) == (2, "kN")
    assert (dead.origin.bearings[0].double.digits, dead.origin.bearings[0].double.unit) == (3, "")


def test_sums_are_of_the_printed_bearing_values_by_hand():
    slot = f"{ORIGIN_SLOTS}/0"
    dead = calculate_dead(pier(**{
        f"{slot}/固定死荷重_D1": 0.01, f"{slot}/付加死荷重_D2": -12.34, f"{slot}/雪荷重_10年確率": 0.05,
        f"{slot}/列車分担/L1": 0.125, f"{slot}/列車分担/L2": -0.333}))
    assert dead.origin.pier.d1.value == 4210.01  # 0.01 + 1340 + 1340 + 1530
    assert dead.origin.pier.d2.value == 347.66  # -12.34 + 100 + 100 + 160
    assert dead.origin.pier.snow10.value == 420.05
    assert dead.origin.bearings[0].double.value == -0.208
    assert dead.origin.track_total.value == 1.341  # -0.208 + 0.549 + 0.549 + 0.451


def test_empty_slots_are_absent_bearings_and_keep_their_slot_numbers():
    moved = pier(**{f"{ORIGIN_SLOTS}/1": None, f"{ORIGIN_SLOTS}/7": {
        "支承位置": 4.5, "固定死荷重_D1": 10.0, "付加死荷重_D2": 1.0, "雪荷重_2年確率": 2.0,
        "雪荷重_10年確率": 3.0, "雪荷重_30年確率": 4.0,
        "列車分担": {"L1": 0.1, "L2": 0.2, "L3": None, "L4": None}}})
    dead = calculate_dead(moved)
    assert [bearing.slot for bearing in dead.origin.bearings] == [0, 2, 3, 7]
    assert dead.origin.pier.d1.value == 1530 + 1340 + 1530 + 10
    assert dead.origin.track_total.value == 1.751  # 0.451 + 0.549 + 0.451 + 0.3


def test_a_side_without_bearings_carries_nothing():
    dead = calculate_dead(pier(**{f"{END_SLOTS}/0": None, f"{END_SLOTS}/1": None}))
    assert dead.end.bearings == ()
    assert loads(dead.end.pier) == (0.0,) * 5
    assert dead.end.track_total.value == 0.0


def test_the_double_share_is_l1_plus_l2_and_no_third_track_is_carried():
    # Decision 23: L3/L4 must be blank (parse rejects a value), so the result carries only L1 and L2.
    bearing = calculate_dead(pier()).origin.bearings[0]
    shares = bearing.bearing.shares
    assert (shares.l1.value, shares.l2.value, bearing.double.value) == (0.471, -0.02, 0.451)
    assert not hasattr(shares, "l3") and not hasattr(shares, "l4")


def test_far_supports_are_the_entered_totals():
    dead = calculate_dead(pier(**{"上部工反力/起点側/A支点/固定死荷重_D1": -5.0,
                                  "上部工反力/終点側/D支点/雪荷重_30年確率": 0.0}))
    assert dead.origin.far.d1.value == -5.0
    assert dead.end.far.snow30.value == 0.0
