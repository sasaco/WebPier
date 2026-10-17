"""Verify retained directional NDU candidates in V5.2, then publish those bytes.

The normal CLI has no JRSNAP dependency. This deliberately separate acceptance
entry point retains independent evidence and supports receipt-only recovery if
the final receipt write fails after successful publication. It never runs SNAP.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gridlayoutpdf import LayoutError

PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = PROJECT.parent
sys.path.insert(0, str(PROJECT))

from src.jrsnap_readback import ReadbackError, verify_readback
from src.jrsnap_artifacts import implementation_hashes

DEFAULT_ORACLE = PROJECT / "tests" / "fixtures" / "jrsnap_v52_longitudinal_expected.json"
DEFAULT_ORACLES = {"0710": DEFAULT_ORACLE,
                   "0720": PROJECT / "tests/fixtures/jrsnap_v52_transverse_expected.json"}
_DIRECTIONS = {"0710": "longitudinal", "0720": "transverse"}
DEFAULT_APP = Path("C:/RTRI_Program/JRSNAP(Ver5.2-L03)/JRSNAP_Input.exe")
DEFAULT_HELPER = REPOSITORY / ".agents/skills/jrsnap-input-open-save/scripts/save-ndu.ps1"


class AcceptanceError(ValueError):
    """Acceptance failed; a completed publication must not be claimed."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _ps_literal(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _powershell_json(command: str, *, timeout: int) -> Any:
    prefix = ("$ErrorActionPreference='Stop'; "
              "$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); ")
    encoded = base64.b64encode((prefix + command).encode("utf-16le")).decode("ascii")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, timeout=timeout, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AcceptanceError(f"JRSNAP helper could not finish: {exc}") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise AcceptanceError(f"JRSNAP helper exit {result.returncode}: {detail}")
    try:
        return json.loads(result.stdout.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError("JRSNAP helper did not return valid JSON") from exc


def app_identity(executable: Path = DEFAULT_APP) -> dict[str, str]:
    """Check the installed build, rather than trusting an NDU header."""
    executable = executable.resolve(strict=True)
    command = (
        "$p=" + _ps_literal(executable) + "; $f=Get-Item -LiteralPath $p; "
        "[ordered]@{file_version=$f.VersionInfo.FileVersion;"
        "product_version=$f.VersionInfo.ProductVersion;"
        "assembly_version=[Reflection.AssemblyName]::GetAssemblyName($p).Version.ToString()}"
        "| ConvertTo-Json -Compress"
    )
    identity = _powershell_json(command, timeout=30)
    required = {"file_version": "5.2.3.0", "product_version": "5.2.3.0",
                "assembly_version": "5.2.3.1"}
    if not isinstance(identity, dict) or any(identity.get(key) != value for key, value in required.items()):
        raise AcceptanceError(f"Installed application is not JRSNAP 5.2-L03: {identity}")
    return {**identity, "path": str(executable), "sha256": sha256(executable.read_bytes())}


def run_v52_roundtrip(candidate: bytes, *, timeout: int = 30,
                      helper: Path = DEFAULT_HELPER) -> dict[str, Any]:
    """Read/save copies twice using the installed app and retain both byte arrays."""
    if not 5 <= timeout <= 300:
        raise AcceptanceError("Helper timeout must be 5-300 seconds")
    identity = app_identity()
    helper = helper.resolve(strict=True)
    sources = {str(path): sha256(path.read_bytes()) for path in (helper, helper.with_name("roundtrip.cs"))}
    with tempfile.TemporaryDirectory(prefix="p7-ndu-acceptance-") as temporary:
        copied = Path(temporary) / "candidate.ndu"
        copied.write_bytes(candidate)
        started = datetime.now(UTC).timestamp()
        command = ("& " + _ps_literal(helper) + " -Path " + _ps_literal(copied)
                   + f" -Version V52 -TimeoutSeconds {timeout} | ConvertTo-Json -Depth 8 -Compress")
        report = _powershell_json(command, timeout=2 * timeout + 90)
        if (not isinstance(report, dict) or report.get("Written") is not False
                or report.get("ConvertedS6") is not False
                or str(report.get("BeforeHash", "")).lower() != sha256(candidate)):
            raise AcceptanceError("The helper did not validate the unchanged candidate in dry-run mode")
        if copied.read_bytes() != candidate:
            raise AcceptanceError("The application modified the acceptance input copy")
        stage = Path(str(report.get("Stage", "")))
        if not stage.is_dir() or not stage.name.startswith("jrsnap-ndu-save-"):
            raise AcceptanceError("JRSNAP helper stage is missing or invalid")
        paths = [stage / f"case1.{part}.ndu" for part in ("original", "saved", "second")]
        for path in paths:
            if not path.is_file() or path.stat().st_mtime < started - 2:
                raise AcceptanceError(f"Missing or stale JRSNAP readback: {path}")
        original, first, second = (path.read_bytes() for path in paths)
        if original != candidate or not first or first != second:
            raise AcceptanceError("JRSNAP second save is not byte-stable")
        if str(report.get("AfterHash", "")).lower() != sha256(first):
            raise AcceptanceError("JRSNAP helper output hash differs")
    if app_identity() != identity or any(sha256(Path(path).read_bytes()) != digest for path, digest in sources.items()):
        raise AcceptanceError("JRSNAP application or helper changed during acceptance")
    return {"application": identity, "first": first, "second": second,
            "helper_sources": sources, "helper_report": report}


def _check_files(expected: Mapping[str, str], label: str) -> None:
    if not expected:
        raise AcceptanceError(f"Empty {label} binding")
    for name, digest in expected.items():
        path = Path(name)
        if path.is_symlink() or not path.is_file() or sha256(path.read_bytes()) != digest:
            raise AcceptanceError(f"{label} changed or is missing: {name}")


def _write_receipt(path: Path, document: dict[str, Any], *, create: bool) -> None:
    encoded = (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if create:
        # Incomplete creation can never authorize publication: the file is read
        # back and checked before publish(). Existing receipts are never replaced.
        with path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
    if path.read_bytes() != encoded:
        raise AcceptanceError("Acceptance receipt bytes changed while writing")


def _origin_snapshot(candidate: Any) -> Path:
    origin = candidate.options.input_path.resolve()
    snapshot = origin.parent / "snapshots" / f"ndu-origin-{candidate.input_sha256}.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if not snapshot.exists():
        with snapshot.open("xb") as stream:
            stream.write(candidate.input_bytes)
    if snapshot.is_symlink() or snapshot.read_bytes() != candidate.input_bytes:
        raise AcceptanceError("Origin snapshot does not match the full raw input bytes")
    return snapshot.resolve()


def _candidate_views(candidate: Any) -> dict[str, tuple[Path, Mapping[str, Any]]]:
    stages = ("0710", "0720") if candidate.options.stage == "all" else (candidate.options.stage,)
    paths = getattr(candidate, "ndu_paths", None)
    metadata = getattr(candidate, "metadata_by_stage", None)
    if paths is None and stages == ("0710",):
        return {"0710": (candidate.ndu_path, candidate.metadata)}
    if not isinstance(paths, Mapping) or not isinstance(metadata, Mapping) or set(paths) != set(stages) or set(metadata) != set(stages):
        raise AcceptanceError("Held directional candidates do not match the selected stages")
    return {stage: (paths[stage], metadata[stage]) for stage in stages}


def _receipt_binding(candidate: Any, *, oracle_paths: Mapping[str, Path], receipt_path: Path,
                     app_results: Mapping[str, Mapping[str, Any]], semantics: Mapping[str, dict[str, Any]],
                     supporting_sources: Mapping[str, str]) -> dict[str, Any]:
    evidence = receipt_path.with_suffix(".evidence")
    evidence.mkdir()
    views = _candidate_views(candidate)
    directional = {}
    sources = {str(path.resolve()): digest for path, digest in candidate.source_hashes.items()}
    for stage, (native_path, metadata) in views.items():
        app_result = app_results[stage]
        location = evidence if len(views) == 1 else evidence / stage
        if location != evidence:
            location.mkdir()
        native = candidate.read_paths[native_path].read_bytes()
        evidence_hashes = {}
        for name, data in (("candidate.ndu", native), ("first.ndu", app_result["first"]),
                           ("second.ndu", app_result["second"])):
            path = location / name
            with path.open("xb") as stream:
                stream.write(data)
            evidence_hashes[str(path.resolve())] = sha256(data)
        for source, digest in app_result["helper_sources"].items():
            if source in sources and sources[source] != digest:
                raise AcceptanceError("Application helper source changed between directions")
            sources[source] = digest
        directional[stage] = {"stage": stage, "direction": _DIRECTIONS[stage], "metadata": metadata,
                              "native_path": str(native_path.resolve()), "oracle_path": str(oracle_paths[stage]),
                              "evidence_hashes": evidence_hashes, "semantic_inspection": semantics[stage]}
    sources.update(supporting_sources)
    binding = {
        "publication_id": candidate.publication_id,
        "raw_input_path": str(candidate.options.input_path.resolve()),
        "raw_input_sha256": candidate.input_sha256,
        "origin_input_sha256": candidate.input_sha256,
        "origin_snapshot": str(_origin_snapshot(candidate)),
        "canonical_snapshot_sha256": {stage: canonical_sha256(candidate.computed[stage]) for stage in ("0500", *views)},
        "expected_artifacts": {str(path.resolve()): digest for path, digest in candidate.artifact_hashes.items()},
        "source_hashes": sources,
        "implementation_source_paths": sorted(str(path.resolve()) for path in candidate.source_hashes),
        "implementation_source_directory": str((PROJECT / "src").resolve()),
        "application": next(iter(app_results.values()))["application"],
        "gui_inspected": False, "analysis_executed": False,
    }
    if len(directional) == 1:
        binding.update(next(iter(directional.values())))
    else:
        binding["directions"] = directional
    return binding


def _check_binding(receipt: Mapping[str, Any], *, published: bool) -> None:
    binding = receipt.get("binding", {})
    if receipt.get("schema_version") not in (1, 2) or canonical_sha256(binding) != receipt.get("binding_sha256"):
        raise AcceptanceError("Acceptance receipt binding is missing or altered")
    if receipt.get("status") not in ("verified_pending_publication", "complete"):
        raise AcceptanceError("Unsupported acceptance receipt status")
    raw_hash = binding["raw_input_sha256"]
    if binding["origin_input_sha256"] != raw_hash:
        raise AcceptanceError("Origin and raw input generations differ")
    _check_files({binding["raw_input_path"]: raw_hash, binding["origin_snapshot"]: raw_hash}, "Input")
    _check_files(binding["source_hashes"], "Source/profile/oracle")
    try:
        current_hashes = implementation_hashes(Path(binding["implementation_source_directory"]))
        current_sources = sorted(str(path) for path in current_hashes)
    except (OSError, ValueError, LayoutError) as exc:
        raise AcceptanceError(f"Implementation dependencies cannot be verified: {exc}") from exc
    if current_sources != binding["implementation_source_paths"]:
        raise AcceptanceError("Implementation source file set changed")
    if any(binding["source_hashes"].get(str(path)) != digest for path, digest in current_hashes.items()):
        raise AcceptanceError("Implementation dependency bytes changed")
    if receipt["schema_version"] == 2:
        directions = binding.get("directions", {})
        if set(directions) != {"0710", "0720"}:
            raise AcceptanceError("Both directional readbacks are required")
        if set(binding["canonical_snapshot_sha256"]) != {"0500", "0710", "0720"}:
            raise AcceptanceError("Both directional calculation bindings are required")
        for stage, direction in directions.items():
            if direction.get("stage") != stage or direction.get("direction") != _DIRECTIONS[stage]:
                raise AcceptanceError("Directional receipt identity differs")
            _check_direction_binding(direction, binding)
    else:
        if "directions" in binding:
            raise AcceptanceError("Unexpected multiple directions in a single-direction receipt")
        _check_direction_binding(binding, binding)
    if published:
        _check_files(binding["expected_artifacts"], "Published artifact")


def _check_direction_binding(direction: Mapping[str, Any], binding: Mapping[str, Any]) -> None:
    _check_files(direction["evidence_hashes"], "Readback evidence")
    oracle = json.loads(Path(direction["oracle_path"]).read_text(encoding="utf-8"))
    if oracle.get("acceptance_approved") is not True:
        raise AcceptanceError("The independent acceptance oracle has not been approved")
    if oracle.get("input_sha256") != binding["raw_input_sha256"]:
        raise AcceptanceError("Independent oracle belongs to another input generation")
    _check_roles(direction["metadata"], oracle)
    evidence = {Path(name).name: Path(name).read_bytes() for name in direction["evidence_hashes"]}
    if set(evidence) != {"candidate.ndu", "first.ndu", "second.ndu"}:
        raise AcceptanceError("Incomplete readback evidence set")
    if evidence["first.ndu"] != evidence["second.ndu"]:
        raise AcceptanceError("Application second save changed")
    for data in evidence.values():
        verify_readback(data, oracle)
    if sha256(evidence["candidate.ndu"]) != binding["expected_artifacts"].get(direction["native_path"]):
        raise AcceptanceError("Readback candidate is not the bound publication candidate")


def finalize_receipt(path: Path, *, identity_reader: Callable[[], dict[str, str]] = app_identity) -> dict[str, Any]:
    """Recheck all retained bindings before completing a receipt; never regenerate."""
    if path.is_symlink():
        raise AcceptanceError("Acceptance receipt must not be a symlink")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    _check_binding(receipt, published=True)
    if identity_reader() != receipt["binding"]["application"]:
        raise AcceptanceError("The installed application changed since readback")
    receipt.update(status="complete", completed_utc=_utc_now())
    _write_receipt(path, receipt, create=False)
    return receipt


def _held_calculation_hash(candidate: Any) -> str:
    views = _candidate_views(candidate)
    return canonical_sha256({"metadata": {stage: data[1] for stage, data in views.items()},
                             "native_paths": {stage: str(data[0].resolve()) for stage, data in views.items()},
                             "calculations": {stage: candidate.computed[stage] for stage in ("0500", *views)},
                             "publication_id": candidate.publication_id,
                             "input_sha256": candidate.input_sha256})


def _check_roles(metadata: Mapping[str, Any], oracle: Mapping[str, Any]) -> None:
    if metadata.get("profile_id") != oracle.get("profile_id"):
        raise AcceptanceError("The candidate profile differs from the independent oracle")
    if metadata.get("target_version") not in ("5.2-L03", "JRSNAP 5.2-L03"):
        raise AcceptanceError("The candidate target version is not JRSNAP 5.2-L03")
    roles = metadata.get("roles", {})
    for role, identifier in oracle["role_ids"].items():
        source_role = oracle.get("role_sources", {}).get(role, "cap_top" if role in ("load_top", "control") else role)
        if role == "control":
            configured = metadata.get("settings", {}).get("analysis", {}).get("control_role", "cap_top")
            if configured != source_role:
                raise AcceptanceError("The candidate control role differs from the independent oracle")
        if roles.get(source_role) != identifier:
            raise AcceptanceError(f"The candidate role {role} differs from the independent oracle")


def accept_generation(options: Any, *, oracle_path: Path | None = None,
                      oracle_paths: Mapping[str, Path] | None = None,
                      receipt_path: Path | None = None,
                      prepare: Callable[..., Any] | None = None,
                      app_runner: Callable[[bytes], dict[str, Any]] = run_v52_roundtrip,
                      identity_reader: Callable[[], dict[str, str]] = app_identity) -> Path:
    """Publish the same held candidates only after independent real-app acceptance."""
    if not options.jrsnap or options.stage not in ("0710", "0720", "all"):
        raise AcceptanceError("Acceptance requires --stage 0710/0720/all and JRSNAP output")
    if prepare is None:
        from src.cli import prepare_generation
        prepare = prepare_generation
    stages = ("0710", "0720") if options.stage == "all" else (options.stage,)
    if oracle_path is not None and (oracle_paths is not None or len(stages) != 1):
        raise AcceptanceError("Use stage-keyed oracle_paths for both directions")
    selected = dict(oracle_paths if oracle_paths is not None else {stage: DEFAULT_ORACLES[stage] for stage in stages})
    if oracle_path is not None:
        selected = {stages[0]: oracle_path}
    if set(selected) != set(stages):
        raise AcceptanceError("An independent oracle is required for every selected direction")
    selected = {stage: path.resolve(strict=True) for stage, path in selected.items()}
    oracles = {stage: json.loads(path.read_text(encoding="utf-8")) for stage, path in selected.items()}
    if any(oracle.get("acceptance_approved") is not True for oracle in oracles.values()):
        raise AcceptanceError("The independent acceptance oracle has not been approved")
    supporting_sources = {str(path.resolve()): sha256(path.read_bytes()) for path in (
        Path(__file__), PROJECT / "src/jrsnap_readback.py", *selected.values())}
    with prepare(options) as candidate:
        candidate.validate_unchanged()
        _check_files(supporting_sources, "Acceptance source/oracle")
        views = _candidate_views(candidate)
        for stage, (_, metadata) in views.items():
            if oracles[stage].get("input_sha256") != candidate.input_sha256:
                raise AcceptanceError("Independent oracle is for another raw input generation")
            _check_roles(metadata, oracles[stage])
        held_calculation_hash = _held_calculation_hash(candidate)
        app_results, semantics = {}, {}
        for stage, (native_path, _) in views.items():
            oracle = oracles[stage]
            native = candidate.read_paths[native_path].read_bytes()
            before = verify_readback(native, oracle)
            app_result = app_runner(native)
            if app_result["first"] != app_result["second"]:
                raise AcceptanceError("Application second save changed")
            first = verify_readback(app_result["first"], oracle)
            second = verify_readback(app_result["second"], oracle)
            app_results[stage] = app_result
            semantics[stage] = {"candidate": before, "first": first, "second": second}
        candidate.validate_unchanged()
        _check_files(supporting_sources, "Acceptance source/oracle")
        if _held_calculation_hash(candidate) != held_calculation_hash:
            raise AcceptanceError("Held calculation/profile metadata changed during readback")
        path = (receipt_path or REPOSITORY / ".agents/docs/research" /
                f"p7-{_DIRECTIONS.get(options.stage, 'both')}-ndu-acceptance-{candidate.publication_id}.json").resolve()
        if path in {artifact.resolve() for artifact in candidate.artifact_hashes} or path == options.input_path.resolve():
            raise AcceptanceError("Receipt collides with a product artifact or input")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() or path.is_symlink():
            raise AcceptanceError("Receipt already exists; use --finalize-receipt for recovery")
        identities = [result["application"] for result in app_results.values()]
        if any(identity != identities[0] for identity in identities[1:]):
            raise AcceptanceError("Application identity differs between directions")
        binding = _receipt_binding(candidate, oracle_paths=selected, receipt_path=path,
                                   app_results=app_results, semantics=semantics,
                                   supporting_sources=supporting_sources)
        receipt = {"schema_version": 2 if len(views) > 1 else 1, "status": "verified_pending_publication",
                   "verified_utc": _utc_now(), "binding": binding, "binding_sha256": canonical_sha256(binding)}
        _write_receipt(path, receipt, create=True)
        stored = json.loads(path.read_text(encoding="utf-8"))
        _check_binding(stored, published=False)
        if identity_reader() != binding["application"]:
            raise AcceptanceError("Application changed before publication")
        candidate.validate_unchanged()
        if _held_calculation_hash(candidate) != held_calculation_hash:
            raise AcceptanceError("Held calculation/profile metadata changed before publication")
        candidate.publish()
        try:
            finalize_receipt(path, identity_reader=identity_reader)
        except Exception as exc:
            raise AcceptanceError(
                f"Published; acceptance receipt is incomplete. Recheck with --finalize-receipt {path}: {exc}"
            ) from exc
        return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=PROJECT / "pre/input.json")
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "output")
    parser.add_argument("--post-dir", type=Path)
    parser.add_argument("--stage", choices=("0710", "0720", "all"), default="0710")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--oracle", type=Path, help="Independent oracle for a single selected stage")
    parser.add_argument("--longitudinal-oracle", type=Path)
    parser.add_argument("--transverse-oracle", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--finalize-receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.finalize_receipt:
            finalize_receipt(args.finalize_receipt)
            path = args.finalize_receipt
        else:
            from src.cli import GenerationOptions
            options = GenerationOptions(input_path=args.input, output_dir=args.output_dir,
                                        post_dir=args.post_dir, stage=args.stage,
                                        overwrite=args.overwrite, jrsnap=True)
            direction_paths = None
            if args.longitudinal_oracle or args.transverse_oracle:
                direction_paths = {stage: selected for stage, selected in (
                    ("0710", args.longitudinal_oracle), ("0720", args.transverse_oracle)) if selected is not None}
            path = accept_generation(options, oracle_path=args.oracle, oracle_paths=direction_paths,
                                     receipt_path=args.receipt)
    except (AcceptanceError, ReadbackError, OSError, ValueError, KeyError) as exc:
        print(f"受入未完了: {exc}", file=sys.stderr)
        return 2
    print(f"受入完了（入力読込・再保存のみ、解析未実行）: {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
