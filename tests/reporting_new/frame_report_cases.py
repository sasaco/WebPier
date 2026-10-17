"""Inputs for the 0610/0710 report and frame-figure tests: Example2 and variants that change the frame.

Each variant changes the shape of the frame the reports draw and print:
``pedestal`` has a 桁受け (H1 > 0) off the column axis, so the bearings sit on
its top; ``asymmetric`` has an asymmetric footing with a haunch, so the rigid
member from the footing top to its centroid is inclined; ``merged`` has no beam
prism and no haunch (H2 = H3 = 0), so three node roles share one node.
"""

from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal
from functools import cache
from pathlib import Path

from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import LongitudinalResult, calculate_longitudinal
from webpier.calc.reaction import ReactionResult, calculate_reaction
from webpier.calc.seismic_longitudinal import SeismicLongitudinalResult, calculate_seismic_longitudinal
from webpier.core.printed import Printed
from webpier.inputs import PierInput, parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
_DIMS = {"B": "下部構造/寸法/側面/", "W": "下部構造/寸法/正面/", "H": "下部構造/寸法/高さ/"}


def _dims(**sizes: float) -> dict[str, float]:
    return {_DIMS[key[0]] + key: size for key, size in sizes.items()}


CASES: dict[str, dict[str, object]] = {
    "current": {},
    "pedestal": _dims(B2=0.5, B3=1.0, W2=1.0, W3=7.0, H1=0.3),
    "asymmetric": _dims(B7=2.5, B9=1.8, H5=0.5, H6=2.2, B8=3.0, W8=5.0),
    "merged": _dims(H2=0.0, H3=0.0),
}


def pier_input(case: str) -> PierInput:
    document = deepcopy(CURRENT)
    for path, value in CASES[case].items():
        node = document
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[key] = value
    return parse_input(document)


@cache
def chain(case: str) -> tuple[PierInput, ReactionResult, LongitudinalResult, SeismicLongitudinalResult]:
    pier = pier_input(case)
    foundation = calculate_foundation(pier)
    reaction = calculate_reaction(pier)
    longitudinal = calculate_longitudinal(pier, foundation, reaction)
    return pier, reaction, longitudinal, calculate_seismic_longitudinal(pier, foundation, reaction, longitudinal)


def text(value: Printed | None, *, thousands: bool = False) -> str:
    """Independent of webpier.reporting: the written decimal at the carried digits."""
    if value is None:
        return ""
    decimal = Decimal(repr(value.value)).quantize(Decimal(1).scaleb(-value.digits))
    assert float(decimal) == value.value
    return format(decimal, ",f" if thousands else "f")


# 0620/0720: the transverse frame changes with W sizes; R ≠ 0 adds the centrifugal cases (decision 33);
# the ground (footing top + min(df1, df2)) cuts the column in Example2 and the haunch in ``haunch_ground``.
TRANSVERSE_CASES: dict[str, dict[str, object]] = {
    "current": {},
    "curve": {"上部構造/起点側/曲線半径": 600, "上部構造/終点側/曲線半径": 800},
    "pedestal": CASES["pedestal"],
    "asymmetric": _dims(W7=2.75, W9=1.75, H5=0.5, H6=2.2, W8=5.0),
    "haunch_ground": {"下部構造/土かぶり/起点側_df1": 5.2, "下部構造/土かぶり/終点側_df2": 5.4},
    "merged": CASES["merged"],
}


def _input(changes: dict[str, object]) -> PierInput:
    document = deepcopy(CURRENT)
    for path, value in changes.items():
        node = document
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[key] = value
    return parse_input(document)


@cache
def transverse_chain(case: str):
    """(pier, reaction, TransverseResult, SeismicTransverseResult) of a transverse variant."""
    from webpier.calc.seismic_transverse import calculate_seismic_transverse
    from webpier.calc.transverse import calculate_transverse

    pier = _input(TRANSVERSE_CASES[case])
    foundation = calculate_foundation(pier)
    reaction = calculate_reaction(pier)
    transverse = calculate_transverse(pier, foundation, reaction)
    return pier, reaction, transverse, calculate_seismic_transverse(pier, foundation, reaction, transverse)
