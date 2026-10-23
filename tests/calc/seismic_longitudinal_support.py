"""Shared helpers for the 0710 tests: Example2 10 lookups and the calculation chain."""

import json

from reaction_support import FIXTURES, pier
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.seismic_longitudinal import calculate_seismic_longitudinal

S10 = json.loads((FIXTURES / "example2" / "seismic_longitudinal.json").read_text(encoding="utf-8"))


def chain(p=None):
    """0500, 0600, 0610 and 0710 for one input; returns (pier, reaction, 0610 result, 0710 result)."""
    p = p or pier()
    foundation = calculate_foundation(p)
    reaction = calculate_reaction(p)
    longitudinal = calculate_longitudinal(p, foundation, reaction)
    return p, reaction, longitudinal, calculate_seismic_longitudinal(p, foundation, reaction)


def seismic(p=None):
    return chain(p)[3]


def diagram(case):
    """Printed values of one load diagram case (10-9 to 10-11), by key."""
    found = next(c for c in S10["load_cases"]["cases"] if c["case"] == case)
    return {item["key"]: item["value"] for item in found["items"]}


def inertia_item(key):
    return next(item for item in S10["actions"]["self_weight_inertia"]["items"] if item["key"] == key)


def points(action):
    """{node: (N, H, M)} of the point loads of one basic case."""
    found = {}
    for point in action.points:
        assert point.node not in found
        found[point.node] = (point.n.value, point.h.value, point.m.value)
    return found
