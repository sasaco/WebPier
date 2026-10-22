"""Shared helpers of the 0800 / 0810 / 0820 tests: current.json made sandy with the sample's footing bars, the
sample's reactions as FEMPython returns them, the stand-in's step table, and one direction prepared and completed."""

from __future__ import annotations

from reaction_support import pier
from webpier.calc import foundation_check as fc
from webpier.calc import footing
from webpier.calc.foundation import calculate_foundation
from webpier.calc.longitudinal import calculate_longitudinal
from webpier.calc.reaction import calculate_reaction
from webpier.calc.seismic_longitudinal import PATTERNS
from webpier.calc.transverse import calculate_transverse

SANDY = {"地盤データ/層/1/土質区分": "砂質土", "地盤データ/層/0/単位体積重量/水中": 9.0}
DIRECTIONS = {"0800_longitudinal": footing.LONGITUDINAL, "0800_transverse": footing.TRANSVERSE}
NON_SEISMIC = ("safety_moment", "safety_shear", "short_term", "long_term")
COMBINATIONS = {"safety_moment": 11, "safety_shear": 12, "short_term": 13, "long_term": 14}
# The sample's columns (12_フーチング.pdf 244 and 249): Vd, Hd, Md at the footing base.
SAMPLE_ACTIONS = {
    "0800_longitudinal": {"safety_moment": (21870.77, 495.01, 5460.42), "safety_shear": (22585.12, 473.43, 4767.98),
                          "short_term": (19505.93, 300.0, 3327.13), "long_term": (18049.95, 240.0, 3056.25)},
    "0800_transverse": {"safety_moment": (20045.0, 797.47, 10409.79), "safety_shear": (22585.12, 194.91, 3451.7),
                        "short_term": (19505.93, 0.0, 0.0), "long_term": (18049.95, 0.0, 0.0)},
}


def bars(diameter=None, pitch=None, cover_mode="自動", center=None):
    return {"diameter_mm": diameter, "pitch_mm": pitch, "cover_mode": cover_mode, "center_mm": center,
            "inner_layers": []}


def stirrup():
    return {"diameter_mm": 16, "pitch_mm": 250, "distribution_mode": "密度", "width_pitch_mm": None,
            "density_per_m": 2}


def sample_rebar():
    """The sample's footing bars (12_フーチング.pdf 255・258): D25@125 at 100 along, D29@125 at 127 across, D16 2本/m."""
    return {"materials": {"main": "SD390", "transverse": "SD390"}, "concrete_strength_mpa": 27, "aggregate_max_mm": 25,
            "pure_cover_mm": None,
            "faces": {"上": {"outer_direction": "線路", "線路": bars(), "直角": bars()},
                      "下": {"outer_direction": "線路", "線路": bars(25, 125, "指定", 100),
                             "直角": bars(29, 125, "指定", 127)}},
            "stirrups": {"線路": stirrup(), "直角": stirrup()}}


def step(case_index, number, v, h, m, rvd):
    return footing.FoundationStep(case_index, f"Case{case_index + 1}", 7, number, v, h, m, 3236.74, 3296.9, rvd,
                                  54120.2, 0.081)


# The αf of each Case: the four 照査パターン of 0710 (decision 76); the Case of STEPS is the first (αf 1.0).
ALPHA_F = tuple(alpha_f for _, alpha_f in PATTERNS)
STEPS = (step(0, 1, 16825.97, 0.0, 580.25, 543358.71), step(0, 2, 16825.97, -5747.86, 52784.78, 22069.94),
         step(0, 3, 16825.97, -5901.07, 54168.43, 16655.87), step(0, 4, 16825.97, -5949.26, 54514.06, 16655.87))


def footing_pier(**changes):
    return pier(**{**SANDY, "鉄筋/フーチング": sample_rebar(), **changes})


def prepared(direction: str, **changes):
    """(the basis of *direction*, its frame result) of current.json made sandy with the sample's footing bars."""
    p = footing_pier(**changes)
    foundation, reaction = calculate_foundation(p), calculate_reaction(p)
    if direction == "0800_longitudinal":
        frame_result = calculate_longitudinal(p, foundation, reaction)
    else:
        frame_result = calculate_transverse(p, foundation, reaction)
    return footing.prepare(p, foundation, frame_result, DIRECTIONS[direction]), frame_result


def reactions(direction: str, basis: footing.FootingBasis) -> fc.Reactions:
    """The sample's columns as both extremes of their pickup and focus (the other extreme never wins)."""
    found = {}
    for key, spec in zip(NON_SEISMIC, footing.COLUMNS):
        vd, hd, md = SAMPLE_ACTIONS[direction][key]
        extreme = fc.SupportReaction(COMBINATIONS[key], hd, -vd, md)
        found[(basis.pickups[key], spec.focus.value)] = (extreme, extreme)
    return found


def completed(direction: str, **changes) -> footing.FootingDirection:
    basis, _ = prepared(direction, **changes)
    return footing.complete(basis, reactions(direction, basis), STEPS, ALPHA_F)
