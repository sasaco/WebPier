"""Rendering identity binds actual recursive source/data/font/package bytes."""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import gridlayoutpdf
from PIL import Image
import pytest
from reportlab.pdfbase import pdfmetrics

from src import jrsnap_artifacts
from src.reporting.fonts import font_files, load_fonts
from src.reporting import runtime


@pytest.fixture
def isolated_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    package = tmp_path / "src"
    package.mkdir()
    (package / "jrsnap_artifacts.py").write_text("# application source\n", encoding="utf-8")
    (package / "reporting" / "stages").mkdir(parents=True)
    (package / "reporting" / "stages" / "reaction.py").write_text("# nested source\n", encoding="utf-8")
    (package / "assets").mkdir()
    (package / "assets" / "reaction_report_layout.json").write_text('{"formulas":{"A1":"=1+2"}}', encoding="utf-8")
    monkeypatch.setattr(jrsnap_artifacts, "__file__", str(package / "jrsnap_artifacts.py"))
    return package


def test_implementation_identity_contains_nested_rendering_and_pure_value_resources(isolated_package: Path) -> None:
    hashes = jrsnap_artifacts.implementation_hashes()
    for relative in ("reporting/stages/reaction.py", "assets/reaction_report_layout.json"):
        path = (isolated_package / relative).resolve()
        assert hashes.get(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_identity_binds_actual_installed_renderer_and_font_files() -> None:
    hashes = jrsnap_artifacts.implementation_hashes()
    for path in (Path(gridlayoutpdf.__file__), Path(pdfmetrics.__file__), Path(Image.__file__), *font_files().values()):
        assert hashes.get(path.resolve()) == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("change", ["add", "delete", "modify", "resource"])
def test_nested_source_and_resource_changes_alter_the_manifest(isolated_package: Path, change: str) -> None:
    before = jrsnap_artifacts.implementation_hashes()
    source = isolated_package / "reporting" / "stages" / "reaction.py"
    if change == "add":
        source.with_name("added.py").write_text("# new nested source\n", encoding="utf-8")
    elif change == "delete":
        source.unlink()
    elif change == "modify":
        source.write_text("# changed nested source\n", encoding="utf-8")
    else:
        (isolated_package / "assets" / "reaction_report_layout.json").write_text('{"formulas":{"A1":"=1+3"}}', encoding="utf-8")
    assert before != jrsnap_artifacts.implementation_hashes()


def test_receipt_rechecks_nested_source_addition_at_its_bound_app_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reuse the established independent readback harness; no real app launch."""
    path = Path(__file__).parents[1] / "test_jrsnap_acceptance.py"
    spec = importlib.util.spec_from_file_location("render_identity_receipt_harness", path)
    assert spec is not None and spec.loader is not None
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    harness = fixture_module.harness.__wrapped__(tmp_path, monkeypatch)
    fixture_module.run_accept(harness)
    nested = fixture_module.acceptance.PROJECT / "src" / "reporting" / "stages"
    nested.mkdir(parents=True)
    (nested / "new_stage.py").write_text("# Newly added rendering source\n", encoding="utf-8")
    with pytest.raises(fixture_module.acceptance.AcceptanceError):
        fixture_module.acceptance.finalize_receipt(harness.receipt, identity_reader=lambda: harness.identity)


def test_registered_font_cache_cannot_hide_changed_font_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "Windows" / "Fonts"
    directory.mkdir(parents=True)
    for original in font_files().values():
        shutil.copyfile(original, directory / original.name)
    registry = load_fonts(directory)
    old_registered_digest = registry.resolve("body").sha256
    monkeypatch.setenv("WINDIR", str(directory.parent))
    before = jrsnap_artifacts.implementation_hashes()
    body = (directory / "msmincho.ttc").resolve()
    with body.open("ab") as stream:
        stream.write(b"\0")
    after = jrsnap_artifacts.implementation_hashes()
    assert registry.resolve("body").sha256 == old_registered_digest
    assert before != after
    assert after[body] == hashlib.sha256(body.read_bytes()).hexdigest()


@pytest.mark.parametrize("change", ["add", "delete", "same-stat-bytes", "font", "image"])
def test_installed_package_and_asset_changes_are_detected(
    isolated_package: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    packages = {}
    for name in ("gridlayoutpdf", "reportlab", "PIL"):
        root = tmp_path / "installed" / name
        root.mkdir(parents=True)
        (root / "__init__.py").write_bytes(b"# installed v1\n")
        packages[name] = SimpleNamespace(__file__=str(root / "__init__.py"))
    font = tmp_path / "body.ttc"
    font.write_bytes(b"font one")
    image = isolated_package / "assets" / "diagram.png"
    image.write_bytes(b"image one")
    monkeypatch.setattr(runtime.importlib, "import_module", packages.__getitem__)
    monkeypatch.setattr(runtime, "font_files", lambda: {"body": font})
    before = runtime.dependency_hashes(isolated_package)
    source = Path(packages["gridlayoutpdf"].__file__)
    if change == "add":
        source.with_name("renderer.py").write_bytes(b"# added renderer")
    elif change == "delete":
        source.unlink()
    elif change == "same-stat-bytes":
        info = source.stat()
        source.write_bytes(b"# installed v2\n")
        os.utime(source, ns=(info.st_atime_ns, info.st_mtime_ns))
        assert source.stat().st_size == info.st_size
        assert source.stat().st_mtime_ns == info.st_mtime_ns
    elif change == "font":
        font.write_bytes(b"font two")
    else:
        image.write_bytes(b"image two")
    if change == "delete":
        # A package whose imported entry point disappears is invalid.
        with pytest.raises(FileNotFoundError):
            runtime.dependency_hashes(isolated_package)
    else:
        assert runtime.dependency_hashes(isolated_package) != before


def test_removing_real_reporting_subtree_does_not_reduce_tracking_scope(
    isolated_package: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime, "__file__", str(isolated_package / "reporting" / "runtime.py"))
    shutil.rmtree(isolated_package / "reporting")
    with pytest.raises(runtime.RuntimeIdentityError, match="reporting"):
        jrsnap_artifacts.implementation_hashes()
