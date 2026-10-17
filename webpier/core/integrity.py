"""Strict JSON and content hashes.

Every reader of input.json uses the same strict parser, so a file never
loads in one path and fails in another.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .errors import InputError


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"JSONのキーが重複しています: {key}")
        result[key] = value
    return result


def _reject_constant(text: str) -> None:
    raise InputError(f"JSONに有限でない数値があります: {text}")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        _reject_constant(text)
    return value


def load_json(data: bytes) -> Any:
    """Parse UTF-8 JSON (BOM allowed); reject duplicate keys and non-finite numbers."""
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant, parse_float=_finite_float)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"JSONを読み込めません: {exc}") from exc


def dump_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical_sha256(value: Any) -> str:
    """Hash a JSON-compatible value independent of key order."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return sha256(encoded)
