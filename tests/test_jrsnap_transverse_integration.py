"""Both directional candidates remain bound to one calculation and transaction."""

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from src import cli, jrsnap_artifacts
from src.inputs import InputError
from test_jrsnap_cli import fake_ndu as fake_ndu  # noqa: PLC0414 - pytest fixture export
from test_jrsnap_cli import generation_options as generation_options  # noqa: PLC0414 - pytest fixture export
from test_jrsnap_cli import quick_reports as quick_reports  # noqa: PLC0414 - pytest fixture export
from test_seismic_longitudinal_cli import files


@pytest.mark.parametrize("stage,expected", [("0710", {"0710"}), ("0720", {"0720"}),
                                           ("all", {"0710", "0720"})])
def test_direction_maps_aliases_and_shared_snapshots(
    generation_options, fake_ndu, quick_reports, stage, expected,
):
    options = replace(generation_options, stage=stage)
    with cli.prepare_generation(options) as candidate:
        assert set(candidate.ndu_models) == set(candidate.ndu_paths) == set(candidate.metadata_by_stage) == expected
        assert set(candidate.canonical_snapshot_sha256) == {"0500", *expected}
        selected = "0720" if stage == "0720" else "0710"
        assert candidate.ndu_model is candidate.ndu_models[selected]
        assert candidate.ndu_path == candidate.ndu_paths[selected]
        assert candidate.metadata == candidate.metadata_by_stage[selected]
        assert len(fake_ndu[0]) == len(expected)
        for call in fake_ndu[0]:
            assert call[1] is candidate.computed["0500"]
            assert call[2] is candidate.computed[call[2]["stage"]]
        if stage == "all":
            assert fake_ndu[0][0][0] is fake_ndu[0][1][0]
        for mapping in (candidate.ndu_models, candidate.ndu_paths, candidate.metadata_by_stage):
            with pytest.raises(TypeError):
                mapping["0720"] = None
        copied = candidate.metadata_by_stage
        copied[selected]["profile_id"] = "changed outside candidate"
        assert candidate.metadata["profile_id"] != "changed outside candidate"
        candidate.validate_unchanged()


@pytest.mark.parametrize("stage", ["0710", "0720"])
@pytest.mark.parametrize("change", ["model", "calculation", "native", "sidecar"])
def test_all_rejects_drift_in_either_direction(
    generation_options, fake_ndu, quick_reports, stage, change,
):
    options = replace(generation_options, stage="all")
    with cli.prepare_generation(options) as candidate:
        if change == "model":
            candidate.ndu_models[stage]["metadata"]["profile_id"] = "changed"
        elif change == "calculation":
            candidate.computed[stage]["basic_cases"][0]["label"] = "changed"
        else:
            final = (candidate.ndu_paths[stage] if change == "native"
                     else candidate.sidecars[f"{stage}.jrsnap_sidecar"])
            candidate.read_paths[final].write_bytes(b"changed")
        with pytest.raises(InputError):
            candidate.publish()
        assert not candidate.published
    assert files(options.output_dir) == {}


def test_transverse_only_preserves_longitudinal_and_frameweb_files(
    generation_options, fake_ndu, quick_reports, monkeypatch,
):
    options = replace(generation_options, stage="0720")
    post = options.output_dir / "post"
    post.mkdir(parents=True)
    protected = [*jrsnap_artifacts.jrsnap_paths(post), post / "線路直角方向.json",
                 post / "線路直角方向.provenance.json", post / "frameWebForJS.json"]
    for path in protected:
        path.write_bytes(("preserved " + path.name).encode())
    before = {path: path.read_bytes() for path in protected}

    def no_longitudinal(*args, **kwargs):
        pytest.fail("0720 must not calculate 0610/0710")

    monkeypatch.setattr(cli, "calculate_longitudinal", no_longitudinal)
    monkeypatch.setattr(cli, "calculate_seismic_longitudinal", no_longitudinal)
    with cli.prepare_generation(options) as candidate:
        assert len(candidate.artifact_hashes) == 4
        candidate.publish()
    assert {path: path.read_bytes() for path in protected} == before
    assert set(quick_reports) == {"0720"}


@pytest.mark.parametrize("failure", ["replace", "final_validate"])
def test_second_direction_failure_restores_both_ndus_and_reports(
    generation_options, fake_ndu, quick_reports, monkeypatch, failure,
):
    options = replace(generation_options, stage="all")
    with cli.prepare_generation(options) as candidate:
        destinations = tuple(candidate.artifact_hashes)
    for path in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("previous " + path.name).encode())
    before = files(options.output_dir)
    if failure == "replace":
        actual = os.replace

        def fail_second(source, destination):
            if Path(source).name == Path(destination).name == "線路直角方向.ndu":
                raise PermissionError("second direction locked")
            return actual(source, destination)

        monkeypatch.setattr(os, "replace", fail_second)
    else:
        actual = cli.validate_jrsnap_artifacts

        def fail_second(**kwargs):
            if kwargs["stage"] == "0720" and kwargs.get("read_paths") is None:
                raise InputError("second direction final validation failed")
            return actual(**kwargs)

        monkeypatch.setattr(cli, "validate_jrsnap_artifacts", fail_second)
    with pytest.raises((InputError, PermissionError)), cli.prepare_generation(options) as candidate:
        candidate.publish()
    assert files(options.output_dir) == before
    assert not list(options.output_dir.rglob(".pier-design-*"))


@pytest.mark.parametrize("change", ["stage", "direction", "convention", "profile", "profile_direction", "snapshot"])
def test_transverse_sidecar_rejects_longitudinal_substitution(
    generation_options, fake_ndu, quick_reports, change,
):
    options = replace(generation_options, stage="0720")
    with cli.prepare_generation(options) as candidate:
        candidate.publish()
    _, sidecar = jrsnap_artifacts.jrsnap_paths(options.output_dir / "post", stage="0720")
    metadata = json.loads(sidecar.read_text("utf-8"))
    if change == "stage":
        metadata["stage"] = "0710"
    elif change == "direction":
        metadata["direction"] = "longitudinal"
    elif change == "convention":
        metadata["convention_version"] = jrsnap_artifacts.CONVENTION_VERSION
    elif change == "profile":
        metadata["profile"]["profile_id"] = "p7-longitudinal-v52-v1"
        metadata["profile_sha256"] = jrsnap_artifacts.canonical_sha256(metadata["profile"])
    elif change == "profile_direction":
        metadata["profile"]["direction"] = "longitudinal"
        metadata["profile_sha256"] = jrsnap_artifacts.canonical_sha256(metadata["profile"])
    else:
        metadata["calculation_snapshot_sha256"]["0710"] = metadata["calculation_snapshot_sha256"].pop("0720")
    sidecar.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(InputError):
        jrsnap_artifacts.validate_jrsnap_artifacts(
            post_dir=options.output_dir / "post", output_dir=options.output_dir,
            expected_input_sha256=candidate.input_sha256, expected_stages=("0720",), stage="0720",
        )
