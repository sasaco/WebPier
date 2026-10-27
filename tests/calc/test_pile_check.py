"""The 基礎の照査 of a pile foundation (decision 89): the heads of the piles and the footing top against SOIL-JR's limits.

The frame is Example橋脚4's (two pile rows of three piles along the track). The responses are made up and checked by hand: the
force of a row's member is over its piles, Vd is the largest compression and Vud the largest tension of the rows, δd and θd the
extremes of the footing top, and each check is γi times the response over the limit, rounded to two decimals. The
responses of the safety are the frame's times the 応答値係数 γR 1.2 (decision 104)."""

import pytest

from pile_check_support import LIMITS, basis, forces, frame_result, motion, result
from webpier.calc.foundation_check import Requirement
from webpier.calc.frame import NodeRole
from webpier.calc.pile_check import LONGITUDINAL, TRANSVERSE, HeadForce, PileResponseError, check, prepare
from webpier.core.errors import InputError


def test_the_basis_is_the_pile_rows_the_footing_top_and_the_pickups():
    pier, frame = frame_result()
    found = basis((pier, frame))
    assert [(member.row, member.piles) for member in found.members] == [(1, 3), (2, 3)]
    assert [member.member for member in found.members] == [nodes.member for nodes in frame.frame.pile_nodes]
    assert found.node == frame.frame.node(NodeRole.FOOTING_TOP).number
    assert found.pickups == {"long_term": 7, "short_term": 8, "safety": 6}  # the extraction groups of 0610


def test_a_frame_without_piles_is_refused():
    from longitudinal_support import chain  # noqa: PLC0415

    pier, _, frame = chain()
    with pytest.raises(InputError, match="杭の骨組が必要です"):
        prepare(pier, frame, LONGITUDINAL)


def test_the_responses_are_the_largest_per_pile_and_the_checks_are_gamma_times_over_the_limit():
    found = result()
    long_term, short_term, safety = found.columns
    assert (long_term.vd.value, long_term.vd_row, long_term.vd_combination) == (4000.0, 2, 2)  # 12000 / 3 piles of row 2
    assert (long_term.vud, long_term.vud_row, long_term.vud_combination) == (None, None, None)  # -30 / 3 is no tension
    assert long_term.pull_out is None
    assert (long_term.delta.value, long_term.delta_combination) == (12.0, 5)  # 0.012 m
    assert (long_term.theta.value, long_term.theta_combination) == (0.0006, 6)
    assert long_term.gamma_i.value == 1.0 and safety.gamma_i.value == 1.2
    assert (long_term.gamma_r.value, short_term.gamma_r.value, safety.gamma_r.value) == (1.0, 1.0, 1.2)
    # the safety's responses times γR: 1.2 × 12000 / 3 = 4800, 1.2 × 12 = 14.4 mm, 1.2 × 0.0006 = 0.00072 rad
    assert (safety.vd.value, safety.delta.value, safety.theta.value) == (4800.0, 14.4, 0.00072)
    assert (long_term.vertical.value.value, long_term.horizontal.value.value, long_term.rotation.value.value) == (0.5, 1.2, 0.3)
    assert not long_term.horizontal.ok and long_term.vertical.ok and long_term.rotation.ok  # 12 / 10 = 1.2
    # 1.2 × 4800 / 12000, 1.2 × 14.4 / 30 = 0.576, 1.2 × 0.00072 / 0.006 = 0.144
    assert (safety.vertical.value.value, safety.horizontal.value.value, safety.rotation.value.value) == (0.48, 0.58, 0.14)
    assert short_term.requirement is Requirement.SHORT_TERM
    assert found.engineering_status == "not_ok"


def test_a_pile_head_in_tension_is_checked_against_the_pull_out_resistance():
    found = basis()
    changes = {(found.pickups["safety"], found.members[0].member): HeadForce(2700.0, 7, -9000.0, 2)}
    done = result(changes, delta=0.001)
    safety = done.columns[2]
    assert (safety.vud.value, safety.vud_row, safety.vud_combination) == (1080.0, 1, 7)  # γR 1.2 × 2700 / 3 piles
    assert safety.pull_out.value.value == 0.14 and safety.pull_out.ok  # 1.2 × 1080 / 9000 = 0.144
    assert done.engineering_status == "ok"


def test_a_tension_above_the_resistance_fails_the_check():
    found = basis()
    changes = {(found.pickups["long_term"], found.members[0].member): HeadForce(1200.0, 3, -9000.0, 2)}
    done = result(changes, delta=0.001)
    assert done.columns[0].pull_out.value.value == 1.33 and not done.columns[0].pull_out.ok  # 400 / 300
    assert done.engineering_status == "not_ok"


def test_a_missing_pickup_is_named():
    found = basis()
    missing = forces(found)
    del missing[(found.pickups["short_term"], found.members[1].member)]
    with pytest.raises(PileResponseError, match=f"杭頭の軸力のピックアップ {found.pickups['short_term']}"):
        check(found, LIMITS, missing, motion(found))
    incomplete = motion(found)
    del incomplete[(found.pickups["safety"], "rz")]
    with pytest.raises(PileResponseError, match=f"フーチング天端の変位のピックアップ {found.pickups['safety']}"):
        check(found, LIMITS, forces(found), incomplete)


def test_the_transverse_direction_is_the_same_check_on_the_other_widths():
    assert LONGITUDINAL.turned is False and TRANSVERSE.turned is True
