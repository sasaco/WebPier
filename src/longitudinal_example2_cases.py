"""0610 nonseismic case definitions from Example2, independent of runtime files.

The coefficients are nominal definitions. Usage-specific pier impact must be
resolved separately; this table is not a multiplier for an already-resolved I.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .inputs import InputError
from .reaction_math import excel_round as R


CASE_MODEL_VERSION = "example2-nonseismic-pier-impact-v1"

# Example橋脚2/08_線路.pdf, physical page 9. IDs follow the source row order.
# key, source symbol, source label, spring, action domain, track (if applicable).
_BASIC_CASES = (
    ("dead_fixed", "D1", "固定死荷重", 1, "vertical", None),
    ("dead_additional", "D2", "付加死荷重", 1, "vertical", None),
    ("buoyancy_high", "WP1", "浮力 高水位", 1, "vertical", None),
    ("buoyancy_normal", "WP2", "浮力 平水位", 1, "vertical", None),
    ("buoyancy_low", "WP3", "浮力 低水位", 1, "vertical", None),
    ("snow_2_year", "S2", "雪荷重 2年確率", 1, "vertical", None),
    ("snow_10_year", "S10", "雪荷重 10年確率", 1, "vertical", None),
    ("snow_30_year", "S30", "雪荷重 30年確率", 1, "vertical", None),
    ("train_single", "L1", "列車荷重 単線", 2, "vertical", "single"),
    ("train_double", "L2", "列車荷重 複線", 2, "vertical", "double"),
    ("impact_single", "I1", "衝撃荷重 安全性・復旧性 単線", 2, "vertical", "single"),
    ("impact_double", "I2", "衝撃荷重 安全性・復旧性 複線", 2, "vertical", "double"),
    ("rail_service_08", "0.8LR", "ロングレール縦荷重 使用性 0.8LR", 1, "horizontal", None),
    ("rail_service_10", "1.0LR", "ロングレール縦荷重 使用性 1.0LR", 1, "horizontal", None),
    ("rail_braking_safety", "1.0LR+1.23B", "ロングレール+制動 安全性 1.0LR+1.23B", 2, "horizontal", None),
    ("rail_max_braking_safety", "1.1LR+1.23B", "ロングレール+制動 安全性 1.1LR+1.23B", 2, "horizontal", None),
    ("rail_braking_max_safety", "1.0LR+1.35B", "ロングレール+制動 安全性 1.0LR+1.35B", 2, "horizontal", None),
    ("rail_safety", "1.0LR", "ロングレール縦荷重 安全性 1.0LR", 1, "horizontal", None),
    ("rail_braking_recovery", "1.0LR+1.23B", "ロングレール+制動 復旧性 1.0LR+1.23B", 2, "horizontal", None),
    ("rail_recovery", "1.0LR", "ロングレール縦荷重 復旧性 1.0LR", 1, "horizontal", None),
)

# Public horizontal labels describe the adopted source family, without turning
# the document's fixed 1.23/1.35 into an assertion about current input factors.
_PUBLIC_HORIZONTAL = {
    15: ("1.0LR+ρB", "ロングレール+制動 安全性 1.0LR+ρB"),
    16: ("1.1LR+ρB", "ロングレール+制動 安全性 1.1LR+ρB"),
    17: ("1.0LR+ρmaxB", "ロングレール+制動 安全性 1.0LR+ρmaxB"),
    19: ("1.0LR+B（側別係数）", "ロングレール+制動 復旧性 1.0LR+B（側別係数）"),
}

# Example2 page 10: key, label, scope, followed by all 20 coefficients per case.
_COMBINATIONS = (
    ("body_failure_train_max", "安全性 破壊 列車最大", "body"),
    ("body_failure_braking_max", "安全性 破壊 制動最大", "body"),
    ("body_failure_rail_max", "安全性 破壊 ロング最大", "body"),
    ("body_failure_snow_max", "安全性 破壊 雪最大", "body"),
    ("body_service_permanent_variable", "使用性・耐久性 ひび割れ 縁応力度", "body"),
    ("body_service_permanent", "使用性・耐久性 ひび割れ 永久荷重", "body"),
    ("body_service_variable", "使用性・耐久性 ひび割れ 変動荷重", "body"),
    ("body_recovery_train_max", "復旧性 損傷 列車最大", "body"),
    ("body_recovery_snow_max", "復旧性 損傷 雪最大", "body"),
    ("foundation_stability_train_max", "安全性 地盤の安定 列車最大", "foundation"),
    ("foundation_stability_braking_max", "安全性 地盤の安定 制動最大", "foundation"),
    ("foundation_stability_rail_max", "安全性 地盤の安定 ロング最大", "foundation"),
    ("foundation_stability_snow_max", "安全性 地盤の安定 雪最大", "foundation"),
    ("foundation_support_long_term", "使用性 長期", "foundation"),
    ("foundation_support_short_term_low", "使用性 短期 低水位", "foundation"),
    ("foundation_support_short_term_high", "使用性 短期 高水位", "foundation"),
)
_U, _MAX, _S, _SI = "ultimate", "maximum", "service", "service_impact"
_COEFFICIENTS = (
    (1.1, 1.2, 0, 0, 0, 0, 1, 0, 0, _MAX, 0, _MAX, 0, 0, 1, 0, 0, 0, 0, 0),
    (1.1, 1.2, 0, 0, 0, 0, 1, 0, 0, _U, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0),
    (1.1, 1.2, 0, 0, 0, 0, 1, 0, 0, _U, 0, _U, 0, 0, 0, 1, 0, 0, 0, 0),
    (1.1, 1.2, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0),
    (1, 1, 0, 0, 0, 1, 0, 0, 0, _S, 0, _SI, 0, 1, 0, 0, 0, 0, 0, 0),
    (1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0),
    (0, 0, 0, 0, 0, 0, 0, 0, _S, 0, _SI, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    (1, 1, 0, 0, 0, 0, 1, 0, 0, _U, 0, _U, 0, 0, 0, 0, 0, 0, 1, 0),
    (1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1),
    (1.1, 1.2, 0, 0, 1, 0, 1, 0, 0, _MAX, 0, _MAX, 0, 0, 1, 0, 0, 0, 0, 0),
    (1.1, 1.2, 0, 0, 1, 0, 1, 0, 0, _U, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0),
    (1.1, 1.2, 0, 0, 1, 0, 1, 0, 0, _U, 0, _U, 0, 0, 0, 1, 0, 0, 0, 0),
    (1.1, 1.2, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0),
    (1, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    (1, 1, 0, 0, 1, 1, 0, 0, _S, 0, _SI, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    (1, 1, 1, 0, 0, 1, 0, 0, _S, 0, _SI, 0, 0, 0, 0, 0, 0, 0, 0, 0),
)

# Example2 page 11: extraction is a reference grouping, not a response solver.
_EXTRACTIONS = (
    ("failure", "安全性（破壊）", (1, 2, 3, 4)),
    ("permanent_variable", "永久＋変動", (5,)),
    ("permanent", "永久作用", (6,)),
    ("variable", "変動作用", (7,)),
    ("recovery", "復旧性（損傷）", (8, 9)),
    ("stability", "安全性（安定）", (10, 11, 12, 13)),
    ("support_long_term", "長期支持性能", (14,)),
    ("support_short_term", "短期支持性能", (15, 16)),
)


def _nonnegative_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{path}: 0以上の有限数値が必要です")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise InputError(f"{path}: 0以上の有限数値が必要です") from exc
    if not math.isfinite(result) or result < 0:
        raise InputError(f"{path}: 0以上の有限数値が必要です")
    return result


def build_case_model(*, ultimate_factor: float, service_factor: float) -> dict[str, Any]:
    """Build fresh case definitions, preserving source and adopted labels."""
    ultimate = _nonnegative_number(ultimate_factor, "ultimate_factor")
    service = _nonnegative_number(service_factor, "service_factor")
    try:
        factors = {_U: R(ultimate, 2), _MAX: R(ultimate * 1.1, 2),
                   _S: service, _SI: 0.75 * service}
    except InputError as exc:
        raise InputError(f"ultimate_factor: {exc}") from exc
    basics = []
    defines = []
    for identifier, (key, source_symbol, source_label, spring, domain, track) in enumerate(_BASIC_CASES, 1):
        symbol, label = _PUBLIC_HORIZONTAL.get(identifier, (source_symbol, source_label))
        basic = {"id": identifier, "key": key, "symbol": symbol, "label": label,
                 "source_symbol": source_symbol, "source_label": source_label,
                 "spring_case": spring, "action_domain": domain, "source_page": 9}
        if track is not None:
            basic["track"] = track
        basics.append(basic)
        # Define uses SS2/SS10/SS30; the coefficient table uses S2/S10/S30.
        define_source_symbol = "S" + source_symbol if identifier in (6, 7, 8) else source_symbol
        defines.append({
            "id": identifier, "basic_case_id": identifier,
            "symbol": symbol if identifier in _PUBLIC_HORIZONTAL else define_source_symbol,
            "source_symbol": define_source_symbol, "source_label": source_label,
            "signed_basic_case_ids": [identifier, -identifier] if domain == "horizontal" else [identifier],
            "sign_scope": "horizontal_action_only" if domain == "horizontal" else "positive_only",
            "source_page": 9,
        })
    combinations = [
        {"id": identifier, "key": key, "label": label, "source_label": label,
         "scope": scope, "source_page": 10, "coefficient_kind": "nominal",
         "coefficients": [factors[value] if isinstance(value, str) else value for value in coefficients]}
        for identifier, ((key, label, scope), coefficients) in enumerate(zip(_COMBINATIONS, _COEFFICIENTS, strict=True), 1)
    ]
    extractions = [
        {"id": identifier, "key": key, "label": label, "source_label": label,
         "combination_ids": list(combination_ids), "source_page": 11}
        for identifier, (key, label, combination_ids) in enumerate(_EXTRACTIONS, 1)
    ]
    model = {
        "case_model_version": CASE_MODEL_VERSION, "coefficient_kind": "nominal",
        "factors": {"ultimate_factor": ultimate, "service_factor": service,
                    "ultimate_effective": factors[_U], "maximum_train_effective": factors[_MAX],
                    "service_impact_nominal": factors[_SI]},
        "basic_cases": basics, "combinations": combinations,
        "define_cases": defines, "extraction_cases": extractions,
    }
    validate_case_model(model)
    return model


def _records(model: Mapping[str, Any], name: str, count: int, *, keyed: bool = True) -> list[dict]:
    rows = model.get(name)
    if not isinstance(rows, list) or len(rows) != count:
        raise InputError(f"{name}: {count}行が必要です")
    if not all(isinstance(row, dict) for row in rows):
        raise InputError(f"{name}: 各行はオブジェクトである必要があります")
    identifiers = [row.get("id") for row in rows]
    if any(type(identifier) is not int for identifier in identifiers) or identifiers != list(range(1, count + 1)):
        raise InputError(f"{name}: IDは重複・欠落のない1～{count}の順序が必要です")
    if keyed:
        keys = [row.get("key") for row in rows]
        if any(not isinstance(key, str) or not key for key in keys) or len(set(keys)) != count:
            raise InputError(f"{name}: 意味付きkeyは空欄・重複を許容しません")
    return rows


def validate_case_model(model: Mapping[str, Any]) -> None:
    """Reject missing or ambiguous references before any action resolution."""
    if not isinstance(model, Mapping) or model.get("case_model_version") != CASE_MODEL_VERSION:
        raise InputError("case_model_version: 0610正規ケース定義の版が一致しません")
    basics = _records(model, "basic_cases", 20)
    combinations = _records(model, "combinations", 16)
    defines = _records(model, "define_cases", 20, keyed=False)
    extractions = _records(model, "extraction_cases", 8)
    by_basic = {row["id"]: row for row in basics}
    for row in basics:
        identifier = row["id"]
        domain = "vertical" if identifier <= 12 else "horizontal"
        if row.get("action_domain") != domain:
            raise InputError(f"basic_cases[{identifier}].action_domain: 基本作用の方向が一致しません")
        if type(row.get("spring_case")) is not int or row["spring_case"] not in (1, 2):
            raise InputError(f"basic_cases[{identifier}].spring_case: ばね番号1または2が必要です")
    for row in combinations:
        path = f"combinations[{row['id']}].coefficients"
        coefficients = row.get("coefficients")
        if not isinstance(coefficients, list) or len(coefficients) != 20:
            raise InputError(f"{path}: 20基本作用の係数が必要です")
        for index, value in enumerate(coefficients, 1):
            _nonnegative_number(value, f"{path}[{index}]")
    defined_ids = []
    for row in defines:
        path = f"define_cases[{row['id']}]"
        reference = row.get("basic_case_id")
        if type(reference) is not int or reference not in by_basic:
            raise InputError(f"{path}.basic_case_id: 未知の基本作用です")
        defined_ids.append(reference)
        horizontal = by_basic[reference]["action_domain"] == "horizontal"
        expected = [reference, -reference] if horizontal else [reference]
        signed = row.get("signed_basic_case_ids")
        if (not isinstance(signed, list) or any(type(value) is not int for value in signed)
                or signed != expected):
            raise InputError(f"{path}.signed_basic_case_ids: 水平作用だけに正負の展開が必要です")
        if row.get("sign_scope") != ("horizontal_action_only" if horizontal else "positive_only"):
            raise InputError(f"{path}.sign_scope: 作用方向と符号展開が一致しません")
    if defined_ids != list(range(1, 21)):
        raise InputError("define_cases: 全基本作用を同番号で重複なく参照する必要があります")
    combination_ids = {row["id"] for row in combinations}
    extracted_ids = []
    for row in extractions:
        references = row.get("combination_ids")
        if (not isinstance(references, list) or not references
                or any(type(value) is not int or value not in combination_ids for value in references)):
            raise InputError(f"extraction_cases[{row['id']}].combination_ids: 有効な組合せIDが必要です")
        extracted_ids.extend(references)
    if sorted(extracted_ids) != list(range(1, 17)):
        raise InputError("extraction_cases: 全16組合せを過不足なく参照する必要があります")
