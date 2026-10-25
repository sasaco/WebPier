"""A stage with JRSNAP's figures (decisions 50, 51): JRSNAP draws the データ確認図 and the 荷重図 from the NDU the
generation stages, each basic case from the combination the stage names for it; the report takes the pages by name,
the NDU's sidecar names the runner, the combinations and what the runner reports, and without a working runner nothing
is published."""

from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path

import pymupdf
import pytest
from pypdf import PdfReader

from pipeline_support import CURRENT, Recorder, choose, copy_input, tree
from webpier.core.errors import InputError
from webpier.core.integrity import load_json
from webpier.inputs import parse_input
from webpier.pipeline import fempython, generate, jrsnap
from webpier.pipeline.generate import GenerationError, GenerationOptions, figure_cases
from webpier.pipeline.stages import STAGES, AlsoFigures, Export, JrsnapFigures, Registry, StageSpec
from webpier.reporting.stages.insertion import DATA_CHECK, LOAD_DIAGRAM

# The shape of 0720: two combinations, nine basic cases, CASE-6 from combination 2 (tests/fixtures/jrsnap).
NDU = b"Virsion=5.2.3.S.4\r\nLoadNum=9\r\nSNAPConbNum=2\r\n"
CASES = tuple((case, 2 if case == 6 else 1) for case in range(1, 10))
DIGEST = hashlib.sha256(NDU).hexdigest()


def registry(recorder: Recorder, pages: list) -> Registry:
    def render(results, pier, path, drawn):
        pages.append(drawn)
        Path(path).write_bytes(b"%PDF B")
        return path

    return Registry((
        StageSpec("A", "A_基礎", (), recorder.calculate("A"), recorder.render("A")),
        StageSpec("B", "B_荷重", ("A",), recorder.calculate("B"), render,
                  (Export("jrsnap", "pier.ndu", recorder.export("B", NDU)),),
                  jrsnap_figures=JrsnapFigures("jrsnap", lambda results, pier: CASES)),
    ), outputs={"ground_model": ("A",), "longitudinal": ("B",)})


def published(options: GenerationOptions) -> list[Path]:
    return [path for directory in (options.output_dir, options.post_dir) if Path(directory).exists()
            for path in Path(directory).iterdir()]


def texts(pdf: bytes) -> list[str]:
    return [page.extract_text().strip() for page in PdfReader(BytesIO(pdf)).pages]


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})
    monkeypatch.setattr(jrsnap, "ENV_FILE", tmp_path / ".env")
    pages: list = []
    options = GenerationOptions(copy_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post")
    return options, registry(Recorder(), pages), pages


@pytest.fixture(scope="module")
def pier():
    return parse_input(load_json(CURRENT.read_bytes()))


def test_the_report_takes_the_pages_drawn_from_the_staged_ndu_by_name(env):
    options, stages, pages = env
    generate.generate(options, registry=stages)
    (drawn,) = pages  # stage B only
    assert sorted(drawn) == [DATA_CHECK, LOAD_DIAGRAM]
    assert texts(drawn[DATA_CHECK]) == [f"FAKE DATA CHECK {figure} {DIGEST[:16]}"
                                        for figure in jrsnap.DATA_CHECK_FIGURES]
    assert texts(drawn[LOAD_DIAGRAM]) == [f"FAKE LOAD DIAGRAM COMB {combination} CASE {case} {DIGEST[:16]}"
                                          for case, combination in CASES]
    assert (Path(options.post_dir) / "pier.ndu").read_bytes() == NDU


def test_the_ndu_sidecar_records_the_figures_and_the_runner_summary(env):
    options, stages, pages = env
    generate.generate(options, registry=stages)
    sidecar = json.loads((Path(options.post_dir) / "pier.ndu.provenance.json").read_text(encoding="utf-8"))
    assert "data_check" not in sidecar and "load_diagram" not in sidecar
    record = sidecar["jrsnap_figures"]
    assert {key: value for key, value in record.items() if key != "runner_summary"} == {
        "report": "B.pdf", "engine": "jrsnap", "engine_version": "fake-1",
        "data_check": {"combination": 1, "figures": ["nonlinear-numbers", "section-numbers", "element-table",
                                                     "section-detail", "node-springs"]},
        "load_diagram": [{"case": case, "combination": combination} for case, combination in CASES]}
    summary = record["runner_summary"]
    assert summary["jrsnap"] == {"product": "5.2-L03", "assemblyVersion": "5.2.3.1"}
    assert summary["dataCheck"] == {
        "combination": 1, "ndt": "pier(Case1_ρm10_αf1_正向).ndt", "sha256": DIGEST,
        "figures": [{"figure": figure, "file": f"{figure}.pdf", "pages": 1} for figure in jrsnap.DATA_CHECK_FIGURES]}
    assert summary["loadDiagram"] == [
        {"combination": combination, "ndt": f"pier(Case{combination}_ρm10_αf1_正向).ndt", "sha256": DIGEST,
         "file": f"load-diagram-{combination}.pdf",
         "pages": [{"page": case, "case": case, "title": f"CASE-{case} FAKE"} for case in range(1, 10)]}
        for combination in (1, 2)]


def test_a_stage_without_figures_needs_no_jrsnap_runner_and_takes_no_pages(env, monkeypatch: pytest.MonkeyPatch):
    options, stages, pages = env
    monkeypatch.setenv(jrsnap.RUNNER_KEY, "")
    rendered = []

    def render(results, pier, path, drawn):
        rendered.append(drawn)
        Path(path).write_bytes(b"%PDF A")

    plain = Registry((StageSpec("A", "A_基礎", (), Recorder().calculate("A"), render),),
                     outputs={"ground_model": ("A",)})
    choose(Path(options.input_path), "ground_model")
    generate.generate(options, registry=plain)
    assert rendered == [{}]
    generate.generate(GenerationOptions(options.input_path, options.output_dir, options.post_dir, overwrite=True),
                      registry=stages)
    assert pages == []
    assert sorted(tree(Path(options.output_dir))) == ["A_基礎.json", "A_基礎.pdf"]


@pytest.mark.parametrize("setting,message", [("", "JRSNAP の runner が設定されていません"),
                                             ("C:/missing/runner.exe", "ありません")])
def test_without_a_runner_nothing_is_calculated_or_published(env, monkeypatch: pytest.MonkeyPatch, setting, message):
    """The input is read for its 出力項目 (decision 72); the runners are looked up before anything is calculated."""
    options, _, pages = env
    recorder = Recorder()
    monkeypatch.setenv(jrsnap.RUNNER_KEY, setting)
    with pytest.raises(GenerationError, match=message):
        generate.generate(options, registry=registry(recorder, pages))
    assert recorder.log == [] and pages == [] and published(options) == []


@pytest.mark.parametrize("mode,message", [("fail", "UNKNOWN_DIALOG"), ("pages", r"load-diagram-2\.pdf のページが")])
def test_a_runner_that_fails_publishes_nothing(env, monkeypatch: pytest.MonkeyPatch, mode, message):
    options, stages, pages = env
    monkeypatch.setenv("FAKE_JRSNAP_FIGURES", mode)
    with pytest.raises(GenerationError, match=f"pier.ndu のデータ確認図と荷重図を JRSNAP で描けません: .*{message}"):
        generate.generate(options, registry=stages)
    assert pages == [] and published(options) == []


def _figures() -> JrsnapFigures:
    return JrsnapFigures("jrsnap", lambda results, pier: ((1, 1),))


@pytest.mark.parametrize("spec,message", [
    (dict(jrsnap_figures=_figures()), "Aのデータ確認図と荷重図の出力jrsnapがありません"),
    (dict(exports=(Export("jrsnap", "a.ndu", lambda results, pier: b""),), jrsnap_figures=_figures(), render=None),
     "Aのデータ確認図と荷重図を差し込む計算書がありません"),
    (dict(exports=(Export("jrsnap", "a.ndu", lambda results, pier: b""),
                   Export("frameweb", "a.json", lambda results, pier: b"")), jrsnap_figures=_figures(),
          load_diagram="frameweb"), "AにFEMPythonの荷重図とJRSNAPの荷重図の両方は差し込めません"),
    (dict(exports=(Export("jrsnap", "a.ndu", lambda results, pier: b""),),
          jrsnap_figures=JrsnapFigures("jrsnap", lambda results, pier: ((1, 1),),
                                       (AlsoFigures("jrsnapreverse", lambda results, pier: ((2, 1),)),))),
     "Aのデータ確認図と荷重図の出力jrsnapreverseがありません"),
])
def test_the_figures_must_name_an_export_of_a_stage_with_a_report(spec, message):
    recorder = Recorder()
    fields = {"render": recorder.render("A"), **spec}
    with pytest.raises(ValueError, match=message):
        Registry((StageSpec("A", "A_x", (), recorder.calculate("A"), **fields),), outputs={"ground_model": ("A",)})


def test_only_0710_and_0720_take_the_figures_of_their_ndu(pier):
    assert [(stage.id, stage.jrsnap_figures.export) for stage in STAGES.stages if stage.jrsnap_figures] == [
        ("0710", "jrsnap"), ("0720", "jrsnap")]
    assert not hasattr(StageSpec, "data_check") and "data_check" not in StageSpec.__dataclass_fields__


def test_each_basic_case_is_drawn_from_the_first_combination_that_uses_it(pier):
    """Decision 51: along the track every case is in combination 1; across it CASE-6 (the down track) is first in
    combination 5, the first of the down track (decision 76)."""
    assert figure_cases(pier, "0710") == tuple((case, 1) for case in range(1, 9))
    assert figure_cases(pier, "0720") == tuple((case, 5 if case == 6 else 1) for case in range(1, 10))
    results = generate._calculate(STAGES, pier, ("0720",))
    assert STAGES.get("0720").jrsnap_figures.load_cases(generate._own(STAGES, results, "0720"), pier) == \
        figure_cases(pier, "0720")


@pytest.mark.parametrize("stage,message", [("0500", "0500に JRSNAP のデータ確認図と荷重図はありません"),
                                           ("0711", "0711に JRSNAP のデータ確認図と荷重図はありません"),
                                           ("0999", "計算段階が不正です")])
def test_figure_cases_of_a_stage_without_figures_is_an_error(pier, stage, message):
    with pytest.raises(InputError, match=message):
        figure_cases(pier, stage)


def _page_order(path: Path, ndu: Path, chapter: int, cases: tuple[tuple[int, int], ...]) -> None:
    """§n and n.1, the データ確認図, n.2 on a new page and the n.3 heading, the load diagram one case a page in case
    order from its combination, then n.4 on a new page (decisions 50, 51)."""
    digest = hashlib.sha256(ndu.read_bytes()).hexdigest()[:16]
    with pymupdf.open(path) as pdf:
        texts = [page.get_text().strip() for page in pdf]
    checks = [index for index, text in enumerate(texts) if text.startswith("FAKE DATA CHECK")]
    diagrams = [index for index, text in enumerate(texts) if text.startswith("FAKE LOAD DIAGRAM")]
    assert [texts[index] for index in checks] == [f"FAKE DATA CHECK {figure} {digest}"
                                                  for figure in jrsnap.DATA_CHECK_FIGURES]
    assert [texts[index] for index in diagrams] == [f"FAKE LOAD DIAGRAM COMB {combination} CASE {case} {digest}"
                                                    for case, combination in cases]
    first, after = checks[0], diagrams[0]
    assert checks == list(range(first, first + 5)) and diagrams == list(range(after, after + len(cases)))
    assert first >= 1 and f"{chapter}.1 検討モデル" in texts[0]
    assert all(f"{chapter}.2 " not in text for text in texts[:first])
    assert texts[first + 5].startswith(f"{chapter}.2 作用の計算")
    between = "\n".join(texts[first + 5:after])
    assert f"{chapter}.3 荷重図" in between and texts[after - 1].splitlines()[-1] == f"{chapter}.3 荷重図"
    assert texts[after + len(cases)].startswith(f"{chapter}.4 ")


@pytest.mark.parametrize("stage,stem,ndu,chapter,direction", [
    ("0710", "0710_線路方向荷重", "線路方向.ndu", 10, "longitudinal"),
    ("0720", "0720_線路直角方向荷重", "線路直角方向.ndu", 11, "transverse")])
def test_the_report_has_the_figures_of_the_published_ndu_where_they_go(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                       pier, stage, stem, ndu, chapter, direction):
    """The real registry, with the stand-in runners: JRSNAP's pages are those of the NDU published with the report."""
    monkeypatch.setattr(fempython, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(jrsnap, "ENV_FILE", tmp_path / ".env")
    items = ("ground_model", "reactions", direction, f"{direction}_seismic")
    options = GenerationOptions(copy_input(tmp_path / "pre", *items), tmp_path / "output", tmp_path / "post")
    generate.generate(options)
    _page_order(Path(options.output_dir) / f"{stem}.pdf", Path(options.post_dir) / ndu, chapter,
                figure_cases(pier, stage))
    sidecar = json.loads((Path(options.post_dir) / f"{ndu}.provenance.json").read_text(encoding="utf-8"))
    assert sidecar["jrsnap_figures"]["load_diagram"] == [
        {"case": case, "combination": combination} for case, combination in figure_cases(pier, stage)]
