"""Explicit V5.2 profile and direct-foundation conditions for NDU export.

No sample files or saved reports are read here.  The native-field rationale is
recorded in .claude/docs/research/webpier-longitudinal-ndu-field-map.md.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from .calculator import calculate as calculate_foundation
from .inputs import InputError, parse_input
from .reaction_inputs import parse_reaction_input
from .reaction_math import excel_round

PROFILE_ID = "webpier-longitudinal-v52-v1"
TRANSVERSE_PROFILE_ID = "webpier-transverse-v52-v1"
TARGET_VERSION = "5.2-L03"
SCHEMA_VERSION = 1
GEOMETRY_TOLERANCE = 1e-9
UNSET = -3.402823e38

# Engineering choices belong to raw input; there are no implicit sample values.
_PROFILE = {
    "foundation_type": "direct", "nonlinear_curve": "M-theta",
    "failure_mode": "bending", "micro_length_m": .01,
    "rigid": {"area_m2": 1000, "inertia_m4": 1000, "Ec_kn_mm2": 25},
    "analysis": {"method": "displacement_increment", "steps": 300,
                 "target_displacement_m": -.3, "control_role": "cap_top",
                 "load_divisions": 1000, "limited_final_step": 200,
                 "convergence_tolerance": .001, "intermediate_trials": 999,
                 "final_trials": 999, "increment_displacement_m": -.001},
    "foundation": {"period": "short_term", "water_level": "normal",
                   "soil_type": 1, "cohesion_kn_m2": 0, "KR2": 2, "KR3": 20},
    "section": {"Es_kn_mm2": 200, "aggregate_max_mm": None,
                "cracking_strength": 0, "joint_concrete_strength": 0,
                "fixed_axial_force": None, "end_condition": 0,
                "end_condition_length_mm": 0, "yield_location": "centroid",
                "safety": {"GC": 1.3, "GR": 1, "GS": 1.05, "GB1": 1,
                           "GB2": 1, "GB23": 1.15, "GBC": None, "GBV": None,
                           "GBS": 0, "K": .9, "GBVD": None, "GBVO": 1.3}},
}


def get_profile(raw: Mapping, direction: str = "longitudinal") -> dict:
    """Resolve the versioned model with the four explicitly entered conditions."""
    if direction not in ("longitudinal", "transverse"):
        raise InputError("JRSNAP: directionはlongitudinal/transverseが必要です")
    namespace = f"jrsnap_{direction}"
    profile = deepcopy(_PROFILE)
    if direction == "transverse":
        profile["analysis"].update(steps=350, target_displacement_m=.35,
                                   control_role="superstructure_b", limited_final_step=300,
                                   increment_displacement_m=.001)
    for field, coefficient in (("shear_factor_vcd", "GBC"), ("shear_factor_vsd", "GBV"),
                               ("shear_factor_vdd", "GBVD")):
        value = number(at(raw, f"{namespace}.{field}"), f"{namespace}.{field}",
                       minimum=0, maximum=99.99)
        if value == 0:
            raise InputError(f"JRSNAP: {namespace}.{field}は正値が必要です")
        profile["section"]["safety"][coefficient] = value
    profile["section"]["aggregate_max_mm"] = number(
        at(raw, f"{namespace}.aggregate_max_mm"), f"{namespace}.aggregate_max_mm",
        minimum=.1, maximum=999999)
    return profile


def at(value: Mapping, path: str) -> Any:
    current: Any = value
    for key in path.split("."):
        if not isinstance(current, Mapping) or key not in current:
            raise InputError(f"JRSNAP: {path}が必要です")
        current = current[key]
    return current


def number(value: Any, path: str, *, minimum: float | None = None,
           maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"JRSNAP: {path}には有限の数値が必要です")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise InputError(f"JRSNAP: {path}の数値範囲を超えています") from exc
    if not math.isfinite(result):
        raise InputError(f"JRSNAP: {path}には有限の数値が必要です")
    if ((minimum is not None and result < minimum) or
            (maximum is not None and result > maximum)):
        raise InputError(f"JRSNAP: {path}が対応範囲外です")
    return result


def canonical_sha256(value: Mapping) -> str:
    try:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, OverflowError) as exc:
        raise InputError("JRSNAP: 計算スナップショットに正規化できない値があります") from exc
    return hashlib.sha256(data).hexdigest()


def derive_jrsnap_soil_conditions(raw: dict, foundation: Mapping,
                                  seismic: Mapping, direction: str = "longitudinal") -> dict:
    """Derive Df/GAM2 for one level cover layer, with water inside that layer."""
    if direction not in ("longitudinal", "transverse"):
        raise InputError("JRSNAP: directionはlongitudinal/transverseが必要です")
    stage = "0720" if direction == "transverse" else "0710"
    geometry = at(seismic, "input.geometry")
    # Equality comes before min(), so a sloping cover cannot silently pass.
    df1 = number(at(geometry, "df1"), f"{stage}.input.geometry.df1", minimum=0)
    df2 = number(at(geometry, "df2"), f"{stage}.input.geometry.df2", minimum=0)
    cover_difference = abs(df1 - df2)
    if cover_difference > GEOMETRY_TOLERANCE:
        raise InputError("JRSNAP: df1/df2の土被り差は1e-9 m以下が必要です")
    df = sum(number(at(geometry, name), f"{stage}.input.geometry.{name}", minimum=0)
             for name in ("h6", "h5")) + min(df1, df2)
    number(df, "Df", minimum=0, maximum=999999)
    if df == 0:
        raise InputError("JRSNAP: Dfは正値が必要です")
    layers = at(foundation, "layers")
    if (not isinstance(layers, list) or len(layers) != 2 or
            not all(isinstance(layer, Mapping) for layer in layers) or
            [layer.get("name") for layer in layers] != ["表層", "支持層"]):
        raise InputError("JRSNAP: 地盤は表層1層＋支持層1層だけに対応します")
    surface, support = layers
    thickness = number(at(surface, "thickness"), "0500.layers[0].thickness", minimum=0)
    difference = abs(df - thickness)
    if difference > GEOMETRY_TOLERANCE:
        raise InputError("JRSNAP: Dfと0500表層厚の差は1e-9 m以下が必要です")
    water = number(at(geometry, "hw2"), f"{stage}.input.geometry.hw2")
    if not 0 < water < df:
        raise InputError("JRSNAP: 平水位hw2は0 < hw2 < Dfが必要です（端点は未対応）")
    parsed = parse_input(raw)
    raw_layers = [layer.to_dict() for layer in parsed.layers]
    comparable_layers = deepcopy(list(layers))
    # The declared geometry tolerance also applies to the equivalent surface
    # thickness in the raw-derived snapshot; other layer values stay exact.
    if abs(raw_layers[0]["thickness"] - comparable_layers[0]["thickness"]) <= GEOMETRY_TOLERANCE:
        comparable_layers[0]["thickness"] = raw_layers[0]["thickness"]
    if raw_layers != comparable_layers or at(foundation, "support_layer") != support:
        raise InputError("JRSNAP: raw地盤と0500.layers/support_layerの入力世代が一致しません")
    # The hash is the caller's byte identity.  Also verify every 0500 quantity
    # consumed here, so a relabelled/stale result cannot supply different springs.
    fresh_foundation = calculate_foundation(parsed)
    for path in ("foundation.B", "foundation.L", "short_term.Ks", "short_term.Kv", "short_term.kv"):
        if at(foundation, path) != at(fresh_foundation, path):
            raise InputError(f"JRSNAP: rawからの0500.{path}と計算スナップショットが一致しません")
    raw_geometry = asdict(parse_reaction_input(raw).geometry)
    for name in ("df1", "df2", "h5", "h6", "hw2"):
        if raw_geometry[name] != geometry[name]:
            raise InputError(f"JRSNAP: rawと{stage}.input.geometry.{name}が一致しません")
    if support.get("soil_type") not in ("砂質土", "砂礫"):
        raise InputError("JRSNAP: 支持層は砂質土または砂礫だけに対応します")
    cohesion_source = number(at(support, "compressive_strength"),
                             "0500.support_layer.compressive_strength", minimum=0)
    if cohesion_source != 0:
        raise InputError("JRSNAP: 支持層の粘着力c=0となる一軸圧縮強度0だけに対応します")
    wet = number(at(surface, "unit_weight_wet"), "表層.unit_weight_wet", minimum=0)
    submerged = number(at(surface, "unit_weight_submerged"),
                       "表層.unit_weight_submerged", minimum=0)
    gamma1 = number(at(support, "unit_weight_submerged"),
                    "支持層.unit_weight_submerged", minimum=0, maximum=999999)
    phi = number(at(support, "friction_angle"), "支持層.friction_angle", minimum=25, maximum=89.999999)
    if min(wet, submerged, gamma1) <= 0:
        raise InputError("JRSNAP: 表層・支持層の有効単位体積重量は正値が必要です")
    gamma2_raw = number(((df - water) * wet + water * submerged) / df, "GAM2.raw")
    gamma2 = excel_round(gamma2_raw, 1)
    springs = {key: number(at(foundation, f"short_term.{key}"), f"0500.short_term.{key}", minimum=0)
               for key in ("Ks", "Kv", "kv")}
    if min(springs.values()) <= 0:
        raise InputError("JRSNAP: 短期Ks/Kv/kvは正値が必要です")
    dimensions = {key: number(at(foundation, f"foundation.{key}"), f"0500.foundation.{key}",
                              minimum=0, maximum=999999) for key in ("B", "L")}
    if min(dimensions.values()) <= 0:
        raise InputError("JRSNAP: 基礎B/Lは正値が必要です")
    if direction == "transverse":
        dimensions = {"B": dimensions["L"], "L": dimensions["B"]}
    return {
        **dimensions, **springs, "Df": df, "gamma1": gamma1, "gamma2": gamma2,
        "phi": phi, "cohesion": 0, "soil_type": 1,
        "provenance": {
            "formula": "((Df-hw2)*gamma_wet+hw2*gamma_submerged)/Df",
            "df_geometry_m": df, "df_surface_m": thickness,
            "df_difference_m": difference, "tolerance_m": GEOMETRY_TOLERANCE,
            "cover_left_m": df1, "cover_right_m": df2, "cover_difference_m": cover_difference,
            "normal_water_m": water, "wet_segment_m": df - water,
            "submerged_segment_m": water, "surface_gamma_wet": wet,
            "surface_gamma_submerged": submerged, "gamma2_raw": gamma2_raw,
            "gamma2_adopted": gamma2, "rounding": "Excel ROUND, 1 decimal",
            "sources": {"Df": f"{stage}.input.geometry.h6+h5+min(df1,df2);0500.layers[0].thickness",
                        "gamma2": f"0500.layers[0].unit_weight_wet/unit_weight_submerged;{stage}.input.geometry.hw2",
                        "gamma1": "0500.support_layer.unit_weight_submerged",
                        "phi": "0500.support_layer.friction_angle",
                        "springs": "0500.short_term.Ks/Kv/kv",
                        "dimensions": ("B=0500.foundation.L;L=0500.foundation.B" if direction == "transverse"
                                       else "0500.foundation.B/L")},
            "scope": "two_layers;level_cover;0<hw2<Df;sandy_support;c=0",
        },
    }
