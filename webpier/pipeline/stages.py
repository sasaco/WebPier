"""The stage registry (ADR-0004): every stage is defined here once, and nowhere else.

A ``StageSpec`` names the stage, its report stem, the stages it reads, how to calculate it from the input and
those results, how to render its report, and which external-program files it writes under post/. The
generation is generic over this table: the dependency closure, the files of a generation and the CLI choices
all come from it, so adding a stage or an export is one entry.

``calculate`` and ``render`` receive only the results of the declared dependencies (and, for ``render`` and an
export, the stage's own result), so an undeclared dependency fails instead of silently working.

A stage with ``load_diagram`` names the export whose load cases FEMPython draws (decision 44): its ``render``
also receives those pages, to put into the report as they are.

A stage may have no report (no ``render``, and then no result JSON) and publish only files under post/. A stage with
``frame_analysis`` has FEMPython analyze the FrameWeb file of a dependency and publishes the returned pickup files
(decision 46). Such a stage is ``opt_in``: ``all`` leaves it out unless it is asked for (``--frame-analysis``), and
so is every stage that reads one; chosen directly, it is calculated with its dependencies.
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
from ..export.frameweb import build_frameweb, build_frameweb_transverse
from ..export.jrsnap import LONGITUDINAL as NDU_LONGITUDINAL, TRANSVERSE as NDU_TRANSVERSE, Profile as NduProfile
from ..export.jrsnap import build_ndu, write_ndu
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
_KIND = re.compile(r"[a-z][a-z0-9]*")


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
class StageSpec:
    id: str
    stem: str  # the report file name without suffix, e.g. "0610_線路方向荷重"
    depends_on: tuple[str, ...]
    calculate: Callable[[PierInput, Results], Any] | None = None  # none: the stage has no result
    # (results, pier, path), and the load diagram PDF after the path when ``load_diagram`` is set; none: no report
    render: Callable[..., Any] | None = None
    exports: tuple[Export, ...] = ()
    load_diagram: str = ""  # the kind of the export FEMPython draws into the report (decision 44), or none
    opt_in: bool = False  # left out of all unless asked for (decision 46)
    frame_analysis: FrameAnalysis | None = None

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
            if not stage.has_report and not stage.exports and stage.frame_analysis is None:
                raise ValueError(f"{stage.id}には成果物がありません")
            outputs = [(item.kind, item.file_name) for item in stage.exports]
            analysis = stage.frame_analysis
            if analysis is not None:
                if analysis.stage not in stage.depends_on:
                    raise ValueError(f"{stage.id}が骨組解析する{analysis.stage}が依存段階にありません")
                if analysis.export not in {item.kind for item in self.get(analysis.stage).exports}:
                    raise ValueError(f"{stage.id}が骨組解析する{analysis.stage}の出力{analysis.export} がありません")
                if sorted(kind for kind, _ in analysis.files) != sorted(ANALYSIS_FILES):
                    raise ValueError(f"{stage.id}の骨組解析の出力は {'・'.join(ANALYSIS_FILES)} です")
                if not stage.opt_in:
                    raise ValueError(f"{stage.id}は骨組解析するので選択式（opt_in）の段階です")
                outputs += analysis.files
            for dependency in stage.depends_on:
                if self.get(dependency).opt_in and not stage.opt_in:
                    raise ValueError(f"{stage.id}は選択式の段階{dependency}に依存するので選択式（opt_in）の段階です")
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
            seen.append(stage.id)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(stage.id for stage in self.stages)

    @property
    def choices(self) -> tuple[str, ...]:
        return (*self.ids, ALL)

    def get(self, stage_id: str) -> StageSpec:
        return self.stages[self.ids.index(stage_id)]

    @property
    def opt_in(self) -> tuple[str, ...]:
        """The stages ``all`` leaves out unless they are asked for (decision 46)."""
        return tuple(stage.id for stage in self.stages if stage.opt_in)

    def select(self, choice: str, *, opt_in: bool = False) -> tuple[str, ...]:
        """*choice* alone, or for ``all`` every stage, the opt-in ones only with *opt_in* (``--frame-analysis``)."""
        if choice == ALL:
            return tuple(stage.id for stage in self.stages if opt_in or not stage.opt_in)
        if choice not in self.ids:
            raise InputError(f"計算段階が不正です: {choice}")
        if opt_in:
            raise InputError(f"--frame-analysis は --stage {ALL} と使います（選択式の段階 {'・'.join(self.opt_in)} は "
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


def _jrsnap(stage_id: str, profile: NduProfile) -> Callable[[Results, PierInput], bytes]:
    def build(results: Results, pier: PierInput) -> bytes:
        foundation = results["0500"]
        return write_ndu(build_ndu(profile, pier, foundation, calculate_embedment(pier, foundation),
                                   column_layout(pier), results[stage_id]))
    return build


def _pickups(stem: str) -> tuple[tuple[str, str], ...]:
    """The files of a frame analysis of ``<stem>.json`` (decision 46)."""
    return (("pik", f"{stem}.pik"), ("displacement", f"{stem}_ピックアップ変位量.csv"),
            ("reaction", f"{stem}_ピックアップ反力.csv"))


# A normal generation only writes the NDU; reading it in JRSNAP and running an analysis are separate records.
_NDU = {"target_version": TARGET_VERSION, "app_read_verified": False, "analysis_run": False}

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
    StageSpec("0611", "0611_線路方向照査", ("0610",), opt_in=True,
              frame_analysis=FrameAnalysis("0610", "frameweb", _pickups("線路方向"))),
    StageSpec("0620", "0620_直角方向荷重", ("0500", "0600"),
              lambda pier, results: calculate_transverse(pier, results["0500"], results["0600"]),
              lambda results, pier, path, pages: render_transverse(results["0620"], results["0600"], pier, path,
                                                                   pages),
              (Export("frameweb", "線路直角方向.json", _frameweb("0620", build_frameweb_transverse)),),
              load_diagram="frameweb"),
    StageSpec("0621", "0621_直角方向照査", ("0620",), opt_in=True,
              frame_analysis=FrameAnalysis("0620", "frameweb", _pickups("線路直角方向"))),
    StageSpec("0710", "0710_線路方向荷重", ("0500", "0600", "0610"),
              lambda pier, results: calculate_seismic_longitudinal(pier, results["0500"], results["0600"],
                                                                   results["0610"]),
              lambda results, pier, path: render_seismic_longitudinal(results["0710"], pier, path),
              (Export("jrsnap", "線路方向.ndu", _jrsnap("0710", NDU_LONGITUDINAL), metadata=_NDU),)),
    StageSpec("0720", "0720_線路直角方向荷重", ("0500", "0600", "0620"),
              lambda pier, results: calculate_seismic_transverse(pier, results["0500"], results["0600"],
                                                                 results["0620"]),
              lambda results, pier, path: render_seismic_transverse(results["0720"], pier, path),
              (Export("jrsnap", "線路直角方向.ndu", _jrsnap("0720", NDU_TRANSVERSE), metadata=_NDU),)),
))
