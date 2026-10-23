"""Shared helpers for the tests of the 基礎の照査 of a pile foundation (decision 89): Example橋脚4's frame, SOIL-JR's limits and
made-up responses of the pile heads and the footing top."""

from pathlib import Path

from webpier.calc.foundation_check import Requirement
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.pile_check import LONGITUDINAL, Extreme, HeadForce, Limits, check, prepare
from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.core.integrity import load_json
from webpier.core.printed import Printed
from webpier.export.soiljr import parse_sdc
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parent / "fixtures"


def frame_result():
    """(pier, the result of 0610) of Example橋脚4: two pile rows of three piles."""
    pier = parse_input(load_json((FIXTURES / "inputs" / "example4.json").read_bytes()))
    foundation = PileFoundation(calculate_pile_ground(pier), parse_sdc((FIXTURES / "soiljr" / "pile_steel_grid.sdc").read_bytes()))
    return pier, calculate_longitudinal(pier, foundation, calculate_reaction(pier))


def limits(rvd, rud, delta, theta):
    return Limits(Printed(9000.0, 1, "kN"), Printed(0.5, 3, ""), Printed(1.0, 3, ""), Printed(rvd, 1, "kN"),
                  Printed(rud, 1, "kN"), Printed(delta, 3, "mm"), "1.2%L≦100mm", Printed(theta, 5, "rad"))


LIMITS = {Requirement.LONG_TERM: limits(8000.0, 300.0, 10.0, 0.002), Requirement.SHORT_TERM: limits(10000.0, 5000.0, 10.0, 0.002),
          Requirement.SAFETY: limits(12000.0, 9000.0, 30.0, 0.006)}


def basis(found=None):
    pier, frame = found or frame_result()
    return prepare(pier, frame, LONGITUDINAL)


def forces(basis_, changes=None):
    """The head forces: by default a compression of 9000 kN in row 1 and of 12000 kN in row 2 in every pickup."""
    found = {}
    for pickup in basis_.pickups.values():
        for member, smallest in zip(basis_.members, (-9000.0, -12000.0)):
            found[(pickup, member.member)] = HeadForce(-30.0, 1, smallest, 2)
    found.update(changes or {})
    return found


def motion(basis_, delta=0.012, theta=0.0006):
    found = {}
    for pickup in basis_.pickups.values():
        found[(pickup, "dx")] = Extreme(delta, 5)
        found[(pickup, "rz")] = Extreme(theta, 6)
    return found


def result(changes=None, **motions):
    """The check of the made-up responses."""
    found = basis()
    return check(found, LIMITS, forces(found, changes), motion(found, **motions))
