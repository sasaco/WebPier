"""The modal PDF browser (ported from the old editor)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk

import pymupdf
import pytest

from conftest import new_root
from webpier.gui import pdf_preview as preview_module
from webpier.gui import pdf_dialog as dialog_module
from webpier.gui.pdf_dialog import PdfCatalog, PdfEntry, PdfPreviewDialog


def make_pdf(path: Path, pages: int = 1, *, size: tuple[int, int] = (600, 840)) -> Path:
    with pymupdf.open() as document:
        for number in range(pages):
            page = document.new_page(width=size[0], height=size[1])
            page.insert_text((30, 40), f"Page {number + 1}")
        document.save(path)
    return path


def finish_render(dialog: PdfPreviewDialog) -> None:
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        dialog.update()
        if dialog.preview._render_after is None:
            return
        time.sleep(0.01)
    pytest.fail("dialog render did not finish")


class FakeHost:
    """Record selection without loading the preview from a host callback."""

    def __init__(self, root: tk.Tk, catalog: PdfCatalog) -> None:
        self.root = root
        self.catalog = catalog
        self.selections: list[Path] = []
        self.accesses = 0
        self.closes = 0
        self.refreshes = 0
        self.dialog: PdfPreviewDialog | None = None
        self.button = ttk.Button(root, text="PDFプレビュー")
        self.button.pack()

    def select(self, path: Path) -> None:
        self.selections.append(path)

    def access(self) -> None:
        self.accesses += 1
        if self.dialog is not None:
            self.dialog.update_labels(self.catalog.entries)

    def close(self) -> None:
        self.closes += 1

    def refresh(self) -> PdfCatalog:
        self.refreshes += 1
        return self.catalog

    def create(self, *, present: bool = True) -> PdfPreviewDialog:
        self.dialog = PdfPreviewDialog(
            self.root, self.catalog, on_refresh=self.refresh, on_select=self.select,
            on_access=self.access, on_close=self.close, focus_target=self.button,
        )
        if present:
            self.dialog.present()
        return self.dialog


@pytest.fixture
def root():
    try:
        window = new_root()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    window.geometry("980x640+100+50")
    callback_errors = []
    window.report_callback_exception = lambda *args: callback_errors.append(args)
    window.update()
    yield window
    try:
        window.destroy()
    except tk.TclError:
        pass
    assert not callback_errors


@pytest.fixture
def reports(tmp_path):
    return tuple(make_pdf(tmp_path / name) for name in ("最初の 帳票.pdf", "次の帳票.pdf", "最後の帳票.pdf"))


def catalog(paths, selected=None, message="") -> PdfCatalog:
    return PdfCatalog(tuple(PdfEntry(path, f"{path.name}（既存出力・今回未計算）") for path in paths), selected, message)


def test_catalog_is_immutable_and_does_not_import_editor():
    path = Path("same-label.pdf")
    entry = PdfEntry(path, "same")
    snapshot = PdfCatalog((entry,), path)
    with pytest.raises(FrozenInstanceError):
        entry.label = "changed"
    with pytest.raises(FrozenInstanceError):
        snapshot.selected = None
    assert "app" not in dialog_module.__dict__ and "calculation" not in dialog_module.__dict__


@pytest.mark.parametrize("screen", [(980, 640), (1360, 900)])
def test_mapped_modal_layout_geometry_and_present_reuse(root, reports, screen, monkeypatch):
    root.geometry(f"{screen[0]}x{screen[1]}+5000+5000")
    root.update()
    host = FakeHost(root, catalog(reports, reports[1]))
    dialog = host.create(present=False)
    monkeypatch.setattr(dialog, "winfo_screenwidth", lambda: screen[0])
    monkeypatch.setattr(dialog, "winfo_screenheight", lambda: screen[1])
    assert dialog.grab_current() is None
    dialog.present()
    finish_render(dialog)
    assert dialog.winfo_ismapped()
    assert dialog.grab_current() is dialog
    assert dialog.grab_status() == "local"
    assert str(dialog.transient()) == str(root)
    assert dialog.pdf_list.winfo_rootx() < dialog.preview.winfo_rootx()
    assert dialog.preview.canvas.winfo_width() > 500
    assert dialog.preview.canvas.winfo_height() > 250
    for button in (
        dialog.preview.previous_button, dialog.preview.next_button, dialog.preview.fit_button,
        dialog.preview.zoom_out_button, dialog.preview.zoom_in_button, dialog.preview.reload_button,
    ):
        assert button.winfo_width() >= button.winfo_reqwidth()
        assert button.winfo_rootx() + button.winfo_width() <= dialog.preview.winfo_rootx() + dialog.preview.winfo_width()
    assert dialog.close_button.winfo_rooty() + dialog.close_button.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
    assert 0 <= dialog.winfo_x() < screen[0] - dialog.winfo_width()
    assert 0 <= dialog.winfo_y() < screen[1] - dialog.winfo_height()
    assert dialog.selected_path == dialog.preview.path == reports[1]
    image = dialog.preview._photo
    dialog.present()
    dialog.update()
    assert dialog.preview._photo is image
    assert host.selections == [reports[1]]
    assert len([child for child in root.winfo_children() if isinstance(child, PdfPreviewDialog)]) == 1


def test_manual_and_automatic_selection_share_paths_without_reentrant_load(root, reports, monkeypatch):
    host = FakeHost(root, catalog(reports, reports[0]))
    dialog = host.create()
    finish_render(dialog)
    calls = []
    real_show = dialog.preview.show_pdf

    def show(path):
        calls.append(path)
        real_show(path)

    monkeypatch.setattr(dialog.preview, "show_pdf", show)
    iid = dialog.pdf_list.get_children()[1]
    dialog.pdf_list.selection_set(iid)
    dialog.pdf_list.event_generate("<<TreeviewSelect>>")
    finish_render(dialog)
    assert host.selections == [reports[0], reports[1]]
    assert calls == [reports[1]]
    assert dialog.filename.get() == reports[1].name
    # The callback selects the next file and leaves loading to PdfPreview.
    assert dialog._next_document() == reports[2]
    dialog.update()
    assert host.selections == [reports[0], reports[1], reports[2]]
    assert calls == [reports[1]]
    assert dialog.preview.path == reports[1]
    assert dialog.selected_path == reports[2]
    assert dialog._next_document() is None


def test_access_label_updates_preserve_order_selection_and_pending_render(root, reports):
    host = FakeHost(root, catalog(reports, reports[1]))
    dialog = host.create()
    pending = dialog.preview._render_after
    selected_iid = dialog.pdf_list.selection()
    entries = tuple(PdfEntry(path, f"{path.name}（今回の計算結果）") for path in reversed(reports))
    dialog.update_labels(entries + (PdfEntry(Path("added.pdf"), "not in this snapshot"),))
    assert dialog.preview._render_after == pending
    assert dialog.selected_path == reports[1]
    assert dialog.pdf_list.selection() == selected_iid
    assert [dialog.pdf_list.item(iid, "text") for iid in dialog.pdf_list.get_children()] == [
        f"{path.name}（今回の計算結果）" for path in reports
    ]
    finish_render(dialog)
    image = dialog.preview._photo
    dialog.update_labels(entries)
    assert dialog.preview._photo is image
    assert host.selections == [reports[1]]


def test_refresh_snapshot_reorder_removal_rename_and_empty_cancel_old_render(root, reports, tmp_path, monkeypatch):
    host = FakeHost(root, catalog(reports, reports[1]))
    dialog = host.create()
    finish_render(dialog)
    calls = []
    real_show = dialog.preview.show_pdf

    def show(path):
        calls.append(path)
        real_show(path)

    monkeypatch.setattr(dialog.preview, "show_pdf", show)
    dialog.preview.set_zoom(2)
    obsolete = dialog.preview._render_after
    added = make_pdf(tmp_path / "追加.pdf")
    host.catalog = catalog((reports[2], added, reports[1]), reports[1])
    dialog.refresh_button.invoke()
    assert host.refreshes == 1
    assert calls == [reports[1]]
    assert obsolete not in dialog.tk.call("after", "info")
    assert dialog.selected_path == reports[1]
    assert dialog._next_document() is None  # new order, selected file is last
    # Rename/delete is resolved by the host; labels are never parsed as paths.
    renamed = reports[1].with_name("改名.pdf")
    reports[1].rename(renamed)
    host.catalog = PdfCatalog((PdfEntry(renamed, "ambiguous label"), PdfEntry(added, "ambiguous label")), renamed)
    dialog.refresh()
    finish_render(dialog)
    assert dialog.selected_path == dialog.preview.path == renamed
    assert dialog.filename.get() == renamed.name
    host.catalog = catalog((added,), added)
    renamed.unlink()
    dialog.refresh()
    assert dialog.selected_path == added
    finish_render(dialog)
    photo = str(dialog.preview._photo)
    dialog.preview.fit_to_width()
    pending = dialog.preview._render_after
    host.catalog = catalog((), None, "出力PDFがありません。")
    dialog.refresh()
    dialog.update()
    assert dialog.selected_path is None
    assert dialog.preview.path is None and dialog.preview._photo is None
    assert dialog.pdf_list.get_children() == ()
    assert pending not in dialog.tk.call("after", "info")
    assert photo not in dialog.tk.call("image", "names")
    assert "ありません" in dialog.preview.status.get()
    assert dialog.refresh_button.instate(["!disabled"])


def test_empty_state_and_refresh_failure_keep_dialog_usable(root, reports, monkeypatch):
    host = FakeHost(root, catalog(()))
    dialog = host.create()
    assert dialog.grab_current() is dialog
    assert dialog.selected_path is None
    assert dialog.preview.reload_button.instate(["disabled"])

    def fail_refresh():
        raise PermissionError("アクセス拒否")

    monkeypatch.setattr(dialog, "_on_refresh", fail_refresh)
    dialog.refresh()
    assert "アクセス拒否" in dialog.catalog_message.get()
    monkeypatch.setattr(dialog, "_on_refresh", host.refresh)
    host.catalog = catalog(reports, reports[0])
    dialog.refresh()
    finish_render(dialog)
    assert dialog.preview.path == reports[0]
    assert dialog.preview._photo is not None


def test_initial_read_failure_cleans_partial_dialog_and_allows_retry(root, reports):
    host = FakeHost(root, catalog(reports, reports[0]))

    def fail_access():
        raise RuntimeError("host access callback failed")

    with pytest.raises(RuntimeError, match="host access"):
        PdfPreviewDialog(
            root, host.catalog, on_refresh=host.refresh, on_select=host.select,
            on_access=fail_access, on_close=host.close,
        )
    root.update()
    assert host.closes == 1
    assert root.grab_current() is None
    assert not any(isinstance(child, PdfPreviewDialog) for child in root.winfo_children())
    replacement = host.create()
    finish_render(replacement)
    assert replacement.preview._photo is not None


def test_many_long_names_sidebar_scrolls_without_pdf_or_global_wheel(root, reports):
    # Nonselected entries need not exist; the stable catalog is host-owned.
    paths = (reports[0],) + tuple(Path(f"{i:03d}_とても長い日本語の帳票ファイル名" * 3 + ".pdf") for i in range(50))
    host = FakeHost(root, catalog(paths, reports[0]))
    dialog = host.create()
    finish_render(dialog)
    global_events = []
    root.bind_all("<MouseWheel>", lambda event: global_events.append(event), add=True)
    root.bind_all("<Button-5>", lambda event: global_events.append(event), add=True)
    original_y = dialog.pdf_list.yview()
    for sequence, args in (("<MouseWheel>", {"delta": -1200}), ("<Button-5>", {})):
        dialog.pdf_list.event_generate(sequence, **args)
        dialog.update()
    assert dialog.pdf_list.yview() != original_y
    original_x = dialog.pdf_list.xview()
    dialog.pdf_list.event_generate("<Shift-MouseWheel>", delta=-120)
    dialog.update()
    assert dialog.pdf_list.xview() != original_x
    dialog.refresh_button.event_generate("<MouseWheel>", delta=-120)
    dialog.update()
    assert not global_events
    assert dialog.selected_path == dialog.preview.path == reports[0]
    assert dialog.preview.page_index == 0
    assert len(dialog.pdf_list.get_children()) == 51
    assert dialog.pdf_list.item(dialog.pdf_list.get_children()[-1], "text").startswith(paths[-1].name)


def test_sidebar_button_wheel_directions_do_not_depend_on_the_event_number(root, reports):
    # Decision 127: Tk 9.0.4 on Windows delivers <Button-5> with num 9 and delta 0; the binding carries the direction.
    paths = (reports[0],) + tuple(Path(f"{i:03d}_帳票.pdf") for i in range(50))
    dialog = FakeHost(root, catalog(paths, reports[0])).create()
    finish_render(dialog)
    top = dialog.pdf_list.yview()
    dialog.pdf_list.event_generate("<Button-5>")
    dialog.update()
    down = dialog.pdf_list.yview()
    assert down[0] > top[0]
    dialog.pdf_list.event_generate("<Button-4>")
    dialog.update()
    assert dialog.pdf_list.yview()[0] < down[0]


def test_real_wheel_visits_all_pages_then_next_pdf_and_stops(root, tmp_path, monkeypatch):
    paths = (make_pdf(tmp_path / "a.pdf", 2, size=(600, 1200)), make_pdf(tmp_path / "b.pdf", size=(1200, 100)))
    clock = [100.0]
    monkeypatch.setattr(preview_module, "monotonic", lambda: clock[0])
    host = FakeHost(root, catalog(paths, paths[0]))
    dialog = host.create()
    finish_render(dialog)
    canvas = dialog.preview.canvas

    def wheel():
        clock[0] += 1.0
        canvas.event_generate("<MouseWheel>", delta=-120)
        dialog.update()

    canvas.yview_moveto(1)
    wheel()
    finish_render(dialog)
    assert dialog.preview.page_index == 1
    assert host.selections == [paths[0]]
    canvas.yview_moveto(1)
    wheel()
    finish_render(dialog)
    assert dialog.selected_path == dialog.preview.path == paths[1]
    assert dialog.preview.page_index == 0
    assert dialog.filename.get() == paths[1].name
    assert host.selections == list(paths)
    assert dialog.pdf_list.selection() == (dialog.pdf_list.get_children()[1],)
    wheel()
    finish_render(dialog)
    assert dialog.selected_path == paths[1]
    assert host.selections == list(paths)


@pytest.mark.parametrize("failure", ["deleted", "corrupt"])
def test_automatic_next_error_stops_then_manual_selection_recovers(root, reports, failure, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(preview_module, "monotonic", lambda: clock[0])
    host = FakeHost(root, catalog(reports, reports[0]))
    dialog = host.create()
    finish_render(dialog)
    if failure == "deleted":
        reports[1].unlink()
    else:
        reports[1].write_bytes(b"not a PDF")
    canvas = dialog.preview.canvas
    canvas.yview_moveto(1)
    clock[0] += 1
    canvas.event_generate("<MouseWheel>", delta=-120)
    dialog.update()
    assert dialog.selected_path == dialog.preview.path == reports[1]
    assert "表示できません" in dialog.preview.status.get()
    assert dialog.preview._photo is None
    clock[0] += 1
    canvas.event_generate("<MouseWheel>", delta=-120)
    dialog.update()
    assert host.selections == [reports[0], reports[1]]
    dialog.pdf_list.selection_set(dialog.pdf_list.get_children()[2])
    dialog.pdf_list.event_generate("<<TreeviewSelect>>")
    finish_render(dialog)
    assert dialog.preview.path == reports[2]
    assert dialog.preview._photo is not None


@pytest.mark.parametrize("how", ["button", "escape", "wm", "destroy", "parent"])
def test_all_close_paths_release_grab_images_callbacks_and_allow_reopen(root, reports, how):
    host = FakeHost(root, catalog(reports, reports[0]))
    dialog = host.create()
    finish_render(dialog)
    photo = str(dialog.preview._photo)
    dialog.preview.set_zoom(2)
    pending = dialog.preview._render_after
    if how == "button":
        dialog.close_button.invoke()
    elif how == "escape":
        dialog.pdf_list.focus_force()
        dialog.pdf_list.event_generate("<Escape>")
    elif how == "wm":
        root.tk.call(dialog.protocol("WM_DELETE_WINDOW"))
    elif how == "destroy":
        dialog.destroy()
    else:
        root.destroy()
    if how == "parent":
        assert host.closes == 1
        assert dialog.preview._photo is None and dialog.preview._render_after is None
        return
    root.update()
    assert host.closes == 1
    assert not dialog.winfo_exists()
    assert root.grab_current() is None
    assert dialog.preview._photo is None and dialog.preview._render_after is None
    assert photo not in root.tk.call("image", "names")
    assert pending not in root.tk.call("after", "info")
    assert root.focus_get() is host.button
    dialog.close()
    dialog.destroy()
    assert host.closes == 1
    replacement = host.create()
    finish_render(replacement)
    assert replacement.grab_current() is replacement
    assert replacement.preview.path == reports[0]


@pytest.mark.parametrize("failure", ["toplevel", "build", "transient", "grab"])
def test_partial_modal_failures_cleanup_and_retry(root, reports, monkeypatch, failure):
    host = FakeHost(root, catalog(reports, reports[0]))
    actual_init = tk.Toplevel.__init__
    actual_build = PdfPreviewDialog._build_widgets
    actual_transient = PdfPreviewDialog.transient
    actual_grab = PdfPreviewDialog.grab_set

    def fail_toplevel(self, *args, **kwargs):
        actual_init(self, *args, **kwargs)
        raise tk.TclError("toplevel failed after creation")

    def fail_build(self, *args, **kwargs):
        actual_build(self, *args, **kwargs)
        raise tk.TclError("widgets failed after creation")

    def fail_transient(self, *args, **kwargs):
        actual_transient(self, *args, **kwargs)
        raise tk.TclError("transient failed")

    def fail_grab(self, *args, **kwargs):
        actual_grab(self, *args, **kwargs)
        raise tk.TclError("grab failed after acquisition")

    target, method, failing = {
        "toplevel": (tk.Toplevel, "__init__", fail_toplevel),
        "build": (PdfPreviewDialog, "_build_widgets", fail_build),
        "transient": (PdfPreviewDialog, "transient", fail_transient),
        "grab": (PdfPreviewDialog, "grab_set", fail_grab),
    }[failure]
    with monkeypatch.context() as patch:
        patch.setattr(target, method, failing)
        with pytest.raises(tk.TclError, match="failed"):
            host.create()
    root.update()
    assert host.closes == 1
    assert root.grab_current() is None
    assert not any(isinstance(child, PdfPreviewDialog) for child in root.winfo_children())
    replacement = host.create()
    finish_render(replacement)
    assert replacement.grab_current() is replacement
    assert replacement.preview._photo is not None


def test_parent_frame_destruction_closes_dialog_and_leaves_root_usable(root, reports):
    parent = ttk.Frame(root)
    parent.pack()
    closed = []
    dialog = PdfPreviewDialog(
        parent, catalog(reports, reports[0]), on_refresh=lambda: catalog(reports),
        on_select=lambda path: None, on_access=lambda: None, on_close=lambda: closed.append(True),
    )
    dialog.present()
    finish_render(dialog)
    dialog.preview.fit_to_width()
    queued = dialog.preview._render_after
    parent.destroy()
    root.update()
    assert closed == [True]
    assert not dialog.winfo_exists()
    assert root.grab_current() is None
    assert queued not in root.tk.call("after", "info")
