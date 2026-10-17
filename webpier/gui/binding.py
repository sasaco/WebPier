"""Table cells bound to input paths; every edit is entered at once (decision 17).

A cell typed into, pasted into, cleared or restored by undo is converted by its field (entry.py): the rounded
value is written into the document and shown in the cell. Text that cannot be entered stays in the cell, marked,
and the document keeps its previous value; the editor refuses to save until it is corrected. Cells whose value is
needed but blank or invalid are marked too, with the reason available for the status line.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tksheet import Sheet

from ..inputs.fields import Field, field, path_text
from .document import MISSING, EditorError, JsonPath, lookup, put
from .entry import EntryError, display, enter, problem
from .grid import DISABLED, EDITABLE, MISSING as MISSING_COLOR, REFUSED, SheetCell, commit_editor, pending_dirty


ABSENT = "（項目なし）"


@dataclass
class Bound:
    path: JsonPath
    cell: SheetCell
    spec: Field
    shown: str  # the text the cell had when it was last entered or displayed
    write: Callable[[Any], None]


class Bindings:
    def __init__(self, data: Callable[[], Any], changed: Callable[[], None]) -> None:
        self._data = data
        self._changed = changed
        self.items: dict[JsonPath, Bound] = {}
        self.refused: dict[JsonPath, str] = {}
        self.sheets: list[Sheet] = []

    def clear(self) -> None:
        self.items.clear()
        self.refused.clear()
        self.sheets.clear()

    def value(self, path: JsonPath) -> Any:
        return lookup(self._data(), path)

    def bind(self, sheet: Sheet, row: int, column: int, path: JsonPath, *,
             write: Callable[[Any], None] | None = None) -> Bound:
        spec = field(path)
        value = self.value(path)
        text = "" if value is MISSING else display(spec, value)
        cell = SheetCell(sheet, row, column)
        if value is MISSING and write is None and not isinstance(self.value(path[:-1]), (dict, list)):
            cell.show(ABSENT)  # an input of another form; nothing is added to it
            return Bound(path, cell, spec, ABSENT, lambda new: None)
        cell.show(text)
        bound = Bound(path, cell, spec, text, write or (lambda new, path=path: put(self._data(), path, new)))
        self.items[path] = bound
        if spec.kind == "blank":
            cell.color(DISABLED)
            return bound
        sheet.readonly_cells(row, column, readonly=False)
        sheet.align_cells(row, column, align="e" if spec.kind in ("number", "integer") else "w")
        if spec.kind == "choice":
            options = ["", *spec.choices] if spec.nullable else list(spec.choices)
            sheet.dropdown((row, column), values=options, edit_data=False, state="readonly", validate_input=False)
        self._paint(bound)
        return bound

    def watch(self, sheet: Sheet) -> None:
        self.sheets.append(sheet)
        sheet.bind("<<SheetModified>>", lambda event: self.modified(sheet), add="+")

    def modified(self, sheet: Sheet) -> None:
        for bound in [bound for bound in self.items.values() if bound.cell.sheet is sheet]:
            text = bound.cell.get()
            if text != bound.shown:
                self._enter(bound, text)
        self.paint()
        self._changed()

    def _enter(self, bound: Bound, text: str) -> None:
        try:
            value = enter(bound.spec, text)
        except EntryError as exc:
            self.refused[bound.path] = str(exc)
            bound.shown = text
            return
        try:
            bound.write(value)
        except EditorError as exc:
            self.refused[bound.path] = str(exc)
            bound.shown = text
            return
        self.refused.pop(bound.path, None)
        bound.shown = display(bound.spec, value)
        if bound.shown != text:
            bound.cell.show(bound.shown)

    def refresh(self) -> None:
        """Show the document's values again, after the editor wrote some itself."""
        for bound in self.items.values():
            if bound.path in self.refused:
                continue
            value = self.value(bound.path)
            bound.shown = "" if value is MISSING else display(bound.spec, value)
            bound.cell.show(bound.shown)
        self.paint()

    def message(self, path: JsonPath) -> str | None:
        """Why the cell at *path* is marked, or None."""
        if path in self.refused:
            return self.refused[path]
        value = self.value(path)
        return None if value is MISSING else problem(self.items[path].spec, value)

    def problems(self) -> list[tuple[JsonPath, str]]:
        found = [(path, self.message(path)) for path in self.items]
        return [(path, message) for path, message in found if message is not None]

    def _paint(self, bound: Bound) -> None:
        if bound.spec.kind == "blank":
            return
        if bound.path in self.refused:
            bound.cell.color(REFUSED)
        else:
            bound.cell.color(MISSING_COLOR if self.message(bound.path) else EDITABLE)

    def paint(self) -> None:
        for bound in self.items.values():
            self._paint(bound)

    def commit(self) -> None:
        for sheet in self.sheets:
            if sheet.winfo_exists():
                commit_editor(sheet)

    @property
    def pending(self) -> bool:
        return any(sheet.winfo_exists() and pending_dirty(sheet) for sheet in self.sheets)

    def first_refusal(self) -> str | None:
        for path, message in self.refused.items():
            return f"{path_text(path)}: {message}"
        return None
