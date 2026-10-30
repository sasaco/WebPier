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
import subprocess

import pymupdf
import pytest

from pipeline_support import FIXTURES, choose, copy_input, fake_reactions, tree
from webpier.core.errors import InputError
from webpier.core.integrity import content_sha256, load_json, sha256
from webpier.export.jrsnap import LONGITUDINAL, TRANSVERSE, validate_ndu
from webpier.inputs.outputs import OUTPUT_KEYS, uses
from webpier.pipeline import jrsnap
from webpier.pipeline.generate import GenerationOptions, generate, validate
from webpier.pipeline.stages import STAGES
from webpier.reporting.stages.cantilever_check import NOT_CHECKED

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
    generation = generate(GenerationOptions(source, root / "output", root / "post", export_dir=root / "export"))
    return root, source, generation


@pytest.fixture(scope="module")
def analysis_generation(tmp_path_factory):
    root = tmp_path_factory.mktemp("analysis")
    source = copy_input(root / "pre", *DEFAULT, *FRAMES)
    generation = generate(GenerationOptions(source, root / "output", root / "post", export_dir=root / "export"))
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
    """The stand-in writes one case per combination of the NDU, named as JRSNAP names it (decisions 47, 76): four
    照査パターン along the track, and across it the up track 正向 and the down track 逆向."""
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
    patterns = ("ρm10_αf1", "ρm12_αf1", "ρm10_αf2", "ρm12_αf2")
    along = tuple(f"Case{case}_{pattern}_正向" for case, pattern in enumerate(patterns, 1))
    across = along + tuple(f"Case{case}_{pattern}_逆向" for case, pattern in enumerate(patterns, 5))
    for stage, source_stage, stem, names in (("0711", "0710", "線路方向", along),
                                             ("0721", "0720", "線路直角方向", across)):
        cases = range(1, len(names) + 1)
        folder, ndu = f"{stem}_JRSNAP", f"{stem}.ndu"
        digest = sha256(post[ndu])
        assert {name: content for name, content in post.items() if name.startswith(folder + "/")} == {
            f"{folder}/{stem}({name}).{suffix}": f"FAKE {word} {ndu} {digest}\n".encode()
            for name in names for suffix, word in (("ndt", "NDT"), ("DB1", "DB1"), ("LOG", "LOG"), ("OUT", "OUT"))}
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
        databases = [post[f"{folder}/{stem}({name}).DB1"] for name in names]
        assert pages == [*(f"FAKE AGGRESE Case{case} {sha256(database)[:16]}" for case, database in zip(cases, databases)),
                         f"FAKE AGGRESE SUMMARY {sha256(post[project])[:16]}"]
        result = load_json(output[f"{reports[stage]}.json"])
        assert result["result"] is None
        assert result["seismic_check"] == {
            "engine": "aggrese", "engine_version": "fake-1", "engineering_status": "not_evaluated",
            "cases": [{"caseNumber": case, "name": f"{stem}({name})", "aggregated": True}
                      for case, name in zip(cases, names)],
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
    """Decisions 48, 121: Capacita (the stand-in) checks the WDJ with the published PIK and its commentary numbered
    from 8.5; the report is its pages, the WDJ it returns is published, and the result JSON records that the check ran
    and the numbers of the sections."""
    root, _, _ = analysis_generation
    post, output = tree(root / "post"), tree(root / "output")
    completed = load_json(post["線路方向.wdj"])
    assert completed["pickup_filename"] == "線路方向.pik"
    assert completed["pickup_data"] == {"fake": sha256(post["線路方向.pik"])}
    assert completed["members"][0]["shape"] == 1 and completed["calc"]["print_section_force_checked"] is True
    assert completed["calc"]["print_commentary_checked"] is True
    sidecar = load_json(post["線路方向.wdj.provenance.json"])
    assert (sidecar["stage"], sidecar["export"], sidecar["sha256"]) == ("0611", "wdj", sha256(post["線路方向.wdj"]))
    assert sidecar["section_check"]["pik"]["sha256"] == sha256(post["線路方向.pik"])
    stem = STAGES.get("0611").stem
    document = load_json(output[f"{stem}.json"])
    assert document["section_check"] == {"engine": "webdan2", "engine_version": "fake-1",
                                         "engineering_status": "not_evaluated",
                                         "wdj": {"file": "線路方向.wdj", "sha256": sha256(post["線路方向.wdj"])},
                                         "skipped_sections": []}
    assert document["result"]["headings"] == {
        "section_forces": "8.5", "bending_safety_destruction": "8.6", "shear_safety_destruction": None,
        "bending_durability": "8.7", "shear_durability": None, "bending_serviceability": "8.8",
        "bending_restorability": "8.9", "shear_restorability": None, "bending_rebar_amount": "8.10"}
    with pymupdf.open(stream=output[f"{stem}.pdf"], filetype="pdf") as pdf:
        texts = [page.get_text().strip() for page in pdf]
    assert len(texts) == 10 and all(text.startswith("FAKE CAPACITA") for text in texts)  # WebPier lays out nothing
    assert texts[0].startswith("FAKE CAPACITA section_forces 1/2")
    assert f"{STAGES.get('0611').stem}.xlsx" not in tree(root / "export")  # no grid Excel workbook (decision 121)
    with pymupdf.open(stream=output[f"{STAGES.get('0612').stem}.pdf"], filetype="pdf") as pdf:
        assert pdf[0].get_text().strip().startswith("8.11 基礎の照査")


def test_the_column_section_check_of_0621(analysis_generation):
    """Decisions 48, 121: across the track the same, numbered from 9.5, with the column bottom at its place in the PIK
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
    assert load_json(output[f"{stem}.json"])["result"]["headings"]["bending_rebar_amount"] == "9.10"
    with pymupdf.open(stream=output[f"{stem}.pdf"], filetype="pdf") as pdf:
        texts = [page.get_text().strip() for page in pdf]
    assert len(texts) == 10 and texts[0].startswith("FAKE CAPACITA section_forces 1/2")


def test_0400_and_the_foundation_check_take_the_numbers_capacita_gave(tmp_path, monkeypatch):
    """Decision 121: with 0621 in the same generation 0400 refers to the numbers Capacita gave its sections, and 0622
    follows the last of them. Capacita skips the serviceability across the track (the stand-in's skip, as Example2):
    使用性（損傷） 9.8, 最小鉄筋量及び最大鉄筋量 9.9, 基礎の照査 9.10. Along the track, not checked in this generation,
    0400 names the column check without a number."""
    monkeypatch.setenv("FAKE_CAPACITA", "skip")
    source = copy_input(tmp_path / "pre", "detailing", *items_for("0621"))
    generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))
    output = tree(tmp_path / "output")
    assert load_json(output[f"{STAGES.get('0621').stem}.json"])["result"]["headings"] == {
        "section_forces": "9.5", "bending_safety_destruction": "9.6", "shear_safety_destruction": None,
        "bending_durability": "9.7", "bending_restorability": "9.8", "shear_restorability": None,
        "bending_rebar_amount": "9.9"}
    with pymupdf.open(stream=output[f"{STAGES.get('0622').stem}.pdf"], filetype="pdf") as pdf:
        assert pdf[0].get_text().strip().startswith("9.10 基礎の照査")
    with pymupdf.open(stream=output[f"{STAGES.get('0400').stem}.pdf"], filetype="pdf") as pdf:
        text = "".join(page.get_text() for page in pdf).replace("\n", "")
    assert "照査は「9.9 最小鉄筋量及び最大鉄筋量」に示す。" in text and "照査は「9.7 耐久性の照査」に示す。" in text
    assert "照査は、柱の断面照査を行うときに「最小鉄筋量及び最大鉄筋量」で確かめる。" in text
    assert "9.10 最小鉄筋量" not in text and "8.10" not in text


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


K012 = ("片持ち梁の照査", "疲労", "等価繰返し回数")


def _with_repetitions(source, a12, b12):
    document = load_json(source.read_bytes())
    node = document
    for key in K012:
        node = node[key]
    node["A列車"]["k=0.12"], node["B列車"]["k=0.12"] = a12, b12
    source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return source


@pytest.mark.parametrize("changes,message", [
    ({"repetitions": (10.39, None)}, "片持ち梁の照査.疲労.等価繰返し回数.B列車.k=0.12: 値が必要です"),
    ({"stirrups": None}, "鉄筋.梁.stirrups.effective_legs: 値が必要です"),
    ({"exposure": None}, "片持ち梁の照査.水掛かりの程度.上面: 値が必要です"),
    ({"ratios": None}, "片持ち梁の照査.疲労.最大変動断面力比.A列車: 値が必要です"),
])
def test_an_input_error_of_0910_stops_the_generation_before_any_runner(tmp_path, monkeypatch, changes, message):
    """Decision 125: 0910 reads its inputs after the four runners (complete); its precheck reads them before any."""
    source = _with_repetitions(copy_input(tmp_path / "pre", *items_for("0910")), *changes.get("repetitions", (10.39, 10.39)))
    document = load_json(source.read_bytes())
    if "stirrups" in changes:
        document["鉄筋"]["梁"]["stirrups"]["effective_legs"] = None
    if "exposure" in changes:
        document["片持ち梁の照査"]["水掛かりの程度"]["上面"] = None
    if "ratios" in changes:
        document["片持ち梁の照査"]["疲労"]["最大変動断面力比"] = {"A列車": None, "B列車": None}
    source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args) or pytest.fail("a runner was called"))
    with pytest.raises(InputError, match=re.escape(message)):
        generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))
    assert not calls and not (tmp_path / "output").exists() and not (tmp_path / "post").exists()
    with pytest.raises(InputError, match=re.escape(message)):  # validate (webpier_validate) says the same
        validate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))


def test_without_the_k012_repetitions_0910_checks_the_main_bars_fatigue_alone(tmp_path):
    """Decision 125: both k = 0.12 blank: the WDJ leaves the shear rows of 疲労 blank, the stand-in (as the real runner)
    returns no shear_safety_fatigue, and the report says so in one sentence."""
    source = _with_repetitions(copy_input(tmp_path / "pre", *items_for("0910")), None, None)
    generation = generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))
    result = generation.results["0910"]
    assert "shear_safety_fatigue" not in result.sections and "bending_safety_fatigue" in result.sections
    wdj = load_json(tree(tmp_path / "post")["片持ち梁.wdj"])
    assert wdj["force"][0]["Vd3_Vd"] is None and wdj["force"][0]["Md3_Md"] is not None
    with pymupdf.open(stream=tree(tmp_path / "output")[f"{STAGES.get('0910').stem}.pdf"], filetype="pdf") as pdf:
        text = "".join(page.get_text() for page in pdf).replace("\n", "")
    assert NOT_CHECKED in text and "FAKE CAPACITA shear_safety_fatigue" not in text
    assert "FAKE CAPACITA bending_safety_fatigue" in text


@pytest.mark.parametrize("path,message", [
    (("鉄筋", "フーチング", "aggregate_max_mm"), "鉄筋.フーチング.aggregate_max_mm: 値が必要です"),
    (("柱の断面照査", "ε'csd"), "柱の断面照査.ε'csd: 値が必要です"),
])
def test_an_input_error_of_0810_stops_the_generation_before_any_runner(tmp_path, monkeypatch, path, message):
    """Decision 125: the footing of the seismic part alone (no column check reads 柱の断面照査 first) reads its inputs in
    complete, after JRSNAP and Aggre-SE; its precheck reads them before any runner."""
    source = copy_input(tmp_path / "pre", "ground_model", "reactions", "longitudinal_seismic", "transverse_seismic",
                        *NONLINEAR, "footing")
    document = load_json(source.read_bytes())
    *parents, key = path
    node = document
    for part in parents:
        node = node[part]
    node[key] = None
    source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args) or pytest.fail("a runner was called"))
    with pytest.raises(InputError, match=re.escape(message)):
        generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))
    assert not calls and not (tmp_path / "output").exists()
