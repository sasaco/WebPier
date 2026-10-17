"""Snow load propagation and calculation-linked 0600/0610 PDF contracts."""

from copy import deepcopy
import re
import unicodedata

from pypdf import PdfReader
import pytest

from src import calculate as calculate_foundation, parse_input
from src.longitudinal_calculator import calculate_longitudinal_legacy as calculate_longitudinal
from src.longitudinal_combinations import BASIC_ROWS, COMBINATION_ROWS
from src.reaction_calculator import calculate_reactions
from src.reaction_inputs import parse_reaction_input
from src.reaction_report import render_reaction_report
from src.transverse_calculator import calculate_transverse_legacy
from test_reaction_load_rules import asymmetric_snow_input, rounded_force, single_precision, SNOW_KEYS


def pipeline(data=None):
    data = asymmetric_snow_input() if data is None else data
    inputs = parse_reaction_input(data)
    return inputs, calculate_foundation(parse_input(data)), calculate_reactions(inputs)


def compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def pdf_text(path):
    return "\n".join(page.extract_text() for page in PdfReader(path).pages)


def longitudinal_section(text):
    return text[text.index("6.3.1"):text.index("6.3.2")]


def test_0610_preserves_ten_handoffs_and_appends_two_s30_single_values():
    inputs, foundation, reactions = pipeline()
    handoff = reactions["macro_handoff_single"]
    handoff["線路雪荷重強度"] = [
        {"RB": single_precision(123.456789), "RC": single_precision(67.891234)},
        {"RB": single_precision(234.567891), "RC": single_precision(78.912345)},
    ]
    result = calculate_longitudinal(inputs, foundation, reactions)
    assert len(result["horizontal"]) == 12
    for index, row in enumerate(result["horizontal"][:10]):
        expected = handoff["線路荷重強度"][index]
        assert row["case"] == index + 1
        assert row["B"] == expected["RB"]
        assert row["C"] == expected["RC"]
        assert row["total"] == expected["RB"] + expected["RC"]
    for index, row in enumerate(result["horizontal"][10:]):
        expected = handoff["線路雪荷重強度"][index]
        assert row["case"] == 11 + index
        assert row["id"] == ("safety_lr_s30", "recovery_lr_s30")[index]
        assert (row["B"], row["C"], row["total"]) == (expected["RB"], expected["RC"], expected["RB"] + expected["RC"])


def test_0610_appended_basics_contain_s30_vertical_moments_and_horizontal_references():
    inputs, foundation, reactions = pipeline()
    result = calculate_longitudinal(inputs, foundation, reactions)
    assert len(result["basic_cases"]) == 24
    for index, (row, expected) in enumerate(zip(result["basic_cases"][:21], BASIC_ROWS), 1):
        source_row, label, condition, track, spring = expected
        assert (row["id"], row["source_row"], row["label"], row["condition"], row["track"], row["spring_case"]) == (
            index, source_row, label, condition, track, spring)
    snow, safety, recovery = result["basic_cases"][21:]
    assert [row["id"] for row in (snow, safety, recovery)] == [22, 23, 24]
    assert "雪荷重" in snow["label"] and "30" in snow["label"]
    loads = snow["loads"]
    for side, arm in (("B", -inputs.spans.b.f), ("C", inputs.spans.c.f)):
        force = reactions["snow_loads"]["points"][side][SNOW_KEYS[2]]
        assert loads[side] == {"N": force, "arm": arm, "M": rounded_force(force * arm)}
    assert loads["N"] == loads["B"]["N"] + loads["C"]["N"]
    assert loads["M"] == loads["B"]["M"] + loads["C"]["M"]
    assert safety["loads"] == result["horizontal"][10]
    assert recovery["loads"] == result["horizontal"][11]


def test_0610_keeps_old_coefficients_and_uses_s30_in_four_new_combinations():
    result = calculate_longitudinal(*pipeline())
    assert len(result["combinations"]) == 24
    for row, expected in zip(result["combinations"][:20], COMBINATION_ROWS):
        scope, identifier, column, title, coefficients = expected
        assert (row["scope"], row["id"], row["source_column"], row["title"]) == (scope, identifier, column, title)
        assert row["coefficients"] == [*coefficients, 0.0, 0.0, 0.0]
    added = {(row["scope"], row["id"]): row for row in result["combinations"][20:]}
    assert set(added) == {("body", 13), ("body", 14), ("foundation", 9), ("foundation", 10)}
    for key, row in added.items():
        expected = [0.0] * 24
        safety = key in (("body", 13), ("foundation", 9))
        expected[0], expected[1] = (1.1, 1.2) if safety else (1.0, 1.0)
        expected[21] = 1.0
        expected[22 if safety else 23] = 1.0
        assert row["coefficients"] == expected
    assert all(any(row["coefficients"][index] != 0 for row in added.values()) for index in (21, 22, 23))


def test_0610_saved_0600_without_snow_extension_retains_legacy_dimensions():
    inputs, foundation, reactions = pipeline()
    reactions.pop("longitudinal_snow_cases")
    reactions["macro_handoff_single"].pop("線路雪荷重強度")
    result = calculate_longitudinal(inputs, foundation, reactions)
    assert len(result["horizontal"]) == 10
    assert len(result["basic_cases"]) == 21
    assert len(result["combinations"]) == 20
    assert [row["coefficients"] for row in result["combinations"]] == [list(row[4]) for row in COMBINATION_ROWS]


def test_legacy_0620_s2_single_handoff_reaches_earthquake_forces_moments_and_basic_case():
    data = asymmetric_snow_input()
    inputs, foundation, reactions = pipeline(data)
    result = calculate_transverse_legacy(inputs, foundation, reactions)
    handoff = reactions["macro_handoff_single"]
    cells = result["cells"]["荷重計算"]
    expected_h = expected_m = 0.0
    for support, force_column, height_column in (("RB", "P", "T"), ("RC", "X", "AB")):
        force = handoff["直角荷重強度"][6][support]
        height = handoff["直角荷重位置"][6][support]
        assert cells[f"{force_column}281"] == force
        assert cells[f"{height_column}281"] == height
        expected_h += force
        expected_m += force * height
    earthquake = next(row for row in result["horizontal_aggregates"] if row["id"] == 7)
    assert earthquake["H"] == expected_h
    assert earthquake["M"] == expected_m
    assert next(row for row in result["basic_cases"] if row["source_row"] == 32)["loads"] == earthquake
    for side, local, remote in (("起点側", "B", "A"), ("終点側", "C", "D")):
        points = data["上部工反力"][side]
        for row in [*points[f"{local}支点"]["支承"], points[f"{remote}支点"]["合計"]]:
            row[SNOW_KEYS[0]] = 0.0
    no_s2 = calculate_transverse_legacy(*pipeline(data))
    assert result["horizontal"][6] != no_s2["horizontal"][6]
    assert result["horizontal_aggregates"][3]["M"] != no_s2["horizontal_aggregates"][3]["M"]
    assert result["horizontal"][4:6] == no_s2["horizontal"][4:6]
    assert result["horizontal_aggregates"][1:3] == no_s2["horizontal_aggregates"][1:3]


@pytest.mark.parametrize("name,coefficients", [
    ("EA-17", ("0.27", "1.00", "0.25", "0.95")),
    ("EC-16", ("0.20", "0.80", "0.19", "0.76")),
])
def test_0600_pdf_documents_selected_vehicle_snow_combinations_and_adopted_rules(tmp_path, name, coefficients):
    data = asymmetric_snow_input()
    data["上部構造"]["列車"]["車両名"] = name
    _, _, result = pipeline(data)
    before = deepcopy(result)
    path = tmp_path / f"0600-{name}.pdf"
    render_reaction_report(result, path)
    text = pdf_text(path)
    section = compact(longitudinal_section(text))
    assert name in section
    for coefficient in coefficients:
        assert coefficient in section
    for symbol, year in (("S2", "2年"), ("S10", "10年"), ("S30", "30年")):
        assert symbol in section and year in section
    service = section.split("支承に働く水平荷重2)使用性", 1)[1].split("【起点側", 1)[0]
    assert "L+I" in service
    assert not re.search(r"0\.9[×・*]?D1|0\.8[×・*]?D2", section)
    for unwanted in ("7-9", "7-11", "Example", "原本", "明示値", "採用有効係数", "SHA256", "ROUND"):
        assert unwanted not in section
    assert result == before


def test_0600_pdf_updates_rm_and_unsaturated_horizontal_force_when_snow_changes(tmp_path):
    data = asymmetric_snow_input()
    _, _, baseline = pipeline(data)
    data["上部工反力"]["起点側"]["A支点"]["合計"][SNOW_KEYS[0]] += 40.0
    _, _, changed = pipeline(data)
    assert changed["longitudinal"][0]["B"]["remote_vertical"] != baseline["longitudinal"][0]["B"]["remote_vertical"]
    assert changed["longitudinal"][0]["B"]["force"] != baseline["longitudinal"][0]["B"]["force"]
    for label, result in (("before", baseline), ("after", changed)):
        before = deepcopy(result)
        path = tmp_path / f"0600-values-{label}.pdf"
        render_reaction_report(result, path)
        section = compact(longitudinal_section(pdf_text(path)))
        detail = result["longitudinal"][0]["B"]
        assert f'{detail["remote_vertical"]:.2f}' in section
        assert f'{detail["force"]:.2f}' in section
        assert result == before
