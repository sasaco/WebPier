"""Native references for 0620, preserving usage and same-track L/I choices."""

from copy import deepcopy
from itertools import product
import math

from .frameweb_cases import FrameWebCases
from .frameweb_common import ActionVector, action_vector as vector_from_actions, compare_vectors
from .inputs import InputError
from .transverse_example2_cases import validate_case_model


EXPORTER_VERSION = "p7-transverse-frameweb-v1"
# load, Define, track, usage, role, consuming combinations, original L/I Defines.
AUXILIARY_CASES = (
    (18, 16, "double", "ultimate", "maximum", (1, 10), (10, 12)),
    (19, 17, "double", "ultimate", "ordinary", (2, 8, 11), (10, 12)),
    (20, 18, "double", "service", "service", (5,), (10, 12)),
    (21, 19, "up", "service", "service", (7, 15, 16), (9, 11)),
    (22, 19, "down", "service", "service", (7, 15, 16), (9, 11)),
)
DEFINE_REFERENCES = tuple((i,) for i in range(1, 9)) + (
    (9, 10), (11,), (12, 13), (14,), (15, -15), (16, -16), (17, -17),
    (18,), (19,), (20,), (21, 22),
)
ACTION_UNITS = {"N": "kN", "H": "kN", "M": "kN m", "arm": "m"}


def _number(value, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputError(f"{path}: 有限の数値が必要です")
    return value


def actions(loads, frame, path="loads"):
    """Read physical actions only, checking their exact canonical anchors."""
    nodes, members = [], []
    if loads["units"] != ACTION_UNITS:
        raise InputError(f"{path}.units: 正規作用の単位と一致しません")
    if not isinstance(loads["points"], list) or not isinstance(loads["line_loads"], list):
        raise InputError(f"{path}: points/line_loads配列が必要です")
    for index, point in enumerate(loads["points"]):
        location = f"{path}.points[{index}]"
        if set(point) != {"anchor", "node_id", "N", "H", "M"}:
            raise InputError(f"{location}: 未対応の点荷重成分です")
        anchor = point["anchor"]
        if (anchor not in ("cap_top", "footing_centroid") or type(point["node_id"]) is not int or
                point["node_id"] != frame["load_anchors"][anchor]["node_id"]):
            raise InputError(f"{location}: 荷重点とanchorが一致しません")
        nodes.append((point["node_id"], _number(point["H"], location + ".H"),
                      -_number(point["N"], location + ".N"), -_number(point["M"], location + ".M")))
    for index, line in enumerate(loads["line_loads"]):
        location = f"{path}.line_loads[{index}]"
        anchor = frame["load_anchors"]["column_line_load"]
        if (set(line) != {"anchor", "from_node_id", "to_node_id", "member_ids", "qN", "qH", "unit"} or
                line["anchor"] != "column_line_load" or line["unit"] != "kN/m" or
                any(line[key] != anchor[key] for key in ("from_node_id", "to_node_id", "member_ids"))):
            raise InputError(f"{location}: 柱分布荷重の範囲・単位が一致しません")
        for identifier in line["member_ids"]:
            if type(identifier) is not int:
                raise InputError(f"{location}.member_ids: 整数IDが必要です")
            members.extend(((identifier, "gx", _number(line["qH"], location + ".qH")),
                            (identifier, "gy", -_number(line["qN"], location + ".qN"))))
    return nodes, members


def action_vector(loads: dict, spring: int, frame: dict, path: str = "loads") -> ActionVector:
    nodes, members = actions(loads, frame, path)
    return vector_from_actions(nodes, members, spring)


def _compare(actual: ActionVector, expected: ActionVector, path: str) -> None:
    compare_vectors(actual, expected, path, "支持・節点・部材別作用が不一致です")


def _validate_components(result):
    frame, basics = result["frame"], result["basic_cases"]
    expected_units = {"length": "m", "force": "kN", "moment": "kN m", "area": "m2",
                      "inertia": "m4", "line_load": "kN/m"}
    if result["units"] != expected_units:
        raise InputError("0620.units: 正規単位と一致しません")
    if set(result["actions"]) != {basic["key"] for basic in basics}:
        raise InputError("0620.actions: 必須17作用の欠損または未対応の作用があります")
    for basic in basics:
        path = f"basic_cases[{basic['id'] - 1}].loads"
        if basic["loads"] != result["actions"][basic["key"]]:
            raise InputError(f"{path}: 正規actionsと不一致です")
        action_vector(basic["loads"], basic["spring_case"], frame, path)
    indexed = {}
    for combination in result["combinations"]:
        path = f"combinations[{combination['id'] - 1}].resolved_components"
        rows = combination["resolved_components"]
        expected_ids = [i for i, factor in enumerate(combination["coefficients"], 1) if factor]
        if (not isinstance(rows, list) or [row["define_case_id"] for row in rows] != expected_ids or
                any(type(row["define_case_id"]) is not int for row in rows)):
            raise InputError(f"{path}: 非零Define全項の順序付き解決作用が必要です")
        indexed[combination["id"]] = {row["define_case_id"]: row for row in rows}
        for row in rows:
            define_id = row["define_case_id"]
            define = result["define_cases"][define_id - 1]
            nominal = combination["coefficients"][define_id - 1]
            location = f"{path}[Define={define_id}]"
            candidates = row["candidates"]
            if (isinstance(row["nominal_coefficient"], bool) or row["nominal_coefficient"] != nominal or row["symbol"] != define["symbol"] or
                    [c["signed_basic_case_id"] for c in candidates] != define["signed_basic_case_ids"]):
                raise InputError(f"{location}: 係数・候補・Define対応が不正です")
            for candidate in candidates:
                signed = candidate["signed_basic_case_id"]
                if type(signed) is not int or type(candidate["basic_case_id"]) is not int:
                    raise InputError(f"{location}: 基本作用のIDは整数が必要です")
                basic = basics[abs(signed) - 1]
                if candidate["basic_case_id"] != basic["id"] or candidate["action_key"] != basic["key"]:
                    raise InputError(f"{location}: 基本作用の対応が不正です")
                expected_track = basic.get("track")
                if expected_track in ("up", "down"):
                    if candidate.get("direction") != expected_track or candidate.get("compatibility_group") != "single_track":
                        raise InputError(f"{location}: 単線の方向・相関groupが不正です")
                elif "direction" in candidate or "compatibility_group" in candidate:
                    raise InputError(f"{location}: 未対応の候補相関groupです")
                effective = (result["factor_parameters"]["service_factor"]
                             if basic["family"] == "impact" and combination["usage"] == "service" else nominal)
                trace = candidate["coefficient_trace"]
                expected_trace = {"usage": combination["usage"], "nominal_coefficient": nominal,
                                  "effective_factor": effective, "applied_factor": effective,
                                  "factor_applications": 1, "remaining_multiplier": 1}
                if any(type(trace[key]) is bool or trace[key] != value for key, value in expected_trace.items()):
                    raise InputError(f"{location}.coefficient_trace: 解決済み係数は1回適用が必要です")
                if basic["family"] in ("train", "impact"):
                    details, provenance = candidate["loads"]["details"], candidate["loads"]["provenance"]
                    if (details["track"] != expected_track or details["effective_factor"] != effective or
                            provenance["remaining_multiplier"] != 1 or
                            (basic["family"] == "impact" and details["usage"] != combination["usage"]) or
                            (basic["family"] == "train" and provenance["factor_applications"] != 1)):
                        raise InputError(f"{location}.loads: 解決作用の用途・適用係数が出典と不一致です")
                actual = action_vector(candidate["loads"], basic["spring_case"], frame, location)
                if not 9 <= define_id <= 12:
                    source = action_vector(basic["loads"], basic["spring_case"], frame)
                    # A native negative case reverses every component. Horizontal
                    # cases therefore cannot quietly acquire vertical loads.
                    if define_id >= 13 and any(value for key, value in source.items() if key[-1] in ("ty", "gy")):
                        raise InputError(f"{location}: 正負水平ケースに鉛直荷重を混在できません")
                    _compare(actual, {key: value * nominal * (1 if signed > 0 else -1)
                                      for key, value in source.items()}, location)
    return indexed


def _merge_actions(candidates, frame):
    """Sum physical components at their existing application points."""
    merged = {"points": [], "line_loads": [], "units": dict(ACTION_UNITS)}
    points, lines = {}, {}
    for candidate in candidates:
        loads = candidate["loads"]
        actions(loads, frame)
        for point in loads["points"]:
            key = point["anchor"], point["node_id"]
            target = points.setdefault(key, {"anchor": key[0], "node_id": key[1], "N": 0, "H": 0, "M": 0})
            for axis in ("N", "H", "M"):
                target[axis] += point[axis]
        for line in loads["line_loads"]:
            key = line["anchor"], tuple(line["member_ids"])
            if key not in lines:
                lines[key] = {**deepcopy(line), "qN": 0, "qH": 0}
            for axis in ("qN", "qH"):
                lines[key][axis] += line[axis]
    merged["points"], merged["line_loads"] = list(points.values()), list(lines.values())
    return merged


def build_frameweb_transverse_cases(result):
    validate_case_model(result)
    indexed = _validate_components(result)
    basics, frame = result["basic_cases"], result["frame"]
    auxiliary, mappings, replacements = [], [], {}
    for load_id, define_id, track, usage, role, consumers, original_ids in AUXILIARY_CASES:
        sources, merged, traces = [], None, None
        for combination_id in consumers:
            components = indexed[combination_id]
            present = [identifier in components for identifier in original_ids]
            if any(present) != all(present):
                raise InputError(f"combinations[{combination_id}]: L/I片方だけの合成は未対応です")
            chosen = []
            for identifier in original_ids if all(present) else ():
                candidates = components[identifier]["candidates"]
                candidate = next((row for row in candidates if basics[row["basic_case_id"] - 1].get("track") == track), None)
                if candidate is None or basics[candidate["basic_case_id"] - 1]["spring_case"] != 2:
                    raise InputError(f"auxiliary[{load_id}]: 同じ線・支持のL/I候補が必要です")
                chosen.append(candidate)
                component_index = list(components).index(identifier)
                candidate_index = candidates.index(candidate)
                sources.append({"combination_id": combination_id, "define_case_id": identifier,
                                "basic_case_id": candidate["basic_case_id"],
                                "source_path": f"combinations[{combination_id - 1}].resolved_components[{component_index}].candidates[{candidate_index}]",
                                "coefficient_trace": deepcopy(candidate["coefficient_trace"])})
            current = _merge_actions(chosen, frame)
            current_traces = [row["coefficient_trace"] for row in chosen]
            if merged is not None and (current != merged or current_traces != traces):
                raise InputError(f"auxiliary[{load_id}]: 同じ用途の解決作用・係数が衝突しています")
            merged, traces = current, current_traces
            if chosen:
                replacements[combination_id] = define_id
        auxiliary.append({"id": load_id, "spring_case": 2, "symbol": f"LI:{role}:{track}",
                          "label": f"列車＋衝撃 {usage} {role} {track} (解決済み)", "loads": merged})
        mappings.append({"native_load_id": load_id, "native_define_id": define_id,
                         "family": "train+impact", "track": track, "usage": usage, "coefficient_role": role,
                         "spring_case": 2, "native_factor": 1, "combination_ids": list(consumers),
                         "sources": sources, "loads": deepcopy(merged)})
    define = {str(i): {"row": i, **{f"C{j}": value for j, value in enumerate(refs, 1)}}
              for i, refs in enumerate(DEFINE_REFERENCES, 1)}
    combine, combination_mapping = {}, []
    for combination in result["combinations"]:
        identifier = combination["id"]
        row = {"row": identifier, "name": combination["label"]}
        correspondence = []
        for original_id, nominal in enumerate(combination["coefficients"], 1):
            helper = replacements.get(identifier) if 9 <= original_id <= 12 and nominal else None
            if 9 <= original_id <= 12 and nominal and helper is None:
                raise InputError(f"combinations[{identifier}]: 未対応のL/I用途です")
            native_id, factor = (helper, 1) if helper is not None else (original_id, nominal)
            if factor:
                row[f"C{native_id}"] = factor
            correspondence.append({"define_case_id": original_id, "native_define_id": native_id,
                                   "nominal_factor": nominal, "native_factor": factor,
                                   "source_path": f"combinations[{identifier - 1}].coefficients[{original_id - 1}]"})
        combine[str(identifier)] = row
        combination_mapping.append({"id": identifier, "key": combination["key"],
                                    "example_pdf_page": 14, "p7_pdf_page": 11, "components": correspondence})
    pickup = {str(source["id"]): {"row": source["id"], "name": source["label"],
              **{f"C{i}": value for i, value in enumerate(source["combination_ids"], 1)}}
              for source in result["extraction_cases"]}
    basic_defines = {abs(ref): i for i, refs in enumerate(DEFINE_REFERENCES[:15], 1) for ref in refs}
    mapping = {"basic_cases": [{"basic_case_id": b["id"], "native_load_id": b["id"],
                                "native_define_id": basic_defines[b["id"]], "key": b["key"],
                                "spring_case": b["spring_case"], "example_pdf_page": 13,
                                "p7_pdf_page": 10, "source_path": f"basic_cases[{b['id'] - 1}].loads"} for b in basics],
               "auxiliary_cases": mappings, "combinations": combination_mapping,
               "pickups": [{"id": p["id"], "combination_ids": list(p["combination_ids"]),
                            "example_pdf_page": 15, "p7_pdf_page": 12,
                            "source_path": f"extraction_cases[{p['id'] - 1}]"} for p in result["extraction_cases"]]}
    return FrameWebCases(auxiliary, define, combine, pickup, mapping)


def validate_available_cases(document):
    """Reject envelopes the specified solver cannot form after empty cases skip.

    A zero original case such as WP3 can be an additive zero. It cannot serve
    as the only source of a requested combination, or disappear as one of the
    alternatives in an active envelope. Native case IDs remain unchanged.
    """
    available_loads = {identifier for identifier, case in document["load"].items()
                       if case.get("load_node") or case.get("load_member")}
    used_defines = {key[1:] for row in document["combine"].values()
                    for key, factor in row.items() if key.startswith("C") and factor}
    available_defines = set()
    for identifier, row in document["define"].items():
        available = [str(abs(ref)) in available_loads for key, ref in row.items() if key.startswith("C")]
        if any(available):
            available_defines.add(identifier)
        if identifier in used_defines and any(available) and not all(available):
            raise InputError(f"native.define.{identifier}: ソルバーがゼロ候補を省略して包絡集合が変わるため出力できません")
    available_combinations = {identifier for identifier, row in document["combine"].items()
                              if any(key[1:] in available_defines and factor
                                     for key, factor in row.items() if key.startswith("C"))}
    for pickup_id, row in document["pickup"].items():
        for key, reference in row.items():
            if key.startswith("C") and str(reference) not in available_combinations:
                raise InputError(f"native.combine.{reference}: 全ゼロ作用はソルバーで結果が省略され、PICKUP {pickup_id}が参照できません")


def validate_action_vectors(result, document, native_vector):
    """Compare every legal candidate state, with independent LF/W signs."""
    count = 0
    for combination in result["combinations"]:
        canonical_states = []
        for candidates in product(*(component["candidates"] for component in combination["resolved_components"])):
            tracks = {row["direction"] for row in candidates if row.get("compatibility_group") == "single_track"}
            if len(tracks) > 1:
                continue
            vector = {}
            for row in candidates:
                basic = result["basic_cases"][row["basic_case_id"] - 1]
                for key, value in action_vector(row["loads"], basic["spring_case"], result["frame"]).items():
                    vector[key] = vector.get(key, 0) + value
            canonical_states.append(vector)
        native_states = []
        terms = []
        for column, factor in document["combine"][str(combination["id"])].items():
            if column.startswith("C"):
                definition = document["define"][column[1:]]
                terms.append([(ref, factor) for key, ref in definition.items() if key.startswith("C")])
        for choices in product(*terms):
            vector = {}
            for ref, factor in choices:
                for key, value in native_vector(document["load"][str(abs(ref))]).items():
                    vector[key] = vector.get(key, 0) + value * factor * (1 if ref > 0 else -1)
            native_states.append(vector)
        if len(canonical_states) != len(native_states):
            raise InputError(f"combinations[{combination['id']}]: 合法候補の状態数が一致しません")
        # Match a multiset, preserving equal-valued but distinct legal choices.
        unmatched = list(native_states)
        for expected in canonical_states:
            for index, actual in enumerate(unmatched):
                if all(abs(actual.get(key, 0) - expected.get(key, 0)) <=
                       1e-10 + 1e-12 * max(abs(actual.get(key, 0)), abs(expected.get(key, 0)))
                       for key in actual.keys() | expected.keys()):
                    unmatched.pop(index)
                    break
            else:
                raise InputError(f"combinations[{combination['id']}]: 支持・荷重点別の合法状態を再現できません")
        count += len(canonical_states)
    return count
