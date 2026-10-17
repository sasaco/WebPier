"""Shared helpers for the 0610 tests: Example2 08 lookups and the calculation chain."""

import json

from reaction_support import FIXTURES, pier
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction

L08 = json.loads((FIXTURES / "example2" / "longitudinal.json").read_text(encoding="utf-8"))
SECTIONS = {section["key"]: section for section in L08["sections"]}


def chain(p=None):
    """0500, 0600 and 0610 for one input; returns (pier, reaction, result)."""
    p = p or pier()
    reaction = calculate_reaction(p)
    return p, reaction, calculate_longitudinal(p, calculate_foundation(p), reaction)


def longitudinal(p=None):
    return chain(p)[2]


def items(section):
    return {item["key"]: item for item in SECTIONS[section]["items"] if "value" in item}


def table(section, key=None):
    """{row key: [cell values]} of a printed table; None for a '-' cell."""
    tables = SECTIONS[section]["tables"]
    chosen = tables[0] if key is None else next(t for t in tables if t["key"] == key)
    return {row["key"]: [None if cell is None else cell["value"] for cell in row["cells"]] for row in chosen["rows"]}


def diagram(case):
    """Printed N/M/q/P/H of one load diagram case (8-6 to 8-8)."""
    found = next(c for c in SECTIONS["load_diagrams"]["cases"] if c["case"] == case)
    return {item["key"]: item["value"] for item in found["items"]}
