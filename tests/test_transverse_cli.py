"""0620 private dependencies and complete report/FrameWeb publication."""

import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from src import cli
from src.inputs import InputError


PROJECT = Path(__file__).resolve().parents[1]
# Fixed historical input from fa27cca^, independent of the working input.
BASELINE = PROJECT / "tests" / "fixtures" / "baseline_input.json"
STEMS = ("0500_直接基礎", "0600_上部工反力", "0610_線路方向荷重", "0620_直角方向荷重", "0710_線路方向荷重", "0720_線路直角方向荷重")
NAMES = tuple(f"{stem}.{suffix}" for stem in STEMS for suffix in ("pdf", "json"))
RENDERERS = (("report", "render_report"), ("reaction_report", "render_reaction_report"),
             ("longitudinal_report", "render_longitudinal_report"), ("transverse_report", "render_transverse_report"),
             ("seismic_longitudinal_report", "render_seismic_longitudinal_report"),
             ("seismic_transverse_report", "render_seismic_transverse_report"))


@pytest.fixture
def quick_reports(monkeypatch):
    # Rendering is replaced here; real runtime identity has dedicated tests.
    source = Path(cli.__file__).resolve()
    monkeypatch.setattr(cli, "implementation_hashes", lambda: {source: cli.file_sha256(source)})
    for module, function in RENDERERS:
        if importlib.util.find_spec(f"src.{module}"):
            monkeypatch.setattr(f"src.{module}.{function}", lambda result, path: Path(path).write_bytes(b"new PDF"))


def write_input(tmp_path, mutate):
    data = json.loads((PROJECT / "pre" / "input.json").read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_0620_publishes_only_its_four_artifacts_and_is_independent_of_0610_errors(tmp_path, quick_reports, monkeypatch):
    originals = {name: ("old " + name).encode("utf-8") for name in (*NAMES[:6], *NAMES[8:])}
    for name, value in originals.items():
        (tmp_path / name).write_bytes(value)

    def fail_0610(*args):
        raise InputError("0610 specific failure must not affect 0620")

    monkeypatch.setattr(cli, "calculate_longitudinal", fail_0610)
    counts = {"0500": 0, "0600": 0}
    for attribute, stage in (("calculate", "0500"), ("calculate_reactions", "0600")):
        actual = getattr(cli, attribute)

        def counted(*args, _actual=actual, _stage=stage, **kwargs):
            counts[_stage] += 1
            return _actual(*args, **kwargs)

        monkeypatch.setattr(cli, attribute, counted)
    # Use the projection-compatible P7 input for publication wiring. The old
    # baseline's wind q=2.625 is covered by the explicit rejection test below.
    data = json.loads((PROJECT / "pre" / "input.json").read_text(encoding="utf-8"))
    source = tmp_path.parent / (tmp_path.name + "-input.json")
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert cli.main(["--stage", "0620", "--input", str(source), "--output-dir", str(tmp_path)]) == 0
    assert counts == {"0500": 1, "0600": 1}
    assert {path.name for path in tmp_path.iterdir()} == set(NAMES) | {"post"}
    assert {path.name for path in (tmp_path / "post").iterdir()} == {
        "線路直角方向.json", "線路直角方向.provenance.json"}
    assert all((tmp_path / name).read_bytes() == value for name, value in originals.items())
    result = json.loads((tmp_path / NAMES[7]).read_text(encoding="utf-8"))
    assert result["stage"] == "0620"
    assert result["frame"]["sections"]["body"]["inertia"] == 20.50313


@pytest.mark.parametrize("stage", ["0620", "all"])
def test_old_baseline_projection_loss_stops_before_render_and_preserves_all_outputs(tmp_path, monkeypatch, capsys, stage):
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    data["鉄筋"] = {part: {"concrete_strength_mpa": 27} for part in ("梁", "柱", "フーチング")}
    source = tmp_path / "input.json"
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    source_bytes = source.read_bytes()
    output = tmp_path / "output"
    post = output / "post"
    post.mkdir(parents=True)
    paths = [*(output / name for name in NAMES), *(post / name for name in (
        "frameWebForJS.json", "frameWebForJS.provenance.json", "線路直角方向.json", "線路直角方向.provenance.json"))]
    originals = {path: ("old " + path.name).encode("utf-8") for path in paths}
    for path, content in originals.items():
        path.write_bytes(content)
    def unexpected(*args, **kwargs):
        pytest.fail("Projection loss must be rejected before rendering or publication")
    for module, renderer in RENDERERS:
        monkeypatch.setattr(f"src.{module}.{renderer}", unexpected)
    monkeypatch.setattr(cli, "_publish_outputs", unexpected)
    assert cli.main(["--stage", stage, "--input", str(source), "--output-dir", str(output), "--overwrite"]) == 2
    error = capsys.readouterr().err
    assert "native.load.16.load_member" in error and "2.625 -> 2.63" in error
    assert {path: path.read_bytes() for path in paths} == originals
    assert source.read_bytes() == source_bytes
    assert not list(output.rglob(".pier-design-*"))


def test_all_calculations_complete_once_before_first_report(tmp_path, quick_reports, monkeypatch):
    counts = {stage: 0 for stage in ("0500", "0600", "0610", "0620", "0710", "0720")}
    for attribute, stage in (("calculate", "0500"), ("calculate_reactions", "0600"),
                             ("calculate_longitudinal", "0610"), ("calculate_transverse", "0620"),
                             ("calculate_seismic_longitudinal", "0710"),
                             ("calculate_seismic_transverse", "0720")):
        actual = getattr(cli, attribute, None)
        assert actual is not None, f"CLI must wire {stage} calculation"

        def counted(*args, _actual=actual, _stage=stage, **kwargs):
            counts[_stage] += 1
            return _actual(*args, **kwargs)

        monkeypatch.setattr(cli, attribute, counted)

    def verify_ready(result, path):
        assert counts == {stage: 1 for stage in counts}
        Path(path).write_bytes(b"new PDF")

    for module, function in RENDERERS:
        monkeypatch.setattr(f"src.{module}.{function}", verify_ready)
    assert cli.main(["--output-dir", str(tmp_path)]) == 0
    assert {path.name for path in tmp_path.iterdir()} == set(NAMES) | {"post"}


@pytest.mark.parametrize("missing", ["地盤データ", "上部構造", "上部工反力"])
def test_0620_validates_both_dependencies_before_render(tmp_path, monkeypatch, missing):
    source = write_input(tmp_path, lambda data: data.pop(missing))

    def unexpected(*args):
        pytest.fail("No report may render before all dependencies validate")

    for module, function in RENDERERS:
        if importlib.util.find_spec(f"src.{module}"):
            monkeypatch.setattr(f"src.{module}.{function}", unexpected)
    output = tmp_path / "output"
    assert cli.main(["--stage", "0620", "--input", str(source), "--output-dir", str(output)]) == 2
    assert not output.exists()


def test_0620_zero_footing_gamma_rejected_but_0600_remains_valid(tmp_path, quick_reports):
    source = write_input(tmp_path, lambda data: data["下部構造"]["単位体積重量"].update(フーチング=0))
    for stage, expected in (("0600", 0), ("0620", 2)):
        output = tmp_path / stage
        assert cli.main(["--stage", stage, "--input", str(source), "--output-dir", str(output)]) == expected
        assert output.exists() == (expected == 0)


def test_0610_does_not_call_0620_or_validate_its_transverse_section(tmp_path, quick_reports, monkeypatch):
    def fail(*args):
        raise InputError("0620-specific failure")

    monkeypatch.setattr(cli, "calculate_transverse", fail, raising=False)
    assert cli.main(["--stage", "0610", "--output-dir", str(tmp_path)]) == 0
    assert {path.name for path in tmp_path.iterdir()} == set(NAMES[4:6]) | {"post"}


@pytest.mark.parametrize("alias", [False, True])
def test_0620_input_output_collision_preserves_input(tmp_path, alias, capsys):
    source = (PROJECT / "pre" / "input.json").read_bytes()
    path = tmp_path / NAMES[7]
    path.write_bytes(source)
    if alias:
        (tmp_path / "alias").mkdir()
        path = tmp_path / "alias" / ".." / NAMES[7]
    assert cli.main(["--stage", "0620", "--input", str(path), "--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert path.read_bytes() == source
    assert "同じパス" in capsys.readouterr().err
    assert not (tmp_path / NAMES[6]).exists()


@pytest.mark.parametrize("name", NAMES[6:8])
def test_0620_directory_collision_preserves_children(tmp_path, quick_reports, name):
    collision = tmp_path / name
    collision.mkdir()
    (collision / "keep").write_bytes(b"keep")
    assert cli.main(["--stage", "0620", "--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert (collision / "keep").read_bytes() == b"keep"
    assert not list(tmp_path.glob(".pier-design-*"))


def test_0620_symlink_collision_preserves_target(tmp_path, quick_reports):
    target = tmp_path / "keep.txt"
    target.write_bytes(b"keep")
    link = tmp_path / NAMES[7]
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Platform cannot create symlink: {exc}")
    assert cli.main(["--stage", "0620", "--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert link.is_symlink()
    assert target.read_bytes() == b"keep"


def test_0620_render_failure_prevents_all_report_publications(tmp_path, monkeypatch, quick_reports):
    renderer = importlib.import_module("src.transverse_report")
    originals = {name: ("old " + name).encode("utf-8") for name in NAMES}
    for name, value in originals.items():
        (tmp_path / name).write_bytes(value)

    def fail(*args):
        raise OSError("0620 report failure")

    monkeypatch.setattr(renderer, "render_transverse_report", fail)
    assert cli.main(["--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == originals


@pytest.mark.parametrize("side,width", [("側面", "B3"), ("正面", "W3")])
@pytest.mark.parametrize("value", [0, 0.01], ids=["zero", "rounded_zero_inertia"])
def test_0620_invalid_h1_section_preserves_all_existing_outputs_before_render(tmp_path, monkeypatch, capsys, side, width, value):
    data = json.loads((PROJECT / "tests/fixtures/pier_models/parapet-asymmetric.json").read_text(encoding="utf-8"))
    data["鉄筋"] = {part: {"concrete_strength_mpa": 27} for part in ("梁", "柱", "フーチング")}
    if value == 0:
        data["下部構造"]["寸法"][side][width] = 0
    else:
        data["下部構造"]["寸法"]["側面"]["B3"] = 0.01
        data["下部構造"]["寸法"]["正面"]["W3"] = 0.1
    source = tmp_path / "input.json"
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    source_bytes = source.read_bytes()
    output = tmp_path / "output"
    output.mkdir()
    originals = {name: ("old " + name).encode("utf-8") for name in NAMES}
    for name, content in originals.items():
        (output / name).write_bytes(content)

    def unexpected(*args):
        pytest.fail("0620 H1 validation must finish before report generation")

    for module, renderer in RENDERERS:
        monkeypatch.setattr(f"src.{module}.{renderer}", unexpected)
    assert cli.main(["--stage", "0620", "--input", str(source), "--output-dir", str(output), "--overwrite"]) == 2
    error = capsys.readouterr().err
    assert "0620.input.geometry." in error
    assert width.lower() in error
    assert source.read_bytes() == source_bytes
    assert {path.name: path.read_bytes() for path in output.iterdir()} == originals


@pytest.mark.parametrize("part", ["梁", "柱", "フーチング"])
def test_0620_requires_materials_without_changing_0600(tmp_path, quick_reports, part):
    source = write_input(tmp_path, lambda data: data["鉄筋"][part].pop("concrete_strength_mpa"))
    for stage, expected in (("0600", 0), ("0620", 2)):
        output = tmp_path / stage
        assert cli.main(["--stage", stage, "--input", str(source), "--output-dir", str(output)]) == expected
        assert output.exists() == (expected == 0)
