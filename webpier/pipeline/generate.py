"""One generation: calculate → render → publish all files together (CLAUDE.md, ADR-0004).

1. The selection and every destination are checked before anything is read or calculated.
2. The input is read once as bytes; its SHA256 is recorded in every result JSON and sidecar. It is always
   parsed strictly (duplicate keys, NaN and Infinity are input errors).
3. The selected stages and their dependencies are all calculated, and every export of the selected stages
   built, before any report is rendered; an input that only an export reads (the JRSNAP settings) is an input
   error before any rendering. A stage with a load diagram (0610, 0620) has the FEMPython runner draw its staged
   FrameWeb file, and its report takes those pages (decision 44); the runner is looked up before anything is
   read, and a missing or failing runner stops the generation.
4. Reports, result JSON, exports and their provenance sidecars are written to staging beside each
   destination, then published as one set by ``publication.publish_outputs``. A final validator checks the
   published bytes, the files that were displaced, the input and the implementation identity, and any
   mismatch restores every old file.

Errors: ``InputError`` (the input is invalid), ``GenerationError`` (the input, the implementation or an output
changed during the generation, a report cannot be laid out, or the FEMPython runner is missing or failed) and ``OSError`` (destinations, file system;
``RecoveryError`` when the old files could not all be restored) are reported to the user. Anything else is a bug.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gridlayoutpdf import LayoutError

from ..core.integrity import canonical_sha256, dump_json, file_sha256, load_json, sha256
from ..core.errors import InputError
from ..inputs import PierInput, parse_input
from .fempython import LoadDiagramPages, RunnerError, draw_load_diagram, runner_path
from .publication import ArtifactStaging, backup_path, publish_outputs, validate_destinations
from .runtime import RuntimeIdentityError, dependency_hashes
from .serialize import SCHEMA_VERSION, result_document, to_json
from .stages import ALL, STAGES, Export, Registry

PROVENANCE_SUFFIX = ".provenance.json"


class GenerationError(Exception):
    """The generation cannot be published as one consistent set; nothing was published."""


@dataclass(frozen=True)
class GenerationOptions:
    input_path: Path
    output_dir: Path  # reports and result JSON
    post_dir: Path  # external-program inputs and their sidecars
    stage: str = ALL
    overwrite: bool = False


@dataclass(frozen=True)
class Artifact:
    role: str  # "0610.pdf", "0610.json", "0610.frameweb", "0610.frameweb.provenance"
    path: Path  # the destination
    directory: str  # "output" or "post", as recorded in the sidecars


def _identity() -> dict[Path, str]:
    try:
        return dependency_hashes()
    except (RuntimeIdentityError, LayoutError) as exc:
        raise GenerationError(f"プログラム・描画依存を確認できません: {exc}") from exc


def _state(path: Path) -> str | None:
    return file_sha256(path) if path.exists() else None


def _plan(options: GenerationOptions, registry: Registry, selected: tuple[str, ...]
          ) -> tuple[list[Artifact], list[tuple[str, Export, Artifact, Artifact]]]:
    reports, exports, sidecars = [], [], []
    planned = []
    for stage_id in selected:
        stage = registry.get(stage_id)
        for suffix in ("pdf", "json"):
            reports.append(Artifact(f"{stage_id}.{suffix}", Path(options.output_dir) / f"{stage.stem}.{suffix}",
                                    "output"))
        for item in stage.exports:
            native = Artifact(f"{stage_id}.{item.kind}", Path(options.post_dir) / item.file_name, "post")
            sidecar = Artifact(f"{native.role}.provenance", native.path.with_name(item.file_name + PROVENANCE_SUFFIX),
                               "post")
            exports.append(native)
            sidecars.append(sidecar)
            planned.append((stage_id, item, native, sidecar))
    return [*reports, *exports, *sidecars], planned


def planned(options: GenerationOptions, *, registry: Registry = STAGES) -> tuple[Artifact, ...]:
    """The files a generation with *options* publishes, in publication order; nothing is read or written.

    The editor uses it to check a finished generation against exactly the files the CLI wrote.
    """
    return tuple(_plan(options, registry, registry.select(options.stage))[0])


def _calculate(registry: Registry, pier: PierInput, selected: tuple[str, ...]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for stage_id in registry.closure(selected):
        stage = registry.get(stage_id)
        results[stage_id] = stage.calculate(pier, {name: results[name] for name in stage.depends_on})
    return results


def _own(registry: Registry, results: Mapping[str, Any], stage_id: str) -> dict[str, Any]:
    """The results a stage's report and exports may read: its dependencies and itself."""
    return {name: results[name] for name in (*registry.get(stage_id).depends_on, stage_id)}


def export_bytes(pier: PierInput, stage_id: str, kind: str, *, registry: Registry = STAGES) -> bytes:
    """The bytes of one export of *stage_id*, as a generation writes them; no report is rendered.

    The real-app acceptance rebuilds its candidate files with this.
    """
    (selected,) = registry.select(stage_id)
    item = next((item for item in registry.get(selected).exports if item.kind == kind), None)
    if item is None:
        raise InputError(f"{selected}に{kind} の出力はありません")
    results = _calculate(registry, pier, (selected,))
    return item.build(_own(registry, results, selected), pier)


class Candidate:
    """A generation held in staging; ``publish`` replaces the destinations with exactly these bytes, once."""

    def __init__(self, options: GenerationOptions, stages: tuple[str, ...], results: Mapping[str, Any],
                 artifacts: list[Artifact], staging: ArtifactStaging, input_sha256: str,
                 identity: Mapping[Path, str], baseline: Mapping[Path, str | None]) -> None:
        self.options = options
        self.stages = stages
        self.results = results
        self.artifacts = tuple(artifacts)
        self.input_sha256 = input_sha256
        self.published = False
        self._staging = staging
        self._identity = dict(identity)
        self._baseline = dict(baseline)
        self._sha256 = {artifact.role: file_sha256(self.staged(artifact.role)) for artifact in artifacts}
        self._active = True
        self._attempted = False

    def staged(self, role: str) -> Path:
        artifact = next(artifact for artifact in self.artifacts if artifact.role == role)
        return self._staging.path_for(artifact.path)

    def _check_sources(self) -> None:
        if file_sha256(self.options.input_path) != self.input_sha256:
            raise GenerationError("生成中に入力ファイルが変更されました。再生成してください")
        if _identity() != self._identity:
            raise GenerationError("生成中にプログラム・描画依存が変更されました。再生成してください")

    def verify(self) -> None:
        """The staged files, the input, the implementation and the destinations are as at the start."""
        staged = {self.staged(artifact.role) for artifact in self.artifacts}
        present = {path for directory in self._staging.directories.values() for path in directory.iterdir()}
        if present != staged:
            raise GenerationError("一時領域のファイル集合が変更されています")
        for artifact in self.artifacts:
            if file_sha256(self.staged(artifact.role)) != self._sha256[artifact.role]:
                raise GenerationError(f"一時領域の成果物が変更されています: {artifact.role}")
        for path, before in self._baseline.items():
            if _state(path) != before:
                raise GenerationError(f"生成中に出力先が変更されました: {path}")
        self._check_sources()

    def _verify_published(self) -> None:
        for artifact in self.artifacts:
            if _state(artifact.path) != self._sha256[artifact.role]:
                raise GenerationError(f"公開した成果物が一致しません: {artifact.role}")
        for path, before in self._baseline.items():
            if _state(backup_path(self._staging.directories, path)) != before:
                raise GenerationError(f"公開の直前に出力先が変更されました: {path}")
        self._check_sources()

    def publish(self) -> None:
        if not self._active:
            raise GenerationError("生成の保持期間が終わっています。再生成してください")
        if self._attempted:
            raise GenerationError("この生成は既に公開を試みました。再生成してください")
        self._attempted = True
        self.verify()
        pairs = [(self.staged(artifact.role), artifact.path) for artifact in self.artifacts]
        publish_outputs(pairs, self._staging.directories, self.options.overwrite,
                        final_validator=self._verify_published)
        self.published = True


def _sidecar(stage_id: str, item: Export, native: Artifact, staging: ArtifactStaging,
             artifacts: list[Artifact], common: Mapping[str, Any], drawn: LoadDiagramPages | None) -> bytes:
    listed = [{"role": artifact.role, "directory": artifact.directory, "file": artifact.path.name,
               "sha256": file_sha256(staging.path_for(artifact.path))}
              for artifact in artifacts if not artifact.role.endswith(".provenance")]
    # The runner's pages are FEMPython's (decision 44): only which runner drew them is recorded.
    diagram = {} if drawn is None else {"load_diagram": {"report": f"{stage_id}.pdf", "engine": "fempython",
                                                         "engine_version": drawn.engine_version}}
    return dump_json({"schema_version": SCHEMA_VERSION, "stage": stage_id, "export": item.kind,
                      "file": item.file_name, "sha256": file_sha256(staging.path_for(native.path)),
                      "metadata": to_json(item.metadata), **diagram, **common, "artifacts": listed})


def _runner(registry: Registry, selected: tuple[str, ...]) -> Path | None:
    if not any(registry.get(stage_id).load_diagram for stage_id in selected):
        return None
    try:
        return runner_path()
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _draw(document: Path, runner: Path) -> LoadDiagramPages:
    try:
        return draw_load_diagram(document, runner)
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


@contextmanager
def prepare(options: GenerationOptions, *, registry: Registry = STAGES) -> Iterator[Candidate]:
    """Calculate and stage one generation; the caller decides whether to ``publish`` it."""
    selected = registry.select(options.stage)
    artifacts, exports = _plan(options, registry, selected)
    destinations = [artifact.path for artifact in artifacts]
    validate_destinations(destinations, overwrite=options.overwrite, input_path=Path(options.input_path))
    baseline = {path: _state(path) for path in destinations}
    identity = _identity()
    runner = _runner(registry, selected)
    data = Path(options.input_path).read_bytes()
    input_sha256 = sha256(data)
    pier = parse_input(load_json(data))
    results = _calculate(registry, pier, selected)
    common = {"input": {"file": Path(options.input_path).name, "sha256": input_sha256},
              "implementation_sha256": canonical_sha256({str(path): digest for path, digest in identity.items()})}
    with ArtifactStaging(destinations) as staging:
        by_role = {artifact.role: artifact for artifact in artifacts}
        for stage_id, item, native, _ in exports:
            staging.path_for(native.path).write_bytes(item.build(_own(registry, results, stage_id), pier))
        drawn = {stage_id: _draw(staging.path_for(native.path), runner)
                 for stage_id, item, native, _ in exports
                 if runner is not None and item.kind == registry.get(stage_id).load_diagram}
        for stage_id in selected:
            pages = (drawn[stage_id].pdf,) if stage_id in drawn else ()
            try:
                registry.get(stage_id).render(_own(registry, results, stage_id), pier,
                                              staging.path_for(by_role[f"{stage_id}.pdf"].path), *pages)
            except LayoutError as exc:
                raise GenerationError(f"{stage_id}の帳票を作成できません: {exc}") from exc
            document = result_document(stage_id, results[stage_id], input_file=common["input"]["file"],
                                       input_sha256=input_sha256,
                                       implementation_sha256=common["implementation_sha256"])
            staging.path_for(by_role[f"{stage_id}.json"].path).write_bytes(dump_json(document))
        for stage_id, item, native, sidecar in exports:
            content = _sidecar(stage_id, item, native, staging, artifacts,
                               {**common, "selected_stages": list(selected)},
                               drawn.get(stage_id) if item.kind == registry.get(stage_id).load_diagram else None)
            staging.path_for(sidecar.path).write_bytes(content)
        candidate = Candidate(options, selected, results, artifacts, staging, input_sha256, identity, baseline)
        try:
            yield candidate
        finally:
            candidate._active = False


def generate(options: GenerationOptions, *, registry: Registry = STAGES) -> Candidate:
    """Calculate, render and publish one generation."""
    with prepare(options, registry=registry) as candidate:
        candidate.publish()
    return candidate
