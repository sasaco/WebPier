"""0720 uses current in-memory 0600/0620 and atomically publishes its pair."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

import pytest
from pypdf import PdfReader

from src import cli
from src.frameweb_artifacts import (
    ALL_STAGES, FRAMEWEB_STAGES, REPORT_STEMS, publication_paths, validate_frameweb_artifacts,
)


STEM = "0720_線路直角方向荷重"
RENDERERS = (
    ("report", "render_report"),
    ("reaction_report", "render_reaction_report"),
    ("longitudinal_report", "render_longitudinal_report"),
    ("transverse_report", "render_transverse_report"),
    ("seismic_longitudinal_report", "render_seismic_longitudinal_report"),
    ("seismic_transverse_report", "render_seismic_transverse_report"),
)


@pytest.fixture
def quick_reports(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    recorded: dict[str, dict[str, Any]] = {}
    # This fixture replaces every renderer; dedicated identity tests exercise
    # real installed packages/fonts. Keep a live source digest at this boundary.
    source = Path(cli.__file__).resolve()
    monkeypatch.setattr(cli, "implementation_hashes", lambda: {
        source: hashlib.sha256(source.read_bytes()).hexdigest(),
    })

    def render(result: dict[str, Any], path: Path) -> None:
        recorded[result.get("stage", "0500")] = result
        Path(path).write_bytes(b"test PDF")

    for module, function in RENDERERS:
        monkeypatch.setattr(importlib.import_module("src." + module), function, render)
    return recorded


def files(parent: Path) -> dict[Path, bytes]:
    return {path.relative_to(parent): path.read_bytes() for path in parent.rglob("*") if path.is_file()}


@contextmanager
def current_report_reads_only(monkeypatch: pytest.MonkeyPatch, output: Path) -> Iterator[None]:
    """Permit exact new artifacts only inside the publisher's final validator."""
    actual_open, actual_publish = Path.open, cli._publish_outputs
    root = output.resolve()
    declared = {root / (STEM + suffix) for suffix in (".pdf", ".json")}
    validating = False

    def open_current(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        resolved = path.resolve()
        reading = "r" in mode or "+" in mode
        staged = (resolved.parent.parent == root
                  and resolved.parent.name.startswith(".pier-design-")
                  and resolved.name in {p.name for p in declared})
        accepted = validating and resolved in declared
        if reading and not accepted:
            if resolved.suffix.lower() == ".pdf" and not staged:
                pytest.fail(f"0720 must not read a reference PDF: {path}")
            if resolved.parent == root and resolved.suffix.lower() in (".json", ".pdf"):
                pytest.fail(f"0720 must not load a previous result: {path}")
        return actual_open(path, mode, *args, **kwargs)

    def publish(pairs: list[tuple[Path, Path]], staging: Path | Mapping[Path, Path],
                overwrite: bool, *, final_validator: Callable[[], None] | None = None) -> None:
        assert {target.resolve() for _, target in pairs} == declared

        def verify() -> None:
            nonlocal validating
            validating = True
            try:
                assert final_validator is not None
                final_validator()
            finally:
                validating = False

        actual_publish(pairs, staging, overwrite, final_validator=verify)

    with monkeypatch.context() as guarded:
        guarded.setattr(Path, "open", open_current)
        guarded.setattr(cli, "_publish_outputs", publish)
        yield


@pytest.mark.parametrize("forbidden", ["reference", "saved-pdf", "saved-json", "fake-staging"])
def test_current_report_read_guard_does_not_admit_old_or_reference_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, forbidden: str,
) -> None:
    output = tmp_path / "output"
    target = {
        "reference": tmp_path / "reference" / (STEM + ".pdf"),
        "saved-pdf": output / (STEM + ".pdf"),
        "saved-json": output / (STEM + ".json"),
        "fake-staging": tmp_path / ".pier-design-reference" / (STEM + ".pdf"),
    }[forbidden]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"previous artifact")
    with current_report_reads_only(monkeypatch, output):
        with pytest.raises(pytest.fail.Exception, match="must not"):
            target.read_bytes()


def test_current_report_read_guard_limits_final_validation_to_selected_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    staging = output / ".pier-design-test"
    staging.mkdir(parents=True)
    pairs = []
    for suffix in (".pdf", ".json"):
        source, target = staging / (STEM + suffix), output / (STEM + suffix)
        source.write_bytes(b"new artifact")
        pairs.append((source, target))
    unrelated = output / "unselected.pdf"
    unrelated.write_bytes(b"old unrelated artifact")

    def final_validate() -> None:
        assert all(target.read_bytes() == b"new artifact" for _, target in pairs)
        with pytest.raises(pytest.fail.Exception, match="reference PDF"):
            unrelated.read_bytes()

    with current_report_reads_only(monkeypatch, output):
        cli._publish_outputs(pairs, staging, False, final_validator=final_validate)
        with pytest.raises(pytest.fail.Exception, match="reference PDF"):
            pairs[0][1].read_bytes()


@pytest.mark.parametrize("stage", ["0720", "all"])
def test_single_input_and_same_run_dependencies_are_computed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    quick_reports: dict[str, dict[str, Any]], stage: str,
) -> None:
    source = tmp_path / "input.json"
    source.write_bytes((cli.PROJECT_DIR / "pre" / "input.json").read_bytes())
    input_bytes = source.read_bytes()
    digest = hashlib.sha256(input_bytes).hexdigest()
    output = tmp_path / "output"
    calls = dict.fromkeys(("input", *ALL_STAGES), 0)
    produced: dict[str, dict[str, Any]] = {}
    parsed_inputs: list[Any] = []
    actual_read = Path.read_bytes

    def read(path: Path) -> bytes:
        if path.resolve() == source.resolve():
            calls["input"] += 1
        return actual_read(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    for function, label in (
        ("calculate", "0500"), ("calculate_reactions", "0600"),
        ("calculate_longitudinal", "0610"), ("calculate_transverse", "0620"),
        ("calculate_seismic_longitudinal", "0710"), ("calculate_seismic_transverse", "0720"),
    ):
        actual = getattr(cli, function)

        def calculate(*args: Any, _actual: Callable[..., dict[str, Any]] = actual,
                      _label: str = label, **kwargs: Any) -> dict[str, Any]:
            calls[_label] += 1
            if stage == "0720" and _label in ("0610", "0710"):
                pytest.fail("0720 must not calculate either longitudinal stage")
            if _label == "0600":
                parsed_inputs.append(args[0])
            if _label == "0620":
                assert args[0] is parsed_inputs[0]
                assert args[1] is produced["0500"] and args[2] is produced["0600"]
            if _label == "0720":
                assert args[0] is parsed_inputs[0]
                assert args[1] is produced["0600"] and args[2] is produced["0620"]
                assert args[1]["provenance"]["input_sha256"] == digest
                assert args[2]["provenance"]["input_sha256"] == digest
            produced[_label] = _actual(*args, **kwargs)
            return produced[_label]

        monkeypatch.setattr(cli, function, calculate)
    exports: list[str] = []
    actual_export = cli.build_frameweb_input

    def export(result: dict[str, Any]) -> Any:
        exports.append(result["stage"])
        return actual_export(result)

    monkeypatch.setattr(cli, "build_frameweb_input", export)
    assert cli.main(["--stage", stage, "--input", str(source), "--output-dir", str(output)]) == 0
    expected = dict.fromkeys(calls, 1)
    if stage == "0720":
        expected.update({"0610": 0, "0710": 0})
    assert calls == expected
    assert quick_reports["0720"] is produced["0720"]
    assert quick_reports["0720"]["provenance"]["input_sha256"] == digest
    assert actual_read(source) == input_bytes
    if stage == "0720":
        assert tuple(quick_reports) == ("0720",)
        assert files(output).keys() == {Path(STEM + ".pdf"), Path(STEM + ".json")}
        assert not exports and not (output / "post").exists()
    else:
        assert tuple(quick_reports) == ALL_STAGES
        assert exports == list(FRAMEWEB_STAGES)
        assert len(files(output)) == 16


def test_standalone_needs_no_reference_pdf_or_saved_result_and_matches_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    results, pages = [], []
    for stage in ("0720", "all"):
        output = tmp_path / stage
        if stage == "0720":
            with current_report_reads_only(monkeypatch, output):
                assert cli.main(["--stage", stage, "--output-dir", str(output)]) == 0
            assert set(files(output)) == {Path(STEM + ".pdf"), Path(STEM + ".json")}
        else:
            assert cli.main(["--stage", stage, "--output-dir", str(output)]) == 0
        results.append(json.loads((output / f"{STEM}.json").read_text("utf-8")))
        pdf = PdfReader(output / f"{STEM}.pdf")
        assert len(pdf.pages) > 0
        pages.append([page.extract_text() for page in pdf.pages])
        content = "".join(pages[-1])
        for required in ("線路直角方向", "地震時", "列車荷重", "慣性力", "Case"):
            assert required in content
    assert results[0] == results[1]
    assert pages[0] == pages[1]


def test_standalone_preserves_every_other_report_and_post(
    tmp_path: Path, quick_reports: dict[str, dict[str, Any]],
) -> None:
    output, post = tmp_path / "output", tmp_path / "post"
    declared, sidecars = publication_paths(output, post, ALL_STAGES)
    originals: dict[Path, bytes] = {}
    for path in (*declared.values(), *sidecars.values()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("old unreadable " + path.name).encode("utf-8"))
        if not path.name.startswith("0720_"):
            originals[path] = path.read_bytes()
    assert cli.main(["--stage", "0720", "--output-dir", str(output), "--post-dir", str(post), "--overwrite"]) == 0
    assert {path: path.read_bytes() for path in originals} == originals
    assert tuple(quick_reports) == ("0720",)


@pytest.mark.parametrize("stage", ["0720", "all"])
@pytest.mark.parametrize("failure", ["render_oserror", "render_valueerror", "json_write", "publish_pdf", "publish_json"])
@pytest.mark.parametrize("existing", [False, True])
def test_failure_restores_all_selected_and_unselected_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, quick_reports: dict[str, dict[str, Any]],
    capsys: pytest.CaptureFixture[str], stage: str, failure: str, existing: bool,
) -> None:
    output, post = tmp_path / "output", tmp_path / "post"
    if existing:
        declared, sidecars = publication_paths(output, post, ALL_STAGES)
        for path in (*declared.values(), *sidecars.values()):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("original " + path.name).encode("utf-8"))
    before = files(tmp_path)
    if failure.startswith("render"):
        def fail_render(result: dict[str, Any], path: Path) -> None:
            Path(path).write_bytes(b"partial PDF")
            if failure == "render_valueerror":
                raise ValueError("0720 layout exceeds page bounds")
            raise OSError("0720 PDF write failed")
        monkeypatch.setattr("src.seismic_transverse_report.render_seismic_transverse_report", fail_render)
    elif failure == "json_write":
        actual_write = Path.write_text

        def fail_write(path: Path, *args: Any, **kwargs: Any) -> int:
            if path.name == f"{STEM}.json":
                raise OSError("0720 result write failed")
            return actual_write(path, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", fail_write)
    else:
        actual_replace = os.replace
        suffix = failure.removeprefix("publish_")

        def fail_publish(source: Any, destination: Any) -> None:
            if Path(source).name == f"{STEM}.{suffix}" and Path(destination) == output / f"{STEM}.{suffix}":
                raise PermissionError("0720 publication locked")
            actual_replace(source, destination)

        monkeypatch.setattr(os, "replace", fail_publish)
    assert cli.main(["--stage", stage, "--output-dir", str(output), "--post-dir", str(post), "--overwrite"]) == 2
    assert files(tmp_path) == before
    assert not list(tmp_path.rglob(".pier-design-*"))
    if failure == "render_valueerror":
        error = capsys.readouterr().err
        assert "0720帳票を作成できません" in error and "layout exceeds" in error
        assert "Traceback" not in error


@pytest.mark.parametrize("suffix", ["pdf", "json"])
@pytest.mark.parametrize("change", ["missing", "modified"])
def test_all_manifest_rejects_missing_or_modified_0720(
    tmp_path: Path, quick_reports: dict[str, dict[str, Any]], suffix: str, change: str,
) -> None:
    output = tmp_path / "output"
    assert cli.main(["--stage", "all", "--output-dir", str(output)]) == 0
    metadata = json.loads((output / "post" / "frameWebForJS.provenance.json").read_text("utf-8"))
    assert len(metadata["artifact_manifest"]) == 14
    assert {row["role"] for row in metadata["artifact_manifest"] if row["role"].startswith("0720.")} == {
        "0720.result_pdf", "0720.result_json"}
    path = output / f"{REPORT_STEMS['0720']}.{suffix}"
    if change == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        validate_frameweb_artifacts(
            post_dir=output / "post", output_dir=output, expected_stages=ALL_STAGES,
            expected_input_sha256=quick_reports["0720"]["provenance"]["input_sha256"],
        )


@pytest.mark.parametrize("stage", ["0720", "all"])
@pytest.mark.parametrize("suffix", ["pdf", "json"])
def test_failed_0720_backup_restores_whole_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, quick_reports: dict[str, dict[str, Any]],
    stage: str, suffix: str,
) -> None:
    output, post = tmp_path / "output", tmp_path / "post"
    declared, sidecars = publication_paths(output, post, ALL_STAGES)
    for path in (*declared.values(), *sidecars.values()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("original " + path.name).encode("utf-8"))
    before = files(tmp_path)
    actual_replace = os.replace
    target = output / f"{STEM}.{suffix}"

    def fail_backup(source: Any, destination: Any) -> None:
        if Path(source) == target and Path(destination).name.endswith(".backup"):
            raise PermissionError("0720 backup locked")
        actual_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_backup)
    assert cli.main(["--stage", stage, "--output-dir", str(output), "--post-dir", str(post), "--overwrite"]) == 2
    assert files(tmp_path) == before
    assert not list(tmp_path.rglob(".pier-design-*"))


@pytest.mark.parametrize("part", ["梁", "柱", "フーチング"])
def test_0720_keeps_canonical_transverse_material_validation(
    tmp_path: Path, quick_reports: dict[str, dict[str, Any]], capsys: pytest.CaptureFixture[str], part: str,
) -> None:
    data = json.loads((cli.PROJECT_DIR / "pre" / "input.json").read_text("utf-8"))
    data["鉄筋"][part]["concrete_strength_mpa"] = 0
    source, output = tmp_path / "input.json", tmp_path / "output"
    source.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    output.mkdir()
    old_pdf = output / f"{STEM}.pdf"
    old_pdf.write_bytes(b"preserve report")
    before = files(tmp_path)
    assert cli.main(["--stage", "0720", "--input", str(source), "--output-dir", str(output), "--overwrite"]) == 2
    assert f"鉄筋.{part}.concrete_strength_mpa" in capsys.readouterr().err
    assert not quick_reports
    assert files(tmp_path) == before
