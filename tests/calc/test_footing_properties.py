"""Properties of the base pressure distribution of 0800 (decision 60) that follow from its equations alone:
equilibrium of the resultant with Vd in every Case, of the moment with Md in Cases 1〜3 and with Mmd in Case 4, and
the continuity of Case 1 and Case 2 at ex = B/6. The inputs are printed values; the tolerances are their rounding."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, strategies as st

from webpier.calc import footing
from webpier.core.printed import Printed

LENGTHS = st.integers(3000, 15000).map(lambda mm: mm / 1000)  # B, L in m, 3 decimals
VD = st.integers(500_000, 5_000_000).map(lambda n: n / 100)  # kN, 2 decimals
ECCENTRICITY = st.floats(0.0, 0.45)  # ex as a fraction of B
QD = st.integers(10_000, 500_000).map(lambda n: n / 100)  # kN/m2, 2 decimals


def printed(value: float, digits: int, unit: str) -> Printed:
    return Printed(round(value, digits), digits, unit)


def make(b: float, l: float, vd: float, fraction: float, qd: float):
    ex = printed(b * fraction, 3, "m")
    md = printed(vd * ex.value, 2, "kN m")
    mmd = printed(b * vd / 2 - vd * vd / (2 * qd * l), 2, "kN m")
    dist = footing.distribution(printed(vd, 2, "kN"), md, ex, printed(b, 3, "m"), printed(l, 3, "m"),
                                printed(qd, 2, "kN/m2"), mmd)
    return dist, md, mmd


def resultant(dist: footing.Distribution, b: float, l: float) -> tuple[float, float]:
    """(force, moment about the footing centre) of the printed profile from the q1 edge."""
    q1, q2, x1, x2 = dist.qd1.value, dist.qd2.value, dist.x1.value, dist.x2.value
    if dist.case == 1:
        return (q1 + q2) / 2 * b * l, (q1 - q2) / 12 * b * b * l
    if dist.case == 2:
        return q1 * x1 / 2 * l, q1 * x1 / 2 * l * (b / 2 - x1 / 3)
    block, triangle = q1 * x1 * l, q1 * x2 / 2 * l
    return block + triangle, block * (b / 2 - x1 / 2) + triangle * (b / 2 - x1 - x2 / 3)


@given(LENGTHS, LENGTHS, VD, ECCENTRICITY, QD)
def test_the_profile_carries_vd_in_every_case(b, l, vd, fraction, qd):
    dist, _, _ = make(b, l, vd, fraction, qd)
    force, _ = resultant(dist, b, l)
    assert abs(force - vd) <= 0.005 * b * l + 0.0005 * l * dist.qd1.value * 2 + 0.01 * vd


@given(LENGTHS, LENGTHS, VD, ECCENTRICITY, QD)
def test_the_profile_balances_md_or_mmd(b, l, vd, fraction, qd):
    dist, md, mmd = make(b, l, vd, fraction, qd)
    _, moment = resultant(dist, b, l)
    target = mmd.value if dist.case == 4 else md.value
    assert abs(moment - target) <= 0.02 * vd * b


@given(st.sampled_from([3.0, 6.0, 9.0, 12.0]), LENGTHS, VD)
def test_case_1_meets_case_2_at_ex_of_b_over_6(b, l, vd):
    # At ex = B/6 the trapezoid's far pressure is 0 and its edge pressure is the triangle's apex over B.
    dist, _, _ = make(b, l, vd, 1 / 6, 100_000.0)  # qd far above the apex, so neither Case 3 nor 4
    assert dist.case == 1
    assert dist.qd2.value == 0.0
    assert abs(dist.qd1.value - dist.apex.value) <= 0.01
    assert dist.x1.value == b


@given(LENGTHS, LENGTHS, VD, ECCENTRICITY, QD)
def test_the_case_follows_the_three_tests_in_order(b, l, vd, fraction, qd):
    dist, md, mmd = make(b, l, vd, fraction, qd)
    ex = Decimal(str(round(b * fraction, 3)))
    expected = (4 if md.value > mmd.value else 3 if dist.apex.value > qd else 2 if ex * 6 > Decimal(str(b)) else 1)
    assert dist.case == expected
    assert dist.x2.value == 0.0 or dist.case == 3
    assert dist.qd2.value == 0.0 or dist.case == 1
