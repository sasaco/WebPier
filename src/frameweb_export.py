"""Pure conversion of canonical 0610/0620 results to FrameWeb saved input."""

from collections.abc import Mapping
from dataclasses import dataclass
import math

from .frameweb_cases import PICKUP_GROUPS, build_frameweb_cases
from . import frameweb_common as common
from . import frameweb_transverse_cases as transverse
from .inputs import InputError


EXPORTER_VERSION = "p7-longitudinal-frameweb-v1"
_REQUIRED_ROLES = {"cap_top", "footing_top", "footing_centroid", "footing_bottom", "h2_h3", "h3_h4"}
_REGIONS = {
    "h2": ("cap_top", "h2_h3", "elastic", "body", "beam", 1),
    "h3": ("h2_h3", "h3_h4", "elastic", "body", "beam", 1),
    "h4": ("h3_h4", "footing_top", "elastic", "body", "column", 2),
    "footing_top_to_centroid": ("footing_top", "footing_centroid", "rigid", None, None, 3),
    "footing_centroid_to_bottom": ("footing_centroid", "footing_bottom", "rigid", None, None, 3),
    "parapet_arm": ("cap_top", "parapet_base", "rigid", None, None, 3),
    "h1": ("parapet_base", "parapet_top", "elastic", "parapet", "column", 4),
}


def _number(value, path, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{path}: 有限の数値が必要です")
    try:
        valid = math.isfinite(value)
    except (OverflowError, ValueError):
        valid = False
    if not valid or (positive and value <= 0):
        raise InputError(f"{path}: {'正の' if positive else ''}有限数値が必要です")
    return value


def _finite(value, path="0610"):
    if isinstance(value, Mapping):
        for key, item in value.items():
            _finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _finite(item, f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        _number(value, path)


def _identifier(value, path):
    if type(value) is not int or value <= 0:
        raise InputError(f"{path}: 正の整数IDが必要です")
    return value


def _indexed(rows, path):
    if not isinstance(rows, list) or not rows:
        raise InputError(f"{path}: 空でない行配列が必要です")
    indexed = {}
    for row in rows:
        identifier = _identifier(row["id"], f"{path}.id")
        if identifier in indexed:
            raise InputError(f"{path}: IDが重複しています")
        indexed[identifier] = row
    return indexed


def _validate_frame(frame, direction="longitudinal"):
    if type(frame["model_version"]) is not int or frame["model_version"] != 2:
        raise InputError("frame.model_version: 対応する版は2です")
    nodes, members = _indexed(frame["nodes"], "frame.nodes"), _indexed(frame["members"], "frame.members")
    roles = frame["node_ids"]
    allowed = _REQUIRED_ROLES | {"parapet_base", "parapet_top"}
    if not _REQUIRED_ROLES <= roles.keys() or roles.keys() - allowed:
        raise InputError("frame.node_ids: 必須役割の欠損または未対応の役割があります")
    if ("parapet_base" in roles) != ("parapet_top" in roles):
        raise InputError("frame.node_ids: H1の両端役割が必要です")
    for role, identifier in roles.items():
        _identifier(identifier, f"frame.node_ids.{role}")
        if identifier not in nodes or role not in nodes[identifier]["roles"]:
            raise InputError(f"frame.node_ids.{role}: 節点の役割と一致しません")
    for identifier, node in nodes.items():
        for axis in ("x", "y"):
            _number(node[axis], f"frame.nodes[{identifier}].{axis}")
        if set(node["roles"]) != {role for role, ref in roles.items() if ref == identifier}:
            raise InputError(f"frame.nodes[{identifier}].roles: 役割の参照が不整合です")
    support = _identifier(frame["support_node_id"], "frame.support_node_id")
    if support != roles["footing_bottom"]:
        raise InputError("frame.support_node_id: 基礎底面の支持節点が必要です")
    if (frame["spring_provenance"]["support_node_id"] != support or
            frame["spring_provenance"]["direction"] != direction):
        raise InputError("frame.spring_provenance: 解析方向の支持節点が一致しません")
    actual_regions, edges = {}, set()
    adjacency = {identifier: set() for identifier in nodes}
    for identifier, member in members.items():
        region = member["region"]
        if region not in _REGIONS or region in actual_regions:
            raise InputError(f"frame.members[{identifier}].region: 未対応または重複した部位です")
        start_role, end_role, behavior, section, material, _ = _REGIONS[region]
        if start_role not in roles or end_role not in roles:
            raise InputError(f"frame.members[{identifier}]: 必須の端部役割がありません")
        start, end = member["node_i"], member["node_j"]
        if (start, end) != (roles[start_role], roles[end_role]):
            raise InputError(f"frame.members[{identifier}]: 部位と端部節点参照が一致しません")
        if (member["behavior"], member["section_ref"], member["material_ref"]) != (behavior, section, material):
            raise InputError(f"frame.members[{identifier}]: 未対応の断面・材料・挙動の組合せです")
        length = math.hypot(nodes[start]["x"] - nodes[end]["x"], nodes[start]["y"] - nodes[end]["y"])
        edge = frozenset((start, end))
        if not math.isfinite(length) or length <= 0 or edge in edges:
            raise InputError(f"frame.members[{identifier}]: ゼロ長または重複接続です")
        edges.add(edge)
        adjacency[start].add(end)
        adjacency[end].add(start)
        actual_regions[region] = identifier
    required = {region for region, (a, b, *_) in _REGIONS.items()
                if a in roles and b in roles and roles[a] != roles[b]}
    if required != actual_regions.keys():
        raise InputError("frame.members: 役割間の部材が欠落しています")
    reached, pending = set(), [support]
    while pending:
        identifier = pending.pop()
        if identifier not in reached:
            reached.add(identifier)
            pending.extend(adjacency[identifier] - reached)
    if reached != nodes.keys():
        raise InputError("frame.nodes: 支持節点へ接続しない節点があります")
    anchors = frame["load_anchors"]
    for role in ("cap_top", "footing_centroid"):
        if anchors[role]["node_id"] != roles[role]:
            raise InputError(f"frame.load_anchors.{role}: 役割と荷重点が一致しません")
    line = anchors["column_line_load"]
    expected_members = {identifier for region, identifier in actual_regions.items() if region in ("h2", "h3", "h4")}
    if (line["from_node_id"] != roles["cap_top"] or line["to_node_id"] != roles["footing_top"] or
            not isinstance(line["member_ids"], list) or len(line["member_ids"]) != len(expected_members) or
            set(line["member_ids"]) != expected_members):
        raise InputError("frame.load_anchors.column_line_load: 柱分布荷重の範囲が不整合です")
    if (anchors["pedestal"]["equivalent_node_id"] != roles["cap_top"] or
            anchors["pedestal"]["automatic_self_weight"] is not False):
        raise InputError("frame.load_anchors.pedestal: 等価荷重と自動自重の契約が不整合です")
    expected_sections = {"body"} | ({"parapet"} if "parapet_top" in roles else set())
    if set(frame["sections"]) != expected_sections or set(frame["materials"]) != {"beam", "column", "footing"}:
        raise InputError("frame.sections/materials: 未対応の断面・材料です")
    for name, section in frame["sections"].items():
        for key in ("area", "inertia"):
            _number(section[key], f"frame.sections.{name}.{key}", positive=True)
    for name, material in frame["materials"].items():
        _number(material["Ec"], f"frame.materials.{name}.Ec", positive=True)
    for term in ("long_term", "short_term"):
        for component in ("Ks", "Kv", "Kr"):
            value = _number(frame["springs"][term][component], f"frame.springs.{term}.{component}", positive=True)
            if value == 1:
                raise InputError(f"frame.springs.{term}.{component}: 値1はnative固定拘束と衝突します")
    provenance = frame["spring_provenance"]["components"]
    if not isinstance(provenance, list) or len(provenance) != 6:
        raise InputError("frame.spring_provenance.components: 長短期の全6成分が必要です")
    seen = set()
    for row in provenance:
        key = row["term"], row["component"]
        if (key in seen or key[0] not in ("long_term", "short_term") or key[1] not in ("Ks", "Kv", "Kr") or
                row["value"] != frame["springs"][key[0]][key[1]] or row["direction"] != direction):
            raise InputError("frame.spring_provenance.components: ばね値・方向の出典が一致しません")
        seen.add(key)
    return nodes, members


def _section(name, modulus, area, inertia):
    return {"n": name, "E": modulus, "G": None, "Xp": 1e-5, "A": area, "J": None, "Iy": None, "Iz": inertia}


def _actions(basic_id, loads, frame):
    """Return sparse physical node/member actions before native row formatting."""
    anchors = frame["load_anchors"]
    top, footing = anchors["cap_top"]["node_id"], anchors["footing_centroid"]["node_id"]
    nodes, members = [], []

    def vertical(identifier, action):
        nodes.append((identifier, 0, -_number(action["N"], "loads.N"), -_number(action["M"], "loads.M")))

    if basic_id == 1:
        vertical(top, loads["top"])
        vertical(footing, loads["footing"])
        q = _number(loads["column"]["intensity"], "loads.column.intensity")
        members = [(identifier, -q) for identifier in anchors["column_line_load"]["member_ids"]]
    elif basic_id == 2:
        vertical(top, loads["top"])
        vertical(footing, loads["soil"])
    elif basic_id in (3, 4, 5):
        vertical(footing, loads)
    elif basic_id <= 12:
        vertical(top, loads)
    else:
        nodes.append((top, _number(loads["total"], "loads.total"), 0, 0))
    return nodes, members


def _load_case(basic, original_id, frame, stage="0610"):
    result = {"fix_node": basic["spring_case"], "element": 1,
              "symbol": basic.get("symbol", basic.get("key")), "name": basic["label"], "LL_pitch": 0.1, "rate": 1}
    if stage == "0620":
        nodes, members = transverse.actions(basic["loads"], frame, f"load[{basic['id']}]")
    else:
        nodes, vertical = _actions(original_id, basic["loads"], frame)
        members = [(identifier, "gy", q) for identifier, q in vertical]
    node_rows = [{"n": str(identifier), "tx": tx or None, "ty": ty or None,
                  "tz": None, "rx": None, "ry": None, "rz": rz or None, "row": index}
                 for index, (identifier, tx, ty, rz) in enumerate((row for row in nodes if any(row[1:])), 1)]
    member_rows = [{"m1": str(identifier), "m2": str(identifier), "mark": 2, "direction": axis,
                    "P1": q, "P2": q, "L1": 0, "L2": 0, "row": index}
                   for index, (identifier, axis, q) in enumerate((row for row in members if row[2]), 1)]
    if node_rows:
        result["load_node"] = node_rows
    if member_rows:
        result["load_member"] = member_rows
    return result


def _accumulate(vector: common.ActionVector, key: common.ActionKey, value: float) -> None:
    common.accumulate(vector, key, value)


def _canonical_vector(basic_id: int, loads: dict, spring: int, frame: dict) -> common.ActionVector:
    nodes, members = _actions(basic_id, loads, frame)
    return common.action_vector(nodes, ((identifier, "gy", value) for identifier, value in members), spring)


def _native_vector(case):
    spring, vector = case["fix_node"], {}
    for row in case.get("load_node", []):
        for component in ("tx", "ty", "rz"):
            _accumulate(vector, (spring, "node", int(row["n"]), component), row[component] or 0)
    for row in case.get("load_member", []):
        _accumulate(vector, (spring, "member", int(row["m1"]), row["direction"]), row["P1"])
    return vector


def _zero_action(case):
    return (not any(row.get(component) for row in case.get("load_node", []) for component in ("tx", "ty", "rz"))
            and not any(row.get(component) for row in case.get("load_member", []) for component in ("P1", "P2")))


def _zero_response_row(node_id):
    return {"n": str(node_id), "tx": 0, "ty": 0, "tz": None, "rx": None, "ry": None, "rz": 0, "row": 1}


def _needs_zero_variable_response(document):
    return _zero_action(document["load"]["21"]) and _zero_action(document["load"]["25"])


def _compare_vectors(actual: common.ActionVector, expected: common.ActionVector, path: str) -> None:
    common.compare_vectors(actual, expected, path, "ばね・節点・部材別作用が一致しません")


def _validate_action_vectors(result, document):
    frame, basics = result["frame"], result["basic_cases"]
    count = 0
    for combination in result["combinations"]:
        identifier = combination["id"]
        signed = any(row["basic_case_id"] >= 13 and row["nominal_factor"] for row in combination["resolved_components"])
        variants = combination["variants"]
        if [row["horizontal_sign"] for row in variants] != ([1, -1] if signed else [1]):
            raise InputError(f"combinations[{identifier}].variants: 水平正負の状態が不整合です")
        for variant in variants:
            sign, expected, actual = variant["horizontal_sign"], {}, {}
            rows = variant["resolved_components"]
            if len(rows) != 20 or [row["basic_case_id"] for row in rows] != list(range(1, 21)):
                raise InputError(f"combinations[{identifier}].variants: 全20作用が必要です")
            for base, row in zip(combination["resolved_components"], rows, strict=True):
                basic_id = row["basic_case_id"]
                if any(row[field] != base[field] for field in ("nominal_factor", "residual_factor", "resolution")):
                    raise InputError(f"combinations[{identifier}].variants: 解決係数・用途が元成分と一致しません")
                spring = basics[basic_id - 1]["spring_case"]
                source_vector = _canonical_vector(basic_id, base["loads"], spring, frame)
                if base["nominal_factor"] == 0 and any(value != 0 for value in source_vector.values()):
                    raise InputError(f"combinations[{identifier}].excluded_components[{basic_id}]: 名目係数0の解決作用は厳密なゼロが必要です")
                variant_vector = _canonical_vector(basic_id, row["loads"], spring, frame)
                if row["nominal_factor"] == 0 and any(value != 0 for value in variant_vector.values()):
                    raise InputError(f"combinations[{identifier}].variants[{sign}].excluded_components[{basic_id}]: 名目係数0の解決作用は厳密なゼロが必要です")
                expected_sign = sign if basic_id >= 13 else 1
                _compare_vectors(variant_vector, {key: value * expected_sign for key, value in source_vector.items()},
                                 f"combinations[{identifier}].variants[{sign}]")
                if basic_id not in (9, 10, 11, 12):
                    physical = _canonical_vector(basic_id, basics[basic_id - 1]["loads"], spring, frame)
                    _compare_vectors(source_vector, {key: value * base["nominal_factor"] for key, value in physical.items()},
                                     f"combinations[{identifier}].resolved_components[{basic_id}]")
                for key, value in variant_vector.items():
                    _accumulate(expected, key, value)
            for column, factor in document["combine"][str(identifier)].items():
                if not column.startswith("C"):
                    continue
                definition = document["define"][column[1:]]
                load_id = definition["C2"] if sign < 0 and "C2" in definition else definition["C1"]
                for key, value in _native_vector(document["load"][str(abs(load_id))]).items():
                    _accumulate(actual, key, value * factor * (1 if load_id > 0 else -1))
            _compare_vectors(actual, expected, f"combinations[{identifier}].variants[{sign}]")
            count += 1
    return count


@dataclass(frozen=True)
class FrameWebExport:
    document: dict
    source_mapping: dict


def build_frameweb_input(result: dict) -> FrameWebExport:
    """Convert an already computed schema-2 result; no I/O or recalculation.

    Source precision is retained. Finite rigid regions use the documented
    Example convention E=26,500,000 and A=Iz=1000; they are not exact rigid ties.
    """
    try:
        _finite(result)
        stage = result["stage"]
        if type(result["schema_version"]) is not int or result["schema_version"] != 2 or stage not in ("0610", "0620"):
            raise InputError("schema_version/stage: 0610/0620 schema2の正規結果が必要です")
        frame = result["frame"]
        nodes, members = _validate_frame(frame, "transverse" if stage == "0620" else "longitudinal")
        cases = transverse.build_frameweb_transverse_cases(result) if stage == "0620" else build_frameweb_cases(result)
        body = frame["sections"]["body"]
        elements = {
            "1": _section("柱体（梁材料）", frame["materials"]["beam"]["Ec"], body["area"], body["inertia"]),
            "2": _section("柱体（柱材料）", frame["materials"]["column"]["Ec"], body["area"], body["inertia"]),
            "3": _section("剛域（有限剛性）", 26500000, 1000, 1000),
        }
        if "parapet" in frame["sections"]:
            section = frame["sections"]["parapet"]
            elements["4"] = _section("H1（柱材料継承）", frame["materials"]["column"]["Ec"], section["area"], section["inertia"])
        document = {
            "dimension": 2,
            "node": {str(identifier): {"x": node["x"], "y": node["y"], "z": None}
                     for identifier, node in sorted(nodes.items())},
            "member": {str(identifier): {"ni": str(member["node_i"]), "nj": str(member["node_j"]),
                                          "e": str(_REGIONS[member["region"]][5]), "cg": None}
                       for identifier, member in sorted(members.items())},
            "element": {"1": elements},
            "fix_node": {str(identifier): [{"n": str(frame["support_node_id"]),
                                            "tx": frame["springs"][term]["Ks"], "ty": frame["springs"][term]["Kv"],
                                            "tz": None, "rx": None, "ry": None, "rz": frame["springs"][term]["Kr"], "row": 1}]
                         for identifier, term in ((1, "long_term"), (2, "short_term"))},
            "load": {str(basic["id"]): _load_case(basic, basic["id"], frame, stage) for basic in result["basic_cases"]},
            "define": cases.define, "combine": cases.combine, "pickup": cases.pickup,
        }
        for basic, mapping in zip(cases.auxiliary, cases.mapping["auxiliary_cases"], strict=True):
            original_id = mapping["basic_case_id"] if stage == "0610" else basic["id"]
            document["load"][str(basic["id"])] = _load_case(basic, original_id, frame, stage)
        retained_zero = []
        if stage == "0610" and _needs_zero_variable_response(document):
            # FEMPython omits an entirely unavailable COMBINE, making PICKUP4
            # invalid when service=0. One explicit zero response preserves the
            # existing definition and extraction without introducing a load.
            document["load"]["21"]["load_node"] = [_zero_response_row(frame["load_anchors"]["cap_top"]["node_id"])]
            retained_zero = [21]
        validate_frameweb_input(document, stage=stage)
        count = (transverse.validate_action_vectors(result, document, _native_vector) if stage == "0620"
                 else _validate_action_vectors(result, document))
        mapping = {
            "schema_version": 1, "exporter_version": transverse.EXPORTER_VERSION if stage == "0620" else EXPORTER_VERSION,
            "canonical_schema_version": 2, "case_model_version": result["case_model_version"], "frame_model_version": 2,
            "source_documents": ({"example": "Example橋脚2/09_直角.pdf", "p7": "0620_直角方向荷重.pdf"}
                                 if stage == "0620" else {"example": "Example橋脚2/08_線路.pdf", "p7": "0610_線路方向荷重.pdf"}),
            "conventions": {"units": "kN,m,kN/m2", "signs": {"tx": "H", "ty": "-N", "rz": "-M"},
                            "rigid_region": {"E": 26500000, "A": 1000, "Iz": 1000, "policy": "Example finite stiffness, not exact rigidity"},
                            "Xp": {"value": 1e-5, "source": "Example software convention"},
                            "member_load": ("Each anchored member: mark=2, global gx=qH/gy=-qN, P1=P2, L1=L2=0"
                                            if stage == "0620" else "Each anchored member: mark=2, global gy, P1=P2=-q, L1=L2=0"),
                            "automatic_self_weight": False,
                            "zero_load_rows": ("omitted except required auxiliary21 zero response for zero Combine7; IDs retained"
                                               if stage == "0610" else "omitted; case and Define IDs retained"),
                            "gui_precision": "GUI Single parse/JSON serialization can change source values; headless uses native Double"},
            "sections": {"1": "body/beam", "2": "body/column", "3": "finite rigid", **({"4": "parapet/column"} if "4" in elements else {})},
            **cases.mapping,
            "zero_load_case_ids": [int(identifier) for identifier, case in document["load"].items()
                                   if _zero_action(case)],
            "verified_variant_count": count,
        }
        if stage == "0610":
            mapping.update(
                skipped_load_case_ids=[int(identifier) for identifier, case in document["load"].items()
                                       if not case.get("load_node") and not case.get("load_member")],
                retained_zero_response_case_ids=retained_zero,
            )
        return FrameWebExport(document, mapping)
    except InputError:
        raise
    except (KeyError, TypeError, AttributeError, IndexError, ValueError, OverflowError) as exc:
        raise InputError(f"FrameWeb変換: 正規結果の必須値・構造が不正です ({exc})") from exc


def validate_frameweb_input(document: dict, *, stage="0610") -> None:
    """Validate the generated native subset again after JSON serialization."""
    try:
        if stage not in ("0610", "0620"):
            raise InputError("native.stage: 対応する方向は0610/0620です")
        _finite(document, "native")
        expected_keys = {"dimension", "node", "member", "element", "fix_node", "load", "define", "combine", "pickup"}
        if set(document) != expected_keys or document["dimension"] != 2:
            raise InputError("native: 2D保存形式のトップレベルが不正です")
        for name, count in (("load", 22 if stage == "0620" else 28), ("define", 19 if stage == "0620" else 28),
                            ("combine", 16), ("pickup", 8), ("fix_node", 2)):
            if set(document[name]) != {str(identifier) for identifier in range(1, count + 1)}:
                raise InputError(f"native.{name}: ID集合が不正です")
        if set(document["element"]) != {"1"} or set(document["element"]["1"]) not in ({"1", "2", "3"}, {"1", "2", "3", "4"}):
            raise InputError("native.element: TYPE1の断面ID集合が不正です")
        for name in ("node", "member"):
            if not document[name] or any(str(int(key)) != key or int(key) <= 0 for key in document[name]):
                raise InputError(f"native.{name}: 正の整数文字列IDが必要です")
        for identifier, node in document["node"].items():
            for axis in ("x", "y"):
                _number(node[axis], f"native.node.{identifier}.{axis}")
            if node["z"] is not None:
                raise InputError("native.node.z: 2D未使用欄はnullが必要です")
        for identifier, section in document["element"]["1"].items():
            for key in ("E", "A", "Iz"):
                _number(section[key], f"native.element.1.{identifier}.{key}", positive=True)
        for identifier, member in document["member"].items():
            if member["ni"] not in document["node"] or member["nj"] not in document["node"] or member["e"] not in document["element"]["1"]:
                raise InputError(f"native.member.{identifier}: 節点・断面参照が不正です")
            a, b = document["node"][member["ni"]], document["node"][member["nj"]]
            if math.hypot(a["x"] - b["x"], a["y"] - b["y"]) <= 0:
                raise InputError(f"native.member.{identifier}: ゼロ長部材です")
        for identifier, rows in document["fix_node"].items():
            if len(rows) != 1 or rows[0]["n"] not in document["node"]:
                raise InputError(f"native.fix_node.{identifier}: 支持節点が不正です")
            for component in ("tx", "ty", "rz"):
                if _number(rows[0][component], f"native.fix_node.{identifier}.{component}", positive=True) == 1:
                    raise InputError("native.fix_node: ばね値1は固定拘束と衝突します")
        for identifier, case in document["load"].items():
            if type(case["fix_node"]) is not int or str(case["fix_node"]) not in document["fix_node"] or case["element"] != 1:
                raise InputError(f"native.load.{identifier}: 支持・TYPE参照が不正です")
            number = int(identifier)
            expected_spring = 2 if number in (9, 10, 11, 12, 15, 16, 17, 19) or number > 20 else 1
            if stage == "0620":
                expected_spring = 1 if number <= 8 else 2
            if case["fix_node"] != expected_spring:
                raise InputError(f"native.load.{identifier}.fix_node: 基本作用の支持ばねが不整合です")
            if stage == "0620" and (type(case["element"]) is not int or case["rate"] != 1 or
                                    case["LL_pitch"] != 0.1 or case["symbol"] == "LL"):
                raise InputError(f"native.load.{identifier}: 静的作用のTYPE・倍率・形式が不正です")
            for row in case.get("load_node", []):
                permitted_zero = (stage == "0610" and number == 21 and _needs_zero_variable_response(document)
                                  and case.get("load_node") == [_zero_response_row(row["n"])]
                                  and not case.get("load_member"))
                if row["n"] not in document["node"] or (not any(row[key] for key in ("tx", "ty", "rz")) and not permitted_zero):
                    raise InputError(f"native.load.{identifier}.load_node: 無効な節点参照またはゼロ行です")
                for key in ("tx", "ty", "rz"):
                    if row[key] is not None:
                        _number(row[key], f"native.load.{identifier}.load_node.{key}")
                if stage == "0620":
                    if (set(row) != {"n", "tx", "ty", "tz", "rx", "ry", "rz", "row"} or
                            any(row[key] is not None for key in ("tz", "rx", "ry"))):
                        raise InputError(f"native.load.{identifier}.load_node: 未対応の3D成分・形式です")
                    if 15 <= number <= 17 and row["ty"]:
                        raise InputError(f"native.load.{identifier}: 正負水平ケースに鉛直荷重を混在できません")
            for row in case.get("load_member", []):
                if (row["m1"] != row["m2"] or row["m1"] not in document["member"] or row["mark"] != 2 or
                        row["direction"] not in (("gx", "gy") if stage == "0620" else ("gy",)) or
                        row["L1"] != 0 or row["L2"] != 0 or row["P1"] != row["P2"] or not row["P1"]):
                    raise InputError(f"native.load.{identifier}.load_member: 分布荷重の参照・形式が不正です")
                _number(row["P1"], f"native.load.{identifier}.load_member.P1")
                if stage == "0620" and 15 <= number <= 17 and row["direction"] == "gy":
                    raise InputError(f"native.load.{identifier}: 正負水平ケースに鉛直分布荷重を混在できません")
                # CalculationRequest.PositionMemberRows applies JS rounding to
                # P1/P2 at 0.01. Do not silently publish an action the solver
                # would change; retain canonical precision or reject the input.
                projected = math.floor(row["P1"] * 100 + 0.5) / 100
                tolerance = (1e-10 + 1e-12 * abs(row["P1"])) if stage == "0620" else 0
                if projected == 0 or abs(projected - row["P1"]) > tolerance:
                    raise InputError(f"native.load.{identifier}.load_member: ソルバー投影で0.01丸めにより荷重が変わります ({row['P1']} -> {projected})")
        for identifier, row in document["define"].items():
            number = int(identifier)
            expected = {"row": number, "C1": number, **({"C2": -number} if 13 <= number <= 20 else {})}
            if stage == "0620":
                expected = {"row": number, **{f"C{i}": ref for i, ref in enumerate(transverse.DEFINE_REFERENCES[number - 1], 1)}}
            if row != expected or any(type(value) is not int for value in row.values()):
                raise InputError(f"native.define.{identifier}: 水平作用だけの正負参照が必要です")
        for name, references in (("combine", document["define"]), ("pickup", document["combine"])):
            for identifier, row in document[name].items():
                if row["row"] != int(identifier):
                    raise InputError(f"native.{name}.{identifier}.row: IDと一致しません")
                for key, value in row.items():
                    if key in ("row", "name"):
                        continue
                    if not key.startswith("C") or not key[1:].isdigit():
                        raise InputError(f"native.{name}.{identifier}: 未対応の列です")
                    reference = key[1:] if name == "combine" else str(value)
                    if reference not in references:
                        raise InputError(f"native.{name}.{identifier}: 未定義参照です")
                    _number(value, f"native.{name}.{identifier}.{key}", positive=True)
                    if name == "combine" and 9 <= int(reference) <= 12:
                        raise InputError("native.combine: L/I基本値への名目係数再適用は禁止です")
                    if name == "combine" and int(reference) > (15 if stage == "0620" else 20) and value != 1:
                        raise InputError("native.combine: 解決済みL/I補助作用の係数は1が必要です")
                    if name == "combine" and stage == "0620" and int(reference) >= 16:
                        consumers = {c for _, d, _, _, _, group, _ in transverse.AUXILIARY_CASES
                                     if d == int(reference) for c in group}
                        if int(identifier) not in consumers:
                            raise InputError(f"native.combine.{identifier}: L/I補助の用途が不一致です")
                if name == "pickup":
                    expected = {f"C{index}": value for index, value in enumerate(PICKUP_GROUPS[int(identifier) - 1], 1)}
                    if {key: value for key, value in row.items() if key.startswith("C")} != expected:
                        raise InputError(f"native.pickup.{identifier}: 抽出の所属群が不整合です")
        if stage == "0620":
            transverse.validate_available_cases(document)
        elif _needs_zero_variable_response(document):
            rows = document["load"]["21"].get("load_node", [])
            if (len(rows) != 1 or rows[0] != _zero_response_row(rows[0]["n"]) or
                    document["combine"]["7"].get("C21") != 1 or document["combine"]["7"].get("C25") != 1):
                raise InputError("native.combine.7: ゼロの変動作用にも補助21のゼロ応答と21/25参照が必要です")
    except InputError:
        raise
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError) as exc:
        raise InputError(f"native: 保存JSONの必須値・構造が不正です ({exc})") from exc
