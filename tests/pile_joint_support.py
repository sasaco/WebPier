"""A joint result of the example (Example橋脚4 表 3.2.10 and 3.2.11) for the tests of the report and the pipeline."""

from copy import deepcopy

from webpier.calc.pile_body import PointForces, SectionForce, steel
from webpier.calc.pile_joint import assemble, section, select
from webpier.core.integrity import load_json
from webpier.inputs import parse_input
from example4_support import EXAMPLE4_INPUT

PUSH, PULL = 2957.2, 2449.8  # the example's Mud, kN m (row 2, the push side, and row 1, the pull side)


def example4_input():
    return parse_input(deepcopy(load_json(EXAMPLE4_INPUT.read_bytes())))


def head_line(md=284.6, nd=3847.9, combination=18, piles=3):
    """The PIK line (focus M) of the head of a pile row whose largest bending moment is *md* in the case with the axial
    compression *nd*: the bundled member's forces are the piles' times *piles*; the other sign has a smaller moment."""
    return PointForces("M", "ITAN", 0.0, SectionForce(md * piles, 0.0, -nd * piles, combination),
                       SectionForce(-md / 2 * piles, 0.0, -nd * piles, 1))


# the sample's table 3.2.10: row 1 (member 7, the pull side) and row 2 (member 8, the push side)
ROWS = {1: (284.0, 1338.1, 15), 2: (284.6, 3847.9, 18)}


def joint_result(rows=(1, 2), moments=None):
    pier = example4_input()
    forces = [select(row, row + 6, 3, [head_line(*ROWS[row])]) for row in rows]
    found = moments or {1: PULL, 2: PUSH}
    return assemble(section(pier, steel(pier)), forces, {row: found[row] for row in rows}, "5.0.1", "ab" * 32)
