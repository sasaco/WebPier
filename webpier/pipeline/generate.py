"""One generation: calculate → render → publish all files together (CLAUDE.md, ADR-0004).

1. The input is read once as bytes; its SHA256 is recorded in every result JSON and sidecar. It is always
   parsed strictly (duplicate keys, NaN and Infinity are input errors).
2. Its 出力項目 select the stages (decision 72, ADR-0011): an item is chosen only with every item it uses, so they are
   every stage the generation calculates. Every destination is checked before anything is calculated.
3. The selected stages are all calculated, and every export of them built, before any report is rendered; an input that only an export reads (the JRSNAP settings) is an input
   error before any rendering. A stage with a load diagram (0610, 0620) has the FEMPython runner draw its staged
   FrameWeb file, and its report takes those pages (decision 44); a stage with JRSNAP's figures (0710, 0720) has the
   JRSNAP runner draw the データ確認図 and the 荷重図 from its NDU in one call, each basic case from the combination
   the stage names for it, and its report takes those pages the same way (decisions 50, 51). A stage with a frame analysis (0611, 0612, 0621,
   0622) has the runner analyze the FrameWeb file of its dependency, in a separate call, before any report is
   rendered; the returned pickup files are staged as they are (decision 46). Stages that analyze the same file share
   one call and one set of files, staged under the first of them; a stage that reads them (the 基礎の照査, decision
   54) finishes its result with them before any report is rendered. A stage with a static nonlinear
   analysis (0711, 0721) has the JRSNAP runner analyze the NDU of its dependency the same way; every returned
   file is staged, under JRSNAP's name, in one folder (decision 47), and beside it the Aggre-SE project that reads
   the DB1 of each Case (decision 49; its input is checked before any analysis). The Aggre-SE runner then checks with
   that staged project and folder: its report is the stage's report as it is (decision 56) and its section force
   pickup and summary workbook are staged as they are (decisions 57, 58). Each export is built
   once, so the file analyzed is the bytes staged. A stage with SOIL-JR's calculation (0500 of a pile foundation, decision
   85, ADR-0013) has the JRSNAP runner calculate its .sdt in one call, before any report is rendered: the report is
   SOIL-JR's as the runner printed it, its .sdr and .sdc (and the two for the liquefaction, when the input considers it)
   are staged as they are, and the stage finishes its result with them. The runners are looked up before anything is
   calculated, and a missing or failing runner stops the generation. The stages are those of the input's 基礎形式
   (``Registry.for_foundation``).
4. Reports, their grid Excel workbooks (export/: the pages WebPier lays out, ``StageSpec.grid_documents``, on one
   sheet, written strictly), result JSON, exports, pickup files, the JRSNAP folder and their provenance sidecars are
   written to staging beside each destination, then published as one set by ``publication.publish_outputs`` (the folder is
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
from types import ModuleType
from typing import Any

from gridlayoutpdf import LayoutError, XlsxError

from ..core.integrity import canonical_sha256, content_sha256, dump_json, file_sha256, load_json, sha256
from ..core.errors import InputError
from ..export.aggrese import ProjectError
from ..calc.cantilever import ResponseError
from ..calc.footing import StepsError
from ..calc.foundation_check import ReactionError
from ..calc.pile_check import PileResponseError
from ..export.capacita import PickupError
from ..export.soiljr import SdrError
from ..inputs import PierInput, parse_input
from ..reporting.workbook import write_workbook
from . import aggrese, capacita, fempython, jrsnap
from .addin import load_addin
from .fempython import ENGINE, AnalysisFiles, LoadDiagramPages, RunnerError, analyze_frame, draw_load_diagram
from .publication import ArtifactStaging, backup_path, publish_outputs, validate_destinations
from .runtime import RuntimeIdentityError, dependency_hashes
from .serialize import SCHEMA_VERSION, result_document, to_json
from .stages import (STAGES, Export, FrameAnalysis, NonlinearAnalysis, Project, Registry, SectionCheck, SeismicCheck,
                     SoilJrCalculation, StageSpec, seismic_file, stages_for)

PROVENANCE_SUFFIX = ".provenance.json"


class GenerationError(Exception):
    """The generation cannot be published as one consistent set; nothing was published."""


@dataclass(frozen=True)
class GenerationOptions:
    input_path: Path
    output_dir: Path  # reports and result JSON
    post_dir: Path  # external-program inputs and their sidecars
    overwrite: bool = False
    addin: Path | None = None  # the folder of a load model's add-in (decision 70); none: the train's
    export_dir: Path | None = None  # where the grid Excel workbooks go; none: they are not written (decision 75)


@dataclass(frozen=True)
class Artifact:
    role: str  # "0610.pdf", "0610.xlsx", "0610.json", "0610.frameweb", "0610.frameweb.provenance", "0711.jrsnap"
    path: Path  # the destination
    directory: str  # "output", "export" or "post", as recorded in the sidecars
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
    seismic: SeismicCheck | None = None  # a file of the stage's 耐震性能照査 (decisions 57, 58)
    soil: SoilJrCalculation | None = None  # a file SOIL-JR returned for the stage's .sdt (decision 85)


def _identity() -> dict[Path, str]:
    try:
        return dependency_hashes()
    except (RuntimeIdentityError, LayoutError) as exc:
        raise GenerationError(f"プログラム・描画依存を確認できません: {exc}") from exc


def _implementation_sha256(identity: Mapping[Path, str]) -> str:
    return canonical_sha256({str(path): digest for path, digest in identity.items()})


def _state(path: Path) -> str | None:
    return content_sha256(path) if path.exists() else None


def _analysis_key(analysis: FrameAnalysis) -> tuple[str, str]:
    """The FrameWeb file an analysis reads: stages with the same key share one analysis (decision 54)."""
    return analysis.stage, analysis.export


def _plan(options: GenerationOptions, registry: Registry, selected: tuple[str, ...], pier: PierInput | None = None
          ) -> tuple[list[Artifact], list[_PostFile]]:
    """The files of a generation of *selected* stages of *registry* (the stages of the input's 基礎形式). Which files
    SOIL-JR returns depends on the input (the two for the liquefaction), so they are planned only with its *pier*."""
    reports, posts = [], []
    analyzed: set[tuple[str, str]] = set()
    for stage_id in selected:
        stage = registry.get(stage_id)
        if stage.has_report:
            for suffix in ("pdf", "json"):
                reports.append(Artifact(f"{stage_id}.{suffix}", Path(options.output_dir) / f"{stage.stem}.{suffix}",
                                        "output"))
        if stage.grid_documents is not None and options.export_dir is not None:
            reports.append(Artifact(f"{stage_id}.xlsx", Path(options.export_dir) / f"{stage.stem}.xlsx", "export"))
        files = [(item.kind, item.file_name, item, False, None, None, None) for item in stage.exports]
        if stage.frame_analysis is not None and _analysis_key(stage.frame_analysis) not in analyzed:
            analyzed.add(_analysis_key(stage.frame_analysis))
            files += [(kind, file_name, None, False, None, None, None)
                      for kind, file_name in stage.frame_analysis.files]
        if (check := stage.section_check) is not None:
            files.append((check.kind, check.file_name, None, False, None, check, None))
        if (nonlinear := stage.nonlinear_analysis) is not None:
            files.append((nonlinear.kind, nonlinear.folder, None, True, None, None, None))
            if (project := nonlinear.project) is not None:
                files.append((project.kind, project.file_name, None, False, project, None, None))
        if (seismic := stage.seismic_check) is not None:
            files += [(kind, file_name, None, False, None, None, seismic) for kind, file_name in seismic.files]
        ground = stage.soil_jr
        returned = () if ground is None else (*ground.files, *(ground.liquefaction if pier is not None
                                                                and ground.liquefied(pier) else ()))
        files += [(kind, file_name, None, False, None, None, None) for kind, file_name in returned]
        for kind, file_name, item, folder, project, check, seismic in files:
            native = Artifact(f"{stage_id}.{kind}", Path(options.post_dir) / file_name, "post", folder)
            sidecar = Artifact(f"{native.role}.provenance", native.path.with_name(file_name + PROVENANCE_SUFFIX),
                               "post")
            posts.append(_PostFile(stage_id, kind, native, sidecar, item, project, check, seismic,
                                   ground if (kind, file_name) in returned else None))
    return [*reports, *(post.native for post in posts), *(post.sidecar for post in posts)], posts


def _stale(options: GenerationOptions, artifacts: list[Artifact]) -> list[Artifact]:
    """Everything in the output folders that this generation does not write (decision 82, replacing decision 74's
    registry-only removal): a publication empties ``output``, ``export`` and ``post`` just before the new files go in,
    so old and new files are never mixed. Only with ``overwrite``; without it nothing is touched. The input file (or
    a folder holding it), the staging folders and the output folders themselves are never taken."""
    if not options.overwrite:
        return []
    planned_paths = {artifact.path for artifact in artifacts}
    folders = {"output": options.output_dir, "post": options.post_dir,
               **({} if options.export_dir is None else {"export": options.export_dir})}
    roots = {Path(folder).resolve() for folder in folders.values()}
    protected = Path(options.input_path).resolve()
    stale = []
    for directory, folder in folders.items():
        if not Path(folder).is_dir():
            continue
        for entry in sorted(Path(folder).iterdir()):
            resolved = entry.resolve()
            if (entry in planned_paths or entry.name.startswith(".webpier-") or resolved in roots
                    or protected.is_relative_to(resolved) or any(root.is_relative_to(resolved) for root in roots)):
                continue
            stale.append(Artifact(f"{directory}/{entry.name}", entry, directory, entry.is_dir() and not entry.is_symlink()))
    return stale


def _read(options: GenerationOptions, registry: Registry) -> tuple[bytes, PierInput]:
    """The input's bytes, read once, and the input parsed from them strictly."""
    data = Path(options.input_path).read_bytes()
    return data, parse_input(load_json(data), load_model=registry.load_model is not None)


def resolve(options: GenerationOptions, registry: Registry = STAGES) -> tuple[Registry, tuple[str, ...]]:
    """The registry of the input of *options*, and the stages its 出力項目 choose in it, in registry order (decision 72):
    the registry of its load model's add-in (decision 70), with the stages of its 基礎形式 (decision 85). The input is read
    and parsed strictly, so an invalid one is an input error."""
    registry = with_addin(options, registry)
    pier = _read(options, registry)[1]
    registry = registry.for_foundation(pier.substructure.foundation)
    return registry, registry.selected(pier.outputs)


def selection(options: GenerationOptions, *, registry: Registry = STAGES) -> tuple[str, ...]:
    """The stages the 出力項目 of the input of *options* choose, in registry order (decision 72); the input is read
    and parsed strictly, so an invalid one is an input error."""
    return resolve(options, registry)[1]


def _folders(artifacts: list[Artifact]) -> tuple[Path, ...]:
    return tuple(artifact.path for artifact in artifacts if artifact.folder)


def planned(options: GenerationOptions, selected: Sequence[str], *, registry: Registry = STAGES,
            pier: PierInput | None = None) -> tuple[Artifact, ...]:
    """The files a generation of the stages *selected* (``selection``) with *options* publishes, in publication order;
    nothing is read or written.

    The editor uses it to check a finished generation against exactly the files the CLI wrote. With the *pier* the
    generation read the files are those of its 基礎形式 and of what its input decides (decision 85); without one, those of
    the direct foundation, and of a pile foundation only the files it always has.
    """
    if pier is not None:
        registry = registry.for_foundation(pier.substructure.foundation)
    return tuple(_plan(options, registry, tuple(selected), pier)[0])


def _calculate(registry: Registry, pier: PierInput, selected: tuple[str, ...], results: dict[str, Any] | None = None,
               *, late: bool = False) -> dict[str, Any]:
    """The results of the *selected* stages and what they read, into *results*. The stages that wait for a runner's
    result (``after``, decision 88, and the stages that read them, decision 89) are the *late* ones: calculated in a
    second call, when 0500 is complete."""
    results = {} if results is None else results
    for stage_id in registry.closure(selected):
        stage = registry.get(stage_id)
        if stage.calculate is not None and registry.waits(stage_id) is late:
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
    registry = registry.for_foundation(pier.substructure.foundation)
    selected = registry.stage(stage_id).id
    item = next((item for item in registry.get(selected).exports if item.kind == kind), None)
    if item is None:
        raise InputError(f"{selected}に{kind} の出力はありません")
    if registry.get(selected).after:
        raise InputError(f"{selected}の「{kind}」は、{'・'.join(registry.get(selected).after)}の SOIL-JR の結果から作るので、"
                         "生成のときだけ作れます")
    results = _calculate(registry, pier, (selected,))
    return item.build(_own(registry, results, selected), pier)


def figure_cases(pier: PierInput, stage_id: str, *, registry: Registry = STAGES) -> tuple[tuple[int, int], ...]:
    """(basic case, combination) of each 荷重図 page JRSNAP draws for *stage_id*, as a generation asks for them.

    The real-app acceptance draws its candidate pages with this (decision 51).
    """
    selected = registry.stage(stage_id).id
    figures = registry.get(selected).jrsnap_figures
    if figures is None:
        raise InputError(f"{selected}に JRSNAP のデータ確認図と荷重図はありません")
    results = _calculate(registry, pier, (selected,))
    return figures.load_cases(_own(registry, results, selected), pier)


def project_bytes(pier: PierInput, stage_id: str, names: Sequence[str], *, registry: Registry = STAGES) -> bytes:
    """The Aggre-SE project of *stage_id* for the JRSNAP result files *names*, as a generation writes it.

    The real-app acceptance rebuilds its candidate with this (decision 49).
    """
    selected = registry.stage(stage_id).id
    analysis = registry.get(selected).nonlinear_analysis
    if analysis is None or analysis.project is None:
        raise InputError(f"{selected}に Aggre-SE のプロジェクトはありません")
    results = _calculate(registry, pier, (selected,))
    return analysis.project.build(_own(registry, results, analysis.stage), pier)(analysis.folder, names)


class Candidate:
    """A generation held in staging; ``publish`` replaces the destinations with exactly these bytes, once."""

    def __init__(self, options: GenerationOptions, stages: tuple[str, ...], results: Mapping[str, Any],
                 artifacts: list[Artifact], staging: ArtifactStaging, input_sha256: str,
                 identity: Mapping[Path, str], baseline: Mapping[Path, str | None],
                 addin: Mapping[str, Any] | None = None, stale: Sequence[Artifact] = ()) -> None:
        self.options = options
        self.stale = tuple(stale)  # earlier artifacts of unselected stages, removed by ``publish`` (decision 74)
        self.addin = addin  # the add-in's provenance of a load model (decision 70), as every artifact records it
        self.stages = stages
        self.results = results
        self.artifacts = tuple(artifacts)
        self.input_sha256 = input_sha256
        self.published = False
        self._staging = staging
        self._identity = dict(identity)
        self._baseline = dict(baseline)
        self._stale_paths = [artifact.path for artifact in self.stale]
        self._sha256 = {artifact.role: content_sha256(self.staged(artifact.role)) for artifact in artifacts}
        self._active = True
        self._attempted = False

    @property
    def implementation_sha256(self) -> str:
        """The implementation identity the result JSON and the sidecars record."""
        return _implementation_sha256(self._identity)

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
                        final_validator=self._verify_published, folders=_folders(list(self.artifacts)),
                        remove=self._stale_paths, remove_folders=_folders(list(self.stale)))
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
                  figures: Mapping[str, jrsnap.FigurePages], grounded: Mapping[str, jrsnap.SoilFiles],
                  built: Mapping[tuple[str, str], bytes]) -> dict[str, Any]:
    facts: dict[str, Any] = {"metadata": to_json(post.export.metadata)}
    if post.stage in grounded and post.kind == registry.get(post.stage).soil_jr.export:
        facts |= _ground_facts(post, grounded, built[(post.stage, post.kind)])
    if post.kind == registry.get(post.stage).load_diagram:
        # The runner's pages are FEMPython's (decision 44): only which runner drew them is recorded.
        facts["load_diagram"] = {"report": f"{post.stage}.pdf", "engine": ENGINE,
                                 "engine_version": drawn[post.stage].engine_version}
    if post.stage in figures and post.kind == registry.get(post.stage).jrsnap_figures.export:
        # The pages are JRSNAP's (decisions 50, 51): which runner drew which figures of which combination, the
        # combination each load diagram page was taken from, and what it reports of JRSNAP and of the .ndt it wrote
        # from this file.
        pages = figures[post.stage]
        facts["jrsnap_figures"] = {"report": f"{post.stage}.pdf", "engine": jrsnap.ENGINE,
                                   "engine_version": pages.engine_version,
                                   "data_check": {"combination": jrsnap.DATA_CHECK_COMBINATION,
                                                  "figures": list(jrsnap.DATA_CHECK_FIGURES)},
                                   "load_diagram": [{"case": case, "combination": combination}
                                                    for case, combination in pages.load_cases],
                                   "runner_summary": dict(pages.summary)}
        if pages.also:  # the load diagrams of the cases the first NDU does not have are from the NDUs of the push the other way
            facts["jrsnap_figures"]["load_diagram_from"] = list(pages.drawn_from)
            facts["jrsnap_figures"]["also"] = [{"export": kind, "engine_version": more.engine_version,
                                                "runner_summary": dict(more.summary)} for kind, more in pages.also]
    return facts


def _ground_facts(post: _PostFile, grounded: Mapping[str, jrsnap.SoilFiles], sdt: bytes) -> dict[str, Any]:
    # The returned files and the report are SOIL-JR's (decision 85, ADR-0013): which runner calculated which .sdt, with
    # what it reports of SOIL-JR and its warnings. It returns no judgement, so the check is recorded as run.
    calculated = grounded[post.stage]
    return {"soil_jr": {"engine": jrsnap.ENGINE, "engine_version": calculated.engine_version,
                        "engineering_status": "not_evaluated", "report": f"{post.stage}.pdf",
                        "sdt": {"stage": post.stage, "export": post.soil.export if post.soil else post.kind,
                                "sha256": sha256(sdt)},
                        "runner_summary": dict(calculated.summary),
                        "messages": [dict(message) for message in calculated.messages]}}


def _analysis_facts(registry: Registry, post: _PostFile, analyzed: Mapping[str, AnalysisFiles],
                    built: Mapping[tuple[str, str], bytes], selected: Sequence[str]) -> dict[str, Any]:
    # The returned files are FEMPython's (decision 46): which runner returned them, for which bytes, and which selected
    # stages used them (decision 54). The FrameWeb file need not be of this generation (a stage chosen alone), so its
    # SHA256 is what binds them.
    analysis = registry.get(post.stage).frame_analysis
    users = [stage_id for stage_id in selected if (other := registry.get(stage_id).frame_analysis) is not None
             and _analysis_key(other) == _analysis_key(analysis)]
    return {"frame_analysis": {"engine": ENGINE, "engine_version": analyzed[post.stage].engine_version,
                               "frameweb": {"stage": analysis.stage, "export": analysis.export,
                                            "file": _source(registry, analysis).file_name,
                                            "sha256": sha256(built[(analysis.stage, analysis.export)])},
                               "stages": users}}


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
    # The completed WDJ is Capacita's (decision 48): which runner returned it, for which WDJ and which PIK. Without a
    # PIK (decision 59) the WDJ is WebPier's, calculated as given: which runner checked it. Capacita returns no
    # judgement, so the check is recorded as run, not as passed (ADR-0008).
    facts: dict[str, Any] = {"engine": capacita.ENGINE, "engine_version": inspected[post.stage].engine_version,
                             "engineering_status": "not_evaluated"}
    if post.stage in analyzed:
        facts["pik"] = {"stage": post.stage, "kind": "pik", "file": _pik_name(registry, post.stage),
                        "sha256": sha256(analyzed[post.stage].files["pik"])}
    facts["wdj_given"] = {"sha256": sha256(given[post.stage])}
    return {"section_check": facts}


def _project_facts(registry: Registry, post: _PostFile, staging: ArtifactStaging,
                   checked: Mapping[str, aggrese.SeismicCheckPages]) -> dict[str, Any]:
    # The project names the DB1 of the JRSNAP folder published beside it (decision 49): which folder, and its bytes;
    # and which runner checked with it for which report (decision 56).
    analysis = registry.get(post.stage).nonlinear_analysis
    folder = staging.path_for(post.native.path.with_name(analysis.folder))
    facts: dict[str, Any] = {
        "metadata": to_json(post.project.metadata),
        "aggrese_project": {"jrsnap": {"stage": post.stage, "export": analysis.kind, "file": analysis.folder,
                                       "sha256": content_sha256(folder)}}}
    if post.stage in checked:
        facts["seismic_check"] = {"report": f"{post.stage}.pdf", "engine": aggrese.ENGINE,
                                  "engine_version": checked[post.stage].engine_version}
    return facts


def _seismic_facts(registry: Registry, post: _PostFile, staging: ArtifactStaging,
                   checked: Mapping[str, aggrese.SeismicCheckPages]) -> dict[str, Any]:
    # The file is Aggre-SE's (decisions 57, 58, 60): which runner returned it with which report, for which project
    # and folder, for the pickup what each of its pickups is, and for the step table what its columns are.
    analysis = registry.get(post.stage).nonlinear_analysis
    project = post.native.path.with_name(analysis.project.file_name)
    folder = staging.path_for(project.with_name(analysis.folder))
    facts = {"report": f"{post.stage}.pdf", "engine": aggrese.ENGINE,
             "engine_version": checked[post.stage].engine_version, "engineering_status": "not_evaluated",
             "project": {"file": project.name, "sha256": file_sha256(staging.path_for(project))},
             "jrsnap": {"file": analysis.folder, "sha256": content_sha256(folder)}}
    if post.kind == "pik":
        facts["pickups"] = {str(number): name for number, name in aggrese.PICKUPS.items()}
    if post.kind == "steps":
        facts["columns"] = list(aggrese.FOUNDATION_STEPS_COLUMNS)
    return {"seismic_check": facts}


def _write_project(post: _PostFile, writer: Callable[[str, Sequence[str]], bytes], folder: str,
                   names: Sequence[str]) -> bytes:
    try:
        return writer(folder, names)
    except ProjectError as exc:
        raise GenerationError(f"{post.native.path.name} を作れません: {exc}") from exc


# The runner each kind of stage calls, by the module that finds and calls it, in the order they are looked up:
# FEMPython draws the load diagrams and analyzes the frames (decisions 44, 46), JRSNAP draws the figures, analyzes
# the NDU and has SOIL-JR calculate the ground of a pile foundation (decisions 47, 50, 51, 85), Capacita checks the sections (decisions 48, 59) and Aggre-SE the seismic checks
# (decision 56).
_RUNNERS: tuple[tuple[ModuleType, Callable[[StageSpec], bool]], ...] = (
    (fempython, lambda stage: bool(stage.load_diagram) or stage.frame_analysis is not None),
    (jrsnap, lambda stage: stage.jrsnap_figures is not None or stage.nonlinear_analysis is not None
     or stage.soil_jr is not None),
    (capacita, lambda stage: stage.section_check is not None),
    (aggrese, lambda stage: stage.seismic_check is not None),
)
RUNNERS = tuple(module for module, _ in _RUNNERS)  # every runner a generation may call, in lookup order


def _required(registry: Registry, selected: Sequence[str]) -> tuple[ModuleType, ...]:
    return tuple(module for module, calls in _RUNNERS
                 if any(calls(registry.get(stage_id)) for stage_id in selected))


def required_runners(selected: Sequence[str], *, registry: Registry = STAGES) -> tuple[ModuleType, ...]:
    """The modules of the runners a generation of the stages *selected* calls (each has ``ENGINE``, ``RUNNER_KEY``
    and ``runner_path``), in the order they are looked up; nothing is read."""
    return _required(registry, selected)


def _runner_paths(registry: Registry, selected: tuple[str, ...]) -> dict[ModuleType, Path]:
    paths: dict[ModuleType, Path] = {}
    for module in _required(registry, selected):
        try:
            paths[module] = module.runner_path()
        except RunnerError as exc:
            raise GenerationError(str(exc)) from exc
    return paths


def _check_seismic(project: Path, folder: Path, runner: Path) -> aggrese.SeismicCheckPages:
    """Aggre-SE's report for the staged *project* and the JRSNAP *folder* it names, which it must leave as they are:
    they are published as staged (decision 56)."""
    before = (content_sha256(project), content_sha256(folder))
    try:
        checked = aggrese.check_seismic(project, runner)
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc
    if (content_sha256(project), content_sha256(folder)) != before:
        raise GenerationError(f"Aggre-SE の runner が {project.name} か {folder.name} を変更しました")
    return checked


def _check_column(pik_name: str, wdj: bytes, pik: bytes, runner: Path, sections: tuple[str, ...]
                  ) -> capacita.ColumnCheckPages:
    try:
        return capacita.check_column(wdj, pik_name, pik, runner, sections)
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _check_section(name: str, wdj: bytes, runner: Path, sections: tuple[str, ...]) -> capacita.ColumnCheckPages:
    try:
        return capacita.check_section(wdj, name, runner, sections)
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _completion_files(registry: Registry, stage_id: str, analyzed: Mapping[str, AnalysisFiles],
                      checked: Mapping[str, aggrese.SeismicCheckPages]) -> dict[str, bytes]:
    """The files a stage's ``complete`` reads: its frame analysis' by kind, and its dependencies' frame analyses' and
    seismic checks' by ``seismic_file`` (decisions 54, 59, 60)."""
    files: dict[str, bytes] = dict(analyzed[stage_id].files) if stage_id in analyzed else {}
    for name in registry.closure(registry.get(stage_id).depends_on):
        for returned in (analyzed, checked):
            if name in returned:
                files |= {seismic_file(name, kind): content for kind, content in returned[name].files.items()}
    return files


def _complete(registry: Registry, stage_id: str, result: Any, files: Mapping[str, bytes], pier: PierInput,
              results: Mapping[str, Any]) -> Any:
    try:
        return registry.get(stage_id).complete(result, files, pier, results)
    except ReactionError as exc:
        analysis = registry.get(stage_id).frame_analysis
        if analysis is None:  # the reactions of its dependencies' analyses (0800, decision 60)
            raise GenerationError(f"依存段階の反力で{stage_id}の結果を仕上げられません: {exc}") from exc
        name = dict(analysis.files)["reaction"]
        raise GenerationError(f"{name} で{stage_id}の基礎の照査ができません: {exc}") from exc
    except StepsError as exc:  # the step table of its dependencies' seismic checks (0800, decision 60)
        raise GenerationError(f"直接基礎のステップ表で{stage_id}の結果を仕上げられません: {exc}") from exc
    except ResponseError as exc:
        raise GenerationError(f"{stage_id}の片持ち梁の照査ができません: {exc}") from exc
    except RunnerError as exc:  # SteelDan's check of the pile body (0612, 0622, decision 89)
        raise GenerationError(str(exc)) from exc
    except PileResponseError as exc:  # the pile heads and the footing top of the frame analysis (0612, 0622, decision 89)
        raise GenerationError(f"骨組解析の結果で{stage_id}の杭基礎の照査ができません: {exc}") from exc
    except SdrError as exc:  # the .sdr SOIL-JR returned for the stage's .sdt (0500, decision 85)
        raise GenerationError(f"SOIL-JR の .sdr で{stage_id}の結果を仕上げられません: {exc}") from exc


def _build_wdj(check: SectionCheck, own: Results, pier: PierInput, pik_name: str, pik: bytes) -> bytes:
    try:
        return check.build(own, pier, pik)
    except PickupError as exc:
        raise GenerationError(f"{pik_name} で柱の断面照査の WDJ を作れません: {exc}") from exc


def _draw(document: Path, runner: Path) -> LoadDiagramPages:
    try:
        return draw_load_diagram(document, runner)
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _draw_figures(name: str, document: bytes, runner: Path, load_cases: Sequence[tuple[int, int]]
                  ) -> jrsnap.FigurePages:
    try:
        return jrsnap.draw_figures(name, document, runner, load_cases)
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _stage_figures(registry: Registry, results: Mapping[str, Any], pier: PierInput, post: _PostFile,
                   posted: Mapping[tuple[str, str], _PostFile], built: Mapping[tuple[str, str], bytes],
                   runner: Path) -> jrsnap.FigurePages:
    """The figures of the NDU of *post*, and the load diagrams of the cases it has none of from the other NDUs of its stage."""
    figures = registry.get(post.stage).jrsnap_figures
    assert figures is not None
    own = _own(registry, results, post.stage)
    pages = _draw_figures(post.native.path.name, built[(post.stage, post.kind)], runner, figures.load_cases(own, pier))
    for other in figures.also:
        second = posted[(post.stage, other.export)]
        more = _draw_figures(second.native.path.name, built[(post.stage, other.export)], runner,
                             other.load_cases(own, pier))
        pages = jrsnap.add_load_diagrams(pages, other.export, more)
    return pages


def _analyze(name: str, document: bytes, runner: Path) -> AnalysisFiles:
    try:
        return analyze_frame(name, document, runner)
    except RunnerError as exc:
        raise GenerationError(str(exc)) from exc


def _calculate_ground(name: str, document: bytes, runner: Path, liquefaction: bool) -> jrsnap.SoilFiles:
    try:
        return jrsnap.calculate_ground(name, document, runner, liquefaction=liquefaction)
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


@dataclass(frozen=True)
class _Inputs:
    """What a generation decides from the input before any runner is called."""

    data: bytes
    pier: PierInput
    results: dict[str, Any]
    analyses: dict[str, FrameAnalysis]
    nonlinear: dict[str, NonlinearAnalysis]
    built: dict[tuple[str, str], bytes]
    writers: dict[str, Callable[[str, Sequence[str]], bytes]]


def with_addin(options: GenerationOptions, registry: Registry = STAGES) -> Registry:
    """*registry* with the load model of ``options.addin`` read once (decision 70): its stages (``stages_for``) bound to
    the input; *registry* as it is without an add-in or when it has a load model already. ``AddinError`` when the
    add-in cannot be read."""
    if options.addin is None or registry.load_model is not None:
        return registry
    return stages_for(load_addin(options.addin).bind(options.input_path))


def _inputs(data: bytes, pier: PierInput, registry: Registry, selected: tuple[str, ...],
            posts: list[_PostFile]) -> _Inputs:
    results = _calculate(registry, pier, selected)
    analyses = {stage_id: analysis for stage_id in selected
                if (analysis := registry.get(stage_id).frame_analysis) is not None}
    nonlinear = {stage_id: analysis for stage_id in selected
                 if (analysis := registry.get(stage_id).nonlinear_analysis) is not None}
    built = _build(registry, pier, results, [post for post in posts if not registry.waits(post.stage)],
                   {key: analysis for key, analysis in {**analyses, **nonlinear}.items()
                    if not registry.waits(analysis.stage)})
    # The projects' input is checked now, before any analysis or report; each is written from the analysis' files.
    writers = {stage_id: analysis.project.build(_own(registry, results, analysis.stage), pier)
               for stage_id, analysis in nonlinear.items() if analysis.project is not None}
    return _Inputs(data, pier, results, analyses, nonlinear, built, writers)


def validate(options: GenerationOptions, *, registry: Registry = STAGES) -> tuple[str, ...]:
    """Check the input of a generation with *options* as far as it is decided before any runner: the strict parse,
    the stages its 出力項目 select and their calculations, every export and the Aggre-SE projects' input.
    Nothing is written and no runner is looked up or called; a result a runner's files finish (decisions 54, 59, 60)
    is checked only by a generation. Returns the selected stages."""
    registry = with_addin(options, registry)
    data, pier = _read(options, registry)
    registry = registry.for_foundation(pier.substructure.foundation)
    selected = registry.selected(pier.outputs)
    _inputs(data, pier, registry, selected, _plan(options, registry, selected, pier)[1])
    return selected


@contextmanager
def prepare(options: GenerationOptions, *, registry: Registry = STAGES) -> Iterator[Candidate]:
    """Calculate and stage one generation; the caller decides whether to ``publish`` it."""
    registry = with_addin(options, registry)
    data, pier = _read(options, registry)
    registry = registry.for_foundation(pier.substructure.foundation)
    selected = registry.selected(pier.outputs)
    artifacts, posts = _plan(options, registry, selected, pier)
    destinations = [artifact.path for artifact in artifacts]
    validate_destinations(destinations, overwrite=options.overwrite, input_path=Path(options.input_path),
                          folders=_folders(artifacts))
    stale = _stale(options, artifacts)
    stale_paths = [artifact.path for artifact in stale]
    validate_destinations(stale_paths, overwrite=True, input_path=Path(options.input_path), folders=_folders(stale))
    baseline = {path: _state(path) for path in [*destinations, *stale_paths]}
    identity = _identity()
    runners = _runner_paths(registry, selected)
    runner, jrsnap_runner = runners.get(fempython), runners.get(jrsnap)
    capacita_runner, aggrese_runner = runners.get(capacita), runners.get(aggrese)
    found = _inputs(data, pier, registry, selected, posts)
    results, built = found.results, found.built
    analyses, nonlinear, writers = found.analyses, found.nonlinear, found.writers
    input_sha256 = sha256(found.data)
    # The add-in as it declared itself and the provenance it returned, copied into every artifact (decision 70).
    addin = None if registry.load_model is None else registry.load_model.record(pier)
    common = {"input": {"file": Path(options.input_path).name, "sha256": input_sha256},
              "implementation_sha256": _implementation_sha256(identity), **({} if addin is None else {"addin": addin})}
    with ArtifactStaging([*destinations, *stale_paths]) as staging:
        by_role = {artifact.role: artifact for artifact in artifacts}
        # SOIL-JR calculates first (decision 85); the stages that stand on its springs follow (decision 88).
        grounded = {stage_id: _calculate_ground(
                        next(item for item in registry.get(stage_id).exports if item.kind == ground.export).file_name,
                        built[(stage_id, ground.export)], jrsnap_runner, ground.liquefied(pier))
                    for stage_id in selected if (ground := registry.get(stage_id).soil_jr) is not None}
        for stage_id in grounded:  # SOIL-JR's files and the .sdt they were calculated from (decision 85)
            files = {**grounded[stage_id].files, "sdt": built[(stage_id, registry.get(stage_id).soil_jr.export)]}
            results[stage_id] = _complete(registry, stage_id, results.get(stage_id), files, pier, results)
        late = [post for post in posts if registry.waits(post.stage)]
        waiting = {key: analysis for key, analysis in analyses.items() if registry.waits(analysis.stage)}
        if late or waiting:
            _calculate(registry, pier, selected, results, late=True)
            built |= _build(registry, pier, results, late, waiting)
        for post in posts:
            if post.export is not None:
                staging.path_for(post.native.path).write_bytes(built[(post.stage, post.kind)])
        drawn = {post.stage: _draw(staging.path_for(post.native.path), runner) for post in posts
                 if runner is not None and post.kind == registry.get(post.stage).load_diagram}
        posted = {(post.stage, post.kind): post for post in posts if post.export is not None}
        figures = {post.stage: _stage_figures(registry, results, pier, post, posted, built, jrsnap_runner)
                   for post in posted.values()
                   if (spec := registry.get(post.stage)).jrsnap_figures is not None
                   and post.kind == spec.jrsnap_figures.export}
        runs: dict[tuple[str, str], AnalysisFiles] = {}  # one call for each FrameWeb file (decision 54)
        for analysis in analyses.values():
            if _analysis_key(analysis) not in runs:
                runs[_analysis_key(analysis)] = _analyze(_source(registry, analysis).file_name,
                                                         built[(analysis.stage, analysis.export)], runner)
        analyzed = {stage_id: runs[_analysis_key(analysis)] for stage_id, analysis in analyses.items()}
        solved = {stage_id: _analyze_nonlinear(_source(registry, analysis).file_name,
                                               built[(analysis.stage, analysis.export)], jrsnap_runner)
                  for stage_id, analysis in nonlinear.items()}
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
        # Aggre-SE checks with the project and the folder staged beside it (decision 56).
        checked = {post.stage: _check_seismic(
                       staging.path_for(post.native.path),
                       staging.path_for(post.native.path.with_name(registry.get(post.stage).nonlinear_analysis.folder)),
                       aggrese_runner)
                   for post in posts
                   if post.project is not None and registry.get(post.stage).seismic_check is not None}
        # A stage finishes its result with the files of its frame analysis, or of the seismic checks of its
        # dependencies, or with their finished results (decisions 54, 59), in registry order.
        for stage_id in selected:
            if registry.get(stage_id).complete is not None and stage_id not in grounded:
                files = _completion_files(registry, stage_id, analyzed, checked)
                results[stage_id] = _complete(registry, stage_id, results.get(stage_id), files, pier, results)
        # Capacita checks the section the stage describes: the column with the PIK the stage's own frame analysis
        # returned (decision 48), or the beam with the section forces written in the WDJ (decision 59).
        given: dict[str, bytes] = {}
        inspected: dict[str, capacita.ColumnCheckPages] = {}
        for stage_id in selected:
            if (check := registry.get(stage_id).section_check) is not None:
                own = _own(registry, results, stage_id)
                if stage_id in analyzed:
                    pik = analyzed[stage_id].files["pik"]
                    given[stage_id] = _build_wdj(check, own, pier, _pik_name(registry, stage_id), pik)
                    inspected[stage_id] = _check_column(_pik_name(registry, stage_id), given[stage_id], pik,
                                                        capacita_runner, tuple(check.sections(own)))
                else:
                    given[stage_id] = check.build(own, pier, None)
                    inspected[stage_id] = _check_section(check.file_name, given[stage_id], capacita_runner,
                                                         tuple(check.sections(own)))
        for post in posts:
            if post.check is not None:
                staging.path_for(post.native.path).write_bytes(inspected[post.stage].wdj)
            elif post.soil is not None:
                staging.path_for(post.native.path).write_bytes(grounded[post.stage].files[post.kind])
            elif post.seismic is not None:
                staging.path_for(post.native.path).write_bytes(checked[post.stage].files[post.kind])
            elif post.export is None and not post.native.folder and post.project is None:
                staging.path_for(post.native.path).write_bytes(analyzed[post.stage].files[post.kind])
        for stage_id in selected:
            if not registry.get(stage_id).has_report:
                continue
            # The pages of other programs, by the name the report takes them: none, or those of one runner.
            pages = {name: content for drawn_by in (drawn, figures, inspected, checked, grounded) if stage_id in drawn_by
                     for name, content in drawn_by[stage_id].pages.items()}
            spec = registry.get(stage_id)
            try:
                spec.render(_own(registry, results, stage_id), pier, staging.path_for(by_role[f"{stage_id}.pdf"].path),
                            pages)
                if spec.grid_documents is not None and options.export_dir is not None:
                    write_workbook(spec.grid_documents(_own(registry, results, stage_id), pier, pages),
                                   staging.path_for(by_role[f"{stage_id}.xlsx"].path), spec.stem)
            except (LayoutError, XlsxError) as exc:
                raise GenerationError(f"{stage_id}の帳票を作成できません: {exc}") from exc
            # A stage whose report is Aggre-SE's has no result of its own (decision 56).
            document = result_document(stage_id, results.get(stage_id), input_file=common["input"]["file"],
                                       input_sha256=input_sha256,
                                       implementation_sha256=common["implementation_sha256"], addin=addin)
            if stage_id in inspected:  # that the check ran, not its judgement (ADR-0008)
                document["section_check"] = {
                    "engine": capacita.ENGINE, "engine_version": inspected[stage_id].engine_version,
                    "engineering_status": "not_evaluated",
                    "wdj": {"file": registry.get(stage_id).section_check.file_name,
                            "sha256": sha256(inspected[stage_id].wdj)},
                    "skipped_sections": list(inspected[stage_id].skipped)}
            if stage_id in checked:  # that the check ran with which files, not its judgement (ADR-0009)
                analysis = registry.get(stage_id).nonlinear_analysis
                project = Path(options.post_dir) / analysis.project.file_name
                document["seismic_check"] = {
                    "engine": aggrese.ENGINE, "engine_version": checked[stage_id].engine_version,
                    "engineering_status": "not_evaluated",
                    "cases": [{key: case.get(key) for key in ("caseNumber", "name", "aggregated")}
                              for case in checked[stage_id].cases],
                    "project": {"file": project.name, "sha256": file_sha256(staging.path_for(project))},
                    "jrsnap": {"file": analysis.folder,
                               "sha256": content_sha256(staging.path_for(project.with_name(analysis.folder)))},
                    "files": {kind: {"file": file_name, "sha256": sha256(checked[stage_id].files[kind])}
                              for kind, file_name in registry.get(stage_id).seismic_check.files}}
            if stage_id in grounded:  # that SOIL-JR calculated, with which files, not a judgement (ADR-0013)
                ground = registry.get(stage_id).soil_jr
                calculated = grounded[stage_id]
                document["soil_jr"] = {
                    "engine": jrsnap.ENGINE, "engine_version": calculated.engine_version,
                    "engineering_status": "not_evaluated",
                    "sdt": {"file": next(item for item in registry.get(stage_id).exports if item.kind == ground.export
                                         ).file_name, "sha256": sha256(built[(stage_id, ground.export)])},
                    "files": {kind: {"file": file_name, "sha256": sha256(calculated.files[kind])}
                              for kind, file_name in (*ground.files, *(ground.liquefaction if ground.liquefied(pier)
                                                                       else ()))},
                    "report": {"file": f"{stage_id}.pdf", "sha256": sha256(calculated.report)},
                    "runner_summary": dict(calculated.summary),
                    "messages": [dict(message) for message in calculated.messages]}
            staging.path_for(by_role[f"{stage_id}.json"].path).write_bytes(dump_json(document))
        for post in posts:
            facts = (_export_facts(registry, post, drawn, figures, grounded, built) if post.export is not None
                     else _nonlinear_facts(registry, post, staging, solved, built) if post.native.folder
                     else _project_facts(registry, post, staging, checked) if post.project is not None
                     else _check_facts(registry, post, inspected, given, analyzed) if post.check is not None
                     else _seismic_facts(registry, post, staging, checked) if post.seismic is not None
                     else _ground_facts(post, grounded, built[(post.stage, post.soil.export)])
                     if post.soil is not None
                     else _analysis_facts(registry, post, analyzed, built, selected))
            content = _sidecar(post, staging, artifacts, {**common, "selected_stages": list(selected)}, facts)
            staging.path_for(post.sidecar.path).write_bytes(content)
        candidate = Candidate(options, selected, results, artifacts, staging, input_sha256, identity, baseline, addin, stale)
        try:
            yield candidate
        finally:
            candidate._active = False


def generate(options: GenerationOptions, *, registry: Registry = STAGES) -> Candidate:
    """Calculate, render and publish one generation."""
    with prepare(options, registry=registry) as candidate:
        candidate.publish()
    return candidate
