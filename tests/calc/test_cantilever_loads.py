"""The vertical loads of the girders on the cantilever (decision 59; Example2 13-1 .. 13-14): the three loadings, the
train on each bearing, the seismic train and the torques. Expected values are the transcription cantilever.json
(where the sample's inputs are WebPier's) and hand calculations from 0600's values otherwise."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cantilever_support import (KH, ORIGIN_MAX_LEVERS, ORIGIN_MAX_RA, ORIGIN_MAX_RB, SAMPLE, D, origin_max_bearing,
                                pier, q, reaction_of, value)
from webpier.calc.cantilever import calculate_cantilever
from webpier.calc.cantilever.geometry import numbered
from webpier.calc.cantilever.loads import (Loading, Wind, lateral_torques, seismic_girder_torques, seismic_train,
                                           seismic_train_torques, torque, train_loadings, wind_torques)
from webpier.calc.moving_load import Girder, Objective, search_reactions
from webpier.calc.vehicles import vehicle


@pytest.fixture(scope="module")
def current():
    pier_input = pier()
    reaction = reaction_of(pier_input)
    return pier_input, reaction, calculate_cantilever(pier_input, reaction)


def _loading(basis, loading: Loading):
    return next(item for item in basis.loadings if item.loading is loading)


def test_the_three_loadings_maximise_rb_rc_and_their_sum(current):
    pier_input, _, basis = current
    expected = SAMPLE["loadings"]
    assert [item.loading for item in basis.loadings] == [Loading.ORIGIN_MAX, Loading.END_MAX, Loading.BOTH_MAX]
    assert ORIGIN_MAX_RB == Decimal("532.41") and ORIGIN_MAX_RA == Decimal("267.59")
    assert expected["B支点最大"]["rb"] == 517.77  # the sample: the axle at the joint not counted (decision 125)
    for item in basis.loadings:
        values = dict(expected[item.loading.value])
        if item.loading is Loading.ORIGIN_MAX:
            values.update(ra=float(ORIGIN_MAX_RA), rb=float(ORIGIN_MAX_RB), rb_levers=[float(x) for x in ORIGIN_MAX_LEVERS])
        result = item.result
        assert (result.ra.value, result.rb.value, result.rc.value, result.rd.value) == (
            values["ra"], values["rb"], values["rc"], values["rd"])
        levers = [axle.lever.value for axle in result.axles if axle.girder is Girder.ORIGIN]
        assert levers == values["rb_levers"]
        if "rc_levers" in values:
            assert [axle.lever.value for axle in result.axles if axle.girder is Girder.END] == values["rc_levers"]
    # the objective is the moving-load search's: RB alone, RC alone, RB + RC (0600)
    trains = vehicle(pier_input.train).trains
    for loading, objective in ((Loading.ORIGIN_MAX, Objective.ORIGIN), (Loading.END_MAX, Objective.END),
                               (Loading.BOTH_MAX, Objective.PIER)):
        result = search_reactions(pier_input.spans.origin, pier_input.spans.end, trains, objective=objective)
        assert result == _loading(basis, loading).result
    assert Objective.PIER.value == "RB+RC" and Objective.ORIGIN.value == "RB" and Objective.END.value == "RC"


def test_the_default_objective_of_the_search_is_0600s(current):
    pier_input, reaction, basis = current
    assert _loading(basis, Loading.BOTH_MAX).result == reaction.train.loading


def test_the_train_on_each_bearing_by_one_and_both_tracks(current):
    _, reaction, basis = current
    expected = SAMPLE["train_per_bearing"]
    shares = expected["shares"]
    for item in basis.loadings:
        values = dict(expected[item.loading.value])
        if item.loading is Loading.ORIGIN_MAX:  # RB 532.41, not the sample's 517.77 (decision 125)
            values.update(origin_single=[float(origin_max_bearing(x)) for x in ("0.471", "0.373", "0.373", "0.471")],
                          origin_double=[float(origin_max_bearing(x)) for x in ("0.451", "0.549", "0.549", "0.451")])
        origin, end = item.girders[Girder.ORIGIN], item.girders[Girder.END]
        assert origin.reaction == item.result.rb and end.reaction == item.result.rc
        assert [bearing.single.share.value for bearing in origin.bearings] == shares["origin_single"]
        assert [bearing.double.share.value for bearing in origin.bearings] == shares["origin_double"]
        assert [bearing.single.load.value for bearing in origin.bearings] == values["origin_single"]
        assert [bearing.double.load.value for bearing in origin.bearings] == values["origin_double"]
        assert [bearing.single.load.value for bearing in end.bearings] == values["end_single"]
        assert [bearing.double.load.value for bearing in end.bearings] == values["end_double"]
        assert [bearing.single.share.value for bearing in end.bearings] == shares["end_single"]
        # L = R × share by hand, at 2 decimals
        for bearing in (*origin.bearings, *end.bearings):
            girder = origin if bearing in origin.bearings else end
            assert value(bearing.single.load) == q(value(girder.reaction) * value(bearing.single.share), 2)
            assert value(bearing.double.load) == q(value(girder.reaction) * value(bearing.double.share), 2)
        # the girder coefficients are 0600's (decision 26)
        assert origin.impact_ultimate == reaction.train.ultimate.origin_impact
        assert end.impact_service == reaction.train.service.end_impact


def test_the_impact_of_each_track_count_and_group(current):
    _, reaction, basis = current
    expected = SAMPLE["train_per_bearing"]
    coefficients = expected["impact"]
    assert reaction.train.ultimate.origin_impact.single.value == coefficients["origin"]["ultimate_single"]
    assert reaction.train.service.end_impact.double.value == coefficients["end"]["service_double"]
    b = _loading(basis, Loading.ORIGIN_MAX).girders[Girder.ORIGIN].bearing(1)
    # B支点最大 with RB 532.41 (decision 125; the sample's 243.87 × 0.245 = 59.75 etc. come from RB 517.77)
    assert origin_max_bearing("0.471") == Decimal("250.77") and origin_max_bearing("0.451") == Decimal("240.12")
    assert value(b.single.impact_ultimate) == q(Decimal("250.77") * Decimal("0.245"), 2) == Decimal("61.44")
    assert value(b.double.impact_ultimate) == q(Decimal("240.12") * Decimal("0.222"), 2) == Decimal("53.31")
    assert value(b.single.impact_service) == q(Decimal("250.77") * Decimal("0.184"), 2) == Decimal("46.14")
    assert expected["B支点最大"]["origin_g1_impact_ultimate_single"] == 59.75
    c = _loading(basis, Loading.END_MAX)
    assert c.girders[Girder.END].bearing(1).double.impact_ultimate.value == expected["C支点最大"]["end_g1_impact_ultimate_double"]
    assert c.girders[Girder.END].bearing(1).single.impact_ultimate.value == expected["C支点最大"]["end_g1_impact_ultimate_single"]
    assert c.girders[Girder.ORIGIN].bearing(1).single.impact_ultimate.value == expected["C支点最大"]["origin_g1_impact_ultimate_single"]
    bc = _loading(basis, Loading.BOTH_MAX)
    assert bc.girders[Girder.ORIGIN].bearing(1).single.impact_ultimate.value == expected["B+C支点最大"]["origin_g1_impact_ultimate_single"]
    assert bc.girders[Girder.END].bearing(1).double.impact_ultimate.value == expected["B+C支点最大"]["end_g1_impact_ultimate_double"]
    # the 使用性 impact is smaller than the 安全性 one (the sample repeats the 安全性 values: ADR-0001)
    for item in basis.loadings:
        for girder in item.girders.values():
            for bearing in girder.bearings:
                for track in (bearing.single, bearing.double):
                    assert track.impact_service.value <= track.impact_ultimate.value
                    if track.load.value:
                        assert track.impact_service.value < track.impact_ultimate.value


def test_the_cantilever_carries_the_larger_of_one_and_both_tracks(current):
    _, _, basis = current
    b = _loading(basis, Loading.ORIGIN_MAX).girders[Girder.ORIGIN]
    assert not b.bearing(1).adopted_double and b.bearing(1).adopted.load.value == 250.77  # 単線 250.77 > 複線 240.12
    assert b.bearing(2).adopted_double and b.bearing(2).adopted.load.value == 292.29  # 複線 292.29 > 単線 198.59
    c = _loading(basis, Loading.END_MAX).girders[Girder.END]
    assert c.bearing(1).adopted_double and c.bearing(1).adopted.load.value == 416.86  # 複線 416.86 > 単線 357.25
    zero = _loading(basis, Loading.ORIGIN_MAX).girders[Girder.END].bearing(1)
    assert not zero.adopted_double and zero.adopted.load.value == 0.0  # equal loads keep one track


def test_the_seismic_train_loads_each_bearing_by_one_track(current):
    _, reaction, basis = current
    expected = SAMPLE["train_per_bearing"]["seismic"]
    origin, end = basis.seismic_train[Girder.ORIGIN], basis.seismic_train[Girder.END]
    assert [item.load.value for item in origin] == expected["origin"]
    assert [item.load.value for item in end] == expected["end"]
    assert origin[0].reaction.value == expected["reaction_origin"] and end[0].reaction.value == expected["reaction_end"]
    assert origin[0].share.value == 0.471 and origin[3].share.value == 0.471 and end[0].share.value == 0.857
    assert origin[0].reaction == reaction.train.seismic.origin
    assert value(origin[1].load) == q(D(320) * D(0.373), 2)


def test_the_torque_of_a_horizontal_force(current):
    _, reaction, basis = current
    origin = basis.girders[Girder.ORIGIN]
    found = torque(origin, reaction.transverse.lateral_loading.rb, reaction.transverse.origin.rail_height)
    expected = SAMPLE["torques"]["lateral"]["B+C支点最大"]["origin"]
    assert (found.force.value, found.height.value, found.moment.value) == (expected["force"], 3.850, expected["moment"])
    assert [item.force.value for item in found.verticals] == expected["verticals"]
    assert found.sum_squares == origin.sum_squares and found.girder is Girder.ORIGIN
    assert found.vertical(1) == found.verticals[0].force and found.vertical(2).value == 9.12
    # by hand: M = H × y, V = M × |x| / Σx²
    assert value(found.moment) == q(D(52.71) * D(3.85), 2)
    assert value(found.vertical(1)) == q(D(202.93) * D(3.8) / D(33.38), 2)


def test_the_vehicle_lateral_torque_of_each_loading(current):
    _, reaction, basis = current
    expected = SAMPLE["torques"]["lateral"]
    for loading, girders in basis.lateral.items():
        for girder, found in girders.items():
            values = expected[loading.value]["origin" if girder is Girder.ORIGIN else "end"]
            if loading is Loading.ORIGIN_MAX and girder is Girder.ORIGIN:  # 0.2 × 532.41 (decision 125)
                force = q(Decimal("0.2") * ORIGIN_MAX_RB, 2)
                moment = q(force * Decimal("3.85"), 2)
                values = {"force": float(force), "moment": float(moment),
                          "verticals": [float(q(moment * Decimal(x) / Decimal("33.38"), 2)) for x in ("3.8", "1.5", "1.5", "3.8")]}
                assert (force, moment) == (Decimal("106.48"), Decimal("409.95"))
            assert found.force.value == values["force"]
            assert found.height.value == SAMPLE["torques"]["rail_height"]
            if values["force"]:
                assert found.moment.value == values["moment"]
                assert [item.force.value for item in found.verticals] == values["verticals"]
            else:
                assert found.moment.value == 0.0 and {item.force.value for item in found.verticals} == {0.0}
    # 0.2 × R of the maximised girder, 0600's junction loading for B+C支点最大
    assert value(basis.lateral[Loading.ORIGIN_MAX][Girder.ORIGIN].force) == q(D("0.2") * ORIGIN_MAX_RB, 2)
    assert value(basis.lateral[Loading.END_MAX][Girder.END].force) == q(D("0.2") * D(416.86), 2)
    assert basis.lateral[Loading.BOTH_MAX][Girder.ORIGIN].force == reaction.transverse.lateral_loading.rb
    assert basis.lateral[Loading.BOTH_MAX][Girder.END].force == reaction.transverse.lateral_loading.rc
    # the end girder's M × 2.95 / 17.4050 is the sample's M / 5.9000
    assert value(basis.lateral[Loading.END_MAX][Girder.END].vertical(1)) == q(D(320.97) / D("5.9"), 2)


def test_the_wind_torques_are_0600s_forces_heights_and_moments(current):
    _, reaction, basis = current
    for kind, girders in basis.wind.items():
        for girder, found in girders.items():
            side = reaction.transverse.origin if girder is Girder.ORIGIN else reaction.transverse.end
            action = side.wind_with_train if kind is Wind.WITH_TRAIN else side.wind_without_train
            assert (found.force, found.height, found.moment) == (action.force, action.height, action.moment)
            for item in found.verticals:
                assert value(item.force) == q(abs(value(action.moment) * value(item.bearing.position))
                                              / value(found.sum_squares), 2)
    assert set(basis.wind) == {Wind.WITH_TRAIN, Wind.WITHOUT_TRAIN}
    assert basis.wind[Wind.WITHOUT_TRAIN][Girder.ORIGIN].force.value > basis.wind[Wind.WITH_TRAIN][Girder.ORIGIN].force.value


def test_the_seismic_train_torque_is_0600s(current):
    _, reaction, basis = current
    expected = SAMPLE["torques"]["seismic_train"]
    for girder, key in ((Girder.ORIGIN, "origin"), (Girder.END, "end")):
        found = basis.seismic_train_torque[girder]
        side = reaction.transverse.origin if girder is Girder.ORIGIN else reaction.transverse.end
        assert found.force == side.seismic_train.force and found.height == side.seismic_train.height
        assert (found.force.value, found.height.value, found.moment.value) == (
            expected[key]["force"], expected[key]["height"], expected[key]["moment"])
        assert [item.force.value for item in found.verticals] == expected[key]["verticals"]


def test_the_seismic_girder_torque_scales_0600s_force_by_the_kh(current):
    _, reaction, basis = current
    found = seismic_girder_torques(reaction.transverse, KH(0.552), basis.girders)
    for girder in Girder:
        side = reaction.transverse.origin if girder is Girder.ORIGIN else reaction.transverse.end
        assert value(found[girder].force) == q(value(side.seismic_girder.force) * D("0.552"), 2)
        assert found[girder].height == side.seismic_girder.height
    # 0600's girder inertia is (D1 + D2 + S2) × 1.00 at B: 5740 + 520 + 460
    assert reaction.transverse.origin.seismic_girder.force.value == 6720.0
    assert value(found[Girder.ORIGIN].force) == q(D(6720) * D("0.552"), 2)
    assert value(found[Girder.ORIGIN].vertical(1)) == q(value(found[Girder.ORIGIN].moment) * D("3.8") / D("33.38"), 2)


def test_the_builders_match_the_basis(current):
    pier_input, reaction, basis = current
    girders = numbered(reaction.dead)
    assert train_loadings(pier_input, reaction.train, girders) == basis.loadings
    assert seismic_train(reaction.train, girders) == basis.seismic_train
    assert lateral_torques(basis.loadings, reaction.transverse, girders, Decimal("0.2")) == basis.lateral  # P-16
    assert wind_torques(reaction.transverse, girders) == basis.wind
    assert seismic_train_torques(reaction.transverse, girders) == basis.seismic_train_torque
