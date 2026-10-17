"""Joint-grid regressions with expectations from independent statics."""

from dataclasses import replace
from fractions import Fraction
from itertools import accumulate
import json
from pathlib import Path
import struct

import pytest

from src import calculate as calculate_foundation, parse_input
from src.longitudinal_calculator import calculate_longitudinal
from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
from src.moving_load import _reactions, search_reactions
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import EndReaction, ReactionInput, SnowReactions, parse_reaction_input
from src.transverse_calculator import calculate_transverse


CASES = json.loads((Path(__file__).parent / "fixtures/moving_load_boundary_cases.json").read_text(encoding="utf-8-sig"))
EXAMPLE = CASES["example2"]


def moment_reactions(lengths: list[float], positions: list[float], sides: list[str], load: float) -> tuple[float, ...]:
    """Exact decimal dimensions; RB/RC come from moments, RA/RD from force sums."""
    a, span_b, end_b, start_c, span_c, end_c = map(lambda x: Fraction(str(x)), lengths)
    total = a + span_b + end_b + start_c + span_c + end_c
    force = Fraction(str(load))
    rb = sum(force * (Fraction(str(p)) - a) / span_b for p, side in zip(positions, sides) if side == "B")
    rc = sum(force * (total - Fraction(str(p)) - end_c) / span_c for p, side in zip(positions, sides) if side == "C")
    return tuple(map(float, (sides.count("B") * force - rb, rb, rc, sides.count("C") * force - rc)))


def test_example2_reactions_and_assignment_follow_support_moments() -> None:
    case = EXAMPLE
    expected = moment_reactions(case["search"]["lengths"], case["positions"], case["sides"], 160)
    assert [round(value, 2) for value in expected] == case["display_reactions"]
    result = search_reactions(**case["search"])
    assert result.reactions == pytest.approx(expected, rel=0, abs=0.0001)
    assert result.positions == pytest.approx(case["positions"], rel=0, abs=0.00001)
    assert [term.side for term in result.contributions] == case["sides"]
    assert result.candidate_count == case["candidate_count"]
    assert result.reactions[0] + result.reactions[1] == pytest.approx(4 * 160, rel=0, abs=0.0001)
    assert result.reactions[2] + result.reactions[3] == pytest.approx(2 * 160, rel=0, abs=0.0001)
    assert result.contributions[-1].reaction < 0  # left overhang is not clipped


def test_example2_reactions_match_source_workbook_single_values() -> None:
    # Example 2 workbook 反力!AC50:AC56, read from its unchanged ZIP XML.
    assert search_reactions(**EXAMPLE["search"]).reactions == (
        367.533172607421875, 272.466827392578125,
        294.91888427734375, 25.08111572265625,
    )


def single(value: float) -> float:
    return struct.unpack("f", struct.pack("f", value))[0]


@pytest.mark.parametrize("noise", [-2**-19, 0, 2**-19])
@pytest.mark.parametrize(("lengths", "joint", "joint_side"), [
    ((0, 10, 1, 0, 20, 0), 11, "B"),
    ((0, 10, 0, 1, 20, 0), 10, "C"),
])
def test_joint_noise_and_neighbouring_millimetres(lengths: tuple, joint: float, joint_side: str, noise: float) -> None:
    positions = tuple(single(joint + offset) for offset in (-0.001, 0, 0.001))
    la, lb = single(joint + noise), sum(lengths[3:])
    values, terms = _reactions(lengths, tuple(enumerate(positions)), 100, la, lb)
    assert [term.side for term in terms] == ["B", joint_side, "C"]
    assert sum(values) == pytest.approx(300, rel=0, abs=0.00003)
    # Assignment and right-hand lever arms use the same millimetre joint.
    assert terms[-1].distance == single(single(lb - single(positions[-1] - joint)) - lengths[5])
    assert len({term.axle_index for term in terms}) == 3


@pytest.mark.parametrize(("joint", "position", "side"), [
    (1.0625, 1.062, "C"),  # binary-exact half-millimetre: ties to even down
    (1.1875, 1.188, "B"),  # binary-exact half-millimetre: ties to even up
])
def test_comparison_grid_uses_ties_to_even(joint: float, position: float, side: str) -> None:
    # Each case chooses the opposite side from a raw position/joint comparison.
    lengths = (0, 1, joint - 1, 0.5 if side == "C" else 0, 1, 0)
    _, terms = _reactions(lengths, ((0, single(position)),), 100, joint, sum(lengths[3:]))
    assert terms[0].side == side


@pytest.mark.parametrize("joint", [1.0625, 1.1875])
def test_real_submillimetre_joint_dimension_is_preserved_in_right_lever_arm(joint):
    lengths = (0, 1, joint - 1, .5, 1, 0)
    position = single(joint + .1)
    _, terms = _reactions(lengths, ((0, position),), 100, joint, 1.5)
    assert terms[0].side == "C"
    assert terms[0].distance == single(1.5 - single(position - joint))


def test_equal_joint_reactions_choose_c_with_zero_overhang() -> None:
    values, terms = _reactions((0, 10, 0, 0, 10, 0), ((0, 10),), 100, 10, 10)
    assert values == (0, 0, 100, 0)
    assert terms[0].side == "C"


def test_subgrid_left_span_keeps_origin_on_b_and_valid_right_span_search() -> None:
    lengths = (0, single(0.00001), 0, 0, 10, 0)
    # A positive span must not disappear into the origin when the joint rounds
    # to zero. This also keeps the pre-existing both-subgrid InputError test.
    values, terms = _reactions(lengths, ((0, 0),), 100, lengths[1], 10)
    assert values == (100, 0, 0, 0)
    assert terms[0].side == "B"
    result = search_reactions(lengths, 1, 12, 4, 0, 100)
    assert result.selected_axle is not None
    assert result.max_rb_rc == pytest.approx(80, rel=0, abs=0.001)


def exact_event_maximum(case: dict) -> tuple[Fraction, set[tuple[Fraction, ...]]]:
    """Independent rational influence-line events, without Single traversal."""
    segments = tuple(Fraction(str(v)) for v in case["lengths"])
    car, a1, a2 = (Fraction(str(case[key])) for key in ("car_length", "a1", "a2"))
    axes = [i * car + t for i in range(case["car_count"]) for t in (0, a2, car - a1 - a2, car - a1)]
    joint, total = sum(segments[:3]), sum(segments)
    events = {x + support for x in axes for support in (Fraction(0), *accumulate(segments))}
    scores = {}
    for event in events:
        positions = tuple(event - x for x in axes if 0 <= event - x <= total)
        # At the joint, either beam gives the same objective in this symmetric case.
        scores[positions] = sum(case["axle_load"] * ((p - segments[0]) / segments[1] if p < joint
                                 else (total - p - segments[5]) / segments[4]) for p in positions)
    maximum = max(scores.values())
    return maximum, {positions for positions, score in scores.items() if score == maximum}


def test_long_span_change_is_a_valid_mathematical_maximum() -> None:
    case = CASES["long_span"]
    maximum, optima = exact_event_maximum(case["search"])
    assert maximum == Fraction(case["max_rb_rc_fraction"])
    assert len(optima) == 4  # distinct mathematical ties; Single can select a different one
    result = search_reactions(**case["search"])
    positions = tuple(Fraction(str(round(p, 3))) for p in result.positions)
    assert positions in optima
    # 36 axes accumulate Single error; < 0.001 kN is still below display precision.
    assert result.max_rb_rc == pytest.approx(float(maximum), rel=0, abs=0.001)
    joint = sum(Fraction(str(value)) for value in case["search"]["lengths"][:3])
    # Either beam is a valid assignment at the mathematically tied joint.
    # Away from it, nominal coordinates determine the beam independently.
    expected_sides = ["B" if position < joint else "C" if position > joint else term.side
                      for position, term in zip(positions, result.contributions)]
    assert [term.side for term in result.contributions] == expected_sides
    expected = moment_reactions(case["search"]["lengths"], list(positions), expected_sides, 150)
    assert result.reactions == pytest.approx(expected, rel=0, abs=0.0003)
    assert result.reactions != tuple(case["legacy_reactions"])
    assert result.candidate_count == 280
    assert len(result.positions) == len(result.contributions) == 36
    assert sum(result.reactions) == pytest.approx(36 * 150, rel=0, abs=0.001)
    assert sum(result.reactions[:2]) == pytest.approx(expected_sides.count("B") * 150, abs=.001)
    assert sum(result.reactions[2:]) == pytest.approx(expected_sides.count("C") * 150, abs=.001)


def fixed_example_inputs(factor: float) -> tuple[ReactionInput, dict]:
    """Freeze train/span data; use the historical fixture for unrelated geometry."""
    data = json.loads((Path(__file__).parent / "fixtures/baseline_input.json").read_text(encoding="utf-8"))
    inputs = parse_reaction_input(data)
    spans = [replace(span, l1=lengths[0], span=lengths[1], l2=lengths[2], impact=0,
                     mu=0.1, bearing="可動", h1=0, h2=2, h3=0)
             for span, lengths in zip((inputs.spans.b, inputs.spans.c),
                                     (EXAMPLE["search"]["lengths"][:3], EXAMPLE["search"]["lengths"][3:]))]
    # Every synthetic slot carries load; make its application position explicit.
    bearings = [tuple(replace(row, position=row.position if row.position is not None else 0.0,
                              d1=10, d2=0, factors=(0.1, 0.1, 0, 0)) for row in rows)
                for rows in (inputs.dead.b, inputs.dead.c)]
    inputs = replace(inputs, spans=replace(inputs.spans, b=spans[0], c=spans[1]),
                     train=replace(inputs.train, length=20, a1=2.8, a2=2.2, axle_load=160, n=10,
                                   name="EA-16", factors_ultimate=factor, factors_service=1),
                     dead=replace(inputs.dead, b=bearings[0], c=bearings[1],
                                  a=EndReaction(100, 0), d=EndReaction(100, 0)), snow=SnowReactions())
    return inputs, calculate_foundation(parse_input(data))


@pytest.mark.parametrize("case", EXAMPLE["lateral"], ids=lambda case: f"rho={case['factor']}")
def test_lateral_factors_and_downstream_actions_have_independent_expectations(case: dict) -> None:
    inputs, foundation = fixed_example_inputs(case["factor"])
    reactions = calculate_reactions(inputs)
    positions, sides = [22.2, 20, 17.2, 15], ["C", "C", "B", "B"]
    expected_lateral = moment_reactions(EXAMPLE["search"]["lengths"], positions, sides, case["axle_load"])[1:3]
    assert reactions["cells"]["直角荷重"]["S73"] == case["axle_load"]
    assert [round(value, 2) for value in expected_lateral] == case["display_rb_rc"]
    assert reactions["moving_lateral"]["reactions"][1:3] == pytest.approx(expected_lateral, rel=0, abs=0.00003)
    assert [term["side"] for term in reactions["moving_lateral"]["contributions"]] == sides

    # Service 1.0LR: two tracks, D1=100 kN/support, impact=0, mu=0.1.
    # The local friction candidate controls both movable bearings (below LR/2).
    raw = moment_reactions(EXAMPLE["search"]["lengths"], EXAMPLE["positions"], EXAMPLE["sides"], 160)
    expected_friction = [round(0.1 * (100 + 2 * force), 2) for force in raw[1:3]]
    assert expected_friction == [64.49, 68.98]
    for side, expected, applied, remote in zip(("B", "C"), expected_friction, (400, 200), (raw[0], raw[3])):
        detail = reactions["longitudinal"][1][side]
        assert detail["movable_friction"] == expected
        assert detail["fixed_candidate"] == round(applied - 0.05 * (100 + 2 * remote), 2)
        assert detail["force"] == expected
    conditions = parse_longitudinal_design_conditions({
        "鉄筋": {part: {"concrete_strength_mpa": 27} for part in ("梁", "柱", "フーチング")},
    })
    longitudinal = calculate_longitudinal(inputs, foundation, reactions, design_conditions=conditions)
    for side, expected in zip(("B", "C"), expected_friction):
        assert longitudinal["horizontal"][1][side] == single(expected)

    transverse = calculate_transverse(inputs, foundation, reactions, design_conditions=conditions)
    # The canonical basic LF is un-factored: independent 0.2P statics first,
    # then one effective factor in the resolved combination. The upstream
    # 0600 reaction assertions above retain their original rounding contract.
    base_sides = moment_reactions(EXAMPLE["search"]["lengths"], positions, sides, 32.0)[1:3]
    base_h = sum(round(value, 2) for value in base_sides)
    lateral = next(row for row in transverse["basic_cases"] if row["key"] == "vehicle_lateral")
    totals = lateral["loads"]["table_totals"]
    assert totals["H"] == pytest.approx(base_h, rel=0, abs=1e-10)
    assert totals["M"] == pytest.approx(2 * base_h, rel=0, abs=1e-10)
    combination = next(row for row in transverse["combinations"] if row["id"] == 2)
    effective = round(1.1 * case["factor"], 2)
    assert combination["coefficients"][12] == effective
    resolved = next(row for row in combination["resolved_components"] if row["define_case_id"] == 13)
    positive = next(row for row in resolved["candidates"] if row["signed_basic_case_id"] == 15)
    assert positive["coefficient_trace"]["remaining_multiplier"] == 1
    assert positive["coefficient_trace"]["effective_factor"] == effective
    assert positive["loads"]["table_totals"]["H"] == pytest.approx(effective * base_h, rel=0, abs=1e-10)
    assert positive["loads"]["table_totals"]["M"] == pytest.approx(effective * 2 * base_h, rel=0, abs=1e-10)
