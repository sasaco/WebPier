"""Read historical Excel expectations without reusing stale A/D snapshots."""

import json
from dataclasses import replace
from pathlib import Path

from src.reaction_inputs import parse_reaction_input
from src.inputs import parse_input


def load_legacy_reaction_oracle(filename: str) -> dict:
    """Reproduce the A=B/D=C inputs used to collect these existing oracles.

    Their stored input JSON predates recalculation and can contain stale A/D
    totals. The independently calculated expectations used B/C detail sums.
    Remove only those snapshots from freshly decoded test inputs so the parser's
    missing-input fallback reproduces that run. Raw fixtures and expected values
    remain unchanged; explicit A/D input behavior has separate regression tests.
    """
    oracle = json.loads((Path(__file__).parent / "fixtures" / filename).read_text(encoding="utf-8"))
    for case in oracle["cases"]:
        reactions = case["input"]["上部工反力"]
        for side, point in (("起点側", "A支点"), ("終点側", "D支点")):
            reactions[side].get(point, {}).pop("合計", None)
    return oracle


def parse_legacy_reaction_input(data):
    """Restore typed snapshots used by historical calculation-only oracles.

    Those workbooks were driven by copied numeric inputs, including the eleven
    cells now restored as input formulas. Keep their raw evidence/expectations
    unchanged and isolate this legacy setup from current parser-contract tests.
    """
    inputs = parse_reaction_input(data)
    geometry = replace(
        inputs.geometry,
        b9=data["下部構造"]["寸法"]["側面"]["B9"],
        unit_weight_displaced_soil=data["下部構造"]["単位体積重量"]["土"]["排除した土"],
    )
    spans = {}
    bearings = {}
    for side, point, name in (("起点側", "B支点", "b"), ("終点側", "C支点", "c")):
        raw = data["上部構造"][side]
        spans[name] = replace(getattr(inputs.spans, name), h4=raw["高さ"]["h4"],
                              hs=raw["重心高_hs"], f=raw["支承位置_f"])
        rows = list(getattr(inputs.dead, name))
        rows[1] = replace(rows[1], position=data["上部工反力"][side][point]["支承"][1]["支承位置"])
        bearings[name] = tuple(rows)
    return replace(inputs, geometry=geometry, spans=replace(inputs.spans, **spans),
                   dead=replace(inputs.dead, **bearings))


def parse_legacy_foundation_input(data):
    """Keep the asymmetric B9 copied into historical calculation workbooks."""
    parsed = parse_input(data)
    side = data["下部構造"]["寸法"]["側面"]
    return replace(parsed, b_parts=tuple(side[f"B{i}"] for i in (7, 8, 9)))
