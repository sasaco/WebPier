"""The stage registry (ADR-0004): every stage is defined here once, and nowhere else.

A ``StageSpec`` names the stage, its report stem, the stages it reads, how to calculate it from the input and
those results, how to render its report, and which external-program files it writes under post/. The
generation is generic over this table: the dependency closure, the files of a generation and the CLI choices
all come from it, so adding a stage or an export is one entry.

``calculate`` and ``render`` receive only the results of the declared dependencies (and, for ``render`` and an
export, the stage's own result), so an undeclared dependency fails instead of silently working.

A stage with ``load_diagram`` names the export whose load cases FEMPython draws (decision 44): its ``render``
also receives those pages, to put into the report as they are. A stage with ``data_check`` names the NDU export
whose データ確認図 JRSNAP draws (decision 50), and its ``render`` receives those pages the same way.

A stage may have no report (no ``render``, and then no result JSON) and publish only files under post/. A stage with
``frame_analysis`` has FEMPython analyze the FrameWeb file of a dependency and publishes the returned pickup files
(decision 46). A stage with ``nonlinear_analysis`` has JRSNAP analyze the NDU of a dependency and publishes every
returned file as one folder under post/ (decision 47), and may write beside it the Aggre-SE project that reads those
results (decision 49). Such a stage is ``opt_in``: ``all`` leaves it out unless its
switch is given (``--frame-analysis``, ``--nonlinear-analysis``), and so is every stage that reads one, with the same
switch; chosen directly, it is calculated with its dependencies.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..calc.column_rebar import column_layout
from ..calc.embedment import applicable_embedment, calculate_embedment
from ..calc.foundation import calculate_foundation
from ..calc.longitudinal import calculate_longitudinal
from ..calc.reaction import calculate_reaction
from ..calc.seismic_longitudinal import calculate_seismic_longitudinal
from ..calc.seismic_transverse import calculate_seismic_transverse
from ..calc.transverse import calculate_transverse
from ..core.errors import InputError
from ..core.integrity import dump_json
from ..export.aggrese import BATCH_VERSION, build_project, databases, write_project
from ..export.frameweb import build_frameweb, build_frameweb_transverse
from ..export.jrsnap import LONGITUDINAL as NDU_LONGITUDINAL, TRANSVERSE as NDU_TRANSVERSE, Profile as NduProfile
from ..export.jrsnap import build_ndu, write_ndu
from ..export.jrsnap.model import NduModel
from ..export.jrsnap.profile import TARGET_VERSION
from ..inputs import PierInput
from ..reporting.stages.foundation import render_foundation
from ..reporting.stages.longitudinal import render_longitudinal
from ..reporting.stages.reaction import render_reaction
from ..reporting.stages.seismic_longitudinal import render_seismic_longitudinal
from ..reporting.stages.seismic_transverse import render_seismic_transverse
from ..reporting.stages.transverse import render_transverse
from .fempython import ANALYSIS_FILES

Results = Mapping[str, Any]
ALL = "all"
# The switches that add opt-in stages to all, by the name GenerationOptions and the editor settings use.
FRAME_ANALYSIS = "frame_analysis"  # --frame-analysis: FEMPython (decision 46)
NONLINEAR_ANALYSIS = "nonlinear_analysis"  # --nonlinear-analysis: JRSNAP (decision 47)
SWITCHES = (FRAME_ANALYSIS, NONLINEAR_ANALYSIS)
_KIND = re.compile(r"[a-z][a-z0-9]*")


def flag(switch: str) -> str:
    """The command-line flag of a switch, e.g. ``--frame-analysis``."""
    return "--" + switch.replace("_", "-")


def _plain_name(name: str) -> bool:
    return bool(name) and name not in {".", ".."} and not set(name) & set("/\\:")


@dataclass(frozen=True)
class Export:
    """A file for an external program, written under post/ with a provenance sidecar beside it.

    Every export of a selected stage is written; none is written only on request (decision 42).
    """

    kind: str  # the program, e.g. "frameweb"
    file_name: str
    build: Callable[[Results, PierInput], bytes]
    metadata: Mapping[str, Any] = field(default_factory=dict)  # fixed facts recorded in the sidecar


@dataclass(frozen=True)
class FrameAnalysis:
    """FEMPython analyzes the FrameWeb file of a dependency (decision 46, ADR-0006).

    The runner returns the pickup section forces (PIK), displacements and reactions (CSV); each is published under
    post/ as it is returned, with a provenance sidecar, by its kind ("pik", "displacement", "reaction").
    """

    stage: str  # the dependency whose export is analyzed, e.g. "0610"
    export: str  # the kind of that export, "frameweb"
    files: tuple[tuple[str, str], ...]  # (kind, file name) of each file the analysis returns


@dataclass(frozen=True)
class Project:
    """The Aggre-SE project XML that reads the JRSNAP results of the analysis (decision 49).

    ``build`` reads the results of the analyzed stage and the input before the analysis, so a blank input stops the
    generation first; it returns the writer of the XML from the DB1 path of each Case (from the XML: the folder, then
    the name JRSNAP gave the file). The XML is published under post/ beside the folder, with a provenance sidecar.
    """

    kind: str  # "aggrese"
    file_name: str  # e.g. "線路方向.xml"
    build: Callable[[Results, PierInput], Callable[[str, Sequence[str]], bytes]]
    metadata: Mapping[str, Any] = field(default_factory=dict)  # fixed facts recorded in the sidecar


@dataclass(frozen=True)
class NonlinearAnalysis:
    """JRSNAP analyzes the NDU of a dependency (decision 47, ADR-0007).

    The runner returns the analysis data (.ndt) and every file of S_ANALYSIS.exe; they are published under post/ as
    one folder, with JRSNAP's names, replaced whole, with one provenance sidecar beside it.
    """

    stage: str  # the dependency whose export is analyzed, e.g. "0710"
    export: str  # the kind of that export, "jrsnap"
    kind: str  # the kind the folder is published as
    folder: str  # the folder under post/, e.g. "線路方向_JRSNAP"
    project: Project | None = None  # the Aggre-SE project beside the folder (decision 49), or none


@dataclass(frozen=True)
class StageSpec:
    id: str
    stem: str  # the report file name without suffix, e.g. "0610_線路方向荷重"
    depends_on: tuple[str, ...]
    calculate: Callable[[PierInput, Results], Any] | None = None  # none: the stage has no result
    # (results, pier, path), and after the path the PDF of the load diagram when ``load_diagram`` is set, or of the
    # データ確認図 when ``data_check`` is; none: no report
    render: Callable[..., Any] | None = None
    exports: tuple[Export, ...] = ()
    load_diagram: str = ""  # the kind of the export FEMPython draws into the report (decision 44), or none
    data_check: str = ""  # the kind of the NDU export whose データ確認図 JRSNAP draws into the report (decision 50)
    opt_in: str = ""  # the switch without which all leaves the stage out (decisions 46, 47), or none
    frame_analysis: FrameAnalysis | None = None
    nonlinear_analysis: NonlinearAnalysis | None = None

    @property
    def has_report(self) -> bool:
        """A report (PDF) with its result JSON; a stage without one publishes only its files under post/."""
        return self.render is not None


@dataclass(frozen=True)
class Registry:
    stages: tuple[StageSpec, ...]

    def __post_init__(self) -> None:
        if not self.stages:
            raise ValueError("段階がありません")
        seen: list[str] = []
        files: set[str] = set()
        for stage in self.stages:
            if stage.id == ALL:
                raise ValueError(f"段階の名前に{ALL}は使えません")
            if stage.id in seen:
                raise ValueError(f"段階が重複しています: {stage.id}")
            for dependency in stage.depends_on:
                if dependency not in seen:
                    raise ValueError(f"{stage.id}の依存段階{dependency}が先に登録されていません")
            if not stage.stem.startswith(stage.id + "_") or not _plain_name(stage.stem):
                raise ValueError(f"{stage.id}のファイル{stage.stem}の名前は「{stage.id}_」で始まる必要があります")
            if stage.render is not None and stage.calculate is None:
                raise ValueError(f"{stage.id}の計算書には計算が必要です")
            if stage.opt_in and stage.opt_in not in SWITCHES:
                raise ValueError(f"{stage.id}の選択式のスイッチ{stage.opt_in}がありません")
            if stage.frame_analysis is not None and stage.nonlinear_analysis is not None:
                raise ValueError(f"{stage.id}は骨組解析と静的非線形解析の両方はできません")
            if (not stage.has_report and not stage.exports and stage.frame_analysis is None
                    and stage.nonlinear_analysis is None):
                raise ValueError(f"{stage.id}には成果物がありません")
            outputs = [(item.kind, item.file_name) for item in stage.exports]
            analysis = stage.frame_analysis
            if analysis is not None:
                self._check_source(stage, analysis.stage, analysis.export, "骨組解析")
                if sorted(kind for kind, _ in analysis.files) != sorted(ANALYSIS_FILES):
                    raise ValueError(f"{stage.id}の骨組解析の出力は {'・'.join(ANALYSIS_FILES)} です")
                if stage.opt_in != FRAME_ANALYSIS:
                    raise ValueError(f"{stage.id}は骨組解析するので選択式（{FRAME_ANALYSIS}）の段階です")
                outputs += analysis.files
            nonlinear = stage.nonlinear_analysis
            if nonlinear is not None:
                self._check_source(stage, nonlinear.stage, nonlinear.export, "静的非線形解析")
                if stage.opt_in != NONLINEAR_ANALYSIS:
                    raise ValueError(f"{stage.id}は静的非線形解析するので選択式（{NONLINEAR_ANALYSIS}）の段階です")
                outputs.append((nonlinear.kind, nonlinear.folder))
                if nonlinear.project is not None:
                    outputs.append((nonlinear.project.kind, nonlinear.project.file_name))
            for dependency in stage.depends_on:
                if self.get(dependency).opt_in not in ("", stage.opt_in):
                    raise ValueError(f"{stage.id}は選択式の段階{dependency}に依存するので、同じスイッチ"
                                     f"（{self.get(dependency).opt_in}）の選択式の段階です")
            kinds: set[str] = set()
            for kind, file_name in outputs:
                if not _KIND.fullmatch(kind):
                    raise ValueError(f"出力の種類の名前が不正です: {kind}")
                if kind in kinds:
                    raise ValueError(f"{stage.id}の出力の種類が重複しています: {kind}")
                if not _plain_name(file_name):
                    raise ValueError(f"出力ファイル名が不正です: {file_name}")
                if file_name in files:
                    raise ValueError(f"出力ファイル名が重複しています: {file_name}")
                kinds.add(kind)
                files.add(file_name)
            if stage.load_diagram and stage.load_diagram not in {item.kind for item in stage.exports}:
                raise ValueError(f"{stage.id}の荷重図の出力{stage.load_diagram}がありません")
            if stage.load_diagram and not stage.has_report:
                raise ValueError(f"{stage.id}の荷重図を差し込む計算書がありません")
            if stage.data_check and stage.data_check not in {item.kind for item in stage.exports}:
                raise ValueError(f"{stage.id}のデータ確認図の出力{stage.data_check}がありません")
            if stage.data_check and not stage.has_report:
                raise ValueError(f"{stage.id}のデータ確認図を差し込む計算書がありません")
            if stage.data_check and stage.load_diagram:
                raise ValueError(f"{stage.id}に荷重図とデータ確認図の両方は差し込めません")
            seen.append(stage.id)

    def _check_source(self, stage: StageSpec, source: str, export: str, what: str) -> None:
        if source not in stage.depends_on:
            raise ValueError(f"{stage.id}が{what}する{source}が依存段階にありません")
        if export not in {item.kind for item in self.get(source).exports}:
            raise ValueError(f"{stage.id}が{what}する{source}の出力{export} がありません")

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(stage.id for stage in self.stages)

    @property
    def choices(self) -> tuple[str, ...]:
        return (*self.ids, ALL)

    def get(self, stage_id: str) -> StageSpec:
        return self.stages[self.ids.index(stage_id)]

    def opt_in(self, switch: str) -> tuple[str, ...]:
        """The stages ``all`` leaves out unless *switch* is given (decisions 46, 47)."""
        return tuple(stage.id for stage in self.stages if stage.opt_in == switch)

    def select(self, choice: str, *, switches: frozenset[str] = frozenset()) -> tuple[str, ...]:
        """*choice* alone, or for ``all`` every stage, an opt-in one only when its switch is in *switches*."""
        if unknown := switches - set(SWITCHES):
            raise InputError(f"選択式のスイッチが不正です: {'・'.join(sorted(unknown))}")
        if choice == ALL:
            return tuple(stage.id for stage in self.stages if not stage.opt_in or stage.opt_in in switches)
        if choice not in self.ids:
            raise InputError(f"計算段階が不正です: {choice}")
        if switches:
            given = [switch for switch in SWITCHES if switch in switches]
            stages = "・".join(stage for switch in given for stage in self.opt_in(switch))
            raise InputError(f"{' '.join(map(flag, given))} は --stage {ALL} と使います（選択式の段階 {stages} は "
                             f"--stage で直接選べます）")
        return (choice,)

    def closure(self, selected: Sequence[str]) -> tuple[str, ...]:
        """The selected stages and everything they read, in registry (dependency) order."""
        needed = set(selected)
        for stage in reversed(self.stages):
            if stage.id in needed:
                needed.update(stage.depends_on)
        return tuple(stage_id for stage_id in self.ids if stage_id in needed)


def _frameweb(stage_id: str, build: Callable[[Any], dict[str, Any]]) -> Callable[[Results, PierInput], bytes]:
    return lambda results, pier: dump_json(build(results[stage_id]))


def _ndu_model(stage_id: str, profile: NduProfile, results: Results, pier: PierInput) -> NduModel:
    foundation = results["0500"]
    return build_ndu(profile, pier, foundation, calculate_embedment(pier, foundation), column_layout(pier),
                     results[stage_id])


def _jrsnap(stage_id: str, profile: NduProfile) -> Callable[[Results, PierInput], bytes]:
    return lambda results, pier: write_ndu(_ndu_model(stage_id, profile, results, pier))


def _aggrese(stage_id: str, profile: NduProfile) -> Callable[[Results, PierInput],
                                                              Callable[[str, Sequence[str]], bytes]]:
    """The project of the NDU of *stage_id*, checked before the analysis; then its writer (decision 49)."""
    def build(results: Results, pier: PierInput) -> Callable[[str, Sequence[str]], bytes]:
        project = build_project(_ndu_model(stage_id, profile, results, pier), pier)
        return lambda folder, names: write_project(project, databases(folder, names, project.cases))
    return build


def _pickups(stem: str) -> tuple[tuple[str, str], ...]:
    """The files of a frame analysis of ``<stem>.json`` (decision 46)."""
    return (("pik", f"{stem}.pik"), ("displacement", f"{stem}_ピックアップ変位量.csv"),
            ("reaction", f"{stem}_ピックアップ反力.csv"))


# A normal generation only writes the NDU; reading it in JRSNAP and running an analysis are separate records.
_NDU = {"target_version": TARGET_VERSION, "app_read_verified": False, "analysis_run": False}
# A normal generation only writes the project; Aggre-SE reading it and checking with it are separate records.
_PROJECT = {"target": "Aggre-SE", "target_version": BATCH_VERSION, "app_read_verified": False,
            "seismic_check_run": False}

STAGES = Registry((
    StageSpec("0500", "0500_直接基礎", (),
              lambda pier, results: calculate_foundation(pier),
              lambda results, pier, path: render_foundation(
                  results["0500"], pier, applicable_embedment(pier, results["0500"]), path)),
    StageSpec("0600", "0600_上部工反力", (),
              lambda pier, results: calculate_reaction(pier),
              lambda results, pier, path: render_reaction(results["0600"], pier, path)),
    StageSpec("0610", "0610_線路方向荷重", ("0500", "0600"),
              lambda pier, results: calculate_longitudinal(pier, results["0500"], results["0600"]),
              lambda results, pier, path, pages: render_longitudinal(results["0610"], results["0600"], pier, path,
                                                                     pages),
              (Export("frameweb", "線路方向.json", _frameweb("0610", build_frameweb)),), load_diagram="frameweb"),
    StageSpec("0611", "0611_線路方向照査", ("0610",), opt_in=FRAME_ANALYSIS,
              frame_analysis=FrameAnalysis("0610", "frameweb", _pickups("線路方向"))),
    StageSpec("0620", "0620_直角方向荷重", ("0500", "0600"),
              lambda pier, results: calculate_transverse(pier, results["0500"], results["0600"]),
              lambda results, pier, path, pages: render_transverse(results["0620"], results["0600"], pier, path,
                                                                   pages),
              (Export("frameweb", "線路直角方向.json", _frameweb("0620", build_frameweb_transverse)),),
              load_diagram="frameweb"),
    StageSpec("0621", "0621_直角方向照査", ("0620",), opt_in=FRAME_ANALYSIS,
              frame_analysis=FrameAnalysis("0620", "frameweb", _pickups("線路直角方向"))),
    StageSpec("0710", "0710_線路方向荷重", ("0500", "0600", "0610"),
              lambda pier, results: calculate_seismic_longitudinal(pier, results["0500"], results["0600"],
                                                                   results["0610"]),
              lambda results, pier, path, pages: render_seismic_longitudinal(results["0710"], pier, path, pages),
              (Export("jrsnap", "線路方向.ndu", _jrsnap("0710", NDU_LONGITUDINAL), metadata=_NDU),),
              data_check="jrsnap"),
    StageSpec("0711", "0711_線路方向非線形解析", ("0710",), opt_in=NONLINEAR_ANALYSIS,
              nonlinear_analysis=NonlinearAnalysis(
                  "0710", "jrsnap", "jrsnap", "線路方向_JRSNAP",
                  Project("aggrese", "線路方向.xml", _aggrese("0710", NDU_LONGITUDINAL), _PROJECT))),
    StageSpec("0720", "0720_線路直角方向荷重", ("0500", "0600", "0620"),
              lambda pier, results: calculate_seismic_transverse(pier, results["0500"], results["0600"],
                                                                 results["0620"]),
              lambda results, pier, path, pages: render_seismic_transverse(results["0720"], pier, path, pages),
              (Export("jrsnap", "線路直角方向.ndu", _jrsnap("0720", NDU_TRANSVERSE), metadata=_NDU),),
              data_check="jrsnap"),
    # Its NDU has two combinations, so the runner analyzes both in one run of S_ANALYSIS.exe (decision 47).
    StageSpec("0721", "0721_線路直角方向非線形解析", ("0720",), opt_in=NONLINEAR_ANALYSIS,
              nonlinear_analysis=NonlinearAnalysis(
                  "0720", "jrsnap", "jrsnap", "線路直角方向_JRSNAP",
                  Project("aggrese", "線路直角方向.xml", _aggrese("0720", NDU_TRANSVERSE), _PROJECT))),
))
