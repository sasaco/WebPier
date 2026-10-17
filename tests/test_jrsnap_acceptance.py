"""Independent native inspection and acceptance/publication failure boundaries."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from src.jrsnap_readback import ReadbackError, parse_ndu, verify_readback

PROJECT = Path(__file__).resolve().parents[1]
ORACLE = PROJECT / "tests/fixtures/jrsnap_v52_longitudinal_expected.json"
SPEC = importlib.util.spec_from_file_location("accept_jrsnap_ndu", PROJECT / "scripts/accept_jrsnap_ndu.py")
assert SPEC is not None and SPEC.loader is not None
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


def oracle() -> dict[str, Any]:
    return json.loads(ORACLE.read_text(encoding="utf-8"))


def reference_bytes() -> bytes:
    """Literal oracle records only; never call the production serializer."""
    expected = oracle()
    records = {**expected["expected_records"], **expected["prefix_fields"]}
    suffixes = set(expected["text_suffix_records"])
    lines = []
    for key, values in records.items():
        fields = [str(value) for value in values]
        if key in suffixes:
            fields.append("独立照合")
        lines.append(key + "=" + ",".join(fields))
    return ("\r\n".join(lines) + "\r\n").encode("cp932")


def approved_snapshot_bytes() -> bytes:
    """Use the immutable full input named by the independent case oracle."""
    digest = oracle()["input_sha256"]
    snapshot = PROJECT / "pre/snapshots" / f"ndu-origin-{digest}.json"
    data = snapshot.read_bytes()
    assert acceptance.sha256(data) == digest
    return data


@pytest.mark.parametrize("revision", ["current", "previous"])
def test_real_export_from_immutable_input_matches_independent_literal_oracle(revision: str) -> None:
    from src.cli import _calculate_stages
    from src.jrsnap_export import build_longitudinal_ndu_model
    from src.jrsnap_ndu import serialize_ndu

    if revision == "previous":
        previous = oracle()["input_revision"]["previous_input_sha256"]
        raw_bytes = (PROJECT / "pre/snapshots" / f"ndu-origin-{previous}.json").read_bytes()
        assert acceptance.sha256(raw_bytes) == previous
    else:
        raw_bytes = approved_snapshot_bytes()
    digest = acceptance.sha256(raw_bytes)
    raw = json.loads(raw_bytes)
    computed = _calculate_stages(raw, ("0710",), f"ndu-origin-{digest}.json", digest)
    model = build_longitudinal_ndu_model(raw, computed["0500"], computed["0710"], input_sha256=digest)
    native = serialize_ndu(model)
    result = verify_readback(native, oracle())
    assert acceptance.sha256(native) == "02e2475aa4c16be3ffbc2ba94f770adb02e3df5e35bfa1e987e71857ea26ed71"
    assert result["verified"] is True
    assert result["checked_records"] == len(oracle()["expected_records"]) + len(oracle()["prefix_fields"])
    assert len(result["resultants_about_footing_bottom"]) == 8


@pytest.mark.parametrize("extension", ["json", "pdf"])
def test_receipt_collision_with_relative_real_output_never_creates_formal_files(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extension: str) -> None:
    from src.cli import GenerationOptions

    monkeypatch.chdir(tmp_path)
    input_path = tmp_path / "input.json"
    input_path.write_bytes(approved_snapshot_bytes())
    receipt_path = Path("output") / f"0710_線路方向荷重.{extension}"
    options = GenerationOptions(input_path=input_path, output_dir=Path("output"),
                                post_dir=Path("post"), stage="0710", jrsnap=True)

    def unchanged_readback(data: bytes) -> dict[str, Any]:
        return {"first": data, "second": data}

    with pytest.raises(acceptance.AcceptanceError, match="Receipt collides"):
        acceptance.accept_generation(options, oracle_path=ORACLE, receipt_path=receipt_path,
                                     app_runner=unchanged_readback)
    assert not receipt_path.exists()
    assert not receipt_path.with_suffix(".evidence").exists()
    assert not (tmp_path / "snapshots").exists()
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*") if path.is_file()} == {Path("input.json")}


def replace_field(data: bytes, key: str, index: int, value: str) -> bytes:
    rows = data.decode("cp932").splitlines()
    for line, row in enumerate(rows):
        if row.startswith(key + "="):
            values = row.split("=", 1)[1].split(",")
            values[index] = value
            rows[line] = key + "=" + ",".join(values)
            break
    else:
        raise AssertionError(key)
    return ("\r\n".join(rows) + "\r\n").encode("cp932")


def test_independent_native_oracle_checks_fields_and_integrates_all_eight_cases() -> None:
    result = verify_readback(reference_bytes(), oracle())
    assert result["verified"] is True
    assert result["checked_records"] >= 160
    assert result["checked_fields"] > 600
    assert result["resultants_about_footing_bottom"][8] == pytest.approx([-4067.5425, 0, -22575.103133333333])
    assert not result["gui_inspected"] and not result["analysis_executed"]


@pytest.mark.parametrize("key,index,value", [
    ("JointXY4", 1, "0"), ("ElementInfo4", 0, "1"),
    ("ElementInfo4", 5, "6"), ("MemberInfo4", 1, "6"),
    ("NonLinInfo1", 1, "2"), ("SectInfo1", 4, "2700"),
    ("SectConc1", 2, "26500000"), ("SectRein1-1", 2, "28"),
    ("SectSher1", 2, "6"), ("FootInfo1", 7, "3.78"),
    ("FootInfo1", 9, "11.6"), ("FootInfo1", 8, "19"),
    ("SuppotInfo1", 2, "3"), ("SuppotNum", 0, "2"),
    ("JLoadInfo9", 3, "1"), ("JLoadInfo9", 4, "-25.6"),
    ("JLoadInfo5", 5, "1701"), ("JLoadInfo4", 2, "6"),
    ("MLoadInfo8", 2, "3"), ("MLoadInfo6", 7, "297.68"),
    ("MLoadInfo6", 8, "595.35"), ("ConbAlpf1", 6, "0.2"),
    ("DataInfo", 18, "0.3"), ("JointXY1", 0, "NaN"),
])
def test_changed_geometry_material_rebar_support_and_loads_fail(key: str, index: int, value: str) -> None:
    with pytest.raises(ReadbackError):
        verify_readback(replace_field(reference_bytes(), key, index, value), oracle())


def test_numeric_readback_tolerance_does_not_hide_wrong_locations_or_injection() -> None:
    data = replace_field(reference_bytes(), "JLoadInfo2", 5, "4167.45")
    data = replace_field(data, "JLoadInfo1", 4, " ")
    verify_readback(data, oracle())
    with pytest.raises(ReadbackError, match="Unexpected engineering"):
        verify_readback(data + b"JLoadInfo11=8,,7,1,0,0,0,\r\n", oracle())
    with pytest.raises(ReadbackError, match="duplicate"):
        parse_ndu(data + b"JointNum=7\r\n")
    with pytest.raises(ReadbackError, match="CRLF"):
        parse_ndu(data.replace(b"\r\n", b"\n"))


def test_foundation_check_and_old_links_are_rejected_but_zero_link_count_may_be_omitted() -> None:
    data = reference_bytes()
    verify_readback(data, oracle())
    verify_readback(data + b"SRenkeiNum=0\r\n", oracle())
    for record in (b"SRenkeiNum=1", b"SoilRenkeiFile1=old.sdc", b"NDTPath=old.ndt", b"CHOKU_KISO1=0"):
        with pytest.raises(ReadbackError):
            verify_readback(data + record + b"\r\n", oracle())


def test_resultant_oracle_detects_a_wrong_load_table_even_if_record_expectations_were_altered() -> None:
    altered = deepcopy(oracle())
    altered["expected_records"]["MLoadInfo6"][7:9] = [297.68, 595.35]
    data = replace_field(reference_bytes(), "MLoadInfo6", 7, "297.68")
    data = replace_field(data, "MLoadInfo6", 8, "595.35")
    # Same total force, but the integrated first moment is different.
    with pytest.raises(ReadbackError, match="EQ2 resultant"):
        verify_readback(data, altered)


def test_physical_length_roundoff_is_allowed_but_fractional_identifiers_are_not() -> None:
    data = replace_field(reference_bytes(), "SectInfo1", 9, "7600.000000000001")
    verify_readback(data, oracle())
    with pytest.raises(ReadbackError, match="JointXY4"):
        verify_readback(replace_field(data, "JointXY4", 2, "4.000000000001"), oracle())


class FakeCandidate:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project = root / "project"
        implementation = project / "src"
        implementation.mkdir(parents=True)
        (implementation / "jrsnap_readback.py").write_bytes((PROJECT / "src/jrsnap_readback.py").read_bytes())
        (implementation / "profile.py").write_text("profile = 'v1'\n", encoding="utf-8")
        monkeypatch.setattr(acceptance, "PROJECT", project)
        self.input_bytes = (PROJECT / "pre/input.json").read_bytes()
        self.input_sha256 = acceptance.sha256(self.input_bytes)
        self.input_path = project / "pre/input.json"
        self.input_path.parent.mkdir()
        self.input_path.write_bytes(self.input_bytes)
        self.options = SimpleNamespace(input_path=self.input_path, jrsnap=True, stage="0710")
        self.ndu_path = project / "post/線路方向.ndu"
        self.ndu_path.parent.mkdir()
        staging = root / "staging"
        staging.mkdir()
        self.read_paths = {}
        for name, data in (("0710.pdf", b"%PDF candidate"), ("0710.json", b'{"stage":"0710"}'),
                           ("線路方向.ndu", reference_bytes()), ("線路方向.ndu.provenance.json", b'{"generation":"new"}')):
            target = self.ndu_path.parent / name
            stage = staging / name
            stage.write_bytes(data)
            self.read_paths[target] = stage
            target.write_bytes(b"old " + name.encode("utf-8"))
        self.artifact_hashes = {path: acceptance.sha256(stage.read_bytes()) for path, stage in self.read_paths.items()}
        self.source_hashes = {path: acceptance.sha256(path.read_bytes()) for path in implementation.glob("*.py")}
        self.metadata = {"profile_id": oracle()["profile_id"], "settings": {"version": 1}, "target_version": "JRSNAP 5.2-L03"}
        self.metadata["roles"] = {"cap_top": 1, "column_base_micro_top": 4, "footing_top": 5,
                                  "footing_centroid": 6, "footing_bottom": 7}
        self.computed = {"0500": {"df": 4.7}, "0710": {"input_sha256": self.input_sha256}}
        self.publication_id = "test-publication"
        self.old = {path: path.read_bytes() for path in self.read_paths}
        self.published = False
        self.cleaned = False

    def validate_unchanged(self) -> None:
        if self.input_path.read_bytes() != self.input_bytes:
            raise acceptance.AcceptanceError("input changed")
        for path, digest in self.source_hashes.items():
            if acceptance.sha256(path.read_bytes()) != digest:
                raise acceptance.AcceptanceError("profile changed")
        for path, stage in self.read_paths.items():
            if acceptance.sha256(stage.read_bytes()) != self.artifact_hashes[path]:
                raise acceptance.AcceptanceError("candidate changed")
            if not self.published and path.read_bytes() != self.old[path]:
                raise acceptance.AcceptanceError("destination changed")

    def publish(self) -> None:
        self.validate_unchanged()
        for path, stage in self.read_paths.items():
            path.write_bytes(stage.read_bytes())
        self.published = True

    @contextmanager
    def prepare(self, options: Any) -> Any:
        assert options is self.options
        try:
            yield self
        finally:
            self.cleaned = True


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    candidate = FakeCandidate(tmp_path, monkeypatch)
    path = tmp_path / "oracle.json"
    independent = oracle()
    independent["acceptance_approved"] = True
    path.write_text(json.dumps(independent, ensure_ascii=False), encoding="utf-8")
    identity = {"path": "fake-app.exe", "sha256": "a" * 64, "file_version": "5.2.3.0",
                "product_version": "5.2.3.0", "assembly_version": "5.2.3.1"}
    helper = tmp_path / "helper.ps1"
    helper.write_text("# fixture helper\n", encoding="utf-8")

    def runner(data: bytes) -> dict[str, Any]:
        return {"first": data, "second": data, "application": identity,
                "helper_sources": {str(helper): acceptance.sha256(helper.read_bytes())}}

    return SimpleNamespace(candidate=candidate, oracle=path, runner=runner, identity=identity,
                           receipt=tmp_path / "receipt.json", monkeypatch=monkeypatch)


def run_accept(harness: Any, **kwargs: Any) -> Path:
    return acceptance.accept_generation(
        harness.candidate.options, oracle_path=harness.oracle, receipt_path=harness.receipt,
        prepare=harness.candidate.prepare, app_runner=kwargs.pop("app_runner", harness.runner),
        identity_reader=lambda: harness.identity, **kwargs)


def test_acceptance_publishes_exact_held_bytes_and_retains_a_complete_bound_receipt(harness: Any) -> None:
    path = run_accept(harness)
    candidate = harness.candidate
    assert path == harness.receipt
    assert candidate.published and candidate.cleaned
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert receipt["status"] == "complete"
    binding = receipt["binding"]
    assert len(binding["expected_artifacts"]) == 4
    assert binding["origin_input_sha256"] == candidate.input_sha256
    assert Path(binding["origin_snapshot"]).read_bytes() == candidate.input_bytes
    assert set(binding["canonical_snapshot_sha256"]) == {"0500", "0710"}
    assert not binding["gui_inspected"] and not binding["analysis_executed"]
    for path, digest in candidate.artifact_hashes.items():
        assert acceptance.sha256(path.read_bytes()) == digest


@pytest.mark.parametrize("changed", ["input", "profile", "ndu", "pdf", "sidecar", "destination", "oracle", "metadata", "calculation"])
def test_changes_during_app_readback_prevent_publication(harness: Any, changed: str) -> None:
    candidate = harness.candidate

    def changed_runner(data: bytes) -> dict[str, Any]:
        if changed == "metadata":
            candidate.metadata["settings"]["version"] = 99
            return harness.runner(data)
        if changed == "calculation":
            candidate.computed["0500"]["df"] = 3.78
            return harness.runner(data)
        if changed == "input":
            path = candidate.input_path
        elif changed == "profile":
            path = next(path for path in candidate.source_hashes if path.name == "profile.py")
        elif changed == "destination":
            path = candidate.ndu_path
        elif changed == "oracle":
            path = harness.oracle
        else:
            suffix = {"ndu": ".ndu", "pdf": ".pdf", "sidecar": ".provenance.json"}[changed]
            path = next(stage for final, stage in candidate.read_paths.items() if str(final).endswith(suffix))
        path.write_bytes(path.read_bytes() + b" ")
        return harness.runner(data)

    with pytest.raises(acceptance.AcceptanceError, match="changed"):
        run_accept(harness, app_runner=changed_runner)
    assert not candidate.published
    for path, old in candidate.old.items():
        if changed != "destination" or path != candidate.ndu_path:
            assert path.read_bytes() == old


@pytest.mark.parametrize("problem", ["failure", "unstable", "meaning", "wrong_build"])
def test_app_failure_and_bad_readback_preserve_formal_artifacts(harness: Any, problem: str) -> None:
    def bad_runner(data: bytes) -> dict[str, Any]:
        if problem == "failure":
            raise acceptance.AcceptanceError("app timeout")
        result = harness.runner(data)
        if problem == "unstable":
            result["second"] = data + b"unexpected\r\n"
        elif problem == "meaning":
            result["first"] = result["second"] = replace_field(data, "FootInfo1", 9, "11.6")
        else:
            result["application"] = {**result["application"], "assembly_version": "5.3.1.3"}
        return result

    with pytest.raises((acceptance.AcceptanceError, ReadbackError)):
        run_accept(harness, app_runner=bad_runner)
    assert not harness.candidate.published


def test_receipt_creation_failure_prevents_publication(harness: Any) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("receipt disk full")
    harness.monkeypatch.setattr(acceptance, "_write_receipt", fail)
    with pytest.raises(OSError, match="disk full"):
        run_accept(harness)
    assert not harness.candidate.published


def test_failed_final_receipt_write_has_explicit_recovery_without_regeneration(harness: Any) -> None:
    write = acceptance._write_receipt

    def fail_final(path: Path, document: dict[str, Any], *, create: bool) -> None:
        if not create:
            raise OSError("receipt update failed")
        write(path, document, create=create)

    harness.monkeypatch.setattr(acceptance, "_write_receipt", fail_final)
    with pytest.raises(acceptance.AcceptanceError, match="Published; acceptance receipt is incomplete"):
        run_accept(harness)
    assert harness.candidate.published
    assert json.loads(harness.receipt.read_text(encoding="utf-8"))["status"] == "verified_pending_publication"
    before = {path: path.read_bytes() for path in harness.candidate.artifact_hashes}
    harness.monkeypatch.setattr(acceptance, "_write_receipt", write)
    acceptance.finalize_receipt(harness.receipt, identity_reader=lambda: harness.identity)
    assert json.loads(harness.receipt.read_text(encoding="utf-8"))["status"] == "complete"
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize("changed", ["input", "profile", "output", "evidence", "receipt", "oracle", "source_set"])
def test_finalize_receipt_rechecks_all_original_bindings(harness: Any, changed: str) -> None:
    run_accept(harness)
    binding = json.loads(harness.receipt.read_text(encoding="utf-8"))["binding"]
    if changed == "input":
        path = harness.candidate.input_path
    elif changed == "profile":
        path = next(path for path in harness.candidate.source_hashes if path.name == "profile.py")
    elif changed == "output":
        path = harness.candidate.ndu_path
    elif changed == "evidence":
        path = Path(next(iter(binding["evidence_hashes"])))
    elif changed == "oracle":
        path = harness.oracle
    elif changed == "source_set":
        path = Path(binding["implementation_source_directory"]) / "new.py"
        path.write_bytes(b"")
    else:
        receipt = json.loads(harness.receipt.read_text(encoding="utf-8"))
        receipt["binding"]["metadata"]["settings"]["version"] = 2
        harness.receipt.write_text(json.dumps(receipt), encoding="utf-8")
        path = None
    if path is not None:
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(acceptance.AcceptanceError):
        acceptance.finalize_receipt(harness.receipt, identity_reader=lambda: harness.identity)


def test_wrong_input_oracle_blocks_before_app_launch(harness: Any) -> None:
    value = oracle()
    value["acceptance_approved"] = True
    value["input_sha256"] = "0" * 64
    harness.oracle.write_text(json.dumps(value), encoding="utf-8")

    def unexpected(data: bytes) -> dict[str, Any]:
        raise AssertionError("App must not launch")

    with pytest.raises(acceptance.AcceptanceError, match="another raw input"):
        run_accept(harness, app_runner=unexpected)


def test_wrong_role_metadata_blocks_before_app_launch(harness: Any) -> None:
    harness.candidate.metadata["roles"]["cap_top"] = 4
    with pytest.raises(acceptance.AcceptanceError, match="candidate role"):
        run_accept(harness)


def test_unapproved_oracle_cannot_start_acceptance(harness: Any) -> None:
    value = oracle()
    value["acceptance_approved"] = False
    harness.oracle.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(acceptance.AcceptanceError, match="not been approved"):
        run_accept(harness)
    assert not harness.candidate.published


def test_wrong_target_metadata_blocks_before_app_launch(harness: Any) -> None:
    harness.candidate.metadata["target_version"] = "5.3-L01"
    with pytest.raises(acceptance.AcceptanceError, match="candidate target"):
        run_accept(harness)


@pytest.mark.parametrize("problem", ["exit", "timeout", "bad_json"])
def test_helper_process_failures_are_explicit(monkeypatch: pytest.MonkeyPatch, problem: str) -> None:
    def process(*args: Any, **kwargs: Any) -> Any:
        assert kwargs["timeout"] == 12
        if problem == "timeout":
            raise subprocess.TimeoutExpired("powershell", 12)
        return SimpleNamespace(returncode=3 if problem == "exit" else 0, stderr=b"failed", stdout=b"not JSON")
    monkeypatch.setattr(acceptance.subprocess, "run", process)
    with pytest.raises(acceptance.AcceptanceError):
        acceptance._powershell_json("test", timeout=12)


@pytest.mark.parametrize("version", ["5.3.1.3", "5.2.3.0", None])
def test_application_identity_requires_exact_installed_assembly_build(tmp_path: Path,
                                                                    monkeypatch: pytest.MonkeyPatch,
                                                                    version: str | None) -> None:
    executable = tmp_path / "JRSNAP_Input.exe"
    executable.write_bytes(b"test")
    identity = {"file_version": "5.2.3.0", "product_version": "5.2.3.0", "assembly_version": version}
    monkeypatch.setattr(acceptance, "_powershell_json", lambda *args, **kwargs: identity)
    with pytest.raises(acceptance.AcceptanceError, match="not JRSNAP 5.2"):
        acceptance.app_identity(executable)


@pytest.mark.parametrize("problem", ["none", "missing", "stale", "unstable", "hash", "write_mode"])
def test_roundtrip_requires_fresh_stable_unchanged_app_outputs(tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch,
                                                            problem: str) -> None:
    helper = tmp_path / "save-ndu.ps1"
    helper.write_bytes(b"# test")
    helper.with_name("roundtrip.cs").write_bytes(b"// test")
    identity = {"assembly_version": "5.2.3.1"}
    monkeypatch.setattr(acceptance, "app_identity", lambda: identity)

    def fake_process(command: str, *, timeout: int) -> dict[str, Any]:
        copied = Path(re.search(r" -Path '([^']+)'", command).group(1))
        data = copied.read_bytes()
        stage = tmp_path / "jrsnap-ndu-save-test"
        stage.mkdir()
        for suffix in ("original", "saved", "second"):
            if problem == "missing" and suffix == "saved":
                continue
            path = stage / f"case1.{suffix}.ndu"
            path.write_bytes(data + (b"changed" if problem == "unstable" and suffix == "second" else b""))
            if problem == "stale":
                os.utime(path, (100, 100))
        return {"Written": problem == "write_mode", "ConvertedS6": False,
                "BeforeHash": acceptance.sha256(data), "Stage": str(stage),
                "AfterHash": "0" * 64 if problem == "hash" else acceptance.sha256(data)}

    monkeypatch.setattr(acceptance, "_powershell_json", fake_process)
    if problem == "none":
        result = acceptance.run_v52_roundtrip(reference_bytes(), helper=helper, timeout=5)
        assert result["first"] == result["second"] == reference_bytes()
    else:
        with pytest.raises(acceptance.AcceptanceError):
            acceptance.run_v52_roundtrip(reference_bytes(), helper=helper, timeout=5)
