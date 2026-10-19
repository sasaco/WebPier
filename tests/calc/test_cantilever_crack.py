"""The cracking moment of the beam and ε'csd (decision 59; Example2 13-54, 13-55), from the printed parts."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cantilever_support import SAMPLE, D, q, result_of, value
from webpier.calc.cantilever.crack import (AGES, UNCRACKED, Cracking, CrackingMoment, cracking, cracking_moment,
                                           significant)
from webpier.calc.materials import concrete
from webpier.core.printed import MOMENT, Precision

MM = Precision(0, "mm")


@pytest.fixture(scope="module")
def current():
    return result_of()


def test_the_cracking_moment_of_the_beam_section(current):
    _, _, result = current
    found = result.cracking.cracking_moment
    expected = SAMPLE["cracking_13_54"]
    assert (found.width.value, found.depth.value) == (expected["b"], expected["h"])
    assert found.inertia.value == expected["I"]  # 2700⁴/12 = 4.4287e12 → 4.43E+12 (3 significant figures)
    assert (found.neutral_axis.value, found.area.value) == (expected["y"], expected["A"])
    assert (found.strength.value, found.aggregate_max.value) == (expected["fck"], expected["dmax"])
    assert found.tensile_strength.value == expected["ftk"]  # 0.23 × 27^(2/3)
    assert found.fracture_energy.value == expected["GF"]  # 25^(1/3) × 27^(1/3) / 100
    assert found.modulus.value == expected["Ec"]  # 2.65 × 10^7 kN/m² → 26.5 kN/mm²
    assert found.characteristic_length.value == expected["lch"]  # 1000 × 0.0877 × 26.5 / 2.07²
    assert (found.kob.value, found.k1b.value, found.crack_stress.value) == (expected["kob"], expected["k1b"],
                                                                            expected["sigma_crd"])
    assert found.axial.value == expected["Nd"]
    assert found.moment.value == expected["Mcrd"]  # the sample's 7053.1 uses the unrounded I
    # by hand from the printed parts
    assert value(found.tensile_strength) == q(D("0.23") * D(27) ** (Decimal(2) / 3), 2)
    assert value(found.characteristic_length) == q(1000 * D("0.0877") * D("26.5") / D("2.07") ** 2, 0)
    assert value(found.kob) == q(1 + 1 / (D("0.85") + D("4.5") * 2700 / 542), 2)
    assert value(found.crack_stress) == q(D("1.04") * D("1.0") * D("2.07"), 2)
    assert value(found.moment) == q(D("2.15") * D("4.43e12") / 1350 / 10 ** 6, 2)


def test_the_age_at_first_cracking_gives_ecsd(current):
    _, _, result = current
    found = result.cracking
    expected = SAMPLE["cracking_13_54"]
    assert found.self_weight.value == expected["compared"]["self_weight"]
    assert found.permanent == result.selection(1, type(result.selections[0].quantity).BENDING).md
    assert found.permanent_variable == result.selection(5, type(result.selections[0].quantity).BENDING).md
    assert found.permanent.value < found.cracking_moment.moment.value
    assert found.permanent_variable.value < found.cracking_moment.moment.value
    assert (found.ecsd.value, found.ecsd.digits, found.ecsd.unit) == (expected["ecsd"], 0, "×10⁻⁶")
    assert found.age == expected["age"]
    assert dict((age, ecsd) for _, ecsd, age in AGES) == expected["table"] and UNCRACKED == 300


def test_the_table_of_ages():
    moment = CrackingMoment(*(MM(0),) * 2, MM(0), MM(0), MM(0), MM(0), MM(0), MM(0), MM(0), MM(0), MM(0), MM(0),
                            MM(0), MM(0), MM(0), MOMENT(1000))
    weight, permanent, variable = MOMENT(400), MOMENT(1200), MOMENT(1500)

    def found(self_weight, permanent_, variable_) -> Cracking:
        return cracking(moment, self_weight, permanent_, variable_)

    assert (found(MOMENT(1000), permanent, variable).ecsd.value, found(MOMENT(1000), permanent, variable).age) == (450, "30日")
    assert (found(weight, permanent, variable).ecsd.value, found(weight, permanent, variable).age) == (350, "100日")
    assert (found(weight, MOMENT(900), variable).ecsd.value, found(weight, MOMENT(900), variable).age) == (300, "200日以上")
    assert (found(weight, MOMENT(900), MOMENT(900)).ecsd.value, found(weight, MOMENT(900), MOMENT(900)).age) == (300, "200日以上")
    # a hogging moment is compared by its magnitude
    assert found(weight, MOMENT(-1200), variable).ecsd.value == 350


def test_significant_figures():
    assert significant(Decimal("4428675000000"), 3).value == 4.43e12
    assert significant(Decimal("4428675000000"), 3).digits == 0
    assert significant(Decimal("0.012345"), 3).value == 0.0123 and significant(Decimal("0.012345"), 3).digits == 4
    assert significant(Decimal("123.456"), 3).value == 123.0


def test_the_moment_of_another_section():
    found = cracking_moment(MM(1000), MM(2000), concrete(Precision(1, "N/mm2")(30.0), "x"), Precision(1, "mm")(20.0))
    assert found.inertia.value == 6.67e11  # 1000 × 2000³ / 12 = 6.667e11
    assert value(found.tensile_strength) == q(D("0.23") * D(30) ** (Decimal(2) / 3), 2)
    assert found.modulus.value == 28.0 and found.neutral_axis.value == 1000 and found.area.value == 2_000_000
    assert value(found.moment) == q(value(found.crack_stress) * D("6.67e11") / 1000 / 10 ** 6, 2)
