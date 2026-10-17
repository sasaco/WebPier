"""Dedicated metadata catches stale/cross-generation artifacts independently."""

import json

import pytest
from src import cli, jrsnap_artifacts
from src.frameweb_artifacts import ALL_STAGES, frameweb_paths
from src.inputs import InputError
from test_jrsnap_cli import fake_ndu as fake_ndu  # noqa: PLC0414 - pytest fixture export
from test_jrsnap_cli import generation_options as generation_options  # noqa: PLC0414 - pytest fixture export
from test_jrsnap_cli import quick_reports as quick_reports  # noqa: PLC0414 - pytest fixture export


@pytest.mark.parametrize("change", ["input", "native", "snapshot", "profile_snapshot", "version",
                                    "manifest_extra", "manifest_path", "app_verified", "source", "profile"])
def test_dedicated_validator_rejects_corruption(generation_options, fake_ndu, quick_reports, change):
    with cli.prepare_generation(generation_options) as candidate:
        candidate.publish()
    output = generation_options.output_dir
    native, sidecar = jrsnap_artifacts.jrsnap_paths(output / "post")
    metadata = json.loads(sidecar.read_text("utf-8"))
    if change == "input":
        metadata["provenance"]["raw_input_sha256"] = "0" * 64
    elif change == "native":
        native.write_bytes(native.read_bytes() + b"changed")
    elif change == "snapshot":
        metadata["calculation_snapshot_sha256"]["0710"] = "0" * 64
    elif change == "profile_snapshot":
        metadata["profile"]["canonical_snapshot_sha256"]["foundation"] = "0" * 64
    elif change == "version":
        metadata["target_version"] = "5.3-L01"
    elif change == "manifest_extra":
        metadata["artifact_manifest"].append(metadata["artifact_manifest"][0])
    elif change == "manifest_path":
        metadata["artifact_manifest"][0]["path"] += ".other"
    elif change == "app_verified":
        metadata["app_read_verified"] = True
    elif change == "profile":
        metadata["profile"]["settings"] = {"changed": True}
    else:
        fake_ndu[1].write_text("new profile", encoding="utf-8")
    sidecar.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(InputError):
        jrsnap_artifacts.validate_jrsnap_artifacts(
            output_dir=output, post_dir=output / "post",
            expected_input_sha256=candidate.input_sha256, expected_stages=("0710",),
        )


def test_ndu_and_frameweb_must_share_publication_id(generation_options, fake_ndu, quick_reports):
    options = cli.GenerationOptions(generation_options.input_path, generation_options.output_dir,
                                    stage="all", jrsnap=True)
    with cli.prepare_generation(options) as candidate:
        candidate.publish()
    output, post = options.output_dir, options.output_dir / "post"
    _, peer_path = frameweb_paths(post)
    peer = json.loads(peer_path.read_text("utf-8"))
    peer["publication_id"] = "other-run"
    peer_path.write_text(json.dumps(peer), encoding="utf-8")
    with pytest.raises(InputError, match="公開世代"):
        jrsnap_artifacts.validate_jrsnap_artifacts(
            output_dir=output, post_dir=post, expected_input_sha256=candidate.input_sha256,
            expected_stages=ALL_STAGES,
        )


def test_canonical_hash_ignores_json_layout_but_covers_all_fields():
    first = {"日本語": [1, 2.0], "provenance": {"timestamp": "a"}}
    second = {"provenance": {"timestamp": "a"}, "日本語": [1, 2.0]}
    assert jrsnap_artifacts.canonical_sha256(first) == jrsnap_artifacts.canonical_sha256(second)
    second["provenance"]["timestamp"] = "b"
    assert jrsnap_artifacts.canonical_sha256(first) != jrsnap_artifacts.canonical_sha256(second)
    with pytest.raises(ValueError):
        jrsnap_artifacts.canonical_sha256({"value": float("nan")})
