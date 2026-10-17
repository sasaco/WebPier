"""Shared helpers for the 0600 tests: input variants and hand rounding without the implementation."""

import json
from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
REACTION = json.loads((FIXTURES / "example2" / "reaction.json").read_text(encoding="utf-8"))
SELF_WEIGHT_08 = json.loads((FIXTURES / "example2" / "self_weight_08.json").read_text(encoding="utf-8"))

ORIGIN_SLOTS = "上部工反力/起点側/B支点"
END_SLOTS = "上部工反力/終点側/C支点"


def document(**changes):
    """current.json with each 'a/b/0/c' path replaced by its value."""
    data = deepcopy(CURRENT)
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value
    return data


def pier(**changes):
    return parse_input(document(**changes))


def D(value):
    """The decimal a person reads from a printed number."""
    return Decimal(repr(float(value)))


def q(value, digits):
    """Hand rounding, 0.5 away from zero."""
    return Decimal(value).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def example2(section_id):
    """Printed values of one 05/07 section, by key."""
    section = next(item for item in REACTION["sections"] if item["id"] == section_id)
    return {item["key"]: item.get("value", item.get("result")) for item in section["items"]}


def value(printed):
    return Decimal(repr(printed.value))
