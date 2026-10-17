"""Modal PDF browser with a host-owned, path-based catalog."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from .lifecycle import cancel_timers
from .pdf_catalog import PdfCatalog, PdfEntry
from .pdf_preview import PdfPreview

__all__ = ["PdfCatalog", "PdfEntry", "PdfPreviewDialog"]


class PdfPreviewDialog(tk.Toplevel):
    """Browse a stable catalog without depending on the calculation controller.

    Construction is separate from ``present`` so the host can retain its
    reference before modal setup, rendering, or close callbacks run.
    """

    def __init__(
        self, parent: tk.Misc, catalog: PdfCatalog, *,
        on_refresh: Callable[[], PdfCatalog],
        on_select: Callable[[Path], None],
        on_access: Callable[[], None],
        on_close: Callable[[], None],
        focus_target: tk.Misc | None = None,
    ) -> None:
        self._parent = parent
        self._focus_target = focus_target
        self._on_refresh = on_refresh
        self._on_select = on_select
        self._on_close = on_close
        self._closed = False
        self._close_notified = False
        self._parent_destroy_binding: str | None = None
        self._entries: tuple[PdfEntry, ...] = ()
        self._iid_to_path: dict[str, Path] = {}
        self._path_to_iid: dict[Path, str] = {}
        self.selected_path: Path | None = None
        try:
            super().__init__(parent)
            self.withdraw()
            self.title("計算書 PDFプレビュー")
            self.protocol("WM_DELETE_WINDOW", self.close)
            self.bind("<Escape>", self._escape)
            self.bind("<Destroy>", self._destroyed, add=True)
            # Each child handles its own scrolling; do not let any remaining
            # wheel event reach the input editor's application-wide bindings.
            for sequence in ("<MouseWheel>", "<Shift-MouseWheel>", "<Button-4>", "<Button-5>"):
                self.bind(sequence, lambda event: "break")
            self._build_widgets(on_access)
            self._parent_destroy_binding = parent.bind("<Destroy>", self._parent_destroyed, add=True)
            self.set_catalog(catalog)
        except Exception:
            self.close()
            raise

    def _build_widgets(self, on_access: Callable[[], None]) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        content = ttk.Frame(self, padding=10)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        self._build_sidebar(content)
        self._build_viewer(content, on_access)
        footer = ttk.Frame(self, padding=(10, 0, 10, 10))
        footer.grid(row=1, column=0, sticky="ew")
        self.close_button = ttk.Button(footer, text="閉じる", command=self.close)
        self.close_button.pack(side="right")

    def _build_sidebar(self, content: ttk.Frame) -> None:
        self.sidebar = ttk.Frame(content, width=250)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.sidebar.grid_propagate(False)
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar.rowconfigure(2, weight=1)
        ttk.Label(self.sidebar, text="PDF一覧").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.refresh_button = ttk.Button(self.sidebar, text="一覧を更新", command=self.refresh)
        self.refresh_button.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.pdf_list = ttk.Treeview(self.sidebar, show="tree", selectmode="browse", height=12)
        self.pdf_list.column("#0", width=450, minwidth=100, stretch=False)
        self.pdf_list.grid(row=2, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(self.sidebar, orient="vertical", command=self.pdf_list.yview)
        vertical.grid(row=2, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(self.sidebar, orient="horizontal", command=self.pdf_list.xview)
        horizontal.grid(row=3, column=0, sticky="ew")
        self.pdf_list.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.pdf_list.bind("<<TreeviewSelect>>", self._list_selected)
        for widget in (self.pdf_list, vertical, horizontal):
            widget.bind("<MouseWheel>", self._sidebar_mousewheel)
            widget.bind("<Shift-MouseWheel>", lambda event: self._sidebar_mousewheel(event, horizontal=True))
            widget.bind("<Button-4>", self._sidebar_mousewheel)
            widget.bind("<Button-5>", self._sidebar_mousewheel)
        self.catalog_message = tk.StringVar(master=self)
        ttk.Label(self.sidebar, textvariable=self.catalog_message, wraplength=230, justify="left").grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(7, 0),
        )

    def _build_viewer(self, content: ttk.Frame, on_access: Callable[[], None]) -> None:
        right = ttk.Frame(content)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.filename = tk.StringVar(master=self, value="PDFを選択してください。")
        self.filename_label = ttk.Label(right, textvariable=self.filename, wraplength=650, justify="left")
        self.filename_label.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        right.bind("<Configure>", self._right_resized)
        self.preview = PdfPreview(
            right, on_access=on_access, advance_on_scroll=True,
            on_document_end=self._next_document,
        )
        self.preview.grid(row=1, column=0, sticky="nsew")

    def present(self) -> None:
        """Bring the single host-owned dialog forward and take a local grab."""
        if self._closed:
            return
        try:
            self.transient(self._parent.winfo_toplevel())
            if not self.winfo_ismapped():
                self._place_window()
            self.deiconify()
            self.update_idletasks()
            self.lift()
            self.grab_set()
            self.pdf_list.focus_set()
        except Exception:
            self.close()
            raise

    def _place_window(self) -> None:
        self.update_idletasks()
        parent = self._parent.winfo_toplevel()
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        available_width, available_height = max(1, screen_width - 40), max(1, screen_height - 80)
        parent_width, parent_height = parent.winfo_width(), parent.winfo_height()
        width = min(1200, available_width, max(900, parent_width - 40))
        height = min(820, available_height, max(540, parent_height - 40))
        x = min(max(0, parent.winfo_rootx() + (parent_width - width) // 2), max(0, screen_width - width - 20))
        y = min(max(0, parent.winfo_rooty() + (parent_height - height) // 2), max(0, screen_height - height - 60))
        self.minsize(min(740, available_width), min(460, available_height))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def refresh(self) -> None:
        if self._closed:
            return
        try:
            catalog = self._on_refresh()
        except Exception as exc:
            self.catalog_message.set(f"一覧を更新できません。{str(exc)[:250]}")
            return
        if not self._closed:
            self.set_catalog(catalog)

    def set_catalog(self, catalog: PdfCatalog) -> None:
        """Replace the snapshot and load exactly one selection from its start."""
        if self._closed:
            return
        self.preview.clear()
        previous = self.selected_path
        self._replace_entries(catalog.entries)
        self.catalog_message.set(catalog.message)
        selected = next((path for path in (catalog.selected, previous) if path in self._path_to_iid), None)
        if selected is None and self._entries:
            selected = self._entries[0].path
        self.selected_path = None
        if selected is None:
            self.filename.set("出力PDFがありません。")
            self.preview.clear(catalog.message or "出力PDFがありません。「一覧を更新」で読み直せます。")
        else:
            self._select_path(selected)
            self.preview.show_pdf(selected)

    def _replace_entries(self, entries: tuple[PdfEntry, ...]) -> None:
        self._entries = entries
        self._iid_to_path = {f"pdf_{i}": entry.path for i, entry in enumerate(self._entries)}
        self._path_to_iid = {path: iid for iid, path in self._iid_to_path.items()}
        children = self.pdf_list.get_children()
        if children:
            self.pdf_list.delete(*children)
        for iid, entry in zip(self._iid_to_path, self._entries):
            self.pdf_list.insert("", "end", iid=iid, text=entry.label)
        self._resize_list_column()

    def update_labels(self, entries: tuple[PdfEntry, ...]) -> None:
        """Update freshness text only; preserve the snapshot order and render."""
        if self._closed:
            return
        labels = {entry.path: entry.label for entry in entries}
        self._entries = tuple(PdfEntry(entry.path, labels.get(entry.path, entry.label)) for entry in self._entries)
        for entry in self._entries:
            self.pdf_list.item(self._path_to_iid[entry.path], text=entry.label)
        self._resize_list_column()

    def _resize_list_column(self) -> None:
        font = tkfont.Font(master=self, font=ttk.Style(self).lookup("Treeview", "font") or "TkDefaultFont")
        width = max((font.measure(entry.label) + 28 for entry in self._entries), default=230)
        self.pdf_list.column("#0", width=max(230, width))

    def _select_path(self, path: Path) -> None:
        self.selected_path = path
        iid = self._path_to_iid[path]
        self.pdf_list.selection_set(iid)
        self.pdf_list.focus(iid)
        self.pdf_list.see(iid)
        self.filename.set(path.name)
        self._on_select(path)

    def _list_selected(self, event: tk.Event) -> None:
        if self._closed:
            return
        selection = self.pdf_list.selection()
        path = self._iid_to_path.get(selection[0]) if selection else None
        if path is not None and path != self.selected_path:
            self._select_path(path)
            self.preview.show_pdf(path)

    def _next_document(self) -> Path | None:
        if self._closed:
            return None
        paths = tuple(entry.path for entry in self._entries)
        if self.selected_path not in paths:
            return None
        index = paths.index(self.selected_path) + 1
        if index >= len(paths):
            return None
        path = paths[index]
        # PdfPreview owns the load and preserves its input guard. Calling
        # show_pdf here would re-enter it and reset that guard.
        self._select_path(path)
        return path

    def _sidebar_mousewheel(self, event: tk.Event, *, horizontal: bool = False) -> str:
        number = getattr(event, "num", None)
        if number in (4, 5):
            steps = -1 if number == 4 else 1
        else:
            delta = getattr(event, "delta", 0)
            steps = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1 if delta < 0 else 0)
        if steps:
            scroll = self.pdf_list.xview_scroll if horizontal else self.pdf_list.yview_scroll
            scroll(steps, "units")
        return "break"

    def _right_resized(self, event: tk.Event) -> None:
        self.filename_label.configure(wraplength=max(100, event.width))

    def _escape(self, event: tk.Event) -> str:
        self.close()
        return "break"

    def _parent_destroyed(self, event: tk.Event) -> None:
        if event.widget is self._parent:
            self.close()

    def _destroyed(self, event: tk.Event) -> None:
        if event.widget is self:
            # Also cover destruction requested directly through Tcl.
            self.close()

    def close(self) -> None:
        """Release rendering, bindings and grab, even after partial creation."""
        if self._closed:
            return
        self._closed = True
        try:
            if self._parent_destroy_binding is not None:
                self._parent.unbind("<Destroy>", self._parent_destroy_binding)
                self._parent_destroy_binding = None
        except tk.TclError:
            pass
        try:
            if hasattr(self, "preview"):
                self.preview.cleanup()
            if hasattr(self, "tk") and self.grab_current() is self:
                self.grab_release()
        except tk.TclError:
            pass
        try:
            if hasattr(self, "_w"):
                cancel_timers(self)
                super().destroy()
        except tk.TclError:
            pass
        finally:
            if not self._close_notified:
                self._close_notified = True
                self._on_close()
            try:
                if self._focus_target is not None and self._focus_target.winfo_exists():
                    self._focus_target.focus_set()
            except tk.TclError:
                pass

    def destroy(self) -> None:
        self.close()
