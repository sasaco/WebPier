"""Stable native cases for the versioned, usage-resolved 0610 action model.

The PDF coefficients are nominal. In particular, rounded train moments and
usage-specific impact forces must be copied from resolved components, never
recovered by division or multiplied by the nominal factor a second time.
"""

from copy import deepcopy
from dataclasses import dataclass

from .inputs import InputError
from .longitudinal_example2_cases import validate_case_model


# Native ID, original basic ID, usage, and the complete set of consumers.
AUXILIARY_CASES = (
    (21, 9, "service", (7, 15, 16)),
    (22, 10, "service", (5,)),
    (23, 10, "ultimate", (2, 3, 8, 11, 12)),
    (24, 10, "maximum", (1, 10)),
    (25, 11, "service", (7, 15, 16)),
    (26, 12, "service", (5,)),
    (27, 12, "ultimate", (3, 8, 12)),
    (28, 12, "maximum", (1, 10)),
)
PICKUP_GROUPS = ((1, 2, 3, 4), (5,), (6,), (7,), (8, 9), (10, 11, 12, 13), (14,), (15, 16))
_BASIC_KEYS = (
    "dead_fixed", "dead_additional", "buoyancy_high", "buoyancy_normal", "buoyancy_low",
    "snow_2_year", "snow_10_year", "snow_30_year", "train_single", "train_double",
    "impact_single", "impact_double", "rail_service_08", "rail_service_10",
    "rail_braking_safety", "rail_max_braking_safety", "rail_braking_max_safety",
    "rail_safety", "rail_braking_recovery", "rail_recovery",
)
_COMBINATION_KEYS = (
    "body_failure_train_max", "body_failure_braking_max", "body_failure_rail_max",
    "body_failure_snow_max", "body_service_permanent_variable", "body_service_permanent",
    "body_service_variable", "body_recovery_train_max", "body_recovery_snow_max",
    "foundation_stability_train_max", "foundation_stability_braking_max",
    "foundation_stability_rail_max", "foundation_stability_snow_max",
    "foundation_support_long_term", "foundation_support_short_term_low",
    "foundation_support_short_term_high",
)


@dataclass(frozen=True)
class FrameWebCases:
    auxiliary: list[dict]
    define: dict
    combine: dict
    pickup: dict
    mapping: dict


def _components(combination: dict) -> list[dict]:
    rows = combination["resolved_components"]
    if (not isinstance(rows, list) or len(rows) != 20 or
            [row["basic_case_id"] for row in rows] != list(range(1, 21))):
        raise InputError(f"combinations[{combination['id']}].resolved_components: 全20基本作用が必要です")
    return rows


def build_frameweb_cases(result: dict) -> FrameWebCases:
    """Construct case references and copy auxiliary actions without recalculation."""
    validate_case_model(result)
    basics, combinations = result["basic_cases"], result["combinations"]
    for identifier, (basic, key) in enumerate(zip(basics, _BASIC_KEYS, strict=True), 1):
        spring = 2 if identifier in (9, 10, 11, 12, 15, 16, 17, 19) else 1
        if basic["key"] != key or basic["spring_case"] != spring:
            raise InputError(f"basic_cases[{identifier}]: 作用の意味または支持ばねが既知の版と一致しません")
        if identifier in (9, 10, 11, 12):
            track = "single" if identifier in (9, 11) else "double"
            if basic.get("track") != track:
                raise InputError(f"basic_cases[{identifier}].track: 単複線の対応が一致しません")
    for combination, key in zip(combinations, _COMBINATION_KEYS, strict=True):
        if combination["key"] != key or combination.get("coefficient_kind") != "nominal":
            raise InputError(f"combinations[{combination['id']}]: 既知の名目ケース定義が必要です")
        for row, nominal in zip(_components(combination), combination["coefficients"], strict=True):
            if row["nominal_factor"] != nominal or row["residual_factor"] != (1 if nominal else 0):
                raise InputError(f"combinations[{combination['id']}].resolved_components: 名目係数または残係数が不整合です")
            if row["basic_case_id"] in (9, 10, 11, 12):
                resolution = row["resolution"]
                if resolution.get("included") is not bool(nominal):
                    raise InputError("resolved_components.resolution.included: 名目係数と一致しません")

    auxiliary, auxiliary_mapping, replacements = [], [], {}
    for native_id, basic_id, usage, consumers in AUXILIARY_CASES:
        source = basics[basic_id - 1]
        components = [combinations[identifier - 1]["resolved_components"][basic_id - 1] for identifier in consumers]
        first = components[0]
        factor = first["resolution"]["effective_train_factor"]
        for consumer, component in zip(consumers, components, strict=True):
            resolution = component["resolution"]
            if resolution["usage"] != usage or resolution["track"] != source["track"]:
                raise InputError(f"combinations[{consumer}]: 補助ケースの用途・単複線が一致しません")
            if component["loads"] != first["loads"] or resolution["effective_train_factor"] != factor:
                raise InputError(f"auxiliary[{native_id}]: 同じ意味の解決作用・有効係数が衝突しています")
            expected_factor = (component["nominal_factor"] if basic_id in (9, 10) else
                               result["factors"][{"service": "service_factor", "ultimate": "ultimate_effective",
                                                  "maximum": "maximum_train_effective"}[usage]])
            if factor != expected_factor:
                raise InputError(f"auxiliary[{native_id}]: 解決時の有効係数が不整合です")
            replacements[consumer, basic_id] = native_id
        label = {"service": "使用性", "ultimate": "安全性・復旧性", "maximum": "最大"}[usage]
        auxiliary.append({**deepcopy(source), "id": native_id,
                          "symbol": f"{source['symbol']}:{usage}", "label": f"{source['label']} ({label} 解決済み)",
                          "loads": deepcopy(first["loads"])})
        auxiliary_mapping.append({
            "native_load_id": native_id, "native_define_id": native_id, "basic_case_id": basic_id,
            "family": "train" if basic_id in (9, 10) else "impact", "track": source["track"],
            "usage": usage, "spring_case": source["spring_case"], "effective_factor": factor,
            "combination_ids": list(consumers), "loads": deepcopy(first["loads"]),
            "source_paths": [f"combinations[{identifier - 1}].resolved_components[{basic_id - 1}]" for identifier in consumers],
        })

    define = {}
    for source in result["define_cases"]:
        identifier = source["id"]
        define[str(identifier)] = {"row": identifier, **{
            f"C{index}": value for index, value in enumerate(source["signed_basic_case_ids"], 1)}}
    define.update({str(identifier): {"row": identifier, "C1": identifier}
                   for identifier, *_ in AUXILIARY_CASES})
    combine, combination_mapping = {}, []
    for combination in combinations:
        identifier = combination["id"]
        row = {"row": identifier, "name": combination["label"]}
        correspondence = []
        for component in combination["resolved_components"]:
            basic_id, nominal = component["basic_case_id"], component["nominal_factor"]
            native_id = replacements.get((identifier, basic_id), basic_id)
            if basic_id in (9, 10, 11, 12) and nominal and native_id == basic_id:
                raise InputError(f"combinations[{identifier}]: 未対応の列車・衝撃用途です")
            # A designated auxiliary already contains the complete resolved
            # action, including a nominal-zero action. Keep its reference at
            # one so a zero variable combination can still produce a result.
            coefficient = 1 if native_id > 20 else nominal
            if coefficient:
                row[f"C{native_id}"] = coefficient
            correspondence.append({
                "basic_case_id": basic_id, "native_define_id": native_id,
                "nominal_factor": nominal, "native_factor": coefficient,
                "effective_factor": component["resolution"].get("effective_train_factor", nominal),
                "source_path": f"combinations[{identifier - 1}].resolved_components[{basic_id - 1}]",
            })
        combine[str(identifier)] = row
        combination_mapping.append({"id": identifier, "key": combination["key"],
                                    "example_pdf_page": combination["source_page"], "webpier_pdf_page": 7,
                                    "components": correspondence})
    pickup = {}
    for source, expected in zip(result["extraction_cases"], PICKUP_GROUPS, strict=True):
        identifier = source["id"]
        if source["combination_ids"] != list(expected):
            raise InputError(f"extraction_cases[{identifier}]: 抽出の所属群が既知の版と一致しません")
        pickup[str(identifier)] = {"row": identifier, "name": source["label"], **{
            f"C{index}": value for index, value in enumerate(expected, 1)}}
    mapping = {
        "basic_cases": [{"basic_case_id": source["id"], "native_load_id": source["id"],
                         "native_define_id": source["id"], "symbol": source["symbol"],
                         "spring_case": source["spring_case"], "example_pdf_page": source["source_page"],
                         "webpier_pdf_page": 6, "source_path": f"basic_cases[{source['id'] - 1}]"}
                        for source in basics],
        "auxiliary_cases": auxiliary_mapping, "combinations": combination_mapping,
        "pickups": [{"id": source["id"], "combination_ids": list(source["combination_ids"]),
                     "example_pdf_page": source["source_page"], "webpier_pdf_page": 8,
                     "source_path": f"extraction_cases[{source['id'] - 1}]"}
                    for source in result["extraction_cases"]],
    }
    return FrameWebCases(auxiliary, define, combine, pickup, mapping)
