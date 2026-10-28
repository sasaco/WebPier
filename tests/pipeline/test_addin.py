"""Reading a load model's add-in (decision 70): its declaration, its contract version, its import, its result and its
provenance, and every way it can fail (ADDIN_ERROR, or an input error for its own input)."""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from pipeline_support import CURRENT
from webpier.core.errors import InputError
from webpier.core.printed import LENGTH
from webpier.inputs import parse_input
from webpier.inputs.model import CalculationSection
from webpier.loadmodel import CONTRACT_VERSION, LoadModelResult
from webpier.pipeline.addin import MANIFEST, AddinError, load_addin
from webpier.pipeline.generate import GenerationOptions, resolve_input

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
    assert (found.folder, found.name, found.version, found.contract) == (MINIMAL, "minimal", "1.0.0", 2)
    p = pier()
    result = found.calculate(p, Path("pre/input.json"))
    assert isinstance(result, LoadModelResult) and found.calculate(p, Path("pre/input.json")) is result  # once
    assert found.record(result) == {"name": "minimal", "version": "1.0.0", "contract": 2,
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
    ('version = "1"\ncontract = 2\nentry = "model:make"\n', "name の宣言がありません（str が必要です）"),
    ('name = "x"\ncontract = 2\nentry = "model:make"\n', "version の宣言がありません（str が必要です）"),
    ('name = "x"\nversion = "1"\ncontract = "1"\nentry = "model:make"\n', "contract の宣言がありません（int が必要です）"),
    ('name = "x"\nversion = "1"\ncontract = true\nentry = "model:make"\n', "contract の宣言がありません（int が必要です）"),
    ('name = "x"\nversion = "1"\ncontract = 2\n', "entry の宣言がありません（str が必要です）"),
    ('name = " "\nversion = "1"\ncontract = 2\nentry = "model:make"\n', "name の宣言がありません（str が必要です）"),
    ('name = "x"\nversion = "1"\ncontract = 1\nentry = "model:make"\n',
     "アドイン x の約束の版 1 は、この WebPier の約束の版 2 と違います"),
    ('name = "x"\nversion = "1"\ncontract = 2\nentry = "model.make"\n', "entry は「モジュール:関数」の形が必要です（model.make）"),
    ('name = "x"\nversion = "1"\ncontract = 2\nentry = "other:make"\n', "アドイン x のモジュール other が"),
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


# decision 118: the 計算上断面 of the column, declared apart from the load model (current.json: B6 2.700, W6 4.500 m)
MODEL = ("from decimal import Decimal\n"
         "from webpier.loadmodel import ColumnSection, LoadModelInputError, LoadModelResult\n"
         "MADE = []\n"
         "class M:\n    def calculate(self, context):\n        return LoadModelResult((), (), (), (), (), ())\n"
         "def make():\n    MADE.append(1)\n    return M()\n")


def sectioned(folder: Path, function: str, body: str = "") -> Path:
    return addin(folder, MODEL + body, manifest=f'name = "test"\nversion = "0.1"\ncontract = {CONTRACT_VERSION}\n'
                                                f'entry = "model:make"\ncolumn_section = "{function}"\n')


def test_the_column_section_of_an_add_in(tmp_path: Path):
    # one module for both functions: section sees what make did
    found = load_addin(sectioned(tmp_path / "addin", "model:section", (
        "def section(context):\n"
        "    assert MADE == [1] and context.input_path == __import__('pathlib').Path('pre/input.json')\n"
        "    return ColumnSection(Decimal('2.600'), Decimal('4.500'))\n")))
    p = pier()
    calculated = found.with_section(p, Path("pre/input.json"))
    assert calculated.calculation_section == CalculationSection(LENGTH(2.6), LENGTH(4.5))
    assert calculated.column_section == (LENGTH(2.6), LENGTH(4.5))
    assert calculated.substructure is p.substructure and p.calculation_section is None  # the shape: B6 × W6
    assert found.bind(Path("pre/input.json")).with_section(p).calculation_section == calculated.calculation_section


def test_without_a_column_section_the_input_is_as_it_is():
    p = pier()
    assert load_addin(MINIMAL).with_section(p, Path("input.json")) is p


@pytest.mark.parametrize("declared,body,message", [
    ("1", "", "column_section の宣言がありません（str が必要です）"),
    ('"model.section"', "", "column_section は「モジュール:関数」の形が必要です（model.section）"),
    ('"model:nothing"', "", "アドイン test を読み込めません（model:nothing）: AttributeError"),
    ('"other:section"', "", "アドイン test のモジュール other が"),
    ('"model:VALUE"', "VALUE = 1\n", "アドイン test の model:VALUE は関数が必要です"),
])
def test_a_wrong_column_section_declaration_is_an_addin_error(tmp_path: Path, declared, body, message):
    folder = addin(tmp_path / "addin", MODEL + body, manifest=(
        f'name = "test"\nversion = "0.1"\ncontract = {CONTRACT_VERSION}\nentry = "model:make"\n'
        f"column_section = {declared}\n"))
    with pytest.raises(AddinError, match=re.escape(message)):
        load_addin(folder)


def test_a_column_section_that_raises_is_an_addin_error(tmp_path: Path):
    found = load_addin(sectioned(tmp_path / "addin", "model:section", "def section(context):\n    1 / 0\n"))
    with pytest.raises(AddinError, match=re.escape("アドイン test の column_section が失敗しました: ZeroDivisionError")):
        found.with_section(pier(), Path("input.json"))


@pytest.mark.parametrize("returned,message", [
    ("LoadModelInputError('input.addin.json:柱の計算上断面', '値が必要です')",
     "input.addin.json:柱の計算上断面: 値が必要です"),
    ("1", "アドイン: 柱の計算上断面は ColumnSection が必要です（int）"),
    ("ColumnSection(2.6, Decimal('4.500'))", "アドイン:column_section.along: 小数3桁までの Decimal が必要です（2.6）"),
    ("ColumnSection(Decimal('2.6001'), Decimal('4.500'))",
     "アドイン:column_section.along: 小数3桁までの Decimal が必要です（2.6001）"),
    ("ColumnSection(Decimal('2.701'), Decimal('4.500'))",
     "アドイン:column_section.along: 0 より大きく、実断面の B6 = 2.700 m 以下の値が必要です（2.701）"),
    ("ColumnSection(Decimal('2.700'), Decimal('0.000'))",
     "アドイン:column_section.across: 0 より大きく、実断面の W6 = 4.500 m 以下の値が必要です（0.000）"),
])
def test_a_column_section_the_application_cannot_use_is_an_input_error(tmp_path: Path, returned, message):
    action = "raise" if returned.startswith("LoadModelInputError") else "return"
    found = load_addin(sectioned(tmp_path / "addin", "model:section", f"def section(context):\n    {action} {returned}\n"))
    with pytest.raises(InputError, match=re.escape(message)):
        found.with_section(pier(), Path("input.json"))


def test_the_column_section_may_be_the_real_one(tmp_path: Path):
    found = load_addin(sectioned(tmp_path / "addin", "model:section", (
        "def section(context):\n    return ColumnSection(Decimal('2.700'), Decimal('4.500'))\n")))
    p = pier()
    assert found.with_section(p, Path("input.json")).column_section == p.column_section


def test_a_generation_reads_the_input_with_the_column_section(tmp_path: Path):
    folder = sectioned(tmp_path / "addin", "model:section", (
        "def section(context):\n    return ColumnSection(Decimal('2.600'), Decimal('4.400'))\n"))
    options = GenerationOptions(CURRENT, tmp_path / "output", tmp_path / "post", addin=folder)
    pier_input = resolve_input(options)[2]
    assert pier_input.column_section == (LENGTH(2.6), LENGTH(4.4))
    assert resolve_input(GenerationOptions(CURRENT, tmp_path / "output", tmp_path / "post"))[2].column_section == (
        LENGTH(2.7), LENGTH(4.5))
