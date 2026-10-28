"""The stage registry (ADR-0004): every stage is defined here once, and nowhere else.

A ``StageSpec`` names the stage, its report stem, the stages it reads, how to calculate it from the input and
those results, how to render its report, and which external-program files it writes under post/. The
generation is generic over this table: the dependency closure, the files of a generation and the CLI choices
all come from it, so adding a stage or an export is one entry.

``calculate`` and ``render`` receive only the results of the declared dependencies (and, for ``render`` and an
export, the stage's own result), so an undeclared dependency fails instead of silently working.

Every ``render`` receives, after the path, the pages of other programs to put into the report as they are, by the
name the report takes them (reporting.stages.insertion); a stage without any receives an empty mapping. A stage with
``load_diagram`` names the export whose load cases FEMPython draws (decision 44): its ``render`` receives those pages
as ``load_diagram``. A stage with ``jrsnap_figures`` names the NDU export from which JRSNAP draws the データ確認図 and
the 荷重図 (decisions 50, 51): its ``render`` receives them as ``data_check`` and ``load_diagram``.

A stage may have no report (no ``render``, and then no result JSON) and publish only files under post/. A stage with
``frame_analysis`` has FEMPython analyze the FrameWeb file of a dependency and publishes the returned pickup files
(decision 46). A stage with ``nonlinear_analysis`` has JRSNAP analyze the NDU of a dependency and publishes every
returned file as one folder under post/ (decision 47), and may write beside it the Aggre-SE project that reads those
results (decision 49). A stage with ``seismic_check`` (0711, 0721) also has Aggre-SE check with that project and
those results: its report is Aggre-SE's report as it is, which its ``render`` receives, and it needs no calculation
(decision 56, ADR-0009); Aggre-SE's section force pickup and summary workbook are published under post/ as they
are (decisions 57, 58). A stage with ``section_check`` (0611, 0621) also has Capacita check the column bottom with
the PIK of its own frame analysis (decision 48, ADR-0008): its ``render`` receives Capacita's pages of each section
by the section's id (none for a section Capacita skipped), and the completed WDJ is published under post/. A stage
with ``section_check`` but no frame analysis (0910) builds its WDJ with its section forces and Capacita calculates it
as given (``run-rc`` without ``--pickup``, decision 59); the WDJ WebPier wrote is what is published. A stage with
``complete`` finishes its result after the runners of its dependencies: with the files of its own frame analysis
(0612, 0622: the 基礎の照査 reads the support reactions, decision 54), or with the files of the seismic checks of its
dependencies (0900: the 最大応答震度 of Aggre-SE's summary workbook, decision 59, named ``seismic_file(stage, kind)``),
or with the completed results of its dependencies alone (0910); ``calculate`` gives what the input alone decides,
before any runner, and may be absent when everything waits for ``complete``. Stages that analyze the same FrameWeb
file declare the same files and share one analysis: a generation runs it once and publishes its files once (decision
54).

A stage with ``soil_jr`` (0500 for a pile foundation, decision 85, ADR-0013) has SOIL-JR calculate the .sdt of its
export with the JRSNAP runner: its report is SOIL-JR's as the runner printed it, its .sdr and .sdc (and the two for the
liquefaction, when a layer along the pile liquefies) are published under post/ as returned, and ``complete`` finishes its
result with them. A stage with ``after`` (0610 and 0620 of a pile foundation, decision 88) calculates and builds its exports only once
the stages it names have their runner's files and are complete: its frame stands on the springs SOIL-JR returned. Such a
stage is checked only by a generation (``validate`` has no runner's result); so are the stages that read it, which are
waited for too (``Registry.waits``: the frame analyses 0611 and 0612 of a pile foundation, decision 89). The items a pile
foundation can choose are inputs.outputs.PILE_OUTPUT_KEYS.

A stage with ``foundations`` is the one of the direct foundation; the stages of the other 基礎形式 are its
values, and ``Registry.for_foundation`` makes the registry of a 基礎形式 once the input is read.

Which stages a generation makes is decided by the input's 出力項目 alone (decision 72, ADR-0011): ``OUTPUT_STAGES``
gives the stages of each item, and the registry checks that a stage reads only the stages of its own item and of the
items that item uses (inputs.outputs), so the stages of the chosen items are all a generation calculates.

With a load model's add-in (decision 70) the registry is ``stages_for(source)``: 0600 has the dead loads only, 0610 /
0620 / 0710 / 0720 / 0900 are calculated from the load model's result (calc.generic) and 0711 / 0721 write the Aggre-SE
project of their NDU; every other stage is the same StageSpec, reading the generic results as it reads the train
path's. Its ``load_model`` tells the generation to read the input without the load model's items and to record the
add-in in every artifact.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Protocol

from ..calc.cantilever import calculate_cantilever, complete_cantilever, read_max_response
from ..calc.cantilever.check import calculate_cantilever_section
from ..calc.column_check import LONGITUDINAL as COLUMN_LONGITUDINAL, TRANSVERSE as COLUMN_TRANSVERSE
from ..calc.column_check import Direction, calculate_column_check
from ..calc.column_rebar import column_layout
from ..calc.detailing import calculate_detailing
from ..calc.detailing.pile import PileSeismicResult, minimum_bars, pile_head_reaction
from ..calc.embedment import applicable_embedment, calculate_embedment
from ..calc.footing import calculate_footing, complete_footing
from ..calc.footing_check import calculate_footing_check
from ..calc.pile_footing import SEISMIC_PICKUP, calculate_footing as calculate_pile_footing, complete_footing as complete_pile_footing
from ..calc.pile_footing_check import calculate_pile_footing_check
from ..calc.foundation import calculate_foundation
from ..calc.foundation_check import LONGITUDINAL as FOUNDATION_LONGITUDINAL, TRANSVERSE as FOUNDATION_TRANSVERSE
from ..calc.foundation_check import Direction as FoundationDirection, check as check_foundation
from ..calc.foundation_check import prepare as prepare_foundation_check
from ..calc.frame import Direction as FrameDirection, Region
from ..calc.ground_displacement import considered as displaces, region_coefficient, surface_layers
from ..calc.response_displacement import ResponseDisplacementResult
from ..calc.generic.cantilever import calculate_generic_cantilever, complete_generic_cantilever
from ..calc.generic.frame import calculate_generic_frame
from ..calc.generic.seismic import calculate_generic_seismic
from ..calc.longitudinal import calculate_longitudinal
from ..calc.pile_body import assemble as assemble_pile_body, factored, select as select_pile_forces, steel as pile_steel
from ..calc.pile_cast import REPORT_SECTIONS as PILE_CAST_SECTIONS, assemble as assemble_pile_cast
from ..calc.pile_cast import pile_factor, section as pile_cast_section, select as select_pile_cast
from ..calc.pile_check import check as check_pile, prepare as prepare_pile_check, with_body, with_cast, with_joint
from ..calc.pile_joint import assemble as assemble_pile_joint, section as pile_joint_section, select as select_pile_joint
from ..calc.pile_frame import PileFoundation
from ..calc.pile_ground import calculate_pile_ground
from ..calc.reaction import calculate_dead_reaction, calculate_reaction
from ..calc.seismic_longitudinal import calculate_seismic_longitudinal
from ..calc.seismic_transverse import calculate_seismic_transverse
from ..calc.transverse import calculate_transverse
from ..core.errors import InputError
from ..core.integrity import dump_json, sha256
from ..export.aggrese import BATCH_VERSION, build_pile_project, build_project, databases, ndu_databases, write_project
from ..export.capacita import (build_cantilever_wdj, build_footing_wdj, build_wdj, point_index, write_footing_wdj,
                               write_wdj)
from ..export.capacita.pile_footing_wdj import build_pile_footing_wdj, write_pile_footing_wdj
from ..export.drawing import drawing_dxf, drawing_figures
from ..export.frameweb import build_frameweb, build_frameweb_generic, build_frameweb_transverse
from ..export.jrsnap import LONGITUDINAL as NDU_LONGITUDINAL, TRANSVERSE as NDU_TRANSVERSE, Profile as NduProfile
from ..export.jrsnap import build_ndu, build_pile_ndu, diagram_combinations, write_ndu, write_pile_ndu
from ..export.jrsnap.build_pile import (RESPONSE_PATTERN, element_numbers, pile_node_depths, response_ndu,
                                       response_pattern)
from ..export.jrsnap.model import NduModel
from ..export.jrsnap.pile_model import PileNduModel
from ..export.jrsnap.profile import TARGET_VERSION, generic_profile
from ..export.capacita.pile_joint import row_id, write as write_pile_joint
from ..export.capacita.pile_wdj import build_pile_wdj, write_pile_wdj
from ..export.soiljr.sdc_seismic import parse_seismic
from ..export.steeldan import write_wsj
from ..inputs import PierInput, choices
from ..inputs.outputs import OUTPUT_KEYS, FootingParts, footing_parts, uses
from ..reporting.stages import cantilever as cantilever_report
from ..reporting.stages import cantilever_check as cantilever_check_report
from ..reporting.stages import detailing as detailing_report
from ..reporting.stages import footing as footing_report
from ..reporting.stages import footing_check as footing_check_report
from ..reporting.stages import pile_footing as pile_footing_report
from ..reporting.stages import foundation as foundation_report
from ..reporting.stages import foundation_check as foundation_check_report
from ..reporting.stages import longitudinal as longitudinal_report
from ..reporting.stages import pile_check as pile_check_report
from ..reporting.stages import reaction as reaction_report
from ..reporting.stages import seismic_longitudinal as seismic_longitudinal_report
from ..reporting.stages import seismic_transverse as seismic_transverse_report
from ..reporting.stages import transverse as transverse_report
from ..reporting.stages.cantilever import render_cantilever
from ..reporting.stages.cantilever_check import render_cantilever_check
from ..reporting.stages.column_check import LONGITUDINAL as CHAPTER_8, TRANSVERSE as CHAPTER_9
from ..reporting.stages.column_check import Chapter, following_section, render_column_check
from ..reporting.stages.detailing import render_detailing
from ..reporting.stages.footing import render_footing
from ..reporting.stages.footing_check import Chapter as FootingChapter, render_footing_check
from ..reporting.stages.footing_check import chapters as footing_chapters
from ..reporting.stages.foundation import render_foundation
from ..reporting.stages.foundation_check import LONGITUDINAL as FOUNDATION_CHAPTER_8
from ..reporting.stages.foundation_check import TRANSVERSE as FOUNDATION_CHAPTER_9
from ..reporting.stages.foundation_check import Chapter as FoundationChapter, render_foundation_check
from ..reporting.stages.generic import cantilever as generic_cantilever_report
from ..reporting.stages.generic import frame as generic_frame_report
from ..reporting.stages.generic import reaction as generic_reaction_report
from ..reporting.stages.generic import seismic as generic_seismic_report
from ..reporting.stages.generic.cantilever import render_generic_cantilever
from ..reporting.stages.generic.frame import render_generic_frame
from ..reporting.stages.generic.reaction import render_dead_reaction
from ..reporting.stages.generic.seismic import render_generic_seismic
from ..reporting.stages.longitudinal import render_longitudinal
from ..reporting.stages.pile_check import render_pile_check
from ..reporting.stages.reaction import render_reaction
from ..reporting.stages.seismic_check import render_pile_seismic_check, render_seismic_check
from ..reporting.stages.seismic_longitudinal import render_seismic_longitudinal
from ..reporting.stages.seismic_transverse import render_seismic_transverse
from ..reporting.stages.transverse import render_transverse
from . import capacita, soiljr
from .pile_check import limits as pile_limits
from .pilejoint import check_joint as run_pile_joint
from .steeldan import check_pile as run_pile_body
from .aggrese import AXIAL, PILE_PUBLISHED as AGGRESE_PILE_FILES, PUBLISHED as AGGRESE_FILES, TRANSVERSE, foundation_steps
from .fempython import ANALYSIS_FILES, footing_displacements, head_forces, member_forces, support_reactions

Results = Mapping[str, Any]
# The stages of each 出力項目 (decision 72): the frame analysis (decisions 46, 54), the static nonlinear analysis
# (decision 47), the footing (decision 60) and the cantilever (decision 59) are items of their own.
OUTPUT_STAGES: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "detailing": ("0400",),
    "ground_model": ("0500",), "reactions": ("0600",),
    "longitudinal": ("0610",), "longitudinal_frame_analysis": ("0611", "0612"),
    "transverse": ("0620",), "transverse_frame_analysis": ("0621", "0622"),
    "longitudinal_seismic": ("0710",), "longitudinal_nonlinear_analysis": ("0711",),
    "transverse_seismic": ("0720",), "transverse_nonlinear_analysis": ("0721",),
    "footing": ("0800", "0810", "0820"), "cantilever": ("0900", "0910"),
})
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
    # written only for an input some layer of whose ground liquefies (``soiljr.liquefied``, decision 95), like SOIL-JR's files
    # for the liquefaction
    liquefied: bool = False


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
class SectionCheck:
    """Capacita checks a section the stage describes (decisions 48, 59; ADR-0008).

    With the stage's own frame analysis (0611, 0621) ``build`` writes the WDJ without pickup data from the stage's
    results and the PIK (only the place of the check point among its points is read: export.capacita.point_index),
    and the runner imports the PIK; the completed WDJ it returns is published. Without one (0910) ``build`` receives
    no PIK and writes the section forces into the WDJ, which the runner calculates as given and which is published as
    written. ``sections`` names the sections of Capacita's report the stage asks for (Capacita's ids, in order). The
    stage's ``render`` receives the pages of each section and the sections Capacita skipped for zero forces. The WDJ
    goes under post/ as ``kind`` with a provenance sidecar. With ``commentary`` (chapter, first section) Capacita
    numbers the commentary of a WDJ that asks for it from "chapter.first", and ``finish`` gives the stage's result the
    number each returned section carries (0611, 0621: decision 121).
    """

    kind: str  # "wdj"
    file_name: str  # e.g. "線路方向.wdj"
    build: Callable[[Results, PierInput, bytes | None], bytes]  # (results, pier, PIK or None)
    sections: Callable[[Results], Sequence[str]]
    commentary: tuple[int, int] | None = None  # run-rc --commentary-chapter, --commentary-first-section
    # (the stage's result, the heading number of each returned section by its id) → the stage's result
    finish: Callable[[Any, Mapping[str, str | None]], Any] | None = None


def seismic_file(stage_id: str, kind: str) -> str:
    """How ``complete`` receives a file of a dependency's seismic check or frame analysis: by the stage and the kind
    (decisions 59, 60)."""
    return f"{stage_id}/{kind}"


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
class ResponseAnalysis:
    """The 応答変位法 of the stage's piles (decision 97), for an input that considers the 地盤変位: once Aggre-SE has checked the
    inertia Cases, ``case`` is the Case (from 1) whose Teq and Kh it takes; ``ndus`` the NDU of each of its Cases (file name,
    bytes), which JRSNAP analyzes into the same folder and which are published in it; ``project`` the writer of the project of
    every Case, with which Aggre-SE checks again."""

    case: Callable[[Results, PierInput], int]
    ndus: Callable[[Results, PierInput, ResponseDisplacementResult], tuple[tuple[str, bytes], ...]]
    project: Callable[[Results, PierInput, ResponseDisplacementResult], Callable[[str, Sequence[str]], bytes]]


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
    # the kinds of the stage's other NDUs, analyzed one by one into the same folder (the NDU of the reversed push of a pile
    # foundation, decisions 93 and 94)
    also: tuple[str, ...] = ()
    response: ResponseAnalysis | None = None  # the 応答変位法 of a pile foundation on G3〜G5 (decision 97)


@dataclass(frozen=True)
class SeismicCheck:
    """Aggre-SE checks with the project of the stage's nonlinear analysis (decisions 56〜58, 60, ADR-0009).

    Its report is the stage's report as it is; each of its other files (pipeline.aggrese.PUBLISHED: the section force
    pickup "pik", the summary workbook "xlsx", the step table of the direct foundation "steps") is
    published under post/ as it is, by its kind, with a provenance sidecar naming the project and the folder (and,
    for the pickup, the meaning of each pickup; for the step table, its columns).
    """

    files: tuple[tuple[str, str], ...]  # (kind, file name) of each file, e.g. ("pik", "線路方向_Aggre-SE.pik")
    # a pile foundation (decision 94): the direction of the .sdr of 0500 the runner takes the limit values of the stability
    # from (aggrese.AXIAL or TRANSVERSE); the files then have no step table of the direct foundation
    direction: str | None = None


@dataclass(frozen=True)
class SoilJrCalculation:
    """SOIL-JR calculates the .sdt of an export of the stage (decision 85, ADR-0013).

    The runner returns the 基礎照査連携用データ and the 解析連携データ, and the same two for the liquefaction only for an
    input that considers it (``liquefied``, decided from the input before any runner), and prints the report, which is
    the stage's report as it is. Each file is published under post/ as returned, by its kind, with a provenance sidecar.
    """

    export: str  # the kind of the export whose bytes (a .sdt) SOIL-JR calculates, "sdt"
    files: tuple[tuple[str, str], ...]  # (kind, file name) of the files it always returns, e.g. ("sdr", "杭基礎.sdr")
    liquefaction: tuple[tuple[str, str], ...]  # the files it returns besides when ``liquefied``
    liquefied: Callable[[PierInput], bool]


@dataclass(frozen=True)
class GroundDisplacementRun:
    """SoilStructure calculates the 地盤変位 at the depths of the stage's pile nodes (decision 97): 0710 and 0720 of a pile
    foundation on G3〜G5 (``calc.ground_displacement.considered``). The answer is added to the stage's result once it is
    calculated (after 0500), before its files are built; the stage's report prints it and 0711 / 0721 put it into the NDUs of
    the 応答変位法."""

    depths: Callable[[Results, PierInput], tuple[Decimal, ...]]  # m below the ground surface


@dataclass(frozen=True)
class AlsoFigures:
    """The 荷重図 of the basic cases another NDU of the stage draws: the NDU of the reversed push of a pile foundation."""

    export: str
    load_cases: Callable[[Results, PierInput], tuple[tuple[int, int], ...]]


@dataclass(frozen=True)
class JrsnapFigures:
    """JRSNAP draws the データ確認図 and the 荷重図 of the stage's NDU into its report (decisions 50, 51)."""

    export: str  # the kind of the NDU export, "jrsnap"
    load_cases: Callable[[Results, PierInput], tuple[tuple[int, int], ...]]  # (basic case, combination) to draw
    also: tuple[AlsoFigures, ...] = ()  # the cases the first NDU does not have, from other NDUs of the stage (decision 93)


@dataclass(frozen=True)
class StageSpec:
    id: str
    stem: str  # the report file name without suffix, e.g. "0610_線路方向荷重"
    depends_on: tuple[str, ...]
    calculate: Callable[[PierInput, Results], Any] | None = None  # none: the stage has no result
    # (results, pier, path, pages): pages maps the name of each insertion (reporting.stages.insertion) to its PDF,
    # FEMPython's load diagram when ``load_diagram`` is set, JRSNAP's データ確認図 and 荷重図 when ``jrsnap_figures``
    # is, Capacita's pages of each section when ``section_check`` is, or Aggre-SE's report when ``seismic_check`` is;
    # empty for a stage with none. None: no report
    render: Callable[[Results, PierInput, Any, Mapping[str, bytes]], Any] | None = None
    exports: tuple[Export, ...] = ()
    load_diagram: str = ""  # the kind of the export FEMPython draws into the report (decision 44), or none
    jrsnap_figures: JrsnapFigures | None = None  # JRSNAP draws figures of the NDU into the report (decisions 50, 51)
    frame_analysis: FrameAnalysis | None = None
    nonlinear_analysis: NonlinearAnalysis | None = None
    section_check: SectionCheck | None = None  # Capacita checks the column with the PIK of frame_analysis (decision 48)
    # Aggre-SE checks with the project of nonlinear_analysis; its report is the stage's report (decisions 56, 57)
    seismic_check: SeismicCheck | None = None
    # (the result of calculate or None, the files it reads, the input, the results so far) → the stage's result
    # (decisions 54, 59), or none. The files are those of the stage's frame analysis by kind, and those of the seismic
    # checks of its dependencies by seismic_file(stage, kind).
    # SOIL-JR calculates the .sdt of an export; its report is the stage's report (decision 85)
    soil_jr: SoilJrCalculation | None = None
    complete: Callable[[Any, Mapping[str, bytes], PierInput, Results], Any] | None = None
    # (results, pier, pages) → the documents of the report WebPier lays out, in order, without the pages of other
    # programs: its grid Excel workbook (export/). None: a report with none of WebPier's pages (0711, 0721)
    grid_documents: Callable[[Results, PierInput, Mapping[str, bytes]], Sequence[Any]] | None = None
    # the stage of each pile foundation (a 基礎形式 of choices.PILE_FOUNDATIONS) in place of this one, which is the direct
    # foundation's: the same id, and its own stem, files and runners (decision 85)
    foundations: Mapping[str, StageSpec] = field(default_factory=dict)
    # the stages (with ``soil_jr``) that must be complete before this stage is calculated and its exports are built
    after: tuple[str, ...] = ()
    # a check of the input a generation makes before any runner is called, when it selects the stage (decision 94)
    precheck: Callable[[PierInput], None] | None = None
    # SoilStructure calculates the 地盤変位 of the stage's piles, for an input that considers it (decision 97)
    ground_displacement: GroundDisplacementRun | None = None
    # the stage of a footing of one part in place of this one, which makes both (decision 110): FRAMES_PART with the frame
    # analyses alone, SEISMIC_PART with the nonlinear analyses alone; the same id and stem
    parts: Mapping[str, StageSpec] = field(default_factory=dict)
    # the stages whose results the report reads when the same generation makes them, finished by their Capacita check:
    # the numbers of the sections it refers to or follows (0400 and 0612 / 0622 the column checks, decision 121). Not
    # dependencies: without them the report has no number to take (0400 stays the input alone, ADR-0012)
    reads: tuple[str, ...] = ()

    @property
    def has_report(self) -> bool:
        """A report (PDF) with its result JSON; a stage without one publishes only its files under post/."""
        return self.render is not None


FRAMES_PART, SEISMIC_PART = "frames", "seismic"


def _part(parts: FootingParts) -> str | None:
    """The key of ``StageSpec.parts`` for the footing *parts*; None when both (or neither) are made."""
    if parts.frames == parts.seismic:
        return None
    return FRAMES_PART if parts.frames else SEISMIC_PART


class LoadModelSource(Protocol):
    """A load model bound to the input being calculated (pipeline.addin.BoundAddin, decision 70)."""

    def result(self, pier: PierInput) -> Any: ...

    def with_section(self, pier: PierInput) -> PierInput: ...

    def record(self, pier: PierInput) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Registry:
    stages: tuple[StageSpec, ...]
    load_model: LoadModelSource | None = None  # stages_for: the input is read without the load model's items
    outputs: Mapping[str, tuple[str, ...]] = OUTPUT_STAGES  # the stages of each 出力項目 (decision 72)
    foundation: str | None = None  # the 基礎形式 of for_foundation: which items an item uses (outputs.uses)

    def __post_init__(self) -> None:
        if not self.stages:
            raise ValueError("段階がありません")
        if unknown := set(self.outputs) - set(OUTPUT_KEYS):
            raise ValueError(f"出力項目がありません: {'・'.join(sorted(unknown))}")
        items = [(key, stage_id) for key, stage_ids in self.outputs.items() for stage_id in stage_ids]
        item_of = {stage_id: key for key, stage_id in items}
        if len(item_of) != len(items):
            raise ValueError("段階が複数の出力項目にあります")
        if unknown := set(item_of) - {stage.id for stage in self.stages}:
            raise ValueError(f"出力項目の段階がありません: {'・'.join(sorted(unknown))}")
        seen: list[str] = []
        files: set[str] = set()
        shared: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {}  # the files of each analyzed FrameWeb file
        for stage in self.stages:
            if stage.id not in item_of:
                raise ValueError(f"{stage.id}の出力項目がありません")
            if stage.id in seen:
                raise ValueError(f"段階が重複しています: {stage.id}")
            for dependency in stage.depends_on:
                if dependency not in seen:
                    raise ValueError(f"{stage.id}の依存段階{dependency}が先に登録されていません")
            if unread := [name for name in stage.reads if name == stage.id or name not in item_of]:
                raise ValueError(f"{stage.id}が読む段階がありません: {'・'.join(unread)}")
            if not stage.stem.startswith(stage.id + "_") or not _plain_name(stage.stem):
                raise ValueError(f"{stage.id}のファイル{stage.stem}の名前は「{stage.id}_」で始まる必要があります")
            if (stage.render is not None and stage.calculate is None and stage.seismic_check is None
                    and stage.complete is None):
                raise ValueError(f"{stage.id}の計算書には計算が必要です")
            if stage.frame_analysis is not None and stage.nonlinear_analysis is not None:
                raise ValueError(f"{stage.id}は骨組解析と静的非線形解析の両方はできません")
            if (not stage.has_report and not stage.exports and stage.frame_analysis is None
                    and stage.nonlinear_analysis is None):
                raise ValueError(f"{stage.id}には成果物がありません")
            outputs = [(item.kind, item.file_name) for item in stage.exports]
            reused: set[str] = set()  # the files of an analysis an earlier stage shares
            analysis = stage.frame_analysis
            if analysis is not None:
                self._check_source(stage, analysis.stage, analysis.export, "骨組解析")
                if sorted(kind for kind, _ in analysis.files) != sorted(ANALYSIS_FILES):
                    raise ValueError(f"{stage.id}の骨組解析の出力は {'・'.join(ANALYSIS_FILES)} です")
                key = (analysis.stage, analysis.export)
                if key in shared:
                    if shared[key] != analysis.files:
                        raise ValueError(f"{stage.id}は{analysis.stage}の骨組解析を共有するので、同じ出力が必要です")
                    reused = {file_name for _, file_name in analysis.files}
                shared[key] = analysis.files
                outputs += analysis.files
            if stage.complete is not None and not stage.has_report:
                raise ValueError(f"{stage.id}の結果を仕上げるには計算書が必要です")
            for name in stage.after:
                if name not in stage.depends_on or self.get(name).soil_jr is None:
                    raise ValueError(f"{stage.id}が待つ{name}は、依存段階の SOIL-JR で計算する段階である必要があります")
                if stage.complete is not None or stage.frame_analysis is not None or stage.nonlinear_analysis is not None:
                    raise ValueError(f"{stage.id}は待つ段階があるので、仕上げと解析は持てません")
            # the files a completion reads: its own analysis, or those of a dependency (the footing of the frame
            # analyses alone reads their files, decision 110)
            if stage.complete is not None and analysis is None and stage.soil_jr is None and not any(
                    self.get(name).seismic_check is not None or self.get(name).complete is not None
                    or self.get(name).frame_analysis is not None for name in self.closure(stage.depends_on)):
                raise ValueError(f"{stage.id}の結果を仕上げるには、骨組解析か、骨組解析・耐震性能照査または仕上げる結果を持つ依存段階が"
                                 "必要です")
            check = stage.section_check
            if check is not None:
                if not stage.has_report:
                    raise ValueError(f"{stage.id}の断面照査を差し込む計算書がありません")
                outputs.append((check.kind, check.file_name))
            nonlinear = stage.nonlinear_analysis
            if nonlinear is not None:
                for kind in (nonlinear.export, *nonlinear.also):
                    self._check_source(stage, nonlinear.stage, kind, "静的非線形解析")
                outputs.append((nonlinear.kind, nonlinear.folder))
                if nonlinear.project is not None:
                    outputs.append((nonlinear.project.kind, nonlinear.project.file_name))
            if (seismic := stage.seismic_check) is not None:
                if nonlinear is None or nonlinear.project is None:
                    raise ValueError(f"{stage.id}の耐震性能照査には静的非線形解析と Aggre-SE のプロジェクトが必要です")
                if not stage.has_report:
                    raise ValueError(f"{stage.id}の耐震性能照査の計算書がありません")
                wanted = AGGRESE_FILES if seismic.direction is None else AGGRESE_PILE_FILES
                if sorted(kind for kind, _ in seismic.files) != sorted(wanted):
                    raise ValueError(f"{stage.id}の耐震性能照査の出力は {'・'.join(wanted)} です")
                if seismic.direction not in (None, AXIAL, TRANSVERSE):
                    raise ValueError(f"{stage.id}の耐震性能照査の方向が不正です: {seismic.direction}")
                outputs += seismic.files
            if (ground := stage.soil_jr) is not None:
                if ground.export not in {item.kind for item in stage.exports}:
                    raise ValueError(f"{stage.id}が SOIL-JR で計算する出力{ground.export}がありません")
                if stage.complete is None:  # (a report is checked with every completion)
                    raise ValueError(f"{stage.id}の SOIL-JR の結果の仕上げがありません")
                if stage.frame_analysis is not None or stage.nonlinear_analysis is not None:
                    raise ValueError(f"{stage.id}は SOIL-JR の計算と解析の両方はできません")
                outputs += [*ground.files, *ground.liquefaction]
            own = item_of[stage.id]
            for dependency in stage.depends_on:
                if item_of[dependency] != own and item_of[dependency] not in uses(own, self.foundation):
                    raise ValueError(f"{stage.id}（出力項目 {own}）は{dependency}（出力項目 {item_of[dependency]}）を読むので、"
                                     f"{own} は {item_of[dependency]} を使う出力項目です")
            kinds: set[str] = set()
            for kind, file_name in outputs:
                if not _KIND.fullmatch(kind):
                    raise ValueError(f"出力の種類の名前が不正です: {kind}")
                if kind in kinds:
                    raise ValueError(f"{stage.id}の出力の種類が重複しています: {kind}")
                if not _plain_name(file_name):
                    raise ValueError(f"出力ファイル名が不正です: {file_name}")
                if file_name in files and file_name not in reused:
                    raise ValueError(f"出力ファイル名が重複しています: {file_name}")
                kinds.add(kind)
                files.add(file_name)
            if stage.load_diagram and stage.load_diagram not in {item.kind for item in stage.exports}:
                raise ValueError(f"{stage.id}の荷重図の出力{stage.load_diagram}がありません")
            if stage.load_diagram and not stage.has_report:
                raise ValueError(f"{stage.id}の荷重図を差し込む計算書がありません")
            if (figures := stage.jrsnap_figures) is not None:
                for kind in (figures.export, *(item.export for item in figures.also)):
                    if kind not in {item.kind for item in stage.exports}:
                        raise ValueError(f"{stage.id}のデータ確認図と荷重図の出力{kind}がありません")
                if not stage.has_report:
                    raise ValueError(f"{stage.id}のデータ確認図と荷重図を差し込む計算書がありません")
                if stage.load_diagram:  # both put pages into the report as its load diagram
                    raise ValueError(f"{stage.id}にFEMPythonの荷重図とJRSNAPの荷重図の両方は差し込めません")
            seen.append(stage.id)
        for stage in self.stages:
            for foundation, variant in stage.foundations.items():
                if foundation not in choices.PILE_FOUNDATIONS or variant.id != stage.id or variant.foundations:
                    raise ValueError(f"{stage.id}の{foundation}の段階が不正です")
            for part, variant in stage.parts.items():
                if (part not in (FRAMES_PART, SEISMIC_PART) or variant.id != stage.id or variant.stem != stage.stem
                        or variant.parts or variant.foundations):
                    raise ValueError(f"{stage.id}の{part}の段階が不正です")
        for foundation in sorted({name for stage in self.stages for name in stage.foundations}):
            self.for_foundation(foundation)  # the registry of each 基礎形式 is checked as a registry is
        for part in sorted({name for stage in self.stages for name in stage.parts}):
            self._for_part(part)  # and so is the registry of each part of the footing

    def for_foundation(self, foundation: str | None) -> Registry:
        """The registry of the 基礎形式 *foundation*: each stage that has a stage for it is replaced by that; the registry
        itself when none has (the direct foundation, decision 85)."""
        if not any(foundation in stage.foundations for stage in self.stages):
            return self
        return replace(self, stages=tuple(stage.foundations.get(foundation, stage) for stage in self.stages),
                       foundation=foundation)

    def _for_part(self, part: str | None) -> Registry:
        if part is None or not any(part in stage.parts for stage in self.stages):
            return self
        return replace(self, stages=tuple(stage.parts.get(part, stage) for stage in self.stages))

    def for_footing(self, parts: FootingParts) -> Registry:
        """The registry of the footing *parts* (decision 110): each stage that has a stage for the one part made is
        replaced by that; the registry itself when both are made."""
        return self._for_part(_part(parts))

    def for_input(self, pier: PierInput) -> Registry:
        """The registry of the input: its 基礎形式 (decision 85), then the parts of the footing it chooses (decision 110)."""
        return self.for_foundation(pier.substructure.foundation).for_footing(footing_parts(pier.outputs))

    def _check_source(self, stage: StageSpec, source: str, export: str, what: str) -> None:
        if source not in stage.depends_on:
            raise ValueError(f"{stage.id}が{what}する{source}が依存段階にありません")
        if export not in {item.kind for item in self.get(source).exports}:
            raise ValueError(f"{stage.id}が{what}する{source}の出力{export} がありません")

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(stage.id for stage in self.stages)

    def get(self, stage_id: str) -> StageSpec:
        return self.stages[self.ids.index(stage_id)]

    def stage(self, stage_id: str) -> StageSpec:
        """The stage *stage_id*; an input error for a stage the registry does not have."""
        if stage_id not in self.ids:
            raise InputError(f"計算段階が不正です: {stage_id}")
        return self.get(stage_id)

    def item(self, stage_id: str) -> str:
        """The 出力項目 of the stage *stage_id*."""
        return next(key for key, stage_ids in self.outputs.items() if stage_id in stage_ids)

    def selected(self, outputs: Iterable[str]) -> tuple[str, ...]:
        """The stages of the 出力項目 *outputs*, in registry (dependency) order (decision 72): with every item each of
        them uses, as the input has them, these are every stage the generation calculates."""
        chosen = set(outputs)
        return tuple(stage.id for stage in self.stages if self.item(stage.id) in chosen)

    def waits(self, stage_id: str) -> bool:
        """Whether the stage is calculated only once SOIL-JR has returned its files: it has ``after``, or reads a stage
        that does (the frame analyses of a pile foundation, decision 89)."""
        stage = self.get(stage_id)
        return bool(stage.after) or any(self.waits(name) for name in stage.depends_on)

    def deferred(self, stage_ids: Sequence[str]) -> tuple[str, ...]:
        """Those of *stage_ids* that wait for a runner's result (``after``), in registry order."""
        return tuple(stage_id for stage_id in self.ids if stage_id in stage_ids and self.get(stage_id).after)

    def closure(self, selected: Sequence[str]) -> tuple[str, ...]:
        """The selected stages and everything they read, in registry (dependency) order."""
        needed = set(selected)
        for stage in reversed(self.stages):
            if stage.id in needed:
                needed.update(stage.depends_on)
        return tuple(stage_id for stage_id in self.ids if stage_id in needed)


# The 配筋図 of 4.1 by the report's names: export.drawing draws them, the report puts their (PDF, PNG) as they are.
_DRAWINGS = {"beam": "梁", "column": "柱", "footing": "フーチング", "pile": "杭"}


def _pile_detailing(detailing: Any) -> Any:
    """The 杭の構造細目 of the 0400 result *detailing*: a 場所打ち杭's, a 鋼管ソイルセメント杭's or None."""
    return detailing.pile if detailing.pile is not None else detailing.steel_pile


def _drawings(pier: PierInput, detailing: Any) -> dict[str, Any]:
    """The 配筋図 of 4.1 of the 0400 result *detailing* (with the pile of a pile foundation, decisions 98 and 99)."""
    drawn = drawing_figures(pier, _pile_detailing(detailing))
    return detailing_report.figure_specs({name: drawn[figure] for name, figure in _DRAWINGS.items() if figure in drawn})


def _frameweb(stage_id: str, build: Callable[[Any], dict[str, Any]]) -> Callable[[Results, PierInput], bytes]:
    return lambda results, pier: dump_json(build(results[stage_id]))


def _ndu_model(stage_id: str, profile: NduProfile, results: Results, pier: PierInput) -> NduModel:
    foundation = results["0500"]
    return build_ndu(profile, pier, foundation, calculate_embedment(pier, foundation), column_layout(pier),
                     results[stage_id])


def _jrsnap(stage_id: str, profile: NduProfile) -> Callable[[Results, PierInput], bytes]:
    return lambda results, pier: write_ndu(_ndu_model(stage_id, profile, results, pier))


def _load_cases(stage_id: str, profile: NduProfile) -> Callable[[Results, PierInput], tuple[tuple[int, int], ...]]:
    """(basic case, combination) of each 荷重図 page of the NDU of *stage_id*, from the model the NDU is written from
    (decision 51)."""
    return lambda results, pier: diagram_combinations(_ndu_model(stage_id, profile, results, pier))


def _aggrese(stage_id: str, profile: NduProfile) -> Callable[[Results, PierInput],
                                                              Callable[[str, Sequence[str]], bytes]]:
    """The project of the NDU of *stage_id*, checked before the analysis; then its writer (decision 49)."""
    def build(results: Results, pier: PierInput) -> Callable[[str, Sequence[str]], bytes]:
        project = build_project(_ndu_model(stage_id, profile, results, pier), pier)
        return lambda folder, names: write_project(project, databases(folder, names, len(project.cases)))
    return build


def _seismic_check(results: Results, pier: PierInput, path: Any, pages: Mapping[str, bytes]) -> Any:
    """Aggre-SE's report as the stage's report (decision 56, ADR-0009); with the 応答変位法 (decision 97) before its pages,
    and of a 場所打ち杭 with 杭頭反力の最大値から定める最小鉄筋量 and the 杭の段落とし計算書 after them (decision 98)."""
    piled = next(((stage_id, result) for stage_id, result in results.items() if isinstance(result, PileSeismicResult)),
                 None)
    if piled is None:
        return render_seismic_check(path, pages)
    stage_id, result = piled
    first = result.response.first_case if result.response is not None else None
    return render_pile_seismic_check(stage_id, result, first, path, pages)


def _pile_minimum(stage_id: str, source: str, profile: NduProfile, direction: str
                  ) -> Callable[[Any, Mapping[str, bytes], PierInput, Results], PileSeismicResult]:
    """How 0711 / 0721 of a 場所打ち杭 finishes its result (decision 98): Pvmax from the pickup of 復旧性L2 of its own Aggre-SE
    check, at the head element of each pile row of the NDU of *source*, for 杭頭反力の最大値から定める最小鉄筋量."""
    def complete(result: Any, files: Mapping[str, bytes], pier: PierInput, results: Results) -> PileSeismicResult:
        model = _pile_ndu_model(source, profile, results, pier)
        members = {member.number: member for member in model.members}
        heads = [(pile.first, members[pile.member].depth_piles) for pile in model.piles]
        lines = member_forces(files[seismic_file(stage_id, "pik")], [first for first, _ in heads], SEISMIC_PICKUP)
        pvmax = pile_head_reaction([(lines[first], piles) for first, piles in heads])
        words = "線路方向" if direction == AXIAL else "線路直角方向"
        return PileSeismicResult(minimum_bars(pier, words, pvmax), result)
    return complete


def _aggrese_files(stem: str) -> SeismicCheck:
    """The pickup, the summary workbook and the direct-foundation step table of Aggre-SE's check, beside
    ``<stem>.xml`` (decisions 57, 58, 60); *stem* is the stage's file stem, or its id (0711, 0721)."""
    stem = {"0711": "線路方向", "0721": "線路直角方向"}.get(stem, stem)
    return SeismicCheck((("pik", f"{stem}_Aggre-SE.pik"), ("xlsx", f"{stem}_Aggre-SE.xlsx"),
                         ("steps", f"{stem}_Aggre-SE_直接基礎.csv")))


def _pickups(stem: str) -> tuple[tuple[str, str], ...]:
    """The files of a frame analysis of ``<stem>.json`` (decision 46)."""
    return (("pik", f"{stem}.pik"), ("displacement", f"{stem}_ピックアップ変位量.csv"),
            ("reaction", f"{stem}_ピックアップ反力.csv"))


def _column_check(stage_id: str, stem: str, source: str, name: str, direction: Direction,
                  chapter: Chapter) -> StageSpec:
    """The frame analysis of the FrameWeb file of *source*, then Capacita's check of the column bottom in *direction*
    with its PIK, as chapter *chapter* of the report (decisions 46, 48)."""
    def wdj(results: Results, pier: PierInput, pik: bytes) -> bytes:
        check = results[stage_id]
        return write_wdj(build_wdj(check, point_index(pik, check.member)))

    # The report is Capacita's pages with its commentary, numbered from n.5 (decision 121): no grid Excel workbook.
    return StageSpec(stage_id, stem, (source,),
                     lambda pier, results: calculate_column_check(pier, results[source], direction),
                     lambda results, pier, path, pages: render_column_check(results[stage_id], path, pages),
                     frame_analysis=FrameAnalysis(source, "frameweb", _pickups(name)),
                     section_check=SectionCheck("wdj", f"{name}.wdj", wdj, lambda results: results[stage_id].sections,
                                                commentary=chapter.commentary,
                                                finish=lambda result, headings: replace(
                                                    result, headings=MappingProxyType(dict(headings)))))


# The column check each foundation check follows (decision 121), and each direction's for 0400's references.
_COLUMN_OF = {"0612": "0611", "0622": "0621"}
_COLUMNS = {"線路": "0611", "直角": "0621"}


def _after_column(chapter: FoundationChapter, stage_id: str, results: Results) -> FoundationChapter:
    """*chapter* numbered after the column check of the same direction (column_check.following_section)."""
    return replace(chapter, section=following_section(results.get(_COLUMN_OF[stage_id])))


def _columns(results: Results) -> dict[str, Any]:
    """The column checks of the same generation by direction, which 0400 refers to (decision 121)."""
    return {direction: results[stage_id] for direction, stage_id in _COLUMNS.items() if stage_id in results}


def _foundation_check(stage_id: str, stem: str, source: str, name: str, direction: FoundationDirection,
                      chapter: FoundationChapter) -> StageSpec:
    """The 基礎の照査 in *direction* with the support reactions of the frame analysis of the FrameWeb file of *source*,
    shared with the column check of the same file (decision 54)."""
    return StageSpec(stage_id, stem, ("0500", source),
                     lambda pier, results: prepare_foundation_check(pier, results["0500"], results[source], direction),
                     lambda results, pier, path, pages: render_foundation_check(
                         results[stage_id], path, _after_column(chapter, stage_id, results)),
                     frame_analysis=FrameAnalysis(source, "frameweb", _pickups(name)),
                     complete=lambda basis, files, pier, results: check_foundation(
                         basis, support_reactions(files["reaction"], basis.node)),
                     grid_documents=lambda results, pier, pages: foundation_check_report.grid_documents(
                         results[stage_id], _after_column(chapter, stage_id, results)),
                     reads=(_COLUMN_OF[stage_id],))


def _pile_check(stage_id: str, stem: str, source: str, name: str, direction: FoundationDirection,
                chapter: FoundationChapter) -> StageSpec:
    """The 基礎の照査 of a pile foundation in *direction* (decision 89): the pile heads' forces and the footing top's
    displacements of the frame analysis of the FrameWeb file of *source* against the limits of SOIL-JR's .sdr in 0500.
    It waits for them (the frame stands on SOIL-JR's springs), so it is calculated once 0500 is complete."""
    def complete(basis: Any, files: Mapping[str, bytes], pier: PierInput, results: Results) -> Any:
        found = check_pile(basis, pile_limits(results["0500"].sdr, direction),
                           head_forces(files["pik"], [member.member for member in basis.members]),
                           footing_displacements(files["displacement"], basis.node))
        # the 安全性（破壊）'s section forces times the 応答値係数 γR (decision 104)
        lines = {member: factored(found_lines) for member, found_lines in
                 member_forces(files["pik"], [member.member for member in basis.members], basis.body_pickup).items()}
        if pier.substructure.foundation == choices.CAST_IN_PLACE_PILE:
            # the pile body of a cast-in-place pile: WebPier chooses the design forces, Capacita checks the circular section
            # and returns its pages (decision 91)
            cast = pile_cast_section(pier)
            rows = [select_pile_cast(member.row, member.member, member.piles, lines[member.member])
                    for member in basis.members]
            wdj = write_pile_wdj(build_pile_wdj(cast, pile_factor(cast), rows))
            checked = capacita.check_section(wdj, "pile.wdj", capacita.runner_path(), PILE_CAST_SECTIONS)
            return with_cast(found, assemble_pile_cast(cast, rows, checked.engine_version, sha256(wdj), checked.skipped,
                                                       checked.pages))
        # the pile body of a steel pipe pile: WebPier chooses the design forces, Capacita's SteelDan calculates (decision 89)
        steel = pile_steel(pier)
        rows = [select_pile_forces(member.row, member.member, member.piles, lines[member.member])
                for member in basis.members]
        wsj = write_wsj(steel, rows)
        values, version = run_pile_body(wsj, {row.row for row in rows}, capacita.runner_path())
        found = with_body(found, assemble_pile_body(steel, rows, values, version, sha256(wsj)))
        # the joint with the footing (decision 90): the same pickup's head lines, Capacita's HsCalc calculates Mud
        forces = [select_pile_joint(member.row, member.member, member.piles, lines[member.member]) for member in basis.members]
        joint = pile_joint_section(pier, steel)
        content = write_pile_joint(joint, forces)
        moments, joint_version = run_pile_joint(content, {row_id(row.row) for row in forces}, capacita.runner_path())
        return with_joint(found, assemble_pile_joint(joint, forces, {row.row: moments[row_id(row.row)] for row in forces},
                                                     joint_version, sha256(content)))

    def prepare(pier: PierInput, results: Results) -> Any:
        if pier.substructure.foundation == choices.CAST_IN_PLACE_PILE:
            pile_cast_section(pier)  # a blank item of the pile body is an input error before any runner is called
        return prepare_pile_check(pier, results[source], direction)

    return StageSpec(stage_id, stem, ("0500", source), prepare,
                     lambda results, pier, path, pages: render_pile_check(
                         results[stage_id], path, _after_column(chapter, stage_id, results)),
                     frame_analysis=FrameAnalysis(source, "frameweb", _pickups(name)), complete=complete,
                     grid_documents=lambda results, pier, pages: pile_check_report.grid_documents(
                         results[stage_id], _after_column(chapter, stage_id, results)),
                     reads=(_COLUMN_OF[stage_id],))


def _with_pile_check(stage: StageSpec, source: str, name: str, direction: FoundationDirection,
                     chapter: FoundationChapter) -> StageSpec:
    """The direct foundation's 基礎の照査 *stage* with its stage for each pile foundation (decision 89)."""
    return replace(stage, foundations={foundation: _pile_check(stage.id, stage.stem, source, name, direction, chapter)
                                       for foundation in choices.PILE_FOUNDATIONS})


_FOOTING_FRAMES = ("0610", "0612", "0620", "0622")
_FOOTING_SEISMIC = ("0710", "0711", "0720", "0721")


def _footing(stem: str, frames: bool = True, seismic: bool = True) -> StageSpec:
    """0800: the footing response values of both directions (decision 60), prepared from 0500 and the frames of
    0610 and 0620 before any runner, finished with the support reactions of the frame analyses of 0612 and 0622
    (the same analyses as 0611 and 0621) and the step tables of the seismic checks of 0711 and 0721, whose Cases are
    the combinations of 0710 and 0720 (decision 76). A stage of one part (decision 110) reads only its analyses; with
    both, it has the stage of each part alone."""
    def complete(bases: Any, files: Mapping[str, bytes], pier: PierInput, results: Results) -> Any:
        def analyses(reactions_of: str, steps_of: str, nonlinear: str, basis: Any):
            return (support_reactions(files[seismic_file(reactions_of, "reaction")], basis.node) if frames else None,
                    foundation_steps(files[seismic_file(steps_of, "steps")]) if seismic else None,
                    tuple(combination.alpha_f for combination in results[nonlinear].combinations) if seismic else None)
        return complete_footing(bases, analyses("0612", "0711", "0710", bases.longitudinal),
                                analyses("0622", "0721", "0720", bases.transverse))

    depends = ("0500", *(_FOOTING_FRAMES if frames else ()), *(_FOOTING_SEISMIC if seismic else ()))
    stage = StageSpec("0800", stem, depends,
                      lambda pier, results: calculate_footing(pier, results["0500"], results.get("0610"),
                                                              results.get("0620")),
                      lambda results, pier, path, pages: render_footing(results["0800"], path),
                      complete=complete,
                      grid_documents=lambda results, pier, pages: footing_report.grid_documents(results["0800"]))
    if frames and seismic:
        stage = replace(stage, parts={FRAMES_PART: _footing(stem, seismic=False),
                                      SEISMIC_PART: _footing(stem, frames=False)})
    return stage


def _footing_check(stage_id: str, stem: str, name: str, direction: str,
                   parts: FootingParts = FootingParts(frames=True, seismic=True)) -> StageSpec:
    """0810 / 0820: Capacita checks the overhang of *direction* ("longitudinal" / "transverse") with the response
    values of 0800 written in the WDJ, as the sections of the footing *parts* (decision 110; with both, the stage has
    the stage of each part alone), numbered by their chapter (decision 60, ADR-0008)."""
    chapter = footing_chapters(parts.frames, parts.seismic)[0 if direction == "longitudinal" else 1]
    stage = _footing_check_stage(stage_id, stem, name, direction, chapter)
    if parts.frames and parts.seismic:
        stage = replace(stage, parts={part: _footing_check(stage_id, stem, name, direction, FootingParts(
            frames=part == FRAMES_PART, seismic=part == SEISMIC_PART)) for part in (FRAMES_PART, SEISMIC_PART)})
    return stage


def _footing_check_stage(stage_id: str, stem: str, name: str, direction: str, chapter: FootingChapter) -> StageSpec:
    return StageSpec(stage_id, stem, ("0800",), None,
                     lambda results, pier, path, pages: render_footing_check(results[stage_id], path, pages, chapter),
                     section_check=SectionCheck("wdj", f"{name}フーチング.wdj",
                                                lambda results, pier, pik: write_footing_wdj(
                                                    build_footing_wdj(results[stage_id])),
                                                lambda results: results[stage_id].sections),
                     complete=lambda result, files, pier, results: calculate_footing_check(
                         pier, getattr(results["0800"], direction)),
                     grid_documents=lambda results, pier, pages: footing_check_report.grid_documents(
                         results[stage_id], chapter))


def member_frame_forces(basis: Any, frame_pik: bytes) -> dict[tuple[int, int], Any]:
    """The PIK lines of the frame analysis by (pickup, member) of the base members of *basis* (decision 96)."""
    frame_forces: dict[tuple[int, int], Any] = {}
    for pickup in sorted(set(basis.pickups.values())):
        for member, lines in member_forces(frame_pik, list(basis.members), pickup).items():
            frame_forces[(pickup, member)] = lines
    return frame_forces


def pile_footing_forces(basis: Any, frame_pik: bytes | None, seismic_pik: bytes, seismic_frame: Any
                        ) -> tuple[dict[tuple[int, int], Any] | None, Any, dict[int, int]]:
    """What ``calc.pile_footing.complete`` reads for one direction: the PIK lines of the frame analysis by (pickup, member)
    (None without it, decision 110), the pickup lines of Aggre-SE by its member, and the element of the NDU of each base
    member of the frame (found by where the member is in *seismic_frame*, the frame of 0710 / 0720, whose NDU the pickup is
    of; decision 96)."""
    frame_forces = None if frame_pik is None else member_frame_forces(basis, frame_pik)
    numbers = element_numbers(seismic_frame)
    by_ends = {(seismic_frame.nodes[member.start - 1].x, seismic_frame.nodes[member.end - 1].x): member.number
               for member in seismic_frame.members if member.region is Region.FOOTING_BASE}
    elements = {member: numbers[by_ends[ends]] for member, ends in basis.chain.items() if ends in by_ends}
    return frame_forces, member_forces(seismic_pik, sorted(set(elements.values())), SEISMIC_PICKUP), elements


def _pile_footing(stem: str, frames: bool = True, seismic: bool = True) -> StageSpec:
    """0800 of a pile foundation (decision 96): the section forces of the footing of both directions, prepared from the
    pile frames of 0610 and 0620 before any runner, finished with the PIK of the frame analyses of 0612 and 0622 and the
    pickup of 復旧性L2 of the seismic checks of 0711 and 0721. A stage of one part (decision 110) reads only its analyses
    (the seismic part alone takes the sections from the frames of 0710 and 0720); with both, it has the stage of each
    part alone."""
    def complete(bases: Any, files: Mapping[str, bytes], pier: PierInput, results: Results) -> Any:
        def analyses(reactions_of: str, seismic_check: str, nonlinear: str, basis: Any) -> tuple[Any, Any, Any]:
            if not seismic:
                return member_frame_forces(basis, files[seismic_file(reactions_of, "pik")]), None, None
            frame_pik = files[seismic_file(reactions_of, "pik")] if frames else None
            return pile_footing_forces(basis, frame_pik, files[seismic_file(seismic_check, "pik")],
                                       results[nonlinear].frame)
        return complete_pile_footing(bases, analyses("0612", "0711", "0710", bases.longitudinal),
                                     analyses("0622", "0721", "0720", bases.transverse))

    frame_of = ("0610", "0620") if frames else ("0710", "0720")
    depends = ("0500", *(_FOOTING_FRAMES if frames else ()), *(_FOOTING_SEISMIC if seismic else ()))
    stage = StageSpec("0800", stem, depends,
                      lambda pier, results: calculate_pile_footing(pier, results[frame_of[0]], results[frame_of[1]],
                                                                   frames),
                      lambda results, pier, path, pages: pile_footing_report.render_pile_footing(results["0800"], path),
                      complete=complete,
                      grid_documents=lambda results, pier, pages: pile_footing_report.grid_documents(results["0800"]))
    if frames and seismic:
        stage = replace(stage, parts={FRAMES_PART: _pile_footing(stem, seismic=False),
                                      SEISMIC_PART: _pile_footing(stem, frames=False)})
    return stage


def _pile_footing_check(stage: StageSpec, direction: str,
                        parts: FootingParts = FootingParts(frames=True, seismic=True)) -> StageSpec:
    """0810 / 0820 of a pile foundation (decision 96): the WDJ of the five points of the footing, the sections of the
    footing *parts* (decision 110; with both, the stage has the stage of each part alone)."""
    stage_id = stage.id
    chapter = footing_chapters(parts.frames, parts.seismic)[0 if direction == "longitudinal" else 1]
    found = _pile_footing_check_stage(stage, direction, chapter)
    if parts.frames and parts.seismic:
        found = replace(found, parts={part: _pile_footing_check(stage, direction, FootingParts(
            frames=part == FRAMES_PART, seismic=part == SEISMIC_PART)) for part in (FRAMES_PART, SEISMIC_PART)})
    return found


def _pile_footing_check_stage(stage: StageSpec, direction: str, chapter: FootingChapter) -> StageSpec:
    stage_id = stage.id
    return StageSpec(stage_id, stage.stem, ("0800",), None,
                     lambda results, pier, path, pages: render_footing_check(results[stage_id], path, pages, chapter),
                     section_check=SectionCheck(
                         "wdj", stage.section_check.file_name if stage.section_check else f"{stage_id}.wdj",
                         lambda results, pier, pik: write_pile_footing_wdj(build_pile_footing_wdj(results[stage_id])),
                         lambda results: results[stage_id].sections),
                     complete=lambda result, files, pier, results: calculate_pile_footing_check(
                         pier, getattr(results["0800"], direction)),
                     grid_documents=lambda results, pier, pages: footing_check_report.grid_documents(
                         results[stage_id], chapter))


def _with_pile_footing(stage: StageSpec, direction: str | None = None) -> StageSpec:
    """The direct footing's *stage* with its stage for a 場所打ち杭 (decision 96); each part of the footing has its own
    (decision 110)."""
    piled = _pile_footing(stage.stem) if direction is None else _pile_footing_check(stage, direction)
    return replace(stage, foundations={choices.CAST_IN_PLACE_PILE: piled})


def _max_responses(files: Mapping[str, bytes], *stages: str) -> list[Any]:
    """The 最大応答震度 of the summary workbook of each seismic check of *stages* (decision 59)."""
    return [read_max_response(files[seismic_file(stage_id, "xlsx")], dict(_aggrese_files(stage_id).files)["xlsx"])
            for stage_id in stages]


def _cantilever(stem: str, longitudinal: str, transverse: str) -> StageSpec:
    """0900: the 応答値 of the cantilever beam from 0600, finished with the 最大応答震度 of the seismic checks of
    *longitudinal* (0711) and *transverse* (0721) (decision 59)."""
    def complete(basis: Any, files: Mapping[str, bytes], pier: PierInput, results: Results) -> Any:
        return complete_cantilever(pier, results["0600"], basis, *_max_responses(files, longitudinal, transverse))

    return StageSpec("0900", stem, ("0600", longitudinal, transverse),
                     lambda pier, results: calculate_cantilever(pier, results["0600"]),
                     lambda results, pier, path, pages: render_cantilever(results["0900"], results["0600"], pier, path),
                     complete=complete,
                     grid_documents=lambda results, pier, pages: cantilever_report.grid_documents(
                         results["0900"], results["0600"], pier))


def _cantilever_check(stem: str, name: str) -> StageSpec:
    """0910: Capacita checks the beam at the column face with the section forces of 0900 (decision 59)."""
    return StageSpec("0910", stem, ("0900",), None,
                     lambda results, pier, path, pages: render_cantilever_check(results["0910"], pier, path, pages),
                     section_check=SectionCheck("wdj", f"{name}.wdj",
                                                lambda results, pier, pik: write_wdj(build_cantilever_wdj(results["0910"])),
                                                lambda results: results["0910"].sections),
                     complete=lambda result, files, pier, results: calculate_cantilever_section(pier, results["0900"]),
                     grid_documents=lambda results, pier, pages: cantilever_check_report.grid_documents(
                         results["0910"], pier, pages))


def _pile_ground() -> StageSpec:
    """0500 of a pile foundation (decision 85, ADR-0013): the ground rows WebPier derives, the .sdt of them, SOIL-JR's
    calculation of it, and SOIL-JR's report as the stage's report."""
    return StageSpec("0500", f"0500_{soiljr.STEM}", (),
                     lambda pier, results: calculate_pile_ground(pier), soiljr.render,
                     (Export("sdt", soiljr.SDT, soiljr.sdt, metadata=soiljr.SDT_FACTS),),
                     soil_jr=SoilJrCalculation("sdt", soiljr.FILES, soiljr.LIQUEFACTION, soiljr.liquefied),
                     complete=soiljr.complete)


def _with_piles(stage: StageSpec, calculate: Callable[[PierInput, PileFoundation, Any], Any]) -> StageSpec:
    """*stage* with its stage for each pile foundation (``_on_piles``)."""
    return replace(stage, foundations={foundation: _on_piles(stage, calculate)
                                       for foundation in choices.PILE_FOUNDATIONS})


def _pile_foundation(results: Results) -> PileFoundation:
    """What the frame of a pile foundation takes of 0500, once SOIL-JR has returned its springs (decision 88)."""
    model = results["0500"]
    return PileFoundation(model.ground, model.springs)


def _pile_ndu_model(stage_id: str, profile: NduProfile, results: Results, pier: PierInput,
                    reverse: bool = False, liquefied: bool = False) -> PileNduModel:
    """The NDU model of the piles of the 0710 or 0720 result, from the seismic tables of SOIL-JR's .sdc (decision 93): the
    one of the combinations that push forward, or of the reversed (逆向) ones, whose columns of the .sdc go the other way.
    With *liquefied* it is the one for the liquefaction, from the .sdc for it (decision 95)."""
    ground = results["0500"]
    springs = parse_seismic(ground.liquefied_sdc, liquefied=True) if liquefied else parse_seismic(ground.sdc)
    return build_pile_ndu(profile, pier, column_layout(pier), results[stage_id], springs, reverse=reverse,
                          liquefied=liquefied)


def _with_seismic_piles(stage: StageSpec, calculate: Callable[[PierInput, PileFoundation, Any], Any], profile: NduProfile,
                        file_name: str, reverse_file_name: str | None = None) -> StageSpec:
    """*stage* (0710 or 0720) with its stage for a 場所打ち杭: the frame on the piles, the NDU of the piles (decision 93) and the
    figures JRSNAP draws of it. A stage with reversed combinations (0720) has a second NDU for them, *reverse_file_name*, and
    the cases of the reversed push only are drawn from that one."""
    split = reverse_file_name is not None

    def ndu(reverse: bool, liquefied: bool = False) -> Callable[[Results, PierInput], bytes]:
        return lambda results, pier: write_pile_ndu(_pile_ndu_model(stage.id, profile, results, pier, reverse, liquefied))

    def figures(reverse: bool) -> Callable[[Results, PierInput], tuple[tuple[int, int], ...]]:
        return lambda results, pier: diagram_combinations(_pile_ndu_model(stage.id, profile, results, pier, reverse),
                                                         used_only=split)

    exports = (Export("jrsnap", file_name, ndu(False), metadata=_NDU),)
    also: tuple[AlsoFigures, ...] = ()
    if reverse_file_name is not None:
        exports += (Export("jrsnapreverse", reverse_file_name, ndu(True), metadata=_NDU),)
        also = (AlsoFigures("jrsnapreverse", figures(True)),)
    # the NDUs for the liquefaction (decision 95): one for each push, written for an input that liquefies; no figures of theirs
    exports += (Export("jrsnapliquefied", file_name.replace(".ndu", "_液状化.ndu"), ndu(False, True), metadata=_NDU,
                       liquefied=True),)
    if reverse_file_name is not None:
        exports += (Export("jrsnapliquefiedreverse", reverse_file_name.replace("_逆向.ndu", "_液状化_逆向.ndu"),
                           ndu(True, True), metadata=_NDU, liquefied=True),)
    piles = replace(_on_piles(stage, calculate), exports=exports,
                    jrsnap_figures=JrsnapFigures("jrsnap", figures(False), also), precheck=_ground_inputs,
                    ground_displacement=GroundDisplacementRun(lambda results, pier: _ground_depths(stage.id, profile,
                                                                                                   results, pier)))
    return replace(stage, foundations={choices.CAST_IN_PLACE_PILE: piles})


def _ground_depths(stage_id: str, profile: NduProfile, results: Results, pier: PierInput) -> tuple[Decimal, ...]:
    """The depths of the pile nodes of the NDU of *stage_id* below the ground surface: the pile heads are at Df (decision 97)."""
    head = Decimal(repr(results["0500"].ground.depth.value))
    return tuple(head + depth for depth in pile_node_depths(_pile_ndu_model(stage_id, profile, results, pier)))


def _ground_inputs(pier: PierInput) -> None:
    """The inputs of the 地盤変位 of an input that considers it, checked before any runner (decision 97)."""
    if displaces(pier):
        surface_layers(pier)
        region_coefficient(pier)


def _liquefaction_index(stage_id: str) -> Callable[[PierInput], None]:
    """The check that an input whose ground liquefies has the 液状化指数, which Aggre-SE's Cases for the liquefaction need and
    which is not filled in by a default (decision 95)."""
    def check(pier: PierInput) -> None:
        if pier.seismic_design.liquefaction_index is None and soiljr.liquefied(pier):
            raise InputError(f"耐震設計条件.液状化指数: 液状化する地層がある杭基礎の{stage_id}には値が必要です"
                             f"（{'・'.join(choices.LIQUEFACTION_INDEXES)}）")
    return check


def _pile_aggrese(stage_id: str, profile: NduProfile, file_names: Sequence[str]
                  ) -> Callable[[Results, PierInput], Callable[[str, Sequence[str]], bytes]]:
    """The project of the piles of the NDUs *file_names* of *stage_id* (the NDU of the forward push, then the one of the
    reversed push, decisions 93 and 94, and for an input that liquefies the NDUs for the liquefaction in the same order,
    decision 95), checked before the analysis; then its writer."""
    return lambda results, pier: _pile_project(stage_id, profile, file_names, results, pier)


def _pile_project(stage_id: str, profile: NduProfile, file_names: Sequence[str], results: Results, pier: PierInput,
                  response: ResponseDisplacementResult | None = None) -> Callable[[str, Sequence[str]], bytes]:
    """The writer of the project of ``_pile_aggrese``, and with *response* the Cases of the 応答変位法 after them (decision 97)."""
    models = [_pile_ndu_model(stage_id, profile, results, pier, reverse=index > 0) for index in range(len(file_names))]
    names = list(file_names)
    liquefied: list[PileNduModel] = []
    if soiljr.liquefied(pier):
        liquefied = [_pile_ndu_model(stage_id, profile, results, pier, reverse=index > 0, liquefied=True)
                     for index in range(len(file_names))]
        names += [name.replace("_逆向.ndu", "_液状化_逆向.ndu") if name.endswith("_逆向.ndu")
                  else name.replace(".ndu", "_液状化.ndu") for name in file_names]
    responded = () if response is None else _response_models(stage_id, profile, results, pier, response)
    project = build_pile_project(models, pier, liquefied=liquefied,
                                 response=[(case.level, model) for _, case, model in responded])
    groups = [(name.removesuffix(".ndu"), len(model.combinations)) for name, model in zip(names, [*models, *liquefied])]
    groups += [(name.removesuffix(".ndu"), 1) for name, _, _ in responded]
    return lambda folder, found: write_project(project, ndu_databases(folder, found, groups))


def _response_models(stage_id: str, profile: NduProfile, results: Results, pier: PierInput,
                     response: ResponseDisplacementResult) -> tuple[tuple[str, Any, PileNduModel], ...]:
    """The NDU of each Case of the 応答変位法 of the piles of *stage_id* (decision 97): its file name, the Case and the model."""
    seismic, ground = results[stage_id], results["0500"]
    springs = parse_seismic(ground.sdc)
    head = Decimal(repr(ground.ground.depth.value))
    return tuple((f"{profile.data_name}_応答変位法_{case.level}-{case.number}.ndu", case,
                  response_ndu(profile, pier, column_layout(pier), seismic, springs, seismic.ground_displacement, head,
                               case)) for case in response.cases)


def _inertia_case(stage_id: str, profile: NduProfile, results: Results, pier: PierInput) -> int:
    """The Aggre-SE Case of the forward combination of ρm 1.0 and αf 1.0 (decision 97): the Cases of the forward NDU come first,
    in its order."""
    pattern = response_pattern(results[stage_id])
    model = _pile_ndu_model(stage_id, profile, results, pier)
    return 1 + next(index for index, combination in enumerate(model.combinations)
                    if (Decimal(repr(combination.rho_m.value)), Decimal(repr(combination.alpha_f.value))) == RESPONSE_PATTERN
                    and combination.coefficients == tuple(int(action.case in pattern.cases)
                                                          for action in results[stage_id].basic_cases))


def _response(stage_id: str, profile: NduProfile, file_names: Sequence[str]) -> ResponseAnalysis:
    """The 応答変位法 of the piles of *stage_id* whose NDUs are *file_names* (decision 97)."""
    def ndus(results: Results, pier: PierInput, response: ResponseDisplacementResult) -> tuple[tuple[str, bytes], ...]:
        return tuple((name, write_pile_ndu(model))
                     for name, _, model in _response_models(stage_id, profile, results, pier, response))

    return ResponseAnalysis(lambda results, pier: _inertia_case(stage_id, profile, results, pier), ndus,
                            lambda results, pier, response: _pile_project(stage_id, profile, file_names, results, pier,
                                                                          response))


def _with_nonlinear_piles(stage: StageSpec, source: str, profile: NduProfile, file_names: Sequence[str],
                          direction: str) -> StageSpec:
    """*stage* (0711 or 0721) with its stage for a 場所打ち杭 (decision 94): JRSNAP analyzes each NDU of *source* (the one
    of the reversed push too, when *file_names* has it) into the one folder, Aggre-SE checks the piles with the project of
    all their Cases and the limits of SOIL-JR's .sdr in *direction*, and the direct foundation's step table is not made."""
    analysis, seismic = stage.nonlinear_analysis, stage.seismic_check
    assert analysis is not None and analysis.project is not None and seismic is not None
    analysis = replace(analysis, project=replace(analysis.project, build=_pile_aggrese(source, profile, file_names)),
                       also=(*(("jrsnapreverse",) if len(file_names) > 1 else ()), "jrsnapliquefied",
                             *(("jrsnapliquefiedreverse",) if len(file_names) > 1 else ())),
                       response=_response(source, profile, file_names))
    piled = replace(stage, nonlinear_analysis=analysis, precheck=_liquefaction_index(stage.id),
                    seismic_check=SeismicCheck(tuple(file for file in seismic.files if file[0] != "steps"), direction),
                    complete=_pile_minimum(stage.id, source, profile, direction))
    return replace(stage, foundations={choices.CAST_IN_PLACE_PILE: piled})


def _on_piles(stage: StageSpec, calculate: Callable[[PierInput, PileFoundation, Any], Any]) -> StageSpec:
    """*stage* of the direct foundation as it is for a pile foundation: the frame stands on the piles and the springs of
    SOIL-JR, so it is calculated and its files are built once 0500 is complete (decision 88)."""
    return replace(stage, calculate=lambda pier, results: calculate(pier, _pile_foundation(results), results["0600"]),
                   after=("0500",), foundations={})


# A normal generation only writes the NDU; reading it in JRSNAP and running an analysis are separate records.
_NDU = {"target_version": TARGET_VERSION, "app_read_verified": False, "analysis_run": False}
# The same generation has Aggre-SE read the project and check with it (decision 56): the sidecar names that report.
_PROJECT = {"target": "Aggre-SE", "target_version": BATCH_VERSION}

_DETAILING = StageSpec(
    "0400", "0400_照査の前提", (),
    lambda pier, results: calculate_detailing(pier),
    lambda results, pier, path, pages: render_detailing(results["0400"], path, _drawings(pier, results["0400"]),
                                                        _columns(results)),
    (Export("dxf", "配筋図.dxf", lambda results, pier: drawing_dxf(pier, _pile_detailing(results["0400"]))),),
    grid_documents=lambda results, pier, pages: detailing_report.grid_documents(
        results["0400"], _drawings(pier, results["0400"]), _columns(results)),
    reads=tuple(_COLUMNS.values()))

STAGES = Registry((
    StageSpec("0500", "0500_直接基礎", (),
              lambda pier, results: calculate_foundation(pier),
              lambda results, pier, path, pages: render_foundation(
                  results["0500"], pier, applicable_embedment(pier, results["0500"]), path),
              grid_documents=lambda results, pier, pages: foundation_report.grid_documents(
                  results["0500"], pier, applicable_embedment(pier, results["0500"])),
              foundations={foundation: _pile_ground() for foundation in choices.PILE_FOUNDATIONS}),
    # 照査の前提 (decision 73): the input alone; the 配筋図 in 4.1 and in post/ (one DXF of the three). A 場所打ち杭's
    # 杭の構造細目 read 1/β of SOIL-JR's .sdc, so its 0400 is calculated once 0500 is complete (decision 98).
    replace(_DETAILING, foundations={choices.CAST_IN_PLACE_PILE: replace(
        _DETAILING, depends_on=("0500",), after=("0500",),
        calculate=lambda pier, results: calculate_detailing(pier, results["0500"].springs))}),
    StageSpec("0600", "0600_上部工反力", (),
              lambda pier, results: calculate_reaction(pier),
              lambda results, pier, path, pages: render_reaction(results["0600"], pier, path),
              grid_documents=lambda results, pier, pages: reaction_report.grid_documents(results["0600"], pier)),
    _with_piles(StageSpec("0610", "0610_線路方向荷重", ("0500", "0600"),
              lambda pier, results: calculate_longitudinal(pier, results["0500"], results["0600"]),
              lambda results, pier, path, pages: render_longitudinal(results["0610"], results["0600"], pier, path,
                                                                     pages),
              (Export("frameweb", "線路方向.json", _frameweb("0610", build_frameweb)),), load_diagram="frameweb",
              grid_documents=lambda results, pier, pages: longitudinal_report.grid_documents(
                  results["0610"], results["0600"], pier)), calculate_longitudinal),
    _column_check("0611", "0611_線路方向照査", "0610", "線路方向", COLUMN_LONGITUDINAL, CHAPTER_8),
    _with_pile_check(
        _foundation_check("0612", "0612_線路方向基礎", "0610", "線路方向", FOUNDATION_LONGITUDINAL, FOUNDATION_CHAPTER_8),
        "0610", "線路方向", FOUNDATION_LONGITUDINAL, FOUNDATION_CHAPTER_8),
    _with_piles(StageSpec("0620", "0620_直角方向荷重", ("0500", "0600"),
              lambda pier, results: calculate_transverse(pier, results["0500"], results["0600"]),
              lambda results, pier, path, pages: render_transverse(results["0620"], results["0600"], pier, path,
                                                                   pages),
              (Export("frameweb", "線路直角方向.json", _frameweb("0620", build_frameweb_transverse)),),
              load_diagram="frameweb",
              grid_documents=lambda results, pier, pages: transverse_report.grid_documents(
                  results["0620"], results["0600"], pier)), calculate_transverse),
    _column_check("0621", "0621_直角方向照査", "0620", "線路直角方向", COLUMN_TRANSVERSE, CHAPTER_9),
    _with_pile_check(
        _foundation_check("0622", "0622_直角方向基礎", "0620", "線路直角方向", FOUNDATION_TRANSVERSE, FOUNDATION_CHAPTER_9),
        "0620", "線路直角方向", FOUNDATION_TRANSVERSE, FOUNDATION_CHAPTER_9),
    # 0710 / 0720 calculate D1, D2, the buoyancy and the snow themselves and read no 0610 / 0620 (decision 78).
    _with_seismic_piles(StageSpec(
        "0710", "0710_線路方向荷重", ("0500", "0600"),
        lambda pier, results: calculate_seismic_longitudinal(pier, results["0500"], results["0600"]),
        lambda results, pier, path, pages: render_seismic_longitudinal(results["0710"], results["0600"], pier, path, pages),
        (Export("jrsnap", "線路方向.ndu", _jrsnap("0710", NDU_LONGITUDINAL), metadata=_NDU),),
        jrsnap_figures=JrsnapFigures("jrsnap", _load_cases("0710", NDU_LONGITUDINAL)),
        grid_documents=lambda results, pier, pages: seismic_longitudinal_report.grid_documents(
            results["0710"], results["0600"], pier)), calculate_seismic_longitudinal, NDU_LONGITUDINAL, "線路方向.ndu"),
    _with_nonlinear_piles(StageSpec(
        "0711", "0711_線路方向非線形解析", ("0710",), render=_seismic_check,
        nonlinear_analysis=NonlinearAnalysis(
            "0710", "jrsnap", "jrsnap", "線路方向_JRSNAP",
            Project("aggrese", "線路方向.xml", _aggrese("0710", NDU_LONGITUDINAL), _PROJECT)),
        seismic_check=_aggrese_files("線路方向")), "0710", NDU_LONGITUDINAL, ("線路方向.ndu",), AXIAL),
    _with_seismic_piles(StageSpec(
        "0720", "0720_線路直角方向荷重", ("0500", "0600"),
        lambda pier, results: calculate_seismic_transverse(pier, results["0500"], results["0600"]),
        lambda results, pier, path, pages: render_seismic_transverse(results["0720"], results["0600"], pier, path, pages),
        (Export("jrsnap", "線路直角方向.ndu", _jrsnap("0720", NDU_TRANSVERSE), metadata=_NDU),),
        jrsnap_figures=JrsnapFigures("jrsnap", _load_cases("0720", NDU_TRANSVERSE)),
        grid_documents=lambda results, pier, pages: seismic_transverse_report.grid_documents(
            results["0720"], results["0600"], pier)),
        calculate_seismic_transverse, NDU_TRANSVERSE, "線路直角方向.ndu", "線路直角方向_逆向.ndu"),
    # Its NDU has two combinations, so the runner analyzes both in one run of S_ANALYSIS.exe (decision 47).
    _with_nonlinear_piles(StageSpec(
        "0721", "0721_線路直角方向非線形解析", ("0720",), render=_seismic_check,
        nonlinear_analysis=NonlinearAnalysis(
            "0720", "jrsnap", "jrsnap", "線路直角方向_JRSNAP",
            Project("aggrese", "線路直角方向.xml", _aggrese("0720", NDU_TRANSVERSE), _PROJECT)),
        seismic_check=_aggrese_files("線路直角方向")),
        "0720", NDU_TRANSVERSE, ("線路直角方向.ndu", "線路直角方向_逆向.ndu"), TRANSVERSE),
    _with_pile_footing(_footing("0800_フーチング")),
    _with_pile_footing(_footing_check("0810", "0810_線路方向フーチング照査", "線路方向", "longitudinal"), "longitudinal"),
    _with_pile_footing(_footing_check("0820", "0820_直角方向フーチング照査", "線路直角方向", "transverse"), "transverse"),
    _cantilever("0900_片持ち梁", "0711", "0721"),
    _cantilever_check("0910_片持ち梁照査", "片持ち梁"),
))

# --- a load model (decision 70) ------------------------------------------------------------------------------------


def _generic_ndu(stage_id: str, base: NduProfile) -> Callable[[Results, PierInput], NduModel]:
    def model(results: Results, pier: PierInput) -> NduModel:
        return _ndu_model(stage_id, generic_profile(base, results[stage_id]), results, pier)
    return model


def _generic_seismic_stage(stage_id: str, stem: str, base: NduProfile, file_name: str,
                           direction: FrameDirection, source: LoadModelSource) -> StageSpec:
    ndu = _generic_ndu(stage_id, base)
    return StageSpec(stage_id, stem, ("0500", "0600"),
                     lambda pier, results: calculate_generic_seismic(pier, results["0500"], results["0600"],
                                                                     source.result(pier), direction),
                     lambda results, pier, path, pages: render_generic_seismic(results[stage_id], results["0600"],
                                                                               pier, path, pages),
                     (Export("jrsnap", file_name, lambda results, pier: write_ndu(ndu(results, pier)), metadata=_NDU),),
                     jrsnap_figures=JrsnapFigures("jrsnap", lambda results, pier: diagram_combinations(
                         ndu(results, pier))),
                     grid_documents=lambda results, pier, pages: generic_seismic_report.grid_documents(
                         results[stage_id], results["0600"], pier))


def _generic_nonlinear(stage: StageSpec, source_stage: str, base: NduProfile) -> StageSpec:
    """0711 / 0721 with the Aggre-SE project of the generic NDU of *source_stage*."""
    ndu = _generic_ndu(source_stage, base)
    analysis = stage.nonlinear_analysis
    assert analysis is not None and analysis.project is not None

    def build(results: Results, pier: PierInput) -> Callable[[str, Sequence[str]], bytes]:
        project = build_project(ndu(results, pier), pier)
        return lambda folder, names: write_project(project, databases(folder, names, len(project.cases)))

    # (the stage of a pile foundation is the train load's: a load model's stages have none of the piles', decision 94)
    return replace(stage, foundations={},
                   nonlinear_analysis=replace(analysis, project=replace(analysis.project, build=build)))


def _generic_cantilever(stem: str, longitudinal: str, transverse: str, source: LoadModelSource) -> StageSpec:
    def complete(basis: Any, files: Mapping[str, bytes], pier: PierInput, results: Results) -> Any:
        return complete_generic_cantilever(pier, results["0600"], basis,
                                           *_max_responses(files, longitudinal, transverse))

    return StageSpec("0900", stem, ("0600", longitudinal, transverse),
                     lambda pier, results: calculate_generic_cantilever(pier, results["0600"], source.result(pier)),
                     lambda results, pier, path, pages: render_generic_cantilever(results["0900"], pier, path),
                     complete=complete,
                     grid_documents=lambda results, pier, pages: generic_cantilever_report.grid_documents(
                         results["0900"], pier))


def _refuse_piles(stage: StageSpec) -> StageSpec:
    """*stage* of a load model's frame on a pile foundation: its frame is not built (the frame of a pile foundation is of
    the train load, decision 88), so the input is refused as the stage is calculated."""
    def refuse(pier: PierInput, results: Results) -> Any:
        raise InputError(f"下部構造.基礎形式: 荷重モデル（--addin）の{stage.id}は、{pier.substructure.foundation}では"
                         "計算できません（杭基礎の骨組は列車荷重だけです）")

    return replace(stage, calculate=refuse)


def stages_for(source: LoadModelSource) -> Registry:
    """The stages with the load model *source* (decision 70): 0600 the dead loads only, 0610 / 0620 / 0710 / 0720 /
    0900 from its result, 0711 / 0721 with the project of their generic NDU; every other stage is shared, reading the
    generic results as it reads the train path's."""
    generic = {
        "0600": StageSpec("0600", STAGES.get("0600").stem, (),
                          lambda pier, results: calculate_dead_reaction(pier),
                          lambda results, pier, path, pages: render_dead_reaction(results["0600"], pier, path),
                          grid_documents=lambda results, pier, pages: generic_reaction_report.grid_documents(
                              results["0600"], pier)),
        "0610": StageSpec("0610", STAGES.get("0610").stem, ("0500", "0600"),
                          lambda pier, results: calculate_generic_frame(pier, results["0500"], results["0600"],
                                                                        source.result(pier), FrameDirection.LONGITUDINAL,
                                                                        "0610"),
                          lambda results, pier, path, pages: render_generic_frame(results["0610"], results["0600"],
                                                                                  pier, path, pages),
                          (Export("frameweb", "線路方向.json", _frameweb("0610", build_frameweb_generic)),),
                          load_diagram="frameweb",
                          grid_documents=lambda results, pier, pages: generic_frame_report.grid_documents(
                              results["0610"], results["0600"], pier)),
        "0620": StageSpec("0620", STAGES.get("0620").stem, ("0500", "0600"),
                          lambda pier, results: calculate_generic_frame(pier, results["0500"], results["0600"],
                                                                        source.result(pier), FrameDirection.TRANSVERSE,
                                                                        "0620"),
                          lambda results, pier, path, pages: render_generic_frame(results["0620"], results["0600"],
                                                                                  pier, path, pages),
                          (Export("frameweb", "線路直角方向.json", _frameweb("0620", build_frameweb_generic)),),
                          load_diagram="frameweb",
                          grid_documents=lambda results, pier, pages: generic_frame_report.grid_documents(
                              results["0620"], results["0600"], pier)),
        "0710": _generic_seismic_stage("0710", STAGES.get("0710").stem, NDU_LONGITUDINAL, "線路方向.ndu",
                                       FrameDirection.LONGITUDINAL, source),
        "0711": _generic_nonlinear(STAGES.get("0711"), "0710", NDU_LONGITUDINAL),
        "0720": _generic_seismic_stage("0720", STAGES.get("0720").stem, NDU_TRANSVERSE, "線路直角方向.ndu",
                                       FrameDirection.TRANSVERSE, source),
        "0721": _generic_nonlinear(STAGES.get("0721"), "0720", NDU_TRANSVERSE),
        "0900": _generic_cantilever(STAGES.get("0900").stem, "0711", "0721", source),
    }
    for stage_id in ("0610", "0620"):
        generic[stage_id] = replace(generic[stage_id], foundations={
            foundation: _refuse_piles(generic[stage_id]) for foundation in choices.PILE_FOUNDATIONS})
    return Registry(tuple(generic.get(stage.id, stage) for stage in STAGES.stages), load_model=source)
