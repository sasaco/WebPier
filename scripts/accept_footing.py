"""Acceptance of the 0800 / 0810 / 0820 フーチングの照査 with the real runners (decision 60).

A whole generation of every 出力項目 but the cantilever (decision 72) is prepared, not published, in a temporary folder
from tests/fixtures/inputs/current.json (the Example2 input) with the sample's footing bars (12_フーチング.pdf 255・258:
D25@125 中心 100、D29@125 中心 127、D16 2本/m@250、SD390、f'ck 27), as ``python -m webpier`` runs it: the real FrameWebforCS.Headless analyzes the 0610 / 0620 frames, JRSNAP.Headless the
0710 / 0720 NDUs, AggreSE.Headless checks them and returns the step tables, and WebDanforCS.Headless checks the two
footing WDJs. Recorded in tests/fixtures/acceptance/footing/record.json and compared:

- the four non-seismic columns of each direction (the combination and the Vd・Hd・Md 0800 reads from the real
  reactions) with the sample 244 / 249: 線路方向 within 0.25 kN (kN m) as 0612's acceptance, but the Vd of the 使用性
  columns within 0.5 kN (the sample rounds hidden intermediates; owner 2026-10-19); 線路直角方向 only Vd (WebPier's
  0620 wind differs from the sample's: decisions 12, 35);
- the Rvd到達ステップ of each direction (Case, step, Vd・Hd・Md, Rvd), recorded beside the sample's 10-23 / 11-24
  values (its step 31 is JRSNAP's output list number; the input's Df 4.70 differs from the sample's 3.78, so the step
  and the forces need not agree) and the design forces of the chosen overhang (Md, Vd, La of every column);
- the capacities Capacita prints for 安全性（破壊）の曲げ (Mud) and 復旧性（地震時）の曲げ (Myd) of each WDJ: the
  線路方向 Mud must be the sample's 255 (3670.5 kN m) within 0.2 % (the same section, bars and N'd 0; the ratios
  differ with the forces).

tests/acceptance checks that the record still belongs to the current generator (the input and the files the
engines were given). The values and the judgements are the engines' (ADR-0006〜0009).

    uv run --project "." --locked python -X utf8 scripts/accept_footing.py
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile

import pymupdf

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from webpier.core.integrity import canonical_sha256, dump_json, load_json, sha256  # noqa: E402
from webpier.pipeline import aggrese, capacita, fempython, generate, jrsnap  # noqa: E402
from webpier.inputs.outputs import OUTPUT_KEYS  # noqa: E402
from webpier.pipeline.generate import GenerationOptions  # noqa: E402
from webpier.pipeline.runtime import dependency_hashes  # noqa: E402

INPUT = "tests/fixtures/inputs/current.json"
RECORDS = PROJECT / "tests" / "fixtures" / "acceptance" / "footing"
SAMPLE = PROJECT / "tests" / "fixtures" / "example2" / "footing.json"
TOLERANCE = 0.25  # kN, kN m: the sample's hidden digits (as scripts/accept_foundation_check.py)
SERVICE_VD_TOLERANCE = 0.5  # kN: the Vd of the 使用性 columns (owner 2026-10-19)
SERVICE = ("short_term", "long_term")
CAPACITY_TOLERANCE = 0.002  # the sample's WebDan and the current Capacita (as scripts/accept_capacita_column.py)
SAMPLE_MUD = {"0810": 3670.5}  # 12_フーチング.pdf 255: Mud of 安全性（破壊）の曲げ, 線路方向
NON_SEISMIC = ("safety_moment", "safety_shear", "short_term", "long_term")
# direction: (the sample's key, its page, the actions compared, the seismic page, the check stage, the WDJ stem)
DIRECTIONS = {"longitudinal": ("0800_longitudinal", "244", ("vd", "hd", "md"), "10-23", "0810", "線路方向フーチング"),
              "transverse": ("0800_transverse", "249", ("vd",), "11-24", "0820", "線路直角方向フーチング")}
# (section: label of the ratio, label of the capacity) on the first result page of Capacita's section
CHECKS = {"bending_safety_destruction": ("γi･Md/Mud", "Mud (kN･m)"),
          "bending_restorability_eq": ("γi･Md/Myd", "Myd (kN･m)")}
# The sample's footing bars (12_フーチング.pdf 255・258); current.json itself keeps 鉄筋.フーチング blank.
_BARS = {"diameter_mm": None, "pitch_mm": None, "cover_mode": "自動", "center_mm": None, "inner_layers": []}
_STIRRUP = {"diameter_mm": 16, "pitch_mm": 250, "distribution_mode": "密度", "width_pitch_mm": None, "density_per_m": 2}
FOOTING = {
    "materials": {"main": "SD390", "transverse": "SD390"}, "concrete_strength_mpa": 27, "aggregate_max_mm": 25,
    "pure_cover_mm": None,
    "faces": {"上": {"outer_direction": "線路", "線路": _BARS, "直角": _BARS},
              "下": {"outer_direction": "線路",
                     "線路": {**_BARS, "diameter_mm": 25, "pitch_mm": 125, "cover_mode": "指定", "center_mm": 100},
                     "直角": {**_BARS, "diameter_mm": 29, "pitch_mm": 125, "cover_mode": "指定", "center_mm": 127}}},
    "stirrups": {"線路": _STIRRUP, "直角": _STIRRUP}}


class AcceptanceError(RuntimeError):
    """The acceptance did not hold; no record is written."""


def footing_input(directory: Path) -> tuple[Path, bytes]:
    """current.json with the sample's footing bars, written as the generation's input with every 出力項目 but the
    cantilever; and the recorded input, the same without the 出力項目 (no condition of the calculation, ADR-0011)."""
    data = load_json((PROJECT / INPUT).read_bytes())
    del data["outputs"]
    data["鉄筋"]["フーチング"] = FOOTING
    recorded = dump_json(data)
    data["outputs"] = {key: key != "cantilever" for key in OUTPUT_KEYS}
    directory.mkdir(parents=True)
    path = directory / "input.json"
    path.write_bytes(dump_json(data))
    return path, recorded


def _after(lines: list[str], label: str) -> str:
    """The value printed on the line after *label* (the first word: "0.132 ≦ 1.0" → "0.132")."""
    try:
        return lines[lines.index(label) + 1].split()[0]
    except (ValueError, IndexError) as exc:
        raise AcceptanceError(f"「{label}」が計算書にありません") from exc


def _number(printed) -> float:
    return printed.value


def _columns(found, sample: dict, compared: tuple[str, ...], failures: list[str], label: str) -> dict:
    columns = {}
    for column in found.columns:
        source = column.source
        ours = {"vd": _number(column.vd), "hd": _number(column.hd), "md": _number(column.md),
                "chosen": found.basis.sides[column.chosen].name,
                "design": {"md": _number(column.forces.md), "vd": _number(column.forces.vd),
                           "la": _number(column.forces.la)}}
        if column.key in NON_SEISMIC:
            expected = sample[column.key]
            ours["combination"] = source.combination
            differences = {key: round(ours[key] - expected[key.capitalize()], 2) for key in ("vd", "hd", "md")}
            columns[column.key] = {"ours": ours, "sample": {key: expected[key] for key in ("Vd", "Hd", "Md")},
                                   "differences": differences}
            failures += [f"{label} {column.key}: {key} の差 {differences[key]}" for key in compared
                         if abs(differences[key]) > (SERVICE_VD_TOLERANCE if key == "vd" and column.key in SERVICE
                                                     else TOLERANCE)]
        else:
            ours |= {"case_index": source.case_index, "case_name": source.case_name, "step": source.step,
                     "rvd": _number(source.rvd)}
            columns[column.key] = {"ours": ours, "sample": {key: sample[column.key][key] for key in ("Vd", "Hd", "Md")}}
    return columns


def _capacities(name: str, wdj: bytes, sections, runner: Path) -> dict:
    """The ratio and the capacity Capacita prints on the first page of each section of CHECKS."""
    pages = capacita.check_section(wdj, f"{name}.wdj", runner, sections)
    values = {}
    with pymupdf.open(stream=pages.pdf, filetype="pdf") as document:
        for section, (ratio, capacity) in CHECKS.items():
            first, _ = pages.section(section)
            lines = [line.strip() for line in document[first - 1].get_text().splitlines() if line.strip()]
            values[section] = {"page": first, "ratio": _after(lines, ratio), "capacity": _after(lines, capacity)}
    return {"engine_version": pages.engine_version, "sections": values}


def main() -> int:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))["directions"]
    runners = {"fempython": fempython.runner_path(), "jrsnap": jrsnap.runner_path(),
               "aggrese": aggrese.runner_path(), "capacita": capacita.runner_path()}
    with tempfile.TemporaryDirectory(prefix="webpier-accept-footing-") as temp:
        root = Path(temp)
        source, input_bytes = footing_input(root / "pre")
        options = GenerationOptions(source, root / "output", root / "post")
        with generate.prepare(options) as candidate:
            result = candidate.results["0800"]
            given = {stage: candidate.staged(f"{stage}.wdj").read_bytes() for stage in ("0810", "0820")}
            checks = {stage: candidate.results[stage] for stage in ("0810", "0820")}
            engines = {"frameweb": {name: sha256(candidate.staged(f"{stage}.frameweb").read_bytes())
                                    for stage, name in (("0610", "線路方向.json"), ("0620", "線路直角方向.json"))},
                       "reaction": {name: sha256(candidate.staged(f"{stage}.reaction").read_bytes())
                                    for stage, name in (("0611", "線路方向_ピックアップ反力.csv"),
                                                        ("0621", "線路直角方向_ピックアップ反力.csv"))},
                       "ndu": {name: sha256(candidate.staged(f"{stage}.jrsnap").read_bytes())
                               for stage, name in (("0710", "線路方向.ndu"), ("0720", "線路直角方向.ndu"))},
                       "steps": {name: sha256(candidate.staged(f"{stage}.steps").read_bytes())
                                 for stage, name in (("0711", "線路方向_Aggre-SE_直接基礎.csv"),
                                                     ("0721", "線路直角方向_Aggre-SE_直接基礎.csv"))}}
            input_sha256 = sha256(input_bytes)
    failures: list[str] = []
    directions = {}
    for direction, (key, page, compared, seismic_page, stage, name) in DIRECTIONS.items():
        found = getattr(result, direction)
        columns = _columns(found, sample[key]["columns"], compared, failures, direction)
        capacities = _capacities(name, given[stage], checks[stage].sections, runners["capacita"])
        if stage in SAMPLE_MUD:
            mud = float(capacities["sections"]["bending_safety_destruction"]["capacity"])
            if abs(mud - SAMPLE_MUD[stage]) / SAMPLE_MUD[stage] >= CAPACITY_TOLERANCE:
                failures.append(f"{stage}: Mud {mud}（見本 255 は {SAMPLE_MUD[stage]}）")
        directions[direction] = {"sample_page": page, "seismic_sample_page": seismic_page, "compared": list(compared),
                                 "node": found.basis.node, "columns": columns,
                                 "check": {"stage": stage, "wdj": {"file": f"{name}.wdj", "sha256": sha256(given[stage])},
                                           **capacities}}
    RECORDS.mkdir(parents=True, exist_ok=True)
    (RECORDS / "input.json").write_bytes(input_bytes)
    record = {
        "schema_version": 1, "kind": "footing_acceptance",
        "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": ("current.json に見本の配筋（鉄筋.フーチング）を足した入力で片持ち梁以外の出力項目の生成を"
                   "本物の4つの runner で一時フォルダーに用意し（公開しない）、0800 の5列（反力の組合せと Vd・Hd・Md、Rvd到達"
                   "ステップ、採った張出しの Md・Vd・La）と 0810・0820 の WDJ を Capacita が照査した耐力を記録し、見本と比べた。"),
        "input": {"path": INPUT, "footing_bars": FOOTING, "file": "input.json", "sha256": input_sha256},
        "implementation_sha256": canonical_sha256({str(path): digest for path, digest in dependency_hashes().items()}),
        "runners": {name: str(path) for name, path in runners.items()},
        "engines": engines, "tolerance": TOLERANCE, "service_vd_tolerance": SERVICE_VD_TOLERANCE,
        "capacity_tolerance": CAPACITY_TOLERANCE,
        "sample_mud": SAMPLE_MUD, "directions": directions, "accepted": not failures, "failures": failures,
    }
    (RECORDS / "record.json").write_bytes(dump_json(record))
    print(json.dumps({"accepted": not failures, "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
