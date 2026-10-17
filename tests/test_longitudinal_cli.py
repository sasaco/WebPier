"""0610 dependency selection and isolation from previously published stages."""

import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from src import cli


PROJECT = Path(__file__).resolve().parents[1]
# Fixed historical input from fa27cca^, independent of the working input.
BASELINE = PROJECT / "tests" / "fixtures" / "baseline_input.json"
STEMS = ("0500_直接基礎", "0600_上部工反力", "0610_線路方向荷重")
NAMES = tuple(f"{stem}.{suffix}" for stem in STEMS for suffix in ("pdf", "json"))
ALL_NAMES = (*NAMES, "0620_直角方向荷重.pdf", "0620_直角方向荷重.json",
             "0710_線路方向荷重.pdf", "0710_線路方向荷重.json",
             "0720_線路直角方向荷重.pdf", "0720_線路直角方向荷重.json")


@pytest.fixture
def data():
    return json.loads((PROJECT / "pre" / "input.json").read_text(encoding="utf-8"))


@pytest.fixture
def quick_reports(monkeypatch):
    # Rendering is replaced here; real runtime identity has dedicated tests.
    source = Path(cli.__file__).resolve()
    monkeypatch.setattr(cli, "implementation_hashes", lambda: {source: cli.file_sha256(source)})
    def render(result, path):
        Path(path).write_bytes(b"new PDF")

    monkeypatch.setattr("src.report.render_report", render)
    monkeypatch.setattr("src.reaction_report.render_reaction_report", render)
    if importlib.util.find_spec("src.longitudinal_report"):
        monkeypatch.setattr("src.longitudinal_report.render_longitudinal_report", render)
    if importlib.util.find_spec("src.transverse_report"):
        monkeypatch.setattr("src.transverse_report.render_transverse_report", render)
    monkeypatch.setattr("src.seismic_longitudinal_report.render_seismic_longitudinal_report", render)
    monkeypatch.setattr("src.seismic_transverse_report.render_seismic_transverse_report", render)


def write_input(tmp_path, data):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_0610_publishes_its_pair_and_post_and_preserves_upstream(tmp_path, quick_reports):
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    for part in ("梁", "柱", "フーチング"):
        data.setdefault("鉄筋", {}).setdefault(part, {})["concrete_strength_mpa"] = 27
    source = write_input(tmp_path, data)
    output = tmp_path / "output"
    output.mkdir()
    originals = {name: ("old " + name).encode("utf-8") for name in NAMES[:4]}
    for name, content in originals.items():
        (output / name).write_bytes(content)
    assert cli.main(["--stage", "0610", "--input", str(source), "--output-dir", str(output)]) == 0
    assert {path.name for path in output.iterdir()} == set(NAMES) | {"post"}
    for name, content in originals.items():
        assert (output / name).read_bytes() == content
    result = json.loads((output / NAMES[-1]).read_text(encoding="utf-8"))
    assert result["stage"] == "0610"
    assert result["schema_version"] == 2
    assert result["vertical"]["fixed"]["top"]["N"] == 1956.77


@pytest.mark.parametrize("missing", ["地盤データ", "上部構造", "上部工反力"])
def test_0610_validates_both_dependencies_before_render(tmp_path, data, missing, monkeypatch):
    del data[missing]
    source = write_input(tmp_path, data)

    def unexpected(*args):
        pytest.fail("Dependencies must validate before any report is rendered")

    monkeypatch.setattr("src.report.render_report", unexpected)
    monkeypatch.setattr("src.reaction_report.render_reaction_report", unexpected)
    if importlib.util.find_spec("src.longitudinal_report"):
        monkeypatch.setattr("src.longitudinal_report.render_longitudinal_report", unexpected)
    output = tmp_path / "output"
    assert cli.main(["--stage", "0610", "--input", str(source), "--output-dir", str(output)]) == 2
    assert not output.exists()


def test_zero_footing_gamma_stays_valid_for_0600_but_fails_0610(tmp_path, data, quick_reports):
    data["下部構造"]["単位体積重量"]["フーチング"] = 0
    source = write_input(tmp_path, data)
    for stage, expected in (("0600", 0), ("0610", 2)):
        output = tmp_path / stage
        assert cli.main(["--stage", stage, "--input", str(source), "--output-dir", str(output)]) == expected
        assert output.exists() == (expected == 0)


@pytest.mark.parametrize("stage", ["0610", "all"])
def test_each_dependency_is_calculated_once(tmp_path, monkeypatch, quick_reports, stage):
    counts = {"0500": 0, "0600": 0}
    for attribute, label in (("calculate", "0500"), ("calculate_reactions", "0600")):
        actual = getattr(cli, attribute)

        def counted(*args, _actual=actual, _label=label, **kwargs):
            counts[_label] += 1
            return _actual(*args, **kwargs)

        monkeypatch.setattr(cli, attribute, counted)
    assert cli.main(["--stage", stage, "--output-dir", str(tmp_path)]) == 0
    assert counts == {"0500": 1, "0600": 1}
    assert {path.name for path in tmp_path.iterdir()} == set(NAMES[-2:] if stage == "0610" else ALL_NAMES) | {"post"}


@pytest.mark.parametrize("alias", [False, True])
def test_0610_input_output_collision_preserves_input(tmp_path, alias, capsys):
    source = (PROJECT / "pre" / "input.json").read_bytes()
    path = tmp_path / NAMES[-1]
    path.write_bytes(source)
    if alias:
        (tmp_path / "alias").mkdir()
        path = tmp_path / "alias" / ".." / NAMES[-1]
    assert cli.main(["--stage", "0610", "--input", str(path), "--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert path.read_bytes() == source
    assert "同じパス" in capsys.readouterr().err
    assert not (tmp_path / NAMES[-2]).exists()


@pytest.mark.parametrize("name", NAMES[-2:])
def test_0610_directory_collision_keeps_existing_contents(tmp_path, name, quick_reports):
    destination = tmp_path / name
    destination.mkdir()
    (destination / "keep").write_bytes(b"keep")
    assert cli.main(["--stage", "0610", "--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert (destination / "keep").read_bytes() == b"keep"
    assert not list(tmp_path.glob(".webpier-*"))


def test_0610_symlink_collision_preserves_target(tmp_path, quick_reports):
    target = tmp_path / "keep.txt"
    target.write_bytes(b"keep")
    link = tmp_path / NAMES[-1]
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Platform cannot create symlink: {exc}")
    assert cli.main(["--stage", "0610", "--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert link.is_symlink()
    assert target.read_bytes() == b"keep"


def test_failed_0610_report_preserves_old_six_and_creates_no_0620(tmp_path, monkeypatch, quick_reports):
    renderer = importlib.import_module("src.longitudinal_report")
    originals = {name: ("old " + name).encode("utf-8") for name in NAMES}
    for name, content in originals.items():
        (tmp_path / name).write_bytes(content)

    def fail_report(*args):
        raise OSError("0610 report failure")

    monkeypatch.setattr(renderer, "render_longitudinal_report", fail_report)
    assert cli.main(["--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == originals


@pytest.mark.parametrize("stage", ["0610", "all"])
@pytest.mark.parametrize("side,width", [("側面", "B3"), ("正面", "W3")])
@pytest.mark.parametrize("value", [0, 0.01], ids=["zero", "rounded_zero_inertia"])
def test_invalid_h1_section_fails_before_any_render_or_publication(tmp_path, monkeypatch, capsys, stage, side, width, value):
    data = json.loads((PROJECT / "tests/fixtures/pier_models/parapet-asymmetric.json").read_text(encoding="utf-8"))
    for part in ("梁", "柱", "フーチング"):
        data.setdefault("鉄筋", {}).setdefault(part, {})["concrete_strength_mpa"] = 27
    if value == 0:
        data["下部構造"]["寸法"][side][width] = 0
    else:
        # A=.001 remains valid for0600; both directional I values round to0.
        data["下部構造"]["寸法"]["側面"]["B3"] = 0.01
        data["下部構造"]["寸法"]["正面"]["W3"] = 0.1
    source = write_input(tmp_path, data)
    source_bytes = source.read_bytes()
    output = tmp_path / "output"
    output.mkdir()
    originals = {name: ("old " + name).encode("utf-8") for name in ALL_NAMES}
    for name, content in originals.items():
        (output / name).write_bytes(content)

    def unexpected(*args):
        pytest.fail("H1 model validation must precede every report")

    for module, renderer in (("report", "render_report"), ("reaction_report", "render_reaction_report"),
                             ("longitudinal_report", "render_longitudinal_report"),
                             ("transverse_report", "render_transverse_report"),
                             ("seismic_longitudinal_report", "render_seismic_longitudinal_report"),
                             ("seismic_transverse_report", "render_seismic_transverse_report")):
        monkeypatch.setattr(f"src.{module}.{renderer}", unexpected)
    assert cli.main(["--stage", stage, "--input", str(source), "--output-dir", str(output), "--overwrite"]) == 2
    error = capsys.readouterr().err
    assert "0610.input.geometry." in error
    assert width.lower() in error
    assert source.read_bytes() == source_bytes
    assert {path.name: path.read_bytes() for path in output.iterdir()} == originals


@pytest.mark.parametrize("side,width", [("側面", "B3"), ("正面", "W3")])
@pytest.mark.parametrize("value", [0, 0.01], ids=["zero", "rounded_zero_inertia"])
def test_0600_alone_keeps_legacy_h1_zero_volume_contract(tmp_path, quick_reports, side, width, value):
    data = json.loads((PROJECT / "tests/fixtures/pier_models/parapet-asymmetric.json").read_text(encoding="utf-8"))
    if value == 0:
        data["下部構造"]["寸法"][side][width] = 0
    else:
        data["下部構造"]["寸法"]["側面"]["B3"] = 0.01
        data["下部構造"]["寸法"]["正面"]["W3"] = 0.1
    source = write_input(tmp_path, data)
    source_bytes = source.read_bytes()
    output = tmp_path / "output"
    assert cli.main(["--stage", "0600", "--input", str(source), "--output-dir", str(output)]) == 0
    assert {path.name for path in output.iterdir()} == set(NAMES[2:4])
    result = json.loads((output / NAMES[3]).read_text(encoding="utf-8"))
    assert result["cells"]["橋脚自重"]["X64"] == (0 if value == 0 else 0.01)
    assert source.read_bytes() == source_bytes
