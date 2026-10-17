"""The input file being edited: read strictly, replaced cautiously; independent of Tk.

The data is kept as the JSON value itself, so keys the editor shows nothing for (出典) are saved unchanged. A
save never overwrites a file that changed since it was opened or last saved, and keeps the replaced bytes as a
``.bak`` beside it.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.errors import InputError
from ..core.integrity import dump_json, load_json
from ..inputs.fields import path_text

JsonPath = tuple[str | int, ...]
MISSING = object()


class EditorError(ValueError):
    """Something the user can correct; the message says what."""


class SaveConflict(EditorError):
    """The destination is not the version the user saw."""


def lookup(data: Any, path: JsonPath) -> Any:
    """The value at *path*, or MISSING."""
    for key in path:
        try:
            data = data[key]
        except (KeyError, IndexError, TypeError):
            return MISSING
    return data


def put(data: Any, path: JsonPath, value: Any) -> None:
    owner = lookup(data, path[:-1])
    key = path[-1]
    if owner is MISSING or (isinstance(key, int) and not (isinstance(owner, list) and 0 <= key < len(owner))) or (
            isinstance(key, str) and not isinstance(owner, dict)):
        raise EditorError(f"入力項目がありません: {path_text(path)}")
    owner[key] = value


def fingerprint(path: Path) -> str | None:
    """SHA256 of the file, or None when there is none."""
    path = Path(path)
    if path.is_symlink():
        raise EditorError(f"シンボリックリンクには保存できません: {path}")
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


@dataclass(frozen=True)
class SaveResult:
    path: Path
    backup: Path | None


class EditorDocument:
    def __init__(self, path: Path, data: dict, source: bytes) -> None:
        self.path = path
        self.data = data
        self._saved = dump_json(data)
        self.fingerprint = hashlib.sha256(source).hexdigest()

    @classmethod
    def open(cls, path: str | Path) -> EditorDocument:
        path = Path(path).absolute()
        if path.is_symlink():
            raise EditorError("シンボリックリンクではなく入力JSON本体を開いてください")
        source = path.read_bytes()
        try:
            data = load_json(source)
        except InputError as exc:
            raise EditorError(str(exc)) from None
        if not isinstance(data, dict):
            raise EditorError("入力JSONの最上位はオブジェクトである必要があります")
        return cls(path, data, source)

    @property
    def dirty(self) -> bool:
        return dump_json(self.data) != self._saved

    def save(self, destination: str | Path | None = None, *, expected: str | None = None) -> SaveResult:
        """Write the data; *expected* is the fingerprint of another destination the user agreed to replace."""
        target = Path(destination).absolute() if destination is not None else self.path
        snapshot = self.fingerprint if target == self.path else expected
        payload = dump_json(self.data)
        if fingerprint(target) != snapshot:
            raise SaveConflict("保存先が読込後に変更・削除されました。別名で保存するか、開き直して変更を確認してください。")
        if target == self.path and payload == self._saved:
            return SaveResult(target, None)
        backup = temporary = None
        try:
            handle, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            temporary = Path(name)
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if snapshot is not None:
                original = target.read_bytes()
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                backup = target.with_name(f"{target.name}.{stamp}.bak")
                with backup.open("xb") as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
            if fingerprint(target) != snapshot:
                raise SaveConflict("保存先が保存処理中に変更されました。保存を中止しました。")
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.path = target
        self._saved = payload
        self.fingerprint = hashlib.sha256(payload).hexdigest()
        return SaveResult(target, backup)
