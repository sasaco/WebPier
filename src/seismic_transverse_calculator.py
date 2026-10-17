"""0720 seismic actions from the same-run input, direct 0600 and canonical 0620.

The detached result defines physical actions and report geometry, not restraints,
constitutive laws, response analysis, or capacity checks.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import json
import math
import re
from typing import Any

from .inputs import InputError
from .reaction_inputs import ReactionInput
from .reaction_math import excel_round as R
from .seismic_frame import build_seismic_frame


CASE_MODEL_VERSION = "seismic-transverse-example2-v1"
FRAME_SPEC_VERSION = "seismic-transverse-upper-column-base-micro-v1"
_FIXED_CASES = ((1, "dead_fixed", "固定死荷重"), (2, "dead_additional", "付加死荷重"),
                (4, "buoyancy_normal", "浮力 平水位"), (6, "snow_2_year", "雪荷重 2年確率"))


def _at(value: Any, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(value, Mapping) or key not in value:
            raise InputError(f"0720: {path}が必要です")
        value = value[key]
    return value


def _number(value: Any, path: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"0720: {path}には有限の数値が必要です")
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise InputError(f"0720: {path}は数値範囲を超えています") from exc
    if not finite:
        raise InputError(f"0720: {path}には有限の数値が必要です")
    return value


def _finite(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _finite(item, f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        _number(value, path)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InputError(f"0720: {path}にはオブジェクトが必要です")
    return value


def _rows(value: Any, path: str) -> list | tuple:
    if not isinstance(value, (list, tuple)):
        raise InputError(f"0720: {path}には配列が必要です")
    return value


def _identity(value: Any) -> str:
    """JSON identity accepts in-memory tuples and decoded lists equally."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _same_number(actual: Any, expected: float, path: str) -> None:
    actual = _number(actual, path)
    if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-10):
        raise InputError(f"0720: {path}と現在入力の式が一致しません")


def _validate_sources(inputs: ReactionInput, reactions: Mapping[str, Any],
                      transverse: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    if not isinstance(inputs, ReactionInput):
        raise InputError("0720: ReactionInputが必要です")
    snapshot = asdict(inputs)
    _finite(snapshot, "input")
    shas = []
    for source, stage, version in ((reactions, "0600", 1), (transverse, "0620", 2)):
        source = _mapping(source, stage)
        if type(source.get("schema_version")) is not int or source["schema_version"] != version or source.get("stage") != stage:
            raise InputError(f"0720: schema_version={version}、stage={stage}の正規結果が必要です")
        source_input = _mapping(_at(source, "input"), f"{stage}.input")
        _finite(source_input, f"{stage}.input")
        if _identity(source_input) != _identity(snapshot):
            raise InputError(f"0720: {stage}.inputと現在入力のスナップショットが一致しません")
        provenance = _mapping(source.get("provenance", {}), f"{stage}.provenance")
        if "input_sha256" in provenance:
            sha = provenance["input_sha256"]
            if not isinstance(sha, str) or re.fullmatch(r"[0-9a-fA-F]{64}", sha) is None:
                raise InputError(f"0720: {stage}.provenance.input_sha256が不正です")
            shas.append(sha.lower())
    if len(set(shas)) > 1:
        raise InputError("0720: 0600/0620の入力SHAが一致しません")
    return deepcopy(snapshot), shas[0] if shas else None


def _point(frame: Mapping[str, Any], anchor: str, *, N: float = 0., H: float = 0., M: float = 0.) -> dict[str, Any]:
    return {"anchor": anchor, "node_id": frame["node_ids"][anchor], "N": N, "H": H, "M": M}


def _action(frame: Mapping[str, Any], *, rows: list[dict[str, Any]] | None = None,
            N: float = 0., H: float = 0., M: float = 0.,
            details: dict[str, Any] | None = None, provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"points": [_point(frame, "cap_top", N=N, H=H, M=M)], "line_loads": [],
            "rows": rows or [], "table_totals": {"anchor": "cap_top", "N": N, "H": H, "M": M},
            "details": details or {}, "provenance": provenance or {},
            "units": {"N": "kN", "H": "kN", "M": "kN m", "arm": "m"}}


def _remap_reference(value: Any, node_map: Mapping[int, int], member_map: Mapping[int, list[int]],
                     path: str) -> Any:
    """Copy references explicitly, expanding an old H4 member into both pieces."""
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if key in ("node_id", "from_node_id", "to_node_id", "equivalent_node_id"):
                if type(item) is not int or item not in node_map:
                    raise InputError(f"0720: {path}.{key}の節点参照が不正です")
                result[key] = node_map[item]
            elif key == "member_ids":
                ids = _rows(item, f"{path}.{key}")
                if any(type(identifier) is not int or identifier not in member_map for identifier in ids):
                    raise InputError(f"0720: {path}.{key}の部材参照が不正です")
                result[key] = [part for identifier in ids for part in member_map[identifier]]
                if len(set(result[key])) != len(result[key]):
                    raise InputError(f"0720: {path}.{key}の部材参照が重複しています")
            else:
                result[key] = _remap_reference(item, node_map, member_map, f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_remap_reference(item, node_map, member_map, f"{path}[]") for item in value]
    return deepcopy(value)


def _fixed_actions(source: Mapping[str, Any], frame: dict[str, Any], node_map: Mapping[int, int],
                    member_map: Mapping[int, list[int]]) -> dict[str, Any]:
    basics = _rows(_at(source, "basic_cases"), "0620.basic_cases")
    if source.get("case_model_version") != "example2-nonseismic-pier-impact-v1":
        raise InputError("0720: 0620.case_model_versionが一致しません")
    result = {}
    for identifier, key, label in _FIXED_CASES:
        matches = [row for row in basics if isinstance(row, Mapping)
                   and (row.get("id") == identifier or row.get("key") == key)]
        if (len(matches) != 1 or type(matches[0].get("id")) is not int
                or matches[0]["id"] != identifier or matches[0].get("key") != key
                or matches[0].get("label") != label):
            raise InputError(f"0720: 0620.basic_casesの{key}の識別・一意性・意味が一致しません")
        original = _mapping(_at(source, f"actions.{key}"), f"0620.actions.{key}")
        _finite(original, f"0620.actions.{key}")
        if _identity(matches[0].get("loads")) != _identity(original):
            raise InputError(f"0720: 0620.basic_cases.{key}.loadsがactionsと一致しません")
        selected = {name: deepcopy(_at(original, name)) for name in
                    ("points", "line_loads", "rows", "table_totals", "details", "provenance", "units")}
        action = _remap_reference(selected, node_map, member_map, f"actions.{key}")
        for point in _rows(action["points"], f"actions.{key}.points"):
            if point.get("anchor") not in frame["node_ids"] or point.get("node_id") != frame["node_ids"][point["anchor"]]:
                raise InputError(f"0720: actions.{key}.pointsの作用位置が一致しません")
            for field in ("N", "H", "M"):
                _number(point.get(field), f"actions.{key}.points.{field}")
        for line in _rows(action["line_loads"], f"actions.{key}.line_loads"):
            for field in ("qN", "qH"):
                _number(line.get(field), f"actions.{key}.line_loads.{field}")
            anchor = frame["load_anchors"]["column_line_load"]
            if (line.get("anchor") != "column_line_load"
                    or any(line.get(field) != anchor[field] for field in ("from_node_id", "to_node_id"))
                    or set(line.get("member_ids", [])) != set(anchor["member_ids"])):
                raise InputError(f"0720: actions.{key}.line_loadsの作用区間が一致しません")
        for row in _rows(action["rows"], f"actions.{key}.rows"):
            for field in ("N", "H", "M", "raw_N", "raw_M", "arm"):
                _number(row.get(field), f"actions.{key}.rows.{field}")
        for field in ("N", "H", "M"):
            _number(_at(action, f"table_totals.{field}"), f"actions.{key}.table_totals.{field}")
        result[key] = action
    return result


def _train_action(inputs: ReactionInput, reactions: Mapping[str, Any], frame: dict[str, Any],
                   track: str) -> dict[str, Any]:
    slot, source_track = (0, "L1") if track == "down" else (1, "L2")
    rows = []
    for side in ("B", "C"):
        bearings = getattr(inputs.dead, side.lower())
        span = getattr(inputs.spans, side.lower())
        upstream = _number(_at(reactions, f"train.earthquake.R{side}"), f"0600.train.earthquake.R{side}")
        _same_number(upstream, inputs.train.earthquake_load * (span.l1 + span.span + span.l2) / 2,
                     f"0600.train.earthquake.R{side}")
        for index, bearing in enumerate(bearings, 1):
            factor = _number(bearing.factors[slot], f"input.dead.{side}[{index}].{source_track}")
            force = upstream * factor
            if bearing.position is None and force != 0:
                raise InputError(f"0720: input.dead.{side}[{index}].position: 荷重がある支承の位置が必要です")
            arm = 0. if bearing.position is None else _number(bearing.position, f"input.dead.{side}[{index}].position")
            moment = force * arm
            rows.append({"side": side, "bearing": index, "label": f"{side} G{index}",
                         "bearing_position": bearing.position, "active": bearing.position is not None,
                         "arm": arm, "raw_N": force, "raw_M": moment, "N": R(force, 2), "H": 0.,
                         "M": R(moment, 2), "factor": factor, "upstream_N": upstream,
                         "source_track": source_track})
    return _action(frame, rows=rows, N=R(sum(row["raw_N"] for row in rows), 2),
                   M=R(sum(row["M"] for row in rows), 2),
                   details={"track": track, "effective_factor": 1.0},
                   provenance={"source": "0600.train.earthquake", "factor_applications": 1,
                               "remaining_multiplier": 1, "rounding": "N: raw row sum, M: sum of 2-digit row moments"})


def _horizontal(inputs: ReactionInput, reactions: Mapping[str, Any], frame: dict[str, Any],
                *, train: bool) -> dict[str, Any]:
    identifier, label, kh = (8, "地震時 列車荷重", .3) if train else (7, "地震時 桁荷重", 1.)
    matches = [row for row in _rows(_at(reactions, "transverse"), "0600.transverse")
               if isinstance(row, Mapping) and row.get("case") == identifier]
    if len(matches) != 1 or type(matches[0].get("case")) is not int or matches[0].get("label") != label:
        raise InputError(f"0720: 0600.transverse.case{identifier}の識別・一意性・意味が一致しません")
    rows = []
    for side in ("B", "C"):
        span = getattr(inputs.spans, side.lower())
        source = _mapping(_at(matches[0], side), f"0600.transverse.case{identifier}.{side}")
        force, height, moment = (_number(source.get(key), f"0600.transverse.case{identifier}.{side}.{key}")
                                 for key in ("force", "height", "moment"))
        if train:
            reaction = _number(_at(reactions, f"train.earthquake.R{side}"), f"0600.train.earthquake.R{side}")
            raw_force = reaction * kh
            expected_height = span.h1 + span.h2 + span.h3 + inputs.train.height_seismic
            factors = {"earthquake_reaction": reaction, "Kh": kh, "h1": span.h1, "h2": span.h2,
                       "h3": span.h3, "height_seismic": inputs.train.height_seismic}
        else:
            bearings, snow = getattr(inputs.dead, side.lower()), getattr(inputs.snow, side.lower())
            d1, d2, s2 = sum(row.d1 for row in bearings), sum(row.d2 for row in bearings), sum(row[0] for row in snow)
            raw_force = (d1 + d2 + s2) * kh
            expected_height = span.hs
            factors = {"D1": d1, "D2": d2, "S2": s2, "hs": span.hs, "Kh": kh}
        _same_number(force, R(raw_force, 2), f"0600.transverse.case{identifier}.{side}.force")
        _same_number(height, expected_height, f"0600.transverse.case{identifier}.{side}.height")
        _same_number(moment, force * height, f"0600.transverse.case{identifier}.{side}.moment")
        rows.append({"side": side, "label": side, "H": force, "height": height, "arm": height,
                     "M": moment, "raw_H": raw_force, "raw_M": moment,
                     "formula": {"factors": factors, "force_unrounded": raw_force, "force": force,
                                 "moment_unrounded": moment, "moment": R(moment, 2), "rounding_digits": 2}})
    action = _action(frame, rows=rows, H=sum(row["H"] for row in rows), M=sum(row["M"] for row in rows),
                     details={"Kh": kh, "coefficient_applied": True, "remaining_multiplier": 1,
                              "application_role": "cap_top"},
                     provenance={"source": f"0600.transverse.case{identifier}", "precision": "direct binary64; not Single handoff",
                                 "height_policy": "full equivalent moment about cap_top; no second transfer"})
    action["display_totals"] = {field: R(action["table_totals"][field], 2) for field in ("N", "H", "M")}
    return action


def _self_inertia(inputs: ReactionInput, reactions: Mapping[str, Any], frame: dict[str, Any],
                  fixed: Mapping[str, Any]) -> tuple[dict, dict, dict]:
    g, kh = inputs.geometry, 1.
    inertia: dict[str, Any] = {"Kh": kh}
    formulas = {}
    for name, width, depth in (("beam_top", g.b1, g.w1),
                               ("beam_bottom", g.b1-g.b4-g.b5, g.w1-g.w4-g.w5),
                               ("column", g.b6, g.w6)):
        raw = width * depth * g.unit_weight_body * kh
        inertia[name] = R(raw, 2)
        formulas[name] = {"expression": "b*w*unit_weight*Kh", "factors": {"b": width, "w": depth,
                           "unit_weight": g.unit_weight_body, "Kh": kh}, "unrounded": raw,
                           "value": inertia[name], "unit": "kN/m", "rounding_digits": 2}
    pedestal_weight = _number(_at(reactions, "macro_handoff_single.桁受け.N"), "0600.macro_handoff_single.桁受け.N")
    fixed_pedestal = _number(_at(fixed, "details.pedestal_N"), "0620.actions.dead_fixed.details.pedestal_N")
    if pedestal_weight != fixed_pedestal:
        raise InputError("0720: 0600桁受け重量と0620固定死荷重の重量が一致しません")
    pedestal_height = _number(_at(reactions, "macro_handoff_single.桁受け.hG"), "0600.macro_handoff_single.桁受け.hG")
    pedestal_force, pedestal_moment = pedestal_weight * kh, pedestal_weight * kh * pedestal_height
    inertia["pedestal"] = {"H": pedestal_force, "height": pedestal_height, "M": R(pedestal_moment, 2)}
    formulas["pedestal"] = {"expression": "weight*Kh", "moment_expression": "H*height",
        "factors": {"weight": pedestal_weight, "height": pedestal_height, "Kh": kh, "b": g.b3, "w": g.w3, "h": g.h1},
        "unrounded": pedestal_force, "value": pedestal_force, "moment_unrounded": pedestal_moment,
        "moment": inertia["pedestal"]["M"], "unit": "kN", "rounding_digits": 2}
    weight = _number(_at(reactions, "macro_handoff_single.フーチング.N"), "0600.macro_handoff_single.フーチング.N")
    footing_points = [point for point in fixed["points"] if point["anchor"] == "footing_centroid"]
    if len(footing_points) != 1:
        raise InputError("0720: 0620固定死荷重のフーチング重心作用は1件必要です")
    fixed_footing = _number(footing_points[0]["N"], "0620.actions.dead_fixed.footing.N")
    if weight != fixed_footing:
        raise InputError("0720: 0600フーチング重量と0620固定死荷重の重量が一致しません")
    if g.unit_weight_footing <= 0:
        raise InputError("0720: 基礎単位重量は正値が必要です")
    raw = weight / g.unit_weight_footing * (g.unit_weight_footing - g.unit_weight_displaced_soil) * kh
    inertia["footing"] = R(raw, 2)
    formulas["footing"] = {"expression": "weight/unit_weight*(unit_weight-displaced_unit_weight)*Kh",
        "factors": {"weight": weight, "unit_weight": g.unit_weight_footing,
                    "displaced_unit_weight": g.unit_weight_displaced_soil, "Kh": kh},
        "geometry": {"b": g.b7+g.b8+g.b9, "w": g.w7+g.w8+g.w9, "h5": g.h5, "h6": g.h6},
        "unrounded": raw, "value": inertia["footing"], "unit": "kN", "rounding_digits": 2}
    action = _action(frame, details={"Kh": kh, "coefficient_applied": True},
                     provenance={"source": "input.geometry + 0600.macro_handoff_single weights",
                                 "distribution": "H2 constant; H3 linear top-to-bottom; H4 constant including micro segment"})
    action["points"] = [_point(frame, "cap_top", H=pedestal_force, M=inertia["pedestal"]["M"]),
                        _point(frame, "footing_centroid", H=inertia["footing"])]
    action["table_totals"] = {"anchor": "multiple", "N": 0., "H": pedestal_force + inertia["footing"],
                              "M": inertia["pedestal"]["M"], "scope": "point loads only; line loads are separate"}
    nodes = {node["id"]: node for node in frame["nodes"]}
    for member in frame["members"]:
        region = member["region"]
        if region not in ("h2", "h3", "h4", "column_base_micro_member"):
            continue
        top = inertia["beam_top"] if region in ("h2", "h3") else inertia["column"]
        bottom = inertia["beam_bottom"] if region == "h3" else top
        length = nodes[member["node_i"]]["y"] - nodes[member["node_j"]]["y"]
        action["line_loads"].append({"anchor": region, "member_ids": [member["id"]],
            "from_node_id": member["node_i"], "to_node_id": member["node_j"],
            "distribution": "linear" if region == "h3" else "constant",
            "qN": 0., "qH_top": top, "qH_bottom": bottom, "length": length,
            "resultant_H": (top+bottom)/2*length, "unit": "kN/m"})
    return inertia, formulas, action


def _validate_geometry(frame: Mapping[str, Any], geometry: Mapping[str, Any]) -> None:
    nodes = {node["id"]: node for node in frame["nodes"]}
    if len({(node["x"], node["y"]) for node in nodes.values()}) != len(nodes):
        raise InputError("0720: 同座標の節点が統合されていません")
    for role, identifier in frame["node_ids"].items():
        if role not in nodes[identifier]["roles"]:
            raise InputError(f"0720: frame.node_ids.{role}の役割が一致しません")
    adjacency: dict[int, set[int]] = {identifier: set() for identifier in nodes}
    edges = set()
    for member in frame["members"]:
        first, second = member["node_i"], member["node_j"]
        edge = frozenset((first, second))
        if first == second or edge in edges:
            raise InputError("0720: 骨組部材の接続が重複しています")
        edges.add(edge)
        adjacency[first].add(second)
        adjacency[second].add(first)
    visited: set[int] = set()
    pending = [frame["node_ids"]["cap_top"]]
    while pending:
        identifier = pending.pop()
        if identifier not in visited:
            visited.add(identifier)
            pending.extend(adjacency[identifier] - visited)
    if visited != set(nodes):
        raise InputError("0720: 骨組に未接続の節点があります")
    for region in ("h1", "h2", "h3", "h4"):
        regions = (region, "column_base_micro_member") if region == "h4" else (region,)
        selected = [member for member in frame["members"] if member["region"] in regions]
        for member in selected:
            if nodes[member["node_i"]]["x"] != nodes[member["node_j"]]["x"]:
                raise InputError(f"0720: {region}部材は鉛直である必要があります")
            # Canonical H1 runs upward from its base; the distributed H2/H3/H4
            # members must run downward so their end intensities retain meaning.
            if region != "h1" and nodes[member["node_i"]]["y"] <= nodes[member["node_j"]]["y"]:
                raise InputError(f"0720: {region}部材は上端から下端への接続が必要です")
        length = sum(abs(nodes[member["node_i"]]["y"] - nodes[member["node_j"]]["y"])
                     for member in selected)
        _same_number(length, geometry[region], f"frame.{region}.length")
    for role, expected in (("cap_top", sum(geometry[f"h{i}"] for i in range(2, 7))),
                           ("footing_top", geometry["h5"] + geometry["h6"]), ("footing_bottom", 0.)):
        _same_number(nodes[frame["node_ids"][role]]["y"], expected, f"frame.{role}.y")
    if not 0 <= nodes[frame["node_ids"]["footing_centroid"]]["y"] <= nodes[frame["node_ids"]["footing_top"]]["y"]:
        raise InputError("0720: 基礎重心は基礎底面から天端の間に必要です")


def calculate_seismic_transverse(inputs: ReactionInput, reactions: Mapping[str, Any],
                                  transverse: Mapping[str, Any]) -> dict[str, Any]:
    """Build a detached snapshot without reading artifacts or executing legacy code."""
    try:
        snapshot, sha = _validate_sources(inputs, reactions, transverse)
        geometry = snapshot["geometry"]
        frame, node_map, member_map = build_seismic_frame(transverse, geometry,
            target_stage="0720", source_stage="0620", frame_spec_version=FRAME_SPEC_VERSION,
            upper_levels={side: float(Decimal(str(getattr(inputs.spans, side.lower()).h1))
                                      + Decimal(str(getattr(inputs.spans, side.lower()).h2)))
                          for side in ("B", "C")})
        _validate_geometry(frame, geometry)
        anchors = _mapping(_at(transverse, "frame.load_anchors"), "0620.frame.load_anchors")
        frame["load_anchors"] = _remap_reference({key: _at(anchors, key) for key in
            ("cap_top", "footing_centroid", "column_line_load", "pedestal")}, node_map, member_map, "frame.load_anchors")
        line_anchor = frame["load_anchors"]["column_line_load"]
        physical_line_ids = {member["id"] for member in frame["members"]
                             if member["region"] in ("h2", "h3", "h4", "column_base_micro_member")}
        if (line_anchor.get("from_node_id") != frame["node_ids"]["cap_top"]
                or line_anchor.get("to_node_id") != frame["node_ids"]["footing_top"]
                or set(line_anchor.get("member_ids", [])) != physical_line_ids
                or frame["load_anchors"]["cap_top"].get("node_id") != frame["node_ids"]["cap_top"]
                or frame["load_anchors"]["footing_centroid"].get("node_id") != frame["node_ids"]["footing_centroid"]
                or frame["load_anchors"]["pedestal"].get("equivalent_node_id") != frame["node_ids"]["cap_top"]):
            raise InputError("0720: frame.load_anchorsの作用区間・節点が一致しません")
        actions = _fixed_actions(transverse, frame, node_map, member_map)
        for track in ("down", "up"):
            actions[f"train_{track}"] = _train_action(inputs, reactions, frame, track)
        actions["girder_inertia"] = _horizontal(inputs, reactions, frame, train=False)
        actions["train_inertia"] = _horizontal(inputs, reactions, frame, train=True)
        inertia, formulas, actions["self_inertia"] = _self_inertia(inputs, reactions, frame, actions["dead_fixed"])
        specs = (("dead_fixed", "D1", "固定死荷重", "down", "fixed"),
                 ("dead_additional", "D2", "付加死荷重", "down", "fixed"),
                 ("buoyancy_normal", "Wp", "浮力（平水位）", "up", "fixed"),
                 ("snow_2_year", "Sw2", "雪荷重（2年確率）", "down", "fixed"),
                 ("train_down", "L", "地震時列車荷重 下り", "down", "fixed"),
                 ("train_up", "L", "地震時列車荷重 上り", "down", "fixed"),
                 ("girder_inertia", "EQ1", "地震時桁荷重慣性力", "right", "incremental"),
                 ("train_inertia", "EQL", "地震時列車荷重慣性力", "right", "limited_incremental"),
                 ("self_inertia", "EQ2", "自重による地震時慣性力", "right", "incremental"))
        basics = [{"id": index, "key": key, "symbol": symbol, "label": label, "direction": direction,
                   "load_type": kind, "coefficient": 1., "loads": deepcopy(actions[key])}
                  for index, (key, symbol, label, direction, kind) in enumerate(specs, 1)]
        provenance = {
            "references": [{"document": ".claude/docs/Example橋脚2/09_直角.pdf", "physical_pages": [1], "purpose": "physical_frame"},
                           {"document": ".claude/docs/Example橋脚2/11_直角(耐震).pdf", "physical_pages": [1,2,3,4,5,8,9,12,13],
                            "purpose": "seismic_geometry_actions_and_cases"}],
            "dependencies": ["current input", "0600.train.earthquake", "0600.transverse.case7",
                             "0600.transverse.case8", "0600.macro_handoff_single weights", "0620.frame",
                             *[f"0620.actions.{key}" for _, key, _ in _FIXED_CASES]],
            "case_authority": "原本物理p13を正とする。Case5下り/Case6上り。p11の逆表記との不一致は2026-10-17ユーザー確認済み。",
            "reference_section": "11.4作用の組合せを本帳票11.3として構成。",
            "precision": "EQ1/EQLは0600直接値。自重・固定作用は既存Single受渡し重量を保持。列車Kh0.30適用済み。",
            "model_scope": "上部は形状表示のみ。微小部材の原本非線形分類は出典であり構成則・応答は未定義。"}
        if sha is not None:
            provenance["input_sha256"] = sha
        result = {"schema_version": 1, "stage": "0720", "direction": "transverse",
            "case_model_version": CASE_MODEL_VERSION, "input": snapshot, "frame": frame,
            "seismic_conditions": {"girder_Kh": 1., "train_Kh": .3, "pier_Kh": 1., "self_Kh": 1.,
                                   "train_coefficient_applied": True},
            "actions": actions, "vertical": {"train": {"down": deepcopy(actions["train_down"]), "up": deepcopy(actions["train_up"])}},
            "horizontal": {"girder": deepcopy(actions["girder_inertia"]), "train": deepcopy(actions["train_inertia"])},
            "inertia": inertia, "formulas": formulas, "basic_cases": basics,
            "combinations": [{"id": 1, "alpha_f": 1., "rho_m": 1., "direction": "right",
                              "ground_resistance_type": 1, "coefficients": [1.,1.,1.,1.,1.,0.,1.,1.,1.]}],
            "units": {"length": "m", "force": "kN", "moment": "kN m", "line_load": "kN/m",
                      "area": "m2", "inertia": "m4", "unit_weight": "kN/m3", "elastic_modulus": "kN/m2"},
            "provenance": provenance,
            "warnings": ["0720は骨組形状と地震時作用・組合せを示します。構造解析・断面照査は実施しません。"]}
        _finite(result, "result")
        return result
    except InputError:
        raise
    except (ArithmeticError, ValueError, TypeError, KeyError, IndexError) as exc:
        raise InputError(f"0720: 入力または上流結果の形式・数値範囲が不正です（{exc}）") from exc
