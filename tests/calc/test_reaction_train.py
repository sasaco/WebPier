"""0600 train loads, impact tables, pier impact reduction and seismic train: Example2 07 7-1/7-2, 08 8-4, by hand."""

from decimal import Decimal

import pytest

from reaction_support import D, SELF_WEIGHT_08, example2, pier, q, value
from webpier.calc.reaction.dead import calculate_dead
from webpier.calc.reaction.self_weight import calculate_self_weight
from webpier.calc.reaction.train import calculate_train
from webpier.core.errors import InputError

TABLE = example2("07_7-1_support_reactions_and_service_train")
FACTORS = example2("07_7-2_load_factors_seismic_train_impact")


def train(p=None):
    p = p or pier()
    return calculate_train(p, calculate_dead(p), calculate_self_weight(p))


def supports(track):
    return tuple(getattr(track, s) for s in ("a", "b", "c", "d"))


def test_example2_reactions_and_load_factors_7_1_7_2():
    result = train()
    loading = result.loading
    assert tuple(r.value for r in (loading.ra, loading.rb, loading.rc, loading.rd)) == tuple(
        TABLE[f"serviceability_train.{s}"] for s in ("RA", "RB", "RC", "RD"))
    assert result.ultimate.load_factor.value == FACTORS["load_factor_rho_f.safety_restorability"]
    assert result.fatigue.load_factor.value == FACTORS["load_factor_rho_f.fatigue"]
    # Service ρf = 1.000: the service train loads are the 7-1 reactions.
    assert [s.load.value for s in supports(result.service.single)] == [367.53, 272.47, 294.92, 25.08]


@pytest.mark.parametrize("group,usage", [("ultimate", "safety_restorability"), ("service", "serviceability_fatigue"),
                                         ("fatigue", "serviceability_fatigue")])
def test_example2_impact_coefficients_7_2(group, usage):
    result = getattr(train(), group)
    for girder, impact in (("start_girder", result.origin_impact), ("end_girder", result.end_impact)):
        assert impact.single.value == FACTORS[f"impact.{usage}.single.{girder}"]
        assert impact.double.value == FACTORS[f"impact.{usage}.double.{girder}"]


def test_double_track_impact_is_one_expression_rounded_once():
    # Decision 23: i = i_single × (1 − L/200), only the result rounded. With i 0.500 and L 1.100:
    # 0.5 × 0.9945 = 0.49725 -> 0.497 (rounding the factor first, 0.995, would give 0.498).
    result = train(pier(**{"上部構造/起点側/衝撃係数_単線終局": 0.5, "上部構造/起点側/桁長/スパン長": 1.1}))
    assert result.ultimate.origin_impact.double.value == 0.497
    assert not hasattr(result, "origin_reduction")


def test_example2_seismic_train_7_2():
    seismic = train().seismic
    assert seismic.origin.value == FACTORS["seismic_train.start_girder_RA_RB"]
    assert seismic.end.value == FACTORS["seismic_train.end_girder_RC_RD"]
    assert (seismic.origin_length.value, seismic.end_length.value) == (20.0, 10.0)


def test_example2_08_double_track_train_loads():
    service = train().service.double
    expected = SELF_WEIGHT_08["8-4"]["train_double"]
    assert service.c.load.value == expected["RC"]
    # 08 p.8-4 prints 544.93 = 2 × 272.4668 (unrounded RB); from the printed 272.47, 272.47 × 2.000 = 544.94.
    assert service.b.load.value == 544.94 != expected["RB"]


def test_group_tables_by_hand():
    result = train()
    shares = {"a": D(2), "b": D(2), "c": D(2), "d": D(2)}
    reactions = {"a": D(367.53), "b": D(272.47), "c": D(294.92), "d": D(25.08)}
    i_single = {"a": D(0.245), "b": D(0.245), "c": D(0.546), "d": D(0.546)}
    i_double = {"a": D(0.222), "b": D(0.222), "c": D(0.521), "d": D(0.521)}
    for group, rho, scale in (("ultimate", D(1.231), None), ("service", D(1.0), D(0.75)), ("fatigue", D(1.0), D(0.75))):
        tables = getattr(result, group)
        for s in "abcd":
            single = q(reactions[s] * rho, 2)
            double = q(single * shares[s], 2)
            coefficient = i_single[s] if scale is None else q(i_single[s] * scale, 3)
            coefficient_d = i_double[s] if scale is None else q(i_double[s] * scale, 3)
            row = getattr(tables.single, s)
            assert (value(row.load), value(row.coefficient), value(row.impact)) == (
                single, coefficient, q(single * coefficient, 2)), (group, s)
            row = getattr(tables.double, s)
            assert (value(row.load), value(row.coefficient), value(row.impact)) == (
                double, coefficient_d, q(double * coefficient_d, 2)), (group, s)


def test_pier_impact_reduction_by_hand():
    # RC標準 解4.4.4: i = i0 (1 − Ds / (L + DU + Ds)), Ds = pier-bottom weight, DU = D1 + D2 on the pier.
    result = train()
    ds, du = D(2961.88), D(8380.0)
    assert (value(result.pier_weight), value(result.superstructure_dead)) == (ds, du)
    for group, rho, track, i_b, i_c in (
            ("ultimate", D(1.231), "single", D(0.245), D(0.546)), ("ultimate", D(1.231), "double", D(0.222), D(0.521)),
            ("service", D(1.0), "single", D(0.184), D(0.41)), ("service", D(1.0), "double", D(0.167), D(0.391))):
        tracks = D(1) if track == "single" else D(2)
        l_b, l_c = q(q(D(272.47) * rho, 2) * tracks, 2), q(q(D(294.92) * rho, 2) * tracks, 2)
        pier_impact = getattr(getattr(result, "pier_" + group), track)
        total = l_b + l_c
        factor = 1 - ds / (total + du + ds)
        assert value(pier_impact.train_total) == total
        for support, load, i0 in (("b", l_b, i_b), ("c", l_c, i_c)):
            row = getattr(pier_impact, support)
            coefficient = q(i0 * factor, 3)
            assert (value(row.load), value(row.coefficient), value(row.impact)) == (
                load, coefficient, q(load * coefficient, 2)), (group, track, support)
        assert value(pier_impact.impact_total) == value(pier_impact.b.impact) + value(pier_impact.c.impact)


def test_example2_pier_impact_numbers():
    ultimate = train().pier_ultimate.single
    # L = 335.41 + 363.05 = 698.46; 1 − 2961.88/12040.34 = 0.754004; 0.245 × 0.754004 = 0.18473 -> 0.185.
    assert (ultimate.b.coefficient.value, ultimate.c.coefficient.value) == (0.185, 0.412)


@pytest.mark.parametrize("side", ["起点側", "終点側"])
def test_double_track_reduction_outside_its_range_is_an_input_error(side):
    with pytest.raises(InputError, match="200"):
        train(pier(**{f"上部構造/{side}/桁長/スパン長": 200.0}))


def test_span_just_below_200_m_gives_almost_no_impact():
    result = train(pier(**{"上部構造/起点側/桁長/スパン長": 199.9}))
    assert result.ultimate.origin_impact.double.value == 0.0  # 0.245 × 0.0005 = 0.0001225


def test_pier_impact_with_a_zero_denominator_is_an_input_error():
    # Negative dead loads cancelling the pier weight and train make L + DU + Ds = 0.
    result = train()
    l_total = Decimal(repr(result.pier_service.single.train_total.value))
    ds = Decimal(repr(result.pier_weight.value))
    target = -(l_total + ds)  # DU needed; 5740 + 520 + 1860 + 260 on the pier now
    change = target - Decimal(8380)
    with pytest.raises(InputError, match="衝撃"):
        train(pier(**{"上部工反力/起点側/B支点/0/固定死荷重_D1": float(Decimal(1530) + change)}))


def test_seismic_train_by_hand():
    result = train(pier(**{"上部構造/列車/軸重/地震": 30.15, "上部構造/起点側/桁長/L1": 0.333}))
    # 30.15 × (0.333 + 18.850 + 0.575) / 2 = 30.15 × 19.758 / 2 = 297.85185 -> 297.85
    assert result.seismic.origin_length.value == 19.758
    assert result.seismic.origin.value == 297.85
