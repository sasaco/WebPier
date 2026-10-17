"""Direction-specific springs copied from the normal 0500 calculation results."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .inputs import InputError


def _spring_value(values: Mapping[str, Any], component: str, path: str) -> int | float:
    if component not in values:
        raise InputError(f"計算結果がありません: {path}")
    value = values[component]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{path}: 有限の数値が必要です")
    try:
        finite = math.isfinite(value)
    except (OverflowError, ValueError) as exc:
        raise InputError(f"{path}: 有限の数値が必要です") from exc
    if not finite:
        raise InputError(f"{path}: 有限の数値が必要です")
    return value


def foundation_spring_set(foundation: Mapping[str, Any], direction: str) -> dict[str, Any]:
    """Return long/short Kv, Ks, and directional Kr without Single conversion.

    Numeric values are copied unchanged. The legacy macro handoff is not read.
    """
    if direction not in ("longitudinal", "transverse"):
        raise InputError("0500.direction: longitudinal または transverse が必要です")
    if not isinstance(foundation, Mapping):
        raise InputError("0500: 正規計算結果が必要です")

    terms: dict[str, dict[str, int | float]] = {}
    components: list[dict[str, Any]] = []
    for term in ("long_term", "short_term"):
        values = foundation.get(term)
        if not isinstance(values, Mapping):
            raise InputError(f"0500.{term}: 正規計算結果が必要です")
        terms[term] = {}
        for component in ("Kv", "Ks", "Kr"):
            source_component = f"Kr_{direction}" if component == "Kr" else component
            source_path = f"0500.{term}.{source_component}"
            value = _spring_value(values, source_component, source_path)
            terms[term][component] = value
            components.append({
                "direction": direction,
                "term": term,
                "component": component,
                "value": value,
                "source_path": source_path,
                "precision": "Double",
                "unit": "kN·m/rad" if component == "Kr" else "kN/m",
            })
    return {"direction": direction, "terms": terms, "components": components}
