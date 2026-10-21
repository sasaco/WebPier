"""The 照査の前提 (decision 73): the 出力項目 detailing alone makes 0400 from the input, with its report, its result JSON
and its grid Excel workbook, its 配筋図 (the DXF in post/ with its sidecar), the judgement of every check and the
engineering status; the report, the workbook and the DXF are the same bytes from a second generation, and choosing it
with the other items changes none of their reports."""

from __future__ import annotations

import json

from pipeline_support import copy_input, tree
from webpier.core.integrity import load_json, sha256
from webpier.pipeline.generate import GenerationOptions, generate

STEM = "0400_照査の前提"


def make(root, *items):
    source = copy_input(root / "pre", *items)
    return source, generate(GenerationOptions(source, root / "output", root / "post"))


def test_the_detailing_alone_from_the_input(tmp_path):
    source, generation = make(tmp_path / "a", "detailing")
    assert generation.stages == ("0400",)
    assert sorted(artifact.role for artifact in generation.artifacts) == [
        "0400.dxf", "0400.dxf.provenance", "0400.json", "0400.pdf", "0400.xlsx"]
    assert sorted(tree(tmp_path / "a" / "output")) == [f"{STEM}.json", f"{STEM}.pdf"]
    assert sorted(tree(tmp_path / "a" / "export")) == [f"{STEM}.xlsx"]
    assert sorted(tree(tmp_path / "a" / "post")) == ["配筋図.dxf", "配筋図.dxf.provenance.json"]
    sidecar = load_json((tmp_path / "a" / "post" / "配筋図.dxf.provenance.json").read_bytes())
    assert (sidecar["stage"], sidecar["export"], sidecar["sha256"]) == (
        "0400", "dxf", sha256((tmp_path / "a" / "post" / "配筋図.dxf").read_bytes()))
    document = load_json((tmp_path / "a" / "output" / f"{STEM}.json").read_bytes())
    assert document["stage"] == "0400" and document["input"]["sha256"] == sha256(source.read_bytes())
    result = document["result"]
    # current.json: the beam's upper layers are 32 mm apart, less than 4/3 × 25 = 33.3 (calc tests)
    assert result["engineering_status"] == "not_ok"
    assert result["beam"]["spacings"][0]["ok"] is False and result["column"]["amount"]["minimum_ok"] is True
    assert [direction["lateral"]["ok"] for direction in result["column"]["directions"]] == [True, True]
    _, again = make(tmp_path / "b", "detailing")
    for folder, name in (("output", f"{STEM}.pdf"), ("export", f"{STEM}.xlsx"), ("post", "配筋図.dxf")):
        assert (tmp_path / "b" / folder / name).read_bytes() == (tmp_path / "a" / folder / name).read_bytes(), name
    assert again.stages == ("0400",)


def test_the_detailing_changes_no_other_report(tmp_path):
    _, alone = make(tmp_path / "a", "ground_model")
    _, both = make(tmp_path / "b", "detailing", "ground_model")
    assert both.stages == ("0400", "0500")
    first, second = tree(tmp_path / "a" / "output"), tree(tmp_path / "b" / "output")
    assert first["0500_直接基礎.pdf"] == second["0500_直接基礎.pdf"]
    strip = (lambda content: {key: value for key, value in json.loads(content).items() if key != "input"})
    assert strip(first["0500_直接基礎.json"]) == strip(second["0500_直接基礎.json"])
