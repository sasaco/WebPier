"""Public 0610 schema 2, dependency selection, and atomic PDF/JSON publication."""

import hashlib
import importlib
import json
import os
from pathlib import Path

import pytest

from src import cli
from src.calculator import calculate as calculate_foundation
from src.inputs import parse_input


BASELINE = Path(__file__).parent / "fixtures" / "baseline_input.json"
STEMS = {"0500": "0500_直接基礎", "0600": "0600_上部工反力",
         "0610": "0610_線路方向荷重", "0620": "0620_直角方向荷重", "0710": "0710_線路方向荷重", "0720": "0720_線路直角方向荷重"}
NAMES = tuple(f"{stem}.{suffix}" for stem in STEMS.values() for suffix in ("pdf", "json"))
LONG_NAMES = (STEMS["0610"] + ".pdf", STEMS["0610"] + ".json")


@pytest.fixture
def data():
    value = json.loads(BASELINE.read_text(encoding="utf-8"))
    for part, strength in (("梁", 24), ("柱", 27), ("フーチング", 40)):
        value.setdefault("鉄筋", {}).setdefault(part, {})["concrete_strength_mpa"] = strength
    return value


@pytest.fixture
def publication_data():
    # CLI all now exports 0620 too. Its q projection must preserve the source
    # loads; baseline q=2.625 is tested as an explicit rejection separately.
    return json.loads((Path(__file__).parents[1] / "pre" / "input.json").read_text(encoding="utf-8"))


def write_input(tmp_path, data):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def old_outputs(directory):
    directory.mkdir()
    originals = {name: ("old " + name).encode("utf-8") for name in NAMES}
    for name, content in originals.items():
        (directory / name).write_bytes(content)
    return originals


def output_bytes(directory):
    return {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}


@pytest.fixture
def quick_reports(monkeypatch):
    # Rendering is replaced here; real runtime identity has dedicated tests.
    source = Path(cli.__file__).resolve()
    monkeypatch.setattr(cli, "implementation_hashes", lambda: {source: cli.file_sha256(source)})
    recorded = []
    def render(result, path):
        stage = result.get("stage", "0500")
        if stage in ("0610", "0620"):
            assert result["schema_version"] == 2
        recorded.append(stage)
        Path(path).write_bytes(("new PDF " + stage).encode("ascii"))
    for module, function in (("report", "render_report"), ("reaction_report", "render_reaction_report"),
                             ("longitudinal_report", "render_longitudinal_report"),
                             ("transverse_report", "render_transverse_report"),
                             ("seismic_longitudinal_report", "render_seismic_longitudinal_report"),
                             ("seismic_transverse_report", "render_seismic_transverse_report")):
        monkeypatch.setattr(importlib.import_module("src." + module), function, render)
    return recorded


def test_0610_updates_its_pair_and_post_and_publishes_canonical_materials_springs_sha(tmp_path, data, quick_reports):
    source = write_input(tmp_path, data)
    input_bytes = source.read_bytes()
    directory = tmp_path / "output"
    originals = old_outputs(directory)
    foundation = calculate_foundation(parse_input(data))
    assert cli.main(["--stage", "0610", "--input", str(source), "--output-dir", str(directory), "--overwrite"]) == 0
    assert quick_reports == ["0610"]
    assert set(output_bytes(directory)) == set(NAMES)
    assert {path.name for path in (directory / "post").iterdir()} == {
        "frameWebForJS.json", "frameWebForJS.provenance.json"}
    for name in set(NAMES) - set(LONG_NAMES):
        assert (directory / name).read_bytes() == originals[name]
    result = json.loads((directory / LONG_NAMES[1]).read_text(encoding="utf-8"))
    assert result["schema_version"] == 2
    assert result["case_model_version"] == "example2-nonseismic-pier-impact-v1"
    assert result["provenance"]["input_sha256"] == hashlib.sha256(input_bytes).hexdigest()
    for part, fck, ec in (("beam", 24, 25e6), ("column", 27, 26.5e6), ("footing", 40, 31e6)):
        assert result["frame"]["materials"][part]["fck"] == fck
        assert result["frame"]["materials"][part]["Ec"] == ec
    for term in ("long_term", "short_term"):
        assert result["frame"]["springs"][term] == {
            "Kv": foundation[term]["Kv"], "Ks": foundation[term]["Ks"], "Kr": foundation[term]["Kr_longitudinal"]}
    assert result["frame"]["spring_provenance"]["direction"] == "longitudinal"
    assert source.read_bytes() == input_bytes


@pytest.mark.parametrize("stage", ["0610", "all"])
def test_one_input_read_and_one_calculation_per_dependency(tmp_path, publication_data, monkeypatch, quick_reports, stage):
    source = write_input(tmp_path, publication_data)
    counts = {"input": 0, "0500": 0, "0600": 0, "0610": 0}
    original_read = Path.read_bytes
    def read_once(path):
        if path.resolve() == source.resolve():
            counts["input"] += 1
        return original_read(path)
    monkeypatch.setattr(Path, "read_bytes", read_once)
    for name, key in (("calculate", "0500"), ("calculate_reactions", "0600"), ("calculate_longitudinal", "0610")):
        actual = getattr(cli, name)
        def counted(*args, _actual=actual, _key=key, **kwargs):
            counts[_key] += 1
            return _actual(*args, **kwargs)
        monkeypatch.setattr(cli, name, counted)
    directory = tmp_path / "output"
    assert cli.main(["--stage", stage, "--input", str(source), "--output-dir", str(directory)]) == 0
    assert counts == {"input": 1, "0500": 1, "0600": 1, "0610": 1}
    assert quick_reports == (["0610"] if stage == "0610" else ["0500", "0600", "0610", "0620", "0710", "0720"])
    if stage == "all":
        transverse = json.loads((directory / (STEMS["0620"] + ".json")).read_text(encoding="utf-8"))
        assert transverse["schema_version"] == 2
        assert transverse["frame"]["spring_provenance"]["direction"] == "transverse"


def test_0610_result_is_identical_in_all_and_standalone(tmp_path, publication_data, quick_reports):
    source = write_input(tmp_path, publication_data)
    results = []
    for stage in ("0610", "all"):
        directory = tmp_path / stage
        assert cli.main(["--stage", stage, "--input", str(source), "--output-dir", str(directory)]) == 0
        results.append(json.loads((directory / LONG_NAMES[1]).read_text(encoding="utf-8")))
    assert results[0] == results[1]
    assert results[0]["schema_version"] == 2


@pytest.mark.parametrize("part", ["梁", "柱", "フーチング"])
@pytest.mark.parametrize("bad", ["missing", None, 0, True, "27"])
def test_invalid_materials_fail_before_render_or_publication(tmp_path, data, monkeypatch, capsys, part, bad):
    if bad == "missing":
        del data["鉄筋"][part]["concrete_strength_mpa"]
    else:
        data["鉄筋"][part]["concrete_strength_mpa"] = bad
    source = write_input(tmp_path, data)
    directory = tmp_path / "output"
    originals = old_outputs(directory)
    def unexpected(*args, **kwargs):
        pytest.fail("0610 material validation must precede rendering and publication")
    for module, function in (("report", "render_report"), ("reaction_report", "render_reaction_report"),
                             ("longitudinal_report", "render_longitudinal_report"),
                             ("transverse_report", "render_transverse_report")):
        monkeypatch.setattr(importlib.import_module("src." + module), function, unexpected)
    monkeypatch.setattr(cli, "_publish_outputs", unexpected)
    assert cli.main(["--stage", "0610", "--input", str(source), "--output-dir", str(directory), "--overwrite"]) == 2
    assert f"鉄筋.{part}.concrete_strength_mpa" in capsys.readouterr().err
    assert output_bytes(directory) == originals


def test_0600_alone_keeps_nullable_material_compatibility(tmp_path, data, quick_reports):
    for part in ("梁", "柱", "フーチング"):
        data["鉄筋"][part]["concrete_strength_mpa"] = None
    source = write_input(tmp_path, data)
    directory = tmp_path / "output"
    assert cli.main(["--stage", "0600", "--input", str(source), "--output-dir", str(directory)]) == 0
    assert quick_reports == ["0600"]
    assert set(output_bytes(directory)) == {STEMS["0600"] + ".pdf", STEMS["0600"] + ".json"}


def test_0610_render_failure_preserves_the_existing_pair_and_other_stages(tmp_path, data, monkeypatch, quick_reports):
    source = write_input(tmp_path, data)
    directory = tmp_path / "output"
    originals = old_outputs(directory)
    def fail(result, path):
        assert result["schema_version"] == 2
        Path(path).write_bytes(b"partial PDF")
        raise OSError("0610 report failure")
    monkeypatch.setattr("src.longitudinal_report.render_longitudinal_report", fail)
    assert cli.main(["--stage", "0610", "--input", str(source), "--output-dir", str(directory), "--overwrite"]) == 2
    assert output_bytes(directory) == originals


def test_0610_second_publish_failure_restores_both_old_files(tmp_path, data, monkeypatch, quick_reports):
    source = write_input(tmp_path, data)
    directory = tmp_path / "output"
    originals = old_outputs(directory)
    original_replace = os.replace
    attempts = []
    def fail_second(staged, destination):
        staged, destination = Path(staged), Path(destination)
        if destination.parent == directory and staged.name in LONG_NAMES:
            attempts.append(destination.name)
            if destination.name == LONG_NAMES[1]:
                raise PermissionError("second 0610 publication locked")
        return original_replace(staged, destination)
    monkeypatch.setattr(os, "replace", fail_second)
    assert cli.main(["--stage", "0610", "--input", str(source), "--output-dir", str(directory), "--overwrite"]) == 2
    assert attempts == list(LONG_NAMES)
    assert output_bytes(directory) == originals
