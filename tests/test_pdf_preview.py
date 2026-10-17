from __future__ import annotations

from pathlib import Path
import tkinter as tk
import time
from types import SimpleNamespace

import pymupdf
from pypdf import PdfWriter
import pytest

from src import pdf_preview as preview


def make_pdf(path: Path, pages: int = 3, *, size: tuple[int, int] = (600, 840), label: str = "Report") -> Path:
    with pymupdf.open() as document:
        for number in range(pages):
            page = document.new_page(width=size[0], height=size[1])
            page.insert_text((36, 50), f"{label} {number + 1}")
        document.save(path)
    return path


@pytest.fixture
def pdf(tmp_path: Path) -> Path:
    return make_pdf(tmp_path / "日本語と空白を含む とても長い帳票ファイル名.pdf")


@pytest.fixture
def widget():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    view = preview.PdfPreview(root)
    view.pack(fill="both", expand=True)
    yield view
    root.destroy()


def finish_render(widget: preview.PdfPreview) -> None:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        widget.update()
        if widget._render_after is None:
            return
        time.sleep(0.01)
    pytest.fail("preview render did not finish")


def test_first_last_pages_and_metadata_close_files(pdf: Path, monkeypatch):
    opened = []
    actual_open = pymupdf.open

    def track_open(*args, **kwargs):
        document = actual_open(*args, **kwargs)
        opened.append(document)
        return document

    monkeypatch.setattr(preview.pymupdf, "open", track_open)
    assert preview.read_pdf_info(pdf).page_count == 3
    first = preview.render_pdf_page(pdf)
    last = preview.render_pdf_page(pdf, 2)
    assert first.png.startswith(b"\x89PNG")
    assert first.png != last.png
    assert first.page_count == last.page_count == 3
    assert first.page_index == 0 and last.page_index == 2
    assert (first.width, first.height) == (600, 840)
    for invalid in (-1, 3, 1.5):
        with pytest.raises(preview.PdfPreviewError, match="ページ"):
            preview.render_pdf_page(pdf, invalid)
    assert all(document.is_closed for document in opened)
    # Windows would reject this replacement if a document handle remained open.
    replacement = make_pdf(pdf.with_name("replacement.pdf"), pages=1, label="Updated")
    replacement.replace(pdf)
    assert preview.read_pdf_info(pdf).page_count == 1


@pytest.mark.parametrize("zoom, expected", [(-5, preview.MIN_ZOOM), (0.5, 0.5), (20, preview.MAX_ZOOM)])
def test_zoom_clamps_to_supported_range(pdf: Path, zoom: float, expected: float):
    rendered = preview.render_pdf_page(pdf, zoom=zoom)
    assert rendered.scale == expected


def test_fit_width_and_large_pages_obey_allocation_bounds(tmp_path: Path, pdf: Path):
    fitted = preview.render_pdf_page(pdf, fit_width=80)
    assert fitted.width <= 80
    assert fitted.scale < preview.MIN_ZOOM
    large = make_pdf(tmp_path / "large.pdf", pages=1, size=(10000, 12000))
    rendered = preview.render_pdf_page(large, zoom=1e10)
    assert max(rendered.width, rendered.height) <= preview.MAX_RENDER_DIMENSION
    assert rendered.width * rendered.height <= preview.MAX_RENDER_PIXELS
    for zoom in (float("nan"), float("inf")):
        with pytest.raises(preview.PdfPreviewError, match="倍率"):
            preview.render_pdf_page(pdf, zoom=zoom)
    with pytest.raises(preview.PdfPreviewError, match="幅"):
        preview.render_pdf_page(pdf, fit_width=0)


def test_missing_empty_corrupt_non_pdf_and_password_errors(tmp_path: Path, pdf: Path):
    with pytest.raises(preview.PdfPreviewError, match="見つかりません"):
        preview.read_pdf_info(tmp_path / "missing.pdf")
    corrupt = tmp_path / "corrupt.pdf"
    for content in (b"", b"invalid PDF"):
        corrupt.write_bytes(content)
        with pytest.raises(preview.PdfPreviewError, match="読み込めません"):
            preview.read_pdf_info(corrupt)
    empty = tmp_path / "empty.pdf"
    PdfWriter().write(empty)
    with pytest.raises(preview.PdfPreviewError, match="ページがありません"):
        preview.read_pdf_info(empty)
    image = tmp_path / "image.png"
    image.write_bytes(preview.render_pdf_page(pdf).png)
    with pytest.raises(preview.PdfPreviewError, match="PDF形式"):
        preview.read_pdf_info(image)
    encrypted = tmp_path / "encrypted.pdf"
    with pymupdf.open(pdf) as document:
        document.save(encrypted, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    with pytest.raises(preview.PdfPreviewError, match="パスワード"):
        preview.read_pdf_info(encrypted)


def test_access_failure_is_a_preview_error(pdf: Path, monkeypatch):
    def deny(*args, **kwargs):
        raise PermissionError("アクセスが拒否されました")

    monkeypatch.setattr(preview.pymupdf, "open", deny)
    with pytest.raises(preview.PdfPreviewError, match="アクセス"):
        preview.render_pdf_page(pdf)


def test_widget_navigation_zoom_and_reload_replaced_pdf(widget: preview.PdfPreview, pdf: Path):
    widget.show_pdf(pdf)
    widget.set_zoom(1)
    finish_render(widget)
    assert widget.page_label.get() == "1 / 3"
    assert widget.previous_button.instate(["disabled"])
    assert widget._photo is not None
    old_image_name = str(widget._photo)
    widget.go_to_page(2)
    finish_render(widget)
    assert widget.page_label.get() == "3 / 3"
    assert widget.next_button.instate(["disabled"])
    assert old_image_name not in widget.tk.call("image", "names")
    widget.go_to_page(3)
    assert widget.page_index == 2
    widget.set_zoom(100)
    finish_render(widget)
    assert widget.zoom == preview.MAX_ZOOM
    assert widget.zoom_in_button.instate(["disabled"])
    replacement = make_pdf(pdf.with_name("replacement.pdf"), pages=1, label="Replaced")
    replacement.replace(pdf)
    widget.reload()
    finish_render(widget)
    assert widget.page_label.get() == "1 / 1"
    assert widget._photo is not None
    widget.fit_to_width()
    finish_render(widget)
    assert widget.fit_width


def test_widget_recovers_from_deleted_corrupt_and_conversion_errors(widget, pdf: Path, monkeypatch):
    widget.show_pdf(pdf)
    widget.set_zoom(1)
    finish_render(widget)
    pdf.unlink()
    widget.reload()
    assert widget._photo is None
    assert "表示できません" in widget.status.get()
    assert widget.reload_button.instate(["!disabled"])
    pdf.write_bytes(b"broken PDF")
    widget.reload()
    assert "読み込めません" in widget.status.get()
    pdf.unlink()
    make_pdf(pdf)
    widget.reload()
    real_photo = preview.tk.PhotoImage

    def fail_photo(**kwargs):
        raise tk.TclError("cannot allocate image")

    monkeypatch.setattr(preview.tk, "PhotoImage", fail_photo)
    finish_render(widget)
    assert "cannot allocate image" in widget.status.get()
    assert widget._photo is None
    monkeypatch.setattr(preview.tk, "PhotoImage", real_photo)
    widget.reload()
    finish_render(widget)
    assert widget._photo is not None


def test_widget_debounces_and_cleans_images_callbacks(widget, pdf: Path, monkeypatch):
    calls = []
    real_render = preview.render_pdf_page

    def track_render(*args, **kwargs):
        calls.append(args[1])
        return real_render(*args, **kwargs)

    monkeypatch.setattr(preview, "render_pdf_page", track_render)
    widget.show_pdf(pdf)
    obsolete = widget._render_after
    widget.go_to_page(1)
    widget.go_to_page(2)
    widget.set_zoom(0.5)
    assert obsolete not in widget.tk.call("after", "info")
    finish_render(widget)
    assert calls == [2]
    photo_name = str(widget._photo)
    widget.fit_to_width()
    queued = widget._render_after
    widget.cleanup()
    assert widget._render_after is None and widget._photo is None
    assert queued not in widget.tk.call("after", "info")
    assert photo_name not in widget.tk.call("image", "names")
    widget.show_pdf(pdf)
    queued = widget._render_after
    widget._render()
    assert queued not in widget.tk.call("after", "info")
    widget.fit_to_width()
    queued = widget._render_after
    widget.destroy()
    assert queued not in widget.tk.call("after", "info")
    assert widget._photo is None


def test_widget_clear_and_wheel_do_not_reach_global_input_scroll(widget, pdf: Path):
    global_events = []
    widget.bind_all("<MouseWheel>", lambda event: global_events.append(event), add=True)
    widget.show_pdf(pdf)
    widget.set_zoom(2)
    finish_render(widget)
    assert widget._mousewheel(SimpleNamespace(delta=-120)) == "break"
    widget.canvas.event_generate("<MouseWheel>", delta=-120)
    widget.update()
    assert not global_events
    widget.show_pdf(None)
    assert widget.page_label.get() == "0 / 0"
    assert widget._photo is None and widget._render_after is None
    assert widget.reload_button.instate(["disabled"])
    widget.clear("出力PDFがありません。")
    assert widget.status.get() == "出力PDFがありません。"


class ScrollClock:
    """A clock for gesture boundaries; rendering still uses real Tk callbacks."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def idle(self) -> None:
        self.now += preview.SCROLL_IDLE_SECONDS + 0.001


@pytest.fixture
def mapped_preview(monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.geometry("920x600+40+40")
    clock = ScrollClock()
    monkeypatch.setattr(preview, "monotonic", clock)

    def create(**kwargs):
        kwargs.setdefault("advance_on_scroll", True)
        view = preview.PdfPreview(root, **kwargs)
        view.pack(fill="both", expand=True)
        root.deiconify()
        root.update()
        assert view.canvas.winfo_ismapped()
        return view, clock

    yield create
    root.destroy()


def render_now(view: preview.PdfPreview) -> None:
    view.update_idletasks()
    view._render()
    view.update_idletasks()
    assert view._render_after is None
    assert view._photo is not None


def wheel(view: preview.PdfPreview, delta: int = -120, *, target=None, state: int = 0) -> None:
    target = target or view.canvas
    assert target.winfo_ismapped()
    target.event_generate("<MouseWheel>", delta=delta, state=state)
    view.update_idletasks()


def scrollbar(view: preview.PdfPreview, *args) -> None:
    view.tk.call(view.vertical_scrollbar.cget("command"), *args)


def test_two_toolbar_rows_show_full_buttons_at_small_preview_width(mapped_preview):
    view, clock = mapped_preview()
    view.winfo_toplevel().geometry("480x460")
    view.update()
    buttons = (view.previous_button, view.next_button, view.fit_button, view.zoom_out_button,
               view.zoom_in_button, view.reload_button)
    for button in buttons:
        assert button.winfo_ismapped()
        assert button.winfo_width() >= button.winfo_reqwidth(), button.cget("text")
        assert button.winfo_rootx() >= button.master.winfo_rootx()
        assert button.winfo_rootx() + button.winfo_width() <= button.master.winfo_rootx() + button.master.winfo_width()
    assert view.previous_button.winfo_rooty() < view.fit_button.winfo_rooty()


def test_scroll_visits_each_page_before_notifying_document_end(mapped_preview, tmp_path):
    source = make_pdf(tmp_path / "first.pdf", pages=2, size=(600, 200))
    following = make_pdf(tmp_path / "next.pdf", pages=1, size=(600, 200))
    accesses = []
    endings = []

    def next_pdf():
        endings.append(view.path)
        return following if view.path == source else None

    view, clock = mapped_preview(on_access=lambda: accesses.append(True), on_document_end=next_pdf)
    view.show_pdf(source)
    render_now(view)
    assert view.canvas.yview() == (0.0, 1.0)
    assert not endings  # A fitted page never advances from its position alone.
    first_image = str(view._photo)
    wheel(view)
    assert view.path == source and view.page_index == 1 and not endings
    render_now(view)
    assert first_image not in view.tk.call("image", "names")
    assert view.page_label.get() == "2 / 2"
    clock.idle()
    wheel(view)
    assert view.path == following and view.page_index == 0
    assert endings == [source]
    render_now(view)
    clock.idle()
    wheel(view)
    assert view.path == following and view.page_index == 0
    assert endings == [source, following]  # Final file stops without wrapping.
    assert accesses


def test_first_bottom_action_is_readable_and_fresh_action_rearms(mapped_preview, pdf):
    view, clock = mapped_preview()
    view.show_pdf(pdf)
    view.set_zoom(1)
    render_now(view)
    assert view.canvas.yview()[1] < 1
    wheel(view, -120_000)
    assert view.canvas.yview()[1] == 1 and view.page_index == 0
    for _ in range(5):
        clock.now += 0.1
        wheel(view)
        assert view.page_index == 0
    clock.now += preview.SCROLL_IDLE_SECONDS - 0.001
    wheel(view)
    assert view.page_index == 0
    clock.idle()
    wheel(view)
    assert view.page_index == 1 and view._render_after is not None
    clock.now += 0.1
    wheel(view)  # Waiting for rendering extends the gesture, too.
    render_now(view)
    clock.now += 0.2
    wheel(view)
    assert view.page_index == 1 and view.canvas.yview()[0] == 0
    clock.idle()
    wheel(view)
    assert view.page_index == 1 and view.canvas.yview()[0] > 0
    wheel(view, -120_000)
    assert view.canvas.yview()[1] == 1
    clock.idle()
    wheel(view)
    assert view.page_index == 2  # Verify rearm with a real next transition.


def test_residual_input_does_not_skip_short_documents_after_render(mapped_preview, tmp_path):
    paths = [make_pdf(tmp_path / f"{name}.pdf", pages=1, size=(600, 160)) for name in "ABC"]
    endings = []

    def next_pdf():
        endings.append(view.path)
        index = paths.index(view.path)
        return paths[index + 1] if index + 1 < len(paths) else None

    view, clock = mapped_preview(on_document_end=next_pdf)
    view.show_pdf(paths[0])
    render_now(view)
    wheel(view, -120_000)
    assert view.path == paths[1] and endings == paths[:1]
    clock.now += 0.2
    wheel(view)
    render_now(view)
    for _ in range(4):
        clock.now += 0.2
        wheel(view)
        assert view.path == paths[1] and endings == paths[:1]
    clock.idle()
    view.update()  # An idle event loop alone does not advance.
    assert view.path == paths[1]
    wheel(view)
    assert view.path == paths[2] and endings == paths[:2]


@pytest.mark.parametrize("transition", ["page", "document"])
def test_slow_raster_and_access_work_do_not_rearm_queued_wheel_input(mapped_preview, tmp_path, monkeypatch, transition):
    source = make_pdf(tmp_path / "source.pdf", pages=2 if transition == "page" else 1, size=(600, 160))
    following = make_pdf(tmp_path / "following.pdf", pages=1, size=(600, 160))
    endings = []

    def next_pdf():
        endings.append(view.path)
        return following if view.path == source else None

    def access():
        if view._rendering:
            clock.now += 0.2  # Freshness checks are part of the blocked Tk work.

    view, clock = mapped_preview(on_document_end=next_pdf)
    view.show_pdf(source)
    render_now(view)
    wheel(view)  # The first input on an initially fitted page is accepted.
    assert view.page_index == (1 if transition == "page" else 0)
    assert view.path == (source if transition == "page" else following)
    expected_endings = [] if transition == "page" else [source]
    assert endings == expected_endings
    actual_render = preview.render_pdf_page

    def slow_render(*args, **kwargs):
        rendered = actual_render(*args, **kwargs)
        clock.now += 1.0
        return rendered

    monkeypatch.setattr(preview, "render_pdf_page", slow_render)
    view._on_access = access
    render_now(view)
    after_render = clock.now
    wheel(view)  # Queued while Tk was blocked, despite >250ms handling gap.
    assert endings == expected_endings
    clock.now += 0.2
    wheel(view)
    assert endings == expected_endings
    assert clock.now > after_render
    clock.idle()
    wheel(view)  # A real fresh input rearms page/document advancement.
    assert endings == expected_endings + [source if transition == "page" else following]


@pytest.mark.parametrize("what", ["units", "pages"])
def test_scrollbar_steps_keep_semantics_and_require_extra_bottom_action(mapped_preview, pdf, what):
    view, clock = mapped_preview()
    view.show_pdf(pdf)
    view.set_zoom(1)
    render_now(view)
    view.canvas.yview_scroll(1, what)
    expected = view.canvas.yview()
    view.canvas.yview_moveto(0)
    scrollbar(view, "scroll", 1, what)
    assert view.canvas.yview() == pytest.approx(expected)
    view.canvas.yview_moveto(0)
    clock.idle()
    scrollbar(view, "scroll", 1000, what)
    assert view.canvas.yview()[1] == 1 and view.page_index == 0
    clock.idle()
    scrollbar(view, "scroll", 1, what)
    assert view.page_index == 1
    render_now(view)
    assert view.canvas.yview()[0] == 0


def test_scrollbar_moveto_and_up_horizontal_zero_inputs_never_advance(mapped_preview, pdf):
    endings = []
    view, clock = mapped_preview(on_document_end=lambda: endings.append(True))
    view.show_pdf(pdf)
    view.set_zoom(2)
    view.go_to_page(2)
    render_now(view)
    scrollbar(view, "moveto", 1)
    assert view.canvas.yview()[1] == 1 and not endings
    scrollbar(view, "scroll", 1, "units")
    assert not endings
    clock.idle()
    wheel(view, 120)
    assert view.canvas.yview()[0] < 1 and not endings
    view.canvas.yview_moveto(1)
    clock.idle()
    before = view.canvas.yview()
    wheel(view, state=1)
    assert view.canvas.xview()[0] > 0 and view.canvas.yview() == before
    wheel(view, 0)
    scrollbar(view, "scroll", -1, "pages")
    assert not endings and view.path == pdf and view.page_index == 2


@pytest.mark.parametrize("button", [4, 5])
def test_button_wheel_directions_and_shift_are_explicit_vertical_inputs(mapped_preview, tmp_path, button):
    pdf = make_pdf(tmp_path / "fitted.pdf", pages=2, size=(600, 160))
    view, clock = mapped_preview()
    view.show_pdf(pdf)
    render_now(view)
    view.canvas.event_generate(f"<Button-{button}>", state=1)
    assert view.page_index == 0
    clock.idle()
    view.canvas.event_generate(f"<Button-{button}>")
    assert view.page_index == (1 if button == 5 else 0)


@pytest.mark.parametrize("target_name", ["canvas", "vertical_scrollbar", "horizontal_scrollbar"])
def test_preview_surface_wheels_do_not_reach_global_handlers(mapped_preview, tmp_path, target_name):
    pdf = make_pdf(tmp_path / "fitted.pdf", pages=2, size=(600, 160))
    view, clock = mapped_preview()
    global_events = []
    view.bind_all("<MouseWheel>", lambda event: global_events.append(event), add=True)
    view.show_pdf(pdf)
    render_now(view)
    wheel(view, target=getattr(view, target_name))
    assert view.page_index == 1 and not global_events


def test_scroll_advance_is_opt_in(mapped_preview, tmp_path):
    pdf = make_pdf(tmp_path / "fitted.pdf", pages=2, size=(600, 160))
    endings = []
    view, clock = mapped_preview(advance_on_scroll=False, on_document_end=lambda: endings.append(True))
    view.show_pdf(pdf)
    render_now(view)
    for _ in range(3):
        clock.idle()
        wheel(view)
    assert view.page_index == 0 and not endings


def test_render_resize_zoom_manual_page_and_programmatic_positions_never_advance(mapped_preview, tmp_path):
    pdf = make_pdf(tmp_path / "fitted.pdf", pages=2, size=(600, 160))
    endings = []
    view, clock = mapped_preview(on_document_end=lambda: endings.append(True))
    view.show_pdf(pdf)
    wheel(view)
    render_now(view)
    view.go_to_page(1)
    render_now(view)
    view.set_zoom(0.25)
    wheel(view)
    render_now(view)
    view.fit_to_width()
    render_now(view)
    view.winfo_toplevel().geometry("980x640")
    view.update_idletasks()
    render_now(view)
    view.canvas.yview_moveto(1)
    view.canvas.yview_scroll(1000, "pages")
    clock.idle()
    view.update()
    assert view.path == pdf and view.page_index == 1 and not endings


@pytest.mark.parametrize("content", [None, b"broken PDF"])
def test_failed_next_document_stops_and_keeps_selected_path_for_retry(mapped_preview, tmp_path, content):
    source = make_pdf(tmp_path / "source.pdf", pages=1, size=(600, 160))
    following = tmp_path / "next.pdf"
    if content is not None:
        following.write_bytes(content)
    endings = []

    def next_pdf():
        endings.append(True)
        return following

    view, clock = mapped_preview(on_document_end=next_pdf)
    view.show_pdf(source)
    render_now(view)
    wheel(view)
    assert view.path == following and view._photo is None
    assert "表示できません" in view.status.get()
    for _ in range(3):
        clock.idle()
        wheel(view)
    assert endings == [True] and view.path == following
    if following.exists():
        following.unlink()
    make_pdf(following, pages=1)
    view.reload()
    render_now(view)
    assert view.page_label.get() == "1 / 1"


def test_end_callback_failure_is_recoverable_preview_error(mapped_preview, tmp_path):
    pdf = make_pdf(tmp_path / "source.pdf", pages=1, size=(600, 160))

    def fail():
        raise RuntimeError("catalog unavailable")

    view, clock = mapped_preview(on_document_end=fail)
    view.show_pdf(pdf)
    render_now(view)
    wheel(view)
    assert view.path == pdf and view._photo is None
    assert "catalog unavailable" in view.status.get()
    clock.idle()
    wheel(view)
    assert view.page_count == 0
    view.reload()
    render_now(view)
    assert view.page_count == 1


def test_automatic_document_load_closes_handles_and_cleanup_cancels_pending(mapped_preview, tmp_path, monkeypatch):
    first = make_pdf(tmp_path / "first.pdf", pages=1, size=(600, 160))
    second = make_pdf(tmp_path / "second.pdf", pages=1, size=(600, 160))
    opened = []
    actual_open = pymupdf.open

    def track_open(*args, **kwargs):
        document = actual_open(*args, **kwargs)
        opened.append(document)
        return document

    monkeypatch.setattr(preview.pymupdf, "open", track_open)
    view, clock = mapped_preview(on_document_end=lambda: second)
    view.show_pdf(first)
    render_now(view)
    image_name = str(view._photo)
    wheel(view)
    queued = view._render_after
    assert view.path == second and queued is not None
    assert image_name not in view.tk.call("image", "names")
    assert opened and all(document.is_closed for document in opened)
    view.cleanup()
    clock.idle()
    wheel(view)
    assert queued not in view.tk.call("after", "info")
    assert view.path is None and view._photo is None and view._render_after is None
    second.unlink()  # Windows rejects deletion while a PDF handle is open.
