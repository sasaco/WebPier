"""The inputs of the 片持ち梁の照査 (decision 59) in the editor: the bearing devices of each girder on the 上部構造
page, the beam's Dmax and the 梁「断面照査の条件」 group on the 鉄筋 page, and the calculation page naming 0900・0910
under the nonlinear switch only."""

import tkinter as tk

import pytest

from webpier.core.integrity import load_json
from webpier.gui import app as gui
from webpier.gui import rebar_page
from webpier.gui.pages import BEARING_DEVICES

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


def test_the_bearing_devices_are_integer_columns_of_the_support_table(editor):
    assert editor.select("上部構造")
    assert BEARING_DEVICES == ("ゴム支承の箇所数", "ストッパーの箇所数", "片持ち梁上のゴム支承", "片持ち梁上のストッパー")
    assert [cell(editor, *SUPPORT, "起点側", key).get() for key in BEARING_DEVICES] == ["4", "3", "1", "1"]
    assert [cell(editor, *SUPPORT, "終点側", key).get() for key in BEARING_DEVICES] == ["2", "7", "1", "0"]
    target = (*SUPPORT, "終点側", "ストッパーの箇所数")
    cell(editor, *target).type("1.5")
    assert target in editor.bindings.refused
    cell(editor, *target).type("8")
    assert not editor.bindings.refused
    assert editor.document.data["上部構造"]["支承データ"]["終点側"]["ストッパーの箇所数"] == 8
    cell(editor, *SUPPORT, "起点側", "片持ち梁上のゴム支承").type("")
    assert editor.save()
    saved = load_json(editor.document.path.read_bytes())["上部構造"]["支承データ"]
    assert saved["終点側"]["ストッパーの箇所数"] == 8 and saved["起点側"]["片持ち梁上のゴム支承"] is None
    assert any("片持ち梁の照査（0900、決定59）" in text for text in texts(editor.form))


def test_the_beam_has_its_own_aggregate_size(editor):
    assert editor.select("鉄筋")
    assert editor.view.select_member("梁")  # every selection rebuilds the page: editor.view is the new one
    dmax = cell(editor, "鉄筋", "梁", "aggregate_max_mm")
    assert dmax.get() == "25.0"
    dmax.type("20.04")
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
    assert len(paths) == 11
    upper = cell(editor, CHECK, "鋼材の腐食に対する環境条件", "上面")
    assert upper.get() == "腐食性環境"
    assert upper.sheet.get_dropdown_values(upper.row, upper.column) == ["", "一般の環境", "腐食性環境", "特に厳しい腐食性環境"]
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


def test_the_calculation_page_names_the_cantilever_stages_under_the_nonlinear_switch(editor):
    assert editor.select("計算・印刷")
    shown = list(texts(editor.view.frame))
    frame = next(text for text in shown if text.startswith("骨組解析も行う"))
    nonlinear = next(text for text in shown if text.startswith("静的非線形解析も行う"))
    assert "0900" not in frame and "0910" not in frame
    assert "0611・0621 は Capacita で柱の断面照査も行う（決定48）" in frame
    assert "0612・0622 は反力で基礎の照査も行う（決定54）" in frame
    assert "0711・0721・0800・0810・0820・0900・0910。" in nonlinear
    assert "0900・0910 は片持ち梁の応答値と Capacita の断面照査も行い、post/片持ち梁.wdj を出力（決定59）" in nonlinear
