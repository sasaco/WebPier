"""Reading a load model's add-in (decision 70): its declaration, its contract version, its import, its result and its
provenance, and every way it can fail (ADDIN_ERROR, or an input error for its own input)."""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from pipeline_support import CURRENT
from webpier.core.errors import InputError
from webpier.inputs import parse_input
from webpier.loadmodel import CONTRACT_VERSION, LoadModelResult
from webpier.pipeline.addin import MANIFEST, AddinError, load_addin

MINIMAL = Path(__file__).parents[1] / "fixtures" / "addin" / "minimal"


def addin(folder: Path, body: str, *, manifest: str | None = None, module: str = "model") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / MANIFEST).write_text(manifest if manifest is not None else
                                   f'name = "test"\nversion = "0.1"\ncontract = {CONTRACT_VERSION}\n'
                                   f'entry = "{module}:make"\n', encoding="utf-8")
    (folder / f"{module}.py").write_text(body, encoding="utf-8")
    return folder


def pier():
    return parse_input(json.loads(CURRENT.read_text(encoding="utf-8")), load_model=True)


def test_the_minimal_add_in():
    found = load_addin(MINIMAL)
    assert (found.folder, found.name, found.version, found.contract) == (MINIMAL, "minimal", "1.0.0", 1)
    p = pier()
    result = found.calculate(p, Path("pre/input.json"))
    assert isinstance(result, LoadModelResult) and found.calculate(p, Path("pre/input.json")) is result  # once
    assert found.record(result) == {"name": "minimal", "version": "1.0.0", "contract": 1,
                                    "provenance": {"source": "tests/fixtures/addin/minimal", "bearings": 6}}
    assert found.record(None)["provenance"] == {}


def test_a_package_add_in(tmp_path: Path):
    folder = tmp_path / "package"
    (folder / "model").mkdir(parents=True)
    (folder / MANIFEST).write_text(f'name = "p"\nversion = "1"\ncontract = {CONTRACT_VERSION}\nentry = "model:make"\n',
                                   encoding="utf-8")
    (folder / "model" / "__init__.py").write_text("from .inner import make\n", encoding="utf-8")
    (folder / "model" / "inner.py").write_text(
        "from webpier.loadmodel import LoadModelResult\n"
        "class M:\n    def calculate(self, context):\n        return LoadModelResult((), (), (), (), (), ())\n"
        "def make():\n    return M()\n", encoding="utf-8")
    result = load_addin(folder).calculate(pier(), Path("input.json"))
    assert result.cases == ()


def test_a_missing_or_broken_declaration_is_an_addin_error(tmp_path: Path):
    folder = tmp_path / "addin"
    folder.mkdir()
    with pytest.raises(AddinError, match=re.escape(f"アドインの宣言 {folder / MANIFEST} がありません")):
        load_addin(folder)
    (folder / MANIFEST).write_text("name = ", encoding="utf-8")
    with pytest.raises(AddinError, match=re.escape(f"アドインの宣言 {folder / MANIFEST} を読めません")):
        load_addin(folder)


@pytest.mark.parametrize("manifest,message", [
    ('version = "1"\ncontract = 1\nentry = "model:make"\n', "name の宣言がありません（str が必要です）"),
    ('name = "x"\ncontract = 1\nentry = "model:make"\n', "version の宣言がありません（str が必要です）"),
    ('name = "x"\nversion = "1"\ncontract = "1"\nentry = "model:make"\n', "contract の宣言がありません（int が必要です）"),
    ('name = "x"\nversion = "1"\ncontract = true\nentry = "model:make"\n', "contract の宣言がありません（int が必要です）"),
    ('name = "x"\nversion = "1"\ncontract = 1\n', "entry の宣言がありません（str が必要です）"),
    ('name = " "\nversion = "1"\ncontract = 1\nentry = "model:make"\n', "name の宣言がありません（str が必要です）"),
    ('name = "x"\nversion = "1"\ncontract = 2\nentry = "model:make"\n',
     "アドイン x の約束の版 2 は、この WebPier の約束の版 1 と違います"),
    ('name = "x"\nversion = "1"\ncontract = 1\nentry = "model.make"\n', "entry は「モジュール:関数」の形が必要です（model.make）"),
    ('name = "x"\nversion = "1"\ncontract = 1\nentry = "other:make"\n', "アドイン x のモジュール other が"),
])
def test_a_wrong_declaration_is_an_addin_error(tmp_path: Path, manifest, message):
    with pytest.raises(AddinError, match=re.escape(message)):
        load_addin(addin(tmp_path / "addin", "def make():\n    return None\n", manifest=manifest))


@pytest.mark.parametrize("body,message", [
    ("import webpier.nothing\n", "アドイン test を読み込めません（model:make）: ModuleNotFoundError"),
    ("x = 1\n", "アドイン test を読み込めません（model:make）: AttributeError"),
    ("def make():\n    raise RuntimeError('no')\n", "アドイン test を読み込めません（model:make）: RuntimeError: no"),
    ("def make():\n    return 1\n", "アドイン test の model:make が返したものに calculate がありません"),
])
def test_an_add_in_that_cannot_be_imported_is_an_addin_error(tmp_path: Path, body, message):
    with pytest.raises(AddinError, match=re.escape(message)):
        load_addin(addin(tmp_path / "addin", body))


def test_a_calculate_that_raises_is_an_addin_error(tmp_path: Path):
    found = load_addin(addin(tmp_path / "addin", "class M:\n    def calculate(self, context):\n        1 / 0\n"
                                                 "def make():\n    return M()\n"))
    with pytest.raises(AddinError, match=re.escape("アドイン test の calculate が失敗しました: ZeroDivisionError")):
        found.calculate(pier(), Path("input.json"))


def test_the_add_in_s_own_input_error_is_an_input_error(tmp_path: Path):
    found = load_addin(addin(tmp_path / "addin", (
        "from webpier.loadmodel import LoadModelInputError\n"
        "class M:\n    def calculate(self, context):\n"
        "        raise LoadModelInputError('input.addin.json:車荷重[1]', '値が必要です')\n"
        "def make():\n    return M()\n")))
    with pytest.raises(InputError, match=re.escape("input.addin.json:車荷重[1]: 値が必要です")):
        found.calculate(pier(), Path("input.json"))


def test_a_result_the_application_cannot_use_is_an_input_error(tmp_path: Path):
    found = load_addin(addin(tmp_path / "addin", "class M:\n    def calculate(self, context):\n        return 1\n"
                                                 "def make():\n    return M()\n"))
    with pytest.raises(InputError, match=re.escape("アドイン: 荷重モデルの結果は LoadModelResult が必要です（int）")):
        found.calculate(pier(), Path("input.json"))
