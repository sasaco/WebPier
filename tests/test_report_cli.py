from __future__ import annotations

from copy import deepcopy
import json
import hashlib
import os
from pathlib import Path

import pytest
from pypdf import PdfReader

from src.cli import main
from test_pier_model_samples import assert_frame_matches_expected

PROJECT = Path(__file__).resolve().parents[1]
# Fixed historical input from fa27cca^, independent of the working input.
BASELINE = PROJECT / "tests" / "fixtures" / "baseline_input.json"
STEM = "0500_直接基礎"


def material_complete_data(source, *, export_compatible=False):
    """Complete old fixtures for the current all-stage material contract.

    The source fixture stays byte-identical; explicit strengths belong only to
    the test's input copy, which is used for every selected calculation stage.
    """
    data = json.loads(source.read_text(encoding="utf-8"))
    reinforcement = data.setdefault("鉄筋", {})
    for part in ("梁", "柱", "フーチング"):
        reinforcement.setdefault(part, {})["concrete_strength_mpa"] = 27
    if export_compatible:
        # An explicit integration-test input, not a replacement numeric oracle:
        # old B6=1.75 gives wind qH=2.625, which the solver changes to 2.63.
        # B6=1.76 gives solver-compatible two-decimal qH=2.64/5.28. Keep every other
        # dimension, including parapet eccentricity and footing asymmetry.
        assert data["下部構造"]["寸法"]["側面"]["B6"] == 1.75
        data["下部構造"]["寸法"]["側面"]["B6"] = 1.76
        # The original sample has no L2. A zero/nonzero single-track pair
        # cannot retain both native envelope candidates, so explicitly add
        # the second track for this publication test, retaining L1/positions.
        for side, support in (("起点側", "B支点"), ("終点側", "C支点")):
            for bearing in data["上部工反力"][side][support]["支承"][:2]:
                assert bearing["列車分担"]["L2"] is None
                bearing["列車分担"]["L2"] = 0.5
        data["出典"]["公開統合試験条件"] = (
            "B6=1.76m: 柱風2.64/5.28kN/m; 両側d1,d2のL2=0.5; 元数値fixtureは変更しない")
    return data


def test_cli_generates_complete_native_report_and_calculation_json(tmp_path):
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(material_complete_data(BASELINE), ensure_ascii=False), encoding="utf-8")
    assert main(["--stage", "0500", "--input", str(input_path), "--output-dir", str(tmp_path)]) == 0
    reader = PdfReader(tmp_path / f"{STEM}.pdf")
    assert len(reader.pages) > 0
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "地盤" in text
    assert "95,011" in text or "95011" in text
    assert "29,872,885" in text or "29872885" in text
    assert all(title in text for title in ("地盤のモデル化", "せん断地盤ばね定数", "回転地盤ばね定数"))
    result = json.loads((tmp_path / f"{STEM}.json").read_text(encoding="utf-8"))
    assert result["long_term"]["Kv"] == 3657924
    assert len(result["provenance"]["input_sha256"]) == 64


def test_existing_outputs_require_explicit_overwrite(tmp_path):
    pdf = tmp_path / f"{STEM}.pdf"
    pdf.write_bytes(b"existing")
    assert main(["--output-dir", str(tmp_path)]) == 2
    assert pdf.read_bytes() == b"existing"
    assert main(["--output-dir", str(tmp_path), "--overwrite"]) == 0
    assert len(PdfReader(pdf).pages) > 0
    assert "回転地盤ばね定数" in "".join(page.extract_text() for page in PdfReader(pdf).pages)


def test_invalid_input_produces_no_output(tmp_path):
    bad = tmp_path / "invalid.json"
    bad.write_text('{"schema_version":1}', encoding="utf-8")
    output = tmp_path / "output"
    assert main(["--input", str(bad), "--output-dir", str(output)]) == 2
    assert not output.exists()


def test_cli_accepts_json_with_bom_and_changed_input(tmp_path):
    data = material_complete_data(BASELINE)
    data["地盤データ"]["層"][1]["土質区分"] = "安山岩"
    path = tmp_path / "custom.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8-sig")
    output = tmp_path / "custom-output"
    assert main(["--stage", "0500", "--input", str(path), "--output-dir", str(output)]) == 0
    result = json.loads((output / f"{STEM}.json").read_text(encoding="utf-8"))
    assert result["long_term"]["Kv"] == 1713058
    text = "\n".join(page.extract_text() for page in PdfReader(output / f"{STEM}.pdf").pages)
    assert "安山岩" in text
    assert "13,989,812" in text or "13989812" in text


def test_failed_second_publication_restores_both_originals(tmp_path, monkeypatch):
    pdf, json_path = tmp_path / f"{STEM}.pdf", tmp_path / f"{STEM}.json"
    pdf.write_bytes(b"old pdf")
    json_path.write_bytes(b"old json")
    actual_replace = os.replace

    def locked_second_output(source, destination):
        if Path(source).name == json_path.name and Path(destination) == json_path:
            raise PermissionError("locked JSON")
        return actual_replace(source, destination)

    monkeypatch.setattr(os, "replace", locked_second_output)
    assert main(["--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert pdf.read_bytes() == b"old pdf"
    assert json_path.read_bytes() == b"old json"
    assert not list(tmp_path.glob(".pier-design-*"))


def test_locked_existing_json_does_not_replace_pdf(tmp_path, monkeypatch):
    pdf, json_path = tmp_path / f"{STEM}.pdf", tmp_path / f"{STEM}.json"
    pdf.write_bytes(b"old pdf")
    json_path.write_bytes(b"old json")
    actual_replace = os.replace

    def locked_json(source, destination):
        if Path(source) == json_path:
            raise PermissionError("locked JSON")
        return actual_replace(source, destination)

    monkeypatch.setattr(os, "replace", locked_json)
    assert main(["--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert pdf.read_bytes() == b"old pdf"
    assert json_path.read_bytes() == b"old json"


@pytest.mark.parametrize("suffix", ["pdf", "json"])
def test_output_directory_is_never_removed_by_overwrite(tmp_path, suffix):
    collision = tmp_path / f"{STEM}.{suffix}"
    collision.mkdir()
    keep = collision / "user-file.txt"
    keep.write_bytes(b"keep me")
    other_suffix = "pdf" if suffix == "json" else "json"
    other = tmp_path / f"{STEM}.{other_suffix}"
    other.write_bytes(b"old output")
    assert main(["--output-dir", str(tmp_path), "--overwrite"]) == 2
    assert keep.read_bytes() == b"keep me"
    assert other.read_bytes() == b"old output"


@pytest.mark.parametrize("sample", [None, "parapet-asymmetric.json", "asymmetric-footing.json"],
                         ids=["default", "parapet", "asymmetric_footing"])
def test_complete_samples_publish_identical_standalone_and_all_results_with_one_input_sha(tmp_path, sample):
    source = PROJECT / "tests/fixtures/pier_models" / sample if sample else BASELINE
    original = source.read_bytes()
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(material_complete_data(source, export_compatible=True), ensure_ascii=False), encoding="utf-8")
    complete_input = input_path.read_bytes()
    expected_sha = hashlib.sha256(complete_input).hexdigest()
    stems = {"0500": "0500_直接基礎", "0600": "0600_上部工反力",
             "0610": "0610_線路方向荷重", "0620": "0620_直角方向荷重", "0710": "0710_線路方向荷重", "0720": "0720_線路直角方向荷重"}
    all_output = tmp_path / "all"
    assert main(["--stage", "all", "--input", str(input_path), "--output-dir", str(all_output)]) == 0
    assert {path.name for path in all_output.iterdir()} == {
        f"{stem}.{suffix}" for stem in stems.values() for suffix in ("pdf", "json")
    } | {"post"}
    assert {path.name for path in (all_output / "post").iterdir()} == {
        "frameWebForJS.json", "frameWebForJS.provenance.json",
        "線路直角方向.json", "線路直角方向.provenance.json",
    }
    expectations = json.loads((PROJECT / "tests/fixtures/pier_models/expectations.json").read_text(encoding="utf-8"))
    case = "parapet_asymmetric" if sample == "parapet-asymmetric.json" else "asymmetric_footing" if sample else "default"
    for stage, stem in stems.items():
        separate = tmp_path / stage
        assert main(["--stage", stage, "--input", str(input_path), "--output-dir", str(separate)]) == 0
        assert {path.name for path in separate.iterdir()} == (
            {f"{stem}.pdf", f"{stem}.json"} | ({"post"} if stage in ("0610", "0620") else set()))
        together = json.loads((all_output / f"{stem}.json").read_text(encoding="utf-8"))
        alone = json.loads((separate / f"{stem}.json").read_text(encoding="utf-8"))
        assert alone == together
        assert alone["provenance"]["input_sha256"] == expected_sha
        assert len(PdfReader(all_output / f"{stem}.pdf").pages) > 0
        assert len(PdfReader(separate / f"{stem}.pdf").pages) > 0
        if stage in ("0610", "0620"):
            direction = "b" if stage == "0610" else "w"
            expected = deepcopy(expectations["cases"][case]["directions"][direction])
            # Independent literal rectangular-section expectations for this
            # explicit B6=1.76, W6=6.5 input: A=B6*W6; Iz=width*depth^3/12.
            # Original node/role/alias/member/anchor and parapet expectations
            # remain unchanged. Original B6=1.75 body/weight oracles remain
            # exercised in test_pier_model_samples.py.
            expected["sections"]["body"].update({
                "b": {"width": 6.5, "depth": 1.76, "area": 11.44, "inertia": 2.95305},
                "w": {"width": 1.76, "depth": 6.5, "area": 11.44, "inertia": 40.27833},
            }[direction])
            assert {path.name for path in (separate / "post").iterdir()} == (
                {"frameWebForJS.json", "frameWebForJS.provenance.json"} if stage == "0610"
                else {"線路直角方向.json", "線路直角方向.provenance.json"})
            for member in expected["members"]:
                member["material_ref"] = (None if member["behavior"] == "rigid" else
                                          "beam" if member["region"] in ("h2", "h3") else "column")
            assert_frame_matches_expected(alone["frame"], expected)
    assert source.read_bytes() == original
    assert input_path.read_bytes() == complete_input
