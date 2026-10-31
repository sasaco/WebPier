"""Bounded, single-page PDF rendering and an embedded Tk preview of the calculation reports.

All PDF access and Tk operations run on the caller's main thread. Documents
are closed before returning so the calculation process can replace reports.
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Callable
from dataclasses import dataclass
import math
from pathlib import Path
from time import monotonic
import tkinter as tk
from tkinter import ttk
from typing import Iterator

import pymupdf


MIN_ZOOM = 0.25
MAX_ZOOM = 3.0
MAX_RENDER_DIMENSION = 3000
MAX_RENDER_PIXELS = 6_000_000
RENDER_DELAY_MS = 120
SCROLL_IDLE_SECONDS = 0.250


class PdfPreviewError(ValueError):
    """A PDF cannot be previewed; the editor can continue to be used."""


@dataclass(frozen=True)
class PdfInfo:
    page_count: int


@dataclass(frozen=True)
class RenderedPage:
    png: bytes
    width: int
    height: int
    page_index: int
    page_count: int
    scale: float


@contextmanager
def _open_pdf(path: Path | str) -> Iterator[pymupdf.Document]:
    try:
        source = Path(path)
        if not source.is_file():
            raise PdfPreviewError("PDFが見つかりません。出力一覧を更新してください。")
        with pymupdf.open(source) as document:
            if not document.is_pdf:
                raise PdfPreviewError("PDF形式のファイルではありません。")
            if document.needs_pass:
                raise PdfPreviewError("パスワード付きPDFは表示できません。")
            if document.page_count < 1:
                raise PdfPreviewError("PDFに表示できるページがありません。")
            yield document
    except PdfPreviewError:
        raise
    except Exception as exc:
        detail = str(exc).strip()[:300]
        raise PdfPreviewError(f"PDFを読み込めません。{detail}") from exc


def read_pdf_info(path: Path | str) -> PdfInfo:
    """Read current metadata without retaining the PDF or any pages."""
    with _open_pdf(path) as document:
        return PdfInfo(page_count=document.page_count)


def render_pdf_page(
    path: Path | str,
    page_index: int = 0,
    *,
    zoom: float = 1.0,
    fit_width: int | None = None,
) -> RenderedPage:
    """Render one zero-based page as RGB PNG within fixed allocation limits.

    Explicit zoom is limited to 25–300%. Fit width can go below 25% to keep a
    wide page visible. Pixel limits override either mode for oversized pages.
    """
    if not math.isfinite(zoom):
        raise PdfPreviewError("表示倍率は有限の数値で指定してください。")
    if fit_width is not None and fit_width < 1:
        raise PdfPreviewError("表示幅は1以上で指定してください。")
    with _open_pdf(path) as document:
        if not isinstance(page_index, int) or not 0 <= page_index < document.page_count:
            raise PdfPreviewError("指定ページはありません。PDFを再表示してください。")
        page = document.load_page(page_index)
        width, height = page.rect.width, page.rect.height
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise PdfPreviewError("PDFのページ寸法が不正です。")
        requested = min(MAX_ZOOM, max(MIN_ZOOM, zoom))
        if fit_width is not None:
            requested = min(MAX_ZOOM, fit_width / width)
        # Reserve rounding space: raster dimensions round each edge upward.
        scale = min(
            requested,
            (MAX_RENDER_DIMENSION - 1) / width,
            (MAX_RENDER_DIMENSION - 1) / height,
            math.sqrt((MAX_RENDER_PIXELS - 2 * MAX_RENDER_DIMENSION) / (width * height)),
        )
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
        return RenderedPage(
            png=pixmap.tobytes("png"), width=pixmap.width, height=pixmap.height,
            page_index=page_index, page_count=document.page_count, scale=scale,
        )


def wheel_steps(event: tk.Event) -> int:
    """The steps of a <MouseWheel> event (<Button-4> and <Button-5> are bound with their own direction, as Tk 9 on
    Windows delivers them with num 9 and delta 0: decision 127)."""
    delta = getattr(event, "delta", 0)
    if abs(delta) >= 120:
        return -int(delta / 120)
    if delta > 0:
        return -1
    if delta < 0:
        return 1
    return 0


class PdfPreview(ttk.Frame):
    """A reusable, main-thread-only preview that owns one rendered image."""

    def __init__(self, parent: tk.Misc, *, on_access: Callable[[], None] | None = None,
                 advance_on_scroll: bool = False,
                 on_document_end: Callable[[], Path | None] | None = None,
                 **kwargs: object) -> None:
        super().__init__(parent, **kwargs)
        # The host may update result labels, but must not reload this preview
        # from the callback. Both successful reads and read failures are checked.
        self._on_access = on_access
        self._advance_on_scroll = advance_on_scroll
        self._on_document_end = on_document_end
        self._last_vertical_input: float | None = None
        self._scroll_not_before = 0.0
        self._scroll_burst_blocked = False
        self._rendering = False
        self.path: Path | None = None
        self.page_index = 0
        self.page_count = 0
        self.zoom = 1.0
        self.fit_width = True
        self._photo: tk.PhotoImage | None = None
        self._render_after: str | None = None
        self._disposed = False
        self._last_width = 0
        self.page_label = tk.StringVar(master=self, value="0 / 0")
        self.zoom_label = tk.StringVar(master=self, value="幅に合わせる")
        self.status = tk.StringVar(master=self, value="PDFを選択してください。")

        self._build_controls()
        self._build_viewport()
        self._status_label = ttk.Label(self, textvariable=self.status, wraplength=650)
        self._status_label.pack(fill="x", pady=(5, 0))
        self.bind("<Destroy>", self._destroyed, add=True)
        self._update_controls()

    def _build_controls(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 6))
        pages = ttk.Frame(controls)
        pages.pack(fill="x", pady=(0, 4))
        display = ttk.Frame(controls)
        display.pack(fill="x")
        self.previous_button = ttk.Button(pages, text="前ページ", command=lambda: self.go_to_page(self.page_index - 1))
        self.previous_button.pack(side="left")
        ttk.Label(pages, textvariable=self.page_label, width=10, anchor="center").pack(side="left")
        self.next_button = ttk.Button(pages, text="次ページ", command=lambda: self.go_to_page(self.page_index + 1))
        self.next_button.pack(side="left")
        self.fit_button = ttk.Button(display, text="幅に合わせる", command=self.fit_to_width)
        self.fit_button.pack(side="left", padx=(0, 2))
        self.zoom_out_button = ttk.Button(display, text="−", width=3, command=lambda: self.set_zoom(self.zoom - 0.25))
        self.zoom_out_button.pack(side="left")
        ttk.Label(display, textvariable=self.zoom_label, width=11, anchor="center").pack(side="left")
        self.zoom_in_button = ttk.Button(display, text="＋", width=3, command=lambda: self.set_zoom(self.zoom + 0.25))
        self.zoom_in_button.pack(side="left")
        self.reload_button = ttk.Button(display, text="再表示", command=self.reload)
        self.reload_button.pack(side="left", padx=(8, 0))

    def _build_viewport(self) -> None:
        viewport = ttk.Frame(self)
        viewport.pack(fill="both", expand=True)
        viewport.rowconfigure(0, weight=1)
        viewport.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(viewport, background="#dce1e8", highlightthickness=0, height=340)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vertical_scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=self._vertical_scrollbar)
        self.vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        self.horizontal_scrollbar = ttk.Scrollbar(viewport, orient="horizontal", command=self.canvas.xview)
        self.horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(yscrollcommand=self.vertical_scrollbar.set, xscrollcommand=self.horizontal_scrollbar.set)
        self.canvas.bind("<Configure>", self._resized)
        for target in (self.canvas, self.vertical_scrollbar, self.horizontal_scrollbar):
            target.bind("<MouseWheel>", self._mousewheel)
            target.bind("<Shift-MouseWheel>", lambda event: self._mousewheel(event, horizontal=True))
            target.bind("<Button-4>", lambda event: self._mousewheel(event, steps=-1))
            target.bind("<Button-5>", lambda event: self._mousewheel(event, steps=1))

    def show_pdf(self, path: Path | str | None) -> None:
        """Select a PDF, reset its page, and queue rendering of the first page."""
        self.clear()
        if path is None or self._disposed:
            return
        self.path = Path(path)
        self.fit_width = True
        self.zoom = 1.0
        self._read_info()

    def reload(self) -> None:
        """Re-read a replaced PDF, keeping the page if it still exists."""
        if self.path is None or self._disposed:
            return
        self._cancel_render()
        self._drop_image()
        self._read_info()

    def _read_info(self) -> None:
        try:
            assert self.path is not None
            self._notify_access()
            self.page_count = read_pdf_info(self.path).page_count
            self.page_index = min(self.page_index, self.page_count - 1)
        except PdfPreviewError as exc:
            self._show_error(exc)
            return
        finally:
            self._notify_access()
        self._update_controls()
        self._schedule_render()

    def _notify_access(self) -> None:
        if self._on_access is not None:
            self._on_access()

    def go_to_page(self, page_index: int) -> None:
        if not 0 <= page_index < self.page_count or page_index == self.page_index:
            return
        self.page_index = page_index
        self._drop_image()
        self._update_controls()
        self._schedule_render()

    def set_zoom(self, zoom: float) -> None:
        if self.path is None or not self.page_count or not math.isfinite(zoom):
            return
        self.fit_width = False
        self.zoom = min(MAX_ZOOM, max(MIN_ZOOM, zoom))
        self._update_controls()
        self._schedule_render()

    def fit_to_width(self) -> None:
        if self.path is None or not self.page_count:
            return
        self.fit_width = True
        self._schedule_render()

    def clear(self, message: str = "PDFを選択してください。") -> None:
        self._cancel_render()
        self.path = None
        self.page_index = self.page_count = 0
        self._drop_image()
        if not self._disposed:
            self.status.set(message)
            self._update_controls()

    def cleanup(self) -> None:
        """Release callbacks and image; reusable after calculation finishes."""
        self.clear()

    def destroy(self) -> None:
        if not self._disposed:
            self.cleanup()
            self._disposed = True
        super().destroy()

    def _destroyed(self, event: tk.Event) -> None:
        if event.widget is self:
            self._cancel_render()
            self._photo = None
            self._disposed = True

    def _cancel_render(self) -> None:
        if self._render_after is not None:
            try:
                self.after_cancel(self._render_after)
            except tk.TclError:
                pass
            self._render_after = None

    def _drop_image(self) -> None:
        # Keep the input timestamp across clear/show_pdf: automatic document
        # changes must not turn the remainder of one wheel gesture into a new
        # action on a short next document. Manual changes also discard that burst.
        self._scroll_burst_blocked = True
        if not self._disposed:
            self.canvas.delete("all")
            self.canvas.configure(scrollregion=(0, 0, 0, 0))
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
        self._photo = None

    def _schedule_render(self) -> None:
        self._cancel_render()
        self._scroll_burst_blocked = True
        if self.path is not None and self.page_count and not self._disposed:
            self.status.set("プレビューを読み込んでいます…")
            self._render_after = self.after(RENDER_DELAY_MS, self._render)

    def _render(self) -> None:
        self._cancel_render()
        if self.path is None or self._disposed:
            return
        self._rendering = True
        try:
            self._notify_access()
            rendered = render_pdf_page(
                self.path, self.page_index, zoom=self.zoom,
                fit_width=max(1, self.canvas.winfo_width() - 24) if self.fit_width else None,
            )
            self._display_page(rendered)
        except (PdfPreviewError, tk.TclError) as exc:
            self._show_error(exc)
        finally:
            try:
                self._notify_access()
            finally:
                self._rendering = False
                if self._last_vertical_input is not None:
                    # A synchronous raster/access callback can block Tk long
                    # enough to queue old wheel events for more than 250ms.
                    # Start a rearm floor after all of that work completes.
                    self._scroll_not_before = monotonic() + SCROLL_IDLE_SECONDS

    def _display_page(self, rendered: RenderedPage) -> None:
        photo = tk.PhotoImage(master=self, data=rendered.png, format="png")
        self._drop_image()
        self._photo = photo
        self.page_count = rendered.page_count
        self.zoom = rendered.scale
        self.canvas.create_image(12, 12, image=photo, anchor="nw", tags="page")
        self._position_image()
        self.status.set("Shift＋ホイールで横にスクロールできます。")
        self._update_controls()

    def _show_error(self, exc: Exception) -> None:
        if self._disposed:
            return
        self._drop_image()
        self.page_count = 0
        self.page_index = 0
        self.status.set(f"プレビューを表示できません。{str(exc)[:350]}\n「再表示」で読み直せます。")
        self._update_controls()

    def _update_controls(self) -> None:
        self.page_label.set(f"{self.page_index + 1 if self.page_count else 0} / {self.page_count}")
        self.zoom_label.set(f"{self.zoom:.0%}" if self.page_count else "—")
        for button, enabled in (
            (self.previous_button, self.page_count and self.page_index > 0),
            (self.next_button, self.page_index + 1 < self.page_count),
            (self.reload_button, self.path is not None),
            (self.fit_button, self.page_count),
            (self.zoom_out_button, self.page_count and self.zoom > MIN_ZOOM),
            (self.zoom_in_button, self.page_count and self.zoom < MAX_ZOOM),
        ):
            button.state(["!disabled" if enabled else "disabled"])

    def _position_image(self) -> None:
        if self._photo is None:
            return
        width, height = self._photo.width(), self._photo.height()
        canvas_width, canvas_height = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.canvas.coords("page", max(12, (canvas_width - width) // 2), 12)
        self.canvas.configure(scrollregion=(0, 0, max(canvas_width, width + 24), max(canvas_height, height + 24)))

    def _resized(self, event: tk.Event) -> None:
        self._scroll_burst_blocked = True
        self._status_label.configure(wraplength=max(100, event.width))
        self._position_image()
        if self.fit_width and event.width != self._last_width:
            self._last_width = event.width
            self._schedule_render()

    def _mousewheel(self, event: tk.Event, *, horizontal: bool = False, steps: int | None = None) -> str:
        horizontal = horizontal or bool(getattr(event, "state", 0) & 0x1)
        steps = wheel_steps(event) if steps is None else steps
        if not steps:
            return "break"
        if horizontal:
            if not self._disposed:
                self.canvas.xview_scroll(steps, "units")
        else:
            self._vertical_scroll(steps, "units")
        return "break"

    def _vertical_scrollbar(self, *args: str) -> None:
        """Handle user scrollbar actions, never canvas position notifications."""
        if self._disposed:
            return
        if len(args) == 3 and args[0] == "scroll" and args[2] in ("units", "pages"):
            self._vertical_scroll(int(args[1]), args[2])
        elif len(args) == 2 and args[0] == "moveto":
            # Dragging the thumb to the bottom only reveals the page ending.
            self._last_vertical_input = monotonic()
            self.canvas.yview(*args)

    def _vertical_scroll(self, steps: int, what: str) -> None:
        if not steps or self._disposed:
            return
        now = monotonic()
        previous = self._last_vertical_input
        self._last_vertical_input = now
        fresh = (previous is None or now - previous >= SCROLL_IDLE_SECONDS) and now >= self._scroll_not_before
        # Inputs while waiting for rendering still extend the same gesture.
        # No idle timer moves a page; only a later, fresh user action can do so.
        if self._photo is None or self._render_after is not None or self._rendering:
            return
        if self._scroll_burst_blocked and not fresh:
            return
        self._scroll_burst_blocked = False
        at_bottom = self.canvas.yview()[1] >= 1.0 - 1e-6
        if self._advance_on_scroll and steps > 0 and at_bottom and fresh:
            self._advance_from_bottom()
        else:
            self.canvas.yview_scroll(steps, what)

    def _advance_from_bottom(self) -> None:
        self._scroll_burst_blocked = True
        if self.page_index + 1 < self.page_count:
            self.go_to_page(self.page_index + 1)
            return
        if self._on_document_end is None:
            return
        try:
            next_path = self._on_document_end()
            if next_path is not None and not self._disposed:
                self.show_pdf(next_path)
        except Exception as exc:
            self._show_error(PdfPreviewError(f"次のPDFを開けません。{str(exc)[:300]}"))
