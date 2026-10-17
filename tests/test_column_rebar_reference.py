"""Exact independent PDF oracle for one physical column arrangement.

The fixture is a literal transcription of both source tables, followed by
physical pairings from those tables and their diagrams. Expected locations
never come from the production placement algorithm or the HTML mock.
"""

from collections import Counter
from copy import deepcopy
import importlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "column_rebar_example2.json"
BAR_FIELDS = ("x_mm", "y_mm", "diameter_mm", "material")


def reference():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def reference_column_input():
    """Basic input recipe, deliberately separate from the expected coordinates."""
    return {
        "materials": {"main": "SD390", "transverse": "SD390"},
        "concrete_strength_mpa": 27,
        "pure_cover_mm": 70,
        "main_rows": [
            {
                "face_direction": "線路", "layer": 1, "diameter_mm": 32,
                "material": None, "per_face_count": 29, "endpoints": "含む",
                "cover_mode": "自動", "center_mm": None, "clear_gap_mm": None,
                "distribution": {
                    "mode": "両端＋中央ピッチ", "edge_center_mm": 108, "pitch_mm": 150,
                },
            },
            {
                "face_direction": "直角", "layer": 1, "diameter_mm": 19,
                "material": None, "per_face_count": 9, "endpoints": "含む",
                "cover_mode": "指定", "center_mm": 102, "clear_gap_mm": None,
                "distribution": {
                    "mode": "中央ピッチ", "edge_center_mm": None, "pitch_mm": 250,
                },
            },
        ],
        "side_rows": [], "band_rows": [], "manual_positions": [],
        "position_mode": "基本",
        "column_hoops": {
            "enclosing_diameter_mm": 22,
            "direction_rows": [
                {
                    "direction": "線路", "diameter_mm": 22, "material": "SD390",
                    "effective_legs": 10, "pitch_mm": 150,
                    "start_mm": None, "end_mm": None,
                },
                {
                    "direction": "直角", "diameter_mm": 22, "material": "SD390",
                    "effective_legs": 6, "pitch_mm": 150,
                    "start_mm": None, "end_mm": None,
                },
            ],
        },
    }


def reference_document():
    """Exercise the real document shape without changing any production file."""
    document = json.loads((PROJECT / "pre" / "input.json").read_text(encoding="utf-8"))
    document = deepcopy(document)
    document["鉄筋"]["version"] = 2
    document["鉄筋"]["柱"] = reference_column_input()
    return document


def physical_records(bars):
    return sorted(tuple(bar[key] for key in BAR_FIELDS) for bar in bars)


def test_independent_reference_tables_and_physical_pairings_are_complete():
    expected = reference()
    bars = expected["physical_bars"]
    assert len(bars) == 76
    assert Counter(bar["diameter_mm"] for bar in bars) == {32: 58, 19: 18}
    assert len({(bar["x_mm"], bar["y_mm"]) for bar in bars}) == 76
    assert {bar["material"] for bar in bars} == {"SD390"}
    for bar in bars:
        radius = bar["diameter_mm"] / 2
        assert radius <= bar["x_mm"] <= 4500 - radius
        assert radius <= bar["y_mm"] <= 2700 - radius

    # Count each printed row independently of the application's aggregator.
    for direction, axis, row_count in (("線路", "y_mm", 11), ("直角", "x_mm", 31)):
        rows = expected["directional_rows"][direction]
        assert len(rows) == row_count
        assert sum(row["count"] for row in rows) == 76
        actual = Counter((bar[axis], bar["diameter_mm"], bar["material"]) for bar in bars)
        printed = {
            (row["center_mm"], row["diameter_mm"], row["material"]): row["count"]
            for row in rows
        }
        assert len(printed) == row_count
        assert actual == printed

    # The unusual end spacing and printed D19 centre are essential anchors.
    top = sorted(bar["x_mm"] for bar in bars if bar["y_mm"] == 108)
    assert (top[0], top[1], top[-2], top[-1]) == (108, 300, 4200, 4392)
    assert [right - left for left, right in zip(top, top[1:])] == [192] + [150] * 26 + [192]
    assert {bar["x_mm"] for bar in bars if bar["diameter_mm"] == 19} == {102, 4398}
    assert expected["concrete_strength_mpa"] == 27
    assert expected["pure_cover_mm"] == 70
    assert expected["column_hoops"]["enclosing_diameter_mm"] == 22
    hoop_rows = expected["column_hoops"]["direction_rows"]
    assert [(row["direction"], row["effective_legs"]) for row in hoop_rows] == [("線路", 10), ("直角", 6)]
    for row in hoop_rows:
        assert (row["diameter_mm"], row["pitch_mm"], row["material"]) == (22, 150, "SD390")
        assert row["start_mm"] is None and row["end_mm"] is None


def test_v2_basic_input_matches_every_reference_bar_and_both_full_tables_after_reload():
    # Resolve in-test: absent feature support must be a test failure, never a
    # collection error. The old implementation rejects the new saved version.
    model = importlib.import_module("src.rebar_model")
    expected = reference()
    document = reference_document()
    before = deepcopy(document)
    loaded = json.loads(json.dumps(document, ensure_ascii=False))
    model.validate_document_rebar(loaded)
    member = model.load_member(loaded, "柱")
    geometry = model.section_geometry(loaded, "柱")
    assert (geometry["width_mm"], geometry["height_mm"]) == (4500, 2700)
    bars, _lines, _centers, warnings = model.member_preview("柱", member, geometry)
    assert warnings == []
    assert physical_records(bars) == physical_records(expected["physical_bars"])
    for direction in ("線路", "直角"):
        assert model.directional_rows(bars, direction) == expected["directional_rows"][direction]
    assert member["materials"] == expected["materials"]
    assert member["concrete_strength_mpa"] == expected["concrete_strength_mpa"]
    assert member["pure_cover_mm"] == expected["pure_cover_mm"]
    assert member["column_hoops"] == expected["column_hoops"]
    assert model.patch_member(loaded, "柱", member) == loaded
    assert loaded == before == document


def test_actual_webpier_column_matches_reference_after_reload():
    """The shipped example must use the approved recipe and exact PDF layout.

    This durable test reads only repository files. The implementation-session
    non-column preservation comparison uses root's separate captured baseline.
    """
    model = importlib.import_module("src.rebar_model")
    expected = reference()
    document = json.loads((PROJECT / "pre" / "input.json").read_text(encoding="utf-8"))
    assert document["鉄筋"]["version"] == 2
    column = document["鉄筋"]["柱"]
    assert column["position_mode"] == "基本"
    for key in ("materials", "concrete_strength_mpa", "pure_cover_mm", "column_hoops"):
        assert column[key] == expected[key]
    recipe = reference_column_input()
    assert len(column["main_rows"]) == len(recipe["main_rows"]) == 2
    for actual_row, recipe_row in zip(column["main_rows"], recipe["main_rows"]):
        for key, value in recipe_row.items():
            assert actual_row[key] == value

    reloaded = json.loads(json.dumps(document, ensure_ascii=False))
    model.validate_document_rebar(reloaded)
    geometry = model.section_geometry(reloaded, "柱")
    assert geometry["width_mm"] == expected["coordinates"]["width_mm"]
    assert geometry["height_mm"] == expected["coordinates"]["height_mm"]
    member = model.load_member(reloaded, "柱")
    bars, _lines, _centers, warnings = model.member_preview("柱", member, geometry)
    assert warnings == []
    assert physical_records(bars) == physical_records(expected["physical_bars"])
    for direction in ("線路", "直角"):
        assert model.directional_rows(bars, direction) == expected["directional_rows"][direction]
    assert model.patch_member(reloaded, "柱", member) == document
