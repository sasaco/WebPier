"""0710 / 0720 with a load model (decision 70): the cases fixed, incremental and limited incremental, their directions,
the application's D1, D2, buoyancy and EQ2, and the control node weighted by the incremental cases across the track.
"""

from addin_support import CURRENT, chain
from webpier.calc.foundation import calculate_foundation
from webpier.calc.frame import Direction, NodeRole
from webpier.calc.generic.frame import calculate_generic_frame
from webpier.calc.generic.seismic import calculate_generic_seismic, girder_weights
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.seismic_longitudinal import (
    ActionDirection as A, Increment as I, SeismicCase, calculate_seismic_longitudinal,
)
from webpier.calc.seismic_transverse import SeismicCase as TransverseCase, calculate_seismic_transverse
from webpier.calc.transverse import calculate_transverse
from webpier.core.printed import FORCE
from webpier.inputs import parse_input

ORDER = ["D1", "D2", "WP_NORMAL", "LE", "EQ1", "EQL", "EQ2"]


def generic(direction: Direction):
    p, foundation, reaction, model = chain()
    stage = "0710" if direction is Direction.LONGITUDINAL else "0720"
    return model, calculate_generic_seismic(p, foundation, reaction, model, direction, stage)


def train(direction: Direction):
    p = parse_input(CURRENT)
    foundation, reaction = calculate_foundation(p), calculate_reaction(p)
    if direction is Direction.LONGITUDINAL:
        return calculate_seismic_longitudinal(p, foundation, reaction)
    return calculate_seismic_transverse(p, foundation, reaction)


def test_the_longitudinal_cases_and_their_kinds():
    _, result = generic(Direction.LONGITUDINAL)
    assert [(c.number, c.id, c.direction, c.increment) for c in result.basic_cases] == [
        (1, "D1", A.DOWNWARD, I.FIXED), (2, "D2", A.DOWNWARD, I.FIXED), (3, "WP_NORMAL", A.UPWARD, I.FIXED),
        (4, "LE", A.DOWNWARD, I.FIXED), (5, "EQ1", A.TOWARD_ORIGIN, I.INCREMENTAL),
        (6, "EQL", A.TOWARD_ORIGIN, I.LIMITED), (7, "EQ2", A.TOWARD_ORIGIN, I.INCREMENTAL)]
    assert result.girder_weights is None and result.earthquake == -1
    assert [c.case for c in result.basic_cases] == [c.id for c in result.basic_cases]  # the NDU names them by id
    # The application's cases are those of the train path on the same frame.
    old = train(Direction.LONGITUDINAL)
    for case, kind in (("D1", SeismicCase.D1), ("D2", SeismicCase.D2), ("WP_NORMAL", SeismicCase.BUOYANCY),
                       ("EQ2", SeismicCase.SELF_INERTIA)):
        mine, theirs = result.basic(case), old.basic(kind)
        assert (mine.points, mine.line_loads, mine.member_loads) == (theirs.points, theirs.line_loads,
                                                                   theirs.member_loads)
    assert result.frame == old.frame


def test_the_longitudinal_bearing_actions_by_hand():
    _, result = generic(Direction.LONGITUDINAL)
    le = result.basic("LE").points[0]
    # 90.00 × (−0.325) + 80.00 × 0.675 = −29.25 + 54.00
    assert (le.n.value, le.h.value, le.m.value) == (170.0, 0.0, 24.75)
    eq1 = result.basic("EQ1").points[0]
    assert (eq1.n.value, eq1.h.value, eq1.m.value) == (0.0, -750.0, 0.0)  # toward the origin side, −x
    eql = result.basic("EQL").bearings
    assert (eql.h.value, eql.m.value) == (-110.0, 0.0)
    assert eq1.node == result.frame.node(NodeRole.CAP_TOP).number


def test_one_combination_with_every_case_in_order_by_pattern():
    _, result = generic(Direction.LONGITUDINAL)
    # Decision 76: the one combination of the load model for each 照査パターン (ρm, αf), toward the earthquake.
    assert [(c.number, c.name, c.cases, c.rho_m.value, c.alpha_f.value, c.direction, c.reverse)
            for c in result.combinations] == [
        (number, "地震時", tuple(ORDER), rho_m, alpha_f, A.TOWARD_ORIGIN, False)
        for number, (rho_m, alpha_f) in enumerate(((1.0, 1.0), (1.2, 1.0), (1.0, 2.0), (1.2, 2.0)), 1)]
    assert [section.title for section in result.sections] == ["地震時の作用の根拠"]


def test_the_transverse_cases_toward_w9():
    model, result = generic(Direction.TRANSVERSE)
    assert [c.id for c in result.basic_cases] == ORDER
    assert result.basic("EQ1").direction is A.TOWARD_W9 and result.earthquake == 1
    eq1 = result.basic("EQ1").bearings
    # 400.00 × 1.000 + 350.00 × 1.200 at the seat, toward W9
    assert (eq1.h.value, eq1.m.value) == (750.0, 820.0)
    old = train(Direction.TRANSVERSE)
    assert result.basic("EQ2").member_loads == old.basic(TransverseCase.SELF_INERTIA).member_loads
    assert result.sections == ()


def test_the_control_node_is_weighted_by_the_incremental_cases_across_the_track():
    model, result = generic(Direction.TRANSVERSE)
    # EQ1 (incremental) only: 400.00 at 起点側1, 350.00 at 終点側2; EQL is limited incremental.
    assert [w.value for w in result.girder_weights] == [400.0, 350.0]
    assert girder_weights(model, {"EQL", "LE"}) == (FORCE(0), FORCE(0))
    assert any(NodeRole.CONTROL in node.roles for node in result.frame.nodes)


def test_only_the_cases_the_combinations_use():
    from dataclasses import replace

    from webpier.loadmodel import SeismicCombination
    p, foundation, reaction, model = chain()
    model = replace(model, seismic_longitudinal=(SeismicCombination("車なし", ("D1", "D2", "EQ1")),
                                                 SeismicCombination("車あり", ("D1", "D2", "LE", "EQ1"), reverse=True)))
    result = calculate_generic_seismic(p, foundation, reaction, model, Direction.LONGITUDINAL, "0710")
    assert [c.id for c in result.basic_cases] == ["D1", "D2", "LE", "EQ1"]  # no buoyancy, no EQ2
    assert [c.cases for c in result.combinations] == [*[("D1", "D2", "EQ1")] * 4, *[("D1", "D2", "LE", "EQ1")] * 4]
    # A reversed (逆向) combination pushes away from the earthquake: → along the track (decision 76).
    assert [(c.name, c.reverse, c.direction) for c in result.combinations[3:5]] == [
        ("車なし", False, A.TOWARD_ORIGIN), ("車あり", True, A.TOWARD_END)]
