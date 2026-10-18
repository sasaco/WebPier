"""One generation: calculate → render → publish all files together (CLAUDE.md, ADR-0004).

1. The selection and every destination are checked before anything is read or calculated.
2. The input is read once as bytes; its SHA256 is recorded in every result JSON and sidecar. It is always
   parsed strictly (duplicate keys, NaN and Infinity are input errors).
3. The selected stages and their dependencies are all calculated, and every export of the selected stages
   built, before any report is rendered; an input that only an export reads (the JRSNAP settings) is an input
   error before any rendering. A stage with a load diagram (0610, 0620) has the FEMPython runner draw its staged
   FrameWeb file, and its report takes those pages (decision 44); a stage with a データ確認図 (0710, 0720) has the
   JRSNAP runner draw it from its NDU the same way (decision 50). A stage with a frame analysis (0611, 0621,
   opt-in) has the runner analyze the FrameWeb file of its dependency, in a separate call, before any report is
   rendered; the returned pickup files are staged as they are (decision 46). A stage with a static nonlinear
   analysis (0711, 0721, opt-in) has the JRSNAP runner analyze the NDU of its dependency the same way; every returned
   file is staged, under JRSNAP's name, in one folder (decision 47), and beside it the Aggre-SE project that reads
   the DB1 of each Case (decision 49; its input is checked before any analysis). Each export is built once, so the file
   analyzed is the bytes staged, even when the dependency's own files are not published. The runners are looked
   up before anything is read, and a missing or failing runner stops the generation.
4. Reports, result JSON, exports, pickup files, the JRSNAP folder and their provenance sidecars are written to
   staging beside each destination, then published as one set by ``publication.publish_outputs`` (the folder is
   replaced whole). A final validator checks the published bytes, the files that were displaced, the input and
   the implementation identity, and any mismatch restores every old file.

Errors: ``InputError`` (the input is invalid), ``GenerationError`` (the input, the implementation or an output
changed during the generation, a report cannot be laid out, or a runner is missing or failed) and ``OSError``
(destinations, file system; ``RecoveryError`` when the old files could not all be restored) are reported to the
user. Anything else is a bug.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gridlayoutpdf import LayoutError

from ..core.integrity import canonical_sha256, content_sha256, dump_json, file_sha256, load_json, sha256
from ..core.errors import InputError
from ..export.aggrese import ProjectError
from ..inputs import PierInput, parse_input
from . import capacita, jrsnap
from .fempython import (ENGINE, AnalysisFiles, LoadDiagramPages, RunnerError, analyze_frame, draw_load_diagram,
                        runner_path)
from .publication import ArtifactStaging, backup_path, publish_outputs, validate_destinations
from .runtime import RuntimeIdentityError, dependency_hashes
from .serialize import SCHEMA_VERSION, result_document, to_json
from .stages import (ALL, FRAME_ANALYSIS, NONLINEAR_ANALYSIS, STAGES, Export, FrameAnalysis, NonlinearAnalysis,
                     Project, Registry, SectionCheck)

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
    frame_analysis: bool = False  # add the opt-in stages to all: FEMPython analyzes the frames (decision 46)
    nonlinear_analysis: bool = False  # add the opt-in stages to all: JRSNAP analyzes the NDU (decision 47)

    @property
    def switches(self) -> frozenset[str]:
        return frozenset(name for name, given in ((FRAME_ANALYSIS, self.frame_analysis),
                                                  (NONLINEAR_ANALYSIS, self.nonlinear_analysis)) if given)


@dataclass(frozen=True)
class Artifact:
    role: str  # "0610.pdf", "0610.json", "0610.frameweb", "0610.frameweb.provenance", "0611.pik", "0711.jrsnap"
    path: Path  # the destination
    directory: str  # "output" or "post", as recorded in the sidecars
    folder: bool = False  # a folder replaced whole (the JRSNAP analysis, decision 47); its SHA256 is content_sha256


@dataclass(frozen=True)
class _PostFile:
    stage: str
    kind: str
    native: Artifact
    sidecar: Artifact
    export: Export | None  # none: a file the stage's frame analysis returns, or the folder of its JRSNAP analysis
    project: Project | None = None  # the Aggre-SE project beside that folder (decision 49)
    check: SectionCheck | None = None  # the completed WDJ of the stage's column section check (decision 48)


def _identity() -> dict[Path, str]:
    try:
        return dependency_hashes()
    except (RuntimeIdentityError, LayoutError) as exc:
        raise GenerationError(f"プログラム・描画依存を確認できません: {exc}") from exc


def _state(path: Path) -> str | None:
    return content_sha256(path) if path.exists() else None


def _plan(options: GenerationOptions, registry: Registry, selected: tuple[str, ...]
          ) -> tuple[list[Artifact], list[_PostFile]]:
    reports, posts = [], []
    for stage_id in selected:
        stage = registry.get(stage_id)
        if stage.has_report:
            for suffix in ("pdf", "json"):
                reports.append(Artifact(f"{stage_id}.{suffix}", Path(options.output_dir) / f"{stage.stem}.{suffix}",
                                        "output"))
        files = [(item.kind, item.file_name, item, False, None, None) for item in stage.exports]
        if stage.frame_analysis is not None:
            files += [(kind, file_name, None, False, None, None) for kind, file_name in stage.frame_analysis.files]
        if (check := stage.section_check) is not None:
            files.append((check.kind, check.file_name, None, False, None, check))
        if (nonlinear := stage.nonlinear_analysis) is not None:
            files.append((nonlinear.kind, nonlinear.folder, None, True, None, None))
            if (project := nonlinear.project) is not None:
                files.append((project.kind, project.file_name, None, False, project, None))
        for kind, file_name, item, folder, project, check in files:
            native = Artifact(f"{stage_id}.{kind}", Path(options.post_dir) / file_name, "post", folder)
            sidecar = Artifact(f"{native.role}.provenance", native.path.with_name(file_name + PROVENANCE_SUFFIX),
                               "post")
            posts.append(_PostFile(stage_id, kind, native, sidecar, item, project, check))
    return [*reports, *(post.native for post in posts), *(post.sidecar for post in posts)], posts


def _select(options: GenerationOptions, registry: Registry) -> tuple[str, ...]:
    return registry.select(options.stage, switches=options.switches)


def _folders(artifacts: list[Artifact]) -> tuple[Path, ...]:
    return tuple(artifact.path for artifact in artifacts if artifact.folder)


def planned(options: GenerationOptions, *, registry: Registry = STAGES) -> tuple[Artifact, ...]:
    """The files a generation with *options* publishes, in publication order; nothing is read or written.

    The editor uses it to check a finished generation against exactly the files the CLI wrote.
    """
    return tuple(_plan(options, registry, _select(options, registry))[0])


def _calculate(registry: Registry, pier: PierInput, selected: tuple[str, ...]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for stage_id in registry.closure(selected):
        stage = registry.get(stage_id)
        if stage.calculate is not None:
            results[stage_id] = stage.calculate(pier, {name: results[name] for name in stage.depends_on
                                                       if name in results})
    return results


def _own(registry: Registry, results: Mapping[str, Any], stage_id: str) -> dict[str, Any]:
    """The results a stage's report and exports may read: its dependencies and itself (those that calculate)."""
    return {name: results[name] for name in (*registry.get(stage_id).depends_on, stage_id) if name in results}


def _source(registry: Registry, analysis: FrameAnalysis | NonlinearAnalysis) -> Export:
    """The export an analysis reads, FrameWeb or NDU (the registry checked that it exists)."""
    return next(item for item in registry.get(analysis.stage).exports if item.kind == analysis.export)


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


def project_bytes(pier: PierInput, stage_id: str, names: Sequence[str], *, registry: Registry = STAGES) -> bytes:
    """The Aggre-SE project of *stage_id* for the JRSNAP result files *names*, as a generation writes it.

    The real-app acceptance rebuilds its candidate with this (decision 49).
    """
    (selected,) = registry.select(stage_id)
    analysis = registry.get(selected).nonlinear_analysis
    if analysis is None or analysis.project is None:
        raise InputError(f"{selected}に Aggre-SE のプロジェクトはありません")
    results = _calculate(registry, pier, (selected,))
    return analysis.project.build(_own(registry, results, analysis.stage), pier)(analysis.folder, names)


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
        self._sha256 = {artifact.role: content_sha256(self.staged(artifact.role)) for artifact in artifacts}
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
            if content_sha256(self.staged(artifact.role)) != self._sha256[artifact.role]:
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
                        final_validator=self._verify_published, folders=_folders(list(self.artifacts)))
        self.published = True


def _sidecar(post: _PostFile, staging: ArtifactStaging, artifacts: list[Artifact], common: Mapping[str, Any],
             facts: Mapping[str, Any]) -> bytes:
    listed = [{"role": artifact.role, "directory": artifact.directory, "file": artifact.path.name,
               "sha256": content_sha256(staging.path_for(artifact.path))}
              for artifact in artifacts if not artifact.role.endswith(".provenance")]
    return dump_json({"schema_version": SCHEMA_VERSION, "stage": post.stage, "export": post.kind,
                      "file": post.native.path.name, "sha256": content_sha256(staging.path_for(post.native.path)),
                      **facts, **common, "artifacts": listed})


def _export_facts(registry: Registry, post: _PostFile, drawn: Mapping[str, LoadDiagramPages],
                  checked: Mapping[str, jrsnap.DataCheckPages]) -> dict[str, Any]:
    facts: dict[str, Any] = {"metadata": to_json(post.export.metadata)}
    if post.kind == registry.get(post.stage).load_diagram:
        # The runner's pages are FEMPython's (decision 44): only which runner drew them is recorded.
        facts["load_diagram"] = {"report": f"{post.stage}.pdf", "engine": ENGINE,
                                 "engine_version": drawn[post.stage].engine_version}
    if post.kind == registry.get(post.stage).data_check:
        # The pages are JRSNAP's (decision 50): which runner drew which figures of which combination, and what it
        # reports of JRSNAP and of the .ndt it wrote from this file.
        pages = checked[post.stage]
        facts["data_check"] = {"report": f"{post.stage}.pdf", "engine": jrsnap.ENGINE,
                               "engine_version": pages.engine_version, "case": jrsnap.DATA_CHECK_CASE,
                               "figures": list(jrsnap.DATA_CHECK_FIGURES), "runner_summary": dict(pages.summary)}
    return facts


def _analysis_facts(registry: Registry, post: _PostFile, analyzed: Mapping[str, AnalysisFiles],
                    built: Mapping[tuple[str, str], bytes]) -> dict[str, Any]:
    # The returned files are FEMPython's (decision 46): which runner returned them, and for which bytes. The
    # FrameWeb file need not be of this generation (a stage chosen alone), so its SHA256 is what binds them.
    analysis = registry.get(post.stage).frame_analysis
    return {"frame_analysis": {"engine": ENGINE, "engine_version": analyzed[post.stage].engine_version,
                               "frameweb": {"stage": analysis.stage, "export": analysis.export,
                                            "file": _source(registry, analysis).file_name,
                                            "sha256": sha256(built[(analysis.stage, analysis.export)])}}}


def _nonlinear_facts(registry: Registry, post: _PostFile, staging: ArtifactStaging,
                     analyzed: Mapping[str, jrsnap.NonlinearFiles], built: Mapping[tuple[str, str], bytes]
                     ) -> dict[str, Any]:
    # The returned files are JRSNAP's (decision 47): which runner returned them for which bytes, what it reports of
    # JRSNAP and of the confirmations it answered, and each file. The NDU need not be of this generation (a stage
    # chosen alone), so its SHA256 is what binds them.
    analysis = registry.get(post.stage).nonlinear_analysis
    result = analyzed[post.stage]
    folder = staging.path_for(post.native.path)
    return {"nonlinear_analysis": {"engine": jrsnap.ENGINE, "engine_version": result.engine_version,
                                   "engineering_status": "not_checked",
                                   "ndu": {"stage": analysis.stage, "export": analysis.export,
                                           "file": _source(registry, analysis).file_name,
                                           "sha256": sha256(built[(analysis.stage, analysis.export)])},
                                   "runner_summary": dict(result.summary),
                                   "messages": [dict(message) for message in result.messages]},
            "files": [{"file": name, "bytes": (folder / name).stat().st_size, "sha256": file_sha256(folder / name)}
                      for name in sorted(result.files)]}


def _pik_name(registry: Registry, stage_id: str) -> str:
    """The file name of the PIK the stage's frame analysis returns (the registry checked that it exists)."""
    return dict(registry.get(stage_id).frame_analysis.files)["pik"]


def _check_facts(registry: Registry, post: _PostFile, inspected: Mapping[str, capacita.ColumnCheckPages],
                 given: Mapping[str, bytes], analyzed: Mapping[str, AnalysisFiles]) -> dict[str, Any]:
    # The completed WDJ is Capacita's (decision 48): which runner returned it, for which WDJ and which PIK. Capacita
    # returns no judgement, so the check is recorded as run, not as passed (ADR-0008).
    return {"section_check": {"engine": capacita.ENGINE, "engine_version": inspected[post.stage].engine_version,
                              "engineering_status": "not_evaluated",
                              "pik": {"stage": post.stage, "kind": "pik", "file": _pik_name(registry, post.stage),
                                      "sha256": sha256(analyzed[post.stage].files["pik"])},
                              "wdj_given": {"sha256": sha256(given[post.stage])}}}


def _project_facts(registry: Registry, post: _PostFile, staging: ArtifactStaging) -> dict[str, Any]:
    # The project names the DB1 of the JRSNAP folder published beside it (decision 49): which folder, and its bytes.
    analysis = registry.get(post.stage).nonlinear_analysis
    folder = staging.path_for(post.native.path.with_name(analysis.folder))
    return {"metadata": to_json(post.project.metadata),
            "aggrese_project": {"jrsnap": {"stage": post.stage, "export": analysis.kind, "file": analysis.folder,
                                           "sha256": content_sha256(folder)}}}


def _write_project(post: _PostFile, writer: Callable[[str, Sequence[str]], bytes], folder: str,
                   names: Sequence[str]) -> bytes:
    try:
        return writer(folder, names)
    except ProjectError as exc:
        raise GenerationError(f"{post.native.path.name} を作れません: {exc}") from exc


def _runner(registry: Registry, selected: tuple[str, ...]) -> Path | None:
    if not any(registry.get(stage_id).load_diagram or registry.get(stage_id).frame_analysis is not None
               for stage_id in selected):
        return None
    try:
        return runner_path()
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _capacita_runner(registry: Registry, selected: tuple[str, ...]) -> Path | None:
    if not any(registry.get(stage_id).section_check is not None for stage_id in selected):
        return None
    try:
        return capacita.runner_path()
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _check_column(pik_name: str, wdj: bytes, pik: bytes, runner: Path, sections: tuple[str, ...]
                  ) -> capacita.ColumnCheckPages:
    try:
        return capacita.check_column(wdj, pik_name, pik, runner, sections)
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _jrsnap_runner(registry: Registry, selected: tuple[str, ...]) -> Path | None:
    if not any(registry.get(stage_id).data_check or registry.get(stage_id).nonlinear_analysis is not None
               for stage_id in selected):
        return None
    try:
        return jrsnap.runner_path()
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _draw(document: Path, runner: Path) -> LoadDiagramPages:
    try:
        return draw_load_diagram(document, runner)
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _draw_data_check(name: str, document: bytes, runner: Path) -> jrsnap.DataCheckPages:
    try:
        return jrsnap.draw_data_check(name, document, runner)
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _analyze(name: str, document: bytes, runner: Path) -> AnalysisFiles:
    try:
        return analyze_frame(name, document, runner)
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _analyze_nonlinear(name: str, document: bytes, runner: Path) -> jrsnap.NonlinearFiles:
    try:
        return jrsnap.analyze_nonlinear(name, document, runner)
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _build(registry: Registry, pier: PierInput, results: Mapping[str, Any], posts: list[_PostFile],
           analyses: Mapping[str, FrameAnalysis | NonlinearAnalysis]) -> dict[tuple[str, str], bytes]:
    """Each export to stage or to analyze, built once: the file a runner analyzes is the file staged."""
    wanted = [*((post.stage, post.export) for post in posts if post.export is not None),
              *((analysis.stage, _source(registry, analysis)) for analysis in analyses.values())]
    built: dict[tuple[str, str], bytes] = {}
    for stage_id, item in wanted:
        if (stage_id, item.kind) not in built:
            built[(stage_id, item.kind)] = item.build(_own(registry, results, stage_id), pier)
    return built


@contextmanager
def prepare(options: GenerationOptions, *, registry: Registry = STAGES) -> Iterator[Candidate]:
    """Calculate and stage one generation; the caller decides whether to ``publish`` it."""
    selected = _select(options, registry)
    artifacts, posts = _plan(options, registry, selected)
    destinations = [artifact.path for artifact in artifacts]
    validate_destinations(destinations, overwrite=options.overwrite, input_path=Path(options.input_path),
                          folders=_folders(artifacts))
    baseline = {path: _state(path) for path in destinations}
    identity = _identity()
    runner = _runner(registry, selected)
    jrsnap_runner = _jrsnap_runner(registry, selected)
    capacita_runner = _capacita_runner(registry, selected)
    data = Path(options.input_path).read_bytes()
    input_sha256 = sha256(data)
    pier = parse_input(load_json(data))
    results = _calculate(registry, pier, selected)
    analyses = {stage_id: analysis for stage_id in selected
                if (analysis := registry.get(stage_id).frame_analysis) is not None}
    nonlinear = {stage_id: analysis for stage_id in selected
                 if (analysis := registry.get(stage_id).nonlinear_analysis) is not None}
    built = _build(registry, pier, results, posts, {**analyses, **nonlinear})
    # The projects' input is checked now, before any analysis or report; each is written from the analysis' files.
    writers = {stage_id: analysis.project.build(_own(registry, results, analysis.stage), pier)
               for stage_id, analysis in nonlinear.items() if analysis.project is not None}
    common = {"input": {"file": Path(options.input_path).name, "sha256": input_sha256},
              "implementation_sha256": canonical_sha256({str(path): digest for path, digest in identity.items()})}
    with ArtifactStaging(destinations) as staging:
        by_role = {artifact.role: artifact for artifact in artifacts}
        for post in posts:
            if post.export is not None:
                staging.path_for(post.native.path).write_bytes(built[(post.stage, post.kind)])
        drawn = {post.stage: _draw(staging.path_for(post.native.path), runner) for post in posts
                 if runner is not None and post.kind == registry.get(post.stage).load_diagram}
        checked = {post.stage: _draw_data_check(post.native.path.name, built[(post.stage, post.kind)], jrsnap_runner)
                   for post in posts
                   if post.export is not None and post.kind == registry.get(post.stage).data_check}
        analyzed = {stage_id: _analyze(_source(registry, analysis).file_name,
                                       built[(analysis.stage, analysis.export)], runner)
                    for stage_id, analysis in analyses.items()}
        solved = {stage_id: _analyze_nonlinear(_source(registry, analysis).file_name,
                                               built[(analysis.stage, analysis.export)], jrsnap_runner)
                  for stage_id, analysis in nonlinear.items()}
        # Capacita checks the column with the PIK the stage's own frame analysis returned (decision 48).
        given: dict[str, bytes] = {}
        inspected: dict[str, capacita.ColumnCheckPages] = {}
        for stage_id in selected:
            if (check := registry.get(stage_id).section_check) is not None:
                own = _own(registry, results, stage_id)
                given[stage_id] = check.build(own, pier)
                inspected[stage_id] = _check_column(_pik_name(registry, stage_id), given[stage_id],
                                                    analyzed[stage_id].files["pik"], capacita_runner,
                                                    tuple(check.sections(own)))
        for post in posts:
            if post.native.folder:
                folder = staging.path_for(post.native.path)
                folder.mkdir()
                for name, content in solved[post.stage].files.items():
                    (folder / name).write_bytes(content)
            elif post.project is not None:
                analysis = registry.get(post.stage).nonlinear_analysis
                staging.path_for(post.native.path).write_bytes(
                    _write_project(post, writers[post.stage], analysis.folder, list(solved[post.stage].files)))
            elif post.check is not None:
                staging.path_for(post.native.path).write_bytes(inspected[post.stage].wdj)
            elif post.export is None:
                staging.path_for(post.native.path).write_bytes(analyzed[post.stage].files[post.kind])
        for stage_id in selected:
            if not registry.get(stage_id).has_report:
                continue
            pages = ((drawn[stage_id].pdf,) if stage_id in drawn else (checked[stage_id].pdf,) if stage_id in checked
                     else (inspected[stage_id],) if stage_id in inspected else ())
            try:
                registry.get(stage_id).render(_own(registry, results, stage_id), pier,
                                              staging.path_for(by_role[f"{stage_id}.pdf"].path), *pages)
            except LayoutError as exc:
                raise GenerationError(f"{stage_id}の帳票を作成できません: {exc}") from exc
            document = result_document(stage_id, results[stage_id], input_file=common["input"]["file"],
                                       input_sha256=input_sha256,
                                       implementation_sha256=common["implementation_sha256"])
            if stage_id in inspected:  # that the check ran, not its judgement (ADR-0008)
                document["section_check"] = {
                    "engine": capacita.ENGINE, "engine_version": inspected[stage_id].engine_version,
                    "engineering_status": "not_evaluated",
                    "wdj": {"file": registry.get(stage_id).section_check.file_name,
                            "sha256": sha256(inspected[stage_id].wdj)}}
            staging.path_for(by_role[f"{stage_id}.json"].path).write_bytes(dump_json(document))
        for post in posts:
            facts = (_export_facts(registry, post, drawn, checked) if post.export is not None
                     else _nonlinear_facts(registry, post, staging, solved, built) if post.native.folder
                     else _project_facts(registry, post, staging) if post.project is not None
                     else _check_facts(registry, post, inspected, given, analyzed) if post.check is not None
                     else _analysis_facts(registry, post, analyzed, built))
            content = _sidecar(post, staging, artifacts, {**common, "selected_stages": list(selected)}, facts)
            staging.path_for(post.sidecar.path).write_bytes(content)
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
