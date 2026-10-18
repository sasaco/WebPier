"""The command line of one generation (``python -m webpier``).

``--frame-analysis`` adds the opt-in stages of the FEMPython frame analysis (0611, 0621, decision 46) and
``--nonlinear-analysis`` those of the JRSNAP static nonlinear analysis (0711, 0721, decision 47; with Aggre-SE's
耐震性能照査 as their report, decision 56) to ``--stage all``;
such a stage chosen directly with ``--stage`` needs no flag.

Exit codes: 0 published; 2 the input, a destination or the environment prevents the generation
(``InputError``, ``GenerationError``, ``OSError``) and nothing was published; 3 publication failed and not
every old file could be restored (``RecoveryError``; the message names the retained backups). Any other
exception is a bug and ends with its traceback.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..core.errors import InputError
from .generate import GenerationError, GenerationOptions, generate
from .publication import RecoveryError
from .stages import ALL, FRAME_ANALYSIS, NONLINEAR_ANALYSIS, STAGES, Registry, flag

PROJECT_DIR = Path(__file__).resolve().parents[2]
EXIT_ERROR = 2
EXIT_RECOVERY = 3
_REPORT_LABELS = {"pdf": "計算書", "json": "計算結果"}


def parser(registry: Registry) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="python -m webpier",
                                     description="入力JSONから橋脚の計算書・計算結果と解析入力を作成します。")
    result.add_argument("--input", type=Path, default=PROJECT_DIR / "pre" / "input.json", help="入力JSON")
    result.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "output", help="計算書・計算結果の出力先")
    result.add_argument("--post-dir", type=Path, help="解析入力と付帯JSONの出力先（既定: 出力先と並ぶ post）")
    result.add_argument("--stage", choices=registry.choices, default=ALL, help=f"計算段階（既定: {ALL}）")
    result.add_argument(flag(FRAME_ANALYSIS), action="store_true",
                        help=f"--stage {ALL} に選択式の段階（{'・'.join(registry.opt_in(FRAME_ANALYSIS))}）を加える。"
                             "FEMPython で骨組解析し、ピックアップ断面力・変位量・反力を解析入力の出力先に書く")
    result.add_argument(flag(NONLINEAR_ANALYSIS), action="store_true",
                        help=f"--stage {ALL} に選択式の段階（{'・'.join(registry.opt_in(NONLINEAR_ANALYSIS))}）を加える。"
                             "JRSNAP で静的非線形解析し、解析用データと解析結果を解析入力の出力先のフォルダーに書き、"
                             "Aggre-SE で耐震性能照査した帳票を計算書にし、そのピックアップ（PIK）を解析入力の出力先に書く")
    result.add_argument("--overwrite", action="store_true", help="既存の出力を上書きする")
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
                *((spec.seismic_check.kind,) if spec.seismic_check is not None else ())}
    native = "解析結果" if kind in returned else "入力"
    return f"{stage} {kind}{'付帯JSON' if sidecar else native}"


def main(argv: list[str] | None = None, *, registry: Registry = STAGES) -> int:
    arguments = parser(registry).parse_args(argv)
    options = GenerationOptions(
        arguments.input, arguments.output_dir, post_dir(arguments.output_dir, arguments.post_dir),
        stage=arguments.stage, overwrite=arguments.overwrite, frame_analysis=arguments.frame_analysis,
        nonlinear_analysis=arguments.nonlinear_analysis)
    try:
        generation = generate(options, registry=registry)
    except RecoveryError as exc:
        print(f"復旧が必要です: {exc}", file=sys.stderr)
        return EXIT_RECOVERY
    except (InputError, GenerationError, OSError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return EXIT_ERROR
    for artifact in generation.artifacts:
        print(f"{_label(artifact.role, registry)}: {artifact.path.resolve()}")
    return 0
