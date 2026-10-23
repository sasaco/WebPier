"""The headless runner (decision 61): one generation as a protocol v1 runner that structural-mcp starts.

``run_headless.py`` at the repository root runs ``main``::

    run      --input <JSON> --output-dir <empty folder> [--addin <folder>]
    validate --input <JSON> [--output-dir <folder>] [--addin <folder>]
    contract [--addin <folder>]
    schema   [--addin <folder>]

``--addin`` reads a load model's add-in (decision 70, pipeline.addin): the stages are those of the load model
(``stages_for``), the input is read without its items, and every result JSON, sidecar and the summary record the
add-in as it declared itself and the provenance it returned (``addin``). An add-in that cannot be read or run is
``ADDIN_ERROR`` (exit 2); an error in its own input is ``INPUT_ERROR``. ``schema --addin`` marks the items of the load
model (``x-webpier-load-model``), which may then hold anything or be left out.

Which stages ``run`` and ``validate`` take is the input's 出力項目 alone (``outputs``, decision 72, ADR-0011); the
summary names the chosen items. ``run`` is one generation by ``generate`` as the CLI makes it, with ``output/`` and ``post/`` under the output folder
(never ``--overwrite``: the folder is new). ``validate`` checks the input as far as it is decided before any runner
(``generate.validate``). ``contract`` gives the stages, their dependencies, and for each 出力項目 its stages, the
items it uses, the runners choosing it needs and the files it publishes, and ``schema`` the JSON Schema of the input; both from the registry and the field table, not written by
hand.

stdout is one JSON envelope (protocol v1) and nothing else; anything a library prints goes to stderr. The runners are
only those of the process environment (``STRUCTURAL_MCP_*_RUNNER``): before a generation every runner it calls is
looked up there without the ``.env`` file, and a missing one is ``RUNNER_UNAVAILABLE``, so the generation never
reads ``.env`` either. Exit codes are the CLI's: 0 ``ok``; 2 an argument, the input, the add-in, a runner, the
generation or the file system (``INVALID_ARGUMENT``, ``INPUT_ERROR``, ``ADDIN_ERROR``, ``RUNNER_UNAVAILABLE``,
``ENGINE_FAILED``, ``GENERATION_FAILED``, ``IO_ERROR``) and nothing published; 3 ``RECOVERY_REQUIRED``. An input error names the input path when its message
does.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import redirect_stdout
import json
from pathlib import Path
import re
import sys
import tomllib
from types import ModuleType
from typing import Any

from ..core.errors import InputError
from ..core.integrity import sha256
from ..inputs.fields import FIELDS, Field
from ..inputs.outputs import OUTPUT_ITEMS, uses
from ..inputs.parse import BEARING_SLOTS, SCHEMA_VERSION as INPUT_SCHEMA_VERSION, TOP_KEYS, load_model_item
from ..inputs.rebar import REBAR_VERSION
from .cli import EXIT_ERROR, EXIT_RECOVERY, PROJECT_DIR
from .addin import AddinError
from .fempython import RunnerError
from .generate import (RUNNERS, Candidate, GenerationError, GenerationOptions, generate, planned, required_runners,
                       selection, validate, with_addin)
from .publication import RecoveryError
from .stages import STAGES, Registry

ENGINE = "webpier"
PROTOCOL_VERSION = 1
READINESS = "experimental"
COMMANDS = ("run", "validate", "contract", "schema")
_MEDIA_TYPES = {".pdf": "application/pdf", ".json": "application/json", ".wdj": "application/json",
                ".xml": "application/xml", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".pik": "text/plain", ".ndu": "text/plain", ".csv": "text/csv"}
_BINARY = "application/octet-stream"
_STATUSES = ("not_ok", "ok")  # the judgements a stage can return, the first one deciding the whole (decision 54)
_NOT_EVALUATED = "not_evaluated"
_PATH = re.compile(r"(?:入力項目がありません: )?([^:\s]+)(?::|$)")


class _ArgumentError(Exception):
    """The command line is not one of the runner's."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # argparse would print and exit; the envelope reports it instead
        raise _ArgumentError(message)


def parser() -> argparse.ArgumentParser:
    result = _Parser(prog="run_headless.py", description="WebPier の headless runner（protocol v1）")
    commands = result.add_subparsers(dest="command", required=True)
    for command in ("run", "validate"):
        sub = commands.add_parser(command)
        sub.add_argument("--input", type=Path, required=True)
        sub.add_argument("--output-dir", type=Path, required=command == "run")
        sub.add_argument("--addin", type=Path)
    for command in ("contract", "schema"):
        commands.add_parser(command).add_argument("--addin", type=Path)
    return result


def engine_version() -> str:
    """The version of the webpier project (pyproject.toml)."""
    return tomllib.loads((PROJECT_DIR / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def _envelope(ok: bool, summary: Any, *, engineering: str = _NOT_EVALUATED, artifacts: Sequence[Mapping] = (),
              errors: Sequence[Mapping] = (), messages: Sequence[Mapping] = ()) -> dict[str, Any]:
    return {"protocolVersion": PROTOCOL_VERSION, "engine": ENGINE, "engineVersion": engine_version(),
            "readiness": READINESS, "ok": ok, "executionStatus": "success" if ok else "failed",
            "engineeringStatus": engineering, "summary": summary, "messages": list(messages),
            "artifacts": list(artifacts), "errors": list(errors)}


def input_path(message: str) -> str | None:
    """The input path an error message names first (``<path>: …`` or ``入力項目がありません: <path>``), if any."""
    match = _PATH.match(message)
    if match is None:
        return None
    path = match.group(1)
    return path if re.split(r"[.\[]", path, maxsplit=1)[0] in TOP_KEYS else None


def _failure(code: str, exc: BaseException | str, summary: Any = None, *,
             category: str = "execution") -> tuple[int, dict[str, Any]]:
    message = str(exc)
    path = input_path(message) if code == "INPUT_ERROR" else None
    error = {"category": category, "code": code, "message": message, **({"path": path} if path else {})}
    text = {"level": "error", "code": code, "text": message, "path": path}
    return (EXIT_RECOVERY if code == "RECOVERY_REQUIRED" else EXIT_ERROR,
            _envelope(False, summary, errors=[error], messages=[text]))


def _options(arguments: argparse.Namespace, output_dir: Path) -> GenerationOptions:
    return GenerationOptions(arguments.input, output_dir / "output", output_dir / "post", addin=arguments.addin,
                             export_dir=output_dir / "export")


def _chosen(registry: Registry, selected: Sequence[str]) -> list[str]:
    """The 出力項目 of the stages *selected*, in registry order."""
    return list(dict.fromkeys(registry.item(stage_id) for stage_id in selected))


def _runner(module: ModuleType) -> dict[str, Any]:
    return {"engine": module.ENGINE, "environmentVariable": module.RUNNER_KEY}


def _available(module: ModuleType) -> bool:
    try:
        module.runner_path(dotenv=False)
    except RunnerError:
        return False
    return True


def _media_type(path: Path, data: bytes, in_folder: bool) -> str:
    media = _BINARY if in_folder else _MEDIA_TYPES.get(path.suffix.lower(), _BINARY)
    if not media.startswith("text/"):
        return media
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return f"{media}; charset=shift_jis"  # the NDU and Aggre-SE's files are CP932
    return f"{media}; charset=utf-8"


def _published(generation: Candidate) -> Iterator[tuple[str, Path, bool]]:
    """(kind, file, inside a folder) of every published file; a folder's files one by one (decision 47)."""
    for artifact in generation.artifacts:
        kind = artifact.role.replace(".", "-")
        if artifact.folder:
            for path in sorted(item for item in artifact.path.rglob("*") if item.is_file()):
                yield kind, path, True
        else:
            yield kind, artifact.path, False


def _artifacts(root: Path, generation: Candidate) -> list[dict[str, Any]]:
    listed = []
    for kind, path, in_folder in _published(generation):
        data = path.read_bytes()
        listed.append({"kind": kind, "mediaType": _media_type(path, data, in_folder),
                       "relativePath": path.resolve().relative_to(root).as_posix(), "bytes": len(data),
                       "sha256": sha256(data)})
    return listed


def _engine_versions(documents: Sequence[Any]) -> dict[str, set[str]]:
    """The ``engine_version`` of each ``engine`` the result JSON and the sidecars record (decisions 44〜60)."""
    found: dict[str, set[str]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("engine"), str) and isinstance(value.get("engine_version"), str):
                found.setdefault(value["engine"], set()).add(value["engine_version"])
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for document in documents:
        visit(document)
    return found


def _stage_status(result: Any) -> str:
    status = getattr(result, "engineering_status", _NOT_EVALUATED)
    return status if status in _STATUSES else _NOT_EVALUATED


def engineering_status(statuses: Sequence[str]) -> str:
    """not_ok when a stage is, else ok when a stage judged ok, else not_evaluated (no stage judges)."""
    return next((status for status in _STATUSES if status in statuses), _NOT_EVALUATED)


def _run(arguments: argparse.Namespace, registry: Registry) -> tuple[int, dict[str, Any]]:
    root = arguments.output_dir.resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        return _failure("INVALID_ARGUMENT", f"--output-dir は空のフォルダーにしてください: {root}", category="request")
    options = _options(arguments, root)
    summary: dict[str, Any] = {"command": arguments.command}
    try:
        registry = with_addin(options, registry)
        selected = selection(options, registry=registry)
    except AddinError as exc:
        return _failure("ADDIN_ERROR", exc, summary, category="addin")
    except InputError as exc:
        return _failure("INPUT_ERROR", exc, summary, category="input")
    except OSError as exc:
        return _failure("IO_ERROR", exc, summary, category="file_system")
    summary["outputs"] = _chosen(registry, selected)
    needed = required_runners(selected, registry=registry)
    if missing := [module for module in needed if not _available(module)]:
        names = "・".join(f"{module.ENGINE}（{module.RUNNER_KEY}）" for module in missing)
        return _failure("RUNNER_UNAVAILABLE", f"この生成に必要な runner がありません: {names}",
                        {**summary, "missingRunners": [_runner(module) for module in missing]},
                        category="engine_unavailable")
    try:
        generation = generate(options, registry=registry)
    except RecoveryError as exc:
        return _failure("RECOVERY_REQUIRED", exc, summary, category="file_system")
    except InputError as exc:
        return _failure("INPUT_ERROR", exc, summary, category="input")
    except AddinError as exc:
        return _failure("ADDIN_ERROR", exc, summary, category="addin")
    except GenerationError as exc:
        code = "ENGINE_FAILED" if isinstance(exc.__cause__, RunnerError) else "GENERATION_FAILED"
        return _failure(code, exc, summary)
    except OSError as exc:
        return _failure("IO_ERROR", exc, summary, category="file_system")
    artifacts = _artifacts(root, generation)
    # The result JSON (role "<stage>.json") and the sidecars ("….provenance") name the runners and their versions.
    versions = _engine_versions([json.loads((root / item["relativePath"]).read_bytes()) for item in artifacts
                                 if item["kind"].endswith(("-json", "-provenance"))])
    stages = [{"id": stage_id, "stem": registry.get(stage_id).stem, "hasReport": registry.get(stage_id).has_report,
               "engineeringStatus": _stage_status(generation.results.get(stage_id))} for stage_id in generation.stages]
    status = engineering_status([stage["engineeringStatus"] for stage in stages])
    summary = {**summary, "stages": stages, "engineeringStatus": status,
               "runners": [{**_runner(module), "engineVersions": sorted(versions.get(module.ENGINE, ()))}
                           for module in needed],
               "input": {"file": Path(arguments.input).name, "sha256": generation.input_sha256},
               "implementationSha256": generation.implementation_sha256,
               **({} if generation.addin is None else {"addin": generation.addin})}
    return 0, _envelope(True, summary, engineering=status, artifacts=artifacts)


def _validate(arguments: argparse.Namespace, registry: Registry) -> tuple[int, dict[str, Any]]:
    # Nothing is written, so the destinations are only names.
    options = _options(arguments, Path("."))
    summary: dict[str, Any] = {"command": arguments.command}
    try:
        registry = with_addin(options, registry)
        selected = validate(options, registry=registry)
        needed = required_runners(selected, registry=registry)
    except AddinError as exc:
        return _failure("ADDIN_ERROR", exc, summary, category="addin")
    except InputError as exc:
        return _failure("INPUT_ERROR", exc, summary, category="input")
    except OSError as exc:
        return _failure("IO_ERROR", exc, summary, category="file_system")
    summary = {**summary, "outputs": _chosen(registry, selected), "stages": list(selected),
               "requiredRunners": [{**_runner(module), "available": _available(module)} for module in needed]}
    return 0, _envelope(True, summary)


def _declared(arguments: argparse.Namespace, registry: Registry) -> tuple[Registry, dict[str, Any]]:
    """For contract and schema: the registry of the add-in of ``--addin``, and its declaration for the summary."""
    if arguments.addin is None:
        return registry, {}
    bound = with_addin(GenerationOptions(Path("input.json"), Path("output"), Path("post"), addin=arguments.addin,
                                      export_dir=Path("export")),
                       registry)
    addin = bound.load_model.addin  # type: ignore[union-attr]
    return bound, {"addin": {"name": addin.name, "version": addin.version, "contract": addin.contract}}


def _contract(arguments: argparse.Namespace, registry: Registry) -> tuple[int, dict[str, Any]]:
    try:
        registry, declared = _declared(arguments, registry)
    except AddinError as exc:
        return _failure("ADDIN_ERROR", exc, {"command": "contract"}, category="addin")
    return 0, _envelope(True, {**contract(registry), **declared})


def _schema(arguments: argparse.Namespace, registry: Registry) -> tuple[int, dict[str, Any]]:
    try:
        _, declared = _declared(arguments, registry)
    except AddinError as exc:
        return _failure("ADDIN_ERROR", exc, {"command": "schema"}, category="addin")
    return 0, _envelope(True, {"command": "schema", "schema": input_schema(load_model=bool(declared)), **declared})


def contract(registry: Registry = STAGES) -> dict[str, Any]:
    """The stages, and for each 出力項目 (decision 72) its stages, the items it uses, the runners choosing it calls
    (with the items it uses, which are chosen with it) and the files it publishes (``planned``), from the registry."""
    options = GenerationOptions(Path("input.json"), Path("output"), Path("post"), export_dir=Path("export"))

    def output(key: str, requires: tuple[str, ...]) -> dict[str, Any]:
        stages = registry.outputs.get(key, ())
        needed = [stage_id for item in (*uses(key), key) for stage_id in registry.outputs.get(item, ())]
        return {"key": key, "requires": list(requires), "stages": list(stages),
                "runners": [module.ENGINE for module in required_runners(needed, registry=registry)],
                "files": [{"role": artifact.role, "path": f"{artifact.directory}/{artifact.path.name}",
                           "folder": artifact.folder} for artifact in planned(options, stages, registry=registry)]}

    return {"command": "contract",
            "stages": [{"id": stage.id, "stem": stage.stem, "dependsOn": list(stage.depends_on),
                        "output": registry.item(stage.id), "hasReport": stage.has_report}
                       for stage in registry.stages],
            "runners": [_runner(module) for module in RUNNERS],
            "outputs": [output(item.key, item.requires) for item in OUTPUT_ITEMS]}


def _parts(pattern: str) -> list[str]:
    """The keys of a field pattern; a key with a dot in it (``k=0.06``) is joined back: no key is all digits."""
    parts: list[str] = []
    for part in pattern.split("."):
        if part.isdigit() and parts:
            parts[-1] += "." + part
        else:
            parts.append(part)
    return parts


def _leaf(spec: Field) -> dict[str, Any]:
    if spec.kind == "blank":
        return {"type": "null", "description": spec.message}
    if spec.kind == "choice":
        leaf: dict[str, Any] = {"enum": [*spec.choices, *((None,) if spec.nullable else ())]}
    elif spec.kind == "integer":
        leaf = {"type": "integer", "minimum": spec.minimum, "maximum": spec.maximum}
    elif spec.kind == "text":
        leaf = {"type": "string"}
    elif spec.kind == "boolean":
        leaf = {"type": "boolean"}
    else:
        leaf = {"type": "number", "x-webpier-unit": spec.unit, "x-webpier-digits": spec.precision.digits}
        if spec.sign == "positive":
            leaf["exclusiveMinimum"] = 0
        elif spec.sign == "nonnegative":
            leaf["minimum"] = 0
        if spec.limit is not None:
            leaf["x-webpier-limit"] = spec.limit.message
    if spec.nullable and "type" in leaf:
        leaf["type"] = [leaf["type"], "null"]
    if spec.reserved:
        leaf["x-webpier-reserved"] = True
    return leaf


def _object() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": False}  # the parser rejects unknown keys


_LOAD_MODEL = {"description": "荷重モデル（--addin）では読まない項目（どの値でも、なくてもよい）", "x-webpier-load-model": True}


def input_schema(*, load_model: bool = False) -> dict[str, Any]:
    """The JSON Schema of the schema 2 input from the field table (fields.FIELDS): the keys, and each value's type,
    choices, range, sign, unit and printed digits. Which values a stage needs and the rules between fields are the
    parser's (``validate``). With *load_model* the items of the load model are any value (decision 70): the train,
    the 列車分担 of a bearing, and each other item of it (parse.load_model_item)."""
    root = _object()
    root["properties"]["schema_version"] = {"const": INPUT_SCHEMA_VERSION}
    root["properties"]["出典"] = {"description": "入力の出典（自由な形式。計算には使わない）"}
    for pattern, spec in FIELDS.items():
        node = root
        *branches, last = _parts(pattern)  # a field is a scalar of an object, or a list of scalars (杭の列の位置)
        for branch in branches:
            name, array = (branch[:-3], True) if branch.endswith("[*]") else (branch, False)
            child = node["properties"].setdefault(name, {"type": "array", "items": _object()} if array else _object())
            node = child["items"] if array else child
        leaf = _LOAD_MODEL if load_model and load_model_item(pattern) else _leaf(spec)
        if last.endswith("[*]"):
            node["properties"][last[:-3]] = {"type": "array", "items": leaf}
        else:
            node["properties"][last] = leaf
    rebar = root["properties"]["鉄筋"]["properties"]
    rebar["version"] = {"const": REBAR_VERSION}
    rebar["梁"]["properties"]["side_bars"]["type"] = ["object", "null"]  # null: no side bars (rebar._beam_side)
    reactions = root["properties"]["上部工反力"]["properties"]
    for side, slots in (("起点側", "B支点"), ("終点側", "C支点")):  # an empty bearing slot is null (parse._bearing)
        array = reactions[side]["properties"][slots]
        array["items"]["type"] = ["object", "null"]
        array["minItems"] = array["maxItems"] = BEARING_SLOTS
        if load_model:
            array["items"]["properties"]["列車分担"] = _LOAD_MODEL
    if load_model:
        root["properties"]["上部構造"]["properties"]["列車"] = _LOAD_MODEL
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "WebPier 入力（schema 2）",
            "description": "項目・型・選択肢・範囲・単位（x-webpier-unit）・印字桁（x-webpier-digits）。空欄は null、"
                           "空き支承枠は枠ごと null。必須の項目と項目間の規則（段階が要る値の空欄、印字桁より細かい値など）"
                           "は書かず、webpier の validate が入力エラーにする。x-webpier-reserved は形式だけを検証する予約項目。",
            **root}


_COMMANDS: dict[str, Callable[[argparse.Namespace, Registry], tuple[int, dict[str, Any]]]] = {
    "run": _run, "validate": _validate,
    "contract": _contract, "schema": _schema,
}


def main(argv: list[str] | None = None, *, registry: Registry = STAGES) -> int:
    """Run one command and write its envelope to stdout; anything else printed meanwhile goes to stderr."""
    stdout = sys.stdout
    with redirect_stdout(sys.stderr):
        try:
            arguments = parser().parse_args(argv)
        except _ArgumentError as exc:
            code, envelope = _failure("INVALID_ARGUMENT", exc, category="request")
        else:
            code, envelope = _COMMANDS[arguments.command](arguments, registry)
    stdout.buffer.write(json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
    stdout.flush()
    return code
