"""A stage with a load diagram (decision 44): its staged FrameWeb file is drawn by the FEMPython runner, the
report takes the pages, the sidecar names the runner, and without a working runner nothing is published."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from pipeline_support import Recorder, copy_input, tree
from webpier.pipeline import fempython, generate
from webpier.pipeline.generate import GenerationError, GenerationOptions
from webpier.pipeline.stages import Export, Registry, StageSpec
from webpier.reporting.stages.insertion import LOAD_DIAGRAM

FRAMEWEB = json.dumps({"dimension": 2, "load": {"1": {}, "2": {}, "3": {}}}).encode()


def registry(recorder: Recorder, pages: list) -> Registry:
    def render(results, pier, path, drawn):
        pages.append(drawn)
        Path(path).write_bytes(b"%PDF B")
        return path

    return Registry((
        StageSpec("A", "A_基礎", (), recorder.calculate("A"), recorder.render("A")),
        StageSpec("B", "B_荷重", ("A",), recorder.calculate("B"), render,
                  (Export("frameweb", "frame.json", recorder.export("B", FRAMEWEB)),), load_diagram="frameweb"),
    ))


def published(options: GenerationOptions) -> list[Path]:
    return [path for directory in (options.output_dir, options.post_dir) if Path(directory).exists()
            for path in Path(directory).iterdir()]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    monkeypatch.setattr(fempython, "ENV_FILE", tmp_path / ".env")
    pages: list = []
    options = GenerationOptions(copy_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post")
    return options, registry(Recorder(), pages), pages


def test_the_report_takes_the_pages_drawn_from_the_staged_file(env):
    options, stages, pages = env
    generate.generate(options, registry=stages)
    (drawn,) = pages  # stage B only, its pages by name
    assert sorted(drawn) == [LOAD_DIAGRAM]
    assert [page.extract_text().strip().partition(" CASES ")[2]
            for page in PdfReader(BytesIO(drawn[LOAD_DIAGRAM])).pages] == ["1 2", "3"]
    sidecar = json.loads((Path(options.post_dir) / "frame.json.provenance.json").read_text(encoding="utf-8"))
    assert sidecar["load_diagram"] == {"report": "B.pdf", "engine": "fempython", "engine_version": "fake-1"}


def test_a_stage_without_a_load_diagram_renders_as_before(env):
    options, stages, pages = env
    generate.generate(GenerationOptions(options.input_path, options.output_dir, options.post_dir, stage="A"),
                      registry=stages)
    assert pages == []
    assert sorted(tree(Path(options.output_dir))) == ["A_基礎.json", "A_基礎.pdf"]


@pytest.mark.parametrize("setting,message", [("", "runner が設定されていません"), ("C:/missing/runner.exe", "ありません")])
def test_without_a_runner_nothing_is_read_or_published(env, monkeypatch: pytest.MonkeyPatch, setting, message):
    options, stages, pages = env
    monkeypatch.setenv(fempython.RUNNER_KEY, setting)
    read = []
    monkeypatch.setattr(generate, "parse_input", lambda data: read.append(data))
    with pytest.raises(GenerationError, match=message):
        generate.generate(options, registry=stages)
    assert read == [] and pages == [] and published(options) == []


def test_a_runner_that_fails_publishes_nothing(env, monkeypatch: pytest.MonkeyPatch):
    options, stages, pages = env
    monkeypatch.setenv("FAKE_FEMPYTHON", "fail")
    with pytest.raises(GenerationError, match="frame.json の荷重図を FEMPython で描けません"):
        generate.generate(options, registry=stages)
    assert pages == [] and published(options) == []


def test_a_load_diagram_must_name_an_export_of_its_stage():
    recorder = Recorder()
    with pytest.raises(ValueError, match="Aの荷重図の出力frameweb"):
        Registry((StageSpec("A", "A_x", (), recorder.calculate("A"), recorder.render("A"), load_diagram="frameweb"),))
