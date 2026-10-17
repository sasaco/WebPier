"""Calculation results as deterministic JSON.

A ``Printed`` becomes its printed number, an enum its value, a tuple a list, a set a list sorted by its JSON,
and a mapping key a string. Anything else is a programming error: the result JSON never guesses.
"""

from __future__ import annotations

import enum
import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any

from ..core.printed import Printed

SCHEMA_VERSION = 1


def _key(key: Any) -> str:
    if isinstance(key, enum.Enum):
        key = key.value
    if isinstance(key, str):
        return key
    if isinstance(key, int) and not isinstance(key, bool):
        return str(key)
    raise TypeError(f"JSONのキーにできません: {key!r}")


def to_json(value: Any) -> Any:
    if isinstance(value, Printed):
        return value.value
    if isinstance(value, enum.Enum):
        return to_json(value.value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"有限でない数値はJSONにできません: {value!r}")
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_json(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        encoded: dict[str, Any] = {}
        for key, item in value.items():
            name = _key(key)
            if name in encoded:
                raise ValueError(f"JSONのキーが重複します: {name}")
            encoded[name] = to_json(item)
        return encoded
    if isinstance(value, (tuple, list)):
        return [to_json(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [to_json(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    raise TypeError(f"JSONにできない値です: {type(value).__name__}")


def result_document(stage: str, result: Any, *, input_file: str, input_sha256: str,
                    implementation_sha256: str) -> dict[str, Any]:
    """The result JSON of one stage, bound to the input bytes and the implementation that produced it."""
    return {"schema_version": SCHEMA_VERSION, "stage": stage,
            "input": {"file": input_file, "sha256": input_sha256},
            "implementation_sha256": implementation_sha256, "result": to_json(result)}
