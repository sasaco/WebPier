"""Actual WebPier reference through the real Tk editor and temporary save paths."""

from copy import deepcopy
import json
from pathlib import Path

from src import editor_gui as gui
from test_editor_gui import app
from test_rebar_ui import assert_real_diagram, direction_records, open_rebar


PROJECT = Path(__file__).resolve().parents[1]
ORACLE = Path(__file__).parent / "fixtures" / "column_rebar_example2.json"
BAR_FIELDS = ("x_mm", "y_mm", "diameter_mm", "material")


def _physical_records(bars):
    return sorted(tuple(bar[key] for key in BAR_FIELDS) for bar in bars)


def _normalization_changes(before, after, path=()):
    """Record exact existing loader changes separately from reinforcement QA."""
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(before.keys() | after.keys()):
            if key not in before:
                changes.append({"path": [*path, key], "added": after[key]})
            elif key not in after:
                changes.append({"path": [*path, key], "removed": before[key]})
            else:
                changes.extend(_normalization_changes(before[key], after[key], (*path, key)))
        return changes
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [change for index, (old, new) in enumerate(zip(before, after))
                for change in _normalization_changes(old, new, (*path, index))]
    if before != after or type(before) is not type(after):
        return [{"path": list(path), "before": before, "after": after}]
    return []


def _assert_reference_in_live_editor(app, expected):
    view = open_rebar(app)
    assert view.member == "柱" and view.column_editor is not None
    assert view.preview_error == ""
    assert view.preview_geometry["width_mm"] == expected["coordinates"]["width_mm"]
    assert view.preview_geometry["height_mm"] == expected["coordinates"]["height_mm"]
    assert _physical_records(view.preview_bars) == _physical_records(expected["physical_bars"])
    assert len(view.preview_bars) == 76
    assert_real_diagram(view)
    for direction in ("線路", "直角"):
        assert view.select_direction(direction)
        app.root.update()
        assert direction_records(view) == [
            (row["center_mm"], row["diameter_mm"], row["count"], row["material"])
            for row in expected["directional_rows"][direction]
        ]
    member = view.draft
    assert member["position_mode"] == "基本"
    assert member["manual_positions"] == []
    assert "manual_basis" not in member
    for key in ("materials", "concrete_strength_mpa", "pure_cover_mm", "column_hoops"):
        assert member[key] == expected[key]
    assert view.effective_centers == [108, 102]
    return view


def test_actual_webpier_gui_save_save_as_reload_preserves_full_reference(app, tmp_path, monkeypatch, record_property):
    """Never open/write the real input; exercise normal editor paths on its copy."""
    source = PROJECT / "pre" / "input.json"
    source_bytes = source.read_bytes()
    raw = json.loads(source_bytes.decode("utf-8-sig"))
    expected = json.loads(ORACLE.read_text(encoding="utf-8"))
    copied = tmp_path / "actual-webpier-input.json"
    copied.write_bytes(source_bytes)
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kw: str(copied))
    monkeypatch.setattr(gui.messagebox, "askyesnocancel", lambda *args, **kw: False)
    assert app.open_file()
    assert app.document.path == copied

    normalized = deepcopy(app.document.data)
    changes = _normalization_changes(raw, normalized)
    normalization_log = tmp_path / "webpier-load-normalization.json"
    normalization_log.write_text(json.dumps(changes, ensure_ascii=False, indent=2), encoding="utf-8")
    record_property("webpier_load_normalization", json.dumps(changes, ensure_ascii=False))
    record_property("webpier_load_normalization_log", str(normalization_log))
    print(f"WebPier existing loader normalization: {normalization_log}\n{json.dumps(changes, ensure_ascii=False)}")
    assert normalized["鉄筋"] == raw["鉄筋"], "Loader normalization must not alter reinforcement"
    assert normalized["鉄筋"]["version"] == 2
    _assert_reference_in_live_editor(app, expected)
    assert app.document.data == normalized

    assert app.save()
    assert json.loads(copied.read_text(encoding="utf-8")) == normalized
    assert app.document.data == normalized
    destination = tmp_path / "actual-webpier-save-as.json"
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kw: str(destination))
    assert app.save_as()
    assert app.document.path == destination
    assert json.loads(destination.read_text(encoding="utf-8")) == normalized

    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kw: str(destination))
    assert app.open_file()
    assert app.document.data == normalized
    _assert_reference_in_live_editor(app, expected)
    assert app.document.data == normalized
    assert source.read_bytes() == source_bytes
