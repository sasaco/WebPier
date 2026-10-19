"""Shared helpers for the 0900 report tests: the current input and its variants, the completed result, the records.

Independent of the calc test support (tests/calc/cantilever_support.py), so that this file runs on its own.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from webpier.calc.cantilever import CantileverResult, calculate_cantilever, complete_cantilever
from webpier.calc.cantilever.response import MaxResponse, ResponseValue
from webpier.calc.reaction import ReactionResult, calculate_reaction
from webpier.core.printed import Precision
from webpier.inputs import PierInput, parse_input
from webpier.reporting.stages.cantilever import content, semantic_records

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
KH = Precision(3, "")
# The 最大応答震度 of the post/ workbooks of the current input (decision 59): Case 1 安全性 along the track,
# Case 2 安全性 across it.
LONGITUDINAL = ("線路方向_Aggre-SE.xlsx", 1, "安全性", 0.386)
TRANSVERSE = ("線路直角方向_Aggre-SE.xlsx", 2, "安全性", 0.571)


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


def response(file: str, case: int, block: str, kh: float) -> MaxResponse:
    value = ResponseValue(case, f"Case{case}", block, KH(kh))
    return MaxResponse(file, (value,), value)


def result_of(**changes) -> tuple[PierInput, ReactionResult, CantileverResult]:
    """The completed 0900 result for the current input with *changes*."""
    pier = parse_input(document(**changes))
    reaction = calculate_reaction(pier)
    basis = calculate_cantilever(pier, reaction)
    return pier, reaction, complete_cantilever(pier, reaction, basis, response(*LONGITUDINAL), response(*TRANSVERSE))


def records(pier: PierInput, reaction: ReactionResult, result: CantileverResult) -> dict[str, str]:
    """The semantic records by their id."""
    found = semantic_records(result, reaction, pier)
    assert len({record["id"] for record in found}) == len(found)
    return {record["id"]: record["text"] for record in found}


def units(pier: PierInput, reaction: ReactionResult, result: CantileverResult):
    return content(result, reaction, pier)
