"""Destroy widgets together with the Tcl timers their callbacks still have pending.

tkinter names the Tcl command of a Python callback ``id(function) + function.__name__``. Destroying a widget
deletes its commands but not the ``after``/``after_idle`` timers that call them (tksheet schedules such timers
when a sheet is created or redrawn). Once Python frees the function, a new callback can get the same id, hence
the same command name, and the stale timer then calls that unrelated callback: a button command or a key
binding runs by itself, or a callback fails for a missing argument. Which callback is hit depends on memory reuse,
so it shows only in some runs (the order-dependent failure of the old column editor test). The editor rebuilds
pages often, so it cancels those timers whenever it destroys widgets.
"""

from __future__ import annotations

import tkinter as tk


def _commands(widget: tk.Misc) -> set[str]:
    names: set[str] = set()
    pending = [widget]
    while pending:
        current = pending.pop()
        names.update(getattr(current, "_tclCommands", None) or ())
        pending.extend(current.winfo_children())
    return names


def cancel_timers(widget: tk.Misc) -> int:
    """Cancel the pending timers that call callbacks of *widget* or its descendants; return how many."""
    commands = _commands(widget)
    cancelled = 0
    for event in widget.tk.splitlist(widget.tk.call("after", "info")):
        try:
            script = widget.tk.splitlist(widget.tk.call("after", "info", event))[0]
        except tk.TclError:  # fired or cancelled meanwhile
            continue
        words = widget.tk.splitlist(script)
        if words and words[0] in commands:
            widget.tk.call("after", "cancel", event)
            cancelled += 1
    return cancelled


def destroy(widget: tk.Misc) -> None:
    try:
        cancel_timers(widget)
        widget.destroy()
    except tk.TclError:
        pass  # already destroyed with its parent


def destroy_children(widget: tk.Misc) -> None:
    for child in widget.winfo_children():
        destroy(child)
