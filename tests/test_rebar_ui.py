"""Reinforcement editing joins the existing Tk editor's save transaction.

The view's cells use local member paths and get/set controls. Numeric table
controls are real SheetCell instances. Diagram tags expose physical bars and
their source rows, rather than testing implementation-specific widget trees.
"""

from copy import deepcopy
import json

import pytest

from src import editor_gui as gui
from src import editor_model, rebar_model
from src.editor_grid import SheetCell
from test_editor_gui import (
    app, controlled_calculation, field, paste_cells, pending_text,
    withdraw_without_focus,
)


def install_document(app, data):
    """Use only the fixture's temporary input and its normal document loader."""
    editor_model.update_formula_snapshots(data)
    app.document.path.write_bytes(editor_model.encode(data))
    app.document = editor_model.EditorDocument.open(app.document.path)
    app.refresh_tree(("下部構造",))


def invented_document(app, *, members=None):
    data = deepcopy(app.document.data)
    data.pop("鉄筋", None)
    dimensions = data["下部構造"]["寸法"]
    dimensions["側面"].update(B1=4.3, B4=0.4, B5=0.6, B6=2.0,
                               B7=0.35, B8=4.6, B9=0.5)
    dimensions["正面"].update(W6=1.2, W7=0.6, W8=5.2, W9=0.7)
    dimensions["高さ"].update(H2=0.45, H3=0.3, H4=3.4, H5=0.25, H6=0.8)
    if members is not None:
        data["鉄筋"] = {"version": 1, "future_schema": {"null": None, "zero": 0}, **members}
    return data


def column_member(*, automatic=False, paired=False):
    member = rebar_model.blank_member("柱")
    member.update(pure_cover_mm=40, concrete_strength_mpa=30)
    member["materials"] = {"main": "SD345", "transverse": "SD295"}
    row = {
        "face_direction": "線路", "layer": 1, "diameter_mm": 20,
        "per_face_count": 4, "endpoints": "含む", "material": None,
        "cover_mode": "自動" if automatic else "指定",
        "center_mm": None if automatic else 60, "clear_gap_mm": None,
        "future_row": {"keep": [None, 0]},
    }
    member["main_rows"] = [row]
    if paired:
        other = deepcopy(row)
        other.update(face_direction="直角", per_face_count=3)
        member["main_rows"].append(other)
    member["band_rows"] = [{
        "type": "外巻き", "direction": "線路", "diameter_mm": 10,
        "sets": 1, "pitch_mm": 150, "start_mm": 0, "end_mm": 2000,
        "material": None,
    }]
    return member


def open_rebar(app):
    # The new API is resolved during execution, never at collection time.
    page = getattr(gui, "REBAR_PAGE")
    assert page in app.paths.values()
    app.select_path(page)
    app.root.update()
    assert app.current_path is page
    return app.rebar_view


def cell(view, *path):
    assert path in view.cells, (
        f"Missing reinforcement cell {path!r}; member={view.member!r}, "
        f"group={view.group!r}, disposed={view._disposed!r}, "
        f"current_page={view.app.current_path!r}, active_view={view.app.rebar_view is view}, "
        f"available_keys={list(view.cells)!r}"
    )
    control = view.cells[path]
    assert callable(control.get) and callable(control.set)
    return control


def put(app, view, path, text):
    if len(path) >= 3 and path[0] in ("main_rows", "side_rows", "band_rows", "manual_positions"):
        view.select_row(path[0], path[1])
        app.root.update()
    cell(view, *path).set(text)
    app.root.update()


def saved(app):
    return json.loads(app.document.path.read_text(encoding="utf-8"))


def reopen(app, monkeypatch):
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kw: str(app.document.path))
    assert app.open_file()


def bar_locations(view):
    return sorted((bar["x_mm"], bar["y_mm"], bar["diameter_mm"])
                  for bar in view.preview_bars)


def assert_real_diagram(view):
    items = view.preview_canvas.find_withtag("rebar")
    circles = [item for item in items if view.preview_canvas.type(item) == "oval"]
    lines = [item for item in items if view.preview_canvas.type(item) == "line"]
    assert len(circles) == len(view.preview_bars)
    if view.member == "フーチング":
        assert len(lines) == len(view.preview_lines)
        assert set(lines) == set(view.preview_canvas.find_withtag("rebar-line"))
    else:
        assert len(circles) == len(items)
    assert view.preview_canvas.find_withtag("section-outline")


def visible_text(widget):
    values = []
    if "text" in widget.keys():
        values.append(str(widget.cget("text")))
    for child in widget.winfo_children():
        values.extend(visible_text(child))
    return values


def test_absent_reinforcement_visit_all_members_groups_and_save_is_exact_noop(app):
    assert "鉄筋" not in app.document.data
    before = app.document.path.read_bytes()
    original = deepcopy(app.document.data)
    view = open_rebar(app)
    assert view.member == "柱"
    for member in ("梁", "柱", "フーチング"):
        assert view.select_member(member)
        for group in ("main", "bands", "placement"):
            assert view.select_group(group)
            app.root.update()
            assert view.preview_bars == [], "Layout defaults must not create reinforcement"
            if member == "フーチング":
                assert view.preview_lines == []
            assert not app.dirty
    app.select_path(("地盤データ",))
    assert app.current_path == ("地盤データ",)
    assert app.save()
    assert app.document.data == original
    assert app.document.path.read_bytes() == before
    assert "鉄筋" not in saved(app)


def test_reinforcement_page_remains_available_without_lower_structure(app):
    install_document(app, {})
    view = open_rebar(app)
    assert view.member == "柱"
    assert view.preview_geometry is None
    assert view.preview_bars == []
    assert "寸法" in view.preview_error
    assert not app.dirty and app.document.data == {}


@pytest.mark.parametrize("member", ["梁", "柱", "フーチング"])
def test_member_edits_survive_member_screen_save_reopen_and_keep_extensions(app, monkeypatch, member):
    stored = rebar_model.blank_member(member)
    stored["future_member"] = {"nullable": None, "zero": 0}
    stored["main_rows"][0]["future_row"] = {"retain": "001"}
    data = invented_document(app, members={member: stored})
    data["future_root"] = {"keep": [None, 0]}
    install_document(app, data)
    view = open_rebar(app)
    assert view.select_member(member)
    put(app, view, ("pure_cover_mm",), "0")
    put(app, view, ("concrete_strength_mpa",), "35")
    put(app, view, ("materials", "main"), "SD345")
    put(app, view, ("main_rows", 0, "diameter_mm"), "16")
    quantity = "pitch_mm" if member == "フーチング" else "per_face_count" if member == "柱" else "count"
    put(app, view, ("main_rows", 0, quantity), "180" if member == "フーチング" else "4")
    assert view.select_member("梁" if member != "梁" else "柱")
    app.select_path(("上部構造",))
    assert app.save()
    reopen(app, monkeypatch)
    view = open_rebar(app)
    assert view.select_member(member)
    result = saved(app)
    loaded = result["鉄筋"][member]
    assert loaded["pure_cover_mm"] == 0 and type(loaded["pure_cover_mm"]) is int
    assert loaded["concrete_strength_mpa"] == 35
    assert loaded["materials"]["main"] == "SD345"
    assert loaded["materials"]["transverse"] is None
    assert loaded["main_rows"][0]["diameter_mm"] == 16
    assert loaded["main_rows"][0][quantity] == (180 if member == "フーチング" else 4)
    assert loaded["main_rows"][0]["center_mm"] is None
    assert loaded["main_rows"][0]["future_row"] == {"retain": "001"}
    assert loaded["future_member"] == {"nullable": None, "zero": 0}
    assert result["future_root"] == {"keep": [None, 0]}
    assert result["鉄筋"]["future_schema"] == {"null": None, "zero": 0}
    assert not app.dirty


@pytest.mark.parametrize("member", ["梁", "柱", "フーチング"])
def test_sparse_existing_member_only_materializes_changed_leaf(app, member):
    stored = {"pure_cover_mm": 70, "future": {"null": None, "zero": 0}}
    install_document(app, invented_document(app, members={member: stored}))
    view = open_rebar(app)
    assert view.select_member(member)
    put(app, view, ("concrete_strength_mpa",), "30")
    assert app.save()
    assert saved(app)["鉄筋"][member] == {**stored, "concrete_strength_mpa": 30}


@pytest.mark.parametrize("action", ["member", "screen", "save"])
def test_focusless_pending_main_table_editor_commits_before_actions(app, action):
    install_document(app, invented_document(app, members={"柱": column_member()}))
    view = open_rebar(app)
    control = cell(view, "main_rows", 0, "per_face_count")
    assert isinstance(control, SheetCell)
    pending_text(app, control.sheet, "5", control.row, control.column)
    withdraw_without_focus(app)
    assert app.root.focus_get() is None
    assert control.sheet.MT.text_editor.open
    assert app.dirty
    if action == "member":
        assert view.select_member("梁")
    elif action == "screen":
        app.select_path(("下部構造",))
        assert app.current_path == ("下部構造",)
    else:
        assert app.save()
    assert app.document.data["鉄筋"]["柱"]["main_rows"][0]["per_face_count"] == 5


@pytest.mark.parametrize("bad", ["invalid", "2.5", "-1"])
def test_invalid_pending_reinforcement_blocks_navigation_save_and_partial_updates(app, bad):
    install_document(app, invented_document(app, members={"柱": column_member()}))
    view = open_rebar(app)
    before = deepcopy(app.document.data)
    raw = app.document.path.read_bytes()
    put(app, view, ("concrete_strength_mpa",), "35")
    control = cell(view, "main_rows", 0, "per_face_count")
    pending_text(app, control.sheet, bad, control.row, control.column)
    withdraw_without_focus(app)
    assert not view.select_member("梁")
    assert view.member == "柱"
    assert not view.select_group("bands")
    app.select_path(("地盤データ",))
    assert app.current_path is getattr(gui, "REBAR_PAGE")
    assert not app.save()
    assert app.document.data == before
    assert app.document.path.read_bytes() == raw
    assert cell(view, "concrete_strength_mpa").get() == "35"
    assert cell(view, "main_rows", 0, "per_face_count").get() == bad
    assert view.preview_bars == [] and view.preview_error
    put(app, view, ("main_rows", 0, "per_face_count"), "5")
    assert app.save()
    assert saved(app)["鉄筋"]["柱"]["concrete_strength_mpa"] == 35


def test_clipboard_undo_redo_refresh_draft_and_real_diagram_until_atomic_flush(app):
    install_document(app, invented_document(app, members={"柱": column_member()}))
    app.root.deiconify()
    view = open_rebar(app)
    original = deepcopy(app.document.data)
    before = bar_locations(view)
    assert len(before) == 8
    assert_real_diagram(view)
    control = cell(view, "main_rows", 0, "per_face_count")
    assert isinstance(control, SheetCell)
    control.sheet.select_cell(control.row, control.column)
    control.sheet.copy()
    assert app.root.clipboard_get().strip() == "4"
    paste_cells(app, control.sheet, "5", control.row, control.column)
    app.root.update()
    assert view.draft["main_rows"][0]["per_face_count"] == 5
    assert len(view.preview_bars) == 10
    assert app.document.data == original
    control.sheet.undo()
    app.root.update()
    assert view.draft["main_rows"][0]["per_face_count"] == 4
    assert bar_locations(view) == before
    assert not app.dirty
    control.sheet.redo()
    app.root.update()
    assert len(view.preview_bars) == 10 and app.dirty
    diameter = cell(view, "main_rows", 0, "diameter_mm")
    paste_cells(app, diameter.sheet, "16", diameter.row, diameter.column)
    app.root.update()
    assert all(bar["diameter_mm"] == 16 for bar in view.preview_bars)
    assert app.document.data == original
    assert_real_diagram(view)
    assert app.flush_fields()
    assert app.document.data["鉄筋"]["柱"]["main_rows"][0]["per_face_count"] == 5


def test_selection_highlights_only_actual_bars_belonging_to_selected_row(app):
    install_document(app, invented_document(app, members={"柱": column_member(paired=True)}))
    app.root.deiconify()
    view = open_rebar(app)
    assert len(view.preview_bars) == 10
    view.select_row("main_rows", 0)
    app.root.update()
    canvas = view.preview_canvas
    row_items = set(canvas.find_withtag("rebar:main_rows:0"))
    highlighted = set(canvas.find_withtag("selected")) & set(canvas.find_withtag("rebar"))
    assert row_items and highlighted == row_items
    assert len(row_items) == 8
    assert set(canvas.find_withtag("rebar")) - row_items
    view.select_row("main_rows", 1)
    app.root.update()
    assert set(canvas.find_withtag("selected")) & set(canvas.find_withtag("rebar")) == set(canvas.find_withtag("rebar:main_rows:1"))


def test_preview_tracks_current_geometry_haunch_taper_and_editor_b9_formula(app):
    install_document(app, invented_document(app))
    app.select_path(("下部構造",))
    for group, key, value in (
        ("側面", "B6", "2.4"), ("正面", "W6", "1.6"),
        ("側面", "B1", "4.7"), ("高さ", "H2", "0.6"), ("高さ", "H3", "0.2"),
        ("側面", "B7", "0.4"), ("側面", "B8", "4.8"),
        ("高さ", "H5", "0.3"), ("高さ", "H6", "0.9"),
    ):
        field(app, ("下部構造", "寸法", group, key)).text.set(value)
    view = open_rebar(app)
    assert view.preview_geometry["width_mm"] == 1600
    assert view.preview_geometry["height_mm"] == 2400
    assert view.select_member("梁")
    assert view.preview_geometry["width_mm"] == 4700
    assert view.preview_geometry["height_mm"] == pytest.approx(800)
    assert view.preview_geometry["haunch_mm"] == 200
    assert view.preview_geometry["lower_width_mm"] == pytest.approx(3700)
    outline = view.preview_canvas.find_withtag("section-outline")
    assert len(outline) == 1 and len(view.preview_canvas.coords(outline[0])) >= 12
    assert view.select_member("フーチング")
    assert view.preview_geometry["width_mm"] == pytest.approx(5600)
    assert view.preview_geometry["height_mm"] == pytest.approx(1200)
    assert view.preview_geometry["taper_mm"] == 300
    assert view.preview_geometry["top_left_mm"] == 400
    assert app.document.data["下部構造"]["寸法"]["側面"]["B9"] == 0.4
    outline = view.preview_canvas.find_withtag("section-outline")
    assert len(outline) == 1 and len(view.preview_canvas.coords(outline[0])) >= 12


def test_automatic_and_explicit_center_refresh_real_points_and_show_ambiguous_zones(app):
    member = column_member(automatic=True)
    install_document(app, invented_document(app, members={"柱": member}))
    view = open_rebar(app)
    assert view.effective_centers == [60]
    assert min(bar["y_mm"] for bar in view.preview_bars) == 60
    put(app, view, ("pure_cover_mm",), "50")
    assert view.effective_centers == [70]
    assert min(bar["y_mm"] for bar in view.preview_bars) == 70
    put(app, view, ("main_rows", 0, "cover_mode"), "指定")
    put(app, view, ("main_rows", 0, "center_mm"), "90")
    assert view.effective_centers == [90]
    assert min(bar["y_mm"] for bar in view.preview_bars) == 90
    put(app, view, ("main_rows", 0, "cover_mode"), "自動")
    assert view.effective_centers == [70]
    assert view.select_group("bands")
    view.add_row("band_rows")
    for key, value in (("type", "外巻き"), ("diameter_mm", "13"),
                       ("start_mm", "2000"), ("end_mm", "3000")):
        put(app, view, ("band_rows", 1, key), value)
    assert view.select_group("main")
    assert view.effective_centers == [None]
    assert view.preview_bars == []
    assert "外帯筋径" in view.preview_error and "指定" in view.preview_error
    assert cell(view, "main_rows", 0, "center_mm").get() == "90"


def test_beam_exposes_shape_layer_side_columns_and_automatic_second_layer_gap(app):
    member = rebar_model.blank_member("梁")
    member.update(pure_cover_mm=40, concrete_strength_mpa=30)
    member["main_rows"] = [
        {"face": "上", "bar_type": "ループ筋", "layer": 1, "diameter_mm": 32,
         "count": None, "cover_mode": "自動", "center_mm": None, "clear_gap_mm": None},
        {"face": "上", "bar_type": "直筋", "layer": 1, "diameter_mm": 20,
         "count": 2, "cover_mode": "自動", "center_mm": None, "clear_gap_mm": None},
        {"face": "上", "bar_type": "直筋", "layer": 2, "diameter_mm": 16,
         "count": 2, "cover_mode": "自動", "center_mm": None, "clear_gap_mm": 25},
    ]
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 10, "sets": 1, "pitch_mm": 150}]
    member["side_rows"] = [{"diameter_mm": 16, "per_face_count": 2, "columns": 2,
                            "column_pitch_mm": 35, "start_mm": 250, "pitch_mm": 150,
                            "stirrup_position": "内側"}]
    install_document(app, invented_document(app, members={"梁": member}))
    view = open_rebar(app)
    assert view.select_member("梁")
    assert cell(view, "main_rows", 0, "bar_type").get() == "ループ筋"
    assert cell(view, "main_rows", 1, "bar_type").get() == "直筋"
    assert cell(view, "main_rows", 2, "layer").get() == "2"
    assert view.effective_centers == [66, 60, 103]
    view.select_row("side_rows", 0)
    for key in ("per_face_count", "columns", "column_pitch_mm", "start_mm", "pitch_mm", "stirrup_position"):
        assert ("side_rows", 0, key) in view.cells
    assert view.preview_bars
    assert_real_diagram(view)
    put(app, view, ("main_rows", 2, "clear_gap_mm"), "35")
    assert view.effective_centers == [66, 60, 113]
    before = deepcopy(view.draft["side_rows"][0])
    put(app, view, ("side_rows", 0, "stirrup_position"), "外側")
    assert view.draft["side_rows"][0] == {**before, "stirrup_position": "外側"}


def test_beam_loop_and_straight_share_one_alternating_equal_spacing_set(app):
    member = rebar_model.blank_member("梁")
    member["pure_cover_mm"] = 40
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 10, "sets": 1, "pitch_mm": 150}]
    member["main_rows"] = [
        {"face": "上", "bar_type": "ループ筋", "layer": 1, "diameter_mm": 32,
         "count": 2, "cover_mode": "自動", "center_mm": None, "clear_gap_mm": None},
        {"face": "上", "bar_type": "直筋", "layer": 1, "diameter_mm": 20,
         "count": 2, "cover_mode": "自動", "center_mm": None, "clear_gap_mm": None},
    ]
    install_document(app, invented_document(app, members={"梁": member}))
    view = open_rebar(app)
    assert view.select_member("梁")
    ordered = sorted(view.preview_bars, key=lambda bar: bar["x_mm"])
    assert len(ordered) == 4
    assert [bar["row_indices"] for bar in ordered] == [[0], [1], [0], [1]]
    assert [bar["y_mm"] for bar in ordered] == [66, 60, 66, 60]
    differences = [right["x_mm"] - left["x_mm"] for left, right in zip(ordered, ordered[1:])]
    assert differences == pytest.approx([differences[0]] * 3)
    assert "同じ段の全本数を等間隔に配置" in "\n".join(visible_text(app.root))
    assert_real_diagram(view)


def test_beam_multiple_side_columns_remain_partial_until_column_pitch_is_entered(app):
    member = rebar_model.blank_member("梁")
    member["pure_cover_mm"] = 40
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 10, "sets": 1, "pitch_mm": 150}]
    member["side_rows"] = [{"diameter_mm": 16, "per_face_count": 2, "columns": 2,
                            "column_pitch_mm": None, "start_mm": 250, "pitch_mm": 150,
                            "stirrup_position": "内側"}]
    install_document(app, invented_document(app, members={"梁": member}))
    view = open_rebar(app)
    assert view.select_member("梁")
    assert view.preview_bars == []
    assert "列の芯間隔" in view.preview_error
    assert app.save()  # Incomplete placement stays saveable.
    put(app, view, ("side_rows", 0, "column_pitch_mm"), "35")
    assert len(view.preview_bars) == 4
    assert_real_diagram(view)


def test_footing_has_four_primary_rows_layers_order_and_distinct_transverse_spacings(app):
    install_document(app, invented_document(app))
    view = open_rebar(app)
    assert view.select_member("フーチング")
    assert {(row["direction"], row["face"]) for row in view.draft["main_rows"]} == {
        ("線路", "上"), ("線路", "下"), ("直角", "上"), ("直角", "下"),
    }
    assert len(view.draft["main_rows"]) == 4
    for index in range(4):
        view.select_row("main_rows", index)
        assert ("main_rows", index, "layers") in view.cells
        assert ("main_rows", index, "stack_order") in view.cells
    put(app, view, ("main_rows", 0, "layers"), "2")
    put(app, view, ("main_rows", 0, "stack_order"), "1")
    put(app, view, ("main_rows", 2, "stack_order"), "2")
    assert view.select_group("bands")
    view.add_row("band_rows")
    for key in ("distribution_mode", "width_pitch_mm", "density_per_m", "pitch_mm", "sets"):
        assert ("band_rows", 0, key) in view.cells
    for key, value in (("distribution_mode", "間隔"), ("width_pitch_mm", "250"),
                       ("density_per_m", "4"), ("pitch_mm", "150"), ("sets", "2")):
        put(app, view, ("band_rows", 0, key), value)
    assert app.save()
    stored = saved(app)["鉄筋"]["フーチング"]
    assert stored["main_rows"][0]["layers"] == 2
    assert stored["main_rows"][2]["stack_order"] == 2
    assert stored["band_rows"][0]["width_pitch_mm"] == 250
    assert stored["band_rows"][0]["density_per_m"] == 4
    assert stored["band_rows"][0]["pitch_mm"] == 150


def test_column_transverse_zones_sets_and_effective_legs_are_explicit(app):
    install_document(app, invented_document(app, members={"柱": column_member()}))
    view = open_rebar(app)
    assert view.select_group("bands")
    for key in ("type", "direction", "diameter_mm", "sets", "pitch_mm", "start_mm", "end_mm"):
        assert ("band_rows", 0, key) in view.cells
    put(app, view, ("band_rows", 0, "sets"), "3")
    assert cell(view, "band_rows", 0, "effective_legs").get() == "6"
    assert app.save()
    row = saved(app)["鉄筋"]["柱"]["band_rows"][0]
    assert row["sets"] == 3 and row["start_mm"] == 0 and row["end_mm"] == 2000
    assert "effective_legs" not in row


def test_fractional_transverse_sets_show_equivalent_legs_and_allow_explicit_override(app):
    install_document(app, invented_document(app, members={"柱": column_member()}))
    view = open_rebar(app)
    assert view.select_group("bands")
    assert ("band_rows", 0, "legs_mode") in view.cells
    assert "1組＝2脚相当" in "\n".join(visible_text(app.root))
    put(app, view, ("band_rows", 0, "sets"), "5.5")
    assert cell(view, "band_rows", 0, "effective_legs").get() == "11"
    assert app.save()
    assert saved(app)["鉄筋"]["柱"]["band_rows"][0]["sets"] == 5.5
    put(app, view, ("band_rows", 0, "legs_mode"), "指定")
    put(app, view, ("band_rows", 0, "effective_legs"), "10")
    assert app.save()
    row = saved(app)["鉄筋"]["柱"]["band_rows"][0]
    assert row["sets"] == 5.5 and row["legs_mode"] == "指定" and row["effective_legs"] == 10
    put(app, view, ("band_rows", 0, "legs_mode"), "自動")
    assert cell(view, "band_rows", 0, "effective_legs").get() == "11"
    assert app.save()
    assert saved(app)["鉄筋"]["柱"]["band_rows"][0]["effective_legs"] == 10


def test_footing_explicit_row_centers_and_layer_gaps_make_physical_points(app):
    member = rebar_model.blank_member("フーチング")
    member["main_rows"][0].update(
        diameter_mm=16, pitch_mm=250, layers=1, stack_order=1,
        cover_mode="指定", center_mm=200,
    )
    # A rail-direction cut shows cross bars as circles and rail bars in plane.
    member["main_rows"][2].update(
        diameter_mm=20, pitch_mm=250, layers=2, stack_order=1,
        cover_mode="指定", center_mm=300, clear_gap_mm=25,
    )
    member["main_rows"][3].update(
        diameter_mm=20, pitch_mm=250, layers=1, stack_order=1,
        cover_mode="指定", center_mm=100,
    )
    install_document(app, invented_document(app, members={"フーチング": member}))
    view = open_rebar(app)
    assert view.select_member("フーチング")
    assert view.preview_geometry["direction"] == "線路"
    assert "断面方向" in "\n".join(visible_text(app.root))
    before_direction_change = deepcopy(app.document.data)
    assert not app.dirty
    assert view.select_direction("直角")
    assert view.select_direction("線路")
    assert app.document.data == before_direction_change and not app.dirty
    assert view.preview_bars
    assert all(0 not in bar["row_indices"] for bar in view.preview_bars)
    top = [bar for bar in view.preview_bars if 2 in bar["row_indices"]]
    assert {bar["y_mm"] for bar in top} == {300, 345}
    assert any(0 in line["row_indices"] for line in view.preview_lines)
    assert view.preview_canvas.find_withtag("rebar-line")
    assert_real_diagram(view)
    put(app, view, ("main_rows", 2, "center_mm"), "330")
    top = [bar for bar in view.preview_bars if 2 in bar["row_indices"]]
    assert {bar["y_mm"] for bar in top} == {330, 375}
    assert view.select_direction("直角")
    app.root.update()
    assert view.preview_geometry["direction"] == "直角"
    assert view.preview_geometry["width_mm"] == pytest.approx(6500)
    assert view.preview_bars and all(0 in bar["row_indices"] for bar in view.preview_bars)
    assert {bar["y_mm"] for bar in view.preview_bars} == {200}
    assert any(2 in line["row_indices"] for line in view.preview_lines)
    assert all(0 not in line["row_indices"] for line in view.preview_lines)
    assert_real_diagram(view)


def test_add_remove_rows_preserve_unknowns_and_do_not_mutate_document_until_flush(app):
    install_document(app, invented_document(app, members={"柱": column_member()}))
    view = open_rebar(app)
    before = deepcopy(app.document.data)
    view.add_row("main_rows")
    assert len(view.draft["main_rows"]) == 2
    view.delete_row("main_rows", 1)
    assert len(view.draft["main_rows"]) == 1
    assert view.draft["main_rows"][0]["future_row"] == {"keep": [None, 0]}
    assert app.document.data == before
    assert not app.dirty


def test_column_manual_positions_keep_basic_and_override_representations_across_reopen(app, monkeypatch):
    install_document(app, invented_document(app, members={"柱": column_member()}))
    view = open_rebar(app)
    basic = bar_locations(view)
    assert view.select_group("placement")
    assert view.copy_basic_positions()
    assert view.draft["position_mode"] == "指定"
    assert len(view.draft["manual_positions"]) == len(basic)
    original_x = view.draft["manual_positions"][0]["x_mm"]
    put(app, view, ("manual_positions", 0, "x_mm"), str(original_x + 5))
    manual = bar_locations(view)
    assert manual != basic
    assert any(x == original_x + 5 for x, y, diameter in manual)
    assert view.select_group("main")
    put(app, view, ("main_rows", 0, "per_face_count"), "5")
    assert bar_locations(view) == manual
    assert app.save()
    reopen(app, monkeypatch)
    view = open_rebar(app)
    assert bar_locations(view) == manual
    assert view.select_group("placement")
    assert view.draft["position_mode"] == "指定"
    assert view.column_editor.begin_regeneration(to_auto=True)
    assert view.column_editor.apply_regeneration()
    assert len(view.preview_bars) == 10
    assert len(view.draft["manual_positions"]) == len(basic)
    assert app.save()
    reopen(app, monkeypatch)
    view = open_rebar(app)
    assert len(view.preview_bars) == 10
    assert view.draft["manual_positions"][0]["x_mm"] == original_x + 5
    assert view.draft["main_rows"][0]["per_face_count"] == 5


def test_rebar_only_dirty_cancel_close_and_pending_save_as_use_custom_transaction(app, monkeypatch, tmp_path):
    install_document(app, invented_document(app, members={"柱": column_member()}))
    view = open_rebar(app)
    control = cell(view, "main_rows", 0, "per_face_count")
    pending_text(app, control.sheet, "5", control.row, control.column)
    asked = []
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *a, **kw: asked.append(True) or None)
    assert not app.close()
    assert asked == [True] and app.dirty
    destination = tmp_path / "reinforcement-save-as.json"
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kw: str(destination))
    assert app.save_as()
    assert app.document.path == destination
    assert saved(app)["鉄筋"]["柱"]["main_rows"][0]["per_face_count"] == 5
    assert not app.dirty


def test_rebar_invalid_blocks_calculation_and_valid_pending_data_precedes_fake_start(app, monkeypatch):
    install_document(app, invented_document(app, members={"柱": column_member()}))
    controller = controlled_calculation(app)
    controller.output_dir.mkdir(parents=True, exist_ok=True)
    # Opaque old artifacts are only preservation sentinels; no PDFs are made.
    for stem in gui.OUTPUT_STEMS:
        (controller.output_dir / f"{stem}.pdf").write_bytes(b"existing artifact")
        (controller.output_dir / f"{stem}.json").write_bytes(b'{"old": true}')
    before = {path.name: path.read_bytes() for path in controller.output_dir.iterdir()}
    view = open_rebar(app)
    control = cell(view, "main_rows", 0, "per_face_count")
    pending_text(app, control.sheet, "2.5", control.row, control.column)
    assert not app.start_calculation()
    assert controller.calls == [] and not app._calculation_busy
    put(app, view, ("main_rows", 0, "per_face_count"), "4")
    pending_text(app, control.sheet, "5", control.row, control.column)
    observed = []
    original_start = controller.start

    def start_after_save(path, digest):
        observed.append(json.loads(path.read_text(encoding="utf-8"))["鉄筋"]["柱"]["main_rows"][0]["per_face_count"])
        return original_start(path, digest)

    monkeypatch.setattr(controller, "start", start_after_save)
    assert app.start_calculation()
    assert observed == [5]
    assert controller.calls[0][1] == app.document._fingerprint
    assert {path.name: path.read_bytes() for path in controller.output_dir.iterdir()} == before


@pytest.mark.parametrize("malformed", [None, {"main_rows": None}])
def test_malformed_target_member_keeps_current_view_pending_values_and_document(app, monkeypatch, malformed):
    install_document(app, invented_document(app, members={"柱": column_member(), "梁": malformed}))
    view = open_rebar(app)
    original = deepcopy(app.document.data)
    raw = app.document.path.read_bytes()
    put(app, view, ("concrete_strength_mpa",), "35")
    errors = []
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, message, **kw: errors.append(str(message)))
    assert not view.select_member("梁")
    assert view.member == "柱" and view.member_var.get() == "柱"
    assert app.rebar_view is view and not view._disposed
    assert cell(view, "main_rows", 0, "per_face_count").get() == "4"
    assert cell(view, "concrete_strength_mpa").get() == "35"
    assert app.document.data == original and app.document.path.read_bytes() == raw
    assert app.dirty
    assert errors and "梁" in errors[-1]
    assert any(label in errors[-1] for label in ("主筋", "オブジェクト", "配列"))


@pytest.mark.parametrize("malformed", [None, {"main_rows": None}, {"main_rows": [[]]}, {"materials": []}])
def test_malformed_initial_member_is_controlled_unavailable_and_navigation_still_works(app, malformed):
    install_document(app, invented_document(app, members={"柱": malformed}))
    original = deepcopy(app.document.data)
    raw = app.document.path.read_bytes()
    app.select_path(getattr(gui, "REBAR_PAGE"))
    app.root.update()
    assert app.current_path is getattr(gui, "REBAR_PAGE")
    assert app.rebar_view is None
    text = "\n".join(visible_text(app.root))
    assert "表示できません" in text
    assert any(label in text for label in ("主筋", "材料", "オブジェクト", "配列"))
    app.select_path(("地盤データ",))
    assert app.current_path == ("地盤データ",)
    assert app.document.data == original and app.document.path.read_bytes() == raw


def footing_with_invalid_cross_cut(app):
    member = rebar_model.blank_member("フーチング")
    member.update(pure_cover_mm=70, concrete_strength_mpa=30)
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 10, "sets": 1, "pitch_mm": 150}]
    member["main_rows"][0].update(diameter_mm=20, pitch_mm=200, layers=1,
                                  stack_order=1, cover_mode="指定", center_mm=100)
    member["main_rows"][2].update(diameter_mm=20, pitch_mm=200, layers=1,
                                  stack_order=2, cover_mode="指定", center_mm=200)
    data = invented_document(app, members={"フーチング": member})
    dimensions = data["下部構造"]["寸法"]
    dimensions["側面"].update(B7=0, B8=2, B9=0)
    dimensions["正面"].update(W7=0, W8=0.1, W9=0)
    dimensions["高さ"].update(H5=0, H6=1)
    return data


def test_save_checks_both_available_footing_cuts_before_any_document_application(app):
    install_document(app, footing_with_invalid_cross_cut(app))
    view = open_rebar(app)
    assert view.select_member("フーチング")
    assert view.preview_geometry["direction"] == "線路" and view.preview_bars
    original = deepcopy(app.document.data)
    raw = app.document.path.read_bytes()
    put(app, view, ("concrete_strength_mpa",), "35")
    assert not app.save()
    assert app.document.data == original and app.document.path.read_bytes() == raw
    assert cell(view, "concrete_strength_mpa").get() == "35"
    assert app.dirty


def test_calculation_checks_stored_other_direction_before_saving_pending_legacy_edit(app):
    install_document(app, footing_with_invalid_cross_cut(app))
    controller = controlled_calculation(app)
    original = deepcopy(app.document.data)
    raw = app.document.path.read_bytes()
    dimension = field(app, ("下部構造", "寸法", "側面", "B6"))
    dimension.text.set("2.5")
    assert not app.start_calculation()
    assert controller.calls == [] and not app._calculation_busy
    assert app.document.data == original and app.document.path.read_bytes() == raw
    assert dimension.text.get() == "2.5" and app.dirty


@pytest.mark.parametrize("missing", ["missing", None])
def test_genuinely_missing_other_cut_geometry_remains_partial_and_saveable(app, missing):
    data = footing_with_invalid_cross_cut(app)
    front = data["下部構造"]["寸法"]["正面"]
    if missing == "missing":
        del front["W8"]
    else:
        front["W8"] = None
    install_document(app, data)
    view = open_rebar(app)
    assert view.select_member("フーチング")
    put(app, view, ("concrete_strength_mpa",), "35")
    assert app.save()
    assert saved(app)["鉄筋"]["フーチング"]["concrete_strength_mpa"] == 35


def test_active_position_source_badge_remains_visible_on_basic_table(app):
    install_document(app, invented_document(app, members={"柱": column_member()}))
    view = open_rebar(app)
    assert view.select_group("placement")
    assert view.copy_basic_positions()
    assert view.select_group("main")
    assert "使用中：詳細修正" in "\n".join(visible_text(app.root))
    assert view.select_group("placement")
    assert view.column_editor.begin_regeneration(to_auto=True)
    assert view.column_editor.apply_regeneration()
    assert view.select_group("main")
    assert "使用中：自動配置" in "\n".join(visible_text(app.root))


def direction_review_sheet(view):
    from tksheet import Sheet

    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)

    matches = [widget for widget in walk(view.frame) if isinstance(widget, Sheet)
               and list(widget.headers()) == ["芯位置 mm", "径 mm", "本数", "材質"]]
    assert len(matches) == 1, "A visible readonly calculation-direction table is required"
    return matches[0]


def direction_records(view):
    return [(float(row[0]), float(row[1]), int(float(row[2])), row[3])
            for row in direction_review_sheet(view).get_sheet_data()]


def test_column_direction_review_is_readonly_and_follows_active_physical_positions(app):
    install_document(app, invented_document(app, members={"柱": column_member()}))
    view = open_rebar(app)
    assert view.select_group("placement")
    assert view.select_direction("線路")
    assert direction_records(view) == [(60, 20, 4, "SD345"), (1940, 20, 4, "SD345")]
    text = "".join("\n".join(visible_text(app.root)).split())
    assert "方向別の配筋表" in text and "物理本数8本" in text
    table = direction_review_sheet(view)
    before = deepcopy(table.get_sheet_data())
    paste_cells(app, table, "99", 0, 2)
    app.root.update()
    assert table.get_sheet_data() == before and not app.dirty
    assert view.select_direction("直角")
    assert direction_records(view) == [(60, 20, 2, "SD345"), (420, 20, 2, "SD345"),
                                       (780, 20, 2, "SD345"), (1140, 20, 2, "SD345")]
    assert view.copy_basic_positions()
    put(app, view, ("manual_positions", 0, "y_mm"), "80")
    assert view.select_direction("線路")
    assert direction_records(view) == [(60, 20, 3, "SD345"), (80, 20, 1, "SD345"), (1940, 20, 4, "SD345")]


def test_selected_transverse_outline_highlight_tracks_current_cover_input(app):
    install_document(app, invented_document(app, members={"柱": column_member(automatic=True)}))
    view = open_rebar(app)
    assert view.select_group("bands")
    view.select_row("band_rows", 0)
    app.root.update()
    canvas = view.preview_canvas
    items = set(canvas.find_withtag("rebar:band_rows:0"))
    assert items and items <= set(canvas.find_withtag("selected"))
    polygons = [item for item in items if canvas.type(item) == "polygon"]
    assert polygons and all(canvas.itemcget(item, "outline") == "#1674bf" for item in polygons)
    before = [canvas.coords(item) for item in polygons]
    original = deepcopy(app.document.data)
    put(app, view, ("pure_cover_mm",), "50")
    current = [canvas.coords(item) for item in canvas.find_withtag("rebar:band_rows:0") if canvas.type(item) == "polygon"]
    assert current != before
    assert app.document.data == original


def test_common_cover_label_explicitly_references_outside_band_surface(app):
    view = open_rebar(app)
    assert view.member == "柱"
    assert "外帯筋の外面" in "\n".join(visible_text(app.root))


@pytest.mark.parametrize("window", ["980x640", "1360x900"])
@pytest.mark.parametrize("member,manual", [("柱", False), ("梁", False),
                                           ("フーチング", False), ("柱", True)])
def test_linked_section_figure_stays_inside_body_viewport_during_input_and_manual_scroll(app, window, member, manual):
    column = column_member()
    if manual:
        column["position_mode"] = "指定"
        column["manual_positions"] = [
            {"x_mm": x, "y_mm": y, "diameter_mm": 20, "material": "SD345"}
            for y in (100, 300, 500, 700) for x in (100, 300, 500, 700, 900)
        ]
    install_document(app, invented_document(app, members={
        "柱": column, "梁": rebar_model.blank_member("梁"),
        "フーチング": rebar_model.blank_member("フーチング"),
    }))
    app.root.deiconify()
    app.root.geometry(window)
    app.root.update()
    view = open_rebar(app)
    assert view.select_member(member)
    if manual:
        assert view.select_group("placement")
        view.select_row("manual_positions", 19)
        last = cell(view, "manual_positions", 19, "x_mm")
        assert isinstance(last, SheetCell)
        last.sheet.see(last.row, last.column)
    else:
        view.select_row("main_rows", len(view.draft["main_rows"]) - 1)
    app.root.update()
    viewport = app.canvas
    figure = view.preview_canvas
    left, top = viewport.winfo_rootx(), viewport.winfo_rooty()
    right, bottom = left + viewport.winfo_width(), top + viewport.winfo_height()
    figure_bounds = (figure.winfo_rootx(), figure.winfo_rooty(),
                     figure.winfo_rootx() + figure.winfo_width(),
                     figure.winfo_rooty() + figure.winfo_height())
    diagnostic = f"member={member}, manual={manual}, window={window}, viewport={(left, top, right, bottom)}, figure={figure_bounds}"
    assert figure.winfo_ismapped(), diagnostic
    assert figure.winfo_height() >= 140, diagnostic
    assert figure_bounds[0] >= left - 1 and figure_bounds[1] >= top - 1, diagnostic
    assert figure_bounds[2] <= right + 1 and figure_bounds[3] <= bottom + 1, diagnostic


def test_side_effective_offsets_are_visible_live_and_preserve_inactive_override(app):
    import re

    member = rebar_model.blank_member("梁")
    member["pure_cover_mm"] = 70
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 22, "sets": 1, "pitch_mm": 150}]
    member["side_rows"] = [{"diameter_mm": 22, "per_face_count": 4, "columns": 2,
                            "column_pitch_mm": 30, "start_mm": 250, "pitch_mm": 150,
                            "stirrup_position": "内側", "cover_mode": "自動", "center_mm": None}]
    install_document(app, invented_document(app, members={"梁": member}))
    original = deepcopy(app.document.data)
    raw = app.document.path.read_bytes()
    view = open_rebar(app)
    assert view.select_member("梁")
    view.select_row("side_rows", 0)
    app.root.update()

    def assert_offsets(expected):
        text = "\n".join(visible_text(view.details))
        assert "mm" in text
        for value in expected:
            assert re.search(rf"(?<![\d.]){value}(?:\.0+)?(?![\d.])", text), (
                f"Selected side-row readout must show actual offsets {expected} mm; visible={text!r}"
            )
        width = view.preview_geometry["width_mm"]
        actual = {bar["x_mm"] for bar in view.preview_bars
                  if bar.get("family") == "side_rows" and bar["x_mm"] < width / 2}
        assert actual == set(expected)

    def center_entry():
        variable_name = str(cell(view, "side_rows", 0, "center_mm"))
        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)
        matches = [widget for widget in walk(view.details)
                   if isinstance(widget, gui.ttk.Entry)
                   and str(widget.cget("textvariable")) == variable_name]
        assert len(matches) == 1
        return matches[0]

    assert_offsets((103, 133))
    assert center_entry().instate(["readonly"])
    put(app, view, ("pure_cover_mm",), "80")
    assert_offsets((113, 143))
    put(app, view, ("side_rows", 0, "stirrup_position"), "外側")
    assert_offsets((69, 39))
    put(app, view, ("side_rows", 0, "cover_mode"), "指定")
    put(app, view, ("side_rows", 0, "center_mm"), "120")
    assert_offsets((120, 90))
    assert center_entry().instate(["!readonly"])
    put(app, view, ("side_rows", 0, "cover_mode"), "自動")
    assert_offsets((69, 39))
    assert center_entry().instate(["readonly"])
    assert cell(view, "side_rows", 0, "center_mm").get() == "120"
    put(app, view, ("pure_cover_mm",), "")
    assert "未確定" in "\n".join(visible_text(view.details))
    assert view.preview_bars == []
    assert app.document.data == original and app.document.path.read_bytes() == raw
    assert app.flush_fields()
    stored = app.document.data["鉄筋"]["梁"]
    assert stored["pure_cover_mm"] is None
    assert stored["side_rows"][0]["cover_mode"] == "自動"
    assert stored["side_rows"][0]["center_mm"] == 120


@pytest.mark.parametrize("window", ["980x640", "1360x900"])
def test_footing_distribution_labels_fit_their_own_boxes_beside_entries(app, window):
    import math
    from tkinter import font as tkfont

    member = rebar_model.blank_member("フーチング")
    member["pure_cover_mm"] = 50
    member["band_rows"] = [{"type": "外巻き", "direction": "線路", "diameter_mm": 10,
                            "sets": 1, "pitch_mm": 150, "distribution_mode": "間隔",
                            "width_pitch_mm": 250, "density_per_m": 4}]
    install_document(app, invented_document(app, members={"フーチング": member}))
    app.root.deiconify()
    app.root.geometry(window)
    app.root.update()
    view = open_rebar(app)
    assert view.select_member("フーチング")
    assert view.select_group("bands")
    view.select_row("band_rows", 0)
    app.root.update()
    first = view._detail_widgets[("band_rows", 0, "width_pitch_mm")]
    viewport = view.input_canvas
    offset = first.winfo_rooty() - view.inputs.winfo_rooty() - viewport.winfo_height() / 2
    viewport.yview_moveto(max(0, offset) / max(1, view.inputs.winfo_height()))
    app.root.update()
    for key, expected in (("width_pitch_mm", "幅方向の配置間隔 mm"),
                          ("density_per_m", "幅方向の配置密度 組/m")):
        entry = view._detail_widgets[("band_rows", 0, key)]
        labels = [widget for widget in entry.master.winfo_children() if isinstance(widget, gui.ttk.Label)]
        assert len(labels) == 1
        label = labels[0]
        assert str(label.cget("text")) == expected
        specification = label.cget("font") or gui.ttk.Style(app.root).lookup(label.winfo_class(), "font") or "TkDefaultFont"
        font = tkfont.Font(root=app.root, font=specification)
        text_width, box_width = font.measure(expected), label.winfo_width()
        if text_width > box_width:
            wrap_width = float(label.cget("wraplength") or 0)
            assert 0 < wrap_width <= box_width, (
                f"{expected!r} clips at {window}: text={text_width}, box={box_width}, wrap={wrap_width}"
            )
            minimum_lines = math.ceil(text_width / wrap_width)
            minimum_height = minimum_lines * font.metrics("linespace")
            assert label.winfo_reqheight() >= minimum_height
            assert label.winfo_height() >= minimum_height
    body = app.canvas
    figure = view.preview_canvas
    assert figure.winfo_rootx() >= body.winfo_rootx() - 1
    assert figure.winfo_rooty() >= body.winfo_rooty() - 1
    assert figure.winfo_rootx() + figure.winfo_width() <= body.winfo_rootx() + body.winfo_width() + 1
    assert figure.winfo_rooty() + figure.winfo_height() <= body.winfo_rooty() + body.winfo_height() + 1


def test_side_readout_preview_limit_is_controlled_and_preserves_pending_save_transaction(app):
    member = rebar_model.blank_member("梁")
    member["pure_cover_mm"] = 70
    member["band_rows"] = [{"type": "外巻き", "diameter_mm": 22, "sets": 1, "pitch_mm": 150}]
    member["side_rows"] = [{"diameter_mm": 22, "per_face_count": 10001, "columns": 10001,
                            "column_pitch_mm": 30, "start_mm": 250, "pitch_mm": 150,
                            "stirrup_position": "内側", "cover_mode": "自動", "center_mm": None}]
    # This is legal input syntax. Preview must reject its requested count
    # before either side positions or the effective-offset list is allocated.
    rebar_model.validate_member("梁", member)
    install_document(app, invented_document(app, members={"梁": member}))
    original = deepcopy(app.document.data)
    raw = app.document.path.read_bytes()
    view = open_rebar(app)
    assert view.select_member("梁")
    assert view.group == "main"
    view.select_row("side_rows", 0)
    app.root.update()
    assert "上限" in view.preview_error or "10000" in view.preview_error
    assert "未確定" in "\n".join(visible_text(view.details))
    assert view.preview_bars == []
    put(app, view, ("concrete_strength_mpa",), "35")
    assert not app.save()
    assert app.rebar_view is view and not view._disposed
    assert app.current_path is getattr(gui, "REBAR_PAGE") and view.member == "梁"
    assert cell(view, "concrete_strength_mpa").get() == "35" and app.dirty
    assert app.document.data == original and app.document.path.read_bytes() == raw
