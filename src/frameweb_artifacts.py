"""Shared FrameWeb destination and published-generation checks for CLI/GUI."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .inputs import InputError

PROJECT_DIR = Path(__file__).resolve().parents[1]
LONGITUDINAL_OUTPUT_STEM = "0610_線路方向荷重"
NATIVE_FILENAME = "frameWebForJS.json"
PROVENANCE_FILENAME = "frameWebForJS.provenance.json"
CONVENTION_VERSION = "p7-longitudinal-frameweb-v1"
TRANSVERSE_OUTPUT_STEM = "0620_直角方向荷重"


@dataclass(frozen=True)
class FrameWebSpec:
    output_stem: str
    native_filename: str
    direction: str
    convention_version: str

    @property
    def sidecar_filename(self) -> str:
        return Path(self.native_filename).stem + ".provenance.json"


FRAMEWEB_STAGES = {
    "0610": FrameWebSpec(LONGITUDINAL_OUTPUT_STEM, NATIVE_FILENAME, "longitudinal", CONVENTION_VERSION),
    "0620": FrameWebSpec(TRANSVERSE_OUTPUT_STEM, "線路直角方向.json", "transverse", "p7-transverse-frameweb-v1"),
}
REPORT_STEMS = {"0500": "0500_直接基礎", "0600": "0600_上部工反力",
                **{stage: spec.output_stem for stage, spec in FRAMEWEB_STAGES.items()},
                "0710": "0710_線路方向荷重", "0720": "0720_線路直角方向荷重"}
ALL_STAGES = tuple(REPORT_STEMS)


def _spec(stage: str) -> FrameWebSpec:
    if stage not in FRAMEWEB_STAGES:
        raise InputError(f"FrameWebの計算段階が不正です: {stage}")
    return FRAMEWEB_STAGES[stage]


def resolve_post_dir(output_dir: Path, post_dir: Path | None = None) -> Path:
    if post_dir is not None:
        return Path(post_dir).resolve()
    output_dir = Path(output_dir).resolve()
    return ((PROJECT_DIR / "post").resolve() if output_dir == (PROJECT_DIR / "output").resolve()
            else output_dir / "post")


def frameweb_paths(post_dir: Path, *, stage: str = "0610") -> tuple[Path, Path]:
    spec = _spec(stage)
    return Path(post_dir) / spec.native_filename, Path(post_dir) / spec.sidecar_filename


def publication_paths(output_dir: Path, post_dir: Path, stages: Sequence[str]) -> tuple[dict[str, Path], dict[str, Path]]:
    """Ordered job registration, with all sidecars kept separate and last."""
    if (not stages or len(set(stages)) != len(stages)
            or any(stage not in REPORT_STEMS for stage in stages)):
        raise InputError("公開する計算段階の集合が不正です")
    artifacts = {f"{stage}.result_{suffix}": Path(output_dir) / f"{REPORT_STEMS[stage]}.{suffix}"
                 for stage in stages for suffix in ("pdf", "json")}
    sidecars = {}
    for stage in stages:
        if stage in FRAMEWEB_STAGES:
            native, sidecar = frameweb_paths(post_dir, stage=stage)
            artifacts[f"{stage}.native"] = native
            sidecars[f"{stage}.sidecar"] = sidecar
    return artifacts, sidecars


def _read(path: Path, read_paths: Mapping[Path, Path]) -> bytes:
    source = read_paths.get(path.resolve(), path)
    if source.is_symlink() or not source.is_file():
        raise InputError(f"成果物が通常ファイルではありません: {source}")
    return source.read_bytes()


def build_artifact_manifest(artifacts: Mapping[str, Path], *,
                            read_paths: Mapping[Path, Path] | None = None) -> list[dict]:
    aliases = {path.resolve(): source for path, source in (read_paths or {}).items()}
    return [{"role": role, "path": str(path.resolve()),
             "sha256": hashlib.sha256(_read(path, aliases)).hexdigest()}
            for role, path in artifacts.items()]


def build_provenance(*, input_sha256: str, input_file: str, native_path: Path,
                     result_json_path: Path, result_pdf_path: Path,
                     correspondence: dict, stage: str = "0610", publication_id: str | None = None,
                     selected_stages: Sequence[str] | None = None,
                     artifact_manifest: list[dict] | None = None,
                     expected_sidecars: list[dict] | None = None) -> dict:
    spec = _spec(stage)
    metadata = {
        "schema_version": 1,
        "convention_version": spec.convention_version,
        "provenance": {"input_file": input_file, "input_sha256": input_sha256},
        "artifacts": {
            key: {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for key, path in (("native", native_path), ("result_json", result_json_path),
                              ("result_pdf", result_pdf_path))
        },
        "correspondence": correspondence,
    }
    if publication_id is None:
        if stage != "0610" or any(value is not None for value in (selected_stages, artifact_manifest, expected_sidecars)):
            raise InputError("新規FrameWeb付帯JSONには公開ジョブのmanifestとpublication_idが必要です")
        return metadata  # Legacy 0610 callers retain schema1 compatibility.
    if not publication_id or not selected_stages or not artifact_manifest or not expected_sidecars:
        raise InputError("公開ジョブのmanifestが不完全です")
    metadata.update(schema_version=2, stage=stage, direction=spec.direction,
                    publication_id=publication_id, selected_stages=list(selected_stages),
                    artifact_manifest=artifact_manifest, expected_sidecars=expected_sidecars)
    return metadata


def validate_frameweb_artifacts(*, post_dir: Path, output_dir: Path,
                                expected_input_sha256: str, stage: str = "0610",
                                expected_stages: Sequence[str] | None = None,
                                read_paths: Mapping[Path, Path] | None = None) -> None:
    """Verify the complete declared generation, reading staged or final bytes.

    Manifest paths always identify final destinations; read_paths only selects
    the source bytes for pre-publication checks. The GUI supplies ALL_STAGES so
    a valid single-direction run cannot masquerade as a completed all job.
    """
    aliases = {path.resolve(): source for path, source in (read_paths or {}).items()}
    try:
        _validate_generation(post_dir, output_dir, expected_input_sha256, stage,
                             expected_stages, aliases)
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError(f"FrameWeb成果物を読み込めません: {exc}") from exc


def _validate_direction(metadata: dict, *, stage: str, output_dir: Path, post_dir: Path,
                        expected_sha: str, aliases: Mapping[Path, Path]) -> None:
    from .frameweb_export import validate_frameweb_input
    spec = _spec(stage)
    native, sidecar = frameweb_paths(post_dir, stage=stage)
    paths = {"native": native,
             "result_json": Path(output_dir) / f"{spec.output_stem}.json",
             "result_pdf": Path(output_dir) / f"{spec.output_stem}.pdf"}
    if (metadata.get("convention_version") != spec.convention_version
            or not isinstance(metadata.get("correspondence"), dict)):
        raise InputError(f"FrameWeb付帯JSONの形式・規約版が不正です: {sidecar}")
    if metadata.get("provenance", {}).get("input_sha256") != expected_sha:
        raise InputError(f"入力SHAが一致しないFrameWeb付帯JSONです: {sidecar}")
    contents = {key: _read(path, aliases) for key, path in paths.items()}
    for key, path in paths.items():
        expected = metadata.get("artifacts", {}).get(key, {})
        if (expected.get("file") != path.name
                or expected.get("sha256") != hashlib.sha256(contents[key]).hexdigest()):
            raise InputError(f"FrameWeb成果物のSHAが一致しません: {path}")
    result = json.loads(contents["result_json"].decode("utf-8-sig"))
    if result.get("provenance", {}).get("input_sha256") != expected_sha:
        raise InputError(f"入力SHAが一致しない{stage}計算結果です: {paths['result_json']}")
    direction = result.get("direction", result.get("frame", {}).get("spring_provenance", {}).get("direction"))
    if result.get("stage") != stage or direction != spec.direction:
        raise InputError(f"計算段階・方向が一致しないFrameWeb計算結果です: {paths['result_json']}")
    document = json.loads(contents["native"].decode("utf-8-sig"))
    validate_frameweb_input(document, stage=stage)


def _validate_job_manifest(metadata: dict, *, sidecar: Path, stage: str,
                           output_dir: Path, post_dir: Path,
                           expected_stages: Sequence[str] | None,
                           aliases: Mapping[Path, Path]) -> tuple[dict[str, Path], dict[str, Path]]:
    selected = metadata.get("selected_stages")
    if (metadata.get("schema_version") != 2 or not isinstance(selected, list)
            or any(not isinstance(item, str) for item in selected)
            or stage not in selected or (expected_stages is not None and selected != list(expected_stages))
            or not isinstance(metadata.get("publication_id"), str) or not metadata["publication_id"].strip()):
        raise InputError(f"FrameWeb公開ジョブの形式・計算段階・publication_idが不正です: {sidecar}")
    declared, sidecars = publication_paths(output_dir, post_dir, selected)
    expected_manifest = build_artifact_manifest(declared, read_paths=aliases)
    expected_sidecars = [{"role": role, "path": str(path.resolve())} for role, path in sidecars.items()]
    if metadata.get("artifact_manifest") != expected_manifest or metadata.get("expected_sidecars") != expected_sidecars:
        raise InputError(f"FrameWeb公開ジョブのmanifest・SHA・成果物集合が一致しません: {sidecar}")
    return declared, sidecars


def _validate_peer_metadata(peer: object, metadata: dict, *, peer_stage: str, path: Path) -> None:
    if (not isinstance(peer, dict) or peer.get("schema_version") != 2
            or peer.get("stage") != peer_stage or peer.get("direction") != _spec(peer_stage).direction
            or any(peer.get(key) != metadata.get(key) for key in (
                "publication_id", "selected_stages", "artifact_manifest", "expected_sidecars"))):
        raise InputError(f"FrameWeb付帯JSONの公開世代・方向が一致しません: {path}")


def _validate_generation(post_dir: Path, output_dir: Path, expected_sha: str, stage: str,
                         expected_stages: Sequence[str] | None, aliases: Mapping[Path, Path]) -> None:
    _, sidecar = frameweb_paths(post_dir, stage=stage)
    metadata = json.loads(_read(sidecar, aliases).decode("utf-8-sig"))
    if not isinstance(metadata, dict):
        raise InputError(f"FrameWeb付帯JSONの形式が不正です: {sidecar}")
    if metadata.get("schema_version") == 1:
        if stage != "0610" or (expected_stages is not None and tuple(expected_stages) != ("0610",)):
            raise InputError("schema1の付帯JSONは0610単独の確認に限定されます")
        _validate_direction(metadata, stage=stage, output_dir=output_dir, post_dir=post_dir,
                            expected_sha=expected_sha, aliases=aliases)
        return
    declared, sidecars = _validate_job_manifest(
        metadata, sidecar=sidecar, stage=stage, output_dir=output_dir, post_dir=post_dir,
        expected_stages=expected_stages, aliases=aliases)
    for role, path in declared.items():
        if role.endswith(".result_json"):
            result = json.loads(_read(path, aliases).decode("utf-8-sig"))
            if result.get("provenance", {}).get("input_sha256") != expected_sha:
                raise InputError(f"入力SHAが一致しない計算結果です: {path}")
    for role, path in sidecars.items():
        peer = json.loads(_read(path, aliases).decode("utf-8-sig"))
        peer_stage = role.split(".")[0]
        _validate_peer_metadata(peer, metadata, peer_stage=peer_stage, path=path)
        _validate_direction(peer, stage=peer_stage, output_dir=output_dir, post_dir=post_dir,
                            expected_sha=expected_sha, aliases=aliases)
