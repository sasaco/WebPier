"""Nonseismic transverse definitions from Example2 pages 13-15.

Coefficients address the 15 Define cases, not the 17 basic actions. This
module defines candidates and references; it does not select a governing
response, combine candidate alternatives, or solve a structural model.
"""

import math

from .inputs import InputError
from .reaction_math import excel_round


CASE_MODEL_VERSION = "example2-nonseismic-pier-impact-v1"
SOURCE_SHA256 = "b6a7f5658b9f98ee8a7d6b29691edcb0209bc7455fa8309d4e3a2e16605474de"

# Literal PDF identities. The fixture is maintained separately and is never
# loaded by this module, either at import time or during a calculation.
_BASIC_ROWS = (
    ("dead_fixed", "固定死荷重", "dead_fixed", {}),
    ("dead_additional", "付加死荷重", "dead_additional", {}),
    ("buoyancy_high", "浮力 高水位", "buoyancy", {"water_level": "high"}),
    ("buoyancy_normal", "浮力 平水位", "buoyancy", {"water_level": "normal"}),
    ("buoyancy_low", "浮力 低水位", "buoyancy", {"water_level": "low"}),
    ("snow_2_year", "雪荷重 2年確率", "snow", {"return_period_years": 2}),
    ("snow_10_year", "雪荷重 10年確率", "snow", {"return_period_years": 10}),
    ("snow_30_year", "雪荷重 30年確率", "snow", {"return_period_years": 30}),
    ("train_up", "列車荷重 単線 上り", "train", {"track": "up"}),
    ("train_down", "列車荷重 単線 下り", "train", {"track": "down"}),
    ("train_double", "列車荷重 複線", "train", {"track": "double"}),
    ("impact_up", "衝撃荷重 安全性・復旧性 単線 上り", "impact", {"track": "up"}),
    ("impact_down", "衝撃荷重 安全性・復旧性 単線 下り", "impact", {"track": "down"}),
    ("impact_double", "衝撃荷重 安全性・復旧性 複線", "impact", {"track": "double"}),
    ("vehicle_lateral", "車両横荷重", "vehicle_lateral", {}),
    ("wind_with_train", "風荷重 列車荷重がある場合", "wind", {"train_present": True}),
    ("wind_without_train", "風荷重 列車荷重がない場合", "wind", {"train_present": False}),
)

# key, Define-page symbol, coefficient-page symbol, signed basic alternatives.
_DEFINE_ROWS = (
    ("dead_fixed", "D1", "D1", (1,)),
    ("dead_additional", "D2", "D2", (2,)),
    ("buoyancy_high", "WP1", "WP1", (3,)),
    ("buoyancy_normal", "WP2", "WP2", (4,)),
    ("buoyancy_low", "WP3", "WP3", (5,)),
    ("snow_2_year", "SS2", "S2", (6,)),
    ("snow_10_year", "SS10", "S10", (7,)),
    ("snow_30_year", "SS30", "S30", (8,)),
    ("train_single", "L1", "L1", (9, 10)),
    ("train_double", "L3", "L2", (11,)),
    ("impact_single", "I1", "I1", (12, 13)),
    ("impact_double", "I3", "I2", (14,)),
    ("vehicle_lateral", "LF", "LF", (15, -15)),
    ("wind_with_train", "W1", "W1", (16, -16)),
    ("wind_without_train", "W2", "W2", (17, -17)),
)

# Each literal vector follows Define IDs 1..15. Source dashes are zero.
_COMBINATION_ROWS = (
    ("body_failure_train_max", "安全性 破壊 列車最大", (1.1, 1.2, 0, 0, 0, 0, 1, 0, 0, 1.35, 0, 1.35, 1.23, 1, 0)),
    ("body_failure_lateral_max", "安全性 破壊 車横最大", (1.1, 1.2, 0, 0, 0, 0, 1, 0, 0, 1.23, 0, 1.23, 1.35, 1, 0)),
    ("body_failure_wind_max", "安全性 破壊 風最大", (1.1, 1.2, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1.2)),
    ("body_failure_snow_max", "安全性 破壊 雪最大", (1.1, 1.2, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0)),
    ("body_service_permanent_variable", "使用性・耐久性 ひび割れ 縁応力度", (1, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0.75, 0, 0, 0)),
    ("body_service_permanent", "使用性・耐久性 ひび割れ 永久荷重", (1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0)),
    ("body_service_variable", "使用性・耐久性 ひび割れ 変動荷重", (0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0.75, 0, 0, 0, 0)),
    ("body_recovery_train_max", "復旧性 損傷 列車最大", (1, 1, 0, 0, 0, 0, 1, 0, 0, 1.23, 0, 1.23, 1.23, 1, 0)),
    ("body_recovery_snow_max", "復旧性 損傷 雪最大", (1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0)),
    ("foundation_stability_train_max", "安全性 地盤の安定 列車最大", (1.1, 1.2, 0, 0, 1, 0, 1, 0, 0, 1.35, 0, 1.35, 1.23, 1, 0)),
    ("foundation_stability_lateral_max", "安全性 地盤の安定 車横最大", (1.1, 1.2, 0, 0, 1, 0, 1, 0, 0, 1.23, 0, 1.23, 1.35, 1, 0)),
    ("foundation_stability_wind_max", "安全性 地盤の安定 風最大", (1.1, 1.2, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1.2)),
    ("foundation_stability_snow_max", "安全性 地盤の安定 雪最大", (1.1, 1.2, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0)),
    ("foundation_support_long_term", "使用性 長期", (1, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0)),
    ("foundation_support_short_term_low", "使用性 短期 低水位", (1, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0.75, 0, 0, 0, 0)),
    ("foundation_support_short_term_high", "使用性 短期 高水位", (1, 1, 1, 0, 0, 1, 0, 0, 1, 0, 0.75, 0, 0, 0, 0)),
)

_EXTRACTION_ROWS = (
    ("failure", "安全性（破壊）", (1, 2, 3, 4)),
    ("permanent_variable", "永久＋変動", (5,)),
    ("permanent", "永久作用", (6,)),
    ("variable", "変動作用", (7,)),
    ("recovery", "復旧性（損傷）", (8, 9)),
    ("stability", "安全性（安定）", (10, 11, 12, 13)),
    ("support_long_term", "長期支持性能", (14,)),
    ("support_short_term", "短期支持性能", (15, 16)),
)


def _factor(value, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{path}: 非負の有限数値が必要です")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise InputError(f"{path}: 数値範囲を超えています") from exc
    if not math.isfinite(number) or number < 0:
        raise InputError(f"{path}: 非負の有限数値が必要です")
    return number


def _parameters(ultimate_factor, service_factor) -> dict:
    ultimate = _factor(ultimate_factor, "ultimate_factor")
    service = _factor(service_factor, "service_factor")
    try:
        ordinary = excel_round(ultimate, 2)
        maximum = excel_round(1.1 * ultimate, 2)
    except InputError as exc:
        raise InputError(f"ultimate_factor: 有効係数を丸められません: {exc}") from exc
    return {"ultimate_factor": ultimate, "service_factor": service,
            "ordinary_factor": ordinary, "maximum_factor": maximum}


def _definitions(parameters: dict) -> dict:
    basics = [
        {"id": number, "key": key, "label": label, "family": family, **extra,
         "spring_case": 1 if number <= 8 else 2,
         "action_domain": "vertical" if number <= 14 else "horizontal", "source_page": 13}
        for number, (key, label, family, extra) in enumerate(_BASIC_ROWS, 1)
    ]
    defines = []
    for number, (key, source_symbol, symbol, candidates) in enumerate(_DEFINE_ROWS, 1):
        kind = "track_alternative" if number in (9, 11) else "horizontal_sign" if number >= 13 else "identity"
        row = {"id": number, "key": key, "symbol": symbol, "source_symbol": source_symbol,
               "combination_symbol": symbol, "signed_basic_case_ids": list(candidates),
               "selection_kind": kind,
               "sign_scope": "horizontal_action_only" if kind == "horizontal_sign" else "positive_only",
               "source_page": 13}
        if kind == "track_alternative":
            row.update(selection_group="single_track", option_keys=["up", "down"])
        elif kind == "horizontal_sign":
            row["option_keys"] = ["positive", "negative"]
        defines.append(row)
    combinations = []
    for number, (key, label, original) in enumerate(_COMBINATION_ROWS, 1):
        usage = "service" if number in (5, 6, 7, 14, 15, 16) else "ultimate"
        coefficients = []
        for define_id, coefficient in enumerate(original, 1):
            if coefficient == 1.23:
                coefficient = parameters["ordinary_factor"]
            elif coefficient == 1.35:
                coefficient = parameters["maximum_factor"]
            elif coefficient and usage == "service" and define_id in (9, 10, 11, 12):
                coefficient *= parameters["service_factor"]
            coefficients.append(coefficient)
        combinations.append({"id": number, "key": key, "label": label,
                             "scope": "body" if number <= 9 else "foundation", "source_page": 14,
                             "usage": usage, "coefficients": coefficients})
    extractions = [
        {"id": number, "key": key, "label": label, "combination_ids": list(ids), "source_page": 15}
        for number, (key, label, ids) in enumerate(_EXTRACTION_ROWS, 1)
    ]
    return {"case_model_version": CASE_MODEL_VERSION, "direction": "transverse",
            "source": {"path": ".claude/docs/Example橋脚2/09_直角.pdf", "sha256": SOURCE_SHA256, "pages": [13, 14, 15]},
            "factor_parameters": dict(parameters), "coefficient_define_case_ids": list(range(1, 16)),
            "basic_cases": basics, "define_cases": defines,
            "combinations": combinations, "extraction_cases": extractions}


def build_case_model(*, ultimate_factor, service_factor) -> dict:
    """Return fresh definitions with input-dependent nominal coefficients.

    A service impact coefficient includes the source 0.75 only as nominal
    metadata. The action resolver uses the already usage-specific pier
    coefficient and must not multiply the resolved impact by 0.75 again.
    """
    model = _definitions(_parameters(ultimate_factor, service_factor))
    validate_case_model(model)
    return model


def _matches_definition(actual, expected, path: str) -> None:
    """Check required definition fields, allowing attached action/provenance data."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise InputError(f"{path}: objectが必要です")
        for key, value in expected.items():
            if key not in actual:
                raise InputError(f"{path}.{key}: 必須項目がありません")
            _matches_definition(actual[key], value, f"{path}.{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise InputError(f"{path}: {len(expected)}個の順序付き要素が必要です")
        for index, (value, reference) in enumerate(zip(actual, expected, strict=True)):
            item_path = f"{path}[{index}]"
            if path.endswith(".coefficients"):
                number = _factor(value, item_path)
                if number != reference:
                    raise InputError(f"{item_path}: 入力係数に対応する原本定義と一致しません")
            else:
                _matches_definition(value, reference, item_path)
    elif isinstance(expected, float):
        if _factor(actual, path) != expected:
            raise InputError(f"{path}: 採用係数の計算値と一致しません")
    elif type(actual) is not type(expected) or actual != expected:
        # Exact types keep True and 1.0 from being accepted as integer IDs.
        # Exact references also preserve coupled up/down choices and aliases.
        raise InputError(f"{path}: 原本のケース定義と一致しません")


def validate_case_model(model) -> None:
    """Validate all references, alternatives and adopted nominal coefficients.

    Definition fields are fixed by this document and the two input factors.
    Enforcing them together prevents a valid-looking ID swap from changing a
    load's meaning, or train/impact alternatives from becoming independent.
    Additional physical loads and resolved components are left to their owner.
    """
    if not isinstance(model, dict):
        raise InputError("case_model: objectが必要です")
    parameters = model.get("factor_parameters")
    if not isinstance(parameters, dict):
        raise InputError("factor_parameters: objectが必要です")
    expected = _definitions(_parameters(parameters.get("ultimate_factor"), parameters.get("service_factor")))
    _matches_definition(model, expected, "case_model")
