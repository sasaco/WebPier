"""Physical 0620 actions, with separate application points and usage resolution.

No source-workbook cells or selected-track fallback enter this module. Train
rates retain their signs and totals; a double-track reaction is never distributed
for a second time. Impact keeps the upstream usage-specific pier reduction.
"""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from .calculator import vba_single
from .inputs import InputError
from .moving_load import search_reactions
from .reaction_inputs import ReactionInput, SNOW_LOAD_CASES
from .reaction_math import excel_round as R


TRACK_KEYS = {"up": (1, "L2"), "down": (0, "L1"), "double": (None, "L1+L2")}


def _point(frame: dict, anchor: str, *, N=0.0, H=0.0, M=0.0) -> dict:
    return {"anchor": anchor, "node_id": frame["load_anchors"][anchor]["node_id"],
            "N": N, "H": H, "M": M}


def _line(frame: dict, *, qN=0.0, qH=0.0) -> dict:
    return {"anchor": "column_line_load", **deepcopy(frame["load_anchors"]["column_line_load"]),
            "qN": qN, "qH": qH, "unit": "kN/m"}


def _action(frame: dict, *, anchor="cap_top", N=0.0, H=0.0, M=0.0,
            rows=None, points=None, line_loads=None, details=None, provenance=None) -> dict:
    return {"points": points if points is not None else [_point(frame, anchor, N=N, H=H, M=M)],
            "line_loads": line_loads or [], "rows": rows or [],
            "table_totals": {"anchor": anchor, "N": N, "H": H, "M": M},
            "details": details or {}, "provenance": provenance or {},
            "units": {"N": "kN", "H": "kN", "M": "kN m", "arm": "m"}}


def _arm(bearing, force: float, path: str) -> float:
    if bearing.position is None:
        if force != 0:
            raise InputError(f"{path}.position: 荷重がある支承の位置が必要です")
        return 0.0
    return bearing.position


def _row(side, index, force, arm, *, label=None, bearing_position=None, **extra) -> dict:
    raw_moment = force * arm
    return {"side": side, "bearing": index, "label": label or f"{side} G{index}",
            "bearing_position": bearing_position, "active": side is None or bearing_position is not None,
            "arm": arm, "raw_N": force, "raw_M": raw_moment,
            "N": R(force, 2), "H": 0.0, "M": R(raw_moment, 2), **extra}


def _vertical_table(frame: dict, rows: list, **kwargs) -> dict:
    # The reference aggregates the unrounded force but the printed row moments.
    return _action(frame, rows=rows, N=R(sum(row["raw_N"] for row in rows), 2),
                   M=R(sum(row["M"] for row in rows), 2), **kwargs)


def _bearings(inputs: ReactionInput):
    return (("B", "RB", inputs.dead.b), ("C", "RC", inputs.dead.c))


def _rates(bearings, track: str) -> list[float]:
    index = TRACK_KEYS[track][0]
    return [bearing.factors[0] + bearing.factors[1] if index is None else bearing.factors[index]
            for bearing in bearings]


def train_action(inputs: ReactionInput, reactions: dict, frame: dict, track: str,
                 effective_factor: float = 1.0) -> dict:
    rows = []
    for side, support, bearings in _bearings(inputs):
        raw = reactions["train"]["raw_reactions"][support]
        for index, (bearing, rate) in enumerate(zip(bearings, _rates(bearings, track)), 1):
            force = raw * effective_factor * rate
            arm = _arm(bearing, force, f"0620.input.dead.{side}[{index}]")
            rows.append(_row(side, index, force, arm, factor=rate, upstream_N=raw,
                             bearing_position=bearing.position,
                             source_track=TRACK_KEYS[track][1]))
    return _vertical_table(frame, rows, details={"track": track, "effective_factor": effective_factor},
                           provenance={"source": "0600.train.raw_reactions", "factor_applications": 1,
                                       "remaining_multiplier": 1})


def impact_action(inputs: ReactionInput, reactions: dict, frame: dict, track: str,
                  usage: str, effective_factor: float) -> dict:
    rows, sides = [], []
    track_group = "double" if track == "double" else "single"
    for side, support, bearings in _bearings(inputs):
        rates = _rates(bearings, track)
        rate_sum = sum(rates)
        raw = reactions["train"]["raw_reactions"][support]
        cp = reactions["train"]["pier"][usage][track_group][support]["coefficient"]
        total_train = raw * effective_factor * rate_sum
        total_impact = vba_single(R(total_train * cp, 1))
        raw_forces = [raw * effective_factor * cp * rate for rate in rates]
        raw_impact_total = math.fsum(raw_forces)
        residual = total_impact - raw_impact_total
        absolute_rate_sum = math.fsum(abs(rate) for rate in rates)
        # Keep the raw couple even when positive and negative rates nearly
        # cancel. Redistribute only the bounded rounding residual; division by
        # the signed sum would erase or amplify the whole couple. For rates of
        # one sign this is algebraically the original total * rate / rate_sum.
        corrections = [residual * abs(rate) / absolute_rate_sum if absolute_rate_sum else 0.0
                       for rate in rates]
        sides.append({"side": side, "support": support, "raw_reaction": raw,
                      "rate_sum": rate_sum, "train_total": total_train,
                      "impact_coefficient": cp, "impact_total": total_impact,
                      "raw_impact_total": raw_impact_total, "rounding_residual": residual,
                      "absolute_rate_sum": absolute_rate_sum,
                      "distribution_policy": "raw_force_plus_absolute_rate_rounding_residual",
                      "zero_sum_signed_rates": rate_sum == 0 and any(rates),
                      "source": f"0600.train.pier.{usage}.{track_group}.{support}.coefficient"})
        for index, (bearing, rate, unrounded, correction) in enumerate(
                zip(bearings, rates, raw_forces, corrections, strict=True), 1):
            force = unrounded + correction
            arm = _arm(bearing, force, f"0620.input.dead.{side}[{index}]")
            rows.append(_row(side, index, force, arm, factor=rate, upstream_N=raw,
                             bearing_position=bearing.position,
                             unrounded_impact=unrounded, rounding_correction=correction,
                             impact_coefficient=cp, source_track=TRACK_KEYS[track][1]))
    return _vertical_table(frame, rows,
                           details={"track": track, "usage": usage, "effective_factor": effective_factor,
                                    "sides": sides},
                           provenance={"source": "0600.train.pier", "pier_reduction_preserved": True,
                                       "service_075_already_in_coefficient": usage == "service",
                                       "rounding": "side total 0.1 kN then Single; raw bearing forces plus absolute-rate weighted rounding residual",
                                       "remaining_multiplier": 1})


def _dead_actions(inputs: ReactionInput, reactions: dict, frame: dict) -> dict:
    g = inputs.geometry
    handoff = reactions["macro_handoff_single"]
    result = {}
    for field, key in (("d1", "dead_fixed"), ("d2", "dead_additional")):
        rows = []
        for side, _, bearings in _bearings(inputs):
            for index, bearing in enumerate(bearings, 1):
                force = getattr(bearing, field)
                rows.append(_row(side, index, force, _arm(bearing, force, f"0620.input.dead.{side}[{index}]"),
                                 bearing_position=bearing.position))
        details = {}
        lines = []
        if field == "d1":
            for component, label in (("桁受け", "桁受け"), ("はり", "はり・ハンチ等価荷重")):
                load = handoff[component]
                rows.append(_row(None, None, load["N"], load["xC"], label=label))
            intensity = R(g.w6 * g.b6 * g.unit_weight_body, 2)
            overlap_height = g.h2 + g.h3
            gross = sum(row["raw_N"] for row in rows)
            top_n = R(gross - intensity * overlap_height, 2)
            component = handoff["フーチング"]
            lines = [_line(frame, qN=intensity)]
            details = {"column_intensity": intensity, "overlap_height": overlap_height,
                       "overlap_deduction": intensity * overlap_height,
                       "gross_top_N": gross, "beam_N": handoff["はり"]["N"],
                       "pedestal_N": handoff["桁受け"]["N"]}
        else:
            top_n = R(sum(row["raw_N"] for row in rows), 2)
            component = handoff["上載土"]
        top_m = R(sum(row["M"] for row in rows), 2)
        foundation_m = R(component["N"] * component["xC"], 2)
        points = [_point(frame, "cap_top", N=top_n, M=top_m),
                  _point(frame, "footing_centroid", N=component["N"], M=foundation_m)]
        result[key] = _action(frame, N=top_n, M=top_m, rows=rows, points=points,
                              line_loads=lines, details=details,
                              provenance={"source": "input.dead + 0600.macro_handoff_single"})
    for condition, component in (("high", "高水位"), ("normal", "平水位"), ("low", "低水位")):
        load = handoff[component]
        result[f"buoyancy_{condition}"] = _action(
            frame, anchor="footing_centroid", N=load["N"], M=R(load["N"] * load["xC"], 2),
            details={"water_level": getattr(g, {"high": "hw1", "normal": "hw2", "low": "hw3"}[condition])},
            provenance={"source": f"0600.macro_handoff_single.{component}"})
    return result


def _snow_actions(inputs: ReactionInput, frame: dict) -> dict:
    result = {}
    for slot, years in enumerate((2, 10, 30)):
        rows = []
        for side, _, bearings in _bearings(inputs):
            snow = getattr(inputs.snow, side.lower())
            for index, (bearing, values) in enumerate(zip(bearings, snow), 1):
                force = values[slot]
                rows.append(_row(side, index, force, _arm(bearing, force, f"0620.input.snow.{side}[{index}]"),
                                 bearing_position=bearing.position))
        result[f"snow_{years}_year"] = _vertical_table(
            frame, rows, details={"return_period_years": years},
            provenance={"source": f"input.snow.{SNOW_LOAD_CASES[slot][0]}"})
    return result


def _lateral_action(inputs: ReactionInput, frame: dict) -> dict:
    vehicle = inputs.train
    lengths = tuple(value for span in (inputs.spans.b, inputs.spans.c)
                    for value in (span.l1, span.span, span.l2))
    lateral_length = vba_single(vba_single(vba_single(vehicle.a1) + vba_single(vehicle.a2)) * 2)
    axle = R(0.2 * vehicle.axle_load, 2)
    moving = search_reactions(lengths, 1, lateral_length, vehicle.a1, vehicle.a2, axle)
    rows = []
    for side, span, raw in zip(("B", "C"), (inputs.spans.b, inputs.spans.c), moving.reactions[1:3]):
        height = span.h1 + span.h2 + span.h3
        force = R(raw, 2)
        rows.append({"side": side, "bearing": None, "label": side, "arm": height,
                     "N": 0.0, "H": force, "M": R(force * height, 2), "raw_H": raw,
                     "raw_M": force * height})
    return _action(frame, H=R(sum(row["H"] for row in rows), 2),
                   M=R(sum(row["raw_M"] for row in rows), 2), rows=rows,
                   details={"axle_load": axle, "applied_factor": 1.0},
                   provenance={"source": "moving_load.search_reactions(0.2P)",
                               "upstream_rho_not_reapplied": True, "remaining_multiplier": 1})


def _wind_actions(inputs: ReactionInput, reactions: dict, frame: dict) -> dict:
    result = {}
    handoff = reactions["macro_handoff_single"]
    for index, name, pressure in ((4, "with_train", 1.5), (5, "without_train", 3.0)):
        rows = []
        for side in ("B", "C"):
            force = handoff["直角荷重強度"][index][f"R{side}"]
            height = handoff["直角荷重位置"][index][f"R{side}"]
            rows.append({"side": side, "bearing": None, "label": side, "arm": height,
                         "N": 0.0, "H": force, "M": force * height})
        result[f"wind_{name}"] = _action(
            frame, H=sum(row["H"] for row in rows), M=sum(row["M"] for row in rows), rows=rows,
            line_loads=[_line(frame, qH=pressure * inputs.geometry.b6)],
            details={"pressure": pressure, "pressure_unit": "kN/m2"},
            provenance={"source": "0600.macro_handoff_single.直角荷重", "adjusted_input_preserved": True})
    return result


def build_transverse_actions(inputs: ReactionInput, reactions: dict, *, frame: dict) -> dict[str, dict]:
    actions = {**_dead_actions(inputs, reactions, frame), **_snow_actions(inputs, frame)}
    for track in TRACK_KEYS:
        actions[f"train_{track}"] = train_action(inputs, reactions, frame, track)
        actions[f"impact_{track}"] = impact_action(inputs, reactions, frame, track, "ultimate", 1.0)
    actions["vehicle_lateral"] = _lateral_action(inputs, frame)
    actions.update(_wind_actions(inputs, reactions, frame))
    return actions


def _scale(action: dict, factor: float, sign: int) -> dict:
    scaled = deepcopy(action)
    if "applied_factor" in scaled["details"]:
        scaled["details"]["applied_factor"] *= factor
    for point in [*scaled["points"], scaled["table_totals"], *scaled["rows"]]:
        for key in ("N", "H", "M", "raw_N", "raw_H", "raw_M"):
            if key in point:
                point[key] *= factor * (sign if key in ("H", "M", "raw_H", "raw_M") else 1)
    for line in scaled["line_loads"]:
        line["qN"] *= factor
        line["qH"] *= factor * sign
    return scaled


def resolve_transverse_combinations(inputs: ReactionInput, reactions: dict, frame: dict,
                                    actions: dict, case_model: dict) -> list[dict]:
    basics = {row["id"]: row for row in case_model["basic_cases"]}
    defines = case_model["define_cases"]
    combinations = deepcopy(case_model["combinations"])
    for combination in combinations:
        usage = combination["usage"]
        components = []
        for define, nominal in zip(defines, combination["coefficients"], strict=True):
            if nominal == 0:
                continue
            candidates = []
            for signed in define["signed_basic_case_ids"]:
                basic = basics[abs(signed)]
                key, sign = basic["key"], -1 if signed < 0 else 1
                effective = nominal
                if key.startswith("train_"):
                    loads = train_action(inputs, reactions, frame, key.removeprefix("train_"), effective)
                    source = "0600.train.raw_reactions"
                elif key.startswith("impact_"):
                    effective = inputs.train.factors_service if usage == "service" else nominal
                    loads = impact_action(inputs, reactions, frame, key.removeprefix("impact_"), usage, effective)
                    source = "0600.train.raw_reactions + 0600.train.pier.coefficient"
                else:
                    loads = _scale(actions[key], effective, sign)
                    source = actions[key]["provenance"]["source"]
                candidate = {"basic_case_id": basic["id"], "signed_basic_case_id": signed,
                             "action_key": key, "loads": loads,
                             "coefficient_trace": {"usage": usage, "nominal_coefficient": nominal,
                                                   "effective_factor": effective, "applied_factor": effective,
                                                   "factor_applications": 1, "remaining_multiplier": 1,
                                                   "source": source}}
                if key.endswith(("_up", "_down")):
                    candidate.update(direction=key.rsplit("_", 1)[1], compatibility_group="single_track")
                candidates.append(candidate)
            components.append({"define_case_id": define["id"], "symbol": define["symbol"],
                               "nominal_coefficient": nominal, "candidates": candidates})
        combination["resolved_components"] = components
    return combinations
