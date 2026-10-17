"""The real registry: every stage alone gives the same bytes as the all generation."""

from __future__ import annotations

import pytest

from pipeline_support import copy_input, tree
from webpier.core.integrity import load_json, sha256
from webpier.export.jrsnap import LONGITUDINAL, TRANSVERSE, validate_ndu
from webpier.pipeline.generate import GenerationOptions, generate
from webpier.pipeline.stages import STAGES


@pytest.fixture(scope="module")
def all_generation(tmp_path_factory):
    root = tmp_path_factory.mktemp("all")
    source = copy_input(root / "pre")
    generation = generate(GenerationOptions(source, root / "output", root / "post"))
    return root, source, generation


def test_all_publishes_a_report_and_result_for_every_stage_and_the_frameweb_files(all_generation):
    root, source, generation = all_generation
    output, post = tree(root / "output"), tree(root / "post")
    assert sorted(output) == sorted(f"{stage.stem}.{suffix}" for stage in STAGES.stages for suffix in ("pdf", "json"))
    exports = [item.file_name for stage in STAGES.stages for item in stage.exports if not item.opt_in]
    assert sorted(post) == sorted([*exports, *(name + ".provenance.json" for name in exports)])
    for stage in STAGES.stages:
        assert output[f"{stage.stem}.pdf"].startswith(b"%PDF-")
        document = load_json(output[f"{stage.stem}.json"])
        assert (document["schema_version"], document["stage"]) == (1, stage.id)
        assert document["input"] == {"file": "input.json", "sha256": sha256(source.read_bytes())}
    sidecar = load_json(post["frameWebForJS.json.provenance.json"])
    assert sidecar["sha256"] == sha256(post["frameWebForJS.json"])
    assert {item["file"]: item["sha256"] for item in sidecar["artifacts"]} == {
        name: sha256(content) for name, content in {**output, **post}.items() if not name.endswith(".provenance.json")}
    assert load_json(post["frameWebForJS.json"])  # strict JSON for FrameWeb
    assert generation.published


@pytest.mark.parametrize("stage", STAGES.ids)
def test_each_stage_alone_publishes_the_same_bytes_as_all(all_generation, tmp_path, stage):
    root, _, _ = all_generation
    source = copy_input(tmp_path / "pre")
    generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post", stage=stage))
    spec = STAGES.get(stage)
    alone = tree(tmp_path / "output")
    assert sorted(alone) == [f"{spec.stem}.json", f"{spec.stem}.pdf"]
    assert alone == {name: content for name, content in tree(root / "output").items() if name in alone}
    exported = tree(tmp_path / "post") if (tmp_path / "post").exists() else {}
    assert {name: content for name, content in exported.items() if not name.endswith(".provenance.json")} == {
        item.file_name: tree(root / "post")[item.file_name] for item in spec.exports if not item.opt_in}


@pytest.mark.parametrize("stage,profile", [("0710", LONGITUDINAL), ("0720", TRANSVERSE)])
def test_jrsnap_writes_a_valid_ndu_only_when_requested(all_generation, tmp_path, stage, profile):
    root, _, _ = all_generation
    source = copy_input(tmp_path / "pre")
    generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post", stage=stage,
                               opt_in=frozenset({"jrsnap"})))
    (item,) = STAGES.get(stage).exports
    post = tree(tmp_path / "post")
    assert sorted(post) == [item.file_name, item.file_name + ".provenance.json"]
    validate_ndu(post[item.file_name], profile)
    assert post[item.file_name].endswith(b"\r\n")
    sidecar = load_json(post[item.file_name + ".provenance.json"])
    assert (sidecar["stage"], sidecar["export"], sidecar["sha256"]) == (stage, "jrsnap", sha256(post[item.file_name]))
    assert sidecar["metadata"] == {"target_version": "5.2-L03", "app_read_verified": False, "analysis_run": False}
    assert tree(tmp_path / "output") == {name: content for name, content in tree(root / "output").items()
                                         if name.startswith(stage)}
