"""Destroyed widgets leave no timers behind that could call a later callback (the old flaky test's cause)."""

import tkinter as tk
from tkinter import ttk

from webpier.gui.grid import make_sheet
from webpier.gui.lifecycle import cancel_timers, destroy, destroy_children


def stale(root):
    """Pending timers whose callback command no longer exists."""
    found = []
    for event in root.tk.splitlist(root.tk.call("after", "info")):
        script = root.tk.splitlist(root.tk.call("after", "info", event))[0]
        name = root.tk.splitlist(script)[0]
        if not root.tk.call("info", "commands", name):
            found.append(name)
    return found


def test_plain_destroy_leaves_stale_timers_behind(tk_root):
    """The mechanism: tkinter deletes the callback's command, Tcl keeps the timer that calls it by name."""
    frame = ttk.Frame(tk_root)
    frame.after(60_000, lambda: None)
    make_sheet(frame, ["a"], [["1"]], [50])  # tksheet schedules its own timers when created
    frame.destroy()
    assert stale(tk_root)
    for event in tk_root.tk.splitlist(tk_root.tk.call("after", "info")):
        tk_root.after_cancel(event)


def test_destroy_cancels_the_timers_of_the_widget_and_its_children(tk_root):
    frame = ttk.Frame(tk_root)
    child = ttk.Label(frame)
    child.after(60_000, lambda: None)
    sheet = make_sheet(frame, ["a"], [["1"]], [50])
    sheet.after_idle(lambda: None)
    kept = tk_root.after(60_000, lambda: None)  # the root's own timer is not the frame's
    destroy(frame)
    assert not stale(tk_root)
    assert tk_root.tk.splitlist(tk_root.tk.call("after", "info")) == (kept,)
    tk_root.after_cancel(kept)
    destroy(frame)  # destroying again is harmless


def test_destroy_children_and_count(tk_root):
    frame = ttk.Frame(tk_root)
    for _ in range(3):
        ttk.Label(frame).after(60_000, lambda: None)
    assert cancel_timers(ttk.Frame(tk_root)) == 0
    destroy_children(frame)
    assert not frame.winfo_children() and not stale(tk_root)


def test_the_editor_rebuilds_pages_without_stale_timers(tk_root, input_path, quiet):
    from webpier.gui import app as gui
    editor = gui.InputEditor(tk_root, input_path)
    for page in (*gui.INPUT_PAGES, "鉄筋"):
        editor.select(page)
    editor.view.select_group("hoops")
    editor.view.select_member("梁")
    editor.select("下部構造")
    assert not stale(tk_root)
