"""Variable-page native style, snapshot isolation and readable atomic output."""

import builtins
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
import io
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reporting_seismic_audit import audited_sections, owned_pdf_glyphs

import fitz
from pypdf import PdfReader
import pytest

from src.calculator import calculate
from src.inputs import parse_input
from src.longitudinal_design_conditions import parse_longitudinal_design_conditions
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from src.seismic_transverse_calculator import calculate_seismic_transverse
from src.seismic_transverse_report import render_seismic_transverse_report
from src.transverse_calculator import calculate_transverse


FIXTURES = Path(__file__).parent / "fixtures"


def calculated(*, geometry=None, train=None, spans=None, bearings=None):
    data = json.loads((FIXTURES / "seismic_transverse_input.json").read_text(encoding="utf-8-sig"))
    inputs = parse_reaction_input(data)
    if geometry:
        inputs = replace(inputs, geometry=replace(inputs.geometry, **geometry))
    if train:
        inputs = replace(inputs, train=replace(inputs.train, **train))
    if spans:
        inputs = replace(inputs, spans=replace(inputs.spans, **{
            key: replace(getattr(inputs.spans, key), **values) for key, values in spans.items()}))
    if bearings:
        inputs = replace(inputs, dead=replace(inputs.dead, **bearings(inputs.dead)))
    reactions = calculate_reactions(inputs)
    transverse = calculate_transverse(inputs, calculate(parse_input(data)), reactions,
                                     design_conditions=parse_longitudinal_design_conditions(data))
    return calculate_seismic_transverse(inputs, reactions, transverse)


def render(result, path):
    render_seismic_transverse_report(result, path)
    return audited_sections(result, path)[0]


def assert_readable(path):
    with fitz.open(path) as document:
        assert len(document) > 0
        for page in document:
            assert tuple(page.rect) == (0, 0, 595, 842)
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        rect = fitz.Rect(span["bbox"])
                        assert rect.x0 >= 47.5 and rect.x1 <= 576.5
                        assert rect.y0 >= 71.5 and rect.y1 <= 824
                        assert any(abs(span["size"] - role) < .1 for role in (9.9, 6.5, 8.0))
                        assert span["color"] == 0
            for drawing in page.get_drawings():
                rect = drawing["rect"]
                assert rect.x0 >= 47.5 and rect.x1 <= 576.5
                assert rect.y0 >= 71.5 and rect.y1 <= 824


def test_current_four_pages_have_all_actions_current_values_and_selected_case(tmp_path):
    result = calculated()
    path = tmp_path / "current.pdf"
    texts = render(result, path)
    assert len(texts) == 4  # Heading-defined scopes, independently audited against every PDF glyph.
    for number, (text, heading) in enumerate(zip(texts, (
        "11.1 検討モデル", "11.2 作用の計算（1）", "11.2 作用の計算（2）", "11.3 作用の組合せ"), strict=True), 1):
        assert heading in text
    assert all(f"11 - {number}" in page.extract_text() for number, page in enumerate(PdfReader(path).pages, 1))
    for value in ("13.050", "10.340", "2.750", "2.000", "0.700", "4.890", "1.350", "9.000"):
        assert value in texts[0]
    assert texts[0].count("0.010") == 2
    actions = texts[1]
    for value in ("上り線載荷", "下り線載荷", "320.00", "160.00", "-0.020", "-2.950", "480.00",
                  "1028.62", "-1028.62", "6720.00", "2370.00", "9090.00", "19838.00", "7267.00", "27105.00"):
        assert value in actions
    assert "9080.00" not in actions and "シェルター" not in actions
    assert "等価作用（橋脚天端）" in actions
    assert "Mは丸め前鉛直力×アーム" in actions
    for value in ("Kh=0.30 適用済み", "96.00", "48.00", "144.00", "770.40", "595.35", "297.68", "1105.65"):
        assert value in texts[2]
    cases = texts[3]
    assert "1 + 2 + 3 + 4 + 5 + 7 + 8 + 9" in cases
    assert "→" in cases and "限定増分" in cases and "Kh=0.30" in cases
    assert "列車荷重 下り" in cases and "列車荷重 上り" in cases
    assert "TYPE" in cases and "kN" not in cases
    whole = "\n".join(texts) + str(PdfReader(path).metadata)
    for forbidden in ("ばね", "バネ", "Kv", "Ks", "Kr", "spring", "固定端", "Example", "legacy", "拡大"):
        assert forbidden not in whole
    assert_readable(path)


def test_model_uses_true_scaled_nodes_and_top_down_labels(tmp_path):
    result = calculated()
    path = tmp_path / "model.pdf"
    render(result, path)
    with fitz.open(path) as document:
        page = document[0]
        marks = [drawing for drawing in page.get_drawings()
                 if drawing.get("color") == (0, 0, 0) and drawing["width"] == pytest.approx(.48, abs=.002)
                 and drawing["rect"].width == pytest.approx(2.4, abs=.002)
                 and drawing["rect"].height == pytest.approx(2.4, abs=.002)]
        assert len(marks) == len(result["frame"]["nodes"]) == 8
        ys = sorted((drawing["rect"].y0 + drawing["rect"].y1) / 2 for drawing in marks)
        heights = sorted((node["y"] for node in result["frame"]["nodes"]), reverse=True)
        scale = (ys[-1] - ys[0]) / (heights[0] - heights[-1])
        assert ys == pytest.approx([ys[-1] - height * scale for height in heights], abs=.002)
        spans = [span for block in page.get_text("dict")["blocks"]
                 for line in block.get("lines", []) for span in line["spans"]]
        nodes = owned_pdf_glyphs(result, path, "0720/frame.nodes")
        members = owned_pdf_glyphs(result, path, "0720/frame.members")
        assert [span["text"] for span in sorted(nodes, key=lambda span: span["bbox"][1])] == list("12345678")
        assert [span["text"] for span in sorted(members, key=lambda span: span["bbox"][1])] == list("1234567")


def test_renderer_uses_only_snapshot_and_does_not_mutate_it(tmp_path, monkeypatch):
    result = calculated()
    original = deepcopy(result)
    def guard(open_function):
        def checked(file, mode="r", *args, **kwargs):
            if isinstance(file, (str, Path)) and not any(flag in mode for flag in "wax+"):
                if Path(file).suffix.lower() in (".json", ".pdf", ".xls", ".xlsx"):
                    pytest.fail(f"Renderer reopened a source file: {file}")
            return open_function(file, mode, *args, **kwargs)
        return checked
    monkeypatch.setattr(builtins, "open", guard(builtins.open))
    monkeypatch.setattr(io, "open", guard(io.open))
    render_seismic_transverse_report(result, tmp_path / "snapshot.pdf")
    assert result == original


@pytest.mark.parametrize("spans", [{"b": {"h1": .65}}, {"b": {"h1": 0, "h2": 0}, "c": {"h1": 0, "h2": 0}}])
def test_distinct_and_zero_upper_levels_remain_four_pages(tmp_path, spans):
    result = calculated(spans=spans)
    path = tmp_path / "upper-levels.pdf"
    texts = render(result, path)
    for level in result["frame"]["upper_levels"].values():
        assert f"{level['height']:.3f}" in texts[0]
    assert_readable(path)


def test_nonround_geometry_pedestal_and_all_inertia_components_are_printed(tmp_path):
    result = calculated(geometry={
        "b1": 3.113, "w1": 9.377, "b4": .131, "b5": .177, "w4": 1.671, "w5": 2.143,
        "b6": 2.719, "w6": 4.637, "h1": .837, "b2": .253, "b3": 1.217, "w2": 1.003, "w3": 2.137,
        "h5": .457, "unit_weight_body": 25.237, "unit_weight_footing": 26.173,
        "unit_weight_displaced_soil": 18.431,
    }, train={"earthquake_load": 41.173})
    path = tmp_path / "nonround.pdf"
    texts = render(result, path)
    actions = texts[2]
    assert "桁受けに作用する水平力" in actions and "はり下" in actions
    for key in ("beam_top", "beam_bottom", "column", "footing"):
        assert f"{result['inertia'][key]:.2f}" in actions
    number = r"(-?\d+\.\d+)"
    rows = re.findall(rf"Hw[123] = {number} × {number} × {number} × {number} = {number} kN/m", actions)
    assert len(rows) == 3
    for row in rows:
        b, w, gamma, kh, expected = map(Decimal, row)
        assert (b * w * gamma * kh).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == expected
    row = re.search(rf"H = {number} / {number}\s+× \( {number} - {number} \) × {number} = {number} kN", actions)
    assert row is not None
    weight, gamma, repeated_gamma, displaced, kh, expected = map(Decimal, row.groups())
    assert gamma == repeated_gamma
    assert (weight / gamma * (gamma - displaced) * kh).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == expected
    assert_readable(path)


def test_printed_girder_and_train_factors_reproduce_values(tmp_path):
    result = calculated(train={"earthquake_load": 37.137}, spans={"b": {"hs": 2.951237}, "c": {"hs": 3.067123}})
    texts = render(result, tmp_path / "precision.pdf")
    number = r"(-?\d+(?:\.\d+)?)"
    rows = re.findall(rf"B  H = \( {number} \+ {number} \+ {number} \) × {number} = {number} kN", texts[1])
    rows += re.findall(rf"C  H = \( {number} \+ {number} \+ {number} \) × {number} = {number} kN", texts[1])
    assert len(rows) == 2
    for row in rows:
        d1, d2, snow, kh, expected = map(Decimal, row)
        assert ((d1 + d2 + snow) * kh).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == expected
    moments = re.findall(rf"(?m)^M = {number} × {number} = {number} kN・m", texts[1])
    assert len(moments) == 2
    for row in moments:
        force, arm, expected = map(Decimal, row)
        assert (force * arm).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == expected
    train_rows = re.findall(rf"(?m)^(?:起点側|終点側) G\d+ {number} × {number} = {number} {number} {number}$", texts[1])
    assert len(train_rows) == 12
    for row in train_rows:
        source, rate, force, arm, moment = map(Decimal, row)
        assert (source * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == force
        assert (source * rate * arm).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == moment


def test_all_active_bearings_are_shown_including_zero_reaction(tmp_path):
    def extra(dead):
        return {"c": (*dead.c[:2], replace(dead.c[0], position=0.123, factors=(0, 0, 0, 0)), *dead.c[3:])}
    result = calculated(bearings=extra)
    texts = render(result, tmp_path / "active-bearings.pdf")
    assert texts[1].count("終点側 G3") == 2
    assert texts[1].count("0.123") == 2


def test_twenty_active_bearings_per_track_fit_with_every_equation_and_own_arm(tmp_path):
    def expanded(dead):
        return {side: tuple(replace(bearing, position=index + (.125 if side == "c" else 0))
                            for index, bearing in enumerate(getattr(dead, side)))
                for side in ("b", "c")}
    result = calculated(bearings=expanded)
    path = tmp_path / "twenty-bearings.pdf"
    texts = render(result, path)
    text = texts[1]
    assert "上り線載荷" in text and "下り線載荷" in text
    number = r"(-?\d+(?:\.\d+)?)"
    equations = re.findall(rf"(?m)^(起点側|終点側) G(\d+) {number} × {number} = {number} {number} {number}$", text)
    assert len(equations) == 40
    expected_rows = [row for track in ("up", "down") for row in result["vertical"]["train"][track]["rows"]]
    for printed, expected in zip(equations, expected_rows, strict=True):
        side, index, *numbers = printed
        source, rate, force, arm, moment = map(Decimal, numbers)
        assert ({"起点側": "B", "終点側": "C"}[side], int(index)) == (expected["side"], expected["bearing"])
        assert arm == Decimal(str(expected["arm"]))
        assert force == Decimal(f"{expected['N']:.2f}")
        assert moment == Decimal(f"{expected['M']:.2f}")
        assert (source * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == force
        assert (source * rate * arm).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == moment
    assert "9090.00" in text and "27105.00" in text
    assert_readable(path)


@pytest.mark.parametrize("existing", (False, True))
@pytest.mark.parametrize("failure", ("label", "bearings"))
def test_unreadable_four_page_result_fails_without_touching_target(tmp_path, existing, failure):
    result = calculated()
    if failure == "label":
        result["basic_cases"][0]["label"] = "荷重" * 10000
    else:
        for action in result["vertical"]["train"].values():
            action["rows"] = [deepcopy(action["rows"][0]) for _ in range(30)]
    path = tmp_path / "too-large.pdf"
    if existing:
        path.write_bytes(b"previous approved report")
    from gridlayoutpdf import LayoutOverflowError
    with pytest.raises((LayoutOverflowError, ValueError), match="height|rows|fit|duplicate|overflow|tall|page"):
        render_seismic_transverse_report(result, path)
    assert path.read_bytes() == b"previous approved report" if existing else not path.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_failed_atomic_replace_preserves_existing_file_and_cleans_temp(tmp_path, monkeypatch):
    result = calculated()
    path = tmp_path / "locked.pdf"
    path.write_bytes(b"previous approved report")
    def reject_replace(*args):
        raise PermissionError("locked output")
    monkeypatch.setattr("os.replace", reject_replace)
    with pytest.raises(PermissionError, match="locked"):
        render_seismic_transverse_report(result, path)
    assert path.read_bytes() == b"previous approved report"
    assert not list(tmp_path.glob("*.tmp"))

