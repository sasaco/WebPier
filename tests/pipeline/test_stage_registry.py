"""The stage registry (ADR-0004): one table of stages, a generic dependency closure, and the stages of each 出力項目
(decision 72)."""

from dataclasses import replace
from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.inputs.outputs import OUTPUT_KEYS, uses
from webpier.pipeline.stages import (OUTPUT_STAGES, STAGES, Export, FrameAnalysis, NonlinearAnalysis, Project,
                                     Registry, SeismicCheck, SoilJrCalculation, StageSpec)


def spec(stage_id, *depends_on, exports=()):
    return StageSpec(stage_id, f"{stage_id}_名前", depends_on, lambda pier, results: stage_id,
                     lambda results, pier, path, pages: path, exports)


def export(kind, file_name):
    return Export(kind, file_name, lambda results, pier: b"")


FRAMEWEB = (export("frameweb", "x.json"),)
NDU = (export("jrsnap", "x.ndu"),)
PICKUPS = (("pik", "x.pik"), ("displacement", "x_変位量.csv"), ("reaction", "x_反力.csv"))


def analyzing(stage_id, *depends_on, source="A", files=PICKUPS, exports=()):
    """A stage without a report that analyzes the FrameWeb file of *source* (decision 46)."""
    return StageSpec(stage_id, f"{stage_id}_照査", depends_on, exports=exports,
                     frame_analysis=FrameAnalysis(source, "frameweb", files))


def solving(stage_id, *depends_on, source="A", folder="x_JRSNAP", kind="jrsnap", project=None, render=None,
            seismic_check=None):
    """A stage, without a report unless given one, that has JRSNAP analyze the NDU of *source* (decision 47)."""
    return StageSpec(stage_id, f"{stage_id}_解析", depends_on, render=render,
                     nonlinear_analysis=NonlinearAnalysis(source, "jrsnap", kind, folder, project),
                     seismic_check=seismic_check)


def one_item(*stages):
    """A registry of *stages* that all belong to one 出力項目, so no stage reads another item's."""
    return Registry(stages, outputs={"ground_model": tuple(dict.fromkeys(stage.id for stage in stages))})


PIK = SeismicCheck((("pik", "x_Aggre-SE.pik"), ("xlsx", "x_Aggre-SE.xlsx"), ("steps", "x_Aggre-SE_直接基礎.csv")))


def project(kind="aggrese", file_name="x.xml"):
    return Project(kind, file_name, lambda results, pier: lambda folder, names: b"")


def test_the_registry_lists_every_wired_stage_in_dependency_order():
    ids = STAGES.ids
    assert ids[:3] == ("0400", "0500", "0600")
    assert ids == ("0400", "0500", "0600", "0610", "0611", "0612", "0620", "0621", "0622", "0710", "0711", "0720", "0721",
                   "0800", "0810", "0820", "0900", "0910")
    for position, stage in enumerate(STAGES.stages):
        assert set(stage.depends_on) <= set(ids[:position])
        assert stage.stem.startswith(stage.id + "_")


def test_report_stems_are_the_japanese_stage_names():
    stems = {stage.id: stage.stem for stage in STAGES.stages}
    expected = {"0400": "0400_照査の前提", "0500": "0500_直接基礎", "0600": "0600_上部工反力", "0610": "0610_線路方向荷重",
                "0620": "0620_直角方向荷重", "0710": "0710_線路方向荷重", "0720": "0720_線路直角方向荷重",
                "0611": "0611_線路方向照査", "0621": "0621_直角方向照査", "0612": "0612_線路方向基礎",
                "0622": "0622_直角方向基礎", "0711": "0711_線路方向非線形解析",
                "0721": "0721_線路直角方向非線形解析", "0800": "0800_フーチング", "0810": "0810_線路方向フーチング照査",
                "0820": "0820_直角方向フーチング照査", "0900": "0900_片持ち梁", "0910": "0910_片持ち梁照査"}
    assert stems == {stage: expected[stage] for stage in stems}


def test_declared_dependencies_of_the_real_stages():
    depends = {stage.id: stage.depends_on for stage in STAGES.stages}
    expected = {"0400": (), "0500": (), "0600": (), "0610": ("0500", "0600"), "0620": ("0500", "0600"),
                "0710": ("0500", "0600"), "0720": ("0500", "0600"), "0611": ("0610",),
                "0621": ("0620",), "0612": ("0500", "0610"), "0622": ("0500", "0620"), "0711": ("0710",),
                "0721": ("0720",), "0800": ("0500", "0610", "0612", "0620", "0622", "0710", "0711", "0720", "0721"),
                "0810": ("0800",), "0820": ("0800",), "0900": ("0600", "0711", "0721"), "0910": ("0900",)}
    assert depends == {stage: expected[stage] for stage in depends}


def test_frameweb_is_written_for_the_non_seismic_frames_jrsnap_for_the_seismic_ones_and_the_dxf_for_0400():
    for stage in STAGES.stages:
        for item in stage.exports:
            assert item.kind in {"frameweb", "jrsnap", "dxf"}
            assert stage.id in {"frameweb": {"0610", "0620"}, "jrsnap": {"0710", "0720"}, "dxf": {"0400"}}[item.kind]
    files = {stage.id: [item.file_name for item in stage.exports if item.kind == "frameweb"] for stage in STAGES.stages}
    assert (files["0610"], files["0620"]) == (["線路方向.json"], ["線路直角方向.json"])
    ndu = {stage.id: [item.file_name for item in stage.exports if item.kind == "jrsnap"] for stage in STAGES.stages}
    assert (ndu["0710"], ndu["0720"]) == (["線路方向.ndu"], ["線路直角方向.ndu"])
    assert [item.file_name for item in STAGES.get("0400").exports] == ["配筋図.dxf"]  # the 配筋図 (decision 73)


def test_every_export_is_always_written():
    """Decision 42: an export is part of its stage; nothing is written only on request."""
    assert "opt_in" not in Export.__dataclass_fields__ and "opt_in" not in StageSpec.__dataclass_fields__
    assert not hasattr(STAGES, "opt_in_kinds") and not hasattr(StageSpec, "enabled_exports")


def test_each_output_item_makes_its_stages():
    """Decision 72: the stages of each 出力項目, in registry order; the input's six default items are the stages the
    switches used to leave out of all."""
    assert dict(STAGES.outputs) == {
        "detailing": ("0400",), "ground_model": ("0500",), "reactions": ("0600",), "longitudinal": ("0610",),
        "longitudinal_frame_analysis": ("0611", "0612"), "transverse": ("0620",),
        "transverse_frame_analysis": ("0621", "0622"), "longitudinal_seismic": ("0710",),
        "longitudinal_nonlinear_analysis": ("0711",), "transverse_seismic": ("0720",),
        "transverse_nonlinear_analysis": ("0721",), "footing": ("0800", "0810", "0820"),
        "cantilever": ("0900", "0910")}
    assert STAGES.outputs is OUTPUT_STAGES and tuple(STAGES.outputs) == OUTPUT_KEYS
    assert STAGES.selected(OUTPUT_KEYS) == STAGES.ids
    assert STAGES.selected(("ground_model", "reactions", "longitudinal", "transverse", "longitudinal_seismic",
                            "transverse_seismic")) == ("0500", "0600", "0610", "0620", "0710", "0720")
    assert STAGES.selected(("transverse_frame_analysis", "ground_model")) == ("0500", "0621", "0622")
    # Decision 78: the seismic items without 0610 / 0620.
    assert STAGES.selected(("ground_model", "reactions", "longitudinal_seismic", "transverse_seismic")) == (
        "0500", "0600", "0710", "0720")
    assert STAGES.selected(("detailing",)) == ("0400",)
    assert [STAGES.item(stage_id) for stage_id in ("0400", "0500", "0612", "0721", "0820", "0910")] == [
        "detailing", "ground_model", "longitudinal_frame_analysis", "transverse_nonlinear_analysis", "footing", "cantilever"]


def test_an_item_with_every_item_it_uses_has_every_stage_its_stages_read():
    """Decision 72: an item is chosen only with every item it uses, so the chosen stages are all a generation needs."""
    for key in OUTPUT_KEYS:
        chosen = STAGES.selected({key, *uses(key)})
        assert STAGES.closure(chosen) == chosen


def test_the_frame_analysis_stages_analyze_the_frameweb_files():
    """Decision 46: 0611 and 0621 publish the pickup files of their load stage's FrameWeb, and each the column
    section check by Capacita with that PIK (decision 48); 0612 and 0622 share that analysis for the 基礎の照査, which
    reads its reactions (decision 54)."""
    for stage_id, column in (("0612", "0611"), ("0622", "0621")):
        stage = STAGES.get(stage_id)
        assert stage.has_report and stage.complete is not None and stage.section_check is None
        assert stage.frame_analysis == STAGES.get(column).frame_analysis
    for stage_id, source, stem in (("0611", "0610", "線路方向"), ("0621", "0620", "線路直角方向")):
        stage = STAGES.get(stage_id)
        assert stage.has_report and (stage.exports, stage.load_diagram) == ((), "")
        assert (stage.section_check.kind, stage.section_check.file_name) == ("wdj", f"{stem}.wdj")
        assert stage.frame_analysis == FrameAnalysis(source, "frameweb", (
            ("pik", f"{stem}.pik"), ("displacement", f"{stem}_ピックアップ変位量.csv"),
            ("reaction", f"{stem}_ピックアップ反力.csv")))


def test_the_nonlinear_analysis_stages_analyze_the_ndu_files():
    """Decision 47: 0711 and 0721 publish the folder of the JRSNAP analysis of their seismic stage's NDU, and beside it
    the Aggre-SE project that reads it (decision 49); their report is Aggre-SE's, without a calculation of their own
    (decision 56)."""
    for stage_id, source, folder in (("0711", "0710", "線路方向_JRSNAP"), ("0721", "0720", "線路直角方向_JRSNAP")):
        stage = STAGES.get(stage_id)
        assert (stage.has_report, stage.calculate, stage.exports, stage.frame_analysis) == (True, None, (), None)
        stem = folder.removesuffix("_JRSNAP")
        assert stage.seismic_check == SeismicCheck((("pik", f"{stem}_Aggre-SE.pik"), ("xlsx", f"{stem}_Aggre-SE.xlsx"),
                                                    ("steps", f"{stem}_Aggre-SE_直接基礎.csv")))
        assert stage.section_check is None and stage.jrsnap_figures is None
        analysis = stage.nonlinear_analysis
        assert (analysis.stage, analysis.export, analysis.kind, analysis.folder) == (source, "jrsnap", "jrsnap", folder)
        project_file = folder.removesuffix("_JRSNAP") + ".xml"
        assert (analysis.project.kind, analysis.project.file_name) == ("aggrese", project_file)
        assert analysis.project.metadata == {"target": "Aggre-SE", "target_version": "5.3.0.1"}


def test_the_footing_stages_read_the_analyses_of_both_directions():
    """Decision 60: 0800 is prepared from 0500 and the frames of 0610・0620 and finished with the reactions of the
    analyses of 0612・0622 and the step tables of the seismic checks of 0711・0721, whose Cases are the combinations
    of 0710・0720 (decision 76); 0810・0820 have Capacita check the WDJ of their direction as given (no frame
    analysis of their own)."""
    for stage_id, stem, depends in (
            ("0800", "0800_フーチング", ("0500", "0610", "0612", "0620", "0622", "0710", "0711", "0720", "0721")),
            ("0810", "0810_線路方向フーチング照査", ("0800",)), ("0820", "0820_直角方向フーチング照査", ("0800",))):
        stage = STAGES.get(stage_id)
        assert (stage.stem, stage.depends_on, STAGES.item(stage_id)) == (stem, depends, "footing")
        assert stage.has_report and stage.complete is not None and stage.exports == ()
        assert stage.frame_analysis is None and stage.nonlinear_analysis is None and stage.seismic_check is None
    assert STAGES.get("0800").calculate is not None and STAGES.get("0800").section_check is None
    for stage_id, name in (("0810", "線路方向フーチング.wdj"), ("0820", "線路直角方向フーチング.wdj")):
        check = STAGES.get(stage_id).section_check
        assert (check.kind, check.file_name) == ("wdj", name) and STAGES.get(stage_id).calculate is None
    assert STAGES.closure(("0810",)) == ("0500", "0600", "0610", "0612", "0620", "0622", "0710", "0711", "0720",
                                         "0721", "0800", "0810")


def test_closure_adds_transitive_dependencies_in_registry_order():
    registry = one_item(spec("A"), spec("B"), spec("C", "A"), spec("D", "C"))
    assert registry.closure(("D",)) == ("A", "C", "D")
    assert registry.closure(("B", "C")) == ("A", "B", "C")
    assert registry.closure(registry.ids) == ("A", "B", "C", "D")


def test_a_stage_is_looked_up_by_its_id():
    registry = one_item(spec("A"), spec("B", "A"))
    assert registry.stage("B") is registry.get("B")
    with pytest.raises(InputError, match="計算段階が不正です: C"):
        registry.stage("C")


def test_a_stage_may_have_no_report():
    stage = analyzing("B", "A")
    assert (stage.calculate, stage.render, stage.has_report, stage.exports) == (None, None, False, ())
    assert spec("A").has_report


def test_the_stages_of_the_chosen_items_in_registry_order():
    """Decision 72: an item may have several stages; an item without stages chooses none."""
    registry = Registry((spec("A", exports=(*FRAMEWEB, *NDU)), analyzing("B", "A"), spec("C", "A"), solving("D", "A")),
                        outputs={"ground_model": ("A",), "longitudinal": ("C",), "longitudinal_frame_analysis": ("B",),
                                 "longitudinal_seismic": ("D",)})
    assert registry.selected(("ground_model",)) == ("A",)
    assert registry.selected(("longitudinal_seismic", "longitudinal_frame_analysis", "ground_model")) == ("A", "B", "D")
    assert registry.selected(("reactions",)) == ()
    assert [registry.item(stage) for stage in registry.ids] == [
        "ground_model", "longitudinal_frame_analysis", "longitudinal", "longitudinal_seismic"]


@pytest.mark.parametrize("outputs,message", [
    ({"ground_model": ("A",), "other": ("B",)}, "出力項目がありません: other"),
    ({"ground_model": ("A", "B"), "reactions": ("B",)}, "段階が複数の出力項目にあります"),
    ({"ground_model": ("A",)}, "Bの出力項目がありません"),
    ({"ground_model": ("A", "B", "X")}, "出力項目の段階がありません: X"),
    # B reads A, but reactions does not use ground_model (decision 72)
    ({"ground_model": ("A",), "reactions": ("B",)},
     "B（出力項目 reactions）はA（出力項目 ground_model）を読むので、reactions は ground_model を使う出力項目です"),
    # the other way round: a stage of an item that uses another may read it
    ({"reactions": ("A",), "longitudinal": ("B",)}, None),
])
def test_a_stage_reads_only_its_own_item_and_the_items_it_uses(outputs, message):
    stages = (spec("A"), spec("B", "A"))
    if message is None:
        assert Registry(stages, outputs=outputs).selected(("longitudinal",)) == ("B",)
    else:
        with pytest.raises(ValueError, match=message):
            Registry(stages, outputs=outputs)


def test_get_returns_the_spec():
    first = spec("A")
    assert one_item(first).get("A") is first


@pytest.mark.parametrize("stages,message", [
    ((), "段階がありません"),
    ((spec("A"), spec("A")), "段階が重複しています: A"),
    ((spec("A", "B"), spec("B")), "Aの依存段階Bが先に登録されていません"),
    ((spec("A", "A"),), "Aの依存段階Aが先に登録されていません"),
    ((StageSpec("A", "B_名前", (), lambda p, r: 0, lambda r, p, path, pages: path),), "AのファイルB_名前の名前"),
    ((spec("A", exports=(export("frameweb", "x.json"),)), spec("B", exports=(export("frameweb", "x.json"),))),
     "出力ファイル名が重複しています: x.json"),
    ((spec("A", exports=(export("frameweb", "x.json"), export("frameweb", "y.json"))),),
     "Aの出力の種類が重複しています: frameweb"),
    ((spec("A", exports=(export("Frame Web", "x.ndu"),)),), "出力の種類の名前が不正です: Frame Web"),
    ((spec("A", exports=(export("frameweb", "sub/x.json"),)),), "出力ファイル名が不正です: sub/x.json"),
    ((spec("A", exports=(export("frameweb", ".."),)),), r"出力ファイル名が不正です: \.\."),
    ((StageSpec("A", "A_a\\b", (), lambda p, r: 0, lambda r, p, path, pages: path),), r"AのファイルA_a\\bの名前"),
    ((StageSpec("A", "A_名前", (), None, lambda r, p, path, pages: path),), "Aの計算書には計算が必要です"),
    ((StageSpec("A", "A_名前", ()),), "Aには成果物がありません"),
    ((spec("A", exports=NDU), solving("B", "A", render=lambda r, p, path, pages: path, seismic_check=PIK)),
     "Bの耐震性能照査には静的非線形解析と Aggre-SE のプロジェクトが必要です"),
    ((spec("A", exports=NDU), solving("B", "A", project=project(), seismic_check=PIK)),
     "Bの耐震性能照査の計算書がありません"),
    ((spec("A", exports=NDU), solving("B", "A", project=project(), render=lambda r, p, path, pages: path,
                                      seismic_check=SeismicCheck((("pik", "x.ndu"), ("xlsx", "x.xlsx"),
                                                                  ("steps", "x.csv"))))),
     "出力ファイル名が重複しています: x.ndu"),
    ((spec("A", exports=NDU), solving("B", "A", project=project(), render=lambda r, p, path, pages: path,
                                      seismic_check=SeismicCheck((("pik", "y.pik"),)))),
     "Bの耐震性能照査の出力は pik・xlsx・steps です"),
    ((spec("A", exports=NDU), solving("B", "A", project=project(), render=lambda r, p, path, pages: path,
                                      seismic_check=SeismicCheck((("pik", "y.pik"), ("aggrese", "y.xlsx"))))),
     "Bの耐震性能照査の出力は pik・xlsx・steps です"),
    ((spec("A", exports=NDU), solving("B", "A", project=project(), render=lambda r, p, path, pages: path)),
     "Bの計算書には計算が必要です"),  # only Aggre-SE's report needs no calculation (decision 56)
    ((StageSpec("A", "A_名前", (), lambda p, r: 0, None, FRAMEWEB, load_diagram="frameweb"),),
     "Aの荷重図を差し込む計算書がありません"),
    ((spec("A", exports=FRAMEWEB), StageSpec("B", "B_名前", ("A",), lambda p, r: 0, lambda r, p, path, pages: path,
                                             load_diagram="pik",
                                             frame_analysis=FrameAnalysis("A", "frameweb", PICKUPS))),
     "Bの荷重図の出力pikがありません"),  # a load diagram draws one of the stage's own exports
    ((spec("A", exports=FRAMEWEB), spec("C"), analyzing("B", "C")), "Bが骨組解析するAが依存段階にありません"),
    ((spec("A"), analyzing("B", "A")), "Bが骨組解析するAの出力frameweb がありません"),
    ((spec("A", exports=FRAMEWEB), analyzing("B", "A", files=PICKUPS[:2])),
     "Bの骨組解析の出力は pik・displacement・reaction です"),
    ((spec("A", exports=FRAMEWEB), analyzing("B", "A", files=(*PICKUPS, ("pik", "y.pik")))),
     "Bの骨組解析の出力は pik・displacement・reaction です"),
    ((spec("A", exports=FRAMEWEB), analyzing("B", "A", exports=(export("pik", "p.json"),))),
     "Bの出力の種類が重複しています: pik"),
    ((spec("A", exports=FRAMEWEB), analyzing("B", "A", files=(("pik", "x.json"), *PICKUPS[1:]))),
     "出力ファイル名が重複しています: x.json"),
    ((spec("A", exports=FRAMEWEB), analyzing("B", "A", files=(("pik", "sub/x.pik"), *PICKUPS[1:]))),
     "出力ファイル名が不正です: sub/x.pik"),
    ((spec("A", exports=NDU), spec("C"), solving("B", "C")), "Bが静的非線形解析するAが依存段階にありません"),
    ((spec("A", exports=FRAMEWEB), solving("B", "A")), "Bが静的非線形解析するAの出力jrsnap がありません"),
    ((spec("A", exports=NDU), solving("B", "A", folder="x.ndu")), "出力ファイル名が重複しています: x.ndu"),
    ((spec("A", exports=NDU), solving("B", "A", folder="a/b")), "出力ファイル名が不正です: a/b"),
    ((spec("A", exports=NDU), solving("B", "A", kind="JRSNAP")), "出力の種類の名前が不正です: JRSNAP"),
    ((spec("A", exports=NDU), solving("B", "A", project=project(file_name="x.ndu"))), "出力ファイル名が重複しています: x.ndu"),
    ((spec("A", exports=NDU), solving("B", "A", project=project(kind="jrsnap"))), "Bの出力の種類が重複しています: jrsnap"),
    ((spec("A", exports=NDU), solving("B", "A", project=project(file_name="a/x.xml"))), "出力ファイル名が不正です: a/x.xml"),
    ((spec("A", exports=(*FRAMEWEB, *NDU)),
      StageSpec("B", "B_名前", ("A",), frame_analysis=FrameAnalysis("A", "frameweb", PICKUPS),
                nonlinear_analysis=NonlinearAnalysis("A", "jrsnap", "jrsnap", "x_JRSNAP"))),
     "Bは骨組解析と静的非線形解析の両方はできません"),
])
def test_an_inconsistent_registry_is_a_programming_error(stages, message):
    with pytest.raises(ValueError, match=message):
        one_item(*stages)


def test_stage_callables_are_kept_as_given():
    calculate = lambda pier, results: 1  # noqa: E731
    render = lambda results, pier, path, pages: Path(path)  # noqa: E731
    stage = StageSpec("A", "A_名前", (), calculate, render)
    assert (stage.calculate, stage.render, stage.exports) == (calculate, render, ())


# --- the stages of a pile foundation (decision 85) -------------------------------------------------------------------

def soil(kind="sdt", files=(("sdr", "x.sdr"), ("sdc", "x.sdc")), liquefaction=(("liquefiedsdr", "x(液状化時用).sdr"),)):
    return SoilJrCalculation(kind, files, liquefaction, lambda pier: False)


def calculating(stage_id="A", *, exports=(export("sdt", "x.sdt"),), soil_jr=None, **changes):
    """A stage whose .sdt SOIL-JR calculates: it has a report and finishes its result with SOIL-JR's files."""
    fields = {"complete": lambda result, files, pier, results: result, "soil_jr": soil() if soil_jr is None else soil_jr}
    return StageSpec(stage_id, f"{stage_id}_杭基礎", (), lambda pier, results: stage_id,
                     lambda results, pier, path, pages: path, exports, **{**fields, **changes})


def test_the_real_ground_stage_of_a_pile_foundation_replaces_the_direct_foundations():
    direct, piles = STAGES.get("0500"), STAGES.for_foundation("場所打ち杭")
    assert (direct.stem, direct.soil_jr) == ("0500_直接基礎", None)
    assert set(direct.foundations) == {"場所打ち杭", "鋼管ソイルセメント杭"}
    ground = piles.get("0500")
    assert ground.stem == "0500_杭基礎" and ground.id == "0500" and ground.foundations == {}
    assert [(item.kind, item.file_name) for item in ground.exports] == [("sdt", "杭基礎.sdt")]
    assert ground.soil_jr.export == "sdt" and ground.soil_jr.files == (("sdr", "杭基礎.sdr"), ("sdc", "杭基礎.sdc"))
    assert ground.soil_jr.liquefaction == (("liquefiedsdr", "杭基礎(液状化時用).sdr"),
                                          ("liquefiedsdc", "杭基礎(液状化時用).sdc"))
    assert ground.grid_documents is None  # SOIL-JR's report has no page of WebPier's
    assert [stage.id for stage in piles.stages] == list(STAGES.ids)
    assert STAGES.for_foundation("鋼管ソイルセメント杭").get("0500").stem == "0500_杭基礎"


@pytest.mark.parametrize("foundation", ["直接基礎", None, "鋼管杭"])
def test_the_registry_of_a_foundation_without_stages_of_its_own_is_the_registry(foundation):
    assert STAGES.for_foundation(foundation) is STAGES


def test_a_load_model_and_the_items_stay_with_the_registry_of_a_foundation():
    registry = Registry((replace(spec("A"), foundations={"場所打ち杭": spec("A")}),), outputs={"ground_model": ("A",)})
    assert registry.for_foundation("場所打ち杭").outputs == registry.outputs
    assert registry.for_foundation("場所打ち杭").load_model is registry.load_model


@pytest.mark.parametrize("foundations,message", [
    ({"直接基礎": spec("A")}, "Aの直接基礎の段階が不正です"),
    ({"場所打ち杭": spec("B")}, "Aの場所打ち杭の段階が不正です"),
    ({"場所打ち杭": replace(spec("A"), foundations={"場所打ち杭": spec("A")})}, "Aの場所打ち杭の段階が不正です"),
])
def test_the_stage_of_a_foundation_is_a_stage_of_a_pile_type_with_the_same_id_and_none_of_its_own(foundations, message):
    with pytest.raises(ValueError, match=message):
        Registry((replace(spec("A"), foundations=foundations),), outputs={"ground_model": ("A",)})


def test_the_registry_of_a_foundation_is_checked_as_a_registry_is():
    broken = StageSpec("A", "名前の違い", (), lambda pier, results: None, lambda results, pier, path, pages: path)
    with pytest.raises(ValueError, match="Aのファイル名前の違いの名前は「A_」で始まる必要があります"):
        Registry((replace(spec("A"), foundations={"場所打ち杭": broken}),), outputs={"ground_model": ("A",)})


def test_a_stage_that_soil_jr_calculates_has_its_export_a_report_and_a_completion():
    assert one_item(calculating()).get("A").soil_jr.export == "sdt"
    with pytest.raises(ValueError, match="Aが SOIL-JR で計算する出力sdtがありません"):
        one_item(calculating(exports=(export("jrsnap", "x.ndu"),)))
    with pytest.raises(ValueError, match="Aの結果を仕上げるには計算書が必要です"):
        one_item(StageSpec("A", "A_杭基礎", (), lambda pier, results: 1, None, (export("sdt", "x.sdt"),),
                           soil_jr=soil(), complete=lambda result, files, pier, results: result))
    with pytest.raises(ValueError, match="Aの SOIL-JR の結果の仕上げがありません"):
        one_item(calculating(complete=None))


def test_a_stage_cannot_have_soil_jr_calculate_and_an_analysis_run():
    both = StageSpec("A", "A_杭基礎", ("S",), lambda pier, results: 1, lambda results, pier, path, pages: path,
                     (export("sdt", "x.sdt"),), soil_jr=soil(), complete=lambda result, files, pier, results: result,
                     frame_analysis=FrameAnalysis("S", "frameweb", PICKUPS))
    with pytest.raises(ValueError, match="Aは SOIL-JR の計算と解析の両方はできません"):
        Registry((spec("S", exports=FRAMEWEB), both), outputs={"ground_model": ("S", "A")})


def test_the_files_soil_jr_returns_are_checked_like_any_output():
    with pytest.raises(ValueError, match="出力ファイル名が重複しています: x.sdt"):
        one_item(calculating(soil_jr=soil(files=(("sdr", "x.sdt"),))))
    with pytest.raises(ValueError, match="出力の種類が重複しています: sdr"):
        one_item(calculating(soil_jr=soil(files=(("sdr", "x.sdr"), ("sdr", "y.sdr")))))
    with pytest.raises(ValueError, match="出力の種類の名前が不正です: sdr-liquefied"):
        one_item(calculating(soil_jr=soil(liquefaction=(("sdr-liquefied", "x.sdl"),))))


# --- the stages that wait for SOIL-JR (decision 88) ----------------------------------------------------------------------


def waiting(stage_id="B", *, after=("A",), **changes):
    return replace(spec(stage_id, "A", exports=FRAMEWEB), after=after, **changes)


def test_a_stage_that_waits_names_a_dependency_that_soil_jr_calculates():
    registry = one_item(calculating(), waiting())
    assert registry.get("B").after == ("A",) and registry.deferred(("A", "B")) == ("B",)
    assert registry.deferred(("A",)) == ()


@pytest.mark.parametrize("stages, message", [
    ((calculating(), waiting(after=("C",))), "Bが待つCは、依存段階の SOIL-JR で計算する段階である必要があります"),
    ((spec("A"), waiting()), "Bが待つAは、依存段階の SOIL-JR で計算する段階である必要があります"),
    ((calculating(), waiting(complete=lambda result, files, pier, results: result)),
     "Bは待つ段階があるので、仕上げと解析は持てません"),
])
def test_a_stage_that_waits_is_checked(stages, message):
    with pytest.raises(ValueError, match=message):
        one_item(*stages)


def test_the_frames_of_a_pile_foundation_wait_for_the_ground_and_the_direct_foundations_do_not():
    for foundation in ("場所打ち杭", "鋼管ソイルセメント杭"):
        piles = STAGES.for_foundation(foundation)
        assert [stage.id for stage in piles.stages if stage.after] == ["0610", "0620"]
        assert piles.get("0610").after == piles.get("0620").after == ("0500",) and piles.get("0610").foundations == {}
        assert piles.deferred(piles.closure(("0620",))) == ("0620",)
    assert not any(stage.after for stage in STAGES.stages)
    assert set(STAGES.get("0610").foundations) == set(STAGES.get("0620").foundations) == {"場所打ち杭", "鋼管ソイルセメント杭"}


def test_a_stage_that_reads_a_waiting_stage_waits_too():
    registry = one_item(calculating(), waiting(), spec("C", "B"), spec("D"))
    assert [registry.waits(stage_id) for stage_id in ("A", "B", "C", "D")] == [False, True, True, False]


def test_the_frame_analyses_of_a_pile_foundation_wait_and_have_their_own_stage():
    for foundation in ("場所打ち杭", "鋼管ソイルセメント杭"):
        piles = STAGES.for_foundation(foundation)
        assert [stage_id for stage_id in piles.ids if piles.waits(stage_id)] == [
            "0610", "0611", "0612", "0620", "0621", "0622", "0800", "0810", "0820"]
        assert piles.get("0612").depends_on == ("0500", "0610") and piles.get("0612").complete is not None
        assert piles.get("0612").frame_analysis.files == STAGES.get("0612").frame_analysis.files  # shared with 0611
        assert piles.get("0612").stem == "0612_線路方向基礎" and piles.get("0622").stem == "0622_直角方向基礎"
    assert not any(STAGES.waits(stage_id) for stage_id in STAGES.ids)
    assert set(STAGES.get("0612").foundations) == set(STAGES.get("0622").foundations) == {"場所打ち杭", "鋼管ソイルセメント杭"}
