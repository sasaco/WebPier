"""The stage registry (ADR-0004): every stage is defined here once, and nowhere else.

A ``StageSpec`` names the stage, its report stem, the stages it reads, how to calculate it from the input and
those results, how to render its report, and which external-program files it writes under post/. The
generation is generic over this table: the dependency closure, the files of a generation and the CLI choices
all come from it, so adding a stage or an export is one entry.

``calculate`` and ``render`` receive only the results of the declared dependencies (and, for ``render`` and an
export, the stage's own result), so an undeclared dependency fails instead of silently working.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
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
class StageSpec:
    id: str
    stem: str  # the report file name without suffix, e.g. "0610_線路方向荷重"
    depends_on: tuple[str, ...]
    calculate: Callable[[PierInput, Results], Any]
    render: Callable[[Results, PierInput, Path], Any]
    exports: tuple[Export, ...] = ()


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
            kinds: set[str] = set()
            for item in stage.exports:
                if not _KIND.fullmatch(item.kind):
                    raise ValueError(f"出力の種類の名前が不正です: {item.kind}")
                if item.kind in kinds:
                    raise ValueError(f"{stage.id}の出力の種類が重複しています: {item.kind}")
                if not _plain_name(item.file_name):
                    raise ValueError(f"出力ファイル名が不正です: {item.file_name}")
                if item.file_name in files:
                    raise ValueError(f"出力ファイル名が重複しています: {item.file_name}")
                kinds.add(item.kind)
                files.add(item.file_name)
            seen.append(stage.id)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(stage.id for stage in self.stages)

    @property
    def choices(self) -> tuple[str, ...]:
        return (*self.ids, ALL)

    def get(self, stage_id: str) -> StageSpec:
        return self.stages[self.ids.index(stage_id)]

    def select(self, choice: str) -> tuple[str, ...]:
        if choice == ALL:
            return self.ids
        if choice not in self.ids:
            raise InputError(f"計算段階が不正です: {choice}")
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
              lambda results, pier, path: render_longitudinal(results["0610"], results["0600"], pier, path),
              (Export("frameweb", "線路方向.json", _frameweb("0610", build_frameweb)),)),
    StageSpec("0620", "0620_直角方向荷重", ("0500", "0600"),
              lambda pier, results: calculate_transverse(pier, results["0500"], results["0600"]),
              lambda results, pier, path: render_transverse(results["0620"], results["0600"], pier, path),
              (Export("frameweb", "線路直角方向.json", _frameweb("0620", build_frameweb_transverse)),)),
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
