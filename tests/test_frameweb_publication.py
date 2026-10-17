"""Whole-job manifests bind final destinations to the bytes actually staged."""

import json
import hashlib
from copy import deepcopy

import pytest

from src import frameweb_artifacts as artifacts
from test_editor_calculation import frameweb_template


def make_generation(tmp_path, *, staged=False, shared_parent=False):
    output = tmp_path / "output"
    post = output if shared_parent else tmp_path / "post"
    declared, sidecars = artifacts.publication_paths(output, post, ("0610",))
    read_paths = {path: tmp_path / "staging" / path.name for path in (*declared.values(), *sidecars.values())} if staged else {}
    result, exported = frameweb_template()
    result = deepcopy(result)
    result["provenance"]["input_sha256"] = "a" * 64
    contents = {"0610.result_pdf": b"PDF\r\n", "0610.result_json": json.dumps(result).encode(),
                "0610.native": json.dumps(exported.document).encode()}
    for role, path in declared.items():
        path = read_paths.get(path, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents[role])
    native, sidecar = artifacts.frameweb_paths(post)
    manifest = artifacts.build_artifact_manifest(declared, read_paths=read_paths)
    metadata = artifacts.build_provenance(
        input_sha256="a" * 64, input_file="input.json", native_path=read_paths.get(native, native),
        result_json_path=read_paths.get(declared["0610.result_json"], declared["0610.result_json"]),
        result_pdf_path=read_paths.get(declared["0610.result_pdf"], declared["0610.result_pdf"]),
        correspondence=exported.source_mapping, stage="0610", publication_id="publication-1",
        selected_stages=("0610",), artifact_manifest=manifest,
        expected_sidecars=[{"role": role, "path": str(path.resolve())} for role, path in sidecars.items()],
    )
    read_paths.get(sidecar, sidecar).write_text(json.dumps(metadata), encoding="utf-8")
    return output, post, read_paths, metadata


def test_stage_registry_retains_longitudinal_defaults_and_adds_transverse(tmp_path):
    assert artifacts.ALL_STAGES == ("0500", "0600", "0610", "0620", "0710", "0720")
    assert tuple(artifacts.FRAMEWEB_STAGES) == ("0610", "0620")
    declared, sidecars = artifacts.publication_paths(tmp_path, tmp_path / "post", ("0710",))
    assert tuple(declared) == ("0710.result_pdf", "0710.result_json")
    assert not sidecars
    assert tuple(path.name for path in artifacts.frameweb_paths(tmp_path)) == (
        "frameWebForJS.json", "frameWebForJS.provenance.json")
    assert tuple(path.name for path in artifacts.frameweb_paths(tmp_path, stage="0620")) == (
        "線路直角方向.json", "線路直角方向.provenance.json")
    with pytest.raises(ValueError):
        artifacts.frameweb_paths(tmp_path, stage="0600")
    with pytest.raises(ValueError):
        artifacts.frameweb_paths(tmp_path, stage="0710")
    with pytest.raises(ValueError):
        artifacts.frameweb_paths(tmp_path, stage="0720")
    declared, sidecars = artifacts.publication_paths(tmp_path, tmp_path / "post", ("0720",))
    assert tuple(declared) == ("0720.result_pdf", "0720.result_json")
    assert not sidecars
    assert all(path.parent == tmp_path for path in declared.values())
    declared, sidecars = artifacts.publication_paths(tmp_path, tmp_path / "post", artifacts.ALL_STAGES)
    assert len(declared) == 14 and len(sidecars) == 2


@pytest.mark.parametrize("staged", [False, True])
def test_schema2_validates_bytes_at_explicit_read_paths_without_changing_manifest_paths(tmp_path, staged):
    output, post, read_paths, metadata = make_generation(tmp_path, staged=staged)
    assert metadata["schema_version"] == 2
    assert metadata["stage"] == "0610" and metadata["direction"] == "longitudinal"
    assert len(metadata["artifact_manifest"]) == 3
    assert len(metadata["expected_sidecars"]) == 1
    assert all("staging" not in entry["path"] for entry in metadata["artifact_manifest"])
    artifacts.validate_frameweb_artifacts(post_dir=post, output_dir=output,
        expected_input_sha256="a" * 64, expected_stages=("0610",), read_paths=read_paths)
    if staged:
        assert not output.exists() and not post.exists()


@pytest.mark.parametrize("defect", ["id", "extra", "missing", "sidecar_hash", "direction", "stage", "wrong_path"])
def test_schema2_rejects_incomplete_or_inconsistent_job_declarations(tmp_path, defect):
    output, post, _, metadata = make_generation(tmp_path)
    if defect == "id":
        metadata["publication_id"] = ""
    elif defect == "extra":
        metadata["artifact_manifest"].append(metadata["artifact_manifest"][0])
    elif defect == "missing":
        metadata["artifact_manifest"].pop()
    elif defect == "sidecar_hash":
        metadata["artifact_manifest"].append({**metadata["expected_sidecars"][0], "sha256": "a" * 64})
    elif defect in {"direction", "stage"}:
        metadata[defect] = "incorrect"
    else:
        metadata["artifact_manifest"][0]["path"] = str(tmp_path / "unbound.pdf")
    artifacts.frameweb_paths(post)[1].write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError):
        artifacts.validate_frameweb_artifacts(post_dir=post, output_dir=output,
            expected_input_sha256="a" * 64, expected_stages=("0610",))


def test_schema1_cannot_claim_all_job_guarantee(tmp_path):
    output, post, _, metadata = make_generation(tmp_path)
    metadata["schema_version"] = 1
    for key in ("stage", "direction", "publication_id", "selected_stages", "artifact_manifest", "expected_sidecars"):
        metadata.pop(key)
    artifacts.frameweb_paths(post)[1].write_text(json.dumps(metadata), encoding="utf-8")
    artifacts.validate_frameweb_artifacts(post_dir=post, output_dir=output, expected_input_sha256="a" * 64)
    with pytest.raises(ValueError, match="schema1"):
        artifacts.validate_frameweb_artifacts(post_dir=post, output_dir=output,
            expected_input_sha256="a" * 64, expected_stages=("0500", "0600", "0610", "0620", "0710", "0720"))


def test_native_and_reports_can_share_the_same_output_parent(tmp_path):
    output, post, _, _ = make_generation(tmp_path, shared_parent=True)
    artifacts.validate_frameweb_artifacts(post_dir=post, output_dir=output,
        expected_input_sha256="a" * 64, expected_stages=("0610",))


@pytest.mark.parametrize("defect", ["stage", "direction", "corrupt_json"])
def test_valid_hashes_do_not_hide_wrong_calculation_direction_or_corrupt_json(tmp_path, defect):
    output, post, _, metadata = make_generation(tmp_path)
    result_path = output / "0610_線路方向荷重.json"
    result = json.loads(result_path.read_text("utf-8"))
    if defect == "corrupt_json":
        result_path.write_text("not JSON", encoding="utf-8")
    else:
        result[defect] = "wrong"
        result_path.write_text(json.dumps(result), encoding="utf-8")
    digest = hashlib.sha256(result_path.read_bytes()).hexdigest()
    metadata["artifacts"]["result_json"]["sha256"] = digest
    for entry in metadata["artifact_manifest"]:
        if entry["role"] == "0610.result_json":
            entry["sha256"] = digest
    artifacts.frameweb_paths(post)[1].write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError):
        artifacts.validate_frameweb_artifacts(post_dir=post, output_dir=output, expected_input_sha256="a" * 64)
