"""The stage registry (ADR-0004): one table of stages, a generic dependency closure."""

from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.pipeline.stages import STAGES, Export, FrameAnalysis, Registry, StageSpec


def spec(stage_id, *depends_on, exports=()):
    return StageSpec(stage_id, f"{stage_id}_名前", depends_on, lambda pier, results: stage_id,
                     lambda results, pier, path: path, exports)


def export(kind, file_name):
    return Export(kind, file_name, lambda results, pier: b"")


FRAMEWEB = (export("frameweb", "x.json"),)
PICKUPS = (("pik", "x.pik"), ("displacement", "x_変位量.csv"), ("reaction", "x_反力.csv"))


def analyzing(stage_id, *depends_on, source="A", files=PICKUPS, opt_in=True, exports=()):
    """A stage without a report that analyzes the FrameWeb file of *source* (decision 46)."""
    return StageSpec(stage_id, f"{stage_id}_照査", depends_on, exports=exports, opt_in=opt_in,
                     frame_analysis=FrameAnalysis(source, "frameweb", files))


def test_the_registry_lists_every_wired_stage_in_dependency_order():
    ids = STAGES.ids
    assert ids[:2] == ("0500", "0600")
    assert ids == ("0500", "0600", "0610", "0611", "0620", "0621", "0710", "0720")
    for position, stage in enumerate(STAGES.stages):
        assert set(stage.depends_on) <= set(ids[:position])
        assert stage.stem.startswith(stage.id + "_")


def test_report_stems_are_the_japanese_stage_names():
    stems = {stage.id: stage.stem for stage in STAGES.stages}
    expected = {"0500": "0500_直接基礎", "0600": "0600_上部工反力", "0610": "0610_線路方向荷重",
                "0620": "0620_直角方向荷重", "0710": "0710_線路方向荷重", "0720": "0720_線路直角方向荷重",
                "0611": "0611_線路方向照査", "0621": "0621_直角方向照査"}
    assert stems == {stage: expected[stage] for stage in stems}


def test_declared_dependencies_of_the_real_stages():
    depends = {stage.id: stage.depends_on for stage in STAGES.stages}
    expected = {"0500": (), "0600": (), "0610": ("0500", "0600"), "0620": ("0500", "0600"),
                "0710": ("0500", "0600", "0610"), "0720": ("0500", "0600", "0620"), "0611": ("0610",),
                "0621": ("0620",)}
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
    """Decision 46: 0611 and 0621 have no report; they publish the pickup files of their load stage's FrameWeb."""
    assert STAGES.opt_in == ("0611", "0621")
    assert STAGES.select("all") == ("0500", "0600", "0610", "0620", "0710", "0720")
    for stage_id, source, stem in (("0611", "0610", "線路方向"), ("0621", "0620", "線路直角方向")):
        stage = STAGES.get(stage_id)
        assert (stage.has_report, stage.calculate, stage.exports, stage.load_diagram) == (False, None, (), "")
        assert stage.frame_analysis == FrameAnalysis(source, "frameweb", (
            ("pik", f"{stem}.pik"), ("displacement", f"{stem}_ピックアップ変位量.csv"),
            ("reaction", f"{stem}_ピックアップ反力.csv")))


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
    """Decision 46: the frame analysis stages are added to all by --frame-analysis, or chosen directly."""
    registry = Registry((spec("A", exports=FRAMEWEB), analyzing("B", "A"), spec("C", "A")))
    assert registry.opt_in == ("B",)
    assert registry.select("all") == ("A", "C")
    assert registry.select("all", opt_in=True) == ("A", "B", "C")
    assert registry.select("B") == ("B",)
    assert registry.closure(("B",)) == ("A", "B")
    with pytest.raises(InputError, match="--frame-analysis は --stage all と使います（選択式の段階 B は --stage で直接選べます）"):
        registry.select("A", opt_in=True)


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
                                             opt_in=True, load_diagram="pik",
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
    ((spec("A", exports=FRAMEWEB), analyzing("B", "A", opt_in=False)), "Bは骨組解析するので選択式（opt_in）の段階です"),
    ((spec("A", exports=FRAMEWEB), analyzing("B", "A"), spec("C", "B")),
     "Cは選択式の段階Bに依存するので選択式（opt_in）の段階です"),
])
def test_an_inconsistent_registry_is_a_programming_error(stages, message):
    with pytest.raises(ValueError, match=message):
        Registry(stages)


def test_stage_callables_are_kept_as_given():
    calculate = lambda pier, results: 1  # noqa: E731
    render = lambda results, pier, path: Path(path)  # noqa: E731
    stage = StageSpec("A", "A_名前", (), calculate, render)
    assert (stage.calculate, stage.render, stage.exports) == (calculate, render, ())
