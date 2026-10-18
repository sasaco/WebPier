"""The stage registry (ADR-0004): one table of stages, a generic dependency closure."""

from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.pipeline.stages import (FRAME_ANALYSIS, NONLINEAR_ANALYSIS, STAGES, Export, FrameAnalysis,
                                     NonlinearAnalysis, Project, Registry, StageSpec)


def spec(stage_id, *depends_on, exports=()):
    return StageSpec(stage_id, f"{stage_id}_名前", depends_on, lambda pier, results: stage_id,
                     lambda results, pier, path: path, exports)


def export(kind, file_name):
    return Export(kind, file_name, lambda results, pier: b"")


FRAMEWEB = (export("frameweb", "x.json"),)
NDU = (export("jrsnap", "x.ndu"),)
PICKUPS = (("pik", "x.pik"), ("displacement", "x_変位量.csv"), ("reaction", "x_反力.csv"))


def analyzing(stage_id, *depends_on, source="A", files=PICKUPS, opt_in=FRAME_ANALYSIS, exports=()):
    """A stage without a report that analyzes the FrameWeb file of *source* (decision 46)."""
    return StageSpec(stage_id, f"{stage_id}_照査", depends_on, exports=exports, opt_in=opt_in,
                     frame_analysis=FrameAnalysis(source, "frameweb", files))


def solving(stage_id, *depends_on, source="A", folder="x_JRSNAP", opt_in=NONLINEAR_ANALYSIS, kind="jrsnap",
            project=None):
    """A stage without a report that has JRSNAP analyze the NDU of *source* (decision 47)."""
    return StageSpec(stage_id, f"{stage_id}_解析", depends_on, opt_in=opt_in,
                     nonlinear_analysis=NonlinearAnalysis(source, "jrsnap", kind, folder, project))


def project(kind="aggrese", file_name="x.xml"):
    return Project(kind, file_name, lambda results, pier: lambda folder, names: b"")


def test_the_registry_lists_every_wired_stage_in_dependency_order():
    ids = STAGES.ids
    assert ids[:2] == ("0500", "0600")
    assert ids == ("0500", "0600", "0610", "0611", "0620", "0621", "0710", "0711", "0720", "0721")
    for position, stage in enumerate(STAGES.stages):
        assert set(stage.depends_on) <= set(ids[:position])
        assert stage.stem.startswith(stage.id + "_")


def test_report_stems_are_the_japanese_stage_names():
    stems = {stage.id: stage.stem for stage in STAGES.stages}
    expected = {"0500": "0500_直接基礎", "0600": "0600_上部工反力", "0610": "0610_線路方向荷重",
                "0620": "0620_直角方向荷重", "0710": "0710_線路方向荷重", "0720": "0720_線路直角方向荷重",
                "0611": "0611_線路方向照査", "0621": "0621_直角方向照査", "0711": "0711_線路方向非線形解析",
                "0721": "0721_線路直角方向非線形解析"}
    assert stems == {stage: expected[stage] for stage in stems}


def test_declared_dependencies_of_the_real_stages():
    depends = {stage.id: stage.depends_on for stage in STAGES.stages}
    expected = {"0500": (), "0600": (), "0610": ("0500", "0600"), "0620": ("0500", "0600"),
                "0710": ("0500", "0600", "0610"), "0720": ("0500", "0600", "0620"), "0611": ("0610",),
                "0621": ("0620",), "0711": ("0710",), "0721": ("0720",)}
    assert depends == {stage: expected[stage] for stage in depends}


def test_frameweb_is_written_for_the_non_seismic_frames_and_jrsnap_for_the_seismic_ones():
    for stage in STAGES.stages:
        for item in stage.exports:
            assert item.kind in {"frameweb", "jrsnap"}
            assert stage.id in ({"0610", "0620"} if item.kind == "frameweb" else {"0710", "0720"})
    files = {stage.id: [item.file_name for item in stage.exports if item.kind == "frameweb"] for stage in STAGES.stages}
    assert (files["0610"], files["0620"]) == (["線路方向.json"], ["線路直角方向.json"])
    ndu = {stage.id: [item.file_name for item in stage.exports if item.kind == "jrsnap"] for stage in STAGES.stages}
    assert (ndu["0710"], ndu["0720"]) == (["線路方向.ndu"], ["線路直角方向.ndu"])


def test_every_export_is_always_written():
    """Decision 42: an export is part of its stage; nothing is written only on request."""
    assert "opt_in" not in Export.__dataclass_fields__
    assert not hasattr(STAGES, "opt_in_kinds") and not hasattr(StageSpec, "enabled_exports")


def test_the_frame_analysis_stages_are_opt_in_and_analyze_the_frameweb_files():
    """Decision 46: 0611 and 0621 publish the pickup files of their load stage's FrameWeb, and each the column
    section check by Capacita with that PIK (decision 48)."""
    assert STAGES.opt_in(FRAME_ANALYSIS) == ("0611", "0621")
    assert STAGES.select("all") == ("0500", "0600", "0610", "0620", "0710", "0720")
    assert STAGES.select("all", switches=frozenset({FRAME_ANALYSIS})) == (
        "0500", "0600", "0610", "0611", "0620", "0621", "0710", "0720")
    for stage_id, source, stem in (("0611", "0610", "線路方向"), ("0621", "0620", "線路直角方向")):
        stage = STAGES.get(stage_id)
        assert stage.has_report and (stage.exports, stage.load_diagram) == ((), "")
        assert (stage.section_check.kind, stage.section_check.file_name) == ("wdj", f"{stem}.wdj")
        assert stage.frame_analysis == FrameAnalysis(source, "frameweb", (
            ("pik", f"{stem}.pik"), ("displacement", f"{stem}_ピックアップ変位量.csv"),
            ("reaction", f"{stem}_ピックアップ反力.csv")))


def test_the_nonlinear_analysis_stages_are_opt_in_and_analyze_the_ndu_files():
    """Decision 47: 0711 and 0721 have no report; they publish the folder of the JRSNAP analysis of their seismic
    stage's NDU, and beside it the Aggre-SE project that reads it (decision 49)."""
    assert STAGES.opt_in(NONLINEAR_ANALYSIS) == ("0711", "0721")
    assert STAGES.select("all", switches=frozenset({NONLINEAR_ANALYSIS})) == (
        "0500", "0600", "0610", "0620", "0710", "0711", "0720", "0721")
    assert STAGES.select("all", switches=frozenset({FRAME_ANALYSIS, NONLINEAR_ANALYSIS})) == STAGES.ids
    for stage_id, source, folder in (("0711", "0710", "線路方向_JRSNAP"), ("0721", "0720", "線路直角方向_JRSNAP")):
        stage = STAGES.get(stage_id)
        assert (stage.has_report, stage.calculate, stage.exports, stage.frame_analysis) == (False, None, (), None)
        analysis = stage.nonlinear_analysis
        assert (analysis.stage, analysis.export, analysis.kind, analysis.folder) == (source, "jrsnap", "jrsnap", folder)
        project_file = folder.removesuffix("_JRSNAP") + ".xml"
        assert (analysis.project.kind, analysis.project.file_name) == ("aggrese", project_file)
        assert analysis.project.metadata == {"target": "Aggre-SE", "target_version": "5.3.0.1",
                                             "app_read_verified": False, "seismic_check_run": False}


def test_closure_adds_transitive_dependencies_in_registry_order():
    registry = Registry((spec("A"), spec("B"), spec("C", "A"), spec("D", "C")))
    assert registry.closure(("D",)) == ("A", "C", "D")
    assert registry.closure(("B", "C")) == ("A", "B", "C")
    assert registry.closure(registry.ids) == ("A", "B", "C", "D")


def test_select_all_or_one_stage():
    registry = Registry((spec("A"), spec("B", "A")))
    assert registry.select("all") == ("A", "B")
    assert registry.select("B") == ("B",)
    with pytest.raises(InputError, match="計算段階が不正です: C"):
        registry.select("C")
    assert registry.choices == ("A", "B", "all")


def test_a_stage_may_have_no_report():
    stage = analyzing("B", "A")
    assert (stage.calculate, stage.render, stage.has_report, stage.exports) == (None, None, False, ())
    assert spec("A").has_report and not spec("A").opt_in


def test_all_leaves_out_the_opt_in_stages_unless_they_are_asked_for():
    """Decisions 46, 47: each switch adds its own opt-in stages to all; any of them may be chosen directly."""
    registry = Registry((spec("A", exports=(*FRAMEWEB, *NDU)), analyzing("B", "A"), spec("C", "A"), solving("D", "A")))
    assert (registry.opt_in(FRAME_ANALYSIS), registry.opt_in(NONLINEAR_ANALYSIS)) == (("B",), ("D",))
    assert registry.select("all") == ("A", "C")
    assert registry.select("all", switches=frozenset({FRAME_ANALYSIS})) == ("A", "B", "C")
    assert registry.select("all", switches=frozenset({NONLINEAR_ANALYSIS})) == ("A", "C", "D")
    assert registry.select("all", switches=frozenset({FRAME_ANALYSIS, NONLINEAR_ANALYSIS})) == ("A", "B", "C", "D")
    assert registry.select("B") == ("B",) and registry.select("D") == ("D",)
    assert registry.closure(("B",)) == ("A", "B")
    with pytest.raises(InputError, match="--frame-analysis は --stage all と使います（選択式の段階 B は --stage で直接選べます）"):
        registry.select("A", switches=frozenset({FRAME_ANALYSIS}))
    with pytest.raises(InputError, match="--frame-analysis --nonlinear-analysis は --stage all と使います（選択式の段階 B・D は"):
        registry.select("C", switches=frozenset({NONLINEAR_ANALYSIS, FRAME_ANALYSIS}))
    with pytest.raises(InputError, match="選択式のスイッチが不正です: other"):
        registry.select("all", switches=frozenset({"other"}))


def test_get_returns_the_spec():
    first = spec("A")
    assert Registry((first,)).get("A") is first


@pytest.mark.parametrize("stages,message", [
    ((), "段階がありません"),
    ((spec("A"), spec("A")), "段階が重複しています: A"),
    ((spec("A", "B"), spec("B")), "Aの依存段階Bが先に登録されていません"),
    ((spec("A", "A"),), "Aの依存段階Aが先に登録されていません"),
    ((spec("all"),), "段階の名前にallは使えません"),
    ((StageSpec("A", "B_名前", (), lambda p, r: 0, lambda r, p, path: path),), "AのファイルB_名前の名前"),
    ((spec("A", exports=(export("frameweb", "x.json"),)), spec("B", exports=(export("frameweb", "x.json"),))),
     "出力ファイル名が重複しています: x.json"),
    ((spec("A", exports=(export("frameweb", "x.json"), export("frameweb", "y.json"))),),
     "Aの出力の種類が重複しています: frameweb"),
    ((spec("A", exports=(export("Frame Web", "x.ndu"),)),), "出力の種類の名前が不正です: Frame Web"),
    ((spec("A", exports=(export("frameweb", "sub/x.json"),)),), "出力ファイル名が不正です: sub/x.json"),
    ((spec("A", exports=(export("frameweb", ".."),)),), r"出力ファイル名が不正です: \.\."),
    ((StageSpec("A", "A_a\\b", (), lambda p, r: 0, lambda r, p, path: path),), r"AのファイルA_a\\bの名前"),
    ((StageSpec("A", "A_名前", (), None, lambda r, p, path: path),), "Aの計算書には計算が必要です"),
    ((StageSpec("A", "A_名前", ()),), "Aには成果物がありません"),
    ((StageSpec("A", "A_名前", (), lambda p, r: 0, None, FRAMEWEB, load_diagram="frameweb"),),
     "Aの荷重図を差し込む計算書がありません"),
    ((spec("A", exports=FRAMEWEB), StageSpec("B", "B_名前", ("A",), lambda p, r: 0, lambda r, p, path: path,
                                             opt_in=FRAME_ANALYSIS, load_diagram="pik",
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
    ((spec("A", exports=FRAMEWEB), analyzing("B", "A", opt_in="")), "Bは骨組解析するので選択式（frame_analysis）の段階です"),
    ((spec("A", exports=FRAMEWEB), analyzing("B", "A", opt_in=NONLINEAR_ANALYSIS)),
     "Bは骨組解析するので選択式（frame_analysis）の段階です"),
    ((spec("A", exports=FRAMEWEB), analyzing("B", "A"), spec("C", "B")),
     "Cは選択式の段階Bに依存するので、同じスイッチ（frame_analysis）の選択式の段階です"),
    ((spec("A", exports=(*FRAMEWEB, *NDU)), analyzing("B", "A"),
      StageSpec("C", "C_名前", ("B",), lambda p, r: 0, lambda r, p, path: path, opt_in=NONLINEAR_ANALYSIS)),
     "Cは選択式の段階Bに依存するので、同じスイッチ（frame_analysis）の選択式の段階です"),
    ((StageSpec("A", "A_名前", (), lambda p, r: 0, lambda r, p, path: path, opt_in="other"),),
     "Aの選択式のスイッチotherがありません"),
    ((spec("A", exports=NDU), solving("B", "A", opt_in=FRAME_ANALYSIS)),
     "Bは静的非線形解析するので選択式（nonlinear_analysis）の段階です"),
    ((spec("A", exports=NDU), spec("C"), solving("B", "C")), "Bが静的非線形解析するAが依存段階にありません"),
    ((spec("A", exports=FRAMEWEB), solving("B", "A")), "Bが静的非線形解析するAの出力jrsnap がありません"),
    ((spec("A", exports=NDU), solving("B", "A", folder="x.ndu")), "出力ファイル名が重複しています: x.ndu"),
    ((spec("A", exports=NDU), solving("B", "A", folder="a/b")), "出力ファイル名が不正です: a/b"),
    ((spec("A", exports=NDU), solving("B", "A", kind="JRSNAP")), "出力の種類の名前が不正です: JRSNAP"),
    ((spec("A", exports=NDU), solving("B", "A", project=project(file_name="x.ndu"))), "出力ファイル名が重複しています: x.ndu"),
    ((spec("A", exports=NDU), solving("B", "A", project=project(kind="jrsnap"))), "Bの出力の種類が重複しています: jrsnap"),
    ((spec("A", exports=NDU), solving("B", "A", project=project(file_name="a/x.xml"))), "出力ファイル名が不正です: a/x.xml"),
    ((spec("A", exports=(*FRAMEWEB, *NDU)),
      StageSpec("B", "B_名前", ("A",), opt_in=FRAME_ANALYSIS, frame_analysis=FrameAnalysis("A", "frameweb", PICKUPS),
                nonlinear_analysis=NonlinearAnalysis("A", "jrsnap", "jrsnap", "x_JRSNAP"))),
     "Bは骨組解析と静的非線形解析の両方はできません"),
])
def test_an_inconsistent_registry_is_a_programming_error(stages, message):
    with pytest.raises(ValueError, match=message):
        Registry(stages)


def test_stage_callables_are_kept_as_given():
    calculate = lambda pier, results: 1  # noqa: E731
    render = lambda results, pier, path: Path(path)  # noqa: E731
    stage = StageSpec("A", "A_名前", (), calculate, render)
    assert (stage.calculate, stage.render, stage.exports) == (calculate, render, ())
