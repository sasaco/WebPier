"""The real registry: each 出力項目 with the items it uses gives the same reports as the default generation (decision
72; the result JSON differ only in the SHA256 of the input, which chooses other items), the frame analysis stages
(decision 46) add the pickup files of the stand-in runner without changing any report, and the static nonlinear
analysis (decision 47) adds the folder of the stand-in JRSNAP runner for the published NDU, with the Aggre-SE project
that reads it (decision 49), the reports of 0711 and 0721, which are the stand-in Aggre-SE runner's (decision 56),
and its pickups and summary workbooks (decisions 57, 58)."""

from __future__ import annotations

import hashlib
import json
import re

import pymupdf
import pytest

from pipeline_support import FIXTURES, choose, copy_input, fake_reactions, tree
from webpier.core.errors import InputError
from webpier.core.integrity import content_sha256, load_json, sha256
from webpier.export.jrsnap import LONGITUDINAL, TRANSVERSE, validate_ndu
from webpier.inputs.outputs import OUTPUT_KEYS, uses
from webpier.pipeline import jrsnap
from webpier.pipeline.generate import GenerationOptions, generate
from webpier.pipeline.stages import STAGES

# The 出力項目 current.json chooses (decision 72): every item but the analyses, the footing and the cantilever.
DEFAULT = ("ground_model", "reactions", "longitudinal", "transverse", "longitudinal_seismic", "transverse_seismic")
FRAMES = ("longitudinal_frame_analysis", "transverse_frame_analysis")
NONLINEAR = ("longitudinal_nonlinear_analysis", "transverse_nonlinear_analysis")


def items_for(stage):
    """The 出力項目 of *stage* with every item it uses: the least an input chooses to make *stage*."""
    item = STAGES.item(stage)
    return tuple(key for key in OUTPUT_KEYS if key == item or key in uses(item))


def without_input(output):
    """The published reports and result JSON without the input's name and SHA256, which an input choosing other
    出力項目 changes (decision 72)."""
    return {name: {key: value for key, value in load_json(content).items() if key != "input"}
            if name.endswith(".json") else content for name, content in output.items()}


@pytest.fixture(scope="module")
def all_generation(tmp_path_factory):
    root = tmp_path_factory.mktemp("all")
    source = copy_input(root / "pre")
    generation = generate(GenerationOptions(source, root / "output", root / "post"))
    return root, source, generation


@pytest.fixture(scope="module")
def analysis_generation(tmp_path_factory):
    root = tmp_path_factory.mktemp("analysis")
    source = copy_input(root / "pre", *DEFAULT, *FRAMES)
    generation = generate(GenerationOptions(source, root / "output", root / "post"))
    return root, source, generation


PICKUPS = {"0611": "線路方向", "0621": "線路直角方向"}


def pickup_files(stem):
    return [f"{stem}.pik", f"{stem}_ピックアップ変位量.csv", f"{stem}_ピックアップ反力.csv"]


def test_the_default_items_publish_a_report_and_result_for_every_stage_and_every_export(all_generation):
    root, source, generation = all_generation
    output, post = tree(root / "output"), tree(root / "post")
    reports = [STAGES.get(stage) for stage in STAGES.selected(DEFAULT)]
    assert generation.stages == ("0500", "0600", "0610", "0620", "0710", "0720")
    assert sorted(output) == sorted(f"{stage.stem}.{suffix}" for stage in reports for suffix in ("pdf", "json"))
    exports = ["線路方向.json", "線路直角方向.json", "線路方向.ndu", "線路直角方向.ndu"]
    assert sorted(post) == sorted([*exports, *(name + ".provenance.json" for name in exports)])
    for stage in reports:
        assert output[f"{stage.stem}.pdf"].startswith(b"%PDF-")
        document = load_json(output[f"{stage.stem}.json"])
        assert (document["schema_version"], document["stage"]) == (1, stage.id)
        assert document["input"] == {"file": "input.json", "sha256": sha256(source.read_bytes())}
    # the grid Excel workbook of every report WebPier lays out, in export/ beside output/
    export = tree(root / "export")
    assert sorted(export) == sorted(f"{stage.stem}.xlsx" for stage in reports)
    assert all(content.startswith(b"PK") for content in export.values())
    sidecar = load_json(post["線路方向.json.provenance.json"])
    assert sidecar["sha256"] == sha256(post["線路方向.json"])
    assert {item["file"]: item["sha256"] for item in sidecar["artifacts"]} == {
        name: sha256(content) for name, content in {**output, **post, **export}.items()
        if not name.endswith(".provenance.json")}
    assert {item["directory"] for item in sidecar["artifacts"] if item["file"].endswith(".xlsx")} == {"export"}
    assert load_json(post["線路方向.json"])  # strict JSON for FrameWeb
    assert generation.published


@pytest.mark.parametrize("item", DEFAULT)
def test_each_item_with_the_items_it_uses_publishes_the_same_reports_as_the_default(all_generation, tmp_path, item):
    """Decision 72: the stages of the chosen items, and their reports and exports as the default generation's."""
    root, _, _ = all_generation
    chosen = (*(key for key in OUTPUT_KEYS if key in uses(item)), item)
    source = copy_input(tmp_path / "pre", *chosen)
    generation = generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))
    assert generation.stages == STAGES.selected(chosen)
    alone = tree(tmp_path / "output")
    assert sorted(alone) == sorted(f"{STAGES.get(stage).stem}.{suffix}" for stage in generation.stages
                                   for suffix in ("json", "pdf"))
    assert without_input(alone) == {name: content for name, content in without_input(tree(root / "output")).items()
                                     if name in alone}
    assert {load_json(content)["input"]["sha256"] for name, content in alone.items() if name.endswith(".json")} == {
        sha256(source.read_bytes())}
    exported = tree(tmp_path / "post") if (tmp_path / "post").exists() else {}
    assert {name: content for name, content in exported.items() if not name.endswith(".provenance.json")} == {
        export.file_name: tree(root / "post")[export.file_name] for stage in generation.stages
        for export in STAGES.get(stage).exports}


@pytest.mark.parametrize("stage,profile", [("0710", LONGITUDINAL), ("0720", TRANSVERSE)])
def test_a_seismic_stage_writes_a_valid_ndu(all_generation, tmp_path, stage, profile):
    root, _, _ = all_generation
    source = copy_input(tmp_path / "pre", *items_for(stage))
    generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))
    (item,) = STAGES.get(stage).exports
    post = tree(tmp_path / "post")
    assert sorted(name for name in post if name.startswith(item.file_name)) == [
        item.file_name, item.file_name + ".provenance.json"]
    validate_ndu(post[item.file_name], profile)
    assert post[item.file_name].endswith(b"\r\n")
    sidecar = load_json(post[item.file_name + ".provenance.json"])
    assert (sidecar["stage"], sidecar["export"], sidecar["sha256"]) == (stage, "jrsnap", sha256(post[item.file_name]))
    assert sidecar["metadata"] == {"target_version": "5.2-L03", "app_read_verified": False, "analysis_run": False}
    assert {name: content for name, content in without_input(tree(tmp_path / "output")).items()
            if name.startswith(stage)} == {name: content for name, content in without_input(tree(root / "output")).items()
                                           if name.startswith(stage)}


def blank_jrsnap_input(directory, *items):
    """The current input, choosing *items* when given, with every JRSNAP setting blank (null), as a new input has
    them."""
    source = copy_input(directory, *items)
    document = load_json(source.read_bytes())
    for key in ("jrsnap_longitudinal", "jrsnap_transverse"):
        document[key] = dict.fromkeys(document[key])
    source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return source


@pytest.mark.parametrize("stage", ["0500", "0600", "0610", "0620"])
def test_the_stages_without_an_ndu_need_no_jrsnap_settings(all_generation, tmp_path, stage):
    root, _, _ = all_generation
    generate(GenerationOptions(blank_jrsnap_input(tmp_path / "pre", *items_for(stage)), tmp_path / "output",
                               tmp_path / "post"))
    report = f"{STAGES.get(stage).stem}.pdf"
    assert report in tree(tmp_path / "output") and not any(name.startswith("07") for name in tree(tmp_path / "output"))
    assert tree(tmp_path / "output")[report] == tree(root / "output")[report]  # the settings change no report


@pytest.mark.parametrize("items,key", [(items_for("0710"), "jrsnap_longitudinal"),
                                       (items_for("0720"), "jrsnap_transverse"), (DEFAULT, "jrsnap_longitudinal")])
def test_a_blank_jrsnap_setting_stops_a_generation_with_an_ndu(tmp_path, items, key):
    """Decision 42: the settings are required (decision 40); nothing is filled in and nothing is published."""
    with pytest.raises(InputError, match=re.escape(f"{key}.") + ".*値が必要です"):
        generate(GenerationOptions(blank_jrsnap_input(tmp_path / "pre", *items), tmp_path / "output",
                                   tmp_path / "post"))
    assert not (tmp_path / "output").exists() and not (tmp_path / "post").exists()


def test_the_frame_analysis_adds_the_pickup_files_and_changes_no_report(all_generation, analysis_generation):
    """Decisions 46, 48, 54: the analysis adds the pickup files, 0611 and 0621 their column section checks (report,
    result JSON and the completed WDJ) and 0612 and 0622 their foundation checks (report and result JSON), which share
    the analysis of the same FrameWeb file; the reports of all are unchanged."""
    root, _, _ = analysis_generation
    assert analysis_generation[2].stages == ("0500", "0600", "0610", "0611", "0612", "0620", "0621", "0622", "0710",
                                             "0720")
    output = tree(root / "output")
    columns = tuple(STAGES.get(stage).stem for stage in ("0611", "0612", "0621", "0622"))
    assert without_input({name: content for name, content in output.items() if not name.startswith(columns)}) == (
        without_input(tree(all_generation[0] / "output")))
    assert sorted(name for name in output if name.startswith(columns)) == sorted(
        f"{column}.{suffix}" for column in columns for suffix in ("json", "pdf"))
    post = tree(root / "post")
    natives = ["線路方向.json", "線路直角方向.json", "線路方向.ndu", "線路直角方向.ndu", "線路方向.wdj", "線路直角方向.wdj",
               *(name for stem in PICKUPS.values() for name in pickup_files(stem))]
    assert sorted(post) == sorted([*natives, *(name + ".provenance.json" for name in natives)])
    for stage, stem in PICKUPS.items():
        digest = sha256(post[f"{stem}.json"])
        # the PIK's first line stands for its header; its points follow (tests/fixtures/fempython/fake_runner.py)
        assert [post[name].split(b"\n")[0] + b"\n" for name in pickup_files(stem)[:2]] == [
            f"FAKE {word} {stem}.json {digest}\n".encode() for word in ("PIK", "DISPLACEMENT")]
        assert post[f"{stem}_ピックアップ反力.csv"] == fake_reactions(post[f"{stem}.json"])
        sidecar = load_json(post[f"{stem}.pik.provenance.json"])
        assert (sidecar["stage"], sidecar["export"]) == (stage, "pik")
        assert sidecar["frame_analysis"]["frameweb"] == {"stage": {"0611": "0610", "0621": "0620"}[stage],
                                                         "export": "frameweb", "file": f"{stem}.json",
                                                         "sha256": digest}
        assert sidecar["frame_analysis"]["stages"] == [stage, {"0611": "0612", "0621": "0622"}[stage]]
    assert hashlib.sha256(post["線路方向.json"]).hexdigest() == sha256(tree(all_generation[0] / "post")["線路方向.json"])


def test_the_nonlinear_analysis_adds_the_jrsnap_folder_of_each_published_ndu(all_generation, tmp_path):
    """The stand-in writes one case per combination of the NDU: the transverse one has two (decision 47)."""
    source = copy_input(tmp_path / "pre", *DEFAULT, *NONLINEAR, "cantilever")
    generation = generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))
    assert generation.stages == ("0500", "0600", "0610", "0620", "0710", "0711", "0720", "0721", "0900", "0910")
    output = tree(tmp_path / "output")
    reports = {"0711": "0711_線路方向非線形解析", "0721": "0721_線路直角方向非線形解析", "0900": "0900_片持ち梁",
               "0910": "0910_片持ち梁照査"}
    assert without_input({name: content for name, content in output.items()
                          if not name.startswith(tuple(reports.values()))}) == without_input(
        tree(all_generation[0] / "output"))
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
        assert sidecar["metadata"] == {"target": "Aggre-SE", "target_version": "5.3.0.1"}
        assert sidecar["aggrese_project"] == {"jrsnap": {"stage": stage, "export": "jrsnap", "file": folder,
                                                         "sha256": content_sha256(tmp_path / "post" / folder)}}
        assert sidecar["seismic_check"] == {"report": f"{stage}.pdf", "engine": "aggrese", "engine_version": "fake-1"}
        # Decision 56: the report is the stand-in Aggre-SE runner's, one page per Case and a summary page.
        with pymupdf.open(stream=output[f"{reports[stage]}.pdf"], filetype="pdf") as document:
            pages = [page.get_text().strip() for page in document]
        databases = [post[f"{folder}/{stem}(Case{case}_ρm10_αf1_正向).DB1"] for case in cases]
        assert pages == [*(f"FAKE AGGRESE Case{case} {sha256(database)[:16]}" for case, database in zip(cases, databases)),
                         f"FAKE AGGRESE SUMMARY {sha256(post[project])[:16]}"]
        result = load_json(output[f"{reports[stage]}.json"])
        assert result["result"] is None
        assert result["seismic_check"] == {
            "engine": "aggrese", "engine_version": "fake-1", "engineering_status": "not_evaluated",
            "cases": [{"caseNumber": case, "name": f"{stem}(Case{case}_ρm10_αf1_正向)", "aggregated": True}
                      for case in cases],
            "project": {"file": project, "sha256": sha256(post[project])},
            "jrsnap": {"file": folder, "sha256": content_sha256(tmp_path / "post" / folder)},
            "files": {kind: {"file": name, "sha256": sha256(post[name])}
                      for kind, name in (("pik", f"{stem}_Aggre-SE.pik"), ("xlsx", f"{stem}_Aggre-SE.xlsx"),
                                         ("steps", f"{stem}_Aggre-SE_直接基礎.csv"))}}
        # Decision 57: Aggre-SE's pickup beside the folder, as the stand-in returned it, with its sidecar.
        assert post[f"{stem}_Aggre-SE.pik"] == f"Batch ver1.0.0\r\nFAKE PIK {sha256(post[project])[:16]}\r\n".encode()
        sidecar = load_json(post[f"{stem}_Aggre-SE.pik.provenance.json"])
        assert (sidecar["stage"], sidecar["export"]) == (stage, "pik")
        assert sidecar["seismic_check"]["pickups"] == {"1": "L1地震動", "2": "復旧性L2地震動", "3": "安全性L2地震動"}
        # Decision 58: Aggre-SE's summary workbook beside it the same way.
        sidecar = load_json(post[f"{stem}_Aggre-SE.xlsx.provenance.json"])
        assert (sidecar["stage"], sidecar["export"], sidecar["sha256"]) == (
            stage, "xlsx", sha256(post[f"{stem}_Aggre-SE.xlsx"]))
        # Decision 60: the step table of the direct foundation beside them, with its columns in the sidecar.
        steps = f"{stem}_Aggre-SE_直接基礎.csv"
        assert post[steps].startswith(b"case_index,case_name,node,step,V,H,M,qvd,qd,Rvd,Mmd,plasticity\r\n")
        sidecar = load_json(post[f"{steps}.provenance.json"])
        assert (sidecar["stage"], sidecar["export"], sidecar["sha256"]) == (stage, "steps", sha256(post[steps]))
        assert sidecar["seismic_check"]["columns"] == [
            "case_index", "case_name", "node", "step", "V", "H", "M", "qvd", "qd", "Rvd", "Mmd", "plasticity"]


@pytest.mark.parametrize("key", ["地域別", "地盤区分"])
@pytest.mark.parametrize("stage", ["0711", "0721"])
def test_a_blank_seismic_design_condition_stops_a_nonlinear_analysis_before_it_runs(tmp_path, monkeypatch, stage,
                                                                                    key):
    """Decision 49: only 0711 and 0721 need the 耐震設計条件, and a blank one is an input error before the runner."""
    source = copy_input(tmp_path / "pre", *items_for(stage))
    document = load_json(source.read_bytes())
    document["耐震設計条件"][key] = None
    source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(jrsnap, "analyze_nonlinear", lambda *args, **kwargs: pytest.fail("the runner was called"))
    with pytest.raises(InputError, match=re.escape(f"耐震設計条件.{key}: 値が必要です")):
        generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))
    assert not (tmp_path / "output").exists() and not (tmp_path / "post").exists()
    choose(source, *DEFAULT)
    generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))  # no analysis, no condition


def test_the_column_section_check_of_0611(analysis_generation):
    """Decision 48: Capacita (the stand-in) checks the WDJ with the published PIK; the report inserts its pages
    after WebPier's headings, the WDJ it returns is published, and the result JSON records that the check ran."""
    root, _, _ = analysis_generation
    post, output = tree(root / "post"), tree(root / "output")
    completed = load_json(post["線路方向.wdj"])
    assert completed["pickup_filename"] == "線路方向.pik"
    assert completed["pickup_data"] == {"fake": sha256(post["線路方向.pik"])}
    assert completed["members"][0]["shape"] == 1 and completed["calc"]["print_section_force_checked"] is True
    sidecar = load_json(post["線路方向.wdj.provenance.json"])
    assert (sidecar["stage"], sidecar["export"], sidecar["sha256"]) == ("0611", "wdj", sha256(post["線路方向.wdj"]))
    assert sidecar["section_check"]["pik"]["sha256"] == sha256(post["線路方向.pik"])
    stem = STAGES.get("0611").stem
    document = load_json(output[f"{stem}.json"])
    assert document["section_check"] == {"engine": "webdan2", "engine_version": "fake-1",
                                         "engineering_status": "not_evaluated",
                                         "wdj": {"file": "線路方向.wdj", "sha256": sha256(post["線路方向.wdj"])},
                                         "skipped_sections": []}
    with pymupdf.open(stream=output[f"{stem}.pdf"], filetype="pdf") as pdf:
        texts = [page.get_text() for page in pdf]
    assert texts[0].strip().startswith("8.5 断面力の総括") and "FAKE CAPACITA section_forces 1/2" in texts[1]
    assert sum("FAKE CAPACITA" in text for text in texts) == 9 and "8.9 使用性（損傷）の照査" in "".join(texts)


def test_the_column_section_check_of_0621(analysis_generation):
    """Decision 48: across the track the same, numbered 9.5 to 9.9, with the column bottom at its place in the PIK
    of 0620 (after the point the wind load on the column adds: 7, the stand-in writing FEMPython's points)."""
    root, _, _ = analysis_generation
    post, output = tree(root / "post"), tree(root / "output")
    completed = load_json(post["線路直角方向.wdj"])
    assert completed["pickup_filename"] == "線路直角方向.pik"
    assert [point["index"] for point in completed["points"]] == [7] and completed["bar"][0]["b"] == 2700
    sidecar = load_json(post["線路直角方向.wdj.provenance.json"])
    assert (sidecar["stage"], sidecar["export"]) == ("0621", "wdj")
    assert sidecar["section_check"]["pik"]["sha256"] == sha256(post["線路直角方向.pik"])
    stem = STAGES.get("0621").stem
    assert load_json(output[f"{stem}.json"])["section_check"]["wdj"]["file"] == "線路直角方向.wdj"
    with pymupdf.open(stream=output[f"{stem}.pdf"], filetype="pdf") as pdf:
        texts = [page.get_text() for page in pdf]
    assert texts[0].strip().startswith("9.5 断面力の総括") and "9.9 使用性（損傷）の照査" in "".join(texts)


@pytest.mark.parametrize("item,stages", [("longitudinal_frame_analysis", ("0611", "0612")),
                                         ("transverse_frame_analysis", ("0621", "0622"))])
def test_the_frame_analysis_of_one_direction_runs_one_shared_analysis(analysis_generation, tmp_path, item, stages):
    """Decisions 48, 54, 72: the item of one direction makes its column check and its 基礎の照査 from one analysis of
    the FrameWeb file, with the reports and files of the generation with both directions."""
    root, _, _ = analysis_generation
    column, stage = stages
    assert items_for(column) == items_for(stage) and item in items_for(column)
    source = copy_input(tmp_path / "pre", *items_for(column))
    generation = generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))
    assert generation.stages == ("0500", "0600", {"0611": "0610", "0621": "0620"}[column], column, stage)
    output = tree(tmp_path / "output")
    assert without_input(output) == {name: content for name, content in without_input(tree(root / "output")).items()
                                     if name in output}
    names = [*pickup_files(PICKUPS[column]), {"0611": "線路方向.wdj", "0621": "線路直角方向.wdj"}[column]]
    post = tree(tmp_path / "post")
    assert {name: post[name] for name in names[:3]} == {name: tree(root / "post")[name] for name in names[:3]}
    assert all(name + ".provenance.json" in post for name in names)
    sidecar = load_json(post[f"{PICKUPS[column]}.pik.provenance.json"])
    assert (sidecar["stage"], sidecar["frame_analysis"]["stages"]) == (column, [column, stage])
    result = load_json(output[f"{STAGES.get(stage).stem}.json"])["result"]
    assert result["engineering_status"] in ("ok", "not_ok") and len(result["columns"]) == 4
