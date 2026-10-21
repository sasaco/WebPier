"""0900 / 0910 with a load model (decision 70) by hand: the 支承作用 on the cantilevers, the 最大応答震度 term, the rows
of Capacita's force table and the empty row.

current.json: W6/2 = 2.250 (W4 = W5 = 2.250), Y = (H2 + H3)/2 = 1.350, f = 0.325 / 0.675. The left cantilever carries
起点側1 (−3.800: X = 1.550, e = −0.325) and 終点側1 (−2.950: X = 0.700, e = 0.675); Σxi² = 33.3800 (origin girder),
17.4050 (end girder). The test load model loads 起点側1 and 終点側2.
"""

from dataclasses import replace
from decimal import Decimal

from addin_support import chain
from cantilever_support import response
from webpier.calc.cantilever.actions import _dead
from webpier.calc.cantilever.check import calculate_cantilever_section
from webpier.calc.cantilever.combinations import Quantity
from webpier.calc.cantilever.geometry import Side, geometry
from webpier.calc.generic.cantilever import (
    NO_COMBINATION, calculate_generic_cantilever, complete_generic_cantilever,
)
from webpier.loadmodel import CantileverTerm


def completed(transverse=0.552, longitudinal=0.400):
    p, _, reaction, model = chain()
    # the wind on the girders (WG) in the 変動 combination too, for its torque
    model = replace(model, cantilever=tuple(
        replace(c, terms=(*c.terms, CantileverTerm("WG", Decimal("1.0")))) if c.name == "変動" else c
        for c in model.cantilever))
    basis = calculate_generic_cantilever(p, reaction, model)
    return p, complete_generic_cantilever(p, reaction, basis, response(longitudinal), response(transverse))


def action(result, side, case):
    return next(item for item in result.sides[side].actions if item.key.kind == case)


def rows(item):
    return [(row.label, row.sublabel, row.n and row.n.value, row.md.value, row.h and row.h.value, row.mt.value)
            for row in item.rows]


def test_the_application_s_d1_is_that_of_the_train_path():
    p, result = completed()
    left = result.sides[Side.LEFT]
    p_, _, reaction, _ = chain()
    assert action(result, Side.LEFT, "D1") == _dead(geometry(p, reaction.dead, Side.LEFT), snow=False)[0]
    assert left.geometry.torsion_arm.value == 1.35 and [b.x.value for b in left.geometry.bearings] == [1.55, 0.7]


def test_a_vertical_force_on_a_bearing():
    _, result = completed()
    # 300.00 × 1.550 = 465.00, 300.00 × (−0.325) = −97.50; nothing of L on the right side's 終点側1
    item = action(result, Side.LEFT, "L")
    assert rows(item) == [("支承作用", "起点側 Ｇ1桁", 300.0, 465.0, None, -97.5)]
    assert (item.n.value, item.md.value, item.mt.value) == (300.0, 465.0, -97.5)
    right = action(result, Side.RIGHT, "L")  # 250.00 × 0.700 = 175.00, 250.00 × 0.675 = 168.75
    assert (right.n.value, right.md.value, right.mt.value) == (250.0, 175.0, 168.75)


def test_horizontal_forces_along_and_across_the_track():
    _, result = completed()
    # Along: H × Y on the bearing of this cantilever: 20.00 × 1.350 = 27.00
    br = action(result, Side.LEFT, "BR")
    assert (br.n.value, br.md.value, br.mt.value, br.h.value) == (0.0, 0.0, 27.0, 20.0)
    # Across: M of each girder = Σ H × y, on each of its bearings M·|xi|/Σxi²:
    # origin 8.00 × 2.000 = 16.00 → 16.00 × 3.800 / 33.3800 = 1.82; end 6.00 × 2.500 = 15.00 → 15.00 × 2.950 / 17.4050 = 2.54
    wg = action(result, Side.LEFT, "WG")
    assert [(row.n.value, row.md.value, row.mt.value) for row in wg.rows] == [(1.82, 2.82, -0.59), (2.54, 1.78, 1.71)]


def test_the_seismic_inertia_by_hand():
    _, result = completed()
    eq1 = action(result, Side.LEFT, "EQ1")
    # across: origin 400.00 × 1.000 → 400.00 × 3.800 / 33.3800 = 45.54; end 350.00 × 1.200 = 420.00 → × 2.950 / 17.4050
    # = 71.19; along: 400.00 × 1.350 = 540.00
    assert [(row.n and row.n.value, row.md.value, row.mt.value) for row in eq1.rows] == [
        (45.54, 70.59, -14.8), (71.19, 49.83, 48.05), (None, 0.0, 540.0)]
    assert (eq1.n.value, eq1.md.value, eq1.mt.value) == (116.73, 120.42, 573.25)


def test_the_max_response_term():
    _, result = completed(transverse=0.552)
    case = next(c for c in result.sides[Side.LEFT].cases if c.name == "地震時")
    eq = next(part for part in case.contributions if part.column == "EQ1")
    # 116.73 × 0.552 = 64.43, 120.42 × 0.552 = 66.47, 573.25 × 0.552 = 316.43
    assert (eq.factor, eq.n.value, eq.md.value, eq.mt.value) == ("0.552", 64.43, 66.47, 316.43)
    assert [part.column for part in case.contributions] == ["D1", "D2", "LE", "EQ1"]
    assert case.n.value == round(sum(part.n.value for part in case.contributions), 2)


def test_the_rows_of_the_force_table():
    _, result = completed()
    by_row = {(s.row, s.quantity): s for s in result.selections}
    assert sorted({row for row, _ in by_row}) == list(range(9))
    # 最小鉄筋量 takes the combinations of 耐久性（永久荷重） (decision 73)
    assert by_row[(8, Quantity.BENDING)].case == by_row[(1, Quantity.BENDING)].case
    failure = by_row[(5, Quantity.BENDING)]
    assert failure.case.name == "破壊 車最大"
    # the larger |Md| of the two sides
    left, right = (next(c for c in result.sides[side].cases if c.name == "破壊 車最大") for side in Side)
    assert failure.md == max(left.md, right.md, key=lambda m: abs(m.value))
    durability = by_row[(0, Quantity.BENDING)]
    assert durability.case.name in ("永久", "永久＋変動")


def test_a_row_without_a_combination_is_zero():
    _, result = completed()
    for quantity in (Quantity.BENDING, Quantity.SHEAR, Quantity.TORSION):
        selection = result.selection(6, quantity)
        assert selection.case.name == NO_COMBINATION
        assert (selection.md.value, selection.vd.value, selection.mt.value) == (0.0, 0.0, 0.0)


def test_capacita_is_given_the_generic_result():
    p, result = completed()
    section = calculate_cantilever_section(p, result)
    assert section.shear_span.value == 1.55 and section.selections == result.selections
    assert section.ecsd == result.cracking.ecsd
