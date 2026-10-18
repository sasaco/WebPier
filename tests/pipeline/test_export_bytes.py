"""``export_bytes``: the bytes of one export, as a generation writes them, without rendering any report.

The real-app acceptance (scripts/accept_jrsnap_ndu.py, scripts/check_frameweb_headless.py) and its tests rebuild
the candidate files with it, so they compare exactly the bytes the CLI would publish.
"""

from __future__ import annotations

import pytest

from pipeline_support import CURRENT, Recorder, copy_input, fake_registry
from webpier.core.errors import InputError
from webpier.core.integrity import load_json
from webpier.inputs import parse_input
from webpier.pipeline import generate
from webpier.pipeline.generate import GenerationOptions, export_bytes, prepare


@pytest.fixture(scope="module")
def pier():
    return parse_input(load_json(CURRENT.read_bytes()))


def test_calculates_the_closure_and_renders_nothing(pier):
    recorder = Recorder()
    assert export_bytes(pier, "C", "jrsnap", registry=fake_registry(recorder)) == b"NDU C\r\n"
    assert recorder.actions("calculate") == ["A", "B", "C"]
    assert recorder.actions("render") == []
    assert recorder.log[-1] == ("export", "C", ("B", "C"))  # its dependencies and itself, as in a generation


def test_an_export_of_an_earlier_stage_calculates_only_its_closure(pier):
    recorder = Recorder()
    assert export_bytes(pier, "B", "frameweb", registry=fake_registry(recorder)) == b'{"B": 1}\n'
    assert recorder.actions("calculate") == ["A", "B"]


def test_equals_the_staged_file_of_a_generation(tmp_path, monkeypatch, pier):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {})
    recorder = Recorder()
    registry = fake_registry(recorder)
    options = GenerationOptions(copy_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post", stage="C")
    with prepare(options, registry=registry) as candidate:
        staged = candidate.staged("C.jrsnap").read_bytes()
    generation_log = [entry for entry in recorder.log if entry[0] == "export"]
    recorder.log.clear()
    assert export_bytes(pier, "C", "jrsnap", registry=registry) == staged
    assert [entry for entry in recorder.log if entry[0] == "export"] == generation_log


@pytest.mark.parametrize("stage,kind,message", [("X", "jrsnap", "計算段階が不正です: X"),
                                                ("A", "frameweb", "Aにframeweb の出力はありません"),
                                                ("B", "jrsnap", "Bにjrsnap の出力はありません")])
def test_an_unknown_stage_or_export_is_an_error(pier, stage, kind, message):
    recorder = Recorder()
    with pytest.raises(InputError, match=message):
        export_bytes(pier, stage, kind, registry=fake_registry(recorder))
    assert recorder.log == []
