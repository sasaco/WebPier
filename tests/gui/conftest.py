"""Tk fixtures of the editor tests: a fresh, withdrawn root per test, destroyed afterwards, and a settings file of
the test's own."""

import gc
import time
import tkinter as tk
from pathlib import Path

import pytest

CURRENT = Path(__file__).parents[1] / "fixtures" / "inputs" / "current.json"


def new_root() -> tk.Tk:
    """A Tk root; creation is retried because Tk sometimes cannot read its library files for a moment."""
    for attempt in range(5):
        try:
            return tk.Tk()
        except tk.TclError as exc:
            failure = exc
            time.sleep(0.2 * (attempt + 1))
    pytest.skip(f"Tk display unavailable: {failure}")


@pytest.fixture
def tk_root():
    root = new_root()
    root.withdraw()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    yield root
    try:
        # A timer of a destroyed root would still fire during a later test. Cancel it in Tcl only: after_cancel
        # would delete the callback's command, which its widget then fails to delete again, stopping destroy().
        for event in root.tk.splitlist(root.tk.call("after", "info")):
            root.tk.call("after", "cancel", event)
        root.destroy()
    except tk.TclError:
        pass
    gc.collect()  # finalize this root's images here, not on a worker thread of a later test
    assert not errors, errors


@pytest.fixture
def quiet(monkeypatch):
    """Message boxes record their calls instead of blocking; answers come from *answers*."""
    from tkinter import messagebox

    calls = []
    answers = {}

    def recorder(name):
        def show(*args, **kwargs):
            calls.append((name, *args))
            return answers.get(name)
        return show

    for name in ("showerror", "showwarning", "showinfo", "askyesno", "askyesnocancel"):
        monkeypatch.setattr(messagebox, name, recorder(name))
    return calls, answers


@pytest.fixture
def input_path(tmp_path):
    path = tmp_path / "input.json"
    path.write_bytes(CURRENT.read_bytes())
    return path


@pytest.fixture(autouse=True)
def editor_settings(tmp_path, monkeypatch):
    """Each test's own editor settings file: no test reads or writes the user's %APPDATA% (decision 46)."""
    from webpier.gui import settings

    path = tmp_path / "appdata" / "WebPier" / "editor.json"
    monkeypatch.setattr(settings, "SETTINGS_FILE", path)
    return path
