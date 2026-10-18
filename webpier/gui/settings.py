"""The editor's own settings, one file per user (decisions 46, 47): kept apart from the input JSON.

It holds whether 計算・印刷 adds the frame analysis (``--frame-analysis``) and the static nonlinear analysis
(``--nonlinear-analysis``), so the choices survive a restart of the editor. The file is
``%APPDATA%\\WebPier\\editor.json``. It is a convenience: a missing or unreadable file gives the defaults instead of
an error, and the next change rewrites it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from ..core.errors import InputError
from ..core.integrity import dump_json, load_json


@dataclass(frozen=True)
class EditorSettings:
    frame_analysis: bool = False  # 計算・印刷 adds the opt-in frame analysis stages (0611, 0621)
    nonlinear_analysis: bool = False  # 計算・印刷 adds the opt-in static nonlinear analysis stages (0711, 0721)


def default_path(environ: Mapping[str, str]) -> Path:
    """``%APPDATA%\\WebPier\\editor.json``; the roaming profile of the user's home when APPDATA is not set."""
    base = environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "WebPier" / "editor.json"


SETTINGS_FILE = default_path(os.environ)


def load_settings(path: Path) -> EditorSettings:
    """The settings saved at *path*, or the defaults when there are none or they cannot be read."""
    try:
        document = load_json(Path(path).read_bytes())
    except (OSError, InputError):
        return EditorSettings()
    names = {item.name for item in fields(EditorSettings)}
    if (not isinstance(document, dict) or set(document) != names
            or not all(isinstance(document[name], bool) for name in names)):
        return EditorSettings()
    return EditorSettings(**document)


def save_settings(settings: EditorSettings, path: Path) -> None:
    """Write *settings* to *path* whole: a temporary file beside it replaces the old one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(dump_json(asdict(settings)))
    os.replace(temporary, path)
