"""Inputs for the 0600 report tests: the current input and variants that change the printed branches."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import fields, is_dataclass, replace
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

from webpier.calc.reaction import ReactionResult, calculate_reaction
from webpier.core.printed import Printed
from webpier.inputs import PierInput, parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))
ORIGIN_SLOTS = "上部工反力/起点側/B支点"
END_SLOTS = "上部工反力/終点側/C支点"

# H1 > 0 with an offset pedestal, an asymmetric beam/column/footing, a sloped soil surface
# with the high water inside the sloped zone and a negative low water (as tests/calc).
PEDESTAL = {
    "下部構造/寸法/側面": {"B1": 3.0, "B2": 0.3, "B3": 1.2, "B4": 0.4, "B5": 0.2, "B6": 2.0, "B7": 1.5, "B8": 2.4,
                       "B9": 2.1},
    "下部構造/寸法/正面": {"W1": 8.0, "W2": 0.5, "W3": 6.0, "W4": 1.5, "W5": 2.0, "W6": 4.0, "W7": 2.0, "W8": 4.6,
                       "W9": 2.4},
    "下部構造/寸法/高さ": {"H1": 0.25, "H2": 1.8, "H3": 0.6, "H4": 5.0, "H5": 0.4, "H6": 1.5},
    "下部構造/土かぶり": {"起点側_df1": 1.2, "終点側_df2": 0.6},
    "下部構造/水位": {"高水位_hw1": 2.8, "平水位_hw2": 3.5, "低水位_hw3": -0.5},
}

CASES: dict[str, dict[str, Any]] = {
    "current": {},
    "pedestal": PEDESTAL,
    # The soil is higher at the end side: the wedge lies at the origin side.
    "mirrored": {**PEDESTAL, "下部構造/土かぶり": {"起点側_df1": 0.6, "終点側_df2": 1.2}},
    # EA-17 (its own train with the line load behind it, and its braking rule, decision 101), a curve, swapped bearing
    # types without the restorability coefficient.
    "ea17": {
        "上部構造/列車/車両名": "EA-17", "上部構造/列車/編成数": None,
        "上部構造/起点側/曲線半径": 600, "上部構造/起点側/列車速度": 130,
        "上部構造/終点側/曲線半径": 400, "上部構造/終点側/列車速度": 100,
        "上部構造/支承データ/起点側": {"支承名": "固定", "摩擦係数_μ": 0.15, "ゴム支承の箇所数": None, "ストッパーの箇所数": None,
                               "片持ち梁上のゴム支承": None, "片持ち梁上のストッパー": None},
        "上部構造/支承データ/終点側": {"支承名": "可動", "摩擦係数_μ": 0.05, "ゴム支承の箇所数": None, "ストッパーの箇所数": None,
                               "片持ち梁上のゴム支承": None, "片持ち梁上のストッパー": None},
    },
    # EA-17 on longer girders: the line load behind E-17 reaches the end girder (RC = (q a e + P Σa) / l).
    "ea17_tail": {"上部構造/列車/車両名": "EA-17", "上部構造/列車/編成数": None,
                  "上部構造/起点側/桁長": {"L1": 0.5, "スパン長": 20.0, "L2": 0.5},
                  "上部構造/終点側/桁長": {"L1": 0.5, "スパン長": 15.0, "L2": 0.5}},
    # EA-17 on 3 m girders: A-17 gives the larger reactions, its axle loads printed by load.
    "ea17_a17": {"上部構造/列車/車両名": "EA-17", "上部構造/列車/編成数": None,
                 "上部構造/起点側/桁長": {"L1": 0.3, "スパン長": 3.0, "L2": 0.3},
                 "上部構造/終点側/桁長": {"L1": 0.3, "スパン長": 3.0, "L2": 0.3}},
    # No beam haunch, no soil cover, a column flush with the footing's end edge (B9 = 0),
    # and no bearing of the end girder on this pier (all ten slots empty).
    "bare": {"下部構造/寸法/高さ/H3": 0.0, "下部構造/土かぶり": {"起点側_df1": 0.0, "終点側_df2": 0.0},
             "下部構造/寸法/側面/B9": 0.0,
             **{f"{END_SLOTS}/{slot}": None for slot in range(10)}},
    # Empty slots between occupied bearings, and no snow at all.
    "slots": {
        f"{ORIGIN_SLOTS}/1": None, f"{ORIGIN_SLOTS}/6": deepcopy(CURRENT["上部工反力"]["起点側"]["B支点"][1]),
        f"{END_SLOTS}/0": None, f"{END_SLOTS}/9": deepcopy(CURRENT["上部工反力"]["終点側"]["C支点"][0]),
    },
}


def _zero_snow(document: dict[str, Any]) -> None:
    keys = ("雪荷重_2年確率", "雪荷重_10年確率", "雪荷重_30年確率")
    for side, far, slots in (("起点側", "A支点", "B支点"), ("終点側", "D支点", "C支点")):
        reactions = document["上部工反力"][side]
        for key in keys:
            reactions[far][key] = 0.0
        for slot in reactions[slots]:
            if slot is not None:
                for key in keys:
                    slot[key] = 0.0


def input_document(case: str) -> dict[str, Any]:
    document = deepcopy(CURRENT)
    for path, value in CASES[case].items():
        node = document
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = deepcopy(value)
    if case == "slots":
        _zero_snow(document)
    return document


def pier_input(case: str) -> PierInput:
    return parse_input(input_document(case))


def case(name: str) -> tuple[ReactionResult, PierInput]:
    pier = pier_input(name)
    return calculate_reaction(pier), pier


def text(value: Printed | None) -> str:
    """Independent of webpier.reporting: the written decimal at the carried digits."""
    if value is None:
        return ""
    decimal = Decimal(repr(value.value)).quantize(Decimal(1).scaleb(-value.digits))
    assert float(decimal) == value.value
    return format(decimal, "f")


Path_ = tuple[Any, ...]


def leaves(value: Any, path: Path_ = ()) -> Iterator[tuple[Path_, Printed]]:
    """Every Printed in a result tree, with its path of field names and tuple indices."""
    if isinstance(value, Printed):
        yield path, value
    elif is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            yield from leaves(getattr(value, item.name), (*path, item.name))
    elif isinstance(value, tuple):
        for index, item in enumerate(value):
            yield from leaves(item, (*path, index))
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, (*path, key))
    else:
        assert value is None or isinstance(value, (str, int, Enum)), (path, value)


def replaced(value: Any, path: Path_, new: Any) -> Any:
    if not path:
        return new
    head, *rest = path
    if isinstance(value, tuple):
        return tuple(replaced(item, tuple(rest), new) if index == head else item for index, item in enumerate(value))
    if isinstance(value, dict):
        return {key: replaced(item, tuple(rest), new) if key == head else item for key, item in value.items()}
    return replace(value, **{head: replaced(getattr(value, head), tuple(rest), new)})


def dotted(path: Path_) -> str:
    return ".".join(str(part) for part in path)
