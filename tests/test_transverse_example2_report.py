"""Public 0620 report: independent loads, complete cases, engineering labels."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import re

import fitz
import pytest

from src.calculator import calculate
from src.inputs import parse_input
from src.reaction_inputs import parse_reaction_input
from src.reaction_calculator import calculate_reactions
from src.longitudinal_design_conditions import parse_longitudinal_design_conditions


PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def result():
    from src.transverse_calculator import calculate_transverse
    data = json.loads((PROJECT / "pre/input.json").read_text(encoding="utf-8"))
    inputs = parse_reaction_input(data)
    return calculate_transverse(inputs, calculate(parse_input(data)), calculate_reactions(inputs),
                                design_conditions=parse_longitudinal_design_conditions(data))


# Native report frame (48, 72)-(576, 792); footers sit below the body frame.
FRAME_LEFT, FRAME_RIGHT = 48, 576


def test_public_renderer_delegates_to_the_native_stage(monkeypatch, tmp_path):
    import src.transverse_report as public
    calls = []
    monkeypatch.setattr(public, "render", lambda result, path: calls.append((result, path)))
    public.render_transverse_report({"schema_version": 2}, tmp_path / "x.pdf")
    assert calls == [({"schema_version": 2}, tmp_path / "x.pdf")]


def test_report_uses_only_canonical_result_and_preserves_it(result, tmp_path):
    from src.transverse_report import render_transverse_report
    canonical = deepcopy(result)
    canonical.pop("legacy_audit", None)
    before = deepcopy(canonical)
    path = tmp_path / "canonical.pdf"
    render_transverse_report(canonical, path)
    assert canonical == before
    with fitz.open(path) as document:
        text = "\n".join(page.get_text() for page in document)
        for term in ("基本ケース", "Defineケース", "組合せケース", "抽出ケース", "上り", "下り",
                     "27.0", "26,500,000", "高水位", "雪荷重", "支承", "kN/m"):
            assert term in text
        for forbidden in ("元表", "互換", "監査", "Single", "Double", "Example", "採用候補なし", "未計算"):
            assert forbidden not in text
        assert all(not page.get_images() for page in document)
        for page in document:
            assert page.rect == fitz.Rect(0, 0, 595, 842)
            assert "0620 直角方向荷重" in page.get_text()
            for word in page.get_text("words"):
                assert FRAME_LEFT - .5 <= word[0] <= word[2] <= FRAME_RIGHT + .5
                assert 25 <= word[1] <= word[3] <= 825


def test_zero_service_factor_renders_without_missing_candidate(tmp_path):
    from src.transverse_calculator import calculate_transverse
    from src.transverse_report import render_transverse_report
    data = json.loads((PROJECT / "pre/input.json").read_text(encoding="utf-8"))
    inputs = parse_reaction_input(data)
    inputs = replace(inputs, train=replace(inputs.train, factors_service=0))
    result = calculate_transverse(inputs, calculate(parse_input(data)), calculate_reactions(inputs),
                                  design_conditions=parse_longitudinal_design_conditions(data))
    path = tmp_path / "zero-service.pdf"
    render_transverse_report(result, path)
    with fitz.open(path) as document:
        text = "\n".join(page.get_text() for page in document)
    assert "使用性の荷重修正係数が0" in text


def test_full_bearing_tables_and_nonzero_h1_paginate_within_page(tmp_path):
    from src.transverse_calculator import calculate_transverse
    from src.transverse_report import render_transverse_report
    data = json.loads((PROJECT / "pre/input.json").read_text(encoding="utf-8"))
    inputs = parse_reaction_input(data)
    b = tuple(replace(row, position=float(i - 5)) for i, row in enumerate(inputs.dead.b))
    c = tuple(replace(row, position=float(i - 4)) for i, row in enumerate(inputs.dead.c))
    inputs = replace(inputs, dead=replace(inputs.dead, b=b, c=c),
                     geometry=replace(inputs.geometry, h1=.3, b3=.5, w3=.7))
    result = calculate_transverse(inputs, calculate(parse_input(data)), calculate_reactions(inputs),
                                  design_conditions=parse_longitudinal_design_conditions(data))
    path = tmp_path / "all-bearings.pdf"
    render_transverse_report(result, path)
    with fitz.open(path) as document:
        text = "\n".join(page.get_text() for page in document)
        # H1 is typeset with a real subscript, extracted as "H 1".
        assert re.search(r"H\s*1上端", text)
        # Source typography separates the R subscript and bearing label.
        # Both sides must retain every bearing in all 14 load tables.
        assert text.count("G10") == 28
        assert text.count("G5") == 28  # Includes B's real position zero.
        for page in document:
            assert len(page.get_text()) > 100
            for word in page.get_text("words"):
                assert FRAME_LEFT - .5 <= word[0] <= word[2] <= FRAME_RIGHT + .5
                assert 25 <= word[1] <= word[3] <= 825


def test_section_order_kept_groups_and_open_load_equations(result, tmp_path):
    """Pages vary with content; order, unsplit load tables and typography do not."""
    from src.transverse_report import render_transverse_report
    path = tmp_path / "reference-layout.pdf"
    render_transverse_report(result, path)
    with fitz.open(path) as document:
        pages = [page.get_text() for page in document]
        full = "\n".join(pages)
        order = ["骨組図", "固定死荷重", "付加死荷重", "浮力", "雪荷重", "列車荷重", "衝撃荷重",
                 "車両横荷重", "風荷重", "基本ケース", "Defineケース", "組合せケース", "抽出ケース"]
        cursor = 0
        for term in order:  # ValueError if a section is missing or out of order
            cursor = full.index(term, cursor) + len(term)
        assert full.count("U = −10 ×") == 3
        # Every bearing table starts and finishes on one page: its header and
        # its total (合計 / Σ) are never separated by a page break.
        for page in pages:
            lines = [line.strip() for line in page.splitlines()]
            headers = sum(line.startswith("鉛直力") and line.endswith("(kN)") for line in lines)
            assert headers == sum(line in ("合計", "Σ") for line in lines)
        assert sum(page.count("起点側 RB") for page in pages) == full.count("起点側 RB")
        for page in document:
            assert not page.get_images()
            spans = [span for block in page.get_text("dict")["blocks"]
                     for line in block.get("lines", []) for span in line["spans"]]
            # Reference body typography only: 9.9 pt text, 6.5 pt scripts and
            # 8 pt frame dimensions; nothing is enlarged or shrunk to fit.
            assert {round(span["size"], 1) for span in spans} <= {9.9, 6.5, 8.0}


# Authored native matrix: x=48, No 18, 要求性能 43.2, 性能項目 54, 15 x 24.6 pt.
MATRIX_LEFT, MATRIX_PITCH = 48 + 18 + 43.2 + 54, 24.6


def test_all_240_coefficients_in_the_native_matrix_cells(result, tmp_path):
    """Read every finished coefficient glyph from its physical native cell."""
    from src.transverse_report import render_transverse_report
    path = tmp_path / "coefficient-cells.pdf"
    render_transverse_report(result, path)
    with fitz.open(path) as document:
        pages = [page for page in document if "組合せケースと荷重係数" in page.get_text()]
        assert len(pages) == 1
        page = pages[0]
        assert page.rotation == 0
        words = page.get_text("words")
        top = next(word[3] for word in words if "組合せケースと荷重係数" in word[4])
        bottom = next((word[1] for word in words if "抽出ケース" in word[4] and word[1] > top), 842)
        bands = {}
        for x0, y0, x1, y1, text, *_ in words:
            identifier = re.match(r"\d+", text.strip())
            if x0 < FRAME_LEFT + 18 and top < y0 < bottom and identifier:
                bands.setdefault(int(identifier[0]), (y0, y1))
        cells = {}
        for block in page.get_text("rawdict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    for char in span["chars"]:
                        x0, y0, x1, y1 = char["bbox"]
                        x, y = (x0 + x1) / 2, (y0 + y1) / 2
                        row = next((key for key, (upper, lower) in bands.items() if upper <= y <= lower), None)
                        column = int((x - MATRIX_LEFT) // MATRIX_PITCH) if x >= MATRIX_LEFT else -1
                        if row is not None and 0 <= column < 15:
                            cells[(row, column)] = cells.get((row, column), "") + char["c"]
        actual = []
        for combination in result["combinations"]:
            for column_index, coefficient in enumerate(combination["coefficients"]):
                value = cells.get((combination["id"], column_index), "").strip()
                expected = "－" if coefficient == 0 else (
                    f"{coefficient:.1f}" if coefficient == int(coefficient) else f"{coefficient:g}")
                assert value == expected, (combination["id"], column_index + 1, value, expected)
                actual.append(value)
        assert len(actual) == 240
