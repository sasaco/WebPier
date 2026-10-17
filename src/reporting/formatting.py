"""Display-only formatting; no evaluation of engineering expressions."""

from __future__ import annotations

from typing import Any


def display(value: str) -> str:
    """Keep authored signs, trailing zeros, units and missing-value markers."""
    if not isinstance(value, str):
        raise TypeError("display requires an already-formatted string")
    return value


def number(value: Any, decimals: int | None = None, comma: bool = False) -> str:
    """Preserve the original foundation report's explicit formatting contract."""
    if value is None or value == "":
        return ""
    if decimals is None:
        return f"{value:,g}" if comma else f"{value:g}"
    return format(value, f"{',' if comma else ''}.{decimals}f")
