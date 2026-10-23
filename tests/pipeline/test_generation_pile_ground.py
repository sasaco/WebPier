"""0500 of a pile foundation (decision 85, ADR-0013): WebPier writes the .sdt, the JRSNAP runner has SOIL-JR calculate it, and
the stage's report is SOIL-JR's as the runner printed it; the .sdr and .sdc (and the two for the liquefaction) are published
under post/ as returned, with the result JSON and the sidecars recording the calculation without a judgement. The
runner is the stand-in of tests/fixtures/jrsnap/fake_runner.py (``soil``); the real SOIL-JR is checked in the acceptance."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest

from pipeline_support import FIXTURES, tree
from webpier.core.integrity import load_json, sha256
from webpier.export.soiljr import build_sdt, parse_sdr
from webpier.inputs import parse_input
from webpier.pipeline import generate, jrsnap
from webpier.pipeline.generate import GenerationError, GenerationOptions, export_bytes, planned
from webpier.pipeline.stages import STAGES
from webpier.calc.pile_ground import calculate_pile_ground

PILE = json.loads((FIXTURES / "inputs" / "pile.json").read_text(encoding="utf-8"))
ITEMS = ("detailing", "ground_model", "reactions")
POST = ["杭基礎.sdc", "杭基礎.sdr", "杭基礎.sdt"]
LIQUEFACTION = ["杭基礎(液状化時用).sdc", "杭基礎(液状化時用).sdr"]


def write(directory: Path, **changes) -> Path:
    """pile.json as a generation's input, with each 'a/b/0/c' path replaced by its value."""
    data = deepcopy(PILE)
    for path, value in changes.items():
        node = data
        *parents, key = path.split("/")
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[int(key) if key.isdigit() else key] = value
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "input.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setattr(generate, "dependency_hashes", lambda: {Path("C:/webpier/x.py"): "1" * 64})


def options(root: Path, **changes) -> GenerationOptions:
    return GenerationOptions(write(root / "pre", **changes), root / "output", root / "post", export_dir=root / "export")


def text(pdf: bytes) -> str:
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        return "".join(page.get_text() for page in document)


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    root = tmp_path_factory.mktemp("pile")
    opts = options(root)
    return root, opts, generate.generate(opts)


def test_a_pile_foundation_makes_the_reports_of_its_stages(made):
    root, opts, generation = made
    assert generation.stages == ("0400", "0500", "0600")
    output, post = tree(root / "output"), tree(root / "post")
    assert sorted(output) == ["0400_照査の前提.json", "0400_照査の前提.pdf", "0500_杭基礎.json", "0500_杭基礎.pdf",
                              "0600_上部工反力.json", "0600_上部工反力.pdf"]
    assert sorted(name for name in post if "provenance" not in name and name != "配筋図.dxf") == POST
    assert sorted(name for name in tree(root / "export")) == ["0400_照査の前提.xlsx", "0600_上部工反力.xlsx"]  # none for 0500
    assert "0500_直接基礎.pdf" not in output


def test_the_report_is_soil_jrs_as_the_runner_printed_it(made):
    root, opts, generation = made
    sdt = (root / "post" / "杭基礎.sdt").read_bytes()
    digest = hashlib.sha256(sdt).hexdigest()[:16]
    report = (root / "output" / "0500_杭基礎.pdf").read_bytes()
    assert f"FAKE SOIL-JR REPORT {digest}" in text(report) and f"FAKE SOIL-JR REPORT 2 {digest}" in text(report)
    with pymupdf.open(stream=report, filetype="pdf") as document:
        assert document.page_count == 2  # nothing of WebPier's is added


def test_the_sdt_is_what_the_writer_gives_and_what_was_calculated(made):
    root, opts, generation = made
    pier = parse_input(load_json((root / "pre" / "input.json").read_bytes()))
    sdt = (root / "post" / "杭基礎.sdt").read_bytes()
    assert sdt == build_sdt(calculate_pile_ground(pier), title="WebPier 杭基礎", description="場所打ち杭")
    assert sdt == export_bytes(pier, "0500", "sdt")
    sdr = parse_sdr((root / "post" / "杭基礎.sdr").read_bytes())
    assert sdr.title == f"FAKE SOIL-JR {hashlib.sha256(sdt).hexdigest()[:16]}"  # what the runner calculated from
    assert (root / "post" / "杭基礎.sdc").read_bytes() == f"FAKE SDC {hashlib.sha256(sdt).hexdigest()}".encode()


def test_the_result_holds_what_was_derived_the_sdt_and_the_limits(made):
    root, opts, generation = made
    document = load_json((root / "output" / "0500_杭基礎.json").read_bytes())
    result = document["result"]
    assert set(result) == {"ground", "sdt_sha256", "sdr", "liquefied_sdr"} and result["liquefied_sdr"] is None
    assert result["sdt_sha256"] == sha256((root / "post" / "杭基礎.sdt").read_bytes())
    assert [row["thickness"] for row in result["ground"]["layers"]] == [2.6, 5.0, 4.0, 6.4, 1.0]
    assert result["sdr"]["version"] == "Ver.5.2.3" and len(result["sdr"]["tables"]) == 16
    called = document["soil_jr"]
    assert called["engine"] == "jrsnap" and called["engineering_status"] == "not_evaluated"
    assert called["sdt"] == {"file": "杭基礎.sdt", "sha256": result["sdt_sha256"]}
    assert sorted(called["files"]) == ["sdc", "sdr"]
    assert called["files"]["sdr"] == {"file": "杭基礎.sdr", "sha256": sha256((root / "post" / "杭基礎.sdr").read_bytes())}
    assert called["report"] == {"file": "0500.pdf", "sha256": sha256((root / "output" / "0500_杭基礎.pdf").read_bytes())}
    assert called["runner_summary"]["input"]["sha256"] == result["sdt_sha256"]
    assert called["messages"] == [{"level": "warning", "code": "SOIL_WARNING", "text": "FAKE SOIL WARNING"}]


def test_every_file_of_the_stage_has_a_sidecar_that_names_the_calculation(made):
    root, opts, generation = made
    sdt = sha256((root / "post" / "杭基礎.sdt").read_bytes())
    for name in POST:
        sidecar = load_json((root / "post" / f"{name}.provenance.json").read_bytes())
        assert sidecar["stage"] == "0500" and sidecar["file"] == name
        assert sidecar["sha256"] == sha256((root / "post" / name).read_bytes())
        assert sidecar["soil_jr"]["sdt"]["sha256"] == sdt and sidecar["soil_jr"]["engineering_status"] == "not_evaluated"
        assert sidecar["soil_jr"]["report"] == "0500.pdf"
    export = load_json((root / "post" / "杭基礎.sdt.provenance.json").read_bytes())
    assert export["export"] == "sdt" and export["metadata"]["target"] == "SOIL-JR"
    assert load_json((root / "post" / "杭基礎.sdr.provenance.json").read_bytes())["export"] == "sdr"
    listed = {item["role"] for item in export["artifacts"]}
    assert {"0500.sdt", "0500.sdr", "0500.sdc", "0500.pdf", "0500.json"} <= listed


def test_the_published_files_are_the_planned_ones(made):
    root, opts, generation = made
    pier = parse_input(load_json((root / "pre" / "input.json").read_bytes()))
    assert planned(opts, generation.stages, pier=pier) == generation.artifacts
    # without the input the files that only some inputs have are not planned; the rest are the same
    assert [artifact.role for artifact in planned(opts, generation.stages, registry=STAGES.for_foundation("場所打ち杭"))] == [
        artifact.role for artifact in generation.artifacts]


def test_a_steel_soil_cement_pile_foundation_is_calculated_the_same_way(tmp_path):
    opts = options(tmp_path, **{"下部構造/基礎形式": "鋼管ソイルセメント杭"})
    generation = generate.generate(opts)
    assert sorted(name for name in tree(tmp_path / "post") if name.startswith("杭基礎") and "provenance" not in name) == POST
    sdt = (tmp_path / "post" / "杭基礎.sdt").read_bytes().decode("cp932").split("\r\n")
    assert sdt[sdt.index("●杭条件●") + 1].endswith(",5,7,0,0,0,0,0")
    assert load_json((tmp_path / "output" / "0500_杭基礎.json").read_bytes())["result"]["ground"]["foundation"] == "鋼管ソイルセメント杭"
    assert generation.stages == ("0400", "0500", "0600")


def liquefying(layers=None):
    layers = deepcopy(PILE["地盤データ"]["層"])
    layers[2]["De"] = 0.5
    return {"地盤データ/層": layers}


def test_the_files_for_the_liquefaction_are_published_when_the_input_considers_it(tmp_path):
    opts = options(tmp_path, **liquefying())
    generation = generate.generate(opts)
    assert sorted(name for name in tree(tmp_path / "post") if name.startswith("杭基礎") and "provenance" not in name) == sorted(
        [*POST, *LIQUEFACTION])
    document = load_json((tmp_path / "output" / "0500_杭基礎.json").read_bytes())
    assert document["result"]["ground"]["liquefaction"] is True and document["result"]["liquefied_sdr"]["version"] == "Ver.5.2.3"
    assert sorted(document["soil_jr"]["files"]) == ["liquefiedsdc", "liquefiedsdr", "sdc", "sdr"]
    assert document["soil_jr"]["runner_summary"]["liquefaction"] is True
    pier = parse_input(load_json(opts.input_path.read_bytes()))
    assert planned(opts, generation.stages, pier=pier) == generation.artifacts
    assert len(planned(opts, generation.stages, pier=pier)) == len(planned(opts, generation.stages, pier=parse_input(PILE))) + 4
    assert (tmp_path / "post" / "杭基礎(液状化時用).sdr.provenance.json").is_file()


@pytest.mark.parametrize("mode,message", [
    ("fail", "UNKNOWN_DIALOG"), ("input", "SDT_REJECTED"), ("exit", "JSON ではありません"), ("text", "JSON ではありません"),
    ("protocol", "やり取りの版が違います"), ("summary", "summary・messages"), ("sha", "SHA256・バイト数と一致しません"),
    ("kind", "SOIL-JR の連携ファイルと帳票ではありません"), ("missing", "一覧と一致しません"), ("extra", "一覧と一致しません"),
    ("name", "渡した .sdt と違います"), ("digest", "渡した .sdt と違います"), ("liquefaction", "渡した .sdt と違います"),
    ("pdf", "にページがありません"), ("broken", "を読めません"),
])
def test_a_runner_that_fails_or_returns_what_was_not_asked_publishes_nothing(tmp_path, monkeypatch, mode, message):
    monkeypatch.setenv("FAKE_JRSNAP_SOIL", mode)
    opts = options(tmp_path)
    with pytest.raises(GenerationError, match=message):
        generate.generate(opts)
    assert not (tmp_path / "output").exists() and not (tmp_path / "post").exists()


def test_a_sdr_of_another_pile_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_JRSNAP_SOIL", "header")
    with pytest.raises(GenerationError, match="SOIL-JR の .sdr で0500の結果を仕上げられません: 杭基礎.sdr の杭種（9.0）"):
        generate.generate(options(tmp_path))
    assert not (tmp_path / "output").exists()


def test_a_missing_runner_stops_the_generation_before_anything_is_calculated(tmp_path, monkeypatch):
    monkeypatch.delenv(jrsnap.RUNNER_KEY)
    monkeypatch.setattr(jrsnap, "ENV_FILE", tmp_path / "no.env")
    with pytest.raises(GenerationError, match="JRSNAP の runner が設定されていません"):
        generate.generate(options(tmp_path))
    assert not (tmp_path / "output").exists()


def test_validating_a_pile_input_needs_no_runner(tmp_path, monkeypatch):
    monkeypatch.delenv(jrsnap.RUNNER_KEY)
    monkeypatch.setattr(jrsnap, "ENV_FILE", tmp_path / "no.env")
    assert generate.validate(options(tmp_path)) == ("0400", "0500", "0600")


def test_the_stage_alone_needs_the_runner_and_the_items_without_it_do_not(tmp_path, monkeypatch):
    monkeypatch.delenv(jrsnap.RUNNER_KEY)
    monkeypatch.setattr(jrsnap, "ENV_FILE", tmp_path / "no.env")
    data = deepcopy(PILE)
    data["outputs"] = {key: key in ("detailing", "reactions") for key in data["outputs"]}
    path = tmp_path / "pre" / "input.json"
    path.parent.mkdir()
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    generation = generate.generate(GenerationOptions(path, tmp_path / "output", tmp_path / "post"))
    assert generation.stages == ("0400", "0600")
    assert not any(name.startswith("杭基礎") for name in tree(tmp_path / "post"))


def test_a_direct_foundation_is_unchanged_by_the_pile_stage(tmp_path):
    from pipeline_support import copy_input
    source = copy_input(tmp_path / "pre", "ground_model")
    generation = generate.generate(GenerationOptions(source, tmp_path / "output", tmp_path / "post"))
    assert sorted(tree(tmp_path / "output")) == ["0500_直接基礎.json", "0500_直接基礎.pdf"]
    assert not tree(tmp_path / "post") and generation.stages == ("0500",)
    pier = parse_input(load_json(source.read_bytes()))
    assert planned(GenerationOptions(source, tmp_path / "output", tmp_path / "post"), ("0500",), pier=pier) == planned(
        GenerationOptions(source, tmp_path / "output", tmp_path / "post"), ("0500",))
