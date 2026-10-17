"""Dedicated JRSNAP paths and provenance; FrameWeb schema 2 stays unchanged."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from .frameweb_artifacts import (
    ALL_STAGES,
    REPORT_STEMS,
    build_artifact_manifest,
    frameweb_paths,
)
from .inputs import InputError

TARGET_VERSION = "5.2-L03"
CONVENTION_VERSION = "p7-longitudinal-jrsnap-v1"
NATIVE_ROLE = "0710.jrsnap"
SIDECAR_ROLE = "0710.jrsnap_sidecar"


@dataclass(frozen=True)
class JrsnapSpec:
    direction: str
    native_filename: str
    convention_version: str


JRSNAP_STAGES = {
    "0710": JrsnapSpec("longitudinal", "線路方向.ndu", CONVENTION_VERSION),
    "0720": JrsnapSpec("transverse", "線路直角方向.ndu", "p7-transverse-jrsnap-v1"),
}


def _spec(stage: str) -> JrsnapSpec:
    if stage not in JRSNAP_STAGES:
        raise InputError(f"JRSNAPの計算段階が不正です: {stage}")
    return JRSNAP_STAGES[stage]


def jrsnap_paths(post_dir: Path, *, stage: str = "0710") -> tuple[Path, Path]:
    native = Path(post_dir) / _spec(stage).native_filename
    return native, native.with_suffix(".ndu.provenance.json")


def canonical_sha256(value: object) -> str:
    """Schema 1: the entire JSON-compatible object, without excluded fields."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def implementation_hashes(package_root: Path | None = None) -> dict[Path, str]:
    """Include profile, calculations, rendering and publication implementations."""
    from .reporting.runtime import dependency_hashes

    return dependency_hashes(Path(__file__).parent if package_root is None else package_root)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"JSONキーが重複しています: {key}")
        result[key] = value
    return result


def load_json_bytes(data: bytes) -> object:
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_unique_pairs,
                          parse_constant=lambda value: _reject_constant(value))
    except (UnicodeError, ValueError) as exc:
        raise InputError(f"JSONを読み込めません: {exc}") from exc


def _reject_constant(value: str) -> None:
    raise InputError(f"JSONに非有限値があります: {value}")


def _artifact_paths(output_dir: Path, post_dir: Path, stage: str) -> dict[str, Path]:
    return {f"{stage}.result_pdf": Path(output_dir) / f"{REPORT_STEMS[stage]}.pdf",
            f"{stage}.result_json": Path(output_dir) / f"{REPORT_STEMS[stage]}.json",
            f"{stage}.jrsnap": jrsnap_paths(post_dir, stage=stage)[0]}


def build_jrsnap_provenance(*, output_dir: Path, post_dir: Path,
                            input_sha256: str, input_file: str,
                            foundation: dict, seismic: dict, model: dict,
                            publication_id: str, selected_stages: Sequence[str],
                            source_hashes: Mapping[Path, str],
                            read_paths: Mapping[Path, Path], stage: str = "0710") -> dict:
    spec = _spec(stage)
    metadata = deepcopy(model["metadata"])
    return {
        "schema_version": 1, "convention_version": spec.convention_version,
        "stage": stage, "direction": spec.direction, "target_version": TARGET_VERSION,
        "publication_id": publication_id, "selected_stages": list(selected_stages),
        "provenance": {"input_file": input_file, "input_sha256": input_sha256,
                       "raw_input_sha256": input_sha256},
        "calculation_snapshot_schema_version": 1,
        "calculation_snapshot_sha256": {"0500": canonical_sha256(foundation),
                                        stage: canonical_sha256(seismic)},
        "profile": metadata, "profile_sha256": canonical_sha256(metadata),
        "source_hashes": {str(path.resolve()): digest for path, digest in source_hashes.items()},
        "artifact_manifest": build_artifact_manifest(
            _artifact_paths(output_dir, post_dir, stage), read_paths=read_paths),
        "app_read_verified": False, "analysis_run": False,
    }


def _read(path: Path, aliases: Mapping[Path, Path]) -> bytes:
    source = aliases.get(path.resolve(), path)
    if source.is_symlink() or not source.is_file():
        raise InputError(f"JRSNAP成果物が通常ファイルではありません: {source}")
    return source.read_bytes()


def _validate_native(data: bytes) -> None:
    from .jrsnap_ndu import validate_ndu_bytes
    validate_ndu_bytes(data)


def _sha(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(character in "0123456789abcdef" for character in value))


def validate_jrsnap_artifacts(*, post_dir: Path, output_dir: Path,
                              expected_input_sha256: str,
                              expected_stages: Sequence[str],
                              expected_publication_id: str | None = None,
                              expected_snapshot_sha256: Mapping[str, str] | None = None,
                              read_paths: Mapping[Path, Path] | None = None,
                              stage: str = "0710") -> dict:
    """Verify the dedicated generation and its common all-job publication ID."""
    aliases = {path.resolve(): source for path, source in (read_paths or {}).items()}
    try:
        return _validate(post_dir, output_dir, expected_input_sha256, expected_stages,
                         expected_publication_id, expected_snapshot_sha256, aliases, stage)
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError(f"JRSNAP成果物を読み込めません: {exc}") from exc


def _validate(post_dir, output_dir, expected_sha, stages, publication_id, snapshots, aliases, stage):
    from . import jrsnap_design_conditions
    spec = _spec(stage)
    profile_id = (jrsnap_design_conditions.PROFILE_ID if stage == "0710"
                  else jrsnap_design_conditions.TRANSVERSE_PROFILE_ID)
    native, sidecar = jrsnap_paths(post_dir, stage=stage)
    metadata = load_json_bytes(_read(sidecar, aliases))
    if (not isinstance(metadata, dict) or metadata.get("schema_version") != 1
            or metadata.get("convention_version") != spec.convention_version
            or metadata.get("stage") != stage or metadata.get("direction") != spec.direction
            or metadata.get("target_version") != TARGET_VERSION
            or tuple(stages) not in ((stage,), ALL_STAGES)
            or metadata.get("selected_stages") != list(stages)
            or not isinstance(metadata.get("publication_id"), str) or not metadata["publication_id"]
            or (publication_id is not None and metadata["publication_id"] != publication_id)
            or metadata.get("app_read_verified") is not False
            or metadata.get("analysis_run") is not False):
        raise InputError("JRSNAP付帯JSONの形式・公開世代・対象版が不正です")
    provenance = metadata.get("provenance", {})
    if (not _sha(expected_sha) or provenance.get("input_sha256") != expected_sha
            or provenance.get("raw_input_sha256") != expected_sha):
        raise InputError("JRSNAP付帯JSONの入力SHAが一致しません")
    profile = metadata.get("profile", {})
    if (not isinstance(profile, dict) or profile.get("profile_id") != profile_id
            or profile.get("direction", "longitudinal") != spec.direction
            or profile.get("schema_version") != 1 or profile.get("target_version") != TARGET_VERSION
            or profile.get("input_sha256") != expected_sha
            or metadata.get("profile_sha256") != canonical_sha256(profile)):
        raise InputError("JRSNAP解析profileの形式・入力SHAが不正です")
    expected_sources = {str(path): digest for path, digest in implementation_hashes().items()}
    if metadata.get("source_hashes") != expected_sources:
        raise InputError("JRSNAP生成プログラム・profileが変更されています。再生成してください")
    paths = _artifact_paths(output_dir, post_dir, stage)
    manifest = build_artifact_manifest(paths, read_paths=aliases)
    if metadata.get("artifact_manifest") != manifest:
        raise InputError("JRSNAP成果物のmanifest・SHA・パスが一致しません")
    stored_snapshots = metadata.get("calculation_snapshot_sha256", {})
    if (metadata.get("calculation_snapshot_schema_version") != 1
            or not isinstance(stored_snapshots, dict) or set(stored_snapshots) != {"0500", stage}
            or any(not _sha(value) for value in stored_snapshots.values())
            or (snapshots is not None and stored_snapshots != dict(snapshots))):
        raise InputError("JRSNAP計算スナップショットのSHAが不正です")
    if profile.get("canonical_snapshot_sha256") != {
            "foundation": stored_snapshots["0500"], "seismic": stored_snapshots[stage]}:
        raise InputError("JRSNAP profileと計算スナップショットが一致しません")
    for result_stage in (("0500", stage) if tuple(stages) == ALL_STAGES else (stage,)):
        result = load_json_bytes(_read(Path(output_dir) / f"{REPORT_STEMS[result_stage]}.json", aliases))
        if (not isinstance(result, dict)
                or result.get("provenance", {}).get("input_sha256") != expected_sha
                or canonical_sha256(result) != stored_snapshots[result_stage]):
            raise InputError(f"{result_stage}計算スナップショット・入力SHAが一致しません")
    if tuple(stages) == ALL_STAGES:
        for peer_stage in ("0610", "0620"):
            peer = load_json_bytes(_read(frameweb_paths(post_dir, stage=peer_stage)[1], aliases))
            if (not isinstance(peer, dict) or peer.get("publication_id") != metadata["publication_id"]
                    or peer.get("selected_stages") != list(stages)):
                raise InputError("FrameWebとJRSNAPの公開世代が一致しません")
    _validate_native(_read(native, aliases))
    return metadata
