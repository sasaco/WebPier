"""Shared helpers for the 0720 tests: Example2 11 lookups and the calculation chain."""

import json

from reaction_support import FIXTURES, pier
from webpier.calc.foundation import calculate_foundation
from webpier.calc.reaction import calculate_reaction
from webpier.calc.seismic_transverse import calculate_seismic_transverse
from webpier.calc.transverse import calculate_transverse

S11 = json.loads((FIXTURES / "example2" / "seismic_transverse.json").read_text(encoding="utf-8"))


def chain(p=None):
    """0500, 0600, 0620 and 0720 for one input; returns (pier, reaction, 0620 result, 0720 result)."""
    p = p or pier()
    foundation = calculate_foundation(p)
    reaction = calculate_reaction(p)
    transverse = calculate_transverse(p, foundation, reaction)
    return p, reaction, transverse, calculate_seismic_transverse(p, foundation, reaction, transverse)


def seismic(p=None):
    return chain(p)[3]


def diagram(case):
    """Printed values of one load diagram case (11-10 to 11-12), by key."""
    found = next(c for c in S11["load_cases"]["cases"] if c["case"] == case)
    return {item["key"]: item["value"] for item in found["items"]}


def inertia_item(key):
    return next(item for item in S11["actions"]["self_weight_inertia"]["items"] if item["key"] == key)


def points(action):
    """{node: (N, H, M)} of the point loads of one basic case; a node carries at most one point."""
    found = {}
    for point in action.points:
        assert point.node not in found
        found[point.node] = (point.n.value, point.h.value, point.m.value)
    return found
