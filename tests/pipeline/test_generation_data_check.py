"""A stage with a データ確認図 (decision 50): JRSNAP draws it from the NDU the generation stages, the report takes the
pages, the NDU's sidecar names the runner, and without a working runner nothing is published."""

from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path

import pymupdf
import pytest
from pypdf import PdfReader

from pipeline_support import Recorder, copy_input, tree
from webpier.pipeline import fempython, generate, jrsnap
from webpier.pipeline.generate import GenerationError, GenerationOptions
from webpier.pipeline.stages import STAGES, Export, Registry, StageSpec

NDU = b"Virsion=5.2.3.S.4\r\nSNAPConbNum=2\r\n"


def registry(recorder: Recorder, pages: list) -> Registry:
    def render(results, pier, path, *drawn):
        pages.append(drawn)
        Path(path).write_bytes(b"%PDF B")
        return path

    return Registry((
        StageSpec("A", "A_基礎", (), recorder.calculate("A"), recorder.render("A")),
        StageSpec("B", "B_荷重", ("A",), recorder.calculate("B"), render,
                  (Export("jrsnap", "pier.ndu", recorder.export("B", NDU)),), data_check="jrsnap"),
    ))


def published(options: GenerationOptions) -> list[Path]:
    return [path for directory in (options.output_dir, options.post_dir) if Path(directory).exists()
            for path in Path(directory).iterdir()]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    monkeypatch.setattr(jrsnap, "ENV_FILE", tmp_path / ".env")
    pages: list = []
    options = GenerationOptions(copy_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post")
    return options, registry(Recorder(), pages), pages


def test_the_report_takes_the_pages_drawn_from_the_staged_ndu(env):
    options, stages, pages = env
    generate.generate(options, registry=stages)
    ((drawn,),) = pages  # stage B only, and the pages after its path
    digest = hashlib.sha256(NDU).hexdigest()
    assert [page.extract_text().strip() for page in PdfReader(BytesIO(drawn)).pages] == [
        f"FAKE DATA CHECK {figure} {digest[:16]}" for figure in jrsnap.DATA_CHECK_FIGURES]
    assert (Path(options.post_dir) / "pier.ndu").read_bytes() == NDU
    sidecar = json.loads((Path(options.post_dir) / "pier.ndu.provenance.json").read_text(encoding="utf-8"))
    assert sidecar["data_check"] == {
        "report": "B.pdf", "engine": "jrsnap", "engine_version": "fake-1", "case": 1,
        "figures": ["nonlinear-numbers", "section-numbers", "element-table", "section-detail", "node-springs"],
        "runner_summary": {
            "jrsnap": {"product": "5.2-L03", "assemblyVersion": "5.2.3.1"},
            "case": {"case": 1, "ndt": "pier(Case1_ρm10_αf1_正向).ndt", "sha256": digest},
            "figures": [{"figure": figure, "file": f"{figure}.pdf", "pages": 1}
                        for figure in jrsnap.DATA_CHECK_FIGURES]}}


def test_a_stage_without_a_data_check_needs_no_jrsnap_runner(env, monkeypatch: pytest.MonkeyPatch):
    options, stages, pages = env
    monkeypatch.setenv(jrsnap.RUNNER_KEY, "")
    generate.generate(GenerationOptions(options.input_path, options.output_dir, options.post_dir, stage="A"),
                      registry=stages)
    assert pages == []
    assert sorted(tree(Path(options.output_dir))) == ["A_基礎.json", "A_基礎.pdf"]


@pytest.mark.parametrize("setting,message", [("", "JRSNAP の runner が設定されていません"),
                                             ("C:/missing/runner.exe", "ありません")])
def test_without_a_runner_nothing_is_read_or_published(env, monkeypatch: pytest.MonkeyPatch, setting, message):
    options, stages, pages = env
    monkeypatch.setenv(jrsnap.RUNNER_KEY, setting)
    read = []
    monkeypatch.setattr(generate, "parse_input", lambda data: read.append(data))
    with pytest.raises(GenerationError, match=message):
        generate.generate(options, registry=stages)
    assert read == [] and pages == [] and published(options) == []


def test_a_runner_that_fails_publishes_nothing(env, monkeypatch: pytest.MonkeyPatch):
    options, stages, pages = env
    monkeypatch.setenv("FAKE_JRSNAP_DATA_CHECK", "fail")
    with pytest.raises(GenerationError, match="pier.ndu のデータ確認図を JRSNAP で描けません: UNKNOWN_DIALOG"):
        generate.generate(options, registry=stages)
    assert pages == [] and published(options) == []


@pytest.mark.parametrize("spec,message", [
    (dict(data_check="jrsnap"), "Aのデータ確認図の出力jrsnapがありません"),
    (dict(exports=(Export("jrsnap", "a.ndu", lambda results, pier: b""),), data_check="jrsnap", render=None),
     "Aのデータ確認図を差し込む計算書がありません"),
    (dict(exports=(Export("jrsnap", "a.ndu", lambda results, pier: b""),
                   Export("frameweb", "a.json", lambda results, pier: b"")), data_check="jrsnap",
          load_diagram="frameweb"), "Aに荷重図とデータ確認図の両方は差し込めません"),
])
def test_a_data_check_must_name_an_export_of_a_stage_with_a_report(spec, message):
    recorder = Recorder()
    fields = {"render": recorder.render("A"), **spec}
    with pytest.raises(ValueError, match=message):
        Registry((StageSpec("A", "A_x", (), recorder.calculate("A"), **fields),))


def test_0710_and_0720_take_the_data_check_of_their_ndu():
    assert [(stage.id, stage.data_check) for stage in STAGES.stages if stage.data_check] == [
        ("0710", "jrsnap"), ("0720", "jrsnap")]


def test_the_0710_report_has_the_data_check_of_the_published_ndu_between_10_1_and_10_2(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The real registry, with the stand-in runners: JRSNAP's pages are those of the NDU published with the report."""
    monkeypatch.setattr(fempython, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(jrsnap, "ENV_FILE", tmp_path / ".env")
    options = GenerationOptions(copy_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post",
                                stage="0710")
    generate.generate(options)
    digest = hashlib.sha256((Path(options.post_dir) / "線路方向.ndu").read_bytes()).hexdigest()
    with pymupdf.open(Path(options.output_dir) / "0710_線路方向荷重.pdf") as pdf:
        texts = [page.get_text() for page in pdf]
    marked = [index for index, text in enumerate(texts) if "FAKE DATA CHECK" in text]
    assert [texts[index].split()[3:5] for index in marked] == [
        [figure, digest[:16]] for figure in jrsnap.DATA_CHECK_FIGURES]
    assert marked == list(range(marked[0], marked[0] + 5))
    assert "10.1 検討モデル" in texts[0] and all("10.2" not in text for text in texts[:marked[0]])
    assert texts[marked[-1] + 1].lstrip().startswith("10.2 作用の計算")
