"""Column-specific input rules and detached editing transitions."""

from copy import deepcopy
import json

import pytest

from src import rebar_model as model


def geometry():
    return {"width_mm": 4500, "height_mm": 2700,
            "cross_mm": 4500, "rail_mm": 2700, "member_height_mm": 4900}


def column():
    member = model.blank_member("柱")
    member.update(materials={"main": "SD390", "transverse": "SD390"},
                  pure_cover_mm=70, concrete_strength_mpa=27)
    member["main_rows"] = [{
        "face_direction": "線路", "layer": 1, "diameter_mm": 32,
        "material": None, "per_face_count": 29, "cover_mode": "指定",
        "center_mm": 108, "clear_gap_mm": None, "endpoints": "含む",
        "distribution": {"mode": "両端＋中央ピッチ", "edge_center_mm": 108,
                         "pitch_mm": 150},
    }]
    return member


def api(name):
    function = getattr(model, name, None)
    assert callable(function), f"Missing column facade: {name}"
    return function


@pytest.mark.parametrize("mode,count,edge,pitch,expected", [
    ("等分", 4, 150, None, [150, 1550, 2950, 4350]),
    ("中央ピッチ", 3, None, 250, [2000, 2250, 2500]),
    ("両端＋中央ピッチ", 29, 108, 150,
     [108, *range(300, 4201, 150), 4392]),
])
def test_distribution_rules_separate_face_center_from_in_plane_positions(mode, count, edge, pitch, expected):
    member = column()
    member["main_rows"][0].update(per_face_count=count,
        distribution={"mode": mode, "edge_center_mm": edge, "pitch_mm": pitch})
    before = deepcopy(member)
    result = api("column_layout")(member, geometry())
    assert result["complete"] and result["issues"] == []
    assert result["centers"] == [108]
    assert sorted(bar["x_mm"] for bar in result["bars"] if bar["y_mm"] == 108) == expected
    assert sorted(bar["x_mm"] for bar in result["bars"] if bar["y_mm"] == 2592) == expected
    assert len(result["bars"]) == count * 2
    assert all(bar["material"] == "SD390" for bar in result["bars"])
    assert member == before


@pytest.mark.parametrize("mode,count,edge,pitch,expected", [
    ("等分", 0, None, None, []),
    ("等分", 1, None, None, [2250]),
    ("中央ピッチ", 1, None, None, [2250]),
    ("両端＋中央ピッチ", 2, 108, None, [108, 4392]),
    ("両端＋中央ピッチ", 3, 108, 150, [108, 2250, 4392]),
])
def test_small_counts_use_only_needed_distribution_values(mode, count, edge, pitch, expected):
    member = column()
    row = member["main_rows"][0]
    row.update(per_face_count=count,
               distribution={"mode": mode, "edge_center_mm": edge, "pitch_mm": pitch})
    if count == 0:
        row.update(diameter_mm=None, center_mm=None)
    result = api("column_layout")(member, geometry())
    assert result["complete"] and result["issues"] == []
    assert sorted(bar["x_mm"] for bar in result["bars"] if bar["y_mm"] == 108) == expected


def test_partial_distribution_exposes_missing_field_without_invented_bars():
    member = column()
    member["main_rows"][0]["distribution"]["pitch_mm"] = None
    result = api("column_layout")(member, geometry())
    assert not result["complete"] and result["bars"] == []
    assert result["issues"][0]["row_index"] == 0
    assert "distribution.pitch_mm" in result["issues"][0]["fields"]
    assert result["issues"][0]["message"]
    assert model.member_preview("柱", member, geometry())[0] == []
    assert model.member_preview("柱", member, geometry())[3]


@pytest.mark.parametrize("distribution", [None, [], {"mode": "unknown"},
    {"mode": "中央ピッチ", "pitch_mm": 0},
    {"mode": "中央ピッチ", "pitch_mm": -1},
    {"mode": "中央ピッチ", "pitch_mm": float("nan")},
    {"mode": "中央ピッチ", "pitch_mm": float("inf")},
    {"mode": "中央ピッチ", "pitch_mm": True},
    {"mode": "等分", "edge_center_mm": -1},
])
def test_invalid_distribution_is_rejected_during_shape_and_placement_validation(distribution):
    member = column()
    member["main_rows"][0]["distribution"] = distribution
    with pytest.raises(model.EditorError):
        model.validate_member("柱", member)
    with pytest.raises(model.EditorError):
        api("column_layout")(member, geometry())


@pytest.mark.parametrize("count,edge,pitch", [
    (1, 108, 150), (2, 2300, None), (29, 108, 170),
    (29, 108, 20), (5001, 108, 0.01),
])
def test_impossible_distributions_reject_without_mutation(count, edge, pitch):
    member = column()
    row = member["main_rows"][0]
    row.update(per_face_count=count,
               distribution={"mode": "両端＋中央ピッチ", "edge_center_mm": edge, "pitch_mm": pitch})
    before = deepcopy(member)
    with pytest.raises(model.EditorError):
        api("column_layout")(member, geometry())
    assert member == before


def test_new_distribution_deduplicates_only_shared_matching_corners():
    member = column()
    first = member["main_rows"][0]
    first.update(diameter_mm=20, center_mm=100, per_face_count=5,
                 distribution={"mode": "等分", "edge_center_mm": 100, "pitch_mm": None})
    member["main_rows"].append(dict(deepcopy(first), face_direction="直角"))
    square = {"width_mm": 1000, "height_mm": 1000, "rail_mm": 1000, "cross_mm": 1000}
    result = api("column_layout")(member, square)
    assert len(result["bars"]) == 16
    assert sum(row["count"] for row in model.directional_rows(result["bars"], "線路")) == 16
    member["main_rows"][1]["diameter_mm"] = 19
    with pytest.raises(model.EditorError, match="異なる径"):
        api("column_layout")(member, square)


def hoops():
    return {"enclosing_diameter_mm": 22, "direction_rows": [
        {"direction": direction, "diameter_mm": 22, "material": None,
         "effective_legs": legs, "pitch_mm": 150, "start_mm": None, "end_mm": None}
        for direction, legs in (("線路", 10), ("直角", 6))]}


def document(member, version=2):
    return {"鉄筋": {"version": version, "柱": deepcopy(member),
                     "future_root": {"keep": [None, 0]}},
            "下部構造": {"寸法": {"正面": {"W6": 4.5}, "側面": {"B6": 2.7}, "高さ": {"H4": 4.9}}}}


def test_version_two_promotion_preserves_legacy_data_and_other_member_edits():
    legacy = column()
    legacy["main_rows"][0].pop("distribution")
    legacy["future_member"] = {"keep": [None, 0]}
    original = document(legacy, version=1)
    before = deepcopy(original)
    assert model.patch_member(original, "柱", model.load_member(original, "柱")) == original
    assert model.column_bars(legacy, geometry()) == model.column_bars(model.load_member(original, "柱"), geometry())
    new = deepcopy(legacy)
    new["main_rows"][0]["distribution"] = column()["main_rows"][0]["distribution"]
    promoted = model.patch_member(original, "柱", new)
    assert promoted["鉄筋"]["version"] == 2
    assert promoted["鉄筋"]["future_root"] == original["鉄筋"]["future_root"]
    assert promoted["鉄筋"]["柱"]["future_member"] == legacy["future_member"]
    assert model.patch_member(promoted, "梁", model.blank_member("梁"))["鉄筋"]["version"] == 2
    assert original == before
    model.validate_document_rebar(promoted)


@pytest.mark.parametrize("version", [True, 0, 3, "2"])
def test_unsupported_root_versions_fail(version):
    with pytest.raises(model.EditorError):
        model.load_member(document(column(), version), "柱")


@pytest.mark.parametrize("extension", ["distribution", "column_hoops", "manual_basis"])
def test_stored_version_one_cannot_silently_ignore_new_features(extension):
    member = column()
    member["main_rows"][0].pop("distribution")
    if extension == "distribution":
        member["main_rows"][0][extension] = {"mode": "等分", "edge_center_mm": 108}
    elif extension == "column_hoops":
        member[extension] = hoops()
    else:
        member[extension] = {"generator_version": 1, "geometry": {}, "inputs": {}}
    with pytest.raises(model.EditorError, match="形式|version|バージョン"):
        model.load_member(document(member, 1), "柱")


def test_column_hoops_totals_are_separate_from_enclosure_and_legacy_zones():
    member = column()
    member["main_rows"][0].update(cover_mode="自動", center_mm=None)
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 40,
                            "sets": 5, "start_mm": 6000, "end_mm": 7000}]
    member["column_hoops"] = hoops()
    member["column_hoops"]["future"] = {"keep": [None, 0]}
    member["column_hoops"]["direction_rows"][0]["future_row"] = "keep"
    before = deepcopy(member)
    layout = api("column_layout")(member, geometry())
    assert layout["centers"] == [108]
    assert len(model.member_preview("柱", member, geometry())[0]) == 58
    model.validate_document_rebar(document(member))
    assert model.patch_member(document(member), "柱", member)["鉄筋"]["柱"] == before
    assert member == before
    assert [row["effective_legs"] for row in member["column_hoops"]["direction_rows"]] == [10, 6]
    assert all("sets" not in row and "type" not in row for row in member["column_hoops"]["direction_rows"])


@pytest.mark.parametrize("value", [None, [], {"direction_rows": None},
    {"enclosing_diameter_mm": 0}, {"enclosing_diameter_mm": True},
    {"direction_rows": [None]},
    {"direction_rows": [{"direction": "unknown"}]},
    {"direction_rows": [{"effective_legs": 2.5}]},
    {"direction_rows": [{"effective_legs": -1}]},
    {"direction_rows": [{"pitch_mm": float("inf")}]},
    {"direction_rows": [{"start_mm": 20, "end_mm": 10}]},
])
def test_malformed_column_hoops_do_not_fall_back_to_legacy(value):
    member = column()
    member["column_hoops"] = value
    with pytest.raises(model.EditorError):
        model.validate_member("柱", member)


def test_new_hoop_height_zones_validate_without_filling_unspecified_ends():
    member = column()
    member["column_hoops"] = hoops()
    assert model.member_preview("柱", member, geometry())[0]
    assert member["column_hoops"]["direction_rows"][0]["end_mm"] is None
    member["column_hoops"]["direction_rows"][0]["end_mm"] = 4901
    with pytest.raises(model.EditorError, match="柱高さ"):
        model.member_preview("柱", member, geometry())


def test_automatic_centers_keep_explicit_102_and_previous_layer_clear_gap():
    member = column()
    member["column_hoops"] = hoops()
    row = member["main_rows"][0]
    row.update(cover_mode="自動", center_mm=None)
    assert model.effective_center(member, row) == 108
    side = dict(deepcopy(row), face_direction="直角", diameter_mm=19,
                per_face_count=9, distribution={"mode": "中央ピッチ", "pitch_mm": 250})
    assert model.effective_center(member, side) == 101.5
    side.update(cover_mode="指定", center_mm=102)
    assert model.effective_center(member, side) == 102
    inner = dict(deepcopy(row), layer=2, diameter_mm=16, clear_gap_mm=40,
                 per_face_count=3, distribution={"mode": "中央ピッチ", "pitch_mm": 250})
    member["main_rows"].extend([side, inner])
    assert model.effective_center(member, inner) == 172
    result = api("column_layout")(member, geometry())
    assert result["complete"] and result["centers"] == [108, 102, 172]
    member["column_hoops"]["enclosing_diameter_mm"] = None
    result = api("column_layout")(member, geometry())
    assert not result["complete"]
    assert "column_hoops.enclosing_diameter_mm" in result["issues"][0]["fields"]
    assert len(result["bars"]) == 18  # Explicit side centres are still determinate.


def test_first_detail_edit_is_atomic_and_records_the_generating_basis():
    member = column()
    before = deepcopy(member)
    assert api("column_detail_status")(member, geometry()) == "自動"
    detailed = api("column_edit_detail")(member, geometry(), 0, {"x_mm": 113})
    assert member == before
    assert detailed["position_mode"] == "指定"
    assert len(detailed["manual_positions"]) == 58
    assert detailed["manual_positions"][0]["x_mm"] == 113
    assert all(row["material"] == "SD390" for row in detailed["manual_positions"])
    assert detailed["manual_basis"]["generator_version"] == 1
    assert detailed["manual_basis"]["geometry"] == {"width_mm": 4500, "height_mm": 2700}
    assert detailed["manual_basis"]["inputs"]["main_rows"] == member["main_rows"]
    assert api("column_detail_status")(detailed, geometry()) == "一致"
    assert model.member_preview("柱", detailed, geometry())[0][0]["x_mm"] == 113
    detailed["main_rows"][0]["per_face_count"] = 27
    reloaded = json.loads(json.dumps(document(detailed), ensure_ascii=False))
    detailed = model.load_member(reloaded, "柱")
    assert api("column_detail_status")(detailed, geometry()) == "基本条件変更"
    assert model.member_preview("柱", detailed, geometry())[0][0]["x_mm"] == 113
    assert len(model.member_preview("柱", detailed, geometry())[0]) == 58


@pytest.mark.parametrize("initial_material", ["SD390", None])
def test_new_detail_material_is_frozen_even_when_initially_unresolved(initial_material):
    member = column()
    member["materials"]["main"] = initial_material
    detailed = api("column_edit_detail")(member, geometry(), 0, {"x_mm": 113})
    detailed["materials"]["main"] = "SD345"
    actual = model.member_preview("柱", detailed, geometry())[0]
    assert all(bar["material"] == initial_material for bar in actual)
    assert api("column_detail_status")(detailed, geometry()) == "基本条件変更"


def test_old_manual_without_basis_keeps_material_inheritance_even_under_version_two():
    member = column()
    member["main_rows"][0].pop("distribution")
    member.update(position_mode="指定", manual_positions=[
        {"x_mm": 100, "y_mm": 100, "diameter_mm": 20, "material": None, "future": [None, 0]}])
    loaded = model.load_member(document(member), "柱")
    assert api("column_detail_status")(loaded, geometry()) == "生成元不明"
    edited = api("column_edit_detail")(loaded, geometry(), 0, {"x_mm": 110})
    assert "manual_basis" not in edited and edited["manual_positions"][0]["future"] == [None, 0]
    edited["materials"]["main"] = "SD345"
    assert model.member_preview("柱", edited, geometry())[0][0]["material"] == "SD345"


def test_full_detail_table_commit_validates_every_position_and_allows_explicit_deletion():
    member = column()
    positions = api("column_layout")(member, geometry())["bars"]
    before = deepcopy(member)
    invalid = deepcopy(positions)
    invalid[-1]["x_mm"] = None
    with pytest.raises(model.EditorError):
        api("column_set_detail")(member, geometry(), invalid)
    assert member == before
    changed = api("column_set_detail")(member, geometry(), positions[:-1])
    assert len(model.member_preview("柱", changed, geometry())[0]) == 57
    deleted = api("column_set_detail")(changed, geometry(), [])
    assert deleted["position_mode"] == "指定"
    assert model.member_preview("柱", deleted, geometry())[0] == []
    assert deleted["manual_basis"] == changed["manual_basis"]


def test_first_detail_copy_rejects_partial_automatic_placement():
    member = column()
    member["main_rows"][0]["distribution"]["pitch_mm"] = None
    before = deepcopy(member)
    with pytest.raises(model.EditorError, match="未入力|未完|不完全"):
        api("column_set_detail")(member, geometry(), [])
    assert member == before


@pytest.mark.parametrize("basis", [None, [], {},
    {"generator_version": 2, "geometry": {}, "inputs": {}},
    {"generator_version": True, "geometry": {}, "inputs": {}},
    {"generator_version": 1, "geometry": [], "inputs": {}},
    {"generator_version": 1, "geometry": {}, "inputs": []},
])
def test_invalid_or_unknown_manual_basis_is_not_silently_updated(basis):
    member = column()
    member["manual_basis"] = basis
    with pytest.raises(model.EditorError):
        model.validate_member("柱", member)


def changed_detail():
    member = api("column_edit_detail")(column(), geometry(), 0, {"x_mm": 113})
    member["main_rows"][0]["per_face_count"] = 27
    return member


def test_regeneration_preview_is_detached_and_apply_preserves_detail_mode():
    member = changed_detail()
    before = deepcopy(member)
    preview = api("column_regeneration_preview")(member, geometry())
    assert len(preview["old_bars"]) == 58
    assert len(preview["candidate_bars"]) == 54
    assert preview["old_bars"][0]["x_mm"] == 113
    assert preview["candidate_bars"][0]["x_mm"] == 108
    assert preview["basis"]["inputs"]["main_rows"][0]["per_face_count"] == 27
    assert member == before  # Cancelling the dialog merely discards this preview.
    applied = api("column_apply_regeneration")(member, geometry(), preview)
    assert member == before and applied["position_mode"] == "指定"
    assert len(applied["manual_positions"]) == 54
    assert api("column_detail_status")(applied, geometry()) == "一致"
    applied["main_rows"][0]["per_face_count"] = 25
    assert api("column_detail_status")(applied, geometry()) == "基本条件変更"
    assert len(model.member_preview("柱", applied, geometry())[0]) == 54


@pytest.mark.parametrize("change", ["member", "geometry", "preview"])
def test_regeneration_rejects_stale_source_or_modified_preview_without_mutation(change):
    member = changed_detail()
    shape = geometry()
    preview = api("column_regeneration_preview")(member, shape)
    if change == "member":
        member["materials"]["main"] = "SD345"
    elif change == "geometry":
        shape["width_mm"] = shape["cross_mm"] = 4600
    else:
        preview["candidate_bars"][0]["x_mm"] = 109
    before = deepcopy(member)
    with pytest.raises(model.EditorError, match="変更|再生成|再配置"):
        api("column_apply_regeneration")(member, shape, preview)
    assert member == before


def test_explicit_auto_switch_preserves_archived_detail_and_explicit_restore():
    member = changed_detail()
    preview = api("column_regeneration_preview")(member, geometry())
    automatic = api("column_apply_regeneration")(member, geometry(), preview, to_auto=True)
    assert automatic["position_mode"] == "基本"
    assert automatic["manual_positions"] == member["manual_positions"]
    assert automatic["manual_basis"] == member["manual_basis"]
    assert len(model.member_preview("柱", automatic, geometry())[0]) == 54
    restored = api("column_restore_detail")(automatic, geometry())
    assert automatic["position_mode"] == "基本"
    assert restored["position_mode"] == "指定"
    assert restored["manual_positions"] == member["manual_positions"]
    assert api("column_detail_status")(restored, geometry()) == "基本条件変更"
    assert model.member_preview("柱", restored, geometry())[0][0]["x_mm"] == 113


def test_regeneration_failure_leaves_existing_detail_and_parameters_unchanged():
    member = changed_detail()
    member["main_rows"][0]["distribution"]["pitch_mm"] = None
    before = deepcopy(member)
    with pytest.raises(model.EditorError, match="未入力|未完|不完全"):
        api("column_regeneration_preview")(member, geometry())
    assert member == before
    member["main_rows"][0]["distribution"]["pitch_mm"] = 1000
    before = deepcopy(member)
    with pytest.raises(model.EditorError):
        api("column_regeneration_preview")(member, geometry())
    assert member == before


def test_regeneration_can_repair_detail_outside_changed_dimensions_but_restore_cannot():
    member = api("column_edit_detail")(column(), geometry(), 0, {"x_mm": 113})
    member["main_rows"][0]["per_face_count"] = 3
    smaller = dict(geometry(), width_mm=1000, cross_mm=1000)
    with pytest.raises(model.EditorError):
        model.member_preview("柱", member, smaller)
    preview = api("column_regeneration_preview")(member, smaller)
    assert len(preview["old_bars"]) == 58 and len(preview["candidate_bars"]) == 6
    replaced = api("column_apply_regeneration")(member, smaller, preview)
    assert len(model.member_preview("柱", replaced, smaller)[0]) == 6
    automatic = api("column_apply_regeneration")(member, smaller, preview, to_auto=True)
    with pytest.raises(model.EditorError):
        api("column_restore_detail")(automatic, smaller)


def test_regeneration_of_legacy_detail_creates_basis_only_on_apply():
    member = column()
    member.update(position_mode="指定", manual_positions=[
        {"x_mm": 100, "y_mm": 100, "diameter_mm": 20, "material": None}])
    preview = api("column_regeneration_preview")(member, geometry())
    assert "manual_basis" not in member
    applied = api("column_apply_regeneration")(member, geometry(), preview)
    assert applied["manual_basis"]["generator_version"] == 1
    assert all(row["material"] == "SD390" for row in applied["manual_positions"])


def test_explicit_legacy_hoop_switch_removes_only_new_source_and_keeps_version_two():
    member = column()
    member["column_hoops"] = hoops()
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 22,
                            "sets": 1, "start_mm": 200, "end_mm": 2000,
                            "future_zone": [None, 0]}]
    member["future_member"] = {"keep": [None, 0]}
    detailed = api("column_edit_detail")(member, geometry(), 0, {"x_mm": 113})
    source = document(detailed)
    before = deepcopy(source)
    candidate = model.load_member(source, "柱")
    del candidate["column_hoops"]
    del candidate["future_member"]  # Unknown fields retain the existing patch contract.
    saved = model.patch_member(source, "柱", candidate)
    assert "column_hoops" not in saved["鉄筋"]["柱"]
    assert saved["鉄筋"]["version"] == 2
    assert saved["鉄筋"]["柱"]["band_rows"] == member["band_rows"]
    assert saved["鉄筋"]["柱"]["future_member"] == member["future_member"]
    assert saved["鉄筋"]["柱"]["manual_positions"] == detailed["manual_positions"]
    assert saved["鉄筋"]["柱"]["manual_basis"] == detailed["manual_basis"]
    assert source == before


@pytest.mark.parametrize("direction,width,height", [("線路", 1000, 3000), ("直角", 3000, 1000)])
def test_new_distribution_cover_is_bounded_only_by_normal_section_depth(direction, width, height):
    member = column()
    member["main_rows"][0].update(face_direction=direction, diameter_mm=20,
        per_face_count=1, center_mm=600,
        distribution={"mode": "中央ピッチ", "pitch_mm": None})
    shape = {"width_mm": width, "height_mm": height, "cross_mm": width, "rail_mm": height}
    result = api("column_layout")(member, shape)
    expected = {(500, 600), (500, 2400)} if direction == "線路" else {(600, 500), (2400, 500)}
    assert {(bar["x_mm"], bar["y_mm"]) for bar in result["bars"]} == expected
    assert result["complete"]


def test_explicit_null_equal_distribution_endpoints_stays_incomplete():
    member = column()
    member["main_rows"][0].update(endpoints=None,
        distribution={"mode": "等分", "edge_center_mm": 108})
    before = deepcopy(member)
    result = api("column_layout")(member, geometry())
    assert not result["complete"] and result["bars"] == []
    assert "endpoints" in result["issues"][0]["fields"]
    assert member == before


def test_restore_rejects_virtual_empty_positions_when_no_detail_was_ever_saved():
    member = column()
    before = deepcopy(member)
    assert member["manual_positions"] == [] and "manual_basis" not in member
    with pytest.raises(model.EditorError, match="退避|保存|詳細"):
        api("column_restore_detail")(member, geometry())
    assert not api("column_has_detail")(member)
    assert member == before


def test_restore_accepts_deliberate_empty_snapshot_and_nonempty_legacy_snapshot():
    empty = api("column_set_detail")(column(), geometry(), [])
    preview = api("column_regeneration_preview")(empty, geometry())
    automatic = api("column_apply_regeneration")(empty, geometry(), preview, to_auto=True)
    assert api("column_has_detail")(automatic)
    restored = api("column_restore_detail")(automatic, geometry())
    assert restored["manual_positions"] == [] and "manual_basis" in restored
    assert model.member_preview("柱", restored, geometry())[0] == []
    legacy = column()
    legacy["manual_positions"] = [{"x_mm": 100, "y_mm": 100, "diameter_mm": 20, "material": None}]
    assert api("column_has_detail")(legacy)
    restored = api("column_restore_detail")(legacy, geometry())
    assert "manual_basis" not in restored
    assert model.member_preview("柱", restored, geometry())[0][0]["material"] == "SD390"


def test_regenerated_basis_replaces_old_source_snapshot_atomically_on_save():
    member = column()
    member["column_hoops"] = hoops()
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 22, "sets": 1}]
    member["future_member"] = {"keep": [None, 0]}
    detailed = api("column_edit_detail")(member, geometry(), 0, {"x_mm": 113})
    source = document(detailed)
    candidate = model.load_member(source, "柱")
    del candidate["column_hoops"]
    preview = api("column_regeneration_preview")(candidate, geometry())
    regenerated = api("column_apply_regeneration")(candidate, geometry(), preview)
    assert "column_hoops" not in regenerated["manual_basis"]["inputs"]
    assert "band_rows" in regenerated["manual_basis"]["inputs"]
    saved = model.patch_member(source, "柱", regenerated)
    reloaded = model.load_member(json.loads(json.dumps(saved, ensure_ascii=False)), "柱")
    assert reloaded["manual_basis"] == regenerated["manual_basis"]
    assert api("column_detail_status")(reloaded, geometry()) == "一致"
    assert reloaded["future_member"] == member["future_member"]
    assert "column_hoops" in source["鉄筋"]["柱"]["manual_basis"]["inputs"]


@pytest.mark.parametrize("facade", ["column_layout", "column_regeneration_preview"])
def test_large_integral_float_layer_is_unresolved_without_recursion(facade):
    member = column()
    member["column_hoops"] = hoops()
    member["main_rows"][0].update(layer=1e20, cover_mode="自動", center_mm=None, clear_gap_mm=40)
    before = deepcopy(member)
    if facade == "column_layout":
        result = api(facade)(member, geometry())
        assert not result["complete"] and result["bars"] == []
        assert "previous_layer" in result["issues"][0]["fields"]
    else:
        with pytest.raises(model.EditorError, match="未完|未入力|前段"):
            api(facade)(member, geometry())
    assert member == before


@pytest.mark.parametrize("facade", ["column_layout", "column_regeneration_preview"])
def test_valid_deep_layer_chain_generates_all_bars_without_recursion(facade):
    member = column()
    member["pure_cover_mm"] = 0
    member["column_hoops"] = {"enclosing_diameter_mm": 1, "direction_rows": []}
    template = member["main_rows"][0]
    member["main_rows"] = [dict(template, diameter_mm=1, per_face_count=1,
        layer=layer, cover_mode="自動", center_mm=None, clear_gap_mm=0,
        distribution={"mode": "中央ピッチ", "pitch_mm": None})
        for layer in range(1001, 0, -1)]
    before = deepcopy(member)
    result = api(facade)(member, geometry())
    bars = result["bars"] if facade == "column_layout" else result["candidate_bars"]
    if facade == "column_layout":
        assert result["complete"] and result["issues"] == []
        assert result["centers"] == [layer + .5 for layer in range(1001, 0, -1)]
    assert len(bars) == 2002
    assert {(bar["x_mm"], bar["y_mm"]) for bar in bars} == {
        (2250, center) for layer in range(1, 1002)
        for center in (layer + .5, 2700 - layer - .5)}
    assert member == before


@pytest.mark.parametrize("field,value", [
    ("column_hoops", None), ("column_hoops", []),
    ("direction_rows", None), ("direction_rows", {}), ("direction_rows", [None]),
    ("distribution", None), ("distribution", []), ("distribution", "中央ピッチ"),
])
def test_load_rejects_malformed_column_containers_before_widget_construction(field, value):
    member = column()
    member["column_hoops"] = hoops()
    if field == "column_hoops":
        member[field] = value
    elif field == "direction_rows":
        member["column_hoops"][field] = value
    else:
        member["main_rows"][0][field] = value
    source = document(member)
    before = deepcopy(source)
    with pytest.raises(model.EditorError, match="配列|帯鉄筋|オブジェクト"):
        model.load_member(source, "柱")
    with pytest.raises(model.EditorError, match="配列|帯鉄筋|オブジェクト"):
        model.validate_member_shape("柱", member)
    assert source == before


def test_shape_loading_preserves_absent_and_incomplete_column_containers():
    legacy = column()
    del legacy["main_rows"][0]["distribution"]
    legacy_source = document(legacy, version=1)
    before = deepcopy(legacy_source)
    loaded = model.load_member(legacy_source, "柱")
    assert "distribution" not in loaded["main_rows"][0]
    assert "column_hoops" not in loaded
    assert legacy_source == before
    incomplete = column()
    incomplete["main_rows"][0]["distribution"] = {}
    for hoops_value in ({}, {"direction_rows": []}, {"direction_rows": [{}]}):
        incomplete["column_hoops"] = hoops_value
        source = document(incomplete)
        before = deepcopy(source)
        model.validate_member_shape("柱", incomplete)
        loaded = model.load_member(source, "柱")
        assert loaded["main_rows"][0]["distribution"] == {}
        assert loaded["column_hoops"] == hoops_value
        assert source == before

