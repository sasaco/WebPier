"""Detached physical seismic geometry shared by 0710 and 0720.

This module builds report geometry, never restraints or a response model.
Internal ID maps allow callers to rebind actions after splitting and numbering.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import math

from .inputs import InputError

_MICRO_LENGTH = .01


class _Reader:
    def __init__(self, target: str, source: str) -> None:
        self.target, self.source = target, source

    def at(self, source: Mapping[str, Any], path: str) -> Any:
        value: Any = source
        for key in path.split("."):
            if not isinstance(value, Mapping) or key not in value:
                raise InputError(f"{self.target}: {self.source}.{path}が必要です")
            value = value[key]
        return value


    def number(self, value: Any, path: str) -> int | float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InputError(f"{self.target}: {self.source}.{path}には有限の数値が必要です")
        try:
            finite = math.isfinite(value)
        except OverflowError as exc:
            raise InputError(f"{self.target}: {self.source}.{path}は数値範囲を超えています") from exc
        if not finite:
            raise InputError(f"{self.target}: {self.source}.{path}には有限の数値が必要です")
        return value


    def numbers(self, source: Mapping[str, Any], path: str, keys: tuple[str, ...]) -> dict[str, Any]:
        return {key: self.number(self.at(source, f"{path}.{key}"), f"{path}.{key}") for key in keys}


    def mapping(self, value: Any, path: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise InputError(f"{self.target}: {self.source}.{path}にはオブジェクトが必要です")
        return value


    def rows(self, value: Any, path: str) -> list | tuple:
        if not isinstance(value, (list, tuple)) or not value:
            raise InputError(f"{self.target}: {self.source}.{path}には空でない配列が必要です")
        return value


    def integer(self, value: Any, path: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InputError(f"{self.target}: {self.source}.{path}には正の整数が必要です")
        return value



def _physical_frame(source: Mapping[str, Any], v: _Reader) -> dict[str, Any]:
    """Allowlist geometry/material fields, never support-model metadata."""
    frame = v.mapping(v.at(source, "frame"), "frame")
    if type(frame.get("model_version")) is not int or frame["model_version"] != 2:
        raise InputError(f"{v.target}: {v.source}.frame.model_version=2が必要です")
    result: dict[str, Any] = {
        "model_version": 2,
        "shape_eccentricity": v.number(v.at(frame, "shape_eccentricity"), "frame.shape_eccentricity"),
        "nodes": [], "members": [], "node_ids": {}, "sections": {}, "materials": {},
    }
    ids: set[int] = set()
    for index, node in enumerate(v.rows(v.at(frame, "nodes"), "frame.nodes")):
        path = f"frame.nodes[{index}]"
        node = v.mapping(node, path)
        identifier = v.integer(node.get("id"), f"{path}.id")
        if identifier in ids:
            raise InputError(f"{v.target}: {v.source}.{path}.idが重複しています")
        ids.add(identifier)
        roles = node.get("roles")
        if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
            raise InputError(f"{v.target}: {v.source}.{path}.rolesには役割名の配列が必要です")
        result["nodes"].append({"id": identifier, "roles": list(roles),
                                **{axis: v.number(node.get(axis), f"{path}.{axis}") for axis in ("x", "y")}})
    for role, identifier in v.mapping(v.at(frame, "node_ids"), "frame.node_ids").items():
        if v.integer(identifier, f"frame.node_ids.{role}") not in ids:
            raise InputError(f"{v.target}: {v.source}.frame.node_ids.{role}の節点がありません")
        result["node_ids"][role] = identifier
    for key in ("cap_top", "footing_top", "footing_centroid", "footing_bottom"):
        if key not in result["node_ids"]:
            raise InputError(f"{v.target}: {v.source}.frame.node_ids.{key}が必要です")
    for name, section in v.mapping(v.at(frame, "sections"), "frame.sections").items():
        path = f"frame.sections.{name}"
        section = v.mapping(section, path)
        result["sections"][name] = {key: v.number(section.get(key), f"{path}.{key}")
                                    for key in ("width", "depth", "area", "inertia")}
    result["section"] = v.numbers(source, "frame.section", ("width", "depth", "area", "inertia"))
    for name, material in v.mapping(v.at(frame, "materials"), "frame.materials").items():
        path = f"frame.materials.{name}"
        material = v.mapping(material, path)
        result["materials"][name] = {key: v.number(material.get(key), f"{path}.{key}")
                                     for key in ("fck", "Ec")}
    member_ids: set[int] = set()
    for index, member in enumerate(v.rows(v.at(frame, "members"), "frame.members")):
        path = f"frame.members[{index}]"
        member = v.mapping(member, path)
        row = {key: v.integer(member.get(key), f"{path}.{key}") for key in ("id", "node_i", "node_j")}
        if row["id"] in member_ids or row["node_i"] not in ids or row["node_j"] not in ids:
            raise InputError(f"{v.target}: {v.source}.{path}のIDまたは節点参照が不正です")
        member_ids.add(row["id"])
        for key in ("region", "behavior", "section_ref", "material_ref"):
            if key not in member:
                raise InputError(f"{v.target}: {v.source}.{path}.{key}が必要です")
            row[key] = member[key]
        if not isinstance(row["region"], str) or row["behavior"] not in ("elastic", "rigid"):
            raise InputError(f"{v.target}: {v.source}.{path}の部材種別が不正です")
        if row["behavior"] == "elastic":
            if (not isinstance(row["section_ref"], str) or not isinstance(row["material_ref"], str)
                    or row["section_ref"] not in result["sections"]
                    or row["material_ref"] not in result["materials"]):
                raise InputError(f"{v.target}: {v.source}.{path}の断面・材料参照が不正です")
        elif row["section_ref"] is not None or row["material_ref"] is not None:
            raise InputError(f"{v.target}: {v.source}.{path}の剛部材参照はnullが必要です")
        result["members"].append(row)
    return result


def _number_frame_top_down(frame: dict[str, Any]) -> tuple[dict[int, int], dict[int, int]]:
    """Number detached geometry from top to bottom and update every ID reference."""
    nodes = sorted(frame["nodes"], key=lambda node: (-node["y"], node["x"], node["id"]))
    node_ids = {node["id"]: index for index, node in enumerate(nodes, 1)}
    for node in nodes:
        node["id"] = node_ids[node["id"]]
    frame["nodes"] = nodes
    by_id = {node["id"]: node for node in nodes}
    for member in frame["members"]:
        for end in ("node_i", "node_j"):
            member[end] = node_ids[member[end]]

    def member_order(member: Mapping[str, Any]) -> tuple:
        first, second = by_id[member["node_i"]], by_id[member["node_j"]]
        return (-(first["y"] / 2 + second["y"] / 2), first["x"] / 2 + second["x"] / 2,
                min(first["id"], second["id"]), max(first["id"], second["id"]), member["id"])

    members = sorted(frame["members"], key=member_order)
    member_ids = {member["id"]: index for index, member in enumerate(members, 1)}
    for member in members:
        member["id"] = member_ids[member["id"]]
    frame["members"] = members
    frame["node_ids"] = {role: node_ids[identifier] for role, identifier in frame["node_ids"].items()}
    micro = frame["column_base_micro_member"]
    micro["node_id"] = node_ids[micro["node_id"]]
    micro["member_id"] = member_ids[micro["member_id"]]
    return node_ids, member_ids


def build_seismic_frame(source: Mapping[str, Any], geometry: Mapping[str, Any], *,
                        target_stage: str, source_stage: str, frame_spec_version: str,
                        upper_levels: Mapping[str, float] | None = None,
                        ) -> tuple[dict[str, Any], dict[int, int], dict[int, list[int]]]:
    """Split the column's bottom 0.010 m without moving existing geometry.

    The reference's nonlinear member classification is report metadata only;
    no constitutive law, restraint, stiffness, or response is inferred here.
    """
    v = _Reader(target_stage, source_stage)
    frame = _physical_frame(source, v)
    original_nodes = [node["id"] for node in frame["nodes"]]
    split_members = {member["id"]: [member["id"]] for member in frame["members"]}
    if geometry["h4"] <= _MICRO_LENGTH:
        raise InputError(f"{v.target}: 柱下端に0.010 m微小部材を設けるため、H4は0.010 mより大きい値が必要です")
    columns = [member for member in frame["members"] if member["region"] == "h4"]
    footing_id = frame["node_ids"]["footing_top"]
    if len(columns) != 1 or columns[0]["node_j"] != footing_id:
        raise InputError(f"{v.target}: 微小部材の挿入には基礎天端へ接続するH4部材が1本必要です")
    if "body" not in frame["sections"] or "column" not in frame["materials"]:
        raise InputError(f"{v.target}: 柱下端微小部材にはbody断面とcolumn材料が必要です")
    column = columns[0]
    nodes = {node["id"]: node for node in frame["nodes"]}
    bottom, top = nodes[footing_id], nodes[column["node_i"]]
    new_y = bottom["y"] + _MICRO_LENGTH
    # Do not collapse a positive segment or silently distort the prescribed
    # length when a large coordinate cannot resolve 0.010 m to 1e-12 m.
    if (not math.isfinite(new_y) or not bottom["y"] < new_y < top["y"]
            or not math.isclose(new_y - bottom["y"], _MICRO_LENGTH, rel_tol=0.0, abs_tol=1e-12)):
        raise InputError(f"{v.target}: 0.010 m微小部材と残りのH4部材を座標精度で表現できません")
    if top["x"] != bottom["x"]:
        raise InputError(f"{v.target}: 柱下端微小部材の挿入には鉛直なH4部材が必要です")
    new_node_id = max(nodes) + 1
    new_member_id = max(member["id"] for member in frame["members"]) + 1
    frame["nodes"].append({"id": new_node_id, "x": bottom["x"], "y": new_y,
                           "roles": ["column_base_micro_top"]})
    frame["node_ids"]["column_base_micro_top"] = new_node_id
    column["node_j"] = new_node_id
    frame["members"].append({
        "id": new_member_id, "node_i": new_node_id, "node_j": footing_id,
        "region": "column_base_micro_member", "behavior": "nonlinear",
        "section_ref": "body", "material_ref": "column",
    })
    frame["frame_spec_version"] = frame_spec_version
    frame["column_base_micro_member"] = {
        "node_id": new_node_id, "member_id": new_member_id, "nominal_length": _MICRO_LENGTH,
    }
    split_members[column["id"]].append(new_member_id)
    if upper_levels is not None:
        _add_upper_levels(frame, upper_levels, split_members, v)
    node_map, member_map = _number_frame_top_down(frame)
    if upper_levels is not None:
        for level in frame["upper_levels"].values():
            level["node_id"] = node_map[level["node_id"]]
    return (frame, {old: node_map[old] for old in original_nodes},
            {old: [member_map[part] for part in parts] for old, parts in split_members.items()})




def _add_upper_levels(frame: dict[str, Any], levels: Mapping[str, float],
                      split_members: dict[int, list[int]], v: _Reader) -> None:
    """Keep each side's geometric height, coalescing only identical coordinates."""
    nodes = {node["id"]: node for node in frame["nodes"]}
    cap = nodes[frame["node_ids"]["cap_top"]]
    by_coordinate = {(node["x"], node["y"]): node for node in nodes.values()}
    frame["upper_levels"] = {}
    upper_ids = {cap["id"]}
    for side, raw_height in levels.items():
        height = v.number(raw_height, f"upper_levels.{side}")
        y = cap["y"] + height
        if height < 0 or not math.isfinite(y) or (height > 0 and y <= cap["y"]):
            raise InputError(f"{v.target}: 上部高さを座標精度で表現できません")
        role = f"superstructure_{side.lower()}"
        coordinate = (cap["x"], y)
        if coordinate not in by_coordinate:
            node = {"id": max(nodes) + 1, "x": cap["x"], "y": y, "roles": []}
            nodes[node["id"]] = node
            frame["nodes"].append(node)
            by_coordinate[coordinate] = node
        node = by_coordinate[coordinate]
        node["roles"].append(role)
        frame["node_ids"][role] = node["id"]
        frame["upper_levels"][side] = {"height": height, "node_id": node["id"]}
        upper_ids.add(node["id"])
    # A centered H1 may share the upper centerline. Split its physical member
    # at new levels instead of drawing a second, overlapping geometric member.
    for member in list(frame["members"]):
        first, second = nodes[member["node_i"]], nodes[member["node_j"]]
        if first["x"] != cap["x"] or second["x"] != cap["x"]:
            continue
        interior = [nodes[identifier] for identifier in upper_ids
                    if min(first["y"], second["y"]) < nodes[identifier]["y"] < max(first["y"], second["y"])]
        if not interior:
            continue
        ordered_segment = [first, *sorted(interior, key=lambda node: node["y"],
                                          reverse=first["y"] > second["y"]), second]
        original_end = member["node_j"]
        member["node_j"] = ordered_segment[1]["id"]
        for left, right in zip(ordered_segment[1:], ordered_segment[2:]):
            identifier = max(item["id"] for item in frame["members"]) + 1
            frame["members"].append({**member, "id": identifier, "node_i": left["id"], "node_j": right["id"]})
            split_members[member["id"]].append(identifier)
        assert ordered_segment[-1]["id"] == original_end
    upper_ids.update(node["id"] for node in nodes.values()
                     if node["x"] == cap["x"] and node["y"] >= cap["y"])
    ordered = sorted(upper_ids, key=lambda identifier: nodes[identifier]["y"], reverse=True)
    existing_edges = {frozenset((member["node_i"], member["node_j"])) for member in frame["members"]}
    for first, second in zip(ordered, ordered[1:]):
        if frozenset((first, second)) in existing_edges:
            continue
        frame["members"].append({"id": max(member["id"] for member in frame["members"]) + 1,
                                 "node_i": first, "node_j": second,
                                 "region": "upper_geometry", "behavior": "geometry_only",
                                 "section_ref": None, "material_ref": None})
