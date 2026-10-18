"""The JRSNAP 5.2-L03 acceptance of the データ確認図 and the 荷重図 still belongs to the current generator (decisions 50,
51).

tests/fixtures/acceptance/jrsnap_figures/record.json is what scripts/accept_jrsnap_figures.py recorded of the pages
the real runner (JRSNAPHeadless ``figures``) drew for the 0710 / 0720 NDUs. These tests do not run JRSNAP. They fail
(never skip) when the record is missing, or when the input, the NDU or the cases asked for are no longer the ones the
runner drew: then the acceptance must be redone with
``uv run --project "." --locked python -X utf8 scripts/accept_jrsnap_figures.py --overwrite``.
"""

from functools import cache
import json
from pathlib import Path

import pytest

from webpier.core.integrity import load_json, sha256
from webpier.inputs import parse_input
from webpier.pipeline.generate import export_bytes, figure_cases
from webpier.pipeline.jrsnap import DATA_CHECK_COMBINATION, DATA_CHECK_FIGURES

ROOT = Path(__file__).parents[2]
RECORD_PATH = ROOT / "tests" / "fixtures" / "acceptance" / "jrsnap_figures" / "record.json"
REDO = ("受入をやり直してください: uv run --project \".\" --locked python -X utf8 scripts/accept_jrsnap_figures.py "
        "--overwrite")
STAGES = ("0710", "0720")
CASES = {"0710": 8, "0720": 9}
A4 = (595.3, 841.9)


@cache
def _record() -> dict:
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


def record() -> dict:
    """The record; a missing one fails the test (it is never skipped)."""
    assert RECORD_PATH.is_file(), f"JRSNAP のデータ確認図と荷重図の受入記録がありません: {RECORD_PATH}。{REDO}"
    return _record()


@cache
def _pier():
    data = (ROOT / record()["input"]["path"]).read_bytes()
    assert sha256(data) == record()["input"]["sha256"], f"受入時の入力から変わっています。{REDO}"
    return parse_input(load_json(data))


def _a4_portrait(size) -> bool:
    return abs(size[0] - A4[0]) <= 0.5 and abs(size[1] - A4[1]) <= 0.5


def test_the_record_is_the_real_runner_of_jrsnap_5_2_l03():
    recorded = record()
    assert recorded["kind"] == "jrsnap_figures_acceptance" and recorded["schema_version"] == 1
    assert recorded["runner"]["product"] == "5.2-L03"
    assert not recorded["runner"]["engine_version"].startswith("fake")
    assert set(recorded["stages"]) == set(STAGES)


def test_the_input_is_the_accepted_one():
    data = (ROOT / record()["input"]["path"]).read_bytes()
    assert sha256(data) == record()["input"]["sha256"], f"受入時の入力から変わっています。{REDO}"


@pytest.mark.parametrize("stage", STAGES)
def test_the_drawn_ndu_and_cases_are_what_the_generator_asks_now(stage):
    recorded, pier = record()["stages"][stage], _pier()
    assert sha256(export_bytes(pier, stage, "jrsnap")) == recorded["ndu"]["sha256"], f"{stage} の NDU が変わりました。{REDO}"
    assert [list(item) for item in figure_cases(pier, stage)] == recorded["load_cases"], (
        f"{stage} の荷重図のケースと組合せが変わりました。{REDO}")


@pytest.mark.parametrize("stage", STAGES)
def test_one_load_diagram_page_per_case_in_case_order(stage):
    pages = record()["stages"][stage]["load_diagram"]
    assert len(pages) == CASES[stage]
    assert [page["page"] for page in pages] == list(range(1, CASES[stage] + 1))
    assert [page["case"] for page in pages] == list(range(1, CASES[stage] + 1))
    assert [[page["case"], page["combination"]] for page in pages] == record()["stages"][stage]["load_cases"]
    for page in pages:
        assert page["title"].startswith(f"CASE-{page['case']} "), page


@pytest.mark.parametrize("stage", STAGES)
def test_each_case_is_drawn_from_its_combination(stage):
    """0710 has one combination; in 0720 only CASE-6 (下り線) is drawn from combination 2 (decision 51)."""
    combinations = {page["case"]: page["combination"] for page in record()["stages"][stage]["load_diagram"]}
    expected = {case: 2 if (stage, case) == ("0720", 6) else 1 for case in range(1, CASES[stage] + 1)}
    assert combinations == expected


@pytest.mark.parametrize("stage", STAGES)
def test_the_load_diagram_pages_are_a4_portrait_black_and_white_without_page_numbers(stage):
    for page in record()["stages"][stage]["load_diagram"]:
        assert _a4_portrait(page["size"]), page
        assert page["colored_pixels"] == 0, page
        assert page["page_numbers"] == [], page


def test_both_transverse_train_cases_print_480():
    pages = {page["case"]: page for page in record()["stages"]["0720"]["load_diagram"]}
    assert pages[5]["has_480"] and pages[6]["has_480"]


@pytest.mark.parametrize("stage", STAGES)
def test_the_data_check_is_the_five_figures_of_combination_1(stage):
    data_check = record()["stages"][stage]["data_check"]
    assert data_check["figures"] == list(DATA_CHECK_FIGURES) and len(DATA_CHECK_FIGURES) == 5
    assert data_check["combination"] == DATA_CHECK_COMBINATION == 1
    assert data_check["pages"] >= 5 and len(data_check["sizes"]) == data_check["pages"]
    assert all(_a4_portrait(size) for size in data_check["sizes"]), data_check["sizes"]
