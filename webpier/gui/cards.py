"""Cards of labelled inputs bound to the field table, for the 鉄筋 page (decision 68).

A card is a framed group with a title. Its inputs are an entry (numbers, integers), a choice shown as a row of buttons
(a segment) or a bar size chosen from a list (D10 … D51); each is a binding.Cell, so what is typed or chosen is
entered, rounded and checked through the field table exactly like a table cell, and a refused or needed value is
marked. An explanatory figure or formula opens from a (?) button in a small window beside it.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Mapping
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from ..inputs.fields import field
from .binding import Bound
from .document import JsonPath
from .form import unit_of
from .grid import EDITABLE

if TYPE_CHECKING:
    from .form import Form

SIZES = (10, 13, 16, 19, 22, 25, 29, 32, 35, 38, 41, 51)  # 異形棒鋼の呼び名 (JIS G 3112)
NO_VALUE = "—"  # a readout without its value
BORDER, PRESSED = "#b8c3cd", "#cfe0f2"
FONT = ("Yu Gothic UI", 10)


class EntryCell:
    """A text entry; its text is entered when it loses the focus or on Return."""

    def __init__(self, parent: tk.Misc, width: int, numeric: bool) -> None:
        self.var = tk.StringVar(master=parent)
        self.widget = tk.Entry(parent, textvariable=self.var, width=width, justify="right" if numeric else "left",
                               relief="solid", borderwidth=1, highlightthickness=0, font=FONT)

    def get(self) -> str:
        return self.var.get()

    def show(self, text: str) -> None:
        self.var.set(text)

    def color(self, background: str) -> None:
        self.widget.configure(background=background)

    def focus(self) -> None:
        self.widget.focus_set()


class SegmentCell:
    """A choice as a row of buttons: the value of the pressed one, "" when none is."""

    def __init__(self, parent: tk.Misc, options: list[tuple[str, str]], select: Callable[[], None]) -> None:
        self.var = tk.StringVar(master=parent)
        self.frame = tk.Frame(parent, highlightthickness=1, highlightbackground=BORDER)
        self.buttons = {value: tk.Radiobutton(self.frame, text=label, value=value, variable=self.var,
                                              indicatoron=False, command=select, padx=10, pady=2, relief="flat",
                                              borderwidth=0, selectcolor=PRESSED, font=FONT)
                        for value, label in options}
        for button in self.buttons.values():
            button.pack(side="left")

    def get(self) -> str:
        return self.var.get()

    def show(self, text: str) -> None:
        self.var.set(text)

    def color(self, background: str) -> None:
        marked = background != EDITABLE
        self.frame.configure(highlightbackground=background if marked else BORDER,
                             highlightthickness=2 if marked else 1)

    def focus(self) -> None:
        next(iter(self.buttons.values())).focus_set()


class SizeCell:
    """A bar size from a list (D19 …); the entered text is the size in mm."""

    def __init__(self, parent: tk.Misc, sizes: tuple[int, ...]) -> None:
        self.widget = ttk.Combobox(parent, values=["", *(f"D{size}" for size in sizes)], state="readonly", width=6)

    def get(self) -> str:
        return self.widget.get().removeprefix("D")

    def show(self, text: str) -> None:
        self.widget.set(f"D{text}" if text else "")

    def color(self, background: str) -> None:
        name = f"C{background.lstrip('#')}.TCombobox"
        ttk.Style(self.widget).map(name, fieldbackground=[("readonly", background)])
        self.widget.configure(style=name)

    def focus(self) -> None:
        self.widget.focus_set()


class Help:
    """(?): a small window beside the button with an explanatory figure or formula; pressed again, it closes."""

    def __init__(self, parent: tk.Misc, title: str, build: Callable[[tk.Misc], None]) -> None:
        self.title, self.build = title, build
        self.window: tk.Toplevel | None = None
        self.button = tk.Button(parent, text="?", width=2, padx=0, pady=0, relief="groove", borderwidth=1,
                                font=("Yu Gothic UI", 8), cursor="hand2", command=self.toggle)

    def toggle(self) -> None:
        if self.window is not None:
            self.window.destroy()
            self.window = None
            return
        button = self.button
        window = self.window = tk.Toplevel(button)
        window.title(self.title)
        window.transient(button.winfo_toplevel())
        window.resizable(False, False)
        window.geometry(f"+{button.winfo_rootx()}+{button.winfo_rooty() + button.winfo_height() + 4}")
        window.protocol("WM_DELETE_WINDOW", self.toggle)
        body = ttk.Frame(window, padding=10)
        body.pack(fill="both", expand=True)
        self.build(body)


def help_button(parent: tk.Misc, title: str, lines: Callable[[], list[str]]) -> Help:
    """(?) after the inputs of *parent*; *lines* gives the text for the values at the time it opens."""
    def build(body: tk.Misc) -> None:
        for text in lines():
            ttk.Label(body, text=text, wraplength=360, justify="left").pack(anchor="w")
    help_ = Help(parent, title, build)
    help_.button.pack(side="left", padx=(0, 10), pady=(18, 4))
    return help_


def remove_button(parent: tk.Misc, command: Callable[[], object]) -> tk.Button:
    """×: removes the item of its line."""
    button = tk.Button(parent, text="×", width=2, padx=0, pady=0, relief="groove", borderwidth=1,
                       font=("Yu Gothic UI", 8), fg="#8e1d1d", cursor="hand2", command=command)
    button.pack(side="left", pady=(18, 4))
    return button


def readout_label(parent: tk.Misc, readouts: dict, key: tuple, label: str = "芯かぶり mm") -> None:
    """A value calculated elsewhere, under *label*: the variable kept in *readouts* by *key* is set by the page."""
    frame = labelled(parent, label)
    variable = readouts.setdefault(key, tk.StringVar(master=parent, value=NO_VALUE))
    ttk.Label(frame, textvariable=variable, style="Symbol.TLabel").pack(anchor="w")


def shown(parent: tk.Misc, label: str, number: Any) -> None:
    """*number* read only under *label* (an item another page enters), or no value while it is blank."""
    frame = labelled(parent, label)
    ttk.Label(frame, text=NO_VALUE if number is None else f"{number:g}", style="Symbol.TLabel").pack(anchor="w")


def card(parent: tk.Misc, title: str) -> ttk.LabelFrame:
    frame = ttk.LabelFrame(parent, text=title, style="Sheet.TLabelframe", padding=8)
    frame.pack(fill="x", pady=(0, 8))
    return frame


def line(parent: tk.Misc) -> ttk.Frame:
    """A row of labelled inputs."""
    frame = ttk.Frame(parent)
    frame.pack(fill="x", anchor="w")
    return frame


def labelled(parent: tk.Misc, label: str, path: JsonPath | None = None) -> ttk.Frame:
    """A caption (with the unit of *path*) above the widget packed into the returned frame."""
    unit = unit_of(path) if path is not None else ""
    frame = ttk.Frame(parent)
    frame.pack(side="left", padx=(0, 14), pady=4, anchor="s")
    ttk.Label(frame, text=f"{label} {unit}".strip(), style="Muted.TLabel").pack(anchor="w")
    return frame


def entry(form: Form, parent: tk.Misc, path: JsonPath, label: str, *, width: int = 8) -> Bound:
    cell = EntryCell(labelled(parent, label, path), width, field(path).kind in ("number", "integer"))
    cell.widget.pack(anchor="w")
    bindings = form.editor.bindings
    bound = bindings.bind_cell(cell, path)
    for event in ("<FocusOut>", "<Return>", "<KP_Enter>"):
        cell.widget.bind(event, lambda _event: bindings.entered(bound), add="+")
    return bound


def segment(form: Form, parent: tk.Misc, path: JsonPath, label: str, *, labels: Mapping[str, str] | None = None,
            selected: Callable[[], None] | None = None) -> Bound:
    """The choices of *path* as buttons (*labels* may rename them); *selected* runs after a choice is entered."""
    bindings = form.editor.bindings
    found: list[Bound] = []

    def select() -> None:
        bindings.entered(found[0])
        if selected is not None:
            selected()

    options = [(choice, (labels or {}).get(choice, choice)) for choice in field(path).choices]
    cell = SegmentCell(labelled(parent, label), options, select)
    cell.frame.pack(anchor="w")
    found.append(bindings.bind_cell(cell, path))
    return found[0]


def size(form: Form, parent: tk.Misc, path: JsonPath, label: str, *, sizes: tuple[int, ...] = SIZES) -> Bound:
    cell = SizeCell(labelled(parent, label), sizes)
    cell.widget.pack(anchor="w")
    bindings = form.editor.bindings
    bound = bindings.bind_cell(cell, path)
    cell.widget.bind("<<ComboboxSelected>>", lambda _event: bindings.entered(bound), add="+")
    return bound
