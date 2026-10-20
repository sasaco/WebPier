"""Layers depend only downwards (ADR-0004): core ← inputs ← loadmodel ← calc ← reporting/export ← pipeline ← gui.

loadmodel is the contract a load model is written against (decision 70): a load model imports it only, so it reaches
neither the calculation nor the input."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[1] / "webpier"

ALLOWED = {
    "core": set(),
    "inputs": {"core"},
    "loadmodel": {"core"},
    "calc": {"core", "inputs", "loadmodel"},
    "reporting": {"core", "inputs", "loadmodel", "calc"},
    "export": {"core", "inputs", "loadmodel", "calc"},
    "pipeline": {"core", "inputs", "loadmodel", "calc", "reporting", "export"},
    "gui": {"core", "inputs", "loadmodel", "calc", "reporting", "export", "pipeline"},
}
# Third-party packages a layer must not touch, so calculation never depends on drawing or Tk. A module is imported
# by name only in pipeline (importlib), which reads a load model's add-in (decision 70).
FORBIDDEN_EXTERNAL = {
    "core": {"reportlab", "gridlayoutpdf", "tkinter", "tksheet", "pymupdf", "fitz", "PIL", "pypdf", "importlib"},
    "inputs": {"reportlab", "gridlayoutpdf", "tkinter", "tksheet", "pymupdf", "fitz", "PIL", "pypdf", "importlib"},
    "loadmodel": {"reportlab", "gridlayoutpdf", "tkinter", "tksheet", "pymupdf", "fitz", "PIL", "pypdf", "importlib"},
    "calc": {"reportlab", "gridlayoutpdf", "tkinter", "tksheet", "pymupdf", "fitz", "PIL", "pypdf", "importlib"},
    "export": {"reportlab", "gridlayoutpdf", "tkinter", "tksheet", "pypdf", "importlib"},
    "reporting": {"tkinter", "tksheet", "importlib"},
    "pipeline": {"tkinter", "tksheet"},
    "gui": {"importlib"},
}


def _imports(path: Path) -> list[tuple[str, int]]:
    """Absolute names of everything *path* imports, resolving relative imports."""
    module = path.relative_to(PACKAGE.parent).with_suffix("").parts
    package = module[:-1]
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[:len(package) - node.level + 1]
                found.append((".".join((*base, node.module or "")).rstrip("."), node.lineno))
            else:
                found.append((node.module or "", node.lineno))
    return found


def _modules():
    for path in sorted(PACKAGE.rglob("*.py")):
        parts = path.relative_to(PACKAGE).parts
        if len(parts) > 1:
            yield parts[0], path


@pytest.mark.parametrize("layer,path", list(_modules()), ids=lambda value: str(value))
def test_layer_imports_only_lower_layers(layer, path):
    assert layer in ALLOWED, f"unknown layer package: {layer}"
    for name, line in _imports(path):
        top, *rest = name.split(".")
        where = f"{path.relative_to(PACKAGE.parent)}:{line} imports {name}"
        if top == "webpier":
            target = rest[0] if rest else ""
            assert target == layer or target in ALLOWED[layer], where
        else:
            assert top not in FORBIDDEN_EXTERNAL[layer], where


def test_old_src_package_is_not_used_by_new_layers():
    for _, path in _modules():
        for name, line in _imports(path):
            assert not name.startswith("src"), f"{path}:{line} imports {name}"
