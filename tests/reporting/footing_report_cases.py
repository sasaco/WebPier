"""The 0800 / 0810 / 0820 results the report tests lay out (decision 60).

current.json made sandy with the sample's footing bars (12_フーチング.pdf 255・258), the sample's reactions as
FEMPython returns them and the stand-in's step table: the same input as tests/calc/footing_support.py (each test
directory has its own support module).
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from webpier.calc import foundation_check as fc
from webpier.calc import footing
from webpier.calc.footing_check import FootingCheckResult, calculate_footing_check
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.transverse import calculate_transverse
from webpier.inputs import PierInput, parse_input

CURRENT = json.loads((Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json").read_text(encoding="utf-8"))
DIRECTIONS = {"0800_longitudinal": footing.LONGITUDINAL, "0800_transverse": footing.TRANSVERSE}
NON_SEISMIC = ("safety_moment", "safety_shear", "short_term", "long_term")
SAMPLE_ACTIONS = {
    "0800_longitudinal": {"safety_moment": (21870.77, 495.01, 5460.42), "safety_shear": (22585.12, 473.43, 4767.98),
                          "short_term": (19505.93, 300.0, 3327.13), "long_term": (18049.95, 240.0, 3056.25)},
    "0800_transverse": {"safety_moment": (20045.0, 797.47, 10409.79), "safety_shear": (22585.12, 194.91, 3451.7),
                        "short_term": (19505.93, 0.0, 0.0), "long_term": (18049.95, 0.0, 0.0)},
}


def _row(direction, face, diameter=None, pitch=None, cover_mode="自動", center=None, stack_order=1):
    return {"diameter_mm": diameter, "material": None, "cover_mode": cover_mode, "center_mm": center,
            "clear_gap_mm": None, "direction": direction, "face": face, "pitch_mm": pitch, "layers": 1,
            "stack_order": stack_order}


def _stirrup(direction):
    return {"type": "内側", "direction": direction, "diameter_mm": 16, "material": None, "sets": None, "pitch_mm": 250,
            "start_mm": None, "end_mm": None, "legs_mode": "指定", "effective_legs": None, "distribution_mode": "密度",
            "width_pitch_mm": None, "density_per_m": 2}


def sample_rebar():
    return {"materials": {"main": "SD390", "transverse": "SD390"}, "concrete_strength_mpa": 27, "aggregate_max_mm": 25,
            "pure_cover_mm": None,
            "main_rows": [_row("線路", "上"), _row("線路", "下", 25, 125, "指定", 100, 1), _row("直角", "上", stack_order=2),
                          _row("直角", "下", 29, 125, "指定", 127, 2)],
            "side_rows": [], "band_rows": [_stirrup("線路"), _stirrup("直角")], "manual_positions": [],
            "position_mode": "基本"}


def footing_pier(**conditions) -> PierInput:
    """current.json made sandy with the sample's footing bars; *conditions* replace 柱の断面照査 items."""
    data = deepcopy(CURRENT)
    data["地盤データ"]["層"][1]["土質区分"] = "砂質土"
    data["地盤データ"]["層"][0]["単位体積重量"]["水中"] = 9.0
    data["鉄筋"]["フーチング"] = sample_rebar()
    data["柱の断面照査"] |= conditions
    return parse_input(data)


def _step(number, v, h, m, rvd):
    return footing.FoundationStep(0, "Case1", 7, number, v, h, m, 3236.74, 3296.9, rvd, 54120.2, 0.081)


STEPS = (_step(1, 16825.97, 0.0, 580.25, 543358.71), _step(2, 16825.97, -5747.86, 52784.78, 22069.94),
         _step(3, 16825.97, -5901.07, 54168.43, 16655.87), _step(4, 16825.97, -5949.26, 54514.06, 16655.87))


def completed(direction: str = "0800_longitudinal", pier: PierInput | None = None) -> footing.FootingDirection:
    """0800's result of *direction* with the sample's reactions and the stand-in's step table."""
    pier = pier or footing_pier()
    foundation, reaction = calculate_foundation(pier), calculate_reaction(pier)
    if direction == "0800_longitudinal":
        frame_result = calculate_longitudinal(pier, foundation, reaction)
    else:
        frame_result = calculate_transverse(pier, foundation, reaction)
    basis = footing.prepare(pier, foundation, frame_result, DIRECTIONS[direction])
    reactions = {}
    for key, spec in zip(NON_SEISMIC, footing.COLUMNS):
        vd, hd, md = SAMPLE_ACTIONS[direction][key]
        extreme = fc.SupportReaction(10 + NON_SEISMIC.index(key), hd, -vd, md)
        reactions[(basis.pickups[key], spec.focus.value)] = (extreme, extreme)
    return footing.complete(basis, reactions, STEPS)


def footing_check(direction: str = "0800_longitudinal", **conditions) -> tuple[PierInput, FootingCheckResult]:
    """(the input, 0810's or 0820's check of *direction*)."""
    pier = footing_pier(**conditions)
    return pier, calculate_footing_check(pier, completed(direction, pier))
