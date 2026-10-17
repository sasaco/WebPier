"""Transverse literal oracle and atomic acceptance of every held direction."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import test_jrsnap_acceptance as longitudinal
from src.jrsnap_readback import ReadbackError, verify_readback

acceptance = longitudinal.acceptance
PROJECT = Path(__file__).resolve().parents[1]
ORACLE = PROJECT / "tests/fixtures/jrsnap_v52_transverse_expected.json"


def oracle() -> dict[str, Any]:
    return json.loads(ORACLE.read_text(encoding="utf-8"))


def reference_bytes() -> bytes:
    independent = oracle()
    records = {**independent["expected_records"], **independent["prefix_fields"]}
    lines = []
    for key, values in records.items():
        fields = [str(value) for value in values]
        if key in independent["text_suffix_records"]:
            fields.append("独立直角照合")
        lines.append(key + "=" + ",".join(fields))
    return ("\r\n".join(lines) + "\r\n").encode("cp932")


def test_transverse_oracle_covers_all_nine_cases_and_the_combination() -> None:
    inspected = verify_readback(reference_bytes(), oracle())
    assert inspected["checked_records"] == 200
    assert len(inspected["resultants_about_footing_bottom"]) == 9
    assert inspected["resultants_about_footing_bottom"][7] == pytest.approx([9090, 0, 120732])
    assert inspected["resultants_about_footing_bottom"][8] == pytest.approx([144, 0, 2253.6])
    assert inspected["combination_resultants_about_footing_bottom"]["1"] == pytest.approx(
        [13301.5425, 16828.938170898437, 144532.08313333333])


def test_real_transverse_export_from_immutable_input_matches_independent_oracle() -> None:
    from src.cli import _calculate_stages
    from src.jrsnap_export import build_transverse_ndu_model
    from src.jrsnap_ndu import serialize_ndu

    digest = oracle()["input_sha256"]
    data = (PROJECT / "pre/snapshots" / f"ndu-origin-{digest}.json").read_bytes()
    assert acceptance.sha256(data) == digest
    raw = json.loads(data)
    computed = _calculate_stages(raw, ("0720",), f"ndu-origin-{digest}.json", digest)
    model = build_transverse_ndu_model(raw, computed["0500"], computed["0720"], input_sha256=digest)
    inspected = verify_readback(serialize_ndu(model), oracle())
    assert inspected["checked_records"] == 200
    assert len(inspected["resultants_about_footing_bottom"]) == 9


@pytest.mark.parametrize("key,index,value", [
    ("DataInfo", 2, "300"), ("DataInfo", 3, "2"), ("DataInfo", 5, "200"),
    ("DataInfo", 18, "-0.35"), ("JointXY1", 1, "-7.6"),
    ("ElementInfo5", 0, "1"), ("SectInfo1", 4, "4500"),
    ("SectInfo1", 9, "7600"), ("SectRein1-1", 1, "32"),
    ("SectRein1-1", 2, "2"), ("SectSher1", 2, "10"),
    ("FootInfo1", 3, "7"), ("FootInfo1", 4, "9"),
    ("JLoadInfo7", 6, "1028.62"), ("JLoadInfo8", 6, "-1028.62"),
    ("JLoadInfo9", 2, "1"), ("JLoadInfo9", 4, "9080"),
    ("JLoadInfo10", 4, "43.2"), ("JLoadInfo10", 6, "231.12"),
    ("MLoadInfo8", 2, "4"), ("MLoadInfo6", 7, "595.35"),
    ("ConbAlpf1", 5, "1"), ("SNAPConb1", 9, "1"),
])
def test_wrong_transverse_geometry_direction_and_case_values_fail(key: str, index: int, value: str) -> None:
    changed = longitudinal.replace_field(reference_bytes(), key, index, value)
    with pytest.raises(ReadbackError):
        verify_readback(changed, oracle())


def test_resultant_detects_double_train_kh_even_with_matching_changed_record() -> None:
    independent = deepcopy(oracle())
    independent["expected_records"]["JLoadInfo10"][4] = 43.2
    data = longitudinal.replace_field(reference_bytes(), "JLoadInfo10", 4, "43.2")
    with pytest.raises(ReadbackError, match="EQL resultant"):
        verify_readback(data, independent)


def test_combination_resultant_detects_loading_both_tracks() -> None:
    independent = deepcopy(oracle())
    independent["expected_records"]["ConbAlpf1"][5] = 1
    data = longitudinal.replace_field(reference_bytes(), "ConbAlpf1", 5, "1")
    with pytest.raises(ReadbackError, match="Combination 1 resultant"):
        verify_readback(data, independent)


class DirectionalCandidate(longitudinal.FakeCandidate):
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
        super().__init__(root, monkeypatch)
        self.options.stage = stage
        original_path, original_metadata = self.ndu_path, self.metadata
        self.ndu_paths = {"0710": original_path} if stage == "all" else {}
        self.metadata_by_stage = {"0710": original_metadata} if stage == "all" else {}
        if stage == "0720":
            self.read_paths = {}
        self.computed["0720"] = {"input_sha256": self.input_sha256, "case_count": 9}
        transverse = original_path.with_name("線路直角方向.ndu")
        for name, data in (("0720.pdf", b"%PDF transverse"), ("0720.json", b'{"stage":"0720"}'),
                           (transverse.name, reference_bytes()),
                           ("線路直角方向.ndu.provenance.json", b'{"direction":"transverse"}')):
            final, staged = transverse.parent / name, root / "staging" / name
            final.write_bytes(b"old transverse " + name.encode("utf-8"))
            staged.write_bytes(data)
            self.read_paths[final] = staged
        self.ndu_paths["0720"] = transverse
        self.metadata_by_stage["0720"] = {
            "profile_id": oracle()["profile_id"], "target_version": "5.2-L03",
            "roles": {"cap_top": 2, "superstructure_b": 1, "superstructure_c": 1,
                      "column_base_micro_top": 5, "footing_top": 6, "footing_centroid": 7, "footing_bottom": 8},
            "settings": {"analysis": {"control_role": "superstructure_b"}},
        }
        if stage == "0720":
            self.ndu_path, self.metadata = transverse, self.metadata_by_stage["0720"]
        self.artifact_hashes = {path: acceptance.sha256(data.read_bytes()) for path, data in self.read_paths.items()}
        self.old = {path: path.read_bytes() for path in self.read_paths}
        self.publish_count = 0

    def publish(self) -> None:
        self.publish_count += 1
        super().publish()


def make_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str = "all") -> Any:
    candidate = DirectionalCandidate(tmp_path, monkeypatch, stage)
    paths = {}
    for selected, value in (("0710", longitudinal.oracle()), ("0720", oracle())):
        if selected not in candidate.ndu_paths:
            continue
        path = tmp_path / f"oracle-{selected}.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        paths[selected] = path
    identity = {"path": "fake-app.exe", "sha256": "a" * 64, "file_version": "5.2.3.0",
                "product_version": "5.2.3.0", "assembly_version": "5.2.3.1"}
    helper = tmp_path / "helper.ps1"
    helper.write_text("# fixture helper", encoding="utf-8")
    calls = []

    def runner(data: bytes) -> dict[str, Any]:
        calls.append(data)
        return {"first": data, "second": data, "application": identity,
                "helper_sources": {str(helper): acceptance.sha256(helper.read_bytes())}}

    return SimpleNamespace(candidate=candidate, oracles=paths, runner=runner, calls=calls,
                           identity=identity, receipt=tmp_path / "receipt.json")


def run_accept(harness: Any, **overrides: Any) -> Path:
    options = {"oracle_paths": harness.oracles, "receipt_path": harness.receipt,
               "prepare": harness.candidate.prepare, "app_runner": harness.runner,
               "identity_reader": lambda: harness.identity}
    options.update(overrides)
    return acceptance.accept_generation(harness.candidate.options, **options)


@pytest.mark.parametrize("stage,version,count", [("0720", 1, 1), ("all", 2, 2)])
def test_acceptance_verifies_every_held_direction_then_publishes_once(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, version: int, count: int) -> None:
    harness = make_harness(tmp_path, monkeypatch, stage)
    path = run_accept(harness)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert receipt["status"] == "complete" and receipt["schema_version"] == version
    assert len(harness.calls) == count and harness.candidate.publish_count == 1
    assert set(receipt["binding"]["canonical_snapshot_sha256"]) == {"0500", *harness.oracles}
    if stage == "all":
        assert set(receipt["binding"]["directions"]) == {"0710", "0720"}
    for final, staged in harness.candidate.read_paths.items():
        assert final.read_bytes() == staged.read_bytes()


@pytest.mark.parametrize("problem", ["missing_oracle", "wrong_input", "wrong_control", "missing_candidate"])
def test_incomplete_direction_binding_blocks_before_app_and_publication(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, problem: str) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    if problem == "missing_oracle":
        del harness.oracles["0720"]
    elif problem == "wrong_input":
        value = oracle()
        value["input_sha256"] = "0" * 64
        harness.oracles["0720"].write_text(json.dumps(value), encoding="utf-8")
    elif problem == "wrong_control":
        harness.candidate.metadata_by_stage["0720"]["settings"]["analysis"]["control_role"] = "cap_top"
    else:
        del harness.candidate.ndu_paths["0720"]
    with pytest.raises(acceptance.AcceptanceError):
        run_accept(harness)
    assert not harness.calls and not harness.candidate.published


@pytest.mark.parametrize("problem", ["failure", "meaning", "identity", "metadata", "calculation",
                                    "first_candidate", "helper_source"])
def test_second_direction_failure_preserves_all_formal_bytes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, problem: str) -> None:
    harness = make_harness(tmp_path, monkeypatch)

    def runner(data: bytes) -> dict[str, Any]:
        response = harness.runner(data)
        if len(harness.calls) != 2:
            return response
        if problem == "failure":
            raise acceptance.AcceptanceError("second app timeout")
        if problem == "meaning":
            response["first"] = response["second"] = longitudinal.replace_field(data, "JLoadInfo10", 4, "43.2")
        elif problem == "identity":
            response["application"] = {**harness.identity, "sha256": "b" * 64}
        elif problem == "metadata":
            harness.candidate.metadata_by_stage["0710"]["settings"]["version"] = 99
        elif problem == "calculation":
            harness.candidate.computed["0720"]["case_count"] = 8
        elif problem == "first_candidate":
            harness.candidate.read_paths[harness.candidate.ndu_paths["0710"]].write_bytes(b"changed")
        elif problem == "helper_source":
            helper = Path(next(iter(response["helper_sources"])))
            helper.write_bytes(helper.read_bytes() + b"changed")
            response["helper_sources"][str(helper)] = acceptance.sha256(helper.read_bytes())
        return response

    with pytest.raises((acceptance.AcceptanceError, ReadbackError)):
        run_accept(harness, app_runner=runner)
    assert not harness.candidate.published
    assert {path: path.read_bytes() for path in harness.candidate.old} == harness.candidate.old


def test_all_direction_receipt_recovery_rechecks_both_evidence_sets(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    write = acceptance._write_receipt

    def fail_final(path: Path, document: dict[str, Any], *, create: bool) -> None:
        if not create:
            raise OSError("receipt update failed")
        write(path, document, create=create)

    monkeypatch.setattr(acceptance, "_write_receipt", fail_final)
    with pytest.raises(acceptance.AcceptanceError, match="Published; acceptance receipt is incomplete"):
        run_accept(harness)
    assert harness.candidate.publish_count == 1
    monkeypatch.setattr(acceptance, "_write_receipt", write)
    acceptance.finalize_receipt(harness.receipt, identity_reader=lambda: harness.identity)
    receipt = json.loads(harness.receipt.read_text(encoding="utf-8"))
    assert receipt["status"] == "complete"
    assert harness.candidate.publish_count == 1 and len(harness.calls) == 2
    evidence = Path(next(iter(receipt["binding"]["directions"]["0720"]["evidence_hashes"])))
    evidence.write_bytes(evidence.read_bytes() + b"changed")
    with pytest.raises(acceptance.AcceptanceError, match="Readback evidence changed"):
        acceptance.finalize_receipt(harness.receipt, identity_reader=lambda: harness.identity)


@pytest.mark.parametrize("removed", ["direction", "calculation"])
def test_all_direction_recovery_rejects_missing_direction_binding(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, removed: str) -> None:
    harness = make_harness(tmp_path, monkeypatch)
    run_accept(harness)
    receipt = json.loads(harness.receipt.read_text(encoding="utf-8"))
    key = "directions" if removed == "direction" else "canonical_snapshot_sha256"
    del receipt["binding"][key]["0720"]
    receipt["binding_sha256"] = acceptance.canonical_sha256(receipt["binding"])
    harness.receipt.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(acceptance.AcceptanceError, match="Both directional"):
        acceptance.finalize_receipt(harness.receipt, identity_reader=lambda: harness.identity)

