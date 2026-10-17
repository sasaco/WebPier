"""Optional physical reinforcement, independent of Tk and calculation rows.

Contract: document["鉄筋"] = {"version": 1, "梁"/"柱"/"フーチング": member}.
Dimensions in this optional schema are mm. Materials contains ``main`` and
``transverse`` grades; concrete_strength_mpa and pure_cover_mm are member fields.
Column main_rows describe opposing face pairs, never two independent analysis
directions. Physical XY uses the top-left origin: X is cross, Y is rail.
"""

from copy import deepcopy
import importlib

import pytest


def api():
    """Resolve during a test so an absent implementation is a genuine RED."""
    return importlib.import_module("src.rebar_model")


def geometry_document():
    """Invented dimensions; no production input or example reinforcement."""
    return {
        "future_root": {"keep": [None, 0]},
        "下部構造": {"寸法": {
            "側面": {"B1": 4.3, "B4": 0.4, "B5": 0.6, "B6": 2.0,
                     "B7": 0.35, "B8": 4.6, "B9": 0.5},
            "正面": {"W1": 6.1, "W4": 0.7, "W5": 0.8, "W6": 1.2,
                     "W7": 0.6, "W8": 5.2, "W9": 0.7},
            "高さ": {"H2": 0.45, "H3": 0.3, "H4": 3.4,
                     "H5": 0.25, "H6": 0.8},
        }},
    }


def pair_row(direction="線路", **changes):
    row = {
        "face_direction": direction, "layer": 1, "diameter_mm": 20,
        "per_face_count": 5, "endpoints": "含む", "cover_mode": "指定",
        "center_mm": 60, "clear_gap_mm": None, "material": "SD345",
    }
    row.update(changes)
    return row


def complete_column():
    return {
        "materials": {"main": "SD345", "transverse": "SD295"},
        "concrete_strength_mpa": 30, "pure_cover_mm": 40,
        "main_rows": [pair_row()], "side_rows": [], "band_rows": [],
        "manual_positions": [],
    }


def set_leaf(data, path, value):
    owner = data
    for key in path[:-1]:
        owner = owner[key]
    owner[path[-1]] = value


def numeric_leaves(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from numeric_leaves(child)
    elif isinstance(value, list):
        for child in value:
            yield from numeric_leaves(child)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield value


@pytest.mark.parametrize("member", ["梁", "柱", "フーチング"])
def test_blank_member_is_detached_virtual_schema_without_example_values(member):
    model = api()
    first = model.blank_member(member)
    expected = deepcopy(first)
    assert first["materials"] == {"main": None, "transverse": None}
    assert first["concrete_strength_mpa"] is None
    assert first["pure_cover_mm"] is None
    engineering_inputs = deepcopy(first)
    for family in ("main_rows", "side_rows", "band_rows", "manual_positions"):
        for row in engineering_inputs[family]:
            for selector in ("layer", "layers", "columns", "stack_order"):
                if selector in row:
                    permitted = (None, 1, 2) if selector == "stack_order" else (None, 1)
                    assert row.pop(selector) in permitted
    assert not list(numeric_leaves(engineering_inputs)), "Blank fields must not invent reinforcement"
    assert all(row.get("material") is None for row in first["main_rows"])
    if member == "柱":
        geometry = model.section_geometry(geometry_document(), member)
        assert model.column_bars(first, geometry) == []
    assert set(first) >= {"main_rows", "side_rows", "band_rows", "manual_positions"}
    first["materials"]["main"] = "changed"
    first["main_rows"].append({"future_row": [0]})
    assert model.blank_member(member) == expected


def test_patch_member_is_copy_on_write_and_preserves_unknowns_and_null_zero():
    model = api()
    source = geometry_document()
    old_member = complete_column()
    old_member["future_member"] = {"nullable": None, "zero": 0}
    old_member["main_rows"][0]["future_row"] = {"retain": [None, 0]}
    source["鉄筋"] = {
        "version": 1, "future_schema": {"keep": True}, "柱": old_member,
        "梁": {"future_beam": [1, 2]},
    }
    before = deepcopy(source)
    candidate = deepcopy(old_member)
    candidate["pure_cover_mm"] = 0
    candidate["main_rows"][0]["per_face_count"] = 7
    patched = model.patch_member(source, "柱", candidate)
    assert source == before
    assert patched is not source
    assert patched["future_root"] == before["future_root"]
    assert patched["鉄筋"]["future_schema"] == {"keep": True}
    assert patched["鉄筋"]["梁"] == {"future_beam": [1, 2]}
    stored = patched["鉄筋"]["柱"]
    assert stored["future_member"] == {"nullable": None, "zero": 0}
    assert stored["main_rows"][0]["future_row"] == {"retain": [None, 0]}
    assert stored["pure_cover_mm"] == 0
    assert stored["main_rows"][0]["clear_gap_mm"] is None
    candidate["main_rows"][0]["per_face_count"] = 99
    patched["future_root"]["keep"].append(5)
    assert stored["main_rows"][0]["per_face_count"] == 7
    assert source == before


def test_first_patch_adds_only_optional_root_and_edited_member():
    model = api()
    source = geometry_document()
    before = deepcopy(source)
    candidate = model.blank_member("柱")
    candidate["pure_cover_mm"] = 0
    patched = model.patch_member(source, "柱", candidate)
    assert source == before and "鉄筋" not in source
    assert patched["鉄筋"] == {"version": 1, "柱": candidate}
    assert {key: value for key, value in patched.items() if key != "鉄筋"} == before


@pytest.mark.parametrize("member", ["梁", "柱", "フーチング"])
def test_validation_accepts_partial_null_rows_without_filling_blanks(member):
    model = api()
    candidate = model.blank_member(member)
    candidate["pure_cover_mm"] = 0
    if member == "柱":
        candidate["main_rows"] = [pair_row(
            diameter_mm=None, per_face_count=None, center_mm=None,
            layer=None, material=None,
        )]
    elif member == "梁":
        candidate["main_rows"] = [{
            "face": "上", "bar_type": "ループ筋", "layer": None,
            "diameter_mm": None, "count": None, "cover_mode": "自動",
            "center_mm": None, "clear_gap_mm": None, "material": None,
        }]
        candidate["side_rows"] = [{
            "diameter_mm": None, "per_face_count": None, "columns": None,
            "start_mm": None, "pitch_mm": None,
            "stirrup_position": "内側", "material": None,
        }]
    else:
        candidate["main_rows"] = [{
            "direction": "線路", "face": "上", "diameter_mm": None,
            "pitch_mm": None, "layers": None, "stack_order": None,
            "cover_mode": "自動", "center_mm": None, "material": None,
        }]
    candidate["band_rows"] = [{
        "type": "外巻き", "direction": "線路", "diameter_mm": None,
        "sets": None, "pitch_mm": None, "start_mm": None, "end_mm": None,
        "material": None,
    }]
    before = deepcopy(candidate)
    model.validate_member(member, candidate)
    assert candidate == before


@pytest.mark.parametrize("path,bad,label", [
    (("pure_cover_mm",), -1, "かぶり"),
    (("pure_cover_mm",), float("nan"), "かぶり"),
    (("concrete_strength_mpa",), float("inf"), "強度"),
    (("main_rows", 0, "diameter_mm"), 0, "径"),
    (("main_rows", 0, "diameter_mm"), -13, "径"),
    (("main_rows", 0, "diameter_mm"), float("inf"), "径"),
    (("main_rows", 0, "diameter_mm"), "20", "径"),
    (("main_rows", 0, "per_face_count"), -1, "本数"),
    (("main_rows", 0, "per_face_count"), 2.5, "本数"),
    (("main_rows", 0, "per_face_count"), True, "本数"),
    (("main_rows", 0, "layer"), 0, "段"),
    (("main_rows", 0, "layer"), 1.2, "段"),
    (("main_rows", 0, "center_mm"), -10, "芯"),
    (("main_rows", 0, "clear_gap_mm"), -5, "あき"),
    (("band_rows", 0, "diameter_mm"), -10, "径"),
    (("band_rows", 0, "sets"), True, "組"),
    (("band_rows", 0, "sets"), -1, "組"),
    (("band_rows", 0, "sets"), float("inf"), "組"),
    (("band_rows", 0, "pitch_mm"), 0, "間隔"),
    (("band_rows", 0, "pitch_mm"), float("nan"), "間隔"),
    (("band_rows", 0, "start_mm"), -1, "開始"),
    (("band_rows", 0, "end_mm"), float("inf"), "終了"),
])
def test_column_validation_reports_readable_numeric_errors(path, bad, label):
    candidate = complete_column()
    candidate["band_rows"] = [{
        "type": "外巻き", "direction": "線路", "diameter_mm": 10,
        "sets": 1, "pitch_mm": 150, "start_mm": 0, "end_mm": 1200,
        "material": None,
    }]
    set_leaf(candidate, path, bad)
    with pytest.raises(ValueError, match=label):
        api().validate_member("柱", candidate)


@pytest.mark.parametrize("key,bad,label", [
    ("diameter_mm", float("nan"), "径"),
    ("per_face_count", 3.5, "本数"),
    ("columns", 0, "列"),
    ("columns", True, "列"),
    ("start_mm", -1, "開始"),
    ("pitch_mm", -50, "間隔"),
])
def test_beam_side_validation_has_explicit_count_columns_and_position(key, bad, label):
    candidate = {
        "materials": {"main": None, "transverse": None},
        "pure_cover_mm": None, "concrete_strength_mpa": None,
        "main_rows": [], "band_rows": [], "manual_positions": [],
        "side_rows": [{"diameter_mm": 16, "per_face_count": 4, "columns": 2,
                       "start_mm": 80, "pitch_mm": 120,
                       "stirrup_position": "内側", "material": None}],
    }
    candidate["side_rows"][0][key] = bad
    with pytest.raises(ValueError, match=label):
        api().validate_member("梁", candidate)


@pytest.mark.parametrize("key,bad,label", [
    ("diameter_mm", -25, "径"),
    ("pitch_mm", 0, "間隔"),
    ("pitch_mm", float("inf"), "間隔"),
    ("layers", 1.5, "段"),
    ("layers", 0, "段"),
    ("stack_order", True, "順"),
    ("center_mm", -1, "芯"),
])
def test_footing_validation_covers_pitch_layers_and_stack_order(key, bad, label):
    candidate = {
        "materials": {"main": None, "transverse": None},
        "pure_cover_mm": None, "concrete_strength_mpa": None,
        "main_rows": [{"direction": "線路", "face": "上", "diameter_mm": 25,
                       "pitch_mm": 125, "layers": 1, "stack_order": 1,
                       "cover_mode": "指定", "center_mm": 80, "material": None}],
        "side_rows": [], "band_rows": [], "manual_positions": [],
    }
    candidate["main_rows"][0][key] = bad
    with pytest.raises(ValueError, match=label):
        api().validate_member("フーチング", candidate)


def test_invalid_patch_does_not_mutate_source():
    model = api()
    source = geometry_document()
    before = deepcopy(source)
    candidate = complete_column()
    candidate["main_rows"][0]["per_face_count"] = 1.5
    with pytest.raises(ValueError, match="本数"):
        model.patch_member(source, "柱", candidate)
    assert source == before


def test_section_geometry_uses_current_dimensions_and_preserves_input():
    model = api()
    source = geometry_document()
    before = deepcopy(source)
    column = model.section_geometry(source, "柱")
    assert column["width_mm"] == column["cross_mm"] == 1200
    assert column["height_mm"] == column["rail_mm"] == 2000
    beam = model.section_geometry(source, "梁")
    assert beam["width_mm"] == 4300
    assert beam["height_mm"] == pytest.approx(750)
    assert beam["haunch_mm"] == 300
    assert beam["lower_width_mm"] == pytest.approx(3300)
    assert beam["lower_left_mm"] == 400
    rail = model.section_geometry(source, "フーチング", direction="線路")
    cross = model.section_geometry(source, "フーチング", direction="直角")
    assert rail["width_mm"] == pytest.approx(5450)
    assert cross["width_mm"] == pytest.approx(6500)
    for result, direction, top_width, top_left in (
        (rail, "線路", 4600, 350), (cross, "直角", 5200, 600)
    ):
        assert result["direction"] == direction
        assert result["height_mm"] == pytest.approx(1050)
        assert result["taper_mm"] == 250
        assert result["top_width_mm"] == pytest.approx(top_width)
        assert result["top_left_mm"] == pytest.approx(top_left)
    assert source == before and "鉄筋" not in source
    source["下部構造"]["寸法"]["正面"]["W6"] = 1.6
    assert model.section_geometry(source, "柱")["cross_mm"] == 1600


@pytest.mark.parametrize("stored,expected", [("missing", 5300), (None, 5300), (0, 4950), (0.2, 5150)])
def test_section_geometry_b9_falls_back_only_when_missing_or_null(stored, expected):
    source = geometry_document()
    side = source["下部構造"]["寸法"]["側面"]
    if stored == "missing":
        del side["B9"]
    else:
        side["B9"] = stored
    before = deepcopy(source)
    assert api().section_geometry(source, "フーチング")["width_mm"] == pytest.approx(expected)
    assert source == before


@pytest.mark.parametrize("bad", [True, "0.2", -1, float("nan"), float("inf")])
def test_explicit_invalid_b9_is_not_replaced_by_formula(bad):
    source = geometry_document()
    source["下部構造"]["寸法"]["側面"]["B9"] = bad
    with pytest.raises(ValueError, match="B9"):
        api().section_geometry(source, "フーチング")


def test_column_shared_positions_deduplicate_corners_and_conserve_direction_counts():
    model = api()
    member = complete_column()
    member["main_rows"] = [
        pair_row("線路", per_face_count=5),
        pair_row("直角", per_face_count=3),
        pair_row("線路", per_face_count=2, diameter_mm=16, endpoints="含めない"),
    ]
    before = deepcopy(member)
    geometry = model.section_geometry(geometry_document(), "柱")
    bars = model.column_bars(member, geometry)
    assert member == before
    assert len(bars) == 16  # 10 + 6 - 4 shared corners + 4 different inner bars
    locations = {(bar["x_mm"], bar["y_mm"], bar["diameter_mm"]) for bar in bars}
    assert len(locations) == 16
    assert {(x, y, 20) for x in (60, 1140) for y in (60, 1940)} <= locations
    assert {(x, y, 16) for x in (420, 780) for y in (60, 1940)} <= locations
    rail = model.directional_rows(bars, "線路")
    cross = model.directional_rows(bars, "直角")
    for rows in (rail, cross):
        assert sum(row["count"] for row in rows) == len(bars)
        assert rows == sorted(rows, key=lambda row: (row["center_mm"], row["diameter_mm"], row["material"]))
    assert {(row["center_mm"], row["diameter_mm"], row["count"]) for row in rail} == {
        (60, 20, 5), (60, 16, 2), (1000, 20, 2), (1940, 20, 5), (1940, 16, 2),
    }
    assert {(row["center_mm"], row["diameter_mm"], row["count"]) for row in cross} == {
        (60, 20, 3), (330, 20, 2), (420, 16, 2), (600, 20, 2),
        (780, 16, 2), (870, 20, 2), (1140, 20, 3),
    }


def test_direction_aggregation_keeps_materials_distinct_at_same_center_and_diameter():
    bars = [
        {"x_mm": 10, "y_mm": 20, "diameter_mm": 16, "material": "SD345"},
        {"x_mm": 30, "y_mm": 20, "diameter_mm": 16, "material": "SD390"},
    ]
    before = deepcopy(bars)
    assert api().directional_rows(bars, "線路") == [
        {"center_mm": 20, "diameter_mm": 16, "count": 1, "material": "SD345"},
        {"center_mm": 20, "diameter_mm": 16, "count": 1, "material": "SD390"},
    ]
    assert bars == before


def test_beam_automatic_centers_follow_independently_numbered_bar_type_chains():
    model = api()
    member = model.blank_member("梁")
    member["pure_cover_mm"] = 40
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 10}]
    loop = {"face": "上", "bar_type": "ループ筋", "layer": 1,
            "diameter_mm": 32, "cover_mode": "自動", "center_mm": None,
            "clear_gap_mm": None}
    straight1 = {"face": "上", "bar_type": "直筋", "layer": 1,
                 "diameter_mm": 20, "cover_mode": "自動", "center_mm": None,
                 "clear_gap_mm": None}
    straight2 = {"face": "上", "bar_type": "直筋", "layer": 2,
                 "diameter_mm": 16, "cover_mode": "自動", "center_mm": None,
                 "clear_gap_mm": 25}
    member["main_rows"] = [loop, straight1, straight2]
    before = deepcopy(member)
    assert model.effective_center(member, loop) == 66
    assert model.effective_center(member, straight1) == 60
    assert model.effective_center(member, straight2) == 103  # 60 + 20/2 + 25 + 16/2
    assert member == before


def test_column_rejects_overlapping_discs_with_affected_row_indices():
    model = api()
    member = complete_column()
    member["main_rows"] = [
        pair_row("線路", per_face_count=5, center_mm=60),
        pair_row("直角", per_face_count=3, center_mm=60),
        pair_row("線路", per_face_count=5, center_mm=70),
    ]
    geometry = model.section_geometry(geometry_document(), "柱")
    with pytest.raises(ValueError, match="重な|間隔|干渉") as raised:
        model.column_bars(member, geometry)
    assert "[1]" in str(raised.value)
    assert "[3]" in str(raised.value)


def test_column_allows_touching_discs_after_shared_corner_deduplication():
    model = api()
    member = complete_column()
    member["main_rows"] = [
        pair_row("線路", per_face_count=5, center_mm=60),
        pair_row("直角", per_face_count=3, center_mm=60),
        pair_row("線路", per_face_count=1, center_mm=80),
    ]
    bars = model.column_bars(member, model.section_geometry(geometry_document(), "柱"))
    assert len(bars) == 14
    assert sum(row["count"] for row in model.directional_rows(bars, "線路")) == 14


@pytest.mark.parametrize("cover", [None, 0, 70])
def test_existing_sparse_member_patch_does_not_persist_unchanged_virtual_scaffolding(cover):
    model = api()
    stored = {"pure_cover_mm": cover, "future": {"null": None, "zero": 0}}
    source = {"鉄筋": {"version": 1, "柱": stored}}
    before = deepcopy(source)
    candidate = model.load_member(source, "柱")
    assert "materials" in candidate and "main_rows" in candidate
    candidate["concrete_strength_mpa"] = 30
    patched = model.patch_member(source, "柱", candidate)
    assert patched == {"鉄筋": {"version": 1, "柱": {
        "pure_cover_mm": cover, "concrete_strength_mpa": 30,
        "future": {"null": None, "zero": 0},
    }}}
    assert source == before


def test_existing_explicit_null_and_zero_survive_a_different_leaf_edit():
    model = api()
    source = {"鉄筋": {"version": 1, "梁": {
        "pure_cover_mm": 0, "concrete_strength_mpa": None,
        "materials": {"main": None, "future_grade": "retained"},
    }}}
    candidate = model.load_member(source, "梁")
    candidate["materials"]["main"] = "SD345"
    patched = model.patch_member(source, "梁", candidate)
    assert patched["鉄筋"]["梁"] == {
        "pure_cover_mm": 0, "concrete_strength_mpa": None,
        "materials": {"main": "SD345", "future_grade": "retained"},
    }


def test_automatic_center_accepts_identical_outside_zone_diameters_but_not_conflicts():
    model = api()
    member = complete_column()
    member["main_rows"][0].update(cover_mode="自動", center_mm=None)
    member["band_rows"] = [
        {"type": "外巻き", "diameter_mm": 10, "start_mm": 0, "end_mm": 500},
        {"type": "外巻き", "diameter_mm": 10, "start_mm": 500, "end_mm": 2000},
    ]
    row = member["main_rows"][0]
    assert model.effective_center(member, row) == 60
    member["band_rows"][1]["diameter_mm"] = 13
    assert model.effective_center(member, row) is None


def test_automatic_second_layer_remains_blank_when_earlier_layer_is_incomplete():
    model = api()
    member = complete_column()
    first = pair_row("線路", cover_mode="自動", center_mm=None, diameter_mm=None)
    second = pair_row("線路", cover_mode="自動", center_mm=None,
                      layer=2, diameter_mm=16, clear_gap_mm=25)
    member["main_rows"] = [first, second]
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 10}]
    assert model.effective_center(member, second) is None


def test_column_preview_limits_requested_physical_bars_before_allocating_positions():
    """Preview expansion is bounded at 10000 bars; saving remains independent."""
    model = api()
    member = complete_column()
    # Tiny discs fit geometrically; a spacing check cannot be the resource guard.
    member["main_rows"] = [pair_row(per_face_count=5001, diameter_mm=0.000001)]
    model.validate_member("柱", member)
    with pytest.raises(ValueError, match="上限|最大|10000"):
        model.column_bars(member, model.section_geometry(geometry_document(), "柱"))


@pytest.mark.parametrize("sets,legs", [(0.5, 1), (1.5, 3), (5.5, 11)])
def test_transverse_half_sets_are_explicit_quantities_with_equivalent_legs(sets, legs):
    model = api()
    member = complete_column()
    row = {"type": "内側", "direction": "線路", "diameter_mm": 10,
           "sets": sets, "pitch_mm": 150, "legs_mode": "自動"}
    member["band_rows"] = [row]
    before = deepcopy(member)
    model.validate_member("柱", member)
    assert model.effective_legs(row) == legs
    assert member == before


def test_completed_auto_legs_with_nonintegral_equivalent_request_specification():
    model = api()
    member = complete_column()
    row = {"type": "内側", "direction": "線路", "diameter_mm": 10,
           "sets": 1.25, "pitch_mm": 150, "legs_mode": "自動"}
    member["band_rows"] = [row]
    assert model.effective_legs(row) is None
    with pytest.raises(ValueError, match="有効脚|指定"):
        model.validate_member("柱", member)
    row["legs_mode"] = "指定"
    row["effective_legs"] = None
    model.validate_member("柱", member)  # A specified blank remains incomplete.
    assert model.effective_legs(row) is None


@pytest.mark.parametrize("bad", [True, -1, 1.5, float("inf")])
def test_specified_effective_legs_must_be_nonnegative_finite_integers(bad):
    member = complete_column()
    member["band_rows"] = [{"type": "内側", "diameter_mm": 10, "sets": 5.5,
                            "pitch_mm": 150, "legs_mode": "指定", "effective_legs": bad}]
    with pytest.raises(ValueError, match="脚"):
        api().validate_member("柱", member)


def test_auto_legs_retains_inactive_specified_value_and_never_uses_width_density():
    model = api()
    row = {"sets": 5.5, "legs_mode": "自動", "effective_legs": 10, "density_per_m": 3}
    before = deepcopy(row)
    assert model.effective_legs(row) == 11
    assert row == before
    row["legs_mode"] = "指定"
    assert model.effective_legs(row) == 10
    assert model.effective_legs({"density_per_m": 5.5, "legs_mode": "自動"}) is None


@pytest.mark.parametrize("bad", [-1, float("inf")])
def test_beam_side_column_center_spacing_is_an_explicit_validated_dimension(bad):
    model = api()
    member = model.blank_member("梁")
    member["side_rows"] = [{"diameter_mm": 16, "per_face_count": 4, "columns": 2,
                            "column_pitch_mm": bad, "start_mm": 250, "pitch_mm": 150,
                            "stirrup_position": "内側"}]
    with pytest.raises(ValueError, match="列.*間隔"):
        model.validate_member("梁", member)


def flat_footing_geometry():
    source = geometry_document()
    source["下部構造"]["寸法"]["高さ"].update(H5=0, H6=1)
    return api().section_geometry(source, "フーチング")


def footing_row(direction="直角", face="上", center=100, **changes):
    row = {"direction": direction, "face": face, "diameter_mm": 20,
           "pitch_mm": 200, "layers": 1, "stack_order": 1,
           "cover_mode": "指定", "center_mm": center,
           "clear_gap_mm": None, "material": None}
    row.update(changes)
    return row


@pytest.mark.parametrize("earlier_layers,gap,expected", [(1, None, 127), (2, 30, 182)])
def test_footing_auto_stack_follows_actual_specified_earlier_innermost_envelope(earlier_layers, gap, expected):
    model = api()
    member = model.blank_member("フーチング")
    member["pure_cover_mm"] = 50
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 16, "sets": 1, "pitch_mm": 150}]
    member["main_rows"][1] = footing_row("線路", "下", 100, diameter_mm=25,
                                         layers=earlier_layers, clear_gap_mm=gap, stack_order=1)
    member["main_rows"][3] = footing_row("直角", "下", None, diameter_mm=29,
                                         cover_mode="自動", stack_order=2)
    bars, lines, centers, warnings = model.member_preview("フーチング", member, flat_footing_geometry())
    assert centers[3] == expected
    assert {bar["y_mm"] for bar in bars} == {1000 - expected}
    assert lines and not warnings


def test_flat_footing_vertical_center_and_layers_do_not_change_lateral_bar_grid():
    model = api()
    member = model.blank_member("フーチング")
    member["pure_cover_mm"] = 50
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 10, "sets": 1, "pitch_mm": 150}]
    member["main_rows"] = [footing_row(center=100, layers=2, clear_gap_mm=80, pitch_mm=250)]
    geometry = flat_footing_geometry()
    bars, _, _, _ = model.member_preview("フーチング", member, geometry)
    first = [bar["x_mm"] for bar in bars if bar["y_mm"] == 100]
    second = [bar["x_mm"] for bar in bars if bar["y_mm"] == 200]
    assert first and second == first
    member["main_rows"][0]["center_mm"] = 150
    shifted, _, _, _ = model.member_preview("フーチング", member, geometry)
    assert [bar["x_mm"] for bar in shifted if bar["y_mm"] == 150] == first
    assert [bar["x_mm"] for bar in shifted if bar["y_mm"] == 250] == first


def test_footing_lateral_grid_changes_when_actual_taper_expands_at_deeper_layer():
    model = api()
    source = geometry_document()
    source["下部構造"]["寸法"]["高さ"].update(H5=0.3, H6=0.7)
    member = model.blank_member("フーチング")
    member["pure_cover_mm"] = 50
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 10, "sets": 1, "pitch_mm": 150}]
    member["main_rows"] = [footing_row(center=100, layers=2, clear_gap_mm=80, pitch_mm=250)]
    bars, _, _, _ = model.member_preview("フーチング", member, model.section_geometry(source, "フーチング"))
    upper = [bar["x_mm"] for bar in bars if bar["y_mm"] == 100]
    deeper = [bar["x_mm"] for bar in bars if bar["y_mm"] == 200]
    assert upper and deeper and min(upper) > min(deeper)
    assert len(deeper) >= len(upper)


@pytest.mark.parametrize("kind", ["line_circle", "line_line"])
@pytest.mark.parametrize("separation,overlaps", [(19, True), (20, False)])
def test_footing_line_intersections_reject_overlap_but_allow_exact_contact(kind, separation, overlaps):
    model = api()
    member = model.blank_member("フーチング")
    member["main_rows"] = [footing_row("線路", center=100),
                           footing_row("直角" if kind == "line_circle" else "線路", center=100 + separation)]
    if overlaps:
        with pytest.raises(ValueError, match="重な|間隔"):
            model.member_preview("フーチング", member, flat_footing_geometry())
    else:
        bars, lines, _, _ = model.member_preview("フーチング", member, flat_footing_geometry())
        assert lines and (bars if kind == "line_circle" else len(lines) == 2)


@pytest.mark.parametrize("member", ["柱", "梁"])
def test_manual_duplicate_physical_records_are_rejected_instead_of_deduplicated(member):
    model = api()
    candidate = model.blank_member(member)
    candidate["position_mode"] = "指定"
    point = {"x_mm": 100, "y_mm": 100, "diameter_mm": 20, "material": "SD345"}
    candidate["manual_positions"] = [deepcopy(point), deepcopy(point)]
    geometry = model.section_geometry(geometry_document(), member)
    with pytest.raises(ValueError, match="重複|同じ位置|重な"):
        model.member_preview(member, candidate, geometry)


def test_beam_distinct_layers_with_identical_physical_bar_records_are_rejected():
    model = api()
    member = model.blank_member("梁")
    row = {"face": "上", "bar_type": "直筋", "layer": 1, "diameter_mm": 20,
           "count": 1, "cover_mode": "指定", "center_mm": 100}
    other = {**row, "layer": 2}
    member["main_rows"] = [row, other]
    with pytest.raises(ValueError, match="重複|同じ位置|重な"):
        model.member_preview("梁", member, model.section_geometry(geometry_document(), "梁"))


def test_footing_opposite_groups_cannot_collapse_into_one_identical_bar_plane():
    model = api()
    member = model.blank_member("フーチング")
    member["main_rows"] = [footing_row("直角", "上", 500), footing_row("直角", "下", 500)]
    with pytest.raises(ValueError, match="重複|同じ位置|重な"):
        model.member_preview("フーチング", member, flat_footing_geometry())


def test_column_repeated_same_direction_rows_are_not_shared_corner_records():
    model = api()
    member = complete_column()
    member["main_rows"] = [pair_row(), pair_row()]
    with pytest.raises(ValueError, match="重複|同じ位置|重な"):
        model.column_bars(member, model.section_geometry(geometry_document(), "柱"))


def test_column_opposite_faces_cannot_collapse_to_a_single_plane():
    model = api()
    member = complete_column()
    member["main_rows"] = [pair_row("直角", per_face_count=3, center_mm=600)]
    with pytest.raises(ValueError, match="対向|重複|同じ位置|重な|半幅"):
        model.column_bars(member, model.section_geometry(geometry_document(), "柱"))


def side_member(*, count=4, columns=2, position="内側", column_pitch=30):
    model = api()
    member = model.blank_member("梁")
    member["pure_cover_mm"] = 70
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 22, "sets": 1, "pitch_mm": 150}]
    member["side_rows"] = [{"diameter_mm": 22, "per_face_count": count, "columns": columns,
                            "column_pitch_mm": column_pitch, "start_mm": 250, "pitch_mm": 150,
                            "stirrup_position": position, "cover_mode": "自動"}]
    return member


def test_completed_side_column_count_is_checked_before_any_position_expansion():
    # Only format validation is called: the regression must not run an old
    # implementation's potentially billion-iteration placement loop.
    member = side_member(count=1, columns=10**9)
    with pytest.raises(ValueError, match="列.*本数|本数.*列|列数"):
        api().validate_member("梁", member)


@pytest.mark.parametrize("count", [None, 0])
def test_incomplete_or_inactive_side_count_remains_saveable_with_column_selector(count):
    api().validate_member("梁", side_member(count=count, columns=10**9))


@pytest.mark.parametrize("position,offsets", [("内側", {103, 133}), ("外側", {59, 29})])
def test_side_column_offsets_use_outer_band_cover_reference_and_explicit_column_pitch(position, offsets):
    model = api()
    member = side_member(position=position)
    geometry = model.section_geometry(geometry_document(), "梁")
    bars, _, _, _ = model.member_preview("梁", member, geometry)
    assert {bar["x_mm"] for bar in bars if bar["x_mm"] < geometry["width_mm"] / 2} == offsets
    assert {geometry["width_mm"] - bar["x_mm"] for bar in bars if bar["x_mm"] > geometry["width_mm"] / 2} == offsets


def test_side_outside_columns_overrunning_concrete_are_rejected():
    model = api()
    member = side_member(count=3, columns=3, position="外側", column_pitch=40)
    with pytest.raises(ValueError, match="外|かぶり|配置"):
        model.member_preview("梁", member, model.section_geometry(geometry_document(), "梁"))


def test_zero_set_outer_band_is_retained_but_inactive_for_geometry_and_enclosure():
    model = api()
    member = complete_column()
    member["pure_cover_mm"] = 70
    member["main_rows"][0].update(cover_mode="自動", center_mm=None)
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 22, "sets": 0,
                            "pitch_mm": 150, "start_mm": 0, "end_mm": 10**9}]
    geometry = model.section_geometry(geometry_document(), "柱")
    before = deepcopy(member)
    assert model.band_outline("柱", member, geometry, member["band_rows"][0]) == []
    assert model.effective_center(member, member["main_rows"][0]) == 80
    bars, _, centers, _ = model.member_preview("柱", member, geometry)
    assert bars and centers == [80]
    assert member == before and member["band_rows"][0]["sets"] == 0
    incomplete = deepcopy(member)
    incomplete["band_rows"][0]["sets"] = None
    assert model.effective_center(incomplete, incomplete["main_rows"][0]) != 80
