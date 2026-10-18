"""Shared helpers for the FrameWeb export tests: input variants, the 0610 and 0620 chains and the Example2 files.

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
from webpier.calc.transverse import calculate_transverse
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


def mirrored_nodes(nodes):
    """Example2's nodes (the old FrameWeb format, y upward) in the current axes we write (y downward, decision 44).

    The same pier mirrored top to bottom: y negated, x kept (0 stays 0, not −0).
    """
    return {number: {**node, "y": -node["y"] or 0} for number, node in nodes.items()}


def mirrored_rows(rows):
    """Example2's node load rows (n, tx, ty, rz) in the current axes: ty and rz negated, tx kept (decision 44)."""
    return [(n, tx, None if ty is None else -ty, None if rz is None else -rz) for n, tx, ty, rz in rows]


# 0620. EXAMPLE2_09 is the FrameWeb input of Example2 09 (.claude/docs/Example橋脚2/09_直角/frameWebForJS.json, saved
# by FrameWeb itself; tests/fixtures/frameweb_transverse_example2_file.json is a direct copy with its SHA). T09 is
# the independent transcription of 09_直角.pdf.
EXAMPLE2_09 = json.loads((FIXTURES / "frameweb_transverse_example2_file.json").read_text(encoding="utf-8"))
T09 = {section["key"]: section
       for section in json.loads((FIXTURES / "example2" / "transverse.json").read_text(encoding="utf-8"))["sections"]}
DF = ("下部構造/土かぶり/起点側_df1", "下部構造/土かぶり/終点側_df2")


def ground(depth):
    """Both soil depths over the footing: the ground is the footing top + depth."""
    return dict.fromkeys(DF, depth)


EXAMPLE2_GROUND = ground(1.08)  # Example2 9-12 / 8-28: Df − H6 = 1.080 (current.json has 2.000)
# Pedestal across the track at xC = (2 × 0.500 + 7.000 − 9.000)/2 = −0.500 from the column axis: an arm and a stub.
T_PEDESTAL = dims(B2=0.85, B3=1.0, W2=0.5, W3=7.0, H1=0.3)
T_ASYMMETRIC = dims(W7=2.5, W9=2.0, H5=0.5, H6=2.2, B8=3.0, W8=5.0)
# Beam 3.200 wide, haunch from 3.200 down to 3.200 − 0.100 − 0.200 = 2.900, column 2.500 (decision 12).
WIDTHS = dims(B1=3.2, B4=0.1, B5=0.2, B6=2.5)
CURVE = {"上部構造/起点側/曲線半径": 600, "上部構造/起点側/列車速度": 130}  # decision 33: centrifugal on R ≠ 0


def transverse(**changes):
    p = pier(**changes)
    return calculate_transverse(p, calculate_foundation(p), calculate_reaction(p))
