"""The stage registry (ADR-0004): one table of stages, a generic dependency closure."""

from pathlib import Path

import pytest

from webpier.core.errors import InputError
from webpier.pipeline.stages import STAGES, Export, Registry, StageSpec


def spec(stage_id, *depends_on, exports=()):
    return StageSpec(stage_id, f"{stage_id}_名前", depends_on, lambda pier, results: stage_id,
                     lambda results, pier, path: path, exports)


def export(kind, file_name, *, opt_in=False):
    return Export(kind, file_name, lambda results, pier: b"", opt_in=opt_in)


def test_the_registry_lists_every_wired_stage_in_dependency_order():
    ids = STAGES.ids
    assert ids[:2] == ("0500", "0600")
    assert set(ids) <= {"0500", "0600", "0610", "0620", "0710", "0720"}
    for position, stage in enumerate(STAGES.stages):
        assert set(stage.depends_on) <= set(ids[:position])
        assert stage.stem.startswith(stage.id + "_")


def test_report_stems_are_the_japanese_stage_names():
    stems = {stage.id: stage.stem for stage in STAGES.stages}
    expected = {"0500": "0500_直接基礎", "0600": "0600_上部工反力", "0610": "0610_線路方向荷重",
                "0620": "0620_直角方向荷重", "0710": "0710_線路方向荷重", "0720": "0720_線路直角方向荷重"}
    assert stems == {stage: expected[stage] for stage in stems}


def test_declared_dependencies_of_the_real_stages():
    depends = {stage.id: stage.depends_on for stage in STAGES.stages}
    expected = {"0500": (), "0600": (), "0610": ("0500", "0600"), "0620": ("0500", "0600"),
                "0710": ("0500", "0600", "0610"), "0720": ("0500", "0600", "0620")}
    assert depends == {stage: expected[stage] for stage in depends}


def test_frameweb_is_written_for_the_non_seismic_frames_and_jrsnap_only_on_request():
    for stage in STAGES.stages:
        for item in stage.exports:
            assert (item.kind, item.opt_in) in {("frameweb", False), ("jrsnap", True)}
            assert stage.id in ({"0610", "0620"} if item.kind == "frameweb" else {"0710", "0720"})
    files = {stage.id: [item.file_name for item in stage.exports if item.kind == "frameweb"] for stage in STAGES.stages}
    assert (files["0610"], files["0620"]) == (["frameWebForJS.json"], ["線路直角方向.json"])


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


def test_get_returns_the_spec():
    first = spec("A")
    assert Registry((first,)).get("A") is first


def test_opt_in_kinds_are_collected_once():
    registry = Registry((spec("A", exports=(export("frameweb", "a.json"),)),
                         spec("B", exports=(export("jrsnap", "b.ndu", opt_in=True),)),
                         spec("C", exports=(export("jrsnap", "c.ndu", opt_in=True),))))
    assert registry.opt_in_kinds == ("jrsnap",)


def test_enabled_exports_skip_unrequested_opt_in_exports():
    always, optional = export("frameweb", "a.json"), export("jrsnap", "a.ndu", opt_in=True)
    stage = spec("A", exports=(always, optional))
    assert stage.enabled_exports(frozenset()) == (always,)
    assert stage.enabled_exports(frozenset({"jrsnap"})) == (always, optional)


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
    ((spec("A", exports=(export("jrsnap", "x.ndu", opt_in=True),)),
      spec("B", exports=(export("jrsnap", "y.ndu"),))), "jrsnapは要求したときだけの出力と常の出力を兼ねられません"),
    ((spec("A", exports=(export("Frame Web", "x.ndu"),)),), "出力の種類の名前が不正です: Frame Web"),
    ((spec("A", exports=(export("frameweb", "sub/x.json"),)),), "出力ファイル名が不正です: sub/x.json"),
    ((spec("A", exports=(export("frameweb", ".."),)),), r"出力ファイル名が不正です: \.\."),
    ((StageSpec("A", "A_a\\b", (), lambda p, r: 0, lambda r, p, path: path),), r"AのファイルA_a\\bの名前"),
])
def test_an_inconsistent_registry_is_a_programming_error(stages, message):
    with pytest.raises(ValueError, match=message):
        Registry(stages)


def test_stage_callables_are_kept_as_given():
    calculate = lambda pier, results: 1  # noqa: E731
    render = lambda results, pier, path: Path(path)  # noqa: E731
    stage = StageSpec("A", "A_名前", (), calculate, render)
    assert (stage.calculate, stage.render, stage.exports) == (calculate, render, ())
