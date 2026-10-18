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


def _reject_lone_surrogates(value: Any) -> None:
    """An escape such as \\ud800 loads as a lone surrogate, which UTF-8 cannot write back."""
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            try:
                item.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise InputError(f"JSONの文字列に対になっていないサロゲートがあります: {item[exc.start]!r}") from None
        elif isinstance(item, dict):
            pending.extend(item)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def load_json(data: bytes) -> Any:
    """Parse UTF-8 JSON (BOM allowed); reject duplicate keys, non-finite numbers and lone surrogates."""
    try:
        value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant, parse_float=_finite_float)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"JSONを読み込めません: {exc}") from exc
    _reject_lone_surrogates(value)
    return value


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


def folder_files(path: Path) -> dict[str, str]:
    """The SHA256 of every file under the folder *path*, by its path relative to it ('/'-separated).

    Only folders and regular files may be in it; a link (or junction) anywhere is an ``OSError``.
    """
    files: dict[str, str] = {}
    pending = [Path(path)]
    while pending:
        folder = pending.pop()
        if folder.is_symlink() or folder.is_junction() or not folder.is_dir():
            raise OSError(f"フォルダーではありません: {folder}")
        for entry in folder.iterdir():
            if entry.is_dir() and not entry.is_symlink() and not entry.is_junction():
                pending.append(entry)
            elif entry.is_symlink() or not entry.is_file():
                raise OSError(f"通常ファイルではありません: {entry}")
            else:
                files[entry.relative_to(path).as_posix()] = file_sha256(entry)
    return files


def content_sha256(path: Path) -> str:
    """The SHA256 of a file, or of a folder: its files by relative path (``folder_files``), as ``canonical_sha256``."""
    path = Path(path)
    return canonical_sha256(folder_files(path)) if path.is_dir() and not path.is_symlink() else file_sha256(path)
