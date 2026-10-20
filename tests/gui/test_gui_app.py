"""The editor window: navigation, open, save as, discard, close, input check and the command line."""

import json
from types import SimpleNamespace

import pytest

from conftest import CURRENT
from webpier.gui import app as gui
from webpier.gui import form as form_module


@pytest.fixture
def editor(tk_root, input_path, quiet):
    return gui.InputEditor(tk_root, input_path)


def type_in(editor, path, text):
    editor.bindings.items[path].cell.type(text)


B1 = ("下部構造", "寸法", "側面", "B1")


def test_the_tree_lists_every_page_and_navigates(editor):
    assert editor.tree.get_children() == gui.PAGES
    editor.tree.selection_set("地盤データ")
    editor._tree_selected()
    assert editor.page == "地盤データ"
    assert not editor.select("存在しない")
    assert editor.root.title() == f"橋脚 入力データ編集 — {editor.document.path.name}"


def test_the_title_and_status_show_unsaved_changes(editor):
    type_in(editor, B1, "3")
    assert editor.root.title().startswith("* ")
    assert editor.status.get() == "未保存の変更があります"
    assert editor.save() and editor.status.get().startswith("保存しました: input.json  /  変更前: input.json.")


def test_open_another_file_after_saving_or_discarding(editor, quiet, tmp_path, monkeypatch):
    _, answers = quiet
    other = tmp_path / "other.json"
    data = json.loads(CURRENT.read_text(encoding="utf-8"))
    data["上部構造"]["列車"]["編成数"] = 8
    other.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kwargs: str(other))
    type_in(editor, B1, "3")
    answers["askyesnocancel"] = None
    assert not editor.open_file() and editor.document.data["下部構造"]["寸法"]["側面"]["B1"] == 3.0
    answers["askyesnocancel"] = False
    assert editor.open_file()
    assert editor.document.path == other and editor.document.data["上部構造"]["列車"]["編成数"] == 8
    assert editor.status.get() == "入力を読み込みました"


def test_open_reports_an_unreadable_file_and_keeps_the_current_one(editor, quiet, tmp_path, monkeypatch):
    calls, _ = quiet
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kwargs: str(broken))
    assert not editor.open_file()
    assert calls[-1][:2] == ("showerror", "開けません")
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kwargs: "")
    assert not editor.open_file()


def test_save_as_asks_before_replacing_another_file(editor, quiet, tmp_path, monkeypatch):
    _, answers = quiet
    target = tmp_path / "existing.json"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: str(target))
    answers["askyesno"] = False
    assert not editor.save_as() and target.read_text(encoding="utf-8") == "{}"
    answers["askyesno"] = True
    assert editor.save_as() and editor.document.path == target
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: "")
    assert not editor.save_as()


def test_save_as_reports_a_link(editor, quiet, monkeypatch):
    calls, _ = quiet

    def link(path):
        raise gui.EditorError("シンボリックリンクには保存できません")

    monkeypatch.setattr(gui, "fingerprint", link)
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: "x.json")
    assert not editor.save_as()
    assert calls[-1][:2] == ("showerror", "保存できません")


def test_a_conflicting_save_is_reported(editor, quiet):
    calls, _ = quiet
    editor.document.path.write_text("{}", encoding="utf-8")
    type_in(editor, B1, "3")
    assert not editor.save()
    assert calls[-1][:2] == ("showerror", "保存できません")


def test_input_check_parses_the_whole_input(editor, quiet):
    calls, _ = quiet
    assert editor.check_input() and calls[-1][0] == "showinfo"
    type_in(editor, B1, "")
    assert not editor.check_input()
    assert calls[-1][0] == "showwarning" and "下部構造.寸法.側面.B1: 値が必要です" in calls[-1][2]


def test_input_check_names_the_rebar_warnings(editor, quiet):
    calls, _ = quiet
    editor.document.data["鉄筋"]["梁"]["side_bars"]["start_mm"] = 108  # two pairs of overlapping bars
    assert editor.check_input()
    name, title, text = calls[-1][:3]
    assert name == "showwarning" and title == "入力チェック" and "（計算できます）" in text
    assert "・梁：鉄筋が 2 か所で重なっています。" in text


def test_closing_saves_discards_or_continues(tk_root, input_path, quiet):
    _, answers = quiet
    editor = gui.InputEditor(tk_root, input_path)
    type_in(editor, B1, "3")
    answers["askyesnocancel"] = None
    assert not editor.close() and not editor.closed
    answers["askyesnocancel"] = True
    editor.select("鉄筋")
    assert editor.close() and editor.closed
    assert json.loads(input_path.read_text(encoding="utf-8"))["下部構造"]["寸法"]["側面"]["B1"] == 3.0


def test_the_cell_message_names_the_selected_cell(editor):
    target = editor.bindings.items[B1].cell
    target.sheet.select_cell(target.row, target.column)
    editor.cell_selected(target.sheet)
    assert editor.cell_message.get() == ""
    target.sheet.select_cell(0, 0)  # a caption cell
    editor.cell_selected(target.sheet)
    assert editor.cell_message.get() == ""


def test_the_wheel_scrolls_the_form_but_not_the_rebar_page(editor):
    editor.root.deiconify()
    editor.root.update()
    x, y = editor.form.winfo_rootx() + 5, editor.form.winfo_rooty() + 5
    event = SimpleNamespace(state=0, delta=-120, x_root=x, y_root=y)
    editor._wheel(event)
    editor._wheel(SimpleNamespace(state=0x4, delta=-120, x_root=x, y_root=y))
    editor.select("鉄筋")
    editor._wheel(event)
    editor._resized(SimpleNamespace(width=900, height=600))
    editor.select("計算・印刷")
    editor._wheel(event)  # a page without its own wheel
    editor.select("下部構造")
    editor._resized(SimpleNamespace(width=900, height=600))


def test_a_figure_can_be_enlarged_and_a_missing_one_is_reported(editor, monkeypatch, tmp_path):
    form = gui.Form(editor, editor.form)
    window = form.enlarge("substructure", "側面")
    assert window.title() == "側面 — 原図・記号確認用"
    window.destroy()
    monkeypatch.setattr(form_module, "ASSETS", tmp_path)
    editor.images.clear()
    holder = gui.ttk.Frame(editor.form)
    form.figure(holder, "substructure", "側面")
    (frame,) = holder.winfo_children()
    assert [label.cget("text") for label in frame.winfo_children()] == ["参照図を読み込めませんでした。"]


def test_main_opens_the_editor_or_reports_the_file(monkeypatch, tmp_path, quiet, input_path):
    calls, _ = quiet
    roots = []

    class Root(gui.tk.Tk):
        def mainloop(self, n=0):
            roots.append(self)
            self.destroy()

    monkeypatch.setattr(gui.tk, "Tk", Root)
    assert gui.main(["--input", str(input_path)]) == 0 and roots
    assert gui.main(["--input", str(tmp_path / "missing.json")]) == 1
    assert calls[-1][:2] == ("showerror", "入力JSONを開けません")
