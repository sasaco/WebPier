"""Shared helpers for the tests of the footing of a pile foundation (decision 96): the input of the SOIL-JR sample E (two rows of piles
along the track, three across it), its frames, and the section forces of made-up lines of the PIK."""

from pathlib import Path

from webpier.calc import pile_footing as pf
from webpier.calc.footing import LONGITUDINAL, TRANSVERSE
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.pile_body import PointForces, SectionForce
from webpier.calc.pile_footing import FootingResult
from webpier.calc.pile_footing_check import calculate_pile_footing_check
from webpier.calc.pile_frame import PileFoundation
from webpier.calc.pile_ground import calculate_pile_ground
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.core.integrity import load_json
from webpier.export.soiljr import parse_sdc
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"


def pier():
    return parse_input(load_json((FIXTURES / "inputs" / "pile_seismic.json").read_bytes()))


def frames(found=None):
    found = found or pier()
    foundation = PileFoundation(calculate_pile_ground(found),
                                parse_sdc((FIXTURES / "soiljr" / "pile_cast.sdc").read_bytes()))
    reaction = calculate_reaction(found)
    return calculate_longitudinal(found, foundation, reaction), calculate_transverse(found, foundation, reaction)


def line(focus, point, largest, smallest):
    return PointForces(focus, point, 0.0, SectionForce(*largest), SectionForce(*smallest))


def made_up(basis):
    """Lines for every base member of *basis*: at the face a sagging moment (M 1000 + the member, V −300), at the pile a small
    hogging one (M −50, V 400), each as the largest and the smallest of its focus."""
    found = {}
    for member in basis.members:
        found[member] = []
        for point, moment, shear in (("ITAN", -50.0, 400.0), ("JTAN", -50.0, 400.0)):
            found[member] += [line("M", point, (1000.0 + member, -300.0, 0.0, 1), (moment, shear, 0.0, 2)),
                              line("S", point, (1000.0 + member, -300.0, 0.0, 1), (moment, shear, 0.0, 2))]
    return found


def direction(basis):
    forces = made_up(basis)
    shared = {(pickup, member): lines for pickup in basis.pickups.values() for member, lines in forces.items()}
    elements = {member: member + 100 for member in basis.members}
    return pf.complete(basis, shared, {elements[member]: lines for member, lines in forces.items()}, elements)


def result(found=None) -> FootingResult:
    found = found or pier()
    along, across = frames(found)
    return FootingResult(direction(pf.prepare(found, along, LONGITUDINAL)),
                         direction(pf.prepare(found, across, TRANSVERSE)))


def check(found=None):
    found = found or pier()
    return calculate_pile_footing_check(found, result(found).longitudinal)
