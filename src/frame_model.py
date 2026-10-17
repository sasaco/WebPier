"""Connected frame input metadata shared by the 0610 and 0620 calculators.

This module adds no loads and performs no structural analysis. Source worksheet
nodes remain an audit trail; semantic roles identify the active calculation nodes.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal, localcontext
import math
from typing import Any

from .inputs import InputError
from .reaction_math import excel_round


_PRIORITY = (4, 2, 1, 3, 5, 6, 7, 8)
_ROLES = {1: "cap_top", 2: "footing_top", 3: "footing_centroid",
          4: "footing_bottom", 5: "h2_h3", 6: "h3_h4",
          7: "parapet_base", 8: "parapet_top"}


def _stage(direction: str) -> str:
    if direction not in ("b", "w"):
        raise InputError("frame.direction: b または w が必要です")
    return "0610" if direction == "b" else "0620"


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{path}: 有限の数値が必要です")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise InputError(f"{path}: 数値範囲を超えています") from exc
    if not math.isfinite(result):
        raise InputError(f"{path}: 有限の数値が必要です")
    return result


def parapet_center(geometry: Mapping[str, float], direction: str) -> float:
    """Return the exact decimal-input center, without a centering tolerance.

    Decimal strings distinguish a mathematically centered input from a small real
    eccentricity. The precision covers the complete finite binary64 exponent
    range, including cancellation between very different input magnitudes.
    """
    stage = _stage(direction)
    values = [_number(geometry[f"{direction}{i}"],
                      f"{stage}.input.geometry.{direction}{i}") for i in range(1, 6)]
    with localcontext() as context:
        context.prec = 1000
        a1, a2, a3, a4, a5 = (Decimal(str(value)) for value in values)
        center = (2 * a2 + a3 - a1 - a4 + a5) / 2
    result = float(center)
    if not math.isfinite(result) or (center != 0 and result == 0):
        raise InputError(f"{stage}.input.geometry.{direction}1..{direction}5: "
                         "パラペット偏心が座標の数値範囲を超えています")
    return 0.0 if center == 0 else result


def _add_height(base: float, height: float, path: str) -> float:
    result = base + height
    if not math.isfinite(result) or (height > 0 and result <= base):
        raise InputError(f"{path}: 正の高さを座標精度で表現できません（数値範囲）")
    return result


def _parapet_section(geometry: Mapping[str, float], direction: str) -> dict[str, float]:
    stage = _stage(direction)
    b = _number(geometry["b3"], f"{stage}.input.geometry.b3")
    w = _number(geometry["w3"], f"{stage}.input.geometry.w3")
    for name, value in (("b3", b), ("w3", w)):
        if value <= 0:
            raise InputError(f"{stage}.input.geometry.{name}: H1>0では正値が必要です")
    width, depth = (w, b) if direction == "b" else (b, w)
    try:
        area = excel_round(b * w, 3)
        inertia = excel_round((1 / 12) * width * depth ** 3, 5)
    except (ArithmeticError, ValueError, InputError) as exc:
        raise InputError(f"{stage}.input.geometry.b3/w3: "
                         "H1断面の計算または丸めが数値範囲を超えています") from exc
    if area <= 0 or inertia <= 0:
        raise InputError(f"{stage}.input.geometry.b3/w3: "
                         "H1の丸め後断面積・断面二次モーメントは正値が必要です")
    return {"width": width, "depth": depth, "area": area, "inertia": inertia}


def build_frame_model(geometry: Mapping[str, float], legacy_frame: Mapping[str, Any],
                      direction: str) -> dict[str, Any]:
    """Extend a legacy four-node frame without modifying either input.

    Equal coordinates merge by the complete stable priority, never by a display
    rounding or distance tolerance. Positive heights lost to binary64 precision
    fail explicitly instead of being treated as intentionally zero heights.
    """
    stage = _stage(direction)
    heights = {}
    for index in range(1, 7):
        key = f"h{index}"
        heights[key] = _number(geometry[key], f"{stage}.input.geometry.{key}")
        if heights[key] < 0:
            raise InputError(f"{stage}.input.geometry.{key}: 0以上が必要です")
    original_nodes = deepcopy(legacy_frame["nodes"])
    legacy_by_id = {node["id"]: node for node in original_nodes}
    if len(original_nodes) != 4 or set(legacy_by_id) != {1, 2, 3, 4}:
        raise InputError(f"{stage}.frame.nodes: 元の4節点IDが必要です")
    for node in original_nodes:
        for axis in ("x", "y"):
            _number(node[axis], f"{stage}.frame.nodes[{node['id']}].{axis}")
    zf = _add_height(heights["h6"], heights["h5"], f"{stage}.input.geometry.h5")
    if heights["h6"] > 0 and zf <= heights["h5"]:
        raise InputError(f"{stage}.input.geometry.h6: 正の高さを座標精度で表現できません（数値範囲）")
    zc = _add_height(zf, heights["h4"], f"{stage}.input.geometry.h4")
    zb = _add_height(zc, heights["h3"], f"{stage}.input.geometry.h3")
    zt = _add_height(zb, heights["h2"], f"{stage}.input.geometry.h2")
    hg = _number(legacy_by_id[3]["y"], f"{stage}.0600.macro_handoff_single.フーチング.hG")
    if not 0 <= hg <= zf:
        raise InputError(f"{stage}.0600.macro_handoff_single.フーチング.hG: "
                         "底面から基礎天端までの値が必要です")
    coordinates = {1: (0.0, zt), 2: (0.0, zf), 3: (0.0, hg),
                   4: (0.0, 0.0), 5: (0.0, zb), 6: (0.0, zc)}
    frame = deepcopy(dict(legacy_frame))
    sections = {"body": deepcopy(frame["section"])}
    for key in ("area", "inertia"):
        value = _number(sections["body"][key], f"{stage}.frame.section.{key}")
        if value <= 0:
            raise InputError(f"{stage}.frame.section.{key}: 正値が必要です")
    if heights["h1"] > 0:
        sections["parapet"] = _parapet_section(geometry, direction)
        xp = parapet_center(geometry, direction)
        zp = _add_height(zt, heights["h1"], f"{stage}.input.geometry.h1")
        coordinates.update({7: (xp, zt), 8: (xp, zp)})

    by_coordinate: dict[tuple[float, float], int] = {}
    aliases = {}
    nodes: dict[int, dict[str, Any]] = {}
    for identifier in _PRIORITY:
        if identifier not in coordinates:
            continue
        coordinate = coordinates[identifier]
        active = by_coordinate.setdefault(coordinate, identifier)
        aliases[identifier] = active
        nodes.setdefault(active, {"id": active, "x": coordinate[0], "y": coordinate[1],
                                  "roles": [], "source_rows": []})
    for identifier in sorted(coordinates):
        active_node = nodes[aliases[identifier]]
        active_node["roles"].append(_ROLES[identifier])
        if identifier in legacy_by_id:
            active_node["source_rows"].append(legacy_by_id[identifier]["source_row"])
    for node in nodes.values():
        node["source_rows"].sort()
    node_ids = {_ROLES[identifier]: aliases[identifier] for identifier in sorted(coordinates)}
    members = []
    specs = ((1, 1, 5, "h2", "elastic", "body"),
             (2, 5, 6, "h3", "elastic", "body"),
             (3, 6, 2, "h4", "elastic", "body"),
             (4, 2, 3, "footing_top_to_centroid", "rigid", None),
             (5, 3, 4, "footing_centroid_to_bottom", "rigid", None),
             (6, 1, 7, "parapet_arm", "rigid", None),
             (7, 7, 8, "h1", "elastic", "parapet"))
    for identifier, start, end, region, behavior, section in specs:
        if start not in aliases or end not in aliases or aliases[start] == aliases[end]:
            continue
        members.append({"id": identifier, "node_i": aliases[start], "node_j": aliases[end],
                        "region": region, "behavior": behavior, "section_ref": section,
                        "material_ref": "body" if behavior == "elastic" else None})
    frame.update(model_version=2, nodes=[nodes[key] for key in sorted(nodes)],
                 members=members, node_ids=node_ids, sections=sections,
                 support_node_id=node_ids["footing_bottom"],
                 legacy_nodes=[{**node, "active_node_id": aliases[node["id"]]}
                               for node in sorted(original_nodes, key=lambda node: node["id"])],
                 load_anchors={
                     "cap_top": {"node_id": node_ids["cap_top"]},
                     "footing_centroid": {"node_id": node_ids["footing_centroid"]},
                     "column_line_load": {"from_node_id": node_ids["cap_top"],
                                          "to_node_id": node_ids["footing_top"],
                                          "member_ids": [member["id"] for member in members
                                                         if member["id"] in (1, 2, 3)]},
                     "pedestal": {"equivalent_node_id": node_ids["cap_top"],
                                  "automatic_self_weight": False}})
    _validate_model(frame, stage)
    return frame


def _validate_model(frame: Mapping[str, Any], stage: str) -> None:
    """Check actual references and geometric connectivity before publishing."""
    _validate_finite(frame, f"{stage}.frame")
    nodes = {node["id"]: node for node in frame["nodes"]}
    adjacency: dict[int, set[int]] = {identifier: set() for identifier in nodes}
    edges = set()
    for member in frame["members"]:
        start, end = member["node_i"], member["node_j"]
        if start not in nodes or end not in nodes:
            raise InputError(f"{stage}.frame.members[{member['id']}]: 節点参照が不正です")
        edge = frozenset((start, end))
        length = math.hypot(nodes[start]["x"] - nodes[end]["x"],
                            nodes[start]["y"] - nodes[end]["y"])
        if not math.isfinite(length) or length <= 0 or edge in edges:
            raise InputError(f"{stage}.frame.members[{member['id']}]: 部材長または重複接続が不正です")
        edges.add(edge)
        adjacency[start].add(end)
        adjacency[end].add(start)
        if member["behavior"] == "elastic":
            if (member["section_ref"] not in frame["sections"] or
                    member["material_ref"] not in frame["materials"]):
                raise InputError(f"{stage}.frame.members[{member['id']}]: 断面・材料参照が不正です")
        elif member["section_ref"] is not None or member["material_ref"] is not None:
            raise InputError(f"{stage}.frame.members[{member['id']}]: 剛部材の参照はnullが必要です")
    reached = set()
    pending = [frame["support_node_id"]]
    while pending:
        identifier = pending.pop()
        if identifier not in reached:
            reached.add(identifier)
            pending.extend(adjacency[identifier] - reached)
    if reached != nodes.keys():
        raise InputError(f"{stage}.frame.nodes: 支持節点へ接続しない節点があります")


def _validate_finite(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_finite(item, f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        _number(value, path)
