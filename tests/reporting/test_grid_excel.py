"""Every report's WebPier pages are published as a grid Excel workbook that maps them strictly, and Excel prints them
where the PDF does (plan glp-0.2.0-grid, 2026-10-21).

The workbook is an output, ``export/<stem>.xlsx``, one sheet a report; 0711 and 0721 have none (their report is
Aggre-SE's). Each stage is generated as the CLI does from an input choosing its 出力項目 with the items it uses
(decision 72; stand-in runners), with the documents the generation writes
recorded; the tests check that the published workbook is the one written here strictly from those documents, and the
one compared with Excel. The stages of a load model (decision 70) are generated with the test add-in.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from grid_excel_support import ROOT, accepted_failures, compare_with_excel, comparison
from webpier.pipeline import generate as generate_module
from webpier.pipeline.generate import GenerationOptions, generate
from webpier.inputs.outputs import OUTPUT_KEYS, uses
from webpier.pipeline.stages import STAGES
from webpier.reporting.workbook import grid_pages, write_workbook

_SPEC = importlib.util.spec_from_file_location("grid_excel_pipeline_support",
                                               ROOT / "tests" / "pipeline" / "pipeline_support.py")
_PIPELINE = sys.modules.setdefault(_SPEC.name, importlib.util.module_from_spec(_SPEC))
_SPEC.loader.exec_module(_PIPELINE)
ADDIN = ROOT / "tests" / "fixtures" / "addin" / "minimal"
GENERIC = ("0600", "0610", "0620", "0710", "0720", "0900")  # the stages a load model replaces (decision 70)
TRAIN = tuple(stage.id for stage in STAGES.stages if stage.grid_documents is not None)
CASES = (*(("train", stage) for stage in TRAIN), *(("addin", stage) for stage in GENERIC))
IDS = [f"{model}-{stage}" for model, stage in CASES]


@pytest.fixture(scope="module")
def generations(tmp_path_factory):
    """(model, stage) → (the published workbook, the documents written into it, the stage's stem), made once."""
    made: dict[tuple[str, str], tuple[Path, list, str]] = {}

    def generation(model: str, stage: str) -> tuple[Path, list, str]:
        if (model, stage) not in made:
            root = tmp_path_factory.mktemp(f"{model}-{stage}")
            source = root / "pre" / "input.json"  # current.json with the sample's footing bars (0800〜0820)
            source.parent.mkdir()
            document = _PIPELINE.footing_document()
            item = STAGES.item(stage)  # the stage's 出力項目 with the items it uses (decision 72)
            document["outputs"] = _PIPELINE.outputs(*(key for key in OUTPUT_KEYS if key == item or key in uses(item)))
            source.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
            written: dict[str, list] = {}
            original = generate_module.write_workbook

            def record(documents, path, sheet):
                written[sheet] = list(documents)
                return original(documents, path, sheet)

            options = GenerationOptions(source, root / "output", root / "post",
                                        addin=ADDIN if model == "addin" else None)
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(generate_module, "write_workbook", record)
                generation = generate(options)
            artifact = next(item for item in generation.artifacts if item.role == f"{stage}.xlsx")
            stem = artifact.path.stem
            made[(model, stage)] = (artifact.path, written[stem], stem)
        return made[(model, stage)]

    return generation


@pytest.mark.parametrize(("model", "stage"), CASES, ids=IDS)
def test_the_published_workbook_maps_the_pages_onto_one_sheet_strictly(generations, model, stage, tmp_path):
    published, documents, stem = generations(model, stage)
    assert published.parent.name == "export"
    result = write_workbook(documents, tmp_path / f"{stage}.xlsx", stem)
    assert not result.shifts and not result.fallbacks
    assert [(sheet.name, sheet.first_page, sheet.last_page) for sheet in result.sheets] == \
        [(stem, 1, len(grid_pages(documents)))]
    assert published.read_bytes() == result.path.read_bytes()


@pytest.mark.parametrize(("model", "stage"), CASES, ids=IDS)
def test_excel_prints_the_published_workbook_where_the_pdf_does(generations, model, stage, tmp_path):
    module = comparison()
    if module is None:
        pytest.skip("GridLayoutPdf の比較スクリプトがありません")
    reason = module.excel_missing_reason()
    if reason is not None:
        pytest.skip(f"Excel を使えません: {reason}")
    published, documents, stem = generations(model, stage)
    pages = grid_pages(documents)
    out = tmp_path / stage
    code, report = compare_with_excel(module, f"webpier-{model}-{stage}", stem, pages, out)
    # the workbook Excel printed is the published one
    assert (out / "workbook.xlsx").read_bytes() == published.read_bytes()
    failures = accepted_failures(report, pages)
    assert not failures, f"{out / 'result.json'} (exit {code}):\n" + "\n".join(failures[:40])


def test_a_report_of_another_program_has_no_workbook():
    assert [stage.id for stage in STAGES.stages if stage.has_report and stage.grid_documents is None] == ["0711", "0721"]
