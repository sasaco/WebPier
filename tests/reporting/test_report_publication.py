"""Normal reports retain the same input/runtime generation and staged bytes."""

from __future__ import annotations

import hashlib
from pathlib import Path

from gridlayoutpdf import FontError, LayoutOverflowError
import pytest

from src import cli, report
from src.inputs import InputError


@pytest.fixture
def held_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "input.json"
    source.write_text('{"sentinel":1}', encoding="utf-8")
    dependency = tmp_path / "renderer.py"
    dependency.write_text("# renderer v1", encoding="utf-8")
    monkeypatch.setattr(cli, "implementation_hashes", lambda: {
        dependency.resolve(): hashlib.sha256(dependency.read_bytes()).hexdigest(),
    })
    monkeypatch.setattr(cli, "_calculate_stages", lambda *args: {
        "0500": {"stage": "0500", "schema_version": 1, "value": 12.3, "warnings": []},
    })
    calls = []

    def render(result: dict, path: Path) -> None:
        calls.append(result["value"])
        path.write_bytes(b"%PDF held generation")

    monkeypatch.setattr(report, "render_report", render)
    options = cli.GenerationOptions(source, tmp_path / "output", stage="0500", overwrite=True)
    return options, dependency, calls


@pytest.mark.parametrize("change", ["input", "source", "computed", "destination"])
def test_normal_candidate_rejects_generation_drift(held_report, change: str) -> None:
    options, dependency, _ = held_report
    with cli.prepare_generation(options) as candidate:
        if change == "input":
            options.input_path.write_text('{"sentinel":2}', encoding="utf-8")
        elif change == "source":
            dependency.write_text("# renderer v2", encoding="utf-8")
        elif change == "computed":
            candidate.computed["0500"]["value"] = 42
        else:
            candidate.declared["0500.result_pdf"].write_bytes(b"concurrent external output")
        with pytest.raises(InputError):
            candidate.publish()


def test_normal_candidate_publishes_retained_bytes_once_and_only_declared_files(held_report) -> None:
    options, _, calls = held_report
    with cli.prepare_generation(options) as candidate:
        assert candidate.source_hashes
        held = {target: source.read_bytes() for target, source in candidate.read_paths.items()}
        assert len(held) == 2
        candidate.validate_unchanged()
        candidate.publish()
        assert {path: path.read_bytes() for path in held} == held
        assert calls == [12.3]
        with pytest.raises(InputError):
            candidate.publish()


@pytest.mark.parametrize("change", ["pdf", "extra-file"])
def test_normal_candidate_rejects_pdf_drift_and_qa_in_formal_staging(held_report, change: str) -> None:
    options, _, _ = held_report
    with cli.prepare_generation(options) as candidate:
        pdf = candidate.read_paths[candidate.declared["0500.result_pdf"]]
        if change == "pdf":
            pdf.write_bytes(b"%PDF different generation")
        else:
            pdf.with_name("inspection-overlay.pdf").write_bytes(b"QA must remain separate")
        with pytest.raises(InputError):
            candidate.publish()
        assert not candidate.declared["0500.result_pdf"].exists()


@pytest.mark.parametrize("failure", [FontError("required font missing"), LayoutOverflowError("oversize group"), ValueError("invalid displayed value")])
def test_normal_render_failure_is_input_error_and_preserves_existing_target(held_report, monkeypatch, failure) -> None:
    options, _, _ = held_report
    target = options.output_dir / "0500_直接基礎.pdf"
    target.parent.mkdir()
    target.write_bytes(b"previous approved generation")

    def fail(*args) -> None:
        raise failure

    monkeypatch.setattr(report, "render_report", fail)
    with pytest.raises(InputError, match="0500帳票"):
        with cli.prepare_generation(options):
            pytest.fail("render failure yielded a publishable candidate")
    assert target.read_bytes() == b"previous approved generation"


@pytest.mark.parametrize("change", ["published-pdf", "destination-before-backup"])
def test_normal_final_validation_rejects_changed_bytes_and_restores_backup(
    held_report, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    options, _, _ = held_report
    target = options.output_dir / "0500_直接基礎.pdf"
    target.parent.mkdir()
    original = b"previous approved generation"
    competing = b"competing external generation"
    target.write_bytes(original)
    actual_publish = cli._publish_outputs

    def corrupt(pairs, staging, overwrite, *, final_validator):
        def check():
            if change == "published-pdf":
                target.write_bytes(b"changed after staging")
            final_validator()

        if change == "destination-before-backup":
            target.write_bytes(competing)
        actual_publish(pairs, staging, overwrite, final_validator=check)

    with cli.prepare_generation(options) as candidate:
        monkeypatch.setattr(cli, "_publish_outputs", corrupt)
        with pytest.raises(InputError):
            candidate.publish()
        assert not candidate.published
    assert target.read_bytes() == (competing if change == "destination-before-backup" else original)


def test_missing_font_in_runtime_identity_is_input_error_before_publication(
    held_report, monkeypatch: pytest.MonkeyPatch,
) -> None:
    options, _, calls = held_report

    def missing():
        raise FontError("required font missing")

    monkeypatch.setattr(cli, "implementation_hashes", missing)
    with pytest.raises(InputError, match="描画依存"):
        with cli.prepare_generation(options):
            pytest.fail("missing runtime dependency yielded a candidate")
    assert not calls and not options.output_dir.exists()


@pytest.mark.parametrize("boundary", ["held-validation", "final-validation"])
@pytest.mark.parametrize("change", ["input", "source", "computed"])
def test_mutation_during_validation_is_rejected_at_the_same_boundary(
    held_report, boundary: str, change: str,
) -> None:
    options, dependency, _ = held_report
    with cli.prepare_generation(options) as candidate:
        original_verify = candidate._verify

        def mutate(aliases=None):
            original_verify(aliases)
            if change == "input":
                options.input_path.write_text('{"sentinel":2}', encoding="utf-8")
            elif change == "source":
                dependency.write_text("# changed during validation", encoding="utf-8")
            else:
                candidate.computed["0500"]["value"] = 99

        object.__setattr__(candidate, "_verify", mutate)
        if boundary == "held-validation":
            object.__setattr__(candidate, "_validated", False)
            operation = candidate.validate_unchanged
        else:
            operation = candidate.publish
        with pytest.raises(InputError):
            operation()
        assert not candidate.published
        assert not any(path.exists() for path in candidate.declared.values())
