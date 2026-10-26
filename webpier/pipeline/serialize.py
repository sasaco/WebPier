"""Calculation results as deterministic JSON.

A ``Printed`` becomes its printed number, a Decimal (a load model's value, decision 70) its number, an enum its
value, a tuple a list, a set a list sorted by its JSON, and a mapping key a string. A dataclass field with
``metadata={"json": False}`` is left out (the pages of another program's report a result carries, decision 91), one with
``metadata={"json": "set"}`` is left out while it is None (what only some inputs have, decision 97). Anything else is
a programming error: the result JSON never guesses.
"""

from __future__ import annotations

import enum
import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from decimal import Decimal
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


def _written(item: Any, value: Any) -> bool:
    shown = item.metadata.get("json", True)
    return getattr(value, item.name) is not None if shown == "set" else bool(shown)


def to_json(value: Any) -> Any:
    if isinstance(value, Printed):
        return value.value
    if isinstance(value, enum.Enum):
        return to_json(value.value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        return to_json(float(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"有限でない数値はJSONにできません: {value!r}")
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_json(getattr(value, item.name)) for item in fields(value) if _written(item, value)}
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
                    implementation_sha256: str, addin: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The result JSON of one stage, bound to the input bytes and the implementation that produced it, and with a
    load model to the add-in as it declared itself and the provenance it returned (decision 70)."""
    return {"schema_version": SCHEMA_VERSION, "stage": stage,
            "input": {"file": input_file, "sha256": input_sha256},
            "implementation_sha256": implementation_sha256, **({} if addin is None else {"addin": dict(addin)}),
            "result": to_json(result)}
