"""The inputs of the 片持ち梁の照査 (decision 59) in the editor: the support table of the 上部構造 page without the
bearing devices (decision 125), the beam's Dmax and the 梁「断面照査の条件」 group on the 鉄筋 page, and the calculation
page naming 0900・0910 under the nonlinear switch only."""

import tkinter as tk

import pytest

from webpier.core.integrity import load_json
from webpier.gui import app as gui
from webpier.gui import rebar_page

SUPPORT = ("上部構造", "支承データ")
CHECK = "片持ち梁の照査"


@pytest.fixture
def editor(tk_root, input_path, quiet):
    return gui.InputEditor(tk_root, input_path)


def cell(editor, *path):
    return editor.bindings.items[path].cell


def texts(widget):
    for child in widget.winfo_children():
        try:
            yield str(child.cget("text"))
        except tk.TclError:
            pass
        yield from texts(child)


def test_the_support_table_has_no_bearing_devices(editor):
    """Decision 125: the number of bearings and those on the cantilever follow from 上部工反力 and the geometry."""
    assert editor.select("上部構造")
    support = [path for path in editor.bindings.items if path[:2] == SUPPORT]
    assert sorted({path[3] for path in support}) == sorted({"支承名", "摩擦係数_μ", "復旧性制動係数"})
    assert cell(editor, *SUPPORT, "起点側", "支承名").get() == "可動"
    assert not any("ゴム支承" in text or "ストッパー" in text for text in texts(editor.form))
    assert editor.save()
    saved = load_json(editor.document.path.read_bytes())["上部構造"]["支承データ"]
    assert set(saved["終点側"]) == {"支承名", "摩擦係数_μ", "復旧性制動係数"}


def test_the_beam_has_its_own_aggregate_size(editor):
    assert editor.select("鉄筋")
    assert editor.view.select_member("梁")  # every selection rebuilds the page: editor.view is the new one
    dmax = cell(editor, "鉄筋", "梁", "aggregate_max_mm")  # a card's entry (decision 68)
    assert dmax.get() == "25.0"
    dmax.show("20.04")
    editor.bindings.entered(editor.bindings.items[("鉄筋", "梁", "aggregate_max_mm")])
    assert dmax.get() == "20.0"
    assert editor.document.data["鉄筋"]["梁"]["aggregate_max_mm"] == 20.0
    assert editor.view.select_member("フーチング")
    assert ("鉄筋", "フーチング", "aggregate_max_mm") in editor.bindings.items  # the footing's own (decision 60)


def test_the_beam_check_group_holds_the_cantilever_conditions(editor):
    assert editor.select("鉄筋")
    assert editor.view.select_member("梁")
    assert dict(rebar_page.GROUPS["梁"])["check"] == "断面照査の条件"
    assert editor.view.select_group("check")
    page = editor.view
    paths = [(CHECK, *tail) for tail, _ in rebar_page.CANTILEVER_LABELS]
    assert all(path in editor.bindings.items for path in paths)
    assert len(paths) == 13
    upper = cell(editor, CHECK, "水掛かりの程度", "上面")
    assert upper.get() == "乾湿繰返し"
    assert upper.sheet.get_dropdown_values(upper.row, upper.column) == ["", "常時乾燥", "乾湿繰返し", "常時湿潤"]
    appearance = cell(editor, CHECK, "外観の照査")
    assert appearance.sheet.get_dropdown_values(appearance.row, appearance.column) == ["", "行う", "行わない"]
    assert cell(editor, CHECK, "疲労", "旅客列車本数").get() == "60"
    assert cell(editor, CHECK, "疲労", "等価繰返し回数", "B列車", "k=0.12").get() == "10.39"
    repetitions = (CHECK, "疲労", "等価繰返し回数", "A列車", "k=0.06")
    cell(editor, *repetitions).type("2.724")
    assert cell(editor, *repetitions).get() == "2.72"
    cell(editor, CHECK, "疲労", "設計耐用年数").type("0")
    assert (CHECK, "疲労", "設計耐用年数") in editor.bindings.refused
    cell(editor, CHECK, "疲労", "設計耐用年数").type("50")
    assert not editor.bindings.refused
    assert editor.save()
    saved = load_json(editor.document.path.read_bytes())[CHECK]
    assert saved["疲労"]["設計耐用年数"] == 50 and saved["疲労"]["等価繰返し回数"]["A列車"]["k=0.06"] == 2.72
    assert any(text == rebar_page.CANTILEVER_NOTE for text in texts(page.inputs))
    # the column's group is still the 柱の断面照査
    assert editor.view.select_member("柱") and editor.view.select_group("check")
    assert ("柱の断面照査", "ε'csd") in editor.bindings.items
    assert (CHECK, "外観の照査") not in editor.bindings.items


def test_the_calculation_page_lists_the_cantilever_as_an_item_of_its_own(editor):
    """Decisions 59, 72: 0900・0910 are the 出力項目 片持ち梁の計算, which needs both static nonlinear analyses."""
    assert editor.select("計算・印刷")
    shown = list(texts(editor.view.frame))
    assert "片持ち梁の計算（0900・0910）" in shown and "　両方向の静的非線形解析が必要です" in shown
    assert [text for text in shown if text.startswith("静的非線形解析も行う")] == [
        "静的非線形解析も行う（0711）", "静的非線形解析も行う（0721）"]


def test_the_k012_repetitions_may_be_left_blank(editor):
    """Decision 125: the pair of k = 0.12 may be blank (the sample has no stirrup fatigue check); the editor saves them
    as null and refuses neither."""
    assert editor.select("鉄筋")
    assert editor.view.select_member("梁") and editor.view.select_group("check")
    for train in ("A列車", "B列車"):
        cell(editor, CHECK, "疲労", "等価繰返し回数", train, "k=0.12").type("")
    assert not editor.bindings.refused
    assert editor.save()
    saved = load_json(editor.document.path.read_bytes())[CHECK]["疲労"]["等価繰返し回数"]
    assert saved == {"A列車": {"k=0.06": 10.39, "k=0.12": None}, "B列車": {"k=0.06": 10.39, "k=0.12": None}}


RATIOS = (CHECK, "疲労", "最大変動断面力比")


def test_the_force_ratios_follow_the_repetitions(editor):
    """SA/SC and SB/SC (最大変動断面力比) are entered after the repetitions, at 3 decimals, greater than 0."""
    assert editor.select("鉄筋")
    assert editor.view.select_member("梁") and editor.view.select_group("check")
    labels = [tail for tail, _ in rebar_page.CANTILEVER_LABELS]
    assert labels[-3:] == [("疲労", "等価繰返し回数", "B列車", "k=0.12"), ("疲労", "最大変動断面力比", "A列車"),
                           ("疲労", "最大変動断面力比", "B列車")]
    assert cell(editor, *RATIOS, "A列車").get() == cell(editor, *RATIOS, "B列車").get() == "1.000"
    cell(editor, *RATIOS, "A列車").type("0.7441")
    assert cell(editor, *RATIOS, "A列車").get() == "0.744"
    cell(editor, *RATIOS, "B列車").type("0")
    assert (*RATIOS, "B列車") in editor.bindings.refused
    cell(editor, *RATIOS, "B列車").type("")  # blank until 0910 asks for it
    assert not editor.bindings.refused
    assert editor.save()
    assert load_json(editor.document.path.read_bytes())[CHECK]["疲労"]["最大変動断面力比"] == {"A列車": 0.744,
                                                                                    "B列車": None}

