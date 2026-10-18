"""The real registry: every stage alone gives the same bytes as the all generation, the frame analysis stages
(decision 46) add the pickup files of the stand-in runner without changing any report, and the static nonlinear
analysis (decision 47) adds the folder of the stand-in JRSNAP runner for the published NDU, with the Aggre-SE project
that reads it (decision 49)."""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from pipeline_support import FIXTURES, copy_input, tree
from webpier.core.errors import InputError
from webpier.core.integrity import content_sha256, load_json, sha256
from webpier.export.jrsnap import LONGITUDINAL, TRANSVERSE, validate_ndu
from webpier.pipeline import jrsnap
from webpier.pipeline.generate import GenerationOptions, generate
from webpier.pipeline.stages import STAGES


@pytest.fixture(scope="module")
def all_generation(tmp_path_factory):
    root = tmp_path_factory.mktemp("all")
    source = copy_input(root / "pre")
    generation = generate(GenerationOptions(source, root / "output", root / "post"))
    return root, source, generation


@pytest.fixture(scope="module")
def analysis_generation(tmp_path_factory):
    root = tmp_path_factory.mktemp("analysis")
    source = copy_input(root / "pre")
    generation = generate(GenerationOptions(source, root / "output", root / "post", frame_analysis=True))
    return root, source, generation


PICKUPS = {"0611": "線路方向", "0621": "線路直角方向"}


def pickup_files(stem):
    return [f"{stem}.pik", f"{stem}_ピックアップ変位量.csv", f"{stem}_ピックアップ反力.csv"]


def test_all_publishes_a_report_and_result_for_every_stage_and_every_export(all_generation):
    root, source, generation = all_generation
    output, post = tree(root / "output"), tree(root / "post")
    reports = [stage for stage in STAGES.stages if stage.has_report]  # 0611, 0621 have none (decision 46)
    assert sorted(output) == sorted(f"{stage.stem}.{suffix}" for stage in reports for suffix in ("pdf", "json"))
    exports = ["線路方向.json", "線路直角方向.json", "線路方向.ndu", "線路直角方向.ndu"]
    assert sorted(post) == sorted([*exports, *(name + ".provenance.json" for name in exports)])
    for stage in reports:
        assert output[f"{stage.stem}.pdf"].startswith(b"%PDF-")
        document = load_json(output[f"{stage.stem}.json"])
        assert (document["schema_version"], document["stage"]) == (1, stage.id)
        assert document["input"] == {"file": "input.json", "sha256": sha256(source.read_bytes())}
    sidecar = load_json(post["線路方向.json.provenance.json"])
    assert sidecar["sha256"] == sha256(post["線路方向.json"])
    assert {item["file"]: item["sha256"] for item in sidecar["artifacts"]} == {
        name: sha256(content) for name, content in {**output, **post}.items() if not name.endswith(".provenance.json")}
    assert load_json(post["線路方向.json"])  # strict JSON for FrameWeb
    assert generation.published


@pytest.mark.parametrize("stage", STAGES.select("all"))
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
        item.file_name: tree(root / "post")[item.file_name] for item in spec.exports}


@pytest.mark.parametrize("stage,profile", [("0710", LONGITUDINAL), ("0720", TRANSVERSE)])
def test_a_seismic_stage_writes_a_valid_ndu(all_generation, tmp_path, stage, profile):
    root, _, _ = all_generation
    source = copy_input(tmp_path / "pre")
    generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post", stage=stage))
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


def blank_jrsnap_input(directory):
    """The current input with every JRSNAP setting blank (null), as a new input has them."""
    source = copy_input(directory)
    document = load_json(source.read_bytes())
    for key in ("jrsnap_longitudinal", "jrsnap_transverse"):
        document[key] = dict.fromkeys(document[key])
    source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return source


@pytest.mark.parametrize("stage", ["0500", "0600", "0610", "0620"])
def test_the_stages_without_an_ndu_need_no_jrsnap_settings(all_generation, tmp_path, stage):
    root, _, _ = all_generation
    generate(GenerationOptions(blank_jrsnap_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post",
                               stage=stage))
    report = f"{STAGES.get(stage).stem}.pdf"
    assert sorted(tree(tmp_path / "output")) == sorted([report, report.replace(".pdf", ".json")])
    assert tree(tmp_path / "output")[report] == tree(root / "output")[report]  # the settings change no report


@pytest.mark.parametrize("stage,key", [("0710", "jrsnap_longitudinal"), ("0720", "jrsnap_transverse"),
                                       ("all", "jrsnap_longitudinal")])
def test_a_blank_jrsnap_setting_stops_a_generation_with_an_ndu(tmp_path, stage, key):
    """Decision 42: the settings are required (decision 40); nothing is filled in and nothing is published."""
    with pytest.raises(InputError, match=re.escape(f"{key}.") + ".*値が必要です"):
        generate(GenerationOptions(blank_jrsnap_input(tmp_path / "pre"), tmp_path / "output", tmp_path / "post",
                                   stage=stage))
    assert not (tmp_path / "output").exists() and not (tmp_path / "post").exists()


def test_the_frame_analysis_adds_the_pickup_files_and_changes_no_report(all_generation, analysis_generation):
    root, _, _ = analysis_generation
    assert analysis_generation[2].stages == ("0500", "0600", "0610", "0611", "0620", "0621", "0710", "0720")
    assert tree(root / "output") == tree(all_generation[0] / "output")
    post = tree(root / "post")
    natives = ["線路方向.json", "線路直角方向.json", "線路方向.ndu", "線路直角方向.ndu",
               *(name for stem in PICKUPS.values() for name in pickup_files(stem))]
    assert sorted(post) == sorted([*natives, *(name + ".provenance.json" for name in natives)])
    for stage, stem in PICKUPS.items():
        digest = sha256(post[f"{stem}.json"])
        assert [post[name] for name in pickup_files(stem)] == [
            f"FAKE {word} {stem}.json {digest}\n".encode() for word in ("PIK", "DISPLACEMENT", "REACTION")]
        sidecar = load_json(post[f"{stem}.pik.provenance.json"])
        assert (sidecar["stage"], sidecar["export"]) == (stage, "pik")
        assert sidecar["frame_analysis"]["frameweb"] == {"stage": {"0611": "0610", "0621": "0620"}[stage],
                                                         "export": "frameweb", "file": f"{stem}.json",
                                                         "sha256": digest}
    assert hashlib.sha256(post["線路方向.json"]).hexdigest() == sha256(tree(all_generation[0] / "post")["線路方向.json"])


def test_the_nonlinear_analysis_adds_the_jrsnap_folder_of_each_published_ndu(all_generation, tmp_path):
    """The stand-in writes one case per combination of the NDU: the transverse one has two (decision 47)."""
    source = copy_input(tmp_path / "pre")
    generation = generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post", nonlinear_analysis=True))
    assert generation.stages == ("0500", "0600", "0610", "0620", "0710", "0711", "0720", "0721")
    assert tree(tmp_path / "output") == tree(all_generation[0] / "output")
    post = tree(tmp_path / "post")
    for stage, source_stage, stem, cases in (("0711", "0710", "線路方向", (1,)), ("0721", "0720", "線路直角方向", (1, 2))):
        folder, ndu = f"{stem}_JRSNAP", f"{stem}.ndu"
        digest = sha256(post[ndu])
        assert {name: content for name, content in post.items() if name.startswith(folder + "/")} == {
            f"{folder}/{stem}(Case{case}_ρm10_αf1_正向).{suffix}": f"FAKE {word} {ndu} {digest}\n".encode()
            for case in cases for suffix, word in (("ndt", "NDT"), ("DB1", "DB1"), ("LOG", "LOG"), ("OUT", "OUT"))}
        sidecar = load_json(post[f"{folder}.provenance.json"])
        assert (sidecar["stage"], sidecar["export"], sidecar["file"]) == (stage, "jrsnap", folder)
        assert sidecar["nonlinear_analysis"]["ndu"] == {"stage": source_stage, "export": "jrsnap", "file": ndu,
                                                        "sha256": digest}
        assert post[ndu] == tree(all_generation[0] / "post")[ndu]
        # Decision 49: the Example2 projects saved again by Aggre-SE (tests/fixtures/example2/aggrese/notes.md).
        project = f"{stem}.xml"
        assert post[project] == (FIXTURES / "example2" / "aggrese" / project).read_bytes()
        sidecar = load_json(post[f"{project}.provenance.json"])
        assert (sidecar["stage"], sidecar["export"], sidecar["sha256"]) == (stage, "aggrese", sha256(post[project]))
        assert sidecar["metadata"] == {"target": "Aggre-SE", "target_version": "5.3.0.1", "app_read_verified": False,
                                       "seismic_check_run": False}
        assert sidecar["aggrese_project"] == {"jrsnap": {"stage": stage, "export": "jrsnap", "file": folder,
                                                         "sha256": content_sha256(tmp_path / "post" / folder)}}


@pytest.mark.parametrize("key", ["地域別", "地盤区分"])
@pytest.mark.parametrize("stage", ["0711", "0721"])
def test_a_blank_seismic_design_condition_stops_a_nonlinear_analysis_before_it_runs(tmp_path, monkeypatch, stage,
                                                                                    key):
    """Decision 49: only 0711 and 0721 need the 耐震設計条件, and a blank one is an input error before the runner."""
    source = copy_input(tmp_path / "pre")
    document = load_json(source.read_bytes())
    document["耐震設計条件"][key] = None
    source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(jrsnap, "analyze_nonlinear", lambda *args, **kwargs: pytest.fail("the runner was called"))
    with pytest.raises(InputError, match=re.escape(f"耐震設計条件.{key}: 値が必要です")):
        generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post", stage=stage))
    assert not (tmp_path / "output").exists() and not (tmp_path / "post").exists()
    generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))  # all: no analysis, no condition


@pytest.mark.parametrize("stage", ["0611", "0621"])
def test_a_frame_analysis_stage_alone_publishes_only_its_pickup_files(analysis_generation, tmp_path, stage):
    root, _, _ = analysis_generation
    source = copy_input(tmp_path / "pre")
    generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post", stage=stage))
    assert not (tmp_path / "output").exists()
    names = pickup_files(PICKUPS[stage])
    post = tree(tmp_path / "post")
    assert sorted(post) == sorted([*names, *(name + ".provenance.json" for name in names)])
    assert {name: post[name] for name in names} == {name: tree(root / "post")[name] for name in names}
