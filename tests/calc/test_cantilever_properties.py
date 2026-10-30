"""Identities of the cantilever calculation that follow from its equations (decision 15, ADR-0003): a row's
moments are its printed N times its printed arms, a table's totals are the sums of its printed rows, a case sums the
printed products of its factors, a bearing's share times the girder's bearings returns the girder's force within
the rounding and its force is the smaller of the share and its cap (decision 125), and the governing case has the
maximal measure of its pool."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings, strategies as st

from cantilever_support import KH, D, pier, q, result_of, value
from webpier.calc.cantilever import Quantity, Side, calculate_cantilever, complete_cantilever
from webpier.calc.reaction.longitudinal import BearingType
from webpier.calc.cantilever.combinations import FORCE_ROWS
from webpier.calc.cantilever.loads import torque
from webpier.calc.cantilever.response import MaxResponse, ResponseValue
from webpier.calc.moving_load import Girder
from webpier.core.printed import FORCE, LENGTH

_, REACTION, RESULT = result_of()
BASIS = RESULT.basis


def _response(kh: float) -> MaxResponse:
    value_ = ResponseValue(1, "Case1", "安全性", KH(kh))
    return MaxResponse("x.xlsx", (value_,), value_)


def test_every_vertical_row_is_n_times_its_arms_and_every_total_the_sum_of_its_rows():
    for side in RESULT.sides.values():
        for action in side.actions:
            for row in action.rows:
                if row.n is not None and row.x is not None:
                    assert value(row.md) == q(value(row.n) * value(row.x), 2)
                    assert value(row.mt) == q(value(row.n) * value(row.arm), 2)
                if row.h is not None:
                    assert value(row.mt) == q(value(row.h) * value(row.arm), 2)
            assert value(action.n) == sum((value(row.n) for row in action.rows if row.n is not None), Decimal(0))
            assert value(action.md) == sum(value(row.md) for row in action.rows)
            assert value(action.mt) == sum(value(row.mt) for row in action.rows)
            assert value(action.h) == sum((value(row.h) for row in action.rows if row.h is not None), Decimal(0))


def test_every_case_sums_the_printed_products_and_the_governing_case_is_maximal():
    for side in RESULT.sides.values():
        for case in side.cases:
            assert value(case.n) == sum(value(part.n) for part in case.contributions)
            assert value(case.md) == sum(value(part.md) for part in case.contributions)
            assert value(case.mt) == sum(value(part.mt) for part in case.contributions)
    for selection in RESULT.selections:
        row = next(row for row in FORCE_ROWS if row.id == selection.row)
        pool = [case for side in RESULT.sides.values() for case in side.cases if row.pool(case.definition)]
        measure = {Quantity.BENDING: lambda c: abs(c.md.value), Quantity.SHEAR: lambda c: c.n.value,
                   Quantity.TORSION: lambda c: c.mt.value}[selection.quantity]
        assert measure(selection.case) == max(measure(case) for case in pool)


@given(st.integers(min_value=1, max_value=30), st.integers(min_value=1, max_value=30),
       st.integers(min_value=200, max_value=800))
@settings(max_examples=25, deadline=None)
def test_a_bearings_share_times_n_returns_the_force_and_its_force_is_the_share_or_its_cap(origin_mu, end_mu,
                                                                                         kh_thousandths):
    changes = {"上部構造/支承データ/起点側/摩擦係数_μ": origin_mu / 100, "上部構造/支承データ/終点側/摩擦係数_μ": end_mu / 100}
    _, _, result = result_of(longitudinal=kh_thousandths / 1000, **changes)
    for side in result.sides.values():
        for case in side.bearings:
            for girder in (case.origin, case.end):
                assert abs(value(girder.share) * girder.count - value(girder.applied)) <= Decimal(girder.count) / 200
            for item in case.bearings:
                force = case.origin if item.bearing.girder is Girder.ORIGIN else case.end
                assert item.share == force.share
                if force.bearing is BearingType.MOVABLE:
                    mu = D(changes["上部構造/支承データ/起点側/摩擦係数_μ" if item.bearing.girder is Girder.ORIGIN
                                   else "上部構造/支承データ/終点側/摩擦係数_μ"])
                    assert value(item.cap) == q(mu * value(item.vertical), 2)
                    assert item.force.value == min(item.share.value, item.cap.value)
                else:
                    assert item.cap is None and item.force == item.share
                assert value(item.moment) == q(value(item.force) * value(item.arm), 2)
            assert value(case.force) == sum(value(item.force) for item in case.bearings)
            assert value(case.moment) == sum(value(item.moment) for item in case.bearings)


@given(st.integers(min_value=0, max_value=500000), st.integers(min_value=1, max_value=12000))
@settings(max_examples=40, deadline=None)
def test_a_torque_loads_each_bearing_with_m_times_its_lever_over_the_sum_of_squares(force_hundredths, height_mm):
    girder = BASIS.girders[Girder.ORIGIN]
    found = torque(girder, FORCE(force_hundredths / 100), LENGTH(height_mm / 1000))
    assert value(found.moment) == q(value(found.force) * value(found.height), 2)
    for item in found.verticals:
        assert value(item.force) == q(abs(value(found.moment) * value(item.bearing.position)) / value(found.sum_squares), 2)
        assert item.force.value >= 0
    # the verticals balance the torque: Σ V_i |x_i| = M (within the rounding of each vertical)
    assert abs(sum(value(item.force) * abs(value(item.bearing.position)) for item in found.verticals)
               - value(found.moment)) <= Decimal(len(found.verticals)) * Decimal("0.005") * Decimal(4)


@given(st.integers(min_value=100, max_value=900), st.integers(min_value=100, max_value=900))
@settings(max_examples=15, deadline=None)
def test_only_the_seismic_terms_depend_on_the_kh(longitudinal, transverse):
    completed = complete_cantilever(RESULT.basis.__class__ and _pier(), REACTION, BASIS, _response(longitudinal / 1000),
                                    _response(transverse / 1000))
    for side in Side:
        for mine, theirs in zip(completed.sides[side].cases, RESULT.sides[side].cases):
            same = mine.definition.eq is None
            if same:
                assert (mine.n, mine.md, mine.mt) == (theirs.n, theirs.md, theirs.mt)
    for girder in Girder:
        base = REACTION.transverse.origin if girder is Girder.ORIGIN else REACTION.transverse.end
        assert value(completed.seismic_girder[girder].force) == q(value(base.seismic_girder.force) * D(transverse / 1000), 2)
    for side in Side:
        assert completed.sides[side].bearings[:-1] == RESULT.sides[side].bearings[:-1]  # all but the seismic case


def _pier():
    return pier()
