"""Shared helpers for the FrameWeb export tests: input variants, the 0610 chain and the Example2 FrameWeb file.

``EXAMPLE2`` is the FrameWeb input of Example2 (.claude/docs/Example橋脚2/08_線路/frameWebForJS.json, saved by
FrameWeb itself; tests/fixtures/frameweb_example2_mapping.json is a direct copy with its SHA). Its format and its
model are expected values. Values that differ for a documented reason are listed in each test.
"""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.inputs import parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
EXAMPLE2 = json.loads((FIXTURES / "frameweb_example2_mapping.json").read_text(encoding="utf-8"))
L08 = {section["key"]: section
       for section in json.loads((FIXTURES / "example2" / "longitudinal.json").read_text(encoding="utf-8"))["sections"]}

DIMS = {"B": "下部構造/寸法/側面/", "W": "下部構造/寸法/正面/", "H": "下部構造/寸法/高さ/"}


def dims(**sizes):
    return {DIMS[key[0]] + key: size for key, size in sizes.items()}


PEDESTAL = dims(B2=0.5, B3=1.0, W2=1.0, W3=7.0, H1=0.3)  # pedestal top −0.350 from the column axis
CENTRED_PEDESTAL = dims(B2=0.85, B3=1.0, W2=1.0, W3=7.0, H1=0.3)  # pedestal on the column axis
ASYMMETRIC = dims(B7=2.5, B9=1.8, H5=0.5, H6=2.2, B8=3.0, W8=5.0) | {"下部構造/土かぶり/終点側_df2": 1.5}
CONCRETES = {"鉄筋/梁/concrete_strength_mpa": 24.0, "鉄筋/柱/concrete_strength_mpa": 40.0}


def pier(**changes):
    """current.json with each 'a/b/0/c' path replaced by its value."""
    data = deepcopy(CURRENT)
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value
    return parse_input(data)


def longitudinal(**changes):
    p = pier(**changes)
    return calculate_longitudinal(p, calculate_foundation(p), calculate_reaction(p))


def D(value):
    """The decimal a person reads from a printed or written number."""
    return Decimal(repr(float(value)))
