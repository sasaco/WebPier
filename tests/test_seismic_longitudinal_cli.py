"""0710 shares one in-memory dependency chain and publishes only selected files."""

import importlib
import json
import os
from pathlib import Path

import pytest
from pypdf import PdfReader

from src import cli, jrsnap_artifacts
from src.frameweb_artifacts import (
    ALL_STAGES, REPORT_STEMS, publication_paths, validate_frameweb_artifacts,
)


STEM = "0710_線路方向荷重"
RENDERERS = (
    ("report", "render_report"),
    ("reaction_report", "render_reaction_report"),
    ("longitudinal_report", "render_longitudinal_report"),
    ("transverse_report", "render_transverse_report"),
    ("seismic_longitudinal_report", "render_seismic_longitudinal_report"),
    ("seismic_transverse_report", "render_seismic_transverse_report"),
)


@pytest.fixture
def quick_reports(monkeypatch):
    # Keep the independently injected JRSNAP source provider (including source
    # mutation/addition tests); only replace the real renderer-bound provider.
    if cli.implementation_hashes.__module__ == "src.jrsnap_artifacts":
        source = Path(cli.__file__).resolve()
        def hashes():
            return {source: cli.file_sha256(source)}
        monkeypatch.setattr(cli, "implementation_hashes", hashes)
        monkeypatch.setattr(jrsnap_artifacts, "implementation_hashes", hashes)
    recorded = {}

    def render(result, path):
        recorded[result.get("stage", "0500")] = result
        Path(path).write_bytes(b"test PDF")

    for module, function in RENDERERS:
        monkeypatch.setattr(importlib.import_module("src." + module), function, render)
    return recorded


def files(parent):
    return {path.relative_to(parent): path.read_bytes() for path in parent.rglob("*") if path.is_file()}


@pytest.mark.parametrize("stage", ["0710", "all"])
def test_one_input_read_and_shared_upstream_object_per_run(tmp_path, monkeypatch, quick_reports, stage):
    source = tmp_path / "input.json"
    source.write_bytes((cli.PROJECT_DIR / "pre" / "input.json").read_bytes())
    output = tmp_path / "output"
    calls = {name: 0 for name in ("input", "0500", "0600", "0610", "0710")}
    produced = {}
    actual_read = Path.read_bytes

    def read(path):
        if path.resolve() == source.resolve():
            calls["input"] += 1
        return actual_read(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    for function, label in (("calculate", "0500"), ("calculate_reactions", "0600"),
                            ("calculate_longitudinal", "0610"), ("calculate_seismic_longitudinal", "0710")):
        actual = getattr(cli, function)

        def calculate(*args, _actual=actual, _label=label, **kwargs):
            calls[_label] += 1
            if _label == "0710":
                assert args[0] is produced["0610"]
            result = _actual(*args, **kwargs)
            produced[_label] = result
            return result

        monkeypatch.setattr(cli, function, calculate)
    exports = []
    actual_export = cli.build_frameweb_input

    def export(result):
        exports.append(result["stage"])
        return actual_export(result)

    monkeypatch.setattr(cli, "build_frameweb_input", export)
    assert cli.main(["--stage", stage, "--input", str(source), "--output-dir", str(output)]) == 0
    assert calls == dict.fromkeys(calls, 1)
    assert quick_reports["0710"] is produced["0710"]
    if stage == "0710":
        assert tuple(quick_reports) == ("0710",)
        assert files(output).keys() == {Path(STEM + ".pdf"), Path(STEM + ".json")}
        assert exports == [] and not (output / "post").exists()
    else:
        assert quick_reports["0610"] is produced["0610"]
        assert tuple(quick_reports) == ALL_STAGES
        assert exports == ["0610", "0620"]
        assert len(files(output)) == 16


def test_real_standalone_and_all_have_identical_seismic_values_and_complete_chapters(tmp_path):
    results, pages = [], []
    for stage in ("0710", "all"):
        output = tmp_path / stage
        assert cli.main(["--stage", stage, "--output-dir", str(output)]) == 0
        results.append(json.loads((output / f"{STEM}.json").read_text("utf-8")))
        pdf = PdfReader(output / f"{STEM}.pdf")
        assert len(pdf.pages) > 0
        pages.append([page.extract_text() for page in pdf.pages])
        whole = "".join(pages[-1])
        for heading in ("10.1 検討モデル", "10.2 作用の計算", "10.3 作用の組合せ"):
            assert heading in whole
        assert all(f"10 - {number}" in text for number, text in enumerate(pages[-1], 1))
    # Publication identifiers belong to the FrameWeb sidecars, not this result.
    assert results[0] == results[1]
    assert pages[0] == pages[1]


def test_single_stage_preserves_other_reports_and_existing_post(tmp_path, quick_reports):
    output, post = tmp_path / "output", tmp_path / "post"
    declared, sidecars = publication_paths(output, post, ALL_STAGES)
    originals = {}
    for path in (*declared.values(), *sidecars.values()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("old " + path.name).encode("utf-8"))
        if not path.name.startswith("0710_"):
            originals[path] = path.read_bytes()
    assert cli.main(["--stage", "0710", "--output-dir", str(output), "--post-dir", str(post), "--overwrite"]) == 0
    assert {path: path.read_bytes() for path in originals} == originals
    assert set(quick_reports) == {"0710"}


@pytest.mark.parametrize("stage", ["0710", "all"])
@pytest.mark.parametrize("failure", ["render_oserror", "render_valueerror", "json_write", "publish"])
@pytest.mark.parametrize("existing", [False, True])
def test_failed_seismic_generation_restores_selected_and_unselected_files(
    tmp_path, monkeypatch, quick_reports, capsys, stage, failure, existing,
):
    output, post = tmp_path / "output", tmp_path / "post"
    if existing:
        declared, sidecars = publication_paths(output, post, ALL_STAGES)
        for path in (*declared.values(), *sidecars.values()):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("original " + path.name).encode("utf-8"))
    before = files(tmp_path)
    if failure.startswith("render"):
        def fail_render(*args):
            if failure == "render_valueerror":
                raise ValueError("0710 layout exceeds page bounds")
            raise OSError("0710 renderer failed")
        monkeypatch.setattr("src.seismic_longitudinal_report.render_seismic_longitudinal_report", fail_render)
    elif failure == "json_write":
        actual_write = Path.write_text

        def fail_write(path, *args, **kwargs):
            if path.name == f"{STEM}.json":
                raise OSError("0710 result cannot be written")
            return actual_write(path, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", fail_write)
    else:
        actual_replace = os.replace

        def fail_publish(source, destination):
            if Path(source).name == f"{STEM}.json" and Path(destination) == output / f"{STEM}.json":
                raise PermissionError("0710 result publication locked")
            return actual_replace(source, destination)

        monkeypatch.setattr(os, "replace", fail_publish)
    assert cli.main(["--stage", stage, "--output-dir", str(output), "--post-dir", str(post), "--overwrite"]) == 2
    assert files(tmp_path) == before
    assert not list(tmp_path.rglob(".webpier-*"))
    if failure == "render_valueerror":
        error = capsys.readouterr().err
        assert "0710帳票を作成できません" in error and "layout exceeds" in error
        assert "Traceback" not in error


@pytest.mark.parametrize("suffix", ["pdf", "json"])
@pytest.mark.parametrize("change", ["missing", "modified"])
def test_all_manifest_rejects_missing_or_changed_seismic_report(tmp_path, quick_reports, suffix, change):
    output = tmp_path / "output"
    assert cli.main(["--stage", "all", "--output-dir", str(output)]) == 0
    path = output / f"{REPORT_STEMS['0710']}.{suffix}"
    if change == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        validate_frameweb_artifacts(
            post_dir=output / "post", output_dir=output, expected_stages=ALL_STAGES,
            expected_input_sha256=quick_reports["0710"]["provenance"]["input_sha256"],
        )
