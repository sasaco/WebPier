"""The editor's settings of one user (decision 46): kept in %APPDATA%\\WebPier, apart from the input JSON."""

import json
import os
from pathlib import Path

import pytest

from webpier.gui import settings
from webpier.gui.settings import EditorSettings, default_path, load_settings, save_settings


def test_the_file_is_in_the_users_appdata():
    assert default_path({"APPDATA": r"C:\Users\u\AppData\Roaming"}) == Path(
        r"C:\Users\u\AppData\Roaming\WebPier\editor.json")
    assert default_path({}) == Path.home() / "AppData" / "Roaming" / "WebPier" / "editor.json"


def test_the_tests_never_use_the_real_file(editor_settings):
    assert settings.SETTINGS_FILE == editor_settings
    if os.environ.get("APPDATA"):
        assert Path(os.environ["APPDATA"]) not in editor_settings.parents


def test_without_a_file_the_defaults(tmp_path):
    assert load_settings(tmp_path / "none.json") == EditorSettings(frame_analysis=False)


def test_saved_settings_are_read_back(tmp_path):
    path = tmp_path / "WebPier" / "editor.json"
    save_settings(EditorSettings(frame_analysis=True), path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"frame_analysis": True}
    assert load_settings(path) == EditorSettings(frame_analysis=True)
    assert sorted(item.name for item in path.parent.iterdir()) == ["editor.json"]
    save_settings(EditorSettings(), path)
    assert load_settings(path) == EditorSettings(frame_analysis=False)


@pytest.mark.parametrize("content", [b"not json", b"[]", b'{"frame_analysis": 1}', b'{"frame_analysis": true, "x": 1}',
                                     b"{}", b'{"frame_analysis": true, "frame_analysis": false}'])
def test_an_unreadable_file_gives_the_defaults(tmp_path, content):
    """A convenience of the editor: a broken file is not an input error, and the next change rewrites it."""
    path = tmp_path / "editor.json"
    path.write_bytes(content)
    assert load_settings(path) == EditorSettings()


def test_a_directory_in_place_of_the_file_gives_the_defaults(tmp_path):
    (tmp_path / "editor.json").mkdir()
    assert load_settings(tmp_path / "editor.json") == EditorSettings()
