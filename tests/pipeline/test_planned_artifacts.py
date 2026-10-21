"""The files of a generation, known before it runs (the editor checks a finished generation against them), and the
stages the input's 出力項目 choose (decision 72)."""

from pathlib import Path

import pytest

from pipeline_support import LONGITUDINAL, Recorder, choose, copy_input, fake_registry
from webpier.core.errors import InputError
from webpier.pipeline.generate import GenerationOptions, planned, selection
from webpier.pipeline.stages import STAGES

# The 出力項目 current.json chooses: every item but the frame analysis, the static nonlinear analysis, the footing and
# the cantilever.
DEFAULT = ("ground_model", "reactions", "longitudinal", "transverse", "longitudinal_seismic", "transverse_seismic")


def options():
    return GenerationOptions(Path("pre/input.json"), Path("out"), Path("post"))


def test_the_planned_files_of_a_fake_registry():
    registry = fake_registry(Recorder())
    roles = [artifact.role for artifact in planned(options(), registry.ids, registry=registry)]
    assert roles[:6] == ["A.pdf", "A.json", "B.pdf", "B.json", "C.pdf", "C.json"]
    assert {role for role in roles[6:]} == {"B.frameweb", "C.jrsnap", "B.frameweb.provenance", "C.jrsnap.provenance"}
    frame = planned(options(), registry.selected(LONGITUDINAL), registry=registry)
    assert [(artifact.role, artifact.path, artifact.directory) for artifact in frame] == [
        ("A.pdf", Path("out") / "A_基礎.pdf", "output"), ("A.json", Path("out") / "A_基礎.json", "output"),
        ("B.pdf", Path("out") / "B_荷重.pdf", "output"), ("B.json", Path("out") / "B_荷重.json", "output"),
        ("B.frameweb", Path("post") / "frame.json", "post"),
        ("B.frameweb.provenance", Path("post") / "frame.json.provenance.json", "post")]


def test_the_real_registry_plans_every_report_and_every_export():
    found = planned(options(), STAGES.selected(DEFAULT))
    names = [artifact.path.name for artifact in found]
    reports = [STAGES.get(stage) for stage in STAGES.selected(DEFAULT)]
    assert names[:18] == [f"{stage.stem}.{suffix}" for stage in reports for suffix in ("pdf", "json", "xlsx")]
    assert names[18:] == ["線路方向.json", "線路直角方向.json", "線路方向.ndu", "線路直角方向.ndu",
                          "線路方向.json.provenance.json", "線路直角方向.json.provenance.json",
                          "線路方向.ndu.provenance.json", "線路直角方向.ndu.provenance.json"]
    assert [artifact.path.name for artifact in planned(options(), STAGES.selected(("transverse_seismic",)))][3:] == [
        "線路直角方向.ndu", "線路直角方向.ndu.provenance.json"]


def test_the_grid_excel_workbooks_go_to_export_beside_the_output_or_where_given():
    workbooks = [artifact for artifact in planned(options(), STAGES.selected(DEFAULT))
                 if artifact.role.endswith(".xlsx")]
    assert {(artifact.directory, artifact.path.parent) for artifact in workbooks} == {
        ("export", Path("out").resolve().parent / "export")}
    given = GenerationOptions(Path("pre/input.json"), Path("out"), Path("post"), export_dir=Path("book"))
    assert [(artifact.role, artifact.path) for artifact in planned(given, STAGES.selected(("ground_model",)))] == [
        ("0500.pdf", Path("out") / "0500_直接基礎.pdf"), ("0500.json", Path("out") / "0500_直接基礎.json"),
        ("0500.xlsx", Path("book") / "0500_直接基礎.xlsx")]


def test_a_report_of_another_program_plans_no_workbook():
    found = planned(options(), STAGES.selected(("longitudinal_nonlinear_analysis",)))
    assert [artifact.role for artifact in found if artifact.role.startswith("0711.")][:3] == [
        "0711.pdf", "0711.json", "0711.jrsnap"]


def test_the_selection_is_the_stages_of_the_items_the_input_chooses(tmp_path):
    """Decision 72: ``selection`` reads the input strictly; choosing nothing is an input error."""
    path = copy_input(tmp_path, "ground_model", "reactions", "transverse", "transverse_frame_analysis")
    given = GenerationOptions(path, tmp_path / "out", tmp_path / "post")
    assert selection(given) == ("0500", "0600", "0620", "0621", "0622")
    choose(path)
    with pytest.raises(InputError, match="outputs: 出力項目が選ばれていません"):
        selection(given)
