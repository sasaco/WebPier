"""The command line of one generation (``python -m webpier``).

Which reports it makes is the input's 出力項目 alone (``outputs``, decision 72, ADR-0011); no argument chooses stages.
``--addin <folder>`` calculates with the load model of the add-in (decision 70, pipeline.addin); without it, with the
train's.

Exit codes: 0 published; 2 the input, a destination or the environment prevents the generation
(``InputError``, ``AddinError``, ``GenerationError``, ``OSError``) and nothing was published; 3 publication failed and not
every old file could be restored (``RecoveryError``; the message names the retained backups). Any other
exception is a bug and ends with its traceback.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..core.errors import InputError
from .addin import AddinError
from .generate import GenerationError, GenerationOptions, generate
from .publication import RecoveryError
from .stages import STAGES, Registry

PROJECT_DIR = Path(__file__).resolve().parents[2]
EXIT_ERROR = 2
EXIT_RECOVERY = 3
_REPORT_LABELS = {"pdf": "計算書", "xlsx": "方眼Excel", "json": "計算結果"}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="python -m webpier",
                                     description="入力JSONの出力項目（outputs）の計算書・計算結果と解析入力を作成します。")
    result.add_argument("--input", type=Path, default=PROJECT_DIR / "pre" / "input.json", help="入力JSON")
    result.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "output", help="計算書・計算結果の出力先")
    result.add_argument("--post-dir", type=Path, help="解析入力と付帯JSONの出力先（既定: 出力先と並ぶ post）")
    result.add_argument("--export-dir", type=Path, help="方眼Excel の出力先（既定: 出力先と並ぶ export）")
    result.add_argument("--overwrite", action="store_true", help="既存の出力を上書きする")
    result.add_argument("--addin", type=Path, help="荷重モデルのアドインのフォルダー（なければ列車荷重）")
    return result


def post_dir(output_dir: Path, given: Path | None) -> Path:
    return given if given is not None else Path(output_dir).resolve().parent / "post"


def _label(role: str, registry: Registry) -> str:
    stage, _, rest = role.partition(".")
    if rest in _REPORT_LABELS:
        return f"{stage} {_REPORT_LABELS[rest]}"
    kind, _, sidecar = rest.partition(".")
    spec = registry.get(stage)
    returned = {*(dict(spec.frame_analysis.files) if spec.frame_analysis is not None else ()),
                *((spec.nonlinear_analysis.kind,) if spec.nonlinear_analysis is not None else ()),
                *(dict(spec.seismic_check.files) if spec.seismic_check is not None else ())}
    native = "解析結果" if kind in returned else "入力"
    return f"{stage} {kind}{'付帯JSON' if sidecar else native}"


def main(argv: list[str] | None = None, *, registry: Registry = STAGES) -> int:
    arguments = parser().parse_args(argv)
    options = GenerationOptions(
        arguments.input, arguments.output_dir, post_dir(arguments.output_dir, arguments.post_dir),
        overwrite=arguments.overwrite, addin=arguments.addin, export_dir=arguments.export_dir)
    try:
        generation = generate(options, registry=registry)
    except RecoveryError as exc:
        print(f"復旧が必要です: {exc}", file=sys.stderr)
        return EXIT_RECOVERY
    except (InputError, AddinError, GenerationError, OSError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return EXIT_ERROR
    for artifact in generation.artifacts:
        print(f"{_label(artifact.role, registry)}: {artifact.path.resolve()}")
    return 0
