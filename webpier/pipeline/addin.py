"""Reading a load model's add-in (decision 70, ADR-0010): ``--addin <folder>``.

The folder holds ``webpier-addin.toml``: ``name``, ``version``, ``contract`` (the version of webpier.loadmodel it is
written against) and ``entry = "module:function"``, a function without arguments that returns the load model (an
object with ``calculate(context)``). It may also declare ``column_section = "module:function"``, a function of the
context that returns the 計算上断面 of the column (decision 118), which the input is calculated with as an RC section
(``with_section``). A module is imported from the folder by its file, under a name of its own and once; the add-in
imports webpier.loadmodel only. A missing or wrong declaration, another contract version, an import that fails
and a ``calculate`` or ``column_section`` that raises are ``AddinError`` (ADDIN_ERROR); an error in the add-in's
own input (``LoadModelInputError``) and a result the application cannot use (loadmodel.validate,
validate_column_section) are input errors.

The application does not read, hash or manage the add-in's files or its input; it copies the name, the version and
the contract it declared and the provenance its result gives, without reading them, into the provenance of every
artifact (``record``).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import re
import sys
import tomllib
from types import ModuleType
from typing import Any

from ..calc.bearing_actions import load_model_context
from ..core.errors import InputError
from ..core.printed import LENGTH
from ..inputs import PierInput
from ..inputs.model import CalculationSection
from ..loadmodel import (
    CONTRACT_VERSION, ColumnSectionFunction, LoadModel, LoadModelResult, validate, validate_column_section,
)

MANIFEST = "webpier-addin.toml"
_ENTRY = re.compile(r"([A-Za-z_][A-Za-z0-9_]*):([A-Za-z_][A-Za-z0-9_]*)")


class AddinError(Exception):
    """The add-in cannot be read or run (ADDIN_ERROR)."""


@dataclass
class Addin:
    folder: Path
    name: str
    version: str
    contract: int
    model: LoadModel
    section: ColumnSectionFunction | None = None  # column_section (decision 118); None: the 実断面
    _last: tuple[PierInput, LoadModelResult] | None = field(default=None, repr=False)

    def with_section(self, pier: PierInput, input_path: Path) -> PierInput:
        """*pier* with the 計算上断面 of the column the add-in gives, checked against its 実断面 (decision 118);
        *pier* as it is when the add-in gives none."""
        if self.section is None:
            return pier
        try:
            section = self.section(load_model_context(pier, input_path))
        except InputError:
            raise
        except Exception as exc:  # the add-in's code
            raise AddinError(f"アドイン {self.name} の column_section が失敗しました: "
                             f"{type(exc).__name__}: {exc}") from exc
        b6, w6 = (Decimal(f"{size.value:.3f}") for size in (pier.substructure.b[6], pier.substructure.w[6]))
        validate_column_section(section, b6, w6)
        return replace(pier, calculation_section=CalculationSection(LENGTH(float(section.along)),
                                                                    LENGTH(float(section.across))))

    def calculate(self, pier: PierInput, input_path: Path) -> LoadModelResult:
        """The load model's result for *pier* (once for the input read), checked by the application."""
        if self._last is None or self._last[0] is not pier:
            context = load_model_context(pier, input_path)
            try:
                result = self.model.calculate(context)
            except InputError:
                raise
            except Exception as exc:  # the add-in's code: anything it raises stops the generation
                raise AddinError(f"アドイン {self.name} の calculate が失敗しました: {type(exc).__name__}: {exc}") from exc
            self._last = (pier, validate(result, context))
        return self._last[1]

    def record(self, result: LoadModelResult | None) -> dict[str, Any]:
        """What the provenance records of the add-in: as it declared itself, and the provenance it returned."""
        return {"name": self.name, "version": self.version, "contract": self.contract,
                "provenance": {} if result is None else dict(result.provenance)}

    def bind(self, input_path: Path) -> BoundAddin:
        return BoundAddin(self, Path(input_path))


@dataclass(frozen=True)
class BoundAddin:
    """The add-in for one input file: what the stages of a load model read (pipeline.stages.stages_for)."""

    addin: Addin
    input_path: Path

    def result(self, pier: PierInput) -> LoadModelResult:
        return self.addin.calculate(pier, self.input_path)

    def with_section(self, pier: PierInput) -> PierInput:
        return self.addin.with_section(pier, self.input_path)

    def record(self, pier: PierInput) -> dict[str, Any]:
        return self.addin.record(self.result(pier))


def _declared(manifest: dict[str, Any], key: str, kind: type, path: Path) -> Any:
    value = manifest.get(key)
    if not isinstance(value, kind) or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
        raise AddinError(f"{path}: {key} の宣言がありません（{kind.__name__} が必要です）")
    return value


def _function(folder: Path, name: str, declared: str, key: str, path: Path, modules: dict[str, ModuleType]) -> Any:
    """The function *declared* ("module:function") of the add-in's *key*, its module imported once into *modules*."""
    match = _ENTRY.fullmatch(declared)
    if match is None:
        raise AddinError(f"{path}: {key} は「モジュール:関数」の形が必要です（{declared}）")
    module_name, function = match.groups()
    try:
        if module_name not in modules:
            modules[module_name] = _module(folder, name, module_name)
        return getattr(modules[module_name], function)
    except AddinError:
        raise
    except Exception as exc:  # the add-in's code
        raise AddinError(f"アドイン {name} を読み込めません（{declared}）: {type(exc).__name__}: {exc}") from exc


def _module(folder: Path, name: str, module_name: str) -> ModuleType:
    source = folder / f"{module_name}.py"
    package = folder / module_name / "__init__.py"
    unique = f"webpier_addin_{abs(hash(folder.resolve()))}_{module_name}"
    if package.is_file():
        spec = spec_from_file_location(unique, package, submodule_search_locations=[str(package.parent)])
    elif source.is_file():
        spec = spec_from_file_location(unique, source)
    else:
        raise AddinError(f"アドイン {name} のモジュール {module_name} が {folder} にありません")
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[unique] = module
    spec.loader.exec_module(module)
    return module


def load_addin(folder: Path) -> Addin:
    """The add-in of *folder*, imported and its load model made (``AddinError`` when it cannot be)."""
    folder = Path(folder)
    path = folder / MANIFEST
    try:
        manifest = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise AddinError(f"アドインの宣言 {path} がありません") from None
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise AddinError(f"アドインの宣言 {path} を読めません: {exc}") from exc
    name = _declared(manifest, "name", str, path)
    version = _declared(manifest, "version", str, path)
    contract = _declared(manifest, "contract", int, path)
    entry = _declared(manifest, "entry", str, path)
    if contract != CONTRACT_VERSION:
        raise AddinError(f"アドイン {name} の約束の版 {contract} は、この WebPier の約束の版 {CONTRACT_VERSION} と違います")
    modules: dict[str, ModuleType] = {}
    factory = _function(folder, name, entry, "entry", path, modules)
    try:
        model = factory()
    except Exception as exc:  # the add-in's code
        raise AddinError(f"アドイン {name} を読み込めません（{entry}）: {type(exc).__name__}: {exc}") from exc
    if not callable(getattr(model, "calculate", None)):
        raise AddinError(f"アドイン {name} の {entry} が返したものに calculate がありません")
    section = None
    if "column_section" in manifest:
        declared = _declared(manifest, "column_section", str, path)
        section = _function(folder, name, declared, "column_section", path, modules)
        if not callable(section):
            raise AddinError(f"アドイン {name} の {declared} は関数が必要です")
    return Addin(folder, name, version, contract, model, section)


__all__ = ["MANIFEST", "Addin", "AddinError", "BoundAddin", "load_addin"]
