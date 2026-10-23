"""Inputs for the 0500 report tests: the current input and variants that change every value."""

from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from webpier.calc.embedment import EmbedmentResult, applicable_embedment
from webpier.calc.foundation import FoundationResult, calculate_foundation
from webpier.core.printed import Printed
from webpier.inputs import PierInput, parse_input

FIXTURES = Path(__file__).parents[1] / "fixtures"
CURRENT = json.loads((FIXTURES / "inputs" / "current.json").read_text(encoding="utf-8"))

EXTRA_LAYER = {
    "層番": "第2層", "層厚": 3.25, "土質区分": "粘性土", "N値": 12,
    "単位体積重量": {"湿潤": 17.5, "水中": 7.5}, "内部摩擦角_φd": 28.4,
    "粘着力_c": 120, "変形係数_Ed": 28000, "De": None,
}

# Each variant changes the dimensions, the support soil (equation), Ed, φ and the cover,
# so a value that is not taken from the result cannot coincide with the expectation.
# Df / γ2 are printed where they apply (calc.embedment): current and level; clay and deep have a
# sloping cover and alternating three layers.
CASES: dict[str, dict[str, object]] = {
    "current": {},
    "clay": {
        "地盤データ/層/1/土質区分": "粘性土", "地盤データ/層/1/変形係数_Ed": 50000,
        "地盤データ/層/1/内部摩擦角_φd": 31.3, "地盤データ/層/1/層厚": 6.4,
        "下部構造/寸法/側面/B7": 1.5, "下部構造/寸法/側面/B9": 1.25, "下部構造/寸法/正面/W7": 2.0,
        "下部構造/土かぶり/終点側_df2": 1.08, "下部構造/寸法/高さ/H5": 0.35,
    },
    "alternating": {
        "地盤データ/層/1/土質区分": "砂質土と粘性土の互層", "地盤データ/層/1/変形係数_Ed": 98765,
        "地盤データ/層/1/内部摩擦角_φd": 37.5, "地盤データ/層/1/粘着力_c": 250,
        "下部構造/寸法/側面/B8": 3.05, "下部構造/寸法/正面/W8": 5.15,
        "下部構造/土かぶり/起点側_df1": 1.5,
    },
    # A deep footing: the surface-thickness formula is long enough to wrap.
    "deep": {
        "下部構造/寸法/高さ/H6": 12.345, "下部構造/寸法/高さ/H5": 1.25,
        "下部構造/土かぶり/起点側_df1": 10.125, "下部構造/土かぶり/終点側_df2": 10.5,
        "地盤データ/層/1/内部摩擦角_φd": 29.9,
    },
    # Level cover with other water and unit weights: γ2 = ((4.000 − 1.250) × 19.0 + 1.250 × 9.5) / 4.000 = 16.0.
    "level": {
        "下部構造/寸法/高さ/H6": 2.2, "下部構造/寸法/高さ/H5": 0.3,
        "下部構造/土かぶり/起点側_df1": 1.5, "下部構造/土かぶり/終点側_df2": 1.5, "下部構造/水位/平水位_hw2": 1.25,
        "地盤データ/層/0/単位体積重量/湿潤": 19.0, "地盤データ/層/0/単位体積重量/水中": 9.5,
    },
}


def pier_input(case: str) -> PierInput:
    document = deepcopy(CURRENT)
    for path, value in CASES[case].items():
        node = document
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[key] = value
    if case == "alternating":  # a third layer between 表層 and 支持層
        document["地盤データ"]["層"].insert(1, deepcopy(EXTRA_LAYER))
    return parse_input(document)


def case(name: str) -> tuple[FoundationResult, PierInput, EmbedmentResult | None]:
    pier = pier_input(name)
    foundation = calculate_foundation(pier)
    return foundation, pier, applicable_embedment(pier, foundation)


def text(value: Printed | None, *, thousands: bool = False) -> str:
    """Independent of webpier.reporting: the written decimal at the carried digits."""
    if value is None:
        return ""
    decimal = Decimal(repr(value.value)).quantize(Decimal(1).scaleb(-value.digits))
    assert float(decimal) == value.value
    return format(decimal, ",f" if thousands else "f")
