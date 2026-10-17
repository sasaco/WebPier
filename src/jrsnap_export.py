"""Pure current-input/0500/0710 to JRSNAP longitudinal model conversion."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal

from . import column_rebar, rebar_model
from .editor_model import EditorError
from .inputs import InputError
from .jrsnap_design_conditions import (
    GEOMETRY_TOLERANCE,
    PROFILE_ID,
    SCHEMA_VERSION,
    TARGET_VERSION,
    TRANSVERSE_PROFILE_ID,
    at,
    canonical_sha256,
    derive_jrsnap_soil_conditions,
    get_profile,
    number,
)
from .reaction_inputs import parse_reaction_input

_ROLES = ("cap_top", "footing_top", "footing_centroid", "footing_bottom", "column_base_micro_top")
_CASES = (("D1", 0), ("D2", 0), ("Wp", 0), ("Sw2", 0), ("L", 0),
          ("EQ1", 1), ("EQL", 4), ("EQ2", 1))


def _id(value, label: str) -> int:
    if type(value) is not int or value < 1:
        raise InputError(f"JRSNAP: {label}には正の整数IDが必要です")
    return value


def _same_generation(raw: dict, foundation: Mapping, seismic: Mapping, sha: str,
                     direction: str = "longitudinal") -> None:
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{64}", sha) is None:
        raise InputError("JRSNAP: input_sha256にはraw全バイトの小文字SHA256が必要です")
    stage = "0720" if direction == "transverse" else "0710"
    for label, source in (("0500", foundation), (stage, seismic)):
        if at(source, "provenance.input_sha256") != sha:
            raise InputError(f"JRSNAP: {label}.provenance.input_sha256の入力世代が一致しません")
        canonical_sha256(source)  # Reject non-finite values anywhere in the snapshot.
    if seismic.get("stage") != stage or seismic.get("schema_version") != 1 or seismic.get("direction") != direction:
        raise InputError(f"JRSNAP: {stage}/{direction} schema_version=1の結果が必要です")
    if foundation.get("schema_version") != 1:
        raise InputError("JRSNAP: 0500.schema_version=1が必要です")
    parsed_input = asdict(parse_reaction_input(raw))
    raw_geometry = parsed_input["geometry"]
    if raw_geometry != at(seismic, "input.geometry"):
        raise InputError(f"JRSNAP: rawと{stage}.input.geometryの入力世代が一致しません")
    if direction == "transverse" and canonical_sha256(parsed_input) != canonical_sha256(at(seismic, "input")):
        raise InputError("JRSNAP: rawと0720.inputの上部工・荷重入力世代が一致しません")


def _frame(seismic: Mapping, direction: str = "longitudinal") -> tuple[list, list, dict, dict]:
    frame = at(seismic, "frame")
    source_nodes, source_members = at(frame, "nodes"), at(frame, "members")
    if not isinstance(source_nodes, list) or not isinstance(source_members, list):
        raise InputError("JRSNAP: frame.nodes/membersには配列が必要です")
    if not 1 <= len(source_nodes) <= 2500 or not 1 <= len(source_members) <= 400:
        raise InputError("JRSNAP: 節点2500/部材400の上限または空モデルです")
    indexed = {}
    for node in source_nodes:
        identifier = _id(at(node, "id"), "node.id")
        if identifier in indexed:
            raise InputError("JRSNAP: 節点IDが重複しています")
        indexed[identifier] = node
    if set(indexed) != set(range(1, len(indexed) + 1)):
        raise InputError("JRSNAP: 0710節点IDは1始まりの連番が必要です")
    roles = dict(at(frame, "node_ids"))
    required_roles = _ROLES + (("superstructure_b", "superstructure_c") if direction == "transverse" else ())
    for role in required_roles:
        identifier = roles.get(role)
        matching = [node for node in source_nodes if role in node.get("roles", [])]
        if len(matching) != 1 or matching[0]["id"] != identifier or identifier not in indexed:
            raise InputError(f"JRSNAP: 役割{role}は一致する節点が1件だけ必要です")
    for role, identifier in roles.items():
        if identifier not in indexed or role not in indexed[identifier].get("roles", []):
            raise InputError(f"JRSNAP: 役割{role}の参照が不正です")
    if direction == "transverse":
        if at(frame, "frame_spec_version") != "seismic-transverse-upper-column-base-micro-v1":
            raise InputError("JRSNAP: 0720骨組の定義版が一致しません")
        for side in ("B", "C"):
            role = f"superstructure_{side.lower()}"
            upper = at(frame, f"upper_levels.{side}")
            span = at(seismic, f"input.spans.{side.lower()}")
            expected_height = float(Decimal(str(at(span, "h1"))) + Decimal(str(at(span, "h2"))))
            if (at(upper, "node_id") != roles[role] or
                    at(upper, "height") != expected_height or
                    not math.isclose(number(at(upper, "height"), f"upper_levels.{side}.height"),
                                     indexed[roles[role]]["y"] - indexed[roles["cap_top"]]["y"],
                                     rel_tol=0, abs_tol=1e-12)):
                raise InputError(f"JRSNAP: 上部構造{side}の高さ・役割が一致しません")
        if roles["superstructure_b"] != roles["superstructure_c"]:
            raise InputError("JRSNAP: B/C上部構造の高さが異なる制御点・Laはv1未対応です")
    origin = number(indexed[roles["footing_top"]]["y"], "footing_top.y")
    nodes = [{"id": node["id"], "x": number(node["x"], "node.x", minimum=-20000, maximum=20000),
              "y": number(origin - number(node["y"], "node.y"), "NDU node.y", minimum=-20000, maximum=20000),
              "roles": list(node["roles"])} for node in source_nodes]
    coordinates = {(node["x"], node["y"]) for node in nodes}
    if len(coordinates) != len(nodes):
        raise InputError("JRSNAP: 同一位置の重複節点は未対応です")
    by_id = {node["id"]: node for node in nodes}
    members, adjacency, seen_edges, correspondence = [], {key: set() for key in indexed}, set(), []
    allowed = {"h1", "h2", "h3", "h4", "parapet_arm", "column_base_micro_member",
               "footing_top_to_centroid", "footing_centroid_to_bottom"}
    if direction == "transverse":
        allowed.add("upper_geometry")
    for source in source_members:
        identifier = _id(at(source, "id"), "member.id")
        first, second = _id(at(source, "node_i"), "member.node_i"), _id(at(source, "node_j"), "member.node_j")
        if first not in by_id or second not in by_id or first == second:
            raise InputError("JRSNAP: 部材の節点参照が不正です")
        a, b = by_id[first], by_id[second]
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        if dx != 0 and dy != 0:
            raise InputError("JRSNAP: v1は鉛直・水平部材だけに対応します")
        length = number(math.hypot(dx, dy), "member.length")
        if length <= GEOMETRY_TOLERANCE:
            raise InputError("JRSNAP: 1e-9 m以下の部材は未対応です")
        edge = frozenset((first, second))
        if edge in seen_edges:
            raise InputError("JRSNAP: 部材接続が重複しています")
        seen_edges.add(edge)
        adjacency[first].add(second)
        adjacency[second].add(first)
        swapped = dy < 0 or (dy == 0 and dx < 0)
        if swapped:
            first, second = second, first
        region = source.get("region")
        if region not in allowed:
            raise InputError(f"JRSNAP: 未対応部材領域です: {region}")
        members.append({"id": identifier, "node_i": first, "node_j": second,
                        "region": region, "length": length,
                        "kind": 2 if region == "column_base_micro_member" else 1})
        correspondence.append({"source_id": identifier, "native_id": identifier, "ends_reversed": swapped})
    if {member["id"] for member in members} != set(range(1, len(members) + 1)):
        raise InputError("JRSNAP: 要素IDは重複のない1始まり連番が必要です")
    reached, pending = set(), [roles["footing_bottom"]]
    while pending:
        identifier = pending.pop()
        if identifier not in reached:
            reached.add(identifier)
            pending.extend(adjacency[identifier] - reached)
    if reached != set(indexed):
        raise InputError("JRSNAP: 基礎底面に接続していない節点があります")
    micro = [member for member in members if member["region"] == "column_base_micro_member"]
    if (len(micro) != 1 or micro[0]["id"] != at(frame, "column_base_micro_member.member_id") or
            micro[0]["node_i"] != roles["column_base_micro_top"] or micro[0]["node_j"] != roles["footing_top"] or
            not math.isclose(micro[0]["length"], .01, rel_tol=0, abs_tol=1e-12)):
        raise InputError("JRSNAP: 0.010 m微小部材の役割・接続が一致しません")
    if number(at(seismic, "input.geometry.h4"), "H4") <= .01 + GEOMETRY_TOLERANCE:
        raise InputError("JRSNAP: H4は0.010 m + 1e-9 mより大きい値が必要です")
    for region in ("h4", "column_base_micro_member"):
        if sum(member["region"] == region for member in members) != 1:
            raise InputError(f"JRSNAP: {region}は1本だけ必要です")
    return nodes, members, roles, {"nodes": [{"source_id": key, "native_id": key} for key in indexed],
                                   "members": correspondence}


def _steel(value, label: str) -> float:
    if not isinstance(value, str) or re.fullmatch(r"SD(?:295|345|390)", value) is None:
        raise InputError(f"JRSNAP: {label}はSD295/SD345/SD390だけに対応します")
    return float(value[2:])


def _section(raw: dict, seismic: Mapping, nodes: list, roles: dict, profile: dict,
             direction: str = "longitudinal") -> dict:
    face = "直角" if direction == "transverse" else "線路"
    try:
        member = rebar_model.load_member(raw, "柱")
        geometry = rebar_model.section_geometry(raw, "柱")
        layout = rebar_model.column_layout(member, geometry)
        if not layout["complete"] or not layout["bars"]:
            raise InputError("JRSNAP: 柱配筋が未完成です: " + ";".join(row["message"] for row in layout["issues"]))
        if member.get("position_mode") == "指定" and rebar_model.column_detail_status(member, geometry) != "一致":
            raise InputError("JRSNAP: 柱の詳細配筋の生成元が未設定または基本条件変更です")
        bars, _, _, warnings = rebar_model.member_preview("柱", member, geometry)
        if warnings:
            raise InputError("JRSNAP: 柱配筋の警告を解消してください: " + ";".join(warnings))
        # A manually changed arrangement needs an explicit bar-layer/pitch model.
        if member.get("position_mode") == "指定":
            fields = ("x_mm", "y_mm", "diameter_mm", "material")
            if sorted(tuple(bar[key] for key in fields) for bar in bars) != sorted(
                    tuple(bar[key] for key in fields) for bar in layout["bars"]):
                raise InputError("JRSNAP: 手動変更した詳細配筋の主筋段数・間隔はv1未対応です")
        rows = rebar_model.directional_rows(bars, face)
        material_set = {bar["material"] for bar in bars}
        if len(material_set) != 1:
            raise InputError("JRSNAP: 主筋の複数鋼種混在は未対応です")
        steel = _steel(next(iter(material_set)), "主筋材質")
        face_indices = {index for index, row in enumerate(member["main_rows"])
                        if row.get("face_direction") == face and row.get("per_face_count", 0) > 0}
        face_rows = [member["main_rows"][index] for index in sorted(face_indices)]
        if not face_rows:
            raise InputError(f"JRSNAP: {face}方向の主筋段が必要です")
        # Native DRTU/DRTL select the first/last N aggregated rows, without face IDs.
        # A shared corner remains one physical bar in this intended main-bar subset.
        main_bars = [bar for bar in layout["bars"] if face_indices.intersection(bar["row_indices"])]
        main_rows = rebar_model.directional_rows(main_bars, face)
        layers = len(face_rows)
        if (len(main_rows) != 2 * layers or rows[:layers] != main_rows[:layers] or
                rows[-layers:] != main_rows[-layers:]):
            raise InputError(f"JRSNAP: 先頭・末尾の主筋段数分の配筋行と{face}主筋が一致しません"
                             "（側面筋の割込み・混入はv1未対応です）")
        pitches = []
        for row in face_rows:
            distribution = row.get("distribution", {})
            pitch = distribution.get("pitch_mm")
            if distribution.get("mode") == "等分":
                positions = column_rebar.face_positions(row, geometry[
                    "height_mm" if direction == "transverse" else "width_mm"])
                pitch = positions[1] - positions[0] if len(positions) > 1 else None
            pitches.append(number(pitch, f"柱.main_rows.{face}.distribution.pitch_mm", minimum=.001, maximum=99999))
        if len(set(pitches)) != 1:
            raise InputError("JRSNAP: 主筋段ごとに異なる間隔の代表値はv1未対応です")
        hoops = [row for row in column_rebar.hoop_rows(member) if row.get("direction") == face]
        if len(hoops) != 1 or any(hoops[0].get(key) is not None for key in ("start_mm", "end_mm")):
            raise InputError(f"JRSNAP: {face}方向の帯筋は区間指定のない均一1設定が必要です")
        hoop = hoops[0]
        hoop_steel = _steel(hoop.get("material") or member.get("materials", {}).get("transverse"), "帯筋材質")
        legs = _id(hoop.get("effective_legs"), "帯筋有効脚数")
        diameter = number(hoop.get("diameter_mm"), "帯筋径", minimum=.001, maximum=99999)
        pitch = number(hoop.get("pitch_mm"), "帯筋配置間隔", minimum=.001, maximum=99999)
    except EditorError as exc:
        raise InputError(f"JRSNAP: {exc}") from exc
    fck = number(member.get("concrete_strength_mpa"), "柱fck", minimum=18, maximum=80)
    materials = at(seismic, "frame.materials.column")
    if fck != at(materials, "fck"):
        raise InputError("JRSNAP: raw柱fckと0710の材料が一致しません")
    width_key, height_key = (("height_mm", "width_mm") if direction == "transverse" else ("width_mm", "height_mm"))
    width = number(geometry[width_key], "断面幅", minimum=.1, maximum=999999)
    height = number(geometry[height_key], "断面高さ", minimum=.1, maximum=999999)
    width_source, height_source = (("b6", "w6") if direction == "transverse" else ("w6", "b6"))
    if (width != at(seismic, f"input.geometry.{width_source}") * 1000 or
            height != at(seismic, f"input.geometry.{height_source}") * 1000):
        raise InputError("JRSNAP: raw断面寸法と0710が一致しません")
    indexed = {node["id"]: node for node in nodes}
    span_role = profile["analysis"]["control_role"]
    span = (indexed[roles["footing_top"]]["y"] - indexed[roles[span_role]]["y"]) * 1000
    number(span, "La", minimum=.001, maximum=999999)
    if span / (height - rows[0]["center_mm"]) < 2:
        raise InputError("JRSNAP: La/d<2の低せん断スパンは曲げ型profileの対応範囲外です")
    if not 1 <= len(rows) <= 100:
        raise InputError("JRSNAP: 主筋行数は1～100行が必要です")
    return {"width_mm": width, "height_mm": height, "shear_span_mm": span,
            "fck": fck, "Ec": number(at(materials, "Ec") / 1e6, "Ec", minimum=.001, maximum=999999),
            "fyk": steel, "Es": profile["section"]["Es_kn_mm2"],
            "main_face_layers": len(face_rows), "main_face_pitch_mm": pitches[0],
            "rebar": rows, "hoop": {"fyk": hoop_steel, "diameter_mm": diameter,
                                       "legs": legs, "pitch_mm": pitch}}


def _cases(seismic: Mapping, elements: list, roles: dict) -> list:
    basics = at(seismic, "basic_cases")
    if not isinstance(basics, list) or len(basics) != 8:
        raise InputError("JRSNAP: 0710の8基本ケースが必要です")
    cases = []
    for index, ((symbol, increment), source) in enumerate(zip(_CASES, basics), 1):
        mode = {0: "fixed", 1: "incremental", 4: "limited_incremental"}[increment]
        if source.get("id") != index or source.get("symbol") != symbol or source.get("load_type") != mode or source.get("coefficient") != 1:
            raise InputError(f"JRSNAP: 基本ケース{symbol}の番号・増分方式・係数が一致しません")
        cases.append({"id": index, "symbol": symbol, "label": source["label"],
                      "increment": increment, "member_loads": [], "joint_loads": []})

    def point(case: int, role: str, *, h=0, n=0, m=0, label: str) -> None:
        values = {key: number(value, f"case{case}.{label}.{key}", minimum=-9999999999, maximum=9999999999)
                  for key, value in (("H", h), ("N", n), ("M", m))}
        cases[case - 1]["joint_loads"].append({"node": roles[role], **values, "label": label})

    def vertical(case: int, role: str, path: str, label: str) -> None:
        values = at(seismic, path)
        point(case, role, n=at(values, "N"), m=at(values, "M"), label=label)

    vertical(1, "cap_top", "vertical.fixed.top", "上部工反力")
    vertical(1, "footing_centroid", "vertical.fixed.footing", "フーチング自重")
    vertical(2, "cap_top", "vertical.additional.top", "上部工反力")
    vertical(2, "footing_top", "vertical.additional.soil", "上載土")
    vertical(3, "footing_centroid", "vertical.water.normal", "浮力")
    vertical(4, "cap_top", "vertical.snow.s2", "雪荷重")
    vertical(5, "cap_top", "vertical.train.earthquake", "列車荷重")
    for case, name in ((6, "girder"), (7, "train")):
        if at(seismic, f"horizontal.{name}.coefficient_applied") is not True:
            raise InputError("JRSNAP: 水平慣性力のKh適用済み情報が必要です")
        point(case, "cap_top", h=-number(at(seismic, f"horizontal.{name}.total"), name), label="慣性力")
    point(8, "footing_centroid", h=-number(at(seismic, "inertia.footing"), "inertia.footing"), label="フーチング慣性力")
    pedestal_h = number(at(seismic, "inertia.pedestal.H"), "inertia.pedestal.H")
    pedestal_m = number(at(seismic, "inertia.pedestal.M"), "inertia.pedestal.M")
    if pedestal_h or pedestal_m:
        point(8, "cap_top", h=-pedestal_h, m=-pedestal_m, label="H1慣性力")
    column_q = number(at(seismic, "vertical.fixed.column.intensity"), "D1.column.intensity", minimum=0, maximum=9999999999)
    for element in elements:
        region = element["region"]
        if region not in ("h2", "h3", "h4", "column_base_micro_member"):
            continue
        cases[0]["member_loads"].append({"element": element["id"], "kind": 4,
                                           "q_i": column_q, "q_j": None, "label": "柱自重"})
        first, second = {"h2": ("beam_top", "beam_top"), "h3": ("beam_top", "beam_bottom"),
                         "h4": ("column", "column"), "column_base_micro_member": ("column", "column")}[region]
        cases[7]["member_loads"].append({"element": element["id"], "kind": 1,
                                           "q_i": number(at(seismic, f"inertia.{first}"), first, minimum=0, maximum=9999999999),
                                           "q_j": number(at(seismic, f"inertia.{second}"), second, minimum=0, maximum=9999999999),
                                           "label": "自重慣性力"})
    return cases


def _transverse_cases(seismic: Mapping, elements: list, roles: dict) -> list:
    specs = (("dead_fixed", "D1", 0), ("dead_additional", "D2", 0),
             ("buoyancy_normal", "Wp", 0), ("snow_2_year", "Sw2", 0),
             ("train_down", "L", 0), ("train_up", "L", 0),
             ("girder_inertia", "EQ1", 1), ("train_inertia", "EQL", 4),
             ("self_inertia", "EQ2", 1))
    basics = at(seismic, "basic_cases")
    if not isinstance(basics, list) or len(basics) != 9:
        raise InputError("JRSNAP: 0720の9基本ケースが必要です")
    if (at(seismic, "case_model_version") != "seismic-transverse-example2-v1" or
            at(seismic, "seismic_conditions.train_Kh") != .3 or
            at(seismic, "seismic_conditions.train_coefficient_applied") is not True):
        raise InputError("JRSNAP: 0720のcase定義・列車Kh適用情報が一致しません")
    columns = {row["id"]: row for row in elements
               if row["region"] in ("h2", "h3", "h4", "column_base_micro_member")}
    cases = []
    for index, ((key, symbol, increment), source) in enumerate(zip(specs, basics), 1):
        kind = {0: "fixed", 1: "incremental", 4: "limited_incremental"}[increment]
        expected_direction = "right" if increment else ("up" if index == 3 else "down")
        if (type(source.get("id")) is not int or source["id"] != index or source.get("key") != key or
                source.get("symbol") != symbol or source.get("load_type") != kind or
                source.get("coefficient") != 1 or source.get("direction") != expected_direction):
            raise InputError(f"JRSNAP: 0720基本ケース{index}/{key}の意味が一致しません")
        action = at(seismic, f"actions.{key}")
        if at(source, "loads") != action:
            raise InputError(f"JRSNAP: 0720ケース{key}.loadsがactionsと一致しません")
        if index in (7, 8) and (at(action, "details.coefficient_applied") is not True or
                                at(action, "details.remaining_multiplier") != 1):
            raise InputError("JRSNAP: 0720水平慣性力は係数適用済みが必要です")
        case = {"id": index, "symbol": symbol, "label": source["label"],
                "increment": increment, "member_loads": [], "joint_loads": []}
        points = at(action, "points")
        anchors = (["cap_top", "footing_centroid"] if index in (1, 2, 9) else
                   ["footing_centroid"] if index == 3 else ["cap_top"])
        if not isinstance(points, list) or [at(point, "anchor") for point in points] != anchors:
            raise InputError(f"JRSNAP: 0720ケース{key}の作用位置が不正です")
        for point in points:
            role = point["anchor"]
            if type(at(point, "node_id")) is not int or point["node_id"] != roles[role]:
                raise InputError(f"JRSNAP: 0720ケース{key}の節点参照が不正です")
            values = {name: number(at(point, name), f"{key}.{name}", minimum=-9999999999, maximum=9999999999)
                      for name in ("H", "N", "M")}
            if index == 9 and role == "cap_top" and not any(values.values()):
                continue
            label = ("H1慣性力" if index == 9 and role == "cap_top" else
                     "フーチング慣性力" if index == 9 else
                     "上載土" if index == 2 and role == "footing_centroid" else
                     "フーチング自重" if index == 1 and role == "footing_centroid" else source["label"])
            case["joint_loads"].append({"node": roles[role], **values, "label": label})
        lines = at(action, "line_loads")
        if not isinstance(lines, list) or (index not in (1, 9) and lines):
            raise InputError(f"JRSNAP: 0720ケース{key}の分布荷重が未対応です")
        if index == 1:
            if len(lines) != 1:
                raise InputError("JRSNAP: D1柱分布荷重は1区間が必要です")
            line = lines[0]
            if (at(line, "anchor") != "column_line_load" or
                    at(line, "from_node_id") != roles["cap_top"] or at(line, "to_node_id") != roles["footing_top"] or
                    sorted(at(line, "member_ids")) != sorted(columns) or at(line, "qH") != 0):
                raise InputError("JRSNAP: D1柱分布荷重の要素・区間が一致しません")
            q = number(at(line, "qN"), "D1.qN", minimum=0, maximum=9999999999)
            case["member_loads"] = [{"element": identifier, "kind": 4, "q_i": q, "q_j": None, "label": "柱自重"}
                                    for identifier in columns]
        if index == 9:
            seen = set()
            for line in lines:
                ids = at(line, "member_ids")
                if not isinstance(ids, list) or len(ids) != 1 or ids[0] not in columns or ids[0] in seen:
                    raise InputError("JRSNAP: EQ2分布荷重の要素参照が不正です")
                element = columns[ids[0]]
                if (at(line, "from_node_id") != element["node_i"] or at(line, "to_node_id") != element["node_j"] or
                        at(line, "anchor") != element["region"] or at(line, "qN") != 0 or
                        not math.isclose(number(at(line, "length"), "EQ2.length"), element["length"], rel_tol=0, abs_tol=1e-12)):
                    raise InputError("JRSNAP: EQ2分布荷重の接続・領域・長さが一致しません")
                qi, qj = (number(at(line, name), f"EQ2.{name}", minimum=0, maximum=9999999999)
                          for name in ("qH_top", "qH_bottom"))
                if not math.isclose(number(at(line, "resultant_H"), "EQ2.resultant_H"),
                                    (qi + qj) / 2 * element["length"], rel_tol=1e-12, abs_tol=1e-10):
                    raise InputError("JRSNAP: EQ2分布荷重の合力が一致しません")
                seen.add(ids[0])
                case["member_loads"].append({"element": ids[0], "kind": 1, "q_i": -qi, "q_j": -qj,
                                             "label": "自重慣性力"})
            if seen != set(columns):
                raise InputError("JRSNAP: EQ2分布荷重の柱区間が欠落しています")
        cases.append(case)
    return cases


def _build_model(raw: dict, foundation: Mapping, seismic: Mapping, input_sha256: str,
                  direction: str) -> dict:
    _same_generation(raw, foundation, seismic, input_sha256, direction)
    soil = derive_jrsnap_soil_conditions(raw, foundation, seismic, direction)
    profile = get_profile(raw, direction)
    nodes, members, roles, correspondence = _frame(seismic, direction)
    section = _section(raw, seismic, nodes, roles, profile, direction)
    combinations = at(seismic, "combinations")
    transverse = direction == "transverse"
    expected = {"id": 1, "alpha_f": 1.0, "rho_m": 1.0, "direction": "right" if transverse else "left",
                "ground_resistance_type": 1,
                "coefficients": [1., 1., 1., 1., 1., 0., 1., 1., 1.] if transverse else [1.] * 8}
    if combinations != [expected]:
        raise InputError(f"JRSNAP: {direction}の方向別組合せ1件・係数が一致しません")
    micro = next(member for member in members if member["kind"] == 2)
    namespace = f"raw.jrsnap_{direction}"
    model = {
        "metadata": {"profile_id": TRANSVERSE_PROFILE_ID if transverse else PROFILE_ID, "schema_version": SCHEMA_VERSION,
                     "target_version": TARGET_VERSION, "input_sha256": input_sha256,
                     "canonical_snapshot_sha256": {"foundation": canonical_sha256(foundation),
                                                    "seismic": canonical_sha256(seismic)},
                     "settings": profile, "soil_provenance": soil["provenance"],
                     "setting_sources": {"section.safety.GBC": f"{namespace}.shear_factor_vcd",
                                         "section.safety.GBV": f"{namespace}.shear_factor_vsd",
                                         "section.safety.GBVD": f"{namespace}.shear_factor_vdd",
                                         "section.aggregate_max_mm": f"{namespace}.aggregate_max_mm"},
                     "correspondence": correspondence, "roles": roles},
        "nodes": nodes, "members": members, "elements": deepcopy(members), "section": section,
        "nonlinear": {"id": 1, "section": 1, "element": micro["id"]},
        "supports": [{"node": roles["footing_bottom"], "direction": 1, "stiffness": soil["Ks"]},
                     {"node": roles["footing_bottom"], "direction": 2, "stiffness": soil["Kv"]}],
        "footing": {"node": roles["footing_bottom"], **{key: value for key, value in soil.items() if key != "provenance"}},
        "cases": (_transverse_cases if transverse else _cases)(seismic, members, roles),
        "combination": deepcopy(expected),
    }
    if transverse:
        model["metadata"]["direction"] = direction
    return model


def build_longitudinal_ndu_model(raw: dict, foundation: Mapping, seismic: Mapping,
                                 input_sha256: str) -> dict:
    """Return a detached model; never read files or mutate caller snapshots."""
    return _build_model(raw, foundation, seismic, input_sha256, "longitudinal")


def build_transverse_ndu_model(raw: dict, foundation: Mapping, seismic: Mapping,
                               input_sha256: str) -> dict:
    """Build the rightward 0720 model with its own section, control and cases."""
    return _build_model(raw, foundation, seismic, input_sha256, "transverse")
