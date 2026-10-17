"""Calculate selected WebPier stages and publish their PDF/JSON together."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from gridlayoutpdf import LayoutError

from .artifact_publication import (
    ArtifactStaging,
    validate_destinations,
)
from .artifact_publication import (
    RecoveryError as _RecoveryError,  # noqa: F401 - legacy import used by callers
)
from .artifact_publication import (
    publish_outputs as _publish_outputs,
)
from .calculator import calculate
from .frameweb_artifacts import (
    ALL_STAGES,
    FRAMEWEB_STAGES,
    REPORT_STEMS,
    build_artifact_manifest,
    build_provenance,
    frameweb_paths,
    publication_paths,
    resolve_post_dir,
    validate_frameweb_artifacts,
)
from .frameweb_artifacts import (
    LONGITUDINAL_OUTPUT_STEM as LONGITUDINAL_OUTPUT_STEM,  # noqa: PLC0414 - public compatibility export
)
from .frameweb_artifacts import (
    TRANSVERSE_OUTPUT_STEM as TRANSVERSE_OUTPUT_STEM,  # noqa: PLC0414 - public compatibility export
)
from .frameweb_export import build_frameweb_input, validate_frameweb_input
from .inputs import InputError, parse_input
from .jrsnap_artifacts import (
    JRSNAP_STAGES,
    build_jrsnap_provenance,
    canonical_sha256,
    file_sha256,
    implementation_hashes,
    jrsnap_paths,
    load_json_bytes,
    validate_jrsnap_artifacts,
)
from .longitudinal_calculator import calculate_longitudinal
from .longitudinal_design_conditions import parse_longitudinal_design_conditions
from .reaction_calculator import calculate_reactions
from .reaction_inputs import parse_reaction_input
from .seismic_longitudinal_calculator import calculate_seismic_longitudinal
from .seismic_transverse_calculator import calculate_seismic_transverse
from .transverse_calculator import calculate_transverse

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_STEM = "0500_直接基礎"
REACTION_OUTPUT_STEM = "0600_上部工反力"


@dataclass(frozen=True)
class GenerationOptions:
    input_path: Path
    output_dir: Path
    post_dir: Path | None = None
    stage: str = "0710"
    overwrite: bool = False
    jrsnap: bool = False


def _file_state(path: Path) -> tuple | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise InputError(f"通常ファイルではありません: {path}")
    identity = (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)
    digest = file_sha256(path)
    after = path.lstat()
    if identity != (after.st_dev, after.st_ino, after.st_mode, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns):
        raise InputError(f"検証中にファイルが変更されました: {path}")
    return (*identity, digest)


@dataclass(frozen=True)
class GenerationCandidate:
    """A held generation. App acceptance may read/copy it but never regenerate it."""

    options: GenerationOptions
    stages: tuple[str, ...]
    input_bytes: bytes
    input_sha256: str
    computed: dict
    publication_id: str
    ndu_models: Mapping[str, dict]
    declared: Mapping[str, Path]
    sidecars: Mapping[str, Path]
    pairs: tuple[tuple[Path, Path], ...]
    read_paths: Mapping[Path, Path]
    artifact_hashes: Mapping[Path, str]
    source_hashes: Mapping[Path, str]
    canonical_snapshot_sha256: Mapping[str, str]
    _computed_sha256: Mapping[str, str] = field(repr=False)
    _model_sha256: str | None = field(repr=False)
    _baseline: Mapping[Path, tuple | None] = field(repr=False)
    _staging: ArtifactStaging = field(repr=False)
    _verify: Callable = field(repr=False)
    _active: bool = field(default=True, init=False, repr=False)
    _used: bool = field(default=False, init=False, repr=False)
    _published: bool = field(default=False, init=False, repr=False)
    _validated: bool = field(default=False, init=False, repr=False)

    @property
    def _selected_ndu_stage(self) -> str | None:
        """Keep the historical singular view longitudinal for an all job."""
        return "0710" if "0710" in self.ndu_models else next(iter(self.ndu_models), None)

    @property
    def ndu_model(self) -> dict | None:
        return self.ndu_models.get(self._selected_ndu_stage)

    @property
    def ndu_paths(self) -> Mapping[str, Path]:
        return MappingProxyType({stage: self.declared[f"{stage}.jrsnap"] for stage in self.ndu_models})

    @property
    def metadata_by_stage(self) -> Mapping[str, dict]:
        return MappingProxyType({stage: deepcopy(model["metadata"]) for stage, model in self.ndu_models.items()})

    @property
    def metadata(self) -> dict:
        return deepcopy(self.ndu_model["metadata"]) if self.ndu_model is not None else {}

    @property
    def ndu_path(self) -> Path | None:
        return self.ndu_paths.get(self._selected_ndu_stage)

    @property
    def published(self) -> bool:
        return self._published

    def _validate_sources(self) -> None:
        if file_sha256(self.options.input_path) != self.input_sha256:
            raise InputError("候補生成後に入力が変更されました。再生成してください")
        if _rendering_identity() != dict(self.source_hashes):
            raise InputError("候補生成後にプログラム・profile・描画依存が変更されました。再生成してください")
        try:
            changed = ({stage: canonical_sha256(value) for stage, value in self.computed.items()}
                       != dict(self._computed_sha256))
            if self.options.jrsnap:
                changed |= (canonical_sha256(dict(self.ndu_models)) != self._model_sha256
                            or {stage: canonical_sha256(self.computed[stage])
                                for stage in ("0500", *self.ndu_models)}
                            != dict(self.canonical_snapshot_sha256))
        except (KeyError, TypeError, ValueError) as exc:
            raise InputError("保持したモデル・計算スナップショットを読み込めません") from exc
        if changed:
            raise InputError("保持したモデル・profile・計算スナップショットが変更されています")

    def _validate_hashes(self, aliases: Mapping[Path, Path]) -> None:
        for path, expected in self.artifact_hashes.items():
            actual = aliases.get(path, path)
            state = _file_state(actual)
            if state is None or state[-1] != expected:
                raise InputError(f"保持した候補のSHAが一致しません: {path}")

    def validate_unchanged(self) -> None:
        if not self._active or self._used:
            raise InputError("候補の保持期間が終了したか、既に公開を試行しています")
        expected = set(self.read_paths.values())
        actual = {path for directory in self._staging.directories.values()
                  for path in directory.rglob("*")}
        if actual != expected:
            raise InputError("保持した候補のファイル集合が変更されています")
        self._validate_hashes(self.read_paths)
        for path, before in self._baseline.items():
            if _file_state(path) != before:
                raise InputError(f"候補生成後に出力先が変更されました: {path}")
        # The default CLI preserves its single staged semantic check; hashes
        # prove those validated bytes are still held on subsequent calls.
        if self.options.jrsnap or not self._validated:
            self._verify(self.read_paths)
            object.__setattr__(self, "_validated", True)
        # Re-read input/runtime after semantic validation. There is no further
        # calculation/rendering here, so one complete read at this boundary
        # protects the candidate without duplicate network-package hashing.
        self._validate_sources()
        self._validate_hashes(self.read_paths)

    def _validate_backups(self) -> None:
        # The publisher keeps these backups until final validation completes.
        # Check here as well as before publish: a writer may finish in between.
        for path, before in self._baseline.items():
            backup = self._staging.directories[path.parent.resolve()] / (path.name + ".backup")
            captured = _file_state(backup)
            if before is None:
                unchanged = captured is None
            else:
                # Rename may change ctime. Content and file identity must agree.
                unchanged = captured is not None and captured[:5] == before[:5] and captured[-1] == before[-1]
            if not unchanged:
                raise InputError(f"公開開始時に出力先の競合変更を検出しました: {path}")

    def publish(self) -> None:
        self.validate_unchanged()
        object.__setattr__(self, "_used", True)

        def final_verify():
            self._validate_hashes({})
            self._validate_backups()
            self._verify()
            self._validate_sources()
            self._validate_hashes({})

        _publish_outputs(list(self.pairs), self._staging.directories,
                         self.options.overwrite, final_validator=final_verify)
        object.__setattr__(self, "_published", True)


def _calculate_stages(data: dict, stages: tuple[str, ...], input_file: str, input_sha256: str) -> dict:
    computed = {}
    if any(stage in stages for stage in ("0500", "0610", "0620", "0710", "0720")):
        computed["0500"] = calculate(parse_input(data))
    if any(stage in stages for stage in ("0600", "0610", "0620", "0710", "0720")):
        reaction_inputs = parse_reaction_input(data)
        computed["0600"] = calculate_reactions(reaction_inputs)
    for result in computed.values():
        result["provenance"].update(input_file=input_file, input_sha256=input_sha256)
    if any(stage in stages for stage in ("0610", "0710")):
        computed["0610"] = calculate_longitudinal(
            reaction_inputs, computed["0500"], computed["0600"],
            design_conditions=parse_longitudinal_design_conditions(data),
        )
        computed["0610"]["provenance"].update(input_file=input_file, input_sha256=input_sha256)
    if any(stage in stages for stage in ("0620", "0720")):
        computed["0620"] = calculate_transverse(
            reaction_inputs, computed["0500"], computed["0600"],
            design_conditions=parse_longitudinal_design_conditions(data),
        )
        computed["0620"]["provenance"].update(input_file=input_file, input_sha256=input_sha256)
    if "0710" in stages:
        computed["0710"] = calculate_seismic_longitudinal(computed["0610"])
        computed["0710"]["provenance"].update(input_file=input_file, input_sha256=input_sha256)
    if "0720" in stages:
        computed["0720"] = calculate_seismic_transverse(reaction_inputs, computed["0600"], computed["0620"])
        computed["0720"]["provenance"].update(input_file=input_file, input_sha256=input_sha256)
    return computed


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _render_reports(computed, stages, output_dir, staging):
    # All selected calculations must succeed before any report is generated.
    from .longitudinal_report import render_longitudinal_report
    from .reaction_report import render_reaction_report
    from .report import render_report
    from .seismic_longitudinal_report import render_seismic_longitudinal_report
    from .seismic_transverse_report import render_seismic_transverse_report
    from .transverse_report import render_transverse_report

    renderers = {"0500": render_report, "0600": render_reaction_report,
                 "0610": render_longitudinal_report, "0620": render_transverse_report,
                 "0710": render_seismic_longitudinal_report,
                 "0720": render_seismic_transverse_report}
    pairs = []
    for stage in stages:
        result = computed[stage]
        pdf_path = output_dir / f"{REPORT_STEMS[stage]}.pdf"
        json_path = pdf_path.with_suffix(".json")
        staged_pdf, staged_json = staging.path_for(pdf_path), staging.path_for(json_path)
        try:
            renderers[stage](result, staged_pdf)
        except (ValueError, LayoutError) as exc:
            raise InputError(f"{stage}帳票を作成できません: {exc}") from exc
        _write_json(staged_json, result)
        pairs.extend(((staged_pdf, pdf_path), (staged_json, json_path)))
    return pairs


def _rendering_identity() -> dict[Path, str]:
    try:
        return implementation_hashes()
    except (ValueError, LayoutError, OSError) as exc:
        raise InputError(f"帳票の描画依存を検証できません: {exc}") from exc


@contextmanager
def prepare_generation(options: GenerationOptions) -> Iterator[GenerationCandidate]:
    """Calculate once, hold exact validated bytes, and leave publication to caller."""
    if options.stage not in (*ALL_STAGES, "all"):
        raise InputError(f"計算段階が不正です: {options.stage}")
    if options.jrsnap and options.stage not in (*JRSNAP_STAGES, "all"):
        raise InputError("--jrsnap は --stage 0710、0720 または all で指定してください")
    stages = ALL_STAGES if options.stage == "all" else (options.stage,)
    ndu_stages = tuple(stage for stage in JRSNAP_STAGES if stage in stages) if options.jrsnap else ()
    output_dir = Path(options.output_dir)
    post_dir = resolve_post_dir(output_dir, options.post_dir)
    source_hashes = _rendering_identity()
    fw_declared, fw_sidecars = publication_paths(output_dir, post_dir, stages)
    declared, sidecars = dict(fw_declared), dict(fw_sidecars)
    for stage in ndu_stages:
        declared[f"{stage}.jrsnap"], sidecars[f"{stage}.jrsnap_sidecar"] = jrsnap_paths(post_dir, stage=stage)
    destinations = [*declared.values(), *sidecars.values()]
    validate_destinations(destinations, overwrite=options.overwrite, input_path=options.input_path)
    baseline = {path: _file_state(path) for path in destinations}
    input_bytes = Path(options.input_path).read_bytes()
    try:
        data = load_json_bytes(input_bytes) if options.jrsnap else json.loads(input_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"JSONを読み込めません: {exc}") from exc
    input_digest = hashlib.sha256(input_bytes).hexdigest()
    computed = _calculate_stages(data, stages, Path(options.input_path).name, input_digest)
    frameweb = {stage: build_frameweb_input(computed[stage]) for stage in stages if stage in FRAMEWEB_STAGES}
    models, native_bytes = {}, {}
    if options.jrsnap:
        from .jrsnap_export import (
            build_longitudinal_ndu_model,
            build_transverse_ndu_model,
        )
        from .jrsnap_ndu import serialize_ndu
        builders = {"0710": build_longitudinal_ndu_model, "0720": build_transverse_ndu_model}
        for stage in ndu_stages:
            models[stage] = builders[stage](data, computed["0500"], computed[stage], input_sha256=input_digest)
            native_bytes[stage] = serialize_ndu(models[stage])
    snapshots = ({stage: canonical_sha256(computed[stage]) for stage in ("0500", *ndu_stages)}
                 if options.jrsnap else {})
    computed_hashes = {stage: canonical_sha256(value) for stage, value in computed.items()}
    publication_id = uuid.uuid4().hex
    with ArtifactStaging(destinations) as staging:
        pairs = _render_reports(computed, stages, output_dir, staging)
        for stage, exported in frameweb.items():
            native_path, _ = frameweb_paths(post_dir, stage=stage)
            staged_native = staging.path_for(native_path)
            _write_json(staged_native, exported.document)
            validate_frameweb_input(json.loads(staged_native.read_text(encoding="utf-8")), stage=stage)
            pairs.append((staged_native, native_path))
        for stage in ndu_stages:
            native_path = declared[f"{stage}.jrsnap"]
            staging.path_for(native_path).write_bytes(native_bytes[stage])
            pairs.append((staging.path_for(native_path), native_path))
        read_paths = {path: staging.path_for(path) for path in destinations}
        # Preserve FrameWeb's existing schema-2 artifact set exactly.
        manifest = build_artifact_manifest(fw_declared, read_paths=read_paths)
        expected_sidecars = [{"role": role, "path": str(path.resolve())} for role, path in fw_sidecars.items()]
        for stage, exported in frameweb.items():
            native_path, provenance_path = frameweb_paths(post_dir, stage=stage)
            provenance = build_provenance(
                input_sha256=input_digest, input_file=Path(options.input_path).name,
                native_path=staging.path_for(native_path),
                result_json_path=staging.path_for(fw_declared[f"{stage}.result_json"]),
                result_pdf_path=staging.path_for(fw_declared[f"{stage}.result_pdf"]),
                correspondence=exported.source_mapping, stage=stage, publication_id=publication_id,
                selected_stages=stages, artifact_manifest=manifest, expected_sidecars=expected_sidecars,
            )
            _write_json(staging.path_for(provenance_path), provenance)
            pairs.append((staging.path_for(provenance_path), provenance_path))
        for stage in ndu_stages:
            provenance_path = sidecars[f"{stage}.jrsnap_sidecar"]
            provenance = build_jrsnap_provenance(
                output_dir=output_dir, post_dir=post_dir, input_sha256=input_digest,
                input_file=Path(options.input_path).name, foundation=computed["0500"],
                seismic=computed[stage], model=models[stage], publication_id=publication_id,
                selected_stages=stages, source_hashes=source_hashes, read_paths=read_paths, stage=stage,
            )
            _write_json(staging.path_for(provenance_path), provenance)
            pairs.append((staging.path_for(provenance_path), provenance_path))

        def verify(aliases=None):
            if frameweb:
                validate_frameweb_artifacts(post_dir=post_dir, output_dir=output_dir,
                    expected_input_sha256=input_digest, stage=next(iter(frameweb)),
                    expected_stages=stages, read_paths=aliases)
            for stage in ndu_stages:
                validate_jrsnap_artifacts(post_dir=post_dir, output_dir=output_dir,
                    expected_input_sha256=input_digest, expected_stages=stages,
                    expected_publication_id=publication_id,
                    expected_snapshot_sha256={key: snapshots[key] for key in ("0500", stage)},
                    read_paths=aliases, stage=stage)

        candidate = GenerationCandidate(
            options, stages, input_bytes, input_digest, computed, publication_id, MappingProxyType(models),
            MappingProxyType(declared), MappingProxyType(sidecars), tuple(pairs), MappingProxyType(read_paths),
            MappingProxyType({path: file_sha256(source) for path, source in read_paths.items()}),
            MappingProxyType(source_hashes), MappingProxyType(snapshots),
            MappingProxyType(computed_hashes),
            canonical_sha256(models) if models else None, MappingProxyType(baseline), staging, verify,
        )
        try:
            candidate.validate_unchanged()
            yield candidate
        finally:
            object.__setattr__(candidate, "_active", False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JSONから橋脚の計算書と解析入力を作成します。Excelは不要です。")
    parser.add_argument("--input", type=Path, default=PROJECT_DIR / "pre" / "input.json", help="入力JSON")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "output", help="PDF・結果JSONの出力先")
    parser.add_argument("--post-dir", type=Path, help="FrameWeb・JRSNAP入力と付帯JSONの出力先")
    parser.add_argument("--overwrite", action="store_true", help="同名の出力ファイルを上書きする")
    parser.add_argument("--stage", choices=(*ALL_STAGES, "all"), default="all", help="計算段階（既定: all）")
    parser.add_argument("--jrsnap", action="store_true", help="JRSNAP 5.2-L03入力も出力（0710/0720/allのみ）")
    args = parser.parse_args(argv)
    options = GenerationOptions(args.input, args.output_dir, args.post_dir,
                                args.stage, args.overwrite, args.jrsnap)
    try:
        with prepare_generation(options) as candidate:
            candidate.publish()
            for stage in candidate.stages:
                for warning in candidate.computed[stage]["warnings"]:
                    print(f"{stage} 注記: {warning}")
                print(f"{stage} PDF: {candidate.declared[f'{stage}.result_pdf'].resolve()}")
                print(f"{stage} 計算結果: {candidate.declared[f'{stage}.result_json'].resolve()}")
            for stage in candidate.stages:
                if stage in FRAMEWEB_STAGES:
                    print(f"{stage} FrameWeb入力: {candidate.declared[f'{stage}.native'].resolve()}")
                    print(f"{stage} FrameWeb付帯JSON: {candidate.sidecars[f'{stage}.sidecar'].resolve()}")
            for stage, native in candidate.ndu_paths.items():
                print(f"{stage} JRSNAP入力: {native.resolve()}")
                print(f"{stage} JRSNAP付帯JSON: {candidate.sidecars[f'{stage}.jrsnap_sidecar'].resolve()}")
    except (InputError, OSError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2
    return 0
