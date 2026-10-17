"""Bounded, byte-based identity of the installed report rendering runtime."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import os
from pathlib import Path
import stat

from .fonts import font_files


class RuntimeIdentityError(ValueError):
    """A dependency cannot be safely bound to the held generation."""


def _files(root: Path) -> list[Path]:
    """Scan only named package roots, without following links or hashing caches."""
    found: list[Path] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name in {"__pycache__", ".git"}:
                    continue
                info = entry.stat(follow_symlinks=False)
                if (stat.S_ISLNK(info.st_mode)
                        or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                    raise RuntimeIdentityError(f"描画依存にリンクがあります: {entry.path}")
                path = Path(entry.path)
                if stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    if path.suffix.lower() not in {".pyc", ".pyo"}:
                        found.append(path)
                else:
                    raise RuntimeIdentityError(f"描画依存が通常ファイルではありません: {path}")
    return found


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _digest(path: Path) -> tuple[Path, str]:
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode)
            or getattr(before, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise RuntimeIdentityError(f"描画依存が通常ファイルではありません: {path}")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if _identity(before) != _identity(path.lstat()):
        raise RuntimeIdentityError(f"検証中に描画依存が変更されました: {path}")
    return path, digest


def dependency_hashes(package_root: Path) -> dict[Path, str]:
    """Hash app sources/data and actual installed renderer packages/font assets.

    An explicit minimal receipt-fixture package may have no rendering subtree.
    A real package losing that subtree is invalid, and exact map comparisons
    detect additions/removals even for those minimal fixture roots. Font face
    indices are bound by the included reporting/fonts.py bytes; TTC/TTF assets
    are re-read on every call regardless of a FontRegistry's cached digest.
    """
    root = package_root.resolve(strict=True)
    rendering = root / "reporting"
    if root == Path(__file__).resolve().parents[1] and not rendering.is_dir():
        raise RuntimeIdentityError("描画プログラムの reporting ディレクトリがありません")
    roots = [root]
    assets: set[Path] = set()
    if rendering.is_dir():
        for name in ("gridlayoutpdf", "reportlab", "PIL"):
            module = importlib.import_module(name)
            if module.__file__ is None:
                raise RuntimeIdentityError(f"描画依存の実体を特定できません: {name}")
            roots.append(Path(module.__file__).resolve(strict=True).parent)
        assets.update(path.resolve(strict=True) for path in font_files().values())
    for source_root in roots:
        assets.update(_files(source_root))
    # Network shares benefit from bounded parallel reads; every call rehashes
    # bytes and checks file stability instead of trusting timestamp caches.
    with ThreadPoolExecutor(max_workers=8) as executor:
        return dict(executor.map(_digest, sorted(assets)))
