"""Physical 0610 actions and usage-aware resolution of nominal combinations.

The source table describes twenty action families. In particular, I1/I2 have
different service and ultimate pier coefficients; no common impact vector can
be multiplied by the nominal table to obtain the adopted combinations.
"""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from .calculator import vba_single
from .inputs import InputError
from .reaction_inputs import ReactionInput
from .reaction_math import excel_round as R


_SNOW = {"s2": "雪荷重_2年確率", "s10": "雪荷重_10年確率", "s30": "雪荷重_30年確率"}
# Canonical ID, detailed 0600 family, adopted Single packet, zero-based row.
_HORIZONTAL_SOURCES = (
    (13, "longitudinal", "線路荷重強度", 0),
    (14, "longitudinal", "線路荷重強度", 1),
    (15, "longitudinal", "線路荷重強度", 4),
    (16, "longitudinal", "線路荷重強度", 5),
    (17, "longitudinal", "線路荷重強度", 6),
    (18, "longitudinal_snow_cases", "線路雪荷重強度", 0),
    (19, "longitudinal", "線路荷重強度", 7),
    (20, "longitudinal_snow_cases", "線路雪荷重強度", 1),
)
_MAXIMUM_COMBINATIONS = {"body_failure_train_max", "foundation_stability_train_max"}


def _path(parts: tuple) -> str:
    return "0600." + ".".join(map(str, parts))


def _required(root: dict, *parts: str | int) -> Any:
    value = root
    for part in parts:
        try:
            value = value[part]
        except (KeyError, IndexError, TypeError) as exc:
            raise InputError(f"{_path(parts)}: 必須の上流値がありません") from exc
    return value


def _number(root: dict, *parts: str | int) -> float:
    value = _required(root, *parts)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputError(f"{_path(parts)}: 有限の数値が必要です")
    return value


def _object(root: dict, *parts: str | int) -> dict:
    value = _required(root, *parts)
    if not isinstance(value, dict):
        raise InputError(f"{_path(parts)}: 上流の詳細オブジェクトが必要です")
    return value


def validate_action_upstream(reactions: dict) -> None:
    """Validate adopted data before the common historical equations run.

    Audit-only packets are also required by those equations, but are never used
    to reconstruct the raw canonical train or usage-specific impact forces.
    """
    for side in ("B", "C"):
        _number(reactions, "train", "raw_reactions", "R" + side)
        _number(reactions, "dead_loads", "track_totals", side)
        for group in ("service", "ultimate"):
            for track in ("single", "double"):
                _number(reactions, "train", "pier", group, track, "R" + side, "coefficient")
        for snow in _SNOW.values():
            _number(reactions, "snow_loads", "points", side, snow)
        for kind in ("D1", "D2"):
            _number(reactions, "dead_loads", "points", side, kind)
    for _, family, packet, index in _HORIZONTAL_SOURCES:
        _object(reactions, family, index, "combination")
        for side in ("B", "C"):
            _object(reactions, family, index, side)
            _number(reactions, "macro_handoff_single", packet, index, "R" + side)
    # The common audit also includes the old earthquake and braking-only rows.
    for index in range(10):
        for support in ("RB", "RC"):
            _number(reactions, "macro_handoff_single", "線路荷重強度", index, support)
    for component in ("フーチング", "桁受け", "はり", "上載土", "高水位", "平水位", "低水位"):
        for field in ("N", "xL"):
            _number(reactions, "macro_handoff_single", component, field)
    for component, field in (("柱", "xL"), ("フーチング", "hG"), ("桁受け", "hG")):
        _number(reactions, "macro_handoff_single", component, field)
    for kind, group, track in (("列車荷重", "安全性", "複線"), ("列車荷重", "使用性", "単線"),
                               ("衝撃荷重", "安全性", "複線"), ("衝撃荷重", "使用性", "単線")):
        for support in ("RB", "RC"):
            _number(reactions, "macro_handoff_single", kind, group, track, support)
    for support in ("RB", "RC"):
        _number(reactions, "macro_handoff_single", "地震列車", support)


def _support_loads(inputs: ReactionInput, forces: dict[str, float]) -> dict:
    loads = {side: {"N": forces[side], "arm": arm, "M": R(forces[side] * arm, 2)}
             for side, arm in (("B", -inputs.spans.b.f), ("C", inputs.spans.c.f))}
    loads.update(N=loads["B"]["N"] + loads["C"]["N"], M=loads["B"]["M"] + loads["C"]["M"])
    return loads


def _train_forces(reactions: dict, track: str, factor: float) -> dict[str, float]:
    # Preserve operation order and Double precision. Do not recover raw forces
    # by dividing an already-rounded load by rho (which can legitimately be 0).
    return {side: (reactions["train"]["raw_reactions"]["R" + side] * factor)
            * (1 if track == "single" else reactions["dead_loads"]["track_totals"][side])
            for side in ("B", "C")}


def _usage_factor(model: dict, usage: str) -> float:
    key = {"service": "service_factor", "ultimate": "ultimate_effective",
           "maximum": "maximum_train_effective"}[usage]
    return model["factors"][key]


def _impact(inputs: ReactionInput, reactions: dict, track: str, usage: str, factor: float) -> tuple[dict, dict]:
    group = "service" if usage == "service" else "ultimate"
    train = _train_forces(reactions, track, factor)
    coefficients = {side: reactions["train"]["pier"][group][track]["R" + side]["coefficient"]
                    for side in ("B", "C")}
    unrounded = {side: train[side] * coefficients[side] for side in ("B", "C")}
    rounded = {side: R(unrounded[side], 1) for side in ("B", "C")}
    adopted = {side: vba_single(rounded[side]) for side in ("B", "C")}
    resolution = {
        "usage": usage, "track": track, "effective_train_factor": factor,
        "pier_coefficients": coefficients,
        "coefficient_source_paths": {
            side: f"0600.train.pier.{group}.{track}.R{side}.coefficient" for side in ("B", "C")},
        "coefficient_policy": "upstream_usage_coefficient_including_pier_reduction",
        "service_factor_already_in_coefficient": 0.75 if group == "service" else 1.0,
        "maximum_pier_reduction_recomputed": False,
        "support_calculation": {side: {"train": train[side], "before_rounding": unrounded[side],
                                       "rounded_0_1_kN": rounded[side], "adopted_single": adopted[side]}
                                for side in ("B", "C")},
        "rounding": "支点I=Single(ROUND(L採用×c_p,1))、支点M=ROUND(I×腕,2)、合計は追加丸めなし",
    }
    return _support_loads(inputs, adopted), resolution


def _scale_vertical(loads: dict, factor: float) -> dict:
    scaled = deepcopy(loads)
    for key, value in scaled.items():
        if key in ("N", "M", "intensity"):
            scaled[key] = value * factor
        elif isinstance(value, dict) and key not in ("source_cells", "upstream_details"):
            scaled[key] = _scale_vertical(value, factor)
    return scaled


def _scale_horizontal(loads: dict, factor: float) -> dict:
    scaled = deepcopy(loads)
    for key in ("B", "C", "total"):
        scaled[key] *= factor
    return scaled


def _combination_usage(combination: dict) -> str:
    key = combination["key"]
    if key in _MAXIMUM_COMBINATIONS:
        return "maximum"
    if key.startswith(("body_service_", "foundation_support_")):
        return "service"
    return "ultimate"


def _resolve_combinations(inputs: ReactionInput, reactions: dict, model: dict, basics: list[dict]) -> list[dict]:
    combinations = deepcopy(model["combinations"])
    for combination in combinations:
        usage = _combination_usage(combination)
        components = []
        for basic, nominal in zip(basics, combination["coefficients"], strict=True):
            identifier = basic["id"]
            if identifier in (9, 10):
                track = basic["track"]
                loads = _support_loads(inputs, _train_forces(reactions, track, nominal))
                residual = 1 if nominal else 0
                resolution = {"usage": usage, "track": track, "effective_train_factor": nominal,
                              "precision": "Double", "source_path": "0600.train.raw_reactions",
                              "track_source_path": "0600.dead_loads.track_totals" if track == "double" else None,
                              "included": nominal != 0}
            elif identifier in (11, 12):
                factor = _usage_factor(model, usage)
                loads, resolution = _impact(inputs, reactions, basic["track"], usage, factor)
                if nominal == 0:
                    loads = _scale_vertical(loads, 0)
                residual = 1 if nominal else 0
                resolution["included"] = nominal != 0
            else:
                horizontal = basic["action_domain"] == "horizontal"
                loads = (_scale_horizontal if horizontal else _scale_vertical)(basic["loads"], nominal)
                residual = 1 if nominal else 0
                resolution = {"policy": "physical_components_only", "applied_factor": nominal}
            components.append({"basic_case_id": identifier, "nominal_factor": nominal,
                               "residual_factor": residual, "loads": loads, "resolution": resolution})
        combination["resolved_components"] = components
        signs = [1, -1] if any(row["basic_case_id"] >= 13 and row["nominal_factor"] != 0
                              for row in components) else [1]
        combination["variants"] = []
        for sign in signs:
            signed = deepcopy(components)
            if sign < 0:
                for row in signed:
                    if row["basic_case_id"] >= 13:
                        row["loads"] = _scale_horizontal(row["loads"], sign)
            combination["variants"].append({"horizontal_sign": sign, "resolved_components": signed})
    return combinations


def build_canonical_actions(inputs: ReactionInput, reactions: dict, audit: dict, model: dict) -> dict:
    """Build fresh physical actions, then resolve each nominal combination."""
    vertical = {key: deepcopy(audit["vertical"][key]) for key in ("fixed", "additional", "water")}
    vertical["snow"] = {
        key: _support_loads(inputs, {side: reactions["snow_loads"]["points"][side][source]
                                    for side in ("B", "C")}) for key, source in _SNOW.items()}
    vertical["train"] = {track: _support_loads(inputs, _train_forces(reactions, track, 1))
                         for track in ("single", "double")}
    vertical["impact"] = {}
    impact_metadata = {}
    for usage in ("service", "ultimate", "maximum"):
        vertical["impact"][usage], impact_metadata[usage] = {}, {}
        for track in ("single", "double"):
            loads, metadata = _impact(inputs, reactions, track, usage, _usage_factor(model, usage))
            vertical["impact"][usage][track] = loads
            impact_metadata[usage][track] = metadata
    horizontal = []
    for identifier, family, packet, index in _HORIZONTAL_SOURCES:
        basic = model["basic_cases"][identifier - 1]
        force = reactions["macro_handoff_single"][packet][index]
        horizontal.append({
            "id": identifier, "key": basic["key"], "label": basic["label"],
            "B": force["RB"], "C": force["RC"], "total": force["RB"] + force["RC"],
            "precision": "VBA Single", "source_path": f"0600.macro_handoff_single.{packet}[{index}]",
            "upstream_source_path": f"0600.{family}[{index}]",
            "upstream_details": deepcopy(reactions[family][index]),
        })
    groups = [vertical["fixed"], vertical["additional"],
              *[vertical["water"][key] for key in ("high", "normal", "low")],
              *[vertical["snow"][key] for key in _SNOW],
              *[vertical["train"][track] for track in ("single", "double")],
              *[vertical["impact"]["ultimate"][track] for track in ("single", "double")], *horizontal]
    basics = deepcopy(model["basic_cases"])
    for basic, loads in zip(basics, groups, strict=True):
        basic["loads"] = deepcopy(loads)
        if basic["id"] in (11, 12):
            track = basic["track"]
            basic["usage_loads"] = {usage: deepcopy(vertical["impact"][usage][track]) for usage in vertical["impact"]}
            basic["usage_resolution"] = {usage: deepcopy(impact_metadata[usage][track]) for usage in vertical["impact"]}
            basic["load_policy"] = "usage_family; representative loads are ultimate, not a universal multiplier vector"
    return {"vertical": vertical, "horizontal": horizontal, "basic_cases": basics,
            "combinations": _resolve_combinations(inputs, reactions, model, basics)}


def reference_formulas(audit: dict) -> dict:
    """Retain physical reference equations without publishing D2 omega4–7."""
    cells = audit["cells"]["荷重計算"]
    result = {"fixed": {}, "water": {}}
    for group, name, row in (("fixed", "omega2", 23), ("fixed", "omega3", 24),
                             ("water", "high", 64), ("water", "normal", 69), ("water", "low", 74)):
        result[group][name] = {"source_cell": f"AB{row}", "value": cells[f"AB{row}"],
                              "height": cells[f"J{row}"], "width": cells[f"N{row}"],
                              "unit_weight": cells[f"R{row}"], "formula": "ROUND(height*width*unit_weight,2)",
                              "source_scope": "legacy_physical_reference; not a nominal coefficient cell"}
    return result


def calculation_details(audit: dict) -> dict:
    """Expose the existing D1 evaluation without recomputing or decomposing it."""
    cells = audit["cells"]["荷重計算"]
    return {"fixed": {
        "components": {name: {"N": cells[f"M{row}"], "arm": cells[f"T{row}"], "M": cells[f"Y{row}"]}
                       for name, row in (("B", 29), ("C", 30), ("pedestal", 31), ("beam", 32))},
        "sum_N": cells["M33"], "sum_M": cells["Y33"],
        "column_deduction": {"intensity": cells["R35"], "length": cells["W35"]},
        "adopted_top": {"N": cells["AB35"], "M": cells["AB36"]},
    }}
