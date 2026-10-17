"""The files of a generation, known before it runs (the editor checks a finished generation against them)."""

from pathlib import Path

import pytest

from pipeline_support import Recorder, fake_registry
from webpier.core.errors import InputError
from webpier.pipeline.generate import GenerationOptions, planned
from webpier.pipeline.stages import STAGES


def options(stage="all", opt_in=frozenset()):
    return GenerationOptions(Path("pre/input.json"), Path("out"), Path("post"), stage=stage, opt_in=opt_in)


def test_the_planned_files_of_a_fake_registry():
    registry = fake_registry(Recorder())
    roles = [artifact.role for artifact in planned(options(opt_in=frozenset({"jrsnap"})), registry=registry)]
    assert roles[:6] == ["A.pdf", "A.json", "B.pdf", "B.json", "C.pdf", "C.json"]
    assert {role for role in roles[6:]} == {"B.frameweb", "C.jrsnap", "B.frameweb.provenance", "C.jrsnap.provenance"}
    single = planned(options("B"), registry=registry)
    assert [(artifact.role, artifact.path, artifact.directory) for artifact in single] == [
        ("B.pdf", Path("out") / "B_荷重.pdf", "output"), ("B.json", Path("out") / "B_荷重.json", "output"),
        ("B.frameweb", Path("post") / "frame.json", "post"),
        ("B.frameweb.provenance", Path("post") / "frame.json.provenance.json", "post")]


def test_the_real_registry_plans_every_report_and_the_requested_exports():
    names = [artifact.path.name for artifact in planned(options())]
    assert names[:12:2] == [f"{stage.stem}.pdf" for stage in STAGES.stages]
    assert "線路方向.ndu" not in names
    assert "線路方向.ndu" in [artifact.path.name for artifact in planned(options(opt_in=frozenset({"jrsnap"})))]


def test_an_invalid_selection_is_an_input_error():
    with pytest.raises(InputError):
        planned(options("9999"))
    with pytest.raises(InputError):
        planned(options("0500", frozenset({"jrsnap"})))
