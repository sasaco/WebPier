"""Implementation identity: actual bytes of the webpier sources, installed renderers and fonts."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
from types import SimpleNamespace

import gridlayoutpdf
from PIL import Image
import pypdf
import pytest
from reportlab.pdfbase import pdfmetrics

import webpier
from webpier.pipeline import runtime
from webpier.reporting.fonts import font_files, load_fonts
from webpier.reporting.styles import BODY_FONT

PACKAGE = Path(webpier.__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def isolated_package(tmp_path: Path) -> Path:
    package = tmp_path / "webpier"
    (package / "reporting" / "stages").mkdir(parents=True)
    (package / "__init__.py").write_text("# application\n", encoding="utf-8")
    (package / "reporting" / "stages" / "foundation.py").write_text("# nested source\n", encoding="utf-8")
    (package / "assets").mkdir()
    (package / "assets" / "layout.json").write_text('{"a": 1}', encoding="utf-8")
    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "cached.py").write_text("# cache\n", encoding="utf-8")
    (package / "compiled.pyc").write_bytes(b"\0")
    return package


@pytest.fixture
def fake_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Installed renderer packages and a font, replaced by small files we may change."""
    entries = {}
    for name in ("gridlayoutpdf", "reportlab", "PIL", "pypdf"):
        root = tmp_path / "installed" / name
        root.mkdir(parents=True)
        (root / "__init__.py").write_bytes(b"# installed v1\n")
        entries[name] = root / "__init__.py"
    font = tmp_path / "body.ttc"
    font.write_bytes(b"font one")
    entries["font"] = font
    modules = {name: SimpleNamespace(__file__=str(entries[name])) for name in ("gridlayoutpdf", "reportlab", "PIL", "pypdf")}
    monkeypatch.setattr(runtime.importlib, "import_module", modules.__getitem__)
    monkeypatch.setattr(runtime, "font_files", lambda: {"body": font})
    return entries


def test_default_identity_is_the_webpier_package_with_its_renderers_and_fonts():
    hashes = runtime.dependency_hashes()
    assert hashes == runtime.dependency_hashes(PACKAGE)
    for path in (PACKAGE / "reporting" / "numbers.py", PACKAGE / "calc" / "foundation.py",
                 PACKAGE / "pipeline" / "runtime.py", Path(gridlayoutpdf.__file__), Path(pdfmetrics.__file__),
                 Path(Image.__file__), Path(pypdf.__file__), *font_files().values()):
        assert hashes[path.resolve()] == sha256(path)
    assert not any("__pycache__" in path.parts or path.suffix == ".pyc" for path in hashes)
    assert not any(path.is_relative_to(PACKAGE.parent / "src") for path in hashes)


def test_cache_and_bytecode_are_not_part_of_the_identity(isolated_package: Path, fake_installed: dict[str, Path]):
    hashes = runtime.dependency_hashes(isolated_package)
    expected = {isolated_package / "__init__.py", isolated_package / "reporting/stages/foundation.py",
                isolated_package / "assets/layout.json", *fake_installed.values()}
    assert set(hashes) == {path.resolve() for path in expected}


@pytest.mark.parametrize("change", ["add", "delete", "modify", "resource"])
def test_nested_source_and_resource_changes_alter_the_identity(
    isolated_package: Path, fake_installed: dict[str, Path], change: str,
):
    before = runtime.dependency_hashes(isolated_package)
    source = isolated_package / "reporting" / "stages" / "foundation.py"
    if change == "add":
        source.with_name("added.py").write_text("# new\n", encoding="utf-8")
    elif change == "delete":
        source.unlink()
    elif change == "modify":
        source.write_text("# changed nested source\n", encoding="utf-8")
    else:
        (isolated_package / "assets" / "layout.json").write_text('{"a": 2}', encoding="utf-8")
    assert runtime.dependency_hashes(isolated_package) != before


@pytest.mark.parametrize("change", ["add", "delete", "same-stat-bytes", "font"])
def test_installed_package_and_font_changes_are_detected(
    isolated_package: Path, fake_installed: dict[str, Path], change: str,
):
    before = runtime.dependency_hashes(isolated_package)
    source = fake_installed["gridlayoutpdf"]
    if change == "add":
        source.with_name("renderer.py").write_bytes(b"# added renderer")
    elif change == "delete":
        source.unlink()
        # A package whose imported entry point disappeared is invalid, not smaller.
        with pytest.raises(FileNotFoundError):
            runtime.dependency_hashes(isolated_package)
        return
    elif change == "same-stat-bytes":
        info = source.stat()
        source.write_bytes(b"# installed v2\n")
        os.utime(source, ns=(info.st_atime_ns, info.st_mtime_ns))
        assert (source.stat().st_size, source.stat().st_mtime_ns) == (info.st_size, info.st_mtime_ns)
    else:
        fake_installed["font"].write_bytes(b"font two")
    assert runtime.dependency_hashes(isolated_package) != before


def test_registered_font_cache_cannot_hide_changed_font_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    directory = tmp_path / "Windows" / "Fonts"
    directory.mkdir(parents=True)
    for original in font_files().values():
        shutil.copyfile(original, directory / original.name)
    monkeypatch.setenv("WINDIR", str(directory.parent))
    registry = load_fonts()
    registered = registry.resolve(BODY_FONT).sha256
    assert registry.resolve(BODY_FONT).path.parent == directory
    before = runtime.dependency_hashes()
    body = (directory / "msmincho.ttc").resolve()
    with body.open("ab") as stream:
        stream.write(b"\0")
    after = runtime.dependency_hashes()
    assert registry.resolve(BODY_FONT).sha256 == registered
    assert before != after and after[body] == sha256(body)


def test_minimal_package_without_rendering_hashes_only_its_own_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    package = tmp_path / "receipt"
    package.mkdir()
    (package / "app.py").write_text("# minimal\n", encoding="utf-8")
    monkeypatch.setattr(runtime.importlib, "import_module", lambda name: pytest.fail(f"imported {name}"))
    assert runtime.dependency_hashes(package) == {(package / "app.py").resolve(): sha256(package / "app.py")}


def test_the_real_package_losing_its_reporting_subtree_is_invalid(isolated_package: Path, monkeypatch: pytest.MonkeyPatch):
    (isolated_package / "pipeline").mkdir()
    monkeypatch.setattr(runtime, "__file__", str(isolated_package / "pipeline" / "runtime.py"))
    shutil.rmtree(isolated_package / "reporting")
    with pytest.raises(runtime.RuntimeIdentityError, match="reporting"):
        runtime.dependency_hashes(isolated_package)


def test_a_renderer_without_a_file_cannot_be_identified(isolated_package: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(runtime.importlib, "import_module", lambda name: SimpleNamespace(__file__=None))
    with pytest.raises(runtime.RuntimeIdentityError, match="gridlayoutpdf"):
        runtime.dependency_hashes(isolated_package)


class _Entry:
    """A directory entry whose stat reports another file type or attribute."""

    def __init__(self, entry: os.DirEntry, mode: int | None = None, attributes: int = 0):
        self._entry, self._mode, self._attributes = entry, mode, attributes
        self.name, self.path = entry.name, entry.path

    def stat(self, *, follow_symlinks: bool = True):
        real = self._entry.stat(follow_symlinks=follow_symlinks)
        return SimpleNamespace(st_mode=self._mode if self._mode is not None else real.st_mode,
                               st_file_attributes=self._attributes)


@pytest.mark.parametrize("kind,message", [
    ("symlink", "リンク"), ("reparse", "リンク"), ("fifo", "通常ファイルではありません"),
])
def test_links_and_special_files_in_a_scanned_root_are_rejected(
    isolated_package: Path, fake_installed: dict[str, Path], monkeypatch: pytest.MonkeyPatch, kind: str, message: str,
):
    real_scandir = os.scandir
    target = isolated_package / "assets" / "layout.json"

    class Scan:
        def __init__(self, directory):
            self._scan = real_scandir(directory)

        def __enter__(self):
            entries = list(self._scan.__enter__())
            changed = {"symlink": {"mode": stat.S_IFLNK | 0o777},
                       "reparse": {"attributes": stat.FILE_ATTRIBUTE_REPARSE_POINT},
                       "fifo": {"mode": stat.S_IFIFO | 0o644}}[kind]
            return [_Entry(entry, **changed) if Path(entry.path) == target else entry for entry in entries]

        def __exit__(self, *exc):
            return self._scan.__exit__(*exc)

    monkeypatch.setattr(runtime.os, "scandir", Scan)
    with pytest.raises(runtime.RuntimeIdentityError, match=message):
        runtime.dependency_hashes(isolated_package)


def test_a_path_that_is_no_longer_a_regular_file_when_hashed_is_rejected(
    isolated_package: Path, fake_installed: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
):
    real_files = runtime._files
    monkeypatch.setattr(runtime, "_files", lambda root: [*real_files(root), isolated_package / "assets"])
    with pytest.raises(runtime.RuntimeIdentityError, match="通常ファイルではありません"):
        runtime.dependency_hashes(isolated_package)


def test_a_file_changed_while_being_hashed_is_rejected(
    isolated_package: Path, fake_installed: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
):
    target = (isolated_package / "assets" / "layout.json").resolve()
    real_digest = runtime.hashlib.file_digest

    def digest_while_writing(stream, name):
        result = real_digest(stream, name)
        if Path(stream.name).resolve() == target:
            with target.open("ab") as writer:
                writer.write(b" ")
        return result

    monkeypatch.setattr(runtime.hashlib, "file_digest", digest_while_writing)
    with pytest.raises(runtime.RuntimeIdentityError, match="変更されました"):
        runtime.dependency_hashes(isolated_package)
