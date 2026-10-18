"""A stage with a static nonlinear analysis (decision 47): JRSNAP analyzes the NDU of its dependency, every returned
file is published under JRSNAP's name in one folder that replaces the old one whole, one sidecar beside the folder
names the analyzed bytes and each file, the stage is left out of all unless asked for, and a failing analysis
publishes nothing.

The expected files are those the stand-in runner documents (tests/fixtures/jrsnap/fake_runner.py), written out here
from the analyzed bytes."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

import pytest

from pipeline_support import Recorder, copy_input, tree
from webpier.core.errors import InputError
from webpier.core.integrity import canonical_sha256
from webpier.pipeline import generate, jrsnap, publication
from webpier.pipeline.generate import GenerationError, GenerationOptions, planned
from webpier.export.aggrese import databases
from webpier.pipeline.stages import (NONLINEAR_ANALYSIS, Export, NonlinearAnalysis, Project, Registry,
                                     StageSpec)

NDU = b"Virsion=5.2.3.S.4\r\n"
FOLDER = "model_JRSNAP"
CASE = "model(Case1_ρm10_αf1_正向)"


def registry(recorder: Recorder) -> Registry:
    return Registry((
        StageSpec("A", "A_基礎", (), recorder.calculate("A"), recorder.render("A")),
        StageSpec("C", "C_地震", ("A",), recorder.calculate("C"), recorder.render("C"),
                  (Export("jrsnap", "model.ndu", recorder.export("C", NDU)),)),
        StageSpec("E", "E_解析", ("C",), opt_in=NONLINEAR_ANALYSIS,
                  nonlinear_analysis=NonlinearAnalysis("C", "jrsnap", "jrsnap", FOLDER)),
    ))


def expected() -> dict[str, bytes]:
    """The stand-in's files of an analysis of NDU as model.ndu, by name."""
    digest = hashlib.sha256(NDU).hexdigest()
    return {f"{CASE}.{suffix}": f"FAKE {word} model.ndu {digest}\n".encode("utf-8")
            for suffix, word in (("ndt", "NDT"), ("DB1", "DB1"), ("LOG", "LOG"), ("OUT", "OUT"))}


def sidecar(options: GenerationOptions, name: str) -> dict:
    return json.loads((Path(options.post_dir) / f"{name}.provenance.json").read_text(encoding="utf-8"))


def folder(options: GenerationOptions) -> dict[str, bytes]:
    return tree(Path(options.post_dir) / FOLDER)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    monkeypatch.setattr(jrsnap, "ENV_FILE", tmp_path / ".env")
    recorder = Recorder()
    options = GenerationOptions(copy_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post")
    return options, recorder, registry(recorder)


def with_(options: GenerationOptions, **changes) -> GenerationOptions:
    return GenerationOptions(**{**options.__dict__, **changes})


def test_all_leaves_the_analysis_out_and_needs_no_runner(env, monkeypatch: pytest.MonkeyPatch):
    options, _, stages = env
    monkeypatch.setenv(jrsnap.RUNNER_KEY, "")
    generate.generate(options, registry=stages)
    assert sorted(tree(Path(options.post_dir))) == ["model.ndu", "model.ndu.provenance.json"]


def test_the_analysis_publishes_every_returned_file_in_one_folder(env):
    options, recorder, stages = env
    generation = generate.generate(with_(options, nonlinear_analysis=True), registry=stages)
    assert generation.stages == ("A", "C", "E")
    post = tree(Path(options.post_dir))
    assert sorted(post) == sorted(["model.ndu", "model.ndu.provenance.json", f"{FOLDER}.provenance.json",
                                   *(f"{FOLDER}/{name}" for name in expected())])
    assert folder(options) == expected()
    assert recorder.actions("export") == ["C"]  # built once: the staged NDU is the NDU analyzed
    assert [(artifact.role, artifact.folder) for artifact in generation.artifacts if artifact.role.startswith("E")] == [
        ("E.jrsnap", True), ("E.jrsnap.provenance", False)]
    assert planned(with_(options, nonlinear_analysis=True), registry=stages) == generation.artifacts


def test_the_sidecar_of_the_folder_names_the_ndu_each_file_and_what_jrsnap_reported(env):
    options, _, stages = env
    generate.generate(with_(options, nonlinear_analysis=True), registry=stages)
    document = sidecar(options, FOLDER)
    files = {name: hashlib.sha256(content).hexdigest() for name, content in expected().items()}
    assert {key: document[key] for key in ("stage", "export", "file", "sha256", "selected_stages")} == {
        "stage": "E", "export": "jrsnap", "file": FOLDER, "sha256": canonical_sha256(files),
        "selected_stages": ["A", "C", "E"]}
    assert document["files"] == [{"file": name, "bytes": len(expected()[name]), "sha256": files[name]}
                                 for name in sorted(files)]
    analysis = document["nonlinear_analysis"]
    assert {key: analysis[key] for key in ("engine", "engine_version", "engineering_status", "ndu")} == {
        "engine": "jrsnap", "engine_version": "fake-1", "engineering_status": "not_checked",
        "ndu": {"stage": "C", "export": "jrsnap", "file": "model.ndu", "sha256": hashlib.sha256(NDU).hexdigest()}}
    assert analysis["runner_summary"]["jrsnap"] == {"product": "5.2-L03", "assemblyVersion": "5.2.3.1"}
    assert analysis["runner_summary"]["analysis"]["dialogs"] == [{"title": "耐力と変形性能の自動算定", "answer": "実行(&R)"}]
    assert analysis["messages"] == [{"level": "warning", "code": "LOG_WARNING", "text": "FAKE WARNING"}]
    assert {item["role"]: item["sha256"] for item in document["artifacts"]}["E.jrsnap"] == canonical_sha256(files)
    assert "metadata" not in document and "frame_analysis" not in document
    assert "nonlinear_analysis" not in sidecar(options, "model.ndu")


def test_the_folder_is_replaced_whole(env):
    options, _, stages = env
    old = Path(options.post_dir) / FOLDER
    (old / "sub").mkdir(parents=True)
    (old / "old(Case9).ndt").write_bytes(b"old")
    (old / "sub" / "note.txt").write_bytes(b"old note")
    generate.generate(with_(options, nonlinear_analysis=True, overwrite=True), registry=stages)
    assert folder(options) == expected()  # nothing of the old folder is left
    assert sorted(path.name for path in Path(options.post_dir).iterdir()) == sorted(
        ["model.ndu", "model.ndu.provenance.json", FOLDER, f"{FOLDER}.provenance.json"])


def test_a_generation_without_the_analysis_keeps_the_old_folder(env):
    options, _, stages = env
    generate.generate(with_(options, nonlinear_analysis=True), registry=stages)
    generate.generate(with_(options, overwrite=True), registry=stages)
    assert folder(options) == expected()


def test_a_stage_chosen_alone_is_analyzed_with_its_dependencies_calculated(env):
    options, recorder, stages = env
    generate.generate(with_(options, stage="E"), registry=stages)
    assert not Path(options.output_dir).exists()
    assert sorted(tree(Path(options.post_dir))) == sorted(
        [f"{FOLDER}.provenance.json", *(f"{FOLDER}/{name}" for name in expected())])
    assert recorder.actions("calculate") == ["A", "C"] and recorder.actions("render") == []
    # model.ndu is not of this generation: the sidecar's SHA256 is what binds the analysis to it.
    assert sidecar(options, FOLDER)["nonlinear_analysis"]["ndu"]["sha256"] == hashlib.sha256(NDU).hexdigest()


def test_an_old_folder_is_not_replaced_without_overwrite(env):
    options, _, stages = env
    (Path(options.post_dir) / FOLDER).mkdir(parents=True)
    with pytest.raises(FileExistsError, match="出力が既にあります"):
        generate.generate(with_(options, stage="E"), registry=stages)


def test_a_failing_analysis_stops_before_any_report_and_publishes_nothing(env, monkeypatch: pytest.MonkeyPatch):
    options, recorder, stages = env
    monkeypatch.setenv("FAKE_JRSNAP", "fail")
    with pytest.raises(GenerationError, match="model.ndu を JRSNAP で静的非線形解析できません: ANALYSIS_FAILED"):
        generate.generate(with_(options, nonlinear_analysis=True), registry=stages)
    assert recorder.actions("render") == [] and not Path(options.post_dir).exists()


def test_without_a_runner_nothing_is_read_or_published(env, monkeypatch: pytest.MonkeyPatch):
    options, _, stages = env
    monkeypatch.setenv(jrsnap.RUNNER_KEY, "")
    read = []
    monkeypatch.setattr(generate, "parse_input", lambda data: read.append(data))
    with pytest.raises(GenerationError, match="JRSNAP の runner が設定されていません"):
        generate.generate(with_(options, nonlinear_analysis=True), registry=stages)
    assert read == [] and not Path(options.post_dir).exists()


def test_a_changed_file_of_the_folder_rolls_the_publication_back(env, monkeypatch: pytest.MonkeyPatch):
    options, _, stages = env
    generate.generate(with_(options, nonlinear_analysis=True), registry=stages)
    before = tree(Path(options.post_dir))
    original = generate.publish_outputs

    def tampering(pairs, staging, overwrite, *, final_validator, folders):
        def validator():
            (Path(options.post_dir) / FOLDER / f"{CASE}.OUT").write_bytes(b"changed")
            final_validator()
        return original(pairs, staging, overwrite, final_validator=validator, folders=folders)
    monkeypatch.setattr(generate, "publish_outputs", tampering)
    with pytest.raises(GenerationError, match="公開した成果物が一致しません: E.jrsnap"):
        generate.generate(with_(options, nonlinear_analysis=True, overwrite=True), registry=stages)
    assert tree(Path(options.post_dir)) == before


def test_a_new_folder_is_removed_when_the_publication_rolls_back(env, monkeypatch: pytest.MonkeyPatch):
    options, _, stages = env
    original = generate.publish_outputs

    def failing(pairs, staging, overwrite, *, final_validator, folders):
        def validator():
            raise GenerationError("stop")
        return original(pairs, staging, overwrite, final_validator=validator, folders=folders)
    monkeypatch.setattr(generate, "publish_outputs", failing)
    with pytest.raises(GenerationError, match="stop"):
        generate.generate(with_(options, stage="E"), registry=stages)
    assert not Path(options.post_dir).exists()  # the folders the generation created are removed as well


def test_a_folder_that_cannot_be_removed_on_rollback_keeps_the_backups(env, monkeypatch: pytest.MonkeyPatch):
    options, _, stages = env
    generate.generate(with_(options, stage="E"), registry=stages)
    original, remove = generate.publish_outputs, publication.shutil.rmtree

    def failing(pairs, staging, overwrite, *, final_validator, folders):
        def validator():
            raise GenerationError("stop")
        return original(pairs, staging, overwrite, final_validator=validator, folders=folders)

    def locked(path, *args, **kwargs):
        if Path(path).name == FOLDER:
            raise OSError("locked")
        return remove(path, *args, **kwargs)
    monkeypatch.setattr(generate, "publish_outputs", failing)
    monkeypatch.setattr(publication.shutil, "rmtree", locked)
    with pytest.raises(publication.RecoveryError, match=f"{FOLDER}: locked"):
        generate.generate(with_(options, stage="E", overwrite=True), registry=stages)
    backups = list(Path(options.post_dir).glob(f".webpier-*/{FOLDER}.backup"))
    assert len(backups) == 1 and tree(backups[0]) == expected()  # the old folder is kept for manual recovery


@pytest.mark.parametrize("make,error,message", [
    (lambda path: path.write_bytes(b"x"), OSError, "フォルダー以外は出力フォルダーとして置き換えられません"),
    (lambda path: (path.mkdir(), (path / "a.ndt").write_bytes(b"x"), os.chmod(path / "a.ndt", stat.S_IREAD)),
     PermissionError, "出力フォルダーに読取専用のファイルがあります"),
])
def test_a_destination_that_cannot_be_replaced_as_a_folder_is_refused(env, make, error, message):
    options, _, stages = env
    target = Path(options.post_dir) / FOLDER
    target.parent.mkdir(parents=True)
    make(target)
    try:
        with pytest.raises(error, match=message):
            generate.generate(with_(options, stage="E", overwrite=True), registry=stages)
    finally:
        for path in target.rglob("*") if target.is_dir() else ():
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


def test_a_link_in_place_of_or_inside_the_folder_is_refused(env, tmp_path: Path):
    import _winapi
    options, _, stages = env
    target = Path(options.post_dir) / FOLDER
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    target.parent.mkdir(parents=True)
    _winapi.CreateJunction(str(elsewhere), str(target))
    with pytest.raises(OSError, match="フォルダー以外は出力フォルダーとして置き換えられません"):
        generate.generate(with_(options, stage="E", overwrite=True), registry=stages)
    target.rmdir()
    target.mkdir()
    _winapi.CreateJunction(str(elsewhere), str(target / "link"))
    with pytest.raises(OSError, match="出力フォルダーに通常のファイル・フォルダー以外があります"):
        generate.generate(with_(options, stage="E", overwrite=True), registry=stages)


def test_the_input_may_not_be_inside_the_folder(env, tmp_path: Path):
    options, _, stages = env
    inside = Path(options.post_dir) / FOLDER / "input.json"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(Path(options.input_path).read_bytes())
    with pytest.raises(OSError, match="入力ファイルと出力ファイルを同じパスにはできません"):
        generate.generate(with_(options, input_path=inside, stage="E", overwrite=True), registry=stages)


def projecting(recorder: Recorder, cases: int = 1) -> Registry:
    """The registry with an Aggre-SE project beside the folder (decision 49), naming the DB1 of *cases* Cases."""
    def build(results, pier):
        recorder.log.append(("project", "C", tuple(results)))
        return lambda folder, names: "\r\n".join(databases(folder, names, cases)).encode("cp932")
    project = Project("aggrese", "model.xml", build, {"target": "Aggre-SE"})
    return Registry((*registry(recorder).stages[:2],
                     StageSpec("E", "E_解析", ("C",), opt_in=NONLINEAR_ANALYSIS,
                               nonlinear_analysis=NonlinearAnalysis("C", "jrsnap", "jrsnap", FOLDER, project))))


def test_the_project_names_the_databases_of_the_folder_and_is_published_beside_it(env):
    options, recorder, _ = env
    generation = generate.generate(with_(options, nonlinear_analysis=True), registry=projecting(recorder))
    post = tree(Path(options.post_dir))
    assert post["model.xml"] == f"{FOLDER}/{CASE}.DB1".encode("cp932")
    assert ("project", "C", ("A", "C")) in recorder.log  # the analyzed stage's results, before the analysis
    assert [artifact.role for artifact in generation.artifacts if artifact.role.startswith("E")] == [
        "E.jrsnap", "E.aggrese", "E.jrsnap.provenance", "E.aggrese.provenance"]
    document = sidecar(options, "model.xml")
    files = {name: hashlib.sha256(content).hexdigest() for name, content in expected().items()}
    assert {key: document[key] for key in ("stage", "export", "file", "sha256", "metadata", "aggrese_project")} == {
        "stage": "E", "export": "aggrese", "file": "model.xml",
        "sha256": hashlib.sha256(post["model.xml"]).hexdigest(),
        "metadata": {"target": "Aggre-SE"},
        "aggrese_project": {"jrsnap": {"stage": "E", "export": "jrsnap", "file": FOLDER,
                                       "sha256": canonical_sha256(files)}}}
    assert "nonlinear_analysis" not in document


def test_a_project_without_the_databases_of_every_case_publishes_nothing(env):
    options, recorder, _ = env
    with pytest.raises(GenerationError, match=r"model.xml を作れません: JRSNAP の結果に Case1〜2 の DB1"):
        generate.generate(with_(options, nonlinear_analysis=True), registry=projecting(recorder, cases=2))
    assert not Path(options.post_dir).exists()


def test_the_project_bytes_are_those_a_generation_writes(env):
    """The acceptance rebuilds its candidate this way (decision 49); a stage without a project has none."""
    options, recorder, stages = env
    generate.generate(with_(options, nonlinear_analysis=True), registry=projecting(recorder))
    names = list(expected())
    assert generate.project_bytes(None, "E", names, registry=projecting(recorder)) == tree(
        Path(options.post_dir))["model.xml"]
    for stage in ("C", "E"):
        with pytest.raises(InputError, match=f"{stage}に Aggre-SE のプロジェクトはありません"):
            generate.project_bytes(None, stage, names, registry=stages)
